"""Data models for deterministic frame-sequence playback."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class SequenceManifest:
    """Ordered list of frame paths and timestamps loaded from disk."""

    frame_paths: tuple[Path, ...]
    timestamp_ns: tuple[int, ...]
