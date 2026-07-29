# Reusable `event_vision_utils` foundation

`event_vision_utils` is developed alongside EKLT as an extraction-ready module
boundary. Its public contract can therefore be validated against real
consumers now while preserving a clean future move to EventDataGenerationLib
or a dedicated repository. It is currently versioned and installed by the
single `eklt-rebuild` distribution alongside the distinct `eklt_rebuild` and
`eklt_bridge` import namespaces.

## Stable foundation contract

- `EventArray` owns validated `x`, `y`, signed `p` in `{-1, +1}`, and monotonic
  integer `t_us` columns plus explicit sensor geometry.
- `EventDatasetAdapter -> LoadedEventDataset -> EventArray` is the common
  dataset-loader contract.
- Official ELOPE archives remain strict and use advertised scalar geometry or
  the documented 200-by-200 contract. Generic NPZ input requires explicit
  geometry and never infers it from observed coordinate extrema.
- Count and time slicing return bounded owning chunks without retaining prior
  windows.
- Array visualization primitives return NumPy accumulation, polarity, and time
  surfaces without writing files.
- File-producing analytical plots use Matplotlib and publish atomically with
  explicit title, subtitle, unit-bearing axis, and bounded-sample contracts.
- Event previews, FIBAR diagnostics, and track overlays stream frames to one
  MP4 or a contiguous PNG-sequence fallback. Their summaries retain aggregate
  metadata rather than a path per frame. Encoded artifacts are limited to
  16,777,216 pixels per frame and 1,000,000 frames.
- The strict `id time_s x_px y_px` track reader rejects malformed or
  per-feature time-regressing rows without silently omitting observations.
- Core imports do not require EKLT, ROS, FIBAR, OpenCV, MATLAB, or project
  scripts.
- Optional FIBAR adaptation uses the accepted `eklt_rebuild` distribution; it
  never compiles or searches for a private extension.

## Install and run

Install the unified distribution from the repository Python project:

```bash
python3.12 -m pip install ./python
```

Create and inspect the canonical event representation:

```bash
PYTHONPATH=python python3.12 - <<'PY'
from event_vision_utils import EventArray

events = EventArray.from_arrays(
    x=[1, 2],
    y=[3, 4],
    p=[0, 1],
    t=[0.001, 0.002],
    width=8,
    height=6,
    timestamp_unit="s",
)
print(events.as_columns().tolist())
PY
```

Expected output:

```text
[[1, 3, -1, 1000], [2, 4, 1, 2000]]
```

Run the foundation tests:

```bash
PYTHONPATH=python python3.12 -m pytest -q \
  python/tests/event_vision_utils/test_event_array.py \
  python/tests/event_vision_utils/test_timestamp_normalization.py \
  python/tests/event_vision_utils/test_polarity_normalization.py \
  python/tests/event_vision_utils/test_dataset_adapter.py \
  python/tests/event_vision_utils/test_elope_loader.py \
  python/tests/event_vision_utils/test_generic_npz_loader.py \
  python/tests/event_vision_utils/test_count_slicer.py \
  python/tests/event_vision_utils/test_time_slicer.py \
  python/tests/event_vision_utils/test_visualization_arrays.py
```

## Single-sequence artifact examples

Render transport-neutral ELOPE diagnostics through the accepted native wrapper:

```bash
PYTHONPATH=python python3.12 \
  -m event_vision_utils.examples.reconstruct_elope_fibar \
  --input data/elope/test/0028.npz \
  --output-dir outputs/elope_reconstruction
```

Expected output includes `summary.json`, labeled plots, an event preview,
reconstruction video, and a bounded patch mosaic. If `ffmpeg` is unavailable,
each video path is replaced by a numbered PNG directory described by the same
typed metadata.

Render accepted Stage 14 ROS2 track rows without introducing another ROS
transport implementation:

```bash
PYTHONPATH=python python3.12 \
  -m event_vision_utils.examples.render_elope_tracks \
  --input data/elope/test/0028.npz \
  --tracks outputs/official_elope_event_only/tracking/tracks.txt \
  --output outputs/official_elope_event_only/tracking/eklt_tracks.mp4
```

Expected summary:

```text
outputs/official_elope_event_only/tracking/track_video_summary.json
```

## Extraction checklist

- Preserve the public fields, timestamp/polarity conventions, and import paths.
- Move the focused tests with the package and retain Python 3.12 type and
  documentation gates.
- Keep ELOPE policy strict and generic NPZ geometry explicit.
- Keep `EventArray` as the only event-data contract exported by this namespace;
  do not add aliases for project-specific bridge representations.
- Replace EKLT-local imports with the extracted package dependency.
- Move the strict track reader, plot contracts, bounded event-cloud/rate
  renderers, and streamed video metadata together with their focused tests.
- Keep ROS2 publishers, multi-sequence dataset iteration, and asynchronous
  processing outside this package until their later owning stages are
  accepted.
