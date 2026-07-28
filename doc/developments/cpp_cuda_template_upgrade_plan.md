# `cpp_cuda_template_project` Alignment Plan

This checklist records the semantic upgrade of `rpg_eklt` from its mixed
template snapshot around `cpp_cuda_template_project` v1.2.0 to the reviewed
v1.11.3 donor revision (`dbffe4d4babb88a8682bfd19cf2bea3bc93fe252`).
The one later inherited wrapper helper accepted for Stage 15 comes from the
reviewed parent v1.12.0 commit recorded in that stage; this explicit exception
does not change the general v1.11.3 alignment baseline. The live dirty checkout
is authoritative: existing EKLT, event-only, FIBAR, ROS2, documentation, and
test work must be preserved.

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
| Native API | One `libeklt-rebuild` containing the compiled `eklt_core`, `event_recon_fibar_core`, `visualization`, and `wrap_adapters` implementations | Shared/static builds, one-binary artifact check, and installed consumer |
| Wrappers | Optional Python/MATLAB generation over the always-built C++ adapter API | Python equivalence, relocated-wheel import, and MATLAB R2024b tests |
| ROS | ROS1 reference; ROS2 event-only experimental overlay | Independent catkin/colcon entrypoints |
| Removed features | OptiX, PTX, ZeroMQ | No active options, dependencies, or root-helper usage; inherited helpers stay immutable |
| Runtime | MATLAB preloads system `libgcc_s` and `libstdc++` | Manual preload MATLAB tests |

## Stage 1 - ROS-free native build

- [x] Make plain CMake configuration independent of catkin.
- [x] Export canonical `eklt_rebuild::eklt-rebuild` and logical
      `event_recon_fibar_core`, `visualization`, and `wrap_adapters` API targets
      without publishing separate component binaries.
- [x] Use C++17 consistently for ROS1, the ROS-free native library, FIBAR,
      wrappers, and ROS2.
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
      the optional CUDA `LD_LIBRARY_PATH` declaration in Stage 20, or record the
      exact upstream blocker there before final acceptance.

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
- [x] Require and export Eigen and Ceres for the always-installed native
      adapter and photometric header surfaces.
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
- [x] Preserve separate `eklt_core`, `event_recon_fibar_core`,
      `visualization`, and `wrap_adapters` source/API boundaries within the
      single physical library.
- [x] Co-locate Eigen-backed wrapper adapter headers and implementation under
      `src/wrap_adapters/`, with matching `<wrap_adapters/...>` includes and
      the `wrap_adapters` C++ namespace.
- [x] Remove the legacy repository-root `include/` directory from the native
      target's build interface; the independent ROS1 target continues to own
      its legacy headers.
- [x] Build the adapter/facade convenience API in ordinary native builds,
      independently of Python or MATLAB wrapper-generation options.
- [x] Publish `eklt_rebuild::eklt-rebuild` as the canonical CMake target while
      retaining `eklt_rebuild::event_recon_fibar_core` and
      adding `eklt_rebuild::visualization` and
      `eklt_rebuild::wrap_adapters` as logical views of the same installed
      binary.
- [x] Point gtwrap at the canonical native target so its generated module links
      and packages one project-owned runtime library.
- [x] Remove the obsolete core-only CI matrix and make native facade/adapter
      Catch2 and installed-consumer coverage unconditional.
- [x] Keep ROS1, ROS2, profiling, shared/static builds, documentation, and
      generated wrappers available while making Ceres required by the complete
      native tracking library.
- [x] Own Ceres solver options and gradient caches directly in
      `CPhotometricOptimizer`; do not retain a PIMPL solely to hide a required
      dependency.
- [x] Preserve reference-counted release of timestamped gradient caches so
      repeated feature reinitialization does not retain obsolete full images.
- [x] Keep FIBAR as a supporting EKLT implementation in the same native
      library rather than an independently usable product.

### Deliberate donor-template discrepancies

- [x] Retain the donor's generic optional-wrapper mechanism, but do not model
      EKLT's C++ facade/adapters as optional wrapper-only libraries.
- [x] Keep inherited files under `cmake/` byte-identical to an accepted parent
      commit; express the single-library product topology only in project-owned
      root/source CMake.
