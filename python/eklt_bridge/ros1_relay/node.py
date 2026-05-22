"""ROS1 relay that decodes bridge event batches into EKLT-compatible topics."""

from __future__ import annotations

import argparse

from ..config import load_stage2a_config
from ..messages import decode_event_batch


def _import_ros1_modules():
    import rospy
    from dvs_msgs.msg import Event, EventArray
    from sensor_msgs.msg import Image
    from std_msgs.msg import UInt8MultiArray

    return rospy, Event, EventArray, Image, UInt8MultiArray


class Ros1RelayNode:
    """Relay node that republishes frames and converts encoded event batches into dvs_msgs."""

    def __init__(self, config_path: str) -> None:
        rospy, event_type, event_array_type, image_type, packet_type = _import_ros1_modules()

        self._rospy = rospy
        self._event_type = event_type
        self._event_array_type = event_array_type
        self._image_type = image_type
        self._packet_type = packet_type
        self._config = load_stage2a_config(config_path)

        self._rospy.init_node("eklt_ros1_relay", anonymous=False)
        self._events_publisher = self._rospy.Publisher(self._config.topics.ros1_events, event_array_type, queue_size=10)
        self._image_publisher = self._rospy.Publisher(self._config.topics.ros1_image, image_type, queue_size=10)

        self._rospy.Subscriber(self._config.topics.events, packet_type, self._event_callback, queue_size=10)
        self._rospy.Subscriber(self._config.topics.image, image_type, self._image_callback, queue_size=10)

    def spin(self) -> None:
        """Enter the ROS1 callback loop."""

        self._rospy.spin()

    def _event_callback(self, message) -> None:
        batch = decode_event_batch(bytes(message.data))

        event_array = self._event_array_type()
        event_array.width = int(batch.width)
        event_array.height = int(batch.height)
        event_array.events = []

        for timestamp_ns, x, y, p01 in zip(batch.timestamp_ns, batch.x, batch.y, batch.p01):
            ros_event = self._event_type()
            ros_event.x = int(x)
            ros_event.y = int(y)
            ros_event.ts = self._to_ros_time(int(timestamp_ns))
            ros_event.polarity = bool(p01)
            event_array.events.append(ros_event)

        event_array.header.stamp = self._to_ros_time(batch.stamp_ns)

        self._events_publisher.publish(event_array)

    def _image_callback(self, message) -> None:
        self._image_publisher.publish(message)

    def _to_ros_time(self, timestamp_ns: int):
        seconds = int(timestamp_ns // 1_000_000_000)
        nanoseconds = int(timestamp_ns % 1_000_000_000)
        return self._rospy.Time(secs=seconds, nsecs=nanoseconds)


def main() -> int:
    """CLI entrypoint for the ROS1 relay node."""

    parser = argparse.ArgumentParser(description="Decode bridge event batches into ROS1 dvs_msgs topics.")
    parser.add_argument("--config", required=True, help="Path to the stage-2 bridge JSON config.")
    args = parser.parse_args()

    node = Ros1RelayNode(args.config)
    node.spin()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
