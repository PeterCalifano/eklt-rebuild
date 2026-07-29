"""Render bounded multi-view diagnostics for an event stream.

The event cloud is sampled through a uniform three-dimensional voxel grid so
long sequences remain inexpensive to inspect.

Example:
    from pathlib import Path

    from event_vision_utils.core import EventArray

    events = EventArray(
        x=[0, 1],
        y=[0, 1],
        p=[1, -1],
        t_us=[0, 10_000],
        width=2,
        height=2,
    )
    output = render_event_stream_3d_views(
        events, Path("event_stream_3d_views.png")
    )
    print(output.name)

Output:
    event_stream_3d_views.png
"""

from __future__ import annotations

import os
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib.figure import Figure
from matplotlib.lines import Line2D
from matplotlib.ticker import MaxNLocator
import numpy as np

from event_vision_utils.core.event_array import EventArray
from event_vision_utils.viz.plot_contract import PlotContract


_MAX_EVENT_CLOUD_POINTS = 1_000_000


EVENT_CLOUD_TITLE = "Event Stream in Space and Time"
X_AXIS_LABEL = "X Coordinate [px]"
Y_AXIS_LABEL = "Y Coordinate [px]"
TIME_AXIS_LABEL = "Relative Event Time [s]"
EVENT_CLOUD_PLOT_CONTRACT = PlotContract(
    title=EVENT_CLOUD_TITLE,
    subtitle="Six orthographic views of a bounded X/Y/time voxel sample.",
    x_label="Displayed Horizontal Coordinate [px or s]",
    y_label="Displayed Vertical Coordinate [px or s]",
)


def render_event_stream_3d_views(events: EventArray,
                                 output_path: str | Path,
                                 *,
                                 max_points: int = 50_000) -> Path:
    """Render ±X, ±Y, and ±time views in one 2-by-3 figure.

    Args:
        events: Valid event stream in sensor pixel coordinates.
        output_path: Destination PNG path.
        max_points: Maximum displayed event count after uniform voxel sampling.

    Returns:
        Written figure path.

    Raises:
        ValueError: If the stream is empty or ``max_points`` is not positive.

    Example:
        events = EventArray(
            x=[0, 1],
            y=[0, 1],
            p=[1, -1],
            t_us=[0, 10_000],
            width=2,
            height=2,
        )
        output = render_event_stream_3d_views(
            events, Path("event_stream_3d_views.png"), max_points=50_000
        )
        print(output.name)

    Output:
        event_stream_3d_views.png
    """
    # Validate both publication paths before allocating the comparatively
    # large six-view Matplotlib canvas.
    output = Path(output_path)
    if output.is_symlink():
        raise ValueError(
            f"refusing symlinked event-cloud output: {output}"
        )
    output.parent.mkdir(parents=True, exist_ok=True)
    temporary_path = output.with_name(
        f".{output.stem}.tmp{output.suffix}"
    )
    if temporary_path.is_symlink():
        raise ValueError(
            f"refusing symlinked temporary output: {temporary_path}"
        )
    figure = _build_event_stream_3d_figure(
        events,
        max_points=max_points,
    )
    try:
        figure.savefig(
            temporary_path,
            dpi=120,
            facecolor=figure.get_facecolor(),
        )
        os.replace(temporary_path, output)
    finally:
        temporary_path.unlink(missing_ok=True)
        plt.close(figure)
    return output


