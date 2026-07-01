"""Build the camera calibration profile used by the copied analysis app.

This version calibrates against the values the app itself produces. For each
real leaf sample it loads the filter JPGs, builds the app vegetation mask,
averages the app target bands, normalizes by the white reference, and compares
those values with a robust spectrometer window around each filter wavelength.
"""

from __future__ import annotations

import csv
import json
import math
import re
import statistics
import sys
from pathlib import Path
from typing import Any

import numpy as np
from PIL import Image


ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from plant_health_mvp_new_data.core.models.sample import SpectralSample
from plant_health_mvp_new_data.core.spectrum import compute_average_spectrum
from plant_health_mvp_new_data.core.vegetation import apply_vegetation_mask

DATA_ROOT = Path(r"C:\Users\david\OneDrive\Desktop\data analisys")
REAL_ANALYSIS = ROOT / "outputs" / "real_leaf_analysis"
VALIDATION = ROOT / "outputs" / "camera_validation_report"
OUTPUT = (
    ROOT
    / "plant_health_mvp_new_data"
    / "data"
    / "real_validation"
    / "camera_calibration_profile.json"
)
FILTER_WAVELENGTHS = (532, 556, 680, 725, 850, 940)
LOW_CONFIDENCE_SPECTROMETER_TARGETS = {
    940: (
        "940 nm is treated as low-confidence for spectrometer-derived calibration because "
        "the measured box-source curve is weak there: after dark subtraction, the 940 nm source signal "
        "is about 21% of the 850 nm signal, so curve compensation would multiply noise by about 4.7x. "
        "The Ocean Optics USB2000+XR1-ES nominal range includes 940 nm, but this setup gives a low-SNR "
        "940 nm reference. "
        "The camera band remains available as a raw/white-normalized exploratory measurement, "
        "but it is excluded from spectrometer-equivalent calibration targets and water-index conclusions."
    )
}
SPECTROMETER_TARGET_WAVELENGTHS = tuple(
    wavelength for wavelength in FILTER_WAVELENGTHS if wavelength not in LOW_CONFIDENCE_SPECTROMETER_TARGETS
)
SPECTROMETER_HALF_WINDOW_NM = 10.0
SOURCE_COMPENSATION_REFERENCE_NM = 850
SOURCE_COMPENSATION_LOW_RELATIVE_THRESHOLD = 0.30
RIDGE_ALPHAS = (0.01, 0.03, 0.1, 0.3, 1.0, 3.0, 10.0, 30.0, 100.0, 300.0)


def _float(value: Any) -> float | None:
    try:
        number = float(value)
    except (TypeError, ValueError):
        return None
    return number if math.isfinite(number) else None


def _round(value: Any, digits: int = 6) -> float | None:
    number = _float(value)
    if number is None:
        return None
    return round(number, digits)


def _read_csv(path: Path) -> list[dict[str, str]]:
    with path.open("r", encoding="utf-8-sig", newline="") as handle:
        return list(csv.DictReader(handle))


def _median(values: list[float]) -> float | None:
    finite = [value for value in values if math.isfinite(value)]
    return statistics.median(finite) if finite else None


def _mean(values: list[float]) -> float | None:
    finite = [value for value in values if math.isfinite(value)]
    return statistics.mean(finite) if finite else None


def _median_abs(values: list[float]) -> float | None:
    finite = [abs(value) for value in values if math.isfinite(value)]
    return statistics.median(finite) if finite else None


def _rmse(errors: list[float]) -> float | None:
    finite = [value for value in errors if math.isfinite(value)]
    if not finite:
        return None
    return math.sqrt(sum(value * value for value in finite) / len(finite))


def _mae(errors: list[float]) -> float | None:
    finite = [abs(value) for value in errors if math.isfinite(value)]
    return statistics.mean(finite) if finite else None


def _r2(actual: list[float], predicted: list[float]) -> float | None:
    if len(actual) != len(predicted) or len(actual) < 2:
        return None
    mean_actual = statistics.mean(actual)
    total = sum((value - mean_actual) ** 2 for value in actual)
    if total <= 1e-12:
        return None
    residual = sum((pred - value) ** 2 for pred, value in zip(predicted, actual))
    return 1.0 - (residual / total)


