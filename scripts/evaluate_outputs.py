#!/usr/bin/env python3.12
"""Validate EKLT single-run artifacts and reader-facing plot contracts.

Example:
    from pathlib import Path

    result = evaluate_run(Path("missing"))
    print(result.passed)

Output:
    False
"""

from __future__ import annotations

import argparse
import csv
import json
import math
import re
import shutil
import subprocess
from dataclasses import dataclass, field
from pathlib import Path, PurePosixPath
from typing import Any

from PIL import Image, UnidentifiedImageError

from event_vision_utils.io import load_track_samples


REQUIRED_SUMMARY_KEYS = {
    "schema_version",
    "artifact_type",
    "run_name",
    "status",
    "input",
    "event_count",
    "track_count",
    "track_rows",
    "duration_s",
    "runtime_s",
    "plots",
    "plot_contracts",
    "gt_status",
    "gt_metrics",
}

REQUIRED_TRACK_PLOTS = {
    "active_tracks.png",
    "track_lifetimes.png",
    "reinit_timeline.png",
    "track_xy.png",
}

PROCESSING_TIMING_FIELDS = (
    "packet_index",
    "event_time_s",
    "fibar_ms",
    "eklt_ms",
    "overhead_ms",
    "total_ms",
)
MAX_VIDEO_FRAME_PIXELS = 16_777_216
MAX_VIDEO_FRAMES = 1_000_000


@dataclass(slots=True)
class EvaluationResult:
    """Accumulate acceptance errors without stopping at the first artifact.

    Example:
        result = EvaluationResult(passed=True)
        result.add_error("missing plot")
        print(result.passed, result.errors)

    Output:
        False ['missing plot']
    """

    passed: bool
    errors: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)

    def add_error(self, message: str) -> None:
        """Record one blocking acceptance error.

        Args:
            message: Reader-facing failure description.

        Example:
            result = EvaluationResult(passed=True)
            result.add_error("missing plot")
            print(result.passed)

        Output:
            False
        """
        self.errors.append(message)
        self.passed = False


def evaluate_run(run_dir: str | Path,
                 *,
                 require_tracks: bool = True) -> EvaluationResult:
    """Validate one EKLT component output directory.

    Args:
        run_dir: Directory containing ``summary.json`` and artifacts.
        require_tracks: Whether nonempty track output is mandatory.

    Returns:
        Complete accumulated acceptance result.

    Example:
        result = evaluate_run(Path("missing"))
        print(result.passed)

    Output:
        False
    """
    # Establish the run directory as the trust boundary before reading any
    # manifest-selected artifact path.
    root = Path(run_dir)
    result = EvaluationResult(passed=True)
    if root.is_symlink():
        result.add_error(
            f"run directory must not be a symlink: {root}"
        )
        return result
    if not root.is_dir():
        result.add_error(f"run directory is missing: {root}")
        return result
    root = root.resolve()

    summary_path = root / "summary.json"
    if summary_path.is_symlink():
        result.add_error(
            f"summary.json must not be a symlink: {summary_path}"
        )
        return result
    if not summary_path.is_file():
        result.add_error(f"missing summary.json: {summary_path}")
        return result

    # Parse one strict JSON object first so every subsequent check operates on
    # the same immutable component manifest.
    try:
        summary_value = json.loads(
            summary_path.read_text(
                encoding="utf-8",
                errors="strict",
            )
        )
    except (OSError, UnicodeError, json.JSONDecodeError) as exc:
        result.add_error(f"invalid summary.json: {exc}")
        return result
    if not isinstance(summary_value, dict):
        result.add_error("summary.json must contain one JSON object")
        return result
    summary: dict[str, Any] = summary_value

    # Validate shared scalar fields before selecting the component-specific
    # reconstruction or tracking contract.
    _check_summary_fields(
        summary,
        result,
        expected_artifact_type=(
            "eklt_track_analysis"
            if require_tracks
            else "elope_fibar_reconstruction"
        ),
    )
    if require_tracks:
        _check_tracks(root, summary, result)
    else:
        _check_reconstruction_fields(summary, result)

    # Continue through independent artifact families after errors so one run
    # reports a useful complete acceptance diagnosis.
    _check_plots(
        root,
        summary,
        result,
        require_tracks=require_tracks,
    )
    _check_ground_truth(root, summary, result)
    _check_processing_timing(root, summary, result)
    _check_component_videos(
        root,
        summary,
        result,
        require_tracks=require_tracks,
    )
    return result


