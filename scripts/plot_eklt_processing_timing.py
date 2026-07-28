#!/usr/bin/env python3
"""Validate and plot EKLT EventPacket processing-time composition.

The CSV is produced by the ROS2 event-only adapter. This module keeps the
measurement contract independent of ROS so timing artifacts can be validated
and rendered in a headless Python or Conda environment.

Example:
    python scripts/plot_eklt_processing_timing.py \
        --input outputs/ros2_eventpacket_bag/processing_timing.csv \
        --output outputs/ros2_eventpacket_bag/plots/processing_time_cumulative.png \
        --summary-output outputs/ros2_eventpacket_bag/processing_timing_summary.json

Output:
    Wrote 2000 plotted samples from 2434 timing rows.
"""

from __future__ import annotations

import argparse
import csv
import json
import math
import os
from collections.abc import Sequence
from dataclasses import dataclass
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
from matplotlib import pyplot as plt  # noqa: E402


EXPECTED_FIELDS = (
    "packet_index",
    "event_time_s",
    "fibar_ms",
    "eklt_ms",
    "overhead_ms",
    "total_ms",
)
FIBAR_COLOR = "#2F6B9A"
EKLT_COLOR = "#D9822B"
OVERHEAD_COLOR = "#A8ADB4"
TOTAL_COLOR = "#252A31"
PLOT_TITLE = "EventPacket Processing Time by Component"
PLOT_SUBTITLE = (
    "Per accepted EventPacket [ms]; total includes decoding, native work, "
    "and requested outputs"
)
PLOT_X_LABEL = "Event Time Since First Accepted Packet [s]"
PLOT_Y_LABEL = "Wall Time per Packet [ms]"


@dataclass(frozen=True)
class ProcessingTimingSeries:
    """Validated per-packet processing-time samples.

    Attributes:
        packet_indices: Strictly increasing accepted-packet indices.
        event_times_s: Nondecreasing newest-event timestamps in seconds.
        fibar_ms: FIBAR wall time per packet in milliseconds.
        eklt_ms: Native EKLT wall time excluding FIBAR in milliseconds.
        overhead_ms: ROS2 decoding and requested-output remainder in milliseconds.
        total_ms: Complete measured processing-step time in milliseconds.

    Example:
        series = ProcessingTimingSeries(
            (1,), (0.1,), (1.0,), (2.0,), (0.5,), (3.5,)
        )
        print(len(series))

    Output:
        1
    """

    packet_indices: tuple[int, ...]
    event_times_s: tuple[float, ...]
    fibar_ms: tuple[float, ...]
    eklt_ms: tuple[float, ...]
    overhead_ms: tuple[float, ...]
    total_ms: tuple[float, ...]

    def __len__(self) -> int:
        """Return the number of validated timing rows."""
        return len(self.packet_indices)


@dataclass(frozen=True)
class ProcessingTimingSummary:
    """Serializable metadata for one processing-time plot.

    Attributes:
        input_csv: Validated timing CSV path.
        output_plot: Rendered plot path.
        sample_count: Number of complete timing rows.
        plotted_sample_count: Number of rows selected for drawing.
        first_event_time_s: First newest-event timestamp.
        last_event_time_s: Last newest-event timestamp.
        event_duration_s: Covered event-time interval.
        mean_ms: Mean timing by component and total.
        p95_ms: Ninety-fifth percentile timing by component and total.
        total_p50_ms: Median complete processing time.
        maximum_total_ms: Maximum complete processing time.

    Example:
        summary = ProcessingTimingSummary(
            "timing.csv", "timing.png", 1, 1, 0.1, 0.1, 0.0,
            {"total": 3.5}, {"total": 3.5}, 3.5, 3.5
        )
        print(summary.sample_count)

    Output:
        1
    """

    input_csv: str
    output_plot: str
    sample_count: int
    plotted_sample_count: int
    first_event_time_s: float
    last_event_time_s: float
    event_duration_s: float
    mean_ms: dict[str, float]
    p95_ms: dict[str, float]
    total_p50_ms: float
    maximum_total_ms: float

    def as_json_dict(self) -> dict[str, object]:
        """Return the stable reader-facing JSON representation.

        Returns:
            JSON-compatible summary with plot semantics and statistics.

        Example:
            print(summary.as_json_dict()["status"])

        Output:
            passed
        """
        return {
            "status": "passed",
            "input_csv": self.input_csv,
            "output_plot": self.output_plot,
            "sample_count": self.sample_count,
            "plotted_sample_count": self.plotted_sample_count,
            "first_event_time_s": self.first_event_time_s,
            "last_event_time_s": self.last_event_time_s,
            "event_duration_s": self.event_duration_s,
            "mean_ms": self.mean_ms,
            "p95_ms": self.p95_ms,
            "total_p50_ms": self.total_p50_ms,
            "maximum_total_ms": self.maximum_total_ms,
            "plot": {
                "type": "stacked_area",
                "title": PLOT_TITLE,
                "subtitle": PLOT_SUBTITLE,
                "x": "event_time_since_first_packet_s",
                "x_label": PLOT_X_LABEL,
                "y": "wall_time_per_packet_ms",
                "y_label": PLOT_Y_LABEL,
                "bands": ["fibar_ms", "eklt_ms", "overhead_ms"],
                "boundary_line": "total_ms",
            },
        }


