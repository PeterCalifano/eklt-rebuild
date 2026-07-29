"""Write bounded-memory videos or PNG sequences from image iterables.

Frames are consumed incrementally. MP4 output uses one ffmpeg thread, while
systems without ffmpeg receive a directory of numbered PNGs. Summaries retain
only aggregate metadata rather than one path per frame.

Example:
    from pathlib import Path

    import numpy as np

    result = write_video_or_png_sequence(
        [np.zeros((2, 2), dtype=np.uint8)],
        Path("frame.png"),
    )
    print(result.frame_count)

Output:
    1
"""

from __future__ import annotations

import os
import shutil
import subprocess
from collections.abc import Iterable, Iterator
from dataclasses import dataclass
from itertools import chain
from pathlib import Path

import numpy as np
from PIL import Image

from event_vision_utils.core.event_array import EventArray
from event_vision_utils.slicing import iter_time_slices
from event_vision_utils.viz.polarity_image import render_polarity_rgb
from event_vision_utils.viz.time_surface import render_time_surface_uint8


_MAX_ENCODED_FRAME_PIXELS = 16_777_216
_MAX_ENCODED_FRAMES = 1_000_000


@dataclass(frozen=True, slots=True)
class VideoArtifact:
    """Metadata for one encoded MP4, PNG, or PNG sequence.

    Attributes:
        kind: ``mp4``, ``png``, or ``png_sequence``.
        path: Published file or directory path.
        frame_count: Number of encoded frames.
        width: Encoded frame width in pixels.
        height: Encoded frame height in pixels.
        fps: Frame rate for time-based output, otherwise ``None``.

    Example:
        artifact = VideoArtifact(
            kind="png", path="frame.png", frame_count=1,
            width=8, height=6, fps=None
        )
        print(artifact.kind, artifact.frame_count)

    Output:
        png 1
    """

    kind: str
    path: str
    frame_count: int
    width: int
    height: int
    fps: float | None

    def as_dict(self) -> dict[str, str | int | float | None]:
        """Return stable JSON-compatible artifact metadata.

        Returns:
            Video fields keyed by their artifact-schema names.

        Example:
            artifact = VideoArtifact(
                kind="png", path="frame.png", frame_count=1,
                width=8, height=6, fps=None
            )
            print(artifact.as_dict()["path"])

        Output:
            frame.png
        """
        # Keep serialization explicit so the artifact schema cannot acquire
        # dataclass implementation details or unstable field names.
        return {
            "kind": self.kind,
            "path": self.path,
            "frame_count": self.frame_count,
            "width": self.width,
            "height": self.height,
            "fps": self.fps,
        }


def write_video_or_png_sequence(frames: Iterable[np.ndarray],
                                output_path: str | Path,
                                *,
                                fps: float = 30.0) -> VideoArtifact:
    """Stream frames to one MP4, PNG, or PNG-sequence artifact.

    Args:
        frames: Iterable of constant-size grayscale or RGB-compatible images.
        output_path: MP4 path, single PNG path, or PNG-sequence directory.
        fps: Finite frame rate in ``(0, 1000]``.

    Returns:
        Aggregate output metadata with no per-frame path collection.

    Raises:
        ValueError: If no frame exists, dimensions change, or fps is invalid.
        RuntimeError: If ffmpeg cannot encode the stream.

    Example:
        result = write_video_or_png_sequence(
            [np.zeros((2, 2), dtype=np.uint8)],
            Path("frame.png"),
        )
        print(result.frame_count)

    Output:
        1
    """
    # Validate the stream policy and materialize one validated first frame; it
    # fixes geometry and dtype expectations for every backend.
    if not np.isfinite(fps) or not 0.0 < fps <= 1000.0:
        raise ValueError("fps must be finite and in (0, 1000]")

    output = Path(output_path)
    frame_iterator = iter(frames)
    try:
        first_frame = _as_uint8_frame(next(frame_iterator))
    except StopIteration as exc:
        raise ValueError("at least one frame is required") from exc

    # Route MP4 requests to the bounded ffmpeg stream when available, otherwise
    # preserve all frames through the deterministic PNG-sequence fallback.
    if output.suffix.lower() == ".mp4":
        all_frames = chain((first_frame,), frame_iterator)
        if shutil.which("ffmpeg") is not None:
            return _write_mp4_with_ffmpeg(
                all_frames,
                output,
                fps=fps,
            )
        sequence_dir = output.with_suffix("").with_name(
            output.stem + "_frames"
        )
        return _write_png_sequence(
            all_frames,
            sequence_dir,
            fps=fps,
        )

    # A file-like PNG target deliberately represents exactly one frame; all
    # other target forms represent a numbered sequence directory.
    if output.suffix.lower() == ".png":
        try:
            next(frame_iterator)
        except StopIteration:
            pass
        else:
            raise ValueError(
                "a single PNG output requires exactly one frame"
            )
        return _write_single_png(first_frame, output)

    return _write_png_sequence(
        chain((first_frame,), frame_iterator),
        output,
        fps=fps,
    )


