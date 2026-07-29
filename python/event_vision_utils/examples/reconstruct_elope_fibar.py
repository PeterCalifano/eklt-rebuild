"""Run FIBAR reconstruction and dense patch diagnostics on ELOPE events.

The event preview, reconstructed images, and patch mosaic are encoded from
iterators. Reconstruction events are replayed for the patch pass so enlarged
debug frames never accumulate in RAM.

Example:
    python -m event_vision_utils.examples.reconstruct_elope_fibar \
        --input data/elope/test/0028.npz \
        --output-dir outputs/elope_reconstruction

Output:
    outputs/elope_reconstruction/fibar_patches.mp4
"""

from __future__ import annotations

import argparse
import json
import math
import os
import shutil
import time
from collections.abc import Iterator
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
from PIL import Image, ImageDraw

from event_vision_utils.core import EventArray
from event_vision_utils.io import load_event_dataset
from event_vision_utils.recon import (
    CFibarReconstructor,
    SFibarConfig,
    SLocalFeaturePatch,
    fibar_native_available,
)
from event_vision_utils.slicing import iter_time_slices
from event_vision_utils.viz import (
    EVENT_CLOUD_PLOT_CONTRACT,
    PlotContract,
    VideoArtifact,
    accumulate_event_counts,
    event_rate_plot_contract,
    render_event_rate_plot,
    render_event_stream_3d_views,
    render_polarity_rgb,
    write_event_preview,
    write_video_or_png_sequence,
)


_MAX_PATCH_FRAME_PIXELS = 16_777_216


PATCH_QUALITY_PLOT_CONTRACT = PlotContract(
    title="FIBAR Patch Gradient Quality",
    subtitle=(
        "Mean squared image-gradient magnitude for each inspected "
        "candidate patch."
    ),
    x_label="Inspected Patch [patch index]",
    y_label="Mean Squared Image Gradient [intensity²/px²]",
)


@dataclass(frozen=True, slots=True)
class _PatchQualitySample:
    """Quality metadata retained for one inspected candidate patch."""

    x: int
    y: int
    valid_fraction: float
    gradient_energy: float
    accepted: bool


@dataclass(frozen=True, slots=True)
class _PatchDebugTile:
    """Normalized patch pixels and the diagnostics displayed in one slot."""

    image: np.ndarray
    x: int
    y: int
    valid_fraction: float
    gradient_energy: float
    accepted: bool


@dataclass(slots=True)
class _PatchQualityAccumulator:
    """Retain a bounded prefix while counting every inspected patch."""

    max_samples: int
    samples: list[_PatchQualitySample] = field(default_factory=list)
    inspected_count: int = 0

    def add(self, samples: list[_PatchQualitySample]) -> None:
        """Count one patch batch and retain only the configured prefix."""
        # Count the complete stream while retaining a deterministic bounded
        # prefix suitable for the analytical plot.
        self.inspected_count += len(samples)
        remaining = max(0, self.max_samples - len(self.samples))
        self.samples.extend(samples[:remaining])


_PatchDebugResult = tuple[np.ndarray, list[_PatchQualitySample]]


