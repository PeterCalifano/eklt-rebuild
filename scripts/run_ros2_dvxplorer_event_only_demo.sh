#!/usr/bin/env bash

# Run native event-only EKLT from a live DVXplorer EventPacket stream.
set -Eeuo pipefail

script_dir="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
repo_root="$(cd "${script_dir}/.." && pwd)"

ros_setup="${ROS_SETUP:-}"
overlay_setup="${EKLT_ROS2_SETUP:-}"
default_ros_setup="/opt/ros/jazzy/setup.bash"
output_dir="${repo_root}/outputs/ros2_dvxplorer_event_only"
source_mode="external"
events_topic="/events"
duration_s=0
discovery_timeout_s=20
check_only=false

usage() {
    cat <<'USAGE'
Usage: scripts/run_ros2_dvxplorer_event_only_demo.sh [options]

Options:
  --source external|libcaer  Use an existing EventPacket publisher or launch
                             the standard ROS2 libcaer DVXplorer driver.
  --events-topic <topic>     EventPacket topic. Defaults to /events for an
                             external source and /event_camera/events for
                             libcaer unless explicitly set.
  --output-dir <dir>         Track and log output directory.
  --duration-s <seconds>     Stop after a duration; zero runs until Ctrl-C.
  --discovery-timeout-s <s>  Time allowed for EventPacket topic discovery.
  --ros-setup <file>         Base ROS2 setup file to source explicitly.
  --overlay-setup <file>     EKLT overlay setup file to source explicitly.
  --check-only               Validate the selected runtime dependencies only.
  -h, --help                 Show this help.

dv-runtime note:
  The upstream dv-runtime ROS bridge publishes ROS1 dv_ros_msgs, not ROS2
  EventPacket. Use --source external only with a separate bridge that publishes
  event_camera_msgs/msg/EventPacket. For direct ROS2 camera access, use
  --source libcaer and stop dv-runtime first so it releases the camera.
USAGE
}

die() {
    echo "run_ros2_dvxplorer_event_only_demo.sh: $*" >&2
    exit 2
}

