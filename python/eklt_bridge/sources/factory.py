"""Factory for source adapters selected by bridge config."""

from __future__ import annotations

from ..config import Stage2AConfig
from ..primitives import FrameEventSource
from .frame_sequence import FrameSequenceSource
from .v2e_sequence import V2EFrameSequenceSource


def build_frame_event_source(config: Stage2AConfig) -> FrameEventSource:
    """Build the configured frame/event source adapter."""

    if config.sequence is None:
        raise ValueError("Bridge source requires a 'sequence' section for the configured source kind.")

    if config.source.kind == "frames_only":
        return FrameSequenceSource(config.sequence)

    if config.source.kind == "v2e_sequence":
        return V2EFrameSequenceSource(config.sequence, config.v2e)

    raise ValueError(f"Unsupported bridge source kind '{config.source.kind}'.")
