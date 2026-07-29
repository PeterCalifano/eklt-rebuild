"""Verify strict output evaluation and track-analysis artifact generation."""

from __future__ import annotations

import importlib.util
import json
import sys
from pathlib import Path
from types import ModuleType

import matplotlib.pyplot as plt
import numpy as np
from PIL import Image
import pytest


def load_script(module_name: str, relative_path: str) -> ModuleType:
    """Load one repository script without requiring console installation."""
    repo_root = Path(__file__).resolve().parents[3]
    script_path = repo_root / relative_path
    spec = importlib.util.spec_from_file_location(
        module_name,
        script_path,
    )
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    sys.modules[module_name] = module
    spec.loader.exec_module(module)
    return module


def load_evaluator() -> ModuleType:
    """Load the artifact evaluator."""
    return load_script(
        "evaluate_outputs",
        "scripts/evaluate_outputs.py",
    )


def load_summarizer() -> ModuleType:
    """Load the track summarizer."""
    return load_script(
        "summarize_eklt_tracks",
        "scripts/summarize_eklt_tracks.py",
    )


def write_png(path: Path) -> None:
    """Write one small decodable PNG fixture."""
    path.parent.mkdir(parents=True, exist_ok=True)
    Image.new("RGB", (4, 3), "white").save(path)


def write_run(root: Path,
              *,
              gt_status: str = "unavailable",
              track_rows: int = 1) -> None:
    """Write one minimal accepted output directory."""
    plot_names = [
        "active_tracks.png",
        "track_lifetimes.png",
        "reinit_timeline.png",
        "track_xy.png",
        "event_rate.png",
    ]
    for name in plot_names:
        write_png(root / "plots" / name)
    (root / "tracks.txt").write_text(
        "1 0.0 2.0 3.0\n" if track_rows else "",
        encoding="utf-8",
    )
    summary = {
        "schema_version": 1,
        "artifact_type": "eklt_track_analysis",
        "run_name": "example",
        "status": "passed",
        "input": "input",
        "event_count": 4,
        "track_count": track_rows,
        "track_rows": track_rows,
        "tracks_file": "tracks.txt",
        "duration_s": 0.1,
        "runtime_s": 0.01,
        "plots": [
            f"plots/{name}"
            for name in plot_names
        ],
        "plot_contracts": {
            name: {
                "title": "Example Plot",
                "subtitle": "Synthetic evaluator fixture.",
                "x_label": "Sample [index]",
                "y_label": "Value [unitless]",
            }
            for name in plot_names
        },
        "gt_status": gt_status,
        "gt_metrics": {},
    }
    if gt_status == "available":
        write_png(root / "plots" / "gt_error.png")
        summary["plots"].append("plots/gt_error.png")
        summary["plot_contracts"]["gt_error.png"] = {
            "title": "Example Ground-Truth Error",
            "subtitle": "Synthetic evaluator fixture.",
            "x_label": "Matched Row [row index]",
            "y_label": "Position Error [px]",
        }
        summary["gt_metrics"] = {
            "matched_rows": 1,
            "rmse_px": 1.0,
        }
    (root / "summary.json").write_text(
        json.dumps(summary),
        encoding="utf-8",
    )


def write_elope_fixture(path: Path) -> None:
    """Write one strict ELOPE archive for summarizer integration."""
    np.savez(
        path,
        events=np.array(
            [
                [0, 0, 1, 0],
                [1, 1, -1, 10_000],
                [2, 2, 1, 20_000],
            ]
        ),
        timestamps=np.array([0.0, 0.02]),
        traj=np.zeros((2, 12), dtype=np.float64),
        range_meter=np.array(
            [[0.0, 100.0], [0.02, 99.0]],
            dtype=np.float64,
        ),
    )


