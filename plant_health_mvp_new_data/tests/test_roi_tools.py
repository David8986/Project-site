"""Tests for ROI comparison helpers."""

from __future__ import annotations

import numpy as np

from plant_health_mvp.models.sample import SpectralSample
from plant_health_mvp.roi_tools import compare_roi_to_leaf


def test_compare_roi_to_leaf_reports_target_band_deltas() -> None:
    """ROI comparison should use canonical target-band averages."""

    sample = SpectralSample(
        source_type="hyperspectral_cube",
        available_wavelengths=np.array([680.0, 850.0]),
        data=np.ones((4, 4, 2)),
        target_bands={
            "680": np.full((4, 4), 0.2),
            "850": np.full((4, 4), 0.8),
        },
        metadata={},
    )
    sample.target_bands["680"][1:3, 1:3] = 0.4
    sample.target_bands["850"][1:3, 1:3] = 0.6

    comparison = compare_roi_to_leaf(sample, 1, 1, 2, 2, {"680": 0.2, "850": 0.8})

    assert comparison["bbox"] == [1, 1, 3, 3]
    assert comparison["average_bands"]["680"] == 0.4
    assert comparison["average_bands"]["850"] == 0.6
    assert comparison["delta_from_leaf_average"]["680"] == 0.2
    assert round(comparison["delta_from_leaf_average"]["850"], 6) == -0.2
    assert "NDVI" in comparison["indices"]
