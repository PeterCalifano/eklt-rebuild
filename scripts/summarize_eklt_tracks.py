#!/usr/bin/env python3.12
"""Summarize EKLT tracks and render validated acceptance plots.

The script reads the strict ``id time_s x_px y_px`` artifact format, preserves
an optional native-run summary, and publishes one stable analysis schema.

Example:
    python scripts/summarize_eklt_tracks.py \
        --tracks outputs/example/tracks.txt \
        --output-dir outputs/example \
        --run-name example \
        --input events.npz \
        --event-npz events.npz

Output:
    outputs/example/summary.json
"""

from __future__ import annotations

import argparse
import json
import math
import os
import shutil
import time
from bisect import bisect_left
from collections import defaultdict
from collections.abc import Iterable, Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib.axes import Axes
from matplotlib.figure import Figure
import numpy as np

from event_vision_utils.io import (
    TrackSample,
    load_event_dataset,
    load_track_samples,
)
from event_vision_utils.viz import (
    PlotContract,
    compute_event_rate,
    event_rate_plot_contract,
    render_event_rate_series,
)


_MAX_EVENT_RATE_BINS = 1_000_000
_ActiveTrackSeries = tuple[np.ndarray, np.ndarray, float]
_TimingArtifacts = tuple[dict[str, Any] | None, Path | None, PlotContract | None]


@dataclass(frozen=True, slots=True)
class EventRate:
    """Event-rate bins plus authoritative input-image geometry.

    Attributes:
        event_count: Total or sampled-and-scaled event count.
        duration_s: Covered event-source duration in seconds.
        bin_counts: Event counts in fixed-width time bins.
        bin_us: Bin width in microseconds.
        source: Event-rate provenance.
        source_event_count: Complete source count before represented-run
            limiting, when known.
        image_width: Advertised sensor width when available.
        image_height: Advertised sensor height when available.
        geometry_source: Sensor-geometry provenance.

    Example:
        event_rate = EventRate(
            event_count=2,
            duration_s=0.01,
            bin_counts=(1, 1),
            bin_us=10_000,
            source="fixture",
        )
        print(event_rate.bin_s)

    Output:
        0.01
    """

    event_count: int
    duration_s: float
    bin_counts: tuple[int, ...]
    bin_us: int
    source: str
    source_event_count: int | None = None
    image_width: int | None = None
    image_height: int | None = None
    geometry_source: str = "unavailable"

    @property
    def bin_s(self) -> float:
        """Return the event-rate bin width in seconds.

        Example:
            event_rate = EventRate(
                event_count=1,
                duration_s=0.0,
                bin_counts=(1,),
                bin_us=20_000,
                source="fixture",
            )
            print(event_rate.bin_s)

        Output:
            0.02
        """
        return self.bin_us / 1_000_000.0


@dataclass(frozen=True, slots=True)
class GroundTruthResult:
    """Ground-truth evaluation status, metrics, and generated plots.

    Example:
        result = GroundTruthResult("unavailable", {}, ())
        print(result.status)

    Output:
        unavailable
    """

    status: str
    metrics: dict[str, float | int | str]
    plots: tuple[Path, ...]


TRACK_PLOT_CONTRACTS = {
    "active_tracks.png": PlotContract(
        title="Active EKLT Tracks over Time",
        subtitle="Feature lifetimes that overlap each fixed time bin.",
        x_label="Time Since First Track [s]",
        y_label="Active Track Count [tracks]",
    ),
    "track_lifetimes.png": PlotContract(
        title="EKLT Track Lifetimes",
        subtitle=(
            "Longest feature tracks first; single-row tracks have zero "
            "lifetime."
        ),
        x_label="Track Rank [rank]",
        y_label="Track Lifetime [s]",
    ),
    "reinit_timeline.png": PlotContract(
        title="EKLT Feature Initialization Timeline",
        subtitle="Cumulative unique feature starts over the tracker timeline.",
        x_label="Time Since First Initialization [s]",
        y_label="Cumulative Feature Starts [tracks]",
    ),
    "track_xy.png": PlotContract(
        title="EKLT Track Positions",
        subtitle=(
            "Full sensor image plane from origin (0, 0); Y increases "
            "downward."
        ),
        x_label="Horizontal Image Coordinate, X [px]",
        y_label="Vertical Image Coordinate, Y [px]",
    ),
    "gt_error.png": PlotContract(
        title="EKLT Ground-Truth Position Error",
        subtitle=(
            "Nearest-in-time matches between EKLT and ground-truth rows."
        ),
        x_label="Matched Track Row [row index]",
        y_label="Position Error [px]",
    ),
}


