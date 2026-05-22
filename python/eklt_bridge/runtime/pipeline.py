"""Source replay pipeline shared by bridge wrappers."""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np

from ..config import Stage2AConfig
from ..primitives import EventStream, FrameEventSource, FrameSample
from ..sources import build_frame_event_source
from ..visualization import render_event_preview_mono8


@dataclass(frozen=True)
class BridgeStep:
    """One replay step containing optional frame, events, and preview image."""

    frame: FrameSample | None
    events: EventStream | None
    event_preview_mono8: np.ndarray | None


class BridgePipeline:
    """Build replay steps from any configured frame/event source adapter."""

    def __init__(self, config: Stage2AConfig, source: FrameEventSource | None = None) -> None:
        self._source = build_frame_event_source(config) if source is None else source

    def build_steps(self) -> list[BridgeStep]:
        """Create replay steps with generated event previews."""

        steps: list[BridgeStep] = []
        for step in self._source.build_steps():
            preview = None
            if step.events is not None:
                preview = render_event_preview_mono8(step.events)
            steps.append(
                BridgeStep(
                    frame=step.frame,
                    events=step.events,
                    event_preview_mono8=preview,
                )
            )
        return steps