def _check_reconstruction_fields(summary: dict[str, Any],
                                 result: EvaluationResult) -> None:
    """Validate reconstruction-specific counts and bounded diagnostics."""
    # Require source identity even though its dataset-specific metadata remains
    # extensible within a JSON object.
    if _nonnegative_integer(summary.get("event_count")) <= 0:
        result.add_error(
            "reconstruction event_count must be positive"
        )
    if (
        not isinstance(summary.get("dataset_adapter"), str) or
        not summary["dataset_adapter"].strip()
    ):
        result.add_error(
            "dataset_adapter must be a nonempty string"
        )
    if not isinstance(summary.get("dataset_metadata"), dict):
        result.add_error(
            "dataset_metadata must contain one JSON object"
        )

    # Cross-check complete and retained patch counts so bounded diagnostic
    # sampling remains explicit rather than silently dropping observations.
    reconstruction_frames = _positive_integer_field(
        summary,
        "reconstruction_frames",
        "summary",
        result,
    )
    patch_frames = _positive_integer_field(
        summary,
        "patch_debug_frames",
        "summary",
        result,
    )
    patch_count = summary.get("patch_quality_count")
    retained_count = summary.get("patch_quality_samples")
    if (
        isinstance(patch_count, bool) or
        not isinstance(patch_count, int) or
        patch_count < 0
    ):
        result.add_error(
            "patch_quality_count must be a nonnegative integer"
        )
    if (
        isinstance(retained_count, bool) or
        not isinstance(retained_count, int) or
        retained_count < 0
    ):
        result.add_error(
            "patch_quality_samples must be a nonnegative integer"
        )
    if (
        isinstance(patch_count, int) and
        not isinstance(patch_count, bool) and
        isinstance(retained_count, int) and
        not isinstance(retained_count, bool)
    ):
        if retained_count > patch_count:
            result.add_error(
                "patch_quality_samples exceeds patch_quality_count"
            )
        expected_truncated = patch_count > retained_count
        if summary.get("patch_quality_truncated") is not expected_truncated:
            result.add_error(
                "patch_quality_truncated does not match retained counts"
            )
    elif not isinstance(summary.get("patch_quality_truncated"), bool):
        result.add_error(
            "patch_quality_truncated must be Boolean"
        )

    # The preview accumulation interval is derived from its frame rate and must
    # not drift between renderer metadata and the summary.
    preview_fps = _finite_positive_number(
        summary.get("preview_fps"),
        "preview_fps",
        result,
    )
    preview_dt_ms = _finite_positive_number(
        summary.get("preview_dt_ms"),
        "preview_dt_ms",
        result,
    )
    if (
        preview_fps is not None and
        preview_dt_ms is not None and
        not math.isclose(
            preview_dt_ms,
            1000.0 / preview_fps,
            rel_tol=1e-9,
            abs_tol=1e-9,
        )
    ):
        result.add_error(
            "preview_dt_ms does not match preview_fps"
        )

    # Keep duplicated convenience counts identical to the typed video artifact
    # objects consumed by generic video validation.
    for field_name, expected_frames in (
        ("reconstruction", reconstruction_frames),
        ("patch_debug", patch_frames),
    ):
        video = summary.get(field_name)
        if (
            isinstance(video, dict) and
            expected_frames is not None and
            video.get("frame_count") != expected_frames
        ):
            result.add_error(
                f"{field_name} frame_count does not match summary"
            )

    # Validate the fixed mosaic geometry as a coherent policy rather than three
    # independent positive integers.
    patch_layout = summary.get("patch_layout")
    if not isinstance(patch_layout, dict):
        result.add_error(
            "patch_layout must contain one JSON object"
        )
        return
    panel_size = _positive_integer_field(
        patch_layout,
        "event_panel_size",
        "patch_layout",
        result,
    )
    columns = _positive_integer_field(
        patch_layout,
        "mosaic_columns",
        "patch_layout",
        result,
    )
    maximum_candidates = _positive_integer_field(
        patch_layout,
        "max_candidates",
        "patch_layout",
        result,
    )
    if (
        columns is not None and
        maximum_candidates is not None and
        columns > maximum_candidates
    ):
        result.add_error(
            "patch_layout mosaic_columns exceeds max_candidates"
        )
    patch_video = summary.get("patch_debug")
    if (
        panel_size is not None and
        isinstance(patch_video, dict) and
        patch_video.get("height") != panel_size
    ):
        result.add_error(
            "patch_layout event_panel_size does not match patch video"
        )


def _check_summary_fields(summary: dict[str, Any],
                          result: EvaluationResult,
                          *,
                          expected_artifact_type: str) -> None:
    """Validate the stable component-summary scalar schema."""
    # Pin schema identity before checking payload values so readers can reject
    # future incompatible formats deterministically.
    missing_keys = sorted(REQUIRED_SUMMARY_KEYS - set(summary))
    if missing_keys:
        result.add_error(
            f"summary.json missing keys: {missing_keys}"
        )
    schema_version = summary.get("schema_version")
    if isinstance(schema_version, bool) or schema_version != 1:
        result.add_error("schema_version must equal 1")
    if summary.get("artifact_type") != expected_artifact_type:
        result.add_error(
            f"artifact_type must equal '{expected_artifact_type}'"
        )
    for field_name in ("run_name", "input"):
        value = summary.get(field_name)
        if not isinstance(value, str) or not value.strip():
            result.add_error(
                f"{field_name} must be a nonempty string"
            )
    if summary.get("status") != "passed":
        result.add_error("summary status must be 'passed'")

    # Reject Boolean values explicitly because Python treats them as integers.
    for field_name in ("event_count", "track_count", "track_rows"):
        value = summary.get(field_name)
        if (
            isinstance(value, bool) or
            not isinstance(value, int) or
            value < 0
        ):
            result.add_error(
                f"{field_name} must be a nonnegative integer"
            )
    for field_name in ("duration_s", "runtime_s"):
        value = summary.get(field_name)
        if (
            isinstance(value, bool) or
            not isinstance(value, (int, float)) or
            not math.isfinite(float(value)) or
            float(value) < 0.0
        ):
            result.add_error(
                f"{field_name} must be nonnegative and finite"
            )


