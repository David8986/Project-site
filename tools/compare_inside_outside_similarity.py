"""Compare outside spectra against spectra measured inside the box."""

from __future__ import annotations

import csv
import json
import math
from collections import defaultdict
from pathlib import Path

import matplotlib.pyplot as plt
import numpy as np
from scipy.stats import pearsonr

from run_camera_validation_analysis import (
    ProcessedSpectrum,
    process_spectrum,
    smooth_curve,
)
from run_real_leaf_analysis import (
    CameraMeasurement,
    Spectrum,
    build_reference_index,
    load_all_camera_measurements,
    load_all_spectra,
)


PROJECT_ROOT = Path(r"C:\Users\david\OneDrive\Desktop\Archive\Projects\CodeX")
OUT_DIR = PROJECT_ROOT / "outputs" / "inside_outside_comparison"
GRAPH_DIR = OUT_DIR / "graphs"


def main() -> None:
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    GRAPH_DIR.mkdir(parents=True, exist_ok=True)
    for old in GRAPH_DIR.glob("*.png"):
        old.unlink()

    spectra = load_all_spectra()
    cameras = load_all_camera_measurements()
    references = build_reference_index(spectra)
    processed = {s.relative_path: process_spectrum(s, references) for s in spectra}

    sample_items = [p for p in processed.values() if p.spectrum.role == "sample"]
    comparison_rows = build_comparison_rows(sample_items)
    spectrum_rows = build_environment_spectrum_rows(sample_items)
    camera_inventory = build_camera_inventory(cameras)
    summary = build_summary(comparison_rows, spectrum_rows, camera_inventory)

    write_csv(OUT_DIR / "inside_outside_spectrum_pairs.csv", comparison_rows)
    write_csv(OUT_DIR / "inside_outside_spectrum_environment_features.csv", spectrum_rows)
    write_csv(OUT_DIR / "camera_environment_inventory.csv", camera_inventory)
    (OUT_DIR / "inside_outside_summary.json").write_text(json.dumps(summary, indent=2), encoding="utf-8")

    plot_mean_normalized_spectra(sample_items, GRAPH_DIR / "01_mean_normalized_spectra_inside_vs_outside.png")
    plot_similarity_heatmap(comparison_rows, GRAPH_DIR / "02_inside_outside_similarity_heatmap.png")
    plot_similarity_by_filter(comparison_rows, GRAPH_DIR / "03_similarity_by_filter_and_condition.png")
    plot_raw_area_change(comparison_rows, GRAPH_DIR / "04_raw_signal_area_inside_vs_outside.png")
    plot_noise_and_roughness(spectrum_rows, GRAPH_DIR / "05_noise_roughness_inside_vs_outside.png")
    plot_camera_inventory(camera_inventory, GRAPH_DIR / "06_camera_files_by_environment.png")

    print(OUT_DIR)


def build_comparison_rows(sample_items: list[ProcessedSpectrum]) -> list[dict[str, object]]:
    outside = [p for p in sample_items if p.spectrum.environment.lower() == "afara"]
    inside = [p for p in sample_items if p.spectrum.environment.lower() == "in cutie"]
    rows: list[dict[str, object]] = []

    for out_item in outside:
        out = out_item.spectrum
        if out.condition not in {"healthy", "unhealthy"}:
            continue
        for in_item in inside:
            inside_s = in_item.spectrum
            if inside_s.condition != out.condition:
                continue
            if not filters_match(out, inside_s):
                continue

            corr = safe_corr(out_item.normalized_curve, in_item.normalized_curve)
            rmse = float(np.sqrt(np.nanmean((out_item.normalized_curve - in_item.normalized_curve) ** 2)))
            area_ratio = safe_div(out_item.full_area, in_item.full_area)
            peak_ratio = safe_div(out_item.full_peak, in_item.full_peak)
            rows.append(
                {
                    "condition": out.condition,
                    "filter_label": filter_label(out, inside_s),
                    "outside_sample": out.sample_id,
                    "inside_sample": inside_s.sample_id,
                    "outside_file": out.relative_path,
                    "inside_file": inside_s.relative_path,
                    "shape_similarity_pearson_r": round_float(corr),
                    "normalized_shape_rmse": round_float(rmse),
                    "outside_full_area": round_float(out_item.full_area),
                    "inside_full_area": round_float(in_item.full_area),
                    "outside_to_inside_area_ratio": round_float(area_ratio),
                    "outside_peak": round_float(out_item.full_peak),
                    "inside_peak": round_float(in_item.full_peak),
                    "outside_to_inside_peak_ratio": round_float(peak_ratio),
                    "outside_centroid_nm": round_float(out_item.full_centroid),
                    "inside_centroid_nm": round_float(in_item.full_centroid),
                    "centroid_shift_outside_minus_inside_nm": round_float(out_item.full_centroid - in_item.full_centroid),
                }
            )
    return rows


