# Event-Only EKLT Extension Plan

> **Archived plan.** This document preserves the exploratory Stage 0-9
> implementation sequence and intermediate evidence. The accepted architecture
> and final single-sequence results are documented in
> `doc/eklt_events_only.md`,
> `doc/developments/cpp_cuda_template_upgrade_plan.md`, and
> `doc/developments/official_elope_acceptance_report.md`. Paths, wrapper
> choices, counts, and checkboxes below are historical and must not be used as
> current implementation authority.

## Status

- [x] Stage 0 local repository audit performed.
- [x] Stage 0 upstream FIBAR and ROS event-camera references checked.
- [x] Stage 0 wrapper audit performed.
- [x] Stage 0 implementation map written.
- [x] Stage 0 plan formalizes goal-mode stop conditions.
- [x] Stage 0 future SuperEvent interface constraints recorded.
- [x] Stage 1 event tuple utilities implemented.
- [x] Stage 2 visualization utilities implemented.
- [x] Stage 3 FIBAR facade and wrappers implemented.
- [x] Stage 4 full ELOPE reconstruction example demo implemented.
- [x] Stage 5 EKLT provider seam implemented and verified in ROS1 runtime demos.
- [x] Stage 6 ROS1 event-only EKLT example demo completed in Noetic Docker.
- [x] Stage 7 ROS2 EventPacket playback and reconstruction debug completed in Jazzy Docker.
- [x] Stage 8 ROS2 event-only EKLT prototype implemented.
- [x] Stage 9 tuning, evaluation, and final docs completed.

## Objective

Make EKLT run from events only while preserving current ROS1 frame-plus-event behavior.

Primary working targets:

- Original EKLT example rosbag, using current ROS1/catkin package first.
- Official ELOPE `.npz` event tuple dataset, with default sensor size `200 x 200`.
- Generic event tuple interfaces usable by later datasets.

Hard pass condition:

- [x] Runnable original rosbag testing script exists and completes.
- [x] Runnable ELOPE testing script exists and completes.
- [x] Original rosbag and ELOPE scripts write non-empty tracks.
- [x] Completed ROS1 example demos write output stats and plots.
- [x] If ground truth files are present, evaluation plots/stats use them.
- [x] If ground truth files are absent, evaluation writes explicit non-failing `gt_status: unavailable`.

Use wording rule:

- Full runnable examples are named `example demos`.
- Narrow automated checks are named `tests`.
- Do not use test-only labels for full example demos.

## Design

Keep these boundaries:

- `event_vision_utils`: Python event tuple loading, validation, slicing, visualization, dataset example demos, evaluation helpers.
- `event_recon_fibar_core`: C++ facade over FIBAR, full-frame readout, local patch readout, display normalization, direct wrappers.
- `eklt_core`: tracker-facing event/image/candidate/patch provider abstractions, no ROS2/FIBAR/ELOPE/Python/MATLAB/SuperEvent dependencies.
- `eklt_ros1`: current ROS1 EKLT path plus event-only mode for original rosbag testing.
- `eklt_ros2`: EventPacket playback, reconstruction debug node, final events-only node.

Two initialization alternatives must coexist:

```text
full-frame path:
  SImageFrame
    -> frame/FIBAR full-image feature detection
    -> EKLT feature init/reinit
```

```text
candidate + local patch path:
  SFeatureCandidate
    -> CFeaturePatchProvider local intensity + gradients
    -> EKLT feature init/reinit
```

Baseline event-only data flow:

```text
ELOPE .npz or rosbag events
  -> EventArray/EventBatch
  -> FIBAR C++ reconstructor
  -> CFibarHarrisCandidateProvider + CFibarPatchProvider
  -> EKLT feature init/reinit
  -> EKLT async event tracking
  -> tracks, debug images, stats, plots
```

Full-frame FIBAR remains available for debugging and baseline feature detection. Local FIBAR patch readout becomes the preferred online EKLT initialization primitive when candidates are already available. EKLT tracking remains asynchronous and event-driven.

Future SuperEvent model:

```text
CSuperEventCandidateProvider
  -> SFeatureCandidate only
  -> CFibarPatchProvider
  -> EKLT feature init/reinit
```

SuperEvent is a future candidate provider only. Do not implement it in current stages.

C++ naming convention:

