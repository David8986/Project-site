"""Create separate Set frunze 1 comparison graphs for spectrometer and camera curves."""

from __future__ import annotations

import csv
from pathlib import Path

import matplotlib.pyplot as plt
import numpy as np


OUT_DIR = Path(r"C:\Users\david\OneDrive\Desktop\spectru fara adjusted graphs")
GRAPH_DIR = OUT_DIR / "graphs"
SPECTRU_CSV = OUT_DIR / "spectru_fara_adjusted_values.csv"
CAMERA_CSV = OUT_DIR / "camera_filter_values.csv"

HEALTHY = "in cutie\\Set frunze 1\\frunza verde"
UNHEALTHY = "in cutie\\Set frunze 1\\frunza nesanatoasa"
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


def percent_difference(healthy_mean: float, unhealthy_mean: float) -> tuple[float, str]:
    value = (healthy_mean - unhealthy_mean) / healthy_mean * 100.0
    direction = "lower" if value >= 0 else "higher"
    return abs(value), direction


def stats_text(title: str, healthy_mean: float, unhealthy_mean: float, digits: int = 1) -> tuple[str, float, str]:
    diff, direction = percent_difference(healthy_mean, unhealthy_mean)
    number_format = f"{{:.{digits}f}}"
    return (
        f"{title}\n"
        f"healthy mean: {number_format.format(healthy_mean)}\n"
        f"unhealthy mean: {number_format.format(unhealthy_mean)}\n"
        f"unhealthy is {diff:.1f}% {direction}"
    ), diff, direction


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


def plot_spectrometer(spectru_rows: list[dict[str, str]]) -> tuple[str, dict[str, float | str]]:
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

    text, diff, direction = stats_text("spectrometer 700+ nm", means[HEALTHY], means[UNHEALTHY])
    add_stats_box(ax, text)
    ax.set_xlim(300, 1030)
    ax.set_xlabel("Wavelength (nm)")
    ax.set_ylabel("Spectrometer intensity")
    ax.grid(True, alpha=0.23)
    ax.legend()
    fig.tight_layout()
    out = GRAPH_DIR / "set_frunze_1_continuous_spectrometer_comparison_700plus.png"
    fig.savefig(out, dpi=200)
    plt.close(fig)
    return str(out), {
        "graph": str(out),
        "source": "continuous_spectrometer_curve",
        "region": "700_plus",
        "healthy_mean": round(means[HEALTHY], 3),
        "unhealthy_mean": round(means[UNHEALTHY], 3),
        "unhealthy_percent": round(diff, 3),
        "direction": direction,
    }


def plot_camera(camera_rows: list[dict[str, str]]) -> tuple[str, dict[str, float | str]]:
    fig, ax = plt.subplots(figsize=(11.8, 6.3))
    means: dict[str, float] = {}
    corrected_values_by_sample: dict[str, list[dict[str, float]]] = {}
    for sample_id in [HEALTHY, UNHEALTHY]:
        rows = [row for row in camera_rows if row["sample_id"] == sample_id]
        x = [float(row["filter_nm"]) for row in rows]
        raw_y = [float(row["camera_band_median_0_255"]) for row in rows]
        baseline_680 = next(value for wavelength, value in zip(x, raw_y) if abs(wavelength - 680.0) < 1.0)
        fara = 141.0 if sample_id == HEALTHY else 153.0
        y = [(value - baseline_680) / fara for value in raw_y]
        corrected_values_by_sample[sample_id] = [
            {"wavelength_nm": wavelength, "camera_nir_response": value}
            for wavelength, value in zip(x, y)
        ]
        means[sample_id] = float(np.mean([value for wavelength, value in zip(x, y) if wavelength >= 700.0]))
        ax.plot(
            x,
            y,
            color=COLORS[sample_id],
            linewidth=2.7,
            linestyle="--",
            marker="o",
            markersize=6,
            label=LABELS[sample_id],
        )

    text, diff, direction = stats_text("camera corrected 700+ nm", means[HEALTHY], means[UNHEALTHY], digits=3)
    add_stats_box(ax, text)
    ax.set_xlim(500, 970)
    ax.set_xlabel("Camera filter / wavelength (nm)")
    ax.set_ylabel("Corrected camera NIR response")
    ax.grid(True, alpha=0.23)
    ax.legend()
    fig.tight_layout()
    out = GRAPH_DIR / "set_frunze_1_dotted_camera_comparison_700plus.png"
    fig.savefig(out, dpi=200)
    plt.close(fig)

    corrected_csv = OUT_DIR / "set_frunze_1_corrected_camera_values_700plus.csv"
    rows_for_csv: list[dict[str, float | str]] = []
    for sample_id, values in corrected_values_by_sample.items():
        for row in values:
            rows_for_csv.append(
                {
                    "sample": LABELS[sample_id],
                    "wavelength_nm": row["wavelength_nm"],
                    "corrected_camera_nir_response": round(row["camera_nir_response"], 6),
                    "formula": "(camera_band_median_0_255 - camera_680_median_0_255) / camera_fara_median_0_255",
                }
            )
    with corrected_csv.open("w", encoding="utf-8-sig", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(rows_for_csv[0].keys()))
        writer.writeheader()
        writer.writerows(rows_for_csv)

    return str(out), {
        "graph": str(out),
        "source": "dotted_corrected_camera_curve",
        "region": "700_plus",
        "healthy_mean": round(means[HEALTHY], 3),
        "unhealthy_mean": round(means[UNHEALTHY], 3),
        "unhealthy_percent": round(diff, 3),
        "direction": direction,
    }


def write_summary(rows: list[dict[str, float | str]]) -> Path:
    out = OUT_DIR / "set_frunze_1_split_line_comparison_700plus.csv"
    with out.open("w", encoding="utf-8-sig", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(rows[0].keys()))
        writer.writeheader()
        writer.writerows(rows)
    return out


def main() -> None:
    GRAPH_DIR.mkdir(parents=True, exist_ok=True)
    spectru_graph, spectru_stats = plot_spectrometer(read_rows(SPECTRU_CSV))
    camera_graph, camera_stats = plot_camera(read_rows(CAMERA_CSV))
    summary_csv = write_summary([spectru_stats, camera_stats])
    print(spectru_graph)
    print(camera_graph)
    print(summary_csv)
    print(spectru_stats)
    print(camera_stats)


if __name__ == "__main__":
    main()
