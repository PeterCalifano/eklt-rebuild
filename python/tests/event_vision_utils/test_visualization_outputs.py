"""Verify bounded analytical plots and streamed preview artifacts."""

from __future__ import annotations

import shutil
from pathlib import Path

import matplotlib.pyplot as plt
import numpy as np
from PIL import Image
import pytest

from event_vision_utils import EventArray
import event_vision_utils.viz.video_writer as video_writer
from event_vision_utils.viz import (
    PlotContract,
    compute_event_rate,
    render_event_rate_plot,
    render_event_stream_3d_views,
    write_event_preview,
    write_video_or_png_sequence,
)
from event_vision_utils.viz.event_cloud import (
    EVENT_CLOUD_TITLE,
    _build_event_stream_3d_figure,
)


def make_events() -> EventArray:
    """Return one small signed-polarity event stream for plot tests."""
    return EventArray(
        x=[0, 1, 2, 3],
        y=[0, 1, 2, 3],
        p=[1, -1, 1, -1],
        t_us=[0, 10_000, 20_000, 30_000],
        width=8,
        height=8,
    )


def test_compute_event_rate_bins_counts_and_rates() -> None:
    """Fixed-width event-rate bins preserve counts and physical units."""
    starts, counts, rates_hz = compute_event_rate(
        make_events(),
        bin_us=20_000,
    )

    assert starts.tolist() == [0, 20_000]
    assert counts.tolist() == [2, 2]
    assert counts.dtype == np.int64
    assert rates_hz.tolist() == [100.0, 100.0]


def test_compute_event_rate_handles_full_int64_timestamp_span() -> None:
    """Binning cannot overflow when timestamps cross both int64 extremes."""
    minimum = int(np.iinfo(np.int64).min)
    maximum = int(np.iinfo(np.int64).max)
    events = EventArray(
        x=[0, 0],
        y=[0, 0],
        p=[1, -1],
        t_us=[minimum, maximum],
        width=1,
        height=1,
    )

    starts, counts, rates_hz = compute_event_rate(
        events,
        bin_us=maximum,
        max_bins=3,
    )

    assert starts.tolist() == [
        minimum,
        -1,
        maximum - 1,
    ]
    assert counts.tolist() == [1, 0, 1]
    assert np.all(np.isfinite(rates_hz))


def test_compute_event_rate_rejects_unbounded_bin_count() -> None:
    """A tiny bin over a large duration fails before allocating output."""
    events = EventArray(
        x=[0, 0],
        y=[0, 0],
        p=[1, -1],
        t_us=[0, 1_000_000],
        width=1,
        height=1,
    )

    with pytest.raises(ValueError, match="exceeding max_bins"):
        compute_event_rate(
            events,
            bin_us=1,
            max_bins=100,
        )


def test_render_event_rate_plot_writes_labeled_png(tmp_path: Path) -> None:
    """The event-rate chart includes title, annotation, and unit scales."""
    output = render_event_rate_plot(
        make_events(),
        tmp_path / "event_rate.png",
        bin_us=20_000,
    )

    with Image.open(output) as image:
        assert image.size == (800, 420)


def test_render_event_rate_plot_keeps_scales_for_empty_stream(tmp_path: Path) -> None:
    """Empty event data retain the same titled and labeled chart frame."""
    events = EventArray(
        x=[],
        y=[],
        p=[],
        t_us=[],
        width=8,
        height=8,
    )

    output = render_event_rate_plot(
        events,
        tmp_path / "empty_event_rate.png",
        bin_us=20_000,
    )

    with Image.open(output) as image:
        assert image.size == (800, 420)
        assert image.getbbox() is not None


def test_render_event_rate_plot_refuses_symlinked_temporary(tmp_path: Path) -> None:
    """Atomic plot publication never follows a planted temporary symlink."""
    external = tmp_path / "external.png"
    external.write_bytes(b"preserve")
    (tmp_path / ".event_rate.tmp.png").symlink_to(external)

    with pytest.raises(ValueError, match="symlinked temporary output"):
        render_event_rate_plot(
            make_events(),
            tmp_path / "event_rate.png",
            bin_us=20_000,
        )
    assert external.read_bytes() == b"preserve"


def test_plot_contract_rejects_lowercase_or_unitless_labels() -> None:
    """Plot metadata rejects missing capitalization, units, and scales."""
    with pytest.raises(ValueError, match="title must start"):
        PlotContract(
            title="event rate",
            subtitle="Fixed-width event bins.",
            x_label="Time [s]",
            y_label="Event Rate [events/s]",
        )
    with pytest.raises(ValueError, match="horizontal axis label"):
        PlotContract(
            title="Event Rate",
            subtitle="Fixed-width event bins.",
            x_label="Time",
            y_label="Event Rate [events/s]",
        )


