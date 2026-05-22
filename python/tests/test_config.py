from __future__ import annotations

import json
from pathlib import Path
import sys

from eklt_bridge.config import load_stage2a_config
from eklt_bridge.raytracer import import_spectral_rt_py


def test_load_stage2a_config(tmp_path: Path) -> None:
    config_path = tmp_path / "config.json"
    config_payload = {
        "topics": {"events": "/custom/events", "image": "/custom/image"},
        "runtime": {"realtime_factor": 2.0, "publish_first_frame": False},
        "frame": {"width": 320, "height": 240, "normalize_min": 0.1, "normalize_max": 2.0},
        "source": {"kind": "frames_only"},
        "v2e": {"pos_thres": 0.3, "device": "cpu"},
        "sequence": {"frames_dir": str(tmp_path / "frames"), "fps": 15.0},
    }
    config_path.write_text(json.dumps(config_payload), encoding="utf-8")

    config = load_stage2a_config(config_path)

    assert config.topics.events == "/custom/events"
    assert config.frame.width == 320
    assert config.source.kind == "frames_only"
    assert config.v2e.pos_thres == 0.3
    assert config.runtime.realtime_factor == 2.0
    assert config.runtime.publish_first_frame is False
    assert config.sequence is not None
    assert config.sequence.fps == 15.0


def test_importer_can_load_spectral_rt_py_from_checkout_root(tmp_path: Path) -> None:
    package_root = tmp_path / "spectral_raytracer" / "python" / "spectral_rt_py"
    package_root.mkdir(parents=True)
    (package_root / "__init__.py").write_text("VALUE = 42\n", encoding="utf-8")

    module = import_spectral_rt_py(tmp_path / "spectral_raytracer")

    assert module.VALUE == 42
    sys.modules.pop("spectral_rt_py", None)