- [x] Do not import donor recursive `VerifyTemplateProject*` fixtures; prove
      the product contract with fresh builds, Catch2, CI, install, and external
      consumers.
- [ ] Complete the accepted parent-helper synchronization and wrapper build
      foundation only in Stage 15, using the exact v1.12.0 commit and blob
      recorded there.
- [ ] Replace the dirty broad Python native-library scan with explicit
      target-derived runtime packaging only in Stage 16.
- [ ] Refresh historical acceptance text that names separate
      `libevent_recon_fibar_core` and `libevent_recon_fibar_adapters` artifacts
      in Stage 20; those names are superseded by the one-library decision.
- [x] Review the legacy ROS1 reconstruction/tracking algorithm changes in the
      dedicated Stage 13 source batch without mixing them into Stage 11.

### Consolidation acceptance gates

- [x] The isolated Git-index snapshot produces only `libeklt-rebuild` and
      passes 33/33 native tests in shared and static Werror builds.
- [x] Isolated shared and static installs configure, build, and run the
      external consumer through the canonical target and logical API views.
- [x] Construct an isolated tree from the Git index, add only the pinned
      `lib/fibar_lib` commit, and verify byte parity for every staged path.
- [x] Run the ROS2 Jazzy overlay against the consolidated canonical target; no
      local ROS1 build/test is required for this review.
- [x] Run Doxygen warnings-as-errors, workflow/structured-file parsing, Bash
      syntax, ShellCheck, source-package checks, and
      `git diff --cached --check`.
- [x] Complete the final whole-index reader review required by `AGENTS.md`
      before presenting the staged set for commit review.

Stop condition: do not begin Python/MATLAB implementation or legacy ROS1
algorithm consolidation. Keep later changes to `src/optimizer.cpp`,
`src/tracker.cpp`, and related ROS integration files unstaged.

## Checkpoint protocol for remaining stages

Each functional stage is exactly one mandatory user-commit boundary:

- [ ] Start with a read-only review: reconcile `HEAD`, upstream, index,
      worktree, submodules, inherited-helper provenance, current
      implementation, and the exact intended stage scope.
- [ ] Report review findings and the proposed paths, behavior, validation, and
      commit message before staging the batch.
- [ ] Implement and stage only the current stage; do not edit or pre-stage
      later-stage files.
- [ ] Update this checklist and the ignored `CONTEXT.md` with validation
      evidence.
- [ ] Review the complete index and validate an isolated exact-index snapshot.
- [ ] Report findings, staged paths, remaining work, commit title, and
      description, then stop for the user's review.
- [ ] Apply only the user's requested updates within the same stage, restage
      the complete batch, and rerun every affected gate plus the complete-index
      checks.
- [ ] Stop without committing and wait for the user to commit and say `next`.
- [ ] On `next`, confirm the accepted `HEAD`, reconcile the index, worktree,
      upstream, and submodules, record the commit hash in the checkpoint
      ledger, and only then begin the following stage.

## Stage 12 - CI and development environment

- [x] Stage only the Ceres-aware devcontainer setup and the four standard
      workflows.
- [x] Run workflows only for pull requests targeting `master` and pushes to
      `master`.
- [x] Preserve path filters and `verify_*` job names.
- [x] Validate YAML, Bash, ShellCheck, Docker BuildKit, and focused diffs.
- [x] Stop for the user commit titled
      `Align CI with the C++17 Ceres build`.

## Stage 13 - Legacy ROS1 C++ integration

- [x] Review the tracker, optimizer, patch, viewer, flags, configuration,
      launch, and focused tests as one batch.
- [x] Keep ROS1 headers and implementations in the root `ros1/` overlay,
      parallel to `ros2/`, while preserving installed catkin include names.
- [x] Move image/event scheduling, initialization, KLT/event bootstrap,
      feature lifecycle, reinitialization, and track snapshots into one
      ROS-free C++17 `*Orchestrator` API.
- [x] Reduce ROS1 tracking to message conversion, transport/worker ownership,
      track-file output, and topic publication through standard ROS tools.
- [x] Adapt ROS1 tracking to the consolidated orchestrator API.
- [x] Remove duplicate native computations only after regression parity is
      demonstrated.
- [x] Preserve frame-backed and event-only initialization, viewer output,
      parameters, and track files.