def write_event_preview(events: EventArray,
                        output_path: str | Path,
                        *,
                        dt_ms: float,
                        mode: str = "polarity_rgb",
                        fps: float = 30.0) -> VideoArtifact:
    """Write a streamed event-accumulation preview.

    Args:
        events: Validated nonempty event stream.
        output_path: MP4 path or PNG-sequence directory.
        dt_ms: Event accumulation duration for each emitted frame.
        mode: ``polarity_rgb`` or ``time_surface`` rendering.
        fps: Finite output frame rate in ``(0, 1000]``.

    Returns:
        Aggregate output metadata.

    Raises:
        ValueError: If the stream, accumulation interval, or mode is invalid.

    Example:
        events = EventArray(
            x=[0, 1],
            y=[0, 1],
            p=[1, -1],
            t_us=[0, 10_000],
            width=2,
            height=2,
        )
        result = write_event_preview(
            events, Path("preview_frames"), dt_ms=10.0
        )
        print(result.kind)

    Output:
        png_sequence
    """
    # Bound source geometry and the time-window policy before constructing the
    # lazy slice iterator passed to the generic writer.
    if events.size == 0:
        raise ValueError("event preview requires at least one event")
    if events.width * events.height > _MAX_ENCODED_FRAME_PIXELS:
        raise ValueError(
            "event preview geometry exceeds the encoded-frame pixel limit"
        )
    window_us = int(round(float(dt_ms) * 1000.0))
    if window_us <= 0:
        raise ValueError("dt_ms must be positive")
    if mode not in {"polarity_rgb", "time_surface"}:
        raise ValueError(
            "mode must be 'polarity_rgb' or 'time_surface'"
        )

    # Keep accumulation time independent from playback rate: callers may choose
    # either real-time or accelerated presentation without changing frame data.
    return write_video_or_png_sequence(
        _iter_event_preview_frames(
            events,
            window_us=window_us,
            mode=mode,
        ),
        output_path,
        fps=fps,
    )


def _iter_event_preview_frames(events: EventArray,
                               *,
                               window_us: int,
                               mode: str) -> Iterator[np.ndarray]:
    """Yield one bounded preview frame per event-time window."""
    # Convert each slice immediately and release it before advancing to the next
    # window so retained image state is constant with sequence duration.
    for chunk in iter_time_slices(events, window_us=window_us):
        if mode == "polarity_rgb":
            yield render_polarity_rgb(chunk)
        else:
            yield render_time_surface_uint8(chunk)


def _write_single_png(frame: np.ndarray,
                      output: Path) -> VideoArtifact:
    """Atomically publish one image frame."""
    # Reject unsafe or incompatible targets before removing a stale temporary
    # sibling or encoding replacement bytes.
    _reject_symlink(output)
    _reject_non_file_target(output)
    output.parent.mkdir(parents=True, exist_ok=True)
    temporary_path = output.with_name(
        f".{output.stem}.tmp{output.suffix}"
    )
    _remove_owned_temporary_file(temporary_path)

    # Replace the public path only after PIL has completed the temporary file.
    try:
        Image.fromarray(frame).save(temporary_path)
        os.replace(temporary_path, output)
    finally:
        temporary_path.unlink(missing_ok=True)

    height, width = frame.shape[:2]
    return VideoArtifact(
        kind="png",
        path=str(output),
        frame_count=1,
        width=width,
        height=height,
        fps=None,
    )


