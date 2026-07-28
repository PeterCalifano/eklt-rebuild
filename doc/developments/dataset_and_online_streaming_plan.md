# Multi-Dataset and Online EKLT Streaming Plan

This checklist defines the work that follows the accepted
`cpp_cuda_template_project` alignment. It extends the committed single-sequence
and synchronous ROS2 behavior without replacing the ROS-free EKLT algorithm,
the original ROS1 frame-backed path, or the FIBAR event-only path.

The plan is intentionally divided into one functional stage per user commit.
No stage begins until the preceding stage has been reviewed, committed by the
user, recorded in the checkpoint ledger, and followed by an explicit `next`.

## Required upgrade baseline

- [ ] Wait for Stage 21 of
      `doc/developments/cpp_cuda_template_upgrade_plan.md` to have an accepted
      commit.
- [ ] Record the accepted upgrade commit before editing production files.
- [ ] Require the accepted `eklt_rebuild::eklt-rebuild` native target,
      `eklt_rebuild` Python wrapper, `event_vision_utils` data model, and
      single-sequence ELOPE pipeline.
- [ ] Preserve the Stage 14 ROS2 EventPacket behavior and its recorded-bag
      regressions as the deterministic reference when online processing is
      introduced.
- [ ] Preserve both native initialization modes:
      `ETrackerInitializationMode::FrameBacked` and
      `ETrackerInitializationMode::EventOnlyFibar`.

## Architecture invariants

- [ ] Keep dataset discovery, file decoding, ROS2 transport, queueing,
      diagnostics, and persistence outside `eklt_core`.
- [ ] Keep `CEkltTrackerOrchestrator` synchronous, deterministic, ROS-free, and
      exclusively owned by one execution context.
- [ ] Do not add a second EKLT, Harris, Ceres, KLT, FIBAR, feature-lifecycle, or
      gradient-cache implementation at a dataset or ROS2 boundary.
- [ ] Use one accepted event batch and at most one owning native tracker
      snapshot for all outputs associated with a processed packet.
- [ ] Keep event coordinates in pixels, timestamps in signed integer
      microseconds, and polarity in `{-1,+1}` at the
      `event_vision_utils`/native boundary.
- [ ] Preserve `eklt_bridge.EventStream` seconds/`{0,1}` compatibility only
      through explicit converters; do not make it the native EKLT data model.
- [ ] Require fixed advertised sensor geometry for each tracker lifetime.
      Dataset or stream geometry changes must be rejected or handled through an
      explicit reset/new-lifetime boundary.
- [ ] Keep every queue and retained diagnostic artifact bounded by validated
      configuration.
- [ ] Keep image construction subscriber- or persistence-gated and
      rate-limited.
- [ ] Use standard ROS2 tools such as `rqt_image_view` and PlotJuggler; do not
      add a repository-owned viewer.
- [ ] Keep real DVXplorer execution as a target-device acceptance gate when the
      hardware is unavailable locally.

## Mandatory checkpoint protocol

Every stage follows the same sequence:

- [ ] **Review:** reconcile `HEAD`, upstream, index, worktree, submodules,
      inherited-helper provenance, accepted dependencies, and the complete
      implementation affected by the stage.
- [ ] **Scope:** report findings and state the exact intended paths, behavior,
      tests, documentation, commit title, and commit description before
      staging.
- [ ] **Implementation and staging:** edit and stage only the current
      functional batch. Preserve unrelated staged and unstaged work.
- [ ] **Quality gate:** apply the file/module and public-API documentation,
      functional-block comments, and hand-formatting rules from `AGENTS.md`.
- [ ] **Exact-index validation:** inspect the complete cached diff, run
      `git diff --cached --check`, construct an isolated snapshot from the
      index, verify staged-byte parity, and run every stage-specific gate from
      that snapshot.
- [ ] **User review:** report findings by severity, all staged paths, validation
      evidence, remaining dirty groups, deferred work, and blockers; then stop.
- [ ] **Update:** apply only the user's requested changes within the current
      stage, restage the complete batch, and rerun affected and whole-index
      gates.
- [ ] **User commit:** never commit, tag, push, or open a pull request on the
      user's behalf.
- [ ] **Next:** after the user commits and says `next`, reconcile the new
      `HEAD`, index, worktree, upstream, and submodules, record the accepted
      commit, and only then start the following stage.

