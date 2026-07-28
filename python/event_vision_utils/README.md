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

## Extraction checklist

- Preserve the public fields, timestamp/polarity conventions, and import paths.
- Move the focused tests with the package and retain Python 3.12 type and
  documentation gates.
- Keep ELOPE policy strict and generic NPZ geometry explicit.
- Keep `EventArray` as the only event-data contract exported by this namespace;
  do not add aliases for project-specific bridge representations.
- Replace EKLT-local imports with the extracted package dependency.
- Keep later file-producing plots, streamed videos, ROS2 publishers, dataset
  iteration, and asynchronous processing in their owning stages until their
  APIs and artifact schemas are accepted.
