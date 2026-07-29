"""Compute and render bounded event-rate diagnostics.

Example:
    from pathlib import Path

    from event_vision_utils.core import EventArray

    events = EventArray(
        x=[0, 1, 2, 3],
        y=[0, 1, 2, 3],
        p=[1, -1, 1, -1],
        t_us=[0, 10_000, 20_000, 30_000],
        width=4,
        height=4,
    )
    output = render_event_rate_plot(
        events, Path("event_rate.png"), bin_us=10_000
    )
    print(output.name)

Output:
    event_rate.png
"""

from __future__ import annotations

import os
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np

from event_vision_utils.core.event_array import EventArray
from event_vision_utils.viz.plot_contract import PlotContract


_DEFAULT_MAX_BINS = 1_000_000
_EventRateArrays = tuple[np.ndarray, np.ndarray, np.ndarray]


def compute_event_rate(events: EventArray,
                       *,
                       bin_us: int,
                       max_bins: int = _DEFAULT_MAX_BINS) -> _EventRateArrays:
    """Compute fixed-width event counts and rates.

    Timestamp arithmetic is performed with Python integers so the complete
    signed-int64 event domain cannot overflow while assigning bins.

    Args:
        events: Valid event stream.
        bin_us: Positive event-time bin width in microseconds.
        max_bins: Maximum output bins permitted for bounded memory use.

    Returns:
        Bin start timestamps in microseconds, int64 event counts, and rates in
        events per second.

    Raises:
        ValueError: If the bin policy is invalid or would exceed ``max_bins``.

    Example:
        events = EventArray(
            x=[0, 1, 2, 3],
            y=[0, 1, 2, 3],
            p=[1, -1, 1, -1],
            t_us=[0, 10_000, 20_000, 30_000],
            width=4,
            height=4,
        )
        _, counts, rates = compute_event_rate(events, bin_us=10_000)
        print(counts.sum(), rates.shape)

    Output:
        4 (4,)
    """
    if bin_us <= 0:
        raise ValueError("bin_us must be positive")
    if max_bins <= 0:
        raise ValueError("max_bins must be positive")
    if events.size == 0:
        empty = np.asarray([], dtype=np.int64)
        return empty, empty.copy(), empty.astype(np.float64)

    start_us = int(events.t_us[0])
    stop_us = int(events.t_us[-1])
    bin_count = (stop_us - start_us) // bin_us + 1
    if bin_count > max_bins:
        raise ValueError(
            f"event-rate output requires {bin_count} bins, "
            f"exceeding max_bins={max_bins}"
        )

    # Convert timestamps independently before subtraction so a stream spanning
    # both signed-int64 extremes cannot overflow in NumPy arithmetic.
    bin_indices = np.fromiter(
        (
            (int(timestamp_us) - start_us) // bin_us
            for timestamp_us in events.t_us
        ),
        dtype=np.int64,
        count=events.size,
    )
    counts = np.bincount(
        bin_indices,
        minlength=bin_count,
    ).astype(np.int64, copy=False)
    starts = np.fromiter(
        (
            start_us + index * bin_us
            for index in range(bin_count)
        ),
        dtype=np.int64,
        count=bin_count,
    )
    rates_hz = counts.astype(np.float64) / (bin_us / 1_000_000.0)
    return starts, counts, rates_hz


def event_rate_plot_contract(event_count: int,
                             *,
                             bin_us: int,
                             source: str = "validated event array") -> PlotContract:
    """Return the visible label contract for an event-rate plot.

    Args:
        event_count: Nonnegative number of represented events.
        bin_us: Positive event-time bin width in microseconds.
        source: Reader-facing event-source description.

    Returns:
        Validated title, subtitle, and unit-bearing axis labels.

    Example:
        contract = event_rate_plot_contract(20, bin_us=10_000)
        print(contract.y_label)

    Output:
        Event Rate [events/s]
    """
    if event_count < 0:
        raise ValueError("event_count must be nonnegative")
    if bin_us <= 0:
        raise ValueError("bin_us must be positive")
    normalized_source = source.strip()
    if not normalized_source:
        raise ValueError("source must not be empty")

    return PlotContract(
        title="Event Rate over Time",
        subtitle=(
            f"Source: {normalized_source}; fixed "
            f"{bin_us / 1_000.0:g} ms bins; {event_count:,} events."
        ),
        x_label="Time Since First Event [s]",
        y_label="Event Rate [events/s]",
    )


