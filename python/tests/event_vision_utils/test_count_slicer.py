"""Test bounded event-count slicing."""

import pytest

from event_vision_utils import EventArray
from event_vision_utils.slicing import iter_count_slices, slice_by_count


def make_events() -> EventArray:
    """Return a deterministic five-event fixture."""
    return EventArray(
        x=[0, 1, 2, 3, 4],
        y=[0, 1, 2, 3, 4],
        p=[1, -1, 1, -1, 1],
        t_us=[0, 1, 2, 3, 4],
        width=10,
        height=10,
    )


def test_slice_by_count_clips_to_available_events() -> None:
    """Clip a bounded request at the source end."""
    chunk = slice_by_count(make_events(), start=3, count=5)

    assert chunk.t_us.tolist() == [3, 4]


def test_iter_count_slices_supports_overlap() -> None:
    """Yield ordered bounded windows with explicit overlap."""
    chunks = list(iter_count_slices(make_events(), count=3, overlap=1))

    assert [chunk.t_us.tolist() for chunk in chunks] == [[0, 1, 2], [2, 3, 4]]


def test_count_slicing_rejects_fractional_window_policy() -> None:
    """Reject values that would otherwise truncate through ``range``."""
    with pytest.raises(ValueError, match="finite integer"):
        slice_by_count(make_events(), start=0.5, count=2)