def main(argv: list[str] | None = None) -> int:
    """Write EKLT acceptance metrics, plots, and one JSON summary.

    Args:
        argv: Optional command-line arguments excluding the executable name.

    Returns:
        Zero only when the native/base run and analysis both pass.

    Raises:
        ValueError: If geometry, timing policy, or an artifact is invalid.

    Example:
        status = main([
            "--tracks", "tracks.txt",
            "--output-dir", "outputs/example",
            "--run-name", "example",
            "--input", "fixture",
            "--event-width", "200",
            "--event-height", "200",
        ])
        print(status)

    Output:
        0
    """
    # Collect analysis, geometry, and optional evidence policy before reading
    # any artifact or changing the selected output directory.
    parser = argparse.ArgumentParser(
        description="Summarize EKLT tracks and write acceptance plots."
    )
    parser.add_argument("--tracks", required=True, type=Path)
    parser.add_argument("--output-dir", required=True, type=Path)
    parser.add_argument("--run-name", required=True)
    parser.add_argument("--input", required=True)
    parser.add_argument("--runtime-s", default=None, type=float)
    parser.add_argument("--base-summary", default=None, type=Path)
    parser.add_argument("--summary-output", default=None, type=Path)
    parser.add_argument("--event-bin-ms", default=20.0, type=float)
    parser.add_argument("--event-npz", default=None, type=Path)
    parser.add_argument(
        "--event-width",
        default=None,
        type=int,
        help=(
            "Optional image-plane width; required with --event-height when "
            "input metadata are unavailable."
        ),
    )
    parser.add_argument(
        "--event-height",
        default=None,
        type=int,
        help=(
            "Optional image-plane height; required with --event-width when "
            "input metadata are unavailable."
        ),
    )
    parser.add_argument(
        "--ground-truth",
        default=None,
        type=Path,
        help=(
            "Optional same-format ground-truth file: "
            "id time_s x_px y_px."
        ),
    )
    parser.add_argument(
        "--gt-max-dt-ms",
        default=20.0,
        type=float,
        help=(
            "Maximum timestamp difference for matching tracker and "
            "ground-truth rows."
        ),
    )
    args = parser.parse_args(argv)

    # Validate scalar CLI policy first, then preserve the native run manifest
    # that this analysis will enrich rather than replace semantically.
    _validate_arguments(args)
    started = time.perf_counter()
    base_summary = _load_base_summary(args.base_summary)

    event_rate = _read_event_source(
        event_npz=args.event_npz,
        bin_ms=args.event_bin_ms,
        width=args.event_width,
        height=args.event_height,
        event_count_limit=_represented_event_limit(base_summary),
    )
    image_width, image_height, geometry_source = _resolve_image_geometry(
        event_rate,
        args.event_width,
        args.event_height,
    )

    # Parse every input artifact strictly before cleaning or replacing any
    # previously accepted output.
    rows = sorted(
        load_track_samples(args.tracks),
        key=lambda row: (row.t_s, row.track_id),
    )
    ground_truth_path = args.ground_truth
    ground_truth_rows = (
        None
        if ground_truth_path is None
        else sorted(
            load_track_samples(ground_truth_path),
            key=lambda row: (row.t_s, row.track_id),
        )
    )

    # Resolve all output and inherited-timing paths before cleaning the owned
    # plot set or publishing a canonical track copy.
    output_dir = _resolve_output_directory(args.output_dir)
    summary_output = _resolve_summary_output(
        output_dir,
        args.summary_output,
    )
    timing_summary, timing_plot, timing_contract = (
        _resolve_processing_timing(output_dir, base_summary)
    )
    if timing_summary is not None:
        base_summary = dict(base_summary)
        base_summary["processing_timing"] = timing_summary

    # Validate every mutable analysis target before deleting or replacing any
    # previously accepted plot or canonical track artifact.
    _validate_output_track_target(output_dir)
    _validate_owned_plots(output_dir)
    _remove_owned_plots(output_dir)
    plots_dir = output_dir / "plots"
    plots_dir.mkdir(parents=True, exist_ok=True)
    output_tracks = _ensure_output_tracks(
        args.tracks,
        output_dir,
    )
    by_id = _group_by_id(rows)

    # Produce the mandatory track views from one grouped representation so
    # counts, lifetimes, initialization times, and trajectories share inputs.
    track_plots = [
        _plot_active_tracks(
            by_id,
            plots_dir / "active_tracks.png",
        ),
        _plot_track_lifetimes(
            by_id,
            plots_dir / "track_lifetimes.png",
        ),
        _plot_reinit_timeline(
            by_id,
            plots_dir / "reinit_timeline.png",
        ),
        _plot_track_xy(
            by_id,
            plots_dir / "track_xy.png",
            image_width,
            image_height,
        ),
    ]

    # Render an event-rate plot only when an event source is represented; the
    # summary still records explicit no-event provenance otherwise.
    event_plots: list[Path] = []
    if event_rate.event_count > 0:
        rates_hz = (
            np.asarray(event_rate.bin_counts, dtype=np.float64) /
            event_rate.bin_s
        )
        event_plots.append(
            render_event_rate_series(
                rates_hz,
                plots_dir / "event_rate.png",
                bin_us=event_rate.bin_us,
                event_count=event_rate.event_count,
                source=event_rate.source,
                width=1100,
                height=520,
                max_bins=_MAX_EVENT_RATE_BINS,
            )
        )

    # Keep optional ground-truth matching independent from native run success,
    # then derive one combined analysis/native status.
    gt_result = _summarize_ground_truth(
        rows,
        ground_truth_path,
        ground_truth_rows,
        plots_dir,
        max_dt_s=args.gt_max_dt_ms / 1000.0,
    )
    gt_passed = (
        gt_result.status == "unavailable" or
        int(gt_result.metrics.get("matched_rows", 0)) > 0
    )
    analysis_passed = bool(rows) and gt_passed
    base_status = base_summary.get("status")
    status = (
        "passed"
        if analysis_passed and base_status in {None, "passed"}
        else str(base_status)
        if base_status in {"blocked", "failed"}
        else "failed"
    )

    # Assemble the manifest and label contracts from exactly the artifacts
    # generated or retained by this analysis pass.
    generated_plots = [
        *track_plots,
        *event_plots,
        *gt_result.plots,
    ]
    if timing_plot is not None:
        generated_plots.append(timing_plot)
    plot_contracts = {
        path.name: TRACK_PLOT_CONTRACTS[path.name].as_dict()
        for path in [*track_plots, *gt_result.plots]
    }
    if event_plots:
        plot_contracts["event_rate.png"] = event_rate_plot_contract(
            event_rate.event_count,
            bin_us=event_rate.bin_us,
            source=event_rate.source,
        ).as_dict()
    if timing_plot is not None and timing_contract is not None:
        plot_contracts[timing_plot.name] = timing_contract.as_dict()

    # Prefer authoritative event duration and native runtime while retaining
    # analysis time as a separate diagnostic.
    duration_s = (
        event_rate.duration_s
        if event_rate.duration_s > 0.0
        else _track_duration(rows)
    )
    analysis_runtime_s = time.perf_counter() - started
    runtime_s = _resolve_runtime_s(
        base_summary,
        args.runtime_s,
        analysis_runtime_s,
    )

    # Overlay the stable analysis schema on preserved native fields so Stage 14
    # conversion/timing evidence remains available to later aggregators.
    summary: dict[str, Any] = dict(base_summary)
    summary.update(
        {
            "schema_version": 1,
            "artifact_type": "eklt_track_analysis",
            "run_name": args.run_name,
            "status": status,
            "analysis_status": (
                "passed"
                if analysis_passed
                else "failed"
            ),
            "input": args.input,
            "event_count": event_rate.event_count,
            "track_count": len(by_id),
            "track_rows": len(rows),
            "tracks_file": output_tracks.name,
            "duration_s": duration_s,
            "runtime_s": runtime_s,
            "analysis_runtime_s": analysis_runtime_s,
            "plots": [
                path.relative_to(output_dir).as_posix()
                for path in generated_plots
            ],
            "plot_descriptions": _plot_descriptions(),
            "plot_contracts": plot_contracts,
            "gt_status": gt_result.status,
            "gt_metrics": gt_result.metrics,
            "event_rate_source": event_rate.source,
            "source_event_count": event_rate.source_event_count,
            "image_width_px": image_width,
            "image_height_px": image_height,
            "image_geometry_source": geometry_source,
            "artifacts": {
                "tracks": output_tracks.name,
                "plots": [
                    path.relative_to(output_dir).as_posix()
                    for path in generated_plots
                ],
            },
        }
    )
    _write_summary(summary_output, summary)
    return 0 if status == "passed" else 1


