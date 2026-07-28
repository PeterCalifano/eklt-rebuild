"""Load official ELOPE event archives with validated sensor geometry.

Explicit scalar width/height metadata is authoritative. Official files without
those keys use the documented 200-by-200 sensor contract; event-coordinate
extrema are never treated as geometry metadata.

Example:
    geometry = resolve_elope_geometry(Path("0028.npz"))
    print(geometry.width, geometry.height, geometry.source)

Output:
    200 200 elope_contract
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
from pathlib import Path

import numpy as np

from event_vision_utils.core.event_array import EventArray
from event_vision_utils.core.validation import (
    normalize_integer_scalar,
    validate_sensor_size,
)
from event_vision_utils.io.generic_npz import load_generic_npz

_OFFICIAL_ELOPE_KEYS = ("events", "timestamps", "traj")
_RANGE_METER_KEYS = ("range_meter", "rangemeter")
_GEOMETRY_KEY_PAIRS = (
    ("width", "height"),
    ("sensor_width", "sensor_height"),
    ("camera_width", "camera_height"),
)
_ELOPE_DEFAULT_WIDTH = 200
_ELOPE_DEFAULT_HEIGHT = 200
_MAX_SENSOR_DIMENSION = int(np.iinfo(np.int32).max)


@dataclass(frozen=True, slots=True)
class ElopeGeometry:
    """Resolved ELOPE event-sensor geometry.

    Attributes:
        width: Sensor width in pixels.
        height: Sensor height in pixels.
        source: Dataset metadata, explicit override, or ELOPE contract.

    Example:
        geometry = ElopeGeometry(200, 200, "elope_contract")
        print(geometry.width, geometry.height, geometry.source)

    Output:
        200 200 elope_contract
    """

    width: int
    height: int
    source: str

    def __post_init__(self) -> None:
        """Normalize geometry and require one descriptive source label."""
        width, height = validate_sensor_size(self.width, self.height)
        if not isinstance(self.source, str):
            raise TypeError("ELOPE geometry source must be a string")
        source = self.source.strip()
        if not source:
            raise ValueError("ELOPE geometry source must not be empty")

        object.__setattr__(self, "width", width)
        object.__setattr__(self, "height", height)
        object.__setattr__(self, "source", source)


def load_elope_npz(path: str | Path,
                   *,
                   width: int | None = None,
                   height: int | None = None,
                   events_key: str | None = None,
                   column_order: Sequence[str] = (
                       "x",
                       "y",
                       "p",
                       "t_us",
                   ),
                   timestamp_unit: str = "us",
                   frame_id: str = "event_camera",
                   strict: bool = True) -> EventArray:
    """Load official ELOPE events through the common event-array contract.

    Args:
        path: ELOPE NPZ path.
        width: Optional explicit width paired with height.
        height: Optional explicit height paired with width.
        events_key: Optional matrix key; strict mode permits only ``events``.
        column_order: Matrix column names in storage order.
        timestamp_unit: Timestamp unit for ambiguous event fields.
        frame_id: Event coordinate-frame identifier.
        strict: Whether official auxiliary metadata is required.

    Returns:
        Validated owning ELOPE event array.

    Raises:
        ValueError: If strict schema or geometry validation fails.

    Example:
        events = load_elope_npz(Path("0028.npz"))
        print(events.width, events.height)

    Output:
        200 200
    """
    # Keep official archives on the strict schema path before delegating their
    # event payload to the shared matrix/structured-array implementation.
    if strict:
        validate_elope_npz(path)
        if events_key not in (None, "events"):
            raise ValueError("official ELOPE files use the 'events' matrix key")
        events_key = "events"
    geometry = resolve_elope_geometry(path, width=width, height=height)
    return load_generic_npz(
        path,
        width=geometry.width,
        height=geometry.height,
        events_key=events_key,
        column_order=column_order,
        timestamp_unit=timestamp_unit,
        frame_id=frame_id,
    )


def resolve_elope_geometry(path: str | Path,
                           *,
                           width: int | None = None,
                           height: int | None = None) -> ElopeGeometry:
    """Resolve ELOPE geometry without using observed coordinate extrema.

    Args:
        path: ELOPE NPZ input.
        width: Optional explicit width override.
        height: Optional explicit height override.

    Returns:
        Dataset geometry, a validated explicit override, or the official
        200-by-200 ELOPE contract.

    Raises:
        ValueError: If dimensions are partial, invalid, or conflicting.

    Example:
        geometry = resolve_elope_geometry(Path("0028.npz"))
        print(geometry.width, geometry.height, geometry.source)

    Output:
        200 200 elope_contract
    """
    if (width is None) != (height is None):
        raise ValueError("width and height overrides must be provided together")

    # Read metadata independently from observed events so sparse recordings
    # cannot silently shrink the sensor geometry.
    advertised = _read_advertised_geometry(path)
    if width is not None and height is not None:
        override = ElopeGeometry(
            width=_normalize_dimension("width override", width),
            height=_normalize_dimension("height override", height),
            source="explicit_override",
        )
        if (
            advertised is not None
            and (override.width, override.height)
            != (advertised.width, advertised.height)
        ):
            raise ValueError(
                "explicit sensor geometry conflicts with ELOPE metadata"
            )
        return advertised if advertised is not None else override

    # Official files without geometry metadata use the published ELOPE sensor
    # contract rather than coordinate-extrema inference.
    if advertised is not None:
        return advertised
    return ElopeGeometry(
        width=_ELOPE_DEFAULT_WIDTH,
        height=_ELOPE_DEFAULT_HEIGHT,
        source="elope_contract",
    )


def validate_elope_npz(path: str | Path) -> None:
    """Validate official ELOPE event and auxiliary-array structure.

    Args:
        path: Candidate ELOPE NPZ path.

    Raises:
        ValueError: If required fields or array shapes are absent.

    Example:
        validate_elope_npz(Path("0028.npz"))
        print("valid")

    Output:
        valid
    """
    input_path = Path(path)
    with np.load(input_path, allow_pickle=False) as data:
        missing = [key for key in _OFFICIAL_ELOPE_KEYS if key not in data]
        range_meter_key = _select_range_meter_key(data)
        if range_meter_key is None:
            missing.append("range_meter")
        if missing:
            available = ", ".join(data.files)
            raise ValueError(
                "not an official ELOPE dataset file; missing keys "
                f"{missing}; available keys: {available}"
            )

        # Accept both the released structured dtype and the documented matrix
        # representation while keeping their field contracts unambiguous.
        events = np.asarray(data["events"])
        if events.dtype.names:
            missing_fields = [
                field
                for field in ("x", "y", "p", "t")
                if field not in events.dtype.names
            ]
            if missing_fields:
                raise ValueError(
                    "ELOPE structured 'events' missing fields: "
                    f"{missing_fields}"
                )
            if events.ndim != 1:
                raise ValueError(
                    "ELOPE structured 'events' must be one-dimensional"
                )
        elif events.ndim != 2 or events.shape[1] < 4:
            raise ValueError(
                "ELOPE 'events' must be a structured array or a "
                "two-dimensional matrix with columns x,y,p,t"
            )

        # Validate auxiliary shapes required to identify an official ELOPE
        # archive without retaining those arrays in the returned event model.
        timestamps = np.asarray(data["timestamps"])
        traj = np.asarray(data["traj"])
        rangemeter = np.asarray(data[range_meter_key])
        if timestamps.ndim != 1:
            raise ValueError("ELOPE 'timestamps' must be one-dimensional")
        if traj.ndim != 2 or traj.shape[1] < 12:
            raise ValueError(
                "ELOPE 'traj' must be a two-dimensional state matrix "
                "with at least 12 columns"
            )
        if rangemeter.ndim != 2 or rangemeter.shape[1] < 2:
            raise ValueError(
                "ELOPE 'range_meter' must be a two-dimensional matrix "
                "with at least 2 columns"
            )


def _select_range_meter_key(data: np.lib.npyio.NpzFile) -> str | None:
    """Return the accepted range-meter key present in an archive."""
    for key in _RANGE_METER_KEYS:
        if key in data:
            return key
    return None


def _read_advertised_geometry(path: str | Path) -> ElopeGeometry | None:
    """Read and reconcile every complete geometry metadata pair."""
    advertised: ElopeGeometry | None = None
    with np.load(Path(path), allow_pickle=False) as data:
        # Treat every accepted key pair as an assertion and reject archives
        # whose redundant metadata disagrees.
        for width_key, height_key in _GEOMETRY_KEY_PAIRS:
            has_width = width_key in data
            has_height = height_key in data
            if has_width != has_height:
                raise ValueError(
                    "ELOPE geometry metadata must provide both "
                    f"'{width_key}' and '{height_key}'"
                )
            if not has_width:
                continue

            candidate = ElopeGeometry(
                width=_normalize_dimension(width_key, data[width_key]),
                height=_normalize_dimension(height_key, data[height_key]),
                source=f"npz:{width_key},{height_key}",
            )
            if (
                advertised is not None
                and (candidate.width, candidate.height)
                != (advertised.width, advertised.height)
            ):
                raise ValueError("ELOPE geometry metadata pairs disagree")
            advertised = candidate
    return advertised


def _normalize_dimension(name: str, value: object) -> int:
    """Normalize one bounded scalar ELOPE geometry dimension."""
    try:
        return normalize_integer_scalar(
            f"ELOPE {name}",
            value,
            minimum=1,
            maximum=_MAX_SENSOR_DIMENSION,
        )
    except TypeError as exc:
        raise ValueError(f"ELOPE {name} must be one numeric scalar") from exc
