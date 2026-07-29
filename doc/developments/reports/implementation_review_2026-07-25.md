# Implementation Review — Event-Only EKLT + ROS2 Porting

> **Historical review.** Findings and reproduction commands below describe the
> dirty 2026-07-25 checkout. Later checkpointed stages changed the library
> layout, wrappers, ROS2 ownership, acceptance gates, and artifact schemas.
> Retain this report as audit evidence, but use
> `doc/developments/cpp_cuda_template_upgrade_plan.md` for current status.

- **Date:** 2026-07-25
- **Revision:** 2 (updated after the `cpp_cuda_template_project` alignment upgrade)
- **Branch:** `feature/impl_eklt_rospy_run_script` @ `a0632cf` (worktree dirty)
- **Reviewer:** Claude Opus 5 (automated review, host-verified where possible)
- **Scope:** Uncommitted/untracked event-only extension work, the committed
  `eklt_bridge` work, the template-alignment upgrade, and consistency of all
  `doc/developments/*.md` plans.
- **Status of this document:** Draft for review. No code changes were made.
  Filesystem side effects of this review: building the Python FIBAR extension
  in-place (`python/event_vision_utils/recon/_fibar*.so`), a throwaway CMake
  build under the session scratchpad, and this report.

---

## 0. Revision 2 — What Changed Since Revision 1

A substantial build-system and packaging upgrade landed between revisions
(`doc/developments/cpp_cuda_template_upgrade_plan.md`, all stages self-marked
complete, with evidence in
`reports/cpp_cuda_template_upgrade_acceptance_2026-07-25.md`).

**Independently re-verified on this host for Revision 2:**

| Claim | Source | Result |
|---|---|---|
| Native CTest 11/11 | acceptance report | ✅ **Confirmed** — 11/11, 0 failed |
| Python 80 passed, 1 skipped | acceptance report | ✅ **Confirmed** |
| Plain CMake builds without catkin | Stage 1 | ✅ **Confirmed** — configures + builds clean on a host with no ROS1 |
| Ceres handled as optional gate | Stage 1 | ✅ **Confirmed** — `Ceres not found: skipping test_eklt_core_photometric` |

The upgrade is real and materially improves this repository. It also **closes
one limitation from Revision 1**: the C++ core no longer requires a catkin
workspace to build or test, so §1.2's "not verifiable on this host" list has
shrunk considerably.

**Status of Revision 1 findings:**

| ID | Revision 1 finding | Status now |
|---|---|---|
| M1 | ROS1 event-only degenerate | 🔴 **Open** — untouched |
| M2 | Silent bug fixes unpinned by tests | 🔴 **Open** — `resetPatches` unchanged, still no characterization test |
| M3 | Acceptance gate too weak | 🔴 **Open** — `scripts/evaluate_outputs.py` unmodified (mtime 23 May) |
| m1 | Native wrapper not built by default | 🟡 **Changed shape** — now built via CMake/gtwrap; see m7 |
| m2 | `runtime_s` is a budget | 🔴 Open |
| m3 | Stale plot artifacts | 🔴 Open |
| m4 | Harris masking off-by-one | 🔴 Open (doc-only) |
| m5 | ROS1 needs `fibar_lib` unconditionally | 🟢 **Mitigated** — ROS1 now opt-in behind `EKLT_BUILD_ROS1=OFF` |
| m6 | Placeholder maintainer email | ✅ **Fixed** |

**New in Revision 2:** m7 (module shadowing), m8 (ROS1 regression tests no
longer build by default), C7 (wrapper audit records decisions the upgrade
reversed), C8 (M1 still absent from `known_limitations.md`), and an updated
plan inventory (§5.1) now covering four plan documents plus two reports. §7's
reproduction commands have been rewritten — the Revision 1 commands are
obsolete after the Catch2 v3 migration.

**Corrections to Revision 1 made in this revision:** none of the Revision 1
findings were withdrawn. One Revision 2 draft claim was withdrawn before
publication — an assertion that `doc/known_limitations.md` had gone stale on
the wrapper sections. It had in fact been updated correctly; C8 now credits
that and narrows to the real remaining gap.

**Policy reconciliation.** Revision 2 was written after `AGENTS.md` became the
authoritative repository contract. Two Revision 1 recommendations were revised
to comply: the C1 checkbox fix (AGENTS.md *mandates* checkboxes, so the fix is
to disambiguate their kinds, not remove them) and work-order item 1 (AGENTS.md
forbids autonomous staging/commit/push, so version-control cleanup is flagged
as a user-authorized action).

The headline remains unchanged: **the three major findings are all still open.**
The upgrade improved the build, packaging, CI, and documentation surface; it did
not touch the tracking-correctness or acceptance-gate issues.

---

## 1. Development Status Summary

The repository currently holds **three overlapping work streams** at very
different maturity levels:

| Stream | Tracked? | Plan doc | Real status |
|---|---|---|---|
| Event-only EKLT (FIBAR/ELOPE) | Untracked | `event_only_eklt_extension_plan.md` | Stages 0–9 self-marked complete; **substantially real**, two overstated claims |
| ROS2 bridge (hybrid) | Committed on branch | `eklt_ros2_porting_plan.md` | Stage 2A only; Stage 2B/2C/2D and all of Stage 3 open |
| ROS2 native port | Partially preempted | `eklt_ros2_porting_plan.md` Stage 3 | Not started as specified, but **partially preempted** by event-only Stage 8 |
| Template/build alignment | Untracked | `cpp_cuda_template_upgrade_plan.md` | Stages 0–7 self-marked complete; **verified accurate** on the gates reachable from this host |

