#!/usr/bin/env python3
"""Regenerate .devcontainer/devcontainer.json from environment options.

Merge-preserve behaviour: the existing devcontainer.json (if any) is loaded
first and only the keys managed by this script are rewritten. Everything else
(unmanaged environment values, customizations settings, mounts, ...) is kept
verbatim, so re-running the configure script never wipes project-specific
settings. The default VS Code extension set (DEFAULT_EXTENSIONS) is seeded
and guaranteed present, while any extra extensions in the file are preserved.
Output is plain JSON (JSONC comments in the input are stripped).
"""
import json
import os
import re
import sys

DEFAULT_CUDA_VERSION = "12.9"
DEFAULT_GPU_RUNTIME = "docker"
SUPPORTED_GPU_RUNTIMES = ("docker", "podman")

# remoteEnv entries owned by the CUDA option.
CUDA_REMOTE_ENV = {
    "PATH": "/usr/local/cuda/bin:${containerEnv:PATH}",
    "LD_LIBRARY_PATH": "/usr/local/cuda/lib64:${containerEnv:LD_LIBRARY_PATH}",
    "CUDA_HOME": "/usr/local/cuda",
}

# containerEnv entries owned by the ROS option.
ROS_CONTAINER_ENV = {
    "ROS_LOCALHOST_ONLY": "1",
    "ROS_DOMAIN_ID": "42",
}

CUDA_FEATURE_KEY = "ghcr.io/devcontainers/features/nvidia-cuda:2"

# Default VS Code extensions seeded into customizations.vscode.extensions.
# Managed like the conda/python features: regeneration guarantees these are
# present (even from scratch), while any extra extensions already in the file
# are preserved. Edit this list to change the template's editor defaults.
DEFAULT_EXTENSIONS = [
    "ms-vscode.cpptools",
    "ms-vscode.cpptools-themes",
    "ms-vscode.cmake-tools",
    "twxs.cmake",
    "njpwerner.autodocstring",
    "ms-python.autopep8",
    "ms-python.vscode-pylance",
    "ms-vscode.cpp-devtools",
    "Anthropic.claude-code",
    "ms-python.debugpy",
    "openai.chatgpt",
    "Gruntfuggly.todo-tree",
    "ms-vscode.cpptools-extension-pack",
    "ms-python.python",
    "donjayamanne.python-extension-pack",
    "llvm-vs-code-extensions.vscode-clangd",
]

# GPU passthrough runArgs are selected by the configure script. Docker's
# standard NVIDIA Container Toolkit path uses --gpus all, while Podman uses CDI.
DOCKER_GPU_RUN_ARGS = ["--gpus", "all"]
PODMAN_GPU_RUN_ARGS = [
    "--device",
    "nvidia.com/gpu=all",
    "--security-opt=label=disable",
]


def _gpu_run_args(gpu_runtime: str) -> list[str]:
    """Return managed GPU runArgs for the requested container engine.

    Example:
        arguments = _gpu_run_args("docker")
        print(arguments)
        # Output:
        # ['--gpus', 'all']
    """
    if gpu_runtime == "docker":
        return list(DOCKER_GPU_RUN_ARGS)
    if gpu_runtime == "podman":
        return list(PODMAN_GPU_RUN_ARGS)
    print(
        "update_devcontainer_json.py: DEVCONTAINER_GPU_RUNTIME must be one of: "
        + ", ".join(SUPPORTED_GPU_RUNTIMES),
        file=sys.stderr,
    )
    sys.exit(1)