- [x] Release gradient caches whenever patches retire.
- [x] Keep native working state bounded: do not retain pre-initialization event
      batches, exclude patch buffers and caches from snapshots, and bound the
      ROS1 transport queue.
- [x] Exercise real KLT translation, FIBAR/Ceres event-only tracking, and
      feature loss/reinitialization with runtime-generated synthetic frames
      and ideal frame-difference events.
- [x] Use Catch2 and ROS1 CI evidence; no local ROS1 build is required.
- [x] Stop for the user commit titled
      `Integrate the ROS1 tracker with the native EKLT core`.

## Stage 14 - ROS2 event-only overlay

- [x] Stage the `eklt_rebuild` package, event-only configuration, scripts, and
      directly related documentation.
- [x] Link the canonical native target without recompiling its sources.
- [x] Keep ROS2 transport and parameters confined to the overlay.
- [x] Keep renderer policy outside `eklt_core` under `src/visualization/` and
      expose it through the logical `eklt_rebuild::visualization` target.
- [x] Complete gradient-cache lifecycle handling.
- [x] Validate colcon, EventPacket decoding, deterministic tracking, non-empty
      output, and scripts.
- [x] Run the user-selected existing example through ROS2, converting its bag
      to EventPacket-compatible ROS2 data when necessary, and notify the user
      when it is ready for their first test.
- [x] Publish the original feature overlay for standard ROS2 image tools and
      optionally save bounded finite-normalized FIBAR frames as PNG files.
- [x] Convert the ELOPE event array into bounded EventPacket packets and run it
      through the same tracking, visualization, PNG, and summary path without
      requiring camera intrinsics.
- [x] Treat explicit ELOPE width/height metadata as authoritative, fall back to
      the official 200-by-200 sensor contract, and never infer geometry from
      observed event-coordinate maxima.
- [x] Audit project-owned Python definitions and keep the first parameter on
      the same line as the function name; correct every Stage 14 violation.
- [x] Record bounded per-packet FIBAR, remaining native EKLT, and complete
      ROS2 processing time, then generate a validated stacked-area profile
      whose colored bands reconstruct the total boundary.
- [x] Give the processing-time profile a capitalized descriptive title,
      bracketed time units, explicit component labels, and matching
      machine-readable plot-label metadata.
- [x] Stop for the user commit titled
      `Add the ROS2 event-only EKLT overlay`.

## Stage 15 - Accepted wrapper build foundation

- [ ] Record the resolved parent blocker at `v1.12.0`, commit
      `b277e4b84e2f1e501d6c2e73370efe0ecd101f23`.
- [ ] Sync `HandleWrapper.cmake` byte-for-byte from that commit; the expected
      blob is `367b6c3a226dc6fb64e35f471dfb5cd63b43262c`.
- [ ] Stage `.gitmodules`, the pinned read-only `lib/wrap` gitlink,
      `wrap_interfaces/`, and project-owned wrapper CMake configuration.
- [ ] Generate wrappers against the canonical target without staging generated
      output.
- [ ] Keep Python distribution policy, MATLAB packaging, dataset utilities,
      and demo orchestration outside this foundation commit.
- [ ] Stop for the user commit titled
      `Align generated-wrapper support with template v1.12.0`.

## Stage 16 - Portable Python package

- [ ] Publish the `eklt-rebuild` distribution with the identifier-safe
      `eklt_rebuild` import package, following the root project name without
      exposing an invalid hyphenated Python identifier.
- [ ] Preserve `eklt_bridge` as its existing separately owned distribution and
      do not silently absorb `event_vision_utils` into either Python package. // Review note: Guideline is to prefer clean and clear design without indirections, excessive complexity to keeping backward compatibility at all costs. If this is clean enough and required for compatibility with existing external packages (but if implemenation is currently in this repo but made "compatible", then keep it)
- [ ] Package only explicit target-derived runtime artifacts.
- [ ] Use `$ORIGIN`; omit `_wrapper_build.py`, caches, and bytecode.
- [ ] Validate wrapper CTest, Python tests, wheel contents, CMake installation,
      and relocated import with an empty `LD_LIBRARY_PATH`.
- [ ] Stop for the user commit titled
      `Package a relocatable eklt_rebuild Python wrapper`.

## Stage 17 - MATLAB R2024b wrapper

- [ ] Generate MATLAB bindings from the shared declarations and canonical
      native target.