The overall engineering quality of the event-only work is **higher than the
"unreviewed" label suggests**. The architecture holds up under inspection, the
dependency-direction rules are genuinely enforced, and the failure modes are
honest (hard `ImportError`, explicit `blocker` fields, exit code 2) rather than
silently degrading. Artifacts under `outputs/` are real run products, not
fabrications.

Two claims, however, do not survive verification: the ROS1 event-only mode is
**functionally degenerate** despite Stage 6 being marked complete (§2.1), and
the "original behavior preserved" guarantee is **not strictly true** because the
refactor silently corrected two pre-existing upstream bugs (§2.2).

The plan documents themselves are the weakest artifact in the repo: they use
checkbox semantics inconsistently, contain at least one factually stale claim,
and describe two mutually-preempting ROS2 strategies (§5).

### 1.1 Verification performed on this host

Everything below was executed, not inferred.

**Revision 2 (current, post-upgrade):**

| Check | Result |
|---|---|
| Native CMake configure, no ROS/catkin | **PASS** — OpenCV 4.6.0 found, Catch2 available, Ceres gracefully skipped |
| Native `cmake --build` | **PASS** |
| Native `ctest` | **11/11 passed, 0 failed** |
| Python suite | **80 passed, 1 skipped** |
| `event_vision_utils.recon._fibar` import resolution | Resolves to the **`.so`**, shadowing the new `.py` shim (see m7) |
| `import eklt` (gtwrap package) | **OK** |

**Revision 1 (pre-upgrade, retained for provenance):**

| Check | Result |
|---|---|
| Python suite, as found | 77 passed, **4 skipped** |
| Python suite, after `setup.py build_ext --inplace` | **80 passed, 1 skipped** |
| Native FIBAR pybind11 wrapper build | **Builds clean** from source |
| `tests/test_eklt_core_providers.cpp` (standalone g++, Catch2 v2) | **PASS** — 32 assertions / 6 cases |
| `tests/test_event_recon_fibar_core.cpp` (standalone g++, Catch2 v2) | **PASS** — 27 assertions / 5 cases |
| `eklt_core` forbidden-include scan | **CLEAN** (no ROS/FIBAR/Torch/ONNX headers) |
| `event_recon_fibar_core` ROS-freedom scan | **CLEAN** |

The C++ suites had previously only been run in Docker. Revision 1 confirmed
them via hand-rolled `g++` commands; Revision 2 confirms them through the
project's own supported `cmake` + `ctest` path, which is a materially stronger
result.

### 1.2 Not verifiable on this host

| Item | Blocker | Change since Rev 1 |
|---|---|---|
| ROS1 catkin build of `eklt` | No `~/eklt_catkin_ws`, no ROS1/catkin tools | unchanged |
| `tests/test_eklt_core_photometric.cpp` | Requires Ceres | now a **graceful** CMake skip rather than a hard blocker |
| `tests/test_patch`, `tests/test_tracker_utils` | Gated behind `EKLT_BUILD_ROS1` (default `OFF`) | **new** — see m8 |
| `ros2/eklt_event_packet_debug` build | Requires `event_camera_msgs`, `event_camera_codecs` | unchanged (acceptance report records a passing Jazzy container run) |
| MATLAB R2024b wrapper | No MATLAB on this host | **new** (acceptance report records a passing smoke test) |
| Any end-to-end demo re-run | Host has ROS2 Jazzy only, no ROS1 | unchanged |

`doc/known_limitations.md` and the upgrade acceptance report both document these
environment constraints accurately and prescribe the correct Docker fallbacks.
That part of the documentation is trustworthy — the acceptance report is
explicit that the ROS1 runtime build "remains an environment gate rather than a
source failure", which is exactly the right way to state it.

---

## 2. Major Issues

### M1 — ROS1 event-only mode is functionally degenerate, and this is undisclosed

**Severity:** High. Blocks the Stage 6 completion claim.
**Status (Rev 2):** 🔴 Open. Untouched by the template upgrade.

**Evidence.** Measured directly from the committed track outputs:

| Run | Rows | Unique IDs | Time span | Rows/track |
|---|---|---|---|---|
| `outputs/original_rosbag_example` (frame-based) | 50 784 | 100 | 6.875 s | **507.8** |
| `outputs/ros1_event_only_example` | 255 | 89 | **0.1138 s** | **2.87** |
| `outputs/official_elope_event_only/tracking` (ROS2) | 10 548 | 71 | 48.757 s | 148.6 |

The ROS1 event-only demo covers **1.7 % of a 6.87 s bag**. 89 features are
initialized and produce a mean of 2.87 rows each — they are being *initialized*,
not *tracked*. The ROS2/ELOPE path, by contrast, is genuinely healthy and
demonstrates the concept works when driven correctly.

**Why it passed the gate.** `scripts/evaluate_outputs.py` asserts only:
`summary.status == "passed"`, tracks file non-empty, at least one data row, and
`track_rows > 0`. The extension plan's own negative gate —
*"Do not mark complete when: example demo runs but tracks are empty"* — is
satisfied **literally** while missing its evident intent.

**Rationale for flagging.** `doc/known_limitations.md` is otherwise candid about
scope and environment, but says nothing about this. A reader of the plan plus
the limitations doc would reasonably conclude ROS1 event-only tracking works.
It does not. This is the single largest gap between claimed and actual status.

**Suggested fix.**
1. Reopen Stage 6 in `event_only_eklt_extension_plan.md`; uncheck
   "ROS1 event-only example demo completes" and the corresponding goal-mode
   stop condition.
