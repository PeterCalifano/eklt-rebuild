#!/usr/bin/env bash

# Convert a legacy DVS bag when needed and run it through native ROS2 EKLT.
set -Eeuo pipefail

script_dir="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
repo_root="$(cd "${script_dir}/.." && pwd)"

ros_setup="${ROS_SETUP:-}"
overlay_setup="${EKLT_ROS2_SETUP:-}"
default_ros_setup="/opt/ros/jazzy/setup.bash"
legacy_bag=""
ros2_bag=""
input_topic="/dvs/events"
events_topic="/events"
output_dir="${repo_root}/outputs/ros2_rosbag_event_only"
python_bin="${PYTHON:-python3}"
playback_rate="1.0"
post_playback_wait_s="20"
min_duration_coverage="0.8"
max_messages=0
visualize=false
save_reconstructed_frames=false
saved_frame_stride=1
max_saved_frames=0
png_compression=3

usage() {
    cat <<'USAGE'
Usage: scripts/run_ros2_rosbag_event_only_demo.sh [options]

Input (choose exactly one):
  --legacy-bag <file>       ROS1 bag containing dvs_msgs/EventArray.
  --ros2-bag <directory>    Existing ROS2 bag containing EventPacket.

Options:
  --input-topic <topic>     Legacy EventArray topic. Defaults to /dvs/events.
  --events-topic <topic>    ROS2 EventPacket topic. Defaults to /events.
  --output-dir <directory>  Converted bag, logs, tracks, timing plot, and summary.
  --playback-rate <scale>   rosbag2 playback rate. Defaults to 1.0.
  --post-playback-wait-s <s>
                             Time for the bounded subscriber queue to drain.
                             Defaults to 20 seconds.
  --min-duration-coverage <ratio>
                             Required last-track coverage in [0, 1].
                             Defaults to 0.8; zero disables the gate.
  --max-messages <count>    Convert only the first count legacy messages.
  --visualize               View /eklt/feature_tracks with rqt_image_view.
  --save-reconstructed-frames
                             Save normalized FIBAR frames as PNG files.
  --saved-frame-stride <n>  Save every nth reconstructed frame. Defaults to 1.
  --max-saved-frames <n>    Stop saving after n frames; zero is unlimited.
  --png-compression <0-9>   OpenCV PNG compression. Defaults to 3.
  --ros-setup <file>        Base ROS2 setup file to source explicitly.
  --overlay-setup <file>    EKLT overlay setup file to source explicitly.
  -h, --help                Show this help.

The legacy conversion requires Python 3.12 with rosbags and NumPy. Matplotlib is
required for the processing-time plot. The output bag is created atomically and
reused on later runs. Playback keeps a two-message read-ahead queue so the
example does not scale RAM use with bag size. Visualization and PNG export are
disabled unless explicitly requested.
USAGE
}

die() {
    echo "run_ros2_rosbag_event_only_demo.sh: $*" >&2
    exit 2
}

