"""Verify strict processing-time CSV validation and stacked plot output."""

from __future__ import annotations

import json
import struct
from pathlib import Path

import pytest

from scripts.plot_eklt_processing_timing import (
    PLOT_SUBTITLE,
    PLOT_TITLE,
    PLOT_X_LABEL,
    PLOT_Y_LABEL,
    build_stacked_boundaries,
    load_processing_timing_csv,
    main,
)


VALID_CSV = """packet_index,event_time_s,fibar_ms,eklt_ms,overhead_ms,total_ms
1,10.000000000,1.000000000,2.000000000,0.500000000,3.500000000
2,10.010000000,1.500000000,2.500000000,1.000000000,5.000000000
3,10.020000000,2.000000000,1.000000000,0.250000000,3.250000000
"""


def _write_csv(output_path: Path, contents: str = VALID_CSV) -> Path:
    """Write one timing fixture and return its path."""
    output_path.write_text(contents, encoding="utf-8")
    return output_path


def test_loads_timing_and_builds_cumulative_boundaries(tmp_path: Path) -> None:
    """The stacked bands must reconstruct total without stacking total twice."""
    timing_path = _write_csv(tmp_path / "timing.csv")

    series = load_processing_timing_csv(timing_path)
    fibar_boundary, eklt_boundary, total_boundary = build_stacked_boundaries(series)

    assert series.packet_indices == (1, 2, 3)
    assert fibar_boundary == (1.0, 1.5, 2.0)
    assert eklt_boundary == (3.0, 4.0, 3.0)
    assert total_boundary == series.total_ms


@pytest.mark.parametrize(
    ("contents", "message"),
    (
        (
            VALID_CSV.replace("3.500000000", "3.600000000", 1),
            "violates additive timing",
        ),
        (
            VALID_CSV.replace(
                "3,10.020000000", "3,9.020000000"
            ),
            "regresses event time",
        ),
        (
            VALID_CSV.replace(
                "2,10.010000000", "1,10.010000000"
            ),
            "regresses packet order",
        ),
        (
            VALID_CSV.replace("1.500000000", "nan", 1),
            "contains a non-finite value",
        ),
    ),
)
def test_rejects_invalid_timing_rows(tmp_path: Path,
                                    contents: str,
                                    message: str,
) -> None:
    """Malformed or inconsistent timing rows must fail before plotting."""
    timing_path = _write_csv(tmp_path / "timing.csv", contents)

    with pytest.raises(ValueError, match=message):
        load_processing_timing_csv(timing_path)


def test_cli_writes_png_and_summary_metadata(tmp_path: Path) -> None:
    """The headless example must produce a readable PNG and complete metadata."""
    timing_path = _write_csv(tmp_path / "timing.csv")
    plot_path = tmp_path / "plots" / "processing_time_cumulative.png"
    summary_path = tmp_path / "processing_timing_summary.json"

    status = main(
        (
            "--input",
            str(timing_path),
            "--output",
            str(plot_path),
            "--summary-output",
            str(summary_path),
            "--maximum-points",
            "2",
        )
    )

    assert status == 0
    with plot_path.open("rb") as plot_stream:
        header = plot_stream.read(24)
    assert header[:8] == b"\x89PNG\r\n\x1a\n"
    width, height = struct.unpack(">II", header[16:24])
    assert (width, height) == (1600, 900)

    summary = json.loads(summary_path.read_text(encoding="utf-8"))
    assert summary["status"] == "passed"
    assert summary["sample_count"] == 3
    assert summary["plotted_sample_count"] == 2
    assert summary["event_duration_s"] == pytest.approx(0.02)
    assert summary["plot"]["title"] == PLOT_TITLE
    assert summary["plot"]["subtitle"] == PLOT_SUBTITLE
    assert summary["plot"]["x_label"] == PLOT_X_LABEL
    assert summary["plot"]["y_label"] == PLOT_Y_LABEL
    assert summary["plot"]["title"][0].isupper()
    assert summary["plot"]["x_label"].endswith("]")
    assert summary["plot"]["y_label"].endswith("]")
    assert summary["plot"]["bands"] == ["fibar_ms", "eklt_ms", "overhead_ms"]
    assert summary["plot"]["boundary_line"] == "total_ms"
