"""Test the optional generated FIBAR package through the public adapter."""

import numpy as np
import pytest

from event_vision_utils import EventArray
from event_vision_utils.recon import CFibarReconstructor, SFibarConfig, fibar_native_available


pytestmark = pytest.mark.skipif(
    not fibar_native_available(),
    reason="native FIBAR wrapper is not built",
)


def _make_reconstructor() -> CFibarReconstructor:
    """Construct the shared deterministic fixture configuration."""
    config = SFibarConfig(
        width=6,
        height=5,
        cutoff_time_us=10000,
        fill_ratio=0.5,
        use_spatial_filter=False,
    )
    return CFibarReconstructor(config)


def test_native_wrapper_accepts_arrays_and_returns_float_image_and_patch() -> None:
    """Return owning image and structured patch data after one event batch."""
    reconstructor = _make_reconstructor()
    x = np.array([2, 3, 2, 3], dtype=np.uint16)
    y = np.array([2, 2, 3, 3], dtype=np.uint16)
    p = np.array([1, -1, 1, -1], dtype=np.int8)
    t_us = np.array([10, 20, 30, 40], dtype=np.int64)

    reconstructor.accept_events(x, y, p, t_us)
    image = reconstructor.request_image(40)
    patch = reconstructor.request_patch(2, 2, 1, 40)

    assert image.shape == (5, 6)
    assert image.dtype == np.float32
    assert np.isfinite(image).all()
    assert patch.intensity.shape == (3, 3)
    assert patch.gradient_x.shape == (3, 3)
    assert patch.gradient_y.shape == (3, 3)
    assert patch.valid_mask.shape == (3, 3)
    assert patch.width == 3
    assert patch.height == 3
    assert patch.valid_fraction == pytest.approx(1.0)


def test_native_wrapper_copies_noncontiguous_arrays_and_resets() -> None:
    """Copy strided inputs and permit reuse from a fresh time origin."""
    reconstructor = _make_reconstructor()
    xy = np.array(
        [
            [2, 2],
            [3, 2],
            [2, 3],
            [3, 3],
        ],
        dtype=np.uint16,
    )
    p_and_t = np.array(
        [
            [1, 10],
            [-1, 20],
            [1, 30],
            [-1, 40],
        ],
        dtype=np.int64,
    )

    reconstructor.accept_events(
        xy[:, 0],
        xy[:, 1],
        p_and_t[:, 0].astype(np.int8),
        p_and_t[:, 1],
    )

    image = reconstructor.request_image(40)
    assert image.shape == (5, 6)
    assert np.isfinite(image).all()
    assert reconstructor.latest_timestamp_us == 40

    reconstructor.reset()
    assert reconstructor.latest_timestamp_us == -1
    reconstructor.accept_events(
        xy[:2, 0],
        xy[:2, 1],
        p_and_t[:2, 0].astype(np.int8),
        np.array([1, 2], dtype=np.int64),
    )
    assert reconstructor.latest_timestamp_us == 2


def test_native_wrapper_reports_size_mismatch() -> None:
    """Reject incomplete or lossy batches before crossing the native boundary."""
    reconstructor = _make_reconstructor()

    with pytest.raises(ValueError, match="equal lengths"):
        reconstructor.accept_events(
            np.array([1, 2], dtype=np.uint16),
            np.array([1], dtype=np.uint16),
            np.array([1, -1], dtype=np.int8),
            np.array([10, 20], dtype=np.int64),
        )

    with pytest.raises(ValueError, match="radius"):
        reconstructor.request_patch(1, 1, 2**30, 0)

    lossy_timestamp = EventArray(
        x=[1],
        y=[1],
        p=[1],
        t_us=[2**53 + 1],
        width=6,
        height=5,
    )
    with pytest.raises(ValueError, match="represented exactly"):
        reconstructor.accept_event_array(lossy_timestamp)

    assert reconstructor.latest_timestamp_us == -1