## Stage 0 - Accepted streaming baseline

### Scope

- [ ] Perform a read-only three-way review of the accepted upgrade commit, the
      live checkout, and this plan.
- [ ] Record the accepted Stage 14 ROS2 interface, Stage 18 data-model API,
      Stage 19 artifact schemas, and Stage 21 cumulative validation in the
      checkpoint ledger.
- [ ] Inventory the available ELOPE sequences without downloading or modifying
      dataset files.
- [ ] Verify the local ROS2 Jazzy and Python 3.12 entrypoints required by the
      later stages.
- [ ] Recheck the installed `dv-runtime`, C++ `dv-processing`, and importable
      Python `dv_processing` versions without installing or changing them.
- [ ] Record unavailable hardware and dependency gates as blockers or future
      acceptance work; do not soften invoked-feature failures into skips.
- [ ] Make no production, test, external-repository, submodule, or generated
      file changes.

### Acceptance

- [ ] The baseline report identifies exact accepted commits and public
      contracts rather than relying on prior thread summaries.
- [ ] The plan contains no path or API assumption contradicted by the accepted
      checkout.
- [ ] The index contains only this plan update and the baseline report.

### Commit checkpoint

- [ ] Stop for the user commit titled
      `Record the EKLT streaming implementation baseline`.
- [ ] Suggested description:
  - Record the accepted upgrade and single-sequence interfaces.
  - Pin the locally verified ROS2, Python, and AEDAT4 dependency gates.
  - Establish the one-stage/one-commit streaming ledger.

## Stage 1 - Multi-sequence ELOPE demo

### Selection and execution

- [ ] Extend the accepted ELOPE pipeline with `-n`/`--num-seq`, defaulting to
      five sequences selected without replacement from discovered `.npz`
      files.
- [ ] Use deterministic random selection with `--seed 0`.
- [ ] Accept explicit sequence identifiers as an override and reject duplicate,
      missing, ambiguous, or out-of-range identifiers before processing.
- [ ] Treat a single-file input as exactly one selected sequence, independently
      of `--num-seq`.
- [ ] Process sequences strictly one at a time so memory is bounded by one
      dataset and one sequence's active artifacts.
- [ ] Continue after a per-sequence failure, finish the aggregate report, and
      return failure when any selected sequence fails.
- [ ] Record discovered, selected, succeeded, failed, and skipped sequences plus
      the seed and selection policy.

### Artifact contract

- [ ] Give each sequence a stable collision-resistant output directory derived
      from its dataset-relative identity.
- [ ] Preserve the accepted per-sequence tracks, timing CSV, JSON summaries,
      labeled PNG plots, H.264 MP4 videos, and text logs.
- [ ] Add one aggregate JSON report and a compact CSV sequence table without
      changing the accepted single-sequence schemas.
- [ ] Document readers for JSON, CSV/pandas, NumPy text input, PIL/OpenCV, and
      FFmpeg/OpenCV.
- [ ] Make generated EventPacket bags ephemeral by default.
- [ ] Add `--save-input-bags` for reusable rosbag2 SQLite3 directories accepted
      by `ros2 bag info` and `ros2 bag play`.
- [ ] Reuse a saved bag only when source identity, geometry, topic, packet
      duration, event-count limit, and converter version match its provenance.

### Cleanup safety

- [ ] Before a rerun, remove only generated artifacts owned by the selected
      sequence directories.
- [ ] Preserve valid explicitly saved input bags and all unselected or
      unrelated output directories.
- [ ] Reject filesystem-root, repository-root, output-root, symlink-escape, and
      provenance-mismatched cleanup targets.
- [ ] Repair ShellCheck, pipeline-status, bounded cleanup, or aggregate-summary
      failures only in the scripts that own this stage.

### Tests and validation

- [ ] Test deterministic selection, explicit overrides, invalid counts,
      duplicate identifiers, and single-file compatibility.
- [ ] Test partial failures, aggregate exit status, saved-bag reuse,
      provenance mismatch, unrelated-output preservation, and owned cleanup.
- [ ] Test per-sequence and aggregate schemas plus bounded sequential
      execution.
- [ ] Run a bounded multi-sequence ELOPE acceptance with duration coverage,
      non-empty finite tracks, track-lifetime evidence, images, videos, and
      timing validation.
