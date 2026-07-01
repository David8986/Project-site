"""Create Set frunze 2 healthy/unhealthy comparison graphs."""

from __future__ import annotations

import csv
from pathlib import Path

import matplotlib.pyplot as plt
import numpy as np


OUT_DIR = Path(r"C:\Users\david\OneDrive\Desktop\spectru fara adjusted graphs")
GRAPH_DIR = OUT_DIR / "graphs"
SPECTRU_CSV = OUT_DIR / "spectru_fara_adjusted_values.csv"
CAMERA_CSV = OUT_DIR / "camera_filter_values.csv"

HEALTHY = "in cutie\\Set frunze 2\\sanatoasa"
UNHEALTHY = "in cutie\\Set frunze 2\\nesanatoasa"
COLORS = {HEALTHY: "#ff7f0e", UNHEALTHY: "#1f77b4"}
LABELS = {HEALTHY: "healthy", UNHEALTHY: "unhealthy"}


def read_rows(path: Path) -> list[dict[str, str]]:
    with path.open("r", encoding="utf-8-sig", newline="") as handle:
        return list(csv.DictReader(handle))


def smooth_curve(xs: list[float], ys: list[float], points: int = 900, sigma_nm: float = 12.0) -> tuple[np.ndarray, np.ndarray]:
    x = np.asarray(xs, dtype=float)
    y = np.asarray(ys, dtype=float)
    order = np.argsort(x)
    x = x[order]
    y = y[order]
    dense_x = np.linspace(float(x.min()), float(x.max()), points)
    dense_y = np.interp(dense_x, x, y)
    dx = max(float(dense_x[1] - dense_x[0]), 1e-12)
    sigma_points = max(1.0, sigma_nm / dx)
    radius = int(max(4, round(sigma_points * 3)))
    grid = np.arange(-radius, radius + 1, dtype=float)
    kernel = np.exp(-0.5 * (grid / sigma_points) ** 2)
    kernel /= kernel.sum()
    padded = np.pad(dense_y, radius, mode="edge")
    smooth = np.convolve(padded, kernel, mode="same")[radius:-radius]
    return dense_x, smooth


def scaled_camera_to_spectrum(camera_values: np.ndarray, spectrum_values: np.ndarray) -> np.ndarray:
    cam_min = float(np.nanmin(camera_values))
    cam_max = float(np.nanmax(camera_values))
    spec_min = float(np.nanpercentile(spectrum_values, 18))
    spec_max = float(np.nanpercentile(spectrum_values, 92))
    if abs(cam_max - cam_min) < 1e-12:
        return np.full_like(camera_values, (spec_min + spec_max) / 2.0)
    return spec_min + (camera_values - cam_min) / (cam_max - cam_min) * (spec_max - spec_min)


def lower_stats_text(healthy_mean: float, unhealthy_mean: float) -> tuple[str, float, str]:
    pct = (healthy_mean - unhealthy_mean) / healthy_mean * 100.0
    direction = "lower" if pct >= 0 else "higher"
    return (
        "700+ nm statistics\n"
        f"healthy mean: {healthy_mean:.1f}\n"
        f"unhealthy mean: {unhealthy_mean:.1f}\n"
        f"unhealthy is {abs(pct):.1f}% {direction}"
    ), abs(pct), direction


def add_stats_box(ax: plt.Axes, text: str) -> None:
    ax.text(
        0.035,
        0.94,
        text,
        transform=ax.transAxes,
        va="top",
        ha="left",
        fontsize=10.5,
        bbox={"boxstyle": "round,pad=0.35", "facecolor": "white", "edgecolor": "#cfcfcf", "alpha": 0.94},
    )


def make_continuous(spectru_rows: list[dict[str, str]]) -> tuple[str, dict[str, float | str]]:
    fig, ax = plt.subplots(figsize=(11.8, 6.3))
    means: dict[str, float] = {}
    for sample_id in [HEALTHY, UNHEALTHY]:
        rows = [row for row in spectru_rows if row["sample_id"] == sample_id]
        x = [float(row["bin_center_nm"]) for row in rows]
        y = [float(row["adjusted_display_intensity"]) for row in rows]
        sx, sy = smooth_curve(x, y)
        ax.plot(sx, sy, color=COLORS[sample_id], linewidth=2.7, label=LABELS[sample_id])
        ax.scatter(x[::3], y[::3], color=COLORS[sample_id], s=13, alpha=0.35, edgecolor="none")
        means[sample_id] = float(np.mean([value for wavelength, value in zip(x, y) if wavelength >= 700.0]))

    text, pct, direction = lower_stats_text(means[HEALTHY], means[UNHEALTHY])
    add_stats_box(ax, text)
    ax.set_xlim(300, 1030)
    ax.set_xlabel("Wavelength (nm)")
    ax.set_ylabel("Spectrometer intensity")
    ax.grid(True, alpha=0.23)
    ax.legend()
    fig.tight_layout()
    graph = GRAPH_DIR / "set_frunze_2_continuous_spectrometer_comparison_700plus.png"
    fig.savefig(graph, dpi=200)
    plt.close(fig)
    return str(graph), {
        "graph": str(graph),
        "source": "continuous_spectrometer_curve",
        "healthy_mean": round(means[HEALTHY], 3),
        "unhealthy_mean": round(means[UNHEALTHY], 3),
        "unhealthy_percent": round(pct, 3),
        "direction": direction,
    }


