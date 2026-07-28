"""Test explicit generic-NPZ field, geometry, and timestamp policies."""

from pathlib import Path

import numpy as np
import pytest

from event_vision_utils.io import load_generic_npz


def test_generic_npz_loads_separate_arrays(tmp_path: Path) -> None:
    """Load columnar events while converting the declared timestamp unit."""
    path = tmp_path / "events_separate.npz"
    np.savez(
        path,
        x=np.array([0, 1, 2]),
        y=np.array([3, 4, 5]),
        p=np.array([0, 1, 0]),
        t=np.array([0.0, 0.001, 0.002]),
    )

    events = load_generic_npz(path, width=10, height=10, timestamp_unit="s")

    assert events.x.tolist() == [0, 1, 2]
    assert events.y.tolist() == [3, 4, 5]
    assert events.p.tolist() == [-1, 1, -1]
    assert events.t_us.tolist() == [0, 1000, 2000]


def test_generic_npz_infers_explicit_seconds_suffix(tmp_path: Path) -> None:
    """Honor a conventional timestamp suffix instead of the default unit."""
    path = tmp_path / "events_seconds.npz"
    np.savez(
        path,
        x=np.array([0, 1]),
        y=np.array([1, 0]),
        p=np.array([-1, 1]),
        timestamp_s=np.array([0.001, 0.002]),
    )

    events = load_generic_npz(path, width=2, height=2)

    assert events.t_us.tolist() == [1000, 2000]


def test_generic_npz_loads_configurable_matrix_columns(tmp_path: Path) -> None:
    """Map caller-declared matrix columns into the canonical event order."""
    path = tmp_path / "events_matrix.npz"
    event_matrix = np.array(
        [
            [0, 2, 3, 1],
            [10, 4, 5, -1],
        ]
    )
    np.savez(path, event_tuple=event_matrix)

    events = load_generic_npz(
        path,
        width=10,
        height=10,
        events_key="event_tuple",
        column_order=("t_us", "x", "y", "p"),
    )

    assert events.as_columns(("t_us", "x", "y", "p")).tolist() == [
        [0, 2, 3, 1],
        [10, 4, 5, -1],
    ]


def test_generic_npz_rejects_a_missing_explicit_matrix_key(tmp_path: Path) -> None:
    """Do not silently select another array when an explicit key is absent."""
    path = tmp_path / "events_matrix.npz"
    np.savez(path, events=np.array([[1, 2, 3, 1]], dtype=np.int64))

    with pytest.raises(KeyError, match="missing event matrix key 'requested'"):
        load_generic_npz(
            path,
            width=8,
            height=8,
            events_key="requested",
        )


def test_generic_npz_rejects_duplicate_structured_aliases(tmp_path: Path) -> None:
    """Reject two structured fields that map to one canonical coordinate."""
    path = tmp_path / "duplicate_structured_fields.npz"
    structured = np.array(
        [(1, 1, 2, 1, 10)],
        dtype=[
            ("x", "<i4"),
            ("col", "<i4"),
            ("y", "<i4"),
            ("p", "<i1"),
            ("t_us", "<i8"),
        ],
    )
    np.savez(path, events=structured)

    with pytest.raises(ValueError, match="duplicate 'x' fields"):
        load_generic_npz(path, width=8, height=8)


def test_generic_npz_rejects_multidimensional_structured_events(tmp_path: Path) -> None:
    """Require one structured record per event rather than a record matrix."""
    path = tmp_path / "structured_matrix.npz"
    structured = np.zeros(
        (1, 1),
        dtype=[
            ("x", "<i4"),
            ("y", "<i4"),
            ("p", "<i1"),
            ("t_us", "<i8"),
        ],
    )
    np.savez(path, events=structured)

    with pytest.raises(ValueError, match="one-dimensional"):
        load_generic_npz(path, width=8, height=8)
