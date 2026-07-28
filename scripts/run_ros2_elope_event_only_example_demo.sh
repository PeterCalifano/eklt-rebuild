#!/usr/bin/env bash

# Convert an ELOPE event array and run the standard ROS2 event-only demo.
set -Eeuo pipefail

script_dir="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
repo_root="$(cd "${script_dir}/.." && pwd)"

input=""
output_dir="${repo_root}/outputs/ros2_elope_event_only"
width=""
height=""
events_topic="/events"
dt_ms="20.0"
max_events_per_packet=100000
max_packets=0
python_bin="${PYTHON:-python3}"
playback_rate="10.0"
post_playback_wait_s="5"
min_duration_coverage="0.8"
ros_setup="${ROS_SETUP:-}"
overlay_setup="${EKLT_ROS2_SETUP:-}"
visualize=false
save_reconstructed_frames=false
saved_frame_stride=1
max_saved_frames=0
png_compression=3

usage() {
    cat <<'USAGE'
Usage: scripts/run_ros2_elope_event_only_example_demo.sh [options]

Required:
  --input <file>            ELOPE .npz file containing an events array.

Options:
  --output-dir <directory>  EventPacket bag, tracks, images, logs, and summary.
  --width <pixels>          Optional sensor-width override.
  --height <pixels>         Optional sensor-height override.
  --events-topic <topic>    ROS2 EventPacket topic. Defaults to /events.
  --dt-ms <milliseconds>    Maximum EventPacket time span. Defaults to 20.
  --max-events-per-packet <count>
                             Maximum events in one packet. Defaults to 100000.
  --max-packets <count>     Convert only the first count packets; zero is all.
  --playback-rate <scale>   rosbag2 playback rate. Defaults to 10.0.
  --post-playback-wait-s <s>
                             Time for the bounded EKLT queue to drain.
  --min-duration-coverage <ratio>
                             Required last-track coverage in [0, 1].
  --visualize               View /eklt/feature_tracks with rqt_image_view.
  --save-reconstructed-frames
                             Save normalized FIBAR frames as PNG files.
  --saved-frame-stride <n>  Save every nth reconstructed frame. Defaults to 1.
  --max-saved-frames <n>    Stop saving after n frames; zero is unlimited.
  --png-compression <0-9>   OpenCV PNG compression. Defaults to 3.
  --ros-setup <file>        Base ROS2 setup file to source explicitly.
  --overlay-setup <file>    EKLT overlay setup file to source explicitly.
  -h, --help                Show this help.

The converter uses NumPy and rosbags from PYTHON, including an active Conda
environment. Explicit NPZ width/height metadata is used when present; otherwise
the official 200-by-200 ELOPE geometry applies. Both override options must be
provided together and must match advertised metadata. Camera intrinsics and the
other ELOPE arrays are not required.
USAGE
}

die() {
    echo "run_ros2_elope_event_only_example_demo.sh: $*" >&2
    exit 2
}

