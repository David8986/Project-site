"""Create healthy vs unhealthy reflectance comparison graphs."""

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
from PIL import Image, ImageDraw


DATA_ROOT = Path(r"C:\Users\david\OneDrive\Desktop\data analisys BACKUP 2026-05-22 - Copy")
OUT_DIR = Path(r"C:\Users\david\OneDrive\Desktop\healthy unhealthy reflectance graphs")
GRAPH_DIR = OUT_DIR / "graphs"
MIN_WAVELENGTH_NM = 300.0
MAX_WAVELENGTH_NM = 1030.0
BIN_WIDTH_NM = 10
EPS = 1e-12

COLORS = {
    "healthy": "#1f9d55",
    "unhealthy": "#d62728",
    "healthy_yellow": "#9467bd",
}


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


def condition(sample_id: str) -> str:
    lower = sample_id.lower()
    if "nesan" in lower:
        return "unhealthy"
    if "galbena" in lower:
        return "healthy_yellow"
    return "healthy"


def broad_condition(sample_id: str) -> str:
    return "unhealthy" if condition(sample_id) == "unhealthy" else "healthy"


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


def find_reference_file(folder: Path, tokens: list[str]) -> Path:
    candidates = [path for path in folder.rglob("*.txt") if all(token in path.name.lower() for token in tokens)]
    if not candidates:
        raise FileNotFoundError(f"Could not find reference in {folder} with tokens {tokens}")
    return sorted(candidates, key=lambda path: len(path.name))[0]


def smooth_curve(xs: np.ndarray, ys: np.ndarray, points: int = 1000, sigma_nm: float = 10.0) -> tuple[np.ndarray, np.ndarray]:
    finite = np.isfinite(xs) & np.isfinite(ys)
    x = xs[finite]
    y = ys[finite]
    if x.size < 4:
        return x, y
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


def binned_median(wavelengths: np.ndarray, values: np.ndarray) -> list[dict[str, float]]:
    finite = (
        np.isfinite(wavelengths)
        & np.isfinite(values)
        & (wavelengths >= MIN_WAVELENGTH_NM)
        & (wavelengths <= MAX_WAVELENGTH_NM)
    )
    wavelengths = wavelengths[finite]
    values = values[finite]
    starts = np.floor(wavelengths / BIN_WIDTH_NM).astype(int) * BIN_WIDTH_NM
    rows: list[dict[str, float]] = []
    for start in sorted(set(int(x) for x in starts)):
        mask = starts == start
        rows.append(
            {
                "bin_start_nm": float(start),
                "bin_end_nm": float(start + BIN_WIDTH_NM),
                "bin_center_nm": float(np.mean(wavelengths[mask])),
                "reflectance_median": float(np.median(values[mask])),
                "reflectance_mean": float(np.mean(values[mask])),
                "reflectance_std": float(np.std(values[mask])),
            }
        )
    return rows


def compute_leaf_reflectance(
    leaf_path: Path,
    white_wavelengths: np.ndarray,
    white_intensities: np.ndarray,
    dark_wavelengths: np.ndarray,
    dark_intensities: np.ndarray,
) -> list[dict[str, float]]:
    wavelengths, leaf = read_spectrum(leaf_path)
    finite = (
        np.isfinite(wavelengths)
        & np.isfinite(leaf)
        & (wavelengths >= MIN_WAVELENGTH_NM)
        & (wavelengths <= MAX_WAVELENGTH_NM)
    )
    wavelengths = wavelengths[finite]
    leaf = leaf[finite]
    white = np.interp(wavelengths, white_wavelengths, white_intensities)
    dark = np.interp(wavelengths, dark_wavelengths, dark_intensities)
    denominator = white - dark
    valid = np.abs(denominator) > 10.0
    reflectance = np.full_like(leaf, np.nan, dtype=float)
    reflectance[valid] = (leaf[valid] - dark[valid]) / denominator[valid]
    return binned_median(wavelengths, reflectance)


def index_by_wavelength(rows: list[dict[str, Any]], field: str) -> dict[int, float]:
    return {int(round(float(row["bin_start_nm"]))): float(row[field]) for row in rows if row.get(field) not in ("", None)}


def percent_change(new_value: float, base_value: float) -> float:
    if abs(base_value) < EPS:
        return float("nan")
    return (new_value - base_value) / abs(base_value) * 100.0


