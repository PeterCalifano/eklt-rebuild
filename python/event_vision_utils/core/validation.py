"""Validate and normalize generic event-array values.

The helpers reject lossy narrowing before conversion so large coordinates or
polarity values cannot wrap into an apparently valid native dtype.

Example:
    polarity = normalize_polarity([False, True])
    print(polarity.tolist())

Output:
    [-1, 1]
"""

from __future__ import annotations

import numpy as np

_MAX_SENSOR_DIMENSION = int(np.iinfo(np.int32).max)


def as_numeric_1d(name: str,
                  values: object,
                  *,
                  allow_bool: bool = False) -> np.ndarray:
    """Return a finite one-dimensional numeric array without narrowing it.

    Args:
        name: Reader-facing field name used in diagnostics.
        values: Candidate array-like values.
        allow_bool: Whether Boolean storage is accepted.

    Returns:
        NumPy view or array retaining the input numeric dtype.

    Raises:
        TypeError: If values are not supported numeric values.
        ValueError: If values are not one-dimensional or contain non-finite
            elements.

    Example:
        values = as_numeric_1d("value", [1, 2])
        print(values.tolist())

    Output:
        [1, 2]
    """
    array = np.asarray(values)
    if array.ndim != 1:
        raise ValueError(f"{name} must be a one-dimensional array")

    allowed_kinds = "biuf" if allow_bool else "iuf"
    if array.dtype.kind not in allowed_kinds:
        raise TypeError(f"{name} must contain numeric values")

    if not bool(np.all(np.isfinite(array))):
        raise ValueError(f"{name} must contain finite numeric values")
    return array


def normalize_integer_scalar(name: str,
                             value: object,
                             *,
                             minimum: int | None = None,
                             maximum: int | None = None) -> int:
    """Normalize one finite exact integer with optional inclusive bounds.

    Args:
        name: Reader-facing field name used in diagnostics.
        value: Candidate scalar value.
        minimum: Optional inclusive lower bound.
        maximum: Optional inclusive upper bound.

    Returns:
        Normalized Python integer.

    Raises:
        TypeError: If value is Boolean or non-numeric.
        ValueError: If value is not scalar, finite, integral, or in range.

    Example:
        value = normalize_integer_scalar("count", 3.0, minimum=1)
        print(value)

    Output:
        3
    """
    if isinstance(value, (int, np.integer)) and not isinstance(value, (bool, np.bool_)):
        # Keep Python and fixed-width integers in Python's unbounded domain so
        # exact boundary arithmetic never depends on NumPy dtype inference.
        normalized = int(value)
    else:
        array = np.asarray(value)
        if array.size != 1 or array.dtype.kind not in "iuf":
            raise TypeError(f"{name} must be one numeric scalar")

        scalar = array.reshape(-1)[0]
        if array.dtype.kind in "iu":
            normalized = int(scalar)
        else:
            extended = np.longdouble(scalar)
            if not bool(np.isfinite(extended)) or extended != np.rint(extended):
                raise ValueError(f"{name} must be one finite integer")
            normalized = int(extended)
    if minimum is not None and normalized < minimum:
        raise ValueError(f"{name} must be at least {minimum}")
    if maximum is not None and normalized > maximum:
        raise ValueError(f"{name} must be at most {maximum}")
    return normalized


def normalize_coordinate(name: str,
                         values: object,
                         upper_bound: int) -> np.ndarray:
    """Normalize exact pixel coordinates after validating their range.

    Args:
        name: Coordinate name, normally ``x`` or ``y``.
        values: Candidate coordinate array.
        upper_bound: Exclusive sensor-dimension bound.

    Returns:
        Owning signed 32-bit coordinate array.

    Raises:
        TypeError: If values or the bound are non-numeric.
        ValueError: If coordinates are fractional or out of bounds.

    Example:
        coordinates = normalize_coordinate("x", [0, 2], 3)
        print(coordinates.tolist())

    Output:
        [0, 2]
    """
    bound = normalize_integer_scalar(
        f"{name} upper bound",
        upper_bound,
        minimum=1,
        maximum=_MAX_SENSOR_DIMENSION,
    )
    array = as_numeric_1d(name, values, allow_bool=False)
    extended = array.astype(np.longdouble, copy=False)
    rounded = np.rint(extended)
    if not bool(np.all(extended == rounded)):
        raise ValueError(f"{name} must contain integer pixel coordinates")

    # Validate before narrowing so large exact values cannot wrap into range.
    if rounded.size and bool(np.any((rounded < 0) | (rounded >= bound))):
        raise ValueError(f"{name} coordinates must be in [0, {bound})")
    return rounded.astype(np.int32)