def _build_event_stream_3d_figure(events: EventArray,
                                  *,
                                  max_points: int) -> Figure:
    """Build the six-view figure so tests can inspect its label contract."""
    if events.size == 0:
        raise ValueError("event stream must not be empty")
    if not 0 < max_points <= _MAX_EVENT_CLOUD_POINTS:
        raise ValueError(
            "max_points must be in [1, 1000000]"
        )

    # Materialize only the bounded voxel sample used by all six projections;
    # the complete event stream remains outside the figure state.
    selected = _uniform_spatiotemporal_indices(events, max_points=max_points)
    x_coordinates = events.x[selected]
    y_coordinates = events.y[selected]
    relative_time_s = (
        events.t_us[selected].astype(np.float64) -
        float(events.t_us[0])
    ) / 1_000_000.0
    positive_mask = events.p[selected] > 0
    duration_s = max(events.duration_us / 1_000_000.0, 1e-9)

    # Fix the view order and the hidden line-of-sight axis so every subplot has
    # a stable reader-facing orientation and comparable sensor/time limits.
    views = (
        ("View along +t Axis", 90.0, -90.0, "t"),
        ("View along −t Axis", -90.0, -90.0, "t"),
        ("View along +X Axis", 0.0, 0.0, "x"),
        ("View along −X Axis", 0.0, 180.0, "x"),
        ("View along +Y Axis", 0.0, 90.0, "y"),
        ("View along −Y Axis", 0.0, -90.0, "y"),
    )
    figure = plt.figure(figsize=(15.0, 9.0))
    figure.patch.set_facecolor("#F7F8FA")

    # Encode polarity redundantly through color and marker shape so the views
    # remain interpretable when printed or viewed with impaired color vision.
    for index, (title, elevation, azimuth, hidden_axis) in enumerate(
        views, start=1
    ):
        axis = figure.add_subplot(2, 3, index, projection="3d")
        axis.scatter(
            x_coordinates[positive_mask],
            y_coordinates[positive_mask],
            relative_time_s[positive_mask],
            color="#C43C35",
            marker=".",
            s=2.0,
            alpha=0.55,
            linewidths=0.0,
            rasterized=True,
        )
        axis.scatter(
            x_coordinates[~positive_mask],
            y_coordinates[~positive_mask],
            relative_time_s[~positive_mask],
            color="#3266A8",
            marker="x",
            s=2.0,
            alpha=0.55,
            linewidths=0.35,
            rasterized=True,
        )
        axis.view_init(elev=elevation, azim=azimuth)
        axis.set_proj_type("ortho")
        axis.set(
            xlabel=X_AXIS_LABEL,
            ylabel=Y_AXIS_LABEL,
            zlabel=TIME_AXIS_LABEL,
            xlim=(0, max(events.width - 1, 1)),
            ylim=(0, max(events.height - 1, 1)),
            zlim=(0.0, duration_s),
        )
        axis.set_box_aspect((1.0, 1.0, 1.0))
        axis.xaxis.set_major_locator(MaxNLocator(5))
        axis.yaxis.set_major_locator(MaxNLocator(5))
        axis.zaxis.set_major_locator(MaxNLocator(5))
        axis.tick_params(labelsize=8, pad=1)
        axis.xaxis.label.set_size(9)
        axis.yaxis.label.set_size(9)
        axis.zaxis.label.set_size(9)
        if hidden_axis == "x":
            axis.set_xticks([])
            axis.set_xlabel("")
        elif hidden_axis == "y":
            axis.set_yticks([])
            axis.set_ylabel("")
        else:
            axis.set_zticks([])
            axis.set_zlabel("")
        axis.text2D(
            0.5,
            1.02,
            title,
            transform=axis.transAxes,
            horizontalalignment="center",
            fontweight="bold",
        )

    # Reserve figure-level space for the shared title, sample provenance, and
    # legend instead of duplicating that metadata inside each projection.
    figure.suptitle(
        EVENT_CLOUD_TITLE,
        fontsize=18,
        fontweight="semibold",
        y=0.975,
    )
    figure.text(
        0.5,
        0.943,
        (
            "Uniform X/Y/time voxel sample "
            f"({selected.size:,}/{events.size:,} events shown)"
        ),
        ha="center",
        va="top",
        fontsize=10,
        color="#4C5661",
    )
    figure.legend(
        handles=(
            Line2D(
                (),
                (),
                color="#C43C35",
                marker=".",
                linestyle="None",
                markersize=8,
                label="Positive Polarity (+1)",
            ),
            Line2D(
                (),
                (),
                color="#3266A8",
                marker="x",
                linestyle="None",
                markersize=6,
                label="Negative Polarity (−1)",
            ),
        ),
        loc="upper center",
        bbox_to_anchor=(0.5, 0.925),
        ncols=2,
        frameon=False,
    )
    figure.subplots_adjust(
        left=0.035,
        right=0.985,
        bottom=0.055,
        top=0.84,
        wspace=0.12,
        hspace=0.18,
    )
    return figure


def _uniform_spatiotemporal_indices(events: EventArray,
                                     *,
                                     max_points: int) -> np.ndarray:
    """Select at most one event per uniform x/y/time voxel."""
    if events.size <= max_points:
        return np.arange(events.size, dtype=np.int64)

    # Use equal-resolution bins on x, y, and time so dense spatial regions or
    # bursts cannot consume the complete display budget by themselves.
    bins_per_axis = max(1, int(np.ceil(max_points ** (1.0 / 3.0))))
    x_bins = np.minimum(
        events.x.astype(np.int64) * bins_per_axis // max(events.width, 1),
        bins_per_axis - 1,
    )
    y_bins = np.minimum(
        events.y.astype(np.int64) * bins_per_axis // max(events.height, 1),
        bins_per_axis - 1,
    )
    duration_us = max(events.duration_us, 1)

    # Floating-point normalization is sufficient for display sampling and
    # avoids signed-int64 overflow when a stream spans both timestamp extremes.
    relative_time = (
        events.t_us.astype(np.float64) -
        float(events.t_us[0])
    )
    time_bins = np.minimum(
        np.floor(
            relative_time * bins_per_axis / float(duration_us)
        ).astype(np.int64),
        bins_per_axis - 1,
    )

    # Keep the first causal event in each voxel, then preserve causal order in
    # the selected result. Uniform thinning is applied only if occupied voxels
    # still exceed the hard display bound.
    linear_bins = (
        (time_bins * bins_per_axis + y_bins) * bins_per_axis + x_bins
    )
    _, selected = np.unique(linear_bins, return_index=True)
    selected.sort()
    if selected.size > max_points:
        uniform_positions = np.linspace(
            0, selected.size - 1, max_points, dtype=np.int64
        )
        selected = selected[uniform_positions]
    return selected.astype(np.int64, copy=False)