def build_environment_spectrum_rows(sample_items: list[ProcessedSpectrum]) -> list[dict[str, object]]:
    rows: list[dict[str, object]] = []
    for item in sample_items:
        s = item.spectrum
        residual = s.intensities - smooth_curve(s.intensities)
        noise_index = float(np.nanstd(residual) / max(abs(np.nanmean(item.raw_smooth)), 1e-9))
        roughness_index = float(np.nanmean(np.abs(np.diff(item.normalized_curve))))
        rows.append(
            {
                "environment": s.environment,
                "sample_id": s.sample_id,
                "condition": s.condition,
                "filter_label": s.filter_label,
                "relative_path": s.relative_path,
                "full_area": round_float(item.full_area),
                "full_peak": round_float(item.full_peak),
                "spectral_centroid_nm": round_float(item.full_centroid),
                "noise_index_residual_over_mean": round_float(noise_index),
                "roughness_index_mean_abs_diff": round_float(roughness_index),
            }
        )
    return rows


def build_camera_inventory(cameras: list[CameraMeasurement]) -> list[dict[str, object]]:
    grouped: dict[tuple[str, str], int] = defaultdict(int)
    for cam in cameras:
        grouped[(cam.environment, cam.condition)] += 1
    return [
        {"environment": env, "condition": condition, "image_count": count}
        for (env, condition), count in sorted(grouped.items())
    ]


def build_summary(
    comparison_rows: list[dict[str, object]],
    spectrum_rows: list[dict[str, object]],
    camera_inventory: list[dict[str, object]],
) -> dict[str, object]:
    correlations = [float(r["shape_similarity_pearson_r"]) for r in comparison_rows if r["shape_similarity_pearson_r"] != ""]
    ratios = [float(r["outside_to_inside_area_ratio"]) for r in comparison_rows if r["outside_to_inside_area_ratio"] != ""]
    by_condition: dict[str, dict[str, object]] = {}
    for condition in sorted({str(r["condition"]) for r in comparison_rows}):
        rows = [r for r in comparison_rows if r["condition"] == condition]
        cvals = [float(r["shape_similarity_pearson_r"]) for r in rows if r["shape_similarity_pearson_r"] != ""]
        rvals = [float(r["outside_to_inside_area_ratio"]) for r in rows if r["outside_to_inside_area_ratio"] != ""]
        by_condition[condition] = {
            "matched_pairs": len(rows),
            "median_shape_similarity_r": round_float(np.median(cvals)) if cvals else "",
            "mean_shape_similarity_r": round_float(np.mean(cvals)) if cvals else "",
            "median_outside_to_inside_area_ratio": round_float(np.median(rvals)) if rvals else "",
        }

    env_summary: dict[str, dict[str, object]] = {}
    for env in sorted({str(r["environment"]) for r in spectrum_rows}):
        rows = [r for r in spectrum_rows if r["environment"] == env and r["condition"] in {"healthy", "unhealthy"}]
        noise = [float(r["noise_index_residual_over_mean"]) for r in rows]
        roughness = [float(r["roughness_index_mean_abs_diff"]) for r in rows]
        area = [float(r["full_area"]) for r in rows]
        env_summary[env] = {
            "sample_spectra": len(rows),
            "median_noise_index": round_float(np.median(noise)) if noise else "",
            "median_roughness_index": round_float(np.median(roughness)) if roughness else "",
            "median_full_area": round_float(np.median(area)) if area else "",
        }

    camera_counts = defaultdict(int)
    for row in camera_inventory:
        camera_counts[str(row["environment"])] += int(row["image_count"])

    return {
        "matched_inside_outside_spectrum_pairs": len(comparison_rows),
        "overall_median_shape_similarity_r": round_float(np.median(correlations)) if correlations else "",
        "overall_mean_shape_similarity_r": round_float(np.mean(correlations)) if correlations else "",
        "overall_median_outside_to_inside_area_ratio": round_float(np.median(ratios)) if ratios else "",
        "by_condition": by_condition,
        "environment_spectrum_summary": env_summary,
        "camera_image_counts_by_environment": dict(sorted(camera_counts.items())),
        "note": "No outside camera JPG files were found in the current data folder, so image similarity could only be counted, not compared.",
    }