def normalize_polarity(values: object) -> np.ndarray:
    """Normalize Boolean, binary, or signed polarity to ``{-1, +1}``.

    Args:
        values: One-dimensional polarity array.

    Returns:
        Owning signed 8-bit polarity array.

    Raises:
        TypeError: If values are non-numeric.
        ValueError: If values are fractional or outside an accepted alphabet.

    Example:
        polarity = normalize_polarity([False, True])
        print(polarity.tolist())

    Output:
        [-1, 1]
    """
    array = as_numeric_1d("p", values, allow_bool=True)
    if array.dtype.kind == "b":
        return np.where(array, 1, -1).astype(np.int8)

    extended = array.astype(np.longdouble, copy=False)
    rounded = np.rint(extended)
    if not bool(np.all(extended == rounded)):
        raise ValueError("p must contain discrete polarity values")

    # Inspect the wide values before casting so overflow cannot manufacture a
    # valid zero/one or signed polarity.
    unique_values = set(np.unique(rounded).tolist())
    if unique_values.issubset({-1, 1}):
        return rounded.astype(np.int8)
    if unique_values.issubset({0, 1}):
        return np.where(rounded > 0, 1, -1).astype(np.int8)
    raise ValueError("p must use {-1, +1}, {0, 1}, or bool polarity values")


def validate_sensor_size(width: int, height: int) -> tuple[int, int]:
    """Validate positive sensor dimensions representable by coordinates.

    Args:
        width: Sensor width in pixels.
        height: Sensor height in pixels.

    Returns:
        Normalized width and height.

    Raises:
        TypeError: If either dimension is non-numeric.
        ValueError: If either dimension is fractional or outside range.

    Example:
        print(validate_sensor_size(640, 480))

    Output:
        (640, 480)
    """
    return (
        normalize_integer_scalar(
            "width",
            width,
            minimum=1,
            maximum=_MAX_SENSOR_DIMENSION,
        ),
        normalize_integer_scalar(
            "height",
            height,
            minimum=1,
            maximum=_MAX_SENSOR_DIMENSION,
        ),
    )


def validate_frame_id(frame_id: str) -> str:
    """Validate and normalize a non-empty event coordinate-frame identifier.

    Args:
        frame_id: Candidate frame identifier.

    Returns:
        Identifier without surrounding whitespace.

    Raises:
        TypeError: If frame_id is not text.
        ValueError: If frame_id is empty.

    Example:
        print(validate_frame_id(" camera "))

    Output:
        camera
    """
    if not isinstance(frame_id, str):
        raise TypeError("frame_id must be a string")
    normalized = frame_id.strip()
    if not normalized:
        raise ValueError("frame_id must not be empty")
    return normalized


def validate_equal_lengths(**arrays: np.ndarray) -> None:
    """Require all named arrays to have the same leading length.

    Args:
        **arrays: Named arrays participating in one event batch.

    Raises:
        ValueError: If the arrays do not share one length.

    Example:
        validate_equal_lengths(x=np.zeros(2), y=np.ones(2))
        print("valid")

    Output:
        valid
    """
    lengths = {name: len(array) for name, array in arrays.items()}
    if len(set(lengths.values())) > 1:
        raise ValueError(f"event arrays must have equal lengths: {lengths}")


def validate_monotonic_timestamps(t_us: np.ndarray) -> None:
    """Require monotonically nondecreasing integer timestamps.

    Args:
        t_us: One-dimensional signed 64-bit timestamps.

    Raises:
        ValueError: If any timestamp regresses.

    Example:
        validate_monotonic_timestamps(np.array([1, 1, 2]))
        print("valid")

    Output:
        valid
    """
    # Compare adjacent values directly; subtraction can overflow across the
    # complete signed 64-bit timestamp domain.
    if t_us.size > 1 and bool(np.any(t_us[1:] < t_us[:-1])):
        raise ValueError("t_us must be monotonically nondecreasing")
