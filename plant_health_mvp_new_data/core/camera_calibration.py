"""Camera calibration helpers derived from the real leaf measurements."""

from __future__ import annotations

import json
import math
from pathlib import Path
from typing import Any, Mapping


DATA_DIR = Path(__file__).resolve().parents[1] / "data" / "real_validation"
PROFILE_PATH = DATA_DIR / "camera_calibration_profile.json"
_EPS = 1e-9


def _load_json(path: Path) -> dict[str, Any]:
    with path.open("r", encoding="utf-8") as handle:
        return json.load(handle)


def load_camera_calibration_profile() -> dict[str, Any]:
    """Load the bundled real-data camera calibration profile."""

    return _load_json(PROFILE_PATH)


def _low_confidence_spectrometer_targets(profile: Mapping[str, Any]) -> dict[str, Mapping[str, Any]]:
    """Return spectrometer targets that should not drive calibrated conclusions."""

    raw = profile.get("low_confidence_spectrometer_targets", {})
    if not isinstance(raw, Mapping):
        return {}
    return {
        str(key): value
        for key, value in raw.items()
        if isinstance(value, Mapping)
    }


def _low_confidence_reason(targets: Mapping[str, Mapping[str, Any]], band_key: str) -> str:
    """Return a readable low-confidence reason for a band."""

    item = targets.get(str(band_key), {})
    reason = item.get("reason") if isinstance(item, Mapping) else None
    return str(reason or "spectrometer target marked low-confidence")


def _excluded_index_reasons(targets: Mapping[str, Mapping[str, Any]]) -> dict[str, str]:
    """Map low-confidence wavelengths to calibrated indices that should be hidden."""

    reasons: dict[str, str] = {}
    if "940" in targets:
        reasons["NDWI_850_940"] = (
            "NDWI_850_940 depends on 940 nm. The 940 nm spectrometer target is marked low-confidence, "
            "so this calibrated water proxy is not used for conclusions."
        )
    return reasons


def _coerce_float(value: Any) -> float | None:
    if value is None or value == "":
        return None
    try:
        number = float(value)
    except (TypeError, ValueError):
        return None
    return number if math.isfinite(number) else None


def _round(value: Any, digits: int = 6) -> float | None:
    number = _coerce_float(value)
    if number is None:
        return None
    return round(number, digits)


def _band_key(value: Any) -> str | None:
    number = _coerce_float(value)
    if number is None:
        return None
    rounded = int(round(number))
    if abs(number - rounded) > 1.5:
        return None
    return str(rounded)


def _average_band_items(average_bands: Mapping[str, float | None]) -> list[tuple[str, float]]:
    items: list[tuple[str, float]] = []
    for key, value in average_bands.items():
        band_key = _band_key(key)
        number = _coerce_float(value)
        if band_key is None or number is None:
            continue
        items.append((band_key, number))
    return sorted(items, key=lambda item: int(item[0]))


def _is_eligible(metadata: Mapping[str, Any]) -> bool:
    if bool(metadata.get("camera_calibration_eligible")):
        return True
    source_kind = str(metadata.get("source_data_kind") or "")
    if bool(metadata.get("rgb_only")):
        return False
    return source_kind in {
        "filtered_camera_image",
        "mixed_image_data",
        "mixed_aligned_image_data",
    }


def _dark_white_value(raw_value: float, band_profile: Mapping[str, Any]) -> float | None:
    if not bool(band_profile.get("dark_white_correction_usable")):
        return None
    white = _coerce_float(band_profile.get("camera_white_reference_brightness"))
    dark = _coerce_float(band_profile.get("camera_dark_reference_brightness"))
    if white is None or dark is None:
        return None
    denominator = white - dark
    if abs(denominator) <= _EPS:
        return None
    return (raw_value - dark) / denominator


def _safe_multiply(first: Any, second: Any) -> float | None:
    left = _coerce_float(first)
    right = _coerce_float(second)
    if left is None or right is None:
        return None
    return left * right