2. Debug the root cause. First hypothesis to test: interaction between
   `--event_only_reconstruction_interval_events=5000` and the initialization
   timing in `Tracker::updateEventOnlyReconstruction`
   (`src/tracker.cpp`). Note that before the first image, the interval throttle
   is bypassed (`got_first_image_ && ... < interval`), so exactly one
   reconstruction is admitted early and subsequent ones are gated behind 5000
   events; if patches are declared lost before the second frame arrives, tracks
   die immediately. Second hypothesis: `bootstrap:=events` path interacting with
   `min_corners=0` (see M2) so no replenishment ever occurs.
3. Until fixed, add an explicit entry to `doc/known_limitations.md`.

### M2 — The provider refactor silently fixed two pre-existing bugs, invalidating the "behavior preserved" claim

**Severity:** High (correctness-positive, but the claim is wrong and the change is unpinned).
**Status (Rev 2):** 🔴 Open. `resetPatches` is byte-identical to Revision 1
(re-checked: still `RequestGradientPatch(patch_provider, patches_[index], p)`
and `setBatchSize(patches_[index], ...)`), and no characterization test was
added. Note this is now *more* pressing: with `EKLT_BUILD_ROS1=OFF` by default,
the ROS1 tests that might have caught a regression here do not even build (m8).

`src/tracker.cpp::resetPatches` was rewritten to use
`eklt_core::CFramePatchProvider`. Comparing against `git show HEAD:src/tracker.cpp`
reveals the original contained two defects, **both now silently corrected**.

**(a) Off-by-`p` extraction window.** `padBorders` (`include/tracker.h:184`)
calls `copyMakeBorder(..., p, p, p, p, BORDER_CONSTANT)`, so padded index `i`
maps to original index `i - p`. The two call sites disagreed:

| Function | Original `x_min` | Padded span | Original-image span | Centered at |
|---|---|---|---|---|
| `initPatches` | `center.x` | `[cx, cx+2p]` | `[cx-p, cx+p]` | `cx` ✅ |
| `resetPatches` | `center.x - p` | `[cx-p, cx+p]` | `[cx-2p, cx]` | `cx - p` ❌ |

Re-initialized features therefore received gradient patches offset by `p` pixels
(with the default `patch_size=25`, `p = 12`) — effectively initialized against
the wrong image region.

**(b) Batch size written to a discarded temporary.** The original called
`setBatchSize(reset_patch, ...)` where `Patch& reset_patch = new_patches[i]` is
a short-lived object; `patches_[index]` — the patch actually retained — kept a
stale batch size. The new code correctly targets `patches_[index]`.

**Why these survived upstream.** `config/eklt.conf:24` ships `--min_corners=0`
(the IJCV paper setting), which disables re-initialization entirely. The flag's
compiled default is `60` (`src/flags.cpp:6`). `resetPatches` is therefore **dead
code in the shipped configuration**, which is precisely why two bugs accumulated
there unnoticed.

**Rationale for flagging.** These are genuine improvements and should be kept.
The problem is threefold: (i) the plan asserts "Original frame-camera EKLT
behavior preserved" and "no algorithm or runtime ROS behavior changes", which is
now false for the reinit path; (ii) the change is **unpinned by any test**, so a
future refactor could silently revert it; (iii) anyone comparing tracking output
against published EKLT numbers with `min_corners > 0` will see a discrepancy
with no changelog entry explaining it.

**Suggested fix.**
1. Amend the plan wording: preserved for the *default* (`min_corners=0`)
   frame-backed path; **deliberately corrected** for the reinit path.
2. Add a Catch2 characterization test pinning the patch window to
   `[cx-p, cx+p]` for both `initPatches` and `resetPatches`, and asserting
   `patches_[index].batch_size_` is updated after reset. This is the guard that
   should have existed before the refactor.
3. Record both fixes in the README/changelog as intentional behavior changes.

### M3 — Acceptance gate cannot distinguish tracking from initializing

**Severity:** High (process). Root cause that allowed M1 to be marked complete.
**Status (Rev 2):** 🔴 Open. `scripts/evaluate_outputs.py` is unmodified
(mtime 23 May, no threshold logic present).

`scripts/evaluate_outputs.py` validates *presence*, never *quality*: non-empty
file, `track_rows > 0`, required plots exist and are non-empty, `gt_status`
well-formed. A tracker that emits three rows per feature and dies after 114 ms
passes cleanly.

**Rationale.** Every downstream completion claim in
`event_only_eklt_extension_plan.md` §"Goal-Mode Stop Conditions" is defined in
terms of this script. If the gate is too weak, the entire completion ledger
inherits that weakness — which is exactly what happened.

**Suggested fix.** Add threshold checks with explicit, overridable CLI flags:
- `--min-rows-per-track` (suggest default 10; frame baseline achieves 508)
- `--min-span-fraction` — ratio of track time span to input duration
  (suggest default 0.5; ROS1 event-only currently scores 0.017)
- Emit these ratios into `summary.json` so regressions are visible in the
  artifact itself, not only at gate time.

---

## 3. Minor Issues

### m1 — Native FIBAR wrapper is not built by default; four tests skip silently

As found, the suite reported `77 passed, 4 skipped`, all four skips being
`tests/event_vision_utils/test_recon_fibar_native.py` with reason
*"native FIBAR wrapper is not built"*. That is the **only** coverage exercising
the C++ FIBAR core through Python — the plan's Stage 3 exit criterion
"Python wrapper uses C++ core."

A green suite that never touched the C++ core is misleading. The wrapper builds
cleanly in well under a minute (verified), so there is no real cost to building it.

**Suggested fix.** Either build the extension in CI before `pytest`, or promote
the skip to a failure when an env var such as `EKLT_REQUIRE_NATIVE_FIBAR=1` is
set, and set it in CI. Document the build step in `python/README` or the root
README next to the test command.

