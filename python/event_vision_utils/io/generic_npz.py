"""Load conventional matrix, structured-array, or columnar event NPZ files.

Example:
    events = load_generic_npz(
        Path("events.npz"), width=640, height=480
    )
    print(events.size)

Output:
    1000
"""

from __future__ import annotations

from collections.abc import Sequence
from pathlib import Path

import numpy as np

from event_vision_utils.core.event_array import EventArray
from event_vision_utils.core.timestamps import infer_timestamp_unit


_DEFAULT_MATRIX_KEYS = ("events", "event_tuple", "event_tuples", "event_array")
_DEFAULT_TIMESTAMP_KEYS = (
    "t_us",
    "timestamp_us",
    "timestamps_us",
    "t_ms",
    "timestamp_ms",
    "timestamps_ms",
    "t_ns",
    "timestamp_ns",
    "timestamps_ns",
    "t_s",
    "timestamp_s",
    "timestamps_s",
    "t",
    "ts",
    "time",
    "timestamp",
    "timestamps",
)
_EventColumns = tuple[
    np.ndarray,
    np.ndarray,
    np.ndarray,
    np.ndarray,
    str,
]


def load_generic_npz(path: str | Path,
                     *,
                     width: int,
                     height: int,
                     x_key: str = "x",
                     y_key: str = "y",
                     p_key: str = "p",
                     t_key: str | None = None,
                     events_key: str | None = None,
                     column_order: Sequence[str] = (
                         "x",
                         "y",
                         "t_us",
                         "p",
                     ),
                     timestamp_unit: str = "us",
                     frame_id: str = "event_camera") -> EventArray:
    """Load one generic event NPZ through explicit geometry and field policy.

    Args:
        path: Input NPZ path.
        width: Sensor width in pixels.
        height: Sensor height in pixels.
        x_key: Columnar x-coordinate key.
        y_key: Columnar y-coordinate key.
        p_key: Columnar polarity key.
        t_key: Optional explicit columnar timestamp key.
        events_key: Optional explicit matrix or structured-array key.
        column_order: Matrix column names in storage order.
        timestamp_unit: Default timestamp unit for ambiguous names.
        frame_id: Event coordinate-frame identifier.

    Returns:
        Validated owning event array.

    Raises:
        KeyError: If an explicit or required NPZ key is absent.
        ValueError: If matrix fields, order, or event values are invalid.

    Example:
        events = load_generic_npz(
            Path("events.npz"), width=640, height=480
        )
        print(events.width, events.height)

    Output:
        640 480
    """
    with np.load(Path(path), allow_pickle=False) as data:
        # Prefer an explicit or conventional event-record array; otherwise
        # require a complete set of caller-named parallel columns.
        if events_key is not None or _has_matrix(data):
            key = _select_matrix_key(data, events_key)
            x, y, p, t, unit = _columns_from_matrix(
                data[key],
                column_order=column_order,
                timestamp_unit=timestamp_unit,
            )
            return EventArray.from_arrays(
                x=x,
                y=y,
                p=p,
                t=t,
                width=width,
                height=height,
                timestamp_unit=unit,
                frame_id=frame_id,
            )

        # Resolve timestamp aliases separately because their suffix also
        # carries the unit contract for columnar archives.
        t_name = _select_timestamp_key(data, t_key)
        missing = [key for key in (x_key, y_key, p_key, t_name) if key not in data]
        if missing:
            available = ", ".join(data.files)
            raise KeyError(f"missing npz keys {missing}; available keys: {available}")

        return EventArray.from_arrays(
            x=data[x_key],
            y=data[y_key],
            p=data[p_key],
            t=data[t_name],
            width=width,
            height=height,
            timestamp_unit=infer_timestamp_unit(t_name, timestamp_unit),
            frame_id=frame_id,
        )


def _has_matrix(data: np.lib.npyio.NpzFile) -> bool:
    """Return whether an archive has one unambiguous matrix candidate."""
    if any(key in data for key in _DEFAULT_MATRIX_KEYS):
        return True
    if len(data.files) == 1:
        array = data[data.files[0]]
        return bool(array.dtype.names) or (array.ndim == 2 and array.shape[1] >= 4)
    return False