- [x] C++ classes use `C*` prefix, e.g. `CFibarReconstructor`.
- [x] C++ structs use `S*` prefix, e.g. `SFeatureCandidate`.
- [x] C++ enums use `E*` prefix, e.g. `EImageRequestReason`.
- [x] C++ type aliases and traits use `T*` prefix when added.
- [x] Python dataclasses and modules keep normal Python naming.

## What To Use

- [x] Existing devcontainer/Docker tooling:
  - Use `.devcontainer/`, `configure_devcontainer.sh`, or a purpose-built Docker image to run and verify implementation when host ROS/FIBAR/MATLAB/Python deps are missing or inconsistent.
  - Prefer containerized verification for full example demos when native host setup cannot satisfy ROS1/ROS2 dependency mix.
  - Keep commands reproducible and documented, not dependent on developer shell state.

- [x] Current `rpg_eklt` ROS1/catkin tracker:
  - Use `src/tracker.cpp`, `include/tracker.h`, `include/patch.h`, `include/optimizer.h`.
  - Preserve current frame-camera mode and `test_example.sh` behavior.
  - Add provider seam later instead of replacing tracker wholesale.

- [x] `event-cameras-primitives`:
  - Use for C++ event concepts, packet views, slicing, optional ROS2 EventPacket decode adapter.
  - Reuse `include/event_primitives/events/Event.h`.
  - Reuse `include/event_primitives/events/EventPacket.h`.
  - Reuse `include/event_primitives/events/EventPacketView.h`.
  - Reuse `include/event_primitives/adapters/Ros2EventCameraBridge.h` for `event_camera_codecs` integration.
  - Note: requires C++20, so keep it out of current ROS1 C++11 build unless added as isolated optional target or adapter. --> if needed you can port c++11 then deprecated, features to ensure they compile in c++20. minimal changes only.

- [x] `EventDataGenerationLib`:
  - Reuse ideas and tests from `python/eventDataGenLibPy/io/event_io.py`.
  - Reuse rendering ideas from `python/eventDataGenLibPy/visualization/event_rendering.py`.
  - Do not depend on its current `EventStream` directly because it uses seconds and `p01`; new EKLT utilities should use microseconds and signed polarity.

- [x] `x_events`:
  - Use as reference for alternative async EKLT abstractions and event accumulation.
  - Do not import code blindly; licensing/API fit must be checked before reuse.

- [x] `SuperEvent`:
  - Use as future design reference for detector-only sparse feature candidates.
  - Current repo uses PyTorch and optional ONNX paths, so keep it out of current implementation dependencies.
  - Do not implement `CSuperEventCandidateProvider` now; only design interfaces so it can be added later without EKLT refactor.

- [x] Upstream `fibar_lib`:
  - Use as preferred FIBAR implementation source.
  - It is ROS-free CMake and intended for event image reconstruction.
  - Vendor as submodule or external dependency in Stage 3.
  - Wrap behind local facade so EKLT does not depend on upstream API shape.

- [x] Upstream `event_image_reconstruction_fibar`:
  - Use as ROS2 node/reference behavior only.
  - Do not make EKLT consume `/events/fibar_image` as primary path.

- [x] `event_camera_msgs` and `event_camera_codecs`:
  - Use as ROS2 transport standard for `/events: event_camera_msgs/msg/EventPacket`.
  - Prefer `event_camera_codecs` for C++ decode/encode.

## What Not To Use

- [x] Do not implement E2VID, HyperE2VID, FireNet, or neural reconstruction.
- [x] Do not implement SuperEvent in current stages.
- [x] Do not add PyTorch, LibTorch, ONNX Runtime, or SuperEvent dependencies to EKLT core.
- [x] Do not require descriptors for EKLT initialization.
- [x] Do not add GPU/checkpoint reconstruction.
- [x] Do not add custom primary ROS2 event message.
- [x] Do not force C ABI for wrappers.
- [x] Do not duplicate FIBAR algorithm logic in Python or MATLAB.
- [x] Do not feed display-normalized images into EKLT unless an explicit test mode requests it.

## Stage 0: Audit And Planning

Deliverables:

- [x] `doc/developments/archive/event_only_eklt_extension_plan.md`
- [x] `doc/developments/archive/event_only_integration_audit.md`
- [x] `doc/developments/archive/event_only_wrapper_audit.md`
- [x] `doc/developments/archive/event_only_implementation_map.md`

Exit criteria:

