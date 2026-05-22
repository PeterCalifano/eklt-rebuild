from __future__ import annotations

import sys
from pathlib import Path
from types import ModuleType

import numpy as np
import pytest
from PIL import Image

from eklt_bridge.config import SequenceSettings, V2EEmulatorSettings
from eklt_bridge.primitives import EventStream
from eklt_bridge.sources import V2EFrameSequenceSource
from eklt_bridge.visualization import render_event_preview_mono8


def _write_frame(path: Path, image: np.ndarray) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    Image.fromarray(image.astype(np.uint8), mode="L").save(path)


def test_event_stream_builds_from_v2e_event_matrix() -> None:
    events = np.array(
        [
            [0.001, 2, 3, 1],
            [0.002, 4, 5, -1],
        ],
        dtype=np.float64,
    )

    stream = EventStream.from_v2e_events(events, width=10, height=12, header_timestamp_ns=2_000_000)

    np.testing.assert_array_equal(stream.timestamp_ns, np.array([1_000_000, 2_000_000]))
    np.testing.assert_array_equal(stream.p01, np.array([1, 0], dtype=np.uint8))
    assert stream.stamp_ns == 2_000_000


def test_event_preview_marks_on_and_off_events() -> None:
    stream = EventStream.from_timestamp_ns(
        np.array([0, 1], dtype=np.int64),
        x=np.array([0, 1], dtype=np.int32),
        y=np.array([0, 0], dtype=np.int32),
        p01=np.array([1, 0], dtype=np.uint8),
        width=2,
        height=1,
        header_timestamp_ns=1,
    )

    preview = render_event_preview_mono8(stream, scale=30)

    assert preview.shape == (1, 2)
    assert preview[0, 0] > 127
    assert preview[0, 1] < 127


def test_v2e_sequence_source_uses_external_emulator(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    frames_dir = tmp_path / "frames"
    _write_frame(frames_dir / "frame_000.png", np.full((2, 2), 20, dtype=np.uint8))
    _write_frame(frames_dir / "frame_001.png", np.full((2, 2), 80, dtype=np.uint8))

    emulator_module = ModuleType("v2ecore.emulator")

    class FakeEventEmulator:
        def __init__(self, **kwargs) -> None:
            self.calls = 0

        def generate_events(self, frame: np.ndarray, timestamp_s: float):
            self.calls += 1
            if self.calls == 1:
                return None
            return np.array([[timestamp_s, 1, 1, 1]], dtype=np.float64)

        def cleanup(self) -> None:
            pass

    emulator_module.EventEmulator = FakeEventEmulator
    monkeypatch.setitem(sys.modules, "v2ecore", ModuleType("v2ecore"))
    monkeypatch.setitem(sys.modules, "v2ecore.emulator", emulator_module)

    source = V2EFrameSequenceSource(
        SequenceSettings(frames_dir=frames_dir, fps=10.0),
        V2EEmulatorSettings(device="cpu"),
    )
    steps = source.build_steps()

    assert len(steps) == 2
    assert steps[0].events is None
    assert steps[1].events is not None
    assert steps[1].events.x[0] == 1
    assert steps[1].events.p01[0] == 1
