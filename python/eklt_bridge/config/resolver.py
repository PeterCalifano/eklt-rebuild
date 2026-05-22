"""Config loading helpers for stage 2A."""

from __future__ import annotations

import json
from pathlib import Path

from .models import (
    FrameSettings,
    RuntimeSettings,
    SequenceSettings,
    SourceSettings,
    Stage2AConfig,
    TopicNames,
    V2EEmulatorSettings,
)


def _resolve_path(path_value: str | None, *, base_dir: Path) -> Path | None:
    if path_value is None:
        return None

    path = Path(path_value)
    if not path.is_absolute():
        path = (base_dir / path).resolve()
    return path


def load_stage2a_config(config_path: Path | str) -> Stage2AConfig:
    """Load the stage-2A config from a JSON file."""

    resolved_path = Path(config_path).resolve()
    payload = json.loads(resolved_path.read_text(encoding="utf-8"))
    base_dir = resolved_path.parent

    topics_payload = payload.get("topics", {})
    frame_payload = payload.get("frame", {})
    source_payload = payload.get("source", {})
    v2e_payload = payload.get("v2e", {})
    sequence_payload = payload.get("sequence")

    sequence = None
    if sequence_payload is not None:
        sequence = SequenceSettings(
            frames_dir=_resolve_path(
                sequence_payload["frames_dir"], base_dir=base_dir),
            glob=str(sequence_payload.get("glob", "*.png")),
            fps=float(sequence_payload.get("fps", 30.0)),
            timestamps_path=_resolve_path(sequence_payload.get(
                "timestamps_path"), base_dir=base_dir),
            start_time_ns=int(sequence_payload.get("start_time_ns", 0)),
            max_frames=(
                int(sequence_payload["max_frames"])
                if sequence_payload.get("max_frames") is not None
                else None
            ),
        )

    return Stage2AConfig(
        conda_prefix=_resolve_path(payload.get(
            "conda_prefix"), base_dir=base_dir),
        topics=TopicNames(
            events=str(topics_payload.get("events", "/eklt/events")),
            image=str(topics_payload.get("image", "/eklt/image_raw")),
            rendered_frame=str(topics_payload.get(
                "rendered_frame", "/eklt/rendered_frame")),
            event_preview=str(topics_payload.get(
                "event_preview", "/eklt/event_preview")),
            feature_tracks=str(topics_payload.get(
                "feature_tracks", "/feature_tracks")),
            ros1_events=str(topics_payload.get("ros1_events", "/dvs/events")),
            ros1_image=str(topics_payload.get("ros1_image", "/dvs/image_raw")),
        ),
        frame=FrameSettings(
            width=int(frame_payload.get("width", 640)),
            height=int(frame_payload.get("height", 480)),
            normalize_min=float(frame_payload.get("normalize_min", 0.0)),
            normalize_max=float(frame_payload.get("normalize_max", 1.0)),
        ),
        source=SourceSettings(
            kind=str(source_payload.get("kind", "v2e_sequence")),
        ),
        v2e=V2EEmulatorSettings(
            pos_thres=float(v2e_payload.get("pos_thres", 0.2)),
            neg_thres=float(v2e_payload.get("neg_thres", 0.2)),
            sigma_thres=float(v2e_payload.get("sigma_thres", 0.03)),
            cutoff_hz=float(v2e_payload.get("cutoff_hz", 0.0)),
            leak_rate_hz=float(v2e_payload.get("leak_rate_hz", 0.1)),
            refractory_period_s=float(v2e_payload.get("refractory_period_s", 0.0)),
            shot_noise_rate_hz=float(v2e_payload.get("shot_noise_rate_hz", 0.0)),
            photoreceptor_noise=bool(v2e_payload.get("photoreceptor_noise", False)),
            leak_jitter_fraction=float(v2e_payload.get("leak_jitter_fraction", 0.1)),
            noise_rate_cov_decades=float(v2e_payload.get("noise_rate_cov_decades", 0.1)),
            seed=int(v2e_payload.get("seed", 0)),
            device=str(v2e_payload.get("device", "cpu")),
        ),
        runtime=RuntimeSettings(
            realtime_factor=float(payload.get(
                "runtime", {}).get("realtime_factor", 1.0)),
            publish_first_frame=bool(payload.get(
                "runtime", {}).get("publish_first_frame", True)),
            loop_forever=bool(payload.get(
                "runtime", {}).get("loop_forever", False)),
        ),
        sequence=sequence,
    )