def load_processing_timing_csv(input_path: Path) -> ProcessingTimingSeries:
    """Load and validate one ROS2 processing-time CSV.

    Args:
        input_path: CSV written by ``processing_timing_file_csv``.

    Returns:
        Complete timing rows in their accepted-packet order.

    Raises:
        ValueError: If the header, values, ordering, or additive contract fails.

    Example:
        series = load_processing_timing_csv(Path("processing_timing.csv"))
        print(len(series))

    Output:
        2434
    """
    packet_indices: list[int] = []
    event_times_s: list[float] = []
    fibar_ms: list[float] = []
    eklt_ms: list[float] = []
    overhead_ms: list[float] = []
    total_ms: list[float] = []

    with input_path.open(newline="", encoding="utf-8") as input_stream:
        reader = csv.DictReader(input_stream)
        if tuple(reader.fieldnames or ()) != EXPECTED_FIELDS:
            raise ValueError(
                "processing timing CSV header must be "
                + ",".join(EXPECTED_FIELDS)
            )

        for line_number, row in enumerate(reader, start=2):
            if None in row or any(row[field] is None for field in EXPECTED_FIELDS):
                raise ValueError(
                    f"processing timing row {line_number} has an invalid field count"
                )

            try:
                packet_index = int(row["packet_index"])
                values = tuple(
                    float(row[field])
                    for field in EXPECTED_FIELDS[1:]
                )
            except (TypeError, ValueError) as error:
                raise ValueError(
                    f"processing timing row {line_number} is not numeric"
                ) from error

            event_time_s, fibar_value, eklt_value, overhead_value, total_value = values
            if packet_index <= 0:
                raise ValueError(
                    f"processing timing row {line_number} has a nonpositive packet index"
                )
            if packet_indices and packet_index <= packet_indices[-1]:
                raise ValueError(
                    f"processing timing row {line_number} regresses packet order"
                )
            if not all(math.isfinite(value) for value in values):
                raise ValueError(
                    f"processing timing row {line_number} contains a non-finite value"
                )
            if event_time_s < 0.0 or min(
                fibar_value, eklt_value, overhead_value, total_value
            ) < 0.0:
                raise ValueError(
                    f"processing timing row {line_number} contains a negative value"
                )
            if event_times_s and event_time_s < event_times_s[-1]:
                raise ValueError(
                    f"processing timing row {line_number} regresses event time"
                )

            component_total = fibar_value + eklt_value + overhead_value
            additive_tolerance = 1e-6 * max(1.0, total_value)
            if abs(component_total - total_value) > additive_tolerance:
                raise ValueError(
                    f"processing timing row {line_number} violates additive timing"
                )

            packet_indices.append(packet_index)
            event_times_s.append(event_time_s)
            fibar_ms.append(fibar_value)
            eklt_ms.append(eklt_value)
            overhead_ms.append(overhead_value)
            total_ms.append(total_value)

    if not packet_indices:
        raise ValueError("processing timing CSV contains no samples")

    return ProcessingTimingSeries(
        packet_indices=tuple(packet_indices),
        event_times_s=tuple(event_times_s),
        fibar_ms=tuple(fibar_ms),
        eklt_ms=tuple(eklt_ms),
        overhead_ms=tuple(overhead_ms),
        total_ms=tuple(total_ms),
    )


def build_stacked_boundaries(series: ProcessingTimingSeries) -> tuple[
    tuple[float, ...],
    tuple[float, ...],
    tuple[float, ...],
]:
    """Build cumulative component boundaries without double-counting total.

    Args:
        series: Validated timing samples.

    Returns:
        FIBAR, FIBAR-plus-EKLT, and complete stacked boundaries.

    Example:
        lower, middle, total = build_stacked_boundaries(series)
        print(total[-1])

    Output:
        4.2
    """
    fibar_boundary = series.fibar_ms
    eklt_boundary = tuple(
        fibar_value + eklt_value
        for fibar_value, eklt_value in zip(
            series.fibar_ms, series.eklt_ms, strict=True
        )
    )
    total_boundary = tuple(
        fibar_value + eklt_value + overhead_value
        for fibar_value, eklt_value, overhead_value in zip(
            series.fibar_ms,
            series.eklt_ms,
            series.overhead_ms,
            strict=True,
        )
    )
    return fibar_boundary, eklt_boundary, total_boundary


