"""Test the canonical owning event-array contract."""

import numpy as np
import pytest

from event_vision_utils import EventArray


def test_event_array_normalizes_types_and_reports_duration() -> None:
    """Normalize storage, polarity, and duration without changing order."""
    events = EventArray(
        x=[0.0, 2.0, 4.0],
        y=[1, 3, 5],
        p=[0, 1, 0],
        t_us=[10, 20, 50],
        width=10,
        height=10,
    )

    assert events.size == 3
    assert events.x.dtype == np.int32
    assert events.y.dtype == np.int32
    assert events.p.dtype == np.int8
    assert events.t_us.dtype == np.int64
    assert events.p.tolist() == [-1, 1, -1]
    assert events.t_start_us == 10
    assert events.t_end_us == 50
    assert events.duration_us == 40


def test_event_array_rejects_mismatched_lengths() -> None:
    """Reject parallel columns with different event counts."""
    with pytest.raises(ValueError, match="equal lengths"):
        EventArray(x=[0, 1], y=[0], p=[1], t_us=[0], width=10, height=10)


def test_event_array_rejects_coordinates_outside_sensor() -> None:
    """Reject negative and upper-bound coordinates."""
    with pytest.raises(ValueError, match=r"x coordinates"):
        EventArray(x=[10], y=[0], p=[1], t_us=[0], width=10, height=10)

    with pytest.raises(ValueError, match=r"y coordinates"):
        EventArray(x=[0], y=[-1], p=[1], t_us=[0], width=10, height=10)


def test_event_array_rejects_nonmonotonic_timestamps() -> None:
    """Reject timestamps that regress within one batch."""
    with pytest.raises(ValueError, match="monotonically"):
        EventArray(x=[0, 1], y=[0, 1], p=[1, -1], t_us=[2, 1], width=10, height=10)


def test_event_array_column_export_order_is_configurable() -> None:
    """Export any unique supported column order."""
    events = EventArray(
        x=[1, 2],
        y=[3, 4],
        p=[1, -1],
        t_us=[5, 6],
        width=10,
        height=10,
    )

    columns = events.as_columns(("t_us", "x", "y", "p"))

    assert columns.tolist() == [[5, 1, 3, 1], [6, 2, 4, -1]]


def test_event_array_rejects_values_that_would_wrap_when_narrowed() -> None:
    """Validate coordinates and polarity before fixed-width conversion."""
    with pytest.raises(ValueError, match="x coordinates"):
        EventArray(
            x=[2**32],
            y=[0],
            p=[1],
            t_us=[0],
            width=10,
            height=10,
        )

    with pytest.raises(ValueError, match="polarity"):
        EventArray(
            x=[0],
            y=[0],
            p=[65537],
            t_us=[0],
            width=10,
            height=10,
        )


def test_event_array_duration_uses_complete_int64_domain() -> None:
    """Compute duration without overflowing a NumPy int64 subtraction."""
    timestamps_us = np.array(
        [np.iinfo(np.int64).min, np.iinfo(np.int64).max],
        dtype=np.int64,
    )
    events = EventArray(
        x=[0, 0],
        y=[0, 0],
        p=[-1, 1],
        t_us=timestamps_us,
        width=1,
        height=1,
    )

    assert events.duration_us == 2**64 - 1


def test_event_array_rejects_ambiguous_column_order_and_frame_id() -> None:
    """Require a stable frame identity and unique exported columns."""
    events = EventArray(
        x=[0],
        y=[0],
        p=[1],
        t_us=[0],
        width=1,
        height=1,
    )

    with pytest.raises(ValueError, match="duplicates"):
        events.as_columns(("x", "x"))
    with pytest.raises(ValueError, match="frame_id"):
        EventArray(
            x=[0],
            y=[0],
            p=[1],
            t_us=[0],
            width=1,
            height=1,
            frame_id=" ",
        )
