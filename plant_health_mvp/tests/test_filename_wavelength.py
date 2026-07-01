"""Tests for filename-based wavelength inference."""

from __future__ import annotations

from plant_health_mvp.core.filename_wavelength import infer_wavelength_from_filename


def test_infer_wavelength_from_filename_uses_first_three_digits() -> None:
    """The helper should read the first three filename digits as the wavelength."""

    assert infer_wavelength_from_filename("850_leaf_capture.png") == 850.0
    assert infer_wavelength_from_filename("nir850_closeup.jpg") == 850.0
    assert infer_wavelength_from_filename("940-water-band.tif") == 940.0


def test_infer_wavelength_from_filename_returns_none_without_enough_digits() -> None:
    """Filenames without three digits should not invent a wavelength."""

    assert infer_wavelength_from_filename("leaf.png") is None
    assert infer_wavelength_from_filename("x9y.png") is None