def main(argv: list[str] | None = None) -> int:
    """Run the ELOPE FIBAR reconstruction example.

    Args:
        argv: Optional command-line arguments excluding the executable name.

    Returns:
        Zero on success or two when the native FIBAR wrapper is unavailable.

    Example:
        status = main([
            "--input", "events.npz",
            "--output-dir", "output/reconstruction",
        ])
        print(status)

    Output:
        0
    """
    # Parse all rendering and retention policy through the CLI before loading
    # the potentially large immutable event sequence.
    parser = argparse.ArgumentParser(
        description="Run ELOPE FIBAR reconstruction example demo."
    )
    parser.add_argument("--input", required=True, type=Path)
    parser.add_argument("--output-dir", required=True, type=Path)
    parser.add_argument("--width", type=int)
    parser.add_argument("--height", type=int)
    parser.add_argument("--dt-ms", default=20.0, type=float)
    parser.add_argument("--event-preview-fps", default=100.0, type=float)
    parser.add_argument("--max-3d-points", default=50_000, type=int)
    parser.add_argument("--patch-panel-size", default=800, type=int)
    parser.add_argument("--patch-columns", default=2, type=int)
    parser.add_argument("--patch-max-candidates", default=8, type=int)
    parser.add_argument(
        "--max-patch-quality-samples",
        default=50_000,
        type=int,
    )
    args = parser.parse_args(argv)

    # Bound time, canvas, candidate, and retained-sample policy before any
    # output cleanup or external encoder process can begin.
    if not math.isfinite(args.dt_ms) or not 1.0 <= args.dt_ms <= 1_000_000.0:
        raise ValueError("--dt-ms must be finite and in [1, 1000000]")
    if (
        not math.isfinite(args.event_preview_fps) or
        not 0.0 < args.event_preview_fps <= 1000.0
    ):
        raise ValueError(
            "--event-preview-fps must be finite and in (0, 1000]"
        )
    if not 1 <= args.max_3d_points <= 1_000_000:
        raise ValueError("--max-3d-points must be in [1, 1000000]")
    if not 128 <= args.patch_panel_size <= 2048:
        raise ValueError("--patch-panel-size must be in [128, 2048]")
    if not 1 <= args.patch_max_candidates <= 32:
        raise ValueError("--patch-max-candidates must be in [1, 32]")
    if not 1 <= args.patch_columns <= args.patch_max_candidates:
        raise ValueError("--patch-columns must be in [1, --patch-max-candidates]")
    if args.max_patch_quality_samples <= 0:
        raise ValueError(
            "--max-patch-quality-samples must be positive"
        )
    _patch_debug_frame_geometry(
        max_tiles=args.patch_max_candidates,
        panel_size=args.patch_panel_size,
        mosaic_columns=args.patch_columns,
    )

    # Validate the immutable source before removing any prior owned artifact.
    dataset = load_event_dataset(
        args.input,
        adapter="elope",
        width=args.width,
        height=args.height,
    )

    # Establish the owned artifact root only after the source has passed its
    # complete adapter validation.
    started = time.perf_counter()
    output_dir = _prepare_output_directory(args.output_dir)
    plots_dir = output_dir / "plots"
    plots_dir.mkdir(parents=True, exist_ok=True)

    events = dataset.events
    preview_dt_ms = 1000.0 / args.event_preview_fps

    # Generate transport-independent event diagnostics before consulting the
    # optional native wrapper so blocked runs still explain their input.
    event_preview = write_event_preview(
        events,
        output_dir / "events_preview.mp4",
        dt_ms=preview_dt_ms,
        fps=args.event_preview_fps,
    )
    event_rate_path = render_event_rate_plot(
        events,
        plots_dir / "event_rate.png",
        bin_us=int(round(preview_dt_ms * 1000.0)),
        source="official ELOPE event array",
    )
    event_cloud_path = render_event_stream_3d_views(
        events,
        plots_dir / "event_stream_3d_views.png",
        max_points=args.max_3d_points,
    )
    event_rate_contract = event_rate_plot_contract(
        events.size,
        bin_us=int(round(preview_dt_ms * 1000.0)),
        source="official ELOPE event array",
    )

    # Start from a complete blocked-state schema. Native success fills in the
    # reconstruction-specific artifacts without changing shared field types.
    summary = {
        "schema_version": 1,
        "artifact_type": "elope_fibar_reconstruction",
        "run_name": "elope_reconstruction",
        "status": "blocked",
        "input": str(args.input),
        "event_count": events.size,
        "track_count": 0,
        "track_rows": 0,
        "duration_s": events.duration_us / 1_000_000.0,
        "dataset_adapter": dataset.metadata.name,
        "dataset_metadata": dataset.metadata.attributes,
        "runtime_s": 0.0,
        "plots": [
            str(event_rate_path.relative_to(output_dir)),
            str(event_cloud_path.relative_to(output_dir)),
        ],
        "plot_contracts": {
            event_rate_path.name: event_rate_contract.as_dict(),
            event_cloud_path.name: EVENT_CLOUD_PLOT_CONTRACT.as_dict(),
        },
        "preview": _relative_video_artifact(
            event_preview,
            output_dir,
        ),
        "preview_fps": args.event_preview_fps,
        "preview_dt_ms": preview_dt_ms,
        "gt_status": "unavailable",
        "gt_metrics": {},
        "blocker": "",
    }

    # Publish the portable diagnostics and an explicit blocker when the native
    # wrapper is absent rather than failing with an import-specific traceback.
    if not fibar_native_available():
        summary["blocker"] = (
            "the eklt_rebuild native wrapper is not built"
        )
        summary["runtime_s"] = time.perf_counter() - started
        _write_summary(output_dir, summary)
        return 2

    # Derive one native reconstruction policy from validated geometry and keep
    # patch-quality retention independent from the full inspected count.
    patch_quality = _PatchQualityAccumulator(
        max_samples=args.max_patch_quality_samples,
    )
    patch_radius = 5 if min(events.width, events.height) >= 16 else 1
    window_us = int(round(args.dt_ms * 1000.0))

    # Encode the scalar reconstruction first, retaining only the current FIBAR
    # image and ffmpeg input buffer.
    reconstruction_output = write_video_or_png_sequence(
        _iter_reconstruction_frames(events, window_us=window_us),
        output_dir / "reconstruction.mp4",
        fps=max(1.0, 1000.0 / args.dt_ms),
    )

    # Replay the same immutable event stream through a fresh reconstructor so
    # the larger patch mosaic is also streamed instead of stored in memory.
    patch_output = write_video_or_png_sequence(
        _iter_patch_debug_frames(
            events,
            window_us=window_us,
            radius=patch_radius,
            max_candidates=args.patch_max_candidates,
            panel_size=args.patch_panel_size,
            mosaic_columns=args.patch_columns,
            quality_accumulator=patch_quality,
        ),
        output_dir / "fibar_patches.mp4",
        fps=max(1.0, 1000.0 / args.dt_ms),
    )
    patch_quality_path = _write_patch_quality_plot(
        patch_quality.samples,
        plots_dir / "patch_quality.png",
        inspected_count=patch_quality.inspected_count,
    )

    # Complete the same summary object only after both independent event passes
    # and their bounded diagnostic artifacts have succeeded.
    summary["status"] = "passed"
    summary["blocker"] = ""
    summary["reconstruction"] = _relative_video_artifact(
        reconstruction_output,
        output_dir,
    )
    summary["patch_debug"] = _relative_video_artifact(
        patch_output,
        output_dir,
    )
    summary["reconstruction_frames"] = reconstruction_output.frame_count
    summary["patch_debug_frames"] = patch_output.frame_count
    summary["patch_quality_count"] = patch_quality.inspected_count
    summary["patch_quality_samples"] = len(patch_quality.samples)
    summary["patch_quality_truncated"] = (
        patch_quality.inspected_count > len(patch_quality.samples)
    )
    summary["patch_layout"] = {
        "event_panel_size": patch_output.height,
        "mosaic_columns": args.patch_columns,
        "max_candidates": args.patch_max_candidates,
    }
    summary["plots"].append(str(patch_quality_path.relative_to(output_dir)))
    summary["plot_contracts"][
        patch_quality_path.name
    ] = PATCH_QUALITY_PLOT_CONTRACT.as_dict()
    summary["runtime_s"] = time.perf_counter() - started
    _write_summary(output_dir, summary)
    return 0