def _write_png_sequence(frames: Iterable[np.ndarray],
                        output_dir: Path,
                        *,
                        fps: float) -> VideoArtifact:
    """Publish numbered PNGs while preserving the prior sequence on failure."""
    _reject_symlink(output_dir)
    if output_dir.exists() and not output_dir.is_dir():
        raise ValueError(
            f"PNG sequence output is not a directory: {output_dir}"
        )
    output_dir.mkdir(parents=True, exist_ok=True)

    # Stage every replacement frame under an exact temporary name. A failed
    # encode removes only temporary files and leaves the last valid sequence
    # available to readers.
    _remove_owned_sequence_temporaries(output_dir)
    first_shape: tuple[int, ...] | None = None
    frame_count = 0
    try:
        for index, frame in enumerate(frames):
            if index >= _MAX_ENCODED_FRAMES:
                raise ValueError(
                    "video frame count exceeds the encoded-frame limit"
                )

            # The first validated frame establishes a single shape invariant
            # for the complete staged replacement.
            array = _as_uint8_frame(frame)
            if first_shape is None:
                first_shape = array.shape
            elif array.shape != first_shape:
                raise ValueError(
                    "all sequence frames must have the same shape"
                )

            temporary_path = (
                output_dir / f".frame_{index:06d}.stage.png"
            )
            Image.fromarray(array).save(temporary_path)
            frame_count += 1
    except BaseException:
        _remove_owned_sequence_temporaries(output_dir)
        raise

    if first_shape is None:
        raise ValueError("at least one frame is required")

    # Commit only after the complete replacement has been encoded. Cleanup is
    # restricted to this writer's exact numbered-frame convention.
    try:
        _remove_owned_sequence_frames(output_dir)
        for index in range(frame_count):
            temporary_path = output_dir / f".frame_{index:06d}.stage.png"
            output_path = output_dir / f"frame_{index:06d}.png"
            os.replace(temporary_path, output_path)
    except BaseException:
        _remove_owned_sequence_temporaries(output_dir)
        raise

    return VideoArtifact(
        kind="png_sequence",
        path=str(output_dir),
        frame_count=frame_count,
        width=first_shape[1],
        height=first_shape[0],
        fps=float(fps),
    )


def _write_mp4_with_ffmpeg(frames: Iterable[np.ndarray],
                            output: Path,
                            *,
                            fps: float) -> VideoArtifact:
    """Encode one constant-size stream and publish it atomically."""
    # Convert the first frame before spawning ffmpeg because it fixes raw-video
    # geometry and guarantees a nonempty input stream.
    frame_iterator = iter(frames)
    try:
        first_frame = _as_rgb_frame(next(frame_iterator))
    except StopIteration as exc:
        raise ValueError("at least one frame is required") from exc

    # Validate the owned publication boundary before creating an encoder
    # process or its temporary output.
    _reject_symlink(output)
    _reject_non_file_target(output)
    height, width = first_frame.shape[:2]
    output.parent.mkdir(parents=True, exist_ok=True)
    temporary_output = output.with_name(
        f".{output.stem}.tmp{output.suffix}"
    )
    _remove_owned_temporary_file(temporary_output)

    # Feed raw RGB through one encoder thread and pad only the encoded frame to
    # the even dimensions required by yuv420p.
    command = [
        "ffmpeg",
        "-y",
        "-loglevel",
        "error",
        "-f",
        "rawvideo",
        "-pix_fmt",
        "rgb24",
        "-s:v",
        f"{width}x{height}",
        "-framerate",
        f"{float(fps):.6f}",
        "-i",
        "-",
        "-vf",
        "pad=ceil(iw/2)*2:ceil(ih/2)*2",
        "-an",
        "-c:v",
        "libx264",
        "-threads",
        "1",
        "-pix_fmt",
        "yuv420p",
        str(temporary_output),
    ]
    process = subprocess.Popen(
        command,
        stdin=subprocess.PIPE,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.PIPE,
    )
    if process.stdin is None or process.stderr is None:
        process.kill()
        process.wait()
        raise RuntimeError("failed to open ffmpeg pipes")

    frame_count = 0
    try:
        # Validate and stream each frame immediately; no full-video buffer or
        # per-frame artifact list is retained.
        for frame in chain((first_frame,), frame_iterator):
            if frame_count >= _MAX_ENCODED_FRAMES:
                raise ValueError(
                    "video frame count exceeds the encoded-frame limit"
                )
            rgb_frame = np.ascontiguousarray(_as_rgb_frame(frame))
            if rgb_frame.shape != first_frame.shape:
                raise ValueError(
                    "all video frames must have the same shape"
                )
            process.stdin.write(rgb_frame.tobytes())
            frame_count += 1
        process.stdin.close()
        error_output = process.stderr.read().decode(
            "utf-8",
            errors="replace",
        )
        return_code = process.wait()
    except BaseException:
        process.kill()
        process.wait()
        temporary_output.unlink(missing_ok=True)
        raise

    # Reject an encoder that exits successfully without a complete output, then
    # atomically replace the prior public MP4.
    if return_code != 0 or not temporary_output.exists():
        temporary_output.unlink(missing_ok=True)
        raise RuntimeError(
            f"ffmpeg failed with status {return_code}: "
            f"{error_output.strip()}"
        )
    try:
        os.replace(temporary_output, output)
    except BaseException:
        temporary_output.unlink(missing_ok=True)
        raise

    # Report encoded dimensions after ffmpeg's even-edge padding rather than
    # the unpadded raw-video input size.
    encoded_width = width + width % 2
    encoded_height = height + height % 2
    return VideoArtifact(
        kind="mp4",
        path=str(output),
        frame_count=frame_count,
        width=encoded_width,
        height=encoded_height,
        fps=float(fps),
    )


