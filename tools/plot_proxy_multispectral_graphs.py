"""Plot proxy multispectral graphs from the filtered photo measurements."""

from __future__ import annotations

import csv
from pathlib import Path

import matplotlib.pyplot as plt


PROJECT_ROOT = Path(r"C:\Users\david\OneDrive\Desktop\Archive\Projects\CodeX")
POC_DIR = PROJECT_ROOT / "outputs" / "leaf_analysis_poc"
PROXY_CSV = POC_DIR / "proxy_multispectral_bands_from_photos.csv"


def main() -> None:
    rows = read_proxy_rows()
    plot_proxy_brightness(rows, POC_DIR / "proxy_wavelength_brightness_graph.png")
    plot_proxy_indices(rows, POC_DIR / "proxy_wavelength_indices_graph.png")
    print(POC_DIR / "proxy_wavelength_brightness_graph.png")
    print(POC_DIR / "proxy_wavelength_indices_graph.png")


def read_proxy_rows() -> list[dict[str, object]]:
    with PROXY_CSV.open(newline="", encoding="utf-8") as handle:
        rows = list(csv.DictReader(handle))
    parsed = []
    for row in rows:
        wavelength = row.get("proxy_wavelength_nm", "")
        if not wavelength:
            continue
        parsed.append(
            {
                "photo_group": row["photo_group"],
                "leaf_condition": row["leaf_condition"],
                "wavelength_nm": float(wavelength),
                "mean_leaf_brightness": float(row["mean_leaf_brightness"]),
                "gcc": float(row["gcc"]),
                "saturation": float(row["saturation"]),
                "exg": float(row["exg"]),
            }
        )
    return parsed


def plot_proxy_brightness(rows: list[dict[str, object]], output: Path) -> None:
    fig, ax = plt.subplots(figsize=(9, 5.2))
    for group in sorted({str(row["photo_group"]) for row in rows}):
        group_rows = sorted([row for row in rows if row["photo_group"] == group], key=lambda row: row["wavelength_nm"])
        ax.plot(
            [row["wavelength_nm"] for row in group_rows],
            [row["mean_leaf_brightness"] for row in group_rows],
            marker="o",
            linewidth=2.2,
            label=group,
        )
    ax.set_title("Proxy Multispectral Response From Photos")
    ax.set_xlabel("Assigned filter / wavelength (nm)")
    ax.set_ylabel("Mean leaf brightness from JPG pixels")
    ax.set_xticks([532, 556, 680, 725, 850, 940])
    ax.set_ylim(bottom=0)
    ax.grid(True, alpha=0.25)
    ax.legend()
    fig.tight_layout()
    fig.savefig(output, dpi=180)
    plt.close(fig)


def plot_proxy_indices(rows: list[dict[str, object]], output: Path) -> None:
    fig, axes = plt.subplots(1, 2, figsize=(10, 4.8), sharex=True)
    for group in sorted({str(row["photo_group"]) for row in rows}):
        group_rows = sorted([row for row in rows if row["photo_group"] == group], key=lambda row: row["wavelength_nm"])
        wavelengths = [row["wavelength_nm"] for row in group_rows]
        axes[0].plot(wavelengths, [row["gcc"] for row in group_rows], marker="o", linewidth=2.0, label=group)
        axes[1].plot(wavelengths, [row["saturation"] for row in group_rows], marker="o", linewidth=2.0, label=group)
    axes[0].set_title("GCC by Assigned Wavelength")
    axes[0].set_ylabel("GCC")
    axes[1].set_title("Saturation by Assigned Wavelength")
    axes[1].set_ylabel("Saturation")
    for ax in axes:
        ax.set_xlabel("Assigned filter / wavelength (nm)")
        ax.set_xticks([532, 556, 680, 725, 850, 940])
        ax.grid(True, alpha=0.25)
    axes[1].legend()
    fig.tight_layout()
    fig.savefig(output, dpi=180)
    plt.close(fig)


if __name__ == "__main__":
    main()
