"""Compare Set frunze 1 dotted camera peak regions directly."""

from __future__ import annotations

import csv
from pathlib import Path

import matplotlib.pyplot as plt


OUT_DIR = Path(r"C:\Users\david\OneDrive\Desktop\spectru fara adjusted graphs")
GRAPH_DIR = OUT_DIR / "graphs"
CAMERA_CSV = OUT_DIR / "camera_filter_values.csv"

HEALTHY = "in cutie\\Set frunze 1\\frunza verde"
UNHEALTHY = "in cutie\\Set frunze 1\\frunza nesanatoasa"
COLORS = {HEALTHY: "#1f9d55", UNHEALTHY: "#d62728"}


def read_rows() -> list[dict[str, str]]:
    with CAMERA_CSV.open("r", encoding="utf-8-sig", newline="") as handle:
        return list(csv.DictReader(handle))


def nearest(rows: list[dict[str, str]], target_nm: float) -> dict[str, str]:
    return min(rows, key=lambda row: abs(float(row["filter_nm"]) - target_nm))


def main() -> None:
    GRAPH_DIR.mkdir(parents=True, exist_ok=True)
    rows = read_rows()
    by_sample = {
        sample: sorted([row for row in rows if row["sample_id"] == sample], key=lambda row: float(row["filter_nm"]))
        for sample in [UNHEALTHY, HEALTHY]
    }

    unhealthy_peak = nearest(by_sample[UNHEALTHY], 650.0)
    healthy_peak = nearest(by_sample[HEALTHY], 750.0)
    unhealthy_value = float(unhealthy_peak["camera_band_median_0_255"])
    healthy_value = float(healthy_peak["camera_band_median_0_255"])
    lower_percent = (healthy_value - unhealthy_value) / healthy_value * 100.0

    fig, ax = plt.subplots(figsize=(11.8, 6.3))
    for sample, label in [(UNHEALTHY, "unhealthy"), (HEALTHY, "healthy")]:
        sample_rows = by_sample[sample]
        x = [float(row["filter_nm"]) for row in sample_rows]
        y = [float(row["camera_band_median_0_255"]) for row in sample_rows]
        ax.plot(x, y, color=COLORS[sample], linewidth=2.7, linestyle="--", marker="o", markersize=6, label=label)

    ax.scatter(
        [float(unhealthy_peak["filter_nm"]), float(healthy_peak["filter_nm"])],
        [unhealthy_value, healthy_value],
        s=120,
        facecolor="white",
        edgecolor=[COLORS[UNHEALTHY], COLORS[HEALTHY]],
        linewidth=2.4,
        zorder=5,
    )

    stats_text = (
        "camera dotted peak comparison\n"
        f"unhealthy peak: {unhealthy_value:.1f} at {float(unhealthy_peak['filter_nm']):.0f} nm\n"
        f"healthy peak: {healthy_value:.1f} at {float(healthy_peak['filter_nm']):.0f} nm\n"
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
    ax.set_xlim(500, 970)
    ax.set_xlabel("Camera filter / wavelength (nm)")
    ax.set_ylabel("Camera median brightness (0-255)")
    ax.grid(True, alpha=0.23)
    ax.legend()
    fig.tight_layout()

    graph = GRAPH_DIR / "set_frunze_1_dotted_camera_peak_comparison.png"
    fig.savefig(graph, dpi=200)
    plt.close(fig)

    csv_path = OUT_DIR / "set_frunze_1_dotted_camera_peak_comparison.csv"
    with csv_path.open("w", encoding="utf-8-sig", newline="") as handle:
        writer = csv.DictWriter(
            handle,
            fieldnames=[
                "comparison",
                "unhealthy_filter_nm",
                "unhealthy_camera_median_0_255",
                "healthy_filter_nm",
                "healthy_camera_median_0_255",
                "unhealthy_lower_percent",
            ],
        )
        writer.writeheader()
        writer.writerow(
            {
                "comparison": "unhealthy_peak_near_650_vs_healthy_peak_near_750",
                "unhealthy_filter_nm": float(unhealthy_peak["filter_nm"]),
                "unhealthy_camera_median_0_255": unhealthy_value,
                "healthy_filter_nm": float(healthy_peak["filter_nm"]),
                "healthy_camera_median_0_255": healthy_value,
                "unhealthy_lower_percent": round(lower_percent, 3),
            }
        )
    print(graph)
    print(csv_path)
    print(stats_text)


if __name__ == "__main__":
    main()
