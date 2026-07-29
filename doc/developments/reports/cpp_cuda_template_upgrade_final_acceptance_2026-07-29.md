# EKLT Template Upgrade Final Acceptance

## Decision

The cumulative template/build-system upgrade is ready for the user's final
commit review. No unresolved blocking, high-severity, or material
implementation finding remains. Stage 21 contains only the acceptance record
and three directly related hygiene corrections; it changes no C++, algorithm,
wrapper helper, Python runtime, ROS implementation, or package behavior.

This review covers the complete 252-path EKLT delta from `97f03dff` through
accepted Stage 20 commit `6b9a9045db8d17f92164d0ec4301acf8a40823f0`:
44,735 insertions and 2,397 deletions. The runtime validation source was exact
`HEAD` tree `ed152f39c20ab84004d20a4ca160bd3771c537f2`; the final Stage 21
index adds only this report, plan reconciliation, workflow-filter cleanup, and
removal of an empty placeholder.

## Repository and provenance

- Branch `feature/event-only-eklt-rebuild-ros2` is one expected user commit
  ahead of its upstream and live remote, which both resolve to
  `4c85225825b97bac285aad31e245c131c217bd16`.
- No assistant commit, tag, push, pull request, parent-repository edit, or
  external-checkout edit was made.
- FIBAR remains clean and read-only at
  `cc2fc9b39deb2f2e962d9115036f2265edf95ac3`.
- gtwrap remains clean and read-only at
  `bf9f78617830bfa88c70d81a1a791c0a0c90b548`.
- Generic inherited helpers are byte-identical to accepted parent-template
  `v1.11.3`, peeled commit
  `dbffe4d4babb88a8682bfd19cf2bea3bc93fe252`.
- The four wrapper helpers are byte-identical to accepted signed
  parent-template `v1.12.1`, peeled commit
  `480d10a692836040bcae2023e763c553acfcc64d`. Stage 15 recorded the accepted
  signature verification; this review rechecked the tag peel and every helper
  blob without using the parent's live working tree.

## Accepted product contract

- The published native package and library are `eklt-rebuild`; identifier-only
  contexts use `eklt_rebuild`.
- One C++17 `libeklt-rebuild` owns EKLT, FIBAR, visualization, and
  wrapper-adapter code. Logical CMake views remain
  `eklt_rebuild::eklt_core`,
  `eklt_rebuild::event_recon_fibar_core`,
  `eklt_rebuild::visualization`, and
  `eklt_rebuild::wrap_adapters`.
- Public headers are source-local and explicitly installed. There is no
  repository-root `include/`, no `extern/`, and no imported donor recursive
  verification suite.
- Ceres, OpenCV, and Eigen are required native dependencies. FIBAR is a private
  supporting implementation for shared linkage, not a separate EKLT product.
- ROS-free code remains independent of middleware. ROS1 lives under `ros1/`;
  the experimental ROS2 event-only overlay remains under `ros2/`.
- The unified `eklt-rebuild` Python distribution contains the separate
  `eklt_rebuild`, `eklt_bridge`, and extraction-ready `event_vision_utils`
  namespaces.
- Wheels and CMake Python installs use exact target-derived native artifacts,
  loader-relative runtime paths, and exclude `_wrapper_build.py`, unrelated
  libraries, caches, and bytecode.
- CUDA, TBB, OpenMP, OpenGL, profiling, documentation, and wrappers remain
  opt-in. OptiX, PTX, and ZeroMQ are not active features.

## Findings

### P3 - corrected in Stage 21

- `.github/workflows/build_ros1.yml` and
  `.github/workflows/docs_pages.yml` retained four `include/**` filters after
  the root include directory was removed, while omitting their active
  `lib/fibar_lib` input. The dead filters are removed and the pinned FIBAR
  gitlink is added; the push and pull-request filters remain symmetric on
  `master`.
- The tracked root `.codex` was an unused zero-byte placeholder. It is removed.
  The CPack exclusion remains so future local Codex state cannot enter source
  packages.
- One upgrade-plan item still requested rewriting historical separate-library
  names. Stage 20 deliberately preserved accepted history under prominent
  archive/report warnings while correcting active guidance. The checklist now
  records that actual disposition.

### Deferred historical findings

Findings 4 and 7 retain their explicitly deferred review disposition rather
than being retroactively reclassified. Their original surfaces were the ROS1
C++17 propagation review and a CLI reference to the then-unstaged ROS2 build
helper. Later accepted Stage 13 and Stage 14 commits superseded those surfaces;
Stage 21 introduces no new work under either finding.

