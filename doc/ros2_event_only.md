# ROS2 Event-Only EKLT

The `ros2/eklt_rebuild` overlay is a thin ROS2 interface to the ROS-free
`CEkltTrackerOrchestrator`. It owns EventPacket decoding, ROS2 parameters,
bounded sensor-data QoS, file/topic output, and display-image publication. FIBAR
reconstruction, Harris initialization, event scheduling, Ceres optimization,
feature lifecycle, deterministic event ordering, and gradient-cache release
remain in the canonical C++17 library.

## Build

Build the independent ROS2 Jazzy overlay with one job:

```bash
./build_ros2.sh --workspace "$PWD/eklt_ros2_ws" --jobs 1
source "$PWD/eklt_ros2_ws/install/setup.bash"
```

The package links the canonical `eklt_rebuild::eklt-rebuild` target. It does
not compile a second copy of native EKLT sources.

The event-only node subscribes to `/events` as
`event_camera_msgs/msg/EventPacket` and publishes:

- `/eklt/tracks` as text rows in `std_msgs/msg/String`;
- `/eklt/stats` as JSON in `std_msgs/msg/String`;
- `/eklt/init_debug_image` as a `mono8` `sensor_msgs/msg/Image`;
- `/eklt/feature_tracks` as an annotated `bgr8`
  `sensor_msgs/msg/Image`.

Both ROS2 nodes read their sections from the shared top-level source file
`config/eklt_ros2.yaml`, installed as
`share/eklt_rebuild/config/eklt_ros2.yaml`. The event subscription uses
best-effort sensor-data QoS with a bounded depth of four packets. Packet
sequence discontinuities are counted and logged instead of allowing an
unbounded backlog to consume RAM.

The feature image reuses the transport-neutral renderer used by ROS1. It is
generated only while `display_features` is true and the topic has a subscriber,
is limited by `visualization_max_rate_hz`, and uses a publisher depth of one.
Display scale, flow-arrow length, patch outlines, and identifiers are
configured through the same `scale`, `arrow_length`,
`display_feature_patches`, and `display_feature_id` names as the original
viewer.

## Existing `boxes_6dof.bag` Example

The original example bag stores `/dvs/events` as ROS1
`dvs_msgs/EventArray`. The offline converter reads that topic directly and
writes a standard ROS2 EventPacket bag without requiring a running ROS1 graph.
Use Python 3.12 with NumPy and rosbags. An existing Conda environment is
sufficient; the repository does not create or require a separate virtual
environment:

```bash
conda activate ros2_jazzy
export PYTHON="${CONDA_PREFIX}/bin/python"
"${PYTHON}" -c "import numpy, rosbags"
```

Convert and run the example:

```bash
scripts/run_ros2_rosbag_event_only_demo.sh \
  --legacy-bag /path/to/boxes_6dof.bag \
  --output-dir outputs/ros2_boxes_event_only
```

The converter validates sensor geometry and timestamps, stable-sorts only an
internally disordered legacy packet, preserves equal-timestamp order, splits
packets whose relative nanosecond time would overflow, and creates the output
bag atomically. A successful run writes:

- `tracks.txt` with native EKLT samples;
- `summary.json` with track count and represented-duration evidence;
- `processing_timing.csv` with one accepted-packet timing decomposition;
- `plots/processing_time_cumulative.png` and
  `processing_timing_summary.json`;
- `event_only_eklt_node.log` and `ros2_bag_play.log`;
- `ros2_bag_info.txt`;
- `conversion_summary.json` and `eventpacket_bag/` for legacy input.

The converted bag is reused on later runs. Playback defaults to real time,
holds only two messages in the rosbag2 read-ahead queue, waits for the bounded
EKLT queue to drain, rejects an empty track result, and requires the last track
to represent at least 80% of the bag duration. Use
`--min-duration-coverage 0` for a different bag where the scene intentionally
has no trackable features near the end. Images and IMU from the original bag
are intentionally omitted because this is the event-only path.

The timing plot is produced on every successful rosbag run. Its horizontal
axis is event time since the first accepted packet, and its vertical axis is
wall-clock milliseconds per packet. The stacked blue, orange, and grey bands
show FIBAR reconstruction, native EKLT work excluding FIBAR, and remaining
ROS2 decoding/output overhead. A dark boundary line shows the complete
processing step; total is not stacked again as a fourth component. The
measurement ends after requested track, image-topic, and PNG outputs, while
statistics and timing-file serialization remain outside the interval so the
diagnostic does not recursively time itself. The runner validates finite,
nonnegative, timestamp-ordered rows and their additive total before accepting
the plot. The rendered figure uses a capitalized descriptive title, bracketed
seconds/milliseconds axes, explicit component labels, and the same visible
label strings in `processing_timing_summary.json`. Matplotlib must be available
in the selected `PYTHON` or Conda environment.

