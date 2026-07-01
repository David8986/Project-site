"""Compare masked leaf camera brightness with spectrometer 10 nm medians."""

from __future__ import annotations

import csv
import json
import math
import shutil
from collections import defaultdict
from pathlib import Path
from typing import Any

import matplotlib.pyplot as plt
import numpy as np
from PIL import Image, ImageDraw


ROOT = Path(__file__).resolve().parents[1]
CAMERA_VALUES = ROOT / "outputs" / "camera_image_leaf_values" / "image_leaf_values.csv"
SPECTROMETER_BINS = ROOT / "outputs" / "spectrometer_camera_no_afara_graphs" / "spectrometer_10nm_binned_indoor_only.csv"
OUT_DIR = ROOT / "outputs" / "camera_brightness_vs_spectrometer_10nm_medians"
GRAPH_DIR = OUT_DIR / "graphs"
DESKTOP_DIR = Path(r"C:\Users\david\OneDrive\Desktop\camera_brightness_vs_spectrometer_10nm_medians")
FILTERS = (532, 556, 680, 725, 850, 940)
EPS = 1e-12


def read_csv(path: Path) -> list[dict[str, str]]:
    with path.open("r", encoding="utf-8-sig", newline="") as handle:
        return list(csv.DictReader(handle))


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


def as_float(value: Any) -> float | None:
    try:
        number = float(value)
    except (TypeError, ValueError):
        return None
    if not math.isfinite(number):
        return None
    return number


def rounded(value: Any, digits: int = 6) -> Any:
    number = as_float(value)
    if number is None:
        return ""
    return round(number, digits)


def as_plot_value(value: Any) -> float:
    number = as_float(value)
    return float(number) if number is not None else float("nan")


def normalize(values: list[float | None]) -> list[float | None]:
    """Scale positive measurements by their own maximum without forcing a zero.

    The earlier graph used min-max normalization, `(x - min) / (max - min)`.
    That is mathematically common, but it makes the smallest measured band
    exactly 0 even when the raw value is not zero. For these figures, max
    normalization is clearer: `x / max(x)`.
    """

    finite = [float(value) for value in values if value is not None and math.isfinite(float(value))]
    if not finite:
        return [None for _ in values]
    high = max(finite)
    if abs(high) <= EPS:
        return [None if value is None else 0.0 for value in values]
    return [(float(value) / high) if value is not None else None for value in values]


def pearson(xs: list[float], ys: list[float]) -> float | None:
    if len(xs) < 2 or len(ys) < 2:
        return None
    x = np.asarray(xs, dtype=float)
    y = np.asarray(ys, dtype=float)
    if float(np.std(x)) <= EPS or float(np.std(y)) <= EPS:
        return None
    return float(np.corrcoef(x, y)[0, 1])


def rmse(xs: list[float], ys: list[float]) -> float | None:
    if not xs or len(xs) != len(ys):
        return None
    diff = np.asarray(xs, dtype=float) - np.asarray(ys, dtype=float)
    return float(np.sqrt(np.mean(diff * diff)))


def build_spectrometer_lookup() -> dict[tuple[str, int], dict[str, Any]]:
    lookup: dict[tuple[str, int], dict[str, Any]] = {}
    for row in read_csv(SPECTROMETER_BINS):
        if row.get("sample_role") != "leaf_sample":
            continue
        filter_nm = as_float(row.get("filter_nm"))
        bin_start = as_float(row.get("bin_start_nm"))
        bin_end = as_float(row.get("bin_end_nm"))
        if filter_nm is None or bin_start is None or bin_end is None:
            continue
        wavelength = int(round(filter_nm))
        if int(round(bin_start)) <= wavelength < int(round(bin_end)):
            lookup[(row["sample_id"], wavelength)] = row
    return lookup