def _check_tracks(root: Path,
                  summary: dict[str, Any],
                  result: EvaluationResult) -> None:
    """Validate the declared track file and exact summary counts."""
    # Resolve through the component root before invoking the shared strict
    # parser so manifest paths cannot redirect validation elsewhere.
    track_path = _resolve_artifact(
        root,
        summary.get("tracks_file", "tracks.txt"),
        "tracks_file",
        result,
    )
    if track_path is None:
        return
    if not track_path.is_file():
        result.add_error(f"missing tracks file: {track_path}")
        return
    try:
        samples = load_track_samples(track_path)
    except (OSError, UnicodeError, ValueError) as exc:
        result.add_error(f"invalid tracks file: {exc}")
        return
    if not samples:
        result.add_error(f"tracks file has no data rows: {track_path}")
        return

    # Recompute both aggregate counts from the artifact instead of trusting the
    # duplicated summary values.
    track_count = len({sample.track_id for sample in samples})
    if summary.get("track_rows") != len(samples):
        result.add_error(
            "summary track_rows does not match the track artifact"
        )
    if summary.get("track_count") != track_count:
        result.add_error(
            "summary track_count does not match the track artifact"
        )


def _check_plots(root: Path,
                 summary: dict[str, Any],
                 result: EvaluationResult,
                 *,
                 require_tracks: bool) -> None:
    """Validate every declared plot and the required component subset."""
    plot_values = summary.get("plots")
    if not isinstance(plot_values, list):
        result.add_error("plots must be a list of relative paths")
        return

    # Resolve and decode every manifest entry once, indexing by the stable
    # filename used by the plot-contract schema.
    plot_entries: dict[str, Path] = {}
    for index, entry in enumerate(plot_values):
        path = _resolve_artifact(
            root,
            entry,
            f"plots[{index}]",
            result,
        )
        if path is None:
            continue
        if path.name in plot_entries:
            result.add_error(
                f"duplicate plot filename in manifest: {path.name}"
            )
            continue
        plot_entries[path.name] = path
        _check_png(path, result)
        _check_plot_contract(path.name, summary, result)

    # Derive the mandatory subset from component type and available inputs;
    # optional extra plots still receive the same decoding and label checks.
    required: set[str] = set()
    if require_tracks:
        required.update(REQUIRED_TRACK_PLOTS)
    else:
        required.update(
            {
                "event_stream_3d_views.png",
                "patch_quality.png",
            }
        )
    if _nonnegative_integer(summary.get("event_count")) > 0:
        required.add("event_rate.png")
    if summary.get("gt_status") == "available":
        required.add("gt_error.png")

    for name in sorted(required):
        if name not in plot_entries:
            result.add_error(
                f"required plot is absent from the manifest: {name}"
            )


def _check_png(path: Path, result: EvaluationResult) -> None:
    """Require one regular, nonempty, decodable PNG artifact."""
    if path.suffix.lower() != ".png":
        result.add_error(f"plot artifact must be a PNG: {path}")
        return
    _decode_png_size(path, "declared plot", result)


def _decode_png_size(path: Path,
                     artifact_name: str,
                     result: EvaluationResult) -> tuple[int, int] | None:
    """Decode one regular PNG and return its positive dimensions."""
    if not path.is_file():
        result.add_error(f"missing {artifact_name}: {path}")
        return None
    if path.stat().st_size == 0:
        result.add_error(f"empty {artifact_name}: {path}")
        return None

    # Verify compressed structure first, then reopen to read dimensions because
    # Pillow invalidates an image object after ``verify()``.
    try:
        with Image.open(path) as image:
            image.verify()
        with Image.open(path) as image:
            width, height = image.size
    except (OSError, UnidentifiedImageError) as exc:
        result.add_error(
            f"invalid PNG artifact {path}: {exc}"
        )
        return None
    if width <= 0 or height <= 0:
        result.add_error(f"invalid PNG dimensions: {path}")
        return None
    return width, height


def _check_component_videos(root: Path,
                            summary: dict[str, Any],
                            result: EvaluationResult,
                            *,
                            require_tracks: bool) -> None:
    """Validate reconstruction videos declared by the component schema."""
    if require_tracks:
        return
    for field_name in ("preview", "reconstruction", "patch_debug"):
        if field_name not in summary:
            result.add_error(
                f"summary is missing required video artifact: {field_name}"
            )
            continue
        _check_video_artifact(
            root,
            summary[field_name],
            field_name,
            result,
        )