- [ ] Preserve Eigen-backed exchange and adapter/orchestrator boundaries.
- [ ] Validate MEX and toolbox output with the documented system-runtime
      preload.
- [ ] Do not add a repository-local MATLAB launcher.
- [ ] Stop for the user commit titled
      `Add the MATLAB R2024b EKLT wrapper`.

## Stage 18 - `event_vision_utils` data foundation

- [ ] Stage the documented signed-polarity, integer-microsecond `EventArray`
      model, dataset metadata, ELOPE and generic NPZ adapters, bounded slicing,
      visualization primitives, and native FIBAR wrapper adapter.
- [ ] Preserve the established `event_vision_utils` import API under explicitly
      owned distribution metadata separate from `eklt_bridge` and
      `eklt_rebuild`.
- [ ] Add explicit tested conversions between
      `eklt_bridge.primitives.EventStream` and `EventArray`; do not blur their
      seconds/`{0,1}` and microseconds/`{-1,+1}` contracts.
- [ ] Keep the eager prototype direct ROS2 publisher, multi-sequence selection,
      AEDAT4, asynchronous ROS2 processing, and complete demo orchestration
      outside this foundation commit.
- [ ] Apply the Python documentation, callable type-hint, first-argument
      formatting, bounded-memory, and structured-output gates.
- [ ] Stop for the user commit titled
      `Establish the event_vision_utils data model`.

## Stage 19 - Single-sequence ELOPE analysis pipeline

- [ ] Stage the official-dataset download and validation helpers,
      single-sequence reconstruction and tracking orchestration, output
      evaluation, plots, event/patch/track videos, summaries, tests, and
      directly related documentation.
- [ ] Build on the accepted Stage 14 ROS2 EventPacket runner, Stage 16 Python
      wrapper, and Stage 18 data model rather than retaining parallel codecs,
      loaders, or visualization stacks.
- [ ] Define stable per-sequence artifact schemas and reader documentation so
      the later multi-sequence stage can aggregate results without changing the
      single-sequence contract.
- [ ] Keep generated datasets and outputs ignored, and restrict cleanup to
      explicitly owned artifacts below the selected output directory.
- [ ] Do not add random multi-sequence selection, AEDAT4 ingestion, generic
      direct publishing, or online/asynchronous ROS2 behavior in this stage.
- [ ] Stop for the user commit titled
      `Add the single-sequence ELOPE analysis pipeline`.

## Stage 20 - Repository metadata and hygiene

- [ ] Review issue and pull-request templates, attributes, ignore rules,
      workspace guidance, and deprecated-file removal as one maintenance batch.
- [ ] Refresh obsolete source paths and separate-library references.
- [ ] Correct agent guidance to the accepted src-local native adapter-header
      layout without restoring the removed repository-root `include/`
      directory.
- [ ] Resolve the Stage 8 BuildKit warning or record its exact authorized
      upstream blocker.
- [ ] Archive or mark superseded implementation audits and reconcile the
      active event-only, ROS2, and template-upgrade plans.
- [ ] Keep feature-specific scripts and documentation with their owning earlier
      stages.
- [ ] Validate structured files, stale references, source packaging, and
      diffs.
- [ ] Stop for the user commit titled
      `Refresh EKLT repository metadata and guidance`.
- [ ] Review aiming at simplifying to reduce complexity while keeping functionalities, documentation and code comments for development and readable implementation. Unnecessary or uselessly single use (unless improving clarity a lot) abstractions, indirections, local helpers should be removed

## Stage 21 - Final cumulative review

- [ ] Review the complete cumulative upgrade against the accepted baseline.
- [ ] Reconcile names, layout, APIs, exports, dependencies, packaging,
      documentation, and remaining dirty groups.
- [ ] Run the complete native, wrapper, Python, MATLAB, ROS2, documentation,
      packaging, shell, structured-file, and exact-index gates.
- [ ] Record unavailable ROS1 runtime validation as CI or environment evidence.
- [ ] Confirm findings 4 and 7 remain explicitly deferred.
- [ ] Stage only the acceptance record and directly required corrections.
- [ ] Insert a dedicated correction stage before acceptance if a finding
      requires material source, packaging, or behavior changes; do not hide
      another functional batch in this final record.
