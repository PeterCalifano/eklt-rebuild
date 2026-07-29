"""Verify streamed ELOPE reconstruction and dense FIBAR patch mosaics."""

from __future__ import annotations

import json
from pathlib import Path

import numpy as np
from PIL import Image
import pytest

from event_vision_utils.examples import reconstruct_elope_fibar
from event_vision_utils.examples.reconstruct_elope_fibar import (
    _PatchDebugTile,
    _compose_patch_debug_frame,
    _write_patch_quality_plot,
    main as reconstruct_main,
)
from event_vision_utils.recon import (
    SFibarConfig,
    SLocalFeaturePatch,
    fibar_native_available,
)


class _FakeFibarReconstructor:
    """Provide deterministic native-shaped results for integration tests."""

    def __init__(self, config: SFibarConfig) -> None:
        self._width = config.width
        self._height = config.height

    def accept_events(self,
                      x: object,
                      y: object,
                      p: object,
                      t_us: object) -> None:
        """Accept one event batch without retaining it."""
        del x, y, p, t_us

    def request_image(self, t_us: int) -> np.ndarray:
        """Return a deterministic scalar image at one timestamp."""
        del t_us
        values = np.arange(
            self._width * self._height,
            dtype=np.float32,
        )
        return values.reshape(self._height, self._width)

    def request_patch(self,
                      x: int,
                      y: int,
                      radius: int,
                      t_us: int) -> SLocalFeaturePatch:
        """Return one typed local patch and quality record."""
        width = radius * 2 + 1
        intensity = (
            np.arange(width * width, dtype=np.float32) +
            float(x + y)
        ).reshape(width, width)
        return SLocalFeaturePatch(
            intensity=intensity,
            gradient_x=np.ones_like(intensity),
            gradient_y=np.ones_like(intensity),
            valid_mask=np.ones_like(intensity, dtype=np.uint8),
            width=width,
            height=width,
            center_x=x,
            center_y=y,
            t_us=t_us,
            valid_fraction=1.0,
            gradient_energy=float(t_us + 1),
        )


def _native_available() -> bool:
    """Report an available fake boundary for integration tests."""
    return True


def _write_elope_fixture(path: Path) -> None:
    """Write one strict small ELOPE archive."""
    np.savez(
        path,
        events=np.array(
            [
                [2, 2, 1, 0],
                [3, 3, -1, 10_000],
                [4, 4, 1, 20_000],
                [5, 5, -1, 30_000],
            ]
        ),
        timestamps=np.array([0.0, 0.03]),
        traj=np.zeros((2, 12), dtype=np.float64),
        range_meter=np.array(
            [[0.0, 100.0], [0.03, 99.0]],
            dtype=np.float64,
        ),
    )


def test_reconstruct_reports_missing_native_wrapper(tmp_path: Path) -> None:
    """A missing wrapper reports the public package boundary without aliases."""
    if fibar_native_available():
        pytest.skip("native wrapper is available")

    input_path = tmp_path / "events.npz"
    output_dir = tmp_path / "out"
    _write_elope_fixture(input_path)

    exit_code = reconstruct_main(
        [
            "--input",
            str(input_path),
            "--output-dir",
            str(output_dir),
            "--width",
            "8",
            "--height",
            "8",
            "--dt-ms",
            "20",
        ]
    )

    assert exit_code == 2
    summary = json.loads(
        (output_dir / "summary.json").read_text(encoding="utf-8")
    )
    assert summary["schema_version"] == 1
    assert summary["status"] == "blocked"
    assert summary["blocker"] == (
        "the eklt_rebuild native wrapper is not built"
    )
    assert "_fibar" not in summary["blocker"]
    assert "frames" not in summary["preview"]
    assert set(summary["plot_contracts"]) == {
        "event_rate.png",
        "event_stream_3d_views.png",
    }


def test_reconstruction_and_patch_debug_with_native(tmp_path: Path) -> None:
    """An installed native wrapper produces both documented videos."""
    if not fibar_native_available():
        pytest.skip("native wrapper is unavailable")

    input_path = tmp_path / "events.npz"
    output_dir = tmp_path / "out_native"
    _write_elope_fixture(input_path)

    exit_code = reconstruct_main(
        [
            "--input",
            str(input_path),
            "--output-dir",
            str(output_dir),
            "--width",
            "8",
            "--height",
            "8",
            "--dt-ms",
            "20",
        ]
    )

    assert exit_code == 0
    summary = json.loads(
        (output_dir / "summary.json").read_text(encoding="utf-8")
    )
    assert summary["status"] == "passed"
    assert summary["reconstruction_frames"] == 2
    assert summary["patch_debug_frames"] == 2
    assert summary["patch_debug"]["width"] == 1200
    assert summary["patch_debug"]["height"] == 800
    assert set(summary["plot_contracts"]) == {
        "event_rate.png",
        "event_stream_3d_views.png",
        "patch_quality.png",
    }


def test_fibar_example_streams_typed_patch_mosaic(tmp_path: Path,
                                                  monkeypatch: pytest.MonkeyPatch) -> None:
    """The complete example consumes typed patches in two bounded passes."""
    input_path = tmp_path / "events.npz"
    output_dir = tmp_path / "out_fake_native"
    _write_elope_fixture(input_path)
    monkeypatch.setattr(
        reconstruct_elope_fibar,
        "CFibarReconstructor",
        _FakeFibarReconstructor,
    )
    monkeypatch.setattr(
        reconstruct_elope_fibar,
        "fibar_native_available",
        _native_available,
    )

    exit_code = reconstruct_main(
        [
            "--input",
            str(input_path),
            "--output-dir",
            str(output_dir),
            "--width",
            "8",
            "--height",
            "8",
            "--dt-ms",
            "20",
            "--max-patch-quality-samples",
            "1",
        ]
    )

    assert exit_code == 0
    summary = json.loads(
        (output_dir / "summary.json").read_text(encoding="utf-8")
    )
    assert summary["reconstruction_frames"] == 2
    assert summary["patch_debug_frames"] == 2
    assert summary["patch_debug"]["width"] == 1200
    assert summary["patch_debug"]["height"] == 800
    assert summary["patch_layout"]["mosaic_columns"] == 2
    assert summary["patch_quality_count"] > 1
    assert summary["patch_quality_samples"] == 1
    assert summary["patch_quality_truncated"]
    assert "frames" not in summary["patch_debug"]
    with Image.open(output_dir / "plots" / "patch_quality.png") as image:
        assert image.size == (900, 480)