def _median_ratio(numerators: list[float], denominators: list[float], eps: float = 1e-9) -> float | None:
    ratios: list[float] = []
    for numerator, denominator in zip(numerators, denominators):
        if math.isfinite(numerator) and math.isfinite(denominator) and abs(denominator) > eps:
            ratios.append(numerator / denominator)
    return _median(ratios)


def _reference_values(camera_features: list[dict[str, str]]) -> tuple[dict[int, float], float | None]:
    white: dict[int, float] = {}
    dark_values: list[float] = []
    for row in camera_features:
        condition = row.get("condition", "")
        label = row.get("filter_label", "")
        brightness = _float(row.get("brightness"))
        if brightness is None:
            continue
        if condition == "white_reference" and label not in {"", "none"}:
            white[int(float(label))] = brightness
        elif condition == "dark_reference":
            dark_values.append(brightness)
    return white, _median(dark_values)


def _sample_id_to_path(sample_id: str) -> Path:
    return DATA_ROOT.joinpath(*Path(sample_id).parts)


def _read_spectrum(path: Path) -> tuple[np.ndarray, np.ndarray] | None:
    lines = path.read_text(encoding="utf-8", errors="ignore").splitlines()
    start = 0
    for index, line in enumerate(lines):
        if "Begin Spectral Data" in line:
            start = index + 1
            break
    pairs: list[tuple[float, float]] = []
    for line in lines[start:]:
        nums = re.findall(r"[-+]?(?:\d*\.\d+|\d+)(?:[eE][-+]?\d+)?", line)
        if len(nums) >= 2:
            pairs.append((float(nums[0]), float(nums[1])))
    if len(pairs) < 10:
        return None
    arr = np.asarray(pairs, dtype=float)
    return arr[:, 0], arr[:, 1]


def _spectrometer_window_median(path: Path, wavelength_nm: int) -> float | None:
    parsed = _read_spectrum(path)
    if parsed is None:
        return None
    wavelengths, intensities = parsed
    return _window_median(wavelengths, intensities, wavelength_nm)


def _window_median(wavelengths: np.ndarray, intensities: np.ndarray, wavelength_nm: int) -> float | None:
    mask = (
        (wavelengths >= wavelength_nm - SPECTROMETER_HALF_WINDOW_NM)
        & (wavelengths <= wavelength_nm + SPECTROMETER_HALF_WINDOW_NM)
        & np.isfinite(intensities)
    )
    if not np.any(mask):
        return None
    return float(np.nanmedian(intensities[mask]))


