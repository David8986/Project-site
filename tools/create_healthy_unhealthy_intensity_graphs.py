"""Create raw intensity healthy vs unhealthy comparison graphs."""

from __future__ import annotations

import csv
import json
import math
import re
import shutil
from pathlib import Path
from typing import Any

import matplotlib.pyplot as plt
import numpy as np
from PIL import Image


DATA_ROOT = Path(r"C:\Users\david\OneDrive\Desktop\data analisys BACKUP 2026-05-22 - Copy")
OUT_DIR = Path(r"C:\Users\david\OneDrive\Desktop\healthy unhealthy intensity graphs")
GRAPH_DIR = OUT_DIR / "graphs"
BIN_WIDTH_NM = 10
MIN_WAVELENGTH_NM = 300.0
MAX_WAVELENGTH_NM = 1030.0
EPS = 1e-12


PAIRS = [
    (
        "in cutie\\Set frunze 1\\frunza verde",
        "in cutie\\Set frunze 1\\frunza nesanatoasa",
        "Set frunze 1",
    ),
    (
        "in cutie\\Set frunze 2\\sanatoasa",
        "in cutie\\Set frunze 2\\nesanatoasa",
        "Set frunze 2",
    ),
]


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


def read_spectrum(path: Path) -> tuple[np.ndarray, np.ndarray]:
    lines = path.read_text(encoding="utf-8", errors="ignore").splitlines()
    start = 0
    for index, line in enumerate(lines):
        if "Begin Spectral Data" in line:
            start = index + 1
            break
    pairs: list[tuple[float, float]] = []
    for line in lines[start:]:
        numbers = re.findall(r"[-+]?(?:\d*\.\d+|\d+)(?:[eE][-+]?\d+)?", line)
        if len(numbers) >= 2:
            pairs.append((float(numbers[0]), float(numbers[1])))
    if len(pairs) < 10:
        raise ValueError(f"Could not parse spectrum: {path}")
    data = np.asarray(pairs, dtype=float)
    return data[:, 0], data[:, 1]


def rel(path: Path) -> str:
    try:
        return str(path.relative_to(DATA_ROOT))
    except ValueError:
        return str(path)


def safe_name(text: str) -> str:
    return re.sub(r"[^A-Za-z0-9_-]+", "_", text).strip("_")


def short_name(sample_id: str) -> str:
    return sample_id.replace("in cutie\\", "")


def find_no_filter_leaf_spectra() -> dict[str, Path]:
    out: dict[str, Path] = {}
    indoor = DATA_ROOT / "in cutie"
    for path in sorted(indoor.rglob("*.txt")):
        if path.parent.name.lower() != "spectru":
            continue
        sample_dir = path.parent.parent
        sample_id = rel(sample_dir)
        lower_sample = sample_id.lower()
        if "referinta" in lower_sample or "refirinta" in lower_sample:
            continue
        if "fara" not in path.name.lower():
            continue
        out[sample_id] = path
    return out


def binned_intensity(path: Path) -> list[dict[str, float]]:
    wavelengths, intensities = read_spectrum(path)
    finite = (
        np.isfinite(wavelengths)
        & np.isfinite(intensities)
        & (wavelengths >= MIN_WAVELENGTH_NM)
        & (wavelengths <= MAX_WAVELENGTH_NM)
    )
    wavelengths = wavelengths[finite]
    intensities = intensities[finite]
    starts = np.floor(wavelengths / BIN_WIDTH_NM).astype(int) * BIN_WIDTH_NM
    rows: list[dict[str, float]] = []
    for start in sorted(set(int(value) for value in starts)):
        mask = starts == start
        rows.append(
            {
                "bin_start_nm": float(start),
                "bin_end_nm": float(start + BIN_WIDTH_NM),
                "bin_center_nm": float(np.mean(wavelengths[mask])),
                "intensity_median": float(np.median(intensities[mask])),
                "intensity_mean": float(np.mean(intensities[mask])),
                "intensity_std": float(np.std(intensities[mask])),
            }
        )
    return rows


