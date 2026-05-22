"""ROS2 source node that publishes frames and generic event batches."""

from __future__ import annotations

import argparse
import time

from ..config import load_stage2a_config
from ..messages import encode_event_batch
from ..runtime import BridgePipeline


def _import_ros2_modules():
    import rclpy
    from rclpy.node import Node
    from sensor_msgs.msg import Image
    from std_msgs.msg import UInt8MultiArray

    return rclpy, Node, Image, UInt8MultiArray


def _split_timestamp_ns(timestamp_ns: int) -> tuple[int, int]:
    seconds, nanoseconds = divmod(int(timestamp_ns), 1_000_000_000)
    return seconds, nanoseconds


def _step_timestamp_ns(step) -> int:
    if step.frame is not None:
        return int(step.frame.timestamp_ns)
    if step.events is not None:
        return int(step.events.stamp_ns)
    return 0


class SequenceSourceNode:
    """ROS2 source node that publishes frames, previews, and encoded event batches."""

    def __init__(self, config_path: str) -> None:
        rclpy, node_type, image_type, packet_type = _import_ros2_modules()

        self._rclpy = rclpy
        self._image_type = image_type
        self._packet_type = packet_type
        self._config = load_stage2a_config(config_path)
        self._pipeline = BridgePipeline(self._config)

        self._rclpy.init()
        self._node = node_type("eklt_sequence_source")
        self._event_publisher = self._node.create_publisher(
            packet_type, self._config.topics.events, 10)
        self._image_publisher = self._node.create_publisher(
            image_type, self._config.topics.image, 10)
        self._rendered_frame_publisher = self._node.create_publisher(
            image_type,
            self._config.topics.rendered_frame,
            10,
        )
        self._event_preview_publisher = self._node.create_publisher(
            image_type,
            self._config.topics.event_preview,
            10,
        )

    def destroy(self) -> None:
        """Clean up ROS2 resources."""

        self._node.destroy_node()
        self._rclpy.shutdown()

    def run(self) -> None:
        """Publish the configured sequence once or in a loop."""

        steps = self._pipeline.build_steps()
        if not steps:
            return

        realtime_factor = float(self._config.runtime.realtime_factor)
        if realtime_factor <= 0.0:
            raise ValueError("runtime.realtime_factor must be positive.")

        while self._rclpy.ok():
            for index, step in enumerate(steps):
                if step.frame is not None and (index > 0 or self._config.runtime.publish_first_frame):
                    image_msg = self._build_image_msg(
                        step.frame.timestamp_ns, step.frame.image_mono8)
                    self._image_publisher.publish(image_msg)
                    self._rendered_frame_publisher.publish(image_msg)

                if step.events is not None:
                    packet_msg = self._packet_type()
                    packet_msg.data = list(encode_event_batch(step.events))
                    self._event_publisher.publish(packet_msg)

                    if step.event_preview_mono8 is not None:
                        preview_msg = self._build_image_msg(step.events.stamp_ns, step.event_preview_mono8)
                        self._event_preview_publisher.publish(preview_msg)

                self._rclpy.spin_once(self._node, timeout_sec=0.0)
                self._sleep_until_next_step(index, steps, realtime_factor)

            if not self._config.runtime.loop_forever:
                break

    def _build_image_msg(self, timestamp_ns: int, image_mono8) -> object:
        message = self._image_type()
        seconds, nanoseconds = _split_timestamp_ns(timestamp_ns)
        message.header.stamp.sec = int(seconds)
        message.header.stamp.nanosec = int(nanoseconds)
        message.height = int(image_mono8.shape[0])
        message.width = int(image_mono8.shape[1])
        message.encoding = "mono8"
        message.is_bigendian = 0
        message.step = int(image_mono8.shape[1])
        message.data = image_mono8.tobytes()
        return message

    def _sleep_until_next_step(self,
                               index: int,
                               steps: list,
                               realtime_factor: float) -> None:
        if index >= len(steps) - 1:
            return

        current_timestamp = _step_timestamp_ns(steps[index])
        next_timestamp = _step_timestamp_ns(steps[index + 1])
        sleep_seconds = max(
            0.0, (next_timestamp - current_timestamp) / 1.0e9 / realtime_factor)
        if sleep_seconds > 0.0:
            time.sleep(sleep_seconds)


def main() -> int:
    """CLI entrypoint for the ROS2 source node."""

    parser = argparse.ArgumentParser(
        description="Replay a configured source as ROS2 images and encoded event batches.")
    parser.add_argument("--config", required=True,
                        help="Path to the stage-2 bridge JSON config.")
    args = parser.parse_args()

    node = SequenceSourceNode(args.config)
    try:
        node.run()
    finally:
        node.destroy()

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
