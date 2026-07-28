"""Test strict dataset selection and the common loaded-dataset contract."""

from pathlib import Path

import numpy as np
import pytest

from event_vision_utils.io import (
    DatasetMetadata,
    ElopeNpzAdapter,
    GenericNpzAdapter,
    LoadedEventDataset,
    load_event_dataset,
)
from event_vision_utils import EventArray


def _write_official_elope(path: Path, *, nan_pose: bool = False) -> None:
    """Write one minimal archive satisfying the official ELOPE schema."""
    traj = np.zeros((2, 12), dtype=np.float64)
    if nan_pose:
        traj[:, :6] = np.nan
    np.savez(
        path,
        events=np.array(
            [
                [1, 2, 1, 100],
                [3, 4, -1, 200],
            ],
            dtype=np.int64,
        ),
        timestamps=np.array([0.0, 0.1]),
        traj=traj,
        range_meter=np.array([[0.0, 100.0], [0.1, 99.0]], dtype=np.float64),
    )


def test_elope_adapter_loads_official_dataset_to_common_event_format(tmp_path: Path) -> None:
    """Load strict ELOPE data with consistent events and compact metadata."""
    path = tmp_path / "elope.npz"
    _write_official_elope(path)

    dataset = ElopeNpzAdapter().load(path)

    assert dataset.metadata.name == "elope"
    assert dataset.events.as_columns().tolist() == [
        [1, 2, 1, 100],
        [3, 4, -1, 200],
    ]
    assert dataset.metadata.attributes["timestamps_count"] == 2
    assert dataset.metadata.attributes["position_velocity_available"] is True
    assert dataset.metadata.attributes["geometry_source"] == "elope_contract"


def test_elope_adapter_records_masked_test_trajectory_columns(tmp_path: Path) -> None:
    """Report unavailable pose/velocity columns without retaining arrays."""
    path = tmp_path / "elope_test_masked.npz"
    _write_official_elope(path, nan_pose=True)

    dataset = load_event_dataset(path, adapter="elope")

    assert dataset.metadata.attributes["position_velocity_available"] is False


def test_auto_adapter_prefers_official_elope_over_generic_npz(tmp_path: Path) -> None:
    """Select the strict ELOPE path before considering generic matrix data."""
    path = tmp_path / "elope.npz"
    _write_official_elope(path)

    dataset = load_event_dataset(path, adapter="auto")

    assert dataset.metadata.name == "elope"


def test_generic_adapter_handles_non_elope_npz(tmp_path: Path) -> None:
    """Load generic matrix events only with configured sensor geometry."""
    path = tmp_path / "generic.npz"
    np.savez(
        path,
        events=np.array(
            [
                [1, 2, 100, 1],
                [3, 4, 200, -1],
            ],
            dtype=np.int64,
        ),
    )

    dataset = GenericNpzAdapter(width=8, height=8).load(path)

    assert dataset.metadata.name == "generic_npz"
    assert dataset.events.t_us.tolist() == [100, 200]


def test_auto_adapter_accepts_generic_columnar_timestamps(tmp_path: Path) -> None:
    """Do not treat a generic timestamp key alone as ELOPE metadata."""
    path = tmp_path / "generic_columns.npz"
    np.savez(
        path,
        x=np.array([1, 3], dtype=np.int32),
        y=np.array([2, 4], dtype=np.int32),
        p=np.array([1, -1], dtype=np.int8),
        timestamps=np.array([100, 200], dtype=np.int64),
    )

    dataset = load_event_dataset(
        path,
        adapter="auto",
        width=8,
        height=8,
    )

    assert dataset.metadata.name == "generic_npz"
    assert dataset.events.t_us.tolist() == [100, 200]


def test_explicit_elope_adapter_rejects_non_official_npz(tmp_path: Path) -> None:
    """Reject generic data selected explicitly through the ELOPE adapter."""
    path = tmp_path / "generic.npz"
    np.savez(path, events=np.array([[100, 1, 2, 1]], dtype=np.int64))

    with pytest.raises(ValueError, match="not an official ELOPE dataset file"):
        load_event_dataset(path, adapter="elope", width=8, height=8)


def test_elope_can_load_checks_geometry_and_event_values(tmp_path: Path) -> None:
    """Report false when a schema-shaped archive cannot be loaded safely."""
    path = tmp_path / "partial_geometry.npz"
    np.savez(
        path,
        events=np.array([[1, 2, 1, 100]], dtype=np.int64),
        timestamps=np.array([0.0]),
        traj=np.zeros((1, 12), dtype=np.float64),
        range_meter=np.array([[0.0, 10.0]], dtype=np.float64),
        sensor_width=np.asarray(8),
    )

    assert ElopeNpzAdapter().can_load(path) is False


def test_auto_adapter_rejects_malformed_elope_like_archives(tmp_path: Path) -> None:
    """Do not reinterpret malformed ELOPE metadata as generic event data."""
    path = tmp_path / "malformed_elope.npz"
    np.savez(
        path,
        events=np.array([[1, 2, 1, 100]], dtype=np.int64),
        timestamps=np.array([0.0]),
        traj=np.zeros((1, 3), dtype=np.float64),
        range_meter=np.array([[0.0, 10.0]], dtype=np.float64),
    )

    with pytest.raises(ValueError, match="failed strict validation"):
        load_event_dataset(
            path,
            adapter="auto",
            width=8,
            height=8,
        )


def test_generic_dataset_selection_requires_explicit_geometry(tmp_path: Path) -> None:
    """Reject geometry-free generic loading instead of inferring dimensions."""
    path = tmp_path / "generic.npz"
    np.savez(path, events=np.array([[1, 2, 1, 100]], dtype=np.int64))

    with pytest.raises(ValueError, match="explicit width and height"):
        load_event_dataset(path, adapter="generic_npz")


def test_loaded_dataset_rejects_metadata_contract_mismatch() -> None:
    """Keep event geometry and metadata geometry inseparable."""
    events = EventArray(
        x=[0],
        y=[0],
        p=[1],
        t_us=[0],
        width=2,
        height=2,
        frame_id="camera",
    )
    metadata = DatasetMetadata(
        name="fixture",
        source_path=Path("fixture.npz"),
        width=3,
        height=2,
        frame_id="camera",
    )

    with pytest.raises(ValueError, match="does not match"):
        LoadedEventDataset(events=events, metadata=metadata)
