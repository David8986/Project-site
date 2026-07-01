"""Tests for human-readable analysis report helpers."""

from __future__ import annotations

from plant_health_mvp.analysis_app.readable import (
    build_detailed_report_text,
    build_summary_text,
    classify_anomaly_level,
)


def _report_with_spots(spot_count: int, scores: list[float]) -> dict[str, object]:
    """Build a compact report fixture for readable-text tests."""

    spots = []
    for index, score in enumerate(scores, start=1):
        spots.append(
            {
                "label": index,
                "area_px": 20 + index,
                "severity_rank": index,
                "severity_score": 1.0 + index * 0.5,
                "mean_suspiciousness_score": score,
                "max_suspiciousness_score": min(1.0, score + 0.08),
                "bbox": [10 + index, 20 + index, 13 + index, 24 + index],
                "centroid": [11.5 + index, 22.5 + index],
                "ndvi": 0.2 + index * 0.01,
                "ndre": 0.1 + index * 0.01,
                "gndvi": 0.15 + index * 0.01,
                "ndwi_850_940": 0.05 + index * 0.01,
            }
        )

    return {
        "report_schema": "plant_health_analysis_v2",
        "source": {
            "sample_id": "sample_a",
            "adapter_used": "unit_test_adapter",
            "analysis_data_kind": "raw intensity",
            "vegetation_pixels": 42,
            "source_type": "hyperspectral_cube",
        },
        "wavelengths": {
            "count": 2,
            "min_nm": 680.0,
            "max_nm": 850.0,
            "available_wavelengths_nm": [680.0, 850.0],
            "target_profile": "profile_7band_default",
            "target_wavelengths_nm": [680.0, 725.0, 850.0],
        },
        "whole_leaf": {
            "average_bands": {"680": 0.2, "850": 0.3},
            "indices": {"NDVI": {"value": 0.6}, "NDRE": {"value": 0.4}},
        },
        "suspicious_regions": {
            "spot_count": spot_count,
            "spots": spots,
            "available_maps": ["NDVI", "NDRE"],
            "available_anomaly_maps": ["low_ndvi", "low_ndre"],
            "parameters": {
                "score_threshold": 0.55,
                "min_area_px": 20,
                "morphology_iterations": 1,
                "texture_window": 5,
            },
        },
        "warnings": ["target band 940 is missing"],
    }


def test_classify_anomaly_level_uses_counts_and_scores() -> None:
    """The deterministic label should follow the suspicious-region profile."""

    low_report = _report_with_spots(0, [])
    moderate_report = _report_with_spots(2, [0.58, 0.66])
    high_report = _report_with_spots(4, [0.7, 0.76, 0.81, 0.88])

    assert classify_anomaly_level(low_report) == "anomalie redusa"
    assert classify_anomaly_level(moderate_report) == "anomalie moderata"
    assert classify_anomaly_level(high_report) == "anomalie ridicata"


def test_readable_text_includes_selected_region_and_report_sections() -> None:
    """Summary and detailed text should surface the important report fields."""

    report = _report_with_spots(2, [0.62, 0.71])
    selected_spot = {
        "label": "7",
        "area_px": "33",
        "severity_rank": "1",
        "severity_score": "2.5",
        "mean_suspiciousness_score": "0.81",
        "max_suspiciousness_score": "0.89",
        "bbox_x_min": "1",
        "bbox_y_min": "2",
        "bbox_x_max": "5",
        "bbox_y_max": "6",
        "centroid_x": "3.5",
        "centroid_y": "4.5",
        "ndvi": "0.2",
        "ndre": "0.1",
        "gndvi": "0.15",
        "ndwi_850_940": "0.05",
    }

    summary = build_summary_text(report, selected_spot=selected_spot)
    detailed = build_detailed_report_text(report, selected_spot=selected_spot)

    assert "Rezumat determinist" in summary
    assert "Eticheta anomaliei: anomalie moderata" in summary
    assert "Interpretare" in summary
    assert "Stare generala" in summary
    assert "Regiune selectata" in summary
    assert "Eticheta: 7" in summary
    assert "BBox: (1, 2) la (5, 6)" in summary
    assert "fara diagnostic AI" in summary

    assert "Raport de analiza a sanatatii plantelor" in detailed
    assert "Sursa" in detailed
    assert "Lungimi de unda" in detailed
    assert "Frunza intreaga" in detailed
    assert "Interpretare" in detailed
    assert "Regiuni suspecte" in detailed
    assert "Regiunea 1" in detailed
    assert "Avertismente" in detailed
