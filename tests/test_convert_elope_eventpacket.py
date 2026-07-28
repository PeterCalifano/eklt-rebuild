"""Verify bounded ELOPE conversion to standard ROS2 EventPacket bags."""

from __future__ import annotations

import importlib.util
import json
import sys
from pathlib import Path
from types import ModuleType

import numpy as np
import pytest
from rosbags.rosbag2 import Reader


def load_converter() -> ModuleType:
    """Load the repository converter without making scripts a Python package.

    Returns:
        Imported converter module.
    """
    converter_path = (
        Path(__file__).resolve().parents[1]
        / "scripts"
        / "convert_elope_npz_to_eventpacket.py"
    )
    specification = importlib.util.spec_from_file_location(
        "convert_elope_npz_to_eventpacket", converter_path
    )
    if specification is None or specification.loader is None:
        raise RuntimeError("failed to load ELOPE converter module")

    module = importlib.util.module_from_spec(specification)
    sys.modules[specification.name] = module
    specification.loader.exec_module(module)
    return module


CONVERTER = load_converter()


def write_structured_fixture(path: Path,
                             sensor_width: int | None = None,
                             sensor_height: int | None = None) -> None:
    """Write one compact official-shape ELOPE event fixture.

    Args:
        path: Destination NPZ file.
        sensor_width: Optional advertised sensor width.
        sensor_height: Optional advertised sensor height.
    """
    event_dtype = np.dtype(
        [("x", "u1"), ("y", "u1"), ("p", "?"), ("t", "<u8")]
    )
    events = np.array(
        [
            (1, 2, True, 10),
            (3, 4, False, 20),
            (5, 6, True, 20),
            (7, 8, False, 40),
        ],
        dtype=event_dtype,
    )
    payload: dict[str, object] = {
        "events": events,
        "timestamps": np.array([0.0]),
        "traj": np.zeros((1, 12)),
        "range_meter": np.zeros((1, 2)),
    }
    if sensor_width is not None:
        payload["sensor_width"] = np.asarray(sensor_width)
    if sensor_height is not None:
        payload["sensor_height"] = np.asarray(sensor_height)
    np.savez(path, **payload)


def test_converter_loads_only_required_event_data(tmp_path: Path) -> None:
    """Structured event fields normalize without consuming other arrays."""
    input_path = tmp_path / "elope.npz"
    write_structured_fixture(input_path)

    x_values, y_values, polarities, timestamps_us, keys = (
        CONVERTER.load_elope_events(input_path, 16, 16)
    )

    np.testing.assert_array_equal(x_values, [1, 3, 5, 7])
    np.testing.assert_array_equal(y_values, [2, 4, 6, 8])
    np.testing.assert_array_equal(polarities, [1, 0, 1, 0])
    np.testing.assert_array_equal(timestamps_us, [10, 20, 20, 40])
    assert keys == ["events", "range_meter", "timestamps", "traj"]


def test_geometry_uses_metadata_then_official_contract(tmp_path: Path) -> None:
    """Advertised dimensions take priority without coordinate-max inference."""
    advertised_path = tmp_path / "advertised.npz"
    write_structured_fixture(
        advertised_path, sensor_width=16, sensor_height=12
    )

    advertised = CONVERTER.resolve_sensor_geometry(
        advertised_path, None, None
    )
    assert (advertised.width, advertised.height) == (16, 12)
    assert advertised.source == "npz:sensor_width,sensor_height"

    contract_path = tmp_path / "official_contract.npz"
    write_structured_fixture(contract_path)
    contract = CONVERTER.resolve_sensor_geometry(contract_path, None, None)
    assert (contract.width, contract.height) == (200, 200)
    assert contract.source == "elope_contract"


def test_geometry_rejects_conflicting_override(tmp_path: Path) -> None:
    """An explicit override cannot contradict dimensions stored in the NPZ."""
    input_path = tmp_path / "advertised.npz"
    write_structured_fixture(
        input_path, sensor_width=16, sensor_height=12
    )

    with pytest.raises(ValueError, match="conflicts"):
        CONVERTER.resolve_sensor_geometry(input_path, 20, 12)


def test_geometry_rejects_partial_metadata(tmp_path: Path) -> None:
    """A lone dimension key cannot silently combine with a default."""
    input_path = tmp_path / "partial_geometry.npz"
    write_structured_fixture(input_path, sensor_width=16)

    with pytest.raises(ValueError, match="provide both"):
        CONVERTER.resolve_sensor_geometry(input_path, None, None)


def test_converter_writes_bounded_atomic_eventpacket_bag(tmp_path: Path) -> None:
    """Packet count limits and atomic output are reflected in the summary."""
    input_path = tmp_path / "elope.npz"
    output_path = tmp_path / "eventpacket_bag"
    summary_path = tmp_path / "conversion.json"
    write_structured_fixture(
        input_path, sensor_width=16, sensor_height=12
    )

    statistics = CONVERTER.convert_elope(
        input_path=input_path,
        output_path=output_path,
        output_topic="/events",
        summary_path=summary_path,
        width=None,
        height=None,
        frame_id="event_camera",
        dt_ms=1.0,
        max_events_per_packet=2,
        max_packets=1,
    )

    assert statistics.event_packets == 1
    assert statistics.event_count == 2
    assert (statistics.width, statistics.height) == (16, 12)
    assert statistics.geometry_source == "npz:sensor_width,sensor_height"
    assert output_path.is_dir()
    assert not list(tmp_path.glob(".eventpacket_bag.staging-*"))
    with Reader(output_path) as reader:
        assert sum(1 for _ in reader.messages()) == 1

    summary = json.loads(summary_path.read_text(encoding="utf-8"))
    assert summary["status"] == "passed"
    assert summary["source_event_count"] == 4
    assert summary["event_count"] == 2


def test_converter_rejects_timestamp_regression(tmp_path: Path) -> None:
    """Regressing event timestamps fail before an output directory is made."""
    input_path = tmp_path / "regressing.npz"
    np.savez(
        input_path,
        events=np.array(
            [[1, 1, 1, 20], [2, 2, -1, 10]],
            dtype=np.int64,
        ),
    )

    with pytest.raises(ValueError, match="monotonic"):
        CONVERTER.load_elope_events(input_path, 8, 8)
