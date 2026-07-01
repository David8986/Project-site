"""Create clean summary graphs from the approved 'grafice ok' CSV data."""

from __future__ import annotations

import csv
import json
import math
import shutil
from collections import defaultdict
from pathlib import Path
from typing import Any

import matplotlib.pyplot as plt
import numpy as np
from PIL import Image, ImageDraw


SOURCE_DIR = Path(r"C:\Users\david\OneDrive\Desktop\grafice ok")
SOURCE_PAIRS = SOURCE_DIR / "boosted_intensity_camera_spectrometer_pairs.csv"
SOURCE_GRAPHS = SOURCE_DIR / "graphs"
OUT_DIR = Path(r"C:\Users\david\OneDrive\Desktop\grafice ok generated")
GRAPH_DIR = OUT_DIR / "graphs"
FILTERS = (532, 556, 680, 725, 850, 940)
PEAK_ALIGNMENT_TOLERANCE_NM = 25.0
EPS = 1e-12


def as_float(value: Any) -> float | None:
    try:
        number = float(value)
    except (TypeError, ValueError):
        return None
    if not math.isfinite(number):
        return None
    return number


def read_pairs() -> list[dict[str, Any]]:
    with SOURCE_PAIRS.open("r", encoding="utf-8-sig", newline="") as handle:
        rows: list[dict[str, Any]] = []
        for row in csv.DictReader(handle):
            parsed = dict(row)
            for key in (
                "filter_nm",
                "camera_brightness_median_0_255",
                "camera_display_brightness_boosted",
                "spectrometer_peak_wavelength_nm",
                "spectrometer_peak_offset_from_filter_nm",
                "spectrometer_peak_10nm_median_intensity",
                "spectrometer_display_intensity_boosted",
            ):
                parsed[key] = as_float(parsed.get(key))
            rows.append(parsed)
        return rows


def short_sample_name(sample_id: str) -> str:
    return sample_id.replace("in cutie\\", "")


def safe_name(text: str) -> str:
    import re

    return re.sub(r"[^A-Za-z0-9_-]+", "_", text).strip("_")


def smooth_curve(xs: list[float], ys: list[float], points: int = 350) -> tuple[np.ndarray, np.ndarray]:
    x = np.asarray(xs, dtype=float)
    y = np.asarray(ys, dtype=float)
    if x.size < 2:
        return x, y
    order = np.argsort(x)
    x = x[order]
    y = y[order]
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


def by_sample(rows: list[dict[str, Any]]) -> dict[str, list[dict[str, Any]]]:
    grouped: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for row in rows:
        grouped[str(row["sample_id"])].append(row)
    return {
        sample: sorted(items, key=lambda item: float(item["filter_nm"]))
        for sample, items in sorted(grouped.items())
    }


def add_peak_bands(ax: Any, rows: list[dict[str, Any]]) -> None:
    green_labeled = False
    red_labeled = False
    for row in rows:
        wavelength = as_float(row.get("filter_nm"))
        offset = as_float(row.get("spectrometer_peak_offset_from_filter_nm"))
        if wavelength is None or offset is None:
            continue
        aligned = abs(offset) <= PEAK_ALIGNMENT_TOLERANCE_NM
        color = "#47a76a" if aligned else "#d9574a"
        label = None
        if aligned and not green_labeled:
            label = "peak aligned"
            green_labeled = True
        elif not aligned and not red_labeled:
            label = "peak shifted"
            red_labeled = True
        ax.axvspan(
            wavelength - 13,
            wavelength + 13,
            color=color,
            alpha=0.14 if aligned else 0.18,
            linewidth=0,
            label=label,
            zorder=0,
        )


def set_filter_axis(ax: Any, rows: list[dict[str, Any]] | None = None) -> None:
    ax.set_xticks(list(FILTERS))
    if rows:
        label_by_filter = {}
        for row in rows:
            wavelength = int(row["filter_nm"])
            camera = as_float(row.get("camera_display_brightness_boosted"))
            label_by_filter[wavelength] = f"{wavelength} nm | cam {camera:.0f}" if camera is not None else f"{wavelength} nm"
        ax.set_xticklabels([label_by_filter.get(wl, str(wl)) for wl in FILTERS])
        ax.tick_params(axis="x", labelrotation=90, labelsize=8)
    else:
        ax.set_xticklabels([str(wl) for wl in FILTERS])


