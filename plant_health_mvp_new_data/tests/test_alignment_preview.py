"""Tests for shared alignment preview artifacts."""

from __future__ import annotations

from pathlib import Path

import numpy as np
from PIL import Image

from plant_health_mvp.core.alignment_preview import (
    build_alignment_preview,
    export_alignment_preview_artifacts,
    load_alignment_preview_artifacts,
)
from plant_health_mvp.core.mixed_import import load_mixed_image_bundle, write_mixed_image_bundle_spec


def test_alignment_preview_builds_before_after_images(tmp_path: Path) -> None:
    """Mixed-image samples should expose visual alignment preview data."""

    rgb = np.zeros((8, 10, 3), dtype=np.uint8)
    rgb[:, :] = [20, 90, 30]
    nir = np.full((4, 5), 180, dtype=np.uint8)
    Image.fromarray(rgb, mode="RGB").save(tmp_path / "rgb.png")
    Image.fromarray(nir, mode="L").save(tmp_path / "nir.png")

    spec_path = tmp_path / "bundle.json"
    write_mixed_image_bundle_spec(
        spec_path,
        {
            "sample_id": "preview_case",
            "alignment": {"mode": "resize_only", "reference": "first"},
            "entries": [
                {"path": "rgb.png", "type": "rgb"},
                {"path": "nir.png", "type": "grayscale", "role": "NIR", "wavelength": 850},
            ],
        },
    )
    sample = load_mixed_image_bundle(spec_path)

    preview = build_alignment_preview(sample)

    assert preview is not None
    assert preview.reference_image.shape == (8, 10, 3)
    assert preview.moving_before.shape == (8, 10, 3)
    assert preview.moving_after.shape == (8, 10, 3)
    assert preview.overlay_before.shape == (8, 10, 3)
    assert preview.overlay_after.shape == (8, 10, 3)
    assert preview.metadata["alignment_mode"] == "resize_only"
    assert preview.metadata["moving_image_id"] == "image_002"


def test_alignment_preview_exports_and_reloads(tmp_path: Path) -> None:
    """Analysis outputs should be able to reload the shared preview package."""

    rgb = np.zeros((6, 7, 3), dtype=np.uint8)
    rgb[:, :] = [20, 90, 30]
    nir = np.full((6, 7), 180, dtype=np.uint8)
    Image.fromarray(rgb, mode="RGB").save(tmp_path / "rgb.png")
    Image.fromarray(nir, mode="L").save(tmp_path / "nir.png")

    spec_path = tmp_path / "bundle.json"
    write_mixed_image_bundle_spec(
        spec_path,
        {
            "alignment": {"mode": "resize_only", "reference": "first"},
            "entries": [
                {"path": "rgb.png", "type": "rgb"},
                {"path": "nir.png", "type": "grayscale", "role": "NIR", "wavelength": 850},
            ],
        },
    )
    sample = load_mixed_image_bundle(spec_path)
    paths = export_alignment_preview_artifacts(sample, tmp_path / "output")
    reloaded = load_alignment_preview_artifacts(tmp_path / "output")

    assert paths["metadata"].endswith("alignment_preview.json")
    assert reloaded is not None
    assert reloaded.reference_image.shape == (6, 7, 3)
    assert reloaded.metadata["reference_image_id"] == "image_001"
