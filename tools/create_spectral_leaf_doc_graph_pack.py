"""Create the graph pack needed for the Spectral Leaf document section."""

from __future__ import annotations

import csv
from pathlib import Path

import matplotlib.pyplot as plt
import numpy as np


SOURCE_DIR = Path(r"C:\Users\david\OneDrive\Desktop\spectru fara adjusted graphs")
OUT_DIR = Path(r"C:\Users\david\OneDrive\Desktop\Spectral Leaf graphs for document")
GRAPH_DIR = OUT_DIR / "graphs"
SPECTRU_CSV = SOURCE_DIR / "spectru_fara_adjusted_values.csv"
CAMERA_CSV = SOURCE_DIR / "camera_filter_values.csv"
BANDS_700_PLUS = np.asarray([725.0, 850.0, 940.0], dtype=float)

SETS = {
    "set_1": {
        "label": "Set frunze 1",
        "healthy": "in cutie\\Set frunze 1\\frunza verde",
        "unhealthy": "in cutie\\Set frunze 1\\frunza nesanatoasa",
    },
    "set_2": {
        "label": "Set frunze 2",
        "healthy": "in cutie\\Set frunze 2\\sanatoasa",
        "unhealthy": "in cutie\\Set frunze 2\\nesanatoasa",
    },
}
COLORS = {"healthy": "#ff7f0e", "unhealthy": "#1f77b4"}


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


def add_stats_box(ax: plt.Axes, text: str, x: float = 0.035, y: float = 0.94) -> None:
    ax.text(
        x,
        y,
        text,
        transform=ax.transAxes,
        va="top",
        ha="left",
        fontsize=10.0,
        bbox={"boxstyle": "round,pad=0.35", "facecolor": "white", "edgecolor": "#cfcfcf", "alpha": 0.94},
    )


class DataPack:
    def __init__(self) -> None:
        self.spectru_rows = read_rows(SPECTRU_CSV)
        self.camera_rows = read_rows(CAMERA_CSV)

    def spectrometer_curve(self, sample_id: str) -> tuple[np.ndarray, np.ndarray, np.ndarray, np.ndarray]:
        rows = [row for row in self.spectru_rows if row["sample_id"] == sample_id]
        x = np.asarray([float(row["bin_center_nm"]) for row in rows], dtype=float)
        y = np.asarray([float(row["adjusted_display_intensity"]) for row in rows], dtype=float)
        sx, sy = smooth_curve(x.tolist(), y.tolist())
        return x, y, sx, sy

    def camera_curve(self, sample_id: str) -> tuple[np.ndarray, np.ndarray, np.ndarray, np.ndarray]:
        _, spectrum_values, _, _ = self.spectrometer_curve(sample_id)
        rows = sorted(
            [row for row in self.camera_rows if row["sample_id"] == sample_id],
            key=lambda row: float(row["filter_nm"]),
        )
        x = np.asarray([float(row["filter_nm"]) for row in rows], dtype=float)
        raw_display = np.asarray([float(row["camera_band_display_median_0_255"]) for row in rows], dtype=float)
        y = scaled_camera_to_spectrum(raw_display, spectrum_values)
        sx, sy = smooth_curve(x.tolist(), y.tolist(), points=360, sigma_nm=18.0)
        return x, y, sx, sy


def values_at_bands(curve_x: np.ndarray, curve_y: np.ndarray) -> np.ndarray:
    return np.interp(BANDS_700_PLUS, curve_x, curve_y)


def lower_percent(healthy_values: np.ndarray, unhealthy_values: np.ndarray) -> tuple[float, float, float, str]:
    healthy_mean = float(np.mean(healthy_values))
    unhealthy_mean = float(np.mean(unhealthy_values))
    percent = (healthy_mean - unhealthy_mean) / healthy_mean * 100.0
    direction = "lower" if percent >= 0 else "higher"
    return healthy_mean, unhealthy_mean, abs(percent), direction