**Status (Rev 2):** 🟡 Changed shape. The wrapper is now produced by the CMake/
gtwrap path, and on this host the suite reports `80 passed, 1 skipped` with the
*placeholder* test skipping (reason: "native FIBAR wrapper is available") — the
inverse of Revision 1. That is the desired direction. However, the underlying
concern stands: on a clean checkout with nothing built, the four native tests
skip again and the suite still reports green. The fix above (fail-on-skip in CI)
is still the right one, and is now cheap because `build_linux.yml` already
builds the native targets.

### m2 — `runtime_s` in ELOPE summaries is a configured budget, not a measurement

`outputs/official_elope_event_only/tracking/summary.json` reports
`"runtime_s": 10.0`. This traces to `RUNTIME_S` in
`scripts/run_ros2_elope_event_only_example_demo.sh:185`, passed through as
`--runtime-s`. It is the demo's wall-clock budget, not measured execution time.
The reconstruction summary alongside it reports a genuinely measured
`2.6979421530268155`, so the two fields look alike but mean different things.

`doc/developments/official_elope_acceptance_report.md:107` propagates this as
"Demo runtime: `10.0 s`".

**Suggested fix.** Rename to `runtime_budget_s`, or measure actual elapsed time.
Do not let a configured constant occupy a field named like a measurement.

### m3 — Stale plot artifacts in both ROS1 output directories

`outputs/original_rosbag_example/plots/event_rate.png` and
`outputs/ros1_event_only_example/plots/event_rate.png` are both **exactly 5311
bytes** (identical size across two different runs), and neither appears in its
own `summary.json` `plots` array. Both summaries report
`"event_count": 0` and `"event_rate_source": "rosbag_unavailable"`, i.e. the
event-rate plot could not be generated on those runs.

These are leftovers from an earlier run and are inconsistent with the summaries
that sit beside them.

**Suggested fix.** Have the demo scripts clear the output directory (or at least
`plots/`) before writing, so an output directory always reflects exactly one run.

### m4 — Harris masking off-by-one differences (undocumented behavior change)

`CFrameHarrisCandidateProvider` (`include/eklt_core/initialization_providers.h:151`)
is a corrected reimplementation of the original inline mask, not an exact one:

| Aspect | Original | New |
|---|---|---|
| Border rows/cols | `rowRange(0,hp).colRange(0,w-1)` — last column/row never masked | Full `rowRange`/`colRange` — correct |
| Exclusion zone | `rowRange(min_y,max_y)` — exclusive upper bound | `max_y + 1` — inclusive |
| Corner container | `std::vector<cv::Point2d>` bound to `const cv::Point2f&` | `std::vector<cv::Point2f>` — type-correct |

All three changes are improvements, and `goodFeaturesToTrack(..., useHarris=true)`
is preserved. But detected corner sets can differ slightly near image borders
and near existing features, which is again a silent behavior change.

**Suggested fix.** Note it in the changelog alongside M2. Low risk; no code change needed.

### m5 — ROS1 build now unconditionally requires `fibar_lib`

`include/tracker.h` gained an unconditional
`#include "event_recon_fibar_core/fibar_reconstructor.h"`. Since `tracker.h` is
the central ROS1 header, the catkin build now depends on `lib/fibar_lib`
(a git submodule) **even when `--event_only_mode=false`**.

This is permitted by the plan's dependency rules (`eklt_ros1 -> event_recon_fibar_core`
is explicitly allowed), so it is not a violation — but it widens the default
build surface and makes a fresh clone fail without `git submodule update --init`.

**Suggested fix.** Either document the submodule step prominently in the README
build section, or hold the reconstructor behind a forward declaration +
`std::unique_ptr` pimpl so the header dependency is confined to `tracker.cpp`.
The member is already `std::unique_ptr<...>`, so a forward declaration is likely
sufficient and cheap.

**Status (Rev 2):** 🟢 Largely mitigated. ROS1 is now opt-in behind
`option(EKLT_BUILD_ROS1 ... OFF)` (`CMakeLists.txt:22`), so the default native
build never compiles `tracker.h` and therefore never needs `fibar_lib` for that
reason. The coupling still exists when `EKLT_BUILD_ROS1=ON`; the forward-
declaration cleanup remains worthwhile but is no longer blocking a fresh clone.

### m6 — `ros2/eklt_event_packet_debug/package.xml` has a placeholder maintainer ✅ FIXED

Was `<maintainer email="todo@example.com">`. Now correctly lists
Pietro Califano and Daniel Gehrig. No further action.

### m7 — NEW: compiled `_fibar.so` shadows the new `_fibar.py` shim

**Severity:** Minor-to-moderate. Environment-dependent behavior.

The wrapper migration to gtwrap introduced
`python/event_vision_utils/recon/_fibar.py`, a compatibility facade that
delegates to `eklt.CFibarReconstructorAdapter`. But the legacy pybind11
extension still builds to the **same module name**, and both can coexist:

```
python/event_vision_utils/recon/_fibar.cpython-312-x86_64-linux-gnu.so   # legacy pybind11
python/event_vision_utils/recon/_fibar.py                                # new gtwrap shim
```

Verified empirically — Python's `FileFinder` tries extension loaders before
source loaders, so the **`.so` wins**:

```
resolved to: .../event_vision_utils/recon/_fibar.cpython-312-x86_64-linux-gnu.so
native_available: True
```

So which of two independent binding implementations you execute depends on
whether a stale `.so` is lying around. A developer who built the old
`setup.py build_ext` path and then pulls the gtwrap work will keep silently
running the *old* binding, and their green test suite will say nothing.

`.gitignore` covers `*.so`, so this cannot reach the repository — it is purely
a local-working-copy hazard. But it is exactly the class of problem that costs
an afternoon to diagnose.

