"""Wavelength inspection and target-band mapping helpers.

This module keeps the source dataset format at the edge. It inspects the
available wavelengths, maps them onto the canonical 7-band target set, and
returns a compact description that downstream code can use without knowing
anything about the original source layout.
"""

from __future__ import annotations

from typing import Any, Sequence

import numpy as np

from .models.sample import BandMapping, SpectralSample, TARGET_WAVELENGTHS_NM, VALID_STATUSES


def _to_valid_wavelength_arrays(
    available_wavelengths: Sequence[float] | np.ndarray,
) -> tuple[np.ndarray, np.ndarray]:
    """Return valid wavelength values and their original indices.

    NaN and non-finite values are removed. The returned index array refers to
    the original order of the input sequence before any sorting happens.
    """

    if isinstance(available_wavelengths, np.ndarray):
        values = np.asarray(available_wavelengths, dtype=float).ravel()
    else:
        values = np.asarray(list(available_wavelengths), dtype=float).ravel()

    if values.size == 0:
        return np.asarray([], dtype=float), np.asarray([], dtype=int)

    valid_mask = np.isfinite(values)
    valid_values = values[valid_mask]
    valid_indices = np.flatnonzero(valid_mask)
    return valid_values, valid_indices


def _to_float_array(values: Sequence[float] | np.ndarray) -> np.ndarray:
    """Convert a sequence of numeric values into a flat float array."""

    if isinstance(values, np.ndarray):
        return np.asarray(values, dtype=float).ravel()
    return np.asarray(list(values), dtype=float).ravel()


def _band_key(wavelength: float) -> str:
    """Return the canonical dictionary key for a wavelength."""

    return SpectralSample.band_key(float(wavelength))


def inspect_wavelengths(available_wavelengths: Sequence[float] | np.ndarray) -> dict[str, Any]:
    """Inspect an input wavelength sequence.

    The result is safe for empty or NaN-only inputs and preserves the original
    order of valid values so callers can understand how the source data arrived.
    """

    valid_values, _ = _to_valid_wavelength_arrays(available_wavelengths)
    sorted_values = np.sort(valid_values) if valid_values.size else valid_values

    return {
        "count": int(valid_values.size),
        "min": float(np.min(valid_values)) if valid_values.size else None,
        "max": float(np.max(valid_values)) if valid_values.size else None,
        "sorted": sorted_values.tolist(),
        "original_order": valid_values.tolist(),
    }


def _make_missing_mapping(target_wavelength: float, note: str) -> BandMapping:
    """Create a missing-band mapping with a helpful note."""

    return BandMapping(
        target_wavelength=float(target_wavelength),
        status="missing",
        source_indices=(),
        source_wavelengths=(),
        weights=(),
        distance_nm=None,
        note=note,
    )


def _nearest_source(
    target_wavelength: float,
    source_wavelengths: np.ndarray,
    source_indices: np.ndarray,
) -> tuple[int, float, float]:
    """Return the nearest source wavelength and its original index."""

    deltas = np.abs(source_wavelengths - target_wavelength)
    order = np.lexsort((source_indices, deltas))
    nearest_pos = int(order[0])
    return (
        int(source_indices[nearest_pos]),
        float(source_wavelengths[nearest_pos]),
        float(deltas[nearest_pos]),
    )


def _interpolated_source(
    target_wavelength: float,
    source_wavelengths: np.ndarray,
    source_indices: np.ndarray,
    interpolation_max_gap_nm: float,
) -> BandMapping | None:
    """Build an interpolated mapping when the target is bracketed by sources."""

    if source_wavelengths.size < 2:
        return None

    sort_order = np.argsort(source_wavelengths, kind="mergesort")
    sorted_wavelengths = source_wavelengths[sort_order]
    sorted_indices = source_indices[sort_order]

    upper_pos = int(np.searchsorted(sorted_wavelengths, target_wavelength, side="right"))
    lower_pos = upper_pos - 1
    if lower_pos < 0 or upper_pos >= sorted_wavelengths.size:
        return None

    lower_wavelength = float(sorted_wavelengths[lower_pos])
    upper_wavelength = float(sorted_wavelengths[upper_pos])
    gap_nm = upper_wavelength - lower_wavelength
    if gap_nm <= 0 or gap_nm > interpolation_max_gap_nm:
        return None

    lower_weight = (upper_wavelength - target_wavelength) / gap_nm
    upper_weight = (target_wavelength - lower_wavelength) / gap_nm

    return BandMapping(
        target_wavelength=float(target_wavelength),
        status="interpolated",
        source_indices=(int(sorted_indices[lower_pos]), int(sorted_indices[upper_pos])),
        source_wavelengths=(lower_wavelength, upper_wavelength),
        weights=(float(lower_weight), float(upper_weight)),
        distance_nm=float(min(target_wavelength - lower_wavelength, upper_wavelength - target_wavelength)),
        note=(
            f"Interpolated between {lower_wavelength:g} nm and {upper_wavelength:g} nm "
            f"(gap {gap_nm:g} nm)."
        ),
    )


