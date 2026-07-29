"""Verify deterministic command generation for the ROS bag bridge demo."""

from __future__ import annotations

from pathlib import Path
import signal

import pytest

from eklt_bridge import rosbag_bridge_demo


class _FakeProcess:
    """Minimal managed-process fixture for shutdown-order verification."""

    def __init__(self, pid: int) -> None:
        """Create one process that remains live until ``wait``."""
        self.pid = pid
        self.args = ["fake-process", str(pid)]
        self.wait_timeouts: list[float | None] = []

    def poll(self) -> None:
        """Report that the process remains active."""
        return None

    def wait(self, timeout: float | None = None) -> int:
        """Record the bounded wait and report successful termination."""
        self.wait_timeouts.append(timeout)
        return 0


def _create_required_file(path: Path) -> Path:
    """Create one empty fixture file and return its path."""
    path.parent.mkdir(parents=True, exist_ok=True)
    path.touch()
    return path


def _dry_run_arguments(tmp_path: Path, *,
                       mode: str) -> list[str]:
    """Create complete dry-run arguments for one tracking mode."""
    bag_path = _create_required_file(tmp_path / "boxes_6dof.bag")
    ros1_setup = _create_required_file(
        tmp_path / "catkin_ws" / "devel" / "setup.bash"
    )
    ros2_setup = _create_required_file(
        tmp_path / "jazzy" / "setup.bash"
    )
    return [
        "--bag", str(bag_path),
        "--tracks-file", str(tmp_path / "tracks.txt"),
        "--mode", mode,
        "--ros1-setup", str(ros1_setup),
        "--ros2-setup", str(ros2_setup),
        "--dry-run",
    ]


@pytest.mark.parametrize(
    ("mode", "event_only", "bootstrap"),
    [
        ("frame-backed", "false", "klt"),
        ("event-only", "true", "events"),
    ],
)
def test_dry_run_selects_explicit_eklt_mode(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
    monkeypatch: pytest.MonkeyPatch,
    mode: str,
    event_only: str,
    bootstrap: str,
) -> None:
    """Require the renamed package and mode-specific launch arguments."""
    def fail_to_start(*args: object, **kwargs: object) -> None:
        """Reject subprocess or sleep activity during a dry run."""
        raise AssertionError(f"unexpected dry-run activity: {args}, {kwargs}")

    monkeypatch.setattr(rosbag_bridge_demo.subprocess, "Popen", fail_to_start)
    monkeypatch.setattr(rosbag_bridge_demo.time, "sleep", fail_to_start)

    result = rosbag_bridge_demo.main(
        _dry_run_arguments(tmp_path, mode=mode)
    )
    output = capsys.readouterr().out

    assert result == 0
    assert output.count("\n") == 4
    assert "roslaunch eklt_rebuild eklt.launch" in output
    assert f"event_only_mode:={event_only}" in output
    assert f"bootstrap:={bootstrap}" in output
    assert "roslaunch eklt eklt.launch" not in output

    bridge_command = next(
        line for line in output.splitlines()
        if line.startswith("[ros1_bridge]")
    )
    assert bridge_command.index("catkin_ws") < bridge_command.index("jazzy")


def test_default_ros1_setup_follows_catkin_workspace(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Resolve the catkin setup and preserve the Jazzy/mode defaults."""
    workspace = tmp_path / "custom_catkin"
    monkeypatch.setenv("EKLT_CATKIN_WS", str(workspace))

    assert (
        rosbag_bridge_demo._default_ros1_setup()
        == workspace / "devel" / "setup.bash"
    )
    arguments = rosbag_bridge_demo._build_parser().parse_args([])
    assert arguments.ros1_setup == str(
        workspace / "devel" / "setup.bash"
    )
    assert arguments.ros2_setup == "/opt/ros/jazzy/setup.bash"
    assert arguments.mode == "frame-backed"


def test_dry_run_rejects_missing_catkin_overlay(tmp_path: Path) -> None:
    """Reject invalid setup paths before printing or starting processes."""
    bag_path = _create_required_file(tmp_path / "boxes_6dof.bag")
    ros2_setup = _create_required_file(tmp_path / "jazzy" / "setup.bash")

    with pytest.raises(FileNotFoundError, match="ROS1 catkin setup not found"):
        rosbag_bridge_demo.main(
            [
                "--bag", str(bag_path),
                "--ros1-setup", str(tmp_path / "missing" / "setup.bash"),
                "--ros2-setup", str(ros2_setup),
                "--dry-run",
            ]
        )


def test_stop_terminates_only_owned_groups_in_reverse_order(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Request bounded cooperative shutdown in reverse startup order."""
    first_process = _FakeProcess(101)
    second_process = _FakeProcess(202)
    requested_signals: list[tuple[int, int]] = []

    def process_group_id(process_id: int) -> int:
        """Map each fake process to its isolated process group."""
        return process_id

    def record_signal(group_id: int, requested_signal: int) -> None:
        """Record one process-group signal without affecting the host."""
        requested_signals.append((group_id, requested_signal))

    monkeypatch.setattr(
        rosbag_bridge_demo.os,
        "getpgid",
        process_group_id,
    )
    monkeypatch.setattr(
        rosbag_bridge_demo.os,
        "killpg",
        record_signal,
    )

    rosbag_bridge_demo._stop([first_process, second_process])

    assert requested_signals == [
        (202, signal.SIGTERM),
        (101, signal.SIGTERM),
    ]
    assert second_process.wait_timeouts == [5.0]
    assert first_process.wait_timeouts == [5.0]
