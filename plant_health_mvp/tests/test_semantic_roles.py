"""Tests for semantic band-role resolution."""

from __future__ import annotations

import numpy as np

from plant_health_mvp.models.sample import SpectralSample
from plant_health_mvp.semantic_roles import resolve_semantic_roles


def test_red_role_falls_back_to_650_when_680_missing() -> None:
    """The RED role should prefer 680 but fall back to 650 when needed."""

    sample = SpectralSample(
        source_type="hyperspectral_cube",
        available_wavelengths=np.array([650.0, 850.0]),
        data=None,
        target_bands={"650": np.ones((2, 2)), "850": np.ones((2, 2))},
        metadata={},
    )

    roles = resolve_semantic_roles(sample)

    assert roles["RED"].band_key == "650"
    assert roles["NIR"].band_key == "850"
    assert roles["RED_EDGE"].status == "missing"