while (($# > 0)); do
    case "$1" in
        --input)
            (($# >= 2)) || die "--input requires a value."
            input="$2"
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
        --events-topic)
            (($# >= 2)) || die "--events-topic requires a value."
            events_topic="$2"
            shift 2
            ;;
        --dt-ms)
            (($# >= 2)) || die "--dt-ms requires a value."
            dt_ms="$2"
            shift 2
            ;;
        --max-events-per-packet)
            (($# >= 2)) || die "--max-events-per-packet requires a value."
            max_events_per_packet="$2"
            shift 2
            ;;
        --max-packets)
            (($# >= 2)) || die "--max-packets requires a value."
            max_packets="$2"
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

[[ -n "${input}" ]] || die "--input is required."
[[ -f "${input}" ]] || die "ELOPE input not found: ${input}"
if [[ -n "${width}" || -n "${height}" ]]; then
    [[ -n "${width}" && -n "${height}" ]] ||
        die "--width and --height must be provided together."
    [[ "${width}" =~ ^[1-9][0-9]*$ ]] || die "--width must be positive."
    [[ "${height}" =~ ^[1-9][0-9]*$ ]] || die "--height must be positive."
    ((width <= 65535)) || die "--width must not exceed 65535."
    ((height <= 32767)) || die "--height must not exceed 32767."
fi
[[ "${events_topic}" == /* ]] || die "--events-topic must be absolute."
[[ "${dt_ms}" =~ ^[0-9]+([.][0-9]+)?$ ]] ||
    die "--dt-ms must be a positive number."
[[ "${dt_ms}" != "0" && "${dt_ms}" != "0.0" ]] ||
    die "--dt-ms must be positive."
[[ "${max_events_per_packet}" =~ ^[1-9][0-9]*$ ]] ||
    die "--max-events-per-packet must be positive."
[[ "${max_packets}" =~ ^[0-9]+$ ]] ||
    die "--max-packets must be nonnegative."
command -v "${python_bin}" >/dev/null 2>&1 ||
    die "Python interpreter not found: ${python_bin}"

input="$(realpath "${input}")"
output_dir="$(realpath -m "${output_dir}")"
[[ "${output_dir}" != "/" ]] ||
    die "output directory must not be the filesystem root."
mkdir -p "${output_dir}"

eventpacket_bag="${output_dir}/eventpacket_bag"
conversion_summary="${output_dir}/elope_conversion_summary.json"
if [[ ! -d "${eventpacket_bag}" ]]; then
    "${python_bin}" -c "import numpy, rosbags" >/dev/null 2>&1 ||
        die "ELOPE conversion requires Python packages numpy and rosbags."
    converter_arguments=(
        --input "${input}"
        --output "${eventpacket_bag}"
        --output-topic "${events_topic}"
        --summary-output "${conversion_summary}"
        --dt-ms "${dt_ms}"
        --max-events-per-packet "${max_events_per_packet}"
        --max-packets "${max_packets}"
    )
    if [[ -n "${width}" ]]; then
        converter_arguments+=(--width "${width}" --height "${height}")
    fi
    PYTHONDONTWRITEBYTECODE=1 "${python_bin}" \
        "${script_dir}/convert_elope_npz_to_eventpacket.py" \
        "${converter_arguments[@]}"
else
    [[ -f "${eventpacket_bag}/metadata.yaml" ]] ||
        die "existing EventPacket bag is incomplete: ${eventpacket_bag}"
    [[ -f "${conversion_summary}" ]] ||
        die "existing EventPacket bag has no ELOPE provenance summary."

    # Reuse only a bag generated from the exact requested source and packet
    # policy so stale output cannot silently change the demo input.
    PYTHONDONTWRITEBYTECODE=1 "${python_bin}" - \
        "${conversion_summary}" "${input}" "${events_topic}" \
        "${width}" "${height}" "${dt_ms}" \
        "${max_events_per_packet}" "${max_packets}" <<'PY'
from __future__ import annotations

import json
import sys
from pathlib import Path

summary = json.loads(Path(sys.argv[1]).read_text(encoding="utf-8"))
expected = {
    "input": sys.argv[2],
    "output_topic": sys.argv[3],
    "dt_ms": float(sys.argv[6]),
    "max_events_per_packet": int(sys.argv[7]),
    "max_packets": int(sys.argv[8]),
}
if bool(sys.argv[4]) != bool(sys.argv[5]):
    raise SystemExit("ELOPE width and height overrides must be paired")
if sys.argv[4]:
    expected["width"] = int(sys.argv[4])
    expected["height"] = int(sys.argv[5])
mismatches = {
    key: (summary.get(key), value)
    for key, value in expected.items()
    if summary.get(key) != value
}
if not summary.get("geometry_source"):
    mismatches["geometry_source"] = (
        summary.get("geometry_source"),
        "resolved geometry provenance",
    )
if mismatches:
    print(f"ELOPE EventPacket provenance mismatch: {mismatches}", file=sys.stderr)
    raise SystemExit(1)
PY
    echo "Reusing converted ELOPE EventPacket bag: ${eventpacket_bag}"
fi

runner_arguments=(
    --ros2-bag "${eventpacket_bag}"
    --events-topic "${events_topic}"
    --output-dir "${output_dir}"
    --playback-rate "${playback_rate}"
    --post-playback-wait-s "${post_playback_wait_s}"
    --min-duration-coverage "${min_duration_coverage}"
)
if [[ -n "${ros_setup}" ]]; then
    runner_arguments+=(--ros-setup "${ros_setup}")
fi
if [[ -n "${overlay_setup}" ]]; then
    runner_arguments+=(--overlay-setup "${overlay_setup}")
fi
if [[ "${visualize}" == true ]]; then
    runner_arguments+=(--visualize)
fi
if [[ "${save_reconstructed_frames}" == true ]]; then
    runner_arguments+=(
        --save-reconstructed-frames
        --saved-frame-stride "${saved_frame_stride}"
        --max-saved-frames "${max_saved_frames}"
        --png-compression "${png_compression}"
    )
fi

PYTHON="${python_bin}" "${script_dir}/run_ros2_rosbag_event_only_demo.sh" \
    "${runner_arguments[@]}"

# Extend the common rosbag summary with ELOPE-specific source provenance while
# preserving every shared visualization and PNG result.
PYTHONDONTWRITEBYTECODE=1 "${python_bin}" - \
    "${output_dir}/summary.json" "${conversion_summary}" "${input}" <<'PY'
from __future__ import annotations

import json
import os
import sys
from pathlib import Path

summary_path = Path(sys.argv[1])
conversion_path = Path(sys.argv[2])
summary = json.loads(summary_path.read_text(encoding="utf-8"))
summary["source_type"] = "elope_npz"
summary["elope_input"] = sys.argv[3]
summary["elope_conversion"] = json.loads(
    conversion_path.read_text(encoding="utf-8")
)

temporary_path = summary_path.with_suffix(".tmp.json")
temporary_path.write_text(
    json.dumps(summary, indent=2, sort_keys=True) + "\n",
    encoding="utf-8",
)
os.replace(temporary_path, summary_path)
PY

echo "ELOPE ROS2 event-only demo completed."
echo "Summary: ${output_dir}/summary.json"