def method_stats(spec_values: np.ndarray, camera_values: np.ndarray) -> tuple[float, float]:
    corr = float(np.corrcoef(spec_values, camera_values)[0, 1])
    mape = float(np.mean(np.abs(spec_values - camera_values) / np.maximum(np.abs(spec_values), 1e-12)) * 100.0)
    return corr, mape


def make_method_validation_set1(data: DataPack) -> tuple[str, list[dict[str, float | str]]]:
    set_info = SETS["set_1"]
    fig, ax = plt.subplots(figsize=(11.8, 6.3))
    stat_rows: list[dict[str, float | str]] = []

    for condition in ["unhealthy", "healthy"]:
        sample_id = set_info[condition]
        color = COLORS[condition]
        x, y, sx, sy = data.spectrometer_curve(sample_id)
        cam_x, cam_y, cam_sx, cam_sy = data.camera_curve(sample_id)
        ax.plot(sx, sy, color=color, linewidth=2.6, label=f"{condition} spectrometer")
        ax.plot(cam_sx, cam_sy, color=color, linewidth=2.4, linestyle="--", label=f"{condition} camera")
        ax.scatter(cam_x, cam_y, facecolor="white", edgecolor=color, linewidth=1.2, s=34, zorder=6)

        spec_band_values = values_at_bands(sx, sy)
        camera_band_values = values_at_bands(cam_sx, cam_sy)
        corr, mape = method_stats(spec_band_values, camera_band_values)
        stat_rows.append(
            {
                "figure": "method_validation_set_1",
                "condition": condition,
                "camera_vs_spectrometer_correlation_725_850_940": round(corr, 3),
                "mean_absolute_percent_difference_725_850_940": round(mape, 3),
            }
        )

    box = (
        "camera vs spectrometer\n"
        f"blue r: {stat_rows[0]['camera_vs_spectrometer_correlation_725_850_940']}, diff: {stat_rows[0]['mean_absolute_percent_difference_725_850_940']}%\n"
        f"orange r: {stat_rows[1]['camera_vs_spectrometer_correlation_725_850_940']}, diff: {stat_rows[1]['mean_absolute_percent_difference_725_850_940']}%"
    )
    add_stats_box(ax, box)
    ax.set_xlim(300, 1030)
    ax.set_xlabel("Wavelength (nm)")
    ax.set_ylabel("Intensity / aligned camera signal")
    ax.grid(True, alpha=0.23)
    ax.legend(loc="lower right", ncol=2, fontsize=9)
    fig.tight_layout()
    out = GRAPH_DIR / "figure_1_set_1_camera_vs_spectrometer_overlay.png"
    fig.savefig(out, dpi=220)
    plt.close(fig)
    return str(out), stat_rows