def build_pairs() -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    spectrum_lookup = build_spectrometer_lookup()
    camera_rows = [
        row
        for row in read_csv(CAMERA_VALUES)
        if row.get("sample_role") == "leaf_sample" and row.get("filter_nm") not in {"", None}
    ]
    pairs: list[dict[str, Any]] = []
    for row in camera_rows:
        sample_id = row["sample_id"]
        wavelength = int(round(float(row["filter_nm"])))
        spec = spectrum_lookup.get((sample_id, wavelength))
        camera_median = as_float(row.get("value_0_1_median"))
        camera_mean = as_float(row.get("value_0_1_mean"))
        camera_white_median = as_float(row.get("current_white_normalized_value_median"))
        camera_white_mean = as_float(row.get("current_white_normalized_value_mean"))
        spec_median = as_float(spec.get("median_intensity_10nm")) if spec else None
        spec_mean = as_float(spec.get("mean_intensity_10nm")) if spec else None
        pairs.append(
            {
                "sample_id": sample_id,
                "condition": row.get("condition", ""),
                "filter_nm": wavelength,
                "camera_leaf_brightness_median_0_1": rounded(camera_median),
                "camera_leaf_brightness_mean_0_1": rounded(camera_mean),
                "camera_leaf_brightness_median_0_255": rounded(camera_median * 255 if camera_median is not None else None, 3),
                "camera_white_normalized_median": rounded(camera_white_median),
                "camera_white_normalized_mean": rounded(camera_white_mean),
                "spectrometer_10nm_bin_start_nm": rounded(spec.get("bin_start_nm") if spec else None, 3),
                "spectrometer_10nm_bin_end_nm": rounded(spec.get("bin_end_nm") if spec else None, 3),
                "spectrometer_10nm_median_intensity": rounded(spec_median),
                "spectrometer_10nm_mean_intensity": rounded(spec_mean),
                "matched": bool(spec_median is not None),
            }
        )

    by_sample: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for pair in pairs:
        by_sample[pair["sample_id"]].append(pair)

    correlation_rows: list[dict[str, Any]] = []
    normalized_pairs: list[dict[str, Any]] = []
    for sample_id, rows in sorted(by_sample.items()):
        rows = sorted(rows, key=lambda item: int(item["filter_nm"]))
        camera_raw = [as_float(row["camera_leaf_brightness_median_0_1"]) for row in rows]
        camera_white = [as_float(row["camera_white_normalized_median"]) for row in rows]
        spectrometer = [as_float(row["spectrometer_10nm_median_intensity"]) for row in rows]
        camera_raw_norm = normalize(camera_raw)
        camera_white_norm = normalize(camera_white)
        spectrometer_norm = normalize(spectrometer)

        raw_x: list[float] = []
        white_x: list[float] = []
        spec_y: list[float] = []
        abs_diff_white: list[float] = []
        for row, raw_n, white_n, spec_n in zip(rows, camera_raw_norm, camera_white_norm, spectrometer_norm):
            new_row = dict(row)
            new_row["camera_raw_shape_0_1"] = rounded(raw_n)
            new_row["camera_white_shape_0_1"] = rounded(white_n)
            new_row["spectrometer_shape_0_1"] = rounded(spec_n)
            if raw_n is not None and spec_n is not None:
                raw_x.append(raw_n)
            if white_n is not None and spec_n is not None:
                white_x.append(white_n)
                spec_y.append(spec_n)
                abs_diff_white.append(abs(white_n - spec_n))
                new_row["abs_difference_white_camera_vs_spectrometer_shape"] = rounded(abs(white_n - spec_n))
            else:
                new_row["abs_difference_white_camera_vs_spectrometer_shape"] = ""
            normalized_pairs.append(new_row)

        # Keep y vectors aligned for raw separately.
        raw_spec_y = [
            spec_n
            for raw_n, spec_n in zip(camera_raw_norm, spectrometer_norm)
            if raw_n is not None and spec_n is not None
        ]
        correlation_rows.append(
            {
                "sample_id": sample_id,
                "condition": rows[0].get("condition", "") if rows else "",
                "matched_filter_count": len(spec_y),
                "pearson_raw_camera_shape_vs_spectrometer": rounded(pearson(raw_x, raw_spec_y)),
                "pearson_white_normalized_camera_shape_vs_spectrometer": rounded(pearson(white_x, spec_y)),
                "rmse_white_normalized_shape": rounded(rmse(white_x, spec_y)),
                "mean_abs_difference_white_normalized_shape": rounded(float(np.mean(abs_diff_white)) if abs_diff_white else None),
                "missing_spectrometer_filters": ",".join(str(row["filter_nm"]) for row in rows if not row.get("matched")),
            }
        )
    return normalized_pairs, correlation_rows


