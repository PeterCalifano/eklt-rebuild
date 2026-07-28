"""Expose EKLT-specific transport and source helpers.

This namespace remains separate from generic :mod:`event_vision_utils` modules
inside the unified ``eklt-rebuild`` distribution.
"""

from .config import (
    FrameSettings,
    RuntimeSettings,
    SequenceSettings,
    SourceSettings,
    Stage2AConfig,
    TopicNames,
    V2EEmulatorSettings,
    load_stage2a_config,
)
from .messages import (
    convert_frame_to_mono8,
    decode_event_batch,
    encode_event_batch,
    normalize_mono_frame_to_u8,
    rgba_to_mono_luminance,
)
from .primitives import EventStream, FrameEventSource, FrameEventStep, FrameSample
from .raytracer import import_spectral_rt_py, spectral_rt_py_search_paths

__all__ = [
    "EventStream",
    "FrameSettings",
    "FrameEventSource",
    "FrameEventStep",
    "FrameSample",
    "RuntimeSettings",
    "SequenceSettings",
    "SourceSettings",
    "Stage2AConfig",
    "TopicNames",
    "V2EEmulatorSettings",
    "convert_frame_to_mono8",
    "decode_event_batch",
    "encode_event_batch",
    "import_spectral_rt_py",
    "load_stage2a_config",
    "normalize_mono_frame_to_u8",
    "rgba_to_mono_luminance",
    "spectral_rt_py_search_paths",
]