- [x] Reusable local modules identified.
- [x] Missing modules identified.
- [x] Wrapper strategy selected.
- [x] FIBAR source strategy selected.
- [x] SuperEvent future integration recorded as interface-only non-goal.
- [x] Example-demo and test naming policy recorded.
- [x] Goal-mode stop conditions recorded.
- [x] No algorithm/runtime implementation added.

## Stage 1: Generic Event Tuple Utilities

Deliver:

- [x] Reusable Python event tuple API, staged locally only if external repo move is deferred.
- [x] Reusable ELOPE `.npz` loader, generic enough for dataset utilities outside EKLT.
- [x] Reusable generic `.npz` event tuple loader.
- [x] Dataset adapter base class returning one algorithm-facing `EventArray` format.
- [x] Reusable time/count slicers.
- [x] EKLT-local adapters only where needed to call FIBAR/EKLT providers.

Preferred permanent homes:

- [x] Put Python `EventArray`, loaders, validation, slicing, and dataset utilities in `EventDataGenerationLib` or a shared `event_vision_utils` package.
- [x] Keep C++ EventPacket bridge code dependency-gated and isolated for later extraction to `event-cameras-primitives`.
- [x] Keep generic Python utilities under the staged shared `event_vision_utils` package, not under tracker modules.

Local staging rule:

- [x] If implementation is staged inside `rpg_eklt`, use package/module names, dataclasses, tests, and public interfaces intended for later extraction.
- [x] Do not import EKLT, ROS, FIBAR, or tracker-specific types into generic utility modules.
- [x] Keep migration notes in docstrings or module README: target external repo, expected dependency direction, and extraction checklist.
- [x] Avoid path assumptions that only work inside `rpg_eklt`.
- [x] Keep API stable so later move plus dependency replacement does not break EKLT example demos.

Possible local staging files, only if external repo implementation is deferred:

- [x] `python/event_vision_utils/core/event_array.py`
- [x] `python/event_vision_utils/core/timestamps.py`
- [x] `python/event_vision_utils/core/validation.py`
- [x] `python/event_vision_utils/io/elope_npz.py`
- [x] `python/event_vision_utils/io/generic_npz.py`
- [x] `python/event_vision_utils/io/dataset_adapter.py`
- [x] `python/event_vision_utils/slicing/time_slicer.py`
- [x] `python/event_vision_utils/slicing/count_slicer.py`

Core API:

```python
@dataclass
class EventArray:
    x: np.ndarray
    y: np.ndarray
    p: np.ndarray
    t_us: np.ndarray
    width: int
    height: int
    frame_id: str = "event_camera"
```

Behavior:

- [x] Normalize polarity to signed `int8` values `{-1, +1}`.
- [x] Store timestamps as `int64` microseconds.
- [x] Validate monotonic timestamps, coordinate bounds, equal lengths, finite numeric values.
- [x] Keep ELOPE default `width=200`, `height=200`.
- [x] Generic loader accepts configurable keys/column order.
- [x] Use conventions compatible with `EventDataGenerationLib` conversion helpers and `event-cameras-primitives` C++ event views.

Tests:

- [x] `test_event_array.py`
- [x] `test_polarity_normalization.py`
- [x] `test_timestamp_normalization.py`
- [x] `test_elope_loader.py`
- [x] `test_generic_npz_loader.py`
- [x] `test_time_slicer.py`

Exit criteria:

- [x] Official ELOPE `.npz` loads and validates.
- [x] Generic Nx4 `.npz` loads and validates.
- [x] Tests pass without ROS.
- [x] Generic utility modules have no EKLT imports.
- [x] Extraction target and dependency contract are documented.

## Stage 2: Event Visualization

Deliver:

- [x] `python/event_vision_utils/viz/accumulation.py`
- [x] `python/event_vision_utils/viz/polarity_image.py`
- [x] `python/event_vision_utils/viz/time_surface.py`
- [x] `python/event_vision_utils/viz/event_rate.py`
- [x] `python/event_vision_utils/viz/video_writer.py`
- [x] `python/event_vision_utils/examples/visualize_elope_npz.py`

CLI:

```bash
python -m event_vision_utils.examples.visualize_elope_npz \
  --input data/elope/example.npz \
  --mode polarity_rgb \
  --fps 100 \
  --output outputs/elope_events.mp4
```

Exit criteria:

- [x] Event preview video or PNG sequence generated.
- [x] Event-rate plot generated.
- [x] One bounded 2-by-3 event-cloud figure shows views from ±X, ±Y, and
      ±time with polarity coloring.
