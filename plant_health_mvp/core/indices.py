"""Scalar spectral-index calculations for the plant-health MVP.

This module uses average vegetation-band values, not per-pixel band images.
Per-pixel index maps can plug in later using the same formulas.
"""

from __future__ import annotations

import csv
import json
from pathlib import Path
from typing import Any, Callable, Mapping

from .interpretation import interpret_indices
from .models.sample import SpectralSample
from .mixed_indices import compute_role_aware_indices
from .outputs import ensure_output_dir
from .semantic_roles import resolve_semantic_roles

ROUND_DIGITS = 6
EPSILON = 1e-12

BandValues = Mapping[str, float | int | None]
IndexResult = dict[str, Any]


def _round_value(value: float | int | None) -> float | None:
    """Round JSON numeric output while preserving missing values."""

    if value is None:
        return None
    return round(float(value), ROUND_DIGITS)


def _band_key(wavelength: int) -> str:
    """Return the key used in average-spectrum dictionaries."""

    return str(int(wavelength))


def _prefixed_band_key(wavelength: int) -> str:
    """Return the key used in the indices report average-band section."""

    return f"band_{int(wavelength)}"


def _get_band(avg_bands: BandValues, wavelength: int) -> float | None:
    """Return a band average by numeric or ``band_``-prefixed key."""

    raw_value = avg_bands.get(_band_key(wavelength), avg_bands.get(_prefixed_band_key(wavelength)))
    if raw_value is None:
        return None
    return float(raw_value)


def _missing_result(
    formula: str,
    bands_used: Mapping[str, int],
    components: Mapping[str, float | int | None],
) -> IndexResult:
    """Create a standard result for an index with missing inputs."""

    return {
        "formula": formula,
        "bands_used": dict(bands_used),
        "components": {key: _round_value(value) for key, value in components.items()},
        "value": None,
        "reason": "missing required band",
    }


def _division_result(
    *,
    formula: str,
    bands_used: Mapping[str, int],
    components: Mapping[str, float | int | None],
    numerator: float,
    denominator: float,
    transform: Callable[[float], float] | None = None,
) -> IndexResult:
    """Create a standard result for any division-based index."""

    rounded_components = {key: _round_value(value) for key, value in components.items()}
    if abs(float(denominator)) <= EPSILON:
        return {
            "formula": formula,
            "bands_used": dict(bands_used),
            "components": rounded_components,
            "value": None,
            "reason": "division by zero",
        }

    quotient = float(numerator) / float(denominator)
    value = transform(quotient) if transform is not None else quotient
    return {
        "formula": formula,
        "bands_used": dict(bands_used),
        "components": rounded_components,
        "value": _round_value(value),
    }


def _two_band_normalized_difference(
    avg_bands: BandValues,
    *,
    formula: str,
    first_name: str,
    first_wavelength: int,
    second_name: str,
    second_wavelength: int,
    numerator_name: str,
    denominator_name: str,
) -> IndexResult:
    """Compute ``(first - second) / (first + second)`` safely."""

    first = _get_band(avg_bands, first_wavelength)
    second = _get_band(avg_bands, second_wavelength)
    components = {
        first_name: first,
        second_name: second,
        numerator_name: None if first is None or second is None else first - second,
        denominator_name: None if first is None or second is None else first + second,
        "numerator": None if first is None or second is None else first - second,
        "denominator": None if first is None or second is None else first + second,
    }
    bands_used = {first_name: first_wavelength, second_name: second_wavelength}

    if first is None or second is None:
        return _missing_result(formula, bands_used, components)
    return _division_result(
        formula=formula,
        bands_used=bands_used,
        components=components,
        numerator=first - second,
        denominator=first + second,
    )


