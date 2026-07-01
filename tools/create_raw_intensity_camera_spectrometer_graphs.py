"""Create display-adjusted camera vs spectrometer graphs without normalization."""

from __future__ import annotations

import csv
import json
import math
import os
import shutil
from collections import defaultdict
from pathlib import Path
from typing import Any

import matplotlib.pyplot as plt
import numpy as np
from PIL import Image, ImageDraw


ROOT = Path(__file__).resolve().parents[1]
CAMERA_VALUES = Path(os.environ.get("SPECTRALEAF_CAMERA_VALUES", ROOT / "outputs" / "camera_image_leaf_values" / "image_leaf_values.csv"))
SPECTROMETER_BINS = Path(os.environ.get("SPECTRALEAF_SPECTROMETER_BINS", ROOT / "outputs" / "spectrometer_camera_no_afara_graphs" / "spectrometer_10nm_binned_indoor_only.csv"))
OUT_DIR = Path(os.environ.get("SPECTRALEAF_FINAL_GRAPH_OUT_DIR", ROOT / "outputs" / "boosted_intensity_camera_spectrometer_10nm_median_graphs"))
GRAPH_DIR = OUT_DIR / "graphs"
DESKTOP_DIR = Path(os.environ.get("SPECTRALEAF_FINAL_GRAPH_DESKTOP_DIR", r"C:\Users\david\OneDrive\Desktop\boosted_intensity_camera_spectrometer_10nm_median_graphs"))
FILTERS = (532, 556, 680, 725, 850, 940)
EPS = 1e-12
SPECTROMETER_MIN_WAVELENGTH_NM = 300.0
SPECTROMETER_Y_BOTTOM = 300.0
PEAK_SEARCH_HALF_WINDOW_NM = 90.0
MAX_PEAK_ALIGNMENT_SHIFT_NM = 60.0
SPECTROMETER_BOOST_POINTS = ((725.0, 1.0), (850.0, 1.0), (940.0, 1.0), (1040.0, 1.0))
CAMERA_BOOST_POINTS = ((725.0, 1.0), (850.0, 1.04), (940.0, 1.08))
SPECTROMETER_SMOOTH_SIGMA_NM = 15.0
PEAK_ALIGNMENT_TOLERANCE_NM = 25.0


def read_csv(path: Path) -> list[dict[str, str]]:
    with path.open("r", encoding="utf-8-sig", newline="") as handle:
        return list(csv.DictReader(handle))


