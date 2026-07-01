"""Focused tests for the mixed-image import wizard helpers."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from plant_health_mvp.analysis_app.import_wizard import (
    SCHEMA_ID,
    MixedImportEntry,
    alignment_settings_from_mixed_import_spec,
    build_mixed_import_spec,
    build_quick_start_entries,
    entries_from_mixed_import_spec,
    load_mixed_import_spec,
    save_mixed_import_spec,
)


def test_quick_start_spec_maps_rgb_channels_and_nir_band(tmp_path: Path) -> None:
    """The quick-start preset should emit RGB channels plus an 850 nm NIR band."""

    rgb_path = tmp_path / "leaf_rgb.png"
    nir_path = tmp_path / "leaf_nir.png"
    rgb_path.write_bytes(b"rgb")
    nir_path.write_bytes(b"nir")

    spec = build_mixed_import_spec(
        build_quick_start_entries(rgb_path, nir_path),
        alignment_reference="image_001",
    )

    assert spec["schema"] == SCHEMA_ID
    assert spec["bundle_type"] == "mixed_image_bundle"
    assert spec["alignment"]["mode"] == "automatic_phase_ecc"
    assert spec["alignment"]["transform_model"] == "affine"
    assert spec["alignment"]["reference_image_id"] == "image_001"
    assert len(spec["images"]) == 2
    assert spec["images"][0]["assignment"] == "rgb"
    assert spec["images"][1]["assignment"] == "grayscale"
    assert [band["role"] for band in spec["bands"]] == ["RED", "GREEN", "BLUE", "NIR"]
    assert [band["wavelength_nm"] for band in spec["bands"]] == [650.0, 556.0, 532.0, 850.0]
    assert all(band["alignment_reference_image_id"] == "image_001" for band in spec["bands"])


def test_save_mixed_import_spec_writes_custom_role(tmp_path: Path) -> None:
    """Custom grayscale roles should keep both the canonical and display labels."""

    source_path = tmp_path / "band_705.tif"
    output_path = tmp_path / "bundle_spec"
    source_path.write_bytes(b"band")

    saved_path = save_mixed_import_spec(
        [
            MixedImportEntry(
                path=source_path,
                assignment="grayscale",
                role="custom",
                wavelength_nm=705.0,
                custom_role="CHLOROPHYLL_PROXY",
            )
        ],
        output_path,
    )

    assert saved_path == output_path.with_suffix(".json").resolve(strict=False)
    data = json.loads(saved_path.read_text(encoding="utf-8"))
    assert data["bands"][0]["role"] == "CUSTOM"
    assert data["bands"][0]["role_label"] == "CHLOROPHYLL_PROXY"
    assert data["bands"][0]["custom_role"] == "CHLOROPHYLL_PROXY"
    assert data["bands"][0]["wavelength_nm"] == 705.0


def test_custom_role_requires_label(tmp_path: Path) -> None:
    """A custom grayscale row without a label is not loader-ready."""

    source_path = tmp_path / "band.tif"
    source_path.write_bytes(b"band")

    with pytest.raises(ValueError, match="rol personalizat"):
        build_mixed_import_spec(
            [
                MixedImportEntry(
                    path=source_path,
                    assignment="grayscale",
                    role="CUSTOM",
                    wavelength_nm=705.0,
                )
            ]
        )


def test_build_mixed_import_spec_infers_wavelength_from_first_three_filename_digits(
    tmp_path: Path,
) -> None:
    """Grayscale rows without an explicit wavelength should use the filename."""

    source_path = tmp_path / "725_leaf_detail.png"
    source_path.write_bytes(b"band")

    spec = build_mixed_import_spec(
        [
            MixedImportEntry(
                path=source_path,
                assignment="grayscale",
                role="RED_EDGE",
                wavelength_nm=None,
            )
        ]
    )

    assert spec["images"][0]["wavelength_nm"] == 725.0
    assert spec["bands"][0]["wavelength_nm"] == 725.0


def test_existing_mixed_import_spec_can_be_reopened_for_editing(tmp_path: Path) -> None:
    """Saved mixed specs should round-trip back into editable rows."""

    first = tmp_path / "532.jpg"
    second = tmp_path / "850.jpg"
    first.write_bytes(b"blue")
    second.write_bytes(b"nir")
    saved_path = save_mixed_import_spec(
        [
            MixedImportEntry(first, assignment="grayscale", role="BLUE", wavelength_nm=532.0, image_id="band_532"),
            MixedImportEntry(second, assignment="grayscale", role="NIR", wavelength_nm=850.0, image_id="band_850"),
        ],
        tmp_path / "input_spec.json",
        alignment_reference="band_532",
        alignment_mode="none",
        transform_model="affine",
    )

    loaded = load_mixed_import_spec(saved_path)
    entries = entries_from_mixed_import_spec(loaded)
    settings = alignment_settings_from_mixed_import_spec(loaded)

    assert [entry.image_id for entry in entries] == ["band_532", "band_850"]
    assert [entry.wavelength_nm for entry in entries] == [532.0, 850.0]
    assert [entry.role for entry in entries] == ["BLUE", "NIR"]
    assert settings == {
        "mode": "none",
        "transform_model": "affine",
        "reference_image_id": "band_532",
    }