def _check_video_artifact(root: Path,
                          value: object,
                          field_name: str,
                          result: EvaluationResult) -> None:
    """Validate one typed MP4, PNG, or PNG-sequence artifact."""
    if not isinstance(value, dict):
        result.add_error(
            f"{field_name} must contain one video artifact object"
        )
        return

    kind = value.get("kind")
    if kind not in {"mp4", "png", "png_sequence"}:
        result.add_error(
            f"{field_name}.kind must be mp4, png, or png_sequence"
        )
        return
    path = _resolve_artifact(
        root,
        value.get("path"),
        f"{field_name}.path",
        result,
    )
    if path is None:
        return

    # Bound declared allocation and frame count before opening a potentially
    # expensive sequence or invoking ffprobe.
    frame_count = _positive_integer_field(
        value,
        "frame_count",
        field_name,
        result,
    )
    width = _positive_integer_field(
        value,
        "width",
        field_name,
        result,
    )
    height = _positive_integer_field(
        value,
        "height",
        field_name,
        result,
    )
    if frame_count is not None and frame_count > MAX_VIDEO_FRAMES:
        result.add_error(
            f"{field_name}.frame_count exceeds {MAX_VIDEO_FRAMES}"
        )
    if (
        width is not None and
        height is not None and
        width * height > MAX_VIDEO_FRAME_PIXELS
    ):
        result.add_error(
            f"{field_name} frame geometry exceeds "
            f"{MAX_VIDEO_FRAME_PIXELS} pixels"
        )
    fps = value.get("fps")
    if kind == "png":
        if fps is not None:
            result.add_error(f"{field_name}.fps must be null for PNG output")
        if frame_count != 1:
            result.add_error(
                f"{field_name}.frame_count must equal 1 for PNG output"
            )
    elif (
        isinstance(fps, bool) or
        not isinstance(fps, (int, float)) or
        not math.isfinite(float(fps)) or
        not 0.0 < float(fps) <= 1000.0
    ):
        result.add_error(
            f"{field_name}.fps must be finite and in (0, 1000]"
        )

    # Dispatch only after common schema checks so all backends share identical
    # dimension, frame-count, and frame-rate semantics.
    if kind == "mp4":
        _check_mp4(
            path,
            field_name,
            frame_count,
            width,
            height,
            float(fps) if isinstance(fps, (int, float)) else None,
            result,
        )
    elif kind == "png":
        size = _decode_png_size(path, field_name, result)
        _check_declared_image_size(
            size,
            width,
            height,
            field_name,
            result,
        )
    else:
        _check_png_sequence(
            path,
            field_name,
            frame_count,
            width,
            height,
            result,
        )


def _positive_integer_field(value: dict[str, Any],
                            key: str,
                            field_name: str,
                            result: EvaluationResult) -> int | None:
    """Return one positive integer metadata field after recording errors."""
    field_value = value.get(key)
    if (
        isinstance(field_value, bool) or
        not isinstance(field_value, int) or
        field_value <= 0
    ):
        result.add_error(
            f"{field_name}.{key} must be a positive integer"
        )
        return None
    return field_value


def _finite_positive_number(value: object,
                            field_name: str,
                            result: EvaluationResult) -> float | None:
    """Return one positive finite scalar after recording schema errors."""
    if (
        isinstance(value, bool) or
        not isinstance(value, (int, float)) or
        not math.isfinite(float(value)) or
        float(value) <= 0.0
    ):
        result.add_error(
            f"{field_name} must be positive and finite"
        )
        return None
    return float(value)


def _check_declared_image_size(size: tuple[int, int] | None,
                               width: int | None,
                               height: int | None,
                               field_name: str,
                               result: EvaluationResult) -> None:
    """Match decoded image geometry to declared artifact metadata."""
    if size is None or width is None or height is None:
        return
    if size != (width, height):
        result.add_error(
            f"{field_name} dimensions {size} do not match "
            f"declared {(width, height)}"
        )


def _check_png_sequence(path: Path,
                        field_name: str,
                        frame_count: int | None,
                        width: int | None,
                        height: int | None,
                        result: EvaluationResult) -> None:
    """Validate exact contiguous PNG fallback frames and their dimensions."""
    if not path.is_dir():
        result.add_error(
            f"{field_name} PNG sequence directory is missing: {path}"
        )
        return
    if next(path.glob(".frame_*.stage.png"), None) is not None:
        result.add_error(
            f"{field_name} contains incomplete staged PNG frames"
        )

    # Bound discovery while collecting only the writer's public frame prefix;
    # unrelated files are ignored unless they impersonate that prefix.
    all_frame_paths: list[Path] = []
    for frame_path in path.glob("frame_*.png"):
        all_frame_paths.append(frame_path)
        if len(all_frame_paths) > MAX_VIDEO_FRAMES:
            result.add_error(
                f"{field_name} contains more than "
                f"{MAX_VIDEO_FRAMES} frame-like files"
            )
            return
    all_frame_paths.sort()

    # Separate exact conventional names from frame-like debris before checking
    # contiguous numbering and image contents.
    frame_paths: list[Path] = []
    invalid_names: list[str] = []
    for frame_path in all_frame_paths:
        if re.fullmatch(r"frame_[0-9]{6}[.]png", frame_path.name):
            frame_paths.append(frame_path)
        else:
            invalid_names.append(frame_path.name)
    if invalid_names:
        displayed_names = invalid_names[:10]
        suffix = (
            ""
            if len(invalid_names) <= len(displayed_names)
            else f" and {len(invalid_names) - len(displayed_names)} more"
        )
        result.add_error(
            f"{field_name} contains invalid frame names: "
            f"{displayed_names}{suffix}"
        )
    if frame_count is not None and len(frame_paths) != frame_count:
        result.add_error(
            f"{field_name} frame count {len(frame_paths)} does not match "
            f"declared {frame_count}"
        )

    # Decode every declared frame because one corrupt or mismatched image makes
    # the complete sequence artifact unusable.
    for index, frame_path in enumerate(frame_paths):
        expected_name = f"frame_{index:06d}.png"
        if frame_path.name != expected_name:
            result.add_error(
                f"{field_name} has non-contiguous frame: {frame_path.name}"
            )
        if frame_path.is_symlink():
            result.add_error(
                f"{field_name} frame must not be a symlink: {frame_path}"
            )
            continue
        size = _decode_png_size(frame_path, field_name, result)
        _check_declared_image_size(
            size,
            width,
            height,
            field_name,
            result,
        )