- [x] No reconstruction code introduced.

## Stage 3: FIBAR C++ Facade And Wrappers

Deliver:

- [x] Vendor or external dependency setup for `fibar_lib`.
- [x] Local C++ facade:
  - [x] `SEvent`
  - [x] `SEventBatchView`
  - [x] `SFibarConfig`
  - [x] `SReconstructedImageView`
  - [x] `SLocalFeaturePatch`
  - [x] `CFibarReconstructor`
- [x] Display normalization helper.
- [x] Python direct wrapper using pybind11/setuptools C++ extension.
- [x] MATLAB wrapper docs and optional gtwrap/MEX example.

Facade behavior:

- [x] Accept contiguous `x/y/p/t_us` arrays.
- [x] Return latest-causal full-frame float image for debugging and baseline full-frame detection.
- [x] Return latest-causal local patch with intensity, gradients, valid mask, and quality metrics.
- [x] Own image memory in C++ and copy to wrapper output unless safe zero-copy ownership is implemented.
- [x] Expose finite `float32` internal image.
- [x] Keep display-only `uint8` image separate.

Tests:

- [x] C++ finite image output test.
- [x] Latest-causal timestamp test.
- [x] Local patch readout shape/border/gradient test.
- [x] Display normalization test.
- [x] Python wrapper test calling C++.

Exit criteria:

- [x] FIBAR core produces finite image from events.
- [x] FIBAR core supports both full-frame and local patch readout.
- [x] Python wrapper uses C++ core.
- [x] No FIBAR logic duplicated in Python/MATLAB.

## Stage 4: Full ELOPE Reconstruction Example Demo

Deliver:

- [x] `scripts/run_elope_reconstruction_example_demo.sh`
- [x] `python/event_vision_utils/examples/reconstruct_elope_fibar.py`
- [x] `python/event_vision_utils/examples/debug_fibar_patches.py`

Artifacts:

- [x] `outputs/elope_reconstruction_real/summary.json`
- [x] `outputs/elope_reconstruction_real/reconstruction.mp4`
- [x] `outputs/elope_reconstruction_real/fibar_patches.mp4`
- [x] `outputs/elope_reconstruction_real/events_preview.mp4`
- [x] `outputs/elope_reconstruction_real/plots/event_rate.png`
- [x] `outputs/elope_reconstruction_real/plots/event_stream_3d_views.png`
- [x] `outputs/elope_reconstruction_real/plots/patch_quality.png`

Exit criteria:

- [x] Full example demo runs from one command.
- [x] Reconstruction video shows structure.
- [x] Patch debug video shows candidate features, accepted/rejected candidates, local patches, and gradient quality.
- [x] Summary includes event counts, duration, reconstruction frames, runtime.
- [x] Event preview uses 10 ms accumulation bins encoded at 100 frames per
      second without retaining the complete frame sequence in RAM.
- [x] Verified on official ELOPE `data/elope/test/0028.npz`, not fixture data.

## Stage 4A: Dense ELOPE Diagnostic Videos

Deliver:

- [x] Add a reusable, deterministic EKLT track-dot video renderer.
- [x] Add the track video to the official ELOPE pipeline after ROS2 tracking.
- [x] Replace the sparse horizontal FIBAR patch strip with a fixed 2-by-4
      mosaic beside an enlarged event panel.
- [x] Expose bounded output-size controls through the reconstruction scripts.
- [x] Stream encoded frames without retaining complete videos in RAM.

Artifacts:

- [x] `outputs/official_elope_event_only/tracking/eklt_tracks.mp4`
- [x] Enlarged
      `outputs/official_elope_event_only/reconstruction/fibar_patches.mp4`

Exit criteria:

- [x] Track dots use stable per-track colors and remain aligned with the ELOPE
      event timeline.
- [x] Track rendering rejects malformed or out-of-bounds rows and records its
      frame count, resolution, and timing policy.
- [x] The patch mosaic has constant dimensions, labeled patch slots, and no
      reserved white strip.
- [x] Focused synthetic tests cover track parsing, time alignment, dot
      rendering, mosaic layout, and streaming video output.
- [ ] A bounded official ELOPE run produces both videos with one ffmpeg thread
      and records peak resident memory.

Validation evidence:

- [x] Sixty-one `event_vision_utils` tests pass; four wrapper-dependent tests are
      skipped in the current environment.
