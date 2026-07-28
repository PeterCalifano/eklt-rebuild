"""Slice event arrays by bounded event counts.

Example:
    chunks = list(iter_count_slices(events, count=1000))
    print(max(chunk.size for chunk in chunks))

Output:
    1000
"""

from __future__ import annotations

from collections.abc import Iterator

from event_vision_utils.core.event_array import EventArray
from event_vision_utils.core.validation import normalize_integer_scalar


def slice_by_count(events: EventArray, *, start: int, count: int) -> EventArray:
    """Copy at most ``count`` events from one nonnegative offset.

    Args:
        events: Valid source events.
        start: Nonnegative event offset.
        count: Positive maximum number of events.

    Returns:
        Owning event subset, clipped at the source end.

    Example:
        selected = slice_by_count(events, start=1, count=2)
        print(selected.t_us.tolist())

    Output:
        [20, 30]
    """
    normalized_start = normalize_integer_scalar("start", start, minimum=0)
    normalized_count = normalize_integer_scalar("count", count, minimum=1)
    return events.subset(
        slice(
            normalized_start,
            min(normalized_start + normalized_count, events.size),
        )
    )


def iter_count_slices(events: EventArray,
                      *,
                      count: int,
                      overlap: int = 0) -> Iterator[EventArray]:
    """Yield bounded count windows without retaining prior chunks.

    Args:
        events: Valid source events.
        count: Positive maximum events per window.
        overlap: Events repeated from one window into the next.

    Yields:
        Non-empty owning event chunks in source order.

    Raises:
        ValueError: If count or overlap violates the window contract.

    Example:
        chunks = list(iter_count_slices(events, count=2))
        print([chunk.size for chunk in chunks])

    Output:
        [2, 1]
    """
    normalized_count = normalize_integer_scalar("count", count, minimum=1)
    normalized_overlap = normalize_integer_scalar(
        "overlap",
        overlap,
        minimum=0,
    )
    if normalized_overlap >= normalized_count:
        raise ValueError("overlap must be in [0, count)")

    # Advance by the non-overlapping portion so every yielded owning chunk is
    # bounded while the requested overlap remains exact.
    step = normalized_count - normalized_overlap
    for start in range(0, events.size, step):
        chunk = slice_by_count(
            events,
            start=start,
            count=normalized_count,
        )
        if chunk.size:
            yield chunk
        if start + normalized_count >= events.size:
            break
