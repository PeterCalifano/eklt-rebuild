# Official ELOPE Single-Sequence Acceptance Report

## Acceptance status

The complete Stage 19 single-sequence pipeline passed on 2026-07-28. The run
loaded one official ELOPE sequence, generated FIBAR diagnostics, converted the
complete event array to ROS2 EventPacket messages, tracked through the accepted
ROS2 overlay, analyzed the track artifact, rendered the full-duration track
video, and validated every component summary.

Runtime source came from exact index tree
`74c544b7a5e3753a2d85cdc01f425aa1e8e1236f`. The shared native wrapper and
ROS2 overlay came from the previously built exact index tree
`5d854c53c831db1bd7daca65d57143f9b6aca011`; the trees differ only in the
Stage 19 track-rendering, evaluator, summarizer, focused-test, and reader
documentation paths. No native, wrapper-generation, or ROS2 build input
changed between them. The later report and checkpoint-ledger update are
evidence-only changes.

The disposable acceptance artifacts are under:

```text
/tmp/eklt-stage19-official-elope-final.rtvjo8/
```

## Scope and architecture

The accepted path preserves the existing component boundaries:

1. `event_vision_utils` strictly loads the official NPZ event array.
2. The generated `eklt_rebuild` wrapper calls the canonical native FIBAR
   implementation for reconstruction and patch diagnostics.
3. The accepted Stage 14 converter writes the complete event array as bounded
   ROS2 EventPacket messages.
4. The ROS2 overlay delegates tracking to the ROS-free
   `CEkltTrackerOrchestrator`.
5. Stage 19 reads the accepted track and timing artifacts to publish stable
   JSON, CSV, PNG, and MP4 outputs.

No second event codec, FIBAR implementation, EKLT algorithm, or feature
lifecycle exists in the analysis layer. Ground-truth feature tracks are not
present in the tested ELOPE sequence, so pixel-error metrics remain explicitly
unavailable.

## Dataset

- Zenodo record: `15421707`.
- File: `data/elope/test/0028.npz`.
- File size: `1,325,937` bytes.
- SHA-256:
  `7fdaa6b16a2e7913c7a034804144d2d51367583aba9056eac467dd44d6bebd32`.
- Required keys: `events`, `timestamps`, `traj`, and `range_meter`.
- Events: `386,785`.
- Duration: `48.782 s`.
- Geometry: `200 x 200`, resolved from the official ELOPE contract.
- Event convention: `x`, `y`, signed polarity, integer microseconds.

The strict loader did not infer geometry from observed coordinate maxima.

## Reproduction

Build the shared Python wrapper and the independent Jazzy overlay:

```bash
./build_lib.sh --python --install -t Release -j 1
./build_ros2.sh --workspace eklt_ros2_ws --ros-distro jazzy -j 1
```

Run the complete official pipeline:

```bash
PYTHON=python3.12 \
scripts/run_official_elope_event_only_pipeline_demo.sh \
  --input data/elope/test/0028.npz \
  --output-dir outputs/official_elope_event_only \
  --ros-setup /opt/ros/jazzy/setup.bash \
  --overlay-setup eklt_ros2_ws/install/setup.bash
```

Validate the three published component contracts:

```bash
PYTHONPATH=python python3.12 scripts/evaluate_outputs.py \
  outputs/official_elope_event_only/reconstruction \
  --no-require-tracks

PYTHONPATH=python python3.12 scripts/evaluate_outputs.py \
  outputs/official_elope_event_only/tracking

PYTHONPATH=python python3.12 scripts/evaluate_outputs.py \
  --track-video-summary \
  outputs/official_elope_event_only/tracking/track_video_summary.json
```

All three evaluator commands passed on the recorded run.

## Exact run results

### Pipeline

- Root status: `passed`.
- All seven component and evaluator status codes: `0`.
- Wall time: `54.49 s`.
- Peak resident memory: `244,624 KiB`.
- Swap activity: none.
- Error, fatal, or rejected-packet log entries: none.

### Reconstruction and diagnostics

