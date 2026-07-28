"""Exercise the unified ``eklt_rebuild`` package and FIBAR adapter.

The tests validate the generated Python boundary rather than duplicating the
native Catch2 coverage.

Example:
    python -m pytest -q tests/test_eklt_rebuild.py

Output:
    4 passed
"""

from __future__ import annotations

import numpy as np
import pytest

import eklt_bridge
import eklt_rebuild
import event_vision_utils

_REQUIRES_NATIVE_WRAPPER = pytest.mark.skipif(
    not eklt_rebuild.HAS_WRAPPER,
    reason="generated EKLT wrapper is not available in a source-only install",
)


def _require_wrapper() -> None:
    """Require a successfully loaded generated extension for each API test."""
    assert eklt_rebuild.HAS_WRAPPER, str(eklt_rebuild.WRAPPER_IMPORT_ERROR)


def test_unified_distribution_exposes_separated_namespaces() -> None:
    """Keep native, bridge, and reusable utility namespaces independently usable."""
    assert hasattr(eklt_rebuild, "HAS_WRAPPER")
    assert hasattr(eklt_bridge, "EventStream")
    assert hasattr(event_vision_utils, "EventArray")


@_REQUIRES_NATIVE_WRAPPER
def test_generated_wrapper_is_available() -> None:
    """Expose the two documented adapter types at package scope."""
    _require_wrapper()

    assert hasattr(eklt_rebuild, "CFibarReconstructorAdapter")
    assert hasattr(eklt_rebuild, "CLocalFeaturePatchAdapter")


@_REQUIRES_NATIVE_WRAPPER
def test_noncontiguous_event_batch_reconstructs_image_and_patch() -> None:
    """Copy non-contiguous NumPy views through Eigen-backed wrapper arrays."""
    _require_wrapper()
    reconstructor_ = eklt_rebuild.CFibarReconstructorAdapter(4, 3, 1000, 0.5, False)

    # Select strided views so the generated boundary must normalize array
    # storage before the native adapter validates exact integer values.
    x_ = np.array([1.0, -1.0, 2.0, -1.0], dtype=np.float64)[::2]
    y_ = np.array([1.0, -1.0, 1.0, -1.0], dtype=np.float64)[::2]
    polarity_ = np.array([1.0, 0.0, -1.0, 0.0], dtype=np.float64)[::2]
    timestamps_us_ = np.array(
        [10.0, 0.0, 40.0, 0.0], dtype=np.float64
    )[::2]
    assert not x_.flags.c_contiguous

    reconstructor_.acceptEvents(x_, y_, polarity_, timestamps_us_)

    # Validate owning array geometry and finite reconstructed values at the
    # generated-language surface.
    image_ = np.asarray(reconstructor_.requestImage(40))
    patch_ = reconstructor_.requestPatch(1, 1, 1, 40)
    patch_intensity_ = np.asarray(patch_.intensity())

    assert reconstructor_.latestTimestampUs() == 40
    assert image_.shape == (3, 4)
    assert np.isfinite(image_).all()
    assert patch_.width() == 3
    assert patch_.height() == 3
    assert patch_intensity_.shape == (3, 3)
    assert np.isfinite(patch_intensity_).all()


@_REQUIRES_NATIVE_WRAPPER
def test_invalid_integer_conversion_preserves_adapter_state() -> None:
    """Reject fractional coordinates before accepting any part of a batch."""
    _require_wrapper()
    reconstructor_ = eklt_rebuild.CFibarReconstructorAdapter(4, 3, 1000, 0.5, False)

    with pytest.raises(ValueError, match="in-range integers"):
        reconstructor_.acceptEvents(np.array([1.5], dtype=np.float64),
                                    np.array([1.0], dtype=np.float64),
                                    np.array([1.0], dtype=np.float64),
                                    np.array([10.0], dtype=np.float64))

    assert reconstructor_.latestTimestampUs() == -1


if __name__ == "__main__":
    # Reuse the same namespace and native API regressions for installed and
    # relocated CI execution.
    test_unified_distribution_exposes_separated_namespaces()
    test_generated_wrapper_is_available()
    test_noncontiguous_event_batch_reconstructs_image_and_patch()
    test_invalid_integer_conversion_preserves_adapter_state()
