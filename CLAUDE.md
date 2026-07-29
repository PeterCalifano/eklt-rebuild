# CLAUDE.md

Read `AGENTS.md` first. It is the authoritative repository policy for template
inheritance, review quality, wrappers, MATLAB, ROS boundaries, Git safety, and
external-tool stop conditions.

## Project Overview

EKLT implements asynchronous photometric feature tracking using event-camera
events and conventional frames. The repository now contains four related but
separate surfaces:

- the original ROS1 Noetic frame-backed tracker;
- a ROS-free native initialization and photometric-tracking core;
- FIBAR reconstruction with Python 3.12 and MATLAB R2024b gtwrap adapters;
- an experimental ROS2 Jazzy event-only overlay.

The frame-backed and event-only initialization paths are alternatives. Do not
reduce either path to a compatibility fallback.

## Build Commands

Build the ROS-free native targets out of source:

```bash
git submodule update --init lib/fibar_lib
./build_lib.sh
```

Optional native gates:

```bash
./build_lib.sh --docs --install --package
./build_lib.sh --profile
./build_lib.sh --python
./build_lib.sh --matlab
```

MATLAB must be R2024b and must preload the system `libgcc_s` and `libstdc++`.
Use the existing workstation launcher or invoke MATLAB manually; do not add a
repository-local launcher.

Build ROS independently:

```bash
./build_ros1.sh --import-dependencies
./build_ros2.sh
```

## Architecture

- `ros1/`: original ROS1 transport, parameters, launch-facing adapters, and
  compatibility headers.
- `src/eklt_core/`: ROS-free initialization, tracking, and orchestration.
- `src/event_recon_fibar_core/`: native FIBAR facade.
- `src/visualization/`: transport-neutral feature rendering.
- `src/wrap_adapters/`: Eigen-backed wrapper dtype adaptation.
- `wrap_interfaces/fibar_reconstructor.i`: shared gtwrap declaration for
  Python and MATLAB.
- `python/`: the unified `eklt-rebuild` distribution containing
  `eklt_rebuild`, `eklt_bridge`, and extraction-ready `event_vision_utils`.
- `ros2/eklt_rebuild/`: independent experimental ROS2 event-only overlay.

## Required Boundaries

- Use C++17 for ROS1, the ROS-free native library, FIBAR, wrappers, and ROS2.
- Keep ROS-free targets independent of catkin and ROS messages.
- Do not change inherited `cmake/*.cmake` files. Correct repository usage or
  report an upstream parent-template defect.
- Keep OptiX, PTX, and ZeroMQ out of active EKLT configuration.
- Keep `lib/fibar_lib` and `lib/wrap` pinned at their SSH origins and do not
  edit submodules or external repositories.
- Use Eigen for wrapper arrays. Add `*Adapter` or `*Orchestrator` classes only
  when dtype conversion or functional coordination requires them.
- Preserve unrelated dirty-worktree changes. Do not stage, commit, tag, or push
  without explicit permission.

## Tests

Native tests use Catch2 v3. Python tests use pytest. The installed consumer
fixture is under `tests/consumer/`. Do not import recursive parent-template
conformance tests into the ordinary EKLT CTest suite.

For current validation results and environment gates, see:

- `doc/developments/cpp_cuda_template_upgrade_plan.md`
- `doc/developments/dataset_and_online_streaming_plan.md`
- `doc/developments/reports/cpp_cuda_template_upgrade_acceptance_2026-07-25.md`

Completed and superseded plans under `doc/developments/archive/` are
point-in-time records. Do not use their old paths or decisions as current
implementation guidance.
