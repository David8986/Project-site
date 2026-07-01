"""Tests for structured report generation."""

from __future__ import annotations

import numpy as np

from plant_health_mvp.models.sample import BandMapping, SpectralSample
from plant_health_mvp.reports import build_analysis_report


def test_analysis_report_contains_structured_sections_and_warnings() -> None:
    """The main report should expose source, mapping, roles, spots, and warnings."""

    sample = SpectralSample(
        source_type="hyperspectral_cube",
        available_wavelengths=np.array([680.0, 850.0]),
        data=np.ones((2, 2, 2)),
        target_bands={"680": np.ones((2, 2)), "850": np.ones((2, 2)), "940": None},
        band_status={"680": "exact", "850": "exact", "940": "missing"},
        band_mappings={
            "680": BandMapping(680.0, "exact", (0,), (680.0,), (1.0,), 0.0),
            "850": BandMapping(850.0, "exact", (1,), (850.0,), (1.0,), 0.0),
            "940": BandMapping(940.0, "missing"),
        },
        metadata={
            "mock_flag": False,
            "adapter_used": "unit_test_adapter",
            "sample_id": "sample_a",
            "calibration_applied": False,
            "dimensions": {"shape": [2, 2, 2]},
            "vegetation_mask": {"method": "ndvi", "vegetation_pixel_count": 4},
        },
    )

    report = build_analysis_report(
        sample,
        {"680": 0.2, "850": 0.8, "940": None},
        {"vegetation_pixel_count": 4},
        indices_report={"indices": {"NDVI": {"value": 0.6}}},
        spot_report={"spot_count": 0, "spots": []},
    )

    assert report["report_schema"] == "plant_health_analysis_v2"
    assert report["source"]["adapter_used"] == "unit_test_adapter"
    assert report["source"]["sample_id"] == "sample_a"
    assert report["target_band_mapping"]["940"]["status"] == "missing"
    assert report["band_roles"]["NIR"]["band_key"] == "850"
    assert report["whole_leaf"]["indices"]["NDVI"]["value"] == 0.6
    assert report["interpretation"]["summary_title"] == "Interpretare"
    assert report["whole_leaf"]["interpretation"]["summary_title"] == "Interpretare"
    assert report["suspicious_regions"]["spot_count"] == 0
    assert "target band 940 is missing" in report["warnings"]
    assert report["mapping"]["680"]["status"] == "exact"
