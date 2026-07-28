"""Convert an ELOPE event array into a standard ROS2 EventPacket bag.

Only the ELOPE ``events`` array and sensor geometry are consumed. Explicit
width/height metadata is authoritative when present; otherwise the official
200-by-200 ELOPE contract is used. Trajectory, range, and camera-calibration
data are intentionally outside this two-dimensional EKLT playback boundary.
Encoded packets are written incrementally to an atomic staging directory.

Example:
    python scripts/convert_elope_npz_to_eventpacket.py \
        --input data/elope/test/0028.npz \
        --output outputs/elope_event_only/eventpacket_bag \
        --summary-output outputs/elope_event_only/elope_conversion_summary.json

Output:
    converted 386785 ELOPE events to 2434 ROS2 EventPacket messages
"""

from __future__ import annotations

import argparse
import json
import math
import os
import shutil
import sys
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Sequence

import numpy as np
from rosbags.rosbag2 import Writer
from rosbags.typesys import Stores, get_types_from_msg, get_typestore

EVENT_PACKET_TYPE = "event_camera_msgs/msg/EventPacket"
EVENT_PACKET_DEFINITION = """\
std_msgs/Header header
uint32 height
uint32 width
uint64 seq
uint64 time_base
string encoding
bool is_bigendian
uint8[] events
"""
UINT32_MAX = np.iinfo(np.uint32).max
INT64_MAX = np.iinfo(np.int64).max
ELOPE_DEFAULT_WIDTH = 200
ELOPE_DEFAULT_HEIGHT = 200
GEOMETRY_KEY_PAIRS = (
    ("width", "height"),
    ("sensor_width", "sensor_height"),
    ("camera_width", "camera_height"),
)


@dataclass(frozen=True)
class SensorGeometry:
    """Resolved event-sensor dimensions and their provenance.

    Attributes:
        width: Sensor width in pixels.
        height: Sensor height in pixels.
        source: Dataset metadata, explicit override, or ELOPE contract.
    """

    width: int
    height: int
    source: str


@dataclass
class ConversionStatistics:
    """Accumulate conversion provenance and bounded output evidence.

    Attributes:
        input: Source ELOPE file.
        output: Destination ROS2 bag directory.
        output_topic: Written EventPacket topic.
        width: Resolved event-sensor width.
        height: Resolved event-sensor height.
        geometry_source: Provenance of the resolved dimensions.
        frame_id: Frame identifier assigned to packet headers.
        dt_ms: Maximum packet time span in milliseconds.
        max_events_per_packet: Maximum event count in one packet.
        max_packets: Requested packet limit; zero means unlimited.
        available_keys: Arrays present in the source NPZ file.
        source_event_count: Valid events present in the input.
        event_packets: Number of destination packets written.
        event_count: Number of events written after optional limiting.
        first_event_ns: Earliest encoded event timestamp.
        last_event_ns: Latest encoded event timestamp.
    """

    input: str
    output: str
    output_topic: str
    width: int
    height: int
    geometry_source: str
    frame_id: str
    dt_ms: float
    max_events_per_packet: int
    max_packets: int
    available_keys: list[str]
    source_event_count: int
    encoding: str = "mono"
    event_packets: int = 0
    event_count: int = 0
    first_event_ns: int | None = None
    last_event_ns: int | None = None

    def update_events(self, timestamps_ns: np.ndarray) -> None:
        """Record one non-empty encoded packet.

        Args:
            timestamps_ns: Monotonic packet timestamps in nanoseconds.
        """
        first_timestamp = int(timestamps_ns[0])
        last_timestamp = int(timestamps_ns[-1])
        if self.first_event_ns is None:
            self.first_event_ns = first_timestamp
        self.last_event_ns = last_timestamp
        self.event_count += int(timestamps_ns.size)
        self.event_packets += 1

    def to_dict(self) -> dict[str, object]:
        """Return a JSON-ready conversion summary.

        Returns:
            Provenance fields plus represented duration and pass status.
        """
        summary = asdict(self)
        duration_ns = 0
        if self.first_event_ns is not None and self.last_event_ns is not None:
            duration_ns = self.last_event_ns - self.first_event_ns
        summary["duration_s"] = duration_ns / 1_000_000_000.0
        summary["status"] = "passed"
        return summary