**Rationale.** Revision 1 praised this module for its honest failure mode (N5):
`ImportError` rather than a silent Python fallback. Module shadowing
reintroduces a silent-divergence path through the back door — not in the error
handling, but in the import resolution.

**Suggested fix.** Pick one:
- retire the legacy `setup.py` extension target now that gtwrap is the
  supported path, or
- give the gtwrap facade a distinct module name (e.g. `_fibar_gtwrap.py`) and
  have `fibar.py` select explicitly, or
- have the build emit a warning when both artifacts are present.

Also worth adding a one-line `make clean`-style note to the wrapper docs.

### m8 — NEW: ROS1 regression tests no longer build by default

**Severity:** Minor (coverage visibility).

`tests/CMakeLists.txt` now splits targets into `EKLT_ROS_FREE_TESTS` (built
always) and a ROS1 group gated on `if(EKLT_BUILD_ROS1 AND TARGET eklt)`:

```cmake
if(EKLT_BUILD_ROS1 AND TARGET eklt)
    foreach(test_target IN ITEMS test_patch test_tracker_utils)
```

`EKLT_BUILD_ROS1` defaults to `OFF`, so `test_patch` and `test_tracker_utils`
— the two suites the ROS2 porting plan's Stage 1 specifically commissioned to
pin `Patch` event-buffer behavior, event ordering, and image selection before
any transport refactor — **do not build in the default configuration**. The
verified "11/11" native CTest run does not include them.

This is a defensible design (they need ROS1 types), and `build_ros1.yml` exists
to cover them in CI. It is flagged because the headline pass number now measures
strictly less than it did before, and that is easy to miss.

**Rationale.** Combined with M2, the practical picture is: the only tests that
could detect a regression in `Patch`/tracker behavior are off by default, while
the two silently-corrected `resetPatches` bugs remain unpinned by anything.

**Suggested fix.** Confirm `build_ros1.yml` actually runs `ctest` (not just the
build), and state in the README that the default native CTest count excludes the
ROS1 suites. When the M2 characterization tests are written, put them in a
**ROS-free** target so they run in the default gate.

---

## 4. Notes and Observations (no action required)

These are things I verified as **correct** and want on record, so a future
reviewer does not re-litigate them:

- **N1 — Photometric normalization is faithfully preserved.**
  `eklt_core::NormalizeImageToUnitRange64` keeps the exact
  `convertTo(CV_64F, 1.0/255.0)` branch for `CV_8U` input. Min–max normalization
  applies **only** to non-8U images (the FIBAR `CV_32F` reconstructions). The
  original frame path through `Optimizer::getLogGradients` is therefore
  bit-identical. This was the highest-risk-looking change in the diff and it is clean.

- **N2 — Border handling matches.** `padBorders` uses `BORDER_CONSTANT`
  (value 0); `CFramePatchProvider::requestPatch` zero-initializes and skips
  out-of-bounds pixels via `continue`, tracking them in `valid_mask`. Equivalent.

- **N3 — `trunc()` → `round()` on patch centers is inert.** The provider rounds
  (`initialization_providers.h:246`) where the original truncated. Since
  `cv::goodFeaturesToTrack` returns integral coordinates and no sub-pixel
  refinement is applied, the two agree in practice. Worth remembering if
  `cornerSubPix` is ever introduced.

- **N4 — The provider seam is well designed.** `CFibarPatchProvider` and
  `CFibarImageProvider` derive from callback-based bases and take a `TCallback`,
  so FIBAR is *injected* from the ROS layer. The `eklt_core` headers reference
  FIBAR by **class name only** — the forbidden-include scan confirms zero FIBAR
  headers. This is the right way to name a seam after its intended consumer
  without coupling to it, and it is what makes the future SuperEvent provider a
  drop-in.

- **N5 — Failure modes are honest.** `event_vision_utils.recon.fibar` raises
  `ImportError` rather than falling back to a Python reimplementation of FIBAR
  (which would have violated the plan's explicit "do not duplicate FIBAR logic"
  rule). The example scripts write `summary["blocker"]` and return exit code 2.
  This is why the `outputs/` artifacts can be trusted as real run products.

- **N6 — Genuine concurrency fixes in `tracker.h`/`tracker.cpp`.**
  `static ros::Rate rate_controller` → non-static (a `static` local in a member
  function is shared across all instances); `waitForEvent`'s unconditional
  `while(true)` → `while (ros::ok() && !stop_requested_)` returning `bool`;
  detached thread → owned `std::thread` joined in a new destructor. The old
  code could not shut down cleanly.

- **N7 — Reconstruction outputs were genuinely re-run, not copied.**
  `elope_reconstruction_real/` and `official_elope_event_only/reconstruction/`
  have identical file sizes, which initially looked like a copy, but their
  summaries record different measured runtimes (2.6337 s vs 2.6979 s). Two real
  deterministic runs.

---

## 5. Plan Consistency, Overlaps, and Cleanup

This section addresses the secondary request: consistency, deprecations,
cleanup, merges, and overlaps among the plan documents.

### 5.1 Inventory

Updated for Revision 2 — there are now **four** plan documents plus two reports.

