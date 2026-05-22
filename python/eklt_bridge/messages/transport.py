"""Transport helpers for carrying event streams over standard ROS messages."""

from __future__ import annotations

import io
import json
from typing import Any

import numpy as np

from ..primitives import EventStream

_TRANSPORT_MAGIC = b"EEVS1\0"


def _json_default(value: Any) -> Any:
    if isinstance(value, np.integer):
        return int(value)
    if isinstance(value, np.floating):
        return float(value)
    if isinstance(value, np.ndarray):
        return value.tolist()
    raise TypeError(f"Object of type {type(value).__name__} is not JSON serializable")


def encode_event_batch(stream: EventStream) -> bytes:
    """Serialize event stream into ROS-bridge-safe byte blob."""

    stream.validate()
    metadata_json = json.dumps(stream.metadata, sort_keys=True, separators=(",", ":"), default=_json_default)
    buffer = io.BytesIO()
    np.savez_compressed(
        buffer,
        t_s=stream.t_s,
        x=stream.x,
        y=stream.y,
        p01=stream.p01,
        width=np.array([int(stream.width)], dtype=np.int32),
        height=np.array([int(stream.height)], dtype=np.int32),
        metadata_json=np.array([metadata_json]),
    )
    return _TRANSPORT_MAGIC + buffer.getvalue()


def decode_event_batch(payload: bytes | bytearray | memoryview) -> EventStream:
    """Deserialize bridge transport blob into event stream."""

    buffer = bytes(payload)
    if not buffer.startswith(_TRANSPORT_MAGIC):
        raise ValueError("Transport payload has an invalid event-stream magic value.")

    with np.load(io.BytesIO(buffer[len(_TRANSPORT_MAGIC) :])) as decoded:
        stream = EventStream(
            t_s=decoded["t_s"],
            x=decoded["x"],
            y=decoded["y"],
            p01=decoded["p01"],
            width=int(decoded["width"][0]),
            height=int(decoded["height"][0]),
            metadata=json.loads(str(decoded["metadata_json"][0])),
        )

    stream.validate()
    return stream