def smooth_curve(xs: list[float], ys: list[float], points: int = 900, sigma_nm: float = 12.0) -> tuple[np.ndarray, np.ndarray]:
    x = np.asarray(xs, dtype=float)
    y = np.asarray(ys, dtype=float)
    order = np.argsort(x)
    x = x[order]
    y = y[order]
    dense_x = np.linspace(float(x.min()), float(x.max()), points)
    dense_y = np.interp(dense_x, x, y)
    dx = max(float(dense_x[1] - dense_x[0]), EPS)
    sigma_points = max(1.0, sigma_nm / dx)
    radius = int(max(4, round(sigma_points * 3)))
    grid = np.arange(-radius, radius + 1, dtype=float)
    kernel = np.exp(-0.5 * (grid / sigma_points) ** 2)
    kernel /= kernel.sum()
    padded = np.pad(dense_y, radius, mode="edge")
    smooth = np.convolve(padded, kernel, mode="same")[radius:-radius]
    return dense_x, smooth


def mean_in_range(rows: list[dict[str, Any]], start_nm: float, end_nm: float) -> float:
    values = [
        float(row["intensity_median"])
        for row in rows
        if start_nm <= float(row["bin_center_nm"]) < end_nm
    ]
    return float(np.mean(values)) if values else float("nan")


def percent_less(unhealthy: float, healthy: float) -> float:
    if abs(healthy) < EPS:
        return float("nan")
    return (healthy - unhealthy) / healthy * 100.0


def plot_pair(
    pair_name: str,
    healthy_id: str,
    unhealthy_id: str,
    healthy_rows: list[dict[str, Any]],
    unhealthy_rows: list[dict[str, Any]],
) -> str:
    fig, ax = plt.subplots(figsize=(11.8, 6.3))
    for sample_id, rows, color in [
        (healthy_id, healthy_rows, "#1f9d55"),
        (unhealthy_id, unhealthy_rows, "#d62728"),
    ]:
        x = [float(row["bin_center_nm"]) for row in rows]
        y = [float(row["intensity_median"]) for row in rows]
        sx, sy = smooth_curve(x, y)
        ax.plot(sx, sy, color=color, linewidth=2.7, label=short_name(sample_id))
        ax.scatter(x[::4], y[::4], color=color, s=14, alpha=0.35, edgecolor="none")
    ax.set_xlim(MIN_WAVELENGTH_NM, MAX_WAVELENGTH_NM)
    ax.set_xlabel("Wavelength (nm)")
    ax.set_ylabel("Spectrometer intensity")
    ax.grid(True, alpha=0.23)
    ax.legend()
    fig.tight_layout()
    out = GRAPH_DIR / f"{safe_name(pair_name)}_healthy_vs_unhealthy_intensity.png"
    fig.savefig(out, dpi=180)
    plt.close(fig)
    return str(out)


def matched_region_values(
    healthy_rows: list[dict[str, Any]],
    unhealthy_rows: list[dict[str, Any]],
    start_nm: float,
) -> tuple[np.ndarray, np.ndarray]:
    unhealthy_by_bin = {float(row["bin_start_nm"]): row for row in unhealthy_rows}
    healthy_values: list[float] = []
    unhealthy_values: list[float] = []
    for healthy_row in healthy_rows:
        if float(healthy_row["bin_center_nm"]) < start_nm:
            continue
        unhealthy_row = unhealthy_by_bin.get(float(healthy_row["bin_start_nm"]))
        if unhealthy_row is None:
            continue
        healthy_values.append(float(healthy_row["intensity_median"]))
        unhealthy_values.append(float(unhealthy_row["intensity_median"]))
    return np.asarray(healthy_values, dtype=float), np.asarray(unhealthy_values, dtype=float)


