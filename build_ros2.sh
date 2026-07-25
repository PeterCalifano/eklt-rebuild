#!/usr/bin/env bash

# Build the independent ROS2 event-only overlay in an external workspace.
set -Eeuo pipefail

repo_root="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
workspace="${EKLT_ROS2_WS:-${HOME}/eklt_ros2_ws}"
ros_distro="${ROS_DISTRO:-jazzy}"
jobs="${JOBS:-$(nproc 2>/dev/null || echo 4)}"

usage() {
    cat <<'USAGE'
Usage: ./build_ros2.sh [--workspace <dir>] [--ros-distro <name>] [-j <count>]

Creates or reuses a colcon build/install workspace without deleting it and
builds the experimental eklt_rebuild package from this checkout.
USAGE
}

die() {
    echo "build_ros2.sh: $*" >&2
    exit 2
}

# Validate the complete invocation before creating workspace directories.
while (($# > 0)); do
    case "$1" in
        --workspace)
            (($# >= 2)) || die "--workspace requires a value."
            workspace="$2"
            shift 2
            ;;
        --ros-distro)
            (($# >= 2)) || die "--ros-distro requires a value."
            ros_distro="$2"
            shift 2
            ;;
        -j|--jobs)
            (($# >= 2)) || die "$1 requires a value."
            jobs="$2"
            shift 2
            ;;
        -h|--help) usage; exit 0 ;;
        *) die "unknown option: $1" ;;
    esac
done

[[ "${ros_distro}" =~ ^[a-z0-9][a-z0-9_-]*$ ]] ||
    die "invalid ROS distro name: ${ros_distro}"
[[ "${jobs}" =~ ^[1-9][0-9]*$ ]] ||
    die "job count must be a positive integer: ${jobs}"

# Keep ROS2 implementation under the repository-owned overlay boundary.
ros2_package="${repo_root}/ros2/eklt_rebuild/package.xml"
[[ -f "${ros2_package}" ]] ||
    die "ROS2 package manifest not found: ${ros2_package}"

# Source only the requested installed ROS distribution.
ros_setup="/opt/ros/${ros_distro}/setup.bash"
[[ -f "${ros_setup}" ]] || {
    echo "ROS2 setup not found: ${ros_setup}" >&2
    exit 1
}

set +u
# shellcheck source=/dev/null
source "${ros_setup}"
set -u

command -v colcon >/dev/null 2>&1 || {
    echo "colcon is required." >&2
    exit 1
}

# Colcon receives explicit external build/install/log roots and a single
# package selection, keeping the overlay separate from the native build.
workspace="$(realpath -m "${workspace}")"
[[ "${workspace}" != "/" ]] || die "workspace must not be the filesystem root."
mkdir -p "${workspace}"

colcon --log-base "${workspace}/log" build \
    --base-paths "${repo_root}/ros2" \
    --build-base "${workspace}/build" \
    --install-base "${workspace}/install" \
    --packages-select eklt_rebuild \
    --parallel-workers "${jobs}" \
    --cmake-args -DCMAKE_BUILD_TYPE=RelWithDebInfo