- [ ] Run focused pytest, Bash syntax, ShellCheck, structured-file parsing,
      exact-index parity, and source-package exclusion checks.

### Commit checkpoint

- [ ] Stop for the user commit titled
      `Run ELOPE demos across sampled sequences`.
- [ ] Suggested description:
  - Select ELOPE sequences deterministically and process them sequentially.
  - Preserve per-sequence artifacts and add aggregate result schemas.
  - Make input bags ephemeral by default with provenance-safe persistence.

## Stage 2 - Bounded dataset streaming and acknowledgements

### Dataset record contract

- [ ] Extend `EventDatasetAdapter` with a documented bounded record or event
      batch iterator while preserving the accepted in-memory `load()` API.
- [ ] Use typed dataclasses and enums for event batches, optional image frames,
      metadata, and end-of-stream state rather than unstructured dictionaries
      or multi-value literals.
- [ ] Require iterator outputs to preserve timestamp ordering, fixed geometry,
      source identity, and explicit end-of-stream/error semantics.
- [ ] Keep at most one source-owned record and one encoded EventPacket active
      per publisher execution step.
- [ ] Add bounded ELOPE and generic-NPZ iterator implementations without
      introducing AEDAT4 in this stage.

### Generic direct publisher

- [ ] Add a dataset-neutral ROS2 publisher that consumes the bounded iterator
      and publishes `event_camera_msgs/msg/EventPacket` directly.
- [ ] Retain the ELOPE-specific command as a delegating compatibility
      entrypoint; do not retain a second packet encoder or publisher loop.
- [ ] Publish directly by default and make rosbag2 persistence opt-in.
- [ ] Declare `packet_duration_us: 20000` and
      `packet_max_events: 20000` under a dataset-publisher section in the shared
      root `config/eklt_ros2.yaml`.
- [ ] Close a packet when either the duration or event-count limit is reached,
      preserving stable ordering for equal timestamps.
- [ ] Validate ROS parameter and command-line overrides as one consistent
      policy.

### Processing acknowledgements

- [ ] Publish `/eklt/processed_packet_seq` as
      `std_msgs/msg/UInt64`, carrying the exact sequence number of each
      successfully accepted packet; keep the topic name configurable in the
      shared root ROS2 YAML.
- [ ] Publish the acknowledgement only after native processing and essential
      track/statistic extraction succeed; optional visual-output failure must
      remain separately visible.
- [ ] Make the direct offline publisher wait for the matching acknowledgement
      before publishing the next packet.
- [ ] Reject stale, duplicate, regressing, or mismatched acknowledgements.
- [ ] Bound discovery and acknowledgement timeouts and report them as hard
      failures for an invoked direct-stream demo.
- [ ] Preserve the recorded-bag runner as a separate compatibility and
      regression path.

### Tests and validation

- [ ] Test iteration bounds, ordering, empty records, geometry mismatch,
      exceptions, and compatibility `load()` behavior.
- [ ] Test packet splitting at the duration limit, count limit, equal-time
      boundary, and end of stream.
- [ ] Test direct delivery, acknowledgement ordering, timeout, rejection,
      duplicate acknowledgement, and optional bag persistence.
- [ ] Compare direct and recorded playback against the same bounded fixture and
      require deterministic native track samples and statistics.
- [ ] Run focused pytest, ROS2 colcon/CTest, YAML validation, Bash/ShellCheck,
      documentation, exact-index parity, and `git diff --cached --check`.

### Commit checkpoint

- [ ] Stop for the user commit titled
      `Stream datasets through bounded EventPacket batches`.
- [ ] Suggested description:
  - Add bounded dataset iteration and one generic EventPacket publisher.
  - Pace offline streams with ordered native-processing acknowledgements.
  - Preserve ELOPE compatibility and make rosbag persistence optional.

## Stage 3 - Python 3.12 AEDAT4 dataset support

### Adapter and discovery

- [ ] Add an AEDAT4 adapter using `dv.io.MonoCameraRecording`.
- [ ] Accept one `.aedat4` file or recursively discover recordings below one
      directory using the Stage 1 deterministic sampling and output rules.
- [ ] Read recording-advertised event resolution, camera identity, time range,
      event batches, and optional frames.