def test_cleanup_preserves_unrelated_output(tmp_path: Path,
                                            monkeypatch: pytest.MonkeyPatch) -> None:
    """A rerun removes only exact owned artifacts below its output root."""
    input_path = tmp_path / "events.npz"
    output_dir = tmp_path / "out"
    output_dir.mkdir()
    unrelated = output_dir / "notes.txt"
    unrelated.write_text("preserve\n", encoding="utf-8")
    stale = output_dir / "reconstruction_frames"
    stale.mkdir()
    (stale / "frame_999999.png").write_bytes(b"stale")
    _write_elope_fixture(input_path)
    monkeypatch.setattr(
        reconstruct_elope_fibar,
        "CFibarReconstructor",
        _FakeFibarReconstructor,
    )
    monkeypatch.setattr(
        reconstruct_elope_fibar,
        "fibar_native_available",
        _native_available,
    )

    assert reconstruct_main(
        [
            "--input",
            str(input_path),
            "--output-dir",
            str(output_dir),
            "--width",
            "8",
            "--height",
            "8",
            "--dt-ms",
            "20",
        ]
    ) == 0

    assert unrelated.read_text(encoding="utf-8") == "preserve\n"
    assert not (stale / "frame_999999.png").exists()


def test_reconstruction_cleanup_refuses_symlink(tmp_path: Path) -> None:
    """Owned cleanup never follows a video-fallback directory symlink."""
    input_path = tmp_path / "events.npz"
    output_dir = tmp_path / "out"
    output_dir.mkdir()
    prior_summary = output_dir / "summary.json"
    prior_summary.write_text('{"status": "passed"}\n', encoding="utf-8")
    external = tmp_path / "external"
    external.mkdir()
    marker = external / "preserve.txt"
    marker.write_text("preserve\n", encoding="utf-8")
    (output_dir / "reconstruction_frames").symlink_to(
        external,
        target_is_directory=True,
    )
    _write_elope_fixture(input_path)

    with pytest.raises(
        ValueError,
        match="symlinked owned artifact",
    ):
        reconstruct_main(
            [
                "--input",
                str(input_path),
                "--output-dir",
                str(output_dir),
                "--width",
                "8",
                "--height",
                "8",
            ]
        )
    assert marker.read_text(encoding="utf-8") == "preserve\n"
    assert prior_summary.read_text(encoding="utf-8") == (
        '{"status": "passed"}\n'
    )


def test_cleanup_refuses_symlinked_plot_parent(tmp_path: Path) -> None:
    """Owned plot cleanup never traverses a symlinked plot directory."""
    input_path = tmp_path / "events.npz"
    output_dir = tmp_path / "out"
    output_dir.mkdir()
    external = tmp_path / "external"
    external.mkdir()
    marker = external / "event_rate.png"
    marker.write_text("preserve\n", encoding="utf-8")
    (output_dir / "plots").symlink_to(
        external,
        target_is_directory=True,
    )
    _write_elope_fixture(input_path)

    with pytest.raises(
        ValueError,
        match="symlinked owned-artifact parent",
    ):
        reconstruct_main(
            [
                "--input",
                str(input_path),
                "--output-dir",
                str(output_dir),
                "--width",
                "8",
                "--height",
                "8",
            ]
        )
    assert marker.read_text(encoding="utf-8") == "preserve\n"


def test_empty_patch_quality_plot_keeps_labels(tmp_path: Path) -> None:
    """No candidate patches still produce the full chart contract."""
    output = _write_patch_quality_plot(
        [],
        tmp_path / "empty_patch_quality.png",
    )

    with Image.open(output) as image:
        assert image.size == (900, 480)
        assert image.getbbox() is not None


def test_compose_patch_debug_frame_uses_large_fixed_mosaic() -> None:
    """Patch slots occupy a dark 2-by-4 grid beside the event panel."""
    base = np.full((20, 20, 3), 255, dtype=np.uint8)
    tiles = [
        _PatchDebugTile(
            image=np.full((3, 3, 3), color, dtype=np.uint8),
            x=index + 2,
            y=index + 3,
            valid_fraction=1.0,
            gradient_energy=2.0,
            accepted=True,
        )
        for index, color in enumerate((40, 90, 140))
    ]

    frame = _compose_patch_debug_frame(
        base,
        tiles,
        max_tiles=8,
        panel_size=160,
        mosaic_columns=2,
    )

    assert frame.shape == (160, 240, 3)
    assert frame[34, 180].tolist() == [40, 40, 40]
    mosaic = frame[:, 160:]
    assert not np.any(np.all(mosaic == 255, axis=2))


def test_patch_mosaic_rejects_unbounded_geometry_before_allocation() -> None:
    """Wide candidate grids fail before creating their composite canvas."""
    with pytest.raises(ValueError, match="encoded-frame pixel limit"):
        _compose_patch_debug_frame(
            np.zeros((2, 2, 3), dtype=np.uint8),
            [],
            max_tiles=32,
            panel_size=2048,
            mosaic_columns=32,
        )