def _uniform_indices(sample_count: int, maximum_points: int) -> tuple[int, ...]:
    """Select deterministic uniformly spaced row indices."""
    if maximum_points <= 0:
        raise ValueError("maximum plot points must be positive")
    if sample_count <= maximum_points:
        return tuple(range(sample_count))
    if maximum_points == 1:
        return (sample_count - 1,)

    return tuple(
        round(index * (sample_count - 1) / (maximum_points - 1))
        for index in range(maximum_points)
    )


def _percentile(values: Sequence[float], percentage: float) -> float:
    """Return a linearly interpolated percentile for non-empty values."""
    if not values:
        raise ValueError("percentile input cannot be empty")
    if percentage < 0.0 or percentage > 100.0:
        raise ValueError("percentage must lie between zero and one hundred")

    ordered = sorted(values)
    position = (len(ordered) - 1) * percentage / 100.0
    lower_index = math.floor(position)
    upper_index = math.ceil(position)
    fraction = position - lower_index
    return (
        ordered[lower_index] * (1.0 - fraction)
        + ordered[upper_index] * fraction
    )


def render_processing_timing_plot(series: ProcessingTimingSeries,
                                  output_path: Path,
                                  *,
                                  maximum_points: int = 2000,
) -> int:
    """Render the stacked processing-time composition chart.

    Args:
        series: Validated complete timing rows.
        output_path: PNG destination.
        maximum_points: Maximum uniformly selected rows drawn in the figure.

    Returns:
        Number of plotted samples.

    Raises:
        ValueError: If ``maximum_points`` is not positive.
        RuntimeError: If the PNG cannot be written.

    Example:
        count = render_processing_timing_plot(
            series, Path("processing_time_cumulative.png")
        )
        print(count)

    Output:
        2000
    """
    selected_indices = _uniform_indices(len(series), maximum_points)
    first_event_time_s = series.event_times_s[0]
    relative_time_s = [
        series.event_times_s[index] - first_event_time_s
        for index in selected_indices
    ]
    selected_fibar_ms = [series.fibar_ms[index] for index in selected_indices]
    selected_eklt_ms = [series.eklt_ms[index] for index in selected_indices]
    selected_overhead_ms = [
        series.overhead_ms[index] for index in selected_indices
    ]
    selected_total_ms = [series.total_ms[index] for index in selected_indices]

    figure, axis = plt.subplots(figsize=(16.0, 9.0), dpi=100)
    figure.patch.set_facecolor("#F7F8FA")
    axis.set_facecolor("#FFFFFF")
    collections = axis.stackplot(
        relative_time_s,
        selected_fibar_ms,
        selected_eklt_ms,
        selected_overhead_ms,
        labels=(
            "FIBAR Reconstruction",
            "EKLT Excluding FIBAR",
            "Interface and Output",
        ),
        colors=(FIBAR_COLOR, EKLT_COLOR, OVERHEAD_COLOR),
        alpha=0.92,
    )
    for collection in collections:
        collection.set_edgecolor("#FFFFFF")
        collection.set_linewidth(0.35)
    axis.plot(
        relative_time_s,
        selected_total_ms,
        color=TOTAL_COLOR,
        linewidth=1.35,
        label="Total Processing Step",
        zorder=5,
    )

    figure.suptitle(
        PLOT_TITLE,
        fontsize=18,
        fontweight="semibold",
        x=0.065,
        y=0.965,
        ha="left",
    )
    axis.set_title(
        PLOT_SUBTITLE,
        fontsize=11,
        color="#4C5661",
        loc="left",
        pad=14,
    )
    axis.set_xlabel(PLOT_X_LABEL)
    axis.set_ylabel(PLOT_Y_LABEL)
    axis.grid(axis="y", color="#D8DCE2", linewidth=0.7, alpha=0.75)
    axis.set_axisbelow(True)
    axis.spines[["top", "right"]].set_visible(False)
    axis.legend(loc="upper right", frameon=False, ncols=2)
    if len(relative_time_s) == 1:
        axis.set_xlim(-0.5, 0.5)

    total_p50_ms = _percentile(series.total_ms, 50.0)
    total_p95_ms = _percentile(series.total_ms, 95.0)
    axis.text(
        0.012,
        0.985,
        f"Total p50 {total_p50_ms:.3f} ms  |  p95 {total_p95_ms:.3f} ms",
        transform=axis.transAxes,
        ha="left",
        va="top",
        fontsize=10,
        color="#4C5661",
        bbox={
            "boxstyle": "round,pad=0.35",
            "facecolor": "#FFFFFF",
            "edgecolor": "#D8DCE2",
            "alpha": 0.92,
        },
    )

    output_path.parent.mkdir(parents=True, exist_ok=True)
    temporary_path = output_path.with_name(
        f".{output_path.stem}.tmp{output_path.suffix}"
    )
    try:
        # Use fixed reader-facing margins so long data ranges cannot make
        # tight-layout clip the figure title or the unit-bearing subtitle.
        figure.subplots_adjust(left=0.075, right=0.97, bottom=0.11, top=0.82)
        figure.savefig(temporary_path, format="png", facecolor=figure.get_facecolor())
        os.replace(temporary_path, output_path)
    finally:
        plt.close(figure)
        temporary_path.unlink(missing_ok=True)

    if not output_path.is_file() or output_path.stat().st_size == 0:
        raise RuntimeError(f"processing timing plot was not written: {output_path}")
    return len(selected_indices)


