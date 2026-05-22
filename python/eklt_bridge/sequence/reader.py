"""Utilities for reading deterministic grayscale frame sequences from disk."""

from __future__ import annotations

from pathlib import Path

import numpy as np
from PIL import Image

from ..config import SequenceSettings
from ..primitives import FrameSample
from .models import SequenceManifest


def _load_timestamp_file(timestamps_path: Path) -> tuple[int, ...]:
    raw_lines = timestamps_path.read_text(encoding="utf-8").splitlines()
    values: list[int] = []
    for raw_line in raw_lines:
        line = raw_line.strip()
        if not line or line.startswith("#"):
            continue
        values.append(int(float(line) * 1.0e9))
    return tuple(values)


def load_sequence_manifest(settings: SequenceSettings) -> SequenceManifest:
    """Resolve the sequence file order and timestamps from the provided settings."""

    frames_dir = settings.frames_dir.resolve()
    frame_paths = tuple(sorted(frames_dir.glob(settings.glob)))
    if not frame_paths:
        raise ValueError(f"No frames matched '{settings.glob}' under '{frames_dir}'.")

    if settings.max_frames is not None:
        frame_paths = frame_paths[: settings.max_frames]

    if settings.timestamps_path is not None:
        timestamp_ns = _load_timestamp_file(settings.timestamps_path.resolve())
        if len(timestamp_ns) != len(frame_paths):
            raise ValueError("The timestamps file must contain exactly one timestamp per frame.")
        return SequenceManifest(frame_paths=frame_paths, timestamp_ns=timestamp_ns)

    if settings.fps <= 0.0:
        raise ValueError("Sequence fps must be positive when no timestamps file is provided.")

    frame_period_ns = int(round(1.0e9 / settings.fps))
    timestamp_ns = tuple(settings.start_time_ns + index * frame_period_ns for index in range(len(frame_paths)))
    return SequenceManifest(frame_paths=frame_paths, timestamp_ns=timestamp_ns)


def _load_image_mono8(path: Path) -> np.ndarray:
    with Image.open(path) as image:
        grayscale = image.convert("L")
        return np.asarray(grayscale, dtype=np.uint8)


def iter_frame_samples(settings: SequenceSettings) -> list[FrameSample]:
    """Load the configured frame sequence into deterministic grayscale samples."""

    manifest = load_sequence_manifest(settings)
    samples: list[FrameSample] = []
    for index, (path, timestamp_ns) in enumerate(zip(manifest.frame_paths, manifest.timestamp_ns)):
        samples.append(
            FrameSample(
                index=index,
                path=path,
                timestamp_ns=int(timestamp_ns),
                image_mono8=_load_image_mono8(path),
            )
        )
    return samples
