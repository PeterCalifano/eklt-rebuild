"""Configuration models for the stage-2 bridge package."""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path


@dataclass(frozen=True)
class TopicNames:
    """ROS topic names used by the stage-2 bridge."""

    events: str = "/eklt/events"
    image: str = "/eklt/image_raw"
    rendered_frame: str = "/eklt/rendered_frame"
    event_preview: str = "/eklt/event_preview"
    feature_tracks: str = "/feature_tracks"
    ros1_events: str = "/dvs/events"
    ros1_image: str = "/dvs/image_raw"


@dataclass(frozen=True)
class SourceSettings:
    """Source adapter selected for the ROS2 publisher."""

    kind: str = "v2e_sequence"


@dataclass(frozen=True)
class V2EEmulatorSettings:
    """v2e settings passed through to the external EventEmulator."""

    pos_thres: float = 0.2
    neg_thres: float = 0.2
    sigma_thres: float = 0.03
    cutoff_hz: float = 0.0
    leak_rate_hz: float = 0.1
    refractory_period_s: float = 0.0
    shot_noise_rate_hz: float = 0.0
    photoreceptor_noise: bool = False
    leak_jitter_fraction: float = 0.1
    noise_rate_cov_decades: float = 0.1
    seed: int = 0
    device: str = "cpu"


@dataclass(frozen=True)
class FrameSettings:
    """Frame-shape and normalization settings for grayscale bridge output."""

    width: int = 640
    height: int = 480
    normalize_min: float = 0.0
    normalize_max: float = 1.0


@dataclass(frozen=True)
class SequenceSettings:
    """Settings used to load a deterministic image sequence from disk."""

    frames_dir: Path
    glob: str = "*.png"
    fps: float = 30.0
    timestamps_path: Path | None = None
    start_time_ns: int = 0
    max_frames: int | None = None


@dataclass(frozen=True)
class RuntimeSettings:
    """Runtime playback controls shared by the ROS1 and ROS2 wrappers."""

    realtime_factor: float = 1.0
    publish_first_frame: bool = True
    loop_forever: bool = False


@dataclass(frozen=True)
class Stage2AConfig:
    """Top-level config for the reusable stage-2 bridge package."""

    conda_prefix: Path | None = None
    topics: TopicNames = field(default_factory=TopicNames)
    frame: FrameSettings = field(default_factory=FrameSettings)
    source: SourceSettings = field(default_factory=SourceSettings)
    v2e: V2EEmulatorSettings = field(default_factory=V2EEmulatorSettings)
    runtime: RuntimeSettings = field(default_factory=RuntimeSettings)
    sequence: SequenceSettings | None = None
