# Event-Only EKLT Integration Audit

> **Archived Stage 0 audit.** This document records the repository before the
> C++17 single-library consolidation and ROS2 event-only integration. Its
> C++11, `include/`, `src/tracker.cpp`, and `test_example.sh` statements are
> deliberately preserved as historical evidence, not current guidance.

## Status

- [x] Current EKLT package shape inspected.
- [x] Neighbor event repositories listed.
- [x] Reusable local modules identified.
- [x] Local SuperEvent repo inspected for future detector-only provider implications.
- [x] Upstream FIBAR/EventPacket references checked.
- [x] No implementation beyond documentation in Stage 0.

## Current `rpg_eklt`

- [x] Build system: ROS1 catkin, `catkin_simple`, C++11, OpenCV, Ceres, gflags/glog.
- [x] Devcontainer/Docker tooling exists via `.devcontainer/` and `configure_devcontainer.sh`.
- [x] Main node: `src/eklt_node.cpp`.
- [x] Tracker: `src/tracker.cpp`, `include/tracker.h`.
- [x] Patch state: `include/patch.h`.
- [x] Optimizer: `src/optimizer.cpp`, `include/optimizer.h`.
- [x] Viewer: `src/viewer.cpp`, `include/viewer.h`.
- [x] Current event input: `dvs_msgs/EventArray`.
- [x] Current image input: `sensor_msgs/Image`, subscribed as `images`.
- [x] Current feature provider behavior: OpenCV `goodFeaturesToTrack` with Harris enabled.
- [x] Current frame patch behavior: patch centers plus optimizer log-gradient extraction from frame image.
- [x] Current example script: `test_example.sh`.
- [x] Current original example data path expected: `data/eklt_example/boxes_6dof.bag`.

Important current behavior:

- [x] Tracker waits for first image before processing events.
- [x] Events arriving before first image are dropped.
- [x] Features are detected with `cv::goodFeaturesToTrack`.
- [x] Patch updates and optimization are event-driven.
- [x] Replenishment depends on new frame images.

Implication:

- [x] Event-only path must replace "wait for first image" with provider-driven initialization image availability.
- [ ] Existing image-frame path must remain intact for original rosbag example demo.
- [x] Original frame-backed feature provider must become a first-class provider pair: `CFrameHarrisCandidateProvider + CFramePatchProvider`.

## Local Reuse Candidates

### `event-cameras-primitives`

- [x] Header-only C++ event primitives exist.
- [x] Provides `SEvent`, polarity conversion, event packet views, slicing.
- [x] Provides optional ROS2 EventPacket adapter in `Ros2EventCameraBridge.h`.
- [x] Uses `event_camera_codecs` behind optional compile definitions.
- [x] Requires C++20.

Use:

- [ ] Use concepts/API as reference for generic event batch shape.
- [ ] Use directly in ROS2 optional targets if C++20 target can be isolated.
- [ ] Avoid adding direct dependency to current C++11 ROS1 EKLT library until build plan is ready.

### `EventDataGenerationLib`

- [x] Has Python `EventStream` with `t_s`, `x`, `y`, `p01`.
- [x] Has event format I/O tests.
- [x] Has rendering helper producing BGR event preview images.
- [x] Has pyproject and reusable package style.

Use:

- [ ] Reuse design/test ideas for loaders, validation, rendering.
- [ ] Keep new `event_vision_utils.EventArray` separate because required convention is `t_us` and signed polarity.

### `x_events`

- [x] Contains alternate EKLT-like async feature tracker headers.
- [x] Contains event accumulator and HASTE-related trackers.

Use:

- [ ] Use as design reference for async tracker/provider separation.
- [ ] Check license/API before importing code.
- [ ] Prefer local minimal refactor of current EKLT first.

### `SuperEvent`

- [x] Python package `superevent` exists locally.
- [x] It targets event-based keypoint detection and descriptors.
- [x] It depends on PyTorch; ONNX support is optional.
- [x] It has inference, ONNX export, and pose evaluation utilities.