def plot_line_comparison(pairs: list[dict[str, Any]]) -> str:
    by_sample: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for row in pairs:
        by_sample[row["sample_id"]].append(row)
    sample_ids = sorted(by_sample)
    cols = 2
    rows_n = int(math.ceil(len(sample_ids) / cols))
    fig, axes = plt.subplots(rows_n, cols, figsize=(15, 4.7 * rows_n), sharey=True)
    axes = np.asarray(axes).reshape(rows_n, cols)
    for ax in axes.ravel():
        ax.axis("off")
    for index, sample_id in enumerate(sample_ids):
        ax = axes.ravel()[index]
        ax.axis("on")
        rows = sorted(by_sample[sample_id], key=lambda item: int(item["filter_nm"]))
        xs = [int(row["filter_nm"]) for row in rows]
        raw = [as_plot_value(row.get("camera_raw_shape_0_1")) for row in rows]
        white = [as_plot_value(row.get("camera_white_shape_0_1")) for row in rows]
        spec = [as_plot_value(row.get("spectrometer_shape_0_1")) for row in rows]
        valid_white = [(x, y) for x, y in zip(white, spec) if np.isfinite(x) and np.isfinite(y)]
        r = pearson([x for x, _ in valid_white], [y for _, y in valid_white])
        ax.plot(xs, raw, marker="o", color="#8a8a8a", linewidth=1.6, label="camera raw brightness")
        ax.plot(xs, white, marker="o", color="#287a46", linewidth=2.2, label="camera white-normalized")
        ax.plot(xs, spec, marker="s", color="#315f8c", linewidth=2.2, label="spectrometer 10 nm median")
        for row in rows:
            if not row.get("matched"):
                ax.text(int(row["filter_nm"]), 0.08, "lipsa spectru", rotation=90, ha="center", va="bottom", color="#8a2d21", fontsize=8)
        ax.set_title(f"{sample_id}\nr={r:.2f}" if r is not None else f"{sample_id}\nr=n/a", fontsize=10)
        ax.set_xticks(list(FILTERS))
        ax.set_xlabel("Filter / wavelength (nm)")
        ax.set_ylabel("Relative value / own max")
        ax.grid(True, alpha=0.25)
        ax.legend(fontsize=8)
    fig.suptitle("Leaf-area camera brightness vs spectrometer median intensity every 10 nm\nIndoor data only; normalized as value / maximum, not min-subtracted", fontsize=15, y=0.995)
    fig.tight_layout(rect=(0, 0, 1, 0.975))
    out = GRAPH_DIR / "01_per_sample_camera_brightness_vs_spectrometer_10nm_medians.png"
    fig.savefig(out, dpi=180)
    plt.close(fig)
    return str(out)