def filters_match(a: Spectrum, b: Spectrum) -> bool:
    if a.filter_label == "none" or b.filter_label == "none":
        return a.filter_label == b.filter_label
    if a.filter_nm is None or b.filter_nm is None:
        return a.filter_label == b.filter_label
    return abs(a.filter_nm - b.filter_nm) <= 15.0


def filter_label(a: Spectrum, b: Spectrum) -> str:
    if a.filter_label == b.filter_label:
        return a.filter_label
    if a.filter_nm is not None and b.filter_nm is not None:
        return f"{int(a.filter_nm)}/{int(b.filter_nm)}"
    return f"{a.filter_label}/{b.filter_label}"


def safe_corr(a: np.ndarray, b: np.ndarray) -> float:
    valid = np.isfinite(a) & np.isfinite(b)
    if valid.sum() < 3:
        return float("nan")
    if np.nanstd(a[valid]) < 1e-12 or np.nanstd(b[valid]) < 1e-12:
        return float("nan")
    return float(pearsonr(a[valid], b[valid]).statistic)


def safe_div(a: float, b: float) -> float:
    if abs(b) < 1e-12:
        return float("nan")
    return float(a / b)


def plot_mean_normalized_spectra(sample_items: list[ProcessedSpectrum], path: Path) -> None:
    fig, axes = plt.subplots(1, 2, figsize=(14, 5), sharey=True)
    colors = {"afara": "#b84a3a", "in cutie": "#2f7f4f"}
    for ax, condition in zip(axes, ["healthy", "unhealthy"]):
        for env in ["afara", "in cutie"]:
            curves = [p.normalized_curve for p in sample_items if p.spectrum.environment == env and p.spectrum.condition == condition]
            if not curves:
                continue
            wavelengths = next(p.spectrum.wavelengths for p in sample_items if p.spectrum.environment == env and p.spectrum.condition == condition)
            mean_curve = np.nanmean(np.vstack(curves), axis=0)
            std_curve = np.nanstd(np.vstack(curves), axis=0)
            ax.plot(wavelengths, mean_curve, label=f"{env} mean", color=colors[env], linewidth=2)
            ax.fill_between(wavelengths, mean_curve - std_curve, mean_curve + std_curve, color=colors[env], alpha=0.12)
        ax.set_title(f"{condition}: outside vs inside normalized spectra")
        ax.set_xlabel("Wavelength (nm)")
        ax.grid(True, alpha=0.25)
    axes[0].set_ylabel("Normalized intensity")
    axes[1].legend(loc="best")
    fig.suptitle("Shape comparison using the entire spectrum")
    fig.tight_layout()
    fig.savefig(path, dpi=180)
    plt.close(fig)


def plot_similarity_heatmap(rows: list[dict[str, object]], path: Path) -> None:
    sorted_rows = sorted(rows, key=lambda r: (str(r["condition"]), str(r["filter_label"]), str(r["inside_sample"])))
    values = np.array([[float(r["shape_similarity_pearson_r"])] for r in sorted_rows], dtype=float)
    labels = [f'{r["condition"]} {r["filter_label"]}\n{short_sample(str(r["inside_sample"]))}' for r in sorted_rows]

    fig, ax = plt.subplots(figsize=(7, max(6, len(sorted_rows) * 0.34)))
    im = ax.imshow(values, aspect="auto", vmin=-1, vmax=1, cmap="RdYlGn")
    ax.set_xticks([0])
    ax.set_xticklabels(["Pearson r"])
    ax.set_yticks(np.arange(len(labels)))
    ax.set_yticklabels(labels, fontsize=8)
    ax.set_title("Inside-box spectra similarity to matching outside spectra")
    for i, value in enumerate(values[:, 0]):
        ax.text(0, i, f"{value:.2f}", ha="center", va="center", fontsize=8)
    fig.colorbar(im, ax=ax, label="shape similarity, -1 to 1")
    fig.tight_layout()
    fig.savefig(path, dpi=180)
    plt.close(fig)


def plot_similarity_by_filter(rows: list[dict[str, object]], path: Path) -> None:
    groups: dict[tuple[str, str], list[float]] = defaultdict(list)
    for row in rows:
        value = float(row["shape_similarity_pearson_r"])
        groups[(str(row["condition"]), str(row["filter_label"]))].append(value)

    labels = sorted(groups)
    values = [float(np.median(groups[label])) for label in labels]
    colors = ["#2f7f4f" if condition == "healthy" else "#b84a3a" for condition, _ in labels]
    xticklabels = [f"{condition}\n{filter_label}" for condition, filter_label in labels]

    fig, ax = plt.subplots(figsize=(12, 5))
    ax.bar(np.arange(len(values)), values, color=colors)
    ax.axhline(0, color="#222222", linewidth=0.8)
    ax.axhline(0.6, color="#2f7f4f", linewidth=0.8, linestyle="--", alpha=0.6)
    ax.set_ylim(-1, 1)
    ax.set_ylabel("Median shape similarity (Pearson r)")
    ax.set_title("How similar outside and inside spectra are by condition and filter")
    ax.set_xticks(np.arange(len(values)))
    ax.set_xticklabels(xticklabels, rotation=45, ha="right")
    ax.grid(axis="y", alpha=0.25)
    fig.tight_layout()
    fig.savefig(path, dpi=180)
    plt.close(fig)


