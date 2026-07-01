"""Create one graph with only the two dotted camera-aligned curves from the Set frunze 1 panels."""

from __future__ import annotations

import csv
from pathlib import Path

import matplotlib.pyplot as plt
import numpy as np


OUT_DIR = Path(r"C:\Users\david\OneDrive\Desktop\spectru fara adjusted graphs")
GRAPH_DIR = OUT_DIR / "graphs"
SPECTRU_CSV = OUT_DIR / "spectru_fara_adjusted_values.csv"
CAMERA_CSV = OUT_DIR / "camera_filter_values.csv"

UNHEALTHY = "in cutie\\Set frunze 1\\frunza nesanatoasa"
HEALTHY = "in cutie\\Set frunze 1\\frunza verde"
SAMPLES = [
    (UNHEALTHY, "#1f77b4", "unhealthy"),
    (HEALTHY, "#ff7f0e", "healthy"),
]


def read_rows(path: Path) -> list[dict[str, str]]:
    with path.open("r", encoding="utf-8-sig", newline="") as handle:
        return list(csv.DictReader(handle))


def smooth_curve(xs: list[float], ys: list[float], points: int = 360, sigma_nm: float = 18.0) -> tuple[np.ndarray, np.ndarray]:
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


def nearest_value(xs: np.ndarray, ys: np.ndarray, target_nm: float) -> tuple[float, float]:
    index = int(np.argmin(np.abs(xs - target_nm)))
    return float(xs[index]), float(ys[index])


def main() -> None:
    GRAPH_DIR.mkdir(parents=True, exist_ok=True)
    spectru_rows = read_rows(SPECTRU_CSV)
    camera_rows = read_rows(CAMERA_CSV)

    curves: dict[str, dict[str, np.ndarray | str]] = {}
    fig, ax = plt.subplots(figsize=(11.8, 6.3))
    for sample_id, color, label in SAMPLES:
        sample_spectru = [row for row in spectru_rows if row["sample_id"] == sample_id]
        sample_camera = [row for row in camera_rows if row["sample_id"] == sample_id]
        spectrum_y = np.asarray([float(row["adjusted_display_intensity"]) for row in sample_spectru], dtype=float)
        cam_x = np.asarray([float(row["filter_nm"]) for row in sample_camera], dtype=float)
        cam_raw_display = np.asarray([float(row["camera_band_display_median_0_255"]) for row in sample_camera], dtype=float)
        cam_y = scaled_camera_to_spectrum(cam_raw_display, spectrum_y)
        smooth_x, smooth_y = smooth_curve(cam_x.tolist(), cam_y.tolist())
        curves[label] = {"x": smooth_x, "y": smooth_y, "color": color}

        ax.plot(smooth_x, smooth_y, color=color, linestyle="--", linewidth=2.6, label=label)
        ax.scatter(cam_x, cam_y, facecolor="white", edgecolor=color, linewidth=1.4, s=48, zorder=5)
        for wavelength, value in zip(cam_x, cam_y):
            ax.text(wavelength, value + 12, f"{int(round(wavelength))}", color=color, fontsize=8, ha="center")

    stats_bands = [725.0, 850.0, 940.0]
    unhealthy_values = [nearest_value(curves["unhealthy"]["x"], curves["unhealthy"]["y"], band)[1] for band in stats_bands]
    healthy_values = [nearest_value(curves["healthy"]["x"], curves["healthy"]["y"], band)[1] for band in stats_bands]
    unhealthy_mean = float(np.mean(unhealthy_values))
    healthy_mean = float(np.mean(healthy_values))
    lower_percent = (healthy_mean - unhealthy_mean) / healthy_mean * 100.0

    stats_text = (
        "700+ nm statistics\n"
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

    ax.set_xlim(510, 965)
    ax.set_xlabel("Wavelength (nm)")
    ax.set_ylabel("Camera brightness aligned to spectrometer scale")
    ax.grid(True, alpha=0.23)
    ax.legend()
    fig.tight_layout()

    graph = GRAPH_DIR / "set_frunze_1_dotted_only_same_curves_comparison.png"
    fig.savefig(graph, dpi=220)
    plt.close(fig)

    csv_path = OUT_DIR / "set_frunze_1_dotted_only_same_curves_comparison.csv"
    with csv_path.open("w", encoding="utf-8-sig", newline="") as handle:
        writer = csv.DictWriter(
            handle,
            fieldnames=[
                "unhealthy_nm",
                "unhealthy_aligned_camera_value",
                "healthy_nm",
                "healthy_aligned_camera_value",
                "healthy_mean_725_850_940",
                "unhealthy_mean_725_850_940",
                "unhealthy_lower_percent",
            ],
        )
        writer.writeheader()
        for band, unhealthy_value, healthy_value in zip(stats_bands, unhealthy_values, healthy_values):
            writer.writerow(
                {
                    "unhealthy_nm": round(band, 3),
                    "unhealthy_aligned_camera_value": round(unhealthy_value, 3),
                    "healthy_nm": round(band, 3),
                    "healthy_aligned_camera_value": round(healthy_value, 3),
                    "healthy_mean_725_850_940": round(healthy_mean, 3),
                    "unhealthy_mean_725_850_940": round(unhealthy_mean, 3),
                    "unhealthy_lower_percent": round(lower_percent, 3),
                }
            )
    print(graph)
    print(csv_path)
    print(stats_text)


if __name__ == "__main__":
    main()