def _build_source_response_compensation() -> dict[str, Any]:
    """Build the measured source-curve compensation profile.

    The curve is derived from the user's own box source and dark reference,
    not from a generic datasheet. It is used as a compensation/confidence
    layer because dividing by a very weak source band amplifies noise.
    """

    source_path = DATA_ROOT / "in cutie" / "spectru sursa.txt"
    dark_path = DATA_ROOT / "in cutie" / "Refirinta neagra" / "referinta neagra fara .txt"
    source = _read_spectrum(source_path) if source_path.exists() else None
    dark = _read_spectrum(dark_path) if dark_path.exists() else None
    if source is None or dark is None:
        return {
            "available": False,
            "method": "source_minus_dark_relative_curve",
            "reason": "missing indoor source or dark reference spectrum",
            "bands": {},
        }

    source_wavelengths, source_intensities = source
    dark_wavelengths, dark_intensities = dark
    bands: dict[str, dict[str, Any]] = {}
    net_source_by_band: dict[int, float] = {}
    for wavelength in FILTER_WAVELENGTHS:
        source_window = _window_median(source_wavelengths, source_intensities, wavelength)
        dark_window = _window_median(dark_wavelengths, dark_intensities, wavelength)
        if source_window is None or dark_window is None:
            continue
        net_source_by_band[wavelength] = max(0.0, source_window - dark_window)

    reference_net = net_source_by_band.get(SOURCE_COMPENSATION_REFERENCE_NM)
    if reference_net is None or reference_net <= 1e-9:
        finite_nets = [value for value in net_source_by_band.values() if value > 1e-9]
        reference_net = _median(finite_nets)
    peak_net = max(net_source_by_band.values()) if net_source_by_band else None

    for wavelength in FILTER_WAVELENGTHS:
        source_window = _window_median(source_wavelengths, source_intensities, wavelength)
        dark_window = _window_median(dark_wavelengths, dark_intensities, wavelength)
        net_source = net_source_by_band.get(wavelength)
        relative_to_reference = (
            net_source / reference_net
            if net_source is not None and reference_net is not None and reference_net > 1e-9
            else None
        )
        relative_to_peak = (
            net_source / peak_net
            if net_source is not None and peak_net is not None and peak_net > 1e-9
            else None
        )
        multiplier = (
            reference_net / net_source
            if net_source is not None and reference_net is not None and net_source > 1e-9
            else None
        )
        weight = (
            max(0.0, min(1.0, relative_to_reference))
            if relative_to_reference is not None
            else None
        )
        weak_source = bool(
            relative_to_reference is not None
            and relative_to_reference < SOURCE_COMPENSATION_LOW_RELATIVE_THRESHOLD
        )
        bands[str(wavelength)] = {
            "wavelength_nm": wavelength,
            "source_window_median_intensity": _round(source_window),
            "dark_window_median_intensity": _round(dark_window),
            "net_source_window_intensity": _round(net_source),
            "relative_to_850_net_source": _round(relative_to_reference),
            "relative_to_peak_net_source": _round(relative_to_peak),
            "compensation_multiplier_vs_850": _round(multiplier),
            "reliability_weight": _round(weight),
            "status": "weak_source_amplifies_noise" if weak_source else "usable",
            "warning": (
                "Source curve compensation is possible, but this band is weak and the multiplier "
                "would amplify noise."
                if weak_source
                else ""
            ),
        }

    return {
        "available": bool(bands),
        "method": "source_minus_dark_relative_curve",
        "source_file": str(source_path),
        "dark_file": str(dark_path),
        "reference_wavelength_nm": SOURCE_COMPENSATION_REFERENCE_NM,
        "low_relative_threshold": SOURCE_COMPENSATION_LOW_RELATIVE_THRESHOLD,
        "formula": (
            "camera_source_compensated(lambda) = white_normalized_camera(lambda) * "
            "net_source(850 nm) / net_source(lambda); reliability_weight(lambda) = "
            "min(1, net_source(lambda) / net_source(850 nm))"
        ),
        "bands": bands,
    }


def _load_filter_band(path: Path) -> np.ndarray:
    image = Image.open(path).convert("RGB")
    rgb = np.asarray(image, dtype=np.float32) / 255.0
    return np.max(rgb, axis=2).astype(np.float32, copy=False)


def _app_average_filter_values(sample_id: str, rows_by_filter: dict[int, dict[str, str]]) -> tuple[dict[int, float], dict[str, Any]]:
    target_bands: dict[str, np.ndarray] = {}
    wavelengths: list[float] = []
    arrays: list[np.ndarray] = []
    camera_dir = _sample_id_to_path(sample_id) / "camera"

    for wavelength in sorted(rows_by_filter):
        path = camera_dir / f"{wavelength}.jpg"
        if not path.exists():
            continue
        band = _load_filter_band(path)
        target_bands[str(wavelength)] = band
        arrays.append(band)
        wavelengths.append(float(wavelength))

    if not arrays:
        return {}, {"method": "missing", "vegetation_pixel_count": 0}

    data = np.stack(arrays, axis=-1)
    sample = SpectralSample(
        source_type="mixed_image_bundle",
        available_wavelengths=np.asarray(wavelengths, dtype=float),
        data=data,
        target_bands=target_bands,
        metadata={
            "source_data_kind": "mixed_image_data",
            "mock_flag": False,
        },
    )
    apply_vegetation_mask(sample)
    averages, spectrum_metadata = compute_average_spectrum(sample)
    return (
        {int(float(key)): float(value) for key, value in averages.items() if value is not None},
        {
            "vegetation_pixel_count": spectrum_metadata.get("vegetation_pixel_count"),
            "mask_method": sample.metadata.get("vegetation_mask", {}).get("method"),
            "mask_used_bands": sample.metadata.get("vegetation_mask", {}).get("used_bands"),
        },
    )


