"""Target-band extraction helpers for the plant-health MVP.

This module keeps the downstream pipeline independent from the original dataset
format by projecting a :class:`~plant_health_mvp.models.sample.SpectralSample`
into the canonical target-band representation.
"""

from __future__ import annotations

from typing import Mapping

import numpy as np

from .models.sample import BandMapping, SpectralSample, VALID_STATUSES


def extract_target_bands(
    sample: SpectralSample,
    mappings: Mapping[str, BandMapping],
) -> dict[str, np.ndarray | None]:
    """Extract canonical target bands from a sample.

    Exact and nearest mappings copy a single source band. Interpolated mappings
    linearly combine two source bands using the provided weights. Missing bands
    remain ``None``.

    Parameters
    ----------
    sample:
        Normalized spectral sample containing the source data.
    mappings:
        Mapping from target wavelength key to extraction metadata.

    Returns
    -------
    dict[str, np.ndarray | None]
        A target-band dictionary keyed by the same target labels used in
        ``mappings``.
    """

    target_bands: dict[str, np.ndarray | None] = {}
    data = sample.data

    for key, mapping in _iter_mappings_in_canonical_order(mappings):
        if mapping.status not in VALID_STATUSES:
            raise ValueError(
                f"Unsupported band status {mapping.status!r} for target band {key!r}."
            )

        if mapping.status == "missing" or data is None:
            target_bands[key] = None
            continue

        band_axis = _band_axis_for_sample(data)
        target_bands[key] = _extract_band_from_mapping(data, band_axis, key, mapping)

    return target_bands


def apply_target_bands(
    sample: SpectralSample,
    mappings: Mapping[str, BandMapping],
) -> SpectralSample:
    """Populate the canonical target-band fields on a sample.

    The sample is updated in place and returned for convenience so the caller
    can continue passing the same object through the rest of the pipeline.
    """

    target_bands = extract_target_bands(sample, mappings)

    band_status: dict[str, str] = {}
    band_mappings: dict[str, BandMapping] = {}
    for key, mapping in _iter_mappings_in_canonical_order(mappings):
        band_mappings[key] = mapping
        band_status[key] = "missing" if target_bands.get(key) is None else mapping.status

    sample.target_bands = target_bands
    sample.band_status = band_status
    sample.band_mappings = band_mappings
    return sample


def normalize_band_for_image(band: np.ndarray) -> np.ndarray:
    """Normalize a band to ``uint8`` for quick visualization/debugging.

    The scaling is deterministic min-max normalization over the finite values in
    the array. Non-finite values are treated as background.
    """

    array = np.asarray(band)
    if array.ndim == 0:
        array = array.reshape(1)

    if array.ndim not in (1, 2):
        raise ValueError(
            "normalize_band_for_image expects a 1D or 2D array, "
            f"got shape {array.shape}."
        )

    finite_mask = np.isfinite(array)
    if not finite_mask.any():
        return np.zeros(array.shape, dtype=np.uint8)

    finite_values = array[finite_mask].astype(np.float64, copy=False)
    min_value = float(np.min(finite_values))
    max_value = float(np.max(finite_values))

    if np.isclose(min_value, max_value):
        return np.zeros(array.shape, dtype=np.uint8)

    normalized = np.zeros(array.shape, dtype=np.float64)
    normalized[finite_mask] = (finite_values - min_value) / (max_value - min_value)
    normalized = np.clip(normalized * 255.0, 0.0, 255.0)
    return normalized.astype(np.uint8)


def _iter_mappings_in_canonical_order(
    mappings: Mapping[str, BandMapping],
) -> list[tuple[str, BandMapping]]:
    """Return mappings sorted by numeric target wavelength when possible."""

    def sort_key(item: tuple[str, BandMapping]) -> tuple[float, str]:
        key, mapping = item
        try:
            return float(key), key
        except ValueError:
            return float(mapping.target_wavelength), key

    return sorted(mappings.items(), key=sort_key)


def _band_axis_for_sample(data: np.ndarray) -> int:
    """Return the band axis for supported sample shapes."""

    if data.ndim == 3:
        return 2
    if data.ndim == 2:
        return 1
    raise ValueError(
        "Unsupported sample data shape. Expected an image cube shaped "
        "(height, width, bands) or a spectral table shaped (rows, bands), "
        f"got {data.shape}."
    )


def _validate_source_indices(
    data: np.ndarray,
    band_axis: int,
    mapping: BandMapping,
    target_key: str,
) -> None:
    """Validate that mapping indices are usable for the source data."""

    band_count = int(data.shape[band_axis])
    if mapping.status in {"exact", "nearest"}:
        if len(mapping.source_indices) != 1:
            raise ValueError(
                f"Target band {target_key!r} uses status {mapping.status!r} but "
                f"has {len(mapping.source_indices)} source indices; expected 1."
            )
        index = mapping.source_indices[0]
        if index < 0 or index >= band_count:
            raise ValueError(
                f"Target band {target_key!r} references invalid source index {index} "
                f"for data with {band_count} bands."
            )
        return

    if mapping.status == "interpolated":
        if len(mapping.source_indices) != 2:
            raise ValueError(
                f"Target band {target_key!r} uses interpolated mapping but has "
                f"{len(mapping.source_indices)} source indices; expected 2."
            )
        if len(mapping.weights) != 2:
            raise ValueError(
                f"Target band {target_key!r} uses interpolated mapping but has "
                f"{len(mapping.weights)} weights; expected 2."
            )
        for index in mapping.source_indices:
            if index < 0 or index >= band_count:
                raise ValueError(
                    f"Target band {target_key!r} references invalid source index {index} "
                    f"for data with {band_count} bands."
                )


def _extract_band_from_mapping(
    data: np.ndarray,
    band_axis: int,
    target_key: str,
    mapping: BandMapping,
) -> np.ndarray:
    """Extract a single target band using the supplied mapping."""

    _validate_source_indices(data, band_axis, mapping, target_key)

    if mapping.status in {"exact", "nearest"}:
        source_index = mapping.source_indices[0]
        return np.take(data, source_index, axis=band_axis)

    if mapping.status == "interpolated":
        first_index, second_index = mapping.source_indices
        first_weight, second_weight = mapping.weights
        first_band = np.take(data, first_index, axis=band_axis).astype(np.float64, copy=False)
        second_band = np.take(data, second_index, axis=band_axis).astype(np.float64, copy=False)
        return (first_weight * first_band) + (second_weight * second_band)

    return None


__all__ = [
    "apply_target_bands",
    "extract_target_bands",
    "normalize_band_for_image",
]
