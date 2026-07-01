"""Create a Set frunze 1 healthy/unhealthy graph using camera band medians only."""

from __future__ import annotations

import csv
from pathlib import Path

import matplotlib.pyplot as plt
import numpy as np


ROOT = Path(r"C:\Users\david\OneDrive\Desktop\Archive\Projects\CodeX")
SOURCE_CSV = ROOT / "outputs" / "spectrometer_camera_no_afara_graphs" / "camera_spectrometer_comparison_indoor_only.csv"
OUT_DIR = Path(r"C:\Users\david\OneDrive\Desktop\healthy unhealthy intensity graphs")
GRAPH_DIR = OUT_DIR / "graphs"
HEALTHY = r"in cutie\Set frunze 1\frunza verde"
UNHEALTHY = r"in cutie\Set frunze 1\frunza nesanatoasa"


def short_name(sample_id: str) -> str:
    return sample_id.replace(r"in cutie\\", "").replace("in cutie\\", "")


def read_camera_rows() -> dict[str, list[dict[str, float]]]:
    rows_by_sample = {HEALTHY: [], UNHEALTHY: []}
    with SOURCE_CSV.open("r", encoding="utf-8-sig", newline="") as handle:
        reader = csv.DictReader(handle)
        for row in reader:
            sample_id = row["sample_id"]
            if sample_id not in rows_by_sample:
                continue
            rows_by_sample[sample_id].append(
                {
                    "filter_nm": float(row["filter_nm"]),
                    "raw_median_0_1": float(row["camera_raw_value_median"]),
                    "raw_median_0_255": float(row["camera_raw_value_median"]) * 255.0,
                }
            )
    for rows in rows_by_sample.values():
        rows.sort(key=lambda row: row["filter_nm"])
    return rows_by_sample


def write_stats_csv(path: Path, stats: dict[str, float | str]) -> None:
    with path.open("w", encoding="utf-8-sig", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(stats.keys()))
        writer.writeheader()
        writer.writerow(stats)


def main() -> None:
    GRAPH_DIR.mkdir(parents=True, exist_ok=True)
    rows_by_sample = read_camera_rows()
    healthy_rows = rows_by_sample[HEALTHY]
    unhealthy_rows = rows_by_sample[UNHEALTHY]

    healthy_700 = [row["raw_median_0_255"] for row in healthy_rows if row["filter_nm"] >= 700.0]
    unhealthy_700 = [row["raw_median_0_255"] for row in unhealthy_rows if row["filter_nm"] >= 700.0]
    healthy_mean = float(np.mean(healthy_700))
    unhealthy_mean = float(np.mean(unhealthy_700))
    difference_percent = (unhealthy_mean - healthy_mean) / healthy_mean * 100.0
    comparison_word = "higher" if difference_percent >= 0 else "lower"

    fig, ax = plt.subplots(figsize=(11.8, 6.3))
    for sample_id, color in [(HEALTHY, "#1f9d55"), (UNHEALTHY, "#d62728")]:
        rows = rows_by_sample[sample_id]
        xs = [row["filter_nm"] for row in rows]
        ys = [row["raw_median_0_255"] for row in rows]
        ax.plot(xs, ys, color=color, linewidth=2.7, marker="o", markersize=6, label=short_name(sample_id))

    stats_text = (
        "camera 700+ nm statistics\n"
        f"healthy mean: {healthy_mean:.1f}\n"
        f"unhealthy mean: {unhealthy_mean:.1f}\n"
        f"unhealthy is {abs(difference_percent):.1f}% {comparison_word}"
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
    ax.set_xlim(500, 970)
    ax.set_xlabel("Camera filter / wavelength (nm)")
    ax.set_ylabel("Camera median brightness (0-255)")
    ax.grid(True, alpha=0.23)
    ax.legend()
    fig.tight_layout()

    graph_path = GRAPH_DIR / "Set_frunze_1_healthy_vs_unhealthy_camera_stats_700plus.png"
    fig.savefig(graph_path, dpi=180)
    plt.close(fig)

    stats = {
        "region": "camera_700_plus",
        "healthy_mean_camera_median_0_255": round(healthy_mean, 3),
        "unhealthy_mean_camera_median_0_255": round(unhealthy_mean, 3),
        "unhealthy_percent_relative_to_healthy": round(difference_percent, 3),
        "comparison": comparison_word,
    }
    write_stats_csv(OUT_DIR / "set_frunze_1_camera_700plus_stats.csv", stats)
    print(graph_path)
    print(stats_text)


if __name__ == "__main__":
    main()
