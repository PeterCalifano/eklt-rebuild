# Event Tuple Format

The packaged `event_vision_utils` loaders use one canonical in-memory event
representation:

| field | dtype | meaning |
| --- | --- | --- |
| `x` | integer | pixel column in `[0, width)` |
| `y` | integer | pixel row in `[0, height)` |
| `p` | integer/bool | polarity, normalized to `-1` or `+1` |
| `t_us` | integer | timestamp in microseconds, monotonically nondecreasing |

`EventArray` also carries `width`, `height`, and `frame_id`.

## Dataset Adapter Layer

Dataset-specific loaders derive from `EventDatasetAdapter` and return
`LoadedEventDataset`. The algorithm-facing payload is always `EventArray`;
dataset metadata stays side-channel under `DatasetMetadata.attributes`.

Current adapters:

- `ElopeNpzAdapter`: official ELOPE `.npz`, requires `events`, `timestamps`,
  `traj`, and `range_meter`.
- `GenericNpzAdapter`: generic event tuple fixtures and future dataset staging.

Use `load_event_dataset(path, adapter="elope")` for ELOPE demos. `adapter="auto"`
prefers official ELOPE when metadata keys are present, then falls back to generic
NPZ.

## NPZ Layouts

Two `.npz` layouts are accepted.

Separate arrays:

```text
x=<1D array>
y=<1D array>
p=<1D array>
t_us=<1D array>
```

Matrix layout:

```text
events=<N x 4 array>
```

The official ELOPE loader uses matrix column order `x, y, p, t_us` and requires
the ELOPE metadata keys. The generic loader can override the matrix key and
column order for fixtures and other datasets.

## Validation Rules

- Coordinates must be finite integer pixel indices inside the sensor bounds.
- Polarity may be `{-1, +1}`, `{0, 1}`, or bool; it is normalized to `{-1, +1}`.
- Timestamps are normalized to microseconds and must be monotonic.
- All event columns must have equal length.
- Official ELOPE files must include motion metadata keys even when test-split
  position/velocity values are masked with `nan`.

## ROS2 EventPacket Mapping

The ROS2 helper encodes `EventArray` batches into
`event_camera_msgs/msg/EventPacket` with the documented `mono` encoding:

- one 64-bit word per event,
- bit 63 stores polarity,
- bits 48-62 store `y`,
- bits 32-47 store `x`,
- bits 0-31 store `dt` in nanoseconds from `time_base`.

`mono` is deprecated upstream, but it gives a compact, dependency-light
round-trip path for current tests. Runtime deployments should prefer
`event_camera_codecs` encodings when those packages are available.
