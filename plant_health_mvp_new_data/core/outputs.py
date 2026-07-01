"""Output helpers for the plant-health MVP.

This module persists the intermediate and final artifacts produced by the
analysis pipeline without making assumptions about the source dataset format.
"""

from __future__ import annotations

import csv
import json
from pathlib import Path
from typing import Any

import numpy as np

from .models.sample import SpectralSample
from .reports import build_analysis_report, save_analysis_report

try:  # pragma: no cover - optional dependency
    import matplotlib.pyplot as plt
except Exception:  # pragma: no cover - optional dependency
    plt = None


def ensure_output_dir(path: str | Path) -> Path:
    """Create and return the output directory."""

    output_dir = Path(path)
    output_dir.mkdir(parents=True, exist_ok=True)
    return output_dir


def _normalize_to_uint8(array: np.ndarray) -> np.ndarray:
    """Normalize an array to uint8 for PNG output."""

    values = np.asarray(array, dtype=float)
    if values.size == 0:
        return np.zeros(values.shape, dtype=np.uint8)

    finite_values = values[np.isfinite(values)]
    if finite_values.size == 0:
        return np.zeros(values.shape, dtype=np.uint8)

    min_value = float(np.min(finite_values))
    max_value = float(np.max(finite_values))
    if np.isclose(max_value, min_value):
        return np.zeros(values.shape, dtype=np.uint8)

    scaled = (values - min_value) / (max_value - min_value)
    scaled = np.clip(scaled, 0.0, 1.0)
    return (scaled * 255.0).astype(np.uint8)


def _save_png(array: np.ndarray, path: Path) -> None:
    """Save a 2D array as a grayscale PNG."""

    normalized = _normalize_to_uint8(array)
    try:
        from PIL import Image
    except Exception:  # pragma: no cover - optional dependency
        if plt is None:
            raise RuntimeError("Pillow or matplotlib is required to save PNG outputs.")
        plt.imsave(path, normalized, cmap="gray", vmin=0, vmax=255)
        return

    Image.fromarray(normalized, mode="L").save(path)


def save_band_images(sample: SpectralSample, output_dir: str | Path) -> dict[str, str]:
    """Save 2D target bands as PNG images.

    Only bands that look like 2D images are written to disk. Non-image data is
    skipped quietly so the caller can use the same function for table-like
    samples later.
    """

    output_root = ensure_output_dir(output_dir)
    bands_dir = ensure_output_dir(output_root / "bands")
    saved: dict[str, str] = {}

    for band_key, band_data in sample.target_bands.items():
        if band_data is None:
            continue

        band_array = np.asarray(band_data)
        if band_array.ndim != 2:
            continue

        band_path = bands_dir / f"band_{band_key}.png"
        _save_png(band_array, band_path)
        saved[str(band_key)] = str(band_path)

    return saved


def save_mask_image(mask: np.ndarray | None, output_dir: str | Path) -> str | None:
    """Save a vegetation mask as a PNG image when possible."""

    if mask is None:
        return None

    mask_array = np.asarray(mask)
    if mask_array.ndim != 2 or mask_array.size == 0:
        return None

    output_root = ensure_output_dir(output_dir)
    mask_path = output_root / "vegetation_mask.png"
    _save_png(mask_array.astype(float), mask_path)
    return str(mask_path)


def _band_to_float_key(key: str) -> tuple[float, str]:
    """Parse a band key into a numeric sort key."""

    try:
        return float(key), key
    except ValueError:
        return float("inf"), key


def save_spectrum_plot(average_spectrum: dict[str, float | None], output_dir: str | Path) -> str | None:
    """Save a simple plot of the average spectrum if matplotlib is available."""

    if plt is None:
        return None

    points = []
    for band_key, value in average_spectrum.items():
        if value is None:
            continue
        wavelength, _ = _band_to_float_key(str(band_key))
        if not np.isfinite(wavelength):
            continue
        points.append((wavelength, float(value)))

    if not points:
        return None

    points.sort(key=lambda item: item[0])
    wavelengths = [item[0] for item in points]
    values = [item[1] for item in points]

    output_root = ensure_output_dir(output_dir)
    plot_path = output_root / "average_spectrum.png"

    figure, axis = plt.subplots(figsize=(6, 4))
    axis.plot(wavelengths, values, marker="o", linewidth=1.5)
    axis.set_xlabel("Wavelength (nm)")
    axis.set_ylabel("Average reflectance")
    axis.set_title("Average vegetation spectrum")
    axis.grid(True, alpha=0.3)
    figure.tight_layout()
    figure.savefig(plot_path, dpi=150)
    plt.close(figure)
    return str(plot_path)