def _validate_arguments(args: argparse.Namespace) -> None:
    """Validate CLI values before reading or replacing any artifact."""
    if not math.isfinite(args.event_bin_ms) or args.event_bin_ms <= 0.0:
        raise ValueError("--event-bin-ms must be positive and finite")
    if (
        not math.isfinite(args.gt_max_dt_ms) or
        args.gt_max_dt_ms < 0.0
    ):
        raise ValueError("--gt-max-dt-ms must be nonnegative and finite")
    if args.runtime_s is not None and (
        not math.isfinite(args.runtime_s) or
        args.runtime_s < 0.0
    ):
        raise ValueError("--runtime-s must be nonnegative and finite")


def _load_base_summary(path: Path | None) -> dict[str, Any]:
    """Load one optional native-run summary before it is replaced."""
    if path is None:
        return {}

    # Preserve arbitrary native evidence fields but require one object and a
    # status vocabulary understood by the combined-result policy.
    value = json.loads(path.read_text(encoding="utf-8", errors="strict"))
    if not isinstance(value, dict):
        raise ValueError("base summary must contain one JSON object")
    if value.get("status") not in {None, "passed", "blocked", "failed"}:
        raise ValueError(
            "base summary status must be passed, blocked, or failed"
        )
    return value


def _represented_event_limit(summary: dict[str, Any]) -> int | None:
    """Return the exact event count represented by a Stage 14 conversion."""
    # A missing conversion means the complete source may be analyzed; a
    # present conversion must advertise one exact positive prefix length.
    conversion = summary.get("elope_conversion")
    if conversion is None:
        return None
    if not isinstance(conversion, dict):
        raise ValueError("elope_conversion must contain one JSON object")

    event_count = conversion.get("event_count")
    if (
        isinstance(event_count, bool) or
        not isinstance(event_count, int) or
        event_count <= 0
    ):
        raise ValueError(
            "elope_conversion event_count must be a positive integer"
        )
    return event_count


def _resolve_processing_timing(output_dir: Path,
                               base_summary: dict[str, Any]) -> _TimingArtifacts:
    """Validate and normalize optional Stage 14 timing evidence."""
    # Timing remains optional for non-ROS runs, but a present object must
    # describe one completely passed and internally bounded diagnostic.
    value = base_summary.get("processing_timing")
    if value is None:
        return None, None, None
    if not isinstance(value, dict):
        raise ValueError(
            "processing_timing must contain one JSON object"
        )
    if value.get("status") != "passed":
        raise ValueError("processing_timing status must be passed")

    sample_count = value.get("sample_count")
    plotted_count = value.get("plotted_sample_count")
    if (
        isinstance(sample_count, bool) or
        not isinstance(sample_count, int) or
        sample_count <= 0
    ):
        raise ValueError(
            "processing_timing sample_count must be positive"
        )
    if (
        isinstance(plotted_count, bool) or
        not isinstance(plotted_count, int) or
        not 0 < plotted_count <= sample_count
    ):
        raise ValueError(
            "processing_timing plotted_sample_count must be in "
            "[1, sample_count]"
        )

    # Resolve both artifacts into the analysis root and rewrite their manifest
    # paths to relocatable POSIX-relative form.
    normalized = dict(value)
    resolved_artifacts: dict[str, Path] = {}
    for field_name in ("input_csv", "output_plot"):
        field_value = value.get(field_name)
        if not isinstance(field_value, str) or not field_value.strip():
            raise ValueError(
                f"processing_timing {field_name} must be a nonempty path"
            )
        candidate = Path(field_value)
        candidate_path = (
            candidate
            if candidate.is_absolute()
            else output_dir / candidate
        )
        if candidate_path.is_symlink():
            raise ValueError(
                f"processing_timing {field_name} must not be a symlink"
            )
        path = (
            candidate_path.resolve(strict=False)
        )
        try:
            relative_path = path.relative_to(output_dir)
        except ValueError as exc:
            raise ValueError(
                f"processing_timing {field_name} escaped the output directory"
            ) from exc
        if not path.is_file():
            raise ValueError(
                f"processing_timing {field_name} is not a regular file: {path}"
            )
        normalized[field_name] = relative_path.as_posix()
        resolved_artifacts[field_name] = path

    # Reconstruct the shared immutable plot contract from native summary labels
    # instead of trusting an unvalidated metadata dictionary.
    plot_value = value.get("plot")
    if not isinstance(plot_value, dict):
        raise ValueError(
            "processing_timing plot must contain one JSON object"
        )
    label_values = {
        field_name: plot_value.get(field_name)
        for field_name in ("title", "subtitle", "x_label", "y_label")
    }
    if not all(
        isinstance(label, str)
        for label in label_values.values()
    ):
        raise ValueError(
            "processing_timing plot labels must be strings"
        )
    try:
        contract = PlotContract(
            title=label_values["title"],
            subtitle=label_values["subtitle"],
            x_label=label_values["x_label"],
            y_label=label_values["y_label"],
        )
    except ValueError as exc:
        raise ValueError(
            "processing_timing plot has an invalid label contract"
        ) from exc
    return normalized, resolved_artifacts["output_plot"], contract