No local ROS1 build was run in Stage 21, following the standing user
instruction. The accepted Stage 13 checkpoint records Noetic catkin and
regression evidence, and the current ROS1 workflow remains the owned
environment gate.

## Validation

### Native, install, and wrappers

- Independent shared and static Release builds used
  `WARNINGS_ARE_ERRORS=ON`, Python 3.12 wrappers, MATLAB R2024b wrappers, and
  installation. Each passed 54 of 54 CTests, including 48 native/Catch2 and
  package tests plus four MATLAB regressions.
- Shared and static external CMake consumers configured, built, ran, and
  resolved the canonical target plus all four logical API views.
- Shared and static installed Python imports passed with
  `LD_LIBRARY_PATH` removed.
- The opt-in profiling configuration built twice, including one
  ownership-validated `--clean` rebuild.
- Cleanup rejected a parent directory, a directory without a CMake cache, and
  a cache owned by another source tree.

### Python packaging

- The complete source suite reports 178 passed and seven expected
  native-optional skips.
- Relocated shared and static wheels each report 132 passed and two expected
  skips. Both extensions use `$ORIGIN`; `ldd` reports no missing dependency.
- An injected `libunrelated_plugin.so` was absent from both wheels. The shared
  wheel contains only the generated extension and `libeklt-rebuild.so`; the
  static wheel contains only the generated extension.
- Shared wheel SHA-256:
  `f09419432e041e2e29c6d7d114188b8796bb0f9b2a1c082b847c61a2ce1c3676`.
- Static wheel SHA-256:
  `634ee007a77fb306de45cc44129e3a2fe872ee4ffff24001dbb93488db2c0e5b`.
- The unconfigured pure wheel and installed source distribution each report
  127 passed and seven expected native-optional skips.
- Pure wheel SHA-256:
  `b352be2d68d4f07fd36195d471ef24569aa66f7d191e545bc1c2463e17a953e5`.
- Pure source-distribution SHA-256:
  `d42c91270bcdc1ce8309b106211659fbf1bf87f828498d2f41b9973f74026d99`.

### ROS2 and official ELOPE

- The independent Jazzy overlay built from an exact source snapshot. Colcon
  reports ten tests with zero errors, failures, or skips.
- The complete official ELOPE `0028.npz` path passed with input SHA-256
  `7fdaa6b16a2e7913c7a034804144d2d51367583aba9056eac467dd44d6bebd32`.
- The run processed 386,785 events over 48.782 seconds, wrote 2,434
  EventPackets, retained 8,808 track rows across 38 IDs, and covered
  99.992825% of the source duration.
- All seven reconstruction, tracking, analysis, video, and evaluator status
  codes are zero. The run produced 698 validated additive timing rows,
  4,879-frame event and track videos, 244-frame reconstruction and patch
  videos, and every declared plot.
- Wall time was 54.21 seconds, peak resident memory was 244,072 KiB, and swap
  activity was zero. Logs contain no error, fatal, or rejected-packet entry.

### Documentation, packaging, and hygiene

- Doxygen completed without warnings.
- The cumulative source archive contained 274 regular entries. All 260 tracked
  blobs were byte-identical, and pinned FIBAR sources were present.
- The archive excluded build/install/output/data directories, gtwrap, Git
  metadata, local context, generated wrapper links, caches, and bytecode.
  Its pre-Stage-21-evidence SHA-256 was
  `286145ef914df11ea09d298e8b551c8cd69d8ff34b2f36f911a44b4a1910f4a6`.
- Bash syntax, ShellCheck warning severity, Python compilation/static checks,
  workflow and structured-file parsing, active removed-feature scans, and
  Docker BuildKit `--check` pass.
- The final exact-index snapshot repeats the affected workflow, documentation,
  source-package, byte-parity, and `git diff --cached --check` gates.

## Remaining work and stop condition

The following visible untracked legacy/draft groups remain excluded and
untouched:

- `python/eklt.tpl`;
- `python/eklt/`;
- `scripts/run_original_rosbag_example_demo.sh`;
- `scripts/run_ros1_event_only_example_demo.sh`;
- `test_ros1_demo.sh`.

Stage 21 has no blocker. Stop after staging this acceptance batch. The
multi-dataset and online-streaming plan starts only after the user reviews and
commits Stage 21, then explicitly says `next`.
