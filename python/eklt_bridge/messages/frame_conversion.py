"""Frame conversion helpers for stage 2A."""

from __future__ import annotations

import numpy as np


def rgba_to_mono_luminance(frame: np.ndarray) -> np.ndarray:
    """Convert an RGB or RGBA frame to a floating-point luminance image."""

    frame_array = np.asarray(frame, dtype=np.float64)
    if frame_array.ndim != 3 or frame_array.shape[-1] not in (3, 4):
        raise ValueError(
            "Expected an RGB or RGBA frame with shape (H, W, 3|4).")

    rgb = frame_array[..., :3]
    return (
        0.2126 * rgb[..., 0]
        + 0.7152 * rgb[..., 1]
        + 0.0722 * rgb[..., 2]
    )


def normalize_mono_frame_to_u8(frame: np.ndarray,
                               *,
                               normalize_min: float | None = None,
                               normalize_max: float | None = None) -> np.ndarray:
    """Normalize a scalar image into uint8 grayscale."""

    frame_array = np.asarray(frame, dtype=np.float64)
    if frame_array.ndim != 2:
        raise ValueError("Expected a 2-D scalar frame.")

    min_value = float(np.min(frame_array)
                      ) if normalize_min is None else float(normalize_min)
    max_value = float(np.max(frame_array)
                      ) if normalize_max is None else float(normalize_max)
    if max_value <= min_value:
        raise ValueError("normalize_max must be greater than normalize_min.")

    normalized = np.clip((frame_array - min_value) /
                         (max_value - min_value), 0.0, 1.0)
    return np.rint(normalized * 255.0).astype(np.uint8)


def convert_frame_to_mono8(frame: np.ndarray,
                           *,
                           normalize_min: float | None = None,
                           normalize_max: float | None = None) -> np.ndarray:
    """Convert a scalar, RGB, or RGBA frame to uint8 grayscale."""

    frame_array = np.asarray(frame)
    if frame_array.ndim == 2:
        return normalize_mono_frame_to_u8(
            frame_array,
            normalize_min=normalize_min,
            normalize_max=normalize_max,
        )
    if frame_array.ndim == 3:
        luminance = rgba_to_mono_luminance(frame_array)
        return normalize_mono_frame_to_u8(
            luminance,
            normalize_min=normalize_min,
            normalize_max=normalize_max,
        )

    raise ValueError(
        "Expected either a 2-D scalar frame or a 3-D RGB/RGBA frame.")