def _resolve_runtime_s(base_summary: dict[str, Any],
                       explicit_runtime_s: float | None,
                       analysis_runtime_s: float) -> float:
    """Preserve native runtime unless the caller supplies an explicit value."""
    if explicit_runtime_s is not None:
        return explicit_runtime_s

    base_runtime = base_summary.get("runtime_s")
    if base_runtime is None:
        return analysis_runtime_s
    if (
        isinstance(base_runtime, bool) or
        not isinstance(base_runtime, (int, float)) or
        not math.isfinite(float(base_runtime)) or
        float(base_runtime) < 0.0
    ):
        raise ValueError(
            "base summary runtime_s must be nonnegative and finite"
        )
    return float(base_runtime)


def _resolve_output_directory(output_path: Path) -> Path:
    """Validate and create the selected analysis artifact root."""
    # Reject broad roots before directory creation because later cleanup owns a
    # fixed set of relative plot and track paths.
    if output_path.is_symlink():
        raise ValueError(
            f"refusing symlinked output directory: {output_path}"
        )
    output_dir = output_path.resolve(strict=False)
    repository_root = Path(__file__).resolve().parents[1]
    if (
        output_dir == Path(output_dir.anchor) or
        repository_root == output_dir or
        repository_root.is_relative_to(output_dir)
    ):
        raise ValueError(
            "output directory must not be the filesystem root, repository "
            "root, or a repository ancestor"
        )
    if output_dir.exists() and not output_dir.is_dir():
        raise ValueError(
            f"output path is not a directory: {output_dir}"
        )
    output_dir.mkdir(parents=True, exist_ok=True)
    return output_dir


def _remove_owned_plots(output_dir: Path) -> None:
    """Remove only plots owned by the single-run analysis component."""
    owned_paths = _validate_owned_plots(output_dir)

    # Validate every owned plot before removing any prior accepted output.
    for path in owned_paths:
        if path.is_file():
            path.unlink()


def _validate_owned_plots(output_dir: Path) -> list[Path]:
    """Validate and return every plot path owned by this analysis."""
    # Validate the shared parent first so no per-file check follows a symlinked
    # plots directory.
    plots_dir = output_dir / "plots"
    if plots_dir.is_symlink():
        raise ValueError(
            f"refusing symlinked plot directory: {plots_dir}"
        )
    if plots_dir.exists() and not plots_dir.is_dir():
        raise ValueError(
            f"plot path is not a directory: {plots_dir}"
        )

    owned_paths = [
        plots_dir / name
        for name in (
            "active_tracks.png",
            "track_lifetimes.png",
            "reinit_timeline.png",
            "track_xy.png",
            "event_rate.png",
            "gt_error.png",
        )
    ]

    # Complete validation of the deletion set precedes any removal performed
    # by the caller.
    for path in owned_paths:
        if path.is_symlink():
            raise ValueError(
                f"refusing symlinked owned plot: {path}"
            )
        if path.exists() and not path.is_file():
            raise ValueError(
                f"owned plot path is not a regular file: {path}"
            )
    return owned_paths


def _resolve_summary_output(output_dir: Path,
                            requested_path: Path | None) -> Path:
    """Keep the component summary below its selected artifact root."""
    if requested_path is None:
        candidate = output_dir / "summary.json"
    elif requested_path.is_absolute():
        candidate = requested_path
    else:
        candidate = output_dir / requested_path

    # Normalize parent traversals lexically, then reject every existing
    # symlink component before resolving the target.
    path = Path(os.path.abspath(candidate))
    try:
        relative_path = path.relative_to(output_dir)
    except ValueError as exc:
        raise ValueError(
            "summary output must remain below the output directory"
        ) from exc

    parent = output_dir
    for part in relative_path.parts[:-1]:
        parent /= part
        if parent.is_symlink():
            raise ValueError(
                f"refusing symlinked summary parent: {parent}"
            )
        if parent.exists() and not parent.is_dir():
            raise ValueError(
                f"summary parent is not a directory: {parent}"
            )
    if path.is_symlink():
        raise ValueError(
            f"refusing symlinked summary output: {path}"
        )
    if path.exists() and not path.is_file():
        raise ValueError(
            f"summary output is not a regular file: {path}"
        )
    temporary_path = path.with_name(f".{path.name}.tmp")
    if temporary_path.is_symlink():
        raise ValueError(
            f"refusing symlinked temporary summary: {temporary_path}"
        )
    if temporary_path.exists() and not temporary_path.is_file():
        raise ValueError(
            f"temporary summary is not a regular file: {temporary_path}"
        )
    return path


