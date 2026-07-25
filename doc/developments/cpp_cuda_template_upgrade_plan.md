# `cpp_cuda_template_project` Alignment Plan

This checklist records the semantic upgrade of `rpg_eklt` from its mixed
template snapshot around `cpp_cuda_template_project` v1.2.0 to the reviewed
v1.11.3 donor revision (`dbffe4d4babb88a8682bfd19cf2bea3bc93fe252`).
The live dirty checkout is authoritative: existing EKLT, event-only, FIBAR,
ROS2, documentation, and test work must be preserved.

Checked items record implementation or validation in the live checkout. They
do not imply that the corresponding files are staged, committed, or accepted
from an uncommitted parent-template baseline.

## Stage 0 - Baseline and tailoring ledger

- [x] Confirm the historical template import at target commit `97f03dff`.
- [x] Pin the donor review baseline to v1.11.3.
- [x] Record the pre-upgrade Python baseline: `80 passed, 1 skipped`.
- [x] Record the pre-upgrade shell syntax baseline: passing.
- [x] Record the pre-upgrade native CMake blocker: unconditional
      `catkin_simple` discovery on a host without ROS1/catkin.
- [x] Preserve the original ROS1 tracker, event-only extensions, FIBAR core,
      ROS2 overlay, examples, and evaluation tooling.
- [x] Keep OptiX, PTX, and ZeroMQ outside the supported feature matrix.
- [x] Keep glog rather than importing the donor logger.
- [x] Keep MATLAB host-local and target MATLAB R2024b through the required
      system C++ runtime preload recipe.
- [x] Do not stage, commit, tag, push, or edit external repositories.

| Contract | Tailored state | Required proof |
|---|---|---|
| Identity | Published CMake library/package `eklt-rebuild`; identifier-constrained CMake/ROS/Python name `eklt_rebuild`; utility package `event_vision_utils` | Names flow from the root project without invalid hyphenated identifiers |
| Architecture | ROS1 frame-backed tracker plus alternative event-only path | Existing and event-only tests remain green |
| Native API | One `libeklt-rebuild` containing `event_recon_fibar_core` and `event_recon_fibar_adapters`, plus the header-only `eklt_core` seam | Shared/static builds, one-binary artifact check, and installed consumer |
| Wrappers | Optional Python/MATLAB generation over the always-built C++ adapter API | Python equivalence, relocated-wheel import, and MATLAB R2024b tests |
| ROS | ROS1 reference; ROS2 event-only experimental overlay | Independent catkin/colcon entrypoints |
| Removed features | OptiX, PTX, ZeroMQ | No active options, dependencies, or root-helper usage; inherited helpers stay immutable |
| Runtime | MATLAB preloads system `libgcc_s` and `libstdc++` | Manual preload MATLAB tests |

## Stage 1 - ROS-free native build

- [x] Make plain CMake configuration independent of catkin.
- [x] Export canonical `eklt_rebuild::eklt-rebuild` and logical
      `event_recon_fibar_core`/`event_recon_fibar_adapters` API targets without
      publishing separate FIBAR binaries.
- [x] Keep ROS1 C++11 compatibility and C++17 for FIBAR/wrappers/ROS2.
- [x] Add install, package-config, CPack, Doxygen, and consumer support.
- [x] Upgrade the Catch2 integration to v3.

## Stage 2 - Reusable infrastructure

- [x] Port target-scoped compiler flags, no-optimization, sanitizers, profiling,
      submodule, version, documentation, packaging, and toolchain behavior.
- [x] Keep CUDA, TBB, OpenMP, OpenGL, NumPy, and cross-compilation opt-in.
- [x] Remove OptiX, PTX, and ZeroMQ from active EKLT infrastructure and stale
      project references while leaving inherited CMake helper snapshots
      unchanged.
- [x] Remove template-only recursive verification fixtures.

## Stage 3 - Python and MATLAB wrappers

- [x] Pin `lib/wrap` from its SSH origin at
      `bf9f78617830bfa88c70d81a1a791c0a0c90b548`.
- [x] Replace the SWIG-like wrapper description with valid gtwrap syntax.
- [x] Preserve the Python 3.12 `_fibar` API and NumPy behavior.
- [x] Generate and package the MATLAB wrapper for R2024b.
- [x] Validate MATLAB exclusively through the existing system-runtime preload
      recipe; do not add a repository-local MATLAB launcher.