def plot_matched_peak_overlay(grouped: dict[str, list[dict[str, Any]]]) -> str:
    samples = list(grouped)
    cols = 2
    rows_n = math.ceil(len(samples) / cols)
    fig, axes = plt.subplots(rows_n, cols, figsize=(15, 4.7 * rows_n))
    axes = np.asarray(axes).reshape(rows_n, cols)
    for ax in axes.ravel():
        ax.axis("off")
    for index, sample_id in enumerate(samples):
        rows = grouped[sample_id]
        ax1 = axes.ravel()[index]
        ax1.axis("on")
        xs = [float(row["filter_nm"]) for row in rows]
        camera = [float(row["camera_display_brightness_boosted"]) for row in rows]
        spectrometer = [float(row["spectrometer_display_intensity_boosted"]) for row in rows]
        add_peak_bands(ax1, rows)
        sx, sy = smooth_curve(xs, spectrometer)
        ax1.plot(sx, sy, color="#315f8c", linewidth=2.2, label="spectrometer peak guide")
        ax1.scatter(xs, spectrometer, color="#315f8c", marker="s", s=52, edgecolor="white", linewidth=0.7, label="spectrometer peaks", zorder=5)
        ax1.set_ylim(bottom=300)
        ax1.set_ylabel("Spectrometer peak intensity", color="#315f8c")
        ax1.tick_params(axis="y", labelcolor="#315f8c")
        ax1.grid(True, alpha=0.22)
        set_filter_axis(ax1, rows)
        ax2 = ax1.twinx()
        cx, cy = smooth_curve(xs, camera)
        ax2.plot(cx, cy, color="#f06d2f", linewidth=2.5, alpha=0.86, label="camera guide")
        ax2.scatter(xs, camera, color="#f06d2f", s=52, edgecolor="white", linewidth=0.7, label="camera brightness", zorder=6)
        ax2.set_ylim(0, 255)
        ax2.set_ylabel("Camera brightness (0-255)", color="#b04d22")
        ax2.tick_params(axis="y", labelcolor="#b04d22")
        ax1.set_title(short_sample_name(sample_id), fontsize=10)
        l1, lab1 = ax1.get_legend_handles_labels()
        l2, lab2 = ax2.get_legend_handles_labels()
        ax1.legend(l1 + l2, lab1 + lab2, fontsize=7, loc="upper left")
    fig.suptitle("Camera brightness vs matching spectrometer peaks", fontsize=16, y=0.995)
    fig.tight_layout(rect=(0, 0, 1, 0.975))
    out = GRAPH_DIR / "01_camera_vs_spectrometer_peak_overlay.png"
    fig.savefig(out, dpi=180)
    plt.close(fig)
    return str(out)


def plot_peak_offsets(rows: list[dict[str, Any]]) -> str:
    fig, ax = plt.subplots(figsize=(12, 6.8))
    samples = sorted({str(row["sample_id"]) for row in rows})
    sample_positions = {sample: idx for idx, sample in enumerate(samples)}
    for row in rows:
        sample = str(row["sample_id"])
        offset = as_float(row.get("spectrometer_peak_offset_from_filter_nm"))
        wavelength = int(row["filter_nm"])
        if offset is None:
            continue
        x = sample_positions[sample] + (FILTERS.index(wavelength) - 2.5) * 0.09
        color = "#287a46" if abs(offset) <= PEAK_ALIGNMENT_TOLERANCE_NM else "#c9443d"
        ax.scatter(x, offset, color=color, s=62, edgecolor="white", linewidth=0.8, zorder=4)
        ax.text(x, offset + (2 if offset >= 0 else -2), str(wavelength), fontsize=7, ha="center", va="bottom" if offset >= 0 else "top")
    ax.axhline(0, color="#222222", linewidth=1)
    ax.axhspan(-PEAK_ALIGNMENT_TOLERANCE_NM, PEAK_ALIGNMENT_TOLERANCE_NM, color="#47a76a", alpha=0.09)
    ax.set_xticks(range(len(samples)))
    ax.set_xticklabels([short_sample_name(sample) for sample in samples], rotation=22, ha="right")
    ax.set_ylabel("Spectrometer peak offset from camera/filter band (nm)")
    ax.set_title("Peak alignment by filter: green zone means the spectrometer peak is close to the camera band")
    ax.grid(True, axis="y", alpha=0.25)
    fig.tight_layout()
    out = GRAPH_DIR / "02_peak_offset_by_filter.png"
    fig.savefig(out, dpi=180)
    plt.close(fig)
    return str(out)


def plot_camera_lines(grouped: dict[str, list[dict[str, Any]]]) -> str:
    fig, ax = plt.subplots(figsize=(11, 6.5))
    for sample, rows in grouped.items():
        xs = [float(row["filter_nm"]) for row in rows]
        ys = [float(row["camera_display_brightness_boosted"]) for row in rows]
        sx, sy = smooth_curve(xs, ys)
        ax.plot(sx, sy, linewidth=2.1, label=short_sample_name(sample))
        ax.scatter(xs, ys, s=42, edgecolor="white", linewidth=0.7)
    set_filter_axis(ax)
    ax.set_ylim(0, 255)
    ax.set_xlabel("Camera/filter wavelength (nm)")
    ax.set_ylabel("Camera leaf brightness (0-255)")
    ax.set_title("Camera brightness curves from the approved graph data")
    ax.grid(True, alpha=0.25)
    ax.legend(fontsize=8)
    fig.tight_layout()
    out = GRAPH_DIR / "03_camera_brightness_curves.png"
    fig.savefig(out, dpi=180)
    plt.close(fig)
    return str(out)