def write_track_video_summary(root: Path) -> Path:
    """Write one valid PNG-sequence track-video artifact fixture."""
    (root / "tracks.txt").write_text(
        "1 0.0 2.0 2.0\n",
        encoding="utf-8",
    )
    write_png(root / "track_frames" / "frame_000000.png")
    summary_path = root / "track_video_summary.json"
    summary_path.write_text(
        json.dumps(
            {
                "schema_version": 1,
                "artifact_type": "eklt_track_video",
                "status": "passed",
                "input": "events.npz",
                "tracks": "tracks.txt",
                "dataset_adapter": "elope",
                "dataset_metadata": {},
                "video": {
                    "kind": "png_sequence",
                    "path": "track_frames",
                    "frame_count": 1,
                    "width": 4,
                    "height": 3,
                    "fps": 100.0,
                    "track_rows": 1,
                    "track_count": 1,
                    "boundary_clipped_track_rows": 0,
                    "event_window_us": 10_000,
                    "track_hold_ms": 100.0,
                    "dot_radius": 5,
                    "scale": 1,
                },
            }
        ),
        encoding="utf-8",
    )
    return summary_path


def write_reconstruction_run(root: Path) -> None:
    """Write one complete PNG-sequence reconstruction fixture."""
    plot_names = [
        "event_rate.png",
        "event_stream_3d_views.png",
        "patch_quality.png",
    ]
    for name in plot_names:
        write_png(root / "plots" / name)
    for directory in ("preview_frames", "reconstruction_frames", "patch_frames"):
        write_png(root / directory / "frame_000000.png")

    video = {
        "kind": "png_sequence",
        "frame_count": 1,
        "width": 4,
        "height": 3,
        "fps": 100.0,
    }
    summary = {
        "schema_version": 1,
        "artifact_type": "elope_fibar_reconstruction",
        "run_name": "elope_reconstruction",
        "status": "passed",
        "input": "events.npz",
        "event_count": 2,
        "track_count": 0,
        "track_rows": 0,
        "duration_s": 0.01,
        "runtime_s": 0.02,
        "dataset_adapter": "elope",
        "dataset_metadata": {},
        "plots": [f"plots/{name}" for name in plot_names],
        "plot_contracts": {
            name: {
                "title": "Example Plot",
                "subtitle": "Synthetic evaluator fixture.",
                "x_label": "Sample [index]",
                "y_label": "Value [unitless]",
            }
            for name in plot_names
        },
        "preview": {**video, "path": "preview_frames"},
        "reconstruction": {**video, "path": "reconstruction_frames"},
        "patch_debug": {**video, "path": "patch_frames"},
        "preview_fps": 100.0,
        "preview_dt_ms": 10.0,
        "reconstruction_frames": 1,
        "patch_debug_frames": 1,
        "patch_quality_count": 2,
        "patch_quality_samples": 1,
        "patch_quality_truncated": True,
        "patch_layout": {
            "event_panel_size": 3,
            "mosaic_columns": 2,
            "max_candidates": 8,
        },
        "gt_status": "unavailable",
        "gt_metrics": {},
    }
    (root / "summary.json").write_text(
        json.dumps(summary),
        encoding="utf-8",
    )


def test_evaluate_outputs_accepts_complete_run(tmp_path: Path) -> None:
    """A complete synthetic run satisfies the artifact evaluator."""
    evaluator = load_evaluator()
    write_run(tmp_path)

    result = evaluator.evaluate_run(tmp_path)

    assert result.passed
    assert result.errors == []


def test_evaluator_accepts_complete_reconstruction(tmp_path: Path) -> None:
    """A complete reconstruction schema satisfies the artifact evaluator."""
    evaluator = load_evaluator()
    write_reconstruction_run(tmp_path)

    result = evaluator.evaluate_run(tmp_path, require_tracks=False)

    assert result.passed
    assert result.errors == []


def test_evaluator_rejects_inconsistent_patch_counts(tmp_path: Path) -> None:
    """Patch retention metadata must describe the bounded sample exactly."""
    evaluator = load_evaluator()
    write_reconstruction_run(tmp_path)
    summary_path = tmp_path / "summary.json"
    summary = json.loads(summary_path.read_text(encoding="utf-8"))
    summary["patch_quality_samples"] = 3
    summary_path.write_text(json.dumps(summary), encoding="utf-8")

    result = evaluator.evaluate_run(tmp_path, require_tracks=False)

    assert not result.passed
    assert any(
        "patch_quality_samples exceeds" in error
        for error in result.errors
    )


