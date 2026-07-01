"""Full-spectrum validation analysis for camera vs spectrometer measurements."""

from __future__ import annotations

import csv
import json
import math
from dataclasses import dataclass
from pathlib import Path

import matplotlib.pyplot as plt
import numpy as np
from scipy.signal import savgol_filter
from scipy.spatial.distance import pdist, squareform
from scipy.stats import pearsonr, spearmanr
from sklearn.decomposition import PCA
from sklearn.metrics import confusion_matrix

from run_real_leaf_analysis import (
    OUT_DIR as REAL_OUT_DIR,
    TARGET_WAVELENGTHS,
    Spectrum,
    build_reference_index,
    calibrated_reflectance,
    load_all_camera_measurements,
    load_all_spectra,
    write_csv,
)


VALIDATION_DIR = Path(r"C:\Users\david\OneDrive\Desktop\Archive\Projects\CodeX\outputs\camera_validation_report")
GRAPH_DIR = VALIDATION_DIR / "graphs"


@dataclass
class ProcessedSpectrum:
    spectrum: Spectrum
    raw_smooth: np.ndarray
    dark_corrected_smooth: np.ndarray
    normalized_curve: np.ndarray
    reflectance_smooth: np.ndarray | None
    full_area: float
    full_mean: float
    full_peak: float
    full_centroid: float
    reflectance_area: float | None
    reflectance_mean: float | None


def main() -> None:
    VALIDATION_DIR.mkdir(parents=True, exist_ok=True)
    GRAPH_DIR.mkdir(parents=True, exist_ok=True)
    for old_graph in GRAPH_DIR.glob("*.png"):
        old_graph.unlink()

    spectra = load_all_spectra()
    cameras = load_all_camera_measurements()
    references = build_reference_index(spectra)
    processed = {s.relative_path: process_spectrum(s, references) for s in spectra}

    full_rows = build_full_spectrum_rows(processed)
    paired_rows = build_validation_pairs(processed, cameras)
    sample_corr_rows = build_sample_correlations(paired_rows)
    classifier_rows, classifier_summary = run_full_spectrum_classifier(processed)
    pca_rows, pca_summary = run_pca(processed)
    graph_rows = make_all_graphs(processed, cameras, paired_rows, sample_corr_rows, classifier_summary, pca_rows)
    summary = build_summary(paired_rows, sample_corr_rows, classifier_summary, pca_summary)

    write_csv(VALIDATION_DIR / "full_spectrum_features.csv", full_rows)
    write_csv(VALIDATION_DIR / "camera_spectrometer_validation_pairs.csv", paired_rows)
    write_csv(VALIDATION_DIR / "per_sample_camera_spectrum_correlations.csv", sample_corr_rows)
    write_csv(VALIDATION_DIR / "full_spectrum_classifier_results.csv", classifier_rows)
    write_csv(VALIDATION_DIR / "full_spectrum_pca_scores.csv", pca_rows)
    write_csv(VALIDATION_DIR / "graph_manifest.csv", graph_rows)
    (VALIDATION_DIR / "validation_summary.json").write_text(json.dumps(summary, indent=2), encoding="utf-8")
    print(VALIDATION_DIR)


def process_spectrum(spectrum: Spectrum, references: dict[tuple[str, str, str], Spectrum]) -> ProcessedSpectrum:
    raw_smooth = smooth_curve(spectrum.intensities)
    dark = choose_dark_reference(spectrum, references)
    if dark is not None and np.array_equal(dark.wavelengths, spectrum.wavelengths):
        dark_corrected = spectrum.intensities - dark.intensities
    else:
        dark_corrected = spectrum.intensities.copy()
    dark_corrected_smooth = smooth_curve(dark_corrected)
    positive = positive_signal(dark_corrected_smooth)
    normalized_curve = normalize_curve(dark_corrected_smooth)
    reflectance, status = calibrated_reflectance(spectrum, references)
    reflectance_smooth = smooth_curve(reflectance) if reflectance is not None and status == "ok" else None

    wavelengths = spectrum.wavelengths
    full_area = float(np.trapz(positive, wavelengths))
    full_mean = float(np.nanmean(positive))
    peak_idx = int(np.nanargmax(positive))
    full_peak = float(positive[peak_idx])
    full_centroid = spectral_centroid(wavelengths, positive)
    if reflectance_smooth is not None:
        reflectance_positive = positive_signal(reflectance_smooth)
        reflectance_area = float(np.trapz(reflectance_positive, wavelengths))
        reflectance_mean = float(np.nanmean(reflectance_positive))
    else:
        reflectance_area = None
        reflectance_mean = None

    return ProcessedSpectrum(
        spectrum=spectrum,
        raw_smooth=raw_smooth,
        dark_corrected_smooth=dark_corrected_smooth,
        normalized_curve=normalized_curve,
        reflectance_smooth=reflectance_smooth,
        full_area=full_area,
        full_mean=full_mean,
        full_peak=full_peak,
        full_centroid=full_centroid,
        reflectance_area=reflectance_area,
        reflectance_mean=reflectance_mean,
    )


def choose_dark_reference(spectrum: Spectrum, references: dict[tuple[str, str, str], Spectrum]) -> Spectrum | None:
    for key in (
        (spectrum.environment, "dark_reference", spectrum.filter_label or "none"),
        (spectrum.environment, "dark_reference", "none"),
        (spectrum.environment, "dark_reference", "any"),
    ):
        if key in references:
            return references[key]
    return None