def _build_training_table(
    paired_rows: list[dict[str, str]],
    white_references: dict[int, float],
) -> list[dict[str, Any]]:
    grouped: dict[str, dict[int, dict[str, str]]] = {}
    for row in paired_rows:
        label = row.get("filter_label", "")
        if not label:
            continue
        grouped.setdefault(row["sample_id"], {})[int(float(label))] = row

    training_rows: list[dict[str, Any]] = []
    for sample_id, rows_by_filter in sorted(grouped.items()):
        raw_camera, mask_metadata = _app_average_filter_values(sample_id, rows_by_filter)
        white_normalized: dict[str, float] = {}
        spectrometer_window: dict[str, float] = {}
        old_point_intensity: dict[str, float] = {}

        for wavelength, row in sorted(rows_by_filter.items()):
            white = white_references.get(wavelength)
            raw_value = raw_camera.get(wavelength)
            if white is not None and white > 1e-9 and raw_value is not None:
                white_normalized[str(wavelength)] = raw_value / white

            spectrum_path = _sample_id_to_path(sample_id) / "spectru" / row.get("spectrum_file", "")
            if spectrum_path.exists() and wavelength not in LOW_CONFIDENCE_SPECTROMETER_TARGETS:
                window = _spectrometer_window_median(spectrum_path, wavelength)
                if window is not None:
                    spectrometer_window[str(wavelength)] = window

            point = _float(row.get("raw_intensity_at_filter"))
            if point is not None:
                old_point_intensity[str(wavelength)] = point

        training_rows.append(
            {
                "sample_id": sample_id,
                "condition": next(iter(rows_by_filter.values())).get("condition"),
                "app_white_normalized_camera": white_normalized,
                "spectrometer_window_median": spectrometer_window,
                "spectrometer_point_intensity": old_point_intensity,
                "mask": mask_metadata,
            }
        )
    return training_rows


def _fit_linear(xs: np.ndarray, ys: np.ndarray) -> tuple[float, float]:
    design = np.vstack([xs, np.ones(xs.size)]).T
    slope, intercept = np.linalg.lstsq(design, ys, rcond=None)[0]
    return float(slope), float(intercept)


def _loocv_single_band(xs: list[float], ys: list[float]) -> dict[str, Any]:
    if len(xs) < 3:
        return {
            "available": False,
            "reason": "at least 3 paired samples are required",
        }

    x = np.asarray(xs, dtype=float)
    y = np.asarray(ys, dtype=float)
    linear_predictions: list[float] = []
    multiplier_predictions: list[float] = []
    mean_predictions: list[float] = []

    for holdout in range(len(x)):
        train = [index for index in range(len(x)) if index != holdout]
        train_x = x[train]
        train_y = y[train]
        slope, intercept = _fit_linear(train_x, train_y)
        linear_predictions.append(float((slope * x[holdout]) + intercept))
        factor = _median_ratio(train_y.tolist(), train_x.tolist())
        multiplier_predictions.append(float(x[holdout] * factor) if factor is not None else float(np.mean(train_y)))
        mean_predictions.append(float(np.mean(train_y)))

    linear_errors = [pred - actual for pred, actual in zip(linear_predictions, y.tolist())]
    multiplier_errors = [pred - actual for pred, actual in zip(multiplier_predictions, y.tolist())]
    mean_errors = [pred - actual for pred, actual in zip(mean_predictions, y.tolist())]

    slope, intercept = _fit_linear(x, y)
    factor = _median_ratio(y.tolist(), x.tolist())
    baseline_mean = float(np.mean(y))
    linear_rmse = _rmse(linear_errors)
    mean_rmse = _rmse(mean_errors)

    selected = "linear"
    if linear_rmse is None or mean_rmse is None or linear_rmse > mean_rmse:
        selected = "training_mean"

    return {
        "available": True,
        "selected_model": selected,
        "linear": {
            "slope": _round(slope),
            "intercept": _round(intercept),
            "leave_one_leaf_out_rmse": _round(linear_rmse),
            "leave_one_leaf_out_mae": _round(_mae(linear_errors)),
            "leave_one_leaf_out_r2": _round(_r2(y.tolist(), linear_predictions)),
        },
        "median_multiplier": {
            "factor": _round(factor),
            "leave_one_leaf_out_rmse": _round(_rmse(multiplier_errors)),
            "leave_one_leaf_out_mae": _round(_mae(multiplier_errors)),
        },
        "training_mean": {
            "value": _round(baseline_mean),
            "leave_one_leaf_out_rmse": _round(mean_rmse),
            "leave_one_leaf_out_mae": _round(_mae(mean_errors)),
        },
    }


