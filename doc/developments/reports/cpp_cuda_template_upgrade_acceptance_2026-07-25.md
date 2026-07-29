# `cpp_cuda_template_project` Upgrade Acceptance

> **Historical checkpoint report.** This evidence captures the initial
> 2026-07-25 alignment before the later C++17 single-library, ROS2, wrapper, and
> Python consolidation stages. Its component-library names and early test
> counts are intentionally preserved as point-in-time results. Consult the
> active template-upgrade plan for the accepted current state.

Date: 2026-07-25

## Reviewed baselines

- Target repository: the live `rpg_eklt` worktree, including its pre-existing
  uncommitted event-only, FIBAR, ROS2, documentation, and test work.
- Donor repository: `cpp_cuda_template_project` v1.11.3 at
  `dbffe4d4babb88a8682bfd19cf2bea3bc93fe252`.
- Wrapper generator: `lib/wrap` pinned at
  `bf9f78617830bfa88c70d81a1a791c0a0c90b548`, with SSH origin
  `git@github.com:PeterCalifano/wrap.git`.
- MATLAB target: R2024b.

No inherited CMake helper was patched only in this derived repository.
Generic wrapper-runtime defects were fixed and verified in the parent first;
the resulting `HandleWrapper.cmake` is byte-identical between the current
parent and EKLT worktrees. Project-specific root CMake usage remains in the
root project file. Pre-existing project-only or historically divergent
helpers remain untouched.

## Implemented delta

- Plain CMake builds the ROS-free native targets without catkin.
- `eklt_core`, `event_recon_fibar_core`, and the optional Eigen-based
  `event_recon_fibar_adapters` have install/export support.
- ROS1 is isolated behind `EKLT_BUILD_ROS1`; the ROS2 overlay has its own
  colcon entrypoint.
- Catch2 v3, install consumption, CPack, and Doxygen gates are available.
- Python and MATLAB wrappers are generated from one gtwrap interface in
  `wrap_interfaces/fibar_reconstructor.i`.
- Array adaptation is implemented with Eigen. The boundary classes are named
  `CLocalFeaturePatchAdapter` and `CFibarReconstructorAdapter`; no unnecessary
  wrapper class duplicates the native configuration type.
- OptiX, PTX, and ZeroMQ are absent from the active EKLT feature matrix.
  Inherited helper snapshots are retained unchanged.
- Workflow filenames follow the parent template convention:
  `build_linux.yml`, `build_ros2_overlay.yml`, and `docs_pages.yml`; the ROS1
  counterpart is `build_ros1.yml`. Display names use the same `verify_*`
  convention.
- `--clean` accepts only an EKLT-owned named build directory under `build/`.
- Python wheels and CMake Python installs bundle the wrapper, adapter, and
  FIBAR core shared libraries with loader-relative runtime paths.
- Plain-CMake installation exports only configured ROS-free headers and their
  discoverable dependencies. ROS1 headers remain catkin-owned.
- External library submodules are grouped below `lib/`: FIBAR lives at
  `lib/fibar_lib` and gtwrap at `lib/wrap`, both with SSH origins. The
  repository-root `extern/` directory has been removed.

## Acceptance results

- Native Release build: passed.
- Native CTest: 14 of 14 passed.
- The optional Ceres photometric test was not built because the host CMake
  environment did not expose Ceres; this is a recorded host environment gate.
- Install and package-config export: passed.
- External installed consumer configure/build/run: passed.
- CPack: passed; generated `.sh`, `.tar.gz`, and `.tar.Z` packages.
- Doxygen: passed without warnings.
- Wrapper build: passed for Python 3.12 and MATLAB R2024b.
- Wrapper CTest: 15 of 15 passed.
- Python regression suite: 80 passed, 1 skipped.
- Python functional adapter smoke: passed with a `5 x 6` image and `3 x 3`
  local patch.
- MATLAB R2024b MEX smoke: passed with
  `EKLT_MATLAB_SMOKE_OK release=2024b image=5x6 patch=3x3`.
- Relocatable Linux wheel: passed from an isolated install with
  `LD_LIBRARY_PATH` unset. The wheel contains `eklt.so`,
  `libevent_recon_fibar_adapters.so`, and
  `libevent_recon_fibar_core.so`; all RUNPATH values are `$ORIGIN`, and
  `_wrapper_build.py` is absent.
- Relocatable CMake Python install: passed below the requested install prefix,
  with the same three-library layout and no build-link metadata.
- Installed header surface: passed for both the default native build and the
  wrapper-enabled build. Each installed public header is compiled by the
  external consumer.