def test_evaluator_rejects_boolean_schema_version(tmp_path: Path) -> None:
    """Boolean equality with one cannot satisfy the integer schema contract."""
    evaluator = load_evaluator()
    write_reconstruction_run(tmp_path)
    summary_path = tmp_path / "summary.json"
    summary = json.loads(summary_path.read_text(encoding="utf-8"))
    summary["schema_version"] = True
    summary_path.write_text(json.dumps(summary), encoding="utf-8")

    result = evaluator.evaluate_run(tmp_path, require_tracks=False)

    assert not result.passed
    assert "schema_version must equal 1" in result.errors


def test_track_video_accepts_exact_png_sequence(tmp_path: Path) -> None:
    """The video reader verifies frames, geometry, and track counts."""
    evaluator = load_evaluator()
    summary_path = write_track_video_summary(tmp_path)

    result = evaluator.evaluate_track_video(summary_path)

    assert result.passed
    assert result.errors == []


def test_track_video_rejects_frame_mismatch(tmp_path: Path) -> None:
    """Video metadata cannot claim frames absent from the artifact."""
    evaluator = load_evaluator()
    summary_path = write_track_video_summary(tmp_path)
    summary = json.loads(summary_path.read_text(encoding="utf-8"))
    summary["video"]["frame_count"] = 2
    summary_path.write_text(json.dumps(summary), encoding="utf-8")

    result = evaluator.evaluate_track_video(summary_path)

    assert not result.passed
    assert any(
        "frame count" in error
        for error in result.errors
    )


def test_track_video_rejects_noncanonical_frame_name(tmp_path: Path) -> None:
    """A frame-like file outside the six-digit contract is not ignored."""
    evaluator = load_evaluator()
    summary_path = write_track_video_summary(tmp_path)
    write_png(tmp_path / "track_frames" / "frame_1000000.png")

    result = evaluator.evaluate_track_video(summary_path)

    assert not result.passed
    assert any(
        "invalid frame names" in error
        for error in result.errors
    )


def test_track_video_rejects_invalid_render_policy(tmp_path: Path) -> None:
    """Track video policy metadata must match the encoded frame rate."""
    evaluator = load_evaluator()
    summary_path = write_track_video_summary(tmp_path)
    summary = json.loads(summary_path.read_text(encoding="utf-8"))
    summary["video"]["event_window_us"] = 20_000
    summary["video"]["scale"] = 0
    summary_path.write_text(json.dumps(summary), encoding="utf-8")

    result = evaluator.evaluate_track_video(summary_path)

    assert not result.passed
    assert any("event_window_us" in error for error in result.errors)
    assert any("video.scale" in error for error in result.errors)


def test_track_video_rejects_inexact_clip_count(tmp_path: Path) -> None:
    """Boundary-clipping metadata must match the strict track artifact."""
    evaluator = load_evaluator()
    summary_path = write_track_video_summary(tmp_path)
    summary = json.loads(summary_path.read_text(encoding="utf-8"))
    summary["video"]["boundary_clipped_track_rows"] = 1
    summary_path.write_text(json.dumps(summary), encoding="utf-8")

    result = evaluator.evaluate_track_video(summary_path)

    assert not result.passed
    assert any(
        "boundary_clipped_track_rows does not match" in error
        for error in result.errors
    )


def test_track_video_rejects_unbounded_artifact_metadata(tmp_path: Path) -> None:
    """Declared video dimensions and frame counts retain their hard bounds."""
    evaluator = load_evaluator()
    summary_path = write_track_video_summary(tmp_path)
    summary = json.loads(summary_path.read_text(encoding="utf-8"))
    summary["video"]["frame_count"] = 1_000_001
    summary["video"]["width"] = 5000
    summary["video"]["height"] = 5000
    summary_path.write_text(json.dumps(summary), encoding="utf-8")

    result = evaluator.evaluate_track_video(summary_path)

    assert not result.passed
    assert any("frame_count exceeds" in error for error in result.errors)
    assert any("frame geometry exceeds" in error for error in result.errors)


