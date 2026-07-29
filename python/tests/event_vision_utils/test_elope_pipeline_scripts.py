"""Verify ELOPE download safety and pipeline-owned cleanup boundaries."""

from __future__ import annotations

import io
import json
import os
import subprocess
import zipfile
from pathlib import Path
from unittest.mock import Mock

import numpy as np
import pytest

from event_vision_utils.examples.render_elope_tracks import (
    main as render_elope_tracks,
)


def _repository_root() -> Path:
    """Return the checkout root containing the tested shell entrypoints."""
    return Path(__file__).resolve().parents[3]


def _elope_npz_bytes() -> bytes:
    """Return one strict ELOPE archive payload without a temporary file."""
    payload = io.BytesIO()
    np.savez(
        payload,
        events=np.array(
            [
                [0, 0, 1, 0],
                [1, 1, -1, 10_000],
            ]
        ),
        timestamps=np.array([0.0, 0.01]),
        traj=np.zeros((2, 12), dtype=np.float64),
        range_meter=np.array(
            [[0.0, 100.0], [0.01, 99.0]],
            dtype=np.float64,
        ),
    )
    return payload.getvalue()


def _run_script(script_name: str,
                arguments: list[str]) -> subprocess.CompletedProcess[str]:
    """Run one repository shell script with the Python 3.12 contract."""
    repository_root = _repository_root()
    environment = os.environ.copy()
    environment["PYTHON"] = "python3.12"
    return subprocess.run(
        [
            str(repository_root / "scripts" / script_name),
            *arguments,
        ],
        cwd=repository_root,
        env=environment,
        check=False,
        capture_output=True,
        text=True,
        timeout=60,
    )


def test_downloader_extracts_sorted_selected_sequence(tmp_path: Path) -> None:
    """Relative archive paths resolve below output and preserve neighbors."""
    output_dir = tmp_path / "elope"
    output_dir.mkdir()
    marker = output_dir / "notes.txt"
    marker.write_text("preserve\n", encoding="utf-8")
    archive_path = output_dir / "fixture.zip"
    payload = _elope_npz_bytes()
    with zipfile.ZipFile(archive_path, "w") as archive:
        archive.writestr("test/0002.npz", payload)
        archive.writestr("test/0001.npz", payload)
        archive.writestr("README.txt", "not a sequence")

    completed = _run_script(
        "download_elope_dataset.sh",
        [
            "--output-dir",
            str(output_dir),
            "--zip-path",
            "fixture.zip",
            "--first-only",
        ],
    )

    assert completed.returncode == 0, completed.stderr
    assert (output_dir / "test" / "0001.npz").is_file()
    assert not (output_dir / "test" / "0002.npz").exists()
    assert marker.read_text(encoding="utf-8") == "preserve\n"
    assert "extracted_sequences=1" in completed.stdout


def test_downloader_rejects_archive_traversal(tmp_path: Path) -> None:
    """An unsafe archive member cannot write outside the selected root."""
    output_dir = tmp_path / "elope"
    output_dir.mkdir()
    archive_path = output_dir / "unsafe.zip"
    with zipfile.ZipFile(archive_path, "w") as archive:
        archive.writestr("../escape.npz", _elope_npz_bytes())

    completed = _run_script(
        "download_elope_dataset.sh",
        [
            "--output-dir",
            str(output_dir),
            "--zip-path",
            str(archive_path),
        ],
    )

    assert completed.returncode != 0
    assert "unsafe ELOPE archive member" in completed.stderr
    assert not (tmp_path / "escape.npz").exists()


def test_downloader_rejects_symlinked_target_parent(tmp_path: Path) -> None:
    """Extraction cannot redirect a selected sequence through a parent link."""
    output_dir = tmp_path / "elope"
    output_dir.mkdir()
    external = tmp_path / "external"
    external.mkdir()
    marker = external / "preserve.txt"
    marker.write_text("preserve\n", encoding="utf-8")
    (output_dir / "test").symlink_to(external, target_is_directory=True)
    archive_path = output_dir / "fixture.zip"
    with zipfile.ZipFile(archive_path, "w") as archive:
        archive.writestr("test/0001.npz", _elope_npz_bytes())

    completed = _run_script(
        "download_elope_dataset.sh",
        [
            "--output-dir",
            str(output_dir),
            "--zip-path",
            "fixture.zip",
            "--first-only",
        ],
    )

    assert completed.returncode != 0
    assert "symlinked ELOPE target parent" in completed.stderr
    assert marker.read_text(encoding="utf-8") == "preserve\n"
    assert not (external / "0001.npz").exists()