def mean_in_range(rows: list[dict[str, Any]], start_nm: float, end_nm: float, field: str = "reflectance_median") -> float:
    vals = [
        float(row[field])
        for row in rows
        if start_nm <= float(row["bin_center_nm"]) < end_nm and np.isfinite(float(row[field]))
    ]
    return float(np.mean(vals)) if vals else float("nan")


def plot_group_reflectance(group_rows: dict[str, list[dict[str, Any]]]) -> str:
    fig, ax = plt.subplots(figsize=(12.3, 6.7))
    for group, rows in group_rows.items():
        x = np.asarray([float(row["bin_center_nm"]) for row in rows])
        y = np.asarray([float(row["reflectance_median"]) for row in rows])
        sx, sy = smooth_curve(x, y)
        ax.plot(sx, sy, color=COLORS[group], linewidth=2.6, label=f"{group} mean reflectance")
        ax.scatter(x[::4], y[::4], color=COLORS[group], s=14, alpha=0.35, edgecolor="none")
    ax.axvspan(400, 700, color="#eaf5ee", alpha=0.45, linewidth=0)
    ax.axvspan(700, 750, color="#f7efd7", alpha=0.45, linewidth=0)
    ax.axvspan(750, 1000, color="#f4e8e8", alpha=0.38, linewidth=0)
    ax.set_xlim(MIN_WAVELENGTH_NM, MAX_WAVELENGTH_NM)
    ax.set_xlabel("Wavelength (nm)")
    ax.set_ylabel("Relative reflectance (white/dark corrected)")
    ax.set_title("Healthy vs unhealthy leaves: average spectrometer reflectance")
    ax.grid(True, alpha=0.24)
    ax.legend()
    fig.tight_layout()
    out = GRAPH_DIR / "healthy_vs_unhealthy_mean_reflectance.png"
    fig.savefig(out, dpi=180)
    plt.close(fig)
    return str(out)


def plot_percent_difference(group_rows: dict[str, list[dict[str, Any]]]) -> str:
    healthy = index_by_wavelength(group_rows["healthy"], "reflectance_median")
    unhealthy = index_by_wavelength(group_rows["unhealthy"], "reflectance_median")
    starts = sorted(set(healthy) & set(unhealthy))
    xs = np.asarray([start + BIN_WIDTH_NM / 2 for start in starts], dtype=float)
    diffs = np.asarray([percent_change(healthy[start], unhealthy[start]) for start in starts], dtype=float)
    sx, sy = smooth_curve(xs, diffs, sigma_nm=13.0)
    fig, ax = plt.subplots(figsize=(12.3, 5.9))
    ax.axhline(0, color="#333333", linewidth=1.0)
    ax.fill_between(sx, 0, sy, where=sy >= 0, color=COLORS["healthy"], alpha=0.25, interpolate=True, label="healthy higher")
    ax.fill_between(sx, 0, sy, where=sy < 0, color=COLORS["unhealthy"], alpha=0.25, interpolate=True, label="healthy lower")
    ax.plot(sx, sy, color="#263238", linewidth=2.1)
    ax.scatter(xs[::3], diffs[::3], color="#263238", s=14, alpha=0.45, edgecolor="none")
    ax.set_xlim(MIN_WAVELENGTH_NM, MAX_WAVELENGTH_NM)
    ax.set_xlabel("Wavelength (nm)")
    ax.set_ylabel("Healthy vs unhealthy difference (%)")
    ax.set_title("How much more or less reflectance the healthy leaves have")
    ax.grid(True, alpha=0.24)
    ax.legend()
    fig.tight_layout()
    out = GRAPH_DIR / "healthy_vs_unhealthy_percent_difference.png"
    fig.savefig(out, dpi=180)
    plt.close(fig)
    return str(out)