## Stage 4 - Build and development entrypoints

- [x] Make `build_lib.sh` the ROS-free native/wrapper entrypoint.
- [x] Add non-destructive `build_ros1.sh` and `build_ros2.sh`.
- [x] Preserve devcontainer JSONC customizations while aligning CUDA/ROS
      configuration behavior.

## Stage 5 - Metadata and documentation

- [x] Align version `0.1.0`, `GPL-3.0-only`, and joint maintainers.
- [x] Document native, Python, MATLAB R2024b, ROS1, and ROS2 workflows.
- [x] Keep ROS2 experimental and retain the explicit ROS1 deprecation gate.

## Stage 6 - Focused CI

- [x] Add native, Python 3.12, ROS1 Noetic, ROS2 Jazzy, and hygiene workflows
      using the parent template's standard filenames and `verify_*` names.
- [x] Keep MATLAB R2024b local, defer CUDA CI, and publish docs only as an
      artifact.

## Stage 7 - Acceptance

- [x] Pass available native build/test/install/consumer/package/docs gates.
- [x] Preserve or improve the Python baseline.
- [x] Pass MATLAB R2024b MEX/toolbox tests exclusively with the existing
      system C++ runtime preload recipe.
- [x] Run available ROS build gates and record unavailable environment gates.
- [x] Pass shell syntax, shellcheck, structured-file parsing,
      `git diff --check`, and stale-reference scans.
- [x] Produce the final donor-delta and validation record without staging.

Acceptance evidence is recorded in
`doc/developments/reports/cpp_cuda_template_upgrade_acceptance_2026-07-25.md`.

## Stage 8 - Follow-up alignment audit

- [x] Update `AGENTS.md` from the parent review guidance and tailor it to the
      EKLT native, ROS, wrapper, MATLAB, and immutable-helper contracts.
- [x] Refresh stale companion agent guidance without restoring donor identity.
- [x] Complete the profiling build entrypoint and target propagation policy;
      do not import the parent profiling scripts.
- [x] Restore the parent default cross-toolchain inventory and target
      architecture definitions.
- [x] Align source packaging and repository hygiene files.
- [x] Port applicable devcontainer fixes while retaining Ubuntu 20.04 and ROS1
      Noetic as the default EKLT container.
- [x] Add tailored issue and pull-request templates.
- [x] Record adopted, adapted, and intentionally skipped parent-only surfaces.
- [x] Re-run affected build, package, wrapper, documentation, structured-file,
      shell, and stale-reference gates.
- [ ] Resolve the inherited parent/target BuildKit `UndefinedVar` warning for
      the optional CUDA `LD_LIBRARY_PATH` declaration, then rerun
      `docker buildx build --check`.

## Stage 9 - P1 packaging and deletion safety

- [x] Restrict `--clean` to named directories below `build/`.
- [x] Require an existing clean target to contain a `CMakeCache.txt` owned by
      this exact EKLT checkout.
- [x] Reject parent-directory, build-root, symlink-escape, non-CMake, and
      foreign-source cleanup targets before recursive deletion.
- [x] Bundle the gtwrap extension and its single `libeklt-rebuild` native
      dependency in Python wheels and CMake Python installs.
- [x] Use loader-relative runtime paths and exclude absolute build-link
      metadata from distributable Python packages.
- [x] Install only headers owned by configured plain-CMake targets.
- [x] Export Eigen for the always-installed native adapter headers and Ceres
      only when the Ceres-backed photometric header is installed.
- [x] Leave ROS1 headers under the catkin package install contract.
- [x] Compile and run default and wrapper-enabled installed consumers against
      all advertised headers.
- [x] Confirm the clean and wheel defects in the parent template, apply the
      generic fixes there, and pass the parent's focused conformance tests.
- [x] Confirm the parent does not share EKLT's header-surface defect: its
      explicit module installs, dependency export, and installed-header
      consumer already cover that contract.

## Stage 10 - External-library layout

- [x] Move the FIBAR submodule from its former root external-library location
      to `lib/fibar_lib`.
- [x] Remove the repository-root `extern/` directory.
- [x] Relocate the submodule Git metadata and keep the `release` checkout
      clean.
