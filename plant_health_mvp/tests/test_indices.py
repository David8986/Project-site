"""Tests for scalar spectral-index calculation."""

from __future__ import annotations

from plant_health_mvp.indices import compute_indices


def test_compute_indices_uses_average_band_values() -> None:
    """The scalar index formulas should use average vegetation-band values."""

    averages = {
        "556": 20.0,
        "680": 10.0,
        "725": 30.0,
        "850": 50.0,
        "940": 25.0,
    }

    indices = compute_indices(averages)

    assert indices["NDVI"]["value"] == 0.666667
    assert indices["NDRE"]["value"] == 0.25
    assert indices["GNDVI"]["value"] == 0.428571
    assert indices["CI_RE"]["value"] == 0.666667
    assert indices["NDWI_850_940"]["value"] == 0.333333
    assert indices["NIR_RED_DIFF"]["value"] == 40.0
    assert indices["NIR_RED_SUM"]["value"] == 60.0


def test_compute_indices_reports_missing_required_band() -> None:
    """Missing bands should produce null values and a clear reason."""

    indices = compute_indices({"850": 50.0})

    assert indices["NDVI"]["value"] is None
    assert indices["NDVI"]["reason"] == "missing required band"


def test_compute_indices_reports_division_by_zero() -> None:
    """Zero denominators should produce null values and a clear reason."""

    indices = compute_indices({"680": -10.0, "850": 10.0})

    assert indices["NDVI"]["value"] is None
    assert indices["NDVI"]["reason"] == "division by zero"
