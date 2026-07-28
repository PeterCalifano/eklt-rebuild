"""Test exact and scaled microsecond timestamp normalization."""

import numpy as np
import pytest

from event_vision_utils.core.timestamps import (
    infer_timestamp_unit,
    normalize_timestamps_to_us,
)


def test_seconds_convert_to_microseconds() -> None:
    """Convert finite floating-point seconds to integer microseconds."""
    assert normalize_timestamps_to_us([0.0, 0.001, 1.25], unit="s").tolist() == [
        0,
        1000,
        1250000,
    ]


def test_milliseconds_convert_to_microseconds() -> None:
    """Scale exact millisecond integers without changing order."""
    assert normalize_timestamps_to_us(np.array([1, 2, 3]), unit="ms").tolist() == [
        1000,
        2000,
        3000,
    ]


def test_nanoseconds_round_to_microseconds() -> None:
    """Use round-to-even conversion for sub-microsecond nanoseconds."""
    assert normalize_timestamps_to_us(
        [-2500, -1500, 0, 1500, 2500],
        unit="ns",
    ).tolist() == [-2, -2, 0, 2, 2]


def test_infer_timestamp_units_from_key_names() -> None:
    """Recognize conventional explicit timestamp suffixes."""
    assert infer_timestamp_unit("t_us", "s") == "us"
    assert infer_timestamp_unit("timestamp_ms", "us") == "ms"
    assert infer_timestamp_unit("timestamp_s", "us") == "s"
    assert infer_timestamp_unit("t", "s") == "s"
    assert infer_timestamp_unit("status", "us") == "us"


def test_reject_nonfinite_timestamps() -> None:
    """Reject non-finite source timestamps before scaling."""
    with pytest.raises(ValueError, match="finite"):
        normalize_timestamps_to_us([0.0, float("nan")], unit="us")


def test_preserve_complete_integer_microsecond_domain() -> None:
    """Avoid a float64 round trip for normalized signed int64 values."""
    timestamps_us = np.array(
        [np.iinfo(np.int64).min, np.iinfo(np.int64).max],
        dtype=np.int64,
    )

    normalized = normalize_timestamps_to_us(timestamps_us, unit="us")

    assert np.array_equal(normalized, timestamps_us)


def test_reject_unsigned_and_scaled_timestamp_overflow() -> None:
    """Reject values at the exclusive signed-int64 upper boundary."""
    with pytest.raises(OverflowError, match="int64"):
        normalize_timestamps_to_us(
            np.array([2**63], dtype=np.uint64),
            unit="us",
        )

    with pytest.raises(OverflowError, match="int64"):
        normalize_timestamps_to_us([float(2**63)], unit="us")

    with pytest.raises(OverflowError, match="int64"):
        normalize_timestamps_to_us(
            np.array([np.iinfo(np.int64).max], dtype=np.int64),
            unit="ms",
        )
