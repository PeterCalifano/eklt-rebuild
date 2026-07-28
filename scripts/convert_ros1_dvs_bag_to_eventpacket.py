"""Convert a ROS1 DVS EventArray bag into a ROS2 EventPacket bag.

The converter reads only the selected legacy event topic and writes standard
``event_camera_msgs/msg/EventPacket`` messages using the mono codec understood
by ``event_camera_codecs``. It does not require a running ROS graph.

Example:
    python scripts/convert_ros1_dvs_bag_to_eventpacket.py \
        --input data/eklt_example/boxes_6dof.bag \
        --output outputs/boxes_6dof_eventpacket \
        --input-topic /dvs/events \
        --output-topic /events

Output:
    converted 1794 legacy messages to ROS2 EventPacket
"""

from __future__ import annotations

import argparse
import json
import os
import shutil
import sys
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any, Sequence

import numpy as np
from rosbags.highlevel import AnyReader
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


@dataclass
class ConversionStatistics:
    """Accumulate bounded conversion evidence for the output summary.

    Attributes:
        input: Source ROS1 bag path.
        output: Destination ROS2 bag directory.
        input_topic: Converted legacy event topic.
        output_topic: Written EventPacket topic.
        message_limit: Requested source-message limit; zero means unlimited.
        encoding: EventPacket encoding name.
        legacy_messages: Number of source messages read.
        event_packets: Number of destination packets written.
        event_count: Total encoded change-of-contrast events.
        width: Validated fixed sensor width.
        height: Validated fixed sensor height.
        first_event_ns: Earliest encoded event timestamp.
        last_event_ns: Latest encoded event timestamp.
    """

    input: str
    output: str
    input_topic: str
    output_topic: str
    message_limit: int
    encoding: str = "mono"
    legacy_messages: int = 0
    event_packets: int = 0
    event_count: int = 0
    width: int = 0
    height: int = 0
    first_event_ns: int | None = None
    last_event_ns: int | None = None

    def update_events(self, timestamps_ns: np.ndarray) -> None:
        """Record one non-empty packet timestamp span.

        Args:
            timestamps_ns: Monotonic event timestamps in nanoseconds.
        """
        first_timestamp = int(timestamps_ns[0])
        last_timestamp = int(timestamps_ns[-1])
        if self.first_event_ns is None:
            self.first_event_ns = first_timestamp
        self.last_event_ns = last_timestamp
        self.event_count += int(timestamps_ns.size)

    def to_dict(self) -> dict[str, object]:
        """Return a JSON-ready conversion summary.

        Returns:
            Conversion fields plus the represented event duration.
        """
        summary = asdict(self)
        duration_ns = 0
        if self.first_event_ns is not None and self.last_event_ns is not None:
            duration_ns = self.last_event_ns - self.first_event_ns
        summary["duration_s"] = duration_ns / 1_000_000_000.0
        summary["status"] = "passed"
        return summary


def time_to_nanoseconds(time_message: Any) -> int:
    """Convert a ROS-compatible time object to integer nanoseconds.

    Args:
        time_message: Object exposing integer ``sec`` and ``nanosec`` fields.

    Returns:
        Timestamp in nanoseconds.
    """
    return int(time_message.sec) * 1_000_000_000 + int(time_message.nanosec)


