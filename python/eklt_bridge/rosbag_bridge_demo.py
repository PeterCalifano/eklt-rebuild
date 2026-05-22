"""Run the default ROS1 rosbag example while exposing topics through ros1_bridge."""

from __future__ import annotations

import argparse
import os
from pathlib import Path
import shlex
import signal
import subprocess
import time


def _repo_default_bag() -> Path:
    return Path.cwd() / "data" / "eklt_example" / "boxes_6dof.bag"


def _bash_command(command: list[str], *, setup_files: list[str]) -> list[str]:
    parts = ["set -e"]
    for setup_file in setup_files:
        if setup_file:
            parts.append(f"source {shlex.quote(setup_file)}")
    parts.append(" ".join(shlex.quote(part) for part in command))
    return ["bash", "-lc", " && ".join(parts)]


def _start(name: str, command: list[str], *, setup_files: list[str], dry_run: bool) -> subprocess.Popen | None:
    full_command = _bash_command(command, setup_files=setup_files)
    print(f"[{name}] {' '.join(full_command)}")
    if dry_run:
        return None
    return subprocess.Popen(full_command, preexec_fn=os.setsid)


def _stop(processes: list[subprocess.Popen | None]) -> None:
    for process in reversed([proc for proc in processes if proc is not None]):
        if process.poll() is not None:
            continue
        os.killpg(os.getpgid(process.pid), signal.SIGTERM)
    for process in reversed([proc for proc in processes if proc is not None]):
        try:
            process.wait(timeout=5.0)
        except subprocess.TimeoutExpired:
            os.killpg(os.getpgid(process.pid), signal.SIGKILL)


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Run EKLT's default ROS1 rosbag example and expose topics through ros1_bridge."
    )
    parser.add_argument("--bag", default=str(_repo_default_bag()), help="ROS1 bag to play.")
    parser.add_argument("--tracks-file", default="/tmp/eklt_example/tracks.txt", help="Track output file.")
    parser.add_argument("--v", default="1", help="EKLT glog verbosity passed to roslaunch.")
    parser.add_argument("--ros1-setup", default="/opt/ros/noetic/setup.bash", help="ROS1 setup.bash.")
    parser.add_argument("--ros2-setup", default="/opt/ros/foxy/setup.bash", help="ROS2 setup.bash.")
    parser.add_argument("--startup-delay", type=float, default=2.0, help="Delay between long-running processes.")
    parser.add_argument("--dry-run", action="store_true", help="Print commands without launching them.")
    args = parser.parse_args()

    bag_path = Path(args.bag).expanduser().resolve()
    if not bag_path.exists():
        raise FileNotFoundError(f"ROS bag not found: {bag_path}")

    processes: list[subprocess.Popen | None] = []
    try:
        processes.append(_start("roscore", ["roscore"], setup_files=[args.ros1_setup], dry_run=args.dry_run))
        time.sleep(args.startup_delay)

        processes.append(
            _start(
                "ros1_bridge",
                ["ros2", "run", "ros1_bridge", "dynamic_bridge", "--bridge-all-topics"],
                setup_files=[args.ros1_setup, args.ros2_setup],
                dry_run=args.dry_run,
            )
        )
        time.sleep(args.startup_delay)

        processes.append(
            _start(
                "eklt",
                [
                    "roslaunch",
                    "eklt",
                    "eklt.launch",
                    f"tracks_file_txt:={args.tracks_file}",
                    f"v:={args.v}",
                ],
                setup_files=[args.ros1_setup],
                dry_run=args.dry_run,
            )
        )
        time.sleep(args.startup_delay)

        bag_process = _start(
            "rosbag",
            ["rosbag", "play", str(bag_path)],
            setup_files=[args.ros1_setup],
            dry_run=args.dry_run,
        )
        if bag_process is not None:
            bag_process.wait()
    finally:
        _stop(processes)

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
