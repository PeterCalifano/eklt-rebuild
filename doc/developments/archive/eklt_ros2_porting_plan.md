# EKLT ROS2 Porting Plan

> **Archived migration plan.** The accepted ROS2 overlay no longer follows the
> hybrid/cutover sequence below. Current behavior is documented in
> `doc/ros2_event_only.md`; future multi-dataset and online work is governed by
> `doc/developments/dataset_and_online_streaming_plan.md`.

## Summary

Implement the ROS2 migration in three gated stages, with tests added and run at the end of each stage before moving on.

## Current ROS2 Overlay Status

The checkpointed template-upgrade plan supersedes the historical migration
sequence below for current implementation work.

- [x] Keep the ROS1 package and ROS2 overlay independently buildable.
- [x] Build the ROS2 `eklt_rebuild` package through `./build_ros2.sh`.
- [x] Consume the canonical ROS-free `eklt-rebuild` target without recompiling
      native sources in the ROS2 package.
- [x] Decode `event_camera_msgs/msg/EventPacket` through
      `event_camera_codecs`.
- [x] Delegate FIBAR initialization, scheduling, feature lifecycle, Ceres
      tracking, deterministic ordering, and gradient-cache release to
      `CEkltTrackerOrchestrator`.
- [x] Keep ROS2 ownership limited to transport, parameter loading, file/topic
      output, display-image publication, and optional PNG persistence.
- [x] Share one transport-neutral feature renderer with ROS1 and publish the
      ROS2 `bgr8` overlay at bounded rate and queue depth for standard tools.
- [x] Persist newly reconstructed finite-normalized FIBAR images only when
      explicitly requested, with stride and maximum-count bounds.
- [x] Decompose each accepted packet into FIBAR, remaining native EKLT, and
      ROS2 interface/output wall time; validate and plot the additive total
      without retaining timing history in the node.
- [x] Cover mono EventPacket tuple conversion and deterministic synthetic
      tracking in an ament GTest.
- [x] Provide converted legacy-bag, ELOPE `.npz`, and live DVXplorer
      EventPacket example demos through one common ROS2 runner.
- [x] Document the runnable overlay in `doc/ros2_event_only.md`.
- [ ] Validate a physical DVXplorer on the target device after its firmware and
      ROS2 source path are known.

The sequencing is intentional:

- [x] Stage 2 is a complete, usable hybrid release built around the existing ROS1 EKLT implementation plus ROS2-facing bridge tools.
- [x] Stage 2 is expected to be good enough to tag and archive as the last ROS1-based version before any native ROS2 port begins.
- [x] Stage 3 starts only after the stage-2 hybrid release is validated and tagged.

Defaults chosen for the final design:

- [x] Final ROS2 event interface: `event_camera_msgs/msg/EventPacket`
- [x] Final ROS2 config surface: native ROS2 parameters, not `gflags`
- [x] Final port shape: clean ROS2-only cutover in this repo, no dual ROS1/ROS2 build
- [x] Stage-2 hybrid path: ROS2-native frame-sequence source plus a small ROS1 relay for the existing EKLT node

Public interface targets:

- [ ] Stage 2 ROS2 topics: `/eklt/events` as `std_msgs/msg/UInt8MultiArray` carrying encoded generic event batches, `/eklt/image_raw` as `sensor_msgs/msg/Image` in `mono8`
- [ ] Stage 2 ROS2 visualization topics: `/eklt/rendered_frame`, `/eklt/event_preview`, and `/eklt/feature_tracks` as `sensor_msgs/msg/Image`
- [ ] Stage 2 ROS1 relay output: `/dvs/events` as `dvs_msgs/EventArray`, `/dvs/image_raw` as `sensor_msgs/Image`
- [ ] Stage 3 EKLT ROS2 node: keep internal subscription names `events` and `images`, with ROS2 launch remaps defaulting to `/eklt/events` and `/eklt/image_raw`
- [ ] Stage 3 EKLT ROS2 viewer output: preserve the annotated feature-track image on `/eklt/feature_tracks`
- [ ] Stage 3 config: preserve current parameter names where practical, but expose them as declared ROS2 params and YAML/launch config

## Stage 1: Catch2 and regression seams