def ordered_event_columns(message: Any) -> tuple[np.ndarray, np.ndarray, np.ndarray, np.ndarray]:
    """Extract and deterministically order one legacy EventArray message.

    Args:
        message: Deserialized ``dvs_msgs/msg/EventArray`` instance.

    Returns:
        Tuple of x, y, signed polarity bit, and nanosecond timestamp arrays.

    Raises:
        ValueError: If geometry or event coordinates violate codec limits.
    """
    width = int(message.width)
    height = int(message.height)
    if width <= 0 or width > np.iinfo(np.uint16).max:
        raise ValueError(f"unsupported EventArray width: {width}")
    if height <= 0 or height > 32767:
        raise ValueError(f"unsupported mono EventPacket height: {height}")

    event_count = len(message.events)
    x_coordinates_i64 = np.fromiter(
        (int(event.x) for event in message.events),
        dtype=np.int64,
        count=event_count,
    )
    y_coordinates_i64 = np.fromiter(
        (int(event.y) for event in message.events),
        dtype=np.int64,
        count=event_count,
    )
    polarities = np.fromiter(
        (1 if bool(event.polarity) else 0 for event in message.events),
        dtype=np.uint8,
        count=event_count,
    )
    timestamps_ns = np.fromiter(
        (time_to_nanoseconds(event.ts) for event in message.events),
        dtype=np.int64,
        count=event_count,
    )

    if (
        np.any(x_coordinates_i64 < 0)
        or np.any(x_coordinates_i64 >= width)
        or np.any(y_coordinates_i64 < 0)
        or np.any(y_coordinates_i64 >= height)
        or np.any(timestamps_ns < 0)
    ):
        raise ValueError("legacy EventArray contains invalid coordinates or timestamps")
    x_coordinates = x_coordinates_i64.astype(np.uint16)
    y_coordinates = y_coordinates_i64.astype(np.uint16)

    # Preserve equal-time input order while normalizing any legacy packet whose
    # internal event order is not already monotonic.
    if timestamps_ns.size > 1 and np.any(timestamps_ns[1:] < timestamps_ns[:-1]):
        order = np.argsort(timestamps_ns, kind="stable")
        x_coordinates = x_coordinates[order]
        y_coordinates = y_coordinates[order]
        polarities = polarities[order]
        timestamps_ns = timestamps_ns[order]

    return x_coordinates, y_coordinates, polarities, timestamps_ns


