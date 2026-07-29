"""Read the stable EKLT text-track artifact format.

Track files contain one ``id time_s x_px y_px`` observation per non-comment
line. Parsing is strict so malformed output cannot be silently omitted from an
acceptance summary.

Example:
    samples = load_track_samples(Path("tracks.txt"))
    print(samples[0].track_id)

Output:
    0
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True, slots=True)
class TrackSample:
    """One validated EKLT feature observation.

    Attributes:
        track_id: Stable nonnegative EKLT feature identifier.
        t_s: Nonnegative observation timestamp in seconds.
        x: Finite horizontal image coordinate in pixels.
        y: Finite vertical image coordinate in pixels.

    Example:
        sample = TrackSample(track_id=3, t_s=0.1, x=4.0, y=5.0)
        print(sample.track_id, sample.t_s)

    Output:
        3 0.1
    """

    track_id: int
    t_s: float
    x: float
    y: float


def load_track_samples(input_path: str | Path) -> list[TrackSample]:
    """Load EKLT observations while preserving file order.

    Per-track timestamps must be nondecreasing. Coordinates are required to be
    finite, but geometry checks remain with consumers: analytical plots may
    show and count slight boundary excursions, while image renderers reject
    observations that cannot be displayed faithfully.

    Args:
        input_path: Text file containing ``id time_s x_px y_px`` rows.

    Returns:
        Validated observations in their original file order.

    Raises:
        FileNotFoundError: If the track file does not exist.
        UnicodeError: If the file is not valid UTF-8.
        ValueError: If any non-comment row violates the artifact contract.

    Example:
        samples = load_track_samples(Path("tracks.txt"))
        print(len(samples))

    Output:
        3
    """
    path = Path(input_path)
    samples: list[TrackSample] = []
    last_time_by_track: dict[int, float] = {}

    # Parse every data row through one strict path so summaries cannot hide
    # malformed tracker output by dropping individual observations.
    for line_number, line in enumerate(
        path.read_text(encoding="utf-8", errors="strict").splitlines(),
        start=1,
    ):
        stripped = line.strip()
        if not stripped or stripped.startswith("#"):
            continue

        # Decode the complete row before applying field-level constraints so
        # every malformed token receives the same source-line diagnostic.
        fields = stripped.split()
        if len(fields) != 4:
            raise ValueError(
                f"{path}:{line_number}: expected id time_s x_px y_px"
            )
        try:
            sample = TrackSample(
                track_id=int(fields[0]),
                t_s=float(fields[1]),
                x=float(fields[2]),
                y=float(fields[3]),
            )
        except ValueError as exc:
            raise ValueError(
                f"{path}:{line_number}: invalid track value"
            ) from exc

        # Enforce only the transport-neutral track contract here. Sensor-plane
        # bounds remain a consumer policy because native subpixel estimates may
        # legitimately cross the display boundary.
        if sample.track_id < 0:
            raise ValueError(
                f"{path}:{line_number}: track id must be nonnegative"
            )
        if not all(
            math.isfinite(value)
            for value in (sample.t_s, sample.x, sample.y)
        ):
            raise ValueError(
                f"{path}:{line_number}: track values must be finite"
            )
        if sample.t_s < 0.0:
            raise ValueError(
                f"{path}:{line_number}: timestamp must be nonnegative"
            )

        # Check chronology per feature rather than globally so rows from
        # independently updated tracks may remain interleaved in file order.
        previous_time = last_time_by_track.get(sample.track_id)
        if previous_time is not None and sample.t_s < previous_time:
            raise ValueError(
                f"{path}:{line_number}: per-track timestamp regression"
            )
        last_time_by_track[sample.track_id] = sample.t_s
        samples.append(sample)

    return samples