def plot_raw_area_change(rows: list[dict[str, object]], path: Path) -> None:
    filtered = sorted(rows, key=lambda r: (str(r["condition"]), str(r["filter_label"]), str(r["inside_sample"])))
    labels = [f'{r["condition"]} {r["filter_label"]}\n{short_sample(str(r["inside_sample"]))}' for r in filtered]
    values = [float(r["outside_to_inside_area_ratio"]) for r in filtered]
    colors = ["#2f7f4f" if r["condition"] == "healthy" else "#b84a3a" for r in filtered]

    fig, ax = plt.subplots(figsize=(13, 5.5))
    ax.bar(np.arange(len(values)), values, color=colors)
    ax.axhline(1, color="#222222", linewidth=0.9, linestyle="--")
    ax.set_ylabel("Outside / inside full-spectrum area ratio")
    ax.set_title("Raw signal strength changed strongly outside the box")
    ax.set_xticks(np.arange(len(values)))
    ax.set_xticklabels(labels, rotation=55, ha="right", fontsize=8)
    ax.grid(axis="y", alpha=0.25)
    fig.tight_layout()
    fig.savefig(path, dpi=180)
    plt.close(fig)


def plot_noise_and_roughness(rows: list[dict[str, object]], path: Path) -> None:
    sample_rows = [r for r in rows if r["condition"] in {"healthy", "unhealthy"}]
    envs = ["afara", "in cutie"]
    noise = [[float(r["noise_index_residual_over_mean"]) for r in sample_rows if r["environment"] == env] for env in envs]
    roughness = [[float(r["roughness_index_mean_abs_diff"]) for r in sample_rows if r["environment"] == env] for env in envs]

    fig, axes = plt.subplots(1, 2, figsize=(11, 4.8))
    axes[0].boxplot(noise, tick_labels=envs, patch_artist=True)
    axes[0].set_title("High-frequency noise index")
    axes[0].set_ylabel("Residual std / mean signal")
    axes[0].grid(axis="y", alpha=0.25)
    axes[1].boxplot(roughness, tick_labels=envs, patch_artist=True)
    axes[1].set_title("Spectral roughness index")
    axes[1].set_ylabel("Mean abs diff of normalized curve")
    axes[1].grid(axis="y", alpha=0.25)
    fig.suptitle("Outside measurements are compared with inside-box stability")
    fig.tight_layout()
    fig.savefig(path, dpi=180)
    plt.close(fig)


def plot_camera_inventory(rows: list[dict[str, object]], path: Path) -> None:
    envs = sorted({str(row["environment"]) for row in rows} | {"afara", "in cutie"})
    counts = {env: 0 for env in envs}
    for row in rows:
        counts[str(row["environment"])] += int(row["image_count"])

    fig, ax = plt.subplots(figsize=(6, 4))
    ax.bar(counts.keys(), counts.values(), color=["#b84a3a" if env == "afara" else "#2f7f4f" for env in counts])
    ax.set_title("Camera image files found by environment")
    ax.set_ylabel("JPG count")
    ax.grid(axis="y", alpha=0.25)
    for i, value in enumerate(counts.values()):
        ax.text(i, value + 0.5, str(value), ha="center", va="bottom")
    fig.tight_layout()
    fig.savefig(path, dpi=180)
    plt.close(fig)


def write_csv(path: Path, rows: list[dict[str, object]]) -> None:
    if not rows:
        path.write_text("", encoding="utf-8")
        return
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(rows[0].keys()))
        writer.writeheader()
        writer.writerows(rows)


def short_sample(sample_id: str) -> str:
    return sample_id.replace("in cutie/", "").replace("afara/", "")


def round_float(value: object, digits: int = 6) -> object:
    if value is None:
        return ""
    try:
        number = float(value)
    except (TypeError, ValueError):
        return value
    if math.isnan(number) or math.isinf(number):
        return ""
    return round(number, digits)


if __name__ == "__main__":
    main()
