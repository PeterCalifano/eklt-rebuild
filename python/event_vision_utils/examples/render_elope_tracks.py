"""Render ROS2 EKLT tracks as dots over an ELOPE event preview.

Example:
    python -m event_vision_utils.examples.render_elope_tracks \
        --input data/elope/test/0028.npz \
        --tracks outputs/official_elope_event_only/tracking/tracks.txt \
        --output outputs/official_elope_event_only/tracking/eklt_tracks.mp4

Output:
    outputs/official_elope_event_only/tracking/track_video_summary.json
"""

from __future__ import annotations

import argparse
import json
import os
from pathlib import Path

from event_vision_utils.io import load_event_dataset, load_track_samples
from event_vision_utils.viz import write_track_dot_video


def main(argv: list[str] | None = None) -> int:
    """Render one validated ELOPE track-dot video.

    Args:
        argv: Optional command-line arguments excluding the executable name.

    Returns:
        Zero after the video and its JSON summary are written.

    Example:
        status = main([
            "--input", "events.npz",
            "--tracks", "output/tracks.txt",
            "--output", "output/eklt_tracks.mp4",
        ])
        print(status)

    Output:
        output/track_video_summary.json
        0
    """
    # Collect the rendering and artifact policy in one CLI contract before any
    # dataset is loaded or output path is touched.
    parser = argparse.ArgumentParser(
        description="Render EKLT tracks as dots over ELOPE event activity."
    )
    parser.add_argument("--input", required=True, type=Path)
    parser.add_argument("--tracks", required=True, type=Path)
    parser.add_argument("--output", required=True, type=Path)
    parser.add_argument("--summary-output", type=Path)
    parser.add_argument("--width", type=int)
    parser.add_argument("--height", type=int)
    parser.add_argument("--fps", default=100.0, type=float)
    parser.add_argument("--scale", default=4, type=int)
    parser.add_argument("--track-hold-ms", default=100.0, type=float)
    parser.add_argument("--dot-radius", default=5, type=int)
    args = parser.parse_args(argv)

    # Keep the default summary beside the requested video and reject link-based
    # substitution at every caller-controlled artifact boundary.
    summary_path = args.summary_output
    if summary_path is None:
        summary_path = args.output.parent / "track_video_summary.json"
    if summary_path.is_symlink():
        raise ValueError(
            f"refusing symlinked summary target: {summary_path}"
        )
    if args.output.is_symlink():
        raise ValueError(
            f"refusing symlinked video target: {args.output}"
        )
    if args.tracks.is_symlink():
        raise ValueError(
            f"refusing symlinked track artifact: {args.tracks}"
        )

    # Require the video and summary to share one component root before any
    # expensive rendering or external encoder process begins.
    summary_root = summary_path.parent.resolve(strict=False)
    output_path = args.output.resolve(strict=False)
    track_path = args.tracks.resolve(strict=True)
    try:
        output_path.relative_to(summary_root)
        relative_track_path = track_path.relative_to(summary_root)
    except ValueError as exc:
        raise ValueError(
            "track video and track artifact must remain below "
            "their summary directory"
        ) from exc

    # Load both inputs through their strict shared adapters before starting the
    # incremental renderer or its external encoder.
    dataset = load_event_dataset(
        args.input,
        adapter="elope",
        width=args.width,
        height=args.height,
    )
    samples = load_track_samples(track_path)
    video = write_track_dot_video(
        dataset.events,
        samples,
        output_path,
        fps=args.fps,
        scale=args.scale,
        hold_ms=args.track_hold_ms,
        dot_radius=args.dot_radius,
    )

    # Record the path actually published by the writer because an unavailable
    # FFmpeg encoder replaces the requested MP4 with a PNG-sequence directory.
    published_video_path = Path(video.video.path).resolve(strict=False)
    try:
        relative_video_path = published_video_path.relative_to(summary_root)
    except ValueError as exc:
        raise ValueError(
            "published track video escaped its summary directory"
        ) from exc

    # Publish only component-relative artifact paths so the complete tracking
    # directory can be relocated without rewriting its summary.
    summary_path.parent.mkdir(parents=True, exist_ok=True)
    video_metadata = video.as_dict()
    video_metadata["path"] = relative_video_path.as_posix()
    summary = {
        "schema_version": 1,
        "artifact_type": "eklt_track_video",
        "status": "passed",
        "input": str(args.input),
        "tracks": relative_track_path.as_posix(),
        "dataset_adapter": dataset.metadata.name,
        "dataset_metadata": dataset.metadata.attributes,
        "video": video_metadata,
    }

    # Replace the summary only after a complete deterministic JSON document has
    # been written to its owned sibling.
    temporary_path = summary_path.with_suffix(".tmp.json")
    if temporary_path.is_symlink():
        raise ValueError(
            f"refusing symlinked temporary summary: {temporary_path}"
        )
    try:
        temporary_path.write_text(
            json.dumps(summary, indent=2, sort_keys=True) + "\n",
            encoding="utf-8",
        )
        os.replace(temporary_path, summary_path)
    finally:
        temporary_path.unlink(missing_ok=True)
    print(summary_path)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
