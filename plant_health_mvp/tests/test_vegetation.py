"""Tests for vegetation-mask generation."""

from __future__ import annotations

import numpy as np

from plant_health_mvp.models.sample import SpectralSample
from plant_health_mvp.vegetation import build_vegetation_mask


def test_vegetation_mask_prefers_ndvi_when_680_and_850_exist() -> None:
    """When both 680 and 850 are available, NDVI should drive the mask."""

    sample = SpectralSample(
        source_type="hyperspectral_cube",
        available_wavelengths=np.array([680.0, 850.0], dtype=float),
        data=None,
        target_bands={
            "680": np.array([[0.2, 0.2], [0.2, 0.2]], dtype=float),
            "850": np.array([[0.5, 0.1], [0.4, 0.25]], dtype=float),
        },
        metadata={},
    )

    mask, metadata = build_vegetation_mask(sample, ndvi_threshold=0.2, cleanup=False)

    expected_mask = np.array([[True, False], [True, False]], dtype=bool)
    assert mask is not None
    np.testing.assert_array_equal(mask, expected_mask)
    assert metadata["method"] == "ndvi"
    assert metadata["used_bands"] == ["680", "850"]
    assert metadata["vegetation_pixel_count"] == 2


def test_vegetation_mask_falls_back_when_ndvi_bands_are_missing() -> None:
    """If 680 or 850 is missing, the fallback band threshold should be used."""

    sample = SpectralSample(
        source_type="hyperspectral_cube",
        available_wavelengths=np.array([532.0, 725.0], dtype=float),
        data=None,
        target_bands={
            "532": np.array([[0.1, 0.2], [0.3, 0.4]], dtype=float),
            "725": np.array([[1.0, 2.0], [3.0, 4.0]], dtype=float),
        },
        metadata={},
    )

    mask, metadata = build_vegetation_mask(sample, fallback_percentile=50.0, cleanup=False)

    expected_mask = np.array([[False, False], [True, True]], dtype=bool)
    assert mask is not None
    np.testing.assert_array_equal(mask, expected_mask)
    assert metadata["method"] == "percentile_threshold"
    assert metadata["used_bands"] == ["725"]
    assert "Missing one or both of 850 nm and 680 nm" in metadata["fallback_reason"]