def plot_set_frunze_1_stats(
    healthy_id: str,
    unhealthy_id: str,
    healthy_rows: list[dict[str, Any]],
    unhealthy_rows: list[dict[str, Any]],
) -> str:
    healthy_750, unhealthy_750 = matched_region_values(healthy_rows, unhealthy_rows, 750.0)
    healthy_mean = float(np.mean(healthy_750))
    unhealthy_mean = float(np.mean(unhealthy_750))
    lower_percent = percent_less(unhealthy_mean, healthy_mean)

    fig, ax = plt.subplots(figsize=(11.8, 6.3))
    for sample_id, rows, color in [
        (healthy_id, healthy_rows, "#1f9d55"),
        (unhealthy_id, unhealthy_rows, "#d62728"),
    ]:
        x = [float(row["bin_center_nm"]) for row in rows]
        y = [float(row["intensity_median"]) for row in rows]
        sx, sy = smooth_curve(x, y)
        ax.plot(sx, sy, color=color, linewidth=2.7, label=short_name(sample_id))
        ax.scatter(x[::4], y[::4], color=color, s=14, alpha=0.35, edgecolor="none")

    stats_text = (
        "750+ nm statistics\n"
        f"healthy mean: {healthy_mean:.1f}\n"
        f"unhealthy mean: {unhealthy_mean:.1f}\n"
        f"unhealthy is {lower_percent:.1f}% lower"
    )
    ax.text(
        0.035,
        0.94,
        stats_text,
        transform=ax.transAxes,
        va="top",
        ha="left",
        fontsize=10.5,
        bbox={"boxstyle": "round,pad=0.35", "facecolor": "white", "edgecolor": "#cfcfcf", "alpha": 0.94},
    )
    ax.set_xlim(MIN_WAVELENGTH_NM, MAX_WAVELENGTH_NM)
    ax.set_xlabel("Wavelength (nm)")
    ax.set_ylabel("Spectrometer intensity")
    ax.grid(True, alpha=0.23)
    ax.legend()
    fig.tight_layout()
    out = GRAPH_DIR / "Set_frunze_1_healthy_vs_unhealthy_intensity_stats_750plus.png"
    fig.savefig(out, dpi=180)
    plt.close(fig)

    write_csv(
        OUT_DIR / "set_frunze_1_intensity_stats.csv",
        [
            {
                "region": "750_plus_to_1030",
                "healthy_mean_intensity": round(healthy_mean, 3),
                "unhealthy_mean_intensity": round(unhealthy_mean, 3),
                "unhealthy_less_than_healthy_percent": round(lower_percent, 3),
            }
        ],
    )
    paragraph = (
        f"In the 750+ nm region, the healthy leaf has an average intensity of {healthy_mean:.1f}, "
        f"while the unhealthy leaf has {unhealthy_mean:.1f}. This means the unhealthy leaf reflects "
        f"about {lower_percent:.1f}% less by raw spectrometer intensity."
    )
    (OUT_DIR / "set_frunze_1_750plus_statistical_paragraph.txt").write_text(paragraph, encoding="utf-8")
    return str(out)


def plot_all_pair_bars(summary_rows: list[dict[str, Any]]) -> str:
    labels = [row["pair"] for row in summary_rows]
    values = [float(row["unhealthy_less_than_healthy_percent_nir_750_940"]) for row in summary_rows]
    fig, ax = plt.subplots(figsize=(9.2, 5.2))
    ax.bar(labels, values, color="#d62728", alpha=0.8)
    ax.axhline(0, color="#333333", linewidth=1.0)
    ax.set_ylabel("Unhealthy lower than healthy in NIR (%)")
    ax.grid(True, axis="y", alpha=0.24)
    fig.tight_layout()
    out = GRAPH_DIR / "unhealthy_less_percent_intensity.png"
    fig.savefig(out, dpi=180)
    plt.close(fig)
    return str(out)