def write_csv(path: Path, rows: list[dict[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    if not rows:
        path.write_text("", encoding="utf-8")
        return
    headers: list[str] = []
    for row in rows:
        for key in row:
            if key not in headers:
                headers.append(key)
    with path.open("w", newline="", encoding="utf-8-sig") as handle:
        writer = csv.DictWriter(handle, fieldnames=headers, extrasaction="ignore")
        writer.writeheader()
        writer.writerows(rows)


def as_float(value: Any) -> float | None:
    try:
        number = float(value)
    except (TypeError, ValueError):
        return None
    if not math.isfinite(number):
        return None
    return number


def rounded(value: Any, digits: int = 6) -> Any:
    number = as_float(value)
    if number is None:
        return ""
    return round(number, digits)


def boost_factor(wavelength_nm: float, points: tuple[tuple[float, float], ...]) -> float:
    if wavelength_nm <= points[0][0]:
        return points[0][1]
    for (left_nm, left_factor), (right_nm, right_factor) in zip(points, points[1:]):
        if left_nm <= wavelength_nm <= right_nm:
            span = max(right_nm - left_nm, EPS)
            t = (wavelength_nm - left_nm) / span
            return left_factor + t * (right_factor - left_factor)
    return points[-1][1]


def boosted_spectrometer(value: Any, wavelength_nm: Any) -> float | None:
    number = as_float(value)
    wavelength = as_float(wavelength_nm)
    if number is None or wavelength is None:
        return None
    return number * boost_factor(wavelength, SPECTROMETER_BOOST_POINTS)


def boosted_camera(value: Any, wavelength_nm: Any) -> float | None:
    number = as_float(value)
    wavelength = as_float(wavelength_nm)
    if number is None or wavelength is None:
        return None
    return min(255.0, number * boost_factor(wavelength, CAMERA_BOOST_POINTS))


def display_spectrometer_wavelength(wavelength_nm: Any, shift_nm: float = 0.0) -> float | None:
    wavelength = as_float(wavelength_nm)
    if wavelength is None:
        return None
    return wavelength + shift_nm


def short_sample_name(sample_id: str) -> str:
    return sample_id.replace("in cutie\\", "")


def safe_name(text: str) -> str:
    import re

    return re.sub(r"[^A-Za-z0-9_-]+", "_", text).strip("_")


def filter_nm_from_label(label: str) -> int | None:
    if not label.endswith(" nm"):
        return None
    try:
        return int(label.split()[0])
    except (IndexError, ValueError):
        return None


def pearson(xs: list[float], ys: list[float]) -> float | None:
    if len(xs) < 2 or len(ys) < 2:
        return None
    x = np.asarray(xs, dtype=float)
    y = np.asarray(ys, dtype=float)
    if float(np.std(x)) <= EPS or float(np.std(y)) <= EPS:
        return None
    return float(np.corrcoef(x, y)[0, 1])


def smooth_camera_curve(xs: list[float], ys: list[float], points: int = 500) -> tuple[np.ndarray, np.ndarray]:
    """Interpolate and gently smooth camera points for a visual guide."""

    x = np.asarray(xs, dtype=float)
    y = np.asarray(ys, dtype=float)
    order = np.argsort(x)
    x = x[order]
    y = y[order]
    if x.size < 2:
        return x, y
    dense_x = np.linspace(float(x.min()), float(x.max()), points)
    dense_y = np.interp(dense_x, x, y)
    dx = max(float(dense_x[1] - dense_x[0]), EPS)
    sigma_nm = 18.0
    sigma_points = max(1.0, sigma_nm / dx)
    radius = int(max(3, round(sigma_points * 3)))
    grid = np.arange(-radius, radius + 1, dtype=float)
    kernel = np.exp(-0.5 * (grid / sigma_points) ** 2)
    kernel /= kernel.sum()
    padded = np.pad(dense_y, radius, mode="edge")
    smooth = np.convolve(padded, kernel, mode="same")[radius:-radius]
    return dense_x, smooth


def smooth_spectrometer_curve(xs: list[float], ys: list[float], points: int = 900) -> tuple[np.ndarray, np.ndarray]:
    """Smooth only the displayed line; matched values and exported data stay raw 10 nm medians."""

    x = np.asarray(xs, dtype=float)
    y = np.asarray(ys, dtype=float)
    if x.size < 4:
        return x, y
    order = np.argsort(x)
    x = x[order]
    y = y[order]
    dense_x = np.linspace(float(x.min()), float(x.max()), points)
    dense_y = np.interp(dense_x, x, y)
    dx = max(float(dense_x[1] - dense_x[0]), EPS)
    sigma_points = max(1.0, SPECTROMETER_SMOOTH_SIGMA_NM / dx)
    radius = int(max(4, round(sigma_points * 3)))
    grid = np.arange(-radius, radius + 1, dtype=float)
    kernel = np.exp(-0.5 * (grid / sigma_points) ** 2)
    kernel /= kernel.sum()
    padded = np.pad(dense_y, radius, mode="edge")
    smooth = np.convolve(padded, kernel, mode="same")[radius:-radius]
    return dense_x, smooth


def camera_bottom_tick_labels(camera_rows: list[dict[str, Any]], boosted: bool = True) -> list[str]:
    by_filter = {int(row["filter_nm"]): row for row in camera_rows}
    labels: list[str] = []
    for wavelength in FILTERS:
        row = by_filter.get(wavelength)
        value = None
        if row:
            source_value = row.get("camera_brightness_median_0_255")
            value = boosted_camera(source_value, wavelength) if boosted else as_float(source_value)
        label_value = "--" if value is None else str(int(round(value)))
        labels.append(f"{wavelength} nm | cam {label_value}")
    return labels


def style_camera_tick_labels(ax: Any) -> None:
    ax.tick_params(axis="x", labelsize=8, pad=4)
    for label in ax.get_xticklabels():
        label.set_rotation(90)
        label.set_ha("center")
        label.set_va("top")


def matched_display_points_for_sample(
    camera_rows: list[dict[str, Any]],
    spectrometer_curves: dict[str, list[dict[str, Any]]],
) -> list[dict[str, float]]:
    points: list[dict[str, float]] = []
    for cam in camera_rows:
        wavelength = int(cam["filter_nm"])
        curve = spectrometer_curves.get(f"{wavelength} nm", [])
        if not curve:
            continue
        peak = spectrometer_peak_for_filter(curve, wavelength)
        if peak is None:
            continue
        camera_value = boosted_camera(cam.get("camera_brightness_median_0_255"), wavelength)
        spectrometer_value = boosted_spectrometer(peak.get("median_intensity_10nm"), peak.get("bin_center_nm"))
        if camera_value is None or spectrometer_value is None:
            continue
        points.append(
            {
                "wavelength": float(wavelength),
                "camera_value": float(camera_value),
                "spectrometer_value": float(spectrometer_value),
                "peak_offset_nm": float(peak["bin_center_nm"]) - float(wavelength),
            }
        )
    return points


def spectrometer_peak_for_filter(curve: list[dict[str, Any]], filter_nm: int | float) -> dict[str, Any] | None:
    filter_value = float(filter_nm)
    candidates = [
        row
        for row in curve
        if row.get("bin_center_nm") is not None
        and row.get("median_intensity_10nm") is not None
        and abs(float(row["bin_center_nm"]) - filter_value) <= PEAK_SEARCH_HALF_WINDOW_NM
    ]
    if not candidates:
        candidates = [
            row
            for row in curve
            if row.get("bin_center_nm") is not None and row.get("median_intensity_10nm") is not None
        ]
    if not candidates:
        return None
    return max(candidates, key=lambda row: float(row["median_intensity_10nm"]))


def curve_peak_alignment_shift(curve: list[dict[str, Any]], filter_nm: int | None) -> tuple[float, dict[str, Any] | None]:
    if filter_nm is None:
        return 0.0, None
    peak = spectrometer_peak_for_filter(curve, filter_nm)
    if peak is None:
        return 0.0, None
    shift = float(filter_nm) - float(peak["bin_center_nm"])
    shift = max(-MAX_PEAK_ALIGNMENT_SHIFT_NM, min(MAX_PEAK_ALIGNMENT_SHIFT_NM, shift))
    return shift, peak


def add_visual_agreement_bands(ax: Any, points: list[dict[str, float]]) -> None:
    if not points:
        return
    agreement_labeled = False
    disagreement_labeled = False
    for point in points:
        peak_offset = abs(float(point.get("peak_offset_nm", 0.0)))
        agrees = peak_offset <= PEAK_ALIGNMENT_TOLERANCE_NM
        if agrees:
            color = "#47a76a"
            label = "peak-aligned camera band" if not agreement_labeled else None
            agreement_labeled = True
        else:
            color = "#d9574a"
            label = "peak-shifted camera band" if not disagreement_labeled else None
            disagreement_labeled = True
        ax.axvspan(
            point["wavelength"] - 13,
            point["wavelength"] + 13,
            color=color,
            alpha=0.16 if agrees else 0.18,
            linewidth=0,
            label=label,
            zorder=0,
        )


def camera_rows_by_sample() -> dict[str, list[dict[str, Any]]]:
    rows = read_csv(CAMERA_VALUES)
    out: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for row in rows:
        if row.get("sample_role") != "leaf_sample":
            continue
        wavelength = as_float(row.get("filter_nm"))
        if wavelength is None or int(round(wavelength)) not in FILTERS:
            continue
        out[row["sample_id"]].append(
            {
                "sample_id": row["sample_id"],
                "condition": row.get("condition", ""),
                "filter_nm": int(round(wavelength)),
                "camera_brightness_median_0_255": as_float(row.get("value_0_255_median")),
                "camera_brightness_mean_0_255": as_float(row.get("value_0_255_mean")),
                "camera_brightness_median_0_1": as_float(row.get("value_0_1_median")),
                "camera_brightness_mean_0_1": as_float(row.get("value_0_1_mean")),
            }
        )
    return {sample: sorted(items, key=lambda item: int(item["filter_nm"])) for sample, items in out.items()}


def spectrometer_rows_by_sample() -> dict[str, dict[str, list[dict[str, Any]]]]:
    rows = read_csv(SPECTROMETER_BINS)
    out: dict[str, dict[str, list[dict[str, Any]]]] = defaultdict(lambda: defaultdict(list))
    for row in rows:
        if row.get("sample_role") != "leaf_sample":
            continue
        sample_id = row["sample_id"]
        spectrum_file = row.get("spectrum_file", "")
        filter_label = str(row.get("filter_nm") or row.get("filter_label") or spectrum_file)
        key = f"{filter_label} nm" if filter_label not in {"", "fara"} else "fara"
        parsed = {
            "sample_id": sample_id,
            "condition": row.get("condition", ""),
            "spectrum_file": spectrum_file,
            "filter_nm": int(round(float(row["filter_nm"]))) if row.get("filter_nm") not in {"", None} else None,
            "filter_label": key,
            "bin_center_nm": as_float(row.get("bin_center_nm")),
            "median_intensity_10nm": as_float(row.get("median_intensity_10nm")),
        }
        if parsed["bin_center_nm"] is None or parsed["median_intensity_10nm"] is None:
            continue
        out[sample_id][key].append(parsed)
    return {
        sample: {
            label: sorted(items, key=lambda item: float(item["bin_center_nm"]))
            for label, items in curves.items()
        }
        for sample, curves in out.items()
    }


def matched_filter_pairs(
    camera_by_sample: dict[str, list[dict[str, Any]]],
    spectrometer_by_sample: dict[str, dict[str, list[dict[str, Any]]]],
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    pairs: list[dict[str, Any]] = []
    corr_rows: list[dict[str, Any]] = []
    for sample_id, camera_rows in sorted(camera_by_sample.items()):
        xs: list[float] = []
        ys: list[float] = []
        missing: list[str] = []
        for cam in camera_rows:
            wavelength = int(cam["filter_nm"])
            curve = spectrometer_by_sample.get(sample_id, {}).get(f"{wavelength} nm", [])
            spec_peak_value = None
            spec_peak_wavelength = None
            spec_file = ""
            if curve:
                peak = spectrometer_peak_for_filter(curve, wavelength)
                if peak:
                    spec_peak_value = peak["median_intensity_10nm"]
                    spec_peak_wavelength = peak["bin_center_nm"]
                    spec_file = peak["spectrum_file"]
            if spec_peak_value is None:
                missing.append(str(wavelength))
            else:
                camera_value = boosted_camera(cam["camera_brightness_median_0_255"], wavelength)
                spec_display_value = boosted_spectrometer(spec_peak_value, spec_peak_wavelength)
                if camera_value is not None and spec_display_value is not None:
                    xs.append(float(camera_value))
                    ys.append(float(spec_display_value))
            pairs.append(
                {
                    "sample_id": sample_id,
                    "condition": cam.get("condition", ""),
                    "filter_nm": wavelength,
                    "camera_brightness_median_0_255": rounded(cam.get("camera_brightness_median_0_255"), 3),
                    "camera_display_brightness_boosted": rounded(boosted_camera(cam.get("camera_brightness_median_0_255"), wavelength), 3),
                    "camera_brightness_mean_0_255": rounded(cam.get("camera_brightness_mean_0_255"), 3),
                    "spectrometer_peak_wavelength_nm": rounded(spec_peak_wavelength, 3),
                    "spectrometer_peak_offset_from_filter_nm": rounded((spec_peak_wavelength - wavelength) if spec_peak_wavelength is not None else None, 3),
                    "spectrometer_peak_10nm_median_intensity": rounded(spec_peak_value, 3),
                    "spectrometer_display_intensity_boosted": rounded(boosted_spectrometer(spec_peak_value, spec_peak_wavelength), 3),
                    "spectrometer_match_method": f"local peak within +/-{int(PEAK_SEARCH_HALF_WINDOW_NM)} nm of filter",
                    "spectrometer_file": spec_file,
                    "matched": spec_peak_value is not None,
                }
            )
        corr_rows.append(
            {
                "sample_id": sample_id,
                "condition": camera_rows[0].get("condition", "") if camera_rows else "",
                "matched_filter_count": len(xs),
                "pearson_display_camera_vs_boosted_spectrometer_intensity": rounded(pearson(xs, ys)),
                "missing_filters": ",".join(missing),
            }
        )
    return pairs, corr_rows


def plot_sample_raw_intensity(
    sample_id: str,
    camera_rows: list[dict[str, Any]],
    spectrometer_curves: dict[str, list[dict[str, Any]]],
) -> str:
    fig, ax1 = plt.subplots(figsize=(12.5, 6.8))
    palette = {
        "532 nm": "#2f7f4f",
        "556 nm": "#7ba943",
        "580 nm": "#a8a33e",
        "680 nm": "#ba4a3a",
        "725 nm": "#8d4fb8",
        "850 nm": "#315f8c",
        "940 nm": "#4a4a4a",
        "fara": "#111111",
    }
    for label, curve in sorted(spectrometer_curves.items(), key=lambda item: (9999 if item[0] == "fara" else int(item[0].split()[0]), item[0])):
        filter_nm = filter_nm_from_label(label)
        shift_nm, peak = curve_peak_alignment_shift(curve, filter_nm)
        filtered_curve = [
            row
            for row in curve
            if (display_spectrometer_wavelength(row["bin_center_nm"], shift_nm) or 0.0) >= SPECTROMETER_MIN_WAVELENGTH_NM
        ]
        x = [float(display_spectrometer_wavelength(row["bin_center_nm"], shift_nm) or 0.0) for row in filtered_curve]
        y = [
            float(boosted_spectrometer(row["median_intensity_10nm"], row["bin_center_nm"]) or 0.0)
            for row in filtered_curve
        ]
        smooth_x, smooth_y = smooth_spectrometer_curve(x, y)
        ax1.plot(
            smooth_x,
            smooth_y,
            linewidth=1.75,
            alpha=0.9,
            color=palette.get(label),
            label=f"spectru {label} smoothed",
        )
        if filter_nm is not None and peak is not None:
            peak_x = display_spectrometer_wavelength(peak["bin_center_nm"], shift_nm)
            peak_y = boosted_spectrometer(peak["median_intensity_10nm"], peak["bin_center_nm"])
            if peak_x is not None and peak_y is not None:
                ax1.scatter(
                    [peak_x],
                    [peak_y],
                    marker="^",
                    s=52,
                    color=palette.get(label),
                    edgecolor="white",
                    linewidth=0.7,
                    zorder=6,
                )
    add_visual_agreement_bands(ax1, matched_display_points_for_sample(camera_rows, spectrometer_curves))
    ax1.set_xlabel("Wavelength (nm)")
    ax1.set_ylabel("Spectrometer display intensity, 10 nm median")
    ax1.set_xlim(SPECTROMETER_MIN_WAVELENGTH_NM, 1045)
    ax1.set_ylim(bottom=SPECTROMETER_Y_BOTTOM)
    ax1.grid(True, alpha=0.22)
    ax1.set_xticks(list(FILTERS))
    ax1.set_xticklabels(camera_bottom_tick_labels(camera_rows))
    style_camera_tick_labels(ax1)

    ax2 = ax1.twinx()
    cam_x = [float(row["filter_nm"]) for row in camera_rows if row["camera_brightness_median_0_255"] is not None]
    cam_y = [
        float(boosted_camera(row["camera_brightness_median_0_255"], row["filter_nm"]) or 0.0)
        for row in camera_rows
        if row["camera_brightness_median_0_255"] is not None
    ]
    if cam_x and cam_y:
        smooth_x, smooth_y = smooth_camera_curve(cam_x, cam_y)
        ax2.plot(smooth_x, smooth_y, color="#f06d2f", linewidth=3.0, alpha=0.78, label="camera smoothed guide")
        ax2.scatter(cam_x, cam_y, color="#f06d2f", edgecolor="white", linewidth=0.8, s=66, zorder=5, label="camera display points")
        for x, y in zip(cam_x, cam_y):
            ax2.text(x, y + 5, f"{int(round(y))}", color="#7a2d13", fontsize=8, ha="center")
    ax2.set_ylabel("Camera display brightness median (0-255)")
    ax2.set_ylim(0, 255)

    lines1, labels1 = ax1.get_legend_handles_labels()
    lines2, labels2 = ax2.get_legend_handles_labels()
    ax1.legend(lines1 + lines2, labels1 + labels2, fontsize=8, ncol=4, loc="upper right")
    fig.suptitle(
        f"Display-adjusted intensity comparison - {short_sample_name(sample_id)}\n"
        "Smoothed spectrometer display; green bands have aligned peaks, red bands have shifted peaks",
        fontsize=13,
    )
    fig.tight_layout(rect=(0, 0.08, 1, 0.94))
    out = GRAPH_DIR / f"boosted_intensity_{safe_name(sample_id)}.png"
    fig.savefig(out, dpi=180)
    plt.close(fig)
    return str(out)


def plot_matched_dual_axis(
    camera_by_sample: dict[str, list[dict[str, Any]]],
    pairs: list[dict[str, Any]],
) -> str:
    by_sample: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for row in pairs:
        by_sample[row["sample_id"]].append(row)
    samples = sorted(by_sample)
    cols = 2
    rows_n = int(math.ceil(len(samples) / cols))
    fig, axes = plt.subplots(rows_n, cols, figsize=(15, 4.6 * rows_n))
    axes = np.asarray(axes).reshape(rows_n, cols)
    for ax in axes.ravel():
        ax.axis("off")
    for index, sample_id in enumerate(samples):
        ax1 = axes.ravel()[index]
        ax1.axis("on")
        rows = sorted(by_sample[sample_id], key=lambda row: int(row["filter_nm"]))
        xs = [int(row["filter_nm"]) for row in rows]
        spec = [as_float(row["spectrometer_display_intensity_boosted"]) for row in rows]
        cam = [as_float(row["camera_display_brightness_boosted"]) for row in rows]
        band_points = [
            {
                "wavelength": float(row["filter_nm"]),
                "camera_value": float(cam_value),
                "spectrometer_value": float(spec_value),
                "peak_offset_nm": float(row["spectrometer_peak_offset_from_filter_nm"]),
            }
            for row, cam_value, spec_value in zip(rows, cam, spec)
            if cam_value is not None and spec_value is not None and row.get("spectrometer_peak_offset_from_filter_nm") not in {"", None}
        ]
        add_visual_agreement_bands(ax1, band_points)
        spec_x = [float(x) for x, y in zip(xs, spec) if y is not None]
        spec_y = [float(y) for y in spec if y is not None]
        if spec_x and spec_y:
            spec_smooth_x, spec_smooth_y = smooth_camera_curve(spec_x, spec_y)
            ax1.plot(spec_smooth_x, spec_smooth_y, color="#315f8c", linewidth=2.2, label="spectrometer peak smoothed guide")
            ax1.scatter(spec_x, spec_y, marker="s", color="#315f8c", edgecolor="white", linewidth=0.7, s=54, zorder=5, label="spectrometer raw local peaks")
        ax1.set_ylabel("Spectrometer boosted peak intensity", color="#315f8c")
        ax1.set_ylim(bottom=SPECTROMETER_Y_BOTTOM)
        ax1.tick_params(axis="y", labelcolor="#315f8c")
        ax1.set_xticks(list(FILTERS))
        ax1.set_xticklabels(camera_bottom_tick_labels(rows))
        style_camera_tick_labels(ax1)
        ax1.set_xlabel("Filter / camera boosted median brightness")
        ax1.grid(True, alpha=0.24)
        ax2 = ax1.twinx()
        cam_x = [float(x) for x, y in zip(xs, cam) if y is not None]
        cam_y = [float(y) for y in cam if y is not None]
        if cam_x and cam_y:
            smooth_x, smooth_y = smooth_camera_curve(cam_x, cam_y)
            ax2.plot(smooth_x, smooth_y, color="#f06d2f", linewidth=2.7, alpha=0.78, label="camera smoothed guide")
            ax2.scatter(cam_x, cam_y, color="#f06d2f", edgecolor="white", linewidth=0.7, s=54, zorder=4, label="camera boosted median brightness")
        ax2.set_ylim(0, 255)
        ax2.set_ylabel("Camera display brightness (0-255)", color="#b04d22")
        ax2.tick_params(axis="y", labelcolor="#b04d22")
        ax1.set_title(short_sample_name(sample_id), fontsize=10)
        l1, lab1 = ax1.get_legend_handles_labels()
        l2, lab2 = ax2.get_legend_handles_labels()
        ax1.legend(l1 + l2, lab1 + lab2, fontsize=7, loc="upper left")
    fig.suptitle("Matched filter intensities: green peaks align, red peaks are shifted", fontsize=15, y=0.995)
    fig.tight_layout(rect=(0, 0, 1, 0.975))
    out = GRAPH_DIR / "matched_filter_boosted_intensity_dual_axis.png"
    fig.savefig(out, dpi=180)
    plt.close(fig)
    return str(out)


def plot_scatter(pairs: list[dict[str, Any]]) -> str:
    rows = [row for row in pairs if row.get("matched")]
    fig, ax = plt.subplots(figsize=(8.8, 7.0))
    colors = {532: "#2f7f4f", 556: "#7ba943", 680: "#ba4a3a", 725: "#8d4fb8", 850: "#315f8c", 940: "#555555"}
    xs = [float(row["camera_display_brightness_boosted"]) for row in rows]
    ys = [float(row["spectrometer_display_intensity_boosted"]) for row in rows]
    for row, x, y in zip(rows, xs, ys):
        wavelength = int(row["filter_nm"])
        ax.scatter(x, y, s=62, color=colors.get(wavelength), edgecolor="white", linewidth=0.8)
        ax.text(x + 1.2, y, str(wavelength), fontsize=7)
    ax.set_xlabel("Camera boosted display brightness on leaf mask (0-255)")
    ax.set_ylabel("Spectrometer boosted local peak intensity")
    ax.set_title("Camera brightness vs peak of matching spectrometer curve")
    ax.grid(True, alpha=0.25)
    handles = [plt.Line2D([0], [0], marker="o", linestyle="", color=color, label=f"{wl} nm") for wl, color in colors.items()]
    ax.legend(handles=handles, ncol=3, fontsize=8)
    fig.tight_layout()
    out = GRAPH_DIR / "boosted_intensity_scatter_camera_vs_spectrometer.png"
    fig.savefig(out, dpi=180)
    plt.close(fig)
    return str(out)


def plot_correlation_bars(correlation_rows: list[dict[str, Any]]) -> str:
    rows = sorted(correlation_rows, key=lambda row: row["sample_id"])
    labels = [short_sample_name(row["sample_id"]) for row in rows]
    values = [as_float(row["pearson_display_camera_vs_boosted_spectrometer_intensity"]) or np.nan for row in rows]
    fig, ax = plt.subplots(figsize=(11.5, 5.8))
    colors = ["#287a46" if value >= 0.45 else "#e0a72e" if value >= 0.25 else "#ba4a3a" for value in values]
    ax.bar(np.arange(len(rows)), values, color=colors)
    ax.axhline(0, color="#222222", linewidth=1)
    ax.set_ylim(-1, 1)
    ax.set_xticks(np.arange(len(rows)))
    ax.set_xticklabels(labels, rotation=25, ha="right")
    ax.set_ylabel("Pearson r using boosted display intensities")
    ax.set_title("Camera display brightness correlation with boosted spectrometer 10 nm median intensity")
    ax.grid(True, axis="y", alpha=0.25)
    fig.tight_layout()
    out = GRAPH_DIR / "boosted_intensity_correlation_by_sample.png"
    fig.savefig(out, dpi=180)
    plt.close(fig)
    return str(out)


def make_gallery(graph_paths: list[str]) -> str:
    thumbs: list[Image.Image] = []
    for raw in graph_paths:
        path = Path(raw)
        if not path.exists():
            continue
        with Image.open(path) as image:
            thumb = image.convert("RGB")
            thumb.thumbnail((660, 455))
            canvas = Image.new("RGB", (700, 535), "white")
            canvas.paste(thumb, ((700 - thumb.width) // 2, 18))
            draw = ImageDraw.Draw(canvas)
            draw.text((18, 500), path.name[:96], fill=(20, 20, 20))
            thumbs.append(canvas)
    if not thumbs:
        return ""
    cols = 2
    rows = int(math.ceil(len(thumbs) / cols))
    sheet = Image.new("RGB", (cols * 700, rows * 535), "white")
    for index, thumb in enumerate(thumbs):
        sheet.paste(thumb, ((index % cols) * 700, (index // cols) * 535))
    out = OUT_DIR / "boosted_intensity_graph_gallery.jpg"
    sheet.save(out, quality=92)
    return str(out)


def main() -> None:
    if OUT_DIR.exists():
        shutil.rmtree(OUT_DIR)
    GRAPH_DIR.mkdir(parents=True, exist_ok=True)

    camera_by_sample = camera_rows_by_sample()
    spectrometer_by_sample = spectrometer_rows_by_sample()
    pairs, corr_rows = matched_filter_pairs(camera_by_sample, spectrometer_by_sample)

    graph_paths: list[str] = []
    for sample_id in sorted(camera_by_sample):
        graph_paths.append(plot_sample_raw_intensity(sample_id, camera_by_sample[sample_id], spectrometer_by_sample.get(sample_id, {})))
    graph_paths.append(plot_matched_dual_axis(camera_by_sample, pairs))
    graph_paths.append(plot_scatter(pairs))
    # Correlation is highlighted visually on the comparison graphs instead of printed as a coefficient.
    gallery = make_gallery(graph_paths)

    write_csv(OUT_DIR / "boosted_intensity_camera_spectrometer_pairs.csv", pairs)
    write_csv(OUT_DIR / "boosted_intensity_camera_spectrometer_correlations.csv", corr_rows)

    matched = [row for row in pairs if row.get("matched")]
    overall_r = pearson(
        [float(row["camera_display_brightness_boosted"]) for row in matched],
        [float(row["spectrometer_display_intensity_boosted"]) for row in matched],
    )
    summary = {
        "method": (
            "No normalization. This graph set is display-adjusted: spectrometer intensity is kept on its original "
            "scale, and camera brightness gets a small visual lift at the high-wavelength end. Spectrometer curves are displayed only from 300 nm upward, with the "
            "spectrometer y-axis starting at 300 to hide the low-end noisy baseline. Each filter-specific spectrometer curve is "
            "aligned by its own local peak: for example, the camera 850 nm value is compared with the peak of the 850 nm "
            "spectrometer file, not with the exact 850 nm bin. Spectrometer lines are smoothed only for display, while the exported "
            "values remain the raw 10 nm medians/local peaks. Green camera bands mark spectrometer peaks that land close to the "
            "camera/filter wavelength, and red bands mark peaks shifted farther away. Spectrometer curves still use median intensity inside every 10 nm bin. "
            "Raw camera and spectrometer values are preserved in the CSV beside the boosted display values."
        ),
        "matched_pairs": len(matched),
        "overall_boosted_display_pearson_r": rounded(overall_r),
        "spectrometer_boost_points": SPECTROMETER_BOOST_POINTS,
        "camera_boost_points": CAMERA_BOOST_POINTS,
        "peak_search_half_window_nm": PEAK_SEARCH_HALF_WINDOW_NM,
        "max_peak_alignment_shift_nm": MAX_PEAK_ALIGNMENT_SHIFT_NM,
        "spectrometer_display_smooth_sigma_nm": SPECTROMETER_SMOOTH_SIGMA_NM,
        "peak_alignment_tolerance_nm": PEAK_ALIGNMENT_TOLERANCE_NM,
        "graphs": graph_paths,
        "gallery": gallery,
        "csv_files": {
            "pairs": str(OUT_DIR / "boosted_intensity_camera_spectrometer_pairs.csv"),
            "correlations": str(OUT_DIR / "boosted_intensity_camera_spectrometer_correlations.csv"),
        },
        "judgement": (
            "These boosted plots are meant for visual comparison and presentation. Use the raw value columns in the CSV "
            "for strict measurement claims, and use the boosted display columns only when explaining the compensated graph."
        ),
    }
    (OUT_DIR / "summary.json").write_text(json.dumps(summary, indent=2), encoding="utf-8")

    if DESKTOP_DIR.exists():
        shutil.rmtree(DESKTOP_DIR)
    shutil.copytree(OUT_DIR, DESKTOP_DIR)
    (DESKTOP_DIR / "summary.json").write_text(json.dumps(summary, indent=2), encoding="utf-8")
    print(json.dumps({**summary, "desktop_copy": str(DESKTOP_DIR)}, indent=2))


if __name__ == "__main__":
    main()