An existing ROS2 EventPacket bag can be used directly:

```bash
scripts/run_ros2_rosbag_event_only_demo.sh \
  --ros2-bag /path/to/eventpacket_bag \
  --output-dir outputs/ros2_eventpacket_bag
```

Add the original-demo-equivalent feature overlay with the standard ROS2 image
viewer:

```bash
scripts/run_ros2_rosbag_event_only_demo.sh \
  --ros2-bag /path/to/eventpacket_bag \
  --output-dir outputs/ros2_eventpacket_bag \
  --visualize
```

No custom GUI is started. `--visualize` launches
`rqt_image_view /eklt/feature_tracks` before playback and includes it in the
runner's bounded shutdown handling.

Save bounded FIBAR reconstruction images alongside the track output:

```bash
scripts/run_ros2_rosbag_event_only_demo.sh \
  --ros2-bag /path/to/eventpacket_bag \
  --output-dir outputs/ros2_eventpacket_bag \
  --save-reconstructed-frames \
  --saved-frame-stride 5 \
  --max-saved-frames 100 \
  --png-compression 3
```

Files are written below `<output-dir>/reconstructed_frames/` as
`frame_<index>_t_<timestamp_us>.png`. They contain the finite-normalized
`mono8` display buffer also used by `/eklt/init_debug_image`, not the exact
floating-point FIBAR working state. Each file is encoded to a temporary
sibling and atomically published. The output directory and saved count are
recorded in `summary.json`. Both visualization and PNG export remain disabled
by default.

## ELOPE Event-Only Example

The ELOPE runner converts the dataset's event array to a standard EventPacket
bag, then invokes the same rosbag runner. It therefore has identical headless
tracking, feature visualization, PNG export, processing-time plot, output
validation, and process cleanup:

```bash
conda activate ros2_jazzy
export PYTHON="${CONDA_PREFIX}/bin/python"
"${PYTHON}" -c "import numpy, rosbags"

scripts/run_ros2_elope_event_only_example_demo.sh \
  --input data/elope/test/0028.npz \
  --output-dir outputs/ros2_elope_event_only \
  --visualize \
  --save-reconstructed-frames \
  --saved-frame-stride 5 \
  --max-saved-frames 100
```

The converter uses `PYTHON`, so an existing Conda environment is sufficient;
the repository does not create a virtual environment. Conversion is bounded
by both `--dt-ms` and `--max-events-per-packet`, writes the bag atomically, and
records exact source and parameter provenance before allowing reuse.

Explicit scalar `width`/`height`, `sensor_width`/`sensor_height`, or
`camera_width`/`camera_height` metadata is authoritative when present. The
official files do not carry those fields, so the documented 200-by-200 ELOPE
sensor contract is used. Coordinates are raw pixel indices and geometry is
never inferred from their observed maxima. This EKLT path therefore does not
require a camera matrix or the trajectory and range arrays. Pass `--width` and
`--height` together only as a matching override for a dataset variant.

## Live DVXplorer

EKLT accepts any DVXplorer source that publishes
`event_camera_msgs/msg/EventPacket`. For a direct ROS2 connection, install the
standard `libcaer_driver`, configure its udev permissions, stop dv-runtime so
the camera has one USB owner, and run:

```bash
sudo apt install ros-jazzy-libcaer-driver

scripts/run_ros2_dvxplorer_event_only_demo.sh --source libcaer
```

The demo launches the installed `libcaer_driver` node for a DVXplorer with
compressed `libcaer_cmp` EventPackets on `/event_camera/events`. It starts EKLT
first, validates the discovered message type, writes tracks and logs under
`outputs/ros2_dvxplorer_event_only/`, and runs until interrupted.

The upstream dv-runtime ROS bridge publishes ROS1 `dv_ros_msgs`, not the ROS2
EventPacket contract used here. A separate dv-runtime adapter is still usable
if it publishes EventPacket:

```bash
scripts/run_ros2_dvxplorer_event_only_demo.sh \
  --source external \
  --events-topic /events
```

Do not update a DVXplorer to firmware `v1.0` solely for this path. The
`libcaer_driver` project warns that this update is irreversible and makes the
camera incompatible with libcaer. Check the target device firmware before
choosing between the direct libcaer path and an external publisher.

No custom viewer is included. Use standard ROS2 tools:

```bash
ros2 topic echo /eklt/stats
ros2 topic hz /event_camera/events
ros2 run rqt_image_view rqt_image_view /eklt/init_debug_image
ros2 run rqt_image_view rqt_image_view /eklt/feature_tracks
```

The repository validates the adapter and complete native algorithm with
runtime-generated scalar frames and ideal frame-difference events. A physical
DVXplorer run remains a target-device acceptance gate because the camera and
driver are not installed in the development environment.
