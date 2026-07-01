"""Real validation profile from the leaf camera/spectrometer measurements.

The picture-analysis app can analyze new photos by itself, but the new
spectrometer work gives the app a better interpretation context. This module
keeps those validation numbers in one place and exposes them to JSON reports
and the GUI.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Mapping


PROFILE_ID = "spectraleaf_real_leaf_validation_2026_05"
PROFILE_TITLE = "Profil de validare camera + spectrometru"
DATA_DIR = Path(__file__).resolve().parents[1] / "data" / "real_validation"


def _load_json(filename: str) -> dict[str, Any]:
    path = DATA_DIR / filename
    with path.open("r", encoding="utf-8") as handle:
        return json.load(handle)


def _round(value: Any, digits: int = 3) -> float | None:
    try:
        return round(float(value), digits)
    except (TypeError, ValueError):
        return None


def load_new_data_profile() -> dict[str, Any]:
    """Load the app's bundled real-data validation profile."""

    inside_outside = _load_json("inside_outside_summary.json")
    camera_validation = _load_json("camera_validation_summary.json")
    by_condition = inside_outside.get("by_condition", {})
    env = inside_outside.get("environment_spectrum_summary", {})

    return {
        "profile_id": PROFILE_ID,
        "title": PROFILE_TITLE,
        "source": "real leaf measurements from the current data analysis folder",
        "inside_outside": {
            "matched_pairs": inside_outside.get("matched_inside_outside_spectrum_pairs"),
            "median_shape_similarity_r": inside_outside.get("overall_median_shape_similarity_r"),
            "mean_shape_similarity_r": inside_outside.get("overall_mean_shape_similarity_r"),
            "median_outside_to_inside_area_ratio": inside_outside.get(
                "overall_median_outside_to_inside_area_ratio"
            ),
            "healthy_median_shape_similarity_r": by_condition.get("healthy", {}).get(
                "median_shape_similarity_r"
            ),
            "unhealthy_median_shape_similarity_r": by_condition.get("unhealthy", {}).get(
                "median_shape_similarity_r"
            ),
            "outside_sample_spectra": env.get("afara", {}).get("sample_spectra"),
            "inside_sample_spectra": env.get("in cutie", {}).get("sample_spectra"),
            "outside_median_noise_index": env.get("afara", {}).get("median_noise_index"),
            "inside_median_noise_index": env.get("in cutie", {}).get("median_noise_index"),
            "note": inside_outside.get("note"),
        },
        "camera_spectrometer": {
            "paired_measurements": camera_validation.get("paired_measurements"),
            "median_per_sample_normalized_correlation": camera_validation.get(
                "median_per_sample_normalized_correlation"
            ),
            "overall_within_sample_normalized_pearson_r": camera_validation.get(
                "overall_within_sample_normalized_pearson_r"
            ),
            "overall_raw_camera_vs_spectrometer_area_pearson_r": camera_validation.get(
                "overall_raw_camera_vs_spectrometer_area_pearson_r"
            ),
            "full_spectrum_classifier_accuracy": camera_validation.get(
                "full_spectrum_classifier", {}
            ).get("accuracy"),
        },
        "guidance": [
            "Use normalized band patterns and ratios rather than raw brightness alone.",
            "Treat ordinary RGB-only photos as visual/masking data, not true NIR or red-edge measurements.",
            "For strongest proof, capture the same leaf with the same filter order used by the validation data.",
            "The box and outside measurements need separate calibration because outside light was much stronger.",
        ],
    }