def _ensure_output_tracks(track_path: Path,
                          output_dir: Path) -> Path:
    """Copy an external track artifact atomically into the analysis root."""
    # Reuse an already canonical input in place; external files are copied
    # through the prevalidated temporary sibling.
    output_path, temporary_path = _validate_output_track_target(output_dir)
    if track_path.resolve() == output_path.resolve(strict=False):
        return output_path

    try:
        shutil.copyfile(track_path, temporary_path)
        os.replace(temporary_path, output_path)
    finally:
        temporary_path.unlink(missing_ok=True)
    return output_path


def _validate_output_track_target(output_dir: Path) -> tuple[Path, Path]:
    """Validate canonical track and temporary targets without changing them."""
    # Validate public and temporary paths together so copying never begins with
    # an incomplete ownership check.
    output_path = output_dir / "tracks.txt"
    if output_path.is_symlink():
        raise ValueError(
            f"refusing symlinked track output: {output_path}"
        )
    if output_path.exists() and not output_path.is_file():
        raise ValueError(
            f"track output is not a regular file: {output_path}"
        )

    temporary_path = output_path.with_name(
        f".{output_path.name}.tmp"
    )
    if temporary_path.is_symlink():
        raise ValueError(
            f"refusing symlinked temporary track output: {temporary_path}"
        )
    if temporary_path.exists() and not temporary_path.is_file():
        raise ValueError(
            f"temporary track output is not a regular file: {temporary_path}"
        )
    return output_path, temporary_path


def _group_by_id(rows: Iterable[TrackSample]) -> dict[int, list[TrackSample]]:
    """Group observations by stable feature identifier."""
    by_id: dict[int, list[TrackSample]] = defaultdict(list)
    for row in rows:
        by_id[row.track_id].append(row)
    return dict(by_id)


def _track_duration(rows: Sequence[TrackSample]) -> float:
    """Return the nonnegative first-to-last tracker duration."""
    if len(rows) < 2:
        return 0.0
    return max(0.0, rows[-1].t_s - rows[0].t_s)


def _plot_active_tracks(by_id: dict[int, list[TrackSample]],
                        output_path: Path) -> Path:
    """Render feature lifetimes overlapping each fixed tracker-time bin."""
    contract = TRACK_PLOT_CONTRACTS[output_path.name]
    figure, axis = _new_plot(contract)

    # Plot lifetime overlap rather than observation density, retaining an
    # explicit labeled empty chart when no tracks are available.
    if by_id:
        elapsed_s, values, duration_s = _active_track_series(by_id)
        axis.plot(elapsed_s, values, color="#1C5FA0", linewidth=1.8)
        axis.set_xlim(0.0, max(duration_s, 1e-6))
        axis.set_ylim(0.0, max(float(values.max()) * 1.05, 1.0))
        _annotate(
            axis,
            (
                f"Peak active count: {int(values.max()):,} tracks\n"
                f"Bins: {values.size:,}"
            ),
        )
    else:
        _show_empty(axis, "No track rows are available.")
    return _save_figure(figure, output_path)


def _active_track_series(by_id: dict[int, list[TrackSample]]) -> _ActiveTrackSeries:
    """Count feature lifetimes overlapping each fixed tracker-time bin."""
    lifetimes = [
        (rows[0].t_s, rows[-1].t_s)
        for rows in by_id.values()
        if rows
    ]
    if not lifetimes:
        raise ValueError("at least one feature lifetime is required")
    start_s = min(start for start, _ in lifetimes)
    stop_s = max(stop for _, stop in lifetimes)
    duration_s = stop_s - start_s

    # Count a feature as active when its observed lifetime overlaps a bin. This
    # avoids conflating tracker update density with live-track population.
    if duration_s <= 0.0:
        return (
            np.asarray([0.0], dtype=np.float64),
            np.asarray([len(lifetimes)], dtype=np.int64),
            0.0,
        )

    bin_edges = np.linspace(start_s, stop_s, num=121)
    values = np.asarray(
        [
            sum(
                (
                    track_start < bin_stop or
                    (
                        index == len(bin_edges) - 2 and
                        track_start <= bin_stop
                    )
                ) and
                track_stop >= bin_start
                for track_start, track_stop in lifetimes
            )
            for index, (bin_start, bin_stop) in enumerate(zip(
                bin_edges[:-1],
                bin_edges[1:],
                strict=True,
            ))
        ],
        dtype=np.int64,
    )
    return bin_edges[:-1] - start_s, values, duration_s


def _plot_track_lifetimes(by_id: dict[int, list[TrackSample]],
                          output_path: Path) -> Path:
    """Render descending feature lifetimes by track rank."""
    contract = TRACK_PLOT_CONTRACTS[output_path.name]
    figure, axis = _new_plot(contract)

    # Sort the complete population before applying the display-only top-100
    # bound so the badge can report retained versus total tracks.
    lifetimes = sorted(
        (
            max(0.0, rows[-1].t_s - rows[0].t_s)
            for rows in by_id.values()
        ),
        reverse=True,
    )
    if lifetimes:
        displayed = np.asarray(lifetimes[:100], dtype=np.float64)
        ranks = np.arange(1, displayed.size + 1)
        axis.bar(
            ranks,
            displayed,
            color="#2E7D4E",
            width=0.85,
        )
        axis.set_xlim(0.0, float(displayed.size + 1))
        axis.set_ylim(
            0.0,
            max(float(displayed.max()) * 1.05, 1e-6),
        )
        _annotate(
            axis,
            (
                f"Longest lifetime: {float(displayed.max()):.3f} s\n"
                f"Displayed tracks: {displayed.size:,}/{len(lifetimes):,}"
            ),
        )
    else:
        _show_empty(axis, "No track lifetimes are available.")
    return _save_figure(figure, output_path)