def nearest_value(xs: np.ndarray, ys: np.ndarray, target_nm: float) -> float:
    index = int(np.argmin(np.abs(xs - target_nm)))
    return float(ys[index])


def make_dotted(spectru_rows: list[dict[str, str]], camera_rows: list[dict[str, str]]) -> tuple[str, dict[str, float | str]]:
    fig, ax = plt.subplots(figsize=(11.8, 6.3))
    curves: dict[str, tuple[np.ndarray, np.ndarray]] = {}
    for sample_id in [UNHEALTHY, HEALTHY]:
        sample_spectru = [row for row in spectru_rows if row["sample_id"] == sample_id]
        sample_camera = sorted(
            [row for row in camera_rows if row["sample_id"] == sample_id],
            key=lambda row: float(row["filter_nm"]),
        )
        spectrum_y = np.asarray([float(row["adjusted_display_intensity"]) for row in sample_spectru], dtype=float)
        cam_x = np.asarray([float(row["filter_nm"]) for row in sample_camera], dtype=float)
        cam_raw_display = np.asarray([float(row["camera_band_display_median_0_255"]) for row in sample_camera], dtype=float)
        cam_y = scaled_camera_to_spectrum(cam_raw_display, spectrum_y)
        sx, sy = smooth_curve(cam_x.tolist(), cam_y.tolist(), points=360, sigma_nm=18.0)
        curves[sample_id] = (sx, sy)

        ax.plot(sx, sy, color=COLORS[sample_id], linestyle="--", linewidth=2.6, label=LABELS[sample_id])
        ax.scatter(cam_x, cam_y, facecolor="white", edgecolor=COLORS[sample_id], linewidth=1.4, s=48, zorder=5)
        for wavelength, value in zip(cam_x, cam_y):
            ax.text(wavelength, value + 12, f"{int(round(wavelength))}", color=COLORS[sample_id], fontsize=8, ha="center")

    stats_bands = [725.0, 850.0, 940.0]
    healthy_mean = float(np.mean([nearest_value(*curves[HEALTHY], band) for band in stats_bands]))
    unhealthy_mean = float(np.mean([nearest_value(*curves[UNHEALTHY], band) for band in stats_bands]))
    text, pct, direction = lower_stats_text(healthy_mean, unhealthy_mean)
    add_stats_box(ax, text)
    ax.set_xlim(510, 965)
    ax.set_xlabel("Wavelength (nm)")
    ax.set_ylabel("Camera brightness aligned to spectrometer scale")
    ax.grid(True, alpha=0.23)
    ax.legend()
    fig.tight_layout()
    graph = GRAPH_DIR / "set_frunze_2_dotted_camera_comparison_725_850_940.png"
    fig.savefig(graph, dpi=220)
    plt.close(fig)
    return str(graph), {
        "graph": str(graph),
        "source": "dotted_camera_aligned_curve",
        "healthy_mean_725_850_940": round(healthy_mean, 3),
        "unhealthy_mean_725_850_940": round(unhealthy_mean, 3),
        "unhealthy_percent": round(pct, 3),
        "direction": direction,
    }


def main() -> None:
    GRAPH_DIR.mkdir(parents=True, exist_ok=True)
    spectru_rows = read_rows(SPECTRU_CSV)
    camera_rows = read_rows(CAMERA_CSV)
    graph1, stats1 = make_continuous(spectru_rows)
    graph2, stats2 = make_dotted(spectru_rows, camera_rows)
    csv_path = OUT_DIR / "set_frunze_2_healthy_unhealthy_graph_stats.csv"
    fieldnames: list[str] = []
    for row in [stats1, stats2]:
        for key in row:
            if key not in fieldnames:
                fieldnames.append(key)
    with csv_path.open("w", encoding="utf-8-sig", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames, extrasaction="ignore")
        writer.writeheader()
        writer.writerow(stats1)
        writer.writerow(stats2)
    print(graph1)
    print(graph2)
    print(csv_path)
    print(stats1)
    print(stats2)


if __name__ == "__main__":
    main()