def _iter_reconstruction_frames(events: EventArray,
                                *,
                                window_us: int) -> Iterator[np.ndarray]:
    """Yield finite-normalized FIBAR frames from one bounded event pass."""
    # Own one reconstructor for the iterator lifetime so causal filter state is
    # preserved while only the current output image is exposed.
    reconstructor = CFibarReconstructor(
        SFibarConfig(width=events.width, height=events.height)
    )

    # Submit each non-overlapping time slice atomically and request the image at
    # that slice's final accepted timestamp.
    for chunk in iter_time_slices(events, window_us=window_us):
        reconstructor.accept_events(chunk.x, chunk.y, chunk.p, chunk.t_us)
        yield _normalize_float_image(
            reconstructor.request_image(int(chunk.t_us[-1]))
        )


def _iter_patch_debug_frames(events: EventArray,
                             *,
                             window_us: int,
                             radius: int,
                             max_candidates: int,
                             panel_size: int,
                             mosaic_columns: int,
                             quality_accumulator: _PatchQualityAccumulator) -> Iterator[np.ndarray]:
    """Yield patch mosaics from a fresh bounded FIBAR event pass."""
    # Use a fresh reconstructor because the immutable source is deliberately
    # replayed instead of retaining images from the scalar-video pass.
    reconstructor = CFibarReconstructor(
        SFibarConfig(width=events.width, height=events.height)
    )

    # Accumulate only bounded scalar quality records while yielding each large
    # mosaic directly to the encoder.
    for chunk in iter_time_slices(events, window_us=window_us):
        reconstructor.accept_events(chunk.x, chunk.y, chunk.p, chunk.t_us)
        frame, frame_qualities = _make_patch_debug_frame(
            reconstructor,
            chunk,
            int(chunk.t_us[-1]),
            radius=radius,
            max_candidates=max_candidates,
            panel_size=panel_size,
            mosaic_columns=mosaic_columns,
        )
        quality_accumulator.add(frame_qualities)
        yield frame


