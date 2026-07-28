"""Compute bounded image-plane event accumulations.

Example:
    counts = accumulate_event_counts(events, signed=True)
    print(counts.shape)

Output:
    (480, 640)
"""

from __future__ import annotations

import numpy as np

from event_vision_utils.core.event_array import EventArray


def accumulate_event_counts(events: EventArray, *, signed: bool = False) -> np.ndarray:
    """Accumulate unsigned counts or signed polarity at every pixel.

    Args:
        events: Valid event array.
        signed: Whether each event contributes its signed polarity.

    Returns:
        Signed 64-bit image with shape ``(height, width)``.

    Example:
        counts = accumulate_event_counts(events, signed=True)
        print(counts.tolist())

    Output:
        [[0, -1], [1, 0]]
    """
    dtype = np.int64
    counts = np.zeros((events.height, events.width), dtype=dtype)
    if events.size == 0:
        return counts

    # Indexed accumulation preserves repeated events at one pixel instead of
    # letting later writes overwrite earlier contributions.
    values = events.p.astype(dtype) if signed else np.ones(events.size, dtype=dtype)
    np.add.at(counts, (events.y, events.x), values)
    return counts


def split_polarity_counts(events: EventArray) -> tuple[np.ndarray, np.ndarray]:
    """Accumulate positive and negative event counts separately.

    Args:
        events: Valid event array.

    Returns:
        Positive and negative signed 64-bit count images.

    Example:
        positive, negative = split_polarity_counts(events)
        print(positive.sum(), negative.sum())

    Output:
        1 1
    """
    positive = np.zeros((events.height, events.width), dtype=np.int64)
    negative = np.zeros((events.height, events.width), dtype=np.int64)
    if events.size == 0:
        return positive, negative

    # Accumulate the two alphabets independently so callers can distinguish a
    # mixed pixel from an empty or polarity-exclusive pixel.
    pos_mask = events.p > 0
    neg_mask = events.p < 0
    np.add.at(positive, (events.y[pos_mask], events.x[pos_mask]), 1)
    np.add.at(negative, (events.y[neg_mask], events.x[neg_mask]), 1)
    return positive, negative