def _mapping_to_json(sample: SpectralSample) -> dict[str, Any]:
    """Return a JSON-friendly mapping summary."""

    mapping: dict[str, Any] = {}
    for key, band_mapping in sample.band_mappings.items():
        mapping[str(key)] = band_mapping.to_dict()
    return mapping


def _save_camera_calibration_csv(report: dict[str, Any], output_root: Path) -> Path | None:
    """Save calibrated camera band values when the report contains them."""

    calibration = report.get("camera_calibration", {})
    if not isinstance(calibration, dict) or not calibration.get("calibration_applied"):
        return None
    corrected = calibration.get("corrected_bands", {})
    if not isinstance(corrected, dict) or not corrected:
        return None

    csv_path = output_root / "camera_calibration.csv"
    columns = [
        "wavelength_nm",
        "raw_camera_value",
        "white_reference_brightness",
        "white_normalized_camera",
        "source_curve_compensated_camera",
        "source_curve_compensation_multiplier_vs_850",
        "source_curve_reliability_weight",
        "source_curve_relative_to_850",
        "source_curve_status",
        "spectrometer_target_reliability",
        "spectrometer_target_reliability_reason",
        "dark_reference_brightness",
        "dark_white_reflectance_proxy",
        "dark_white_correction_used",
        "spectrometer_equivalent_raw_intensity_at_filter",
        "spectrometer_equivalent_window_intensity",
        "single_band_spectrometer_window_intensity",
        "single_band_model_used",
        "single_band_leave_one_leaf_out_rmse",
        "best_spectrometer_window_intensity",
        "best_spectrometer_model",
        "spectrometer_equivalent_reflectance_at_filter",
        "normalized_spectrometer_shape_estimate",
        "median_abs_raw_intensity_error_after_factor",
        "median_relative_raw_intensity_error_after_factor",
        "dark_white_status",
    ]
    with csv_path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=columns)
        writer.writeheader()
        for _, values in sorted(corrected.items(), key=lambda item: float(item[0])):
            if not isinstance(values, dict):
                continue
            writer.writerow({column: _format_csv_value(values.get(column)) for column in columns})
    return csv_path


def save_report(
    sample: SpectralSample,
    output_dir: str | Path,
    average_spectrum: dict[str, float | None],
    spectrum_metadata: dict[str, Any],
    extra_metadata: dict[str, Any] | None = None,
    indices_report: dict[str, Any] | None = None,
    spot_report: dict[str, Any] | None = None,
) -> Path:
    """Save a structured JSON report for the current sample."""

    output_root = ensure_output_dir(output_dir)
    report_path = output_root / "mapping_report.json"
    report = build_analysis_report(
        sample,
        average_spectrum,
        spectrum_metadata,
        indices_report=indices_report,
        spot_report=spot_report,
        extra_metadata={
            **(extra_metadata or {}),
            "spectrum_metadata": spectrum_metadata,
        },
    )
    _save_camera_calibration_csv(report, output_root)
    return save_analysis_report(report, report_path)


def _format_csv_value(value: Any) -> Any:
    """Return a simple spreadsheet-friendly value."""

    if isinstance(value, dict):
        return json.dumps(value, sort_keys=True)
    if isinstance(value, (list, tuple)):
        return json.dumps(value)
    return "" if value is None else value


