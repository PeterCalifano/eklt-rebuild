"""Test bounded event-time slicing."""

import numpy as np
import pytest

from event_vision_utils import EventArray
from event_vision_utils.slicing import iter_time_slices, slice_by_time


def make_events() -> EventArray:
    """Return a deterministic four-event timeline."""
    return EventArray(
        x=[0, 1, 2, 3],
        y=[0, 1, 2, 3],
        p=[1, -1, 1, -1],
        t_us=[0, 10, 20, 35],
        width=10,
        height=10,
    )


def test_slice_by_time_uses_half_open_range_by_default() -> None:
    """Exclude the requested end boundary by default."""
    chunk = slice_by_time(make_events(), start_us=10, end_us=35)

    assert chunk.t_us.tolist() == [10, 20]


def test_slice_by_time_can_include_end_timestamp() -> None:
    """Include an event exactly at the requested end when selected."""
    chunk = slice_by_time(make_events(), start_us=10, end_us=35, include_end=True)

    assert chunk.t_us.tolist() == [10, 20, 35]


def test_iter_time_slices_yields_windowed_chunks() -> None:
    """Yield non-empty source-order windows of bounded duration."""
    chunks = list(iter_time_slices(make_events(), window_us=15))

    assert [chunk.t_us.tolist() for chunk in chunks] == [[0, 10], [20], [35]]


def test_time_slicing_supports_negative_timestamps() -> None:
    """Preserve valid negative event-time intervals."""
    events = EventArray(
        x=[0, 0, 0],
        y=[0, 0, 0],
        p=[1, -1, 1],
        t_us=[-20, -10, 0],
        width=1,
        height=1,
    )

    chunks = list(iter_time_slices(events, window_us=10))

    assert [chunk.t_us.tolist() for chunk in chunks] == [[-20], [-10], [0]]


def test_time_slicing_preserves_complete_int64_timestamp_domain() -> None:
    """Keep the maximum timestamp inside the default half-open range."""
    minimum = int(np.iinfo(np.int64).min)
    maximum = int(np.iinfo(np.int64).max)
    events = EventArray(
        x=[0, 0],
        y=[0, 0],
        p=[-1, 1],
        t_us=np.array([minimum, maximum], dtype=np.int64),
        width=1,
        height=1,
    )

    selected = slice_by_time(events,
                             start_us=minimum,
                             end_us=maximum + 1)
    chunks = list(iter_time_slices(events, window_us=2**64))

    assert selected.t_us.tolist() == [minimum, maximum]
    assert [chunk.t_us.tolist() for chunk in chunks] == [[minimum, maximum]]


def test_time_slicing_rejects_fractional_boundaries() -> None:
    """Reject implicit truncation of microsecond boundaries."""
    with pytest.raises(ValueError, match="finite integer"):
        slice_by_time(make_events(), start_us=0.5, end_us=10)
