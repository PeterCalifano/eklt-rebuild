#!/usr/bin/env bash

# Configure and validate the ROS-free native core and optional generated wrappers.
set -Eeuo pipefail

repo_root="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
build_dir="${repo_root}/build/native"
build_type="RelWithDebInfo"
jobs="${JOBS:-$(nproc 2>/dev/null || echo 4)}"
run_tests=true
build_python=false
build_matlab=false
build_docs=false
run_install=false
run_package=false
run_source_package=false
profiling=false
clean_first=false
toolchain_file=""
cmake_defines=()

usage() {
    cat <<'USAGE'
Usage: ./build_lib.sh [options]

Build the ROS-free eklt-rebuild core and optional gtwrap adapters.

Options:
  -B, --build-dir <dir>  Build directory (default: build/native)
  -j, --jobs <count>     Parallel build jobs
  -t, --type <type>      Debug, Release, RelWithDebInfo, or MinSizeRel
  -D, --define <k=v>     Extra CMake definition; repeatable
  -p, --python           Build the Python 3.12 gtwrap adapter
  -m, --matlab           Build the MATLAB R2024b gtwrap adapter
      --docs             Build Doxygen documentation
      --install          Install under <build-dir>/install
      --package          Generate CPack archives
      --source-package   Generate the filtered CPack source archive
      --profile          Enable profiling-friendly flags and gperftools lookup
      --skip-tests       Skip CTest and Python tests
      --toolchain <file> Use a CMake toolchain file
      --clean            Remove only the selected build directory first
  -h, --help             Show this help

ROS is intentionally separate:
  ./build_ros1.sh
  ./build_ros2.sh
USAGE
}

fail() {
    echo "Error: $*" >&2
    exit 2
}

while (($# > 0)); do
    case "$1" in
        -B|--build-dir)
            (($# >= 2)) || fail "$1 requires a directory"
            build_dir="$2"
            shift 2
            ;;
        -j|--jobs)
            (($# >= 2)) || fail "$1 requires a count"
            jobs="$2"
            shift 2
            ;;
        -t|--type)
            (($# >= 2)) || fail "$1 requires a build type"
            build_type="$2"
            shift 2
            ;;
        -D|--define)
            (($# >= 2)) || fail "$1 requires KEY=VALUE"
            cmake_defines+=("-D$2")
            shift 2
            ;;
        -p|--python)
            build_python=true
            shift
            ;;
        -m|--matlab)
            build_matlab=true
            shift
            ;;
        --docs)
            build_docs=true
            shift
            ;;
        --install)
            run_install=true
            shift
            ;;
        --package)
            run_package=true
            shift
            ;;
        --source-package)
            run_source_package=true
            shift
            ;;
        --profile)
            profiling=true
            shift
            ;;
        --skip-tests)
            run_tests=false
            shift
            ;;
        --toolchain)
            (($# >= 2)) || fail "$1 requires a file"
            toolchain_file="$2"
            shift 2
            ;;
        --clean)
            clean_first=true
            shift
            ;;
        -h|--help)
            usage
            exit 0
            ;;
        *)
            fail "unknown option: $1"
            ;;
    esac
done

case "${build_type,,}" in
    debug) build_type="Debug" ;;
    release) build_type="Release" ;;
    relwithdebinfo) build_type="RelWithDebInfo" ;;
    minsizerel) build_type="MinSizeRel" ;;
    *) fail "unsupported build type: ${build_type}" ;;
esac

[[ "${jobs}" =~ ^[1-9][0-9]*$ ]] || fail "jobs must be a positive integer"
command -v cmake >/dev/null 2>&1 || fail "cmake is required"

if [[ -n "${toolchain_file}" ]]; then
    [[ -f "${toolchain_file}" ]] || fail "toolchain file not found: ${toolchain_file}"
    toolchain_file="$(realpath "${toolchain_file}")"
fi

if [[ "${build_python}" == true || "${build_matlab}" == true ]]; then
    [[ -f "${repo_root}/lib/wrap/cmake/PybindWrap.cmake" ]] ||
        fail "pinned lib/wrap checkout is missing; initialize the SSH submodule"
    expected_wrap_commit="bf9f78617830bfa88c70d81a1a791c0a0c90b548"
    actual_wrap_commit="$(git -C "${repo_root}/lib/wrap" rev-parse HEAD 2>/dev/null || true)"
    [[ "${actual_wrap_commit}" == "${expected_wrap_commit}" ]] ||
        fail "lib/wrap must remain pinned at ${expected_wrap_commit}; found ${actual_wrap_commit:-unknown}"
fi

if [[ "${build_python}" == true ]]; then
    command -v python3 >/dev/null 2>&1 || fail "Python 3.12 is required"
    python_version="$(python3 -c 'import sys; print(f"{sys.version_info.major}.{sys.version_info.minor}")')"
    [[ "${python_version}" == "3.12" ]] ||
        fail "Python 3.12 is required for wrappers; found ${python_version}"