def _linear_estimate(value: float, model: Mapping[str, Any]) -> float | None:
    slope = _coerce_float(model.get("slope"))
    intercept = _coerce_float(model.get("intercept"))
    if slope is None or intercept is None:
        return None
    return (slope * value) + intercept


def _single_band_window_estimate(value: float, band_profile: Mapping[str, Any]) -> dict[str, Any]:
    model = band_profile.get("single_band_window_model", {})
    if not isinstance(model, Mapping) or not model.get("available"):
        return {
            "value": None,
            "model": "unavailable",
            "leave_one_leaf_out_rmse": None,
            "training_mean_rmse": None,
        }

    selected = str(model.get("selected_model") or "training_mean")
    linear = model.get("linear", {}) if isinstance(model.get("linear"), Mapping) else {}
    mean_model = model.get("training_mean", {}) if isinstance(model.get("training_mean"), Mapping) else {}
    if selected == "linear":
        estimate = _linear_estimate(value, linear)
        rmse = linear.get("leave_one_leaf_out_rmse")
    else:
        estimate = _coerce_float(mean_model.get("value"))
        rmse = mean_model.get("leave_one_leaf_out_rmse")
    return {
        "value": estimate,
        "model": selected,
        "leave_one_leaf_out_rmse": _coerce_float(rmse),
        "training_mean_rmse": _coerce_float(mean_model.get("leave_one_leaf_out_rmse")),
    }


def _ridge_model_value(
    features: Mapping[str, float],
    model: Mapping[str, Any],
    imputation: Mapping[str, Any],
    feature_wavelengths: list[str],
) -> float | None:
    intercept = _coerce_float(model.get("intercept"))
    coefficients = model.get("coefficients", {})
    means = model.get("feature_means", {})
    stds = model.get("feature_stds", {})
    if intercept is None or not isinstance(coefficients, Mapping) or not isinstance(means, Mapping) or not isinstance(stds, Mapping):
        return None

    estimate = intercept
    for wavelength in feature_wavelengths:
        value = _coerce_float(features.get(wavelength))
        if value is None:
            value = _coerce_float(imputation.get(wavelength))
        coefficient = _coerce_float(coefficients.get(wavelength))
        mean = _coerce_float(means.get(wavelength))
        std = _coerce_float(stds.get(wavelength))
        if value is None or coefficient is None or mean is None or std is None or abs(std) <= _EPS:
            return None
        estimate += coefficient * ((value - mean) / std)
    return estimate


def _ridge_estimates(
    white_values: Mapping[str, float | None],
    profile: Mapping[str, Any],
) -> dict[str, Any]:
    ridge = profile.get("multiband_ridge", {})
    if not isinstance(ridge, Mapping):
        return {
            "used": False,
            "reason": "no multiband ridge profile available",
            "estimates": {},
            "imputed_features": [],
        }

    feature_wavelengths = [str(int(float(value))) for value in ridge.get("feature_wavelengths_nm", [])]
    imputation = ridge.get("feature_imputation_medians", {})
    if not feature_wavelengths or not isinstance(imputation, Mapping):
        return {
            "used": False,
            "reason": "ridge feature metadata is incomplete",
            "estimates": {},
            "imputed_features": [],
        }

    observed_features = {
        key: value
        for key, value in white_values.items()
        if key in feature_wavelengths and value is not None
    }
    minimum_observed = int(ridge.get("minimum_observed_features_for_prediction") or 4)
    imputed = [key for key in feature_wavelengths if key not in observed_features]
    if len(observed_features) < minimum_observed:
        return {
            "used": False,
            "reason": f"needs at least {minimum_observed} observed filter bands",
            "observed_feature_count": len(observed_features),
            "minimum_observed_features": minimum_observed,
            "imputed_features": imputed,
            "estimates": {},
        }

    models = ridge.get("models", {})
    if not isinstance(models, Mapping):
        return {
            "used": False,
            "reason": "ridge models are missing",
            "observed_feature_count": len(observed_features),
            "minimum_observed_features": minimum_observed,
            "imputed_features": imputed,
            "estimates": {},
        }

    estimates: dict[str, Any] = {}
    skipped: dict[str, str] = {}
    for key, model in sorted(models.items(), key=lambda item: int(item[0])):
        if not isinstance(model, Mapping):
            continue
        if not bool(model.get("passes_validation")):
            skipped[str(key)] = "leave-one-leaf-out validation did not beat the baseline"
            continue
        value = _ridge_model_value(observed_features, model, imputation, feature_wavelengths)
        if value is None:
            skipped[str(key)] = "could not evaluate ridge coefficients"
            continue
        estimates[str(key)] = {
            "predicted_spectrometer_window_intensity": _round(value),
            "model": "multiband_ridge",
            "leave_one_leaf_out_rmse": _round(model.get("leave_one_leaf_out_rmse")),
            "baseline_training_mean_rmse": _round(model.get("baseline_training_mean_rmse")),
            "validation_improvement_fraction": _round(model.get("validation_improvement_fraction")),
            "training_samples": model.get("training_samples"),
        }

    return {
        "used": bool(estimates),
        "model_type": ridge.get("model_type"),
        "target_field": ridge.get("target_field"),
        "spectrometer_window_half_width_nm": ridge.get("spectrometer_window_half_width_nm"),
        "observed_feature_count": len(observed_features),
        "minimum_observed_features": minimum_observed,
        "observed_features": sorted(observed_features),
        "imputed_features": imputed,
        "estimates": estimates,
        "skipped_targets": skipped,
        "selection_policy": ridge.get("selection_policy"),
    }


