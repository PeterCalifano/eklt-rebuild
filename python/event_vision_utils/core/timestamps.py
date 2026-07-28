"""Normalize event timestamps to signed integer microseconds.

Example:
    timestamps_us = normalize_timestamps_to_us([0.0, 0.001], unit="s")
    print(timestamps_us.tolist())

Output:
    [0, 1000]
"""

from __future__ import annotations

import numpy as np

from event_vision_utils.core.validation import as_numeric_1d

_UNIT_TO_US = {
    "us": np.longdouble(1),
    "microsecond": np.longdouble(1),
    "microseconds": np.longdouble(1),
    "ms": np.longdouble(1_000),
    "millisecond": np.longdouble(1_000),
    "milliseconds": np.longdouble(1_000),
    "s": np.longdouble(1_000_000),
    "sec": np.longdouble(1_000_000),
    "second": np.longdouble(1_000_000),
    "seconds": np.longdouble(1_000_000),
    "ns": np.longdouble("0.001"),
    "nanosecond": np.longdouble("0.001"),
    "nanoseconds": np.longdouble("0.001"),
}
_INT64_LOWER = -(np.longdouble(2) ** 63)
_INT64_UPPER_EXCLUSIVE = np.longdouble(2) ** 63


def normalize_timestamps_to_us(values: object,
                               *,
                               unit: str = "us") -> np.ndarray:
    """Convert finite timestamps to nearest signed integer microseconds.

    Half-microsecond ties use NumPy's round-to-even rule. Integer-microsecond
    input is handled without a floating-point round trip.

    Args:
        values: One-dimensional numeric timestamp array.
        unit: Input unit name.

    Returns:
        Owning signed 64-bit microsecond array.

    Raises:
        TypeError: If values are non-numeric or unit is not text.
        ValueError: If values are not finite or unit is unsupported.
        OverflowError: If converted timestamps exceed signed 64-bit range.

    Example:
        timestamps_us = normalize_timestamps_to_us(
            [0.0, 0.001], unit="s"
        )
        print(timestamps_us.tolist())

    Output:
        [0, 1000]
    """
    array = as_numeric_1d("t_us", values, allow_bool=False)
    if not isinstance(unit, str):
        raise TypeError("timestamp unit must be a string")

    unit_key = unit.lower()
    if unit_key not in _UNIT_TO_US:
        allowed = ", ".join(sorted(_UNIT_TO_US))
        raise ValueError(
            f"unsupported timestamp unit '{unit}'; expected one of {allowed}"
        )

    scale_to_us = _UNIT_TO_US[unit_key]
    if array.dtype.kind in "iu":
        # Preserve the complete signed domain for already-normalized integer
        # input without an intermediate floating-point representation.
        if scale_to_us == 1:
            if (
                array.dtype.kind == "u"
                and array.size
                and int(array.max()) >= int(_INT64_UPPER_EXCLUSIVE)
            ):
                raise OverflowError("timestamps exceed int64 microsecond range")
            return array.astype(np.int64, copy=True)

        # Use integer quotient/remainder rounding for nanoseconds so exact
        # half-microsecond ties cannot drift below the tie in binary floating
        # point. Floor division plus an even-quotient tie check also handles
        # negative timestamps symmetrically.
        if scale_to_us < 1:
            quotient, remainder = np.divmod(array, 1000)
            round_up = (remainder > 500) | (
                (remainder == 500) & ((quotient % 2) != 0)
            )
            rounded_integer = quotient + round_up.astype(quotient.dtype)
            return rounded_integer.astype(np.int64, copy=True)

        # Validate scaled integer units before multiplication so the fixed-width
        # operation itself cannot overflow.
        integer_scale = int(scale_to_us)
        lower_input = -((-int(np.iinfo(np.int64).min)) // integer_scale)
        upper_input = int(np.iinfo(np.int64).max) // integer_scale
        if array.size and bool(
            np.any((array < lower_input) | (array > upper_input))
        ):
            raise OverflowError("timestamps exceed int64 microsecond range")
        return array.astype(np.int64, copy=True) * integer_scale

    with np.errstate(over="ignore", invalid="ignore"):
        extended = array.astype(np.longdouble, copy=False)
        scaled = (
            extended / np.longdouble(1000)
            if scale_to_us < 1
            else extended * scale_to_us
        )
        rounded = np.rint(scaled)

    if not bool(np.all(np.isfinite(rounded))):
        raise OverflowError("timestamps exceed int64 microsecond range")
    if rounded.size and bool(
        np.any(
            (rounded < _INT64_LOWER)
            | (rounded >= _INT64_UPPER_EXCLUSIVE)
        )
    ):
        raise OverflowError("timestamps exceed int64 microsecond range")
    return rounded.astype(np.int64)


def infer_timestamp_unit(name: str, default: str = "us") -> str:
    """Infer a timestamp unit from a conventional field suffix.

    Args:
        name: Timestamp field name.
        default: Unit returned for ambiguous names.

    Returns:
        Inferred unit or the supplied default.

    Raises:
        TypeError: If name or default is not text.

    Example:
        print(infer_timestamp_unit("timestamp_ns", default="us"))

    Output:
        ns
    """
    if not isinstance(name, str) or not isinstance(default, str):
        raise TypeError("timestamp field name and default unit must be strings")

    lowered = name.lower()
    if lowered == "us" or lowered.endswith("_us"):
        return "us"
    if lowered == "ms" or lowered.endswith("_ms"):
        return "ms"
    if lowered == "ns" or lowered.endswith("_ns"):
        return "ns"
    if lowered == "s" or lowered.endswith("_s"):
        return "s"
    if lowered in {
        "t",
        "ts",
        "time",
        "timestamp",
        "timestamps",
    }:
        return default
    return default
