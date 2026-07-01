"""Tests for RGB-only image input support."""

from __future__ import annotations

from argparse import Namespace
from pathlib import Path

import numpy as np
from PIL import Image

from plant_health_mvp.core.loader import load_sample
from plant_health_mvp.main import run_pipeline


def _write_rgb_leaf(path: Path) -> None:
    """Write a tiny RGB image with a green leaf-like patch."""

    image = np.zeros((32, 32, 3), dtype=np.uint8)
    image[:, :] = [30, 25, 20]
    image[8:24, 7:25] = [45, 150, 55]
    image[14:18, 14:19] = [130, 95, 45]
    Image.fromarray(image, mode="RGB").save(path)


def test_load_rgb_image_sample_labels_rgb_channels(tmp_path: Path) -> None:
    """A JPEG should load as an RGB-only three-band sample."""

    image_path = tmp_path / "leaf.jpg"
    _write_rgb_leaf(image_path)

    sample = load_sample(image_path)

    assert sample.source_type == "rgb_image"
    assert sample.metadata["rgb_only"] is True
    assert sample.metadata["analysis_data_kind"] == "rgb_intensity"
    assert sample.data is not None
    assert sample.data.shape == (32, 32, 3)
    np.testing.assert_allclose(sample.available_wavelengths, np.array([650.0, 556.0, 532.0]))


def test_pipeline_runs_rgb_image_without_wavelength_csv(tmp_path: Path) -> None:
    """The full pipeline should run on RGB-only images and emit RGB bands."""

    image_path = tmp_path / "leaf.jpg"
    output = tmp_path / "rgb_run"
    _write_rgb_leaf(image_path)

    artifacts = run_pipeline(
        Namespace(
            input=image_path,
            archive_sample=None,
            wavelengths=None,
            output=output,
            save_mock_dataset=False,
            exact_tolerance=1.0,
            nearest_tolerance=15.0,
            interpolation_max_gap=80.0,
            prefer_interpolation=False,
            band_profile="profile_7band_default",
            ndvi_threshold=0.2,
            fallback_percentile=70.0,
            no_mask_cleanup=False,
            spot_threshold=0.55,
            spot_min_area=3,
            spot_texture_window=5,
        )
    )

    assert artifacts["band_images"].keys() == {"532", "556", "650"}
    assert (output / "bands" / "band_532.png").exists()
    assert (output / "bands" / "band_556.png").exists()
    assert (output / "bands" / "band_650.png").exists()
    report = (output / "mapping_report.json").read_text(encoding="utf-8")
    assert "rgb_image_data" in report
    assert "profile_rgb_image" in report
    assert "RGB-only image input" in report
