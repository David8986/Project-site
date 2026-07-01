"""Recreate the Set frunze 1 two-panel spectrometer/camera graph without 750 nm highlighting."""

from __future__ import annotations

import csv
from pathlib import Path

import matplotlib.pyplot as plt
import numpy as np


OUT_DIR = Path(r"C:\Users\david\OneDrive\Desktop\spectru fara adjusted graphs")
GRAPH_DIR = OUT_DIR / "graphs"
SPECTRU_CSV = OUT_DIR / "spectru_fara_adjusted_values.csv"
CAMERA_CSV = OUT_DIR / "camera_filter_values.csv"

SAMPLES = [
    ("in cutie\\Set frunze 1\\frunza nesanatoasa", "#1f77b4"),
    ("in cutie\\Set frunze 1\\frunza verde", "#ff7f0e"),
]


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


def main() -> None:
    GRAPH_DIR.mkdir(parents=True, exist_ok=True)
    spectru_rows = read_rows(SPECTRU_CSV)
    camera_rows = read_rows(CAMERA_CSV)

    fig, axes = plt.subplots(1, 2, figsize=(17.2, 4.7), sharex=False)
    for ax, (sample_id, color) in zip(axes, SAMPLES):
        sample_spectru = [row for row in spectru_rows if row["sample_id"] == sample_id]
        sample_camera = [row for row in camera_rows if row["sample_id"] == sample_id]

        x = [float(row["bin_center_nm"]) for row in sample_spectru]
        y = [float(row["adjusted_display_intensity"]) for row in sample_spectru]
        smooth_x, smooth_y = smooth_curve(x, y)
        ax.plot(smooth_x, smooth_y, color=color, linewidth=2.0)
        ax.scatter(x, y, color=color, s=6, alpha=0.28, edgecolor="none")

        cam_x = np.asarray([float(row["filter_nm"]) for row in sample_camera], dtype=float)
        cam_raw = np.asarray([float(row["camera_band_display_median_0_255"]) for row in sample_camera], dtype=float)
        cam_y = scaled_camera_to_spectrum(cam_raw, np.asarray(y, dtype=float))
        cam_sx, cam_sy = smooth_curve(cam_x.tolist(), cam_y.tolist(), points=360, sigma_nm=18.0)
        ax.plot(cam_sx, cam_sy, color=color, linestyle="--", linewidth=1.8)
        ax.scatter(cam_x, cam_y, facecolor="white", edgecolor=color, linewidth=1.2, s=34, zorder=5)

        for wavelength, value in zip(cam_x, cam_y):
            ax.text(
                wavelength,
                value + 14,
                f"{int(round(wavelength))}",
                color=color,
                fontsize=7,
                ha="center",
                va="bottom",
                alpha=0.82,
            )

        ax.set_xlim(300, 1030)
        ax.set_xlabel("Wavelength (nm)")
        ax.set_ylabel("Spectrometer intensity")
        ax.grid(True, alpha=0.2)

    fig.tight_layout(w_pad=2.2)
    out = GRAPH_DIR / "set_frunze_1_clean_no_750_zone_two_panel.png"
    fig.savefig(out, dpi=220)
    plt.close(fig)
    print(out)


if __name__ == "__main__":
    main()
