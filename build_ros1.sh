#!/usr/bin/env bash

# Build the ROS1 tracker in a non-destructively managed catkin workspace.
set -Eeuo pipefail

repo_root="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
workspace="${EKLT_CATKIN_WS:-${HOME}/eklt_catkin_ws}"
ros_distro="${ROS_DISTRO:-noetic}"
import_dependencies=false
jobs="${JOBS:-$(nproc 2>/dev/null || echo 4)}"

usage() {
    cat <<'USAGE'
Usage: ./build_ros1.sh [--workspace <dir>] [--ros-distro <name>]
                       [--import-dependencies] [-j <count>]

Creates or reuses a catkin workspace without deleting it, links this checkout
as the eklt_rebuild package, and builds with EKLT_BUILD_ROS1=ON.
USAGE
}

die() {
    echo "build_ros1.sh: $*" >&2
    exit 2
}

# Parse values before touching the workspace so malformed invocations cannot
# create directories or links.
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
        --import-dependencies) import_dependencies=true; shift ;;
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

# Source only the requested installed ROS distribution.
ros_setup="/opt/ros/${ros_distro}/setup.bash"
[[ -f "${ros_setup}" ]] || {
    echo "ROS1 setup not found: ${ros_setup}" >&2
    exit 1
}

set +u
# shellcheck source=/dev/null
source "${ros_setup}"
set -u

command -v catkin >/dev/null 2>&1 || {
    echo "catkin tools are required." >&2
    exit 1
}

# Canonicalize the workspace and reject the filesystem root before creating
# the package link.
workspace="$(realpath -m "${workspace}")"
[[ "${workspace}" != "/" ]] || die "workspace must not be the filesystem root."
package_link="${workspace}/src/eklt"
mkdir -p "${workspace}/src"

if [[ -e "${package_link}" && ! -L "${package_link}" ]]; then
    echo "Refusing to replace non-symlink package path: ${package_link}" >&2
    exit 1
fi
if [[ -L "${package_link}" &&
      "$(realpath -m "${package_link}")" != "${repo_root}" ]]; then
    echo "Refusing to replace symlink to another checkout: ${package_link}" >&2
    exit 1
fi
if [[ ! -e "${package_link}" ]]; then
    ln -s "${repo_root}" "${package_link}"
fi

# Import only on explicit request; normal builds preserve all existing
# workspace dependencies exactly as they are.
if [[ "${import_dependencies}" == true ]]; then
    command -v vcs >/dev/null 2>&1 || {
        echo "vcstool is required for --import-dependencies." >&2
        exit 1
    }
    vcs import "${workspace}/src" < "${repo_root}/dependencies.yaml"
fi

# Configure and build only the ROS1 compatibility package.
catkin config \
    --workspace "${workspace}" \
    --init \
    --mkdirs \
    --extend "/opt/ros/${ros_distro}" \
    --cmake-args \
        -DCMAKE_BUILD_TYPE=Release \
        -DEKLT_BUILD_ROS1=ON \
        -DEKLT_BUILD_PYTHON=OFF \
        -DEKLT_BUILD_MATLAB=OFF \
        -DPYTHON_EXECUTABLE=/usr/bin/python3

catkin build --workspace "${workspace}" --jobs "${jobs}" eklt_rebuild