def make_gallery(graph_paths: list[str]) -> str:
    thumbs: list[Image.Image] = []
    for raw in graph_paths:
        path = Path(raw)
        with Image.open(path) as image:
            thumb = image.convert("RGB")
            thumb.thumbnail((700, 470))
            canvas = Image.new("RGB", (740, 520), "white")
            canvas.paste(thumb, ((740 - thumb.width) // 2, 18))
            thumbs.append(canvas)
    cols = 2
    rows = int(math.ceil(len(thumbs) / cols))
    sheet = Image.new("RGB", (cols * 740, rows * 520), "white")
    for index, thumb in enumerate(thumbs):
        sheet.paste(thumb, ((index % cols) * 740, (index // cols) * 520))
    out = OUT_DIR / "healthy_unhealthy_intensity_gallery.jpg"
    sheet.save(out, quality=92)
    return str(out)


def main() -> None:
    if OUT_DIR.exists():
        shutil.rmtree(OUT_DIR)
    GRAPH_DIR.mkdir(parents=True, exist_ok=True)
    spectra = find_no_filter_leaf_spectra()
    sample_rows: dict[str, list[dict[str, Any]]] = {}
    all_rows: list[dict[str, Any]] = []
    for sample_id, path in spectra.items():
        rows = binned_intensity(path)
        for row in rows:
            row.update({"sample_id": sample_id, "spectru_file": rel(path)})
            all_rows.append(row.copy())
        sample_rows[sample_id] = rows

    summary_rows: list[dict[str, Any]] = []
    graph_paths: list[str] = []
    for healthy_id, unhealthy_id, pair_name in PAIRS:
        if healthy_id not in sample_rows or unhealthy_id not in sample_rows:
            continue
        healthy_rows = sample_rows[healthy_id]
        unhealthy_rows = sample_rows[unhealthy_id]
        h_visible = mean_in_range(healthy_rows, 400, 700)
        u_visible = mean_in_range(unhealthy_rows, 400, 700)
        h_nir = mean_in_range(healthy_rows, 750, 940)
        u_nir = mean_in_range(unhealthy_rows, 750, 940)
        h_whole = mean_in_range(healthy_rows, 300, 1000)
        u_whole = mean_in_range(unhealthy_rows, 300, 1000)
        summary_rows.append(
            {
                "pair": pair_name,
                "healthy_sample": healthy_id,
                "unhealthy_sample": unhealthy_id,
                "healthy_mean_intensity_visible_400_700": round(h_visible, 3),
                "unhealthy_mean_intensity_visible_400_700": round(u_visible, 3),
                "unhealthy_less_than_healthy_percent_visible_400_700": round(percent_less(u_visible, h_visible), 3),
                "healthy_mean_intensity_nir_750_940": round(h_nir, 3),
                "unhealthy_mean_intensity_nir_750_940": round(u_nir, 3),
                "unhealthy_less_than_healthy_percent_nir_750_940": round(percent_less(u_nir, h_nir), 3),
                "healthy_mean_intensity_whole_300_1000": round(h_whole, 3),
                "unhealthy_mean_intensity_whole_300_1000": round(u_whole, 3),
                "unhealthy_less_than_healthy_percent_whole_300_1000": round(percent_less(u_whole, h_whole), 3),
            }
        )
        graph_paths.append(plot_pair(pair_name, healthy_id, unhealthy_id, healthy_rows, unhealthy_rows))
        if pair_name == "Set frunze 1":
            graph_paths.append(plot_set_frunze_1_stats(healthy_id, unhealthy_id, healthy_rows, unhealthy_rows))

    graph_paths.append(plot_all_pair_bars(summary_rows))
    gallery = make_gallery(graph_paths)

    paragraph_rows = []
    for row in summary_rows:
        paragraph_rows.append(
            f"{row['pair']}: In the 750-940 nm NIR region, the unhealthy leaf has "
            f"{row['unhealthy_mean_intensity_nir_750_940']} intensity compared with "
            f"{row['healthy_mean_intensity_nir_750_940']} for the healthy leaf, meaning it reflects "
            f"{row['unhealthy_less_than_healthy_percent_nir_750_940']}% less by raw spectrometer intensity."
        )
    paragraph = "\n".join(paragraph_rows)
    (OUT_DIR / "short_paragraph.txt").write_text(paragraph, encoding="utf-8")
    write_csv(OUT_DIR / "leaf_intensity_10nm.csv", all_rows)
    write_csv(OUT_DIR / "healthy_unhealthy_intensity_summary.csv", summary_rows)
    summary = {
        "output_folder": str(OUT_DIR),
        "graphs": graph_paths,
        "gallery": gallery,
        "csv_files": {
            "intensity_10nm": str(OUT_DIR / "leaf_intensity_10nm.csv"),
            "summary": str(OUT_DIR / "healthy_unhealthy_intensity_summary.csv"),
            "paragraph": str(OUT_DIR / "short_paragraph.txt"),
        },
        "summary_rows": summary_rows,
        "paragraph": paragraph,
    }
    (OUT_DIR / "summary.json").write_text(json.dumps(summary, indent=2), encoding="utf-8")
    print(json.dumps(summary, indent=2))


if __name__ == "__main__":
    main()
