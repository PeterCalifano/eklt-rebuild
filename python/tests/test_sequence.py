from __future__ import annotations

from pathlib import Path

import numpy as np
from PIL import Image

from eklt_bridge.config import SequenceSettings
from eklt_bridge.sequence import iter_frame_samples, load_sequence_manifest


def _write_frame(path: Path, image: np.ndarray) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    Image.fromarray(image.astype(np.uint8), mode="L").save(path)


def test_sequence_manifest_uses_fps_when_no_timestamp_file(tmp_path: Path) -> None:
    frames_dir = tmp_path / "frames"
    _write_frame(frames_dir / "frame_000.png", np.zeros((2, 3), dtype=np.uint8))
    _write_frame(frames_dir / "frame_001.png", np.ones((2, 3), dtype=np.uint8) * 40)

    manifest = load_sequence_manifest(
        SequenceSettings(
            frames_dir=frames_dir,
            fps=20.0,
            start_time_ns=500,
        )
    )

    assert manifest.timestamp_ns == (500, 50_000_500)


def test_iter_frame_samples_loads_grayscale_images(tmp_path: Path) -> None:
    frames_dir = tmp_path / "frames"
    _write_frame(frames_dir / "frame_000.png", np.array([[0, 10], [20, 30]], dtype=np.uint8))
    _write_frame(frames_dir / "frame_001.png", np.array([[40, 50], [60, 70]], dtype=np.uint8))

    samples = iter_frame_samples(
        SequenceSettings(
            frames_dir=frames_dir,
            fps=10.0,
        )
    )

    assert len(samples) == 2
    assert samples[0].timestamp_ns == 0
    assert samples[1].timestamp_ns == 100_000_000
    assert samples[1].image_mono8[1, 1] == 70