def _feature_medians(training_rows: list[dict[str, Any]]) -> dict[str, float]:
    medians: dict[str, float] = {}
    for wavelength in FILTER_WAVELENGTHS:
        values = [
            float(row["app_white_normalized_camera"][str(wavelength)])
            for row in training_rows
            if str(wavelength) in row["app_white_normalized_camera"]
        ]
        median = _median(values)
        if median is not None:
            medians[str(wavelength)] = median
    return medians


def _matrix_for_samples(
    training_rows: list[dict[str, Any]],
    feature_medians: dict[str, float],
) -> np.ndarray:
    matrix: list[list[float]] = []
    for row in training_rows:
        camera = row["app_white_normalized_camera"]
        matrix.append(
            [
                float(camera.get(str(wavelength), feature_medians[str(wavelength)]))
                for wavelength in FILTER_WAVELENGTHS
            ]
        )
    return np.asarray(matrix, dtype=float)


def _fit_ridge(x: np.ndarray, y: np.ndarray, alpha: float) -> dict[str, Any]:
    mean = np.mean(x, axis=0)
    std = np.std(x, axis=0)
    std[std < 1e-9] = 1.0
    z = (x - mean) / std
    y_mean = float(np.mean(y))
    coefficients = np.linalg.solve(
        z.T @ z + (float(alpha) * np.eye(z.shape[1])),
        z.T @ (y - y_mean),
    )
    return {
        "feature_means": mean,
        "feature_stds": std,
        "intercept": y_mean,
        "coefficients": coefficients,
    }


def _predict_ridge(model: dict[str, Any], x: np.ndarray) -> np.ndarray:
    z = (x - model["feature_means"]) / model["feature_stds"]
    return model["intercept"] + z @ model["coefficients"]


def _loocv_ridge_for_target(
    training_rows: list[dict[str, Any]],
    target: int,
    feature_medians: dict[str, float],
) -> dict[str, Any] | None:
    rows = [row for row in training_rows if str(target) in row["spectrometer_window_median"]]
    if len(rows) < 4:
        return None

    x_all = _matrix_for_samples(rows, feature_medians)
    y_all = np.asarray([float(row["spectrometer_window_median"][str(target)]) for row in rows], dtype=float)
    best: dict[str, Any] | None = None

    for alpha in RIDGE_ALPHAS:
        predictions: list[float] = []
        for holdout in range(len(rows)):
            train_rows = [row for index, row in enumerate(rows) if index != holdout]
            x_train = _matrix_for_samples(train_rows, feature_medians)
            y_train = np.asarray(
                [float(row["spectrometer_window_median"][str(target)]) for row in train_rows],
                dtype=float,
            )
            model = _fit_ridge(x_train, y_train, alpha)
            predictions.append(float(_predict_ridge(model, x_all[holdout : holdout + 1])[0]))

        errors = [pred - actual for pred, actual in zip(predictions, y_all.tolist())]
        rmse = _rmse(errors)
        if rmse is None:
            continue
        if best is None or rmse < best["leave_one_leaf_out_rmse"]:
            best = {
                "alpha": float(alpha),
                "predictions": predictions,
                "leave_one_leaf_out_rmse": rmse,
                "leave_one_leaf_out_mae": _mae(errors),
                "leave_one_leaf_out_r2": _r2(y_all.tolist(), predictions),
            }

    if best is None:
        return None

    mean_predictions = []
    for holdout in range(len(rows)):
        train_values = [y_all[index] for index in range(len(rows)) if index != holdout]
        mean_predictions.append(float(np.mean(train_values)))
    mean_errors = [pred - actual for pred, actual in zip(mean_predictions, y_all.tolist())]
    baseline_rmse = _rmse(mean_errors)

    final_model = _fit_ridge(x_all, y_all, best["alpha"])
    improvement = (
        None
        if baseline_rmse is None or baseline_rmse <= 1e-12
        else 1.0 - (best["leave_one_leaf_out_rmse"] / baseline_rmse)
    )
    passes_validation = bool(
        baseline_rmse is not None
        and best["leave_one_leaf_out_rmse"] < baseline_rmse
        and len(rows) >= 4
    )

    return {
        "target_wavelength_nm": target,
        "training_samples": len(rows),
        "alpha": _round(best["alpha"]),
        "intercept": _round(final_model["intercept"]),
        "coefficients": {
            str(wavelength): _round(value)
            for wavelength, value in zip(FILTER_WAVELENGTHS, final_model["coefficients"].tolist())
        },
        "feature_means": {
            str(wavelength): _round(value)
            for wavelength, value in zip(FILTER_WAVELENGTHS, final_model["feature_means"].tolist())
        },
        "feature_stds": {
            str(wavelength): _round(value)
            for wavelength, value in zip(FILTER_WAVELENGTHS, final_model["feature_stds"].tolist())
        },
        "leave_one_leaf_out_rmse": _round(best["leave_one_leaf_out_rmse"]),
        "leave_one_leaf_out_mae": _round(best["leave_one_leaf_out_mae"]),
        "leave_one_leaf_out_r2": _round(best["leave_one_leaf_out_r2"]),
        "baseline_training_mean_rmse": _round(baseline_rmse),
        "validation_improvement_fraction": _round(improvement),
        "passes_validation": passes_validation,
    }