def plot_pairwise(sample_rows: dict[str, list[dict[str, Any]]]) -> list[str]:
    pairs = [
        (
            "in cutie\\Set frunze 1\\frunza verde",
            "in cutie\\Set frunze 1\\frunza nesanatoasa",
            "Set frunze 1: healthy green vs unhealthy",
        ),
        (
            "in cutie\\Set frunze 2\\sanatoasa",
            "in cutie\\Set frunze 2\\nesanatoasa",
            "Set frunze 2: healthy vs unhealthy",
        ),
    ]
    outs: list[str] = []
    for healthy_id, unhealthy_id, title in pairs:
        if healthy_id not in sample_rows or unhealthy_id not in sample_rows:
            continue
        fig, ax = plt.subplots(figsize=(11.7, 6.3))
        for sample_id, color, label in [
            (healthy_id, COLORS["healthy"], "healthy"),
            (unhealthy_id, COLORS["unhealthy"], "unhealthy"),
        ]:
            rows = sample_rows[sample_id]
            x = np.asarray([float(row["bin_center_nm"]) for row in rows])
            y = np.asarray([float(row["reflectance_median"]) for row in rows])
            sx, sy = smooth_curve(x, y)
            ax.plot(sx, sy, color=color, linewidth=2.55, label=f"{label}: {short_name(sample_id)}")
            ax.scatter(x[::4], y[::4], color=color, s=14, alpha=0.35, edgecolor="none")
        ax.set_xlim(MIN_WAVELENGTH_NM, MAX_WAVELENGTH_NM)
        ax.set_xlabel("Wavelength (nm)")
        ax.set_ylabel("Relative reflectance")
        ax.set_title(title)
        ax.grid(True, alpha=0.24)
        ax.legend()
        fig.tight_layout()
        out = GRAPH_DIR / f"pair_{safe_name(title)}.png"
        fig.savefig(out, dpi=180)
        plt.close(fig)
        outs.append(str(out))
    return outs


