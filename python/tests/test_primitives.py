from __future__ import annotations

from types import SimpleNamespace

import numpy as np
import pytest

from eklt_bridge.primitives import EventStream


def test_event_stream_coerces_dataset_gen_dtypes() -> None:
    stream = EventStream(
        t_s=[0, 0.001],
        x=[1, 2],
        y=[3, 4],
        p01=[1, 0],
        signal_noise=[1, 1],
        width=10,
        height=12,
    )

    assert stream.t_s.dtype == np.float64
    assert stream.x.dtype == np.int32
    assert stream.y.dtype == np.int32
    assert stream.p01.dtype == np.uint8
    assert stream.signal_noise is not None
    assert stream.signal_noise.dtype == np.uint8


@pytest.mark.parametrize(
    ("kwargs", "match"),
    [
        ({"x": [1, 2]}, "same length"),
        ({"p01": [2]}, "p01"),
        ({"width": 0}, "width"),
        ({"height": 0}, "height"),
        ({"x": [10]}, "x coordinates"),
        ({"y": [12]}, "y coordinates"),
    ],
)
def test_event_stream_rejects_invalid_payloads(kwargs: dict, match: str) -> None:
    payload = {
        "t_s": [0.001],
        "x": [1],
        "y": [2],
        "p01": [1],
        "width": 10,
        "height": 12,
    }
    payload.update(kwargs)

    with pytest.raises(ValueError, match=match):
        EventStream(**payload)


def test_event_stream_from_timestamp_ns_round_trips_timestamp_helpers() -> None:
    stream = EventStream.from_timestamp_ns(
        np.array([1_200, 1_234], dtype=np.int64),
        x=np.array([4, 5]),
        y=np.array([7, 8]),
        p01=np.array([1, 0]),
        width=320,
        height=240,
        header_timestamp_ns=1_234,
    )

    np.testing.assert_array_equal(stream.timestamp_ns, np.array([1_200, 1_234], dtype=np.int64))
    assert stream.stamp_ns == 1_234
    assert stream.metadata["header_timestamp_ns"] == 1_234


def test_event_stream_from_v2e_events_maps_polarity_to_p01() -> None:
    events = np.array(
        [
            [0.001, 2, 3, 1],
            [0.002, 4, 5, -1],
            [0.003, 6, 7, 0],
        ],
        dtype=np.float64,
    )

    stream = EventStream.from_v2e_events(events, width=10, height=12, header_timestamp_ns=3_000_000)

    np.testing.assert_array_equal(stream.timestamp_ns, np.array([1_000_000, 2_000_000, 3_000_000]))
    np.testing.assert_array_equal(stream.p01, np.array([1, 0, 0], dtype=np.uint8))
    assert stream.source_format == "v2e"
    assert stream.stamp_ns == 3_000_000


def test_event_stream_duck_typed_dataset_gen_compatibility() -> None:
    dataset_stream = SimpleNamespace(
        t_s=np.array([0.001, 0.002], dtype=np.float64),
        x=np.array([1, 2], dtype=np.int32),
        y=np.array([3, 4], dtype=np.int32),
        p01=np.array([1, 0], dtype=np.uint8),
        signal_noise=None,
        width=10,
        height=12,
        source_format="txt",
        metadata={"source": "fixture"},
    )

    stream = EventStream.from_event_stream(dataset_stream, header_timestamp_ns=2_000_000)

    np.testing.assert_array_equal(stream.t_s, dataset_stream.t_s)
    np.testing.assert_array_equal(stream.p01, dataset_stream.p01)
    assert stream.width == 10
    assert stream.height == 12
    assert stream.source_format == "txt"
    assert stream.metadata["source"] == "fixture"
    assert stream.metadata["header_timestamp_ns"] == 2_000_000