- [x] Change the FIBAR submodule URL to its SSH origin.
- [x] Update native CMake, ROS2, workflows, agent guidance, build
      instructions, and development documentation to the new path.
- [x] Preserve MATLAB's installation-owned `${Matlab_ROOT}/extern` SDK paths.
- [x] Confirm the parent template already follows the `lib/` layout and needs
      no corresponding change.
- [x] Pass fresh native, wrapper, install-consumer, package, documentation,
      Python, and MATLAB R2024b validation from the new layout.

## Stage 11 - Product-native library consolidation

### Accepted design changes

- [x] Treat FIBAR reconstruction as an intrinsic part of `eklt-rebuild`, not
      as an optional product feature.
- [x] Remove `EKLT_BUILD_FIBAR`; a native build now requires the pinned
      `lib/fibar_lib` checkout and Eigen.
- [x] Compile the FIBAR facade and Eigen-backed adapters/orchestrators into the
      same physical `libeklt-rebuild` shared or static library.
- [x] Preserve separate source/header directories and the
      `event_recon_fibar_core` and `event_recon_fibar_adapters` C++ namespaces.
- [x] Build the adapter/facade convenience API in ordinary native builds,
      independently of Python or MATLAB wrapper-generation options.
- [x] Publish `eklt_rebuild::eklt-rebuild` as the canonical CMake target while
      retaining `eklt_rebuild::event_recon_fibar_core` and
      `eklt_rebuild::event_recon_fibar_adapters` as logical views of the same
      installed binary.
- [x] Point gtwrap at the canonical native target so its generated module links
      and packages one project-owned runtime library.
- [x] Remove the obsolete core-only CI matrix and make native facade/adapter
      Catch2 and installed-consumer coverage unconditional.
- [x] Keep ROS1, ROS2, profiling, shared/static builds, Ceres-backed
      photometric APIs, documentation, and generated wrappers available.

### Deliberate donor-template discrepancies

- [x] Retain the donor's generic optional-wrapper mechanism, but do not model
      EKLT's C++ facade/adapters as optional wrapper-only libraries.
- [x] Keep inherited files under `cmake/` byte-identical to an accepted parent
      commit; express the single-library product topology only in project-owned
      root/source CMake.
- [x] Do not import donor recursive `VerifyTemplateProject*` fixtures; prove
      the product contract with fresh builds, Catch2, CI, install, and external
      consumers.
- [ ] Accept wrapper portability changes only after the parent helper fix has
      an authorized commit beyond `dbffe4d`/v1.11.3 and EKLT matches that exact
      helper blob.
- [ ] Replace the dirty broad Python native-library scan with packaging of the
      explicit `libeklt-rebuild` target once the accepted parent API is
      available.
- [ ] Refresh historical acceptance text that names separate
      `libevent_recon_fibar_core` and `libevent_recon_fibar_adapters`
      artifacts; those names are superseded by the one-library decision.
- [ ] Review and stage reconstruction/tracking algorithm implementations only
      in a later source batch; this consolidation must not edit them.

### Consolidation acceptance gates

- [x] Live dirty-worktree shared and static builds produce only
      `libeklt-rebuild` and pass 26/26 native tests with
      `WARNINGS_ARE_ERRORS=ON`.
- [x] Live shared and static installs configure, build, and run the external
      consumer through the canonical target and both logical API views.
- [x] Construct an isolated tree from the Git index, verify byte parity for
      every staged path, and confirm its only configure blocker is the
      deliberately deferred FIBAR algorithm source.
- [ ] Repeat shared/static build, install, artifact, and consumer gates after
      the later algorithm-source batch makes the isolated Git-index snapshot
      self-contained.
- [x] Run the ROS2 Jazzy overlay against the consolidated canonical target; no
      local ROS1 build/test is required for this review.
- [x] Run Doxygen warnings-as-errors, workflow/structured-file parsing, Bash
      syntax, ShellCheck, source-package checks, and
      `git diff --cached --check`.
- [x] Complete the final whole-index reader review required by `AGENTS.md`
      before presenting the staged set for commit review.

Stop condition: do not begin Python/MATLAB implementation. Keep algorithm
implementation files unedited and unstaged in this batch; repeat the full
isolated-index build once their later source batch makes the snapshot
self-contained.