def render_event_rate_plot(events: EventArray,
                           output_path: str | Path,
                           *,
                           bin_us: int,
                           width: int = 800,
                           height: int = 420,
                           max_bins: int = _DEFAULT_MAX_BINS,
                           source: str = "validated event array") -> Path:
    """Render event rate with explicit time and rate scales.

    Args:
        events: Valid event stream.
        output_path: Destination PNG path.
        bin_us: Positive event-time bin width in microseconds.
        width: Output width in pixels.
        height: Output height in pixels.
        max_bins: Maximum plotted bins permitted for bounded memory use.
        source: Reader-facing event-source description.

    Returns:
        Atomically published PNG path.

    Raises:
        ValueError: If the bin policy or chart dimensions are invalid.

    Example:
        events = EventArray(
            x=[0, 1],
            y=[0, 1],
            p=[1, -1],
            t_us=[0, 10_000],
            width=2,
            height=2,
        )
        output = render_event_rate_plot(
            events, Path("event_rate.png"), bin_us=10_000
        )
        print(output.name)

    Output:
        event_rate.png
    """
    _, _, rates_hz = compute_event_rate(
        events,
        bin_us=bin_us,
        max_bins=max_bins,
    )
    return render_event_rate_series(
        rates_hz,
        output_path,
        bin_us=bin_us,
        event_count=events.size,
        source=source,
        width=width,
        height=height,
        max_bins=max_bins,
    )


def render_event_rate_series(rates_hz: np.ndarray,
                             output_path: str | Path,
                             *,
                             bin_us: int,
                             event_count: int,
                             source: str,
                             width: int = 800,
                             height: int = 420,
                             max_bins: int = _DEFAULT_MAX_BINS) -> Path:
    """Render one already-binned event-rate series.

    This entrypoint lets dataset and transport-specific readers share the same
    analytical renderer without introducing a second chart implementation.

    Args:
        rates_hz: One-dimensional finite nonnegative rates.
        output_path: Destination PNG path.
        bin_us: Positive bin width in microseconds.
        event_count: Nonnegative represented event count.
        source: Reader-facing event-source description.
        width: Output width in pixels.
        height: Output height in pixels.
        max_bins: Maximum plotted bins permitted for bounded memory use.

    Returns:
        Atomically published PNG path.

    Raises:
        ValueError: If the series, bin policy, or dimensions are invalid.

    Example:
        output = render_event_rate_series(
            np.array([100.0, 200.0]),
            Path("event_rate.png"),
            bin_us=10_000,
            event_count=3,
            source="fixture",
        )
        print(output.name)

    Output:
        event_rate.png
    """
    if width < 480 or height < 320:
        raise ValueError(
            "event-rate chart must be at least 480 by 320 pixels"
        )
    if max_bins <= 0:
        raise ValueError("max_bins must be positive")
    rates = np.asarray(rates_hz, dtype=np.float64)
    if rates.ndim != 1:
        raise ValueError("rates_hz must be one-dimensional")
    if rates.size > max_bins:
        raise ValueError(
            f"event-rate series has {rates.size} bins, "
            f"exceeding max_bins={max_bins}"
        )
    if not bool(np.all(np.isfinite(rates))) or bool(
        np.any(rates < 0.0)
    ):
        raise ValueError(
            "event rates must be finite and nonnegative"
        )

    contract = event_rate_plot_contract(
        event_count,
        bin_us=bin_us,
        source=source,
    )
    bin_s = bin_us / 1_000_000.0
    elapsed_s = np.arange(rates.size, dtype=np.float64) * bin_s

    # Use Matplotlib for the analytical chart while keeping the canvas and
    # plotted series bounded by explicit dimensions and bin count.
    figure, axis = plt.subplots(
        figsize=(width / 100.0, height / 100.0),
        dpi=100,
        constrained_layout=True,
    )
    axis.set_title(contract.title, fontsize=15, fontweight="semibold")
    axis.text(
        0.5,
        1.01,
        contract.subtitle,
        transform=axis.transAxes,
        ha="center",
        va="bottom",
        fontsize=9,
        color="#4C5661",
    )
    axis.set_xlabel(contract.x_label)
    axis.set_ylabel(contract.y_label)
    axis.grid(True, color="#D8DDE3", linewidth=0.8)

    if rates.size:
        axis.plot(
            elapsed_s,
            rates,
            color="#147850",
            linewidth=1.8,
        )
        axis.set_xlim(0.0, max(float(elapsed_s[-1]), bin_s))
        axis.set_ylim(
            0.0,
            max(float(rates.max()) * 1.05, 1.0),
        )
        axis.text(
            0.02,
            0.95,
            (
                f"Peak: {float(rates.max()):,.1f} events/s\n"
                f"Maximum bin count: "
                f"{int(round(float(rates.max()) * bin_s)):,}"
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
            "No events in the selected interval.",
            transform=axis.transAxes,
            ha="center",
            va="center",
            color="#555555",
        )

    output = Path(output_path)
    if output.is_symlink():
        plt.close(figure)
        raise ValueError(
            f"refusing symlinked event-rate output: {output}"
        )
    output.parent.mkdir(parents=True, exist_ok=True)
    temporary_path = output.with_name(
        f".{output.stem}.tmp{output.suffix}"
    )
    if temporary_path.is_symlink():
        plt.close(figure)
        raise ValueError(
            f"refusing symlinked temporary output: {temporary_path}"
        )
    try:
        figure.savefig(temporary_path, dpi=100)
        os.replace(temporary_path, output)
    finally:
        temporary_path.unlink(missing_ok=True)
        plt.close(figure)
    return output