| Document | Tracked | Role | Recommended disposition |
|---|---|---|---|
| `eklt_ros2_porting_plan.md` | Yes (modified) | Active plan, ROS2 port | **Keep, but reconcile with Stage 8 of the event-only plan** |
| `event_only_eklt_extension_plan.md` | No | Active plan, event-only | **Keep; reopen Stage 6** |
| `cpp_cuda_template_upgrade_plan.md` | No | **New** — build/packaging alignment | **Archive on merge** — it is a completed one-shot migration, not an ongoing plan |
| `event_only_implementation_map.md` | No | File/ownership map | **Merge into the extension plan** |
| `event_only_integration_audit.md` | No | Stage 0 audit | **Archive** (historical, contains stale claim) |
| `event_only_wrapper_audit.md` | No | Stage 0 audit | **Archive** — now doubly superseded: its "pybind11 + setuptools" decision has been replaced by the gtwrap path, and its "no MEX target in the current build" statement is obsolete |
| `official_elope_acceptance_report.md` | No | Run report | **Move to `reports/`** alongside this document (still not done) |
| `reports/cpp_cuda_template_upgrade_acceptance_2026-07-25.md` | No | **New** — upgrade evidence | **Keep** — correctly placed, good precedent |

**Positive note.** The upgrade acceptance report was filed directly into
`doc/developments/reports/`, which is the convention Revision 1 §5.4.3
recommended. That is the right pattern; only
`official_elope_acceptance_report.md` still needs relocating.

**New consistency risk (C7).** `event_only_wrapper_audit.md` records decisions
that the template upgrade has since reversed — most notably "Use direct C++
binding with pybind11 plus setuptools C++ extension" and "do not depend on
gtwrap for Python until helper is fixed". The gtwrap helper evidently *was*
fixed (`lib/wrap` pinned at `bf9f786`), and Python now goes through it. Anyone
reading the audit today would implement the wrong thing. Archiving it with a
superseded-by header resolves this.

### 5.2 Overlaps among plans

**O1 — Two ROS2 strategies, one of which preempts the other.**
This is the most consequential overlap.

`eklt_ros2_porting_plan.md` Stage 3 specifies a *clean cutover*: replace catkin
with `ament_cmake`, **keep the package name `eklt`**, **keep the executable name
`eklt_node`**, port the viewer, replace gflags with ROS2 params. It also states
plainly: *"Stage 3 starts only after the stage-2 hybrid release has been
validated and tagged."*

`event_only_eklt_extension_plan.md` Stage 8 delivered a **native ROS2 EKLT node**
(`ros2/eklt_event_packet_debug/src/event_only_eklt_node.cpp`, 462 lines) with
native ROS2 params and a ROS-free Ceres photometric tracker — i.e. it built a
large fraction of Stage 3's substance, but:

- in a **different package** (`eklt_event_packet_debug`, not `eklt`),
- under a **different executable** (`event_only_eklt_node`, not `eklt_node`),
- **before** Stage 2's preconditions were met (Stage 2B, 2C, 2D all unchecked;
  Stage 1 and Stage 2 acceptance criteria largely unchecked; no hybrid tag exists).

Neither plan acknowledges the other. Left alone, this converges on two parallel
ROS2 EKLT implementations with divergent parameter surfaces.

**Suggested resolution.** Decide explicitly, and record the decision in both docs:
either (a) `eklt_event_packet_debug` is the seed of the Stage 3 port and should
be renamed/absorbed into `eklt` with the gating relaxed, or (b) it stays a
permanent debug/prototype package and Stage 3 proceeds independently — in which
case say so, and state which one is the supported event-only entry point.
Option (a) looks cheaper given the node already works on real ELOPE data.

**Post-review resolution (2026-07-25).** The prototype is the Stage 3 seed and
now uses the ROS-valid package identity `eklt_rebuild`, derived from the root
`eklt-rebuild` library name. Its build consumes the canonical root targets
instead of compiling duplicate ROS2-only core libraries.

**O2 — Two Python packages with overlapping responsibilities in one distribution.**
`python/pyproject.toml` still declares `name = "eklt-bridge"` and
`description = "Stage-2 EKLT bridge helpers..."`, but now ships
`include = ["eklt_bridge*", "event_vision_utils*"]` and exports console scripts
from both. One distribution, two unrelated work streams, one misleading name.

Functional overlap between them:

| Concern | `eklt_bridge` | `event_vision_utils` |
|---|---|---|
| Event transport | `messages/transport.py` (`EEVS1\0` npz over `UInt8MultiArray`) | `ros2/event_packet.py` (`event_camera_msgs/EventPacket`) |
| ROS2 publishing | `ros2_source/node.py` | `ros2/elope_event_packet_publisher.py` |
| Visualization | `visualization/preview.py` | `viz/{accumulation,polarity_image,time_surface,event_rate,video_writer}.py` |

**Suggested resolution.** Rename the distribution to something neutral
(e.g. `eklt-python`) with two packages, or split into two distributions. Update
the stale `description`. Then pick one visualization stack — `event_vision_utils.viz`
is substantially more capable — and have `eklt_bridge.visualization.preview`
delegate to it rather than maintaining a parallel renderer.

**O3 — Three event representations with two incompatible conventions.**

| Type | Time | Polarity |
|---|---|---|
| `eklt_bridge.primitives.EventStream` | `t_s`, float64 **seconds** | `p01`, uint8 **{0,1}** |
| `event_vision_utils.core.EventArray` | `t_us`, int64 **microseconds** | `p`, int8 **{-1,+1}** |
| `event_recon_fibar_core::SEventBatchView` | `t_us`, int64 microseconds | `int8_t` signed |

The extension plan explicitly mandated the second convention, stating: *"Do not
depend on its current `EventStream` directly because it uses seconds and `p01`;
new EKLT utilities should use microseconds and signed polarity."* The bridge's
`EventStream` is intentionally `eventDataGenLibPy`-compatible, so both choices
are defensible in isolation — but they now ship together with **no documented
conversion boundary** and no adapter between them.

**Suggested resolution.** Add an explicit, tested converter (e.g.
`event_vision_utils.io.from_event_stream` / `to_event_stream`) and document
which convention applies at which layer. This is cheap now and expensive after
a third consumer appears.

