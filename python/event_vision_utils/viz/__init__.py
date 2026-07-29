"""Public array, analytical-plot, and streamed-video helpers."""

from event_vision_utils.viz.accumulation import (
    accumulate_event_counts,
    split_polarity_counts,
)
from event_vision_utils.viz.event_cloud import (
    EVENT_CLOUD_PLOT_CONTRACT,
    render_event_stream_3d_views,
)
from event_vision_utils.viz.event_rate import (
    compute_event_rate,
    event_rate_plot_contract,
    render_event_rate_plot,
    render_event_rate_series,
)
from event_vision_utils.viz.plot_contract import PlotContract
from event_vision_utils.viz.polarity_image import render_polarity_rgb
from event_vision_utils.viz.time_surface import (
    render_time_surface,
    render_time_surface_uint8,
)
from event_vision_utils.viz.track_overlay import (
    TrackVideoArtifact,
    write_track_dot_video,
)
from event_vision_utils.viz.video_writer import (
    VideoArtifact,
    write_event_preview,
    write_video_or_png_sequence,
)

__all__ = [
    "EVENT_CLOUD_PLOT_CONTRACT",
    "PlotContract",
    "TrackVideoArtifact",
    "VideoArtifact",
    "accumulate_event_counts",
    "compute_event_rate",
    "event_rate_plot_contract",
    "render_event_rate_plot",
    "render_event_rate_series",
    "render_event_stream_3d_views",
    "render_polarity_rgb",
    "render_time_surface",
    "render_time_surface_uint8",
    "split_polarity_counts",
    "write_event_preview",
    "write_track_dot_video",
    "write_video_or_png_sequence",
]
