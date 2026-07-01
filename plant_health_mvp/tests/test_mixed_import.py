"""Tests for mixed image bundle import support."""

from __future__ import annotations

from pathlib import Path

import numpy as np
import pytest
from PIL import Image

from plant_health_mvp.core.mixed_import import (
    load_mixed_image_bundle,
    write_mixed_image_bundle_spec,
)


def _write_rgb(path: Path) -> None:
    """Write a small RGB test image with stable channel values."""

    image = np.zeros((4, 5, 3), dtype=np.uint8)
    image[:, :] = [10, 20, 30]
    Image.fromarray(image, mode="RGB").save(path)


def _write_gray(path: Path, shape: tuple[int, int], value: int) -> None:
    """Write a small grayscale test image."""

    image = np.full(shape, value, dtype=np.uint8)
    Image.fromarray(image, mode="L").save(path)


def test_load_mixed_image_bundle_combines_rgb_and_explicit_bands(tmp_path: Path) -> None:
    """A mixed spec should create a spectral sample with aligned bands."""

    rgb_path = tmp_path / "rgb.png"
    nir_path = tmp_path / "nir.png"
    red_edge_path = tmp_path / "red_edge.png"
    water_path = tmp_path / "water.png"
    spec_path = tmp_path / "bundle.json"

    _write_rgb(rgb_path)
    _write_gray(nir_path, (2, 3), 200)
    _write_gray(red_edge_path, (4, 5), 120)
    _write_gray(water_path, (2, 3), 80)

    write_mixed_image_bundle_spec(
        spec_path,
        {
            "sample_id": "leaf_mix",
            "alignment": {
                "mode": "resize_to_reference",
                "reference": "first",
                "resample": "nearest",
            },
            "entries": [
                {"path": "rgb.png", "type": "rgb"},
                {
                    "path": "nir.png",
                    "type": "grayscale",
                    "role": "NIR",
                    "wavelength": 850,
                },
                {
                    "path": "red_edge.png",
                    "type": "grayscale",
                    "role": "RED_EDGE",
                    "wavelength_nm": 725,
                },
                {
                    "path": "water.png",
                    "type": "grayscale",
                    "role": "WATER_BAND",
                    "wavelength": 940,
                },
            ],
        },
    )

    sample = load_mixed_image_bundle(spec_path)

    assert sample.source_type == "mixed_image_bundle"
    assert sample.data is not None
    assert sample.data.shape == (4, 5, 6)
    np.testing.assert_allclose(
        sample.available_wavelengths,
        np.array([650.0, 556.0, 532.0, 850.0, 725.0, 940.0]),
    )
    np.testing.assert_allclose(sample.data[:, :, 0], np.full((4, 5), 10 / 255.0))
    np.testing.assert_allclose(sample.target_bands["850"], np.full((4, 5), 200 / 255.0))

    assert sample.band_status == {
        "650": "exact",
        "556": "exact",
        "532": "exact",
        "850": "exact",
        "725": "exact",
        "940": "exact",
    }
    assert sample.metadata["source_data_kind"] == "mixed_image_data"
    assert sample.metadata["analysis_data_kind"] == "mixed_image_intensity"
    assert sample.metadata["alignment_status"] == "resized"
    assert sample.metadata["roles"]["R_650"] == "RED"
    assert sample.metadata["roles"]["NIR_850"] == "NIR"
    assert sample.metadata["wavelengths"]["WATER_BAND_940"] == 940.0
    assert sample.metadata["channel_role_labels"] == [
        "R_650",
        "G_556",
        "B_532",
        "NIR_850",
        "RED_EDGE_725",
        "WATER_BAND_940",
    ]
    assert len(sample.metadata["imported_files"]) == 4


def test_load_mixed_image_bundle_strict_alignment_rejects_mismatched_shapes(
    tmp_path: Path,
) -> None:
    """Alignment mode 'none' should reject mismatched image shapes."""

    rgb_path = tmp_path / "rgb.png"
    nir_path = tmp_path / "nir.png"
    spec_path = tmp_path / "bundle.json"

    _write_rgb(rgb_path)
    _write_gray(nir_path, (2, 3), 200)

    write_mixed_image_bundle_spec(
        spec_path,
        {
            "alignment": "none",
            "entries": [
                {"path": "rgb.png", "type": "rgb", "channels": ["R"]},
                {
                    "path": "nir.png",
                    "type": "grayscale",
                    "role": "NIR",
                    "wavelength": 850,
                },
            ],
        },
    )

    with pytest.raises(ValueError, match="mismatched shapes"):
        load_mixed_image_bundle(spec_path)


def test_load_mixed_image_bundle_infers_wavelength_from_filename_when_missing(
    tmp_path: Path,
) -> None:
    """A grayscale entry can omit wavelength when the filename starts with it."""

    rgb_path = tmp_path / "rgb.png"
    nir_path = tmp_path / "850_leaf_nir.png"
    spec_path = tmp_path / "bundle.json"

    _write_rgb(rgb_path)
    _write_gray(nir_path, (4, 5), 180)

    write_mixed_image_bundle_spec(
        spec_path,
        {
            "alignment": {"mode": "resize_only", "reference": "first"},
            "entries": [
                {"path": "rgb.png", "type": "rgb"},
                {
                    "path": "850_leaf_nir.png",
                    "type": "grayscale",
                    "role": "NIR",
                },
            ],
        },
    )

    sample = load_mixed_image_bundle(spec_path)

    assert 850.0 in sample.available_wavelengths.tolist()
    assert sample.metadata["wavelengths"]["NIR_850"] == 850.0