### 5.3 Consistency issues within the plans

**C1 — Overloaded checkbox semantics.** `- [ ]` / `- [x]` are used for at least
four different meanings across the docs:

1. *Completion* — "Stage 1 event tuple utilities implemented" `[x]`
2. *Negative gate that must stay unchecked* — "Do not mark complete when: Only
   unit tests pass" `[ ]`
3. *Standing prohibition* — "Do not implement E2VID..." `[x]` (checked to mean
   "we complied", which reads as "we did it")
4. *Guidance / decisions* — most `Use:` bullets in the audits, left `[ ]`
   permanently

A reader cannot mechanically compute completion, and "Do not implement E2VID"
marked `[x]` is actively confusing.

**Suggested fix (revised for Rev 2).** `AGENTS.md` now makes checkboxes
mandatory policy: *"Plans and staged work use Markdown checkboxes (`- [ ]` and
`- [x]`) with explicit acceptance and stop conditions."* So the fix is **not** to
abandon them, but to disambiguate the kinds — which the policy's "explicit
acceptance and stop conditions" phrasing already anticipates:

- keep `- [ ]` / `- [x]` for **completion and acceptance** only;
- move standing prohibitions ("Do not implement E2VID…") into an unchecked
  **Constraints** list, since a checked prohibition reads as "we did it";
- keep stop conditions as checkboxes but under an explicit
  **Stop conditions (must remain unchecked)** heading so their polarity is
  unambiguous.

This satisfies the AGENTS.md contract while removing the ambiguity.

**C2 — Factually stale claim in `event_only_integration_audit.md`.** It states:

> - [x] Only pyproject found in current tree; package files not present in
>   current checkout listing.