def _check_mp4(path: Path,
               field_name: str,
               frame_count: int | None,
               width: int | None,
               height: int | None,
               fps: float | None,
               result: EvaluationResult) -> None:
    """Validate MP4 container, stream geometry, rate, and frame count."""
    if not path.is_file() or path.stat().st_size < 12:
        result.add_error(f"{field_name} MP4 is missing or empty: {path}")
        return
    with path.open("rb") as stream:
        header = stream.read(12)
    if header[4:8] != b"ftyp":
        result.add_error(f"{field_name} is not an MP4 container: {path}")
        return

    # Treat the container signature as the portable minimum; when ffprobe is
    # available, require decoded stream metadata to match the manifest exactly.
    ffprobe = shutil.which("ffprobe")
    if ffprobe is None:
        result.warnings.append(
            f"ffprobe unavailable; MP4 stream metadata not checked: {path}"
        )
        return
    try:
        completed = subprocess.run(
            [
                ffprobe,
                "-v",
                "error",
                "-select_streams",
                "v:0",
                "-count_frames",
                "-show_entries",
                "stream=width,height,r_frame_rate,nb_read_frames",
                "-of",
                "json",
                str(path),
            ],
            check=False,
            capture_output=True,
            text=True,
            timeout=60,
        )
    except (OSError, subprocess.TimeoutExpired) as exc:
        result.add_error(f"ffprobe failed for {field_name}: {exc}")
        return
    if completed.returncode != 0:
        result.add_error(
            f"ffprobe rejected {field_name}: {completed.stderr.strip()}"
        )
        return

    # Parse only the first video stream selected by ffprobe and convert rational
    # frame rate to the scalar representation used by the artifact schema.
    try:
        payload = json.loads(completed.stdout)
        streams = payload["streams"]
        stream = streams[0]
        decoded_size = (int(stream["width"]), int(stream["height"]))
        numerator, denominator = stream["r_frame_rate"].split("/", 1)
        decoded_fps = int(numerator) / int(denominator)
        decoded_frames = int(stream["nb_read_frames"])
    except (
        IndexError,
        KeyError,
        TypeError,
        ValueError,
        ZeroDivisionError,
        json.JSONDecodeError,
    ) as exc:
        result.add_error(
            f"invalid ffprobe metadata for {field_name}: {exc}"
        )
        return

    _check_declared_image_size(
        decoded_size,
        width,
        height,
        field_name,
        result,
    )
    if frame_count is not None and decoded_frames != frame_count:
        result.add_error(
            f"{field_name} decoded {decoded_frames} frames, "
            f"declared {frame_count}"
        )
    if fps is not None and not math.isclose(
        decoded_fps,
        fps,
        rel_tol=1e-5,
        abs_tol=1e-5,
    ):
        result.add_error(
            f"{field_name} decoded at {decoded_fps:g} fps, "
            f"declared {fps:g}"
        )


def _check_plot_contract(name: str,
                         summary: dict[str, Any],
                         result: EvaluationResult) -> None:
    """Require title and unit-bearing axis labels for one plot."""
    contracts = summary.get("plot_contracts")
    contract = (
        contracts.get(name)
        if isinstance(contracts, dict)
        else None
    )
    if not isinstance(contract, dict):
        result.add_error(f"missing plot label contract: {name}")
        return

    # Require complete reader-facing text and apply capitalization to the first
    # alphabetic character, allowing conventional numerical prefixes.
    for field_name in ("title", "subtitle", "x_label", "y_label"):
        value = contract.get(field_name)
        if not isinstance(value, str) or not value.strip():
            result.add_error(
                f"plot {name} has an empty {field_name}"
            )
            continue
        first_letter = next(
            (
                character
                for character in value
                if character.isalpha()
            ),
            None,
        )
        if first_letter is None or not first_letter.isupper():
            result.add_error(
                f"plot {name} {field_name} must start "
                "with a capital letter"
            )

    # Unit-bearing axes are an acceptance invariant independent of the
    # renderer that produced the PNG.
    for field_name in ("x_label", "y_label"):
        value = contract.get(field_name)
        if isinstance(value, str) and (
            "[" not in value or
            not value.endswith("]")
        ):
            result.add_error(
                f"plot {name} {field_name} must end with "
                "a bracketed unit or scale"
            )


