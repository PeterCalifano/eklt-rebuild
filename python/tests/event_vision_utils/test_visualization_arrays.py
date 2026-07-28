"""Test bounded array-based visualization primitives."""

import numpy as np
import pytest

from event_vision_utils import EventArray
from event_vision_utils.viz import (
    accumulate_event_counts,
    render_polarity_rgb,
    render_time_surface,
    render_time_surface_uint8,
    split_polarity_counts,
)


def make_events() -> EventArray:
    """Return events containing positive, negative, and mixed pixels."""
    return EventArray(
        x=[0, 1, 1, 2],
        y=[0, 1, 1, 2],
        p=[1, -1, 1, -1],
        t_us=[0, 10, 20, 30],
        width=4,
        height=4,
    )


def test_accumulate_event_counts_unsigned_and_signed() -> None:
    """Accumulate counts without a narrow integer overflow type."""
    events = make_events()

    unsigned = accumulate_event_counts(events)
    signed = accumulate_event_counts(events, signed=True)

    assert unsigned[1, 1] == 2
    assert signed[1, 1] == 0
    assert signed[2, 2] == -1
    assert unsigned.dtype == np.int64


def test_split_polarity_counts() -> None:
    """Separate positive and negative counts at repeated pixels."""
    positive, negative = split_polarity_counts(make_events())

    assert positive[1, 1] == 1
    assert negative[1, 1] == 1


def test_render_polarity_rgb_marks_mixed_pixels() -> None:
    """Use the mixed color where both polarities occur."""
    image = render_polarity_rgb(make_events())

    assert image.shape == (4, 4, 3)
    assert image.dtype == np.uint8
    assert image[1, 1].tolist() == [80, 80, 80]


def test_render_time_surface_shapes_and_scales() -> None:
    """Return normalized float and uint8 time-surface representations."""
    surface = render_time_surface(make_events())
    image = render_time_surface_uint8(make_events())

    assert surface.shape == (4, 4)
    assert surface.dtype == np.float32
    assert image.shape == (4, 4)
    assert image.dtype == np.uint8
    assert float(surface[2, 2]) == 1.0


def test_render_time_surface_retains_negative_timestamps() -> None:
    """Do not confuse negative event times with empty-pixel sentinels."""
    events = EventArray(
        x=[1, 1],
        y=[1, 1],
        p=[1, 1],
        t_us=[-20, -10],
        width=3,
        height=3,
    )

    surface = render_time_surface(events)

    assert float(surface[1, 1]) == 1.0


def test_render_time_surface_marks_a_single_timestamp_as_latest() -> None:
    """Distinguish occupied pixels from empty pixels in a zero-span batch."""
    events = EventArray(
        x=[1],
        y=[1],
        p=[1],
        t_us=[-10],
        width=3,
        height=3,
    )

    surface = render_time_surface(events)

    assert float(surface[1, 1]) == 1.0
    assert float(surface[0, 0]) == 0.0


def test_visualization_policy_rejects_wrapped_colors_and_polarity() -> None:
    """Reject invalid rendering values before unsigned conversion."""
    with pytest.raises(ValueError, match="positive_color"):
        render_polarity_rgb(make_events(), positive_color=(256, 0, 0))
    with pytest.raises(ValueError, match="polarity"):
        render_time_surface(make_events(), polarity=0)

    empty = EventArray(
        x=[],
        y=[],
        p=[],
        t_us=[],
        width=1,
        height=1,
    )
    with pytest.raises(ValueError, match="decay_us"):
        render_time_surface(empty, decay_us=0)
