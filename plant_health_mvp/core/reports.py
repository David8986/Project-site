"""Structured report builders for hyperspectral plant analysis."""

from __future__ import annotations

import json
from collections.abc import Mapping
from pathlib import Path
from typing import Any

import numpy as np

from .interpretation import interpret_indices
from .models.sample import SpectralSample
from .semantic_roles import resolve_semantic_roles


def _json_safe(value: Any) -> Any:
    """Convert NumPy and pathlib values to JSON-friendly equivalents."""

    if isinstance(value, np.ndarray):
        return _json_safe(value.tolist())
    if isinstance(value, np.generic):
        return value.item()
    if isinstance(value, Path):
        return str(value)
    if isinstance(value, Mapping):
        return {str(key): _json_safe(item) for key, item in value.items()}
    if isinstance(value, (list, tuple)):
        return [_json_safe(item) for item in value]
    if isinstance(value, float) and not np.isfinite(value):
        return None
    return value


def _available_wavelengths(sample: SpectralSample) -> list[float]:
    """Return finite source wavelengths as plain floats."""

    values = np.asarray(sample.available_wavelengths, dtype=float).ravel()
    return [float(value) for value in values if np.isfinite(value)]


def _mapping_section(sample: SpectralSample) -> dict[str, Any]:
    """Return JSON-safe target-band mapping details."""

    return {
        str(key): mapping.to_dict()
        for key, mapping in sorted(sample.band_mappings.items(), key=lambda item: float(item[0]))
    }


def _missing_bands(sample: SpectralSample) -> list[str]:
    """Return target bands that were unavailable after mapping/extraction."""

    return [
        str(key)
        for key, value in sample.target_bands.items()
        if value is None or sample.band_status.get(str(key)) == "missing"
    ]


def _role_section(sample: SpectralSample) -> dict[str, Any]:
    """Resolve semantic band roles for reporting."""

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


def _source_section(sample: SpectralSample, spectrum_metadata: Mapping[str, Any]) -> dict[str, Any]:
    """Build source and calibration metadata."""

    metadata = sample.metadata
    dimensions = metadata.get("dimensions", {})
    calibration = metadata.get("calibration", {})
    source = {
        "adapter_used": metadata.get("adapter_used", "legacy_loader"),
        "sample_id": metadata.get("sample_id")
        or metadata.get("adapter_sample_id")
        or metadata.get("archive_member_sample")
        or metadata.get("input_path")
        or "synthetic_mock_sample",
        "source_type": sample.source_type,
        "source_data_kind": metadata.get(
            "source_data_kind",
            "mock_synthetic_data" if metadata.get("mock_flag") else "real_dataset_data",
        ),
        "analysis_data_kind": metadata.get("analysis_data_kind", calibration.get("analysis_data_kind", "raw_intensity")),
        "used_real_sample_data": not bool(metadata.get("mock_flag")),
        "used_mock_synthetic_data": bool(metadata.get("mock_flag")),
        "is_reflectance": bool(metadata.get("is_reflectance")),
        "calibration_applied": bool(metadata.get("calibration_applied")),
        "calibration": calibration,
        "cube_shape": dimensions.get("shape"),
        "vegetation_pixels": int(spectrum_metadata.get("vegetation_pixel_count", 0)),
    }
    imported_files = metadata.get("imported_files")
    if imported_files:
        source["imported_files"] = imported_files
    else:
        discovered_files: dict[str, Any] = {}
        is_mixed = str(metadata.get("source_data_kind", "")).startswith("mixed")
        if metadata.get("input_path") and not is_mixed:
            discovered_files["input"] = metadata.get("input_path")
        if metadata.get("rgb_path"):
            discovered_files["rgb"] = metadata.get("rgb_path")
        elif metadata.get("input_path") and is_mixed:
            discovered_files["rgb"] = metadata.get("input_path")
        if metadata.get("nir_path"):
            discovered_files["nir"] = metadata.get("nir_path")
        if metadata.get("wavelength_csv_path"):
            discovered_files["wavelengths"] = metadata.get("wavelength_csv_path")
        if discovered_files:
            source["imported_files"] = discovered_files
    if metadata.get("mixed_bundle_spec_path"):
        source["mixed_bundle_spec_path"] = metadata.get("mixed_bundle_spec_path")
    if metadata.get("roles"):
        source["assigned_roles"] = metadata.get("roles")
    if metadata.get("channel_wavelength_labels_nm"):
        source["channel_wavelength_labels_nm"] = metadata.get("channel_wavelength_labels_nm")
    if metadata.get("alignment"):
        source["alignment"] = metadata.get("alignment")
    elif metadata.get("alignment_status"):
        source["alignment"] = {"status": metadata.get("alignment_status")}
    return source


def _wavelength_section(sample: SpectralSample) -> dict[str, Any]:
    """Build source wavelength range details."""

    wavelengths = _available_wavelengths(sample)
    return {
        "count": len(wavelengths),
        "min_nm": min(wavelengths) if wavelengths else None,
        "max_nm": max(wavelengths) if wavelengths else None,
        "available_wavelengths_nm": wavelengths,
        "target_profile": sample.metadata.get("band_profile"),
        "target_wavelengths_nm": sample.metadata.get("target_wavelengths_nm", []),
    }


