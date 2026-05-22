from __future__ import annotations

import json
from types import SimpleNamespace

import numpy as np

from eklt_bridge.messages import encode_event_batch
from eklt_bridge.primitives import EventStream
from eklt_bridge.ros1_relay import node as ros1_node


class _FakeEvent:
    pass


class _FakeEventArray:
    def __init__(self) -> None:
        self.header = SimpleNamespace(stamp=None)
        self.events = []
        self.width = 0
        self.height = 0


class _FakePublisher:
    def __init__(self) -> None:
        self.published = []

    def publish(self, message) -> None:
        self.published.append(message)


class _FakeRospy:
    def __init__(self) -> None:
        self.publishers = []
        self.subscribers = []

    def init_node(self, *args, **kwargs) -> None:
        pass

    def Publisher(self, *args, **kwargs) -> _FakePublisher:
        publisher = _FakePublisher()
        self.publishers.append(publisher)
        return publisher

    def Subscriber(self, *args, **kwargs) -> None:
        self.subscribers.append((args, kwargs))

    def Time(self, *, secs: int, nsecs: int):
        return SimpleNamespace(secs=secs, nsecs=nsecs)


def test_ros1_relay_converts_event_stream_p01_to_dvs_polarity(monkeypatch, tmp_path) -> None:
    fake_rospy = _FakeRospy()
    monkeypatch.setattr(
        ros1_node,
        "_import_ros1_modules",
        lambda: (fake_rospy, _FakeEvent, _FakeEventArray, object, object),
    )
    config_path = tmp_path / "stage2.json"
    config_path.write_text(json.dumps({}), encoding="utf-8")
    relay = ros1_node.Ros1RelayNode(str(config_path))

    stream = EventStream(
        t_s=np.array([1.2e-6, 1.234e-6], dtype=np.float64),
        x=np.array([4, 5], dtype=np.int32),
        y=np.array([7, 8], dtype=np.int32),
        p01=np.array([1, 0], dtype=np.uint8),
        width=320,
        height=240,
        metadata={"header_timestamp_ns": 1_234},
    )
    relay._event_callback(SimpleNamespace(data=list(encode_event_batch(stream))))

    published = relay._events_publisher.published[0]
    assert published.width == 320
    assert published.height == 240
    assert published.header.stamp.nsecs == 1_234
    assert [event.polarity for event in published.events] == [True, False]
    assert [event.ts.nsecs for event in published.events] == [1_200, 1_234]