def _select_matrix_key(data: np.lib.npyio.NpzFile, events_key: str | None) -> str:
    """Select an explicit or conventional matrix key."""
    if events_key is not None:
        if events_key not in data:
            available = ", ".join(data.files)
            raise KeyError(
                f"missing event matrix key '{events_key}'; "
                f"available keys: {available}"
            )
        return events_key
    for candidate in _DEFAULT_MATRIX_KEYS:
        if candidate in data:
            return candidate
    return data.files[0]


def _select_timestamp_key(data: np.lib.npyio.NpzFile, t_key: str | None) -> str:
    """Select an explicit or conventional columnar timestamp key."""
    if t_key is not None:
        return t_key
    for candidate in _DEFAULT_TIMESTAMP_KEYS:
        if candidate in data:
            return candidate
    available = ", ".join(data.files)
    raise KeyError(f"missing timestamp key; available keys: {available}")


def _columns_from_matrix(matrix: np.ndarray,
                         *,
                         column_order: Sequence[str],
                         timestamp_unit: str) -> _EventColumns:
    """Extract canonical event columns from matrix-like storage."""
    array = np.asarray(matrix)
    if array.dtype.names:
        return _columns_from_structured_array(array, timestamp_unit=timestamp_unit)

    # Canonicalize aliases before indexing so duplicate semantic columns and
    # omitted required fields fail deterministically.
    canonical_order = [_canonical_column_name(name) for name in column_order]
    if len(set(canonical_order)) != len(canonical_order):
        raise ValueError("event matrix column_order contains duplicate columns")
    if array.ndim != 2 or array.shape[1] < len(column_order):
        raise ValueError(
            "event matrix must be two-dimensional with at least "
            f"{len(column_order)} columns"
        )

    columns: dict[str, np.ndarray] = {}
    detected_unit = timestamp_unit
    for index, (name, canonical) in enumerate(
        zip(column_order, canonical_order, strict=True)
    ):
        columns[canonical] = array[:, index]
        if canonical == "t":
            detected_unit = infer_timestamp_unit(name, timestamp_unit)

    missing = [name for name in ("x", "y", "p", "t") if name not in columns]
    if missing:
        raise ValueError(f"event matrix column_order is missing columns: {missing}")

    return columns["x"], columns["y"], columns["p"], columns["t"], detected_unit


def _columns_from_structured_array(array: np.ndarray,
                                   *,
                                   timestamp_unit: str) -> _EventColumns:
    """Extract canonical columns from a one-dimensional structured array."""
    if array.ndim != 1:
        raise ValueError("event structured array must be one-dimensional")

    # Record the original field spelling while rejecting aliases that would
    # otherwise overwrite the same canonical event column.
    fields: dict[str, str] = {}
    for name in array.dtype.names or ():
        canonical = _canonical_column_name(name)
        if canonical in fields:
            raise ValueError(
                f"event structured array contains duplicate '{canonical}' fields"
            )
        fields[canonical] = name

    missing = [name for name in ("x", "y", "p", "t") if name not in fields]
    if missing:
        raise ValueError(f"event structured array is missing fields: {missing}")

    t_field = fields["t"]
    return (
        array[fields["x"]],
        array[fields["y"]],
        array[fields["p"]],
        array[t_field],
        infer_timestamp_unit(t_field, timestamp_unit),
    )


def _canonical_column_name(name: str) -> str:
    """Map a supported event-column alias to its canonical name."""
    if not isinstance(name, str):
        raise TypeError("event matrix column names must be strings")
    lowered = name.lower()
    if lowered in {"x", "col", "u"}:
        return "x"
    if lowered in {"y", "row", "v"}:
        return "y"
    if lowered in {"p", "polarity", "pol"}:
        return "p"
    if lowered in {
        "t",
        "ts",
        "time",
        "timestamp",
        "timestamps",
        "t_us",
        "timestamp_us",
        "timestamps_us",
        "t_ms",
        "timestamp_ms",
        "timestamps_ms",
        "t_s",
        "timestamp_s",
        "timestamps_s",
        "t_ns",
        "timestamp_ns",
        "timestamps_ns",
    }:
        return "t"
    raise ValueError(f"unsupported event matrix column '{name}'")
