"""Tests for vegetation-spectrum aggregation."""

from __future__ import annotations

import numpy as np

from plant_health_mvp.models.sample import SpectralSample
from plant_health_mvp.spectrum import compute_average_spectrum


def test_average_spectrum_uses_masked_means_for_image_like_bands() -> None:
    """Masked pixels should define the average reflectance for each band."""

    sample = SpectralSample(
        source_type="hyperspectral_cube",
        available_wavelengths=np.array([680.0, 850.0], dtype=float),
        data=None,
        target_bands={
            "680": np.array([[1.0, 2.0], [3.0, 4.0]], dtype=float),
            "850": np.array([[10.0, 20.0], [30.0, 40.0]], dtype=float),
        },
        mask=np.array([[True, False], [False, True]], dtype=bool),
        metadata={},
    )

    averages, metadata = compute_average_spectrum(sample)

    assert averages["680"] == 2.5
    assert averages["850"] == 25.0
    assert metadata["vegetation_pixel_count"] == 2
    assert metadata["mask_used"] is True
    assert metadata["mask_strategy"] == "vegetation_only_for_matching_2d_bands"
    assert metadata["per_band"]["680"]["used_mask"] is True
    assert metadata["per_band"]["850"]["used_mask"] is True


def test_average_spectrum_handles_empty_masks() -> None:
    """An empty vegetation mask should yield ``None`` averages without crashing."""

    sample = SpectralSample(
        source_type="hyperspectral_cube",
        available_wavelengths=np.array([680.0, 850.0], dtype=float),
        data=None,
        target_bands={
            "680": np.array([[1.0, 2.0], [3.0, 4.0]], dtype=float),
            "850": np.array([[10.0, 20.0], [30.0, 40.0]], dtype=float),
        },
        mask=np.zeros((2, 2), dtype=bool),
        metadata={},
    )

    averages, metadata = compute_average_spectrum(sample)

    assert averages == {"680": None, "850": None}
    assert metadata["vegetation_pixel_count"] == 0
    assert metadata["mask_strategy"] == "vegetation_mask_present_but_empty"
    assert "no vegetation pixels" in metadata["note"].lower()