def _build_band_profile(
    filter_label: str,
    rows: list[dict[str, str]],
    validation_rows: list[dict[str, str]],
    training_rows: list[dict[str, Any]],
    white_reference: float | None,
    dark_reference: float | None,
    source_response_compensation: dict[str, Any],
) -> dict[str, Any]:
    wavelength = int(float(filter_label))
    app_camera_values = [
        row["app_white_normalized_camera"][filter_label]
        for row in training_rows
        if filter_label in row["app_white_normalized_camera"]
    ]
    training_pairs = [
        (
            row["app_white_normalized_camera"][filter_label],
            row["spectrometer_window_median"][filter_label],
        )
        for row in training_rows
        if filter_label in row["app_white_normalized_camera"]
        and filter_label in row["spectrometer_window_median"]
    ]
    paired_camera_values = [pair[0] for pair in training_pairs]
    spectrometer_windows = [pair[1] for pair in training_pairs]
    old_point_values = [_float(row.get("raw_intensity_at_filter")) for row in rows]
    old_point_values = [value for value in old_point_values if value is not None]
    single_band_model = _loocv_single_band(paired_camera_values, spectrometer_windows)

    validation_for_band = [row for row in validation_rows if row.get("filter_label") == filter_label]
    cam_shape = [
        _float(row.get("camera_brightness_norm_in_sample"))
        for row in validation_for_band
    ]
    spec_shape = [
        _float(row.get("spectrometer_area_norm_in_sample"))
        for row in validation_for_band
    ]
    shape_gain = _median_ratio(
        [value for value in spec_shape if value is not None],
        [value for value in cam_shape if value is not None],
        eps=0.05,
    )
    shape_errors: list[float] = []
    if shape_gain is not None:
        for cam_value, spec_value in zip(cam_shape, spec_shape):
            if cam_value is None or spec_value is None:
                continue
            if cam_value <= 0.05:
                continue
            shape_errors.append((cam_value * shape_gain) - spec_value)

    raw_camera_values = []
    for row in rows:
        value = _float(row.get("camera_brightness"))
        if value is not None:
            raw_camera_values.append(value)

    dark_white_usable = False
    dark_rejection = "dark reference missing"
    if white_reference is not None and dark_reference is not None:
        denominator = white_reference - dark_reference
        between = [
            value
            for value in raw_camera_values
            if min(white_reference, dark_reference) <= value <= max(white_reference, dark_reference)
        ]
        fraction_between = len(between) / len(raw_camera_values) if raw_camera_values else 0.0
        dark_white_usable = bool(denominator > 0.02 and fraction_between >= 0.6)
        if dark_white_usable:
            dark_rejection = ""
        elif denominator <= 0.02:
            dark_rejection = (
                "dark/white denominator is not positive enough for this filter "
                "(camera auto-exposure or missing per-filter dark frame)"
            )
        else:
            dark_rejection = (
                "paired leaf brightness is mostly below the dark reference, so subtracting "
                "this dark frame would create non-physical negative reflectance"
            )

    source_curve_bands = source_response_compensation.get("bands", {})
    source_curve = source_curve_bands.get(filter_label, {}) if isinstance(source_curve_bands, dict) else {}
    if not isinstance(source_curve, dict):
        source_curve = {}

    return {
        "wavelength_nm": wavelength,
        "paired_sample_count": len(rows),
        "app_training_sample_count": len(app_camera_values),
        "validation_pair_count": len(validation_for_band),
        "camera_white_reference_brightness": _round(white_reference),
        "camera_dark_reference_brightness": _round(dark_reference),
        "dark_white_correction_usable": dark_white_usable,
        "dark_white_rejection_reason": dark_rejection,
        "white_normalization_multiplier": _round(
            1.0 / white_reference if white_reference is not None and white_reference > 1e-9 else None
        ),
        "median_app_white_normalized_camera": _round(_median(app_camera_values)),
        "median_spectrometer_window_median_intensity": _round(_median(spectrometer_windows)),
        "median_spectrometer_point_intensity_at_filter": _round(_median(old_point_values)),
        "single_band_window_model": single_band_model,
        "normalized_shape_gain_from_camera_to_spectrometer": _round(shape_gain),
        "median_abs_normalized_shape_error_after_gain": _round(_median_abs(shape_errors)),
        "spectrometer_window_half_width_nm": SPECTROMETER_HALF_WINDOW_NM,
        "source_curve_compensation": {
            "available": bool(source_curve),
            "method": source_response_compensation.get("method"),
            "source_window_median_intensity": _round(source_curve.get("source_window_median_intensity")),
            "dark_window_median_intensity": _round(source_curve.get("dark_window_median_intensity")),
            "net_source_window_intensity": _round(source_curve.get("net_source_window_intensity")),
            "relative_to_850_net_source": _round(source_curve.get("relative_to_850_net_source")),
            "compensation_multiplier_vs_850": _round(source_curve.get("compensation_multiplier_vs_850")),
            "reliability_weight": _round(source_curve.get("reliability_weight")),
            "status": source_curve.get("status"),
            "warning": source_curve.get("warning", ""),
        },
    }


