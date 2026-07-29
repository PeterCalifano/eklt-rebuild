# ROS2 Visualization and FIBAR Frame Export Plan

> **Archived completed subplan.** This Stage 14 work is accepted and described
> for users in `doc/ros2_event_only.md`. The checklist below remains as
> implementation history rather than an active plan.

## Goal and checkpoint boundary

Extend the open Stage 14 ROS2 event-only overlay with original-demo feature
visualization and optional FIBAR reconstruction export. The implementation
remains part of the single Stage 14 user-commit checkpoint; the sub-stages
below are implementation gates, not independent commit boundaries.

- [x] Publish an annotated feature-track image that standard ROS2 tools can
      display without a repository-owned GUI.
- [x] Save newly reconstructed FIBAR images as deterministic PNG files when
      explicitly enabled.
- [x] Keep tracking, scheduling, lifecycle, and optimization in the canonical
      ROS-free orchestrator.
- [x] Keep image rendering transport-neutral and PNG persistence confined to
      the ROS2 boundary.
- [x] Keep visualization and export disabled or allocation-free when unused.
- [x] Use the shared repository-root `config/` directory for every parameter.
- [x] Stop without committing after the complete revised Stage 14 index passes.

## Stage A - Shared ROS-free feature rendering

- [x] Add documented `SFeatureTrackRenderConfig` and `SRenderedTrackImage`
      contracts under `src/visualization/`, outside the algorithm core.
- [x] Implement a stateless `RenderFeatureTrackOverlay()` function using an
      owning `STrackerSnapshot`.
- [x] Normalize both frame-backed and FIBAR images through the existing finite
      image-normalization contract.
- [x] Preserve deterministic track colors, centers, flow arrows, optional
      warped patch outlines, optional identifiers, and elapsed-time text.
- [x] Omit lost tracks and reject invalid geometry, scale, arrow length, or
      timestamp inputs.
- [x] Return transport-neutral contiguous `bgr8` bytes, dimensions, stride, and
      timestamp without ROS types or retained tracker working state.
- [x] Delegate the existing ROS1 viewer drawing path to the shared renderer so
      ROS1 and ROS2 do not maintain duplicate overlay implementations.
- [x] Add Catch2 coverage for dimensions, deterministic pixels, lost-track
      omission, option toggles, input validation, and both image depths.

## Stage B - ROS2 publication and bounded PNG persistence

- [x] Add `/eklt/feature_tracks` publication as
      `sensor_msgs/msg/Image` with `bgr8` encoding.
- [x] Render only when visualization is enabled and the image topic has a
      subscriber.
- [x] Use snapshot timestamps and a configurable maximum rate to avoid
      playback-speed-dependent rendering load.
- [x] Keep the feature-image publisher depth at one so slow visualization
      clients cannot create an unbounded queue.
- [x] Add a documented stateful `CReconstructedFrameWriter` to the ROS2
      package.
- [x] Save only a new reconstruction timestamp, apply configured stride and
      maximum-count limits, and retain no frame history.
- [x] Encode the same normalized `mono8` buffer used by
      `/eklt/init_debug_image`.
- [x] Write each PNG to a temporary sibling and atomically rename it to
      `frame_<index>_t_<timestamp_us>.png`.
- [x] Validate output directory, stride, maximum count, and PNG compression.
- [x] Add ament GTest coverage for disabled output, deterministic filenames,
      decoded dimensions/pixels, duplicate timestamps, limits, and temporary
      file cleanup.

## Stage C - Demo controls and standard ROS tools

- [x] Add `--visualize` to the ROS2 rosbag demo and launch
      `rqt_image_view /eklt/feature_tracks` only when requested.
- [x] Start the standard viewer before playback and include it in bounded
      signal handling and process cleanup.
- [x] Add `--save-reconstructed-frames`, `--saved-frame-stride`,
      `--max-saved-frames`, and `--png-compression`.
- [x] Store PNGs below `<output-dir>/reconstructed_frames/`.
- [x] Report the saved-frame directory and count in `summary.json`.
- [x] Preserve fully headless behavior when neither visualization nor frame
      export is requested.
- [x] Document that PNG output is normalized display data rather than the exact
      floating-point FIBAR state.

## Stage D - Equivalent ELOPE dataset demo

- [x] Add a documented ELOPE `.npz` to EventPacket bag converter that reads
      the event array, honors explicit scalar geometry metadata when present,
      and otherwise uses the official 200-by-200 sensor contract.
- [x] Keep conversion streaming by bounded time windows and write the bag
      atomically without retaining encoded packet history.
- [x] Reuse the rosbag runner so ELOPE receives the same headless tracking,
      `rqt_image_view`, normalized FIBAR PNG, process-cleanup, and summary
      behavior.
- [x] Support the active Python or Conda environment through `PYTHON` without
      creating a repository-owned virtual environment.
- [x] Record and validate conversion provenance before reusing an existing
      EventPacket bag.
- [x] Document that EKLT consumes only two-dimensional event geometry and does
      not require camera intrinsics for this demo.
- [x] Run the repository ELOPE fixture through native ROS2 EKLT with non-empty
      tracks and readable bounded PNG output.

## Stage E - Acceptance and checkpoint handoff

- [x] Run native shared and static warnings-as-errors tests for the renderer
      and existing algorithm paths.
- [x] Run the ROS2 exact-index colcon build and complete ament test suite with
      one build job and the established memory cap.
- [x] Run a headless EventPacket bag test with PNG export and require non-empty
      tracks plus at least one readable timestamped PNG.
- [x] Verify the feature-track image topic publishes non-empty `bgr8` data
      while subscribed.
- [x] Verify no PNG directory or rendering allocation is produced when both
      features are disabled.
- [x] Run Bash, ShellCheck, YAML, XML, Doxygen, source-package, installed
      consumer, architecture, staged-byte parity, and `git diff --cached
      --check` gates.
- [x] Review file-level and public API documentation, functional block
      comments, compact C++ formatting, and the complete revised index.
- [x] Update the Stage 14 ledger and ignored `CONTEXT.md` with final evidence.
- [x] Stop for the user commit titled
      `Add the ROS2 event-only EKLT overlay`.