def _mean(values: Sequence[float]) -> float:
    """Return the arithmetic mean for non-empty values."""
    if not values:
        raise ValueError("mean input cannot be empty")
    return math.fsum(values) / len(values)


def _build_summary(series: ProcessingTimingSeries,
                   input_path: Path,
                   output_path: Path,
                   plotted_sample_count: int) -> ProcessingTimingSummary:
    """Build deterministic full-series metadata for the rendered chart."""
    component_values = {
        "fibar": series.fibar_ms,
        "eklt": series.eklt_ms,
        "overhead": series.overhead_ms,
        "total": series.total_ms,
    }
    return ProcessingTimingSummary(
        input_csv=str(input_path),
        output_plot=str(output_path),
        sample_count=len(series),
        plotted_sample_count=plotted_sample_count,
        first_event_time_s=series.event_times_s[0],
        last_event_time_s=series.event_times_s[-1],
        event_duration_s=series.event_times_s[-1] - series.event_times_s[0],
        mean_ms={
            name: _mean(values)
            for name, values in component_values.items()
        },
        p95_ms={
            name: _percentile(values, 95.0)
            for name, values in component_values.items()
        },
        total_p50_ms=_percentile(series.total_ms, 50.0),
        maximum_total_ms=max(series.total_ms),
    )


def write_processing_timing_summary(summary: ProcessingTimingSummary,
                                    output_path: Path,
) -> None:
    """Write timing metadata atomically as JSON.

    Args:
        summary: Full-series statistics and plot contract.
        output_path: JSON destination.

    Example:
        write_processing_timing_summary(summary, Path("timing_summary.json"))
        print(Path("timing_summary.json").is_file())

    Output:
        True
    """
    output_path.parent.mkdir(parents=True, exist_ok=True)
    temporary_path = output_path.with_name(f".{output_path.name}.tmp")
    try:
        temporary_path.write_text(
            json.dumps(summary.as_json_dict(), indent=2, sort_keys=True) + "\n",
            encoding="utf-8",
        )
        os.replace(temporary_path, output_path)
    finally:
        temporary_path.unlink(missing_ok=True)


def _parse_arguments(arguments: Sequence[str] | None) -> argparse.Namespace:
    """Parse command-line arguments for the timing renderer."""
    parser = argparse.ArgumentParser(
        description="Validate and plot ROS2 EKLT processing timing."
    )
    parser.add_argument("--input", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--summary-output", type=Path, required=True)
    parser.add_argument("--maximum-points", type=int, default=2000)
    return parser.parse_args(arguments)


def main(arguments: Sequence[str] | None = None) -> int:
    """Run the processing-time validation and plotting example.

    Args:
        arguments: Optional command-line arguments without the program name.

    Returns:
        Zero after writing the plot and summary.

    Example:
        status = main(
            (
                "--input", "processing_timing.csv",
                "--output", "processing_time_cumulative.png",
                "--summary-output", "processing_timing_summary.json",
            )
        )
        print(status)

    Output:
        Wrote 2000 plotted samples from 2434 timing rows.
        0
    """
    parsed = _parse_arguments(arguments)
    series = load_processing_timing_csv(parsed.input)
    plotted_sample_count = render_processing_timing_plot(
        series,
        parsed.output,
        maximum_points=parsed.maximum_points,
    )
    summary = _build_summary(
        series,
        parsed.input,
        parsed.output,
        plotted_sample_count,
    )
    write_processing_timing_summary(summary, parsed.summary_output)
    print(
        f"Wrote {plotted_sample_count} plotted samples "
        f"from {len(series)} timing rows."
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