- [ ] Reject missing or changing geometry, timestamp regression, invalid
      coordinates, unsupported frame encodings, unreadable native data, and
      incomplete metadata.
- [ ] Stream bounded records from the recording; never load a complete AEDAT4
      event stream into memory.

### Auxiliary frames

- [ ] Keep EKLT event-only: recorded frames are dataset diagnostics and never
      become implicit tracker initialization frames.
- [ ] Publish recorded frames on `/dataset/image_raw` when requested.
- [ ] Save recorded frames by default as a bounded H.264 MP4 plus a timestamp
      CSV.
- [ ] Make lossless PNG export explicit and bounded by stride and maximum-count
      policy.
- [ ] Preserve frame/event timestamp relationships and record dropped,
      unsupported, or absent frames in the sequence summary.

### Environment and preflight

- [ ] Add `environment/eklt_ros2_aedat4.yml` for Python 3.12, NumPy, rosbags,
      plotting/image dependencies, and exactly `dv-processing==2.0.3`.
- [ ] Require Python 3.12, `ROS_DISTRO=jazzy`, `rclpy`, ROS image/string and
      EventPacket packages, `event_camera_codecs`,
      `dv_processing.__version__ == "2.0.3"`, the required reader/writer APIs,
      and successful native-library loading.
- [ ] Fail clearly when an invoked AEDAT4 command lacks any dependency; do not
      fall back to an NPZ reader or report a soft skip.
- [ ] Keep the environment additive to the documented ROS installation rather
      than installing a competing ROS distribution.

### Tests and validation

- [ ] Generate a small event-and-frame AEDAT4 recording at test runtime through
      the supported writer API.
- [ ] Verify metadata, ordering, geometry, packet splitting, direct ROS2
      delivery, frame publication/export, recursive discovery, and dependency
      failures.
- [ ] Run a bounded installed-stack AEDAT4 acceptance and record peak memory,
      event/frame counts, duration coverage, tracks, timing, and output media.
- [ ] Run focused pytest, ROS2 colcon/CTest, environment/YAML parsing,
      documentation examples, exact-index parity, and package-content checks.

### Commit checkpoint

- [ ] Stop for the user commit titled
      `Add Python 3.12 AEDAT4 dataset streaming`.
- [ ] Suggested description:
  - Stream advertised AEDAT4 events through the generic dataset publisher.
  - Export optional recorded frames without changing EKLT initialization.
  - Pin and validate the Python 3.12 dv-processing environment.

## Stage 4 - Bounded online EKLT processing

### Worker ownership

- [ ] Refactor the ROS2 node into three bounded execution stages:
  - the subscription callback enqueues immutable EventPacket ownership;
  - one algorithm worker decodes packets and exclusively owns
    `CEkltTrackerOrchestrator`;
  - one output worker handles ROS publication, rendering requests, and
    diagnostic persistence.
- [ ] Preserve the Stage 14 synchronous fixtures as behavioral references; do
      not keep a second production tracker implementation.
- [ ] Keep all native tracker calls, including `reset()`, event acceptance,
      track extraction, statistics, timing, and snapshots, on the algorithm
      worker.
- [ ] Keep ROS2 messages, parameters, executors, and worker lifecycle out of
      `eklt_core`.

### Queue and reset policy

- [ ] Default to `input_queue_depth: 4` and
      `input_overflow_policy: drop_oldest_reset`.
- [ ] When input overflows, drop the oldest queued packet, mark the next
      retained packet with a reset barrier, and increment visible counters.
- [ ] Treat a detected sequence gap, regression, or duplicate according to an
      explicit validated policy; the default gap policy resets before the next
      accepted packet.
- [ ] Reject geometry changes by default because `reset()` preserves the
      configured dimensions; allow a new tracker lifetime only through an
      explicit validated re-creation policy.
- [ ] Reset EKLT/FIBAR before processing the barrier packet and include the new
      tracker generation in statistics.
- [ ] Keep essential track/statistic output ordered and bounded.
- [ ] Use a bounded diagnostic queue and latest-only visual snapshot slot so
      slow viewers cannot create unbounded memory or block algorithm progress.
- [ ] Preserve ordered acknowledgements for direct offline publishers.

### Shutdown and failures

