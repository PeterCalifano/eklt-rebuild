"""Render positive, negative, and mixed event pixels as an RGB array.

Example:
    image = render_polarity_rgb(events)
    print(image.dtype, image.shape)

Output:
    uint8 (480, 640, 3)
"""

from __future__ import annotations

import numpy as np

from event_vision_utils.core.event_array import EventArray
from event_vision_utils.core.validation import (
    normalize_coordinate,
    normalize_integer_scalar,
)
from event_vision_utils.viz.accumulation import split_polarity_counts


def render_polarity_rgb(events: EventArray,
                        *,
                        background: int = 255,
                        positive_color: tuple[int, int, int] = (220, 40, 40),
                        negative_color: tuple[int, int, int] = (40, 90, 220),
                        mixed_color: tuple[int, int, int] = (80, 80, 80)) -> np.ndarray:
    """Render event polarity without retaining intermediate event history.

    Args:
        events: Valid event array.
        background: Grayscale background intensity in ``[0, 255]``.
        positive_color: RGB color for positive-only pixels.
        negative_color: RGB color for negative-only pixels.
        mixed_color: RGB color for pixels containing both polarities.

    Returns:
        Owning unsigned 8-bit RGB image.

    Raises:
        ValueError: If background or a color is outside unsigned 8-bit range.

    Example:
        image = render_polarity_rgb(events, background=0)
        print(image.dtype, image.shape)

    Output:
        uint8 (2, 2, 3)
    """
    background_value = normalize_integer_scalar(
        "background",
        background,
        minimum=0,
        maximum=255,
    )
    positive_rgb = _normalize_rgb_color(
        "positive_color",
        positive_color,
    )
    negative_rgb = _normalize_rgb_color(
        "negative_color",
        negative_color,
    )
    mixed_rgb = _normalize_rgb_color("mixed_color", mixed_color)

    image = np.full(
        (events.height, events.width, 3),
        background_value,
        dtype=np.uint8,
    )
    positive, negative = split_polarity_counts(events)

    # Resolve mutually exclusive masks before coloring so mixed-polarity pixels
    # receive their explicit color independent of assignment order.
    pos_only = (positive > 0) & (negative == 0)
    neg_only = (negative > 0) & (positive == 0)
    mixed = (positive > 0) & (negative > 0)

    image[pos_only] = positive_rgb
    image[neg_only] = negative_rgb
    image[mixed] = mixed_rgb
    return image


def _normalize_rgb_color(name: str,
                         color: tuple[int, int, int]) -> np.ndarray:
    """Normalize one exact three-channel unsigned 8-bit color."""
    channels = normalize_coordinate(name, color, 256)
    if channels.size != 3:
        raise ValueError(f"{name} must contain exactly three channels")
    return channels.astype(np.uint8)