def _check_ground_truth(root: Path,
                        summary: dict[str, Any],
                        result: EvaluationResult) -> None:
    """Validate ground-truth availability and metric consistency."""
    gt_status = summary.get("gt_status")
    if gt_status not in {"available", "unavailable"}:
        result.add_error(
            "gt_status must be 'available' or 'unavailable'"
        )
        return

    # Detect conventional ground-truth artifacts independently from the
    # summary so an unavailable claim cannot conceal existing evidence.
    gt_candidates = {
        root / name
        for name in ("gt.txt", "ground_truth.txt")
        if (root / name).is_file()
    }
    if gt_status == "available":
        metrics = summary.get("gt_metrics")
        if not isinstance(metrics, dict) or not metrics:
            result.add_error(
                "gt_metrics must be nonempty when ground truth is available"
            )
        elif (
            isinstance(metrics.get("matched_rows"), bool) or
            not isinstance(metrics.get("matched_rows"), int) or
            int(metrics.get("matched_rows", 0)) <= 0
        ):
            result.add_error(
                "gt_metrics matched_rows must be a positive integer"
            )
        else:
            # Numeric extension fields are permitted, but every one must remain
            # finite for portable JSON consumers.
            for key, value in metrics.items():
                if (
                    isinstance(value, (int, float)) and
                    not isinstance(value, bool) and
                    not math.isfinite(float(value))
                ):
                    result.add_error(
                        f"gt_metrics {key} must be finite"
                    )
    elif gt_candidates:
        result.add_error(
            "ground truth files exist but summary gt_status is unavailable"
        )


def _check_processing_timing(root: Path,
                             summary: dict[str, Any],
                             result: EvaluationResult) -> None:
    """Validate optional Stage 14 timing evidence retained by the analyzer."""
    value = summary.get("processing_timing")
    if value is None:
        return
    if not isinstance(value, dict):
        result.add_error(
            "processing_timing must contain one JSON object"
        )
        return
    if value.get("status") != "passed":
        result.add_error("processing_timing status must be 'passed'")

    # Validate retained and plotted cardinalities before reading either timing
    # artifact.
    sample_count = _positive_integer_field(
        value,
        "sample_count",
        "processing_timing",
        result,
    )
    plotted_count = _positive_integer_field(
        value,
        "plotted_sample_count",
        "processing_timing",
        result,
    )
    if (
        sample_count is not None and
        plotted_count is not None and
        plotted_count > sample_count
    ):
        result.add_error(
            "processing_timing plotted_sample_count exceeds sample_count"
        )

    # Keep both timing paths inside the component root and require existing
    # nonempty regular files before deeper CSV or plot checks.
    resolved_artifacts: dict[str, Path] = {}
    for field_name in ("input_csv", "output_plot"):
        path = _resolve_artifact(
            root,
            value.get(field_name),
            f"processing_timing.{field_name}",
            result,
        )
        if path is None:
            continue
        if not path.is_file() or path.stat().st_size == 0:
            result.add_error(
                f"processing_timing {field_name} is missing or empty: {path}"
            )
            continue
        resolved_artifacts[field_name] = path

    timing_csv = resolved_artifacts.get("input_csv")
    if timing_csv is not None:
        _check_processing_timing_csv(
            timing_csv,
            sample_count,
            result,
        )

    output_plot = value.get("output_plot")
    plots = summary.get("plots")
    if (
        isinstance(output_plot, str) and
        isinstance(plots, list) and
        output_plot not in plots
    ):
        result.add_error(
            "processing_timing output_plot is absent from the plot manifest"
        )


def _check_processing_timing_csv(path: Path,
                                 expected_count: int | None,
                                 result: EvaluationResult) -> None:
    """Validate retained Stage 14 timing rows and their declared count."""
    row_count = 0
    previous_packet_index = 0
    previous_event_time_s = -math.inf
    try:
        with path.open(newline="", encoding="utf-8") as input_stream:
            reader = csv.DictReader(input_stream)

            # Pin exact column order because downstream tooling consumes this
            # CSV directly without a schema negotiation step.
            if tuple(reader.fieldnames or ()) != PROCESSING_TIMING_FIELDS:
                result.add_error(
                    "processing_timing CSV header must be "
                    + ",".join(PROCESSING_TIMING_FIELDS)
                )
                return

            for line_number, row in enumerate(reader, start=2):
                if (
                    None in row or
                    any(row[field] is None for field in PROCESSING_TIMING_FIELDS)
                ):
                    result.add_error(
                        "processing_timing CSV row "
                        f"{line_number} has an invalid field count"
                    )
                    return
                try:
                    packet_index = int(row["packet_index"])
                    values = tuple(
                        float(row[field])
                        for field in PROCESSING_TIMING_FIELDS[1:]
                    )
                except (TypeError, ValueError):
                    result.add_error(
                        "processing_timing CSV row "
                        f"{line_number} is not numeric"
                    )
                    return

                (
                    event_time_s,
                    fibar_ms,
                    eklt_ms,
                    overhead_ms,
                    total_ms,
                ) = values

                # Enforce causal ordering, finite nonnegative components, and
                # exact additive decomposition for every accepted packet.
                if (
                    packet_index <= previous_packet_index or
                    event_time_s < previous_event_time_s
                ):
                    result.add_error(
                        "processing_timing CSV row "
                        f"{line_number} regresses packet or event time"
                    )
                    return
                if (
                    not all(math.isfinite(item) for item in values) or
                    event_time_s < 0.0 or
                    min(fibar_ms, eklt_ms, overhead_ms, total_ms) < 0.0
                ):
                    result.add_error(
                        "processing_timing CSV row "
                        f"{line_number} contains an invalid value"
                    )
                    return
                component_total = fibar_ms + eklt_ms + overhead_ms
                tolerance = 1e-6 * max(1.0, total_ms)
                if abs(component_total - total_ms) > tolerance:
                    result.add_error(
                        "processing_timing CSV row "
                        f"{line_number} violates additive timing"
                    )
                    return

                previous_packet_index = packet_index
                previous_event_time_s = event_time_s
                row_count += 1
    except (OSError, UnicodeError, csv.Error) as exc:
        result.add_error(
            f"processing_timing CSV cannot be read: {exc}"
        )
        return

    if row_count == 0:
        result.add_error("processing_timing CSV contains no samples")
    if expected_count is not None and row_count != expected_count:
        result.add_error(
            f"processing_timing CSV has {row_count} rows, "
            f"declared {expected_count}"
        )