while (($# > 0)); do
    case "$1" in
        --legacy-bag)
            (($# >= 2)) || die "--legacy-bag requires a value."
            legacy_bag="$2"
            shift 2
            ;;
        --ros2-bag)
            (($# >= 2)) || die "--ros2-bag requires a value."
            ros2_bag="$2"
            shift 2
            ;;
        --input-topic)
            (($# >= 2)) || die "--input-topic requires a value."
            input_topic="$2"
            shift 2
            ;;
        --events-topic)
            (($# >= 2)) || die "--events-topic requires a value."
            events_topic="$2"
            shift 2
            ;;
        --output-dir)
            (($# >= 2)) || die "--output-dir requires a value."
            output_dir="$2"
            shift 2
            ;;
        --playback-rate)
            (($# >= 2)) || die "--playback-rate requires a value."
            playback_rate="$2"
            shift 2
            ;;
        --post-playback-wait-s)
            (($# >= 2)) || die "--post-playback-wait-s requires a value."
            post_playback_wait_s="$2"
            shift 2
            ;;
        --min-duration-coverage)
            (($# >= 2)) || die "--min-duration-coverage requires a value."
            min_duration_coverage="$2"
            shift 2
            ;;
        --max-messages)
            (($# >= 2)) || die "--max-messages requires a value."
            max_messages="$2"
            shift 2
            ;;
        --visualize)
            visualize=true
            shift
            ;;
        --save-reconstructed-frames)
            save_reconstructed_frames=true
            shift
            ;;
        --saved-frame-stride)
            (($# >= 2)) || die "--saved-frame-stride requires a value."
            saved_frame_stride="$2"
            shift 2
            ;;
        --max-saved-frames)
            (($# >= 2)) || die "--max-saved-frames requires a value."
            max_saved_frames="$2"
            shift 2
            ;;
        --png-compression)
            (($# >= 2)) || die "--png-compression requires a value."
            png_compression="$2"
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

if [[ -n "${legacy_bag}" && -n "${ros2_bag}" ]]; then
    die "--legacy-bag and --ros2-bag are mutually exclusive."
fi
if [[ -z "${legacy_bag}" && -z "${ros2_bag}" ]]; then
    die "provide --legacy-bag or --ros2-bag."
fi
[[ "${events_topic}" == /* ]] || die "--events-topic must be absolute."
[[ "${input_topic}" == /* ]] || die "--input-topic must be absolute."
[[ "${playback_rate}" =~ ^[0-9]+([.][0-9]+)?$ ]] ||
    die "--playback-rate must be a positive number."
[[ "${playback_rate}" != "0" && "${playback_rate}" != "0.0" ]] ||
    die "--playback-rate must be positive."
[[ "${post_playback_wait_s}" =~ ^[0-9]+([.][0-9]+)?$ ]] ||
    die "--post-playback-wait-s must be a nonnegative number."
[[ "${min_duration_coverage}" =~ ^(0([.][0-9]+)?|1([.]0+)?)$ ]] ||
    die "--min-duration-coverage must be between zero and one."
[[ "${max_messages}" =~ ^[0-9]+$ ]] ||
    die "--max-messages must be a nonnegative integer."
[[ "${saved_frame_stride}" =~ ^[1-9][0-9]*$ ]] ||
    die "--saved-frame-stride must be a positive integer."
[[ "${max_saved_frames}" =~ ^[0-9]+$ ]] ||
    die "--max-saved-frames must be a nonnegative integer."
[[ "${png_compression}" =~ ^[0-9]$ ]] ||
    die "--png-compression must be an integer between zero and nine."
[[ -z "${ros_setup}" || -f "${ros_setup}" ]] ||
    die "ROS2 setup not found: ${ros_setup}"
[[ -z "${overlay_setup}" || -f "${overlay_setup}" ]] ||
    die "EKLT overlay setup not found: ${overlay_setup}"
command -v "${python_bin}" >/dev/null 2>&1 ||
    die "Python interpreter not found: ${python_bin}"
"${python_bin}" -c "import matplotlib" >/dev/null 2>&1 ||
    die "processing-time plotting requires Matplotlib in ${python_bin}."

output_dir="$(realpath -m "${output_dir}")"
[[ "${output_dir}" != "/" ]] || die "output directory must not be the filesystem root."
mkdir -p "${output_dir}"

conversion_summary="${output_dir}/conversion_summary.json"
if [[ -n "${legacy_bag}" ]]; then
    [[ -f "${legacy_bag}" ]] || die "legacy bag not found: ${legacy_bag}"
    legacy_bag="$(realpath "${legacy_bag}")"

    ros2_bag="${output_dir}/eventpacket_bag"
    if [[ ! -d "${ros2_bag}" ]]; then
        "${python_bin}" -c "import numpy, rosbags" >/dev/null 2>&1 ||
            die "legacy conversion requires Python packages numpy and rosbags."
        PYTHONDONTWRITEBYTECODE=1 "${python_bin}" \
            "${script_dir}/convert_ros1_dvs_bag_to_eventpacket.py" \
            --input "${legacy_bag}" \
            --output "${ros2_bag}" \
            --input-topic "${input_topic}" \
            --output-topic "${events_topic}" \
            --summary-output "${conversion_summary}" \
            --max-messages "${max_messages}"
    else
        [[ -f "${ros2_bag}/metadata.yaml" ]] ||
            die "existing converted-bag directory is incomplete: ${ros2_bag}"
        [[ -f "${conversion_summary}" ]] ||
            die "existing converted bag has no provenance summary: ${conversion_summary}"
        PYTHONDONTWRITEBYTECODE=1 "${python_bin}" - \
            "${conversion_summary}" "${legacy_bag}" "${input_topic}" \
            "${events_topic}" "${max_messages}" <<'PY'
from __future__ import annotations

import json
import sys
from pathlib import Path

summary = json.loads(Path(sys.argv[1]).read_text(encoding="utf-8"))
expected = {
    "input": sys.argv[2],
    "input_topic": sys.argv[3],
    "output_topic": sys.argv[4],
    "message_limit": int(sys.argv[5]),
}
mismatches = {
    key: (summary.get(key), value)
    for key, value in expected.items()
    if summary.get(key) != value
}
if mismatches:
    print(f"converted-bag provenance mismatch: {mismatches}", file=sys.stderr)
    raise SystemExit(1)
PY
        echo "Reusing converted ROS2 bag: ${ros2_bag}"
    fi
else
    [[ -d "${ros2_bag}" && -f "${ros2_bag}/metadata.yaml" ]] ||
        die "ROS2 bag directory is incomplete: ${ros2_bag}"
fi

set +u
if [[ -n "${ros_setup}" ]]; then
    # shellcheck source=/dev/null
    source "${ros_setup}"
elif ! command -v ros2 >/dev/null 2>&1; then
    [[ -f "${default_ros_setup}" ]] ||
        die "ROS2 is not sourced and the default setup is unavailable: ${default_ros_setup}"
    # shellcheck source=/dev/null
    source "${default_ros_setup}"
fi
if [[ -n "${overlay_setup}" ]]; then
    # shellcheck source=/dev/null
    source "${overlay_setup}"
fi
set -u

command -v ros2 >/dev/null 2>&1 || die "ros2 is unavailable after sourcing setup files."
viewer_executable=""
if [[ "${visualize}" == true ]]; then
    viewer_prefix="$(ros2 pkg prefix rqt_image_view 2>/dev/null)" ||
        die "--visualize requires the ROS2 rqt_image_view package."
    viewer_executable="${viewer_prefix}/lib/rqt_image_view/rqt_image_view"
    [[ -x "${viewer_executable}" ]] ||
        die "installed rqt_image_view executable not found: ${viewer_executable}"
fi
package_prefix="$(ros2 pkg prefix eklt_rebuild 2>/dev/null)" ||
    die "eklt_rebuild is not installed in the current ROS2 environment."
node_executable="${package_prefix}/lib/eklt_rebuild/event_only_eklt_node"
params_file="${package_prefix}/share/eklt_rebuild/config/eklt_ros2.yaml"
[[ -x "${node_executable}" ]] ||
    die "installed EKLT node is not executable: ${node_executable}"
[[ -f "${params_file}" ]] ||
    die "installed EKLT parameter file not found: ${params_file}"

bag_information="$(ros2 bag info "${ros2_bag}")"
expected_topic_line="Topic: ${events_topic} | Type: event_camera_msgs/msg/EventPacket |"
[[ "${bag_information}" == *"${expected_topic_line}"* ]] ||
    die "bag does not contain ${events_topic} as event_camera_msgs/msg/EventPacket."

tracks_file="${output_dir}/tracks.txt"
processing_timing_file="${output_dir}/processing_timing.csv"
processing_timing_plot="${output_dir}/plots/processing_time_cumulative.png"
processing_timing_summary="${output_dir}/processing_timing_summary.json"
node_log="${output_dir}/event_only_eklt_node.log"
player_log="${output_dir}/ros2_bag_play.log"
bag_info_file="${output_dir}/ros2_bag_info.txt"
run_summary="${output_dir}/summary.json"
viewer_log="${output_dir}/rqt_image_view.log"
reconstructed_frames_dir=""
rm -f "${tracks_file}" "${processing_timing_file}" \
    "${processing_timing_plot}" "${processing_timing_summary}" \
    "${node_log}" "${player_log}" "${bag_info_file}" \
    "${run_summary}" "${viewer_log}"
printf '%s\n' "${bag_information}" >"${bag_info_file}"

if [[ "${save_reconstructed_frames}" == true ]]; then
    reconstructed_frames_dir="${output_dir}/reconstructed_frames"
    mkdir -p "${reconstructed_frames_dir}"

    # Remove only files owned by the deterministic frame-export naming scheme
    # so a repeated run cannot count stale or interrupted output.
    while IFS= read -r -d '' frame_path; do
        rm -f -- "${frame_path}"
    done < <(
        find "${reconstructed_frames_dir}" -maxdepth 1 -type f \
            \( -name 'frame_*_t_*.png' -o -name 'frame_*_t_*.tmp.png' \) \
            -print0
    )
fi

node_pid=""
player_pid=""
viewer_pid=""
child_is_running() {
    local child_pid="$1"
    local process_status
    kill -0 "${child_pid}" 2>/dev/null || return 1
    process_status="$(ps -o stat= -p "${child_pid}" 2>/dev/null)" || return 1
    [[ "${process_status}" != Z* ]]
}

stop_child() {
    local child_pid="$1"
    local wait_step
    [[ -n "${child_pid}" ]] || return 0
    child_is_running "${child_pid}" || {
        wait "${child_pid}" 2>/dev/null || true
        return 0
    }

    kill -INT "${child_pid}" 2>/dev/null || true
    for ((wait_step = 0; wait_step < 20; ++wait_step)); do
        child_is_running "${child_pid}" || break
        sleep 0.25
    done
    if child_is_running "${child_pid}"; then
        kill -TERM "${child_pid}" 2>/dev/null || true
        for ((wait_step = 0; wait_step < 20; ++wait_step)); do
            child_is_running "${child_pid}" || break
            sleep 0.25
        done
    fi
    if child_is_running "${child_pid}"; then
        kill -KILL "${child_pid}" 2>/dev/null || true
    fi
    wait "${child_pid}" 2>/dev/null || true
}

cleanup() {
    stop_child "${player_pid}"
    stop_child "${viewer_pid}"
    stop_child "${node_pid}"
}
trap cleanup EXIT INT TERM

# Start the installed executable directly so the tracked PID owns the ROS2
# process and receives the demo's bounded shutdown sequence.
node_arguments=(
    --ros-args
    --params-file "${params_file}"
    -p events_topic:="${events_topic}"
    -p tracks_file_txt:="${tracks_file}"
    -p processing_timing_file_csv:="${processing_timing_file}"
)
if [[ "${save_reconstructed_frames}" == true ]]; then
    node_arguments+=(
        -p reconstructed_frames_directory:="${reconstructed_frames_dir}"
        -p reconstructed_frames_stride:="${saved_frame_stride}"
        -p reconstructed_frames_max_count:="${max_saved_frames}"
        -p reconstructed_frames_png_compression:="${png_compression}"
    )
fi

"${node_executable}" "${node_arguments[@]}" \
    >"${node_log}" 2>&1 &
node_pid="$!"

sleep 2
child_is_running "${node_pid}" ||
    die "EKLT node exited before playback; inspect ${node_log}."

if [[ "${visualize}" == true ]]; then
    "${viewer_executable}" /eklt/feature_tracks >"${viewer_log}" 2>&1 &
    viewer_pid="$!"
    sleep 2
    child_is_running "${viewer_pid}" ||
        die "rqt_image_view exited before playback; inspect ${viewer_log}."
fi

# Keep rosbag2 buffering independent of the 1.7-GiB reference bag size.
ros2 bag play "${ros2_bag}" \
    --read-ahead-queue-size 2 \
    --rate "${playback_rate}" \
    --delay 2 \
    --topics "${events_topic}" \
    --disable-keyboard-controls \
    >"${player_log}" 2>&1 &
player_pid="$!"
wait "${player_pid}"
player_pid=""

sleep "${post_playback_wait_s}"
stop_child "${viewer_pid}"
viewer_pid=""
stop_child "${node_pid}"
node_pid=""
trap - EXIT INT TERM

[[ -s "${tracks_file}" ]] ||
    die "no EKLT track rows were produced; inspect ${node_log}."
[[ -s "${processing_timing_file}" ]] ||
    die "no processing timing rows were produced; inspect ${node_log}."

PYTHONDONTWRITEBYTECODE=1 "${python_bin}" \
    "${script_dir}/plot_eklt_processing_timing.py" \
    --input "${processing_timing_file}" \
    --output "${processing_timing_plot}" \
    --summary-output "${processing_timing_summary}"

PYTHONDONTWRITEBYTECODE=1 "${python_bin}" - \
    "${ros2_bag}" "${events_topic}" "${tracks_file}" "${bag_info_file}" \
    "${run_summary}" "${min_duration_coverage}" \
    "${reconstructed_frames_dir}" "${save_reconstructed_frames}" \
    "${processing_timing_summary}" <<'PY'
from __future__ import annotations

import json
import math
import re
import struct
import sys
from pathlib import Path

track_path = Path(sys.argv[3])
track_rows = 0
track_ids: set[int] = set()
last_time_by_track: dict[int, float] = {}
first_track_time_s: float | None = None
last_track_time_s: float | None = None
with track_path.open(encoding="utf-8") as track_stream:
    for line_number, line in enumerate(track_stream, start=1):
        fields = line.split()
        if len(fields) != 4:
            raise ValueError(f"invalid track row {line_number}: expected four fields")
        track_id = int(fields[0])
        track_time_s = float(fields[1])
        x_coordinate = float(fields[2])
        y_coordinate = float(fields[3])
        if not all(
            math.isfinite(value)
            for value in (track_time_s, x_coordinate, y_coordinate)
        ):
            raise ValueError(f"invalid track row {line_number}: non-finite value")
        previous_track_time = last_time_by_track.get(track_id)
        if previous_track_time is not None and track_time_s < previous_track_time:
            raise ValueError(
                f"invalid track row {line_number}: per-track timestamp regression"
            )
        last_time_by_track[track_id] = track_time_s
        if first_track_time_s is None or track_time_s < first_track_time_s:
            first_track_time_s = track_time_s
        if last_track_time_s is None or track_time_s > last_track_time_s:
            last_track_time_s = track_time_s
        track_ids.add(track_id)
        track_rows += 1
track_count = len(track_ids)
if track_rows == 0 or first_track_time_s is None or last_track_time_s is None:
    raise ValueError("track file is empty")

bag_information = Path(sys.argv[4]).read_text(encoding="utf-8")
duration_match = re.search(r"^Duration:\s+([0-9.]+)s$", bag_information, re.MULTILINE)
start_match = re.search(r"^Start:.*\(([0-9.]+)\)$", bag_information, re.MULTILINE)
bag_duration_s = float(duration_match.group(1)) if duration_match else 0.0
bag_start_time_s = float(start_match.group(1)) if start_match else 0.0
represented_duration_s = max(last_track_time_s - bag_start_time_s, 0.0)
duration_coverage = (
    min(represented_duration_s / bag_duration_s, 1.0)
    if bag_duration_s > 0.0
    else 0.0
)
minimum_duration_coverage = float(sys.argv[6])
coverage_passed = duration_coverage >= minimum_duration_coverage

frame_directory = Path(sys.argv[7]) if sys.argv[7] else None
frame_export_requested = sys.argv[8] == "true"
frame_paths: list[Path] = []
if frame_directory is not None:
    frame_paths = sorted(frame_directory.glob("frame_*_t_*.png"))
    temporary_paths = sorted(frame_directory.glob("frame_*_t_*.tmp.png"))
    if temporary_paths:
        raise ValueError(
            f"temporary reconstructed-frame files remain: {temporary_paths}"
        )

    frame_pattern = re.compile(r"^frame_([0-9]{6})_t_([0-9]+)[.]png$")
    for expected_index, frame_path in enumerate(frame_paths):
        frame_match = frame_pattern.match(frame_path.name)
        if frame_match is None:
            raise ValueError(f"invalid reconstructed-frame name: {frame_path.name}")
        if int(frame_match.group(1)) != expected_index:
            raise ValueError(
                f"non-contiguous reconstructed-frame index: {frame_path.name}"
            )

        with frame_path.open("rb") as frame_stream:
            png_header = frame_stream.read(24)
        if (
            len(png_header) != 24
            or png_header[:8] != b"\x89PNG\r\n\x1a\n"
            or png_header[12:16] != b"IHDR"
        ):
            raise ValueError(f"invalid PNG header: {frame_path}")
        frame_width, frame_height = struct.unpack(">II", png_header[16:24])
        if frame_width == 0 or frame_height == 0:
            raise ValueError(f"invalid PNG geometry: {frame_path}")

if frame_export_requested and not frame_paths:
    raise ValueError("reconstructed-frame export produced no PNG files")

timing_summary_path = Path(sys.argv[9])
timing_summary = json.loads(timing_summary_path.read_text(encoding="utf-8"))
if timing_summary.get("status") != "passed":
    raise ValueError("processing timing summary did not pass validation")
if timing_summary.get("sample_count", 0) <= 0:
    raise ValueError("processing timing summary contains no samples")

summary = {
    "status": "passed" if coverage_passed else "failed",
    "ros2_bag": sys.argv[1],
    "events_topic": sys.argv[2],
    "tracks_file": sys.argv[3],
    "track_count": track_count,
    "track_rows": track_rows,
    "first_track_time_s": first_track_time_s,
    "last_track_time_s": last_track_time_s,
    "bag_start_time_s": bag_start_time_s,
    "bag_duration_s": bag_duration_s,
    "represented_duration_s": represented_duration_s,
    "duration_coverage": duration_coverage,
    "minimum_duration_coverage": minimum_duration_coverage,
    "reconstructed_frames_directory": (
        str(frame_directory) if frame_directory is not None else ""
    ),
    "saved_reconstructed_frame_count": len(frame_paths),
    "processing_timing": timing_summary,
}
Path(sys.argv[5]).write_text(
    json.dumps(summary, indent=2, sort_keys=True) + "\n",
    encoding="utf-8",
)
if not coverage_passed:
    print(
        "track duration coverage "
        f"{duration_coverage:.3f} is below {minimum_duration_coverage:.3f}",
        file=sys.stderr,
    )
    raise SystemExit(1)
PY

track_rows="$("${python_bin}" -c \
    'import json, sys; from pathlib import Path; print(json.loads(Path(sys.argv[1]).read_text(encoding="utf-8"))["track_rows"])' \
    "${run_summary}")"
saved_frame_count="$("${python_bin}" -c \
    'import json, sys; from pathlib import Path; print(json.loads(Path(sys.argv[1]).read_text(encoding="utf-8"))["saved_reconstructed_frame_count"])' \
    "${run_summary}")"
echo "ROS2 bag EKLT demo completed with ${track_rows} track rows."
echo "Saved reconstructed frames: ${saved_frame_count}"
echo "Processing timing CSV: ${processing_timing_file}"
echo "Processing timing plot: ${processing_timing_plot}"
if [[ "${save_reconstructed_frames}" == true ]]; then
    echo "Reconstructed frames: ${reconstructed_frames_dir}"
fi
echo "Summary: ${run_summary}"
