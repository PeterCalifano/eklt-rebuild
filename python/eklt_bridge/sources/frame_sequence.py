"""Frame-only sequence source adapter."""

from __future__ import annotations

from ..config import SequenceSettings
from ..primitives import FrameEventStep, FrameSample
from ..sequence import iter_frame_samples


class FrameSequenceSource:
    """Replay frames from disk without generating events."""

    def __init__(self, sequence: SequenceSettings) -> None:
        self._samples = iter_frame_samples(sequence)

    @property
    def samples(self) -> list[FrameSample]:
        """Loaded frame samples."""

        return self._samples

    def build_steps(self) -> list[FrameEventStep]:
        """Return one frame-only step per sequence image."""

        return [FrameEventStep(frame=sample, events=None) for sample in self._samples]