def _normalized_shape_values(
    corrected_bands: Mapping[str, Mapping[str, Any]],
    profile_bands: Mapping[str, Mapping[str, Any]],
) -> dict[str, float | None]:
    values = {
        key: _coerce_float(item.get("white_normalized_camera"))
        for key, item in corrected_bands.items()
    }
    finite = [value for value in values.values() if value is not None]
    if len(finite) < 2:
        return {key: None for key in corrected_bands}
    minimum = min(finite)
    maximum = max(finite)
    denominator = maximum - minimum
    if denominator <= _EPS:
        return {key: None for key in corrected_bands}

    output: dict[str, float | None] = {}
    for key, value in values.items():
        if value is None:
            output[key] = None
            continue
        gain = _coerce_float(profile_bands.get(key, {}).get("normalized_shape_gain_from_camera_to_spectrometer"))
        if gain is None:
            output[key] = None
            continue
        camera_shape = (value - minimum) / denominator
        output[key] = max(0.0, min(1.0, camera_shape * gain))
    return output


def _index_value(first: float | None, second: float | None) -> float | None:
    if first is None or second is None:
        return None
    denominator = first + second
    if abs(denominator) <= _EPS:
        return None
    return (first - second) / denominator


def _ratio_value(first: float | None, second: float | None, *, minus_one: bool = False) -> float | None:
    if first is None or second is None or abs(second) <= _EPS:
        return None
    ratio = first / second
    return ratio - 1.0 if minus_one else ratio


def _compute_calibrated_indices(values: Mapping[str, float | None]) -> dict[str, float | None]:
    band_556 = values.get("556")
    band_680 = values.get("680")
    band_725 = values.get("725")
    band_850 = values.get("850")
    band_940 = values.get("940")
    return {
        "NDVI": _round(_index_value(band_850, band_680)),
        "NDRE": _round(_index_value(band_850, band_725)),
        "GNDVI": _round(_index_value(band_850, band_556)),
        "CI_RE": _round(_ratio_value(band_850, band_725, minus_one=True)),
        "NDWI_850_940": _round(_index_value(band_850, band_940)),
        "SR_RED": _round(_ratio_value(band_850, band_680)),
        "SR_RE": _round(_ratio_value(band_850, band_725)),
    }


def _compute_calibrated_indices_with_exclusions(
    values: Mapping[str, float | None],
    excluded_indices: Mapping[str, str],
) -> dict[str, float | None]:
    """Compute calibrated indices, then suppress low-confidence ones."""

    indices = _compute_calibrated_indices(values)
    for key in excluded_indices:
        if key in indices:
            indices[key] = None
    return indices


