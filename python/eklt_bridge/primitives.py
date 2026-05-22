"""Local primitive contracts for EKLT bridge frame and event streams."""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Protocol

import numpy as np


@dataclass
class EventStream:
    """eventDataGenLibPy-compatible polarity event stream."""

    t_s: np.ndarray
    x: np.ndarray
    y: np.ndarray
    p01: np.ndarray
    signal_noise: np.ndarray | None = None
    width: int | None = None
    height: int | None = None
    source_format: str | None = None
    metadata: dict[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        self.validate()

    def validate(self) -> None:
        """Coerce dtypes and validate event-stream invariants."""

        self.t_s = np.asarray(self.t_s, dtype=np.float64)
        self.x = np.asarray(self.x, dtype=np.int32)
        self.y = np.asarray(self.y, dtype=np.int32)
        self.p01 = np.asarray(self.p01, dtype=np.uint8)
        self.metadata = dict(self.metadata)

        n_events = self.t_s.shape[0]
        if self.x.shape[0] != n_events or self.y.shape[0] != n_events or self.p01.shape[0] != n_events:
            raise ValueError("Event arrays must have the same length")

        if not np.isfinite(self.t_s).all():
            raise ValueError("t_s contains non-finite values")

        if np.any((self.p01 != 0) & (self.p01 != 1)):
            raise ValueError("p01 must only contain values 0 or 1")

        if self.signal_noise is not None:
            self.signal_noise = np.asarray(self.signal_noise, dtype=np.uint8)
            if self.signal_noise.shape[0] != n_events:
                raise ValueError("signal_noise must have the same length as t_s")
            if np.any((self.signal_noise != 0) & (self.signal_noise != 1)):
                raise ValueError("signal_noise must only contain values 0 or 1")

        if self.width is not None:
            self.width = int(self.width)
            if self.width <= 0:
                raise ValueError("width must be positive")
            if np.any(self.x < 0) or np.any(self.x >= self.width):
                raise ValueError("x coordinates are out of bounds")

        if self.height is not None:
            self.height = int(self.height)
            if self.height <= 0:
                raise ValueError("height must be positive")
            if np.any(self.y < 0) or np.any(self.y >= self.height):
                raise ValueError("y coordinates are out of bounds")

    @property
    def timestamp_ns(self) -> np.ndarray:
        """Event timestamps in integer nanoseconds for ROS adapters."""

        return np.rint(self.t_s.astype(np.float64) * 1.0e9).astype(np.int64)

    @property
    def stamp_ns(self) -> int:
        """Header timestamp in nanoseconds, or last event timestamp."""

        if "header_timestamp_ns" in self.metadata:
            return int(self.metadata["header_timestamp_ns"])
        if self.t_s.shape[0] == 0:
            return 0
        return int(self.timestamp_ns[-1])

    @classmethod
    def from_timestamp_ns(
        cls,
        timestamp_ns: np.ndarray,
        *,
        x: np.ndarray,
        y: np.ndarray,
        p01: np.ndarray,
        width: int,
        height: int,
        header_timestamp_ns: int | None = None,
        signal_noise: np.ndarray | None = None,
        source_format: str | None = None,
        metadata: dict[str, Any] | None = None,
    ) -> "EventStream":
        """Build stream from bridge/ROS nanosecond timestamps."""

        stream_metadata = dict(metadata or {})
        if header_timestamp_ns is not None:
            stream_metadata["header_timestamp_ns"] = int(header_timestamp_ns)
        return cls(
            t_s=np.asarray(timestamp_ns, dtype=np.int64).astype(np.float64) / 1.0e9,
            x=x,
            y=y,
            p01=p01,
            signal_noise=signal_noise,
            width=int(width),
            height=int(height),
            source_format=source_format,
            metadata=stream_metadata,
        )

    @classmethod
    def from_v2e_events(
        cls,
        events_t_x_y_p: np.ndarray | None,
        *,
        width: int,
        height: int,
        header_timestamp_ns: int,
    ) -> "EventStream":
        """Build stream from v2e ``[t_s, x, y, polarity]`` event matrix."""

        if events_t_x_y_p is None or len(events_t_x_y_p) == 0:
            return cls.empty(width=width, height=height, header_timestamp_ns=header_timestamp_ns, source_format="v2e")

        events = np.asarray(events_t_x_y_p)
        if events.ndim != 2 or events.shape[1] < 4:
            raise ValueError("v2e events must have shape (N, 4)")

        return cls(
            t_s=events[:, 0],
            x=events[:, 1],
            y=events[:, 2],
            p01=(events[:, 3].astype(np.float64) > 0.0).astype(np.uint8),
            width=int(width),
            height=int(height),
            source_format="v2e",
            metadata={"header_timestamp_ns": int(header_timestamp_ns)},
        )

    @classmethod
    def from_event_stream(cls, stream: object, *, header_timestamp_ns: int | None = None) -> "EventStream":
        """Build local stream from eventDataGenLibPy-style duck-typed object."""

        metadata = dict(getattr(stream, "metadata", {}) or {})
        if header_timestamp_ns is not None:
            metadata["header_timestamp_ns"] = int(header_timestamp_ns)
        return cls(
            t_s=np.asarray(stream.t_s, dtype=np.float64),
            x=np.asarray(stream.x, dtype=np.int32),
            y=np.asarray(stream.y, dtype=np.int32),
            p01=np.asarray(stream.p01, dtype=np.uint8),
            signal_noise=getattr(stream, "signal_noise", None),
            width=getattr(stream, "width", None),
            height=getattr(stream, "height", None),
            source_format=getattr(stream, "source_format", None),
            metadata=metadata,
        )

    @classmethod
    def empty(
        cls,
        *,
        width: int,
        height: int,
        header_timestamp_ns: int,
        source_format: str | None = None,
    ) -> "EventStream":
        """Return empty event stream with known image size."""

        return cls(
            t_s=np.empty((0,), dtype=np.float64),
            x=np.empty((0,), dtype=np.int32),
            y=np.empty((0,), dtype=np.int32),
            p01=np.empty((0,), dtype=np.uint8),
            width=int(width),
            height=int(height),
            source_format=source_format,
            metadata={"header_timestamp_ns": int(header_timestamp_ns)},
        )

    def to_matrix_t_x_y_p(self) -> np.ndarray:
        """Return ``[t_s, x, y, p01]`` matrix accepted by eventDataGenLibPy."""

        self.validate()
        return np.stack(
            [
                self.t_s.astype(np.float64),
                self.x.astype(np.float64),
                self.y.astype(np.float64),
                self.p01.astype(np.float64),
            ],
            axis=1,
        )

    def to_t_x_y_p01_matrix(self) -> np.ndarray:
        """Return ``[t_s, x, y, p01]`` matrix for older bridge callers."""

        return self.to_matrix_t_x_y_p()

    def to_v2e_polarity(self) -> np.ndarray:
        """Return v2e-style polarity in {-1, 1}."""

        self.validate()
        return np.where(self.p01 > 0, 1, -1).astype(np.int8)


@dataclass(frozen=True)
class FrameSample:
    """Single grayscale frame sample with its replay timestamp."""

    index: int
    path: Path
    timestamp_ns: int
    image_mono8: np.ndarray


@dataclass(frozen=True)
class FrameEventStep:
    """One source replay step with optional frame and event stream."""

    frame: FrameSample | None
    events: EventStream | None


class FrameEventSource(Protocol):
    """Protocol for source adapters that can feed ROS bridge."""

    def build_steps(self) -> list[FrameEventStep]:
        """Return finite replay steps for one bridge run."""
