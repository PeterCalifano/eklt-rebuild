#!/usr/bin/env bash

# Download and safely extract validated official ELOPE NPZ sequences.
set -Eeuo pipefail

script_dir="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
repo_root="$(cd "${script_dir}/.." && pwd)"

url="https://zenodo.org/api/records/15421707/files/elope_dataset.zip/content"
output_dir="${repo_root}/data/elope"
zip_path=""
extract=true
first_only=false
force=false
python_bin="${PYTHON:-python3.12}"

usage() {
    cat <<'USAGE'
Usage: scripts/download_elope_dataset.sh [options]

Options:
  --output-dir <directory>  Owned download and extraction root.
  --zip-path <file>         Archive path below --output-dir.
  --url <url>               Alternate ELOPE archive URL.
  --no-extract              Download or reuse the archive without extraction.
  --first-only              Extract only the first sorted NPZ sequence.
  --force                   Replace the owned archive before downloading.
  -h, --help                Show this help.
USAGE
}

die() {
    echo "download_elope_dataset.sh: $*" >&2
    exit 2
}

while (($# > 0)); do
    case "$1" in
        --output-dir)
            (($# >= 2)) || die "--output-dir requires a value."
            output_dir="$2"
            shift 2
            ;;
        --zip-path)
            (($# >= 2)) || die "--zip-path requires a value."
            zip_path="$2"
            shift 2
            ;;
        --url)
            (($# >= 2)) || die "--url requires a value."
            url="$2"
            shift 2
            ;;
        --no-extract)
            extract=false
            shift
            ;;
        --first-only)
            first_only=true
            shift
            ;;
        --force)
            force=true
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

command -v "${python_bin}" >/dev/null 2>&1 ||
    die "Python interpreter not found: ${python_bin}"
command -v realpath >/dev/null 2>&1 ||
    die "realpath is required."

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

if [[ -z "${zip_path}" ]]; then
    zip_path="${output_dir}/elope_dataset.zip"
elif [[ "${zip_path}" != /* ]]; then
    zip_path="${output_dir}/${zip_path}"
fi
[[ ! -L "${zip_path}" ]] ||
    die "archive path must not be a symlink: ${zip_path}"
zip_path="$(realpath -m "${zip_path}")"
case "${zip_path}" in
    "${output_dir}"/*)
        ;;
    *)
        die "--zip-path must remain below --output-dir."
        ;;
esac
if [[ -e "${zip_path}" && ! -f "${zip_path}" ]]; then
    die "archive path is not a regular file: ${zip_path}"
fi
partial_path="${zip_path}.part"
[[ ! -L "${partial_path}" ]] ||
    die "partial archive path must not be a symlink: ${partial_path}"
if [[ -e "${partial_path}" && ! -f "${partial_path}" ]]; then
    die "partial archive path is not a regular file: ${partial_path}"
fi

# --force may remove only the exact conventional archive owned by the selected
# output directory; extracted data and unrelated files remain untouched.
if [[ "${force}" == true ]]; then
    rm -f -- "${zip_path}" "${partial_path}"
fi

if [[ -f "${zip_path}" ]]; then
    echo "archive exists: ${zip_path}"
else
    command -v curl >/dev/null 2>&1 ||
        die "curl is required to download ELOPE."
    echo "downloading ELOPE dataset from ${url}"
    curl \
        --fail \
        --location \
        --continue-at - \
        --output "${partial_path}" \
        "${url}"
    mv -f -- "${partial_path}" "${zip_path}"
fi

if [[ "${extract}" == false ]]; then
    echo "downloaded: ${zip_path}"
    exit 0
fi

PYTHONDONTWRITEBYTECODE=1 \
PYTHONPATH="${repo_root}/python${PYTHONPATH:+:${PYTHONPATH}}" \
"${python_bin}" - "${zip_path}" "${output_dir}" "${first_only}" <<'PY'
from __future__ import annotations

import os
import shutil
import sys
import zipfile
from pathlib import Path, PurePosixPath

from event_vision_utils.io import validate_elope_npz


archive_path = Path(sys.argv[1])
output_dir = Path(sys.argv[2]).resolve()
first_only = sys.argv[3].lower() == "true"

with zipfile.ZipFile(archive_path) as archive:
    members = sorted(
        (
            info
            for info in archive.infolist()
            if (
                not info.is_dir() and
                info.filename.lower().endswith(".npz")
            )
        ),
        key=lambda info: info.filename,
    )
    if not members:
        raise SystemExit(f"no NPZ sequences found in {archive_path}")
    selected = members[:1] if first_only else members
    extracted_paths: list[Path] = []
    selected_targets: set[Path] = set()

    for member in selected:
        member_path = PurePosixPath(member.filename)
        if (
            member_path.is_absolute()
            or ".." in member_path.parts
            or "\\" in member.filename
        ):
            raise SystemExit(
                f"unsafe ELOPE archive member: {member.filename}"
            )

        target_path = output_dir.joinpath(*member_path.parts)
        parent_path = output_dir
        for part in member_path.parts[:-1]:
            parent_path /= part
            if parent_path.is_symlink():
                raise SystemExit(
                    "refusing symlinked ELOPE target parent: "
                    f"{parent_path}"
                )
            if parent_path.exists() and not parent_path.is_dir():
                raise SystemExit(
                    "ELOPE target parent is not a directory: "
                    f"{parent_path}"
                )
        resolved_target = target_path.resolve(strict=False)
        try:
            resolved_target.relative_to(output_dir)
        except ValueError as exc:
            raise SystemExit(
                f"ELOPE archive member escapes output: {member.filename}"
            ) from exc
        if target_path.is_symlink():
            raise SystemExit(
                f"refusing symlinked ELOPE target: {target_path}"
            )
        if target_path.exists() and not target_path.is_file():
            raise SystemExit(
                f"ELOPE target is not a regular file: {target_path}"
            )
        if resolved_target in selected_targets:
            raise SystemExit(
                f"duplicate ELOPE archive target: {member.filename}"
            )
        selected_targets.add(resolved_target)
        target_path.parent.mkdir(parents=True, exist_ok=True)

        # Validate a complete temporary sibling before atomically replacing
        # the selected dataset sequence.
        temporary_path = target_path.with_name(
            f".{target_path.stem}.tmp.npz"
        )
        if temporary_path.is_symlink():
            raise SystemExit(
                f"refusing symlinked temporary target: {temporary_path}"
            )
        if temporary_path.exists() and not temporary_path.is_file():
            raise SystemExit(
                f"temporary target is not a regular file: {temporary_path}"
            )
        try:
            with (
                archive.open(member, "r") as source,
                temporary_path.open("wb") as destination,
            ):
                shutil.copyfileobj(source, destination)
            validate_elope_npz(temporary_path)
            os.replace(temporary_path, target_path)
        finally:
            temporary_path.unlink(missing_ok=True)
        validate_elope_npz(target_path)
        extracted_paths.append(target_path)

first_sequence = extracted_paths[0]
print(f"validated_first_sequence={first_sequence}")
print(f"extracted_sequences={len(extracted_paths)}")
PY
