"""Lazy import helpers for the spectral raytracer Python wrapper."""

from __future__ import annotations

from importlib import import_module
from pathlib import Path
import sys
from types import ModuleType


def spectral_rt_py_search_paths(spectral_raytracer_root: Path | str) -> list[Path]:
    """Return the search paths that may contain the spectral_rt_py package."""

    root = Path(spectral_raytracer_root).resolve()
    candidates = [
        root / "python",
        root / "python" / "spectral_rt_py",
    ]
    return [path for path in candidates if path.exists()]


def import_spectral_rt_py(spectral_raytracer_root: Path | str | None = None) -> ModuleType:
    """Import spectral_rt_py, optionally extending sys.path from a checkout root first."""

    if spectral_raytracer_root is not None:
        for candidate in reversed(spectral_rt_py_search_paths(spectral_raytracer_root)):
            candidate_string = str(candidate)
            if candidate_string not in sys.path:
                sys.path.insert(0, candidate_string)

    return import_module("spectral_rt_py")
