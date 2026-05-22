from __future__ import annotations

import json
from pathlib import Path

import numpy as np
from PIL import Image

from eklt_bridge.config import load_stage2a_config
from eklt_bridge.runtime import BridgePipeline


def _write_frame(path: Path, image: np.ndarray) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    Image.fromarray(image.astype(np.uint8), mode="L").save(path)


def test_pipeline_builds_first_frame_plus_event_steps(tmp_path: Path) -> None:
    frames_dir = tmp_path / "frames"
    _write_frame(frames_dir / "frame_000.png", np.full((2, 2), 50, dtype=np.uint8))
    _write_frame(frames_dir / "frame_001.png", np.full((2, 2), 100, dtype=np.uint8))
    _write_frame(frames_dir / "frame_002.png", np.full((2, 2), 120, dtype=np.uint8))

    config_path = tmp_path / "stage2.json"
    config_path.write_text(
        json.dumps(
            {
                "sequence": {
                    "frames_dir": str(frames_dir),
                    "fps": 10.0,
                },
                "source": {"kind": "frames_only"},
            }
        ),
        encoding="utf-8",
    )

    pipeline = BridgePipeline(load_stage2a_config(config_path))
    steps = pipeline.build_steps()

    assert len(steps) == 3
    assert steps[0].frame is not None
    assert steps[0].events is None
    assert steps[1].event_preview_mono8 is None