def test_evaluator_requires_exact_track_counts(tmp_path: Path) -> None:
    """Declared track counts must match the strict artifact reader."""
    evaluator = load_evaluator()
    write_run(tmp_path)
    summary_path = tmp_path / "summary.json"
    summary = json.loads(summary_path.read_text(encoding="utf-8"))
    summary["track_rows"] = 2
    summary_path.write_text(
        json.dumps(summary),
        encoding="utf-8",
    )

    result = evaluator.evaluate_run(tmp_path)

    assert not result.passed
    assert any(
        "track_rows does not match" in error
        for error in result.errors
    )


def test_evaluator_rejects_malformed_track_row(tmp_path: Path) -> None:
    """A malformed row cannot pass because other rows are valid."""
    evaluator = load_evaluator()
    write_run(tmp_path)
    (tmp_path / "tracks.txt").write_text(
        "1 0.0 2.0 3.0\nmalformed\n",
        encoding="utf-8",
    )

    result = evaluator.evaluate_run(tmp_path)

    assert not result.passed
    assert any(
        "invalid tracks file" in error
        for error in result.errors
    )


def test_evaluator_rejects_escaping_artifact_path(tmp_path: Path) -> None:
    """Manifest paths cannot read artifacts outside the run directory."""
    evaluator = load_evaluator()
    write_run(tmp_path)
    summary_path = tmp_path / "summary.json"
    summary = json.loads(summary_path.read_text(encoding="utf-8"))
    summary["plots"][0] = "../outside.png"
    summary_path.write_text(
        json.dumps(summary),
        encoding="utf-8",
    )

    result = evaluator.evaluate_run(tmp_path)

    assert not result.passed
    assert any(
        "escapes the run directory" in error
        for error in result.errors
    )


def test_evaluate_outputs_rejects_invalid_png(tmp_path: Path) -> None:
    """A nonempty file is not accepted merely because it uses a PNG suffix."""
    evaluator = load_evaluator()
    write_run(tmp_path)
    (tmp_path / "plots" / "active_tracks.png").write_bytes(b"not a png")

    result = evaluator.evaluate_run(tmp_path)

    assert not result.passed
    assert any(
        "invalid PNG artifact" in error
        for error in result.errors
    )


def test_evaluator_rejects_missing_plot_labels(tmp_path: Path) -> None:
    """A decoded PNG cannot pass without its visible label contract."""
    evaluator = load_evaluator()
    write_run(tmp_path)
    summary_path = tmp_path / "summary.json"
    summary = json.loads(summary_path.read_text(encoding="utf-8"))
    del summary["plot_contracts"]["active_tracks.png"]
    summary_path.write_text(
        json.dumps(summary),
        encoding="utf-8",
    )

    result = evaluator.evaluate_run(tmp_path)

    assert not result.passed
    assert any(
        "missing plot label contract: active_tracks.png" in error
        for error in result.errors
    )


def test_evaluator_requires_available_gt_metrics(tmp_path: Path) -> None:
    """Available ground truth requires nonempty metrics and its error plot."""
    evaluator = load_evaluator()
    write_run(tmp_path, gt_status="available")

    result = evaluator.evaluate_run(tmp_path)

    assert result.passed


def test_evaluator_rejects_hidden_ground_truth(tmp_path: Path) -> None:
    """A discovered ground-truth file cannot be marked unavailable."""
    evaluator = load_evaluator()
    write_run(tmp_path)
    (tmp_path / "ground_truth.txt").write_text(
        "0 0.0 0.0 0.0\n",
        encoding="utf-8",
    )

    result = evaluator.evaluate_run(tmp_path)

    assert not result.passed
    assert any(
        "ground truth files exist" in error
        for error in result.errors
    )


