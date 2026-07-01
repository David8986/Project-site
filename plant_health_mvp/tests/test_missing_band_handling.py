"""Tests for safe handling of missing target bands during extraction."""

from __future__ import annotations

import numpy as np

from plant_health_mvp.band_extraction import extract_target_bands
from plant_health_mvp.models.sample import BandMapping, SpectralSample


def test_missing_band_extraction_returns_none_without_crashing() -> None:
    """Missing target bands should remain ``None`` and not break extraction."""

    data = np.array(
        [
            [[1.0, 10.0], [2.0, 20.0]],
            [[3.0, 30.0], [4.0, 40.0]],
        ],
        dtype=float,
    )
    sample = SpectralSample(
        source_type="hyperspectral_cube",
        available_wavelengths=np.array([680.0, 850.0], dtype=float),
        data=data,
        target_bands={},
        metadata={},
    )
    mappings = {
        "680": BandMapping(
            target_wavelength=680.0,
            status="exact",
            source_indices=(0,),
            source_wavelengths=(680.0,),
            weights=(1.0,),
            distance_nm=0.0,
        ),
        "850": BandMapping(
            target_wavelength=850.0,
            status="missing",
        ),
    }

    extracted = extract_target_bands(sample, mappings)

    assert set(extracted) == {"680", "850"}
    np.testing.assert_array_equal(extracted["680"], data[:, :, 0])
    assert extracted["850"] is None