- [ ] Stop subscriptions before queue shutdown, drain or cancel work according
      to one documented policy, join workers, flush essential files, remove
      temporary outputs, and shut down ROS2 once.
- [ ] Surface decode, tracker, output, and shutdown failures through distinct
      counters and diagnostics.
- [ ] Do not acknowledge rejected, lost, or unprocessed packets.
- [ ] Ensure a worker exception cannot leave publishers waiting indefinitely.

### Tests and validation

- [ ] Require deterministic tracking parity between the accepted synchronous
      fixture and the worker path with diagnostics disabled and enabled.
- [ ] Test overflow/drop/reset, sequence gaps, regression, duplicate packets,
      geometry changes, ordered acknowledgements, queue bounds, and tracker
      generation.
- [ ] Test orderly shutdown at idle, with queued work, during output, and after
      injected worker failures.
- [ ] Run sustained synthetic high-rate input with bounded memory and record
      queue occupancy, drops, resets, throughput, and track evidence.
- [ ] Validate recorded EventPacket and synthetic live streams locally; leave
      real DVXplorer execution as an explicit target-device gate.
- [ ] Run native Catch2 where shared APIs change, ROS2 colcon/CTest, sanitizer
      or race-focused gates where available, Doxygen, exact-index parity, and
      structured/shell checks.

### Commit checkpoint

- [ ] Stop for the user commit titled
      `Bound online EKLT ingestion and reset handling`.
- [ ] Suggested description:
  - Give one worker exclusive ownership of native EKLT processing.
  - Bound input and output state with explicit overflow/reset behavior.
  - Preserve ordered acknowledgements and deterministic offline parity.

## Stage 5 - Asynchronous image diagnostics

### Shared diagnostic payload

- [ ] Derive one compact event-activity buffer from the accepted event batch
      before transferring that batch to the native orchestrator; do not retain
      or copy the complete event batch for visualization.
- [ ] Request at most one owning native `STrackerSnapshot` when a due
      subscriber or persistence output requires it.
- [ ] Reuse the snapshot image, feature states, and warp states for every
      FIBAR, track, and patch diagnostic associated with that packet.
- [ ] Never run a second FIBAR reconstructor or reconstruct an image in the ROS2
      output worker.

### Topics and rate policy

- [ ] Publish `/eklt/event_activity` as a polarity-colored event activity
      image.
- [ ] Preserve `/eklt/init_debug_image` as the reconstructed FIBAR image.
- [ ] Preserve `/eklt/feature_tracks` as the shared native track overlay.
- [ ] Publish `/eklt/feature_patches` as a compact active-patch mosaic built
      from the same FIBAR image and native warp states.
- [ ] Preserve `/eklt/tracks` and `/eklt/stats` compatibility streams.
- [ ] Render each image only when subscribed or explicitly persisted.
- [ ] Default maximum rates to 30 Hz for event activity, reconstructed frames,
      and track overlays, and 10 Hz for patch mosaics.
- [ ] Validate all enable flags, topics, queue depths, rates, scale, tile
      geometry, stride, and maximum-count limits from the root ROS2 YAML.
- [ ] Coalesce visual work latest-only and record every dropped/coalesced visual
      request.

### Tests and validation

- [ ] Test subscriber-free avoidance of snapshots, image buffers, and rendering.
- [ ] Test event polarity/color orientation, FIBAR normalization, track overlay,
      patch geometry, tile labeling, output timestamps, rate limits, and
      latest-only coalescing.
- [ ] Require identical native tracks/statistics with all diagnostics disabled,
      individually enabled, and simultaneously enabled.
- [ ] Test slow subscribers and output failures without algorithm queue growth.
- [ ] Inspect bounded live images and saved artifacts with standard readers and
      require finite, non-empty, correctly encoded output.
- [ ] Run ROS2 colcon/CTest, focused native renderer tests, image/schema tests,
      Doxygen, YAML, exact-index parity, and `git diff --cached --check`.

### Commit checkpoint

- [ ] Stop for the user commit titled
      `Publish asynchronous EKLT image diagnostics`.
- [ ] Suggested description:
  - Reuse accepted event and native snapshot state for all image diagnostics.
  - Add event-activity and active-patch views without duplicate reconstruction.
  - Gate, rate-limit, and coalesce visual output independently of EKLT.