def normalize_integer_column(name: str,
                             values: np.ndarray,
                             minimum: int,
                             maximum: int) -> np.ndarray:
    """Validate one numeric event column and return signed 64-bit integers.

    Args:
        name: Column name used in diagnostics.
        values: One-dimensional numeric values.
        minimum: Inclusive minimum accepted value.
        maximum: Inclusive maximum accepted value.

    Returns:
        Contiguous signed 64-bit values.

    Raises:
        TypeError: If values are not numeric.
        ValueError: If shape, finiteness, integrality, or bounds are invalid.
    """
    array = np.asarray(values)
    if array.ndim != 1:
        raise ValueError(f"ELOPE {name} must be one-dimensional")
    if array.dtype.kind not in "biuf":
        raise TypeError(f"ELOPE {name} must contain numeric values")
    if array.dtype.kind == "f":
        if not bool(np.all(np.isfinite(array))):
            raise ValueError(f"ELOPE {name} must contain finite values")
        normalized_values = np.rint(array)
        if not bool(np.all(array == normalized_values)):
            raise ValueError(f"ELOPE {name} must contain integer values")
    else:
        # Retain exact integer comparisons so uint64 event timestamps are not
        # rounded through float64 before range validation.
        normalized_values = array

    below_minimum = (
        normalized_values.size > 0
        and not (normalized_values.dtype.kind == "u" and minimum < 0)
        and bool(np.any(normalized_values < minimum))
    )
    above_maximum = normalized_values.size > 0 and bool(
        np.any(normalized_values > maximum)
    )
    if below_minimum or above_maximum:
        raise ValueError(
            f"ELOPE {name} values must be in [{minimum}, {maximum}]"
        )
    return np.ascontiguousarray(normalized_values, dtype=np.int64)


def normalize_polarities(values: np.ndarray) -> np.ndarray:
    """Normalize ELOPE polarity to zero for OFF and one for ON.

    Args:
        values: Boolean, ``{0, 1}``, or ``{-1, 1}`` polarity values.

    Returns:
        Contiguous unsigned polarity bits.

    Raises:
        ValueError: If polarity contains unsupported values.
    """
    integer_values = normalize_integer_column(
        "polarity", values, minimum=-1, maximum=1
    )
    unique_values = set(np.unique(integer_values).tolist())
    if not (
        unique_values.issubset({-1, 1})
        or unique_values.issubset({0, 1})
    ):
        raise ValueError("ELOPE polarity must use bool, {0, 1}, or {-1, 1}")
    return np.ascontiguousarray(integer_values > 0, dtype=np.uint8)


def normalize_sensor_dimension(name: str,
                               value: object,
                               maximum: int) -> int:
    """Return one positive scalar sensor dimension.

    Args:
        name: Metadata or option name used in diagnostics.
        value: Scalar numeric dimension.
        maximum: Inclusive implementation limit.

    Returns:
        Validated integer dimension.

    Raises:
        ValueError: If the value is not one finite integral scalar in range.
    """
    array = np.asarray(value)
    if array.size != 1 or array.dtype.kind not in "iuf":
        raise ValueError(f"ELOPE {name} must be one numeric scalar")

    scalar = array.reshape(-1)[0]
    if array.dtype.kind == "f":
        if not bool(np.isfinite(scalar)) or float(scalar) != round(float(scalar)):
            raise ValueError(f"ELOPE {name} must be one finite integer")
    dimension = int(scalar)
    if dimension <= 0 or dimension > maximum:
        raise ValueError(f"ELOPE {name} must be in [1, {maximum}]")
    return dimension