def save_summary_csv(
    sample: SpectralSample,
    output_dir: str | Path,
    spectrum_metadata: dict[str, Any],
) -> Path:
    """Save source and run metadata as a compact two-column CSV."""

    output_root = ensure_output_dir(output_dir)
    csv_path = output_root / "summary_report.csv"
    mock_flag = bool(sample.metadata.get("mock_flag"))
    source_data_kind = sample.metadata.get(
        "source_data_kind",
        "mock_synthetic_data" if mock_flag else "real_sample_data",
    )
    dimensions = sample.metadata.get("dimensions", {})

    rows = [
        ("source_type", sample.source_type),
        ("source_data_kind", source_data_kind),
        ("analysis_data_kind", sample.metadata.get("analysis_data_kind", "")),
        ("adapter_used", sample.metadata.get("adapter_used", "")),
        ("calibration_applied", sample.metadata.get("calibration_applied", "")),
        ("used_real_sample_data", not mock_flag),
        ("used_mock_synthetic_data", mock_flag),
        ("sample_id", sample.metadata.get("sample_id", sample.metadata.get("archive_member_sample", ""))),
        ("input_path", sample.metadata.get("input_path", "")),
        ("imported_files", sample.metadata.get("imported_files", "")),
        ("assigned_roles", sample.metadata.get("roles", "")),
        ("alignment_status", sample.metadata.get("alignment_status", "")),
        ("cube_shape", dimensions.get("shape", "")),
        ("height", dimensions.get("height", "")),
        ("width", dimensions.get("width", "")),
        ("bands", dimensions.get("bands", "")),
        ("vegetation_pixel_count", int(spectrum_metadata.get("vegetation_pixel_count", 0))),
        ("mask_method", sample.metadata.get("vegetation_mask", {}).get("method", "")),
        ("suspicious_region_count", sample.metadata.get("spot_detection", {}).get("spot_count", "")),
        ("sensor_type", sample.metadata.get("sensor_type", "")),
    ]

    with csv_path.open("w", newline="", encoding="utf-8") as csv_file:
        writer = csv.writer(csv_file)
        writer.writerow(["field", "value"])
        for field, value in rows:
            writer.writerow([field, _format_csv_value(value)])

    return csv_path


def save_average_bands_csv(
    output_dir: str | Path,
    average_spectrum: dict[str, float | None],
) -> Path:
    """Save average vegetation values as one row per target band."""

    output_root = ensure_output_dir(output_dir)
    csv_path = output_root / "average_bands.csv"
    with csv_path.open("w", newline="", encoding="utf-8") as csv_file:
        writer = csv.writer(csv_file)
        writer.writerow(["target_band_nm", "average_vegetation_value"])
        for band_key in sorted(average_spectrum, key=lambda key: float(key)):
            writer.writerow([band_key, "" if average_spectrum[band_key] is None else average_spectrum[band_key]])
    return csv_path


def save_mapping_csv(
    sample: SpectralSample,
    output_dir: str | Path,
    average_spectrum: dict[str, float | None],
) -> Path:
    """Save target band mapping as a single flat CSV table."""

    output_root = ensure_output_dir(output_dir)
    csv_path = output_root / "band_mapping.csv"

    with csv_path.open("w", newline="", encoding="utf-8") as csv_file:
        writer = csv.writer(csv_file)
        writer.writerow(
            [
                "target_band_nm",
                "source_band_index",
                "source_wavelength_nm",
                "status",
                "distance_nm",
                "average_vegetation_value",
                "note",
            ]
        )
        for band_key, band_mapping in sorted(sample.band_mappings.items(), key=lambda item: float(item[0])):
            writer.writerow(
                [
                    band_key,
                    "" if not band_mapping.source_indices else band_mapping.source_indices[0],
                    "" if not band_mapping.source_wavelengths else band_mapping.source_wavelengths[0],
                    band_mapping.status,
                    "" if band_mapping.distance_nm is None else band_mapping.distance_nm,
                    "" if average_spectrum.get(str(band_key)) is None else average_spectrum.get(str(band_key)),
                    band_mapping.note,
                ]
            )

    return csv_path


