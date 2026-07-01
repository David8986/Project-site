"""Analyze the leaf photo/spectrometer dataset and write report outputs."""

from __future__ import annotations

import csv
import math
from pathlib import Path

import cv2
import matplotlib.pyplot as plt
import numpy as np
from PIL import Image, ImageDraw


DATASET = Path(r"C:\Users\david\OneDrive\Desktop\Archive\Misc\Review Folders\New folder (6)")
OUTPUT = Path("outputs") / "spectrometer_photo_comparison"

FILTER_ORDER = ["532 nm", "556 nm", "full/no filter", "680 nm", "725 nm", "850 nm", "940 nm"]


def main() -> None:
    OUTPUT.mkdir(parents=True, exist_ok=True)
    rows = analyze_photos()
    write_csv(OUTPUT / "per_photo_leaf_analysis.csv", rows)
    write_csv(OUTPUT / "photo_group_summary.csv", summarize_groups(rows))
    write_csv(OUTPUT / "photo_to_filter_association.csv", associate_photos_to_filters(rows))
    make_mask_sheet(rows, OUTPUT / "photo_leaf_masks.jpg")
    make_metric_plot(rows, OUTPUT / "photo_group_metric_summary.png")
    write_report(rows, OUTPUT / "analysis_report.md")
    print(f"Wrote dataset analysis to: {OUTPUT.resolve()}")


def analyze_photos() -> list[dict[str, object]]:
    rows: list[dict[str, object]] = []
    for path in sorted((DATASET / "Camera Roll").rglob("*.jpg")):
        rgb = np.asarray(Image.open(path).convert("RGB"), dtype=np.uint8)
        mask = leaf_mask(rgb)
        pixels = rgb[mask]
        if pixels.size == 0:
            pixels = rgb.reshape(-1, 3)

        rgb_float = pixels.astype(np.float32) / 255.0
        r, g, b = rgb_float[:, 0], rgb_float[:, 1], rgb_float[:, 2]
        hsv = cv2.cvtColor(pixels.reshape(-1, 1, 3), cv2.COLOR_RGB2HSV).reshape(-1, 3)
        hue_deg = hsv[:, 0].astype(np.float32) * 2.0
        sat = hsv[:, 1].astype(np.float32) / 255.0
        val = hsv[:, 2].astype(np.float32) / 255.0

        row = {
            "photo_group": path.parent.name,
            "photo_file": path.name,
            "relative_path": str(path.relative_to(DATASET)),
            "masked_leaf_pixels": int(mask.sum()),
            "leaf_area_fraction": round_float(mask.mean()),
            "mean_r": round_float(r.mean()),
            "mean_g": round_float(g.mean()),
            "mean_b": round_float(b.mean()),
            "mean_hue_deg": round_float(circular_mean_degrees(hue_deg)),
            "mean_saturation": round_float(sat.mean()),
            "mean_value_brightness": round_float(val.mean()),
            "gcc": round_float(np.mean(g / np.maximum(r + g + b, 1e-8))),
            "exg": round_float(np.mean(2.0 * g - r - b)),
            "vari": round_float(np.nanmean((g - r) / np.where(np.abs(g + r - b) < 1e-8, np.nan, g + r - b))),
            "appearance": classify_appearance(r.mean(), g.mean(), b.mean(), sat.mean(), val.mean(), circular_mean_degrees(hue_deg)),
        }
        rows.append(row)
    return rows