def _ratio_index(
    avg_bands: BandValues,
    *,
    formula: str,
    numerator_name: str,
    numerator_wavelength: int,
    denominator_name: str,
    denominator_wavelength: int,
    transform: Callable[[float], float] | None = None,
) -> IndexResult:
    """Compute a simple ratio safely."""

    numerator = _get_band(avg_bands, numerator_wavelength)
    denominator = _get_band(avg_bands, denominator_wavelength)
    components = {
        numerator_name: numerator,
        denominator_name: denominator,
        "numerator": numerator,
        "denominator": denominator,
    }
    bands_used = {numerator_name: numerator_wavelength, denominator_name: denominator_wavelength}

    if numerator is None or denominator is None:
        return _missing_result(formula, bands_used, components)
    return _division_result(
        formula=formula,
        bands_used=bands_used,
        components=components,
        numerator=numerator,
        denominator=denominator,
        transform=transform,
    )


def _difference_index(
    avg_bands: BandValues,
    *,
    formula: str,
    first_name: str,
    first_wavelength: int,
    second_name: str,
    second_wavelength: int,
    component_name: str,
    divisor: float | None = None,
) -> IndexResult:
    """Compute a band difference, optionally divided by a constant."""

    first = _get_band(avg_bands, first_wavelength)
    second = _get_band(avg_bands, second_wavelength)
    raw_difference = None if first is None or second is None else first - second
    components = {
        first_name: first,
        second_name: second,
        component_name: raw_difference,
    }
    bands_used = {first_name: first_wavelength, second_name: second_wavelength}

    if first is None or second is None:
        return _missing_result(formula, bands_used, components)
    if divisor is not None and abs(float(divisor)) <= EPSILON:
        components["denominator"] = divisor
        return {
            "formula": formula,
            "bands_used": dict(bands_used),
            "components": {key: _round_value(value) for key, value in components.items()},
            "value": None,
            "reason": "division by zero",
        }

    value = raw_difference if divisor is None else raw_difference / float(divisor)
    if divisor is not None:
        components["denominator"] = divisor
    return {
        "formula": formula,
        "bands_used": dict(bands_used),
        "components": {key: _round_value(value) for key, value in components.items()},
        "value": _round_value(value),
    }


def _sum_index(
    avg_bands: BandValues,
    *,
    formula: str,
    first_name: str,
    first_wavelength: int,
    second_name: str,
    second_wavelength: int,
    component_name: str,
) -> IndexResult:
    """Compute a two-band sum safely."""

    first = _get_band(avg_bands, first_wavelength)
    second = _get_band(avg_bands, second_wavelength)
    value = None if first is None or second is None else first + second
    components = {
        first_name: first,
        second_name: second,
        component_name: value,
    }
    bands_used = {first_name: first_wavelength, second_name: second_wavelength}

    if first is None or second is None:
        return _missing_result(formula, bands_used, components)
    return {
        "formula": formula,
        "bands_used": dict(bands_used),
        "components": {key: _round_value(value) for key, value in components.items()},
        "value": _round_value(value),
    }


def _average_bands_section(avg_bands: BandValues) -> dict[str, float | None]:
    """Return average target bands using requested ``band_*`` JSON keys."""

    return {
        _prefixed_band_key(wavelength): _round_value(_get_band(avg_bands, wavelength))
        for wavelength in (532, 556, 650, 680, 725, 850, 940)
    }


