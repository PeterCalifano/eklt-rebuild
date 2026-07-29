# Event-Only EKLT Implementation Map

> **Archived implementation map.** This point-in-time file inventory predates
> the accepted `ros1/`, `src/eklt_core/`, `src/event_recon_fibar_core/`,
> `src/visualization/`, and `src/wrap_adapters/` layout. Consult
> `doc/eklt_events_only.md` and the active template-upgrade plan for current
> ownership.

## Status

- [x] Stage order defined.
- [x] Subsystem ownership defined.
- [x] Example-demo acceptance artifacts defined.
- [x] Goal-mode stop conditions linked to artifacts.
- [x] Stage 1 local Python implementation started.

## Dependency Direction

Allowed:

```text
event_vision_utils -> C++ wrapper module
eklt_ros1 -> eklt_core -> tracker/patch/optimizer
eklt_ros1 -> event_recon_fibar_core
eklt_ros2 -> eklt_core
eklt_ros2 -> event_recon_fibar_core
event_recon_fibar_core -> fibar_lib
```

Forbidden:

```text
eklt_core -> ROS2
eklt_core -> FIBAR
eklt_core -> ELOPE
eklt_core -> Python
eklt_core -> MATLAB
eklt_core -> SuperEvent
eklt_core -> PyTorch
eklt_core -> ONNX Runtime
event_recon_fibar_core -> ROS node APIs
```

## C++ Naming Convention

- [x] Classes use `C*`, e.g. `CFibarReconstructor`.
- [x] Structs use `S*`, e.g. `SFeatureCandidate`.
- [x] Enums use `E*`, e.g. `EImageRequestReason`.
- [x] Type aliases and traits use `T*` where added.
- [x] Python APIs keep Python naming style.

## Stage 1 Ownership

- [x] Treat event tuple loaders, validation, slicing, and dataset visualizations as reusable utilities, not EKLT algorithm code.
- [x] Prefer implementing permanent Python utilities in `EventDataGenerationLib` or a shared `event_vision_utils` package.
- [x] Keep C++ EventPacket bridge code dependency-gated and isolated for later extraction to `event-cameras-primitives`.
- [x] Use `rpg_eklt` only as temporary staging area when cross-repo work would block fast validation.
- [x] If staged locally, keep same package names and interfaces planned for external repos.
- Future extraction cleanup: when external repo implementation stabilizes, replace local staged modules with dependency imports and delete duplicate code.

## Stage 1 Local Staging Files

- [x] Add `python/event_vision_utils/` only as migration-ready staging package.
- [x] Add `python/event_vision_utils/core/`.
- [x] Add `python/event_vision_utils/io/`.
- [x] Add `python/event_vision_utils/slicing/`.
- [x] Add tests under `python/tests/event_vision_utils/` or current pytest convention.
- [x] Update `python/pyproject.toml` to include `event_vision_utils*` only while staged locally.
- [x] Add extraction note listing target repo, dependency assumptions, and public API compatibility.

How:

- Use NumPy arrays, no pandas dependency.
- Keep loaders pure Python.
- Keep `EventArray` as canonical Python in-memory event type.
- Convert to C++ wrapper arrays only at reconstruction boundary.
- Keep generic modules free of EKLT, ROS, FIBAR, OpenCV tracker, and script-output assumptions.
- Use API names and timestamp/polarity conventions that map cleanly to
  `EventDataGenerationLib.EventStream` and the `SEvent` type in
  event-cameras-primitives.

## Stage 2 Files

- [x] Add `python/event_vision_utils/viz/` only as migration-ready staging package.
- [x] Add `python/event_vision_utils/examples/visualize_elope_npz.py`.
- [x] Add dataset adapter base class plus ELOPE/generic NPZ adapters.
- [x] Add tests for rendering arrays and output files.

How:

- Use OpenCV or imageio only behind optional visualization extras.
- Always provide PNG sequence fallback if MP4 writer unavailable.
- Keep event display independent from reconstruction.
- Keep reusable visualization code dataset-oriented; keep EKLT-specific output layout in scripts/evaluation only.

## Stage 3 Files

- [x] Add `include/event_recon_fibar_core/`.
- [x] Add `src/event_recon_fibar_core/`.
- [x] Add `lib/fibar_lib` or documented external dependency.
- [x] Add wrapper sources under `python/event_vision_utils/recon/` and C++ binding target.
- [x] Add wrapper interface file under `wrap_interfaces/` with clear path.

How:

- First wrap upstream `fibar_lib`.
- Keep local facade stable even if upstream API changes.
- Provide both full-frame readout and local patch readout.
- Local patch readout returns intensity, gradients, valid mask, and quality metrics.
- Build C++ tests without ROS.
- Keep C++ facade free of Python/MATLAB APIs.
- Build Python wrapper with `cd python && python setup.py build_ext --inplace`.

## Stage 4 Files

- [x] Add `scripts/run_elope_reconstruction_example_demo.sh`.
- [x] Add `python/event_vision_utils/examples/reconstruct_elope_fibar.py`.
- [x] Add `python/event_vision_utils/examples/debug_fibar_patches.py`.
- [x] Add `scripts/evaluate_outputs.py` base utilities if not already added later.

How:

- Script accepts `--input`, `--output-dir`, `--width`, `--height`.
- Script writes `summary.json`.
- Script writes event preview, reconstruction preview, event-rate plot.
- Patch debug example visualizes candidates, accepted/rejected patches, local patches, and gradient quality.

## Stage 5 Files

- [x] Add provider headers in `include/eklt_core/` or current `include/tracker/` namespace plan.
- [x] Add `SFeatureCandidate`.
- [x] Add `SLocalFeaturePatch`.
- [x] Add `CFeatureCandidateProvider`.
- [x] Add `CFeaturePatchProvider`.
- [x] Refactor tracker initialization behind provider seam.
- [x] Add mock-provider and provider-interchangeability tests.

How:

- Keep current public ROS1 node behavior unchanged.
- Preserve full-frame initialization mode as an alternative.
- Add candidate + local patch initialization as an alternative.
- Convert full-frame provider image to grayscale `cv::Mat` suitable for current optimizer.
- Convert local patch provider output to current patch/gradient initialization data.
- Use `CFibarHarrisCandidateProvider + CFibarPatchProvider` as current event-only baseline.
- Keep original EKLT `goodFeaturesToTrack(..., useHarrisDetector=true)` path as `CFrameHarrisCandidateProvider`.
- Keep current frame patch/log-gradient extraction as `CFramePatchProvider`.
- Treat `CFrameHarrisCandidateProvider + CFramePatchProvider` as first-class provider pair for current frame-backed mode.
- Use mock `CSuperEventCandidateProvider` only as interface test double.
- Do not move optimizer math unless required.
- Do not import SuperEvent, PyTorch, LibTorch, or ONNX into EKLT core.

## Stage 6 Files

- [x] Add ROS1 event-only node or mode.
- [x] Add `scripts/run_original_rosbag_example_demo.sh`.
- [x] Add `scripts/run_ros1_event_only_example_demo.sh`.
- [x] Add `scripts/summarize_eklt_tracks.py`.
- [x] Expand `scripts/evaluate_outputs.py`.

How:

- Original rosbag example demo validates no regression.
- Event-only example demo validates `CFibarHarrisCandidateProvider + CFibarPatchProvider`.
- Full-frame mode remains runnable.
- Both scripts produce tracks and evaluation outputs.

## Stage 7 Files

- [x] Add ROS2 EventPacket publisher package/module.
- [x] Add ROS2 reconstruction debug node.
- [x] Add `scripts/run_ros2_elope_playback_test.sh`.
- [x] Add `scripts/run_ros2_reconstruction_debug_example_demo.sh`.

How:

- Use `event_camera_msgs/msg/EventPacket`.
- Use the local `mono` EventPacket codec for dependency-light tests; add `event_camera_codecs` runtime path when that dependency is available.
- Keep ROS2 nodes optional if current workspace is ROS1-only.

## Stage 8 Files

- [x] Add ROS2 events-only EKLT node.
- [x] Add ROS2 params config.
- [x] Add `scripts/run_ros2_elope_event_only_example_demo.sh`.

How:

- Feed decoded EventPacket batches to EKLT and FIBAR provider.
- Use params `feature_provider:=fibar_harris` and `patch_provider:=fibar` for current baseline.
- Document future `feature_provider:=superevent` as not implemented.
- Publish tracks, stats, and debug init image.
- Use native ROS2 params, not gflags.

## Stage 9 Files

- [x] Add user docs under `doc/`.
- [x] Update README.
- [x] Add final example command table.
- [x] Add devcontainer/Docker verification notes when host setup is insufficient.

How:

- Docs list exact commands.
- Docs list expected output files.
- Docs list dependency assumptions and skip policy.
- Docs list container command path for reproducible ROS1/ROS2/FIBAR verification when needed.

## Required Output Schema

Every full example demo writes:

```json
{
  "run_name": "elope_event_only_example",
  "status": "passed",
  "input": "...",
  "event_count": 0,
  "track_count": 0,
  "track_rows": 0,
  "duration_s": 0.0,
  "runtime_s": 0.0,
  "plots": [],
  "gt_status": "available|unavailable",
  "gt_metrics": {}
}
```

Required plots:

- [x] `active_tracks.png`
- [x] `track_lifetimes.png`
- [x] `reinit_timeline.png`
- [x] `event_rate.png` when event input is available.
- [x] `gt_error.png` when GT is available.

## Required Script Names

- [x] `scripts/run_original_rosbag_example_demo.sh`
- [x] `scripts/run_elope_reconstruction_example_demo.sh`
- [x] `scripts/run_ros1_event_only_example_demo.sh`
- [x] `scripts/run_ros2_reconstruction_debug_example_demo.sh`
- [x] `scripts/run_ros2_elope_event_only_example_demo.sh`
- [x] `scripts/evaluate_outputs.py`

## Stage Gate Policy

- [x] Do not start Stage 3 before Stage 1 and Stage 2 tests pass.
- [x] Do not start EKLT provider refactor before FIBAR facade test passes.
- [x] Do not mark ROS1 event-only stage complete until original rosbag example demo also passes.
- [x] Do not mark any example demo complete without plots/stats.
- [x] Do not skip GT metrics when GT exists.
- [x] If host dependencies block verification, use devcontainer/Docker before declaring blocked.
- [x] Do not require SuperEvent for current completion.
- [x] Do not implement SuperEvent unless explicitly requested later.
