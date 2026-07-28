"""Public array-based visualization primitives in the extraction foundation."""

from event_vision_utils.viz.accumulation import (
    accumulate_event_counts,
    split_polarity_counts,
)
from event_vision_utils.viz.polarity_image import render_polarity_rgb
from event_vision_utils.viz.time_surface import (
    render_time_surface,
    render_time_surface_uint8,
)

__all__ = [
    "accumulate_event_counts",
    "render_polarity_rgb",
    "render_time_surface",
    "render_time_surface_uint8",
    "split_polarity_counts",
]