def build_new_data_validation_section(metadata: Mapping[str, Any]) -> dict[str, Any]:
    """Build the report section for the current analyzed sample."""

    profile = load_new_data_profile()
    inside = profile["inside_outside"]
    camera = profile["camera_spectrometer"]
    rgb_only = bool(metadata.get("rgb_only"))
    source_kind = str(metadata.get("source_data_kind") or "")
    analysis_kind = str(metadata.get("analysis_data_kind") or "")

    warnings: list[str] = []
    if rgb_only:
        warnings.append(
            "Profilul de validare este spectrometric; poza RGB analizata acum nu contine NIR/red-edge real."
        )
    if "mixed" in source_kind:
        warnings.append(
            "Pentru imagini mixte, validarea depinde de alinierea corecta intre RGB si benzile grayscale."
        )
    if metadata.get("camera_calibration_applied"):
        pass
    elif "raw" in analysis_kind or not metadata.get("calibration_applied"):
        warnings.append(
            "Interpretarea foloseste intensitati relative; pentru comparatii stricte este nevoie de calibrare."
        )
    if inside.get("note"):
        warnings.append(
            "In setul de validare nu au fost gasite poze JPG facute afara; comparatia afara/in cutie "
            "este bazata pe spectrele spectrometrului."
        )

    return {
        "profile_id": profile["profile_id"],
        "title": profile["title"],
        "applied_to_current_report": True,
        "current_input_kind": source_kind or metadata.get("source_type") or "unknown",
        "reference_metrics": {
            "inside_outside_pairs": inside.get("matched_pairs"),
            "inside_outside_median_shape_similarity_r": _round(inside.get("median_shape_similarity_r"), 3),
            "outside_to_inside_signal_ratio": _round(inside.get("median_outside_to_inside_area_ratio"), 1),
            "healthy_median_shape_similarity_r": _round(inside.get("healthy_median_shape_similarity_r"), 3),
            "unhealthy_median_shape_similarity_r": _round(inside.get("unhealthy_median_shape_similarity_r"), 3),
            "camera_spectrometer_paired_measurements": camera.get("paired_measurements"),
            "camera_median_per_sample_normalized_correlation": _round(
                camera.get("median_per_sample_normalized_correlation"), 3
            ),
            "full_spectrum_classifier_accuracy": _round(
                camera.get("full_spectrum_classifier_accuracy"), 3
            ),
        },
        "guidance": profile["guidance"],
        "warnings": warnings,
    }


def build_validation_profile_text(report: Mapping[str, Any]) -> str:
    """Return a Romanian text block for the GUI validation tab."""

    section = report.get("validation_profile")
    if not isinstance(section, Mapping):
        section = build_new_data_validation_section({})
    metrics = section.get("reference_metrics", {})
    if not isinstance(metrics, Mapping):
        metrics = {}

    lines = [
        str(section.get("title") or PROFILE_TITLE),
        "",
        "Ce inseamna pentru poza analizata:",
        (
            "Aplicatia analizeaza imaginea curenta, iar aceste numere arata cat de bine a fost "
            "validat sistemul camera/spectrometru pe datele reale."
        ),
        "",
        f"Perechi spectrale afara/in cutie: {metrics.get('inside_outside_pairs', 'indisponibil')}",
        (
            "Similaritate mediana forma spectru: "
            f"r = {metrics.get('inside_outside_median_shape_similarity_r', 'indisponibil')}"
        ),
        (
            "Raport semnal afara/in cutie: "
            f"{metrics.get('outside_to_inside_signal_ratio', 'indisponibil')}x"
        ),
        (
            "Corelatie camera/spectrometru pe probe normalizate: "
            f"r = {metrics.get('camera_median_per_sample_normalized_correlation', 'indisponibil')}"
        ),
        "",
        "Cum se foloseste:",
        "- compara forme normalizate si rapoarte intre benzi, nu luminozitatea bruta singura;",
        "- pentru poze RGB simple, foloseste rezultatul ca masca/culoare, nu ca masurare NIR reala;",
        "- pentru dovada mai puternica, fotografiaza aceeasi frunza cu aceleasi filtre si aceeasi ordine;",
        "- masuratorile din cutie si cele de afara trebuie calibrate separat.",
    ]
    warnings = section.get("warnings", [])
    if isinstance(warnings, list) and warnings:
        lines.extend(["", "Atentionari:", *[f"- {item}" for item in warnings]])
    return "\n".join(lines)


__all__ = [
    "PROFILE_ID",
    "PROFILE_TITLE",
    "build_new_data_validation_section",
    "build_validation_profile_text",
    "load_new_data_profile",
]