def map_target_wavelengths(
    available_wavelengths: Sequence[float] | np.ndarray,
    target_wavelengths: Sequence[float] | np.ndarray = TARGET_WAVELENGTHS_NM,
    exact_tolerance_nm: float = 1.0,
    nearest_tolerance_nm: float = 15.0,
    interpolation_max_gap_nm: float = 80.0,
    prefer_interpolation: bool = False,
) -> dict[str, BandMapping]:
    """Map available wavelengths to the canonical target band set.

    Exact matches win first. After that, the function chooses either nearest or
    interpolated bands depending on the preference flag and tolerance checks.
    Missing targets are returned explicitly so downstream code can remain
    format-agnostic.
    """

    source_values, source_indices = _to_valid_wavelength_arrays(available_wavelengths)
    target_array = _to_float_array(target_wavelengths)

    if source_values.size == 0:
        mapping: dict[str, BandMapping] = {}
        for index, target in enumerate(target_array):
            key = _band_key(target) if np.isfinite(target) else f"invalid_target_{index}"
            mapping[key] = _make_missing_mapping(
                float(target) if np.isfinite(target) else float("nan"),
                "No valid source wavelengths were available for mapping.",
            )
        return mapping

    mapping: dict[str, BandMapping] = {}

    for index, target_wavelength in enumerate(target_array):
        if not np.isfinite(target_wavelength):
            mapping[f"invalid_target_{index}"] = _make_missing_mapping(
                float("nan"),
                "Target wavelength was not finite and could not be mapped.",
            )
            continue

        key = _band_key(target_wavelength)
        nearest_index, nearest_wavelength, nearest_delta = _nearest_source(
            float(target_wavelength),
            source_values,
            source_indices,
        )

        if nearest_delta <= exact_tolerance_nm:
            mapping[key] = BandMapping(
                target_wavelength=float(target_wavelength),
                status="exact",
                source_indices=(nearest_index,),
                source_wavelengths=(nearest_wavelength,),
                weights=(1.0,),
                distance_nm=float(nearest_delta),
                note=f"Exact or near-exact source match at {nearest_wavelength:g} nm.",
            )
            continue

        interpolated = _interpolated_source(
            float(target_wavelength),
            source_values,
            source_indices,
            interpolation_max_gap_nm,
        )

        if prefer_interpolation and interpolated is not None:
            mapping[key] = interpolated
            continue

        if nearest_delta <= nearest_tolerance_nm:
            mapping[key] = BandMapping(
                target_wavelength=float(target_wavelength),
                status="nearest",
                source_indices=(nearest_index,),
                source_wavelengths=(nearest_wavelength,),
                weights=(1.0,),
                distance_nm=float(nearest_delta),
                note=f"Nearest source wavelength is {nearest_wavelength:g} nm.",
            )
            continue

        if interpolated is not None:
            mapping[key] = interpolated
            continue

        mapping[key] = _make_missing_mapping(
            float(target_wavelength),
            (
                "No exact, nearest, or interpolatable source band was available "
                f"within the configured tolerances for {target_wavelength:g} nm."
            ),
        )

    return mapping


def summarize_mapping(mapping: dict[str, BandMapping]) -> dict[str, Any]:
    """Summarize a band-mapping result for reporting and JSON output."""

    per_target: dict[str, Any] = {}
    missing_targets: list[str] = []
    status_counts: dict[str, int] = {status: 0 for status in VALID_STATUSES}

    for target_key, band_mapping in mapping.items():
        per_target[target_key] = band_mapping.to_dict()
        status = band_mapping.status
        if status in status_counts:
            status_counts[status] += 1
        else:
            status_counts[status] = 1
        if status == "missing":
            missing_targets.append(target_key)

    return {
        "per_target": per_target,
        "missing_targets": missing_targets,
        "status_counts": status_counts,
        "mapped_targets": int(len(mapping) - len(missing_targets)),
        "total_targets": int(len(mapping)),
    }