- [ ] Stop for the user commit titled
      `Finalize the EKLT template upgrade acceptance record`.

## Handoff to multi-dataset and online streaming

The separate
[`Multi-Dataset and Online EKLT Streaming Plan`](dataset_and_online_streaming_plan.md)
starts only after Stage 21 has an accepted commit and the user says `next`. It
must preserve the Stage 14 synchronous ROS2 path as the deterministic offline
reference and build on the accepted Stage 18/19 data and single-sequence
contracts.

Each handoff stage remains one user commit:

- [ ] Streaming Stage 0 reconciles and records the accepted upgrade baseline
      without production changes.
- [ ] Streaming Stage 1 adds deterministic sampled multi-sequence ELOPE
      orchestration, aggregate results, owned cleanup, and optional saved input
      bags.
- [ ] Streaming Stage 2 adds bounded dataset-record iteration, a generic direct
      EventPacket publisher, ordered processing acknowledgements, packet
      duration/count policy, and a delegating ELOPE compatibility entrypoint.
- [ ] Streaming Stage 3 adds the Python 3.12 AEDAT4 adapter, pinned dependency
      environment, metadata/frame handling, and runtime-generated fixture.
- [ ] Streaming Stage 4 adds bounded input, exclusive algorithm, and bounded
      output workers with sequence-gap/drop reset barriers and ordered
      acknowledgements while preserving deterministic tracking parity.
- [ ] Streaming Stage 5 adds subscriber-gated asynchronous event, FIBAR, track,
      and active-patch image diagnostics with validated rates and latest-only
      coalescing.
- [ ] Streaming Stage 6 adds PlotJuggler-friendly scalar metrics and complete
      queue/FIBAR/EKLT/output/end-to-end timing artifacts.

## Checkpoint ledger

| Stage | Status | Validation summary | Accepted commit |
|---|---|---|---|
| 11 - Product-native library consolidation | accepted | Exact-index shared/static Werror 33/33, installed consumers, Doxygen, one-library layout, source package, staged-byte parity, and live ROS2 build passed | `78bfa69e008dd65b695b1a4f8c8aa192ada2e3a9` |
| 12 - CI and development environment | accepted | Exact-index workflow semantics, preserved filters and names, Bash, ShellCheck, BuildKit checks, and the Ubuntu 20.04 image build passed | `7ab4df431104a0c63939746ba7889299a3403746` |
| 13 - Legacy ROS1 C++ integration | accepted | Exact-index shared/static Werror 43/43 including synthetic KLT, FIBAR/Ceres, and reinitialization algorithm paths; Noetic catkin 51/51; installed consumers and legacy headers, launch/linkage checks, Doxygen, source packaging, structured/shell validation, and staged-byte parity passed | `9c731b88ea82af9b70770ca02941b9d4e19c8c3d` |
| 14 - ROS2 event-only overlay | awaiting user commit | Exact-index shared/static Werror 48/48, installed consumers, Doxygen, colcon 2/2 with eight GTest cases, and the root `ros1/`, `src/visualization/`, and `src/wrap_adapters/` boundaries passed. Shared config installation, legacy and ELOPE tracking with bounded PNG output, advertised/fallback ELOPE geometry resolution, the Python definition-layout audit, and structured/shell/package gates passed. The bounded official ELOPE timing run produced 200 additive rows and a visually reviewed, unit-labeled stacked plot with matching summary metadata, 82,924 KiB peak RSS, and no swaps; the earlier full converted bag retained 99.93% duration coverage | `pending` |
| 15 - Accepted wrapper build foundation | pending | Not run; requires accepted Stage 14 checkpoint | - |
| 16 - Portable Python package | pending | Not run; requires accepted Stage 15 checkpoint | - |
| 17 - MATLAB R2024b wrapper | pending | Not run; requires accepted Stage 16 checkpoint | - |
| 18 - `event_vision_utils` data foundation | pending | Not run; requires accepted Stage 17 checkpoint | - |
| 19 - Single-sequence ELOPE analysis pipeline | pending | Not run; requires accepted Stage 18 checkpoint | - |
| 20 - Repository metadata and hygiene | pending | Not run; requires accepted Stage 19 checkpoint | - |
| 21 - Final cumulative review | pending | Not run; requires accepted Stage 20 checkpoint | - |
