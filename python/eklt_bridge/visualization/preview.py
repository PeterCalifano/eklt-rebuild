"""Preview renderers for bridge event batches."""

from __future__ import annotations

import numpy as np

from ..primitives import EventStream


def render_event_preview_mono8(stream: EventStream, *, scale: int = 24) -> np.ndarray:
    """Render signed event-count preview into mono8 image."""

    stream.validate()
    signed_counts = np.zeros((stream.height, stream.width), dtype=np.int16)
    increments = np.where(stream.p01 > 0, 1, -1).astype(np.int16)
    np.add.at(signed_counts, (stream.y, stream.x), increments)

    preview = 127 + np.clip(signed_counts * int(scale), -127, 128)
    return preview.astype(np.uint8)