def encode_mono_payload(x_coordinates: np.ndarray,
                        y_coordinates: np.ndarray,
                        polarities: np.ndarray,
                        timestamps_ns: np.ndarray) -> np.ndarray:
    """Encode one uint32-relative time slice with the standard mono layout.

    Args:
        x_coordinates: Event x coordinates.
        y_coordinates: Event y coordinates.
        polarities: Zero for OFF and one for ON events.
        timestamps_ns: Monotonic nanosecond timestamps.

    Returns:
        Native-endian bytes for ``event_camera_codecs`` mono decoding.

    Raises:
        ValueError: If the timestamp slice exceeds the mono delta range.
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


def convert_bag(input_path: Path,
                output_path: Path,
                input_topic: str,
                output_topic: str,
                summary_path: Path | None,
                max_messages: int) -> ConversionStatistics:
    """Convert one legacy DVS topic into an atomic ROS2 bag directory.

    Args:
        input_path: ROS1 version-2 bag file.
        output_path: New ROS2 bag directory, which must not exist.
        input_topic: Legacy ``dvs_msgs/EventArray`` topic.
        output_topic: ROS2 ``EventPacket`` topic.
        summary_path: Optional JSON summary path.
        max_messages: Optional positive legacy-message limit; zero is unlimited.

    Returns:
        Completed conversion statistics.

    Raises:
        FileExistsError: If the requested output already exists.
        ValueError: If a topic is relative or the message limit is negative.
        RuntimeError: If the input topic is missing or timestamps regress
            between legacy messages.
    """
    if output_path.exists():
        raise FileExistsError(f"output already exists: {output_path}")
    if not input_topic.startswith("/") or not output_topic.startswith("/"):
        raise ValueError("input and output topics must be absolute")
    if max_messages < 0:
        raise ValueError("max_messages must be nonnegative")

    output_path.parent.mkdir(parents=True, exist_ok=True)
    staging_root = output_path.with_name(f".{output_path.name}.staging-{os.getpid()}")
    partial_path = staging_root / output_path.name
    if staging_root.exists():
        raise FileExistsError(f"temporary output already exists: {staging_root}")
    staging_root.mkdir()

    output_store = get_typestore(Stores.ROS2_JAZZY)
    output_store.register(get_types_from_msg(EVENT_PACKET_DEFINITION, EVENT_PACKET_TYPE))
    event_packet_class = output_store.types[EVENT_PACKET_TYPE]
    header_class = output_store.types["std_msgs/msg/Header"]
    time_class = output_store.types["builtin_interfaces/msg/Time"]

    statistics = ConversionStatistics(
        input=str(input_path),
        output=str(output_path),
        input_topic=input_topic,
        output_topic=output_topic,
        message_limit=max_messages,
    )
    sequence = 0
    previous_event_ns = -1

    try:
        with AnyReader([input_path]) as reader:
            connections = [
                connection
                for connection in reader.connections
                if connection.topic == input_topic
                and connection.msgtype == "dvs_msgs/msg/EventArray"
            ]
            if not connections:
                raise RuntimeError(
                    f"{input_topic} with type dvs_msgs/EventArray is absent from {input_path}"
                )

            with Writer(partial_path, version=9) as writer:
                output_connection = writer.add_connection(
                    output_topic,
                    EVENT_PACKET_TYPE,
                    typestore=output_store,
                )
                for connection, record_timestamp, raw_data in reader.messages(
                    connections=connections
                ):
                    if max_messages > 0 and statistics.legacy_messages >= max_messages:
                        break

                    message = reader.deserialize(raw_data, connection.msgtype)
                    message_width = int(message.width)
                    message_height = int(message.height)
                    if statistics.width == 0 and statistics.height == 0:
                        statistics.width = message_width
                        statistics.height = message_height
                    elif (
                        message_width != statistics.width
                        or message_height != statistics.height
                    ):
                        raise RuntimeError(
                            "legacy EventArray geometry changed during conversion"
                        )

                    x_values, y_values, polarity_values, timestamps_ns = (
                        ordered_event_columns(message)
                    )
                    statistics.legacy_messages += 1
                    if timestamps_ns.size == 0:
                        continue
                    if int(timestamps_ns[0]) < previous_event_ns:
                        raise RuntimeError(
                            "legacy event timestamps regress between EventArray messages"
                        )

                    start = 0
                    while start < timestamps_ns.size:
                        time_limit = int(timestamps_ns[start]) + int(UINT32_MAX)
                        end = int(np.searchsorted(timestamps_ns, time_limit, side="right"))
                        packet_timestamps = timestamps_ns[start:end]
                        packet = event_packet_class(
                            header=header_class(
                                stamp=time_class(
                                    sec=int(record_timestamp // 1_000_000_000),
                                    nanosec=int(record_timestamp % 1_000_000_000),
                                ),
                                frame_id=str(message.header.frame_id),
                            ),
                            height=int(message.height),
                            width=int(message.width),
                            seq=sequence,
                            time_base=int(packet_timestamps[0]),
                            encoding="mono",
                            is_bigendian=sys.byteorder == "big",
                            events=encode_mono_payload(
                                x_values[start:end],
                                y_values[start:end],
                                polarity_values[start:end],
                                packet_timestamps,
                            ),
                        )
                        writer.write(
                            output_connection,
                            int(record_timestamp),
                            output_store.serialize_cdr(packet, EVENT_PACKET_TYPE),
                        )
                        statistics.update_events(packet_timestamps)
                        statistics.event_packets += 1
                        sequence += 1
                        start = end

                    previous_event_ns = int(timestamps_ns[-1])
                    if statistics.legacy_messages % 100 == 0:
                        print(
                            f"converted {statistics.legacy_messages} messages, "
                            f"{statistics.event_count} events",
                            flush=True,
                        )

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
        argv: Optional argument sequence without the program name.

    Returns:
        Parsed conversion options.
    """
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input", required=True, type=Path)
    parser.add_argument("--output", required=True, type=Path)
    parser.add_argument("--input-topic", default="/dvs/events")
    parser.add_argument("--output-topic", default="/events")
    parser.add_argument("--summary-output", type=Path)
    parser.add_argument("--max-messages", type=int, default=0)
    return parser.parse_args(argv)


def main(argv: Sequence[str] | None = None) -> int:
    """Run the ROS1-to-ROS2 event bag conversion.

    Args:
        argv: Optional argument sequence without the program name.

    Returns:
        Zero after successful conversion.
    """
    arguments = parse_arguments(argv)
    if not arguments.input.is_file():
        raise FileNotFoundError(f"input bag not found: {arguments.input}")
    if arguments.max_messages < 0:
        raise ValueError("--max-messages must be nonnegative")

    statistics = convert_bag(
        input_path=arguments.input,
        output_path=arguments.output,
        input_topic=arguments.input_topic,
        output_topic=arguments.output_topic,
        summary_path=arguments.summary_output,
        max_messages=arguments.max_messages,
    )
    print(
        f"converted {statistics.legacy_messages} legacy messages to ROS2 EventPacket"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
