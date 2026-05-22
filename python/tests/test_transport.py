from __future__ import annotations

import pytest
import numpy as np

from eklt_bridge.messages import decode_event_batch, encode_event_batch
from eklt_bridge.primitives import EventStream


def test_transport_round_trip_preserves_event_stream_fields() -> None:
    stream = EventStream(
        t_s=np.array([0.0000012, 0.000001234], dtype=np.float64),
        x=np.array([4, 5], dtype=np.int32),
        y=np.array([7, 8], dtype=np.int32),
        p01=np.array([1, 0], dtype=np.uint8),
        width=320,
        height=240,
        metadata={"header_timestamp_ns": 1234, "source": "test"},
    )

    decoded = decode_event_batch(encode_event_batch(stream))

    assert decoded.width == 320
    assert decoded.height == 240
    assert decoded.stamp_ns == 1234
    assert decoded.metadata["source"] == "test"
    np.testing.assert_allclose(decoded.t_s, stream.t_s)
    np.testing.assert_array_equal(decoded.x, stream.x)
    np.testing.assert_array_equal(decoded.y, stream.y)
    np.testing.assert_array_equal(decoded.p01, stream.p01)


def test_transport_rejects_invalid_magic() -> None:
    with pytest.raises(ValueError):
        decode_event_batch(b"BAD!" + b"\x00" * 20)