def test_write_event_preview_writes_bounded_png_summary(tmp_path: Path) -> None:
    """PNG fallback metadata remains constant-size as frame count grows."""
    result = write_event_preview(
        make_events(),
        tmp_path / "frames",
        dt_ms=20.0,
    )

    assert result.kind == "png_sequence"
    assert result.frame_count == 2
    assert "frames" not in result.as_dict()
    frame_paths = sorted((tmp_path / "frames").glob("frame_*.png"))
    assert len(frame_paths) == 2
    assert all(Image.open(path).size == (8, 8) for path in frame_paths)


def test_png_sequence_replaces_only_owned_frames(tmp_path: Path) -> None:
    """A shorter rerun removes stale numbered frames and preserves neighbors."""
    output_dir = tmp_path / "frames"
    write_video_or_png_sequence(
        (
            np.full((2, 2), index, dtype=np.uint8)
            for index in range(4)
        ),
        output_dir,
    )
    unrelated = output_dir / "notes.txt"
    unrelated.write_text("preserve\n", encoding="utf-8")

    result = write_video_or_png_sequence(
        (
            np.full((2, 2), index, dtype=np.uint8)
            for index in range(2)
        ),
        output_dir,
    )

    assert result.frame_count == 2
    assert len(list(output_dir.glob("frame_*.png"))) == 2
    assert unrelated.read_text(encoding="utf-8") == "preserve\n"


def test_png_sequence_preserves_previous_frames_when_rerun_fails(tmp_path: Path) -> None:
    """A failed replacement leaves the complete prior sequence readable."""
    output_dir = tmp_path / "frames"
    write_video_or_png_sequence(
        [
            np.full((2, 2), 10, dtype=np.uint8),
            np.full((2, 2), 20, dtype=np.uint8),
        ],
        output_dir,
    )

    with pytest.raises(ValueError, match="same shape"):
        write_video_or_png_sequence(
            [
                np.full((2, 2), 30, dtype=np.uint8),
                np.full((3, 2), 40, dtype=np.uint8),
            ],
            output_dir,
        )

    frame_paths = sorted(output_dir.glob("frame_*.png"))
    assert len(frame_paths) == 2
    assert np.asarray(Image.open(frame_paths[0]))[0, 0] == 10
    assert np.asarray(Image.open(frame_paths[1]))[0, 0] == 20
    assert not list(output_dir.glob(".frame_*.stage.png"))


def test_png_sequence_rejects_unbounded_frame_count(tmp_path: Path,
                                                    monkeypatch: pytest.MonkeyPatch) -> None:
    """The six-digit sequence contract rejects excess frames before commit."""
    output_dir = tmp_path / "frames"
    write_video_or_png_sequence(
        [np.full((2, 2), 10, dtype=np.uint8)],
        output_dir,
    )
    monkeypatch.setattr(video_writer, "_MAX_ENCODED_FRAMES", 2)

    with pytest.raises(ValueError, match="frame count"):
        write_video_or_png_sequence(
            (
                np.full((2, 2), index, dtype=np.uint8)
                for index in range(3)
            ),
            output_dir,
        )

    frame_paths = sorted(output_dir.glob("frame_*.png"))
    assert len(frame_paths) == 1
    assert np.asarray(Image.open(frame_paths[0]))[0, 0] == 10
    assert not list(output_dir.glob(".frame_*.stage.png"))


def test_single_png_rejects_additional_frames(tmp_path: Path) -> None:
    """A single-image path cannot silently discard later iterable frames."""
    with pytest.raises(ValueError, match="exactly one frame"):
        write_video_or_png_sequence(
            [
                np.zeros((2, 2), dtype=np.uint8),
                np.ones((2, 2), dtype=np.uint8),
            ],
            tmp_path / "single.png",
        )


def test_event_preview_rejects_unbounded_sensor_geometry(tmp_path: Path) -> None:
    """A sparse event cannot trigger an unbounded full-frame allocation."""
    events = EventArray(
        x=[0],
        y=[0],
        p=[1],
        t_us=[0],
        width=5000,
        height=5000,
    )

    with pytest.raises(ValueError, match="pixel limit"):
        write_event_preview(
            events,
            tmp_path / "frames",
            dt_ms=10.0,
        )