def _resolve_artifact(root: Path,
                      value: object,
                      field_name: str,
                      result: EvaluationResult) -> Path | None:
    """Resolve one manifest path without permitting absolute or parent escape."""
    # Reject lexical escape first so platform path normalization cannot hide a
    # parent traversal from the stable POSIX manifest syntax.
    if not isinstance(value, str) or not value.strip():
        result.add_error(
            f"{field_name} must be a nonempty relative path"
        )
        return None
    pure_path = PurePosixPath(value)
    if pure_path.is_absolute() or ".." in pure_path.parts:
        result.add_error(
            f"{field_name} escapes the run directory: {value}"
        )
        return None

    # Recheck containment after joining and resolution to reject escape through
    # symlinked or otherwise normalized filesystem components.
    path = root.joinpath(*pure_path.parts)
    if path.is_symlink():
        result.add_error(
            f"{field_name} must not be a symlink: {path}"
        )
        return None
    try:
        path.resolve(strict=False).relative_to(root)
    except ValueError:
        result.add_error(
            f"{field_name} escapes the run directory: {value}"
        )
        return None
    return path


def _nonnegative_integer(value: object) -> int:
    """Return a valid nonnegative integer or zero for prior schema errors."""
    if (
        isinstance(value, bool) or
        not isinstance(value, int) or
        value < 0
    ):
        return 0
    return value