- Reconstruction status: `passed`.
- Reconstruction runtime: `12.314 s`.
- Event preview: `4,879` frames, `200 x 200`, `100 fps`.
- FIBAR reconstruction: `244` frames, `200 x 200`, `5 fps`.
- Patch mosaic: `244` frames, `1200 x 800`, `5 fps`.
- Inspected and retained patch-quality samples: `1,952`.
- Labeled plots: event rate, six-view space/time cloud, and patch quality.

### ROS2 tracking and analysis

- Converted EventPacket messages: `2,434`.
- Track rows: `9,060`.
- Distinct track IDs: `66`.
- Represented duration: `48.778 s`.
- Duration coverage: `0.9999180025`.
- Track-analysis runtime: `0.618 s`.
- Accepted timing samples: `697`.
- Maximum timing additivity error:
  `3.552713678800501e-15 ms`.
- Total processing p50: `5.742390 ms`.
- Total processing p95: `15.8189434 ms`.

At the default `10x` playback rate, the bounded ROS2 input queue reported three
sequence-discontinuity warnings and processed `697` accepted packets spanning
the complete sequence. This is not an error or a claim that all `2,434`
converted packets were processed. The accepted offline contract is bounded
latest-data processing plus validated timeline coverage; ordered
acknowledgements and explicit drop accounting remain owned by the later online
streaming plan.

### Track video

- Track-video status: `passed`.
- Frames: `4,879`.
- Geometry: `800 x 800`.
- Frame rate: `100 fps`.
- Observation hold: `100 ms`.
- Displayed track IDs and rows match the strict track artifact.
- Boundary-clipped track rows: `60`.

The source `tracks.txt` preserves every finite native subpixel coordinate.
Only rendered dot centers are clipped to the fixed pixel-center plane. The
summary records the exact clip count, and the evaluator recomputes that count
from the track artifact, encoded geometry, and scale.

## Artifact contract

The root `summary.json` embeds the component statuses and relative summary
paths. Component outputs remain below one owned per-sequence directory:

```text
reconstruction/
  summary.json
  events_preview.mp4
  reconstruction.mp4
  fibar_patches.mp4
  plots/
tracking/
  summary.json
  tracks.txt
  processing_timing.csv
  processing_timing_summary.json
  track_video_summary.json
  eklt_tracks.mp4
  plots/
summary.json
```

All MP4 streams were decoded with `ffprobe`. Exact frame counts, frame rates,
and geometries matched their JSON metadata. Timing rows were finite,
monotonic, and additive. Plot contracts contain nonempty capitalized titles,
descriptive subtitles, and unit-bearing axis labels.

Cleanup prevalidates the complete owned artifact set before removing prior
outputs. It rejects symlinked summaries, tracks, videos, plot directories,
temporary summaries, or owned plot paths without removing earlier accepted
artifacts. Unrelated files below the selected output directory are preserved.

## Findings corrected during acceptance

Two Stage 19 findings were corrected before this report:

1. The track-video renderer rejected finite subpixel estimates outside the
   fixed pixel-center plane even though the accepted static plot clipped only
   for display. The renderer now follows the same contract, publishes the
   exact clip count, and has focused renderer and evaluator regressions.
2. The shared tracker-plot layout placed its title over the subtitle. The
   figure title and axes subtitle now occupy distinct constrained-layout
   regions, with a rendered bounding-box regression.

The final full pipeline passed after both corrections.

## Visual review

Representative frames and every plot family were inspected from the final
run. The event/track dots, candidate boxes, patch tiles, fixed image plane,
titles, subtitles, legends, ticks, units, and annotations are readable and not
clipped. The 200-by-200 track plot visibly reports all `60` display-only
boundary clips.

## Remaining limitations

- The tested ELOPE file has no same-format feature-track ground truth, so
  `gt_status` is `unavailable` and no pixel-error metric is inferred.
- Stage 19 owns exactly one explicit sequence. Deterministic multi-sequence
  selection and aggregation remain in the separate streaming plan.
- The default accelerated playback deliberately exercises a bounded latest-data
  queue. Per-packet acknowledgement and explicit drop metrics are deferred to
  streaming Stages 2 and 6.
- Real DVXplorer execution remains a target-device acceptance gate.