def _plot_reinit_timeline(by_id: dict[int, list[TrackSample]],
                          output_path: Path) -> Path:
    """Render cumulative feature starts over elapsed tracker time."""
    contract = TRACK_PLOT_CONTRACTS[output_path.name]
    figure, axis = _new_plot(contract)

    # Use each stable feature's first observation as its initialization event,
    # then preserve causal order in the cumulative step plot.
    starts = sorted(
        rows[0].t_s
        for rows in by_id.values()
        if rows
    )
    if starts:
        elapsed_s = np.asarray(starts, dtype=np.float64) - starts[0]
        cumulative = np.arange(1, len(starts) + 1)
        axis.step(
            elapsed_s,
            cumulative,
            where="post",
            color="#B86023",
            linewidth=1.8,
        )
        axis.set_xlim(
            0.0,
            max(float(elapsed_s[-1]), 1e-6),
        )
        axis.set_ylim(0.0, float(len(starts) + 1))
        _annotate(
            axis,
            (
                f"Feature starts: {len(starts):,}\n"
                f"Latest start: {float(elapsed_s[-1]):.3f} s"
            ),
        )
    else:
        _show_empty(axis, "No feature initializations are available.")
    return _save_figure(figure, output_path)


def _plot_track_xy(by_id: dict[int, list[TrackSample]],
                   output_path: Path,
                   image_width: int,
                   image_height: int) -> Path:
    """Render feature trajectories on the fixed advertised sensor plane."""
    contract = TRACK_PLOT_CONTRACTS[output_path.name]
    figure, axis = _new_plot(contract)
    maximum_x = float(image_width - 1)
    maximum_y = float(image_height - 1)
    clipped_observations = 0

    # Preserve native coordinates in the track artifact while clipping only
    # plotted samples to the authoritative fixed sensor plane.
    for index, (track_id, track_rows) in enumerate(
        sorted(by_id.items())
    ):
        x_values = np.asarray(
            [row.x for row in track_rows],
            dtype=np.float64,
        )
        y_values = np.asarray(
            [row.y for row in track_rows],
            dtype=np.float64,
        )
        clipped_x = np.clip(x_values, 0.0, maximum_x)
        clipped_y = np.clip(y_values, 0.0, maximum_y)
        clipped_observations += int(
            np.count_nonzero(
                (clipped_x != x_values) |
                (clipped_y != y_values)
            )
        )
        color = _plot_color(index)

        # Draw every trajectory but label only a bounded prefix to avoid turning
        # dense runs into unreadable text fields.
        axis.plot(
            clipped_x,
            clipped_y,
            color=color,
            linewidth=1.0,
            alpha=0.8,
        )
        if clipped_x.size:
            axis.scatter(
                clipped_x[0],
                clipped_y[0],
                color=color,
                s=12,
            )
            if index < 6:
                axis.annotate(
                    str(track_id),
                    (clipped_x[-1], clipped_y[-1]),
                    fontsize=8,
                    color=color,
                )

    _configure_track_axis(
        axis,
        image_width,
        image_height,
    )
    if by_id:
        _annotate(
            axis,
            (
                f"Image plane: {image_width} x {image_height} px\n"
                f"Tracks: {len(by_id):,}; boundary-clipped observations: "
                f"{clipped_observations:,}"
            ),
        )
    else:
        _show_empty(axis, "No track positions are available.")
    return _save_figure(figure, output_path)


def _configure_track_axis(axis: Axes,
                          image_width: int,
                          image_height: int) -> None:
    """Apply the fixed zero-origin, downward-Y image-plane contract."""
    if image_width <= 0 or image_height <= 0:
        raise ValueError("track image geometry must be positive")
    axis.set_xlim(0.0, float(max(image_width - 1, 1)))
    axis.set_ylim(float(max(image_height - 1, 1)), 0.0)
    axis.set_aspect("equal", adjustable="box")


def _read_event_source(*,
                       event_npz: Path | None,
                       bin_ms: float,
                       width: int | None,
                       height: int | None,
                       event_count_limit: int | None) -> EventRate:
    """Read the accepted ELOPE source or return explicit no-event metadata."""
    # Normalize the bin policy even for absent input so summary metadata keeps
    # one consistent unit contract.
    bin_us = max(int(round(bin_ms * 1000.0)), 1)
    if event_npz is None:
        return EventRate(
            event_count=0,
            duration_s=0.0,
            bin_counts=(),
            bin_us=bin_us,
            source="none",
        )
    return _read_event_rate_npz(
        event_npz,
        width,
        height,
        bin_ms,
        event_count_limit=event_count_limit,
    )


def _read_event_rate_npz(path: Path,
                         width: int | None,
                         height: int | None,
                         bin_ms: float,
                         *,
                         event_count_limit: int | None) -> EventRate:
    """Load ELOPE data through the accepted dataset adapter and rate utility."""
    dataset = load_event_dataset(
        path,
        adapter="elope",
        width=width,
        height=height,
    )
    source_events = dataset.events

    # Restrict analysis to the exact prefix represented by converted tracking
    # input, never to events the native run did not process.
    if (
        event_count_limit is not None and
        event_count_limit > source_events.size
    ):
        raise ValueError(
            "represented event count exceeds the ELOPE source"
        )
    events = (
        source_events
        if event_count_limit is None
        else source_events.subset(slice(0, event_count_limit))
    )
    bin_us = max(int(round(bin_ms * 1000.0)), 1)
    _, counts, _ = compute_event_rate(
        events,
        bin_us=bin_us,
        max_bins=_MAX_EVENT_RATE_BINS,
    )

    # Preserve adapter-advertised geometry provenance alongside the bounded
    # rate series used for plotting.
    geometry_source = str(
        dataset.metadata.attributes.get(
            "geometry_source",
            "event_dataset",
        )
    )
    return EventRate(
        event_count=events.size,
        duration_s=events.duration_us / 1_000_000.0,
        bin_counts=tuple(
            int(count)
            for count in counts
        ),
        bin_us=bin_us,
        source=(
            "elope_npz"
            if events.size == source_events.size
            else f"elope_npz_first_{events.size}_events"
        ),
        source_event_count=source_events.size,
        image_width=events.width,
        image_height=events.height,
        geometry_source=geometry_source,
    )