- [x] Official `0028.npz` plus the accepted 10,548-row ROS2 track file produced
      4,879 800-by-800 frames at exactly 100 fps for 71 tracks. Peak resident
      memory was 185,448 KiB with no swap.
- [x] The fake-native integration encoded and visually validated the default
      1200-by-800 2-by-4 patch layout.
- [ ] Rerun the complete official patch video after the Python gtwrap module is
      available in its checkpointed wrapper stage. The current run stopped at
      the documented missing-native-wrapper gate rather than building that
      later stage early.

## Stage 4B: Cumulative Processing-Time Profile

Chart contract:

- [x] Analytical question: how is each ROS2 EventPacket processing step divided
      between FIBAR reconstruction, EKLT tracking, and remaining interface or
      output work over the event timeline?
- [x] Use a stacked-area composition chart with event time on the horizontal
      axis and milliseconds per packet on the vertical axis.
- [x] Stack FIBAR first, EKLT excluding FIBAR second, and total-step remainder
      third. Draw the measured total as a separate dark boundary line so it is
      not double-counted as another additive band.
- [x] Use explicit blue, orange, and neutral-grey fills with a dark total line;
      retain labels and boundaries so interpretation does not depend on color
      alone.

Deliver:

- [x] Measure FIBAR and non-FIBAR EKLT wall time in the ROS-free orchestrator
      with `std::chrono::steady_clock`.
- [x] Measure the complete ROS2 packet callback and write one bounded CSV row
      per accepted packet without retaining timing history in the node.
- [x] Add a reusable parser and Matplotlib renderer for
      `plots/processing_time_cumulative.png`.
- [x] Integrate timing collection and plotting into the common rosbag runner
      and official ELOPE pipeline summary.

Exit criteria:

- [x] Timing rows are finite, nonnegative, timestamp ordered, and satisfy
      `fibar_ms + eklt_ms + overhead_ms == total_ms` within floating-point
      tolerance.
- [x] Focused C++ and Python tests cover timing decomposition, CSV validation,
      stacked boundaries, and summary metadata.
- [x] The final exported chart has readable labels, an explicit unit-bearing
      subtitle, a stable palette, and no clipping or legend ambiguity.
- [x] A bounded official ELOPE run produces the timing CSV and cumulative plot
      without materially increasing resident memory.

Evidence:

- [x] Exact-index shared and static warnings-as-errors builds each pass 47/47
      CTests; the installed consumers exercise the invalid-before-first-batch
      timing contract.
- [x] Exact ROS2 Jazzy colcon reports ten tests with zero errors, failures, or
      skips.
- [x] Six strict timing-parser/plot tests and six ELOPE converter tests pass.
- [x] The first 200 EventPackets converted from official `0028.npz` produce
      200 additive timing rows, 4,639 track rows across 37 tracks, and full
      represented-duration coverage.
- [x] The maximum timing decomposition error is
      `3.552713678800501e-15 ms`. The 1600-by-900 plot was inspected at full
      frame with its title, unit-bearing subtitle, legend, axes, percentile
      badge, and total boundary visible.
- [x] The complete bounded run finishes in 14.80 seconds with 82,924 KiB
      maximum resident memory and no swaps.

## Stage 4C: Generated Plot Label And Scale Audit

Chart contract:

- [x] Inventory every project-owned analytical PNG generator and map each
      output to a descriptive title, axis labels, units or explicit
      count/category scales, tick values, and any legend or color meaning.
- [x] Start reader-facing titles and labels with a capital letter while
      preserving conventional lowercase mathematical symbols such as
      `x`, `y`, and `t` within coordinate expressions.
- [x] Express physical units in square brackets and name dimensionless axes as
      counts, ranks, row indices, or other explicit scales.
- [x] Keep titles neutral and descriptive; put sampling, bin-width, coordinate,
      and polarity details in subtitles or annotations.

Deliver:

- [x] Bring the six EKLT track-summary plots, reusable event-rate plot,
      FIBAR patch-quality plot, six-view event-cloud figure, and ROS2
      processing-time plot under the common title/label/unit contract.
- [x] Preserve fixed-size, bounded-memory rendering and deterministic output.
- [x] Add focused tests that reject missing or lowercase reader-facing labels
      and missing unit/scale metadata.
- [x] Render representative outputs from project-owned generators and inspect
      the complete images for clipping, legibility, and misleading scales.