def build_camera_calibration_section(
    average_bands: Mapping[str, float | None],
    metadata: Mapping[str, Any],
) -> dict[str, Any]:
    """Return calibrated camera values for the report.

    The raw target-band averages are preserved elsewhere in the report. This
    section adds reference-corrected values and spectrometer-equivalent
    estimates for filter-camera images.
    """

    profile = load_camera_calibration_profile()
    profile_bands = profile.get("bands", {})
    if not isinstance(profile_bands, Mapping):
        profile_bands = {}
    low_confidence_targets = _low_confidence_spectrometer_targets(profile)
    excluded_indices = _excluded_index_reasons(low_confidence_targets)

    eligible = _is_eligible(metadata)
    warnings: list[str] = []
    corrected_bands: dict[str, dict[str, Any]] = {}
    unavailable: list[str] = []

    if not eligible:
        if bool(metadata.get("rgb_only")):
            warnings.append(
                "Poza RGB normala nu a fost corectata cu profilul de filtre; corectia se aplica pozelor numite 532/556/680/725/850/940."
            )
        else:
            warnings.append("Tipul curent de intrare nu a fost marcat ca masurare camera calibrabila.")
        return {
            "profile_id": profile.get("profile_id"),
            "title": profile.get("title"),
            "calibration_applied": False,
            "input_eligible_for_camera_calibration": False,
            "method": profile.get("measurement_basis"),
            "primary_corrected_camera_field": profile.get("primary_corrected_camera_field"),
            "primary_spectrometer_estimate_field": profile.get("primary_spectrometer_estimate_field"),
            "corrected_bands": {},
            "source_response_compensation": profile.get("source_response_compensation", {}),
            "calibrated_indices": {
                "from_white_normalized_camera": _compute_calibrated_indices({}),
                "from_best_spectrometer_window_intensity": _compute_calibrated_indices({}),
                "from_dark_white_proxy": _compute_calibrated_indices({}),
            },
            "excluded_calibrated_indices": excluded_indices,
            "low_confidence_spectrometer_targets": low_confidence_targets,
            "dark_reference_policy": profile.get("dark_reference_policy", {}),
            "limitations": profile.get("limitations", []),
            "warnings": warnings,
        }

    for band_key, raw_value in _average_band_items(average_bands):
        band_profile = profile_bands.get(band_key)
        if not isinstance(band_profile, Mapping):
            unavailable.append(band_key)
            continue

        white = _coerce_float(band_profile.get("camera_white_reference_brightness"))
        if white is None or white <= _EPS:
            unavailable.append(band_key)
            continue

        white_normalized = raw_value / white
        source_curve = band_profile.get("source_curve_compensation", {})
        if not isinstance(source_curve, Mapping):
            source_curve = {}
        source_curve_multiplier = _coerce_float(source_curve.get("compensation_multiplier_vs_850"))
        source_curve_compensated = (
            white_normalized * source_curve_multiplier
            if source_curve_multiplier is not None
            else None
        )
        dark_white = _dark_white_value(raw_value, band_profile)
        raw_factor = band_profile.get("spectrometer_raw_intensity_factor_from_white_normalized_camera")
        reflectance_factor = band_profile.get("spectrometer_reflectance_factor_from_white_normalized_camera")
        reflectance_estimate = _safe_multiply(white_normalized, reflectance_factor)
        if reflectance_estimate is not None and reflectance_estimate < 0:
            reflectance_estimate = None

        corrected_bands[band_key] = {
            "wavelength_nm": int(band_key),
            "raw_camera_value": _round(raw_value),
            "white_reference_brightness": _round(white),
            "white_normalized_camera": _round(white_normalized),
            "source_curve_compensated_camera": _round(source_curve_compensated),
            "source_curve_compensation_multiplier_vs_850": _round(source_curve_multiplier),
            "source_curve_reliability_weight": _round(source_curve.get("reliability_weight")),
            "source_curve_relative_to_850": _round(source_curve.get("relative_to_850_net_source")),
            "source_curve_status": source_curve.get("status"),
            "source_curve_warning": source_curve.get("warning", ""),
            "spectrometer_target_reliability": (
                "low_confidence_excluded"
                if band_key in low_confidence_targets
                else "normal"
            ),
            "spectrometer_target_reliability_reason": (
                _low_confidence_reason(low_confidence_targets, band_key)
                if band_key in low_confidence_targets
                else ""
            ),
            "dark_reference_brightness": _round(band_profile.get("camera_dark_reference_brightness")),
            "dark_white_reflectance_proxy": _round(dark_white),
            "dark_white_correction_used": dark_white is not None,
            "dark_white_status": (
                "used"
                if dark_white is not None
                else str(band_profile.get("dark_white_rejection_reason") or "not available")
            ),
            "spectrometer_equivalent_raw_intensity_at_filter": _round(
                _safe_multiply(white_normalized, raw_factor)
            ),
            "spectrometer_equivalent_reflectance_at_filter": _round(reflectance_estimate),
            "median_abs_raw_intensity_error_after_factor": _round(
                band_profile.get("median_abs_raw_intensity_error_after_factor")
            ),
            "median_relative_raw_intensity_error_after_factor": _round(
                band_profile.get("median_relative_raw_intensity_error_after_factor")
            ),
        }

    shape_estimates = _normalized_shape_values(corrected_bands, profile_bands)
    for band_key, estimate in shape_estimates.items():
        corrected_bands[band_key]["normalized_spectrometer_shape_estimate"] = _round(estimate)

    white_values = {
        key: _coerce_float(value.get("white_normalized_camera"))
        for key, value in corrected_bands.items()
    }
    ridge_section = _ridge_estimates(white_values, profile)
    ridge_estimates = ridge_section.get("estimates", {})
    best_spectrometer_estimates: dict[str, Any] = {}
    for band_key, values in corrected_bands.items():
        if band_key in low_confidence_targets:
            reason = _low_confidence_reason(low_confidence_targets, band_key)
            values["single_band_spectrometer_window_intensity"] = None
            values["single_band_model_used"] = "excluded_low_confidence_spectrometer_target"
            values["single_band_leave_one_leaf_out_rmse"] = None
            values["single_band_training_mean_rmse"] = None
            values["spectrometer_equivalent_raw_intensity_at_filter"] = None
            values["spectrometer_equivalent_window_intensity"] = None
            values["best_spectrometer_window_intensity"] = None
            values["best_spectrometer_model"] = "excluded_low_confidence_spectrometer_target"
            values["best_spectrometer_reliability_reason"] = reason
            best_spectrometer_estimates[band_key] = {
                "value": None,
                "model": "excluded_low_confidence_spectrometer_target",
                "leave_one_leaf_out_rmse": None,
                "training_samples": profile_bands.get(band_key, {}).get("app_training_sample_count"),
                "reason": reason,
            }
            continue

        single = _single_band_window_estimate(
            _coerce_float(values.get("white_normalized_camera")) or 0.0,
            profile_bands.get(band_key, {}),
        )
        single_value = _coerce_float(single.get("value"))
        values["single_band_spectrometer_window_intensity"] = _round(single_value)
        values["single_band_model_used"] = single.get("model")
        values["single_band_leave_one_leaf_out_rmse"] = _round(single.get("leave_one_leaf_out_rmse"))
        values["single_band_training_mean_rmse"] = _round(single.get("training_mean_rmse"))
        values["spectrometer_equivalent_raw_intensity_at_filter"] = _round(single_value)
        values["spectrometer_equivalent_window_intensity"] = _round(single_value)

    for key in sorted({*corrected_bands.keys(), *ridge_estimates.keys()}, key=lambda item: int(item)):
        if key in low_confidence_targets:
            continue

        ridge_item = ridge_estimates.get(key)
        if isinstance(ridge_item, Mapping):
            value = _coerce_float(ridge_item.get("predicted_spectrometer_window_intensity"))
            best_spectrometer_estimates[key] = {
                "value": _round(value),
                "model": "multiband_ridge",
                "leave_one_leaf_out_rmse": _round(ridge_item.get("leave_one_leaf_out_rmse")),
                "training_samples": ridge_item.get("training_samples"),
            }
            if key in corrected_bands:
                corrected_bands[key]["best_spectrometer_window_intensity"] = _round(value)
                corrected_bands[key]["best_spectrometer_model"] = "multiband_ridge"
            continue

        corrected = corrected_bands.get(key, {})
        if isinstance(corrected, Mapping):
            value = _coerce_float(corrected.get("single_band_spectrometer_window_intensity"))
            best_spectrometer_estimates[key] = {
                "value": _round(value),
                "model": f"single_band_{corrected.get('single_band_model_used')}",
                "leave_one_leaf_out_rmse": _round(corrected.get("single_band_leave_one_leaf_out_rmse")),
                "training_samples": profile_bands.get(key, {}).get("app_training_sample_count"),
            }
            corrected_bands[key]["best_spectrometer_window_intensity"] = _round(value)
            corrected_bands[key]["best_spectrometer_model"] = best_spectrometer_estimates[key]["model"]

    spectrometer_values = {
        key: _coerce_float(value.get("value"))
        for key, value in best_spectrometer_estimates.items()
        if isinstance(value, Mapping)
    }
    dark_white_values = {
        key: _coerce_float(value.get("dark_white_reflectance_proxy"))
        for key, value in corrected_bands.items()
    }

    dark_used_count = sum(
        1
        for value in corrected_bands.values()
        if bool(value.get("dark_white_correction_used"))
    )
    if eligible and corrected_bands and dark_used_count == 0:
        warnings.append(
            "Referinta neagra a fost verificata, dar nu a fost scazuta deoarece nu este fizic valida pentru aceste filtre."
        )
    for band_key in sorted(low_confidence_targets, key=lambda item: int(item)):
        if band_key in corrected_bands:
            warnings.append(
                f"{band_key} nm este marcat low-confidence pentru calibrarea cu spectrometrul; "
                "banda camera ramane vizibila si poate fi compensata dupa curba sursei, "
                "dar nu este folosita pentru concluzii calibrate."
            )
    for band_key, values in sorted(corrected_bands.items(), key=lambda item: int(item[0])):
        if values.get("source_curve_status") == "weak_source_amplifies_noise":
            multiplier = _round(values.get("source_curve_compensation_multiplier_vs_850"), 2)
            warnings.append(
                f"Compensarea curbei sursei pentru {band_key} nm ar inmulti semnalul cu aproximativ {multiplier}x; "
                "valoarea compensata este raportata, dar are greutate de incredere mica."
            )
    if unavailable:
        warnings.append(f"Nu exista profil de calibrare pentru benzile: {', '.join(unavailable)}.")
    if not ridge_section.get("used") and len(white_values) >= 4:
        warnings.append(
            "Modelul multibanda nu a fost folosit pentru niciun target valid; raportul foloseste modele single-band."
        )
    if ridge_section.get("imputed_features"):
        warnings.append(
            "Modelul multibanda a completat benzile lipsa cu mediane de antrenare: "
            + ", ".join(str(item) for item in ridge_section.get("imputed_features", []))
            + "."
        )

    return {
        "profile_id": profile.get("profile_id"),
        "title": profile.get("title"),
        "calibration_applied": bool(eligible and corrected_bands),
        "input_eligible_for_camera_calibration": eligible,
        "method": profile.get("measurement_basis"),
        "primary_corrected_camera_field": profile.get("primary_corrected_camera_field"),
        "primary_spectrometer_estimate_field": profile.get("primary_spectrometer_estimate_field"),
        "corrected_bands": corrected_bands,
        "best_spectrometer_estimates": best_spectrometer_estimates,
        "regression_calibration": ridge_section,
        "source_response_compensation": profile.get("source_response_compensation", {}),
        "calibrated_indices": {
            "from_white_normalized_camera": _compute_calibrated_indices_with_exclusions(white_values, excluded_indices),
            "from_best_spectrometer_window_intensity": _compute_calibrated_indices_with_exclusions(spectrometer_values, excluded_indices),
            "from_dark_white_proxy": _compute_calibrated_indices_with_exclusions(dark_white_values, excluded_indices),
        },
        "excluded_calibrated_indices": excluded_indices,
        "low_confidence_spectrometer_targets": low_confidence_targets,
        "dark_reference_policy": profile.get("dark_reference_policy", {}),
        "limitations": profile.get("limitations", []),
        "warnings": warnings,
    }