def plot_spectrometer_lines(grouped: dict[str, list[dict[str, Any]]]) -> str:
    fig, ax = plt.subplots(figsize=(11, 6.5))
    for sample, rows in grouped.items():
        xs = [float(row["filter_nm"]) for row in rows]
        ys = [float(row["spectrometer_display_intensity_boosted"]) for row in rows]
        sx, sy = smooth_curve(xs, ys)
        ax.plot(sx, sy, linewidth=2.1, label=short_sample_name(sample))
        ax.scatter(xs, ys, s=42, edgecolor="white", linewidth=0.7)
    set_filter_axis(ax)
    ax.set_ylim(bottom=300)
    ax.set_xlabel("Camera/filter wavelength (nm)")
    ax.set_ylabel("Spectrometer local peak intensity")
    ax.set_title("Spectrometer local peak curves from the approved graph data")
    ax.grid(True, alpha=0.25)
    ax.legend(fontsize=8)
    fig.tight_layout()
    out = GRAPH_DIR / "04_spectrometer_peak_curves.png"
    fig.savefig(out, dpi=180)
    plt.close(fig)
    return str(out)


def plot_scatter(rows: list[dict[str, Any]]) -> str:
    fig, ax = plt.subplots(figsize=(8.8, 7.0))
    colors = {532: "#2f7f4f", 556: "#7ba943", 680: "#ba4a3a", 725: "#8d4fb8", 850: "#315f8c", 940: "#555555"}
    for row in rows:
        wavelength = int(row["filter_nm"])
        camera = as_float(row.get("camera_display_brightness_boosted"))
        spectrometer = as_float(row.get("spectrometer_display_intensity_boosted"))
        if camera is None or spectrometer is None:
            continue
        ax.scatter(camera, spectrometer, s=62, color=colors.get(wavelength, "#777777"), edgecolor="white", linewidth=0.8)
        ax.text(camera + 1.2, spectrometer, str(wavelength), fontsize=7)
    ax.set_xlabel("Camera leaf brightness (0-255)")
    ax.set_ylabel("Spectrometer local peak intensity")
    ax.set_title("Camera brightness compared with matching spectrometer peaks")
    ax.grid(True, alpha=0.25)
    handles = [plt.Line2D([0], [0], marker="o", linestyle="", color=color, label=f"{wl} nm") for wl, color in colors.items()]
    ax.legend(handles=handles, ncol=3, fontsize=8)
    fig.tight_layout()
    out = GRAPH_DIR / "05_camera_vs_spectrometer_peak_scatter.png"
    fig.savefig(out, dpi=180)
    plt.close(fig)
    return str(out)


def make_gallery(graph_paths: list[str]) -> str:
    thumbs: list[Image.Image] = []
    for raw in graph_paths:
        path = Path(raw)
        with Image.open(path) as image:
            thumb = image.convert("RGB")
            thumb.thumbnail((690, 470))
            canvas = Image.new("RGB", (730, 550), "white")
            canvas.paste(thumb, ((730 - thumb.width) // 2, 18))
            draw = ImageDraw.Draw(canvas)
            draw.text((18, 512), path.name[:96], fill=(20, 20, 20))
            thumbs.append(canvas)
    cols = 2
    rows = math.ceil(len(thumbs) / cols)
    sheet = Image.new("RGB", (cols * 730, rows * 550), "white")
    for index, thumb in enumerate(thumbs):
        sheet.paste(thumb, ((index % cols) * 730, (index // cols) * 550))
    out = OUT_DIR / "grafice_ok_generated_gallery.jpg"
    sheet.save(out, quality=92)
    return str(out)


def copy_source_reference_graphs() -> None:
    target = OUT_DIR / "source_reference_graphs"
    if target.exists():
        shutil.rmtree(target)
    if SOURCE_GRAPHS.exists():
        shutil.copytree(SOURCE_GRAPHS, target)


def main() -> None:
    if OUT_DIR.exists():
        shutil.rmtree(OUT_DIR)
    GRAPH_DIR.mkdir(parents=True, exist_ok=True)
    rows = read_pairs()
    grouped = by_sample(rows)
    graph_paths = [
        plot_matched_peak_overlay(grouped),
        plot_peak_offsets(rows),
        plot_camera_lines(grouped),
        plot_spectrometer_lines(grouped),
        plot_scatter(rows),
    ]
    gallery = make_gallery(graph_paths)
    copy_source_reference_graphs()
    summary = {
        "source_folder": str(SOURCE_DIR),
        "source_csv": str(SOURCE_PAIRS),
        "output_folder": str(OUT_DIR),
        "method": "Generated from the approved grafice ok matched-pairs CSV. No source files were modified.",
        "peak_alignment_tolerance_nm": PEAK_ALIGNMENT_TOLERANCE_NM,
        "graphs": graph_paths,
        "gallery": gallery,
    }
    (OUT_DIR / "summary.json").write_text(json.dumps(summary, indent=2), encoding="utf-8")
    print(json.dumps(summary, indent=2))


if __name__ == "__main__":
    main()
