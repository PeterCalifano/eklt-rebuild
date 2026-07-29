"""Render EKLT track samples as dots over event-camera activity.

The renderer consumes the transport-neutral EKLT text-track format and an
``EventArray``. Frames are generated and encoded incrementally so video memory
use does not grow with sequence duration.

Example:
    from pathlib import Path

    from event_vision_utils.core import EventArray
    from event_vision_utils.io import TrackSample

    events = EventArray(
        x=[0], y=[0], p=[1], t_us=[0], width=200, height=200
    )
    samples = [TrackSample(track_id=1, t_s=0.0, x=0.0, y=0.0)]
    result = write_track_dot_video(
        events, samples, Path("eklt_tracks.mp4"), fps=100.0, scale=4
    )
    print(result.video.frame_count)

Output:
    1
"""

from __future__ import annotations

import math
from collections.abc import Iterator, Sequence
from dataclasses import dataclass
from pathlib import Path

import numpy as np
from PIL import Image, ImageDraw

from event_vision_utils.core.event_array import EventArray
from event_vision_utils.io.track_file import TrackSample
from event_vision_utils.slicing import slice_by_time
from event_vision_utils.viz.polarity_image import render_polarity_rgb
from event_vision_utils.viz.video_writer import (
    VideoArtifact,
    write_video_or_png_sequence,
)


_MAX_TRACK_FRAME_PIXELS = 16_777_216


@dataclass(frozen=True, slots=True)
class TrackVideoArtifact:
    """Metadata for one streamed track-overlay video.

    Attributes:
        video: Encoded MP4 or PNG-sequence metadata.
        track_rows: Number of represented track observations.
        track_count: Number of distinct feature identifiers.
        boundary_clipped_track_rows: Number of observations clipped to the
            advertised sensor plane for rendering.
        event_window_us: Event accumulation duration per frame.
        track_hold_ms: Maximum displayed observation age.
        dot_radius: Rendered dot radius in output pixels.
        scale: Integer sensor-image enlargement factor.

    Example:
        artifact = TrackVideoArtifact(
            video=VideoArtifact(
                kind="mp4", path="tracks.mp4", frame_count=10,
                width=800, height=800, fps=100.0
            ),
            track_rows=20,
            track_count=3,
            boundary_clipped_track_rows=0,
            event_window_us=10_000,
            track_hold_ms=100.0,
            dot_radius=5,
            scale=4,
        )
        print(artifact.video.kind, artifact.track_count)

    Output:
        mp4 3
    """

    video: VideoArtifact
    track_rows: int
    track_count: int
    boundary_clipped_track_rows: int
    event_window_us: int
    track_hold_ms: float
    dot_radius: int
    scale: int

    def as_dict(self) -> dict[str, str | int | float | None]:
        """Return flattened JSON-compatible track-video metadata.

        Returns:
            Video and track policy fields for an artifact summary.

        Example:
            artifact = TrackVideoArtifact(
                video=VideoArtifact(
                    kind="mp4", path="tracks.mp4", frame_count=10,
                    width=800, height=800, fps=100.0
                ),
                track_rows=20,
                track_count=3,
                boundary_clipped_track_rows=0,
                event_window_us=10_000,
                track_hold_ms=100.0,
                dot_radius=5,
                scale=4,
            )
            print(artifact.as_dict()["track_count"])

        Output:
            3
        """
        return {
            **self.video.as_dict(),
            "track_rows": self.track_rows,
            "track_count": self.track_count,
            "boundary_clipped_track_rows": (
                self.boundary_clipped_track_rows
            ),
            "event_window_us": self.event_window_us,
            "track_hold_ms": self.track_hold_ms,
            "dot_radius": self.dot_radius,
            "scale": self.scale,
        }