def build_camera_calibration_text(report: Mapping[str, Any]) -> str:
    """Build Romanian GUI text for the calibration report section."""

    section = report.get("camera_calibration")
    if not isinstance(section, Mapping):
        section = build_camera_calibration_section({}, {})

    corrected = section.get("corrected_bands", {})
    if not isinstance(corrected, Mapping) or not corrected:
        warnings = section.get("warnings", [])
        lines = [
            "Corectie camera",
            "Nu exista benzi camera calibrate in raportul curent.",
        ]
        if isinstance(warnings, list) and warnings:
            lines.extend(["", "Avertismente:", *[f"- {warning}" for warning in warnings]])
        return "\n".join(lines)

    lines = [
        "Corectie camera",
        (
            "Valorile brute ale pozei sunt impartite la referinta alba a filtrului. Apoi aplicatia alege "
            "un model validat: regresie ridge multibanda cand trece testul leave-one-leaf-out, altfel "
            "un model single-band pentru lungimea de unda respectiva. Separat, curba masurata a sursei "
            "este folosita ca factor de compensare si ca greutate de incredere."
        ),
        "",
    ]
    for band_key, values in sorted(corrected.items(), key=lambda item: int(item[0])):
        if not isinstance(values, Mapping):
            continue
        if values.get("spectrometer_target_reliability") == "low_confidence_excluded":
            lines.append(
                (
                    f"{band_key} nm: brut {_round(values.get('raw_camera_value'), 4)}, "
                    f"corectat alb {_round(values.get('white_normalized_camera'), 4)}, "
                    f"compensat sursa {_round(values.get('source_curve_compensated_camera'), 4)}, "
                    f"greutate {_round(values.get('source_curve_reliability_weight'), 3)}, "
                    "echiv. spectrometru exclus low-confidence"
                )
            )
            continue
        lines.append(
            (
                f"{band_key} nm: brut {_round(values.get('raw_camera_value'), 4)}, "
                f"corectat alb {_round(values.get('white_normalized_camera'), 4)}, "
                f"compensat sursa {_round(values.get('source_curve_compensated_camera'), 4)}, "
                f"echiv. spectrometru {_round(values.get('best_spectrometer_window_intensity'), 2)} "
                f"({values.get('best_spectrometer_model')})"
            )
        )

    indices = section.get("calibrated_indices", {})
    best_indices = indices.get("from_best_spectrometer_window_intensity") if isinstance(indices, Mapping) else {}
    if isinstance(best_indices, Mapping):
        usable = [
            f"{name} {_round(value, 4)}"
            for name, value in best_indices.items()
            if _coerce_float(value) is not None
        ]
        if usable:
            lines.extend(["", "Indici calculati dupa estimarea spectrometrica validata:", ", ".join(usable)])

    excluded = section.get("excluded_calibrated_indices", {})
    if isinstance(excluded, Mapping) and excluded:
        lines.extend(
            [
                "",
                "Indici exclusi din concluziile calibrate:",
                *[f"- {name}: {reason}" for name, reason in excluded.items()],
            ]
        )

    regression = section.get("regression_calibration", {})
    if isinstance(regression, Mapping):
        lines.extend(
            [
                "",
                (
                    "Regresie multibanda: "
                    f"{'folosita' if regression.get('used') else 'nefolosita'}; "
                    f"benzi observate {regression.get('observed_feature_count', 'indisponibil')}."
                ),
            ]
        )

    warnings = section.get("warnings", [])
    if isinstance(warnings, list) and warnings:
        lines.extend(["", "Avertismente:", *[f"- {warning}" for warning in warnings]])
    return "\n".join(lines)


__all__ = [
    "build_camera_calibration_section",
    "build_camera_calibration_text",
    "load_camera_calibration_profile",
]