def plot_scatter(pairs: list[dict[str, Any]]) -> str:
    rows = [
        row
        for row in pairs
        if row.get("camera_white_shape_0_1") not in {"", None}
        and row.get("spectrometer_shape_0_1") not in {"", None}
    ]
    fig, axes = plt.subplots(1, 2, figsize=(15, 6.6))
    colors = {532: "#2f7f4f", 556: "#7ba943", 680: "#ba4a3a", 725: "#8d4fb8", 850: "#315f8c", 940: "#555555"}

    raw_x = [float(row["camera_leaf_brightness_median_0_1"]) for row in rows]
    spec_raw_y = [float(row["spectrometer_10nm_median_intensity"]) for row in rows]
    for row, x, y in zip(rows, raw_x, spec_raw_y):
        axes[0].scatter(x, y, color=colors.get(int(row["filter_nm"]), "#333333"), s=60, edgecolor="white", linewidth=0.7)
        axes[0].text(x + 0.005, y, str(row["filter_nm"]), fontsize=7)
    r_raw = pearson(raw_x, spec_raw_y)
    axes[0].set_title(f"Raw units: camera brightness vs spectrometer intensity\nPearson r={r_raw:.2f}" if r_raw is not None else "Raw units")
    axes[0].set_xlabel("Camera median brightness on leaf mask (0-1)")
    axes[0].set_ylabel("Spectrometer median intensity in matching 10 nm bin")
    axes[0].grid(True, alpha=0.25)

    shape_x = [float(row["camera_white_shape_0_1"]) for row in rows]
    shape_y = [float(row["spectrometer_shape_0_1"]) for row in rows]
    for row, x, y in zip(rows, shape_x, shape_y):
        axes[1].scatter(x, y, color=colors.get(int(row["filter_nm"]), "#333333"), s=60, edgecolor="white", linewidth=0.7)
        axes[1].text(x + 0.012, y + 0.012, str(row["filter_nm"]), fontsize=7)
    r_shape = pearson(shape_x, shape_y)
    axes[1].plot([0, 1], [0, 1], "--", color="#222222", linewidth=1, label="ideal match")
    axes[1].set_xlim(-0.05, 1.05)
    axes[1].set_ylim(-0.05, 1.05)
    axes[1].set_title(f"Relative shapes: white-corrected camera vs spectrometer\nPearson r={r_shape:.2f}" if r_shape is not None else "Relative shapes")
    axes[1].set_xlabel("Camera white-normalized brightness / max")
    axes[1].set_ylabel("Spectrometer 10 nm median / max")
    axes[1].grid(True, alpha=0.25)
    axes[1].legend()

    handles = [
        plt.Line2D([0], [0], marker="o", linestyle="", color=color, label=f"{wavelength} nm")
        for wavelength, color in colors.items()
    ]
    fig.legend(handles=handles, loc="lower center", ncol=6, bbox_to_anchor=(0.5, -0.01))
    fig.tight_layout(rect=(0, 0.04, 1, 1))
    out = GRAPH_DIR / "02_scatter_camera_brightness_vs_spectrometer_medians.png"
    fig.savefig(out, dpi=180)
    plt.close(fig)
    return str(out)


def plot_correlation_bars(correlation_rows: list[dict[str, Any]]) -> str:
    rows = sorted(correlation_rows, key=lambda row: row["sample_id"])
    labels = [row["sample_id"].replace("in cutie\\", "") for row in rows]
    raw = [as_plot_value(row["pearson_raw_camera_shape_vs_spectrometer"]) for row in rows]
    white = [as_plot_value(row["pearson_white_normalized_camera_shape_vs_spectrometer"]) for row in rows]
    x = np.arange(len(rows))
    width = 0.36
    fig, ax = plt.subplots(figsize=(12, 6.2))
    ax.bar(x - width / 2, raw, width, label="raw camera brightness shape", color="#8a8a8a")
    ax.bar(x + width / 2, white, width, label="white-normalized camera shape", color="#287a46")
    ax.axhline(0, color="#222222", linewidth=1)
    ax.set_ylim(-1, 1)
    ax.set_xticks(x)
    ax.set_xticklabels(labels, rotation=25, ha="right")
    ax.set_ylabel("Pearson r vs spectrometer 10 nm median shape")
    ax.set_title("Which camera brightness comparison follows the spectrometer better?")
    ax.grid(True, axis="y", alpha=0.25)
    ax.legend()
    fig.tight_layout()
    out = GRAPH_DIR / "03_correlation_by_sample_camera_vs_spectrometer.png"
    fig.savefig(out, dpi=180)
    plt.close(fig)
    return str(out)


