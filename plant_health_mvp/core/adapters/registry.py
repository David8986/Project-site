"""Adapter selection helpers."""

from __future__ import annotations

from pathlib import Path

from .base import DatasetAdapter
from .envi_adapter import EnviHyperspectralAdapter
from .mock_adapter import MockAdapter


def adapter_for_path(path: str | Path | None, wavelength_csv: str | Path | None = None) -> DatasetAdapter:
    """Return the best available adapter for a dataset path."""

    if path is None:
        return MockAdapter("mock", wavelength_csv)

    path_text = str(path)
    if path_text.lower() in {"mock", "mock://", "synthetic", "synthetic_mock_sample"}:
        return MockAdapter("mock", wavelength_csv)

    root = Path(path).expanduser()
    if root.is_dir() or root.name.lower().endswith((".tar.gz", ".tgz", ".tar")):
        return EnviHyperspectralAdapter(root, wavelength_csv)
    raise ValueError(f"No dataset adapter is registered for: {root}")
