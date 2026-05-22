from __future__ import annotations

import numpy as np
import pytest

from eklt_bridge.messages import convert_frame_to_mono8, normalize_mono_frame_to_u8, rgba_to_mono_luminance


def test_normalize_scalar_frame_to_uint8() -> None:
    frame = np.array([[0.0, 0.5, 1.0]], dtype=np.float64)

    converted = normalize_mono_frame_to_u8(frame, normalize_min=0.0, normalize_max=1.0)

    assert converted.dtype == np.uint8
    assert converted.tolist() == [[0, 128, 255]]


def test_convert_rgba_frame_to_luminance_then_uint8() -> None:
    frame = np.array(
        [
            [[1.0, 0.0, 0.0, 1.0], [0.0, 1.0, 0.0, 1.0]],
        ],
        dtype=np.float64,
    )

    luminance = rgba_to_mono_luminance(frame)
    converted = convert_frame_to_mono8(frame, normalize_min=0.0, normalize_max=1.0)

    np.testing.assert_allclose(luminance, np.array([[0.2126, 0.7152]]), atol=1e-6)
    assert converted.tolist() == [[54, 182]]


def test_convert_frame_rejects_invalid_shapes() -> None:
    with pytest.raises(ValueError):
        convert_frame_to_mono8(np.array([1.0, 2.0, 3.0]))
