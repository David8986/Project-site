"""Tests for localized suspicious spot detection."""

from __future__ import annotations

import numpy as np

from plant_health_mvp.anomaly_detection import SpotDetectionConfig, detect_suspicious_spots
from plant_health_mvp.models.sample import SpectralSample


def test_detect_suspicious_spots_finds_synthetic_low_ndvi_patch() -> None:
    """A small low-NIR/high-red patch should be detected inside the leaf mask."""

    red = np.full((20, 20), 0.2, dtype=float)
    red_edge = np.full((20, 20), 0.35, dtype=float)
    nir = np.full((20, 20), 0.8, dtype=float)
    green = np.full((20, 20), 0.25, dtype=float)
    water = np.full((20, 20), 0.45, dtype=float)
    red[8:13, 8:13] = 0.55
    red_edge[8:13, 8:13] = 0.3
    nir[8:13, 8:13] = 0.25

    sample = SpectralSample(
        source_type="hyperspectral_cube",
        available_wavelengths=np.array([556.0, 680.0, 725.0, 850.0, 940.0]),
        data=None,
        target_bands={
            "556": green,
            "680": red,
            "725": red_edge,
            "850": nir,
            "940": water,
        },
        mask=np.ones((20, 20), dtype=bool),
        metadata={},
    )

    result = detect_suspicious_spots(
        sample,
        config=SpotDetectionConfig(score_threshold=0.2, min_area_px=5, morphology_iterations=0),
    )

    assert result["spot_count"] >= 1
    assert result["suspicious_mask"][10, 10]
    first_spot = result["spots"][0]
    assert first_spot["severity_score"] > 0
    assert first_spot["severity_rank"] >= 1
    assert "delta_from_nearby_background" in first_spot