def _build_multiband_ridge(training_rows: list[dict[str, Any]]) -> dict[str, Any]:
    feature_medians = _feature_medians(training_rows)
    models: dict[str, Any] = {}
    for wavelength in SPECTROMETER_TARGET_WAVELENGTHS:
        model = _loocv_ridge_for_target(training_rows, wavelength, feature_medians)
        if model is not None:
            models[str(wavelength)] = model
    return {
        "model_type": "per-target ridge regression",
        "feature_field": "app_white_normalized_camera",
        "feature_wavelengths_nm": list(FILTER_WAVELENGTHS),
        "target_wavelengths_nm": list(SPECTROMETER_TARGET_WAVELENGTHS),
        "minimum_observed_features_for_prediction": 4,
        "missing_feature_policy": "impute training median and report imputed bands",
        "feature_imputation_medians": {
            key: _round(value)
            for key, value in sorted(feature_medians.items(), key=lambda item: int(item[0]))
        },
        "target_field": "spectrometer_window_median",
        "spectrometer_window_half_width_nm": SPECTROMETER_HALF_WINDOW_NM,
        "excluded_target_wavelengths": {
            str(wavelength): reason
            for wavelength, reason in LOW_CONFIDENCE_SPECTROMETER_TARGETS.items()
        },
        "selection_policy": (
            "A ridge model is used only for target wavelengths where leave-one-leaf-out RMSE beats "
            "the training-mean baseline; other wavelengths fall back to the selected single-band model."
        ),
        "models": models,
    }