def evaluate_track_video(summary_path: str | Path) -> EvaluationResult:
    """Validate one standalone track-overlay video summary.

    Args:
        summary_path: ``eklt_track_video`` JSON summary path.

    Returns:
        Complete accumulated acceptance result.

    Example:
        result = evaluate_track_video(
            Path("missing-track-video-summary.json")
        )
        print(result.passed)

    Output:
        False
    """
    # Treat the summary directory as the standalone component root and reject
    # link substitution before parsing any referenced artifact.
    path = Path(summary_path)
    result = EvaluationResult(passed=True)
    if path.is_symlink():
        result.add_error(
            f"track-video summary must not be a symlink: {path}"
        )
        return result
    if not path.is_file():
        result.add_error(f"missing track-video summary: {path}")
        return result
    root = path.parent.resolve()

    # Parse the manifest completely before validating its schema and referenced
    # track/video artifacts.
    try:
        value = json.loads(
            path.read_text(encoding="utf-8", errors="strict")
        )
    except (OSError, UnicodeError, json.JSONDecodeError) as exc:
        result.add_error(f"invalid track-video summary: {exc}")
        return result
    if not isinstance(value, dict):
        result.add_error(
            "track-video summary must contain one JSON object"
        )
        return result
    summary: dict[str, Any] = value

    # Validate identity and portable dataset provenance before expensive media
    # inspection.
    schema_version = summary.get("schema_version")
    if isinstance(schema_version, bool) or schema_version != 1:
        result.add_error("track-video schema_version must equal 1")
    if summary.get("artifact_type") != "eklt_track_video":
        result.add_error(
            "track-video artifact_type must equal 'eklt_track_video'"
        )
    if summary.get("status") != "passed":
        result.add_error("track-video status must be 'passed'")
    for field_name in ("input", "tracks", "dataset_adapter"):
        field_value = summary.get(field_name)
        if not isinstance(field_value, str) or not field_value.strip():
            result.add_error(
                f"track-video {field_name} must be a nonempty string"
            )
    if not isinstance(summary.get("dataset_metadata"), dict):
        result.add_error(
            "track-video dataset_metadata must contain one object"
        )

    # Validate encoded media and strict track rows independently, then compare
    # their shared policy and cardinality fields.
    _check_video_artifact(
        root,
        summary.get("video"),
        "video",
        result,
    )
    track_path = _resolve_artifact(
        root,
        summary.get("tracks"),
        "tracks",
        result,
    )
    if track_path is None:
        return result
    try:
        samples = load_track_samples(track_path)
    except (OSError, UnicodeError, ValueError) as exc:
        result.add_error(f"invalid track-video track file: {exc}")
        return result
    if not samples:
        result.add_error("track-video track file has no data rows")

    video = summary.get("video")
    if isinstance(video, dict):
        # Decode the complete track-display policy before evaluating relations
        # among rate, event window, geometry, and observations.
        track_rows = _positive_integer_field(
            video,
            "track_rows",
            "video",
            result,
        )
        track_count = _positive_integer_field(
            video,
            "track_count",
            "video",
            result,
        )
        boundary_clipped_track_rows_value = video.get("boundary_clipped_track_rows")
        boundary_clipped_track_rows: int | None
        if (
            isinstance(boundary_clipped_track_rows_value, bool) or
            not isinstance(boundary_clipped_track_rows_value, int) or
            boundary_clipped_track_rows_value < 0
        ):
            result.add_error(
                "video.boundary_clipped_track_rows must be a "
                "nonnegative integer"
            )
            boundary_clipped_track_rows = None
        else:
            boundary_clipped_track_rows = (
                boundary_clipped_track_rows_value
            )
        event_window_us = _positive_integer_field(
            video,
            "event_window_us",
            "video",
            result,
        )
        dot_radius = _positive_integer_field(
            video,
            "dot_radius",
            "video",
            result,
        )
        scale = _positive_integer_field(
            video,
            "scale",
            "video",
            result,
        )
        hold_ms = video.get("track_hold_ms")
        if (
            isinstance(hold_ms, bool) or
            not isinstance(hold_ms, (int, float)) or
            not math.isfinite(float(hold_ms)) or
            float(hold_ms) < 0.0
        ):
            result.add_error(
                "video.track_hold_ms must be nonnegative and finite"
            )
        if dot_radius is not None and dot_radius > 64:
            result.add_error("video.dot_radius must be in [1, 64]")
        if scale is not None and scale > 8:
            result.add_error("video.scale must be in [1, 8]")

        # The frame window is derived from fps by the renderer and remains an
        # exact integer-microsecond artifact invariant.
        fps = video.get("fps")
        if (
            event_window_us is not None and
            isinstance(fps, (int, float)) and
            not isinstance(fps, bool) and
            math.isfinite(float(fps)) and
            float(fps) > 0.0 and
            event_window_us != max(
                1,
                int(round(1_000_000.0 / float(fps))),
            )
        ):
            result.add_error(
                "video.event_window_us does not match video.fps"
            )

        # Recompute row and feature counts from the strict text artifact rather
        # than accepting the flattened video metadata at face value.
        if track_rows != len(samples):
            result.add_error(
                "track-video track_rows does not match the track artifact"
            )
        observed_track_count = len(
            {sample.track_id for sample in samples}
        )
        if track_count != observed_track_count:
            result.add_error(
                "track-video track_count does not match the track artifact"
            )

        # Reconstruct the advertised sensor plane from encoded geometry and
        # scale so boundary-clipping metadata remains exact and auditable.
        encoded_width = video.get("width")
        encoded_height = video.get("height")
        if (
            scale is not None and
            isinstance(encoded_width, int) and
            not isinstance(encoded_width, bool) and
            isinstance(encoded_height, int) and
            not isinstance(encoded_height, bool) and
            encoded_width > 0 and
            encoded_height > 0
        ):
            if (
                encoded_width % scale != 0 or
                encoded_height % scale != 0
            ):
                result.add_error(
                    "track-video dimensions must be divisible by video.scale"
                )
            elif boundary_clipped_track_rows is not None:
                maximum_x = float(encoded_width // scale - 1)
                maximum_y = float(encoded_height // scale - 1)
                observed_clipped_rows = sum(
                    (
                        not 0.0 <= sample.x <= maximum_x or
                        not 0.0 <= sample.y <= maximum_y
                    )
                    for sample in samples
                )
                if (
                    boundary_clipped_track_rows !=
                    observed_clipped_rows
                ):
                    result.add_error(
                        "track-video boundary_clipped_track_rows does not "
                        "match the track artifact"
                    )
    return result


def main(argv: list[str] | None = None) -> int:
    """Run output validation from the command line.

    Args:
        argv: Optional command-line arguments excluding the executable name.

    Returns:
        Zero when all acceptance checks pass, otherwise one.

    Example:
        print(main(["missing"]))

    Output:
        ERROR: run directory is missing: missing
        1
    """
    # Select exactly one evaluation mode so a standalone video summary cannot
    # be confused with a complete component run.
    parser = argparse.ArgumentParser(
        description="Validate EKLT example artifacts."
    )
    parser.add_argument("run_dir", nargs="?", type=Path)
    parser.add_argument(
        "--no-require-tracks",
        action="store_true",
    )
    parser.add_argument(
        "--track-video-summary",
        type=Path,
    )
    args = parser.parse_args(argv)

    if args.track_video_summary is not None:
        if args.run_dir is not None or args.no_require_tracks:
            parser.error(
                "--track-video-summary cannot be combined with run_dir "
                "or --no-require-tracks"
            )
        result = evaluate_track_video(args.track_video_summary)
        display_path = args.track_video_summary
    else:
        if args.run_dir is None:
            parser.error("run_dir is required")
        result = evaluate_run(
            args.run_dir,
            require_tracks=not args.no_require_tracks,
        )
        display_path = args.run_dir

    # Emit every accumulated warning and error before selecting the process
    # status used by shell orchestration.
    for warning in result.warnings:
        print(f"WARNING: {warning}")
    for error in result.errors:
        print(f"ERROR: {error}")
    if result.passed:
        print(f"passed: {display_path}")
        return 0
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