def write_track_dot_video(events: EventArray,
                          tracks: Sequence[TrackSample],
                          output_path: str | Path,
                          *,
                          fps: float = 100.0,
                          scale: int = 4,
                          hold_ms: float = 100.0,
                          dot_radius: int = 5) -> TrackVideoArtifact:
    """Stream an event preview with recent EKLT tracks drawn as colored dots.

    Track observations are held for a bounded interval so updates produced
    below the video frame rate remain visible. Colors are derived only from the
    track identifier and therefore remain stable across runs. Finite native
    estimates outside the advertised pixel-center plane are preserved in the
    source observations and clipped only for display.

    Args:
        events: Validated event stream defining geometry and video time.
        tracks: EKLT observations on the same timestamp timeline.
        output_path: MP4 path or PNG-sequence directory.
        fps: Video frame rate and event accumulation rate.
        scale: Integer image enlargement factor.
        hold_ms: Maximum age of a displayed track observation.
        dot_radius: Dot radius in enlarged output pixels.

    Returns:
        Typed video metadata including dimensions, frame count, and track
        policy.

    Raises:
        ValueError: If inputs are empty, invalid, or have disjoint timelines.

    Example:
        events = EventArray(
            x=[0], y=[0], p=[1], t_us=[0], width=200, height=200
        )
        tracks = [
            TrackSample(track_id=1, t_s=0.0, x=0.0, y=0.0)
        ]
        result = write_track_dot_video(
            events, tracks, Path("eklt_tracks.mp4"), fps=100.0, scale=4
        )
        print(result.video.width, result.video.height)

    Output:
        800 800
    """
    if events.size == 0:
        raise ValueError("at least one event is required")
    if not tracks:
        raise ValueError("at least one track observation is required")
    if not math.isfinite(fps) or not 0.0 < fps <= 1000.0:
        raise ValueError("fps must be finite and in (0, 1000]")
    if not 1 <= scale <= 8:
        raise ValueError("scale must be in [1, 8]")
    if (
        events.width * scale *
        events.height * scale > _MAX_TRACK_FRAME_PIXELS
    ):
        raise ValueError(
            "scaled track-video geometry exceeds the frame pixel limit"
        )
    if not math.isfinite(hold_ms) or hold_ms < 0.0:
        raise ValueError("hold_ms must be nonnegative and finite")
    if not 1 <= dot_radius <= 64:
        raise ValueError("dot_radius must be in [1, 64]")

    ordered_tracks = sorted(
        tracks,
        key=lambda sample: (sample.t_s, sample.track_id),
    )
    clipped_rows = _validate_track_samples(ordered_tracks,
                                           events.width,
                                           events.height)
    event_start_s = float(events.t_start_us) / 1_000_000.0
    event_end_s = float(events.t_end_us) / 1_000_000.0
    hold_s = hold_ms / 1000.0
    if (
        ordered_tracks[-1].t_s < event_start_s - hold_s or
        ordered_tracks[0].t_s > event_end_s
    ):
        raise ValueError("track and event timelines do not overlap")

    window_us = max(1, int(round(1_000_000.0 / fps)))
    video = write_video_or_png_sequence(
        _iter_track_frames(
            events,
            ordered_tracks,
            window_us=window_us,
            scale=scale,
            hold_s=hold_s,
            dot_radius=dot_radius,
        ),
        output_path,
        fps=fps,
    )
    return TrackVideoArtifact(
        video=video,
        track_rows=len(ordered_tracks),
        track_count=len(
            {sample.track_id for sample in ordered_tracks}
        ),
        boundary_clipped_track_rows=clipped_rows,
        event_window_us=window_us,
        track_hold_ms=hold_ms,
        dot_radius=dot_radius,
        scale=scale,
    )