def save_spot_outputs(spot_result: dict[str, Any] | None, output_dir: str | Path) -> dict[str, str | None]:
    """Save suspicious spot masks, score maps, and per-spot measurements."""

    if not spot_result:
        return {
            "spot_score_image": None,
            "suspicious_spot_mask_image": None,
            "spot_labels_image": None,
            "spots_csv": None,
        }

    output_root = ensure_output_dir(output_dir)
    paths: dict[str, str | None] = {
        "spot_score_image": None,
        "suspicious_spot_mask_image": None,
        "spot_labels_image": None,
        "spots_csv": None,
    }

    score = spot_result.get("score_map")
    if isinstance(score, np.ndarray):
        score_path = output_root / "spot_score.png"
        _save_png(score, score_path)
        paths["spot_score_image"] = str(score_path)

    suspicious_mask = spot_result.get("suspicious_mask")
    if isinstance(suspicious_mask, np.ndarray):
        mask_path = output_root / "suspicious_spot_mask.png"
        _save_png(suspicious_mask.astype(float), mask_path)
        paths["suspicious_spot_mask_image"] = str(mask_path)

    labels = spot_result.get("labels")
    if isinstance(labels, np.ndarray):
        labels_path = output_root / "spot_labels.png"
        _save_png(labels.astype(float), labels_path)
        paths["spot_labels_image"] = str(labels_path)

    spots_csv_path = output_root / "spots.csv"
    with spots_csv_path.open("w", newline="", encoding="utf-8") as csv_file:
        writer = csv.writer(csv_file)
        writer.writerow(
            [
                "label",
                "area_px",
                "bbox_x_min",
                "bbox_y_min",
                "bbox_x_max",
                "bbox_y_max",
                "centroid_x",
                "centroid_y",
                "severity_rank",
                "severity_score",
                "mean_suspiciousness_score",
                "max_suspiciousness_score",
                "mean_band_532",
                "mean_band_556",
                "mean_band_650",
                "mean_band_680",
                "mean_band_725",
                "mean_band_850",
                "mean_band_940",
                "delta_leaf_band_680",
                "delta_leaf_band_850",
                "delta_nearby_band_680",
                "delta_nearby_band_850",
                "ndvi",
                "ndre",
                "gndvi",
                "ndwi_850_940",
            ]
        )
        for spot in spot_result.get("spots", []):
            bbox = spot.get("bbox", ["", "", "", ""])
            centroid = spot.get("centroid", ["", ""])
            bands = spot.get("mean_reflectance", {})
            leaf_deltas = spot.get("delta_from_leaf_average", {})
            nearby_deltas = spot.get("delta_from_nearby_background", {})
            indices = spot.get("mean_indices", {})
            writer.writerow(
                [
                    spot.get("label", ""),
                    spot.get("area_px", ""),
                    bbox[0],
                    bbox[1],
                    bbox[2],
                    bbox[3],
                    centroid[0],
                    centroid[1],
                    spot.get("severity_rank", ""),
                    spot.get("severity_score", ""),
                    spot.get("mean_suspiciousness_score", ""),
                    spot.get("max_suspiciousness_score", ""),
                    bands.get("band_532", ""),
                    bands.get("band_556", ""),
                    bands.get("band_650", ""),
                    bands.get("band_680", ""),
                    bands.get("band_725", ""),
                    bands.get("band_850", ""),
                    bands.get("band_940", ""),
                    leaf_deltas.get("band_680", ""),
                    leaf_deltas.get("band_850", ""),
                    nearby_deltas.get("band_680", ""),
                    nearby_deltas.get("band_850", ""),
                    indices.get("NDVI", ""),
                    indices.get("NDRE", ""),
                    indices.get("GNDVI", ""),
                    indices.get("NDWI_850_940", ""),
                ]
            )
    paths["spots_csv"] = str(spots_csv_path)
    return paths


def write_outputs(
    sample: SpectralSample,
    output_dir: str | Path,
    average_spectrum: dict[str, float | None],
    spectrum_metadata: dict[str, Any],
) -> dict[str, Any]:
    """Persist the standard MVP outputs and return their paths."""

    output_root = ensure_output_dir(output_dir)
    band_images = save_band_images(sample, output_root)
    mask_image = save_mask_image(sample.mask, output_root)
    spectrum_plot = save_spectrum_plot(average_spectrum, output_root)
    report_path = save_report(sample, output_root, average_spectrum, spectrum_metadata)
    summary_csv_path = save_summary_csv(sample, output_root, spectrum_metadata)
    average_bands_csv_path = save_average_bands_csv(output_root, average_spectrum)
    mapping_csv_path = save_mapping_csv(sample, output_root, average_spectrum)

    return {
        "output_dir": str(output_root),
        "band_images": band_images,
        "mask_image": mask_image,
        "spectrum_plot": spectrum_plot,
        "report_path": str(report_path),
        "summary_csv_path": str(summary_csv_path),
        "average_bands_csv_path": str(average_bands_csv_path),
        "mapping_csv_path": str(mapping_csv_path),
    }
