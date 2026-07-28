"""Test accepted polarity alphabets and pre-narrowing validation."""

import pytest

from event_vision_utils.core.validation import normalize_polarity


def test_normalize_bool_polarity() -> None:
    """Map Boolean polarity to signed polarity."""
    assert normalize_polarity([False, True]).tolist() == [-1, 1]


def test_normalize_zero_one_polarity() -> None:
    """Map binary polarity to signed polarity."""
    assert normalize_polarity([0, 1, 1, 0]).tolist() == [-1, 1, 1, -1]


def test_normalize_signed_polarity() -> None:
    """Preserve already-signed polarity."""
    assert normalize_polarity([-1, 1, -1]).tolist() == [-1, 1, -1]


def test_reject_unknown_polarity_values() -> None:
    """Reject mixed and unsupported discrete alphabets."""
    with pytest.raises(ValueError, match="polarity"):
        normalize_polarity([-1, 0, 1])


def test_reject_fractional_and_narrowing_overflow_polarity() -> None:
    """Reject values that could truncate or wrap into an accepted alphabet."""
    with pytest.raises(ValueError, match="discrete"):
        normalize_polarity([0.5])
    with pytest.raises(ValueError, match="polarity"):
        normalize_polarity([65537])
