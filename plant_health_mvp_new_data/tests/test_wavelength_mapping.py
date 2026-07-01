"""Tests for wavelength inspection and target-band mapping."""

from __future__ import annotations

from plant_health_mvp.models.sample import VALID_STATUSES
from plant_health_mvp.wavelength_mapping import map_target_wavelengths


def test_target_mapping_covers_exact_nearest_interpolated_and_missing() -> None:
    """The mapper should classify exact, nearest, interpolated, and missing bands."""

    available_wavelengths = [532.0, 676.0, 700.0, 750.0]
    target_wavelengths = [532.0, 680.0, 725.0, 940.0]

    mapping = map_target_wavelengths(
        available_wavelengths=available_wavelengths,
        target_wavelengths=target_wavelengths,
    )

    assert set(mapping) == {"532", "680", "725", "940"}
    assert set(VALID_STATUSES) >= {"exact", "nearest", "interpolated", "missing"}

    exact = mapping["532"]
    assert exact.status == "exact"
    assert exact.source_indices == (0,)
    assert exact.source_wavelengths == (532.0,)

    nearest = mapping["680"]
    assert nearest.status == "nearest"
    assert nearest.source_indices == (1,)
    assert nearest.source_wavelengths == (676.0,)
    assert nearest.distance_nm == 4.0

    interpolated = mapping["725"]
    assert interpolated.status == "interpolated"
    assert interpolated.source_indices == (2, 3)
    assert interpolated.source_wavelengths == (700.0, 750.0)
    assert len(interpolated.weights) == 2
    assert abs(sum(interpolated.weights) - 1.0) < 1e-9

    missing = mapping["940"]
    assert missing.status == "missing"
    assert missing.source_indices == ()
    assert missing.source_wavelengths == ()