def make_health_comparison(data: DataPack, set_key: str) -> tuple[str, list[dict[str, float | str]]]:
    set_info = SETS[set_key]
    fig, axes = plt.subplots(1, 2, figsize=(15.6, 6.1))
    stat_rows: list[dict[str, float | str]] = []

    # Left: spectrometer continuous.
    spec_values_by_condition: dict[str, np.ndarray] = {}
    for condition in ["healthy", "unhealthy"]:
        sample_id = set_info[condition]
        color = COLORS[condition]
        x, y, sx, sy = data.spectrometer_curve(sample_id)
        axes[0].plot(sx, sy, color=color, linewidth=2.6, label=condition)
        axes[0].scatter(x[::3], y[::3], color=color, s=12, alpha=0.32, edgecolor="none")
        spec_values_by_condition[condition] = values_at_bands(sx, sy)
    h_mean, u_mean, pct, direction = lower_percent(
        spec_values_by_condition["healthy"],
        spec_values_by_condition["unhealthy"],
    )
    add_stats_box(
        axes[0],
        "spectrometer 700+ nm\n"
        f"healthy mean: {h_mean:.1f}\n"
        f"unhealthy mean: {u_mean:.1f}\n"
        f"unhealthy is {pct:.1f}% {direction}",
    )
    stat_rows.append(
        {
            "figure": f"{set_key}_health_comparison",
            "source": "spectrometer",
            "healthy_mean_725_850_940": round(h_mean, 3),
            "unhealthy_mean_725_850_940": round(u_mean, 3),
            "unhealthy_percent": round(pct, 3),
            "direction": direction,
        }
    )
    axes[0].set_xlim(300, 1030)
    axes[0].set_xlabel("Wavelength (nm)")
    axes[0].set_ylabel("Spectrometer intensity")
    axes[0].grid(True, alpha=0.23)
    axes[0].legend(loc="lower right")

    # Right: camera dotted.
    camera_values_by_condition: dict[str, np.ndarray] = {}
    for condition in ["unhealthy", "healthy"]:
        sample_id = set_info[condition]
        color = COLORS[condition]
        cam_x, cam_y, cam_sx, cam_sy = data.camera_curve(sample_id)
        axes[1].plot(cam_sx, cam_sy, color=color, linewidth=2.6, linestyle="--", label=condition)
        axes[1].scatter(cam_x, cam_y, facecolor="white", edgecolor=color, linewidth=1.2, s=38, zorder=6)
        for wavelength, value in zip(cam_x, cam_y):
            axes[1].text(wavelength, value + 10, f"{int(round(wavelength))}", color=color, fontsize=7, ha="center")
        camera_values_by_condition[condition] = values_at_bands(cam_sx, cam_sy)
    h_mean, u_mean, pct, direction = lower_percent(
        camera_values_by_condition["healthy"],
        camera_values_by_condition["unhealthy"],
    )
    add_stats_box(
        axes[1],
        "camera 700+ nm\n"
        f"healthy mean: {h_mean:.1f}\n"
        f"unhealthy mean: {u_mean:.1f}\n"
        f"unhealthy is {pct:.1f}% {direction}",
    )
    stat_rows.append(
        {
            "figure": f"{set_key}_health_comparison",
            "source": "camera",
            "healthy_mean_725_850_940": round(h_mean, 3),
            "unhealthy_mean_725_850_940": round(u_mean, 3),
            "unhealthy_percent": round(pct, 3),
            "direction": direction,
        }
    )
    axes[1].set_xlim(510, 965)
    axes[1].set_xlabel("Wavelength (nm)")
    axes[1].set_ylabel("Camera brightness aligned to spectrometer scale")
    axes[1].grid(True, alpha=0.23)
    axes[1].legend(loc="lower right")

    fig.tight_layout(w_pad=2.0)
    out = GRAPH_DIR / f"figure_2_{set_key}_health_comparison_side_by_side.png"
    fig.savefig(out, dpi=220)
    plt.close(fig)
    return str(out), stat_rows


def write_summary(rows: list[dict[str, float | str]]) -> str:
    out = OUT_DIR / "doc_graph_stats_summary.csv"
    headers: list[str] = []
    for row in rows:
        for key in row:
            if key not in headers:
                headers.append(key)
    with out.open("w", encoding="utf-8-sig", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=headers, extrasaction="ignore")
        writer.writeheader()
        writer.writerows(rows)
    return str(out)


def main() -> None:
    GRAPH_DIR.mkdir(parents=True, exist_ok=True)
    data = DataPack()
    stats: list[dict[str, float | str]] = []
    graph_paths: list[str] = []

    graph, rows = make_method_validation_set1(data)
    graph_paths.append(graph)
    stats.extend(rows)

    for set_key in ["set_1", "set_2"]:
        graph, rows = make_health_comparison(data, set_key)
        graph_paths.append(graph)
        stats.extend(rows)

    summary = write_summary(stats)
    print("Graphs:")
    for graph in graph_paths:
        print(graph)
    print("Stats:")
    for row in stats:
        print(row)
    print(summary)


if __name__ == "__main__":
    main()