- ROS2 Jazzy overlay: passed in a clean `ros:jazzy-ros-base` container.
- ROS1 Noetic runtime build: not run locally because the host and available
  local Noetic image do not contain catkin tools. The non-destructive
  entrypoint and dedicated CI workflow are present; this remains an
  environment gate rather than a source failure.
- Shell syntax, shellcheck with the documented dynamic-source and inherited
  donor-variable exclusions, YAML/XML/JSON parsing, wrapper parsing,
  inherited-helper comparison, stale active-reference scans, and
  `git diff --check`: passed.

MATLAB was invoked directly, without a repository-local launcher:

```bash
LD_PRELOAD=/lib/x86_64-linux-gnu/libgcc_s.so.1:/usr/lib/x86_64-linux-gnu/libstdc++.so.6 \
  /usr/local/MATLAB/R2024b/bin/matlab -nodesktop -nodisplay -batch "<smoke commands>"
```

The ZeroMQ runtime library observed while installing the broad Ubuntu OpenCV
development package in the ROS2 validation container is transitive system
packaging only. EKLT has no active ZeroMQ option, target, include, link
dependency, or documented feature.

## Parent-template upstream fixes

The parent checkout was inspected for the reported P1 defects after the EKLT
solutions passed:

- `build_lib.sh` had the same arbitrary `--clean` risk. It now restricts
  cleanup to conventional in-repository build paths and requires an owned
  CMake cache. A focused parent conformance test covers outside-repository,
  source-directory, and non-CMake cleanup rejection.
- The parent Python wheel copied only its extension and used a non-relocatable
  runtime layout. Its setup template and `HandleWrapper.cmake` now bundle
  declared shared runtime targets, use loader-relative paths, exclude
  build-link metadata, and keep CMake Python installs prefix-relative.
- Parent wheel and CMake-install imports passed from isolated directories with
  `LD_LIBRARY_PATH` unset.
- The parent does not share EKLT's overly broad header-install defect. It
  already installs explicit module headers, exports Eigen and optional
  dependencies, and runs an installed-header consumer.
- The earlier CPack fix remains applied: verbatim variables prevent invalid
  escape diagnostics, recursive patterns exclude nested build trees, and the
  source-release verifier checks them.

The parent's focused clean-safety and nested installed-header CTest gates
passed, as did its complete release-tag/source-archive verifier.

## `lib/` layout follow-up

The FIBAR submodule and its Git metadata were relocated from the former root
external-library location to `lib/fibar_lib`. Native CMake, the ROS2 overlay,
workflows, build instructions, and development documents now use the new
path. The submodule remains on its clean `release` checkout and both its
recorded and local remotes use SSH.

A fresh Release build from the new layout passed 14 native tests, Doxygen,
install, binary CPack, source CPack, and an external installed-consumer
compile and run. The source archive contains `lib/fibar_lib` and no root
`extern/` entry. A fresh combined wrapper build passed 15 CTest checks and the
Python suite (`80 passed, 1 skipped`). MATLAB R2024b, launched directly with
the required system C++ runtime preload, passed the Eigen array smoke with a
`5 x 6` image and `3 x 3` patch.

The parent template already groups repository dependencies below `lib/` and
has no root `extern/` directory, so it required no layout fix. MATLAB's
`${Matlab_ROOT}/extern` include and library paths are SDK-owned and remain
unchanged.

## Adopted, adapted, and skipped surfaces

| Classification | Surfaces |
|---|---|
| Adopted | Agent review policy, source-package filtering, default cross toolchains, profiling option/propagation policy, devcontainer setup fixes, issue/PR templates, safe-clean ownership checks, relocatable wrapper-runtime packaging |
| Adapted | C++11 ROS1 and C++17 FIBAR boundaries, Ubuntu 20.04/Noetic default container, EKLT workflow names, fixed `0.1.0` version policy, MATLAB R2024b preload contract, target-specific installed headers |
| Skipped | Parent profiling runner scripts, CMake presets requiring a newer entrypoint contract, template conformance fixtures/examples, donor logger, OptiX/PTX/ZeroMQ, and the generic ROS2 bootstrap script |

## Open external alignment item

`docker buildx build --check` reports `UndefinedVar` for the inherited
`LD_LIBRARY_PATH` expression in both parent and EKLT Dockerfiles. No
Dockerfile was changed after detecting the parent issue; this remains the only
unchecked Stage 8 item.

## Repository-state boundary

The implementation does not stage, commit, tag, push, or rewrite the existing
dirty worktree. Generated acceptance builds remain under ignored `build/`
directories. The parent template repository was edited only after explicit
authorization; its fixes remain uncommitted.