## Stage 6 - Runtime metrics and timing

### PlotJuggler metrics

- [ ] Publish standard scalar topics below `/eklt/metrics/` for:
  - active tracks;
  - mean and maximum active-track lifetime;
  - initialized and lost tracks;
  - input and accepted event rate;
  - FIBAR, EKLT, algorithm, output, and end-to-end time;
  - input/output queue occupancy;
  - sequence gaps and tracker resets;
  - dropped inputs and dropped/coalesced visual snapshots.
- [ ] Use stable units and standard scalar message types compatible with
      PlotJuggler.
- [ ] Default metrics publication to at most 10 Hz and skip message construction
      when no metrics subscriber exists.
- [ ] Keep monotonic lifetime counters distinct from per-generation and
      instantaneous values.

### Timing artifacts

- [ ] Preserve the accepted per-packet FIBAR/EKLT timing columns and their
      additive invariants.
- [ ] Add input queue wait and algorithm-total timing for every accepted packet.
- [ ] Record output queue wait, output execution, and end-to-end timing keyed by
      packet sequence for packets that produce diagnostic output.
- [ ] Represent absent or coalesced optional output explicitly rather than
      inventing zero-duration work.
- [ ] Keep algorithm and output timing streams bounded and join them by sequence
      only in the artifact/report layer.
- [ ] Extend the validated cumulative/stacked plots with bracketed units,
      stable descriptive labels, matching machine-readable metadata, and
      additivity checks.

### Tests and validation

- [ ] Test scalar names, types, units, rate limits, no-subscriber avoidance,
      generation resets, and counter monotonicity.
- [ ] Test queue, FIBAR, EKLT, output, and end-to-end timing order,
      non-negativity, finiteness, sequence joins, missing-output representation,
      and additive boundaries.
- [ ] Compare metrics-disabled and metrics-enabled tracking for deterministic
      parity.
- [ ] Run a bounded recorded and synthetic-online acceptance with PlotJuggler
      discovery, timing CSV/JSON parsing, labeled plots, duration coverage,
      track lifetimes, queue occupancy, drops, and peak memory.
- [ ] Run ROS2 colcon/CTest, focused plot/parser pytest, documentation, YAML,
      exact-index parity, and complete staged review.

### Commit checkpoint

- [ ] Stop for the user commit titled
      `Publish EKLT runtime metrics and timing`.
- [ ] Suggested description:
  - Expose bounded PlotJuggler-compatible tracking and queue metrics.
  - Join algorithm and asynchronous-output timing by packet sequence.
  - Preserve validated additive timing plots and machine-readable summaries.

## Final acceptance contract

- [ ] Every stage has exactly one accepted user commit recorded below.
- [ ] Frame-backed ROS1/native behavior and FIBAR event-only behavior remain
      independently selectable and tested.
- [ ] Recorded, direct-offline, synthetic-online, and available camera inputs
      use the same native tracker implementation.
- [ ] Dataset processing is bounded by one sequence and bounded record
      iteration; ROS2 processing is bounded by validated queue limits.
- [ ] Optional viewers, frames, plots, and metrics cannot delay the algorithm
      through unbounded storage.
- [ ] Duration coverage, non-empty finite tracks, track lifetimes, timestamp
      ordering, output schemas, timing invariants, and peak-memory evidence are
      required; a merely non-empty track file is insufficient.
- [ ] Complete native, Python, ROS2, documentation, structured-file, shell,
      package, installed-consumer, and exact-index gates pass for the final
      accepted tree.

## Checkpoint ledger

| Stage | Status | Validation summary | Accepted commit |
|---|---|---|---|
| 0 - Accepted streaming baseline | pending | Requires accepted template-upgrade Stage 21 | - |
| 1 - Multi-sequence ELOPE demo | pending | Requires accepted Stage 0 | - |
| 2 - Bounded dataset streaming and acknowledgements | pending | Requires accepted Stage 1 | - |
| 3 - Python 3.12 AEDAT4 dataset support | pending | Requires accepted Stage 2 | - |
| 4 - Bounded online EKLT processing | pending | Requires accepted Stage 3 | - |
| 5 - Asynchronous image diagnostics | pending | Requires accepted Stage 4 | - |
| 6 - Runtime metrics and timing | pending | Requires accepted Stage 5 | - |
