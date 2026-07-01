"""Tests for wavelength CSV loading."""

from __future__ import annotations

from pathlib import Path

import numpy as np

from plant_health_mvp.loader import load_wavelength_csv


def test_two_column_wavelength_csv_uses_wavelength_column(tmp_path: Path) -> None:
    """Index columns should not be treated as wavelengths."""

    csv_path = tmp_path / "wavelengths.csv"
    csv_path.write_text("0,397.66\n1,400.28\n2,402.9\n", encoding="utf-8")

    wavelengths = load_wavelength_csv(csv_path)

    np.testing.assert_allclose(wavelengths, np.array([397.66, 400.28, 402.9]))
