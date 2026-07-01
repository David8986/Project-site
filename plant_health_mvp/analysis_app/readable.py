"""Human-readable text helpers for analysis reports.

These helpers turn the structured JSON report into deterministic prose for the
analysis app. They do not re-run the detector or reinterpret the science.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from typing import Any

from ..core.interpretation import interpret_indices


def _as_mapping(value: Any) -> Mapping[str, Any]:
    """Return a mapping view or an empty mapping."""

    if isinstance(value, Mapping):
        return value
    return {}


def _coerce_int(value: Any) -> int | None:
    """Convert a scalar value to ``int`` when possible."""

    if value is None or value == "":
        return None
    try:
        return int(float(value))
    except (TypeError, ValueError):
        return None


def _coerce_float(value: Any) -> float | None:
    """Convert a scalar value to ``float`` when possible."""

    if value is None or value == "":
        return None
    try:
        number = float(value)
    except (TypeError, ValueError):
        return None
    if number != number:
        return None
    return number


def _format_float(value: Any, digits: int = 2) -> str:
    """Format a scalar for display."""

    number = _coerce_float(value)
    if number is None:
        return "indisponibil"
    return f"{number:.{digits}f}"


def _format_list(values: Sequence[Any] | None, *, limit: int = 6) -> str:
    """Format a sequence for readable display."""

    if values is None:
        return "indisponibil"
    if isinstance(values, str):
        return values
    try:
        items = [str(item) for item in list(values)]
    except TypeError:
        return str(values)
    if not items:
        return "indisponibil"
    if len(items) <= limit:
        return ", ".join(items)
    head = ", ".join(items[: max(1, limit - 2)])
    tail = ", ".join(items[-2:])
    return f"{head}, ... {tail}"


def _format_imported_files(value: Any) -> str:
    """Format mixed-input file records in a compact readable way."""

    if not value:
        return ""
    if isinstance(value, Mapping):
        return "; ".join(f"{key}: {item}" for key, item in value.items())
    if isinstance(value, Sequence) and not isinstance(value, str):
        pieces: list[str] = []
        for item in value:
            if isinstance(item, Mapping):
                kind = item.get("type") or item.get("assignment") or "file"
                path = item.get("path") or item.get("input_path") or ""
                bands = item.get("bands")
                band_text = f" ({_format_list(bands, limit=4)})" if bands else ""
                pieces.append(f"{kind}: {path}{band_text}")
            else:
                pieces.append(str(item))
        return "; ".join(piece for piece in pieces if piece)
    return str(value)


def _spot_bounding_box(spot: Mapping[str, Any]) -> tuple[int | None, int | None, int | None, int | None]:
    """Extract a bounding box from either report or CSV-style spot data."""

    bbox = spot.get("bbox")
    if isinstance(bbox, Sequence) and not isinstance(bbox, str) and len(bbox) >= 4:
        return tuple(_coerce_int(value) for value in bbox[:4])  # type: ignore[return-value]
    return (
        _coerce_int(spot.get("bbox_x_min")),
        _coerce_int(spot.get("bbox_y_min")),
        _coerce_int(spot.get("bbox_x_max")),
        _coerce_int(spot.get("bbox_y_max")),
    )


def _spot_centroid(spot: Mapping[str, Any]) -> tuple[float | None, float | None]:
    """Extract a centroid from either report or CSV-style spot data."""

    centroid = spot.get("centroid")
    if isinstance(centroid, Sequence) and not isinstance(centroid, str) and len(centroid) >= 2:
        return _coerce_float(centroid[0]), _coerce_float(centroid[1])
    return _coerce_float(spot.get("centroid_x")), _coerce_float(spot.get("centroid_y"))


def _spot_summary(spot: Mapping[str, Any]) -> dict[str, Any]:
    """Normalize spot information for readable output."""

    summary = {
        "label": _coerce_int(spot.get("label")),
        "area_px": _coerce_int(spot.get("area_px")),
        "severity_rank": _coerce_int(spot.get("severity_rank")),
        "severity_score": _coerce_float(spot.get("severity_score")),
        "mean_suspiciousness_score": _coerce_float(spot.get("mean_suspiciousness_score")),
        "max_suspiciousness_score": _coerce_float(spot.get("max_suspiciousness_score")),
        "centroid": _spot_centroid(spot),
        "bbox": _spot_bounding_box(spot),
        "ndvi": _coerce_float(spot.get("ndvi")),
        "ndre": _coerce_float(spot.get("ndre")),
        "gndvi": _coerce_float(spot.get("gndvi")),
        "ndwi_850_940": _coerce_float(spot.get("ndwi_850_940")),
        "delta_leaf_band_680": _coerce_float(spot.get("delta_leaf_band_680")),
        "delta_leaf_band_850": _coerce_float(spot.get("delta_leaf_band_850")),
        "delta_nearby_band_680": _coerce_float(spot.get("delta_nearby_band_680")),
        "delta_nearby_band_850": _coerce_float(spot.get("delta_nearby_band_850")),
    }
    return summary


def _spot_score_profile(report: Mapping[str, Any]) -> dict[str, float | int]:
    """Return count and suspiciousness score summary statistics."""

    suspicious = _as_mapping(report.get("suspicious_regions"))
    spots = suspicious.get("spots", [])
    if not isinstance(spots, Sequence) or isinstance(spots, str):
        spots = []

    spot_count = _coerce_int(suspicious.get("spot_count"))
    if spot_count is None:
        spot_count = len(spots)

    mean_scores: list[float] = []
    max_scores: list[float] = []
    severity_scores: list[float] = []
    for spot in spots:
        if not isinstance(spot, Mapping):
            continue
        mean_score = _coerce_float(spot.get("mean_suspiciousness_score"))
        max_score = _coerce_float(spot.get("max_suspiciousness_score"))
        severity_score = _coerce_float(spot.get("severity_score"))
        if mean_score is not None:
            mean_scores.append(mean_score)
        if max_score is not None:
            max_scores.append(max_score)
        if severity_score is not None:
            severity_scores.append(severity_score)

    return {
        "spot_count": int(spot_count),
        "mean_suspiciousness_score": (sum(mean_scores) / len(mean_scores)) if mean_scores else 0.0,
        "max_suspiciousness_score": max(max_scores) if max_scores else 0.0,
        "severity_score": max(severity_scores) if severity_scores else 0.0,
    }


def classify_anomaly_level(report: Mapping[str, Any]) -> str:
    """Classify the report with a deterministic low/moderate/high label."""

    profile = _spot_score_profile(report)
    count = int(profile["spot_count"])
    mean_score = float(profile["mean_suspiciousness_score"])
    max_score = float(profile["max_suspiciousness_score"])
    severity_score = float(profile["severity_score"])

    if count <= 0:
        return "anomalie redusa"
    if count >= 4 or (count >= 3 and (mean_score >= 0.7 or max_score >= 0.8 or severity_score >= 2.5)):
        return "anomalie ridicata"
    if count >= 2 or mean_score >= 0.45 or max_score >= 0.55 or severity_score >= 1.25:
        return "anomalie moderata"
    return "anomalie redusa"


def _line(label: str, value: Any) -> str:
    """Format one label/value pair."""

    if value in (None, "", [], {}):
        return ""
    return f"{label}: {value}"


def _join_lines(lines: Sequence[str]) -> str:
    """Join non-empty lines with blank-line spacing."""

    return "\n".join(line for line in lines if line is not None).strip()


def _warning_list(report: Mapping[str, Any]) -> list[str]:
    """Return a normalized warning list from the report."""

    warnings = report.get("warnings", [])
    if isinstance(warnings, str):
        return [warnings]
    if not isinstance(warnings, Sequence):
        return []
    return [str(warning) for warning in warnings if warning is not None and str(warning).strip()]


def _format_selected_spot(spot: Mapping[str, Any] | None) -> list[str]:
    """Build a compact selected-spot section."""

    if spot is None:
        return []
    summary = _spot_summary(_as_mapping(spot))
    bbox = summary["bbox"]
    centroid = summary["centroid"]
    area = summary["area_px"] if summary["area_px"] is not None else "indisponibil"
    severity_rank = summary["severity_rank"] if summary["severity_rank"] is not None else "indisponibil"
    label = summary["label"] if summary["label"] is not None else "indisponibil"
    bbox_text = f"({bbox[0] if bbox[0] is not None else 'indisponibil'}, {bbox[1] if bbox[1] is not None else 'indisponibil'}) la ({bbox[2] if bbox[2] is not None else 'indisponibil'}, {bbox[3] if bbox[3] is not None else 'indisponibil'})"
    centroid_text = f"({_format_float(centroid[0])}, {_format_float(centroid[1])})"
    lines = [
        "Regiune selectata",
        _line("Eticheta", label),
        _line("Arie", f"{area} px"),
        _line("Rang severitate", severity_rank),
        _line("Scor severitate", _format_float(summary["severity_score"])),
        _line("Suspiciune medie", _format_float(summary["mean_suspiciousness_score"])),
        _line("Suspiciune maxima", _format_float(summary["max_suspiciousness_score"])),
        _line("Centroid", centroid_text),
        _line("BBox", bbox_text),
        _line("NDVI", _format_float(summary["ndvi"])),
        _line("NDRE", _format_float(summary["ndre"])),
        _line("GNDVI", _format_float(summary["gndvi"])),
        _line("NDWI 850/940", _format_float(summary["ndwi_850_940"])),
        _line("Delta banda frunza 680", _format_float(summary["delta_leaf_band_680"])),
        _line("Delta banda frunza 850", _format_float(summary["delta_leaf_band_850"])),
    ]
    return lines


def _interpretation_from_report(report: Mapping[str, Any]) -> Mapping[str, Any]:
    """Return existing interpretation payload or build one from whole-leaf indices."""

    direct = _as_mapping(report.get("interpretation"))
    if direct:
        return direct
    whole_leaf = _as_mapping(report.get("whole_leaf"))
    nested = _as_mapping(whole_leaf.get("interpretation"))
    if nested:
        return nested
    return interpret_indices(_as_mapping(whole_leaf.get("indices")), _as_mapping(whole_leaf.get("average_bands")))


def _format_interpretation_section(report: Mapping[str, Any]) -> list[str]:
    """Build the plain-language interpretation section."""

    interpretation = _interpretation_from_report(report)
    if not interpretation:
        return [
            "Interpretare",
            _line("Stare generala", "indisponibil"),
            _line("Concluzie", "Interpretarea nu este disponibila pentru acest esantion."),
        ]

    lines = [
        str(interpretation.get("summary_title") or "Interpretare"),
        _line("Stare generala", interpretation.get("overall_status") or "indisponibil"),
    ]
    rows = interpretation.get("lines", [])
    if isinstance(rows, Sequence) and not isinstance(rows, str):
        for row in rows:
            if not isinstance(row, Mapping):
                continue
            label = str(row.get("label") or "Indice")
            value = row.get("value")
            prefix = f"{label}: "
            if value is not None:
                prefix = f"{label} {_format_float(value)}: "
            text = row.get("interpretation") or "indisponibil pentru acest esantion."
            if row.get("reason"):
                text = f"{text} Motiv: {row.get('reason')}."
            lines.append(f"{prefix}{text}")
    lines.append(_line("Concluzie", interpretation.get("conclusion") or "indisponibil"))
    if interpretation.get("caution"):
        lines.append(_line("Atentie", interpretation.get("caution")))
    return lines


def build_interpretation_text(report: Mapping[str, Any]) -> str:
    """Build the standalone Interpretation tab text."""

    return _join_lines(_format_interpretation_section(report))


def build_summary_text(report: Mapping[str, Any], selected_spot: Mapping[str, Any] | None = None) -> str:
    """Build a short human-readable summary for the analysis app."""

    source = _as_mapping(report.get("source"))
    suspicious = _as_mapping(report.get("suspicious_regions"))
    whole_leaf = _as_mapping(report.get("whole_leaf"))
    indices = _as_mapping(whole_leaf.get("indices"))
    profile = _spot_score_profile(report)
    lines = [
        "Rezumat determinist",
        _line("Eticheta anomaliei", classify_anomaly_level(report)),
        "Nota: text bazat pe reguli din raportul JSON; fara diagnostic AI.",
        _line("Esantion", source.get("sample_id")),
        _line("Adaptor", source.get("adapter_used")),
        _line("Tip date analiza", source.get("analysis_data_kind")),
        _line("Pixeli de vegetatie", source.get("vegetation_pixels")),
        _line("Regiuni suspecte", profile["spot_count"]),
        _line("Scor mediu spot", _format_float(profile["mean_suspiciousness_score"])),
        _line("Scor maxim spot", _format_float(profile["max_suspiciousness_score"])),
        _line("Avertismente", len(_warning_list(report))),
    ]
    if indices:
        lines.append(
            _line(
                "Indici pe intreaga frunza",
                ", ".join(
                    f"{name} {_format_float(value.get('value'))}"
                    for name, value in sorted(indices.items())
                    if isinstance(value, Mapping)
                ),
            )
        )
    lines.extend(["", *_format_interpretation_section(report)])
    if selected_spot is not None:
        lines.extend(["", *_format_selected_spot(selected_spot)])
    if suspicious.get("reason"):
        lines.append(_line("Nota detectie spoturi", suspicious.get("reason")))
    return _join_lines(lines)


def _format_wavelength_section(report: Mapping[str, Any]) -> list[str]:
    """Build a readable wavelength summary."""

    wavelengths = _as_mapping(report.get("wavelengths"))
    available = wavelengths.get("available_wavelengths_nm", [])
    if not isinstance(available, Sequence) or isinstance(available, str):
        available = []
    lines = [
        _line("Numar", wavelengths.get("count")),
        _line("Interval", f"{_format_float(wavelengths.get('min_nm'))} nm la {_format_float(wavelengths.get('max_nm'))} nm"),
        _line("Profil tinta", wavelengths.get("target_profile")),
        _line("Tinte", _format_list(wavelengths.get("target_wavelengths_nm"))),
    ]
    if available:
        lines.append(_line("Lungimi de unda disponibile", _format_list(available, limit=8)))
    return ["Lungimi de unda", *lines]


def _format_source_section(report: Mapping[str, Any]) -> list[str]:
    """Build a readable source summary."""

    source = _as_mapping(report.get("source"))
    lines = [
        _line("Esantion", source.get("sample_id")),
        _line("Adaptor", source.get("adapter_used")),
        _line("Tip sursa", source.get("source_type")),
        _line("Tip date sursa", source.get("source_data_kind")),
        _line("Tip date analiza", source.get("analysis_data_kind")),
        _line("Calibrare aplicata", source.get("calibration_applied")),
        _line("Date reale esantion", source.get("used_real_sample_data")),
        _line("Date sintetice mock", source.get("used_mock_synthetic_data")),
        _line("Pixeli de vegetatie", source.get("vegetation_pixels")),
        _line("Fisiere importate", _format_imported_files(source.get("imported_files"))),
        _line("Roluri atribuite", _format_list(list(_as_mapping(source.get("assigned_roles")).values()), limit=10)),
        _line("Aliniere", _format_list(_as_mapping(source.get("alignment")).values(), limit=6)),
    ]
    return ["Sursa", *lines]


def _format_whole_leaf_section(report: Mapping[str, Any]) -> list[str]:
    """Build a readable whole-leaf summary."""

    whole_leaf = _as_mapping(report.get("whole_leaf"))
    average_bands = _as_mapping(whole_leaf.get("average_bands"))
    indices = _as_mapping(whole_leaf.get("indices"))
    lines = ["Frunza intreaga"]
    if average_bands:
        formatted_bands = ", ".join(
            f"{band} {_format_float(value)}"
            for band, value in sorted(average_bands.items(), key=lambda item: str(item[0]))
        )
        lines.append(_line("Benzi medii", formatted_bands))
    if indices:
        for name, result in sorted(indices.items(), key=lambda item: str(item[0])):
            if isinstance(result, Mapping):
                label = result.get("label") or name
                value_text = _format_float(result.get("value"))
                if result.get("reason"):
                    value_text = f"{value_text} ({result.get('reason')})"
                lines.append(_line(str(label), value_text))
    availability = _as_mapping(whole_leaf.get("index_availability"))
    if availability:
        lines.append(_line("Indici disponibili", _format_list(availability.get("available_indices"))))
        lines.append(_line("Indici indisponibili", _format_list(availability.get("unavailable_indices"))))
    return lines


def _format_spots_section(report: Mapping[str, Any]) -> list[str]:
    """Build a readable suspicious-region summary."""

    suspicious = _as_mapping(report.get("suspicious_regions"))
    spots = suspicious.get("spots", [])
    if not isinstance(spots, Sequence) or isinstance(spots, str):
        spots = []
    lines = [
        "Regiuni suspecte",
        _line("Eticheta determinista", classify_anomaly_level(report)),
        _line("Numar", suspicious.get("spot_count")),
        _line("Harti disponibile", _format_list(suspicious.get("available_maps"))),
        _line("Harti de anomalie disponibile", _format_list(suspicious.get("available_anomaly_maps"))),
    ]
    parameters = _as_mapping(suspicious.get("parameters"))
    if parameters:
        min_area = _coerce_int(parameters.get("min_area_px"))
        morphology_iterations = _coerce_int(parameters.get("morphology_iterations"))
        texture_window = _coerce_int(parameters.get("texture_window"))
        lines.append(
            _line(
                "Parametri",
                ", ".join(
                    [
                        f"prag {_format_float(parameters.get('score_threshold'))}",
                        f"arie minima {min_area if min_area is not None else 'indisponibil'} px",
                        f"morfologie {morphology_iterations if morphology_iterations is not None else 'indisponibil'}",
                        f"fereastra {texture_window if texture_window is not None else 'indisponibil'}",
                    ]
                ),
            )
        )
    for spot in spots:
        if not isinstance(spot, Mapping):
            continue
        summary = _spot_summary(spot)
        bbox = summary["bbox"]
        centroid = summary["centroid"]
        spot_lines = [
            f"Regiunea {summary['label'] if summary['label'] is not None else '?'}",
            _line("Arie", f'{summary["area_px"]} px'),
            _line("Rang severitate", summary["severity_rank"]),
            _line("Scor severitate", _format_float(summary["severity_score"])),
            _line("Suspiciune medie", _format_float(summary["mean_suspiciousness_score"])),
            _line("Suspiciune maxima", _format_float(summary["max_suspiciousness_score"])),
            _line(
                "Centroid",
                f"({_format_float(centroid[0])}, {_format_float(centroid[1])})",
            ),
            _line(
                "BBox",
                f"({bbox[0]}, {bbox[1]}) la ({bbox[2]}, {bbox[3]})",
            ),
        ]
        lines.extend(spot_lines)
    return lines


def build_detailed_report_text(report: Mapping[str, Any], selected_spot: Mapping[str, Any] | None = None) -> str:
    """Build a detailed human-readable report for the analysis app."""

    lines = [
        "Raport de analiza a sanatatii plantelor",
        _line("Schema", report.get("report_schema")),
        _line("Eticheta determinista a anomaliei", classify_anomaly_level(report)),
        "Nota: aceasta este o redare bazata pe reguli a raportului JSON, nu un diagnostic.",
        "",
        *_format_source_section(report),
        "",
        *_format_wavelength_section(report),
        "",
        *_format_whole_leaf_section(report),
        "",
        *_format_interpretation_section(report),
        "",
        *_format_spots_section(report),
    ]
    if selected_spot is not None:
        lines.extend(["", *_format_selected_spot(selected_spot)])
    warnings = _warning_list(report)
    if warnings:
        lines.extend(
            [
                "",
                "Avertismente",
                *[f"- {warning}" for warning in warnings],
            ]
        )
    return _join_lines(lines)


__all__ = [
    "build_detailed_report_text",
    "build_interpretation_text",
    "build_summary_text",
    "classify_anomaly_level",
]