def test_rejects_unbounded_frame_before_conversion(tmp_path: Path) -> None:
    """A broadcast float view is rejected before conversion copies its pixels."""
    frame = np.broadcast_to(
        np.zeros((1, 1), dtype=np.float32),
        (4097, 4097),
    )

    with pytest.raises(ValueError, match="pixel limit"):
        write_video_or_png_sequence(
            [frame],
            tmp_path / "frame.png",
        )


def test_invalid_channel_layout_fails_before_conversion(tmp_path: Path,
                                                        monkeypatch: pytest.MonkeyPatch) -> None:
    """Unsupported channels fail before clipping can allocate a copy."""
    frame = np.zeros((2, 2, 5), dtype=np.float32)

    def fail_if_called(*args: object, **kwargs: object) -> np.ndarray:
        """Expose any conversion attempted before shape validation."""
        del args, kwargs
        raise AssertionError("np.clip must not be called")

    monkeypatch.setattr(video_writer.np, "clip", fail_if_called)
    with pytest.raises(ValueError, match="HxWx3/HxWx4"):
        write_video_or_png_sequence(
            [frame],
            tmp_path / "frame.png",
        )


def test_png_sequence_refuses_symlinked_owned_frame(tmp_path: Path) -> None:
    """Owned cleanup never follows a numbered-frame symlink."""
    output_dir = tmp_path / "frames"
    output_dir.mkdir()
    external = tmp_path / "external.png"
    external.write_bytes(b"preserve")
    (output_dir / "frame_000000.png").symlink_to(external)

    with pytest.raises(ValueError, match="symlinked sequence frame"):
        write_video_or_png_sequence(
            [np.zeros((2, 2), dtype=np.uint8)],
            output_dir,
        )
    assert external.read_bytes() == b"preserve"
    assert not list(output_dir.glob(".frame_*.stage.png"))


def test_mp4_rejects_directory_target_before_encoding(tmp_path: Path) -> None:
    """A directory cannot be replaced by an encoded MP4 temporary."""
    if shutil.which("ffmpeg") is None:
        pytest.skip("ffmpeg is unavailable")
    output = tmp_path / "preview.mp4"
    output.mkdir()

    with pytest.raises(ValueError, match="not a regular file"):
        write_video_or_png_sequence(
            [np.zeros((2, 2), dtype=np.uint8)],
            output,
        )
    assert not (tmp_path / ".preview.tmp.mp4").exists()


def test_write_event_preview_writes_mp4_when_encoder_available(tmp_path: Path) -> None:
    """MP4 output records frame geometry and rate when ffmpeg is present."""
    if shutil.which("ffmpeg") is None:
        pytest.skip("ffmpeg is unavailable")

    result = write_event_preview(
        make_events(),
        tmp_path / "preview.mp4",
        dt_ms=20.0,
    )

    assert result.kind == "mp4"
    assert result.frame_count == 2
    assert result.width == 8
    assert result.height == 8
    assert result.fps == 30.0
    assert (tmp_path / "preview.mp4").stat().st_size > 0


def test_render_event_stream_3d_views_writes_six_view_figure(tmp_path: Path) -> None:
    """The event cloud writes one landscape six-view artifact."""
    output_path = render_event_stream_3d_views(
        make_events(),
        tmp_path / "event_stream_3d_views.png",
        max_points=3,
    )

    with Image.open(output_path) as image:
        assert image.width > image.height


def test_event_stream_3d_views_rejects_unbounded_display_count() -> None:
    """Display sampling has an explicit upper bound before allocation."""
    with pytest.raises(ValueError, match="max_points must be in"):
        _build_event_stream_3d_figure(
            make_events(),
            max_points=1_000_001,
        )


def test_event_stream_3d_views_expose_labels_and_polarity() -> None:
    """Each projection declares its view, scales, units, and marker meaning."""
    figure = _build_event_stream_3d_figure(
        make_events(),
        max_points=3,
    )
    try:
        assert figure._suptitle is not None
        assert figure._suptitle.get_text() == EVENT_CLOUD_TITLE
        assert len(figure.axes) == 6
        for axis in figure.axes:
            assert axis.texts[0].get_text().startswith("View along ")
            visible_labels = [
                label
                for label in (
                    axis.get_xlabel(),
                    axis.get_ylabel(),
                    axis.get_zlabel(),
                )
                if label
            ]
            assert len(visible_labels) == 2
            assert all(label[0].isupper() for label in visible_labels)
            assert all(label.endswith("]") for label in visible_labels)

        legend = figure.legends[0]
        assert [
            text.get_text()
            for text in legend.get_texts()
        ] == [
            "Positive Polarity (+1)",
            "Negative Polarity (−1)",
        ]
    finally:
        plt.close(figure)
