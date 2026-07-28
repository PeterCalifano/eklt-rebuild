"""Select strict ELOPE or explicitly dimensioned generic NPZ adapters.

Example:
    dataset = load_event_dataset(
        Path("events.npz"), adapter="generic_npz", width=640, height=480
    )
    print(dataset.metadata.name)

Output:
    generic_npz
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import numpy as np

from event_vision_utils.core.event_array import EventArray
from event_vision_utils.core.validation import (
    validate_frame_id,
    validate_sensor_size,
)
from event_vision_utils.io.elope_npz import (
    load_elope_npz,
    resolve_elope_geometry,
    validate_elope_npz,
)
from event_vision_utils.io.generic_npz import load_generic_npz

_ADAPTER_ERRORS = (OSError, KeyError, TypeError, ValueError, OverflowError)


@dataclass(frozen=True, slots=True)
class DatasetMetadata:
    """Describe one loaded event dataset independently of its adapter.

    Attributes:
        name: Stable adapter or dataset name.
        source_path: Source archive path.
        width: Sensor width in pixels.
        height: Sensor height in pixels.
        frame_id: Event coordinate-frame identifier.
        attributes: Adapter-specific metadata values.

    Example:
        metadata = DatasetMetadata(
            name="fixture", source_path=Path("events.npz"),
            width=2, height=2
        )
        print(metadata.name, metadata.width, metadata.height)

    Output:
        fixture 2 2
    """

    name: str
    source_path: Path
    width: int
    height: int
    frame_id: str = "event_camera"
    attributes: dict[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        """Normalize immutable metadata fields and copy mutable attributes."""
        if not isinstance(self.name, str) or not self.name.strip():
            raise ValueError("dataset metadata name must not be empty")
        width, height = validate_sensor_size(self.width, self.height)
        object.__setattr__(self, "name", self.name.strip())
        object.__setattr__(self, "source_path", Path(self.source_path))
        object.__setattr__(self, "width", width)
        object.__setattr__(self, "height", height)
        object.__setattr__(self, "frame_id", validate_frame_id(self.frame_id))
        object.__setattr__(self, "attributes", dict(self.attributes))


@dataclass(frozen=True, slots=True)
class LoadedEventDataset:
    """Pair validated events with matching source metadata.

    Example:
        dataset = LoadedEventDataset(events=events, metadata=metadata)
        print(dataset.events.size, dataset.metadata.name)

    Output:
        1 fixture
    """

    events: EventArray
    metadata: DatasetMetadata

    def __post_init__(self) -> None:
        """Require metadata geometry and frame identity to match the events."""
        event_contract = (
            self.events.width,
            self.events.height,
            self.events.frame_id,
        )
        metadata_contract = (
            self.metadata.width,
            self.metadata.height,
            self.metadata.frame_id,
        )
        if event_contract != metadata_contract:
            raise ValueError("dataset metadata does not match its event array")


class EventDatasetAdapter(ABC):
    """Abstract validated loader producing the common dataset contract.

    Example:
        adapter = ElopeNpzAdapter()
        print(isinstance(adapter, EventDatasetAdapter))

    Output:
        True
    """

    name: str

    @abstractmethod
    def can_load(self, path: str | Path) -> bool:
        """Return whether this adapter recognizes and validates a source.

        Args:
            path: Candidate dataset path.

        Returns:
            True only when this adapter can load the complete source safely.

        Example:
            print(adapter.can_load(Path("events.npz")))

        Output:
            True
        """

    @abstractmethod
    def load(self, path: str | Path) -> LoadedEventDataset:
        """Load one source into the common event-dataset contract.

        Args:
            path: Dataset path owned by the concrete adapter.

        Returns:
            Validated event data and matching source metadata.

        Example:
            dataset = adapter.load(Path("events.npz"))
            print(dataset.metadata.name)

        Output:
            elope
        """

    def validate(self, path: str | Path) -> None:
        """Raise when the source cannot be loaded by this adapter.

        Args:
            path: Candidate dataset path.

        Example:
            adapter.validate(Path("events.npz"))
            print("valid")

        Output:
            valid
        """
        self.load(path)


@dataclass(frozen=True, slots=True)
class ElopeNpzAdapter(EventDatasetAdapter):
    """Load an official ELOPE archive with strict auxiliary metadata.

    Example:
        adapter = ElopeNpzAdapter()
        print(adapter.name, adapter.width)

    Output:
        elope None
    """

    width: int | None = None
    height: int | None = None
    frame_id: str = "event_camera"
    name: str = "elope"

    def __post_init__(self) -> None:
        """Validate optional geometry overrides before opening a dataset."""
        if (self.width is None) != (self.height is None):
            raise ValueError(
                "width and height overrides must be provided together"
            )
        if self.width is not None and self.height is not None:
            width, height = validate_sensor_size(self.width, self.height)
            object.__setattr__(self, "width", width)
            object.__setattr__(self, "height", height)
        object.__setattr__(self, "frame_id", validate_frame_id(self.frame_id))

    def can_load(self, path: str | Path) -> bool:
        """Return whether a source satisfies the official ELOPE schema.

        Args:
            path: Candidate ELOPE archive path.

        Returns:
            True only when schema, geometry, and events all validate.

        Example:
            print(ElopeNpzAdapter().can_load(Path("0028.npz")))

        Output:
            True
        """
        try:
            self.load(path)
        except _ADAPTER_ERRORS:
            return False
        return True

    def load(self, path: str | Path) -> LoadedEventDataset:
        """Load official ELOPE events and bounded auxiliary metadata.

        Args:
            path: Official ELOPE NPZ path.

        Returns:
            Loaded event array and ELOPE metadata.

        Example:
            dataset = ElopeNpzAdapter().load(Path("0028.npz"))
            print(dataset.metadata.name)

        Output:
            elope
        """
        source_path = Path(path)
        validate_elope_npz(source_path)
        geometry = resolve_elope_geometry(
            source_path,
            width=self.width,
            height=self.height,
        )
        events = load_elope_npz(
            source_path,
            width=geometry.width,
            height=geometry.height,
            frame_id=self.frame_id,
        )

        # Retain only compact shapes/counts and validity indicators rather than
        # duplicating auxiliary arrays in the loaded dataset object.
        with np.load(source_path, allow_pickle=False) as data:
            timestamps = np.asarray(data["timestamps"])
            trajectory = np.asarray(data["traj"])
            range_meter_key = (
                "range_meter" if "range_meter" in data else "rangemeter"
            )
            range_meter = np.asarray(data[range_meter_key])
            full_trajectory_columns = _full_trajectory_columns(trajectory)
            attributes = {
                "timestamps_count": int(timestamps.size),
                "traj_shape": tuple(
                    int(value) for value in trajectory.shape
                ),
                "range_meter_shape": tuple(
                    int(value) for value in range_meter.shape
                ),
                "full_traj_columns": full_trajectory_columns,
                "position_velocity_available": all(
                    index in full_trajectory_columns for index in range(6)
                ),
                "geometry_source": geometry.source,
            }

        return LoadedEventDataset(
            events=events,
            metadata=DatasetMetadata(
                name=self.name,
                source_path=source_path,
                width=events.width,
                height=events.height,
                frame_id=events.frame_id,
                attributes=attributes,
            ),
        )


@dataclass(frozen=True, slots=True)
class GenericNpzAdapter(EventDatasetAdapter):
    """Load a generic NPZ only with explicit sensor geometry.

    Example:
        adapter = GenericNpzAdapter(width=640, height=480)
        print(adapter.name, adapter.width, adapter.height)

    Output:
        generic_npz 640 480
    """

    width: int
    height: int
    frame_id: str = "event_camera"
    timestamp_unit: str = "us"
    name: str = "generic_npz"

    def __post_init__(self) -> None:
        """Validate fixed geometry and metadata used for every load."""
        width, height = validate_sensor_size(self.width, self.height)
        object.__setattr__(self, "width", width)
        object.__setattr__(self, "height", height)
        object.__setattr__(self, "frame_id", validate_frame_id(self.frame_id))
        if not isinstance(self.timestamp_unit, str):
            raise TypeError("timestamp_unit must be a string")

    def can_load(self, path: str | Path) -> bool:
        """Return whether the source satisfies the configured generic schema.

        Args:
            path: Candidate generic NPZ path.

        Returns:
            True only when the complete source satisfies this adapter.

        Example:
            print(adapter.can_load(Path("events.npz")))

        Output:
            True
        """
        try:
            self.load(path)
        except _ADAPTER_ERRORS:
            return False
        return True

    def load(self, path: str | Path) -> LoadedEventDataset:
        """Load one generic NPZ with this adapter's explicit geometry.

        Args:
            path: Generic NPZ path.

        Returns:
            Loaded event array and generic metadata.

        Example:
            dataset = adapter.load(Path("events.npz"))
            print(dataset.events.width, dataset.events.height)

        Output:
            640 480
        """
        source_path = Path(path)
        events = load_generic_npz(
            source_path,
            width=self.width,
            height=self.height,
            timestamp_unit=self.timestamp_unit,
            frame_id=self.frame_id,
        )
        return LoadedEventDataset(
            events=events,
            metadata=DatasetMetadata(
                name=self.name,
                source_path=source_path,
                width=events.width,
                height=events.height,
                frame_id=events.frame_id,
            ),
        )


def load_event_dataset(path: str | Path,
                       *,
                       adapter: str = "auto",
                       width: int | None = None,
                       height: int | None = None,
                       frame_id: str = "event_camera") -> LoadedEventDataset:
    """Load strict ELOPE data or an explicitly dimensioned generic NPZ.

    Args:
        path: Dataset NPZ path.
        adapter: ``auto``, ``elope``, or ``generic_npz``.
        width: Optional sensor width; required with height for generic data.
        height: Optional sensor height; required with width for generic data.
        frame_id: Event coordinate-frame identifier.

    Returns:
        Loaded event data and matching metadata.

    Raises:
        ValueError: If adapter selection, geometry, or source data is invalid.

    Example:
        dataset = load_event_dataset(
            Path("events.npz"), adapter="generic_npz",
            width=640, height=480
        )
        print(dataset.metadata.name)

    Output:
        generic_npz
    """
    if (width is None) != (height is None):
        raise ValueError("width and height overrides must be provided together")
    if adapter not in {"auto", "elope", "generic_npz"}:
        raise ValueError(
            f"unknown dataset adapter '{adapter}'; "
            "available: auto, elope, generic_npz"
        )

    elope_adapter = ElopeNpzAdapter(
        width=width,
        height=height,
        frame_id=frame_id,
    )
    if adapter == "elope":
        return elope_adapter.load(path)

    if adapter == "auto":
        try:
            return elope_adapter.load(path)
        except _ADAPTER_ERRORS as elope_error:
            # ELOPE-like archives must fail their strict schema rather than
            # falling through to the permissive generic matrix loader.
            if _contains_elope_metadata(path):
                raise ValueError(
                    "ELOPE-like archive failed strict validation"
                ) from elope_error

    if width is None or height is None:
        raise ValueError(
            "generic NPZ loading requires explicit width and height"
        )
    return GenericNpzAdapter(
        width=width,
        height=height,
        frame_id=frame_id,
    ).load(path)


def _contains_elope_metadata(path: str | Path) -> bool:
    """Return whether an NPZ advertises any ELOPE auxiliary surface."""
    with np.load(Path(path), allow_pickle=False) as data:
        return bool(
            {"traj", "range_meter", "rangemeter"}
            & set(data.files)
        )


def _full_trajectory_columns(trajectory: np.ndarray) -> list[int]:
    """Return columns whose complete trajectory values are finite."""
    if trajectory.ndim != 2:
        return []
    columns: list[int] = []
    for index in range(trajectory.shape[1]):
        values = np.asarray(trajectory[:, index])
        if values.size and bool(np.all(np.isfinite(values))):
            columns.append(index)
    return columns
