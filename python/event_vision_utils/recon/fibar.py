"""Adapt the generated ``eklt_rebuild`` FIBAR API to generic event arrays.

The adapter validates all Python values before converting them to the
Eigen-backed float64 arrays required by gtwrap. Reconstruction remains entirely
native.

Example:
    reconstructor = CFibarReconstructor(SFibarConfig(width=4, height=3))
    reconstructor.accept_events([1], [1], [1], [10])
    print(reconstructor.request_image(10).shape)

Output:
    (3, 4)
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

import numpy as np

from event_vision_utils.core.event_array import EventArray
from event_vision_utils.core.validation import (
    normalize_integer_scalar,
    validate_sensor_size,
)

# Keep native discovery optional and package-based; this adapter never scans a
# build tree or loads an unrelated private extension.
try:
    import eklt_rebuild as _eklt_rebuild
except ImportError as exc:
    _NATIVE_IMPORT_ERROR: ImportError | None = exc
    _NativeCFibarReconstructorAdapter: Any | None = None
else:
    _NativeCFibarReconstructorAdapter = getattr(
        _eklt_rebuild,
        "CFibarReconstructorAdapter",
        None,
    )
    _NATIVE_IMPORT_ERROR = getattr(
        _eklt_rebuild,
        "WRAPPER_IMPORT_ERROR",
        None,
    )
    if _NativeCFibarReconstructorAdapter is None:
        _NATIVE_IMPORT_ERROR = _NATIVE_IMPORT_ERROR or ImportError(
            "eklt_rebuild did not expose CFibarReconstructorAdapter"
        )

_INT64_MIN = int(np.iinfo(np.int64).min)
_INT64_MAX = int(np.iinfo(np.int64).max)
_MAX_NATIVE_PATCH_RADIUS = (int(np.iinfo(np.int32).max) - 1) // 2


@dataclass(frozen=True, slots=True)
class SFibarConfig:
    """Configuration for the native FIBAR reconstruction adapter.

    Attributes:
        width: Sensor width in pixels.
        height: Sensor height in pixels.
        cutoff_time_us: Positive filter cutoff in microseconds.
        fill_ratio: Finite reconstruction fill ratio in ``[0, 1]``.
        use_spatial_filter: Whether to select the native spatial filter.

    Example:
        config = SFibarConfig(width=640, height=480)
        print(config.width, config.height, config.cutoff_time_us)

    Output:
        640 480 10000
    """

    width: int
    height: int
    cutoff_time_us: int = 10000
    fill_ratio: float = 0.5
    use_spatial_filter: bool = True

    def __post_init__(self) -> None:
        """Validate immutable configuration before native construction."""
        width, height = validate_sensor_size(self.width, self.height)
        cutoff = normalize_integer_scalar(
            "cutoff_time_us",
            self.cutoff_time_us,
            minimum=1,
            maximum=np.iinfo(np.uint32).max,
        )
        fill_ratio_value = np.asarray(self.fill_ratio)
        if (
            fill_ratio_value.size != 1
            or fill_ratio_value.dtype.kind not in "iuf"
        ):
            raise TypeError("fill_ratio must be one numeric scalar")
        fill_ratio = float(fill_ratio_value.reshape(-1)[0])
        if not np.isfinite(fill_ratio) or not 0.0 <= fill_ratio <= 1.0:
            raise ValueError("fill_ratio must be finite and in [0, 1]")
        if not isinstance(self.use_spatial_filter, bool):
            raise TypeError("use_spatial_filter must be Boolean")

        object.__setattr__(self, "width", width)
        object.__setattr__(self, "height", height)
        object.__setattr__(self, "cutoff_time_us", cutoff)
        object.__setattr__(self, "fill_ratio", fill_ratio)


@dataclass(frozen=True, slots=True)
class SLocalFeaturePatch:
    """Owning NumPy representation of one reconstructed native patch.

    Attributes:
        intensity: Reconstructed float32 intensity patch.
        gradient_x: Float32 horizontal image gradients.
        gradient_y: Float32 vertical image gradients.
        valid_mask: Unsigned 8-bit binary validity mask.
        width: Patch width in pixels.
        height: Patch height in pixels.
        center_x: Requested sensor x coordinate.
        center_y: Requested sensor y coordinate.
        t_us: Requested causal timestamp in microseconds.
        valid_fraction: Fraction of valid patch pixels in ``[0, 1]``.
        gradient_energy: Nonnegative mean squared gradient magnitude.

    Example:
        patch = reconstructor.request_patch(2, 2, 1, 10)
        print(patch.width, patch.height, patch.intensity.shape)

    Output:
        3 3 (3, 3)
    """

    intensity: np.ndarray
    gradient_x: np.ndarray
    gradient_y: np.ndarray
    valid_mask: np.ndarray
    width: int
    height: int
    center_x: int
    center_y: int
    t_us: int
    valid_fraction: float
    gradient_energy: float


def fibar_native_available() -> bool:
    """Return whether the accepted generated EKLT adapter is importable.

    Returns:
        True only when ``eklt_rebuild`` exposes its generated native adapter.

    Example:
        print(isinstance(fibar_native_available(), bool))

    Output:
        True
    """
    return (
        _NATIVE_IMPORT_ERROR is None
        and _NativeCFibarReconstructorAdapter is not None
    )


class CFibarReconstructor:
    """Snake-case Python facade over the generated native FIBAR adapter.

    Example:
        reconstructor = CFibarReconstructor(
            SFibarConfig(width=4, height=3)
        )
        print(reconstructor.config.width, reconstructor.config.height)

    Output:
        4 3
    """

    def __init__(self, config: SFibarConfig) -> None:
        """Construct a native reconstructor from validated configuration.

        Args:
            config: FIBAR geometry and filter policy.

        Raises:
            ImportError: If the generated ``eklt_rebuild`` package is absent.
        """
        if not isinstance(config, SFibarConfig):
            raise TypeError("config must be an SFibarConfig")
        if _NativeCFibarReconstructorAdapter is None:
            raise ImportError(
                "The eklt_rebuild wrapper is unavailable. Build or install "
                "the generated Python package with ./build_lib.sh --python."
            ) from _NATIVE_IMPORT_ERROR

        # Construct only after every Python-side option has been normalized so
        # native state cannot be partially initialized from invalid values.
        self._config = config
        self._native = _NativeCFibarReconstructorAdapter(
            config.width,
            config.height,
            config.cutoff_time_us,
            config.fill_ratio,
            config.use_spatial_filter,
        )

    @property
    def config(self) -> SFibarConfig:
        """Return the immutable reconstruction configuration.

        Example:
            print(reconstructor.config.cutoff_time_us)

        Output:
            10000
        """
        return self._config

    def accept_event_array(self, events: EventArray) -> None:
        """Accept one complete generic event batch atomically.

        Args:
            events: Valid event array matching configured geometry.

        Raises:
            ValueError: If event geometry differs or timestamps cannot cross
                the exact float64 gtwrap boundary.

        Example:
            reconstructor.accept_event_array(events)
            print(reconstructor.latest_timestamp_us)

        Output:
            10
        """
        if not isinstance(events, EventArray):
            raise TypeError("events must be an EventArray")
        if (
            events.width,
            events.height,
        ) != (
            self._config.width,
            self._config.height,
        ):
            raise ValueError("event geometry does not match FIBAR configuration")

        # Convert the complete validated batch before one atomic native call;
        # any lossy gtwrap value rejects the batch without advancing FIBAR.
        self._native.acceptEvents(
            _as_exact_float64("x", events.x),
            _as_exact_float64("y", events.y),
            _as_exact_float64("p", events.p),
            _as_exact_float64("t_us", events.t_us),
        )

    def accept_events(self,
                      x: object,
                      y: object,
                      p: object,
                      t_us: object) -> None:
        """Validate parallel arrays and accept one complete native batch.

        Args:
            x: Pixel x coordinates.
            y: Pixel y coordinates.
            p: Boolean, binary, or signed polarity values.
            t_us: Monotonic integer-microsecond timestamps.

        Raises:
            ValueError: If the parallel arrays violate the event contract.

        Example:
            reconstructor.accept_events([1], [1], [1], [10])
            print(reconstructor.latest_timestamp_us)

        Output:
            10
        """
        events = EventArray(
            x=np.asarray(x),
            y=np.asarray(y),
            p=np.asarray(p),
            t_us=np.asarray(t_us),
            width=self._config.width,
            height=self._config.height,
        )
        self.accept_event_array(events)

    def request_image(self, t_us: int) -> np.ndarray:
        """Request one owning float32 reconstructed image.

        Args:
            t_us: Requested causal timestamp in microseconds.

        Returns:
            Finite image with configured ``(height, width)`` shape.

        Raises:
            RuntimeError: If native output violates the adapter contract.

        Example:
            image = reconstructor.request_image(10)
            print(image.dtype, image.shape)

        Output:
            float32 (3, 4)
        """
        timestamp_us = normalize_integer_scalar(
            "t_us",
            t_us,
            minimum=_INT64_MIN,
            maximum=_INT64_MAX,
        )
        image = np.array(
            self._native.requestImage(timestamp_us),
            dtype=np.float32,
            copy=True,
        )
        if image.shape != (self._config.height, self._config.width):
            raise RuntimeError(
                "native FIBAR image geometry does not match its configuration"
            )
        if not bool(np.all(np.isfinite(image))):
            raise RuntimeError("native FIBAR image contains non-finite values")
        return image

    def request_patch(self,
                      center_x: int,
                      center_y: int,
                      radius: int,
                      t_us: int) -> SLocalFeaturePatch:
        """Request one owning local feature patch.

        Args:
            center_x: Patch center x coordinate.
            center_y: Patch center y coordinate.
            radius: Nonnegative patch radius.
            t_us: Requested causal timestamp in microseconds.

        Returns:
            Owning array and scalar patch data.

        Raises:
            ValueError: If request coordinates, radius, or timestamp are invalid.
            RuntimeError: If native output violates the adapter contract.

        Example:
            patch = reconstructor.request_patch(2, 1, 1, 10)
            print(patch.width, patch.height)

        Output:
            3 3
        """
        normalized_x = normalize_integer_scalar(
            "center_x",
            center_x,
            minimum=0,
            maximum=self._config.width - 1,
        )
        normalized_y = normalize_integer_scalar(
            "center_y",
            center_y,
            minimum=0,
            maximum=self._config.height - 1,
        )
        normalized_radius = normalize_integer_scalar(
            "radius",
            radius,
            minimum=0,
            maximum=_MAX_NATIVE_PATCH_RADIUS,
        )
        timestamp_us = normalize_integer_scalar(
            "t_us",
            t_us,
            minimum=_INT64_MIN,
            maximum=_INT64_MAX,
        )
        patch = self._native.requestPatch(
            normalized_x,
            normalized_y,
            normalized_radius,
            timestamp_us,
        )

        # Enforce the documented owning patch contract at the generated
        # boundary so malformed native results cannot enter generic utilities.
        intensity = np.array(patch.intensity(), dtype=np.float32, copy=True)
        gradient_x = np.array(patch.gradientX(), dtype=np.float32, copy=True)
        gradient_y = np.array(patch.gradientY(), dtype=np.float32, copy=True)
        valid_mask_source = np.asarray(patch.validMask())
        width = int(patch.width())
        height = int(patch.height())
        center_x = int(patch.centerX())
        center_y = int(patch.centerY())
        patch_timestamp_us = int(patch.timestampUs())
        valid_fraction = float(patch.validFraction())
        gradient_energy = float(patch.gradientEnergy())

        expected_shape = (height, width)
        patch_arrays = (
            intensity,
            gradient_x,
            gradient_y,
            valid_mask_source,
        )
        if width <= 0 or height <= 0:
            raise RuntimeError("native FIBAR patch dimensions must be positive")
        if (
            center_x,
            center_y,
            patch_timestamp_us,
        ) != (
            normalized_x,
            normalized_y,
            timestamp_us,
        ):
            raise RuntimeError(
                "native FIBAR patch metadata does not match its request"
            )
        if any(array.shape != expected_shape for array in patch_arrays):
            raise RuntimeError(
                "native FIBAR patch arrays do not match patch geometry"
            )
        if not bool(
            np.all(np.isfinite(intensity))
            and np.all(np.isfinite(gradient_x))
            and np.all(np.isfinite(gradient_y))
        ):
            raise RuntimeError("native FIBAR patch contains non-finite values")
        if (
            valid_mask_source.dtype.kind not in "biuf"
            or not bool(np.all(np.isfinite(valid_mask_source)))
            or not bool(np.all((valid_mask_source == 0) |
                               (valid_mask_source == 1)))
        ):
            raise RuntimeError("native FIBAR patch mask must be binary")
        if (
            not np.isfinite(valid_fraction)
            or not 0.0 <= valid_fraction <= 1.0
            or not np.isfinite(gradient_energy)
            or gradient_energy < 0.0
        ):
            raise RuntimeError("native FIBAR patch metrics are invalid")
        return SLocalFeaturePatch(
            intensity=intensity,
            gradient_x=gradient_x,
            gradient_y=gradient_y,
            valid_mask=np.array(valid_mask_source, dtype=np.uint8, copy=True),
            width=width,
            height=height,
            center_x=center_x,
            center_y=center_y,
            t_us=patch_timestamp_us,
            valid_fraction=valid_fraction,
            gradient_energy=gradient_energy,
        )

    @property
    def latest_timestamp_us(self) -> int:
        """Return the latest accepted timestamp, or ``-1`` before events.

        Example:
            print(reconstructor.latest_timestamp_us)

        Output:
            -1
        """
        return int(self._native.latestTimestampUs())

    def reset(self) -> None:
        """Reset native filter and timestamp state for independent reuse.

        Example:
            reconstructor.reset()
            print(reconstructor.latest_timestamp_us)

        Output:
            -1
        """
        self._native.reset()


def _as_exact_float64(name: str, values: np.ndarray) -> np.ndarray:
    """Copy exact integer values into the Eigen float64 exchange dtype."""
    converted = np.asarray(values, dtype=np.float64)
    # Compare Python float and integer objects so exactness does not depend on
    # whether this platform implements long double wider than float64.
    if not np.array_equal(converted.astype(object),
                          values.astype(object)):
        raise ValueError(
            f"{name} values cannot be represented exactly by gtwrap float64"
        )
    return np.ascontiguousarray(converted)
