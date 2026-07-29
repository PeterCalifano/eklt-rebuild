# Known Limitations

## Runtime environments

- ROS1 requires Noetic, catkin tools, and the dependencies imported by
  `build_ros1.sh --import-dependencies`. The dedicated CI workflow owns the
  repeatable ROS1 gate when Noetic is unavailable on the development host.
- ROS2 requires Jazzy plus `event_camera_msgs` and `event_camera_codecs`.
  Build the independent overlay through `./build_ros2.sh`; do not mix its
  colcon outputs into the native CMake build tree.
- Python wrappers require Python 3.12 and the pinned `lib/wrap` checkout.
- MATLAB wrappers require R2024b. MATLAB must preload the system `libgcc_s` and
  `libstdc++` as documented in `fibar_matlab_wrapper.md`.
- Official ELOPE video output uses FFmpeg when available. A deterministic
  numbered PNG sequence is published instead when FFmpeg is absent.

## Implementation scope

- The ROS1 package preserves the original frame-backed tracker and its
  explicitly selected event-only alternative.
- The ROS2 overlay currently exposes the event-only EventPacket path. It does
  not provide a second frame-backed ROS2 tracker.
- Both ROS adapters delegate tracking, FIBAR/Harris initialization, Ceres
  updates, feature lifecycle, and gradient-cache ownership to the ROS-free
  `CEkltTrackerOrchestrator`.
- ROS2 reconstruction and feature images are diagnostics. They are generated
  only when requested and remain bounded by configured rate, queue, stride,
  and count limits.
- SuperEvent is future-only. No SuperEvent, PyTorch, or ONNX dependency is part
  of the current native target graph.
- Multi-sequence ELOPE, AEDAT4 ingestion, online worker queues, asynchronous
  diagnostics, and PlotJuggler metrics remain planned work.

## Native and wrapper packaging

- Ceres, OpenCV, Eigen, and FIBAR are required native dependencies.
- The one shared/static `libeklt-rebuild` binary contains EKLT, FIBAR,
  visualization, and wrapper-adapter implementations. Installed logical CMake
  targets do not imply separate component libraries.
- The unified `eklt-rebuild` Python distribution installs the generated
  `eklt_rebuild` extension together with the `eklt_bridge` and
  `event_vision_utils` namespaces.
- A shared wheel co-locates only the generated extension and its required
  `libeklt-rebuild` runtime. A static wheel contains only the extension.
  Loader paths are relative, and `_wrapper_build.py` is excluded.
- CUDA, TBB, OpenMP, OpenGL, profiling, documentation, and wrappers remain
  opt-in. OptiX, PTX, and ZeroMQ are not active features.
- CUDA has no dedicated runtime CI job. The devcontainer BuildKit static check
  passes without the former undefined `LD_LIBRARY_PATH` warning, but a physical
  CUDA build remains environment-dependent.
- Cross-toolchain files provide compiler defaults only. Cross compilers,
  sysroots, and target libraries remain environment-owned.

## Data and evaluation

- Official ELOPE test sequences do not provide same-format feature-track
  ground truth. The pipeline therefore records `gt_status: unavailable`
  instead of inventing an accuracy result.
- The accepted single-sequence pipeline is deterministic for one selected
  input. Random or aggregate multi-sequence selection is intentionally absent.
- Event and video artifacts are bounded, but loading an official NPZ still
  materializes that sequence's immutable event arrays in memory.
- Track coordinates are native subpixel estimates and may cross the image
  boundary slightly. Renderers clip only for display and publish the exact
  clipped-row count.

## Hardware

- Direct DVXplorer acceptance remains a target-device gate. The source must
  publish `event_camera_msgs/msg/EventPacket` in an encoding supported by
  `event_camera_codecs`.
- Do not update DVXplorer firmware solely for this repository. Confirm firmware
  compatibility with the selected camera driver before changing the device.

Current implementation and validation evidence is recorded in:

- `developments/cpp_cuda_template_upgrade_plan.md`
- `developments/official_elope_acceptance_report.md`
- `ros2_event_only.md`
