# Single-Sequence ELOPE Artifact Contract

This document defines the stable Stage 19 interface consumed by the later
multi-sequence and online-streaming work. One official ELOPE sequence is loaded
through `EventArray`, reconstructed through the generated `eklt_rebuild`
wrapper, tracked through the accepted Stage 14 ROS2 EventPacket runner, and
reported without adding another packet codec or publisher.

## Run the pipeline

Build the Python wrapper and ROS2 overlay first:

```bash
./build_lib.sh --python
./build_ros2.sh
```

Then run one sequence:

```bash
scripts/run_official_elope_event_only_pipeline_demo.sh \
  --input data/elope/test/0028.npz \
  --output-dir outputs/official_elope_event_only \
  --overlay-setup eklt_ros2_ws/install/setup.bash
```

The command returns:

- `0` when reconstruction, tracking, analysis, video generation, and their
  evaluators pass;
- `1` for a functional or artifact-validation failure;
- `2` when a required native or ROS2 runtime is unavailable.

Within `status_codes`, `3` means that a downstream step was not run because an
earlier prerequisite did not pass. It is never treated as success.

## Artifact tree

```text
<output>/
├── summary.json
├── reconstruction/
│   ├── summary.json
│   ├── events_preview.mp4
│   ├── reconstruction.mp4
│   ├── fibar_patches.mp4
│   └── plots/
│       ├── event_rate.png
│       ├── event_stream_3d_views.png
│       └── patch_quality.png
└── tracking/
    ├── summary.json
    ├── tracks.txt
    ├── processing_timing.csv
    ├── processing_timing_summary.json
    ├── track_video_summary.json
    ├── eklt_tracks.mp4
    └── plots/
        ├── active_tracks.png
        ├── track_lifetimes.png
        ├── reinit_timeline.png
        ├── track_xy.png
        ├── event_rate.png
        └── processing_time_cumulative.png
```

When `ffmpeg` is unavailable, a video named `<stem>.mp4` is represented by the
directory `<stem>_frames/` containing contiguous
`frame_000000.png`, `frame_000001.png`, and later frames. The JSON `kind` and
`path` fields identify which representation was published.

## Stable JSON schemas

Every Stage 19 summary uses `schema_version: 1`, an exact `artifact_type`, and
one of `passed`, `blocked`, or `failed`.

### Pipeline summary

`<output>/summary.json` has
`artifact_type: "elope_single_sequence_pipeline"` and contains:

- `input`: the selected ELOPE sequence;
- `status_codes`: exit codes for reconstruction, tracking, analysis, both
  component evaluators, track-video generation, and track-video evaluation;
- `components`: embedded reconstruction, tracking, and track-video summaries
  together with their paths;
- `artifacts`: relative paths to those component summaries.

Later multi-sequence aggregation must embed or reference this schema without
changing it.

### Reconstruction summary

`reconstruction/summary.json` has
`artifact_type: "elope_fibar_reconstruction"`. It records the validated
dataset metadata, event count and duration, bounded plot contracts, aggregate
video metadata, reconstruction/patch frame counts, and patch-quality sampling:

- `patch_quality_count` is the total number of inspected patches;
- `patch_quality_samples` is the bounded number retained for the plot;
- `patch_quality_truncated` states whether the retention limit was reached.

### Tracking summary

`tracking/summary.json` has `artifact_type: "eklt_track_analysis"`. The analyzer
preserves the accepted Stage 14 timing, conversion, duration-coverage, and
transport evidence while adding:

- strict `track_count` and `track_rows`;
- the relative `tracks_file`;
- the exact represented `event_count` and complete `source_event_count`;
- fixed image geometry and provenance;
- `runtime_s` for the native run and separate `analysis_runtime_s`;
- labeled plot paths and matching `plot_contracts`;
- explicit `gt_status` and `gt_metrics`.

When Stage 14 converted only a bounded packet prefix, event-rate analysis uses
that same source prefix rather than the complete NPZ file.

### Track-video summary

`tracking/track_video_summary.json` has
`artifact_type: "eklt_track_video"`. Its relative `tracks` path and `video`
object are validated together, including exact track rows/IDs, encoded
dimensions, frame count, frame rate, hold duration, dot radius, and scale.
Finite native subpixel estimates remain unchanged in `tracks.txt`; estimates
outside the fixed pixel-center plane are clipped only for display, and
`boundary_clipped_track_rows` records their exact count.

### Video object

Each video object contains:

```text
kind          "mp4", "png", or "png_sequence"
path          artifact path relative to its component summary
frame_count   positive encoded frame count
width         positive encoded width in pixels
height        positive encoded height in pixels
fps           positive rate for MP4/PNG sequences; null for one PNG
```

Writers and evaluators reject encoded geometry above 16,777,216 pixels per
frame and artifacts above 1,000,000 frames. The frame-count limit matches the
owned six-digit PNG-sequence naming contract.

The evaluator uses Pillow for PNGs and `ffprobe` when available for MP4 stream
geometry, rate, and exact frame count.

## Track and plot readers

`tracks.txt` contains one strict UTF-8 row per observation:

```text
id time_s x_px y_px
```

Blank lines and `#` comments are accepted. Every other row must have exactly
four finite values, a nonnegative integer ID and timestamp, and nondecreasing
time per feature. Read it with:

```python
from event_vision_utils.io import load_track_samples

samples = load_track_samples("outputs/run/tracking/tracks.txt")
print(len(samples))
```

Expected output is the exact number declared by `track_rows`. For numeric
exploration after strict validation, `numpy.loadtxt` or pandas may read the same
four columns.

Open plot PNGs with Pillow or OpenCV. Each declared plot has a machine-readable
title, subtitle, and unit-bearing axis labels in `plot_contracts`.
Read MP4 files with FFmpeg/OpenCV and PNG-sequence fallback directories with
Pillow/OpenCV in filename order.

Validate component and video artifacts directly:

```bash
PYTHONPATH=python scripts/evaluate_outputs.py \
  outputs/official_elope_event_only/reconstruction \
  --no-require-tracks

PYTHONPATH=python scripts/evaluate_outputs.py \
  outputs/official_elope_event_only/tracking

PYTHONPATH=python scripts/evaluate_outputs.py \
  --track-video-summary \
  outputs/official_elope_event_only/tracking/track_video_summary.json
```

## Ownership and cleanup

- `data/` and `outputs/` are generated and ignored.
- An output root may not be the filesystem root, repository root, a repository
  ancestor, or a symlink.
- Reruns remove only explicitly enumerated Stage 19 artifacts below the
  selected component directories.
- Unrelated files, accepted Stage 14 timing files, logs, and converted input
  bags are preserved.
- Cleanup and atomic publication reject symlinked owned targets and temporary
  paths.
- PNG fallback replacement is prepared completely before the prior valid
  numbered sequence is removed.

Random multi-sequence selection, AEDAT4, generic direct publishing, and
asynchronous ROS2 processing remain outside this contract.