def read_advertised_geometry(input_path: Path) -> SensorGeometry | None:
    """Read an unambiguous width/height metadata pair when present.

    Args:
        input_path: ELOPE NPZ input.

    Returns:
        Advertised geometry, or ``None`` when the file has no geometry keys.

    Raises:
        ValueError: If metadata is partial, invalid, or conflicting.
    """
    advertised: SensorGeometry | None = None
    with np.load(input_path, allow_pickle=False) as dataset:
        for width_key, height_key in GEOMETRY_KEY_PAIRS:
            has_width = width_key in dataset
            has_height = height_key in dataset
            if has_width != has_height:
                raise ValueError(
                    "ELOPE geometry metadata must provide both "
                    f"'{width_key}' and '{height_key}'"
                )
            if not has_width:
                continue

            candidate = SensorGeometry(
                width=normalize_sensor_dimension(
                    width_key, dataset[width_key], np.iinfo(np.uint16).max
                ),
                height=normalize_sensor_dimension(
                    height_key, dataset[height_key], 32767
                ),
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


def resolve_sensor_geometry(input_path: Path,
                            width_override: int | None,
                            height_override: int | None) -> SensorGeometry:
    """Resolve geometry without inferring it from observed event coordinates.

    Args:
        input_path: ELOPE NPZ input.
        width_override: Optional explicit sensor width.
        height_override: Optional explicit sensor height.

    Returns:
        Dataset geometry, a validated explicit override, or the ELOPE default.

    Raises:
        ValueError: If overrides are partial, invalid, or conflict with
            advertised metadata.
    """
    if (width_override is None) != (height_override is None):
        raise ValueError("width and height overrides must be provided together")

    advertised = read_advertised_geometry(input_path)
    if width_override is not None and height_override is not None:
        override = SensorGeometry(
            width=normalize_sensor_dimension(
                "width override", width_override, np.iinfo(np.uint16).max
            ),
            height=normalize_sensor_dimension(
                "height override", height_override, 32767
            ),
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

    if advertised is not None:
        return advertised
    return SensorGeometry(
        width=ELOPE_DEFAULT_WIDTH,
        height=ELOPE_DEFAULT_HEIGHT,
        source="elope_contract",
    )


def load_elope_events(input_path: Path,
                      width: int,
                      height: int) -> tuple[np.ndarray, np.ndarray,
                                           np.ndarray, np.ndarray,
                                           list[str]]:
    """Load and validate only the event data required by EKLT playback.

    Args:
        input_path: ELOPE NPZ file.
        width: Fixed sensor width.
        height: Fixed sensor height.

    Returns:
        X, Y, polarity-bit, microsecond-timestamp arrays and available NPZ keys.

    Raises:
        ValueError: If the event array or tuple contract is invalid.
    """
    with np.load(input_path, allow_pickle=False) as dataset:
        available_keys = sorted(dataset.files)
        if "events" not in dataset:
            raise ValueError("ELOPE input does not contain an 'events' array")
        events = np.asarray(dataset["events"])

    if events.dtype.names is not None:
        required_fields = ("x", "y", "p", "t")
        missing_fields = [
            field for field in required_fields if field not in events.dtype.names
        ]
        if missing_fields:
            raise ValueError(
                f"ELOPE structured events are missing fields: {missing_fields}"
            )
        x_values = events["x"]
        y_values = events["y"]
        polarity_values = events["p"]
        timestamp_values = events["t"]
    else:
        if events.ndim != 2 or events.shape[1] < 4:
            raise ValueError(
                "ELOPE events must be structured x/y/p/t data or an Nx4 matrix"
            )
        x_values = events[:, 0]
        y_values = events[:, 1]
        polarity_values = events[:, 2]
        timestamp_values = events[:, 3]

    # Normalize once up front so every packet is encoded from fixed-width,
    # contiguous arrays without retaining a second encoded event history.
    x_coordinates = normalize_integer_column(
        "x", x_values, minimum=0, maximum=width - 1
    ).astype(np.uint16)
    y_coordinates = normalize_integer_column(
        "y", y_values, minimum=0, maximum=height - 1
    ).astype(np.uint16)
    polarities = normalize_polarities(polarity_values)
    timestamps_us = normalize_integer_column(
        "timestamp", timestamp_values, minimum=0, maximum=INT64_MAX // 1000
    )

    event_count = timestamps_us.size
    if (
        x_coordinates.size != event_count
        or y_coordinates.size != event_count
        or polarities.size != event_count
    ):
        raise ValueError("ELOPE event columns have inconsistent lengths")
    if event_count == 0:
        raise ValueError("ELOPE event array is empty")
    if event_count > 1 and bool(np.any(timestamps_us[1:] < timestamps_us[:-1])):
        raise ValueError("ELOPE event timestamps must be monotonic")

    return (
        np.ascontiguousarray(x_coordinates),
        np.ascontiguousarray(y_coordinates),
        polarities,
        timestamps_us,
        available_keys,
    )


def encode_mono_payload(x_coordinates: np.ndarray,
                        y_coordinates: np.ndarray,
                        polarities: np.ndarray,
                        timestamps_ns: np.ndarray) -> np.ndarray:
    """Encode one time-bounded event slice in the standard mono layout.

    Args:
        x_coordinates: Event x coordinates.
        y_coordinates: Event y coordinates.
        polarities: Zero for OFF and one for ON.
        timestamps_ns: Monotonic nanosecond timestamps.

    Returns:
        Native-endian payload bytes accepted by ``event_camera_codecs``.

    Raises:
        ValueError: If the packet timestamp delta exceeds uint32 range.
    """
    if timestamps_ns.size == 0:
        return np.empty(0, dtype=np.uint8)

    deltas_ns = timestamps_ns - timestamps_ns[0]
    if int(deltas_ns[-1]) > int(UINT32_MAX):
        raise ValueError("mono EventPacket slice exceeds uint32 nanosecond range")

    packed_events = (
        polarities.astype(np.uint64) << np.uint64(63)
        | y_coordinates.astype(np.uint64) << np.uint64(48)
        | x_coordinates.astype(np.uint64) << np.uint64(32)
        | deltas_ns.astype(np.uint64)
    )
    native_dtype = np.dtype(">u8" if sys.byteorder == "big" else "<u8")
    return packed_events.astype(native_dtype, copy=False).view(np.uint8).copy()


def convert_elope(input_path: Path,
                  output_path: Path,
                  output_topic: str,
                  summary_path: Path | None,
                  width: int | None,
                  height: int | None,
                  frame_id: str,
                  dt_ms: float,
                  max_events_per_packet: int,
                  max_packets: int) -> ConversionStatistics:
    """Convert one ELOPE event array into an atomic ROS2 bag.

    Args:
        input_path: ELOPE NPZ input.
        output_path: New ROS2 bag directory, which must not exist.
        output_topic: Absolute EventPacket topic.
        summary_path: Optional JSON summary.
        width: Optional explicit sensor width.
        height: Optional explicit sensor height.
        frame_id: Packet header frame identifier.
        dt_ms: Maximum packet time span in milliseconds.
        max_events_per_packet: Maximum events stored in one packet.
        max_packets: Optional packet limit; zero is unlimited.

    Returns:
        Completed conversion statistics.

    Raises:
        FileExistsError: If the final or staging directory already exists.
        ValueError: If source data or conversion bounds are invalid.
    """
    if output_path.exists():
        raise FileExistsError(f"output already exists: {output_path}")
    if not output_topic.startswith("/"):
        raise ValueError("output_topic must be absolute")
    if not math.isfinite(dt_ms) or dt_ms <= 0.0:
        raise ValueError("dt_ms must be positive and finite")
    if max_events_per_packet <= 0:
        raise ValueError("max_events_per_packet must be positive")
    if max_packets < 0:
        raise ValueError("max_packets must be nonnegative")

    # Prefer dimensions carried explicitly by the dataset. The ELOPE contract
    # supplies 200-by-200 when the NPZ contains only pixel coordinates.
    geometry = resolve_sensor_geometry(input_path, width, height)
    x_values, y_values, polarity_values, timestamps_us, available_keys = (
        load_elope_events(input_path, geometry.width, geometry.height)
    )
    window_ns = int(round(dt_ms * 1_000_000.0))
    if window_ns <= 0 or window_ns > int(UINT32_MAX):
        raise ValueError("--dt-ms must map to (0, uint32_max] nanoseconds")

    output_path.parent.mkdir(parents=True, exist_ok=True)
    staging_root = output_path.with_name(
        f".{output_path.name}.staging-{os.getpid()}"
    )
    partial_path = staging_root / output_path.name
    if staging_root.exists():
        raise FileExistsError(f"temporary output already exists: {staging_root}")
    staging_root.mkdir()

    output_store = get_typestore(Stores.ROS2_JAZZY)
    output_store.register(
        get_types_from_msg(EVENT_PACKET_DEFINITION, EVENT_PACKET_TYPE)
    )
    event_packet_class = output_store.types[EVENT_PACKET_TYPE]
    header_class = output_store.types["std_msgs/msg/Header"]
    time_class = output_store.types["builtin_interfaces/msg/Time"]

    statistics = ConversionStatistics(
        input=str(input_path),
        output=str(output_path),
        output_topic=output_topic,
        width=geometry.width,
        height=geometry.height,
        geometry_source=geometry.source,
        frame_id=frame_id,
        dt_ms=dt_ms,
        max_events_per_packet=max_events_per_packet,
        max_packets=max_packets,
        available_keys=available_keys,
        source_event_count=int(timestamps_us.size),
    )

    # Bound each encoded allocation by both time and event count while
    # preserving source order and equal-timestamp order.
    cursor = 0
    try:
        with Writer(partial_path, version=9) as writer:
            output_connection = writer.add_connection(
                output_topic,
                EVENT_PACKET_TYPE,
                typestore=output_store,
            )
            while cursor < timestamps_us.size:
                if max_packets > 0 and statistics.event_packets >= max_packets:
                    break

                first_timestamp_ns = int(timestamps_us[cursor]) * 1000
                time_limit_us = (
                    first_timestamp_ns + window_ns + 999
                ) // 1000
                time_end = int(
                    np.searchsorted(
                        timestamps_us, time_limit_us, side="left"
                    )
                )
                packet_end = min(
                    max(time_end, cursor + 1),
                    cursor + max_events_per_packet,
                    int(timestamps_us.size),
                )
                packet_timestamps_ns = (
                    timestamps_us[cursor:packet_end] * np.int64(1000)
                )
                packet = event_packet_class(
                    header=header_class(
                        stamp=time_class(
                            sec=int(first_timestamp_ns // 1_000_000_000),
                            nanosec=int(first_timestamp_ns % 1_000_000_000),
                        ),
                        frame_id=frame_id,
                    ),
                    height=geometry.height,
                    width=geometry.width,
                    seq=statistics.event_packets,
                    time_base=first_timestamp_ns,
                    encoding="mono",
                    is_bigendian=sys.byteorder == "big",
                    events=encode_mono_payload(
                        x_values[cursor:packet_end],
                        y_values[cursor:packet_end],
                        polarity_values[cursor:packet_end],
                        packet_timestamps_ns,
                    ),
                )
                writer.write(
                    output_connection,
                    first_timestamp_ns,
                    output_store.serialize_cdr(packet, EVENT_PACKET_TYPE),
                )
                statistics.update_events(packet_timestamps_ns)
                cursor = packet_end

        partial_path.rename(output_path)
        staging_root.rmdir()
    except BaseException:
        if staging_root.exists():
            shutil.rmtree(staging_root)
        raise

    if summary_path is not None:
        summary_path.parent.mkdir(parents=True, exist_ok=True)
        summary_path.write_text(
            json.dumps(statistics.to_dict(), indent=2, sort_keys=True) + "\n",
            encoding="utf-8",
        )
    return statistics


def parse_arguments(argv: Sequence[str] | None = None) -> argparse.Namespace:
    """Parse command-line arguments.

    Args:
        argv: Optional arguments without the program name.

    Returns:
        Parsed converter options.
    """
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input", required=True, type=Path)
    parser.add_argument("--output", required=True, type=Path)
    parser.add_argument("--output-topic", default="/events")
    parser.add_argument("--summary-output", type=Path)
    parser.add_argument(
        "--width",
        type=int,
        help="optional width override; must match advertised NPZ metadata",
    )
    parser.add_argument(
        "--height",
        type=int,
        help="optional height override; must match advertised NPZ metadata",
    )
    parser.add_argument("--frame-id", default="event_camera")
    parser.add_argument("--dt-ms", type=float, default=20.0)
    parser.add_argument("--max-events-per-packet", type=int, default=100_000)
    parser.add_argument("--max-packets", type=int, default=0)
    return parser.parse_args(argv)


def main(argv: Sequence[str] | None = None) -> int:
    """Run ELOPE-to-EventPacket conversion.

    Args:
        argv: Optional arguments without the program name.

    Returns:
        Zero after a successful conversion.
    """
    arguments = parse_arguments(argv)
    if not arguments.input.is_file():
        raise FileNotFoundError(f"ELOPE input not found: {arguments.input}")
    if not arguments.output_topic.startswith("/"):
        raise ValueError("--output-topic must be absolute")
    if arguments.max_events_per_packet <= 0:
        raise ValueError("--max-events-per-packet must be positive")
    if arguments.max_packets < 0:
        raise ValueError("--max-packets must be nonnegative")

    statistics = convert_elope(
        input_path=arguments.input.resolve(),
        output_path=arguments.output,
        output_topic=arguments.output_topic,
        summary_path=arguments.summary_output,
        width=arguments.width,
        height=arguments.height,
        frame_id=arguments.frame_id,
        dt_ms=arguments.dt_ms,
        max_events_per_packet=arguments.max_events_per_packet,
        max_packets=arguments.max_packets,
    )
    print(
        f"converted {statistics.event_count} ELOPE events to "
        f"{statistics.event_packets} ROS2 EventPacket messages"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
