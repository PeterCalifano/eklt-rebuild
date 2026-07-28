"""Test the clear optional-dependency failure path without native bindings."""

import numpy as np
import pytest

import event_vision_utils.recon.fibar as fibar_module
from event_vision_utils.recon import (
    CFibarReconstructor,
    SFibarConfig,
    fibar_native_available,
)


class _InvalidMaskPatch:
    """Return one native-shaped patch whose mask would wrap to zero."""

    def intensity(self) -> np.ndarray:
        """Return one finite intensity value."""
        return np.ones((1, 1), dtype=np.float64)

    def gradientX(self) -> np.ndarray:
        """Return one finite horizontal gradient."""
        return np.zeros((1, 1), dtype=np.float64)

    def gradientY(self) -> np.ndarray:
        """Return one finite vertical gradient."""
        return np.zeros((1, 1), dtype=np.float64)

    def validMask(self) -> np.ndarray:
        """Return an invalid mask value that uint8 narrowing would hide."""
        return np.array([[256]], dtype=np.uint16)

    def width(self) -> int:
        """Return the patch width."""
        return 1

    def height(self) -> int:
        """Return the patch height."""
        return 1

    def centerX(self) -> int:
        """Return the requested center x coordinate."""
        return 0

    def centerY(self) -> int:
        """Return the requested center y coordinate."""
        return 0

    def timestampUs(self) -> int:
        """Return the requested timestamp."""
        return 0

    def validFraction(self) -> float:
        """Return a valid coverage metric."""
        return 1.0

    def gradientEnergy(self) -> float:
        """Return a valid gradient metric."""
        return 0.0


class _InvalidMaskNative:
    """Provide the malformed patch through the generated-adapter protocol."""

    def __init__(self, *_args: object) -> None:
        """Accept the generated adapter's construction arguments."""

    def requestPatch(self,
                     _center_x: int,
                     _center_y: int,
                     _radius: int,
                     _t_us: int) -> _InvalidMaskPatch:
        """Return the deterministic malformed patch."""
        return _InvalidMaskPatch()


def test_fibar_python_wrapper_reports_missing_native_module() -> None:
    """Import generic utilities while reporting a missing native constructor."""
    if fibar_native_available():
        pytest.skip("native FIBAR wrapper is available in this environment")

    with pytest.raises(ImportError, match="unavailable"):
        CFibarReconstructor(SFibarConfig(width=4, height=4))


def test_fibar_patch_mask_rejects_uint8_narrowing(monkeypatch: pytest.MonkeyPatch) -> None:
    """Reject native mask values that would wrap into the binary alphabet."""
    monkeypatch.setattr(fibar_module,
                        "_NativeCFibarReconstructorAdapter",
                        _InvalidMaskNative)
    reconstructor = CFibarReconstructor(SFibarConfig(width=1, height=1))

    with pytest.raises(RuntimeError, match="mask must be binary"):
        reconstructor.request_patch(0, 0, 0, 0)