- [x] Treat Catch2 as partially present already: reuse the existing `cmake/HandleCatch2.cmake`, `cmake_utils.cmake`, and test scaffolding, and wire them into the top-level build with the smallest possible CMake delta.
- [x] Copy only the minimal top-level patterns needed from the template project: `ENABLE_TESTS`, `ENABLE_FETCH_CATCH2`, inclusion of Catch2 helpers, and `add_subdirectory(tests)` when tests are enabled.
- [x] Remove the template placeholder tests and replace them with focused regression tests for logic that will be touched later.
- [x] Keep test seams minimal and local. Only extract pure helpers where current behavior is otherwise untestable without a ROS runtime.

Regression coverage to add now:

- [x] `Patch` event-buffer behavior: insertion order preservation inside the patch buffer, batch-size clipping, timestamp update after `getEventFramesAndReset()`, and deterministic event-frame accumulation for a small hand-checked event set.
- [x] Event ordering helper: the current sorted event insertion behavior used before processing should be pinned with out-of-order and equal-timestamp cases.
- [x] Image selection helper: the “latest frame before current event time” behavior should be pinned so ROS2 callback refactors do not change it.

Acceptance for stage 1:

- [ ] Catkin build still succeeds.
- [ ] Catch2 tests build and pass under `ctest`.
- [ ] No algorithm or runtime ROS behavior changes beyond testability seams.

## Stage 2: Full hybrid release using the existing ROS1 EKLT

Stage 2 is split into substeps so the generic bridge lands first, then validation and packaging are added without tying the release to one scene or renderer.

Stage 2 is not just a temporary adapter. It is the full functional pre-porting version:

- [ ] ROS2-facing data generation works end to end.
- [ ] The existing ROS1 EKLT remains the tracker used for real output.
- [ ] Visualization is available during the hybrid run.
- [ ] The resulting version is stable enough to tag before the native ROS2 port starts.

Build stage 2 as a small installable Python package inside this repo, not as one monolithic script.

Python package layout:

- [x] `python/eklt_bridge/raytracer/`: optional import helpers for upstream renderers
- [x] `python/eklt_bridge/messages/`: bridge transport and frame conversion helpers
- [x] `python/eklt_bridge/sources/`: pluggable source interfaces and adapters for frames-only or frame-plus-event producers
- [x] `python/eklt_bridge/ros2_source/`: ROS2 publisher node and CLI entrypoint
- [x] `python/eklt_bridge/ros1_relay/`: ROS1 relay node and CLI entrypoint
- [x] `python/eklt_bridge/visualization/`: small reusable helpers that render ROS2 preview images from frames and event batches without building a custom GUI
- [x] `python/eklt_bridge/config/`: typed config loading for paths, timing, frame size, topic names, and source-adapter settings

Stage-2 substeps:

- [x] Stage 2A: land the reusable Python package, message converters, and config layer with unit tests only.
- [ ] Stage 2B: land the generic ROS2 source, ROS2 preview visualization topics, and ROS1 relay path for a minimal fixture scene and verify EKLT can consume it.
- [ ] Stage 2C: add one command or launch-driven end-to-end demo that starts the full chain, writes EKLT tracks for a configured frame sequence, and exposes the visualization stream in ROS2.
- [ ] Stage 2D: freeze and tag the validated hybrid release as the archived ROS1-based baseline before any ROS2-native EKLT port begins.

Stage-2 data flow:

- [x] ROS2 source node can replay a frame sequence directly, independent of how frames were produced.
- [x] It publishes grayscale frames and encoded event batches derived from the same replay timeline.
- [x] It publishes `/eklt/events` as encoded generic event-batch bytes on `std_msgs/msg/UInt8MultiArray`.
- [x] It publishes `/eklt/image_raw` as `sensor_msgs/msg/Image`.
- [x] It publishes `/eklt/rendered_frame` as a ROS2 image preview of the rendered grayscale frame.
- [x] It publishes `/eklt/event_preview` as a ROS2 image preview generated from short event accumulations on the same source timeline.
- [ ] Standard `ros1_bridge` is used only for shared message types across ROS1 and ROS2.
- [x] A small ROS1 relay node subscribes to bridged ROS1 encoded event-batch bytes and ROS1 `sensor_msgs/Image`, converts the batches to `dvs_msgs/EventArray`, and republishes to the current EKLT ROS1 topics.
- [ ] The hybrid demo also bridges the ROS1 EKLT `feature_tracks` image back into ROS2 as `/eklt/feature_tracks` so the whole chain is viewable from ROS2 tools.

Stage-2 release intent:

- [ ] Treat the bridge path as a supported runtime mode, not as disposable scaffolding.
- [ ] Keep the bridge tools clean enough that they can remain in the repo after the ROS2 port as reusable utilities.
- [ ] Avoid stage-2 shortcuts that would make the archived hybrid tag hard to use later.

Stage-2 environment contract:

- [ ] The ROS2 source accepts explicit config paths and does not depend on local developer shell state.
- [ ] Frame production stays upstream of the bridge: any renderer or dataset exporter can be used if it writes an ordered image sequence.

Encoding and conversion decisions:

- [ ] Stage 2 writes an explicit generic event-batch payload and transports it across ROS1/ROS2 using `std_msgs/UInt8MultiArray`, because that keeps the hybrid bridge dependency-light and easy to validate.
- [ ] The ROS1 relay decodes only the event-batch transport produced by this source.
- [ ] Images are published as `mono8` with preserved timestamps shared with the event timeline.
- [ ] Preview images stay simple: rendered frames in `mono8`, event previews in `mono8`, and EKLT annotated tracks in `bgr8`.

CLI entrypoints to provide:

- [x] `eklt-sequence-source`
- [x] `eklt-ros1-relay`
- [x] `eklt-run-rosbag-bridge-demo`
- [ ] `eklt-preview-events`
- [ ] `eklt-run-hybrid-demo`

Stage-2 scope limits:

- [ ] No attempt to make the ROS1 relay generic for arbitrary event-camera encodings.
- [ ] No devcontainer overhaul unless a missing dependency blocks reproducible testing.
- [ ] No changes to EKLT’s tracking algorithm.
- [ ] No custom visualization GUI in this repo; visualization stays topic-based so standard ROS2 tools can consume it.

Acceptance for stage 2:

- [x] Python unit tests pass for event-batch transport, timestamp mapping, frame conversion, source adapters, and config parsing.
- [ ] End-to-end smoke test passes: sequence source -> `ros1_bridge` -> ROS1 relay -> current ROS1 EKLT.
- [ ] Smoke-test success criterion: EKLT receives frames and events, runs without waiting forever for the first image, and produces a non-empty tracks output on the deterministic sample run.
- [ ] ROS2 visualization smoke test passes: `/eklt/rendered_frame`, `/eklt/event_preview`, and bridged `/eklt/feature_tracks` publish non-empty image streams during the demo run.
- [ ] Generic sequence smoke test writes a non-empty EKLT tracks file.
- [ ] Hybrid demo is runnable through one documented command path rather than a manual multi-terminal recipe only.
- [x] The hybrid mode is documented as a first-class way to run EKLT from ROS2 before the native port exists.
- [ ] The hybrid release is tagged after validation, before any ROS2-native EKLT refactor lands.

## Stage 3: clean ROS2 port of EKLT interfaces

Stage 3 starts only after the stage-2 hybrid release has been validated and tagged.

Port the package to ROS2 as a clean cutover, keeping the tracking algorithm unchanged.

Build and package changes:

- [ ] Replace catkin build plumbing with `ament_cmake`.
- [ ] Use the ROS-valid package name `eklt_rebuild`, derived from the root
  `eklt-rebuild` library identity.
- [ ] Keep the node executable name `eklt_node`.
- [ ] Move launch to ROS2 Python launch files.
- [ ] Drop ROS1-only launch conveniences such as in-launch `rosbag play`; ROS2 bag playback stays external.

ROS2 interface changes:

- [ ] Replace `ros::NodeHandle`, `ros::Subscriber`, `ros::Time`, `ros::Rate`, and ROS1 spin/thread patterns with ROS2 equivalents.
- [ ] Replace `dvs_msgs/EventArray` ingestion with `event_camera_msgs/msg/EventPacket`.
- [ ] Use `event_camera_codecs` in C++ so the ROS2 node decodes packets through the standard codec layer rather than project-local packet parsing.
- [ ] Keep `sensor_msgs/msg/Image` input unchanged conceptually, using ROS2 `cv_bridge`.
- [ ] Port the existing viewer path to ROS2 so EKLT still publishes an annotated feature-track image topic rather than dropping visualization during the interface migration.
- [ ] Keep the viewer output topic-based and ROS2-native: publish `/eklt/feature_tracks` as `sensor_msgs/msg/Image` in `bgr8`.

Configuration changes:

- [ ] Replace `gflags` at the node boundary with declared ROS2 parameters.
- [ ] Convert `config/eklt.conf` into a ROS2 YAML params file with matching names where practical.
- [ ] Keep parameter meaning stable unless ROS2 integration requires a rename for clarity.
- [ ] Preserve topic remap flexibility through launch, not custom wrapper code.
- [ ] Preserve the existing viewer controls as ROS2 params where practical: `display_features`, `display_feature_id`, `display_feature_patches`, `arrow_length`, and `scale`.

Code-structure guidance:

- [ ] Keep core tracker, patch, optimizer, and viewer logic as close as possible to the current implementation.
- [ ] Isolate ROS2 transport, time, and parameter changes at the node, subscriber, and buffer boundary.
- [ ] Prefer a thin translation layer from decoded ROS2 events into the existing internal event representation before touching core tracking code.

Stage-3 useful cleanup that is in scope:

- [ ] Replace ROS1 time aliases in shared types with a project-local time alias or direct ROS2 time usage where needed.
- [ ] Normalize callback and worker-thread ownership so the ROS2 node is explicit about lifecycle and shutdown.
- [ ] Keep the stage-2 bridge package in the repo as an optional hybrid-validation and data-generation tool if it stays small; it must not constrain the ROS2 node design.
- [ ] Preserve the bridge-side source and visualization tools where they remain useful after the port for demos, regression testing, or future bag and simulation workflows.

Acceptance for stage 3:

- [ ] ROS2 build succeeds with `colcon`.
- [ ] Existing Catch2 regression tests still pass after the transport refactor.
- [ ] New ROS2-side tests pass for parameter loading, `EventPacket` decode to internal events, image callback ingestion, and event ordering/buffering invariants.
- [ ] End-to-end ROS2 smoke test passes: sequence source -> ROS2 EKLT, with non-empty tracks output on the deterministic sample run.
- [ ] ROS2 EKLT publishes a non-empty annotated feature-track visualization on `/eklt/feature_tracks`.

## Test plan

Stage 1:

- [ ] Run `ctest` for the new Catch2 suite.
- [ ] Gate stage 2 work on green unit tests.

Stage 2:

- [x] Add `pytest` for the Python package.
- [ ] Add one scripted hybrid smoke test that launches ROS1 EKLT, ROS2 sequence source, `ros1_bridge`, and the ROS1 relay.
- [ ] Check for non-empty tracks output and monotonic timestamps.
- [ ] Check for non-empty ROS2 visualization image streams on `/eklt/rendered_frame`, `/eklt/event_preview`, and `/eklt/feature_tracks`.
- [ ] Add one generic sequence integration test or smoke script that uses a small deterministic frame sequence and the full ROS bridge chain.
- [ ] Check that the sequence demo publishes both frames and events over a shared simulated timeline and that EKLT produces non-empty tracks.
- [ ] Keep the sequence demo deterministic enough that repeated runs have stable event counts and broadly stable track-output size.
- [ ] Before stage 3 begins, record the exact stage-2 validation command path and tag the passing hybrid version.

Stage 3:

- [ ] Keep stage-1 Catch2 tests as regression guards.
- [ ] Add ROS2-focused unit tests and launch or integration smoke tests.
- [ ] Reuse the same deterministic frame sequence as stage 2 so behavior is comparable across the cutover.
- [ ] Compare stage-2 and stage-3 outputs at least at the level of non-empty tracks, monotonic timestamps, and broadly comparable track count or runtime completion on the same sample run.
- [ ] Check that the ROS2 viewer output remains live and visually plausible on the same deterministic scenario.

## Assumptions and defaults

- [ ] Stage 2 source input is an ordered frame sequence plus either `fps` or explicit timestamps.
- [ ] A working mixed ROS1/ROS2 environment already exists for stage 2, so repo changes will not try to solve general multi-distro environment management.
- [ ] `event_camera_msgs` and `event_camera_codecs` remain acceptable dependencies for the later ROS2-native target in stage 3.
- [ ] The final repo is allowed to stop being catkin-first once stage 3 lands.
- [ ] Backward-compatibility code is kept only where it is directly useful for validation or migration; no dual-build compatibility layer is planned.
- [ ] Visualization should remain consumable by standard ROS2 tooling such as `rqt_image_view`, RViz image displays, or equivalent topic-based viewers, without requiring a custom app in this repo.
- [ ] The archived stage-2 tag should remain runnable as the reference ROS1-plus-bridge version after the native ROS2 port has landed.