`python/eklt_bridge/` contains 26 `.py` files and is committed on this branch.
The audit was evidently written from a checkout where the bridge was absent, and
the derived guidance ("Avoid depending on missing package modules until
confirmed") is now misleading.

**Suggested fix.** Archive the audit with a header noting it is a point-in-time
Stage 0 document, and correct or strike this bullet.

**C3 — The audit and the plan disagree on the same item.**
`event_only_integration_audit.md` leaves *"Existing image-frame path must remain
intact for original rosbag example demo"* **unchecked**, while
`event_only_eklt_extension_plan.md` Stage 5 marks *"Original frame-camera EKLT
behavior preserved"* **checked**. Given M2, the audit's unchecked state is
arguably the more accurate of the two.

**C4 — Acceptance claims that the artifacts contradict.** The plan's Stage 6
requires `plots/event_rate.png` for each run; both ROS1 summaries report
`event_rate_source: "rosbag_unavailable"` and omit it from their `plots` arrays,
yet stale copies sit in the directories (see m3). The checked box, the summary,
and the filesystem tell three different stories.

**C5 — `eklt_ros2_porting_plan.md` internal inconsistency.** Stage 1 items are
all `[x]` (Catch2 seams, regression coverage) but Stage 1 **acceptance** is
entirely `[ ]` — including "Catkin build still succeeds" and "Catch2 tests build
and pass under `ctest`". Since this review confirms two of those suites pass
standalone, some of this is simply un-updated bookkeeping rather than real
incompleteness.

**C6 — Only a cosmetic diff is staged for the tracked plan.** The sole
uncommitted change to `eklt_ros2_porting_plan.md` is `synthetic` → `fixture` in
Stage 2B. All the substantive event-only planning lives in untracked files, so
`git log` gives no signal that a second major work stream exists. This has
worsened in Revision 2: the entire template-upgrade work stream is also
untracked.

**C7 — NEW: `event_only_wrapper_audit.md` records decisions the upgrade
reversed.** The audit selects "direct C++ binding with pybind11 plus setuptools
C++ extension" and explicitly says "do not depend on gtwrap for Python until
helper is fixed", noting the gtwrap Python path "stops with fatal error". The
template upgrade fixed exactly that: `lib/wrap` is now pinned at `bf9f786` and
Python goes through gtwrap via `wrap_interfaces/fibar_reconstructor.i`. The audit also
treats MATLAB as "future optional work", which the working R2024b MEX
contradicts. Verified unchanged since 22 May.

A reader following the audit today would implement the superseded design.
Archiving it with a `Superseded by cpp_cuda_template_upgrade_plan.md Stage 3`
header resolves this.

**C8 — `doc/known_limitations.md` was correctly updated, but still omits M1.**
Its wrapper section now accurately describes the gtwrap Python path
(`./build_lib.sh --python`) and the MATLAB R2024b preload requirement. The
upgrade kept this file current, which is the right discipline and worth
crediting explicitly.

The gap is unchanged from Revision 1: a targeted scan for any mention of the
ROS1 event-only track-quality problem returns nothing. Given that this file is
the project's honest-disclosure surface, and that it demonstrably *does* get
maintained, it remains the correct place to record M1 until M1 is fixed.

### 5.4 Recommended documentation actions

1. **Create** `doc/developments/archive/` and move `event_only_integration_audit.md`
   and `event_only_wrapper_audit.md` there with a "point-in-time Stage 0" header
   plus, for the wrapper audit, a `Superseded by cpp_cuda_template_upgrade_plan.md
   Stage 3` note (C7).
2. **Merge** `event_only_implementation_map.md` into
   `event_only_eklt_extension_plan.md` (the file/ownership lists duplicate the
   plan's Deliver sections nearly one-for-one).
3. **Move** `official_elope_acceptance_report.md` into
   `doc/developments/reports/` next to this document and the upgrade acceptance
   report. Still outstanding.
4. **Add a cross-reference block** at the top of both active plans stating that
   the other exists and how they relate (resolves O1's silence). With the
   template plan added, a short index at the top of `doc/developments/` would
   now serve better than pairwise cross-references.
5. **Archive `cpp_cuda_template_upgrade_plan.md` on merge.** It is a completed
   one-shot migration, not an ongoing plan; leaving it beside the two active
   plans invites confusion about what is still in flight.
6. **Disambiguate checkbox kinds** per C1, in a way that still satisfies the
   `AGENTS.md` requirement that plans use checkboxes with explicit acceptance
   and stop conditions.
7. **Record M1 in `doc/known_limitations.md`** until it is fixed (C8).
8. **Get the untracked work under version control.** Roughly 7 000 lines at
   Revision 1, substantially more now with the template upgrade. Note that
   `AGENTS.md` forbids the agent from staging, committing, tagging, or pushing
   without explicit per-action authorization — so **this step is the user's
   call**, listed here as a recommendation rather than something to be actioned
   autonomously.

---

## 6. Suggested Work Order

Ordered by dependency and risk, not by severity alone.

Revised for Revision 2. The template upgrade has already delivered what was
item 1's prerequisite infrastructure (native build, CI, packaging), so the
remaining work is now almost entirely **correctness and bookkeeping**.

| # | Action | Addresses | Rationale |
|---|---|---|---|
| 1 | Get untracked work under version control (**user-authorized**; `AGENTS.md` forbids autonomous staging/commit) | §5.4.8 | Still outstanding, and the tree has grown substantially since Rev 1 — this is now the single largest risk in the repo |
| 2 | Resolve `_fibar` module shadowing | m7 | Do first: until settled, *every* Python result is ambiguous about which binding it exercised |
| 3 | Add characterization tests for `initPatches`/`resetPatches` window + batch size, in a **ROS-free** target | M2, m8 | **Must precede** any further tracker work. ROS-free placement means they run in the default 11/11 gate rather than the off-by-default ROS1 group |
| 4 | Strengthen `evaluate_outputs.py` thresholds | M3 | Must precede M1 debugging, else you cannot tell when it is fixed |
| 5 | Debug ROS1 event-only degeneracy | M1 | The actual functional gap; needs Noetic Docker or the new `build_ros1.sh` path |
| 6 | Fail-on-skip for native FIBAR tests in CI | m1 | Now cheap — `build_linux.yml` already builds the native targets |
| 7 | Amend plan wording; reopen Stage 6; fix checkbox semantics; record M1 in `known_limitations.md` | M2, C1–C8 | Bring the ledger in line with reality |
| 8 | Decide the ROS2 strategy (absorb vs. parallel) | O1 | Architectural fork; cost grows with delay. The upgrade's `EKLT_BUILD_ROS1` split makes this decision *easier* to act on now |
| 9 | Rename distribution; add `EventStream`↔`EventArray` converter | O2, O3 | Cheap now, expensive after a third consumer |
| 10 | Doc archive/merge/move; clear output dirs | §5.4, m3, C7 | Housekeeping; archive the wrapper audit with a superseded-by header |

Items 3 and 4 remain deliberately placed **before** item 5: both are guards that
make the M1 fix verifiable and prevent the M2 corrections from being lost. Doing
5 first would mean debugging against a gate that cannot detect success.

Item 2 moved up in Revision 2 because module shadowing undermines the
interpretation of every Python test result, including the `80 passed, 1 skipped`
figure that both this report and the upgrade acceptance report rely on.

---

## 7. Reproducing This Review

> **Revision 2 note.** The Revision 1 commands are obsolete. `tests/catch_main.cpp`
> was deleted and Catch2 upgraded to v3 (`Catch2::Catch2WithMain`), so the
> hand-rolled `g++` invocations no longer compile. Use the project's own CMake
> path below — it is both simpler and the supported route.

```bash
# C++ suites via the project build (no ROS1 / no catkin needed)
cmake -S . -B build/native-verify -DCMAKE_BUILD_TYPE=Release
cmake --build build/native-verify -j4
( cd build/native-verify && ctest --output-on-failure )
# Expect: 100% tests passed, 0 tests failed out of 11
# Ceres absent  -> test_eklt_core_photometric is skipped at configure time
# EKLT_BUILD_ROS1=OFF -> test_patch / test_tracker_utils are NOT built (see m8)

# Python suite
cd python && python -m pytest -q -rs && cd ..

# m7: check which _fibar implementation actually loads
python -c "import event_vision_utils.recon._fibar as m; print(m.__file__)"
ls python/event_vision_utils/recon/_fibar*     # both .so and .py present == shadowing

# Dependency-direction invariants
grep -rniE "ros/|rclcpp|dvs_msgs|torch|onnx|superevent" include/eklt_core/   # class names only
grep -rniE "rclcpp|ros/|ros::" include/event_recon_fibar_core/ src/event_recon_fibar_core/

# M2: confirm the resetPatches fixes are still present and still unpinned
sed -n '/void Tracker::resetPatches/,/^}/p' src/tracker.cpp | grep -n "RequestGradientPatch\|setBatchSize"
grep -rn "resetPatches" tests/ || echo "M2 STILL UNPINNED: no test references resetPatches"

# M3: confirm the acceptance gate still has no quality thresholds
grep -n "rows_per_track\|span_fraction\|min-rows" scripts/evaluate_outputs.py || echo "M3 still open"

# M1: track quality metric
awk '{n++; ids[$1]; if(NR==1||$2<min)min=$2; if(NR==1||$2>max)max=$2}
     END{print "rows="n, "ids="length(ids), "span="max-min, "rows_per_track="n/length(ids)}' \
  outputs/ros1_event_only_example/tracks.txt
```