def _iter_track_frames(events: EventArray,
                       tracks: Sequence[TrackSample],
                       *,
                       window_us: int,
                       scale: int,
                       hold_s: float,
                       dot_radius: int) -> Iterator[np.ndarray]:
    """Yield constant-size frames while retaining only currently visible tracks."""
    start_us = int(events.t_start_us)
    end_us = int(events.t_end_us) + 1
    active_tracks: dict[int, TrackSample] = {}
    track_index = 0

    for frame_start_us in range(start_us, end_us, window_us):
        frame_end_us = min(frame_start_us + window_us, end_us)
        frame_end_s = frame_end_us / 1_000_000.0

        # Apply every update causal to this frame, retaining only the latest
        # sample for each stable feature identifier.
        while (
            track_index < len(tracks) and
            tracks[track_index].t_s <= frame_end_s
        ):
            sample = tracks[track_index]
            active_tracks[sample.track_id] = sample
            track_index += 1
        active_tracks = {
            track_id: sample
            for track_id, sample in active_tracks.items()
            if frame_end_s - sample.t_s <= hold_s
        }

        chunk = slice_by_time(
            events,
            start_us=frame_start_us,
            end_us=frame_end_us,
            include_end=frame_end_us == end_us,
        )
        yield _render_track_frame(
            render_polarity_rgb(chunk),
            active_tracks,
            scale=scale,
            dot_radius=dot_radius,
            frame_time_s=frame_end_s,
        )


def _render_track_frame(base: np.ndarray,
                        active_tracks: dict[int, TrackSample],
                        *,
                        scale: int,
                        dot_radius: int,
                        frame_time_s: float) -> np.ndarray:
    """Enlarge one event frame and overlay its current track positions."""
    nearest = getattr(getattr(Image, "Resampling", Image), "NEAREST")
    source_height, source_width = base.shape[:2]
    image = Image.fromarray(base).resize(
        (source_width * scale, source_height * scale),
        resample=nearest,
    )
    draw = ImageDraw.Draw(image)

    # Draw an outline around each deterministic color so dots remain visible
    # over both white background and red/blue event pixels. Native subpixel
    # estimates remain unchanged in the source artifact; only their displayed
    # centers are clipped to the fixed sensor plane.
    for track_id, sample in sorted(active_tracks.items()):
        clipped_x = min(max(sample.x, 0.0),
                        float(source_width - 1))
        clipped_y = min(max(sample.y, 0.0),
                        float(source_height - 1))
        center_x = int(round(clipped_x * scale))
        center_y = int(round(clipped_y * scale))
        bounds = (
            center_x - dot_radius,
            center_y - dot_radius,
            center_x + dot_radius,
            center_y + dot_radius,
        )
        draw.ellipse(
            bounds,
            fill=_track_color(track_id),
            outline=(20, 20, 20),
            width=1,
        )

    label = f"t={frame_time_s:.3f}s  active tracks={len(active_tracks)}"
    label_bounds = draw.textbbox((0, 0), label)
    label_width = label_bounds[2] - label_bounds[0]
    label_height = label_bounds[3] - label_bounds[1]
    draw.rectangle(
        (3, 3, label_width + 9, label_height + 9),
        fill=(245, 245, 245),
    )
    draw.text((6, 6), label, fill=(20, 20, 20))
    return np.asarray(image, dtype=np.uint8)


def _validate_track_samples(tracks: Sequence[TrackSample],
                            width: int,
                            height: int) -> int:
    """Validate observations and count fixed-plane rendering clips."""
    previous_time = -math.inf
    maximum_x = float(width - 1)
    maximum_y = float(height - 1)
    boundary_clipped_track_rows = 0
    for sample in tracks:
        if sample.track_id < 0:
            raise ValueError("track ids must be nonnegative")
        if not all(
            math.isfinite(value)
            for value in (sample.t_s, sample.x, sample.y)
        ):
            raise ValueError("track values must be finite")
        if sample.t_s < previous_time:
            raise ValueError("track timestamps must be monotonic")
        if (
            not 0.0 <= sample.x <= maximum_x or
            not 0.0 <= sample.y <= maximum_y
        ):
            boundary_clipped_track_rows += 1
        previous_time = sample.t_s
    return boundary_clipped_track_rows


def _track_color(track_id: int) -> tuple[int, int, int]:
    """Return the native feature renderer's deterministic color in RGB order."""
    hash_value = (
        track_id * 2_654_435_761 + 2_246_822_519
    ) & 0xFFFFFFFF
    blue = 64 + (hash_value & 0x7F)
    green = 64 + ((hash_value >> 8) & 0x7F)
    red = 64 + ((hash_value >> 16) & 0x7F)
    return (
        red,
        green,
        blue,
    )
