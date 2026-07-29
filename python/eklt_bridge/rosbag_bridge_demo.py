"""Run a ROS1 EKLT rosbag example while exposing topics through ``ros1_bridge``.

The runner owns process startup and shutdown for one bounded bag replay. It
sources the configured catkin overlay for every ROS1 process and keeps the
frame-backed and event-only initialization paths explicitly selectable.

Example:
    eklt-run-rosbag-bridge-demo \
        --bag data/eklt_example/boxes_6dof.bag \
        --ros1-setup "$HOME/eklt_catkin_ws/devel/setup.bash" \
        --mode event-only \
        --dry-run

Output:
    [eklt_rebuild] bash -lc '... roslaunch eklt_rebuild eklt.launch ...'
"""

from __future__ import annotations

import argparse
from collections.abc import Sequence
from enum import Enum
import math
import os
from pathlib import Path
import shlex
import signal
import subprocess
import time


class _TrackingMode(str, Enum):
    """Supported ROS1 EKLT initialization paths."""

    FRAME_BACKED = "frame-backed"
    EVENT_ONLY = "event-only"


def _repo_default_bag() -> Path:
    """Return the example-bag path expected from the repository root."""
    return Path.cwd() / "data" / "eklt_example" / "boxes_6dof.bag"


def _default_ros1_setup() -> Path:
    """Return the configured catkin workspace setup path."""
    workspace_value = os.environ.get("EKLT_CATKIN_WS")
    workspace = (
        Path(workspace_value).expanduser()
        if workspace_value
        else Path.home() / "eklt_catkin_ws"
    )
    return workspace / "devel" / "setup.bash"


def _require_file(path_value: str, description: str) -> Path:
    """Resolve a required file or raise a contextual error.

    Args:
        path_value: User-provided path.
        description: Reader-facing name used in diagnostics.

    Returns:
        Absolute path to the existing regular file.

    Raises:
        FileNotFoundError: If the resolved path is not a regular file.
    """
    path = Path(path_value).expanduser().resolve()
    if not path.is_file():
        raise FileNotFoundError(f"{description} not found: {path}")
    return path


def _bash_command(command: Sequence[str], *,
                  setup_files: Sequence[Path]) -> list[str]:
    """Build one shell command with ordered ROS environment overlays.

    Args:
        command: Executable and arguments to run.
        setup_files: Setup scripts sourced in underlay-to-overlay order.

    Returns:
        ``bash -lc`` command suitable for ``subprocess.Popen``.
    """
    command_parts = ["set -e"]
    command_parts.extend(
        f"source {shlex.quote(str(setup_file))}"
        for setup_file in setup_files
    )
    command_parts.append(shlex.join(command))
    return ["bash", "-lc", " && ".join(command_parts)]


def _start(name: str,
           command: Sequence[str], *,
           setup_files: Sequence[Path],
           dry_run: bool) -> subprocess.Popen[bytes] | None:
    """Print and optionally start one independently managed process group.

    Args:
        name: Short process label used in console output.
        command: Executable and arguments to start.
        setup_files: Ordered ROS setup scripts for the subprocess.
        dry_run: When true, print the command without executing it.

    Returns:
        Started process, or ``None`` for a dry run.
    """
    full_command = _bash_command(command, setup_files=setup_files)
    print(f"[{name}] {shlex.join(full_command)}")
    if dry_run:
        return None

    return subprocess.Popen(full_command, start_new_session=True)


def _verify_started(process: subprocess.Popen[bytes] | None, *,
                    name: str,
                    startup_delay_s: float) -> None:
    """Wait for startup and reject an already terminated service.

    Args:
        process: Started service, or ``None`` during a dry run.
        name: Service name used in diagnostics.
        startup_delay_s: Seconds allowed for initial startup.

    Raises:
        RuntimeError: If the service terminates during its startup window.
    """
    if process is None:
        return

    time.sleep(startup_delay_s)
    return_code = process.poll()
    if return_code is not None:
        raise RuntimeError(
            f"{name} exited during startup with status {return_code}"
        )


def _stop(processes: Sequence[subprocess.Popen[bytes] | None]) -> None:
    """Terminate child process groups in reverse startup order.

    Args:
        processes: Processes owned by this invocation.
    """
    active_processes = [
        process for process in reversed(processes)
        if process is not None
    ]

    # Request cooperative shutdown first so ROS nodes can flush their outputs.
    for process in active_processes:
        if process.poll() is not None:
            continue
        try:
            os.killpg(os.getpgid(process.pid), signal.SIGTERM)
        except ProcessLookupError:
            continue

    # Escalate only process groups that outlive the bounded grace period.
    for process in active_processes:
        try:
            process.wait(timeout=5.0)
        except subprocess.TimeoutExpired:
            try:
                os.killpg(os.getpgid(process.pid), signal.SIGKILL)
            except ProcessLookupError:
                pass
            process.wait()


def _eklt_command(mode: _TrackingMode, *,
                  tracks_file: Path,
                  verbosity: str) -> list[str]:
    """Build the ROS1 launch command for one explicit initialization mode.

    Args:
        mode: Frame-backed or event-only initialization mode.
        tracks_file: Output path for EKLT track rows.
        verbosity: glog verbosity forwarded through the launch file.

    Returns:
        Complete ``roslaunch`` argument vector.
    """
    event_only = mode is _TrackingMode.EVENT_ONLY
    return [
        "roslaunch",
        "eklt_rebuild",
        "eklt.launch",
        f"tracks_file_txt:={tracks_file}",
        f"v:={verbosity}",
        f"event_only_mode:={'true' if event_only else 'false'}",
        f"bootstrap:={'events' if event_only else 'klt'}",
    ]


