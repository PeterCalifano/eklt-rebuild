#!/usr/bin/env bash

# Run one official ELOPE sequence through reconstruction, ROS2 EKLT, and
# validated analytical/video artifact generation.
set -Eeuo pipefail

script_dir="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
repo_root="$(cd "${script_dir}/.." && pwd)"

input=""
dataset_dir="${repo_root}/data/elope"
output_dir="${repo_root}/outputs/official_elope_event_only"
width=""
height=""
recon_dt_ms="200"
track_dt_ms="20"
playback_rate="10"
max_packets="0"
patch_panel_size="800"
patch_columns="2"
patch_max_candidates="8"
max_patch_quality_samples="50000"
track_video_fps="100"
track_video_scale="4"
track_hold_ms="100"
track_dot_radius="5"
ros_setup="${ROS_SETUP:-/opt/ros/jazzy/setup.bash}"
overlay_setup="${EKLT_ROS2_SETUP:-}"
python_bin="${PYTHON:-python3.12}"

# Define the complete single-sequence CLI and failure contract.
usage() {
    cat <<'USAGE'
Usage: scripts/run_official_elope_event_only_pipeline_demo.sh [options]

Input:
  --input <file>                 One official ELOPE NPZ sequence.
  --dataset-dir <directory>      Download root used when --input is absent.

Output:
  --output-dir <directory>       Owned per-sequence artifact root.

Geometry and packet policy:
  --width <pixels>               Optional sensor-width override.
  --height <pixels>              Optional sensor-height override.
  --recon-dt-ms <milliseconds>   FIBAR diagnostic interval.
  --track-dt-ms <milliseconds>   EventPacket duration limit.
  --playback-rate <scale>        ROS2 bag playback rate.
  --max-packets <count>          Zero for all packets.

Diagnostic policy:
  --patch-panel-size <pixels>    Event-panel height in [128, 2048].
  --patch-columns <count>        Patch-mosaic columns.
  --patch-max-candidates <count> Candidate slots in [1, 32].
  --max-patch-quality-samples <count>
                                 Maximum retained patch-quality samples.
  --track-video-fps <rate>       Track-overlay frame rate.
  --track-video-scale <factor>   Integer image scale in [1, 8].
  --track-hold-ms <milliseconds> Recent-observation display duration.
  --track-dot-radius <pixels>    Track-dot radius in [1, 64].

ROS2:
  --ros-setup <file>             Base ROS2 setup file.
  --overlay-setup <file>         Built EKLT overlay setup file.
  -h, --help                     Show this help.
USAGE
}

die() {
    echo "run_official_elope_event_only_pipeline_demo.sh: $*" >&2
    exit 2
}