Exit criteria:

- [x] Every non-empty generated analytical plot has a visible capitalized
      title, labeled axes, numeric tick values, and units or an explicit
      dimensionless scale.
- [x] The six-view event cloud keeps both projected coordinate labels and
      scales visible in every view, names the viewing direction, and explains
      polarity without relying on color alone.
- [x] Empty-data plots retain the same title, axes, units/scales, and bounded
      plot frame as their non-empty counterparts.
- [x] Focused plot tests, Python compilation, first-argument definition-layout
      checks, and whitespace checks pass.

Evidence:

- [x] The inventory found ten analytical PNG outputs from five project-owned
      generators; no MATLAB analytical plot generator is present.
- [x] The official ELOPE track and event artifacts regenerated five tracker
      plots, the reusable event-rate plot, and the six-view event cloud.
      Representative ground-truth error and patch-quality inputs exercised the
      two conditionally generated plots; the accepted ROS2 timing CSV exercised
      the staged-area profile.
- [x] Full-frame and contact-sheet inspection found no clipped title, axis,
      tick, unit, legend, or scale. A first reader pass found metric text
      obscured by dense fills; the shared PIL chart style now draws one neutral
      metric badge above plot data.
- [x] Seventy-four focused `event_vision_utils` and timing-plot tests pass;
      four native-wrapper-dependent tests skip at the existing checkpoint.
      The regenerated official ELOPE tracking directory passes
      `evaluate_outputs.py`.
- [x] The complete official ELOPE track-summary regeneration peaked at
      92,348 KiB resident memory with no swaps under the 4-GiB process limit.
      The reviewed gallery is under `/tmp/eklt-plot-audit.VcvQv1/`.
- [x] The track x-y plot uses the complete advertised sensor plane with fixed
      zero-origin limits (`0..width-1`, `0..height-1`) and image-convention
      downward y. ROS event messages and ELOPE metadata/contract are
      authoritative; explicit dimensions are required only when the summary
      has no geometry-bearing event source.

## Stage 5: EKLT Initialization Provider Seam

Deliver:

- [x] `SImageFrame`
- [x] `EImageRequestReason`
- [x] `CInitializationImageProvider`
- [x] `SFeatureCandidate`
- [x] `SLocalFeaturePatch`
- [x] `CFeatureCandidateProvider`
- [x] `CFeaturePatchProvider`
- [x] Feature initializer consuming `SFeatureCandidate + SLocalFeaturePatch`
- [x] `CFrameCameraImageProvider`
- [x] `CFibarImageProvider`
- [x] `CFrameHarrisCandidateProvider` preserving current `goodFeaturesToTrack(..., useHarrisDetector=true)` path.
- [x] `CFramePatchProvider` preserving current frame-image patch and log-gradient extraction path.
- [x] `CFibarHarrisCandidateProvider` / `CFibarPatchProvider`

Rules:

- [x] `eklt_core` has no ROS2 headers.
- [x] `eklt_core` has no FIBAR headers.
- [x] `eklt_core` has no SuperEvent, PyTorch, LibTorch, or ONNX headers.
- [x] Keep substantial non-template `eklt_core` behavior in `.cpp` files while
      retaining public declarations and data contracts in headers.
- [x] Compile provider, normalization, photometric, FIBAR, and adapter
      implementations into the single published `libeklt-rebuild` library.
- [x] Treat Ceres as a required EKLT dependency because the complete native
      tracking implementation is not functional without photometric
      optimization.
- [x] Let `CPhotometricOptimizer` own its Ceres solver options and gradient
      caches directly; do not retain a PIMPL solely to hide a required
      dependency.
- [x] Keep FIBAR as a supporting EKLT implementation within the same published
      library; it is not required to form an independently usable product.
- [ ] Revisit substantial inline bodies in legacy ROS1 headers only during the
      later algorithm/source consolidation; do not mix that cleanup into the
      ROS-free core-layout batch.
- [x] Current ROS1 frame-camera path remains default.
- [x] Original EKLT frame feature provider remains a first-class `CFeatureCandidateProvider`, not a temporary compatibility hack.
- [x] Full-frame initialization path remains supported as an alternative.
- [x] Candidate + local patch initialization path is added as an alternative, not as replacement for full-frame mode.
- [x] Future SuperEvent integration only needs a new `CFeatureCandidateProvider`.
- [x] Current stages use a mock future SuperEvent provider only in tests; no real SuperEvent import.