def compute_indices(avg_bands: BandValues, metadata: Mapping[str, Any] | None = None) -> dict[str, Any]:
    """Compute scalar vegetation indices from average vegetation-band values."""

    del metadata
    return {
        "NDVI": _two_band_normalized_difference(
            avg_bands,
            formula="(NIR - RED) / (NIR + RED)",
            first_name="NIR",
            first_wavelength=850,
            second_name="RED",
            second_wavelength=680,
            numerator_name="NIR_minus_RED",
            denominator_name="NIR_plus_RED",
        ),
        "NDRE": _two_band_normalized_difference(
            avg_bands,
            formula="(NIR - RED_EDGE) / (NIR + RED_EDGE)",
            first_name="NIR",
            first_wavelength=850,
            second_name="RED_EDGE",
            second_wavelength=725,
            numerator_name="NIR_minus_RED_EDGE",
            denominator_name="NIR_plus_RED_EDGE",
        ),
        "SR_RED": _ratio_index(
            avg_bands,
            formula="NIR / RED",
            numerator_name="NIR",
            numerator_wavelength=850,
            denominator_name="RED",
            denominator_wavelength=680,
        ),
        "SR_RE": _ratio_index(
            avg_bands,
            formula="NIR / RED_EDGE",
            numerator_name="NIR",
            numerator_wavelength=850,
            denominator_name="RED_EDGE",
            denominator_wavelength=725,
        ),
        "GNDVI": _two_band_normalized_difference(
            avg_bands,
            formula="(NIR - GREEN) / (NIR + GREEN)",
            first_name="NIR",
            first_wavelength=850,
            second_name="GREEN",
            second_wavelength=556,
            numerator_name="NIR_minus_GREEN",
            denominator_name="NIR_plus_GREEN",
        ),
        "GRI": _ratio_index(
            avg_bands,
            formula="NIR / GREEN",
            numerator_name="NIR",
            numerator_wavelength=850,
            denominator_name="GREEN",
            denominator_wavelength=556,
        ),
        "CI_RE": _ratio_index(
            avg_bands,
            formula="(NIR / RED_EDGE) - 1",
            numerator_name="NIR",
            numerator_wavelength=850,
            denominator_name="RED_EDGE",
            denominator_wavelength=725,
            transform=lambda value: value - 1.0,
        ),
        "RE_RED_DIFF": _difference_index(
            avg_bands,
            formula="RED_EDGE - RED",
            first_name="RED_EDGE",
            first_wavelength=725,
            second_name="RED",
            second_wavelength=680,
            component_name="RED_EDGE_minus_RED",
        ),
        "RE_SLOPE": _difference_index(
            avg_bands,
            formula="(RED_EDGE - RED) / (725 - 680)",
            first_name="RED_EDGE",
            first_wavelength=725,
            second_name="RED",
            second_wavelength=680,
            component_name="RED_EDGE_minus_RED",
            divisor=45.0,
        ),
        "NDWI_850_940": _two_band_normalized_difference(
            avg_bands,
            formula="(NIR - WATER_BAND) / (NIR + WATER_BAND)",
            first_name="NIR",
            first_wavelength=850,
            second_name="WATER_BAND",
            second_wavelength=940,
            numerator_name="NIR_minus_WATER_BAND",
            denominator_name="NIR_plus_WATER_BAND",
        ),
        "WATER_RATIO": _ratio_index(
            avg_bands,
            formula="WATER_BAND / NIR",
            numerator_name="WATER_BAND",
            numerator_wavelength=940,
            denominator_name="NIR",
            denominator_wavelength=850,
        ),
        "GRND": _two_band_normalized_difference(
            avg_bands,
            formula="(GREEN - RED) / (GREEN + RED)",
            first_name="GREEN",
            first_wavelength=556,
            second_name="RED",
            second_wavelength=680,
            numerator_name="GREEN_minus_RED",
            denominator_name="GREEN_plus_RED",
        ),
        "RED_GREEN_RATIO": _ratio_index(
            avg_bands,
            formula="RED / GREEN",
            numerator_name="RED",
            numerator_wavelength=680,
            denominator_name="GREEN",
            denominator_wavelength=556,
        ),
        "NIR_RED_DIFF": _difference_index(
            avg_bands,
            formula="NIR - RED",
            first_name="NIR",
            first_wavelength=850,
            second_name="RED",
            second_wavelength=680,
            component_name="NIR_minus_RED",
        ),
        "NIR_RED_SUM": _sum_index(
            avg_bands,
            formula="NIR + RED",
            first_name="NIR",
            first_wavelength=850,
            second_name="RED",
            second_wavelength=680,
            component_name="NIR_plus_RED",
        ),
        "NIR_RE_DIFF": _difference_index(
            avg_bands,
            formula="NIR - RED_EDGE",
            first_name="NIR",
            first_wavelength=850,
            second_name="RED_EDGE",
            second_wavelength=725,
            component_name="NIR_minus_RED_EDGE",
        ),
        "NIR_RE_SUM": _sum_index(
            avg_bands,
            formula="NIR + RED_EDGE",
            first_name="NIR",
            first_wavelength=850,
            second_name="RED_EDGE",
            second_wavelength=725,
            component_name="NIR_plus_RED_EDGE",
        ),
    }