def build_profile() -> dict[str, Any]:
    camera_features = _read_csv(REAL_ANALYSIS / "camera_features.csv")
    paired = _read_csv(REAL_ANALYSIS / "camera_spectra_pairs.csv")
    validation_rows = _read_csv(VALIDATION / "camera_spectrometer_validation_pairs.csv")
    white_references, dark_reference = _reference_values(camera_features)
    training_rows = _build_training_table(paired, white_references)
    filter_labels = [str(wavelength) for wavelength in FILTER_WAVELENGTHS]
    source_response_compensation = _build_source_response_compensation()

    bands: dict[str, Any] = {}
    for label in filter_labels:
        rows = [row for row in paired if row.get("filter_label") == label]
        bands[label] = _build_band_profile(
            label,
            rows,
            validation_rows,
            training_rows,
            white_references.get(int(label)),
            dark_reference,
            source_response_compensation,
        )

    return {
        "profile_id": "spectraleaf_camera_calibration_2026_05_ridge_v2",
        "title": "Validated camera calibration from app band averages and spectrometer windows",
        "generated_from": {
            "data_root": str(DATA_ROOT),
            "camera_features_csv": str((REAL_ANALYSIS / "camera_features.csv").relative_to(ROOT)),
            "camera_spectra_pairs_csv": str((REAL_ANALYSIS / "camera_spectra_pairs.csv").relative_to(ROOT)),
            "camera_validation_pairs_csv": str(
                (VALIDATION / "camera_spectrometer_validation_pairs.csv").relative_to(ROOT)
            ),
        },
        "spectrometer": {
            "model": "Ocean Optics USB2000+XR1-ES",
            "nominal_wavelength_range_nm": [200, 1025],
            "nominal_optical_resolution_nm": "1.7-2.1",
            "note": (
                "Model information was supplied by the user and cross-checked against public specifications. "
                "Nominal range includes 940 nm, but the current calibration still marks 940 nm low-confidence "
                "because the measured dataset/setup may be unreliable at that band."
            ),
        },
        "measurement_basis": (
            "The calibration is trained on the same values produced by the app: max-channel filter "
            "JPG bands averaged over the app vegetation mask, divided by the matching white-reference "
            "brightness. Spectrometer targets are robust median intensities inside +/-10 nm windows. "
            "The measured source-minus-dark curve is also stored as a compensation/confidence curve, "
            "so weak wavelengths can be corrected without being over-trusted."
        ),
        "source_response_compensation": source_response_compensation,
        "primary_corrected_camera_field": "white_normalized_camera",
        "primary_spectrometer_estimate_field": "best_spectrometer_window_intensity",
        "filter_wavelengths_nm": list(FILTER_WAVELENGTHS),
        "spectrometer_target_wavelengths_nm": list(SPECTROMETER_TARGET_WAVELENGTHS),
        "low_confidence_spectrometer_targets": {
            str(wavelength): {
                "wavelength_nm": wavelength,
                "status": "excluded_from_spectrometer_calibration",
                "reason": reason,
                "affected_outputs": [
                    "best_spectrometer_window_intensity",
                    "from_best_spectrometer_window_intensity.NDWI_850_940",
                    "water proxy interpretation",
                ],
            }
            for wavelength, reason in LOW_CONFIDENCE_SPECTROMETER_TARGETS.items()
        },
        "model_selection": (
            "For four or more observed camera bands, validated multiband ridge regression is tried per target. "
            "If leave-one-leaf-out validation does not beat a training-mean baseline, the app falls back to "
            "the selected single-band model for that wavelength."
        ),
        "dark_reference_policy": {
            "dark_reference_available": dark_reference is not None,
            "dark_reference_brightness": _round(dark_reference),
            "status": "guarded",
            "note": (
                "Only a no-filter camera dark reference was available. The app records it, "
                "but it applies dark subtraction only if a filter passes physical validity checks."
            ),
        },
        "calibrated_wavelengths_nm": list(SPECTROMETER_TARGET_WAVELENGTHS),
        "training_samples": training_rows,
        "multiband_ridge": _build_multiband_ridge(training_rows),
        "bands": bands,
        "limitations": [
            "The correction applies to filter-named camera JPGs, not arbitrary RGB photos.",
            "The white-reference correction compensates filter and light-source strength inside the box.",
            "Dark subtraction is disabled for filters where the no-filter dark frame is brighter than the leaf data.",
            "No outside camera JPG calibration was available; outside comparison remains spectrometer-only.",
            "The regression is guarded by leave-one-leaf-out validation because the current dataset has few leaves.",
            "940 nm can be source-curve compensated, but the compensation multiplier is high because the source signal is weak there; it remains excluded from calibrated conclusions.",
        ],
    }


def main() -> None:
    OUTPUT.parent.mkdir(parents=True, exist_ok=True)
    profile = build_profile()
    OUTPUT.write_text(json.dumps(profile, indent=2, sort_keys=True), encoding="utf-8")
    print(OUTPUT)


if __name__ == "__main__":
    main()