def _normalize_float_image(image: object) -> np.ndarray:
    """Normalize one finite scalar image without changing FIBAR state."""
    array = np.asarray(image, dtype=np.float32)
    if array.ndim != 2 or array.size == 0:
        raise ValueError(
            "reconstructed image must be one nonempty 2D array"
        )
    if not bool(np.all(np.isfinite(array))):
        raise ValueError("reconstructed image values must be finite")

    # Promote the subtraction to float64 so finite float32 extrema cannot
    # overflow while determining the display span.
    min_value = float(array.min())
    max_value = float(array.max())
    span = max(max_value - min_value, 1e-6)
    normalized = (
        array.astype(np.float64) - min_value
    ) * (255.0 / span)
    return np.rint(normalized).astype(np.uint8)


def _make_patch_debug_frame(reconstructor: CFibarReconstructor,
                            chunk: EventArray,
                            t_us: int,
                            *,
                            radius: int,
                            max_candidates: int = 8,
                            panel_size: int = 800,
                            mosaic_columns: int = 2) -> _PatchDebugResult:
    """Render one enlarged event panel and its bounded local-patch mosaic."""
    # Rank candidates from the current event slice only; the native
    # reconstructor supplies the causal image and patch contents.
    base = render_polarity_rgb(chunk)
    counts = accumulate_event_counts(chunk)
    candidates = _top_candidates(counts, limit=max_candidates, radius=radius)
    qualities: list[_PatchQualitySample] = []
    patch_tiles: list[_PatchDebugTile] = []

    # Request and classify only the bounded deterministic candidate set, while
    # preserving every inspected quality record for the accumulator.
    for x, y in candidates:
        patch = reconstructor.request_patch(x, y, radius, t_us)
        valid_fraction = patch.valid_fraction
        gradient_energy = patch.gradient_energy
        accepted = valid_fraction >= 0.75 and gradient_energy >= 0.0
        qualities.append(
            _PatchQualitySample(
                x=x,
                y=y,
                valid_fraction=valid_fraction,
                gradient_energy=gradient_energy,
                accepted=accepted,
            )
        )
        color = (
            (30, 180, 70)
            if accepted
            else (230, 120, 20)
        )
        _draw_square(base, x, y, radius, color)
        patch_tiles.append(
            _render_patch_tile(patch, accepted=accepted, x=x, y=y)
        )
    return (
        _compose_patch_debug_frame(
            base,
            patch_tiles,
            max_tiles=max_candidates,
            panel_size=panel_size,
            mosaic_columns=mosaic_columns,
        ),
        qualities,
    )


def _top_candidates(counts: np.ndarray,
                    *,
                    limit: int,
                    radius: int) -> list[tuple[int, int]]:
    """Select the strongest in-bounds event-count pixels deterministically."""
    if counts.size == 0:
        return []

    # Sort the flattened count image once so strongest activity is considered
    # first and zero-activity pixels terminate the scan.
    flat = np.argsort(counts.reshape(-1))[::-1]
    candidates: list[tuple[int, int]] = []
    height, width = counts.shape
    for index in flat:
        if counts.reshape(-1)[index] <= 0:
            break
        y, x = divmod(int(index), width)

        # Exclude boundary candidates before calling the native patch API so
        # every returned tile has the requested complete square support.
        if (
            x - radius < 0
            or y - radius < 0
            or x + radius >= width
            or y + radius >= height
        ):
            continue
        candidates.append((x, y))
        if len(candidates) >= limit:
            break
    return candidates


def _draw_square(image: np.ndarray,
                 x: int,
                 y: int,
                 radius: int,
                 color: tuple[int, int, int]) -> None:
    """Draw one clipped candidate boundary into an RGB event image."""
    height, width = image.shape[:2]
    x0 = max(0, x - radius)
    x1 = min(width - 1, x + radius)
    y0 = max(0, y - radius)
    y1 = min(height - 1, y + radius)
    image[y0, x0 : x1 + 1] = color
    image[y1, x0 : x1 + 1] = color
    image[y0 : y1 + 1, x0] = color
    image[y0 : y1 + 1, x1] = color