fi

if [[ "${build_matlab}" == true ]]; then
    matlab_root="${EKLT_MATLAB_ROOT:-/usr/local/MATLAB/R2024b}"
    [[ -x "${matlab_root}/bin/matlab" ]] ||
        fail "MATLAB R2024b not found at ${matlab_root}"
fi

build_dir="$(realpath -m "${build_dir}")"
if [[ "${build_dir}" == "/" || "${build_dir}" == "${HOME}" || "${build_dir}" == "${repo_root}" ]]; then
    fail "refusing unsafe build directory: ${build_dir}"
fi

if [[ "${clean_first}" == true ]]; then
    # Constrain recursive removal to one CMake build owned by this checkout.
    build_root="$(realpath -m "${repo_root}/build")"
    case "${build_dir}" in
        "${build_root}/"*) ;;
        *)
            fail "--clean requires a named build directory below ${build_root}"
            ;;
    esac

    if [[ -e "${build_dir}" ]]; then
        build_cache="${build_dir}/CMakeCache.txt"
        [[ -f "${build_cache}" ]] ||
            fail "refusing to clean a directory without an EKLT CMake cache: ${build_dir}"
        cached_source_dir="$(
            sed -n 's/^CMAKE_HOME_DIRECTORY:INTERNAL=//p' "${build_cache}" |
                tail -n 1
        )"
        [[ -n "${cached_source_dir}" ]] ||
            fail "EKLT source marker is missing from ${build_cache}"
        cached_source_dir="$(realpath -m "${cached_source_dir}")"
        [[ "${cached_source_dir}" == "${repo_root}" ]] ||
            fail "refusing to clean a build owned by ${cached_source_dir}"
        cmake -E remove_directory "${build_dir}"
    fi
fi

cmake_args=(
    -S "${repo_root}"
    -B "${build_dir}"
    "-DCMAKE_BUILD_TYPE=${build_type}"
    "-DEKLT_BUILD_ROS1=OFF"
    "-DEKLT_BUILD_PYTHON=$([[ "${build_python}" == true ]] && echo ON || echo OFF)"
    "-DEKLT_BUILD_MATLAB=$([[ "${build_matlab}" == true ]] && echo ON || echo OFF)"
    "-DEKLT_BUILD_DOCS=$([[ "${build_docs}" == true ]] && echo ON || echo OFF)"
    "-DENABLE_TESTS=$([[ "${run_tests}" == true ]] && echo ON || echo OFF)"
    "-DENABLE_PROFILING=$([[ "${profiling}" == true ]] && echo ON || echo OFF)"
    "-DCMAKE_EXPORT_COMPILE_COMMANDS=ON"
)

if [[ "${build_python}" == true || "${build_matlab}" == true ]]; then
    cmake_args+=(
        "-DGTWRAP_SYNC_TO_MASTER=OFF"
        "-DGTWRAP_INIT_SUBMODULE_IF_MISSING=OFF"
        "-DGTWRAP_ADD_SUBMODULE_IF_MISSING=OFF"
    )
fi
if [[ "${build_python}" == true ]]; then
    cmake_args+=("-DPython_EXECUTABLE=$(command -v python3)")
fi
if [[ "${build_matlab}" == true ]]; then
    cmake_args+=("-DMatlab_ROOT_DIR=${matlab_root}")
fi
if [[ -n "${toolchain_file}" ]]; then
    cmake_args+=("-DCMAKE_TOOLCHAIN_FILE=${toolchain_file}")
fi
cmake_args+=("${cmake_defines[@]}")

cmake "${cmake_args[@]}"
cmake --build "${build_dir}" --parallel "${jobs}"

if [[ "${run_tests}" == true ]]; then
    ctest --test-dir "${build_dir}" --output-on-failure --no-tests=error
    if [[ "${build_python}" == true ]]; then
        # In-tree wrapper tests load the canonical src/ library output; wheel
        # and install relocation remain the packaging layer's responsibility.
        native_library_path="${build_dir}/src:${build_dir}"
        PYTHONPATH="${repo_root}/python${PYTHONPATH:+:${PYTHONPATH}}" \
        LD_LIBRARY_PATH="${native_library_path}${LD_LIBRARY_PATH:+:${LD_LIBRARY_PATH}}" \
            python3 -m pytest -q "${repo_root}/python/tests"
    fi
fi

if [[ "${build_docs}" == true ]]; then
    cmake --build "${build_dir}" --target eklt_doc --parallel "${jobs}"
fi

if [[ "${run_install}" == true ]]; then
    cmake --install "${build_dir}" --prefix "${build_dir}/install"
fi

if [[ "${run_package}" == true ]]; then
    cpack --config "${build_dir}/CPackConfig.cmake" -B "${build_dir}/package"
fi

if [[ "${run_source_package}" == true ]]; then
    cpack \
        --config "${build_dir}/CPackSourceConfig.cmake" \
        -B "${build_dir}/package/source"
fi
