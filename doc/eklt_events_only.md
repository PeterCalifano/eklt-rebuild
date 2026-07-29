# EKLT Event-Only Mode

EKLT supports two initialization modes over the same ROS-free C++17 tracker:

- frame-backed initialization from conventional images;
- event-only initialization from FIBAR reconstruction.

The original frame-backed mode remains the default and is not a compatibility
fallback. Event-only mode must be selected explicitly.

## Shared native architecture

`CEkltTrackerOrchestrator` owns the common tracking behavior:

1. validate and causally order accepted events;
2. obtain an initialization image from the selected provider;
3. detect Harris candidates and initialize photometric patches;
4. update patches through the shared Ceres optimizer;
5. retire or replenish features and release gradient-image references;
6. expose owning track, image, timing, and statistics snapshots.

The ROS1 and ROS2 layers own only their transport, configuration, and output
boundaries. They do not implement another FIBAR, Harris, Ceres, KLT, or feature
lifecycle path.

The native implementation is split by responsibility while remaining one
`libeklt-rebuild` binary:

```text
src/eklt_core/                 tracking and initialization orchestration
src/event_recon_fibar_core/    FIBAR reconstruction facade
src/visualization/             transport-neutral feature rendering
src/wrap_adapters/             Eigen-backed wrapper adaptation
```

## ROS1 frame-backed and event-only modes

Build and source the Noetic workspace:

```bash
./build_ros1.sh \
  --workspace "$HOME/eklt_catkin_ws" \
  --import-dependencies \
  --jobs 1
source "$HOME/eklt_catkin_ws/devel/setup.bash"
```

Run the original frame-backed path:

```bash
roslaunch eklt_rebuild eklt.launch \
  bag:=/path/to/boxes_6dof.bag \
  tracks_file_txt:=/tmp/eklt_frame_tracks.txt
```

Run the event-only alternative over the same event topic:

```bash
roslaunch eklt_rebuild eklt.launch \
  bag:=/path/to/boxes_6dof.bag \
  event_only_mode:=true \
  bootstrap:=events \
  tracks_file_txt:=/tmp/eklt_event_only_tracks.txt
```

The event-only launch arguments map to the native FIBAR configuration:

```text
event_only_reconstruction_interval_events:=5000
fibar_cutoff_time_us:=10000
fibar_fill_ratio:=0.5
fibar_use_spatial_filter:=true
```

Event-only mode does not subscribe to the image topic. Frame-backed mode keeps
the original image-and-event behavior.

## ROS2 EventPacket mode

The independent `ros2/eklt_rebuild` overlay decodes
`event_camera_msgs/msg/EventPacket`, loads ROS2 parameters, and delegates every
accepted batch to the same `CEkltTrackerOrchestrator`.

Build and source the Jazzy overlay:

```bash
./build_ros2.sh --workspace "$PWD/eklt_ros2_ws" --jobs 1
source "$PWD/eklt_ros2_ws/install/setup.bash"
```

The event-only node publishes:

- `/eklt/tracks` as text observations;
- `/eklt/stats` as structured JSON text;
- `/eklt/init_debug_image` as a reconstructed `mono8` image;
- `/eklt/feature_tracks` as a bounded annotated `bgr8` image.

Configuration comes from `config/eklt_ros2.yaml`. Event subscription uses
best-effort sensor-data QoS and a bounded queue. Sequence discontinuities are
reported instead of allowing an unbounded backlog.

See [ROS2 Event-Only EKLT](ros2_event_only.md) for recorded-bag conversion,
timing, visualization, bounded PNG export, and live DVXplorer entrypoints.

## Official ELOPE single-sequence pipeline

Build the Python wrapper and ROS2 overlay, then run:

```bash
./build_lib.sh --python
scripts/download_elope_dataset.sh --output-dir data/elope --first-only
scripts/run_official_elope_event_only_pipeline_demo.sh \
  --input data/elope/test/0028.npz \
  --output-dir outputs/official_elope_event_only \
  --overlay-setup "$PWD/eklt_ros2_ws/install/setup.bash"
```

The pipeline:

1. validates the official ELOPE event array and fixed geometry;
2. streams FIBAR reconstruction and patch diagnostics;
3. converts bounded event windows to EventPacket messages;
4. runs the accepted ROS2 EKLT path;
5. analyzes tracks and processing timing;
6. renders bounded event, reconstruction, patch, and track videos;
7. validates every JSON, CSV, text, plot, and media artifact.

The stable artifact schema is defined in
[Single-Sequence ELOPE Artifact Contract](elope_single_sequence_pipeline.md).
The complete accepted run is recorded in
[Official ELOPE Single-Sequence Acceptance Report](developments/official_elope_acceptance_report.md).

## Event and track contracts

The Python event representation uses:

```text
x, y    integer pixel coordinates
p       signed polarity in {-1, +1}
t_us    monotonically nondecreasing integer microseconds
```

See [Event Tuple Format](event_tuple_format.md) for dataset and EventPacket
mapping details.

Track artifacts contain:

```text
id time_s x_px y_px
```

Track coordinates remain native subpixel estimates. Plot and video renderers
clip out-of-plane coordinates only for display and report the exact clip count.

## Current scope

- Ceres and FIBAR are required parts of the native EKLT implementation.
- Python and MATLAB wrappers adapt the same native facade through Eigen.
- SuperEvent remains future work; no PyTorch or ONNX runtime is part of EKLT.
- Multi-sequence datasets, AEDAT4, bounded online workers, asynchronous image
  diagnostics, and PlotJuggler metrics are specified in
  `doc/developments/dataset_and_online_streaming_plan.md` and are not yet
  implemented.

See [Known Limitations](known_limitations.md) for environment and hardware
gates.