def test_empty_tracks_keep_plot_contracts(tmp_path: Path) -> None:
    """Empty track data retain labeled axes while the analysis fails."""
    summarizer = load_summarizer()
    tracks = tmp_path / "tracks.txt"
    tracks.touch()

    status = summarizer.main(
        [
            "--tracks",
            str(tracks),
            "--output-dir",
            str(tmp_path),
            "--run-name",
            "empty_fixture",
            "--input",
            "unit_fixture",
            "--event-width",
            "10",
            "--event-height",
            "10",
        ]
    )

    assert status == 1
    summary = json.loads(
        (tmp_path / "summary.json").read_text(encoding="utf-8")
    )
    assert summary["analysis_status"] == "failed"
    assert set(summary["plot_contracts"]) == {
        "active_tracks.png",
        "reinit_timeline.png",
        "track_lifetimes.png",
        "track_xy.png",
    }
    assert all(
        (tmp_path / "plots" / name).stat().st_size > 0
        for name in summary["plot_contracts"]
    )


def test_summarizer_extends_native_summary(tmp_path: Path) -> None:
    """Track analysis extends rather than discards Stage 14 timing evidence."""
    summarizer = load_summarizer()
    evaluator = load_evaluator()
    tracks = tmp_path / "tracks.txt"
    tracks.write_text(
        "1 0.0 2.0 3.0\n"
        "1 0.1 2.5 3.5\n"
        "2 0.2 5.0 6.0\n",
        encoding="utf-8",
    )
    base_summary = tmp_path / "native_summary.json"
    timing_csv = tmp_path / "processing_timing.csv"
    timing_csv.write_text(
        "packet_index,event_time_s,fibar_ms,eklt_ms,overhead_ms,total_ms\n"
        "1,0.0,1.0,2.0,0.5,3.5\n"
        "2,0.1,1.1,2.1,0.6,3.8\n"
        "3,0.2,1.2,2.2,0.7,4.1\n",
        encoding="utf-8",
    )
    timing_plot = tmp_path / "plots" / "processing_time_cumulative.png"
    write_png(timing_plot)
    base_summary.write_text(
        json.dumps(
            {
                "status": "passed",
                "runtime_s": 7.5,
                "processing_timing": {
                    "status": "passed",
                    "input_csv": str(timing_csv),
                    "output_plot": str(timing_plot),
                    "sample_count": 3,
                    "plotted_sample_count": 3,
                    "plot": {
                        "title": "EventPacket Processing Time by Component",
                        "subtitle": "Accepted packets on the ELOPE timeline.",
                        "x_label": "Time Since First Packet [s]",
                        "y_label": "Processing Time per Packet [ms]",
                    },
                },
            }
        ),
        encoding="utf-8",
    )

    status = summarizer.main(
        [
            "--tracks",
            str(tracks),
            "--output-dir",
            str(tmp_path),
            "--run-name",
            "unit_demo",
            "--input",
            "unit_fixture",
            "--base-summary",
            str(base_summary),
            "--event-width",
            "10",
            "--event-height",
            "10",
        ]
    )

    assert status == 0
    result = evaluator.evaluate_run(tmp_path)
    assert result.passed
    summary = json.loads(
        (tmp_path / "summary.json").read_text(encoding="utf-8")
    )
    assert summary["processing_timing"]["sample_count"] == 3
    assert (
        summary["processing_timing"]["output_plot"] ==
        "plots/processing_time_cumulative.png"
    )
    assert (
        "plots/processing_time_cumulative.png" in summary["plots"]
    )
    assert summary["runtime_s"] == 7.5
    assert summary["analysis_runtime_s"] >= 0.0
    assert summary["track_rows"] == 3
    assert summary["track_count"] == 2
    assert summary["image_geometry_source"] == "explicit_override"

    timing_csv.write_text(
        "packet_index,event_time_s,fibar_ms,eklt_ms,overhead_ms,total_ms\n"
        "1,0.0,1.0,2.0,0.5,3.5\n",
        encoding="utf-8",
    )
    invalid_result = evaluator.evaluate_run(tmp_path)
    assert not invalid_result.passed
    assert (
        "processing_timing CSV has 1 rows, declared 3" in
        invalid_result.errors
    )