def _render_patch_tile(patch: SLocalFeaturePatch,
                       *,
                       accepted: bool,
                       x: int,
                       y: int) -> _PatchDebugTile:
    """Normalize one native patch and retain its displayed quality metadata."""
    intensity = np.asarray(
        patch.intensity,
        dtype=np.float32,
    ).reshape(patch.height, patch.width)
    tile = _normalize_float_image(intensity)
    return _PatchDebugTile(
        image=np.repeat(tile[:, :, None], 3, axis=2),
        x=x,
        y=y,
        valid_fraction=patch.valid_fraction,
        gradient_energy=patch.gradient_energy,
        accepted=accepted,
    )


def _compose_patch_debug_frame(base: np.ndarray,
                               patch_tiles: list[_PatchDebugTile],
                               *,
                               max_tiles: int,
                               panel_size: int,
                               mosaic_columns: int) -> np.ndarray:
    """Compose a large event panel and fixed dark-background patch grid."""
    tile_size, frame_width, frame_height = _patch_debug_frame_geometry(
        max_tiles=max_tiles,
        panel_size=panel_size,
        mosaic_columns=mosaic_columns,
    )

    # Match the event panel height to the patch grid and keep nearest-neighbor
    # pixels so both event and reconstructed-patch structure stay discrete.
    nearest = getattr(getattr(Image, "Resampling", Image), "NEAREST")
    base_image = Image.fromarray(base).resize(
        (frame_height, frame_height),
        resample=nearest,
    )
    canvas = Image.new(
        "RGB",
        (frame_width, frame_height),
        (22, 24, 28),
    )
    canvas.paste(base_image, (0, 0))
    draw = ImageDraw.Draw(canvas)
    draw.rectangle((0, 0, 178, 19), fill=(245, 245, 245))
    draw.text((5, 4), "event activity + candidates", fill=(20, 20, 20))

    # Draw every configured slot, including explicit empty slots, so frame
    # geometry and tile positions remain stable across time.
    for index in range(max_tiles):
        row = index // mosaic_columns
        column = index % mosaic_columns
        left = frame_height + column * tile_size
        top = row * tile_size
        slot_bounds = (
            left + 2,
            top + 2,
            left + tile_size - 3,
            top + tile_size - 3,
        )
        draw.rectangle(
            slot_bounds,
            fill=(38, 41, 47),
            outline=(82, 86, 94),
            width=2,
        )
        if index >= len(patch_tiles):
            draw.text(
                (left + 9, top + 9),
                f"#{index} no candidate",
                fill=(170, 174, 182),
            )
            continue

        tile = patch_tiles[index]
        tile_image = Image.fromarray(tile.image).resize(
            (tile_size - 8, tile_size - 8),
            resample=nearest,
        )
        canvas.paste(tile_image, (left + 4, top + 4))
        border_color = (30, 190, 75) if tile.accepted else (235, 125, 25)
        border_width = max(3, tile_size // 50)
        draw.rectangle(slot_bounds, outline=border_color, width=border_width)

        # Place compact diagnostics over an opaque band so labels do not hide
        # the local intensity structure below the first few pixels.
        label_height = min(38, max(24, tile_size // 5))
        draw.rectangle(
            (left + 4, top + 4, left + tile_size - 5, top + label_height),
            fill=(18, 20, 24),
        )
        status = "accepted" if tile.accepted else "rejected"
        draw.text(
            (left + 9, top + 7),
            f"#{index} ({tile.x},{tile.y}) {status}",
            fill=border_color,
        )
        draw.text(
            (left + 9, top + 20),
            f"valid={tile.valid_fraction:.2f} grad={tile.gradient_energy:.3g}",
            fill=(230, 230, 230),
        )

    return np.asarray(canvas, dtype=np.uint8)


def _patch_debug_frame_geometry(max_tiles: int,
                                *,
                                panel_size: int,
                                mosaic_columns: int) -> tuple[int, int, int]:
    """Resolve bounded patch-mosaic tile, width, and height geometry."""
    if max_tiles <= 0:
        raise ValueError("max_tiles must be positive")
    if mosaic_columns <= 0 or mosaic_columns > max_tiles:
        raise ValueError("mosaic_columns must be in [1, max_tiles]")
    rows = (max_tiles + mosaic_columns - 1) // mosaic_columns
    if panel_size < rows * 32:
        raise ValueError("panel_size is too small for the requested patch grid")

    # Use an even tile edge so the complete fixed-size frame is directly
    # compatible with common yuv420p encoders.
    tile_size = max(32, ((panel_size // rows) // 2) * 2)
    mosaic_height = rows * tile_size
    mosaic_width = mosaic_columns * tile_size
    frame_width = mosaic_height + mosaic_width
    if frame_width * mosaic_height > _MAX_PATCH_FRAME_PIXELS:
        raise ValueError(
            "patch mosaic geometry exceeds the encoded-frame pixel limit"
        )
    return tile_size, frame_width, mosaic_height


def _write_patch_quality_plot(qualities: list[_PatchQualitySample],
                              output_path: Path,
                              *,
                              inspected_count: int | None = None) -> Path:
    """Write a labeled gradient-energy trend for every inspected patch."""
    # Preserve the distinction between all inspected candidates and the
    # bounded prefix retained for rendering.
    if inspected_count is None:
        inspected_count = len(qualities)
    if inspected_count < len(qualities):
        raise ValueError(
            "inspected_count cannot be smaller than retained samples"
        )
    if output_path.is_symlink():
        raise ValueError(
            f"refusing symlinked patch-quality output: {output_path}"
        )

    # Build the complete reader-facing chart contract before inspecting the
    # retained numerical values.
    output_path.parent.mkdir(parents=True, exist_ok=True)
    figure, axis = plt.subplots(
        figsize=(9.0, 4.8),
        dpi=100,
        constrained_layout=True,
    )
    axis.set_title(
        PATCH_QUALITY_PLOT_CONTRACT.title,
        fontsize=15,
        fontweight="semibold",
    )
    axis.text(
        0.5,
        1.01,
        PATCH_QUALITY_PLOT_CONTRACT.subtitle,
        transform=axis.transAxes,
        ha="center",
        va="bottom",
        fontsize=9,
        color="#4C5661",
    )
    axis.set_xlabel(PATCH_QUALITY_PLOT_CONTRACT.x_label)
    axis.set_ylabel(PATCH_QUALITY_PLOT_CONTRACT.y_label)
    axis.grid(True, color="#D8DDE3", linewidth=0.8)

    values = np.asarray(
        [sample.gradient_energy for sample in qualities],
        dtype=np.float64,
    )

    # Render retained quality in inspection order and expose truncation through
    # the badge rather than extrapolating unretained values.
    if values.size:
        if not bool(np.all(np.isfinite(values))) or bool(
            np.any(values < 0.0)
        ):
            raise ValueError(
                "patch gradient energies must be finite and nonnegative"
            )
        indices = np.arange(values.size, dtype=np.int64)
        axis.plot(
            indices,
            values,
            color="#744AA5",
            linewidth=1.8,
        )
        axis.set_xlim(0.0, float(max(values.size - 1, 1)))
        axis.set_ylim(0.0, max(float(values.max()) * 1.05, 1e-6))
        accepted_count = sum(
            sample.accepted
            for sample in qualities
        )
        axis.text(
            0.02,
            0.95,
            (
                f"Peak: {float(values.max()):.4g} intensity²/px²\n"
                f"Accepted in retained sample: "
                f"{accepted_count:,}/{len(qualities):,}\n"
                f"Retained: {len(qualities):,}/{inspected_count:,}"
            ),
            transform=axis.transAxes,
            ha="left",
            va="top",
            bbox={
                "boxstyle": "round,pad=0.35",
                "facecolor": "#FBFBF7",
                "edgecolor": "#CDD1D4",
            },
        )
    else:
        axis.set_xlim(0.0, 1.0)
        axis.set_ylim(0.0, 1.0)
        axis.text(
            0.5,
            0.5,
            "No candidate patches were inspected.",
            transform=axis.transAxes,
            ha="center",
            va="center",
            color="#555555",
        )

    # Publish through one owned sibling so interrupted rendering cannot replace
    # a previously valid diagnostic with a partial PNG.
    temporary_path = output_path.with_name(
        f".{output_path.stem}.tmp{output_path.suffix}"
    )
    if temporary_path.is_symlink():
        plt.close(figure)
        raise ValueError(
            f"refusing symlinked temporary output: {temporary_path}"
        )
    try:
        figure.savefig(temporary_path, dpi=100)
        os.replace(temporary_path, output_path)
    finally:
        temporary_path.unlink(missing_ok=True)
        plt.close(figure)
    return output_path


def _prepare_output_directory(output_path: Path) -> Path:
    """Validate one output root and remove only known reconstruction artifacts."""
    # Reject roots that could turn the fixed cleanup list into repository- or
    # filesystem-wide destruction.
    if output_path.is_symlink():
        raise ValueError(
            f"refusing symlinked output directory: {output_path}"
        )
    output_dir = output_path.resolve(strict=False)
    repository_root = Path(__file__).resolve().parents[3]
    filesystem_root = Path(output_dir.anchor)
    if (
        output_dir == filesystem_root or
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

    # These are the complete artifacts owned by this example. Preserve every
    # unrelated entry below the caller-selected directory.
    owned_artifacts = (
        Path("summary.json"),
        Path("events_preview.mp4"),
        Path("events_preview_frames"),
        Path("reconstruction.mp4"),
        Path("reconstruction_frames"),
        Path("fibar_patches.mp4"),
        Path("fibar_patches_frames"),
        Path("plots/event_rate.png"),
        Path("plots/event_stream_3d_views.png"),
        Path("plots/patch_quality.png"),
    )
    artifact_paths = [
        _resolve_owned_artifact(output_dir, relative_path)
        for relative_path in owned_artifacts
    ]

    # Validate the complete cleanup set before removing any prior artifact.
    for artifact_path in artifact_paths:
        if artifact_path.is_dir():
            shutil.rmtree(artifact_path)
        elif artifact_path.is_file():
            artifact_path.unlink()
    return output_dir


def _resolve_owned_artifact(output_dir: Path,
                            relative_path: Path) -> Path:
    """Validate and return one explicitly named cleanup artifact."""
    # Walk existing parents without following symlinks before validating the
    # final file or directory named by the ownership manifest.
    parent_path = output_dir
    for part in relative_path.parts[:-1]:
        parent_path /= part
        if parent_path.is_symlink():
            raise ValueError(
                f"refusing symlinked owned-artifact parent: {parent_path}"
            )
        if parent_path.exists() and not parent_path.is_dir():
            raise ValueError(
                f"owned-artifact parent is not a directory: {parent_path}"
            )

    artifact_path = output_dir / relative_path
    if artifact_path.is_symlink():
        raise ValueError(
            f"refusing symlinked owned artifact: {artifact_path}"
        )
    if artifact_path.exists() and not (
        artifact_path.is_dir() or artifact_path.is_file()
    ):
        raise ValueError(
            f"owned artifact has unsupported type: {artifact_path}"
        )
    return artifact_path


def _relative_video_artifact(artifact: VideoArtifact,
                             output_dir: Path) -> dict[str, str | int | float | None]:
    """Return video metadata with a path relative to the component root."""
    # Re-resolve the writer's published path before serializing it so an
    # encoder fallback cannot escape the relocatable component root.
    artifact_path = Path(artifact.path).resolve(strict=False)
    try:
        relative_path = artifact_path.relative_to(output_dir)
    except ValueError as exc:
        raise ValueError(
            f"video artifact escaped the output directory: {artifact.path}"
        ) from exc

    metadata = artifact.as_dict()
    metadata["path"] = relative_path.as_posix()
    return metadata


def _write_summary(output_dir: Path, summary: dict[str, Any]) -> None:
    """Atomically write the example summary with stable ordering."""
    # Validate both the public target and its exact temporary sibling before
    # writing any JSON bytes.
    summary_path = output_dir / "summary.json"
    if summary_path.is_symlink():
        raise ValueError(
            f"refusing symlinked summary target: {summary_path}"
        )
    temporary_path = output_dir / ".summary.tmp.json"
    if temporary_path.is_symlink():
        raise ValueError(
            f"refusing symlinked temporary summary: {temporary_path}"
        )
    try:
        temporary_path.write_text(
            json.dumps(summary, indent=2, sort_keys=True) + "\n",
            encoding="utf-8",
        )
        os.replace(temporary_path, summary_path)
    finally:
        temporary_path.unlink(missing_ok=True)


if __name__ == "__main__":
    raise SystemExit(main())