def _mapping_section(sample: SpectralSample) -> dict[str, dict[str, Any]]:
    """Return compact source-band mapping details for the indices report."""

    mapping: dict[str, dict[str, Any]] = {}
    for band_key in ("532", "556", "650", "680", "725", "850", "940"):
        band_mapping = sample.band_mappings.get(band_key)
        if band_mapping is None:
            mapping[band_key] = {
                "source_band_index": None,
                "source_wavelength": None,
                "status": "missing",
            }
            continue
        mapping[band_key] = {
            "source_band_index": (
                None if not band_mapping.source_indices else int(band_mapping.source_indices[0])
            ),
            "source_wavelength": (
                None
                if not band_mapping.source_wavelengths
                else _round_value(band_mapping.source_wavelengths[0])
            ),
            "status": band_mapping.status,
        }
    return mapping


def _role_section(sample: SpectralSample) -> dict[str, dict[str, Any]]:
    """Return semantic role resolution details for role-aware scalar indices."""

    roles = resolve_semantic_roles(sample)
    return {
        role: {
            "band_key": resolved.band_key,
            "wavelength_nm": resolved.wavelength_nm,
            "status": resolved.status,
            "reason": resolved.reason,
        }
        for role, resolved in roles.items()
    }


def _full_mapping_section(sample: SpectralSample) -> dict[str, dict[str, Any]]:
    """Return full target mapping metadata for role-aware source notes."""

    return {
        str(key): mapping.to_dict()
        for key, mapping in sorted(sample.band_mappings.items(), key=lambda item: float(item[0]))
    }


def _role_aware_metadata(sample: SpectralSample) -> dict[str, Any]:
    """Build metadata consumed by mixed-source role-aware index calculation."""

    metadata = dict(sample.metadata)
    metadata["band_roles"] = _role_section(sample)
    metadata["target_band_mapping"] = _full_mapping_section(sample)
    return metadata


def _merged_indices(
    fixed_indices: Mapping[str, Any],
    role_aware_indices: Mapping[str, Any],
) -> dict[str, Any]:
    """Merge role-aware mixed-input indices into the legacy index table.

    Fixed 7-band formulas remain the default for complete hyperspectral input.
    Role-aware values replace legacy missing values when the semantic resolver
    can make an honest fallback, such as NDVI-like from RGB red plus NIR.
    """

    merged: dict[str, Any] = {str(key): value for key, value in fixed_indices.items()}
    role_indices = role_aware_indices.get("indices", {})
    if not isinstance(role_indices, Mapping):
        return merged

    replacements = {
        "NDVI": "NDVI",
        "NDRE": "NDRE",
        "GNDVI": "GNDVI",
        "WATER_PROXY": "NDWI_850_940",
    }
    for role_key, legacy_key in replacements.items():
        role_result = role_indices.get(role_key)
        if not isinstance(role_result, Mapping):
            continue
        legacy_result = merged.get(legacy_key, {})
        legacy_missing = (
            not isinstance(legacy_result, Mapping)
            or legacy_result.get("value") is None
            or role_result.get("available") is True
        )
        if legacy_missing:
            merged[legacy_key] = dict(role_result)

    return merged


def build_indices_report(
    sample: SpectralSample,
    avg_bands: BandValues,
    spectrum_metadata: Mapping[str, Any],
) -> dict[str, Any]:
    """Build the full JSON-ready indices report."""

    source_metadata = sample.metadata
    source_data_kind = source_metadata.get(
        "source_data_kind",
        "mock_synthetic_data" if source_metadata.get("mock_flag") else "real_sample_data",
    )
    dimensions = source_metadata.get("dimensions", {})

    fixed_indices = compute_indices(avg_bands, source_metadata)
    role_aware = compute_role_aware_indices(avg_bands, _role_aware_metadata(sample))
    merged_indices = _merged_indices(fixed_indices, role_aware)
    interpretation = interpret_indices(merged_indices, avg_bands)

    return {
        "source": {
            "sample_id": source_metadata.get("archive_member_sample")
            or source_metadata.get("input_path")
            or "synthetic_mock_sample",
            "source_type": source_data_kind,
            "cube_shape": dimensions.get("shape"),
            "vegetation_pixels": int(spectrum_metadata.get("vegetation_pixel_count", 0)),
        },
        "band_mapping": _mapping_section(sample),
        "average_bands": _average_bands_section(avg_bands),
        "indices": merged_indices,
        "role_aware_indices": role_aware,
        "index_availability": role_aware.get("availability_summary", {}),
        "interpretation": interpretation,
    }


