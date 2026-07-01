"""Tests for role-aware mixed-source scalar indices."""

from __future__ import annotations

from plant_health_mvp.core.mixed_indices import compute_role_aware_indices


def test_role_aware_indices_prefer_proper_ndvi_red() -> None:
    """NDVI should use 680 nm red when proper red and NIR averages exist."""

    result = compute_role_aware_indices(
        {
            "band_556": 20.0,
            "band_650": 12.0,
            "band_680": 10.0,
            "band_725": 30.0,
            "band_850": 50.0,
            "band_940": 25.0,
        }
    )

    ndvi = result["indices"]["NDVI"]

    assert ndvi["available"] is True
    assert ndvi["label"] == "NDVI (proper 680 nm red + NIR)"
    assert ndvi["bands_used"] == {"NIR": 850, "RED": 680}
    assert ndvi["value"] == 0.666667
    assert result["availability_summary"]["available_indices"] == [
        "NDVI",
        "NDRE",
        "GNDVI",
        "WATER_PROXY",
    ]


def test_role_aware_indices_label_rgb_red_ndvi_like() -> None:
    """An approximate RGB red source should be labeled as NDVI-like."""

    result = compute_role_aware_indices(
        {"650": 10.0, "850": 50.0},
        {
            "band_roles": {
                "RED": {
                    "band_key": "650",
                    "wavelength_nm": 650.0,
                    "status": "available",
                    "source_note": "RGB red channel labelled as 650 nm.",
                },
                "NIR": {
                    "band_key": "850",
                    "wavelength_nm": 850.0,
                    "status": "available",
                },
            }
        },
    )

    ndvi = result["indices"]["NDVI"]

    assert ndvi["available"] is True
    assert ndvi["label"] == "NDVI-like (RGB red + NIR)"
    assert ndvi["value"] == 0.666667
    assert ndvi["approximate"] is True
    assert "approximate RGB red/channel 650" in ndvi["source_note"]
    assert result["roles"]["RED"]["approximate_source"] is True


def test_role_aware_indices_report_missing_required_roles() -> None:
    """Missing role inputs should be unavailable with clear reasons."""

    result = compute_role_aware_indices({"850": 50.0})

    ndre = result["indices"]["NDRE"]
    ndvi = result["indices"]["NDVI"]

    assert ndre["available"] is False
    assert ndre["status"] == "unavailable"
    assert ndre["value"] is None
    assert ndre["missing_roles"] == ["RED_EDGE"]
    assert ndre["reason"] == "missing required role: RED_EDGE"
    assert ndvi["missing_roles"] == ["RED"]
    assert result["availability_summary"]["unavailable"] == 4


def test_role_aware_indices_compute_water_proxy() -> None:
    """Water proxy should compute when NIR and water-band roles are present."""

    result = compute_role_aware_indices(
        {"850": 50.0, "940": 25.0},
        {
            "roles": {
                "NIR": {"band_key": "850", "status": "available"},
                "WATER_BAND": {"band_key": "940", "status": "available"},
            }
        },
    )

    water = result["indices"]["WATER_PROXY"]

    assert water["available"] is True
    assert water["label"] == "Water proxy (water band + NIR)"
    assert water["value"] == 0.333333
    assert water["bands_used"] == {"NIR": 850, "WATER_BAND": 940}
    assert result["index_aliases"]["NDWI_850_940"] == "WATER_PROXY"