def smooth_curve(values: np.ndarray) -> np.ndarray:
    arr = np.asarray(values, dtype=float)
    window = 31 if arr.size >= 31 else max(5, arr.size // 2 * 2 - 1)
    if window % 2 == 0:
        window += 1
    if window < 5:
        return arr.copy()
    return savgol_filter(arr, window_length=window, polyorder=3, mode="interp")


def positive_signal(values: np.ndarray) -> np.ndarray:
    arr = np.asarray(values, dtype=float)
    finite = arr[np.isfinite(arr)]
    if finite.size == 0:
        return np.zeros_like(arr)
    shifted = arr - min(float(np.nanpercentile(finite, 1)), 0.0)
    shifted[~np.isfinite(shifted)] = 0.0
    return np.clip(shifted, 0.0, None)


def normalize_curve(values: np.ndarray) -> np.ndarray:
    arr = np.asarray(values, dtype=float)
    finite = arr[np.isfinite(arr)]
    if finite.size == 0:
        return np.zeros_like(arr)
    centered = arr - float(np.nanmean(finite))
    std = float(np.nanstd(centered))
    if std < 1e-12:
        return np.zeros_like(arr)
    norm = centered / std
    norm[~np.isfinite(norm)] = 0.0
    return norm


def spectral_centroid(wavelengths: np.ndarray, signal: np.ndarray) -> float:
    total = float(np.nansum(signal))
    if total <= 1e-12:
        return float("nan")
    return float(np.nansum(wavelengths * signal) / total)


def build_full_spectrum_rows(processed: dict[str, ProcessedSpectrum]) -> list[dict[str, object]]:
    rows: list[dict[str, object]] = []
    for item in processed.values():
        s = item.spectrum
        rows.append(
            {
                "relative_path": s.relative_path,
                "environment": s.environment,
                "sample_id": s.sample_id,
                "condition": s.condition,
                "role": s.role,
                "filter_label": s.filter_label,
                "filter_nm": s.filter_nm if s.filter_nm is not None else "",
                "points_used": int(s.wavelengths.size),
                "wavelength_min_used": round_float(np.nanmin(s.wavelengths)),
                "wavelength_max_used": round_float(np.nanmax(s.wavelengths)),
                "full_spectrum_area": round_float(item.full_area),
                "full_spectrum_mean": round_float(item.full_mean),
                "full_spectrum_peak": round_float(item.full_peak),
                "spectral_centroid_nm": round_float(item.full_centroid),
                "reflectance_area": round_float(item.reflectance_area) if item.reflectance_area is not None else "",
                "reflectance_mean": round_float(item.reflectance_mean) if item.reflectance_mean is not None else "",
            }
        )
    return rows


def build_validation_pairs(
    processed: dict[str, ProcessedSpectrum],
    cameras,
) -> list[dict[str, object]]:
    camera_index = {
        (cam.sample_id, cam.filter_label): cam
        for cam in cameras
        if cam.filter_label not in {"", "none"} and cam.condition not in {"white_reference", "dark_reference", "source_light"}
    }
    camera_white = {
        (cam.environment, cam.filter_label): float(cam.metrics["brightness"])
        for cam in cameras
        if cam.condition == "white_reference" and cam.filter_label not in {"", "none"}
    }
    camera_dark = {
        cam.environment: float(cam.metrics["brightness"])
        for cam in cameras
        if cam.condition == "dark_reference"
    }
    rows: list[dict[str, object]] = []
    for item in processed.values():
        s = item.spectrum
        if s.role != "sample" or s.filter_label in {"", "none"}:
            continue
        cam = camera_index.get((s.sample_id, s.filter_label))
        if cam is None:
            continue
        white_brightness = camera_white.get((s.environment, s.filter_label))
        dark_brightness = camera_dark.get(s.environment)
        camera_reflectance_proxy = ""
        if white_brightness is not None:
            if dark_brightness is None:
                dark_brightness = 0.0
            denom = white_brightness - dark_brightness
            if abs(denom) > 1e-9:
                camera_reflectance_proxy = round_float((float(cam.metrics["brightness"]) - dark_brightness) / denom)
        rows.append(
            {
                "environment": s.environment,
                "sample_id": s.sample_id,
                "condition": s.condition,
                "filter_label": s.filter_label,
                "filter_nm": s.filter_nm if s.filter_nm is not None else "",
                "camera_file": cam.path.name,
                "spectrum_file": s.path.name,
                "camera_brightness": cam.metrics["brightness"],
                "camera_white_brightness": round_float(white_brightness) if white_brightness is not None else "",
                "camera_dark_brightness": round_float(dark_brightness) if dark_brightness is not None else "",
                "camera_reflectance_proxy": camera_reflectance_proxy,
                "camera_saturation": cam.metrics["saturation"],
                "camera_gcc": cam.metrics["gcc"],
                "camera_exg": cam.metrics["exg"],
                "camera_vari": cam.metrics["vari"],
                "spectrometer_full_area": round_float(item.full_area),
                "spectrometer_full_mean": round_float(item.full_mean),
                "spectrometer_full_peak": round_float(item.full_peak),
                "spectral_centroid_nm": round_float(item.full_centroid),
                "reflectance_area": round_float(item.reflectance_area) if item.reflectance_area is not None else "",
                "reflectance_mean": round_float(item.reflectance_mean) if item.reflectance_mean is not None else "",
            }
        )
    add_within_sample_normalized_columns(rows)
    return rows


def add_within_sample_normalized_columns(rows: list[dict[str, object]]) -> None:
    for sample_id in sorted({str(row["sample_id"]) for row in rows}):
        subset = [row for row in rows if row["sample_id"] == sample_id]
        for source, target in (
            ("camera_brightness", "camera_brightness_norm_in_sample"),
            ("camera_reflectance_proxy", "camera_reflectance_proxy_norm_in_sample"),
            ("spectrometer_full_area", "spectrometer_area_norm_in_sample"),
            ("spectrometer_full_peak", "spectrometer_peak_norm_in_sample"),
        ):
            valid_subset = [row for row in subset if row.get(source) not in {"", None}]
            if not valid_subset:
                for row in subset:
                    row[target] = ""
                continue
            values = np.asarray([float(row[source]) for row in valid_subset], dtype=float)
            vmin, vmax = float(np.nanmin(values)), float(np.nanmax(values))
            for row in subset:
                if row.get(source) in {"", None}:
                    row[target] = ""
                else:
                    row[target] = round_float((float(row[source]) - vmin) / (vmax - vmin)) if vmax > vmin else 0.0


def build_sample_correlations(rows: list[dict[str, object]]) -> list[dict[str, object]]:
    output: list[dict[str, object]] = []
    for sample_id in sorted({str(row["sample_id"]) for row in rows}):
        subset = [row for row in rows if row["sample_id"] == sample_id]
        if len(subset) < 3:
            continue
        subset.sort(key=lambda row: float(row["filter_nm"]))
        cam = np.asarray([float(row["camera_brightness"]) for row in subset], dtype=float)
        area = np.asarray([float(row["spectrometer_full_area"]) for row in subset], dtype=float)
        cam_norm = np.asarray([float(row["camera_brightness_norm_in_sample"]) for row in subset], dtype=float)
        area_norm = np.asarray([float(row["spectrometer_area_norm_in_sample"]) for row in subset], dtype=float)
        proxy_pairs = [row for row in subset if row.get("camera_reflectance_proxy_norm_in_sample") not in {"", None}]
        proxy_norm = np.asarray([float(row["camera_reflectance_proxy_norm_in_sample"]) for row in proxy_pairs], dtype=float)
        proxy_area_norm = np.asarray([float(row["spectrometer_area_norm_in_sample"]) for row in proxy_pairs], dtype=float)
        pear_raw = safe_corr(cam, area, method="pearson")
        spear_raw = safe_corr(cam, area, method="spearman")
        pear_norm = safe_corr(cam_norm, area_norm, method="pearson")
        pear_proxy_norm = safe_corr(proxy_norm, proxy_area_norm, method="pearson") if len(proxy_pairs) >= 3 else (float("nan"), float("nan"))
        output.append(
            {
                "sample_id": sample_id,
                "condition": subset[0]["condition"],
                "environment": subset[0]["environment"],
                "paired_filters": len(subset),
                "pearson_camera_vs_full_area": round_float(pear_raw[0]),
                "pearson_p_value": round_float(pear_raw[1]),
                "spearman_camera_vs_full_area": round_float(spear_raw[0]),
                "spearman_p_value": round_float(spear_raw[1]),
                "pearson_normalized_fingerprints": round_float(pear_norm[0]),
                "normalized_r_squared": round_float(pear_norm[0] ** 2) if np.isfinite(pear_norm[0]) else "",
                "pearson_camera_reflectance_proxy_norm": round_float(pear_proxy_norm[0]),
                "camera_reflectance_proxy_r_squared": round_float(pear_proxy_norm[0] ** 2) if np.isfinite(pear_proxy_norm[0]) else "",
            }
        )
    return output


def safe_corr(x: np.ndarray, y: np.ndarray, method: str) -> tuple[float, float]:
    valid = np.isfinite(x) & np.isfinite(y)
    if int(np.count_nonzero(valid)) < 3 or np.nanstd(x[valid]) < 1e-12 or np.nanstd(y[valid]) < 1e-12:
        return float("nan"), float("nan")
    if method == "spearman":
        result = spearmanr(x[valid], y[valid])
    else:
        result = pearsonr(x[valid], y[valid])
    return float(result.statistic), float(result.pvalue)


def run_full_spectrum_classifier(
    processed: dict[str, ProcessedSpectrum],
) -> tuple[list[dict[str, object]], dict[str, object]]:
    samples = [
        item
        for item in processed.values()
        if item.spectrum.role == "sample"
        and item.spectrum.condition in {"healthy", "unhealthy"}
        and item.spectrum.filter_label not in {"", "none"}
    ]
    rows: list[dict[str, object]] = []
    y_true: list[str] = []
    y_pred: list[str] = []
    for idx, item in enumerate(samples):
        train = [other for j, other in enumerate(samples) if j != idx]
        centroids: dict[str, np.ndarray] = {}
        for condition in ("healthy", "unhealthy"):
            curves = [other.normalized_curve for other in train if other.spectrum.condition == condition]
            if curves:
                centroids[condition] = np.nanmean(np.vstack(curves), axis=0)
        distances = {
            condition: float(np.linalg.norm(item.normalized_curve - centroid))
            for condition, centroid in centroids.items()
        }
        prediction = min(distances, key=distances.get) if distances else "unknown"
        y_true.append(item.spectrum.condition)
        y_pred.append(prediction)
        rows.append(
            {
                "relative_path": item.spectrum.relative_path,
                "condition": item.spectrum.condition,
                "predicted_condition": prediction,
                "correct": item.spectrum.condition == prediction,
                "distance_to_healthy_centroid": round_float(distances.get("healthy")),
                "distance_to_unhealthy_centroid": round_float(distances.get("unhealthy")),
            }
        )
    accuracy = sum(t == p for t, p in zip(y_true, y_pred)) / len(y_true) if y_true else float("nan")
    labels = ["healthy", "unhealthy"]
    matrix = confusion_matrix(y_true, y_pred, labels=labels).tolist() if y_true else [[0, 0], [0, 0]]
    return rows, {"accuracy": accuracy, "labels": labels, "confusion_matrix": matrix, "n": len(y_true)}


def run_pca(processed: dict[str, ProcessedSpectrum]) -> tuple[list[dict[str, object]], dict[str, object]]:
    samples = [
        item
        for item in processed.values()
        if item.spectrum.role == "sample" and item.spectrum.filter_label not in {"", "none"}
    ]
    x = np.vstack([item.normalized_curve for item in samples])
    pca = PCA(n_components=2, random_state=0)
    scores = pca.fit_transform(x)
    rows = []
    for item, score in zip(samples, scores):
        rows.append(
            {
                "relative_path": item.spectrum.relative_path,
                "environment": item.spectrum.environment,
                "sample_id": item.spectrum.sample_id,
                "condition": item.spectrum.condition,
                "filter_label": item.spectrum.filter_label,
                "pc1": round_float(score[0]),
                "pc2": round_float(score[1]),
            }
        )
    summary = {
        "pc1_explained_variance": float(pca.explained_variance_ratio_[0]),
        "pc2_explained_variance": float(pca.explained_variance_ratio_[1]),
    }
    return rows, summary


def make_all_graphs(
    processed: dict[str, ProcessedSpectrum],
    cameras,
    paired_rows: list[dict[str, object]],
    sample_corr_rows: list[dict[str, object]],
    classifier_summary: dict[str, object],
    pca_rows: list[dict[str, object]],
) -> list[dict[str, object]]:
    graph_specs = [
        ("01_full_spectrum_raw_all.png", "Raw full spectra, all samples", plot_raw_full_spectra),
        ("02_full_spectrum_normalized_by_condition.png", "Smoothed normalized full spectra by condition", plot_normalized_by_condition),
        ("03_condition_mean_full_spectrum.png", "Condition mean full-spectrum curves", plot_condition_means),
        ("04_healthy_minus_unhealthy_difference.png", "Healthy minus unhealthy full-spectrum difference", plot_condition_difference),
        ("05_full_spectrum_pca.png", "Full-spectrum PCA score plot", lambda p: plot_pca(pca_rows, p)),
        ("06_camera_vs_spectrometer_full_area.png", "Camera brightness vs full-spectrum area", lambda p: plot_scatter(paired_rows, "camera_brightness", "spectrometer_full_area", p)),
        ("07_camera_vs_spectrometer_normalized.png", "Within-sample normalized camera vs spectrometer response", lambda p: plot_scatter(paired_rows, "camera_brightness_norm_in_sample", "spectrometer_area_norm_in_sample", p)),
        ("08_camera_reflectance_proxy_vs_spectrometer.png", "White-referenced camera proxy vs spectrometer response", lambda p: plot_scatter(filter_rows_with_key(paired_rows, "camera_reflectance_proxy_norm_in_sample"), "camera_reflectance_proxy_norm_in_sample", "spectrometer_area_norm_in_sample", p)),
        ("09_per_sample_correlation_bars.png", "Per-sample camera/spectrometer fingerprint correlations", lambda p: plot_correlation_bars(sample_corr_rows, p)),
        ("10_fingerprint_overlays_by_sample.png", "Camera and spectrometer response fingerprints by sample", lambda p: plot_fingerprint_overlays(paired_rows, p)),
        ("11_camera_feature_heatmap.png", "Camera feature heatmap", lambda p: plot_camera_heatmap(paired_rows, p)),
        ("12_spectrometer_feature_heatmap.png", "Spectrometer feature heatmap", lambda p: plot_spectrometer_heatmap(paired_rows, p)),
        ("13_reference_spectra.png", "White/dark/source reference spectra", plot_reference_spectra),
        ("14_peak_and_centroid_by_filter.png", "Peak and centroid by filter", lambda p: plot_peak_centroid(processed, p)),
        ("15_classifier_confusion_matrix.png", "Full-spectrum nearest-centroid classifier confusion matrix", lambda p: plot_confusion(classifier_summary, p)),
        ("16_condition_camera_separation.png", "Camera feature separation by condition", lambda p: plot_camera_condition_box(paired_rows, p)),
        ("17_spectrum_area_by_condition_filter.png", "Full-spectrum area by condition and filter", lambda p: plot_area_by_condition_filter(paired_rows, p)),
        ("18_full_spectrum_similarity_heatmap.png", "Full-spectrum similarity heatmap", lambda p: plot_similarity_heatmap(processed, p)),
        ("19_camera_contact_sheet.png", "Camera contact sheet", lambda p: copy_contact_sheet(p)),
    ]
    rows = []
    for filename, title, fn in graph_specs:
        output = GRAPH_DIR / filename
        fn(output)
        rows.append({"file": filename, "title": title, "path": str(output)})
    return rows


def sample_items(processed: dict[str, ProcessedSpectrum]) -> list[ProcessedSpectrum]:
    return [
        item
        for item in processed.values()
        if item.spectrum.role == "sample" and item.spectrum.filter_label not in {"", "none"}
    ]


def plot_raw_full_spectra(output: Path) -> None:
    processed = current_processed()
    fig, axes = plt.subplots(1, 2, figsize=(14, 5.5), sharex=True)
    colors = condition_colors()
    for ax, environment in zip(axes, ["afara", "in cutie"]):
        for item in sample_items(processed):
            if item.spectrum.environment != environment:
                continue
            ax.plot(item.spectrum.wavelengths, item.raw_smooth, color=colors.get(item.spectrum.condition, "#555"), alpha=0.45, linewidth=0.9)
        ax.set_title(f"{environment}: raw smoothed full spectra")
        ax.set_xlabel("Wavelength (nm)")
        ax.set_ylabel("Intensity")
        ax.grid(alpha=0.25)
    add_condition_legend(axes[1])
    savefig(fig, output)


_PROCESSED_CACHE: dict[str, ProcessedSpectrum] | None = None


def current_processed() -> dict[str, ProcessedSpectrum]:
    global _PROCESSED_CACHE
    if _PROCESSED_CACHE is None:
        spectra = load_all_spectra()
        refs = build_reference_index(spectra)
        _PROCESSED_CACHE = {s.relative_path: process_spectrum(s, refs) for s in spectra}
    return _PROCESSED_CACHE


def plot_normalized_by_condition(output: Path) -> None:
    processed = current_processed()
    fig, ax = plt.subplots(figsize=(11, 5.8))
    colors = condition_colors()
    for item in sample_items(processed):
        ax.plot(item.spectrum.wavelengths, item.normalized_curve, color=colors.get(item.spectrum.condition, "#555"), alpha=0.35, linewidth=0.8)
    ax.set_title("Full 2048-point spectra after smoothing and z-normalization")
    ax.set_xlabel("Wavelength (nm)")
    ax.set_ylabel("Normalized intensity")
    ax.grid(alpha=0.25)
    add_condition_legend(ax)
    savefig(fig, output)


def plot_condition_means(output: Path) -> None:
    processed = current_processed()
    fig, ax = plt.subplots(figsize=(11, 5.8))
    colors = condition_colors()
    for condition in sorted({item.spectrum.condition for item in sample_items(processed)}):
        curves = [item.normalized_curve for item in sample_items(processed) if item.spectrum.condition == condition]
        if not curves:
            continue
        wavelengths = sample_items(processed)[0].spectrum.wavelengths
        mean = np.nanmean(np.vstack(curves), axis=0)
        sem = np.nanstd(np.vstack(curves), axis=0) / math.sqrt(len(curves))
        ax.plot(wavelengths, mean, color=colors.get(condition, "#555"), linewidth=2.2, label=f"{condition} mean")
        ax.fill_between(wavelengths, mean - sem, mean + sem, color=colors.get(condition, "#555"), alpha=0.12)
    ax.set_title("Condition mean curves using the entire spectrum")
    ax.set_xlabel("Wavelength (nm)")
    ax.set_ylabel("Mean normalized intensity")
    ax.grid(alpha=0.25)
    ax.legend()
    savefig(fig, output)


def plot_condition_difference(output: Path) -> None:
    processed = current_processed()
    items = sample_items(processed)
    healthy = [item.normalized_curve for item in items if item.spectrum.condition == "healthy"]
    unhealthy = [item.normalized_curve for item in items if item.spectrum.condition == "unhealthy"]
    wavelengths = items[0].spectrum.wavelengths
    diff = np.nanmean(np.vstack(healthy), axis=0) - np.nanmean(np.vstack(unhealthy), axis=0)
    fig, ax = plt.subplots(figsize=(11, 5.5))
    ax.axhline(0, color="#222", linewidth=0.8)
    ax.plot(wavelengths, diff, color="#315f8c", linewidth=1.8)
    ax.fill_between(wavelengths, 0, diff, where=diff >= 0, color="#287a46", alpha=0.22, label="healthy higher")
    ax.fill_between(wavelengths, 0, diff, where=diff < 0, color="#b24835", alpha=0.22, label="unhealthy higher")
    ax.set_title("Full-spectrum difference: healthy mean minus unhealthy mean")
    ax.set_xlabel("Wavelength (nm)")
    ax.set_ylabel("Normalized difference")
    ax.grid(alpha=0.25)
    ax.legend()
    savefig(fig, output)


def plot_pca(rows: list[dict[str, object]], output: Path) -> None:
    fig, ax = plt.subplots(figsize=(8, 6))
    colors = condition_colors()
    for row in rows:
        ax.scatter(float(row["pc1"]), float(row["pc2"]), color=colors.get(str(row["condition"]), "#555"), s=58, alpha=0.82)
        ax.text(float(row["pc1"]), float(row["pc2"]), str(row["filter_label"]), fontsize=7)
    ax.set_title("PCA of complete normalized spectra")
    ax.set_xlabel("PC1")
    ax.set_ylabel("PC2")
    ax.grid(alpha=0.25)
    add_condition_legend(ax)
    savefig(fig, output)


def plot_scatter(rows: list[dict[str, object]], x_key: str, y_key: str, output: Path) -> None:
    fig, ax = plt.subplots(figsize=(7.8, 5.8))
    colors = condition_colors()
    xs = np.asarray([float(row[x_key]) for row in rows], dtype=float)
    ys = np.asarray([float(row[y_key]) for row in rows], dtype=float)
    for row in rows:
        ax.scatter(float(row[x_key]), float(row[y_key]), color=colors.get(str(row["condition"]), "#555"), s=55, alpha=0.84)
    valid = np.isfinite(xs) & np.isfinite(ys)
    if np.count_nonzero(valid) >= 3:
        coeff = np.polyfit(xs[valid], ys[valid], 1)
        xp = np.linspace(float(np.min(xs[valid])), float(np.max(xs[valid])), 100)
        yp = coeff[0] * xp + coeff[1]
        r, pval = pearsonr(xs[valid], ys[valid])
        ax.plot(xp, yp, color="#17211b", linewidth=1.5, label=f"Pearson r={r:.2f}, p={pval:.3g}")
        ax.legend()
    ax.set_title(f"{labelize(y_key)} vs {labelize(x_key)}")
    ax.set_xlabel(labelize(x_key))
    ax.set_ylabel(labelize(y_key))
    ax.grid(alpha=0.25)
    savefig(fig, output)


def plot_correlation_bars(rows: list[dict[str, object]], output: Path) -> None:
    rows = sorted(rows, key=lambda row: str(row["sample_id"]))
    fig, ax = plt.subplots(figsize=(10.5, 5.5))
    x = np.arange(len(rows))
    width = 0.38
    vals = [float(row["pearson_normalized_fingerprints"]) for row in rows]
    proxy_vals = [float(row["pearson_camera_reflectance_proxy_norm"]) if row["pearson_camera_reflectance_proxy_norm"] != "" else np.nan for row in rows]
    ax.bar(x - width / 2, vals, width=width, color="#315f8c", label="raw camera brightness")
    ax.bar(x + width / 2, proxy_vals, width=width, color="#287a46", label="white-referenced camera proxy")
    ax.axhline(0, color="#222", linewidth=0.8)
    ax.set_xticks(x)
    ax.set_xticklabels([str(row["sample_id"]).replace("in cutie/", "").replace("afara/", "") for row in rows], rotation=35, ha="right")
    ax.set_ylim(-1, 1)
    ax.set_title("Per-sample correlation: camera fingerprint vs spectrometer full-spectrum fingerprint")
    ax.set_ylabel("Pearson r after within-sample normalization")
    ax.grid(axis="y", alpha=0.25)
    ax.legend()
    savefig(fig, output)


def plot_fingerprint_overlays(rows: list[dict[str, object]], output: Path) -> None:
    sample_ids = sorted({str(row["sample_id"]) for row in rows})
    cols = 2
    fig, axes = plt.subplots(math.ceil(len(sample_ids) / cols), cols, figsize=(12, 13), sharey=True)
    axes_flat = np.asarray(axes).ravel()
    for ax, sample_id in zip(axes_flat, sample_ids):
        subset = sorted([row for row in rows if row["sample_id"] == sample_id], key=lambda row: float(row["filter_nm"]))
        xs = [float(row["filter_nm"]) for row in subset]
        cam = [float(row["camera_brightness_norm_in_sample"]) for row in subset]
        spec = [float(row["spectrometer_area_norm_in_sample"]) for row in subset]
        ax.plot(xs, cam, marker="o", label="camera brightness", color="#287a46")
        ax.plot(xs, spec, marker="s", label="spectrometer full area", color="#315f8c")
        ax.set_title(sample_id.replace("in cutie/", "").replace("afara/", ""), fontsize=10)
        ax.set_xlabel("Filter label (nm)")
        ax.grid(alpha=0.25)
    for ax in axes_flat[len(sample_ids):]:
        ax.axis("off")
    axes_flat[0].legend()
    fig.suptitle("Normalized response fingerprints: camera vs full-spectrum spectrometer", y=0.995)
    fig.tight_layout()
    fig.savefig(output, dpi=170)
    plt.close(fig)


def plot_camera_heatmap(rows: list[dict[str, object]], output: Path) -> None:
    plot_heatmap(rows, ["camera_brightness", "camera_saturation", "camera_gcc"], output, "Camera feature heatmap")


def plot_spectrometer_heatmap(rows: list[dict[str, object]], output: Path) -> None:
    plot_heatmap(rows, ["spectrometer_full_area", "spectrometer_full_peak", "spectral_centroid_nm"], output, "Spectrometer full-spectrum feature heatmap")


def plot_heatmap(rows: list[dict[str, object]], keys: list[str], output: Path, title: str) -> None:
    labels = [f"{row['sample_id'].split('/')[-1]} {row['filter_label']}" for row in rows]
    data = np.asarray([[float(row[key]) for key in keys] for row in rows], dtype=float)
    data = (data - np.nanmean(data, axis=0)) / np.maximum(np.nanstd(data, axis=0), 1e-9)
    fig, ax = plt.subplots(figsize=(8, max(5, len(rows) * 0.22)))
    im = ax.imshow(data, aspect="auto", cmap="RdYlGn")
    ax.set_yticks(np.arange(len(labels)))
    ax.set_yticklabels(labels, fontsize=6)
    ax.set_xticks(np.arange(len(keys)))
    ax.set_xticklabels([labelize(key) for key in keys], rotation=25, ha="right")
    ax.set_title(title)
    fig.colorbar(im, ax=ax, shrink=0.75, label="z-score")
    fig.tight_layout()
    fig.savefig(output, dpi=170)
    plt.close(fig)


def plot_reference_spectra(output: Path) -> None:
    processed = current_processed()
    fig, ax = plt.subplots(figsize=(11, 5.5))
    for item in processed.values():
        if item.spectrum.role in {"white_reference", "dark_reference", "source_light"}:
            ax.plot(item.spectrum.wavelengths, item.raw_smooth, linewidth=1.2, alpha=0.75, label=f"{item.spectrum.environment} {item.spectrum.role} {item.spectrum.filter_label}")
    ax.set_title("Reference and source spectra")
    ax.set_xlabel("Wavelength (nm)")
    ax.set_ylabel("Intensity")
    ax.grid(alpha=0.25)
    ax.legend(fontsize=7, ncol=2)
    savefig(fig, output)


def plot_peak_centroid(processed: dict[str, ProcessedSpectrum], output: Path) -> None:
    items = sample_items(processed)
    fig, ax = plt.subplots(figsize=(10.5, 5.5))
    x = np.arange(len(items))
    labels = [f"{item.spectrum.condition[:4]} {item.spectrum.filter_label}" for item in items]
    ax.scatter(x, [item.full_centroid for item in items], color="#315f8c", label="centroid")
    ax.scatter(x, [item.spectrum.wavelengths[np.argmax(positive_signal(item.dark_corrected_smooth))] for item in items], color="#b66b1f", label="peak wavelength")
    ax.set_xticks(x[::2])
    ax.set_xticklabels(labels[::2], rotation=70, ha="right", fontsize=7)
    ax.set_ylabel("Wavelength (nm)")
    ax.set_title("Full-spectrum centroid and peak wavelength by measurement")
    ax.grid(axis="y", alpha=0.25)
    ax.legend()
    fig.tight_layout()
    fig.savefig(output, dpi=170)
    plt.close(fig)


def plot_confusion(summary: dict[str, object], output: Path) -> None:
    matrix = np.asarray(summary["confusion_matrix"], dtype=float)
    labels = list(summary["labels"])
    fig, ax = plt.subplots(figsize=(5.8, 5.2))
    im = ax.imshow(matrix, cmap="Greens")
    ax.set_xticks(np.arange(len(labels)))
    ax.set_xticklabels(labels)
    ax.set_yticks(np.arange(len(labels)))
    ax.set_yticklabels(labels)
    for i in range(matrix.shape[0]):
        for j in range(matrix.shape[1]):
            ax.text(j, i, int(matrix[i, j]), ha="center", va="center", color="#17211b", fontsize=16, fontweight="bold")
    ax.set_xlabel("Predicted")
    ax.set_ylabel("True")
    ax.set_title(f"Full-spectrum classifier, accuracy={summary['accuracy']:.1%}")
    fig.colorbar(im, ax=ax, shrink=0.8)
    fig.tight_layout()
    fig.savefig(output, dpi=170)
    plt.close(fig)


def plot_camera_condition_box(rows: list[dict[str, object]], output: Path) -> None:
    conditions = sorted({str(row["condition"]) for row in rows})
    fig, axes = plt.subplots(1, 3, figsize=(12, 5))
    for ax, key in zip(axes, ["camera_brightness", "camera_saturation", "camera_gcc"]):
        data = [[float(row[key]) for row in rows if row["condition"] == cond] for cond in conditions]
        ax.boxplot(data, labels=conditions)
        ax.set_title(labelize(key))
        ax.grid(axis="y", alpha=0.25)
    fig.suptitle("Camera feature separation by condition")
    fig.tight_layout()
    fig.savefig(output, dpi=170)
    plt.close(fig)


def plot_area_by_condition_filter(rows: list[dict[str, object]], output: Path) -> None:
    conditions = sorted({str(row["condition"]) for row in rows})
    filters = sorted({float(row["filter_nm"]) for row in rows})
    fig, ax = plt.subplots(figsize=(10.5, 5.7))
    for condition in conditions:
        means = []
        for filt in filters:
            vals = [float(row["spectrometer_full_area"]) for row in rows if row["condition"] == condition and float(row["filter_nm"]) == filt]
            means.append(float(np.nanmean(vals)) if vals else np.nan)
        ax.plot(filters, means, marker="o", linewidth=2, label=condition)
    ax.set_title("Full-spectrum area by condition and filter")
    ax.set_xlabel("Filter label (nm)")
    ax.set_ylabel("Full-spectrum area")
    ax.grid(alpha=0.25)
    ax.legend()
    savefig(fig, output)


def plot_similarity_heatmap(processed: dict[str, ProcessedSpectrum], output: Path) -> None:
    items = sample_items(processed)
    # Average repeated filters inside sample_id+condition to keep heatmap readable.
    grouped: dict[str, list[np.ndarray]] = {}
    for item in items:
        key = f"{item.spectrum.condition}|{item.spectrum.sample_id.split('/')[-1]}|{item.spectrum.filter_label}"
        grouped.setdefault(key, []).append(item.normalized_curve)
    labels = list(grouped.keys())
    curves = np.vstack([np.nanmean(np.vstack(curves), axis=0) for curves in grouped.values()])
    dist = squareform(pdist(curves, metric="correlation"))
    sim = 1.0 - dist
    fig, ax = plt.subplots(figsize=(10, 8))
    im = ax.imshow(sim, cmap="viridis", vmin=-1, vmax=1)
    ax.set_xticks(np.arange(len(labels)))
    ax.set_xticklabels(labels, rotation=90, fontsize=6)
    ax.set_yticks(np.arange(len(labels)))
    ax.set_yticklabels(labels, fontsize=6)
    ax.set_title("Full-spectrum correlation similarity")
    fig.colorbar(im, ax=ax, shrink=0.8)
    fig.tight_layout()
    fig.savefig(output, dpi=170)
    plt.close(fig)


def copy_contact_sheet(output: Path) -> None:
    src = REAL_OUT_DIR / "camera_contact_sheet.jpg"
    if src.exists():
        output.write_bytes(src.read_bytes())


def build_summary(
    paired_rows: list[dict[str, object]],
    sample_corr_rows: list[dict[str, object]],
    classifier_summary: dict[str, object],
    pca_summary: dict[str, object],
) -> dict[str, object]:
    x = np.asarray([float(row["camera_brightness_norm_in_sample"]) for row in paired_rows], dtype=float)
    y = np.asarray([float(row["spectrometer_area_norm_in_sample"]) for row in paired_rows], dtype=float)
    overall_norm = safe_corr(x, y, "pearson")
    proxy_rows = [row for row in paired_rows if row.get("camera_reflectance_proxy_norm_in_sample") not in {"", None}]
    proxy_x = np.asarray([float(row["camera_reflectance_proxy_norm_in_sample"]) for row in proxy_rows], dtype=float)
    proxy_y = np.asarray([float(row["spectrometer_area_norm_in_sample"]) for row in proxy_rows], dtype=float)
    overall_proxy_norm = safe_corr(proxy_x, proxy_y, "pearson")
    raw_x = np.asarray([float(row["camera_brightness"]) for row in paired_rows], dtype=float)
    raw_y = np.asarray([float(row["spectrometer_full_area"]) for row in paired_rows], dtype=float)
    overall_raw = safe_corr(raw_x, raw_y, "pearson")
    corr_values = [float(row["pearson_normalized_fingerprints"]) for row in sample_corr_rows if np.isfinite(float(row["pearson_normalized_fingerprints"]))]
    proxy_corr_values = [
        float(row["pearson_camera_reflectance_proxy_norm"])
        for row in sample_corr_rows
        if row.get("pearson_camera_reflectance_proxy_norm") not in {"", None}
        and np.isfinite(float(row["pearson_camera_reflectance_proxy_norm"]))
    ]
    return {
        "paired_measurements": len(paired_rows),
        "per_sample_correlations": len(sample_corr_rows),
        "overall_raw_camera_vs_spectrometer_area_pearson_r": overall_raw[0],
        "overall_raw_camera_vs_spectrometer_area_p": overall_raw[1],
        "overall_within_sample_normalized_pearson_r": overall_norm[0],
        "overall_within_sample_normalized_p": overall_norm[1],
        "overall_camera_reflectance_proxy_normalized_pearson_r": overall_proxy_norm[0],
        "overall_camera_reflectance_proxy_normalized_p": overall_proxy_norm[1],
        "median_per_sample_normalized_correlation": float(np.nanmedian(corr_values)) if corr_values else None,
        "mean_per_sample_normalized_correlation": float(np.nanmean(corr_values)) if corr_values else None,
        "median_per_sample_camera_reflectance_proxy_correlation": float(np.nanmedian(proxy_corr_values)) if proxy_corr_values else None,
        "mean_per_sample_camera_reflectance_proxy_correlation": float(np.nanmean(proxy_corr_values)) if proxy_corr_values else None,
        "full_spectrum_classifier": classifier_summary,
        "pca": pca_summary,
    }


def filter_rows_with_key(rows: list[dict[str, object]], key: str) -> list[dict[str, object]]:
    return [row for row in rows if row.get(key) not in {"", None} and is_number(row.get(key))]


def is_number(value: object) -> bool:
    try:
        return np.isfinite(float(value))
    except (TypeError, ValueError):
        return False


def condition_colors() -> dict[str, str]:
    return {"healthy": "#287a46", "unhealthy": "#b24835", "healthy_yellow": "#b8871f"}


def add_condition_legend(ax) -> None:
    from matplotlib.lines import Line2D

    handles = [Line2D([0], [0], color=color, lw=3, label=label) for label, color in condition_colors().items()]
    ax.legend(handles=handles, fontsize=8)


def savefig(fig, output: Path) -> None:
    fig.tight_layout()
    fig.savefig(output, dpi=170)
    plt.close(fig)


def labelize(key: str) -> str:
    return key.replace("_", " ").title()


def round_float(value: object, digits: int = 6) -> float | str:
    if value is None:
        return ""
    try:
        number = float(value)
    except (TypeError, ValueError):
        return ""
    return round(number, digits) if np.isfinite(number) else ""


if __name__ == "__main__":
    main()