def _remove_owned_sequence_frames(output_dir: Path) -> None:
    """Remove only regular frames owned by this PNG-sequence writer."""
    paths = list(
        output_dir.glob(
            "frame_[0-9][0-9][0-9][0-9][0-9][0-9].png"
        )
    )
    for path in paths:
        if path.is_symlink():
            raise ValueError(
                f"refusing to remove symlinked sequence frame: {path}"
            )
        if not path.is_file():
            raise ValueError(
                f"owned sequence path is not a regular file: {path}"
            )

    # Validate the complete deletion set before removing any prior frame.
    for path in paths:
        path.unlink()


def _remove_owned_sequence_temporaries(output_dir: Path) -> None:
    """Remove only regular staging files owned by this sequence writer."""
    for path in output_dir.glob(
        ".frame_[0-9][0-9][0-9][0-9][0-9][0-9].stage.png"
    ):
        _remove_owned_temporary_file(path)


def _remove_owned_temporary_file(path: Path) -> None:
    """Remove one exact regular temporary file without following a symlink."""
    if path.is_symlink():
        raise ValueError(
            f"refusing symlinked temporary output: {path}"
        )
    if path.is_file():
        path.unlink()
    elif path.exists():
        raise ValueError(
            f"temporary output is not a regular file: {path}"
        )


def _reject_symlink(path: Path) -> None:
    """Reject an existing symlink at an owned output target."""
    if path.is_symlink():
        raise ValueError(f"refusing symlinked output target: {path}")


def _reject_non_file_target(path: Path) -> None:
    """Reject an existing output target that is not one regular file."""
    if path.exists() and not path.is_file():
        raise ValueError(
            f"output target is not a regular file: {path}"
        )


def _as_rgb_frame(frame: np.ndarray) -> np.ndarray:
    """Convert one validated frame to contiguous RGB-compatible storage."""
    array = _as_uint8_frame(frame)

    # Expand grayscale and discard alpha explicitly because the ffmpeg input
    # contract is always packed RGB24.
    if array.ndim == 2:
        return np.repeat(array[:, :, None], 3, axis=2)
    if array.shape[2] == 4:
        return array[:, :, :3]
    return array


def _as_uint8_frame(frame: np.ndarray) -> np.ndarray:
    """Normalize one finite grayscale, RGB, or RGBA frame to uint8."""
    array = np.asarray(frame)

    # Reject unsupported layouts before any finite-value scan, clipping, or
    # dtype conversion can copy an arbitrarily large channel dimension.
    valid_grayscale_shape = (
        array.ndim == 2 and
        all(size > 0 for size in array.shape)
    )
    valid_color_shape = (
        array.ndim == 3 and
        all(size > 0 for size in array.shape[:2]) and
        array.shape[2] in {3, 4}
    )
    if not (valid_grayscale_shape or valid_color_shape):
        raise ValueError(
            "frame must be HxW grayscale or HxWx3/HxWx4 "
            "uint8-compatible array"
        )
    if array.shape[0] * array.shape[1] > _MAX_ENCODED_FRAME_PIXELS:
        raise ValueError(
            "frame geometry exceeds the encoded-frame pixel limit"
        )

    # Validate numerical semantics only after the bounded shape check, then
    # narrow through explicit clipping for integer and floating inputs.
    if array.dtype.kind not in "biuf":
        raise ValueError("frame values must be real numeric values")
    if array.dtype.kind == "f" and not bool(np.all(np.isfinite(array))):
        raise ValueError("frame values must be finite")
    if array.dtype != np.uint8:
        array = np.clip(array, 0, 255).astype(np.uint8)
    return array