def test_summarizer_uses_elope_rate_plot(tmp_path: Path) -> None:
    """ELOPE analysis uses advertised dataset geometry and shared event plots."""
    summarizer = load_summarizer()
    tracks = tmp_path / "tracks.txt"
    tracks.write_text(
        "1 0.0 0.0 0.0\n"
        "1 0.01 1.0 1.0\n",
        encoding="utf-8",
    )
    event_path = tmp_path / "events.npz"
    write_elope_fixture(event_path)

    assert summarizer.main(
        [
            "--tracks",
            str(tracks),
            "--output-dir",
            str(tmp_path),
            "--run-name",
            "elope_fixture",
            "--input",
            str(event_path),
            "--event-npz",
            str(event_path),
            "--event-width",
            "8",
            "--event-height",
            "8",
        ]
    ) == 0

    summary = json.loads(
        (tmp_path / "summary.json").read_text(encoding="utf-8")
    )
    assert summary["event_count"] == 3
    assert summary["source_event_count"] == 3
    assert summary["event_rate_source"] == "elope_npz"
    assert "plots/event_rate.png" in summary["plots"]
    assert summary["plot_contracts"]["event_rate.png"][
        "y_label"
    ] == "Event Rate [events/s]"


def test_summarizer_uses_track_ground_truth(tmp_path: Path) -> None:
    """Matched ground truth adds pixel-error metrics and labels."""
    summarizer = load_summarizer()
    evaluator = load_evaluator()
    tracks = tmp_path / "tracks.txt"
    tracks.write_text(
        "1 0.00 2.0 3.0\n"
        "1 0.01 4.0 3.0\n"
        "2 0.02 8.0 9.0\n",
        encoding="utf-8",
    )
    ground_truth = tmp_path / "reference.txt"
    ground_truth.write_text(
        "1 0.00 1.0 3.0\n"
        "1 0.01 4.0 1.0\n"
        "2 0.02 8.0 12.0\n",
        encoding="utf-8",
    )

    status = summarizer.main(
        [
            "--tracks",
            str(tracks),
            "--output-dir",
            str(tmp_path),
            "--run-name",
            "unit_demo_gt",
            "--input",
            "unit_fixture",
            "--ground-truth",
            str(ground_truth),
            "--event-width",
            "16",
            "--event-height",
            "16",
        ]
    )

    assert status == 0
    result = evaluator.evaluate_run(tmp_path)
    assert result.passed
    summary = json.loads(
        (tmp_path / "summary.json").read_text(encoding="utf-8")
    )
    assert summary["gt_status"] == "available"
    assert summary["gt_metrics"]["matched_rows"] == 3
    assert summary["gt_metrics"]["rmse_px"] > 0.0
    assert "plots/gt_error.png" in summary["plots"]


def test_track_axis_uses_fixed_full_image_plane() -> None:
    """Track coordinates use zero-origin sensor limits and downward Y."""
    summarizer = load_summarizer()
    figure, axis = plt.subplots()
    try:
        summarizer._configure_track_axis(axis, 240, 180)

        assert axis.get_xlim() == pytest.approx((0.0, 239.0))
        assert axis.get_ylim() == pytest.approx((179.0, 0.0))
    finally:
        plt.close(figure)


def test_shared_track_plot_separates_title_and_subtitle() -> None:
    """The shared layout keeps its reader-facing headings disjoint."""
    summarizer = load_summarizer()
    contract = summarizer.TRACK_PLOT_CONTRACTS["track_xy.png"]
    figure, axis = summarizer._new_plot(contract)
    try:
        figure.canvas.draw()
        renderer = figure.canvas.get_renderer()
        title_candidates = (
            text
            for text in figure.texts
            if text.get_text() == contract.title
        )
        title = next(title_candidates)

        title_bounds = title.get_window_extent(renderer=renderer)
        subtitle_bounds = axis.title.get_window_extent(renderer=renderer)

        assert title_bounds.y0 > subtitle_bounds.y1
    finally:
        plt.close(figure)


