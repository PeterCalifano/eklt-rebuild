"""Slice monotonic event arrays by bounded microsecond windows.

Example:
    chunks = list(iter_time_slices(events, window_us=10_000))
    print(chunks[0].duration_us <= 10_000)

Output:
    True
"""

from __future__ import annotations

from collections.abc import Iterator

import numpy as np

from event_vision_utils.core.event_array import EventArray
from event_vision_utils.core.validation import normalize_integer_scalar

_INT64_MIN = int(np.iinfo(np.int64).min)
_INT64_MAX = int(np.iinfo(np.int64).max)


def slice_by_time(events: EventArray,
                  *,
                  start_us: int,
                  end_us: int,
                  include_end: bool = False) -> EventArray:
    """Copy events in one ordered microsecond interval.

    Args:
        events: Valid source events.
        start_us: Inclusive interval start.
        end_us: Exclusive interval end unless ``include_end`` is true.
        include_end: Whether events exactly at ``end_us`` are included.

    Returns:
        Owning event subset.

    Raises:
        ValueError: If the interval is reversed or boundaries are fractional.

    Example:
        selected = slice_by_time(events, start_us=10, end_us=30)
        print(selected.t_us.tolist())

    Output:
        [10, 20]
    """
    normalized_start = normalize_integer_scalar("start_us", start_us)
    normalized_end = normalize_integer_scalar("end_us", end_us)
    if normalized_end < normalized_start:
        raise ValueError("end_us must be greater than or equal to start_us")

    # Monotonic timestamps make binary-search boundaries deterministic even
    # when multiple events share a timestamp. Resolve out-of-int64 Python
    # boundaries explicitly because NumPy can compare them as unsigned values.
    left = _timestamp_boundary_index(events.t_us,
                                     normalized_start,
                                     side="left")
    right_side = "right" if include_end else "left"
    right = _timestamp_boundary_index(events.t_us,
                                      normalized_end,
                                      side=right_side)
    return events.subset(slice(left, right))


def iter_time_slices(events: EventArray,
                     *,
                     window_us: int,
                     start_us: int | None = None,
                     end_us: int | None = None,
                     include_empty: bool = False) -> Iterator[EventArray]:
    """Yield bounded half-open time windows without retaining history.

    Args:
        events: Valid source events.
        window_us: Positive window width in microseconds.
        start_us: Optional explicit first boundary.
        end_us: Optional explicit final boundary.
        include_empty: Whether empty windows are yielded.

    Yields:
        Owning event chunks in time order.

    Raises:
        ValueError: If window or boundary policy is invalid.

    Example:
        chunks = list(iter_time_slices(events, window_us=10))
        print([chunk.t_us.tolist() for chunk in chunks])

    Output:
        [[10], [20], [30]]
    """
    normalized_window = normalize_integer_scalar(
        "window_us",
        window_us,
        minimum=1,
    )
    if events.size == 0 and (start_us is None or end_us is None):
        return

    # Include the final timestamp in the default half-open range without
    # narrowing Python's unbounded boundary arithmetic to int64.
    default_start = events.t_start_us
    default_end = (
        None if events.t_end_us is None else events.t_end_us + 1
    )
    start = normalize_integer_scalar(
        "start_us",
        default_start if start_us is None else start_us,
    )
    end = normalize_integer_scalar(
        "end_us",
        default_end if end_us is None else end_us,
    )
    if end < start:
        raise ValueError("end_us must be greater than or equal to start_us")

    # Materialize only the current owning slice; the iterator retains no prior
    # windows or complete copied sequence.
    cursor = start
    while cursor < end:
        next_cursor = min(cursor + normalized_window, end)
        chunk = slice_by_time(
            events,
            start_us=cursor,
            end_us=next_cursor,
            include_end=False,
        )
        if include_empty or chunk.size:
            yield chunk
        cursor = next_cursor


def _timestamp_boundary_index(t_us: np.ndarray,
                              boundary_us: int,
                              *,
                              side: str) -> int:
    """Return one search index across Python's wider integer domain."""
    if boundary_us < _INT64_MIN:
        return 0
    if boundary_us > _INT64_MAX:
        return int(t_us.size)
    return int(np.searchsorted(t_us, boundary_us, side=side))