def leaf_mask(rgb: np.ndarray) -> np.ndarray:
    gray = cv2.cvtColor(rgb, cv2.COLOR_RGB2GRAY)
    blur = cv2.GaussianBlur(gray, (9, 9), 0)
    _, thresh = cv2.threshold(blur, 0, 255, cv2.THRESH_BINARY + cv2.THRESH_OTSU)

    # The leaf is generally brighter than the black background. If Otsu captures
    # the background instead, invert by comparing border and center coverage.
    mask = thresh > 0
    border = np.concatenate([mask[:20, :].ravel(), mask[-20:, :].ravel(), mask[:, :20].ravel(), mask[:, -20:].ravel()])
    if border.mean() > 0.5:
        mask = ~mask

    mask_u8 = mask.astype(np.uint8) * 255
    contours, _ = cv2.findContours(mask_u8, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
    if contours:
        largest = max(contours, key=cv2.contourArea)
        filled = np.zeros(mask_u8.shape, dtype=np.uint8)
        cv2.drawContours(filled, [largest], -1, 255, thickness=cv2.FILLED)
        mask = filled > 0

    kernel = np.ones((9, 9), dtype=np.uint8)
    mask = cv2.morphologyEx(mask.astype(np.uint8), cv2.MORPH_CLOSE, kernel) > 0
    if mask.mean() < 0.02 or mask.mean() > 0.85:
        mask = gray > np.percentile(gray, 65)
    return mask


def associate_photos_to_filters(rows: list[dict[str, object]]) -> list[dict[str, object]]:
    associations: list[dict[str, object]] = []
    for group in sorted({str(row["photo_group"]) for row in rows}):
        group_rows = [row for row in rows if row["photo_group"] == group]
        group_rows.sort(key=lambda row: row["photo_file"])
        condition = "green/healthy leaf" if group.endswith("1") else "yellow/unhealthy leaf"
        spectrometer_folder = (
            r"Camera Roll\spectrometru frunza\verde frunza"
            if group.endswith("1")
            else r"Camera Roll\spectrometru frunza\fruza nesanatoasa-galben"
        )
        for index, row in enumerate(group_rows):
            filter_label = FILTER_ORDER[index] if index < len(FILTER_ORDER) else "unknown"
            confidence = "medium" if group.endswith("2") else "low"
            reason = (
                "Assigned by photo order and visible color sequence; group 2 visually matches green/white/red/NIR order."
                if group.endswith("2")
                else "Assigned by photo order; group 1 is mostly grayscale, so filter labels need manual confirmation."
            )
            associations.append(
                {
                    "photo_group": group,
                    "photo_file": row["photo_file"],
                    "proposed_leaf_condition": condition,
                    "proposed_camera_filter_or_light": filter_label,
                    "matching_spectrometer_folder": spectrometer_folder,
                    "matching_spectrometer_measurement": filter_label,
                    "confidence": confidence,
                    "reason": reason,
                }
            )
    return associations


def summarize_groups(rows: list[dict[str, object]]) -> list[dict[str, object]]:
    summaries: list[dict[str, object]] = []
    for group in sorted({str(row["photo_group"]) for row in rows}):
        group_rows = [row for row in rows if row["photo_group"] == group]
        summary: dict[str, object] = {"photo_group": group, "photo_count": len(group_rows)}
        for key in ("mean_r", "mean_g", "mean_b", "mean_saturation", "mean_value_brightness", "gcc", "exg", "vari"):
            values = [float(row[key]) for row in group_rows]
            summary[f"avg_{key}"] = round_float(np.mean(values))
            summary[f"std_{key}"] = round_float(np.std(values, ddof=1)) if len(values) > 1 else 0.0
        summaries.append(summary)
    return summaries


def make_mask_sheet(rows: list[dict[str, object]], output: Path) -> None:
    tiles = []
    for row in rows:
        path = DATASET / str(row["relative_path"])
        image = Image.open(path).convert("RGB")
        rgb = np.asarray(image, dtype=np.uint8)
        mask = leaf_mask(rgb)
        overlay = rgb.copy()
        overlay[~mask] = (overlay[~mask] * 0.25).astype(np.uint8)
        overlay[mask] = np.clip(overlay[mask] * 0.75 + np.array([55, 180, 55]) * 0.25, 0, 255).astype(np.uint8)
        tile = Image.fromarray(overlay)
        tile.thumbnail((300, 170))
        canvas = Image.new("RGB", (320, 220), "white")
        canvas.paste(tile, (10, 10))
        draw = ImageDraw.Draw(canvas)
        draw.text((10, 185), f"{row['photo_group']}\n{row['photo_file'][13:21]} {row['appearance']}", fill="black")
        tiles.append(canvas)

    cols = 4
    sheet = Image.new("RGB", (cols * 320, math.ceil(len(tiles) / cols) * 220), (240, 240, 240))
    for index, tile in enumerate(tiles):
        sheet.paste(tile, ((index % cols) * 320, (index // cols) * 220))
    sheet.save(output, quality=92)


def make_metric_plot(rows: list[dict[str, object]], output: Path) -> None:
    summaries = summarize_groups(rows)
    groups = [str(row["photo_group"]) for row in summaries]
    metrics = [("avg_gcc", "GCC"), ("avg_exg", "ExG"), ("avg_vari", "VARI"), ("avg_mean_saturation", "Saturation")]
    x = np.arange(len(groups))
    width = 0.18
    fig, ax = plt.subplots(figsize=(9, 5))
    for index, (key, label) in enumerate(metrics):
        ax.bar(x + (index - 1.5) * width, [float(row[key]) for row in summaries], width, label=label)
    ax.set_xticks(x)
    ax.set_xticklabels(groups)
    ax.set_title("Leaf photo metrics by group")
    ax.grid(axis="y", alpha=0.25)
    ax.legend()
    fig.tight_layout()
    fig.savefig(output, dpi=160)
    plt.close(fig)


def write_report(rows: list[dict[str, object]], output: Path) -> None:
    summaries = summarize_groups(rows)
    associations = associate_photos_to_filters(rows)
    lines = [
        "# Leaf Photo / Spectrometer Analysis",
        "",
        "## What can be analyzed now",
        "",
        "The JPG photos can be analyzed directly. The `.ocv` files found here are OceanView ZIP/XML containers; in the checked files they contain acquisition/view settings, not exported wavelength-intensity tables. Therefore, this report analyzes the photos and prepares the association structure for the spectrometer measurements.",
        "",
        "## Photo group summary",
        "",
        "| Photo group | Count | Avg GCC | Avg ExG | Avg VARI | Avg saturation | Interpretation |",
        "|---|---:|---:|---:|---:|---:|---|",
    ]
    for summary in summaries:
        group = str(summary["photo_group"])
        interpretation = (
            "Mostly grayscale/low-saturation sequence; likely filter/IR-style captures of the first leaf."
            if group.endswith("1")
            else "Contains green, red/brown, and bright low-saturation captures; likely visible + near-IR sequence of the second leaf."
        )
        lines.append(
            f"| {group} | {summary['photo_count']} | {summary['avg_gcc']} | {summary['avg_exg']} | "
            f"{summary['avg_vari']} | {summary['avg_mean_saturation']} | {interpretation} |"
        )

    lines.extend(
        [
            "",
            "## Proposed association",
            "",
            "| Photo group | Leaf condition | Spectrometer folder | Confidence |",
            "|---|---|---|---|",
            "| Poze normale frunza 1 | green/healthy leaf | `Camera Roll\\spectrometru frunza\\verde frunza` | medium for folder, low for exact per-photo wavelength |",
            "| Poze normale frunza 2 | yellow/unhealthy leaf | `Camera Roll\\spectrometru frunza\\fruza nesanatoasa-galben` | medium |",
            "",
            "## Proposed per-photo filter order",
            "",
            "This is a working association, not a substitute for lab notes. Group 2 visually supports the sequence better than group 1.",
            "",
            "| Group | Photo | Proposed filter/light | Appearance | Confidence |",
            "|---|---|---|---|---|",
        ]
    )
    row_lookup = {(row["photo_group"], row["photo_file"]): row for row in rows}
    for assoc in associations:
        row = row_lookup[(assoc["photo_group"], assoc["photo_file"])]
        lines.append(
            f"| {assoc['photo_group']} | {assoc['photo_file']} | {assoc['proposed_camera_filter_or_light']} | "
            f"{row['appearance']} | {assoc['confidence']} |"
        )

    lines.extend(
        [
            "",
            "## How to finish the spectrometer comparison",
            "",
            "Export each OceanView measurement as CSV/TXT with wavelength and intensity columns. Then compare each photo group's averaged visible-camera metrics against the matching spectrometer intensities/reflectance at 532, 556, 680, 725, 850, and 940 nm.",
            "",
            "Recommended comparison features:",
            "",
            "- Camera: GCC, ExG, VARI, mean saturation, mean brightness.",
            "- Spectrometer: intensity or reflectance at 532, 556, 680, 725, 850, 940 nm.",
            "- Ratios: 850/680 and 725/680, because they summarize near-IR/red-edge response against red/chlorophyll-region response.",
        ]
    )
    output.write_text("\n".join(lines), encoding="utf-8")


def classify_appearance(r: float, g: float, b: float, sat: float, val: float, hue: float) -> str:
    if sat < 0.08:
        return "bright grayscale/white" if val > 0.55 else "dark grayscale/IR-like"
    if 70 <= hue <= 165 and g > r and g > b:
        return "green"
    if hue < 35 or hue > 330:
        return "red/brown"
    if 35 <= hue < 70:
        return "yellow/orange"
    return "colored"


def circular_mean_degrees(values: np.ndarray) -> float:
    radians = np.deg2rad(values.astype(float))
    sin_mean = np.mean(np.sin(radians))
    cos_mean = np.mean(np.cos(radians))
    return float((np.rad2deg(np.arctan2(sin_mean, cos_mean)) + 360.0) % 360.0)


def write_csv(path: Path, rows: list[dict[str, object]]) -> None:
    if not rows:
        path.write_text("", encoding="utf-8")
        return
    fieldnames = list(rows[0].keys())
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)


def round_float(value: object, digits: int = 6) -> float:
    try:
        number = float(value)
    except (TypeError, ValueError):
        return math.nan
    return round(number, digits) if math.isfinite(number) else math.nan


if __name__ == "__main__":
    main()