def _strip_gpu_run_args(args: list[str]) -> list[str]:
    """Drop managed GPU passthrough pairs, preserving unrelated runArgs.

    Removes Docker, CDI, and SELinux-label forms owned by this updater so
    toggling/regenerating stays idempotent and migrates old files. Other
    ``--device`` entries are left untouched.
    """
    output: list[str] = []
    index = 0
    argument_count = len(args)

    while index < argument_count:
        current_argument = args[index]
        next_argument = (
            args[index + 1] if index + 1 < argument_count else None
        )
        if current_argument == "--gpus" and next_argument == "all":
            index += 2
            continue
        if current_argument == "--gpus=all":
            index += 1
            continue
        if (
            current_argument == "--device"
            and next_argument == "nvidia.com/gpu=all"
        ):
            index += 2
            continue
        if current_argument == "--device=nvidia.com/gpu=all":
            index += 1
            continue
        if (
            current_argument == "--security-opt"
            and next_argument == "label=disable"
        ):
            index += 2
            continue
        if current_argument == "--security-opt=label=disable":
            index += 1
            continue
        output.append(current_argument)
        index += 1

    return output


def _strip_jsonc_comments(text: str) -> str:
    """Remove JSONC comments while preserving string contents.

    Example:
        cleaned = _strip_jsonc_comments(
            '{"url": "https://example.invalid", // note\\n"x": 1}'
        )
        print(cleaned)
        # Output:
        # {"url": "https://example.invalid",
        # "x": 1}
    """
    output: list[str] = []
    in_string = False
    escape_next = False
    index = 0
    text_length = len(text)

    while index < text_length:
        character = text[index]

        if in_string:
            output.append(character)
            if escape_next:
                escape_next = False
            elif character == "\\":
                escape_next = True
            elif character == '"':
                in_string = False
            index += 1
            continue

        if character == '"':
            in_string = True
            output.append(character)
            index += 1
            continue

        if character == "/" and index + 1 < text_length:
            next_character = text[index + 1]
            if next_character == "/":
                index += 2
                while index < text_length and text[index] not in "\r\n":
                    index += 1
                continue
            if next_character == "*":
                index += 2
                while index + 1 < text_length and not (
                    text[index] == "*" and text[index + 1] == "/"
                ):
                    if text[index] in "\r\n":
                        output.append(text[index])
                    index += 1
                if index + 1 < text_length:
                    index += 2
                continue

        output.append(character)
        index += 1

    return "".join(output)


def _load_existing(path: str) -> dict[str, object]:
    """Load an existing devcontainer object while tolerating JSONC comments.

    Args:
        path: Path to the existing devcontainer configuration.

    Returns:
        Parsed top-level configuration object, or an empty object when the file
        is absent or empty.
    """
    if not os.path.isfile(path):
        return {}
    with open(path, "r", encoding="utf-8") as input_file:
        text = input_file.read()
    text = _strip_jsonc_comments(text)

    # Strip trailing commas before } or ] left behind by comment removal.
    text = re.sub(r",(\s*[}\]])", r"\1", text)
    text = text.strip()
    if not text:
        return {}

    try:
        data = json.loads(text)
    except json.JSONDecodeError as exc:
        print(
            f"update_devcontainer_json.py: cannot parse existing {path}: {exc}",
            file=sys.stderr,
        )
        sys.exit(1)

    if not isinstance(data, dict):
        print(
            f"update_devcontainer_json.py: existing {path} must contain "
            "a top-level JSON object.",
            file=sys.stderr,
        )
        sys.exit(1)

    return data