def test_image_geometry_prefers_advertised_dimensions() -> None:
    """Advertised source geometry is authoritative for the image plane."""
    summarizer = load_summarizer()
    event_rate = summarizer.EventRate(
        event_count=2,
        duration_s=0.1,
        bin_counts=(2,),
        bin_us=100_000,
        source="fixture",
        image_width=240,
        image_height=180,
        geometry_source="ros_event_message",
    )

    geometry = summarizer._resolve_image_geometry(
        event_rate,
        None,
        None,
    )

    assert geometry == (240, 180, "ros_event_message")


def test_summarizer_honors_stage14_event_limit(tmp_path: Path) -> None:
    """Analysis covers exactly the EventPackets represented by Stage 14."""
    summarizer = load_summarizer()
    tracks = tmp_path / "tracks.txt"
    tracks.write_text(
        "1 0.0 0.0 0.0\n"
        "1 0.01 1.0 1.0\n",
        encoding="utf-8",
    )
    event_path = tmp_path / "events.npz"
    write_elope_fixture(event_path)
    base_summary = tmp_path / "native_summary.json"
    base_summary.write_text(
        json.dumps(
            {
                "status": "passed",
                "elope_conversion": {
                    "event_count": 2,
                },
            }
        ),
        encoding="utf-8",
    )

    assert summarizer.main(
        [
            "--tracks",
            str(tracks),
            "--output-dir",
            str(tmp_path),
            "--run-name",
            "bounded_fixture",
            "--input",
            str(event_path),
            "--event-npz",
            str(event_path),
            "--base-summary",
            str(base_summary),
            "--event-width",
            "8",
            "--event-height",
            "8",
        ]
    ) == 0

    summary = json.loads(
        (tmp_path / "summary.json").read_text(encoding="utf-8")
    )
    assert summary["event_count"] == 2
    assert summary["source_event_count"] == 3
    assert summary["duration_s"] == pytest.approx(0.01)
    assert summary["event_rate_source"] == "elope_npz_first_2_events"


def test_active_track_series_uses_lifetimes_not_update_density() -> None:
    """A sparsely updated live track remains active between observations."""
    summarizer = load_summarizer()
    by_id = {
        1: [
            summarizer.TrackSample(1, 0.0, 1.0, 1.0),
            summarizer.TrackSample(1, 1.0, 2.0, 2.0),
        ],
        2: [
            summarizer.TrackSample(2, 0.5, 3.0, 3.0),
            summarizer.TrackSample(2, 0.6, 4.0, 4.0),
        ],
    }

    _, active_counts, duration_s = summarizer._active_track_series(by_id)

    assert duration_s == 1.0
    assert active_counts.max() == 2
    assert active_counts[0] == 1
    assert active_counts[-1] == 1


def test_active_track_series_includes_final_instant_track() -> None:
    """A feature first observed at the run endpoint appears in the last bin."""
    summarizer = load_summarizer()
    by_id = {
        1: [
            summarizer.TrackSample(1, 0.0, 1.0, 1.0),
            summarizer.TrackSample(1, 1.0, 2.0, 2.0),
        ],
        2: [
            summarizer.TrackSample(2, 1.0, 3.0, 3.0),
        ],
    }

    _, active_counts, _ = summarizer._active_track_series(by_id)

    assert active_counts[-1] == 2


def test_summarizer_refuses_symlinked_plot_directory(tmp_path: Path) -> None:
    """Analysis cleanup never removes files through a plot-directory link."""
    summarizer = load_summarizer()
    tracks = tmp_path / "tracks_source.txt"
    tracks.write_text("1 0.0 1.0 1.0\n", encoding="utf-8")
    output_dir = tmp_path / "output"
    output_dir.mkdir()
    external = tmp_path / "external"
    external.mkdir()
    marker = external / "active_tracks.png"
    marker.write_text("preserve\n", encoding="utf-8")
    (output_dir / "plots").symlink_to(
        external,
        target_is_directory=True,
    )

    with pytest.raises(ValueError, match="symlinked plot directory"):
        summarizer.main(
            [
                "--tracks",
                str(tracks),
                "--output-dir",
                str(output_dir),
                "--run-name",
                "symlink_fixture",
                "--input",
                "fixture",
                "--event-width",
                "8",
                "--event-height",
                "8",
            ]
        )
    assert marker.read_text(encoding="utf-8") == "preserve\n"