def save_indices_report(
    sample: SpectralSample,
    output_dir: str | Path,
    avg_bands: BandValues,
    spectrum_metadata: Mapping[str, Any],
) -> Path:
    """Save scalar spectral indices beside the other pipeline reports."""

    output_root = ensure_output_dir(output_dir)
    report_path = output_root / "indices_report.json"
    report = build_indices_report(sample, avg_bands, spectrum_metadata)
    report_path.write_text(json.dumps(report, indent=2, sort_keys=True), encoding="utf-8")
    return report_path


def save_indices_csv(
    sample: SpectralSample,
    output_dir: str | Path,
    avg_bands: BandValues,
    spectrum_metadata: Mapping[str, Any],
) -> Path:
    """Save scalar spectral indices as a single flat spreadsheet table."""

    output_root = ensure_output_dir(output_dir)
    csv_path = output_root / "indices_report.csv"
    report = build_indices_report(sample, avg_bands, spectrum_metadata)

    with csv_path.open("w", newline="", encoding="utf-8") as csv_file:
        writer = csv.writer(csv_file)
        writer.writerow(
            [
                "index",
                "value",
                "reason",
                "formula",
                "nir_band_nm",
                "red_band_nm",
                "red_edge_band_nm",
                "green_band_nm",
                "water_band_nm",
                "nir_value",
                "red_value",
                "red_edge_value",
                "green_value",
                "water_band_value",
                "numerator",
                "denominator",
                "difference_value",
                "sum_value",
            ]
        )
        for index_name, result in report["indices"].items():
            components = result.get("components", {})
            bands_used = result.get("bands_used", {})
            writer.writerow(
                [
                    index_name,
                    "" if result.get("value") is None else result.get("value"),
                    result.get("reason", ""),
                    result.get("formula", ""),
                    bands_used.get("NIR", ""),
                    bands_used.get("RED", ""),
                    bands_used.get("RED_EDGE", ""),
                    bands_used.get("GREEN", ""),
                    bands_used.get("WATER_BAND", ""),
                    components.get("NIR", ""),
                    components.get("RED", ""),
                    components.get("RED_EDGE", ""),
                    components.get("GREEN", ""),
                    components.get("WATER_BAND", ""),
                    "" if components.get("numerator") is None else components.get("numerator"),
                    "" if components.get("denominator") is None else components.get("denominator"),
                    _first_present_component(
                        components,
                        (
                            "NIR_minus_RED",
                            "NIR_minus_RED_EDGE",
                            "NIR_minus_GREEN",
                            "NIR_minus_WATER_BAND",
                            "GREEN_minus_RED",
                            "RED_EDGE_minus_RED",
                        ),
                    ),
                    _first_present_component(
                        components,
                        (
                            "NIR_plus_RED",
                            "NIR_plus_RED_EDGE",
                            "NIR_plus_GREEN",
                            "NIR_plus_WATER_BAND",
                            "GREEN_plus_RED",
                        ),
                    ),
                ]
            )

    return csv_path


def _first_present_component(components: Mapping[str, Any], keys: tuple[str, ...]) -> Any:
    """Return the first available component value for a CSV convenience column."""

    for key in keys:
        if key in components and components[key] is not None:
            return components[key]
    return ""


def summarize_main_indices(indices_report: Mapping[str, Any]) -> dict[str, float | None]:
    """Return the short console summary requested by the MVP workflow."""

    indices = indices_report.get("indices", {})
    return {
        name: indices.get(name, {}).get("value")
        for name in ("NDVI", "NDRE", "GNDVI", "CI_RE", "NDWI_850_940")
    }


__all__ = [
    "build_indices_report",
    "compute_indices",
    "save_indices_csv",
    "save_indices_report",
    "summarize_main_indices",
]
