#!/usr/bin/env bash

# Run one bounded FIBAR reconstruction and diagnostic pass on ELOPE data.
set -Eeuo pipefail

script_dir="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
repo_root="$(cd "${script_dir}/.." && pwd)"

input=""
output_dir="${repo_root}/outputs/elope_reconstruction"
width=""
height=""
dt_ms="20"
event_preview_fps="100"
max_3d_points="50000"
patch_panel_size="800"
patch_columns="2"
patch_max_candidates="8"
max_patch_quality_samples="50000"
python_bin="${PYTHON:-python3.12}"

# Define the CLI contract and failure path without touching selected paths.
usage() {
    cat <<'USAGE'
Usage: scripts/run_elope_reconstruction_example_demo.sh [options]

Required:
  --input <file>                 Official ELOPE NPZ sequence.

Options:
  --output-dir <directory>       Owned reconstruction artifact directory.
  --width <pixels>               Optional sensor-width override.
  --height <pixels>              Optional sensor-height override.
  --dt-ms <milliseconds>         FIBAR output interval. Defaults to 20.
  --event-preview-fps <rate>     Event-preview frame rate. Defaults to 100.
  --max-3d-points <count>        Maximum displayed event-cloud points.
  --patch-panel-size <pixels>    Event-panel height in [128, 2048].
  --patch-columns <count>        Patch-mosaic column count.
  --patch-max-candidates <count> Candidate slots in [1, 32].
  --max-patch-quality-samples <count>
                                 Maximum retained patch-quality samples.
  -h, --help                     Show this help.
USAGE
}

die() {
    echo "run_elope_reconstruction_example_demo.sh: $*" >&2
    exit 2
}

# Parse policy without touching the caller-selected source or output paths.
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
        --dt-ms)
            (($# >= 2)) || die "--dt-ms requires a value."
            dt_ms="$2"
            shift 2
            ;;
        --event-preview-fps)
            (($# >= 2)) || die "--event-preview-fps requires a value."
            event_preview_fps="$2"
            shift 2
            ;;
        --max-3d-points)
            (($# >= 2)) || die "--max-3d-points requires a value."
            max_3d_points="$2"
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
        -h|--help)
            usage
            exit 0
            ;;
        *)
            die "unknown option: $1"
            ;;
    esac
done

# Validate source, paired geometry, interpreter, and cleanup root before
# constructing the Python example command.
[[ -n "${input}" ]] || die "--input is required."
[[ -f "${input}" ]] || die "ELOPE input not found: ${input}"
if [[ -n "${width}" || -n "${height}" ]]; then
    [[ -n "${width}" && -n "${height}" ]] ||
        die "--width and --height must be provided together."
fi
command -v "${python_bin}" >/dev/null 2>&1 ||
    die "Python interpreter not found: ${python_bin}"
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

# Build one argument vector so optional paired geometry is forwarded atomically
# and shell word splitting cannot alter caller values.
arguments=(
    --input "$(realpath "${input}")"
    --output-dir "${output_dir}"
    --dt-ms "${dt_ms}"
    --event-preview-fps "${event_preview_fps}"
    --max-3d-points "${max_3d_points}"
    --patch-panel-size "${patch_panel_size}"
    --patch-columns "${patch_columns}"
    --patch-max-candidates "${patch_max_candidates}"
    --max-patch-quality-samples "${max_patch_quality_samples}"
)
if [[ -n "${width}" ]]; then
    arguments+=(--width "${width}" --height "${height}")
fi

# Run the installed-style module with only the repository Python source added;
# bytecode generation is disabled so the demo does not dirty the checkout.
PYTHONDONTWRITEBYTECODE=1 \
PYTHONPATH="${repo_root}/python${PYTHONPATH:+:${PYTHONPATH}}" \
"${python_bin}" \
    -m event_vision_utils.examples.reconstruct_elope_fibar \
    "${arguments[@]}"