def plot_region_bars(region_rows: list[dict[str, Any]]) -> str:
    labels = [row["region"] for row in region_rows]
    healthy = [float(row["healthy_mean_reflectance"]) for row in region_rows]
    unhealthy = [float(row["unhealthy_mean_reflectance"]) for row in region_rows]
    pct = [float(row["healthy_vs_unhealthy_percent"]) for row in region_rows]
    x = np.arange(len(labels))
    fig, ax1 = plt.subplots(figsize=(11.4, 6.0))
    width = 0.36
    ax1.bar(x - width / 2, unhealthy, width, color=COLORS["unhealthy"], alpha=0.78, label="unhealthy")
    ax1.bar(x + width / 2, healthy, width, color=COLORS["healthy"], alpha=0.82, label="healthy")
    ax1.set_xticks(x)
    ax1.set_xticklabels(labels, rotation=12, ha="right")
    ax1.set_ylabel("Mean relative reflectance")
    ax1.grid(True, axis="y", alpha=0.24)
    ax2 = ax1.twinx()
    ax2.plot(x, pct, color="#263238", linewidth=2.1, marker="o", label="healthy difference %")
    ax2.axhline(0, color="#555555", linewidth=0.8)
    ax2.set_ylabel("Healthy vs unhealthy (%)")
    lines1, labels1 = ax1.get_legend_handles_labels()
    lines2, labels2 = ax2.get_legend_handles_labels()
    ax1.legend(lines1 + lines2, labels1 + labels2, loc="upper left")
    ax1.set_title("Reflectance by spectral region")
    fig.tight_layout()
    out = GRAPH_DIR / "healthy_vs_unhealthy_region_bars.png"
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
            thumb.thumbnail((690, 455))
            canvas = Image.new("RGB", (730, 525), "white")
            canvas.paste(thumb, ((730 - thumb.width) // 2, 18))
            draw = ImageDraw.Draw(canvas)
            draw.text((18, 490), path.name[:100], fill=(20, 20, 20))
            thumbs.append(canvas)
    cols = 2
    rows = int(math.ceil(len(thumbs) / cols))
    sheet = Image.new("RGB", (cols * 730, rows * 525), "white")
    for index, thumb in enumerate(thumbs):
        sheet.paste(thumb, ((index % cols) * 730, (index // cols) * 525))
    out = OUT_DIR / "healthy_unhealthy_reflectance_gallery.jpg"
    sheet.save(out, quality=92)
    return str(out)


def main() -> None:
    if OUT_DIR.exists():
        shutil.rmtree(OUT_DIR)
    GRAPH_DIR.mkdir(parents=True, exist_ok=True)

    white_path = find_reference_file(DATA_ROOT / "in cutie" / "Referinta alba", ["fara"])
    dark_path = find_reference_file(DATA_ROOT / "in cutie" / "Refirinta neagra", ["neagra", "fara"])
    white_w, white_i = read_spectrum(white_path)
    dark_w, dark_i = read_spectrum(dark_path)
    leaf_paths = find_no_filter_leaf_spectra()

    sample_rows: dict[str, list[dict[str, Any]]] = {}
    all_rows: list[dict[str, Any]] = []
    for sample_id, path in leaf_paths.items():
        rows = compute_leaf_reflectance(path, white_w, white_i, dark_w, dark_i)
        for row in rows:
            row.update(
                {
                    "sample_id": sample_id,
                    "leaf_condition": condition(sample_id),
                    "broad_condition": broad_condition(sample_id),
                    "spectru_file": rel(path),
                }
            )
            all_rows.append(row.copy())
        sample_rows[sample_id] = rows

    grouped: dict[str, list[dict[str, Any]]] = {}
    for group in ["healthy", "unhealthy"]:
        by_start: dict[int, list[float]] = {}
        for row in all_rows:
            if row["broad_condition"] != group:
                continue
            by_start.setdefault(int(row["bin_start_nm"]), []).append(float(row["reflectance_median"]))
        grouped[group] = [
            {
                "bin_start_nm": float(start),
                "bin_end_nm": float(start + BIN_WIDTH_NM),
                "bin_center_nm": float(start + BIN_WIDTH_NM / 2),
                "reflectance_median": float(np.nanmean(vals)),
                "sample_count": len(vals),
            }
            for start, vals in sorted(by_start.items())
        ]

    comparison_rows: list[dict[str, Any]] = []
    healthy_idx = index_by_wavelength(grouped["healthy"], "reflectance_median")
    unhealthy_idx = index_by_wavelength(grouped["unhealthy"], "reflectance_median")
    for start in sorted(set(healthy_idx) & set(unhealthy_idx)):
        h = healthy_idx[start]
        u = unhealthy_idx[start]
        comparison_rows.append(
            {
                "bin_start_nm": start,
                "bin_end_nm": start + BIN_WIDTH_NM,
                "healthy_mean_reflectance": round(h, 6),
                "unhealthy_mean_reflectance": round(u, 6),
                "healthy_minus_unhealthy": round(h - u, 6),
                "healthy_vs_unhealthy_percent": round(percent_change(h, u), 3),
            }
        )

    regions = [
        ("visible 400-700 nm", 400, 700),
        ("red edge 680-750 nm", 680, 750),
        ("NIR 750-940 nm", 750, 940),
        ("940 band 930-950 nm", 930, 950),
    ]
    region_rows: list[dict[str, Any]] = []
    for label, start, end in regions:
        h = mean_in_range(grouped["healthy"], start, end)
        u = mean_in_range(grouped["unhealthy"], start, end)
        region_rows.append(
            {
                "region": label,
                "healthy_mean_reflectance": round(h, 6),
                "unhealthy_mean_reflectance": round(u, 6),
                "healthy_minus_unhealthy": round(h - u, 6),
                "healthy_vs_unhealthy_percent": round(percent_change(h, u), 3),
            }
        )

    graph_paths = [
        plot_group_reflectance(grouped),
        plot_percent_difference(grouped),
        plot_region_bars(region_rows),
    ]
    graph_paths.extend(plot_pairwise(sample_rows))
    gallery = make_gallery(graph_paths)

    write_csv(OUT_DIR / "leaf_reflectance_10nm.csv", all_rows)
    write_csv(OUT_DIR / "healthy_unhealthy_reflectance_comparison.csv", comparison_rows)
    write_csv(OUT_DIR / "healthy_unhealthy_region_summary.csv", region_rows)
    summary = {
        "output_folder": str(OUT_DIR),
        "white_reference": str(white_path),
        "dark_reference": str(dark_path),
        "leaf_count": len(sample_rows),
        "method": "Reflectance = (leaf spectrum - black reference) / (white reference - black reference), binned by 10 nm median.",
        "graphs": graph_paths,
        "gallery": gallery,
        "csv_files": {
            "reflectance_10nm": str(OUT_DIR / "leaf_reflectance_10nm.csv"),
            "comparison": str(OUT_DIR / "healthy_unhealthy_reflectance_comparison.csv"),
            "region_summary": str(OUT_DIR / "healthy_unhealthy_region_summary.csv"),
        },
        "region_summary": region_rows,
    }
    (OUT_DIR / "summary.json").write_text(json.dumps(summary, indent=2), encoding="utf-8")
    print(json.dumps(summary, indent=2))


if __name__ == "__main__":
    main()
