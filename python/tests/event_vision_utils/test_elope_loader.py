"""Test official ELOPE schema, geometry, and event-column handling."""

from pathlib import Path

import numpy as np
import pytest

from event_vision_utils.io import (
    ElopeGeometry,
    load_elope_npz,
    resolve_elope_geometry,
)


def _write_official_elope_npz(path: Path, events: object) -> None:
    """Write a minimal official-schema ELOPE archive for loader tests."""
    np.savez(
        path,
        events=np.asarray(events),
        timestamps=np.array([0.0, 0.1]),
        traj=np.zeros((2, 12), dtype=np.float64),
        range_meter=np.array([[0.0, 100.0], [0.1, 95.0]], dtype=np.float64),
    )


def test_elope_npz_uses_default_200_by_200_sensor_size(tmp_path: Path) -> None:
    """Use the published ELOPE geometry when metadata is absent."""
    path = tmp_path / "elope_events.npz"
    events_xy_pt = np.array(
        [
            [0, 0, 1, 100],
            [199, 199, 0, 200],
        ]
    )
    _write_official_elope_npz(path, events_xy_pt)

    events = load_elope_npz(path)

    assert events.width == 200
    assert events.height == 200
    assert events.x.tolist() == [0, 199]
    assert events.y.tolist() == [0, 199]
    assert events.t_us.tolist() == [100, 200]
    assert events.p.tolist() == [1, -1]


def test_elope_geometry_rejects_invalid_direct_construction() -> None:
    """Keep the exported geometry data structure valid when built directly."""
    with pytest.raises(ValueError, match="width"):
        ElopeGeometry(width=0, height=1, source="fixture")
    with pytest.raises(ValueError, match="source"):
        ElopeGeometry(width=1, height=1, source=" ")


def test_elope_npz_uses_advertised_sensor_size(tmp_path: Path) -> None:
    """Prefer a complete scalar geometry pair advertised by the archive."""
    path = tmp_path / "elope_advertised_geometry.npz"
    np.savez(
        path,
        events=np.array([[0, 0, 1, 100], [15, 11, 0, 200]]),
        timestamps=np.array([0.0, 0.1]),
        traj=np.zeros((2, 12), dtype=np.float64),
        range_meter=np.array(
            [[0.0, 100.0], [0.1, 95.0]], dtype=np.float64
        ),
        sensor_width=np.asarray(16),
        sensor_height=np.asarray(12),
    )

    geometry = resolve_elope_geometry(path)
    events = load_elope_npz(path)

    assert (geometry.width, geometry.height) == (16, 12)
    assert geometry.source == "npz:sensor_width,sensor_height"
    assert (events.width, events.height) == (16, 12)


def test_elope_geometry_remains_independent_of_ros_transport_limits(tmp_path: Path) -> None:
    """Accept generic geometry beyond the narrower EventPacket encoding."""
    path = tmp_path / "elope_large_geometry.npz"
    np.savez(
        path,
        events=np.array([[0, 0, 1, 100]], dtype=np.int64),
        timestamps=np.array([0.0]),
        traj=np.zeros((1, 12), dtype=np.float64),
        range_meter=np.array([[0.0, 100.0]], dtype=np.float64),
        sensor_width=np.asarray(70_000),
        sensor_height=np.asarray(40_000),
    )

    geometry = resolve_elope_geometry(path)
    events = load_elope_npz(path)

    assert (geometry.width, geometry.height) == (70_000, 40_000)
    assert (events.width, events.height) == (70_000, 40_000)


def test_elope_npz_rejects_geometry_override_conflict(tmp_path: Path) -> None:
    """Reject an explicit geometry that contradicts archive metadata."""
    path = tmp_path / "elope_advertised_geometry.npz"
    np.savez(
        path,
        events=np.array([[0, 0, 1, 100]]),
        timestamps=np.array([0.0]),
        traj=np.zeros((1, 12), dtype=np.float64),
        range_meter=np.array([[0.0, 100.0]], dtype=np.float64),
        width=np.asarray(16),
        height=np.asarray(12),
    )

    with pytest.raises(ValueError, match="conflicts"):
        load_elope_npz(path, width=20, height=12)


def test_elope_npz_loads_real_structured_event_array(tmp_path: Path) -> None:
    """Load the one-dimensional structured event dtype used by ELOPE."""
    path = tmp_path / "elope_structured_events.npz"
    structured = np.array(
        [(127, 87, True, 18_000), (76, 31, False, 21_000)],
        dtype=[("x", "u1"), ("y", "u1"), ("p", "?"), ("t", "<u8")],
    )
    _write_official_elope_npz(path, structured)

    events = load_elope_npz(path)

    assert events.x.tolist() == [127, 76]
    assert events.y.tolist() == [87, 31]
    assert events.p.tolist() == [1, -1]
    assert events.t_us.tolist() == [18_000, 21_000]


def test_elope_npz_rejects_non_elope_npz(tmp_path: Path) -> None:
    """Require the official auxiliary keys in strict mode."""
    path = tmp_path / "non_elope.npz"
    np.savez(
        path,
        events=np.array(
            [
                [1000, 1, 2, 1],
                [2000, 3, 4, -1],
            ]
        ),
    )

    with pytest.raises(ValueError, match="not an official ELOPE dataset file"):
        load_elope_npz(path)


def test_elope_npz_validates_motion_metadata_shape(tmp_path: Path) -> None:
    """Reject trajectory metadata without the official state width."""
    path = tmp_path / "bad_traj.npz"
    np.savez(
        path,
        events=np.array(
            [
                [1, 2, 1, 1000],
                [3, 4, -1, 2000],
            ]
        ),
        timestamps=np.array([0.0]),
        traj=np.zeros((1, 3)),
        range_meter=np.array([[0.0, 100.0]]),
    )

    with pytest.raises(ValueError, match="traj"):
        load_elope_npz(path)


def test_elope_npz_allows_legacy_fixture_only_when_strict_disabled(tmp_path: Path) -> None:
    """Keep non-official matrix fixtures behind an explicit strictness opt-out."""
    path = tmp_path / "legacy_txy_p.npz"
    events_t_xy_p = np.array(
        [
            [1000, 1, 2, 1],
            [2000, 3, 4, -1],
        ]
    )
    np.savez(path, events=events_t_xy_p)

    events = load_elope_npz(
        path,
        column_order=("t_us", "x", "y", "p"),
        strict=False,
    )

    assert events.x.tolist() == [1, 3]
    assert events.y.tolist() == [2, 4]
    assert events.t_us.tolist() == [1000, 2000]


def test_elope_npz_rejects_multidimensional_structured_events(tmp_path: Path) -> None:
    """Reject structured record matrices before generic event conversion."""
    path = tmp_path / "structured_matrix.npz"
    structured = np.zeros(
        (1, 1),
        dtype=[("x", "u1"), ("y", "u1"), ("p", "?"), ("t", "<u8")],
    )
    _write_official_elope_npz(path, structured)

    with pytest.raises(ValueError, match="one-dimensional"):
        load_elope_npz(path)