def _warnings(sample: SpectralSample, spectrum_metadata: Mapping[str, Any], spot_report: Mapping[str, Any]) -> list[str]:
    """Collect report-level warnings and caveats."""

    warnings: list[str] = []
    metadata = sample.metadata
    calibration = metadata.get("calibration", {})

    if metadata.get("mock_flag"):
        warnings.append("mock synthetic data; do not interpret biological metrics as real measurements")
    if metadata.get("rgb_only"):
        warnings.append(
            "RGB-only image input; channels are approximate display labels, not calibrated spectral bands"
        )
        warnings.append("NIR, red-edge, and 940 nm water-band measurements are unavailable for RGB images")
    if metadata.get("source_data_kind") == "mixed_image_data":
        warnings.append(
            "mixed image bundle input; ordinary RGB channels are approximate display labels unless documented otherwise"
        )
        alignment = metadata.get("alignment", {})
        if metadata.get("alignment_status") in {"resized", "strict_match", "not_required", "aligned", "fallback_resize_only"}:
            warnings.append(f"mixed image alignment status: {metadata.get('alignment_status')}")
        if isinstance(alignment, Mapping) and alignment.get("warning"):
            warnings.append(str(alignment.get("warning")))
    if not metadata.get("calibration_applied"):
        warnings.append("analysis used raw intensity or synthetic values because calibration was not applied")
    if calibration.get("invalid_denominator_count", 0):
        warnings.append("calibration had invalid dark/white denominator pixels; affected reflectance values are NaN")
    if spectrum_metadata.get("vegetation_pixel_count", 0) == 0:
        warnings.append("vegetation mask is empty or was not computed")

    for band in _missing_bands(sample):
        warnings.append(f"target band {band} is missing")
    for key, mapping in sample.band_mappings.items():
        if mapping.status in {"nearest", "interpolated"}:
            warnings.append(f"target band {key} uses {mapping.status} mapping, not an exact source band")

    roles = _role_section(sample)
    for role, resolved in roles.items():
        if resolved.get("status") == "missing":
            warnings.append(f"semantic role {role} is missing")

    if int(spot_report.get("spot_count", 0)) == 0:
        warnings.append("no suspicious regions were detected with the current deterministic thresholds")

    return warnings


def build_analysis_report(
    sample: SpectralSample,
    average_spectrum: Mapping[str, float | None],
    spectrum_metadata: Mapping[str, Any],
    *,
    indices_report: Mapping[str, Any] | None = None,
    spot_report: Mapping[str, Any] | None = None,
    extra_metadata: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    """Build the main structured JSON analysis report."""

    spot_section = dict(spot_report or sample.metadata.get("spot_detection", {}))
    indices_payload = dict(indices_report or {})
    whole_leaf_indices = dict(indices_payload.get("indices", {}))
    interpretation = dict(indices_payload.get("interpretation") or interpret_indices(whole_leaf_indices, average_spectrum))
    missing_bands = _missing_bands(sample)
    mapping = _mapping_section(sample)
    available_wavelengths = _available_wavelengths(sample)

    structured = {
        "report_schema": "plant_health_analysis_v2",
        "source": _source_section(sample, spectrum_metadata),
        "wavelengths": _wavelength_section(sample),
        "target_band_mapping": mapping,
        "band_roles": _role_section(sample),
        "vegetation": {
            "mask": sample.metadata.get("vegetation_mask", {}),
            "spectrum_metadata": dict(spectrum_metadata),
        },
        "whole_leaf": {
            "average_bands": {
                str(key): (None if value is None else float(value))
                for key, value in average_spectrum.items()
            },
            "indices": whole_leaf_indices,
            "role_aware_indices": indices_payload.get("role_aware_indices", {}),
            "index_availability": indices_payload.get("index_availability", {}),
            "interpretation": interpretation,
        },
        "interpretation": interpretation,
        "suspicious_regions": spot_section,
        "warnings": _warnings(sample, spectrum_metadata, spot_section),
        "metadata": {
            **dict(sample.metadata),
            **dict(extra_metadata or {}),
        },
    }

    # Compatibility keys retained for older scripts and earlier notebooks.
    structured.update(
        {
            "source_type": sample.source_type,
            "source_data_kind": structured["source"]["source_data_kind"],
            "used_real_sample_data": structured["source"]["used_real_sample_data"],
            "used_mock_synthetic_data": structured["source"]["used_mock_synthetic_data"],
            "available_wavelengths": available_wavelengths,
            "mapping": mapping,
            "missing_bands": missing_bands,
            "average_spectrum": structured["whole_leaf"]["average_bands"],
            "vegetation_pixel_count": structured["source"]["vegetation_pixels"],
        }
    )
    return _json_safe(structured)


def save_analysis_report(report: Mapping[str, Any], path: str | Path) -> Path:
    """Save a structured analysis report to disk."""

    report_path = Path(path)
    report_path.parent.mkdir(parents=True, exist_ok=True)
    report_path.write_text(json.dumps(_json_safe(report), indent=2, sort_keys=True), encoding="utf-8")
    return report_path


__all__ = ["build_analysis_report", "save_analysis_report"]