def test_track_renderer_reports_png_fallback_path(tmp_path: Path,
                                                  monkeypatch: pytest.MonkeyPatch) -> None:
    """The track summary names the artifact published without FFmpeg."""
    input_path = tmp_path / "events.npz"
    input_path.write_bytes(_elope_npz_bytes())
    output_dir = tmp_path / "tracking"
    output_dir.mkdir()
    track_path = output_dir / "tracks.txt"
    track_path.write_text("1 0.0 0.0 0.0\n", encoding="utf-8")
    monkeypatch.setattr(
        "event_vision_utils.viz.video_writer.shutil.which",
        Mock(return_value=None),
    )

    status = render_elope_tracks(
        [
            "--input", str(input_path),
            "--tracks", str(track_path),
            "--output", str(output_dir / "eklt_tracks.mp4"),
        ]
    )

    summary = json.loads(
        (output_dir / "track_video_summary.json").read_text(
            encoding="utf-8"
        )
    )
    assert status == 0
    assert summary["video"]["kind"] == "png_sequence"
    assert summary["video"]["path"] == "eklt_tracks_frames"
    assert (output_dir / "eklt_tracks_frames").is_dir()


def test_pipeline_refuses_symlinked_component(tmp_path: Path) -> None:
    """Pipeline cleanup never follows a component-directory symlink."""
    input_path = tmp_path / "events.npz"
    input_path.write_bytes(_elope_npz_bytes())
    output_dir = tmp_path / "output"
    output_dir.mkdir()
    external = tmp_path / "external"
    external.mkdir()
    marker = external / "preserve.txt"
    marker.write_text("preserve\n", encoding="utf-8")
    (output_dir / "tracking").symlink_to(
        external,
        target_is_directory=True,
    )

    completed = _run_script(
        "run_official_elope_event_only_pipeline_demo.sh",
        [
            "--input",
            str(input_path),
            "--output-dir",
            str(output_dir),
        ],
    )

    assert completed.returncode == 2
    assert "component output directories must not be symlinks" in (
        completed.stderr
    )
    assert marker.read_text(encoding="utf-8") == "preserve\n"


def test_pipeline_refuses_symlinked_tracking_plots(tmp_path: Path) -> None:
    """Pipeline cleanup never follows the tracking plot directory."""
    input_path = tmp_path / "events.npz"
    input_path.write_bytes(_elope_npz_bytes())
    output_dir = tmp_path / "output"
    tracking_dir = output_dir / "tracking"
    tracking_dir.mkdir(parents=True)
    external = tmp_path / "external"
    external.mkdir()
    marker = external / "active_tracks.png"
    marker.write_text("preserve\n", encoding="utf-8")
    (tracking_dir / "plots").symlink_to(
        external,
        target_is_directory=True,
    )

    completed = _run_script(
        "run_official_elope_event_only_pipeline_demo.sh",
        [
            "--input",
            str(input_path),
            "--output-dir",
            str(output_dir),
        ],
    )

    assert completed.returncode != 0
    assert "refusing symlinked plot directory" in completed.stderr
    assert marker.read_text(encoding="utf-8") == "preserve\n"


def test_pipeline_cleanup_prevalidates_all_artifacts(tmp_path: Path) -> None:
    """A later unsafe artifact preserves earlier accepted tracking output."""
    input_path = tmp_path / "events.npz"
    input_path.write_bytes(_elope_npz_bytes())
    tracking_dir = tmp_path / "output" / "tracking"
    tracking_dir.mkdir(parents=True)
    prior_video = tracking_dir / "eklt_tracks.mp4"
    prior_video.write_bytes(b"preserve")
    external = tmp_path / "external.json"
    external.write_text('{"preserve": true}\n', encoding="utf-8")
    (tracking_dir / "track_video_summary.json").symlink_to(external)

    completed = _run_script(
        "run_official_elope_event_only_pipeline_demo.sh",
        [
            "--input",
            str(input_path),
            "--output-dir",
            str(tmp_path / "output"),
        ],
    )

    assert completed.returncode != 0
    assert "symlinked owned artifact" in completed.stderr
    assert prior_video.read_bytes() == b"preserve"
    assert external.read_text(encoding="utf-8") == (
        '{"preserve": true}\n'
    )
