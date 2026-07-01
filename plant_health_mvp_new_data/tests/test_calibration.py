"""Tests for reflectance calibration behavior."""

from __future__ import annotations

import numpy as np

from plant_health_mvp.calibration import calibrate_reflectance


def test_calibration_reports_zero_denominator_as_invalid() -> None:
    """Pixels with white == dark should become NaN, not fake reflectance."""

    cube = np.array([[[2.0], [6.0]], [[3.0], [8.0]]], dtype=float)
    dark = np.array([[1.0], [2.0]], dtype=float)
    white = np.array([[1.0], [10.0]], dtype=float)

    reflectance, metadata = calibrate_reflectance(cube, dark, white, clip=False)

    assert metadata["calibration_applied"] is True
    assert metadata["analysis_data_kind"] == "calibrated_reflectance"
    assert metadata["invalid_denominator_count"] == 1
    assert np.isnan(reflectance[0, 0, 0])
    np.testing.assert_allclose(reflectance[:, 1, 0], np.array([0.5, 0.75]))