def _resolve_image_geometry(event_rate: EventRate,
                            explicit_width: int | None,
                            explicit_height: int | None) -> tuple[int, int, str]:
    """Resolve one fixed track-plot image plane from input or explicit data."""
    # Explicit geometry is an indivisible pair because either missing dimension
    # would make fixed-plane clipping ambiguous.
    if (explicit_width is None) != (explicit_height is None):
        raise ValueError(
            "--event-width and --event-height must be provided together"
        )
    if (
        explicit_width is not None and
        explicit_height is not None and
        (explicit_width <= 0 or explicit_height <= 0)
    ):
        raise ValueError(
            "--event-width and --event-height must be positive"
        )

    advertised = (
        event_rate.image_width,
        event_rate.image_height,
    )

    # Prefer the event source as authoritative and permit explicit dimensions
    # only when they confirm it exactly.
    if (advertised[0] is None) != (advertised[1] is None):
        raise ValueError(
            "event source returned incomplete image geometry"
        )
    if advertised[0] is not None and advertised[1] is not None:
        if (
            explicit_width is not None and
            explicit_height is not None and
            (explicit_width, explicit_height) != advertised
        ):
            raise ValueError(
                "explicit image geometry conflicts with the event source"
            )
        return (
            advertised[0],
            advertised[1],
            event_rate.geometry_source,
        )

    if explicit_width is not None and explicit_height is not None:
        return (
            explicit_width,
            explicit_height,
            "explicit_override",
        )
    raise ValueError(
        "track image geometry is unavailable; provide --event-width and "
        "--event-height or an event source that advertises dimensions"
    )


def _summarize_ground_truth(rows: Sequence[TrackSample],
                            ground_truth_path: Path | None,
                            ground_truth_rows: Sequence[TrackSample] | None,
                            plots_dir: Path,
                            *,
                            max_dt_s: float) -> GroundTruthResult:
    """Match optional same-format ground truth and render pixel errors."""
    if ground_truth_path is None:
        return GroundTruthResult("unavailable", {}, ())
    if ground_truth_rows is None:
        raise ValueError(
            "ground-truth rows are required for an explicit source"
        )

    # Record source and policy before matching so even a zero-match result
    # remains self-describing.
    metrics: dict[str, float | int | str] = {
        "source": str(ground_truth_path),
        "max_dt_s": max_dt_s,
        "matched_rows": 0,
    }
    errors = _match_ground_truth_errors(
        rows,
        ground_truth_rows,
        max_dt_s,
    )
    metrics.update(
        _ground_truth_metrics(
            errors,
            len(rows),
            len(ground_truth_rows),
        )
    )
    return GroundTruthResult(
        "available",
        metrics,
        (
            _plot_gt_error(
                errors,
                plots_dir / "gt_error.png",
            ),
        ),
    )


def _match_ground_truth_errors(rows: Sequence[TrackSample],
                               ground_truth_rows: Sequence[TrackSample],
                               max_dt_s: float) -> list[float]:
    """Return nearest-in-time same-ID Euclidean pixel errors."""
    # Index ground truth by stable feature and ordered timestamp so each tracker
    # row needs only the two neighbors around its insertion point.
    by_id = _group_by_id(ground_truth_rows)
    gt_times = {
        track_id: [row.t_s for row in track_rows]
        for track_id, track_rows in by_id.items()
    }
    errors: list[float] = []
    for row in rows:
        candidates = by_id.get(row.track_id)
        if not candidates:
            continue
        times = gt_times[row.track_id]
        insert_at = bisect_left(times, row.t_s)
        nearest_indices: list[int] = []
        if insert_at < len(candidates):
            nearest_indices.append(insert_at)
        if insert_at > 0:
            nearest_indices.append(insert_at - 1)

        # Choose the closest admissible same-ID neighbor deterministically,
        # preferring the later candidate only when it is strictly closer.
        best: tuple[float, TrackSample] | None = None
        for index in nearest_indices:
            candidate = candidates[index]
            dt_s = abs(candidate.t_s - row.t_s)
            if (
                dt_s <= max_dt_s and
                (best is None or dt_s < best[0])
            ):
                best = (dt_s, candidate)
        if best is not None:
            candidate = best[1]
            error = math.hypot(
                row.x - candidate.x,
                row.y - candidate.y,
            )
            if not math.isfinite(error):
                raise ValueError(
                    "ground-truth position error must be finite"
                )
            errors.append(error)
    return errors


def _ground_truth_metrics(errors: Sequence[float],
                          track_rows: int,
                          ground_truth_rows: int) -> dict[str, float | int]:
    """Summarize nearest-row position errors."""
    if not errors:
        return {
            "track_rows": track_rows,
            "ground_truth_rows": ground_truth_rows,
            "matched_rows": 0,
            "match_fraction": 0.0,
        }

    # Normalize by the maximum before squaring so finite but extreme error
    # values cannot overflow the RMSE calculation.
    values = np.asarray(errors, dtype=np.float64)
    maximum = float(values.max())
    normalized = (
        values / maximum
        if maximum > 0.0
        else values
    )
    rmse = (
        maximum * float(np.sqrt(np.mean(np.square(normalized))))
        if maximum > 0.0
        else 0.0
    )
    mean_error = (
        maximum * float(np.mean(normalized))
        if maximum > 0.0
        else 0.0
    )
    return {
        "track_rows": track_rows,
        "ground_truth_rows": ground_truth_rows,
        "matched_rows": len(errors),
        "match_fraction": len(errors) / max(track_rows, 1),
        "mean_error_px": mean_error,
        "rmse_px": rmse,
        "median_error_px": float(np.median(values)),
        "max_error_px": maximum,
    }