Tests:

- [x] Mock provider test.
- [x] Original EKLT frame feature provider test.
- [x] Frame patch provider test.
- [x] FIBAR provider test.
- [x] Provider interchangeability test.
- [x] Candidate + patch initialization test that does not require full `SImageFrame`.
- [x] Mock future SuperEvent provider + FIBAR patch provider compatibility test.

Exit criteria:

- [x] Original frame-camera EKLT behavior preserved.
- [x] Original EKLT frame feature provider remains available for normal frame-backed runs.
- [x] Full-frame FIBAR feature detection remains available for baseline/debug.
- [x] FIBAR provider can initialize features without `/image_raw`.
- [x] EKLT tracker refactor can initialize from externally supplied sparse candidates plus local patches.

## Stage 6: ROS1 Event-Only EKLT Example Demo

Deliver:

- [x] ROS1 event-only mode using `dvs_msgs/EventArray`.
- [x] `scripts/run_original_rosbag_example_demo.sh`
- [x] `scripts/run_ros1_event_only_example_demo.sh`
- [x] `scripts/evaluate_outputs.py`
- [x] `scripts/summarize_eklt_tracks.py`

Artifacts for each run:

- [x] `outputs/<run_name>/tracks.txt`
- [x] `outputs/<run_name>/summary.json`
- [x] `outputs/<run_name>/plots/active_tracks.png`
- [x] `outputs/<run_name>/plots/track_lifetimes.png`
- [x] `outputs/<run_name>/plots/reinit_timeline.png`
- [x] `outputs/<run_name>/plots/gt_error.png` when GT available.

Exit criteria:

- [x] Original rosbag example demo completes.
- [x] ROS1 event-only example demo completes.
- [x] Event-only baseline uses `CFibarHarrisCandidateProvider + CFibarPatchProvider`.
- [x] Full-frame mode remains runnable.
- [x] Track files are non-empty.
- [x] Evaluation stats and plots generated.
- [x] Missing GT is recorded as `gt_status: unavailable` when GT files are absent.

Verification note:

- [x] Python/native FIBAR tests pass on host: `43 passed, 1 skipped`.
- [x] Header-only provider smoke accepts reconstructed `CV_32F` images.
- [x] FIBAR C++ facade smoke compiles and runs.
- [x] Launch XML and shell script syntax checks pass.
- [x] Full ROS1/catkin demo execution verified in Noetic Docker.

## Stage 7: ROS2 EventPacket Playback And Reconstruction Debug

Deliver:

- [x] `.npz` publisher to `/events`.
- [x] EventPacket encode/decode adapter.
- [x] C++ reconstruction debug node.
- [x] Python reconstruction debug node.
- [x] `scripts/run_ros2_elope_playback_test.sh`
- [x] `scripts/run_ros2_reconstruction_debug_example_demo.sh`

Rules:

- [x] Use `event_camera_msgs/msg/EventPacket`.
- [x] Use `event_camera_codecs` when available.
- [x] Debug image topic is not EKLT input path.

Exit criteria:

- [x] ELOPE publishes standard EventPacket stream.
- [x] Decode preserves `x/y/p/t`.
- [x] Debug reconstruction image publishes.

Verification note:

- [x] Pure `mono` EventPacket encode/decode tests pass and preserve `x/y/p/t`.
- [x] ROS2 playback script dry-run decode passes.
- [x] Official ELOPE `data/elope/test/0028.npz` dry-run decode passes with 386785 events and 2440 packets.
- [x] Optional C++ ROS2 reconstruction debug package implemented under `ros2/eklt_rebuild`.
- [x] ROS2 EventPacket publish/debug runtime verified in Jazzy Docker with `event_camera_msgs` and `event_camera_codecs`.

## Stage 8: ROS2 Event-Only EKLT

Deliver:

- [x] ROS2 EKLT events-only node.
- [x] Native ROS2 parameters.
- [x] Track/debug/stat topics.
- [x] `scripts/run_ros2_elope_event_only_example_demo.sh`
- [x] Provider parameters: `feature_provider:=fibar_harris`, `patch_provider:=fibar`.

Exit criteria:

- [x] Node starts without `/image_raw`.
- [x] Tracks publish and write to file.
- [x] Init debug images publish.
- [x] Evaluation stats and plots generated.
- [x] Future `feature_provider:=superevent` value is documented as not implemented yet.