def main() -> int:
    """Render the configured devcontainer JSON document to standard output.

    Environment variables select CUDA, GPU-runtime, and ROS settings. Existing
    unmanaged configuration is preserved from ``DEVCONTAINER_JSON_PATH``.

    Returns:
        Zero on success and one when an existing managed value is malformed.

    Example:
        CUDA=off ROS_MODE=none DEVCONTAINER_JSON_PATH=/missing \
            python3 .devcontainer/update_devcontainer_json.py

    Output:
        A JSON object with the managed build, feature, and editor defaults.
    """
    # Options come from the configure script via environment variables.
    cuda = os.environ.get("CUDA", "off")
    cuda_version = os.environ.get("CUDA_VERSION", DEFAULT_CUDA_VERSION)
    gpu_runtime = os.environ.get(
        "DEVCONTAINER_GPU_RUNTIME", DEFAULT_GPU_RUNTIME
    )
    ros_mode = os.environ.get("ROS_MODE", "none")
    ros_distro = os.environ.get("ROS_DISTRO", "")
    ros_profile = os.environ.get("ROS_PROFILE", "ros-base")
    existing_path = os.environ.get(
        "DEVCONTAINER_JSON_PATH",
        os.path.join(
            os.path.dirname(os.path.abspath(__file__)),
            "devcontainer.json",
        ),
    )

    data = _load_existing(existing_path)

    data.setdefault("name", "C++")

    # Managed: build (dockerfile + ROS build args)
    build = data.get("build", {})
    if not isinstance(build, dict):
        build = {}
    build["dockerfile"] = "Dockerfile"
    if ros_mode != "none":
        build["args"] = {
            "ROS_MODE": ros_mode,
            "ROS_DISTRO": ros_distro,
            "ROS_PROFILE": ros_profile,
        }
    else:
        build.pop("args", None)
    data["build"] = build

    # Managed: features (conda + python always; nvidia-cuda when CUDA=on)
    features = data.get("features", {})
    if not isinstance(features, dict):
        features = {}
    features["ghcr.io/devcontainers/features/conda:1"] = {
        "addCondaForge": True,
        "version": "latest",
    }
    features["ghcr.io/devcontainers/features/python:1"] = {
        "installTools": True,
        "enableShared": True,
        "version": "3.12",
    }
    if cuda == "on":
        features[CUDA_FEATURE_KEY] = {
            "installCudnn": True,
            "installCudnnDev": True,
            "installNvtx": True,
            "installToolkit": True,
            "cudaVersion": cuda_version,
            "cudnnVersion": "automatic",
        }
    else:
        features.pop(CUDA_FEATURE_KEY, None)
    # Sorted for stable output regardless of option toggling history.
    data["features"] = dict(sorted(features.items()))

    # Managed: GPU passthrough runArg (CUDA only); other runArgs preserved.
    existing_run_args = data.get("runArgs", [])
    if not isinstance(existing_run_args, list) or not all(
        isinstance(argument, str) for argument in existing_run_args
    ):
        print(
            "update_devcontainer_json.py: existing runArgs must be a list "
            "of strings.",
            file=sys.stderr,
        )
        return 1

    run_args = _strip_gpu_run_args(existing_run_args)
    if cuda == "on":
        run_args = _gpu_run_args(gpu_runtime) + run_args
    if run_args:
        data["runArgs"] = run_args
    else:
        data.pop("runArgs", None)

    # Managed: CUDA entries in remoteEnv; unrelated entries preserved.
    remote_env = data.get("remoteEnv", {})
    if not isinstance(remote_env, dict):
        remote_env = {}
    if cuda == "on":
        remote_env.update(CUDA_REMOTE_ENV)
    else:
        for key in CUDA_REMOTE_ENV:
            remote_env.pop(key, None)
    if remote_env:
        data["remoteEnv"] = remote_env
    else:
        data.pop("remoteEnv", None)

    # Managed: ROS entries in containerEnv; unrelated entries preserved.
    container_env = data.get("containerEnv", {})
    if not isinstance(container_env, dict):
        container_env = {}
    if ros_mode != "none":
        container_env.update(ROS_CONTAINER_ENV)
    else:
        for key in ROS_CONTAINER_ENV:
            container_env.pop(key, None)
    if container_env:
        data["containerEnv"] = container_env
    else:
        data.pop("containerEnv", None)

    # Ensure template editor defaults are present while retaining project-owned
    # extensions and other customizations such as settings.
    customizations = data.get("customizations", {})
    if not isinstance(customizations, dict):
        customizations = {}
    vscode = customizations.get("vscode", {})
    if not isinstance(vscode, dict):
        vscode = {}
    existing_ext = vscode.get("extensions", [])
    if not isinstance(existing_ext, list):
        existing_ext = []
    extras = [e for e in existing_ext if e not in DEFAULT_EXTENSIONS]
    vscode["extensions"] = list(DEFAULT_EXTENSIONS) + extras
    customizations["vscode"] = vscode
    data["customizations"] = customizations

    json.dump(data, sys.stdout, indent=2)
    sys.stdout.write("\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
