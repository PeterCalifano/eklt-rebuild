"""Verify strict track artifacts and deterministic streamed overlay videos."""

from __future__ import annotations

from pathlib import Path

import numpy as np
from PIL import Image
import pytest

from event_vision_utils import EventArray
from event_vision_utils.io import TrackSample, load_track_samples
from event_vision_utils.viz import write_track_dot_video


def _make_events() -> EventArray:
    """Create a small event timeline with room for one isolated track dot."""
    return EventArray(
        x=[0, 1, 2, 3],
        y=[0, 1, 2, 3],
        p=[1, -1, 1, -1],
        t_us=[0, 10_000, 20_000, 30_000],
        width=8,
        height=8,
    )


def test_load_track_samples_preserves_valid_file_order(tmp_path: Path) -> None:
    """The shared reader is strict and preserves transport artifact order."""
    track_path = tmp_path / "tracks.txt"
    track_path.write_text(
        "# id time_s x y\n"
        "7 0.015 5.0 6.0\n"
        "2 0.005 4.0 5.0\n"
        "7 0.020 8.1 -0.1\n",
        encoding="utf-8",
    )

    samples = load_track_samples(track_path)

    assert [sample.track_id for sample in samples] == [7, 2, 7]
    assert samples[-1].x == 8.1


@pytest.mark.parametrize(
    ("contents", "message"),
    [
        ("3 0.01 1.0\n", "expected id time_s x_px y_px"),
        ("3 nan 1.0 2.0\n", "values must be finite"),
        ("3 -0.01 1.0 2.0\n", "timestamp must be nonnegative"),
        (
            "3 0.02 1.0 2.0\n3 0.01 1.0 2.0\n",
            "per-track timestamp regression",
        ),
    ],
)
def test_load_track_samples_rejects_malformed_rows(tmp_path: Path,
                                                   contents: str,
                                                   message: str) -> None:
    """No malformed track row can disappear from a later summary."""
    track_path = tmp_path / "invalid_tracks.txt"
    track_path.write_text(contents, encoding="utf-8")

    with pytest.raises(ValueError, match=message):
        load_track_samples(track_path)


def test_write_track_dot_video_streams_scaled_png_frames(tmp_path: Path) -> None:
    """A recent observation appears at the expected enlarged pixel location."""
    samples = [
        TrackSample(
            track_id=7,
            t_s=0.005,
            x=5.0,
            y=6.0,
        )
    ]

    result = write_track_dot_video(
        _make_events(),
        samples,
        tmp_path / "track_frames",
        fps=100.0,
        scale=4,
        hold_ms=15.0,
        dot_radius=3,
    )

    assert result.video.kind == "png_sequence"
    assert result.video.frame_count == 4
    assert result.video.width == 32
    assert result.video.height == 32
    assert result.track_count == 1
    assert result.boundary_clipped_track_rows == 0
    assert "frames" not in result.as_dict()

    frame_paths = sorted((tmp_path / "track_frames").glob("frame_*.png"))
    first_frame = np.asarray(Image.open(frame_paths[0]).convert("RGB"))
    assert first_frame[24, 20].tolist() != [255, 255, 255]

    # The bounded hold policy removes the dot by the final frame.
    final_frame = np.asarray(Image.open(frame_paths[-1]).convert("RGB"))
    assert final_frame[24, 20].tolist() == [255, 255, 255]


def test_write_track_dot_video_clips_boundary_excursions(tmp_path: Path) -> None:
    """Finite native subpixel excursions clip only at the display boundary."""
    samples = [
        TrackSample(
            track_id=1,
            t_s=0.01,
            x=8.1,
            y=6.0,
        )
    ]

    result = write_track_dot_video(
        _make_events(),
        samples,
        tmp_path / "track_frames",
        fps=100.0,
        scale=4,
        dot_radius=2,
    )

    assert result.boundary_clipped_track_rows == 1
    frame_path = tmp_path / "track_frames" / "frame_000000.png"
    first_frame = np.asarray(Image.open(frame_path).convert("RGB"))
    assert first_frame[24, 28].tolist() != [255, 255, 255]


def test_write_track_dot_video_rejects_disjoint_timeline(tmp_path: Path) -> None:
    """Tracks from an unrelated clock cannot silently produce a blank video."""
    samples = [
        TrackSample(
            track_id=1,
            t_s=10.0,
            x=4.0,
            y=5.0,
        )
    ]

    with pytest.raises(ValueError, match="timelines do not overlap"):
        write_track_dot_video(
            _make_events(),
            samples,
            tmp_path / "track_frames",
        )


def test_track_video_rejects_unbounded_geometry(tmp_path: Path) -> None:
    """Scaling policy rejects a full-frame allocation above its hard bound."""
    events = EventArray(
        x=[0],
        y=[0],
        p=[1],
        t_us=[0],
        width=5000,
        height=5000,
    )
    samples = [
        TrackSample(
            track_id=1,
            t_s=0.0,
            x=0.0,
            y=0.0,
        )
    ]

    with pytest.raises(ValueError, match="frame pixel limit"):
        write_track_dot_video(
            events,
            samples,
            tmp_path / "track_frames",
        )
