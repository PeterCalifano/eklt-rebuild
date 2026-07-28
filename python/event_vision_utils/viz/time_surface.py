"""Render normalized latest-event time surfaces as NumPy arrays.

Example:
    surface = render_time_surface(events, decay_us=10_000)
    print(surface.dtype)

Output:
    float32
"""

from __future__ import annotations

import numpy as np

from event_vision_utils.core.event_array import EventArray
from event_vision_utils.core.validation import normalize_integer_scalar


def render_time_surface(events: EventArray,
                        *,
                        decay_us: int | None = None,
                        polarity: int | None = None) -> np.ndarray:
    """Render latest timestamps linearly or with exponential decay.

    Args:
        events: Valid event array.
        decay_us: Optional positive exponential decay constant.
        polarity: Optional exact ``-1`` or ``+1`` polarity selection.

    Returns:
        Owning float32 surface in ``[0, 1]``.

    Raises:
        ValueError: If decay or polarity policy is invalid.

    Example:
        surface = render_time_surface(events)
        print(surface.dtype, surface.shape)

    Output:
        float32 (2, 2)
    """
    normalized_decay: int | None = None
    if decay_us is not None:
        normalized_decay = normalize_integer_scalar(
            "decay_us",
            decay_us,
            minimum=1,
        )

    normalized_polarity: int | None = None
    if polarity is not None:
        normalized_polarity = normalize_integer_scalar(
            "polarity",
            polarity,
        )
        if normalized_polarity not in {-1, 1}:
            raise ValueError("polarity must be -1, +1, or None")

    surface = np.zeros((events.height, events.width), dtype=np.float32)
    if events.size == 0:
        return surface

    if normalized_polarity is None:
        selected = np.ones(events.size, dtype=bool)
    else:
        selected = events.p == normalized_polarity

    if not bool(np.any(selected)):
        return surface

    # Track occupancy separately so negative timestamps remain valid and never
    # collide with an arbitrary sentinel value.
    selected_y = events.y[selected]
    selected_x = events.x[selected]
    latest = np.full(
        (events.height, events.width),
        np.iinfo(np.int64).min,
        dtype=np.int64,
    )
    valid = np.zeros((events.height, events.width), dtype=bool)
    np.maximum.at(
        latest,
        (selected_y, selected_x),
        events.t_us[selected],
    )
    valid[selected_y, selected_x] = True

    # Exponential surfaces use the final batch timestamp as the causal
    # reference, while the default surface normalizes the selected span.
    if normalized_decay is not None:
        ages = (
            np.longdouble(int(events.t_us[-1]))
            - latest[valid].astype(np.longdouble)
        )
        surface[valid] = np.asarray(
            np.exp(-ages / np.longdouble(normalized_decay)),
            dtype=np.float32,
        )
        return surface

    start = int(events.t_us[selected][0])
    stop = int(events.t_us[selected][-1])
    if stop == start:
        surface[valid] = 1.0
        return surface

    duration = max(stop - start, 1)
    elapsed = latest[valid].astype(np.longdouble) - np.longdouble(start)
    surface[valid] = np.asarray(
        elapsed / np.longdouble(duration),
        dtype=np.float32,
    )
    return np.clip(surface, 0.0, 1.0).astype(np.float32)


def render_time_surface_uint8(events: EventArray,
                              *,
                              decay_us: int | None = None,
                              polarity: int | None = None) -> np.ndarray:
    """Render the normalized time surface as unsigned 8-bit intensities.

    Args:
        events: Valid event array.
        decay_us: Optional positive exponential decay constant.
        polarity: Optional exact ``-1`` or ``+1`` selection.

    Returns:
        Owning unsigned 8-bit surface.

    Example:
        surface = render_time_surface_uint8(events)
        print(surface.dtype, surface.shape)

    Output:
        uint8 (2, 2)
    """
    surface = render_time_surface(events, decay_us=decay_us, polarity=polarity)
    return np.rint(surface * 255.0).astype(np.uint8)