events_topic_explicit=false
while (($# > 0)); do
    case "$1" in
        --source)
            (($# >= 2)) || die "--source requires a value."
            source_mode="$2"
            shift 2
            ;;
        --events-topic)
            (($# >= 2)) || die "--events-topic requires a value."
            events_topic="$2"
            events_topic_explicit=true
            shift 2
            ;;
        --output-dir)
            (($# >= 2)) || die "--output-dir requires a value."
            output_dir="$2"
            shift 2
            ;;
        --duration-s)
            (($# >= 2)) || die "--duration-s requires a value."
            duration_s="$2"
            shift 2
            ;;
        --discovery-timeout-s)
            (($# >= 2)) || die "--discovery-timeout-s requires a value."
            discovery_timeout_s="$2"
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
        --check-only)
            check_only=true
            shift
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

[[ "${source_mode}" == "external" || "${source_mode}" == "libcaer" ]] ||
    die "--source must be external or libcaer."
[[ "${duration_s}" =~ ^[0-9]+([.][0-9]+)?$ ]] ||
    die "--duration-s must be a nonnegative number."
[[ "${discovery_timeout_s}" =~ ^[0-9]+([.][0-9]+)?$ ]] ||
    die "--discovery-timeout-s must be a nonnegative number."
[[ -n "${events_topic}" && "${events_topic}" == /* ]] ||
    die "--events-topic must be an absolute ROS2 topic."
[[ -z "${ros_setup}" || -f "${ros_setup}" ]] ||
    die "ROS2 setup not found: ${ros_setup}"
[[ -z "${overlay_setup}" || -f "${overlay_setup}" ]] ||
    die "EKLT overlay setup not found: ${overlay_setup}"

if [[ "${source_mode}" == "libcaer" && "${events_topic_explicit}" == "false" ]]; then
    events_topic="/event_camera/events"
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
ros2 pkg prefix eklt_rebuild >/dev/null 2>&1 ||
    die "eklt_rebuild is not installed in the current ROS2 environment."
package_prefix="$(ros2 pkg prefix eklt_rebuild)"
node_executable="${package_prefix}/lib/eklt_rebuild/event_only_eklt_node"
[[ -x "${node_executable}" ]] ||
    die "installed EKLT node is not executable: ${node_executable}"

driver_executable=""
if [[ "${source_mode}" == "libcaer" ]]; then
    ros2 pkg prefix libcaer_driver >/dev/null 2>&1 ||
        die "libcaer_driver is required for --source libcaer."
    libcaer_prefix="$(ros2 pkg prefix libcaer_driver)"
    driver_executable="${libcaer_prefix}/lib/libcaer_driver/driver_node"
    [[ -x "${driver_executable}" ]] ||
        die "installed libcaer driver is not executable: ${driver_executable}"
fi

if [[ "${check_only}" == "true" ]]; then
    echo "ROS2 DVXplorer demo dependencies are available for source=${source_mode}."
    exit 0
fi
command -v python3 >/dev/null 2>&1 ||
    die "python3 is required for monotonic demo timing."

output_dir="$(realpath -m "${output_dir}")"
[[ "${output_dir}" != "/" ]] || die "output directory must not be the filesystem root."
mkdir -p "${output_dir}"
tracks_file="${output_dir}/tracks.txt"
node_log="${output_dir}/event_only_eklt_node.log"
driver_log="${output_dir}/libcaer_driver.log"
rm -f "${tracks_file}" "${node_log}" "${driver_log}"

params_file="${package_prefix}/share/eklt_rebuild/config/eklt_ros2.yaml"
[[ -f "${params_file}" ]] || die "installed EKLT parameter file not found: ${params_file}"

node_pid=""
driver_pid=""
stop_requested=false
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
    local child_pid
    for child_pid in "${driver_pid}" "${node_pid}"; do
        stop_child "${child_pid}"
    done
}
request_stop() {
    stop_requested=true
}
trap cleanup EXIT
trap request_stop INT TERM

# Start EKLT first so the bounded sensor-data subscription is ready before a
# high-rate camera publisher begins emitting packets.
"${node_executable}" \
    --ros-args \
    --params-file "${params_file}" \
    -p events_topic:="${events_topic}" \
    -p tracks_file_txt:="${tracks_file}" \
    >"${node_log}" 2>&1 &
node_pid="$!"

if [[ "${source_mode}" == "libcaer" ]]; then
    if command -v dv-runtime >/dev/null 2>&1; then
        echo "Ensure dv-runtime is stopped so libcaer_driver can own the DVXplorer USB device." >&2
    fi
    "${driver_executable}" \
        --ros-args \
        -r __node:=event_camera \
        -p device_type:=dvxplorer \
        -p encoding:=libcaer_cmp \
        >"${driver_log}" 2>&1 &
    driver_pid="$!"
fi

# Require the exact standard message type before treating the source as a live
# camera input. This catches ROS1 dv_ros_msgs bridges and topic typos early.
discovery_deadline="$(
    python3 -c 'import sys, time; print(time.monotonic() + float(sys.argv[1]))' \
        "${discovery_timeout_s}"
)"
topic_type=""
while :; do
    [[ "${stop_requested}" == "false" ]] ||
        die "live demo stopped before EventPacket discovery."
    child_is_running "${node_pid}" ||
        die "EKLT node exited before EventPacket discovery; inspect ${node_log}."
    if [[ -n "${driver_pid}" ]]; then
        child_is_running "${driver_pid}" ||
            die "libcaer driver exited before EventPacket discovery; inspect ${driver_log}."
    fi

    topic_type="$(ros2 topic type "${events_topic}" 2>/dev/null || true)"
    [[ -n "${topic_type}" ]] && break
    python3 -c 'import sys, time; raise SystemExit(time.monotonic() >= float(sys.argv[1]))' \
        "${discovery_deadline}" || die "EventPacket topic was not discovered: ${events_topic}"
    sleep 0.25
done
[[ "${topic_type}" == "event_camera_msgs/msg/EventPacket" ]] ||
    die "${events_topic} has type ${topic_type}, expected event_camera_msgs/msg/EventPacket."

echo "DVXplorer EventPacket input is live on ${events_topic}."
echo "Inspect EKLT with: ros2 topic echo /eklt/stats"
echo "View reconstructed images with: ros2 run rqt_image_view rqt_image_view /eklt/init_debug_image"

duration_deadline=""
if [[ "${duration_s}" != "0" && "${duration_s}" != "0.0" ]]; then
    duration_deadline="$(
        python3 -c 'import sys, time; print(time.monotonic() + float(sys.argv[1]))' \
            "${duration_s}"
    )"
fi

# Poll with short waits so Ctrl-C is a normal demo stop and unexpected node or
# direct-driver termination still produces a useful failure.
duration_expired=false
node_exited=false
driver_exited=false
while [[ "${stop_requested}" == "false" ]]; do
    if ! child_is_running "${node_pid}"; then
        node_exited=true
        break
    fi
    if [[ -n "${driver_pid}" ]] && ! child_is_running "${driver_pid}"; then
        driver_exited=true
        break
    fi
    if [[ -n "${duration_deadline}" ]] &&
       python3 -c 'import sys, time; raise SystemExit(time.monotonic() < float(sys.argv[1]))' \
            "${duration_deadline}"; then
        duration_expired=true
        break
    fi
    sleep 0.25 || true
done

cleanup
trap - EXIT INT TERM
[[ "${node_exited}" == "false" ]] ||
    die "EKLT node exited unexpectedly; inspect ${node_log}."
[[ "${driver_exited}" == "false" ]] ||
    die "libcaer driver exited unexpectedly; inspect ${driver_log}."
[[ "${stop_requested}" == "true" || "${duration_expired}" == "true" ]] ||
    die "live demo ended without a stop request or duration expiry."
[[ -s "${tracks_file}" ]] ||
    die "no EKLT track rows were produced; inspect ${node_log} and camera activity."
echo "DVXplorer EKLT demo completed: ${tracks_file}"