def _plot_gt_error(errors: Sequence[float],
                   output_path: Path) -> Path:
    """Render nearest-in-time EKLT position errors by matched-row index."""
    contract = TRACK_PLOT_CONTRACTS[output_path.name]
    figure, axis = _new_plot(contract)

    # Reuse the overflow-safe normalized RMSE calculation shown in summary
    # metrics so the annotation and machine-readable value remain consistent.
    if errors:
        values = np.asarray(errors, dtype=np.float64)
        indices = np.arange(1, values.size + 1)
        maximum = float(values.max())
        normalized = (
            values / maximum
            if maximum > 0.0
            else values
        )
        rmse = (
            maximum * float(np.sqrt(np.mean(np.square(normalized))))
            if maximum > 0.0
            else 0.0
        )
        axis.plot(
            indices,
            values,
            color="#B84141",
            linewidth=1.8,
        )
        axis.set_xlim(1.0, float(max(values.size, 2)))
        axis.set_ylim(
            0.0,
            max(float(values.max()) * 1.05, 1e-9),
        )
        _annotate(
            axis,
            (
                f"RMSE: {rmse:.3f} px\n"
                f"Matched rows: {values.size:,}"
            ),
        )
    else:
        _show_empty(
            axis,
            "Ground-truth error is unavailable because no rows matched.",
        )
    return _save_figure(figure, output_path)


def _plot_descriptions() -> dict[str, str]:
    """Return stable reader-facing plot descriptions."""
    return {
        "active_tracks.png": "Active feature IDs per fixed time bin.",
        "track_lifetimes.png": (
            "Feature lifetime distribution by descending rank."
        ),
        "reinit_timeline.png": (
            "Cumulative feature initialization count over time."
        ),
        "track_xy.png": (
            "Feature trajectories in image pixel coordinates."
        ),
        "event_rate.png": "Input event rate over elapsed event time.",
        "gt_error.png": (
            "Nearest-in-time feature error when ground truth exists."
        ),
        "processing_time_cumulative.png": (
            "Accepted EventPacket processing time by native component."
        ),
    }


def _new_plot(contract: PlotContract) -> tuple[Figure, Axes]:
    """Create one labeled Matplotlib chart using the shared contract."""
    figure, axis = plt.subplots(
        figsize=(11.0, 5.2),
        dpi=100,
        constrained_layout=True,
    )
    figure.suptitle(contract.title,
                    fontsize=15,
                    fontweight="semibold")
    axis.set_title(contract.subtitle,
                   fontsize=9,
                   color="#4C5661",
                   pad=10)
    axis.set_xlabel(contract.x_label)
    axis.set_ylabel(contract.y_label)
    axis.grid(True, color="#D8DDE3", linewidth=0.8)
    return figure, axis


def _annotate(axis: Axes, text: str) -> None:
    """Draw one readable metric badge above dense plot data."""
    axis.text(
        0.02,
        0.95,
        text,
        transform=axis.transAxes,
        ha="left",
        va="top",
        bbox={
            "boxstyle": "round,pad=0.35",
            "facecolor": "#FBFBF7",
            "edgecolor": "#CDD1D4",
        },
    )


def _show_empty(axis: Axes, message: str) -> None:
    """Retain labeled unit scales and explain an empty plot."""
    axis.set_xlim(0.0, 1.0)
    axis.set_ylim(0.0, 1.0)
    axis.text(
        0.5,
        0.5,
        message,
        transform=axis.transAxes,
        ha="center",
        va="center",
        color="#555555",
    )


def _save_figure(figure: Figure, output_path: Path) -> Path:
    """Atomically publish one analytical PNG and release its canvas."""
    # Validate both publication paths before encoding the complete figure.
    if output_path.is_symlink():
        plt.close(figure)
        raise ValueError(
            f"refusing symlinked plot output: {output_path}"
        )
    output_path.parent.mkdir(parents=True, exist_ok=True)
    temporary_path = output_path.with_name(
        f".{output_path.stem}.tmp{output_path.suffix}"
    )
    if temporary_path.is_symlink():
        plt.close(figure)
        raise ValueError(
            f"refusing symlinked temporary plot: {temporary_path}"
        )

    # Always release the Matplotlib canvas and stale temporary sibling whether
    # encoding, replacement, or later filesystem operations fail.
    try:
        figure.savefig(temporary_path, dpi=100)
        os.replace(temporary_path, output_path)
    finally:
        temporary_path.unlink(missing_ok=True)
        plt.close(figure)
    return output_path


def _plot_color(index: int) -> str:
    """Return one deterministic color from the bounded track palette."""
    colors = (
        "#1C5FA0",
        "#2E7D4E",
        "#B86023",
        "#744AA5",
        "#BA3A4E",
        "#2A8796",
        "#826926",
        "#525252",
    )
    return colors[index % len(colors)]


def _write_summary(path: Path, summary: dict[str, Any]) -> None:
    """Atomically publish one stable JSON analysis artifact."""
    # Validate public and temporary targets before serializing the complete
    # stable-key document.
    if path.is_symlink():
        raise ValueError(
            f"refusing symlinked summary output: {path}"
        )
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary_path = path.with_name(f".{path.name}.tmp")
    if temporary_path.is_symlink():
        raise ValueError(
            f"refusing symlinked temporary summary: {temporary_path}"
        )
    try:
        temporary_path.write_text(
            json.dumps(summary, indent=2, sort_keys=True) + "\n",
            encoding="utf-8",
        )
        os.replace(temporary_path, path)
    finally:
        temporary_path.unlink(missing_ok=True)


if __name__ == "__main__":
    raise SystemExit(main())