def _build_parser() -> argparse.ArgumentParser:
    """Create the command-line parser for the bridge demo."""
    parser = argparse.ArgumentParser(
        description=(
            "Run EKLT on a ROS1 bag and expose its topics through ros1_bridge."
        )
    )
    parser.add_argument(
        "--bag",
        default=str(_repo_default_bag()),
        help="ROS1 bag to play.",
    )
    parser.add_argument(
        "--tracks-file",
        default="/tmp/eklt_example/tracks.txt",
        help="Track output file.",
    )
    parser.add_argument(
        "--mode",
        choices=[mode.value for mode in _TrackingMode],
        default=_TrackingMode.FRAME_BACKED.value,
        help="EKLT initialization path. Defaults to frame-backed.",
    )
    parser.add_argument(
        "--v",
        default="1",
        help="EKLT glog verbosity passed to roslaunch.",
    )
    parser.add_argument(
        "--ros1-setup",
        default=str(_default_ros1_setup()),
        help=(
            "Catkin overlay setup.bash. Defaults to EKLT_CATKIN_WS or "
            "~/eklt_catkin_ws."
        ),
    )
    parser.add_argument(
        "--ros2-setup",
        default="/opt/ros/jazzy/setup.bash",
        help="ROS2 setup.bash. Defaults to the Jazzy installation.",
    )
    parser.add_argument(
        "--startup-delay",
        type=float,
        default=2.0,
        help="Seconds allowed for each long-running process to start.",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Validate inputs and print commands without launching them.",
    )
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    """Run one bounded ROS bag bridge demonstration.

    Args:
        argv: Optional command-line arguments without the executable name.

    Returns:
        Zero after successful playback or dry-run command generation.

    Raises:
        FileNotFoundError: If the bag or a configured setup file is missing.
        ValueError: If the startup delay is not finite and non-negative.
        RuntimeError: If a managed service terminates during startup.
        subprocess.CalledProcessError: If rosbag playback fails.

    Example:
        result = main([
            "--bag", "data/eklt_example/boxes_6dof.bag",
            "--ros1-setup", "/tmp/eklt_catkin_ws/devel/setup.bash",
            "--dry-run",
        ])
        print(result)

    Output:
        0
    """
    args = _build_parser().parse_args(argv)
    if not math.isfinite(args.startup_delay) or args.startup_delay < 0.0:
        raise ValueError("--startup-delay must be finite and non-negative")

    # Resolve every external input before starting any long-running process so
    # configuration failures cannot leave a partial ROS process graph.
    bag_path = _require_file(args.bag, "ROS bag")
    ros1_setup = _require_file(args.ros1_setup, "ROS1 catkin setup")
    ros2_setup = _require_file(args.ros2_setup, "ROS2 setup")
    tracks_file = Path(args.tracks_file).expanduser().resolve()
    if not args.dry_run:
        tracks_file.parent.mkdir(parents=True, exist_ok=True)

    mode = _TrackingMode(args.mode)
    processes: list[subprocess.Popen[bytes] | None] = []

    try:
        # Start the ROS master before bridge or application processes attempt
        # registration.
        roscore_process = _start(
            "roscore",
            ["roscore"],
            setup_files=[ros1_setup],
            dry_run=args.dry_run,
        )
        processes.append(roscore_process)
        _verify_started(
            roscore_process,
            name="roscore",
            startup_delay_s=args.startup_delay,
        )

        # The dynamic bridge needs both environments, with the ROS2 overlay
        # sourced after the ROS1 catkin workspace.
        bridge_process = _start(
            "ros1_bridge",
            ["ros2", "run", "ros1_bridge", "dynamic_bridge",
             "--bridge-all-topics"],
            setup_files=[ros1_setup, ros2_setup],
            dry_run=args.dry_run,
        )
        processes.append(bridge_process)
        _verify_started(
            bridge_process,
            name="ros1_bridge",
            startup_delay_s=args.startup_delay,
        )

        # Launch exactly one explicit EKLT initialization path from the built
        # catkin overlay.
        eklt_process = _start(
            "eklt_rebuild",
            _eklt_command(
                mode,
                tracks_file=tracks_file,
                verbosity=args.v,
            ),
            setup_files=[ros1_setup],
            dry_run=args.dry_run,
        )
        processes.append(eklt_process)
        _verify_started(
            eklt_process,
            name="eklt_rebuild",
            startup_delay_s=args.startup_delay,
        )

        # Start playback only after every consumer survives its startup window.
        bag_process = _start(
            "rosbag",
            ["rosbag", "play", str(bag_path)],
            setup_files=[ros1_setup],
            dry_run=args.dry_run,
        )
        processes.append(bag_process)
        if bag_process is not None:
            return_code = bag_process.wait()
            if return_code != 0:
                raise subprocess.CalledProcessError(
                    return_code,
                    bag_process.args,
                )
    finally:
        _stop(processes)

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
