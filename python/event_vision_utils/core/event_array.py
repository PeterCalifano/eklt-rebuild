"""Define the canonical signed-polarity, microsecond event-array model.

Example:
    events = EventArray(
        x=[1], y=[2], p=[True], t_us=[10], width=4, height=3
    )
    print(events.as_columns().tolist())

Output:
    [[1, 2, 1, 10]]
"""

from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass

import numpy as np

from event_vision_utils.core.timestamps import normalize_timestamps_to_us
from event_vision_utils.core.validation import (
    normalize_coordinate,
    normalize_polarity,
    validate_equal_lengths,
    validate_frame_id,
    validate_monotonic_timestamps,
    validate_sensor_size,
)


@dataclass(slots=True)
class EventArray:
    """Owning event columns with one explicit sensor and timestamp contract.

    Attributes:
        x: Signed 32-bit pixel x coordinates.
        y: Signed 32-bit pixel y coordinates.
        p: Signed 8-bit polarities in ``{-1, +1}``.
        t_us: Monotonic signed 64-bit timestamps in microseconds.
        width: Sensor width in pixels.
        height: Sensor height in pixels.
        frame_id: Coordinate-frame identifier.

    Example:
        events = EventArray(
            x=[1], y=[2], p=[0], t_us=[10], width=4, height=3
        )
        print(events.p.tolist(), events.size)

    Output:
        [-1] 1
    """

    x: np.ndarray
    y: np.ndarray
    p: np.ndarray
    t_us: np.ndarray
    width: int
    height: int
    frame_id: str = "event_camera"

    def __post_init__(self) -> None:
        """Normalize storage and enforce the complete event-array contract."""
        width, height = validate_sensor_size(self.width, self.height)
        self.width = width
        self.height = height
        self.frame_id = validate_frame_id(self.frame_id)

        # Validate wide source values before narrowing each owning column.
        self.x = normalize_coordinate("x", self.x, width)
        self.y = normalize_coordinate("y", self.y, height)
        self.p = normalize_polarity(self.p)
        self.t_us = normalize_timestamps_to_us(self.t_us, unit="us")
        validate_equal_lengths(
            x=self.x,
            y=self.y,
            p=self.p,
            t_us=self.t_us,
        )
        validate_monotonic_timestamps(self.t_us)

    @classmethod
    def from_arrays(cls,
                    *,
                    x: object,
                    y: object,
                    p: object,
                    t: object,
                    width: int,
                    height: int,
                    timestamp_unit: str = "us",
                    frame_id: str = "event_camera") -> "EventArray":
        """Construct events while converting an explicitly named time unit.

        Args:
            x: Pixel x coordinates.
            y: Pixel y coordinates.
            p: Boolean, binary, or signed polarities.
            t: Event timestamps in ``timestamp_unit``.
            width: Sensor width in pixels.
            height: Sensor height in pixels.
            timestamp_unit: Unit used by ``t``.
            frame_id: Coordinate-frame identifier.

        Returns:
            Validated owning event array.

        Example:
            events = EventArray.from_arrays(
                x=[0], y=[0], p=[0], t=[0.001],
                width=1, height=1, timestamp_unit="s"
            )
            print(events.t_us.tolist(), events.p.tolist())

        Output:
            [1000] [-1]
        """
        return cls(
            x=np.asarray(x),
            y=np.asarray(y),
            p=np.asarray(p),
            t_us=normalize_timestamps_to_us(t, unit=timestamp_unit),
            width=width,
            height=height,
            frame_id=frame_id,
        )

    @property
    def size(self) -> int:
        """Return the number of events.

        Example:
            print(events.size)

        Output:
            1
        """
        return int(self.t_us.size)

    @property
    def t_start_us(self) -> int | None:
        """Return the first timestamp, or ``None`` for an empty array.

        Example:
            print(events.t_start_us)

        Output:
            10
        """
        if self.size == 0:
            return None
        return int(self.t_us[0])

    @property
    def t_end_us(self) -> int | None:
        """Return the final timestamp, or ``None`` for an empty array.

        Example:
            print(events.t_end_us)

        Output:
            10
        """
        if self.size == 0:
            return None
        return int(self.t_us[-1])

    @property
    def duration_us(self) -> int:
        """Return the nonnegative first-to-last duration in microseconds.

        Example:
            print(events.duration_us)

        Output:
            0
        """
        if self.size <= 1:
            return 0
        # Convert operands independently so subtraction cannot overflow int64.
        return int(self.t_us[-1]) - int(self.t_us[0])

    def subset(self, indices: object) -> "EventArray":
        """Copy selected events while preserving sensor metadata.

        Args:
            indices: NumPy-compatible slice, mask, or integer index array.

        Returns:
            Validated owning event subset.

        Example:
            selected = events.subset(slice(0, 1))
            print(selected.size)

        Output:
            1
        """
        return EventArray(
            x=self.x[indices],
            y=self.y[indices],
            p=self.p[indices],
            t_us=self.t_us[indices],
            width=self.width,
            height=self.height,
            frame_id=self.frame_id,
        )

    def as_columns(self,
                   order: Iterable[str] = (
                       "x",
                       "y",
                       "p",
                       "t_us",
                   )) -> np.ndarray:
        """Return selected event columns in caller-defined order.

        Args:
            order: Non-empty sequence of unique canonical column names.

        Returns:
            Two-dimensional matrix with one row per event.

        Raises:
            ValueError: If order is empty, duplicated, or unsupported.

        Example:
            columns = events.as_columns(("t_us", "x", "y", "p"))
            print(columns.tolist())

        Output:
            [[10, 1, 2, -1]]
        """
        names = tuple(order)
        if not names:
            raise ValueError("event column order must not be empty")
        if len(set(names)) != len(names):
            raise ValueError("event column order must not contain duplicates")

        columns: list[np.ndarray] = []
        for name in names:
            if name not in {"x", "y", "p", "t_us"}:
                raise ValueError(f"unsupported event column '{name}'")
            columns.append(getattr(self, name))
        return np.column_stack(columns)