# Parse policy before downloading data or creating component output
# directories.
while (($# > 0)); do
    case "$1" in
        --input)
            (($# >= 2)) || die "--input requires a value."
            input="$2"
            shift 2
            ;;
        --dataset-dir)
            (($# >= 2)) || die "--dataset-dir requires a value."
            dataset_dir="$2"
            shift 2
            ;;
        --output-dir)
            (($# >= 2)) || die "--output-dir requires a value."
            output_dir="$2"
            shift 2
            ;;
        --width)
            (($# >= 2)) || die "--width requires a value."
            width="$2"
            shift 2
            ;;
        --height)
            (($# >= 2)) || die "--height requires a value."
            height="$2"
            shift 2
            ;;
        --recon-dt-ms)
            (($# >= 2)) || die "--recon-dt-ms requires a value."
            recon_dt_ms="$2"
            shift 2
            ;;
        --track-dt-ms)
            (($# >= 2)) || die "--track-dt-ms requires a value."
            track_dt_ms="$2"
            shift 2
            ;;
        --playback-rate)
            (($# >= 2)) || die "$1 requires a value."
            playback_rate="$2"
            shift 2
            ;;
        --max-packets)
            (($# >= 2)) || die "--max-packets requires a value."
            max_packets="$2"
            shift 2
            ;;
        --patch-panel-size)
            (($# >= 2)) || die "--patch-panel-size requires a value."
            patch_panel_size="$2"
            shift 2
            ;;
        --patch-columns)
            (($# >= 2)) || die "--patch-columns requires a value."
            patch_columns="$2"
            shift 2
            ;;
        --patch-max-candidates)
            (($# >= 2)) || die "--patch-max-candidates requires a value."
            patch_max_candidates="$2"
            shift 2
            ;;
        --max-patch-quality-samples)
            (($# >= 2)) || die "$1 requires a value."
            max_patch_quality_samples="$2"
            shift 2
            ;;
        --track-video-fps)
            (($# >= 2)) || die "--track-video-fps requires a value."
            track_video_fps="$2"
            shift 2
            ;;
        --track-video-scale)
            (($# >= 2)) || die "--track-video-scale requires a value."
            track_video_scale="$2"
            shift 2
            ;;
        --track-hold-ms)
            (($# >= 2)) || die "--track-hold-ms requires a value."
            track_hold_ms="$2"
            shift 2
            ;;
        --track-dot-radius)
            (($# >= 2)) || die "--track-dot-radius requires a value."
            track_dot_radius="$2"
            shift 2
            ;;
        --ros-setup)
            (($# >= 2)) || die "--ros-setup requires a value."
            ros_setup="$2"
            shift 2
            ;;
        --overlay-setup)
            (($# >= 2)) || die "--overlay-setup requires a value."
            overlay_setup="$2"
            shift 2
            ;;
        -h|--help)
            usage
            exit 0
            ;;
        *)
            die "unknown option: $1"
            ;;
    esac
done

# Resolve the interpreter and indivisible geometry override before selecting an
# input source.
command -v "${python_bin}" >/dev/null 2>&1 ||
    die "Python interpreter not found: ${python_bin}"
if [[ -n "${width}" || -n "${height}" ]]; then
    [[ -n "${width}" && -n "${height}" ]] ||
        die "--width and --height must be provided together."
fi

# When no sequence is supplied, request the downloader's deterministic first
# validated NPZ and consume only its machine-readable path record.
if [[ -z "${input}" ]]; then
    download_output="$(
        PYTHON="${python_bin}" \
            "${script_dir}/download_elope_dataset.sh" \
            --output-dir "${dataset_dir}" \
            --first-only
    )"
    printf '%s\n' "${download_output}"
    input="$(
        sed -n 's/^validated_first_sequence=//p' <<<"${download_output}" |
            tail -n 1
    )"
fi
[[ -n "${input}" && -f "${input}" ]] ||
    die "official ELOPE sequence not found."
input="$(realpath "${input}")"

# Reject roots that could make component cleanup broad, then establish the
# fixed reconstruction/tracking directory boundary.
[[ ! -L "${output_dir}" ]] ||
    die "output directory must not be a symlink: ${output_dir}"
output_dir="$(realpath -m "${output_dir}")"
[[ "${output_dir}" != "/" && "${output_dir}" != "${repo_root}" ]] ||
    die "output directory must not be the filesystem or repository root."
case "${repo_root}" in
    "${output_dir}"/*)
        die "output directory must not be a repository ancestor."
        ;;
esac
mkdir -p "${output_dir}"

reconstruction_dir="${output_dir}/reconstruction"
tracking_dir="${output_dir}/tracking"
[[ ! -L "${reconstruction_dir}" && ! -L "${tracking_dir}" ]] ||
    die "component output directories must not be symlinks."
mkdir -p "${tracking_dir}"

# Remove only Stage 19 analysis/video artifacts. Preserve the converted input
# bag, Stage 14 timing artifacts, logs, and every unrelated tracking entry.
PYTHONDONTWRITEBYTECODE=1 "${python_bin}" - "${tracking_dir}" <<'PY'
from __future__ import annotations

import shutil
import sys
from pathlib import Path


tracking_dir = Path(sys.argv[1])
plots_dir = tracking_dir / "plots"
if plots_dir.is_symlink():
    raise SystemExit(
        f"refusing symlinked plot directory: {plots_dir}"
    )
if plots_dir.exists() and not plots_dir.is_dir():
    raise SystemExit(
        f"plot path is not a directory: {plots_dir}"
    )
owned_paths = (
    Path("eklt_tracks.mp4"),
    Path("eklt_tracks_frames"),
    Path("track_video_summary.json"),
    Path("plots/active_tracks.png"),
    Path("plots/track_lifetimes.png"),
    Path("plots/reinit_timeline.png"),
    Path("plots/track_xy.png"),
    Path("plots/event_rate.png"),
    Path("plots/gt_error.png"),
)
resolved_paths: list[Path] = []
for relative_path in owned_paths:
    path = tracking_dir / relative_path
    if path.is_symlink():
        raise SystemExit(
            f"refusing symlinked owned artifact: {path}"
        )
    if path.exists() and not (path.is_dir() or path.is_file()):
        raise SystemExit(
            f"owned artifact has unsupported type: {path}"
        )
    resolved_paths.append(path)

# Validate the complete cleanup set before removing prior accepted artifacts.
for path in resolved_paths:
    if path.is_dir():
        shutil.rmtree(path)
    elif path.is_file():
        path.unlink()
PY

geometry_arguments=()
if [[ -n "${width}" ]]; then
    geometry_arguments+=(--width "${width}" --height "${height}")
fi

# Run reconstruction and tracking independently so a missing optional runtime
# still produces one complete blocked/failed pipeline summary.
reconstruction_status=0
# Reconstruction owns its diagnostic artifacts and may report the explicit
# native-wrapper blocker without preventing later summary publication.
PYTHON="${python_bin}" \
    "${script_dir}/run_elope_reconstruction_example_demo.sh" \
    --input "${input}" \
    --output-dir "${reconstruction_dir}" \
    --dt-ms "${recon_dt_ms}" \
    --patch-panel-size "${patch_panel_size}" \
    --patch-columns "${patch_columns}" \
    --patch-max-candidates "${patch_max_candidates}" \
    --max-patch-quality-samples "${max_patch_quality_samples}" \
    "${geometry_arguments[@]}" ||
    reconstruction_status="$?"

tracking_arguments=(
    --input "${input}"
    --output-dir "${tracking_dir}"
    --dt-ms "${track_dt_ms}"
    --playback-rate "${playback_rate}"
    --max-packets "${max_packets}"
)
if [[ -n "${ros_setup}" ]]; then
    tracking_arguments+=(--ros-setup "${ros_setup}")
fi
if [[ -n "${overlay_setup}" ]]; then
    tracking_arguments+=(--overlay-setup "${overlay_setup}")
fi
tracking_arguments+=("${geometry_arguments[@]}")

tracking_status=0
# Tracking delegates to the accepted synchronous ROS2 EventPacket path and
# retains its native conversion, timing, log, and track artifacts.
PYTHON="${python_bin}" \
    "${script_dir}/run_ros2_elope_event_only_example_demo.sh" \
    "${tracking_arguments[@]}" ||
    tracking_status="$?"

reconstruction_evaluation_status=3
if [[ "${reconstruction_status}" -eq 0 ]]; then
    # Validate reconstruction media and schema only after its producer reports
    # success; status 3 records a deliberately unattempted evaluator.
    reconstruction_evaluation_status=0
    PYTHONDONTWRITEBYTECODE=1 \
    PYTHONPATH="${repo_root}/python${PYTHONPATH:+:${PYTHONPATH}}" \
        "${python_bin}" "${script_dir}/evaluate_outputs.py" \
        --no-require-tracks \
        "${reconstruction_dir}" ||
        reconstruction_evaluation_status="$?"
fi

analysis_status=3
tracking_evaluation_status=3
track_video_status=3
track_video_evaluation_status=3
if [[ "${tracking_status}" -eq 0 ]]; then
    # Enrich a successful native tracking summary with stable analytical plots
    # before accepting the component.
    analysis_status=0
    analysis_arguments=(
        --tracks "${tracking_dir}/tracks.txt"
        --output-dir "${tracking_dir}"
        --run-name "official_elope_event_only_tracking"
        --input "${input}"
        --event-npz "${input}"
        --base-summary "${tracking_dir}/summary.json"
        --summary-output "${tracking_dir}/summary.json"
    )
    if [[ -n "${width}" ]]; then
        analysis_arguments+=(
            --event-width "${width}"
            --event-height "${height}"
        )
    fi

    PYTHONDONTWRITEBYTECODE=1 \
    PYTHONPATH="${repo_root}/python${PYTHONPATH:+:${PYTHONPATH}}" \
        "${python_bin}" "${script_dir}/summarize_eklt_tracks.py" \
        "${analysis_arguments[@]}" ||
        analysis_status="$?"

    if [[ "${analysis_status}" -eq 0 ]]; then
        tracking_evaluation_status=0
        PYTHONDONTWRITEBYTECODE=1 \
        PYTHONPATH="${repo_root}/python${PYTHONPATH:+:${PYTHONPATH}}" \
            "${python_bin}" "${script_dir}/evaluate_outputs.py" \
            "${tracking_dir}" ||
            tracking_evaluation_status="$?"
    fi

    if ((
        analysis_status == 0 &&
        tracking_evaluation_status == 0
    )); then
        # Encode track video only from an already accepted track artifact, then
        # independently validate its flattened display and media contract.
        track_video_status=0
        track_video_arguments=(
            --input "${input}"
            --tracks "${tracking_dir}/tracks.txt"
            --output "${tracking_dir}/eklt_tracks.mp4"
            --summary-output "${tracking_dir}/track_video_summary.json"
            --fps "${track_video_fps}"
            --scale "${track_video_scale}"
            --track-hold-ms "${track_hold_ms}"
            --dot-radius "${track_dot_radius}"
        )
        if [[ -n "${width}" ]]; then
            track_video_arguments+=(
                --width "${width}"
                --height "${height}"
            )
        fi

        PYTHONDONTWRITEBYTECODE=1 \
        PYTHONPATH="${repo_root}/python${PYTHONPATH:+:${PYTHONPATH}}" \
            "${python_bin}" \
            -m event_vision_utils.examples.render_elope_tracks \
            "${track_video_arguments[@]}" ||
            track_video_status="$?"

        if [[ "${track_video_status}" -eq 0 ]]; then
            track_video_evaluation_status=0
            PYTHONDONTWRITEBYTECODE=1 \
            PYTHONPATH="${repo_root}/python${PYTHONPATH:+:${PYTHONPATH}}" \
                "${python_bin}" "${script_dir}/evaluate_outputs.py" \
                --track-video-summary \
                "${tracking_dir}/track_video_summary.json" ||
                track_video_evaluation_status="$?"
        fi
    fi
fi

# Publish one stable root summary containing the component schemas and exact
# status codes. Paths remain relative to the per-sequence output root.
PYTHONDONTWRITEBYTECODE=1 "${python_bin}" - \
    "${output_dir}" \
    "${input}" \
    "${reconstruction_status}" \
    "${reconstruction_evaluation_status}" \
    "${tracking_status}" \
    "${analysis_status}" \
    "${tracking_evaluation_status}" \
    "${track_video_status}" \
    "${track_video_evaluation_status}" <<'PY'
from __future__ import annotations

import json
import os
import sys
from pathlib import Path
from typing import Any


output_dir = Path(sys.argv[1])
input_path = sys.argv[2]
status_codes = {
    "reconstruction": int(sys.argv[3]),
    "reconstruction_evaluation": int(sys.argv[4]),
    "tracking": int(sys.argv[5]),
    "tracking_analysis": int(sys.argv[6]),
    "tracking_evaluation": int(sys.argv[7]),
    "track_video": int(sys.argv[8]),
    "track_video_evaluation": int(sys.argv[9]),
}


def read_component(relative_path: str) -> dict[str, Any]:
    """Read one component summary or describe its absence."""
    # Keep component failures representable in the root summary instead of
    # aborting publication at the first missing or malformed child.
    path = output_dir / relative_path
    if path.is_symlink():
        return {
            "status": "invalid",
            "summary_path": relative_path,
            "error": "component summary must not be a symlink",
        }
    if not path.is_file():
        return {
            "status": "missing",
            "summary_path": relative_path,
        }
    try:
        value = json.loads(
            path.read_text(encoding="utf-8", errors="strict")
        )
    except (OSError, UnicodeError, json.JSONDecodeError) as exc:
        return {
            "status": "invalid",
            "summary_path": relative_path,
            "error": str(exc),
        }
    if not isinstance(value, dict):
        return {
            "status": "invalid",
            "summary_path": relative_path,
            "error": "component summary must contain one object",
        }
    return {
        "status": value.get("status", "invalid"),
        "summary_path": relative_path,
        "summary": value,
    }


# Accept the pipeline only when every process status and every independently
# parsed component summary agrees on success.
components = {
    "reconstruction": read_component("reconstruction/summary.json"),
    "tracking": read_component("tracking/summary.json"),
    "track_video": read_component(
        "tracking/track_video_summary.json"
    ),
}
passed = (
    all(status == 0 for status in status_codes.values()) and
    all(
        component["status"] == "passed"
        for component in components.values()
    )
)
blocked = (
    not passed and
    (
        status_codes["reconstruction"] == 2 or
        status_codes["tracking"] == 2
    )
)
summary = {
    "schema_version": 1,
    "artifact_type": "elope_single_sequence_pipeline",
    "run_name": "official_elope_event_only_pipeline",
    "status": (
        "passed"
        if passed
        else "blocked"
        if blocked
        else "failed"
    ),
    "input": input_path,
    "status_codes": status_codes,
    "components": components,
    "artifacts": {
        "reconstruction_summary": "reconstruction/summary.json",
        "tracking_summary": "tracking/summary.json",
        "track_video_summary": "tracking/track_video_summary.json",
    },
}

# Publish the root result atomically so interrupted orchestration cannot leave
# a partial status document for later automation.
summary_path = output_dir / "summary.json"
if summary_path.is_symlink():
    raise ValueError(
        f"refusing symlinked pipeline summary: {summary_path}"
    )
temporary_path = output_dir / ".summary.tmp.json"
if temporary_path.is_symlink():
    raise ValueError(
        f"refusing symlinked temporary summary: {temporary_path}"
    )
try:
    temporary_path.write_text(
        json.dumps(summary, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    os.replace(temporary_path, summary_path)
finally:
    temporary_path.unlink(missing_ok=True)
print(summary_path)
PY

# Map the stable summary vocabulary back to shell statuses used by callers and
# CI: success, environment blocker, or functional failure.
pipeline_status="$(
    PYTHONDONTWRITEBYTECODE=1 "${python_bin}" -c \
        'import json, sys; from pathlib import Path; print(json.loads(Path(sys.argv[1]).read_text(encoding="utf-8"))["status"])' \
        "${output_dir}/summary.json"
)"
case "${pipeline_status}" in
    passed)
        exit 0
        ;;
    blocked)
        exit 2
        ;;
    *)
        exit 1
        ;;
esac