def plot_difference_heatmap(pairs: list[dict[str, Any]]) -> str:
    sample_ids = sorted(set(row["sample_id"] for row in pairs))
    matrix = np.full((len(sample_ids), len(FILTERS)), np.nan)
    for row in pairs:
        wavelength = int(row["filter_nm"])
        if wavelength not in FILTERS:
            continue
        diff = as_float(row.get("abs_difference_white_camera_vs_spectrometer_shape"))
        if diff is not None:
            matrix[sample_ids.index(row["sample_id"]), FILTERS.index(wavelength)] = diff
    fig, ax = plt.subplots(figsize=(11.5, max(4.4, len(sample_ids) * 0.72 + 2.4)))
    image = ax.imshow(matrix, cmap="YlOrRd", aspect="auto", vmin=0, vmax=1)
    ax.set_xticks(np.arange(len(FILTERS)))
    ax.set_xticklabels([str(x) for x in FILTERS])
    ax.set_yticks(np.arange(len(sample_ids)))
    ax.set_yticklabels([item.replace("in cutie\\", "") for item in sample_ids], fontsize=8)
    ax.set_xlabel("Filter / wavelength (nm)")
    ax.set_title("Absolute difference between camera brightness shape and spectrometer median shape\nLower is better")
    for row_index in range(matrix.shape[0]):
        for col_index in range(matrix.shape[1]):
            value = matrix[row_index, col_index]
            ax.text(col_index, row_index, "NA" if not np.isfinite(value) else f"{value:.2f}", ha="center", va="center", fontsize=8)
    fig.colorbar(image, ax=ax, label="absolute shape difference")
    fig.tight_layout()
    out = GRAPH_DIR / "04_difference_heatmap_camera_vs_spectrometer.png"
    fig.savefig(out, dpi=180)
    plt.close(fig)
    return str(out)


