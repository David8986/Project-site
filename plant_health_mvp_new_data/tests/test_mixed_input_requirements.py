"""Focused mixed-input requirements checks.

These tests document the expected behavior for RGB/NIR-style partial inputs
without changing shared production modules during the audit.
"""

from __future__ import annotations

import numpy as np

from plant_health_mvp.anomaly_detection import SpotDetectionConfig, detect_suspicious_spots
from plant_health_mvp.indices import build_indices_report, compute_indices
from plant_health_mvp.models.sample import BandMapping, SpectralSample
from plant_health_mvp.reports import build_analysis_report
from plant_health_mvp.semantic_roles import resolve_semantic_roles


def _mapping(wavelength: float, index: int | None = None) -> BandMapping:
    """Build a compact target-band mapping fixture."""

    if index is None:
        return BandMapping(target_wavelength=wavelength, status="missing")
    return BandMapping(
        target_wavelength=wavelength,
        status="exact",
        source_indices=(index,),
        source_wavelengths=(wavelength,),
        weights=(1.0,),
        distance_nm=0.0,
    )


def _mixed_rgb_nir_sample() -> SpectralSample:
    """Return a sample with RGB-like bands plus NIR, but no red-edge or 940 nm."""

    blue = np.full((5, 5), 0.10, dtype=float)
    green = np.full((5, 5), 0.30, dtype=float)
    red = np.full((5, 5), 0.20, dtype=float)
    nir = np.full((5, 5), 0.80, dtype=float)
    sample = SpectralSample(
        source_type="mixed_rgb_nir",
        available_wavelengths=np.array([532.0, 556.0, 650.0, 850.0], dtype=float),
        data=np.stack([blue, green, red, nir], axis=-1),
        target_bands={
            "532": blue,
            "556": green,
            "650": red,
            "725": None,
            "850": nir,
            "940": None,
        },
        band_status={
            "532": "exact",
            "556": "exact",
            "650": "exact",
            "725": "missing",
            "850": "exact",
            "940": "missing",
        },
        band_mappings={
            "532": _mapping(532.0, 0),
            "556": _mapping(556.0, 1),
            "650": _mapping(650.0, 2),
            "725": _mapping(725.0),
            "850": _mapping(850.0, 3),
            "940": _mapping(940.0),
        },
        mask=np.ones((5, 5), dtype=bool),
        metadata={
            "sample_id": "rgb_nir_leaf",
            "adapter_used": "unit_test_adapter",
            "source_data_kind": "mixed_rgb_nir_data",
            "analysis_data_kind": "raw_intensity",
            "mock_flag": False,
            "calibration_applied": False,
            "dimensions": {"shape": [5, 5, 4]},
            "input_path": "leaf_rgb.png",
            "nir_path": "leaf_nir.tif",
            "wavelength_csv_path": "wavelengths.csv",
        },
    )
    return sample


def test_mixed_rgb_nir_roles_allow_ndvi_like_maps_without_red_edge_or_water() -> None:
    """RGB plus NIR should produce NIR/red maps while NDRE and water maps stay absent."""

    sample = _mixed_rgb_nir_sample()
    roles = resolve_semantic_roles(sample)
    result = detect_suspicious_spots(
        sample,
        roles=roles,
        config=SpotDetectionConfig(score_threshold=1.1, min_area_px=1, texture_window=3),
    )

    assert roles["RED"].band_key == "650"
    assert roles["NIR"].band_key == "850"
    assert roles["RED_EDGE"].status == "missing"
    assert roles["WATER_BAND"].status == "missing"
    assert "NDVI" in result["available_maps"]
    assert "NIR_RED_DIFF" in result["available_maps"]
    assert "NDRE" not in result["available_maps"]
    assert "NDWI_850_940" not in result["available_maps"]
    assert "low_ndvi" in result["available_anomaly_maps"]
    assert "low_ndre" not in result["available_anomaly_maps"]
    assert "low_nir_water_diff" not in result["available_anomaly_maps"]


def test_report_exposes_mixed_input_roles_and_missing_role_warnings() -> None:
    """Structured reports should make role assignment and unavailable roles explicit."""

    sample = _mixed_rgb_nir_sample()
    report = build_analysis_report(
        sample,
        {"532": 0.10, "556": 0.30, "650": 0.20, "725": None, "850": 0.80, "940": None},
        {"vegetation_pixel_count": 25},
        indices_report={"indices": compute_indices({"650": 0.20, "850": 0.80})},
        spot_report={"spot_count": 0, "spots": []},
    )

    assert report["band_roles"]["RED"]["band_key"] == "650"
    assert report["band_roles"]["NIR"]["band_key"] == "850"
    assert report["band_roles"]["RED_EDGE"]["status"] == "missing"
    assert report["band_roles"]["WATER_BAND"]["status"] == "missing"
    assert "target band 725 is missing" in report["warnings"]
    assert "target band 940 is missing" in report["warnings"]
    assert "semantic role RED_EDGE is missing" in report["warnings"]
    assert "semantic role WATER_BAND is missing" in report["warnings"]


def test_indices_report_emits_ndvi_like_for_rgb_plus_nir_red_fallback() -> None:
    """The report API should allow NDVI-like output when RED resolves to 650."""

    sample = _mixed_rgb_nir_sample()
    report = build_indices_report(
        sample,
        {"650": 0.20, "850": 0.80},
        {"vegetation_pixel_count": 25},
    )
    indices = report["indices"]
    ndvi_like = indices["NDVI"]

    assert ndvi_like["value"] == 0.6
    assert ndvi_like["label"] == "NDVI-like (RGB red + NIR)"
    assert indices["NDRE"]["value"] is None
    assert indices["NDRE"]["reason"] == "missing required role: RED_EDGE"
    assert indices["NDWI_850_940"]["value"] is None
    assert indices["NDWI_850_940"]["reason"] == "missing required role: WATER_BAND"


def test_report_source_lists_imported_files() -> None:
    """Reports should clearly list every file that contributed to a mixed-input run."""

    sample = _mixed_rgb_nir_sample()
    report = build_analysis_report(
        sample,
        {"650": 0.20, "850": 0.80},
        {"vegetation_pixel_count": 25},
        indices_report={"indices": {}},
        spot_report={"spot_count": 0, "spots": []},
    )

    assert report["source"]["imported_files"] == {
        "rgb": "leaf_rgb.png",
        "nir": "leaf_nir.tif",
        "wavelengths": "wavelengths.csv",
    }