def test_summarizer_refuses_symlinked_canonical_tracks(tmp_path: Path) -> None:
    """An unsafe canonical track target preserves prior accepted plots."""
    summarizer = load_summarizer()
    output_dir = tmp_path / "output"
    output_dir.mkdir()
    external = tmp_path / "external_tracks.txt"
    external.write_text("1 0.0 1.0 1.0\n", encoding="utf-8")
    output_tracks = output_dir / "tracks.txt"
    output_tracks.symlink_to(external)
    plots_dir = output_dir / "plots"
    plots_dir.mkdir()
    prior_plot = plots_dir / "active_tracks.png"
    prior_plot.write_bytes(b"preserve")

    with pytest.raises(ValueError, match="symlinked track output"):
        summarizer.main(
            [
                "--tracks",
                str(output_tracks),
                "--output-dir",
                str(output_dir),
                "--run-name",
                "symlink_fixture",
                "--input",
                "fixture",
                "--event-width",
                "8",
                "--event-height",
                "8",
            ]
        )

    assert external.read_text(encoding="utf-8") == "1 0.0 1.0 1.0\n"
    assert prior_plot.read_bytes() == b"preserve"


def test_summary_symlink_fails_before_plot_cleanup(tmp_path: Path) -> None:
    """An unsafe summary target cannot invalidate prior accepted plots."""
    summarizer = load_summarizer()
    tracks = tmp_path / "tracks_source.txt"
    tracks.write_text("1 0.0 1.0 1.0\n", encoding="utf-8")
    output_dir = tmp_path / "output"
    plots_dir = output_dir / "plots"
    plots_dir.mkdir(parents=True)
    prior_plot = plots_dir / "active_tracks.png"
    prior_plot.write_bytes(b"preserve")
    external = tmp_path / "external.json"
    external.write_text('{"preserve": true}\n', encoding="utf-8")
    (output_dir / "summary.json").symlink_to(external)

    with pytest.raises(ValueError, match="symlinked summary output"):
        summarizer.main(
            [
                "--tracks",
                str(tracks),
                "--output-dir",
                str(output_dir),
                "--run-name",
                "symlink_fixture",
                "--input",
                "fixture",
                "--event-width",
                "8",
                "--event-height",
                "8",
            ]
        )

    assert prior_plot.read_bytes() == b"preserve"
    assert external.read_text(encoding="utf-8") == (
        '{"preserve": true}\n'
    )


def test_plot_cleanup_prevalidates_all_targets(tmp_path: Path) -> None:
    """A later unsafe plot target preserves every earlier valid artifact."""
    summarizer = load_summarizer()
    plots_dir = tmp_path / "plots"
    plots_dir.mkdir()
    prior_plot = plots_dir / "active_tracks.png"
    prior_plot.write_bytes(b"preserve")
    external = tmp_path / "external.png"
    external.write_bytes(b"external")
    (plots_dir / "track_xy.png").symlink_to(external)

    with pytest.raises(ValueError, match="symlinked owned plot"):
        summarizer._remove_owned_plots(tmp_path)

    assert prior_plot.read_bytes() == b"preserve"
    assert external.read_bytes() == b"external"


def test_image_geometry_rejects_conflicting_override() -> None:
    """An explicit image plane cannot contradict event metadata."""
    summarizer = load_summarizer()
    event_rate = summarizer.EventRate(
        event_count=2,
        duration_s=0.1,
        bin_counts=(2,),
        bin_us=100_000,
        source="fixture",
        image_width=240,
        image_height=180,
        geometry_source="ros_event_message",
    )

    with pytest.raises(ValueError, match="conflicts"):
        summarizer._resolve_image_geometry(
            event_rate,
            200,
            200,
        )