Status note:

- [x] Native command writes `summary.json` when dependencies and node executable are available.
- [x] Future `feature_provider:=superevent` is documented as not implemented.
- [x] Native ROS2 event-only node exists as prototype.
- [x] ROS-free Ceres photometric patch tracker is wired into the ROS2 node.
- [x] Official ELOPE `data/elope/test/0028.npz` runs through reconstruction and ROS2 event-only tracking in Jazzy Docker.
- [x] Official ELOPE tracking output is non-empty: 71 tracks and 10548 track rows.
- [x] Reinitialization is observable on official ELOPE: 54 tracks start more than 1.0 s after the first initialization.
- [x] ROS1 remains the reference for full lifecycle/viewer parity.

## Stage 9: Tuning And Final Documentation

Deliver:

- [x] `doc/event_tuple_format.md`
- [x] `doc/fibar_cpp_core.md`
- [x] `doc/fibar_python_wrapper.md`
- [x] `doc/fibar_matlab_wrapper.md`
- [x] `doc/eklt_events_only.md`
- [x] `doc/known_limitations.md`
- [x] README updates.

Final acceptance:

- [x] Original rosbag example demo passes.
- [x] Official ELOPE event-only example demo passes.
- [x] Original rosbag and official ELOPE event-only track outputs are non-empty.
- [x] Original rosbag and official ELOPE event-only output folders contain `summary.json`.
- [x] Original rosbag and official ELOPE event-only output folders contain plots.
- [x] Missing GT is recorded as `gt_status: unavailable` when GT files are absent.
- [x] Docs list exact commands and expected artifacts.
- [x] If host environment cannot run required demos, devcontainer/Docker verification path is documented and used.
- [x] Docs state SuperEvent is future-only and not part of current completion.

## Goal-Mode Stop Conditions

Goal complete only when all required pass conditions for active stage are true.

For whole project goal, complete only when:

- [x] Original rosbag example demo runs end to end.
- [x] Official ELOPE event-only example demo runs end to end.
- [x] `scripts/evaluate_outputs.py outputs/original_rosbag_example` passes.
- [x] `scripts/evaluate_outputs.py outputs/official_elope_event_only/tracking` passes when official ELOPE ROS2 demo output is generated.
- [x] Track files are non-empty for original rosbag and official ELOPE event-only runs.
- [x] Evaluation plots/stats exist for original rosbag and official ELOPE event-only runs.
- [x] Missing GT is documented in `summary.json` when GT files are absent.
- [x] README/docs list exact commands.

Do not mark complete when:

- [ ] Only unit tests pass.
- [ ] Only one of rosbag or ELOPE runs.
- [ ] Example demo runs but tracks are empty.
- [ ] Tracks exist but evaluation plots/stats are missing.
- [ ] GT files exist but GT metrics are skipped.
- [ ] Required scripts are missing.
- [ ] Required dependency absence is not documented with fallback/skip policy.
- [ ] Host dependency failure exists but devcontainer/Docker fallback was not attempted or documented.
- [ ] Docs or scripts require real SuperEvent for current-stage completion.

Mark blocked only when same blocker repeats for three consecutive goal turns and no meaningful progress remains:

- [ ] Required dataset path unavailable and cannot be inferred.
- [ ] Required rosbag path unavailable and cannot be inferred.
- [ ] Required dependency cannot be installed, vendored, or bypassed for current stage.
- [ ] Build/runtime toolchain prevents required example demo from running on host and in available devcontainer/Docker image.
- [ ] User decision needed for license, dependency, or data path.

When blocked, record:

- [ ] Exact failed command.
- [ ] Missing path/dependency.
- [ ] Relevant log excerpt.
- [ ] Next user action needed.

## Sources Checked

- `fibar_lib`: https://index.ros.org/p/fibar_lib/
- `event_image_reconstruction_fibar`: https://index.ros.org/p/event_image_reconstruction_fibar/
- `event_camera_codecs`: https://github.com/ros-event-camera/event_camera_codecs
- `event_camera_msgs`: https://github.com/ros-event-camera/event_camera_msgs
- SuperEvent interface addendum: `/home/peterc/devDir/codeRepoPeterC/codex_prompts/codex_prompt_superevent_patch_interfaces.md`
- Local SuperEvent repo: `/home/peterc/devDir/event-based-repos/SuperEvent`