Use:

- [ ] Use as future design reference for detector-only sparse candidates.
- [ ] Do not implement or import SuperEvent in current stages.
- [ ] Do not require descriptors for EKLT initialization.
- [ ] Keep EKLT core independent from SuperEvent/PyTorch/ONNX.

### Existing `python/eklt_bridge`

- [x] Existing `python/pyproject.toml` names package `eklt-bridge`.
- [x] Scripts currently listed: `eklt-ros1-relay`, `eklt-sequence-source`.
- [x] Only pyproject found in current tree; package files not present in current checkout listing.

Use:

- [ ] Extend Python packaging carefully in Stage 1.
- [ ] Avoid depending on missing package modules until confirmed.

## Upstream References

### `fibar_lib`

- [x] ROS-free CMake library.
- [x] Apache-2.0.
- [x] Depends on CMake/gtest/clang-tidy, no ROS package dependency.
- [x] Best fit for C++ reconstruction core.

Use:

- [x] Vendor as submodule or external dependency.
- [x] Wrap behind local `event_recon_fibar_core::CFibarReconstructor`.

### `event_image_reconstruction_fibar`

- [x] ROS2 package using `fibar_lib`.
- [x] Subscribes to events and publishes reconstructed image frames.
- [x] Depends on `event_camera_msgs`, `event_camera_codecs`, `fibar_lib`, OpenCV, ROS2.

Use:

- [ ] Use as ROS2 debug/reference implementation.
- [ ] Do not use `/events/fibar_image` as primary EKLT input.

### `event_camera_msgs` and `event_camera_codecs`

- [x] Standard ROS event-camera message/codecs ecosystem.
- [x] Required for final ROS2 `/events` path.

Use:

- [ ] Stage 7 publisher and decoder use `EventPacket`.
- [ ] ROS2 EKLT node decodes packets through codec layer.

## Missing Pieces

- [x] ELOPE `.npz` loader, reusable outside EKLT.
- [x] Generic event tuple loader, reusable outside EKLT.
- [x] Event visualization utilities, reusable outside EKLT.
- [x] C++ FIBAR facade.
- [x] C++ FIBAR local patch readout.
- [x] Python wrapper for C++ FIBAR.
- [x] MATLAB wrapper documentation/example.
- [x] EKLT provider seam.
- [x] Sparse feature provider interface.
- [x] Patch provider interface.
- [x] Full-frame initialization path preserved as an alternative.
- [x] ROS1 event-only mode.
- [x] ROS2 EventPacket playback code path and dry-run codec verification.
- [x] Evaluation scripts and plots.
- [x] Full example demo scripts for original rosbag and ELOPE.

## Integration Decisions

- [x] Stage 1 starts in Python because ELOPE/generic dataset inspection is fastest there.
- [x] Stage 1 utility APIs should be general-purpose and migration-ready, even if first implementation is staged locally.
- [x] Generic Python utilities should eventually live in `EventDataGenerationLib` or a shared `event_vision_utils` package.
- [x] Generic C++ event utilities should use or extend `event-cameras-primitives`.
- [x] `rpg_eklt` should keep only EKLT-specific adapters, demos, evaluation scripts, and dependency glue once reusable pieces stabilize.
- [x] Devcontainer or Docker image is valid verification path when host ROS/FIBAR/Python deps are incomplete.
- [x] Full-frame initialization mode and candidate+local-patch initialization mode are alternatives; neither removes the other.
- [x] SuperEvent is future-only for current plan; current work prepares interfaces but does not implement it.
- [x] Future SuperEvent integration should require only a `CFeatureCandidateProvider` implementation.
- [x] FIBAR implementation source is upstream `fibar_lib`, not a handwritten local clone.
- [x] EKLT core gets provider abstraction before ROS2-native event-only node.
- [x] Original ROS1 example demo remains required pass condition.
- [x] ELOPE event-only example demo remains required pass condition.
- [x] Evaluation plots/stats are first-class acceptance artifacts, not optional extras.
