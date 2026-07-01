"""Tests for dataset adapters."""

from __future__ import annotations

from pathlib import Path

import numpy as np

from plant_health_mvp.adapters.envi_adapter import EnviHyperspectralAdapter
from plant_health_mvp.adapters.mock_adapter import MockAdapter


def test_envi_adapter_loads_extracted_directory(tmp_path: Path) -> None:
    """A tiny extracted ENVI folder should load through the adapter interface."""

    sample_dir = tmp_path / "sample_a"
    capture_dir = sample_dir / "capture"
    capture_dir.mkdir(parents=True)
    hdr_path = capture_dir / "sample_a.hdr"
    raw_path = capture_dir / "sample_a.raw"
    hdr_path.write_text(
        "\n".join(
            [
                "ENVI",
                "samples = 3",
                "lines = 2",
                "bands = 2",
                "interleave = bil",
                "data type = 12",
                "byte order = 0",
                "header offset = 0",
                "wavelength = {500.0, 700.0}",
            ]
        ),
        encoding="utf-8",
    )
    bil = np.arange(12, dtype=np.uint16).reshape((2, 2, 3))
    raw_path.write_bytes(bil.tobytes())

    adapter = EnviHyperspectralAdapter(sample_dir)
    loaded = adapter.load_sample()

    assert loaded.sample_id == "sample_a"
    assert loaded.cube.shape == (2, 3, 2)
    np.testing.assert_allclose(loaded.wavelengths, np.array([500.0, 700.0]))
    assert loaded.dark_reference is None
    assert loaded.white_reference is None


def test_mock_adapter_returns_adapter_sample() -> None:
    """The mock dataset should also travel through the adapter interface."""

    adapter = MockAdapter("mock")
    loaded = adapter.load_sample()

    assert adapter.list_samples() == ["synthetic_mock_sample"]
    assert loaded.sample_id == "synthetic_mock_sample"
    assert loaded.cube.ndim == 3
    assert loaded.wavelengths.size == loaded.cube.shape[-1]
    assert loaded.metadata["adapter_used"] == "mock_hyperspectral"
    assert loaded.metadata["source_data_kind"] == "mock_synthetic_data"