def plot_filter_average(pairs: list[dict[str, Any]]) -> str:
    by_filter: dict[int, list[dict[str, Any]]] = defaultdict(list)
    for row in pairs:
        if row.get("matched"):
            by_filter[int(row["filter_nm"])].append(row)
    filters = [w for w in FILTERS if by_filter.get(w)]
    cam_means = []
    spec_means = []
    diffs = []
    for wavelength in filters:
        rows = by_filter[wavelength]
        cam = [float(row["camera_white_shape_0_1"]) for row in rows if row.get("camera_white_shape_0_1") not in {"", None}]
        spec = [float(row["spectrometer_shape_0_1"]) for row in rows if row.get("spectrometer_shape_0_1") not in {"", None}]
        cam_mean = float(np.mean(cam)) if cam else np.nan
        spec_mean = float(np.mean(spec)) if spec else np.nan
        cam_means.append(cam_mean)
        spec_means.append(spec_mean)
        diffs.append(abs(cam_mean - spec_mean) if np.isfinite(cam_mean) and np.isfinite(spec_mean) else np.nan)
    x = np.arange(len(filters))
    fig, ax = plt.subplots(figsize=(10, 6))
    ax.plot(x, cam_means, marker="o", color="#287a46", linewidth=2.2, label="camera average shape")
    ax.plot(x, spec_means, marker="s", color="#315f8c", linewidth=2.2, label="spectrometer average shape")
    ax.bar(x, diffs, color="#f0a55b", alpha=0.35, label="absolute difference")
    ax.set_xticks(x)
    ax.set_xticklabels([str(w) for w in filters])
    ax.set_xlabel("Filter / wavelength (nm)")
    ax.set_ylabel("Average normalized value")
    ax.set_title("Average behavior by filter across all leaf samples")
    ax.grid(True, alpha=0.25)
    ax.legend()
    fig.tight_layout()
    out = GRAPH_DIR / "05_average_by_filter_camera_vs_spectrometer.png"
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
            thumb.thumbnail((660, 460))
            canvas = Image.new("RGB", (700, 540), "white")
            canvas.paste(thumb, ((700 - thumb.width) // 2, 18))
            draw = ImageDraw.Draw(canvas)
            draw.text((18, 500), path.name[:96], fill=(20, 20, 20))
            thumbs.append(canvas)
    if not thumbs:
        return ""
    cols = 2
    rows = int(math.ceil(len(thumbs) / cols))
    sheet = Image.new("RGB", (cols * 700, rows * 540), "white")
    for index, thumb in enumerate(thumbs):
        sheet.paste(thumb, ((index % cols) * 700, (index // cols) * 540))
    out = OUT_DIR / "camera_brightness_spectrometer_graph_gallery.jpg"
    sheet.save(out, quality=92)
    return str(out)


def judgement(pairs: list[dict[str, Any]], correlation_rows: list[dict[str, Any]]) -> dict[str, Any]:
    matched = [row for row in pairs if row.get("matched")]
    raw_x = [float(row["camera_leaf_brightness_median_0_1"]) for row in matched]
    raw_y = [float(row["spectrometer_10nm_median_intensity"]) for row in matched]
    shape_x = [float(row["camera_white_shape_0_1"]) for row in matched if row.get("camera_white_shape_0_1") not in {"", None} and row.get("spectrometer_shape_0_1") not in {"", None}]
    shape_y = [float(row["spectrometer_shape_0_1"]) for row in matched if row.get("camera_white_shape_0_1") not in {"", None} and row.get("spectrometer_shape_0_1") not in {"", None}]
    sample_rs = [
        float(row["pearson_white_normalized_camera_shape_vs_spectrometer"])
        for row in correlation_rows
        if row.get("pearson_white_normalized_camera_shape_vs_spectrometer") not in {"", None}
    ]
    median_r = float(np.median(sample_rs)) if sample_rs else None
    mean_r = float(np.mean(sample_rs)) if sample_rs else None
    overall_raw_r = pearson(raw_x, raw_y)
    overall_shape_r = pearson(shape_x, shape_y)
    return {
        "matched_pairs": len(matched),
        "overall_raw_camera_brightness_vs_spectrometer_median_r": rounded(overall_raw_r),
        "overall_white_normalized_shape_r": rounded(overall_shape_r),
        "median_per_sample_white_normalized_shape_r": rounded(median_r),
        "mean_per_sample_white_normalized_shape_r": rounded(mean_r),
        "best_per_sample_r": rounded(max(sample_rs) if sample_rs else None),
        "worst_per_sample_r": rounded(min(sample_rs) if sample_rs else None),
        "judgement": (
            "The spectrometer is better for precise measurement because it gives the actual spectral intensity curve and "
            "stable 10 nm median values. The camera is useful as a practical proxy after leaf masking and white-reference "
            "normalization, but in this dataset it only follows the spectrometer moderately. It is good enough for a "
            "calibrated prototype/trend detector, not better than the spectrometer as a measurement instrument."
        ),
    }


def main() -> None:
    if OUT_DIR.exists():
        shutil.rmtree(OUT_DIR)
    GRAPH_DIR.mkdir(parents=True, exist_ok=True)
    pairs, correlation_rows = build_pairs()
    graph_paths = [
        plot_line_comparison(pairs),
        plot_scatter(pairs),
        plot_correlation_bars(correlation_rows),
        plot_difference_heatmap(pairs),
        plot_filter_average(pairs),
    ]
    gallery = make_gallery(graph_paths)
    write_csv(OUT_DIR / "camera_brightness_vs_spectrometer_10nm_median_pairs.csv", pairs)
    write_csv(OUT_DIR / "camera_brightness_vs_spectrometer_correlations.csv", correlation_rows)
    summary = {
        "input_camera_values": str(CAMERA_VALUES),
        "input_spectrometer_10nm_bins": str(SPECTROMETER_BINS),
        "method": "camera median brightness on the detected leaf mask compared with spectrometer median intensity in the matching 10 nm wavelength bin",
        "graphs": graph_paths,
        "gallery": gallery,
        "results": judgement(pairs, correlation_rows),
    }
    (OUT_DIR / "summary.json").write_text(json.dumps(summary, indent=2), encoding="utf-8")
    if DESKTOP_DIR.exists():
        shutil.rmtree(DESKTOP_DIR)
    shutil.copytree(OUT_DIR, DESKTOP_DIR)
    (DESKTOP_DIR / "summary.json").write_text(json.dumps(summary, indent=2), encoding="utf-8")
    print(json.dumps({**summary, "desktop_copy": str(DESKTOP_DIR)}, indent=2))


if __name__ == "__main__":
    main()
