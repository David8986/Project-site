"""Create indoor-only spectrometer graphs and camera/spectrometer comparisons."""

from __future__ import annotations

import csv
import json
import math
import os
import re
import shutil
from collections import defaultdict
from pathlib import Path
from typing import Any

import matplotlib.pyplot as plt
import numpy as np
from PIL import Image, ImageDraw


ROOT = Path(__file__).resolve().parents[1]
DATA_ROOT = Path(os.environ.get("SPECTRALEAF_DATA_ROOT", r"C:\Users\david\OneDrive\Desktop\data analisys"))
INDOOR_ROOT = DATA_ROOT / "in cutie"
CAMERA_VALUES = Path(os.environ.get("SPECTRALEAF_CAMERA_VALUES", ROOT / "outputs" / "camera_image_leaf_values" / "image_leaf_values.csv"))
OUT_DIR = Path(os.environ.get("SPECTRALEAF_SPECTROMETER_OUT_DIR", ROOT / "outputs" / "spectrometer_camera_no_afara_graphs"))
GRAPH_DIR = OUT_DIR / "graphs"
DESKTOP_DIR = Path(os.environ.get("SPECTRALEAF_SPECTROMETER_DESKTOP_DIR", r"C:\Users\david\OneDrive\Desktop\spectrometer_camera_graphs_no_afara"))

FILTERS = (532, 556, 680, 725, 850, 940)
BIN_WIDTH_NM = 10
WINDOW_HALF_WIDTH_NM = 5
EPS = 1e-12


def rel(path: Path) -> str:
    try:
        return str(path.relative_to(DATA_ROOT))
    except ValueError:
        return str(path)


def safe_name(text: str) -> str:
    return re.sub(r"[^A-Za-z0-9_-]+", "_", text).strip("_")


def round_float(value: Any, digits: int = 6) -> Any:
    try:
        number = float(value)
    except (TypeError, ValueError):
        return ""
    if not math.isfinite(number):
        return ""
    return round(number, digits)


def infer_filter(path: Path) -> int | None:
    match = re.search(r"(532|556|580|650|680|725|850|940|950)", path.stem)
    if not match:
        return None
    value = int(match.group(1))
    if value == 950:
        return 940
    return value


def sample_dir_for_spectrum(path: Path) -> Path:
    if path.parent.name.lower() == "spectru":
        return path.parent.parent
    return path.parent


def sample_role(sample_dir: Path) -> str:
    lower = rel(sample_dir).lower()
    if "referinta alba" in lower:
        return "white_reference"
    if "refirinta neagra" in lower or "referinta neagra" in lower:
        return "dark_reference"
    if sample_dir == INDOOR_ROOT:
        return "source"
    return "leaf_sample"


def sample_condition(sample_dir: Path) -> str:
    lower = rel(sample_dir).lower()
    role = sample_role(sample_dir)
    if role != "leaf_sample":
        return role
    if "nesan" in lower:
        return "unhealthy"
    if "galbena" in lower:
        return "healthy_yellow"
    if "verde" in lower or "sanatoasa" in lower:
        return "healthy"
    return "leaf_unknown"


def read_spectrum(path: Path) -> tuple[np.ndarray, np.ndarray]:
    lines = path.read_text(encoding="utf-8", errors="ignore").splitlines()
    start = 0
    for index, line in enumerate(lines):
        if "Begin Spectral Data" in line:
            start = index + 1
            break
    pairs: list[tuple[float, float]] = []
    for line in lines[start:]:
        numbers = re.findall(r"[-+]?(?:\d*\.\d+|\d+)(?:[eE][-+]?\d+)?", line)
        if len(numbers) >= 2:
            pairs.append((float(numbers[0]), float(numbers[1])))
    if len(pairs) < 10:
        raise ValueError(f"Could not parse spectrum: {path}")
    data = np.asarray(pairs, dtype=float)
    return data[:, 0], data[:, 1]


def bin_spectrum_10nm(wavelengths: np.ndarray, intensities: np.ndarray) -> list[dict[str, Any]]:
    finite = np.isfinite(wavelengths) & np.isfinite(intensities)
    wavelengths = wavelengths[finite]
    intensities = intensities[finite]
    if wavelengths.size == 0:
        return []
    bin_starts = np.floor(wavelengths / BIN_WIDTH_NM).astype(int) * BIN_WIDTH_NM
    rows: list[dict[str, Any]] = []
    for bin_start in sorted(set(int(x) for x in bin_starts)):
        mask = bin_starts == bin_start
        values = intensities[mask]
        waves = wavelengths[mask]
        if values.size == 0:
            continue
        rows.append(
            {
                "bin_start_nm": int(bin_start),
                "bin_end_nm": int(bin_start + BIN_WIDTH_NM),
                "bin_center_nm": float(np.mean(waves)),
                "mean_intensity_10nm": float(np.mean(values)),
                "median_intensity_10nm": float(np.median(values)),
                "std_intensity_10nm": float(np.std(values)),
                "points_in_bin": int(values.size),
            }
        )
    return rows


def window_mean(wavelengths: np.ndarray, intensities: np.ndarray, center_nm: int) -> float | None:
    mask = (
        (wavelengths >= center_nm - WINDOW_HALF_WIDTH_NM)
        & (wavelengths < center_nm + WINDOW_HALF_WIDTH_NM)
        & np.isfinite(intensities)
    )
    if not np.any(mask):
        return None
    return float(np.mean(intensities[mask]))


def read_csv_rows(path: Path) -> list[dict[str, str]]:
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


def normalize(values: list[float | None]) -> list[float | None]:
    finite = [float(value) for value in values if value is not None and math.isfinite(float(value))]
    if not finite:
        return [None for _ in values]
    low = min(finite)
    high = max(finite)
    if abs(high - low) <= EPS:
        return [0.5 if value is not None else None for value in values]
    return [((float(value) - low) / (high - low)) if value is not None else None for value in values]


def pearson(xs: list[float], ys: list[float]) -> float | None:
    if len(xs) < 2 or len(ys) < 2:
        return None
    x = np.asarray(xs, dtype=float)
    y = np.asarray(ys, dtype=float)
    if np.std(x) <= EPS or np.std(y) <= EPS:
        return None
    return float(np.corrcoef(x, y)[0, 1])


def build_spectrum_rows() -> tuple[list[dict[str, Any]], dict[str, dict[int | str, dict[str, Any]]]]:
    binned_rows: list[dict[str, Any]] = []
    spectrum_lookup: dict[str, dict[int | str, dict[str, Any]]] = defaultdict(dict)
    for path in sorted(INDOOR_ROOT.rglob("*.txt")):
        if "afara" in str(path).lower():
            continue
        try:
            wavelengths, intensities = read_spectrum(path)
        except ValueError:
            continue
        sample_dir = sample_dir_for_spectrum(path)
        sample_id = rel(sample_dir)
        role = sample_role(sample_dir)
        condition = sample_condition(sample_dir)
        filter_nm = infer_filter(path)
        filter_label = str(filter_nm) if filter_nm is not None else ("fara" if "fara" in path.name.lower() else path.stem)

        bins = bin_spectrum_10nm(wavelengths, intensities)
        for row in bins:
            binned_rows.append(
                {
                    "sample_id": sample_id,
                    "sample_role": role,
                    "condition": condition,
                    "spectrum_file": path.name,
                    "relative_path": rel(path),
                    "filter_label": filter_label,
                    "filter_nm": filter_nm if filter_nm is not None else "",
                    **{key: round_float(value) for key, value in row.items()},
                }
            )

        key: int | str = filter_nm if filter_nm is not None else filter_label
        spectrum_lookup[sample_id][key] = {
            "path": path,
            "sample_id": sample_id,
            "sample_role": role,
            "condition": condition,
            "filter_label": filter_label,
            "filter_nm": filter_nm,
            "wavelengths": wavelengths,
            "intensities": intensities,
            "bins": bins,
        }
    return binned_rows, spectrum_lookup


def plot_spectrometer_per_sample(spectrum_lookup: dict[str, dict[int | str, dict[str, Any]]]) -> list[str]:
    paths: list[str] = []
    colors = {
        532: "#2f7f4f",
        556: "#7ba943",
        580: "#a8a33e",
        680: "#ba4a3a",
        725: "#8d4fb8",
        850: "#315f8c",
        940: "#4a4a4a",
        "fara": "#111111",
        "spectru sursa": "#e0a72e",
    }
    for sample_id, records in sorted(spectrum_lookup.items()):
        plt.figure(figsize=(12, 6.4))
        plotted = 0
        for key, record in sorted(records.items(), key=lambda item: (9999 if isinstance(item[0], str) else int(item[0]), str(item[0]))):
            bins = record["bins"]
            if not bins:
                continue
            x = [float(row["bin_center_nm"]) for row in bins]
            y = [float(row["mean_intensity_10nm"]) for row in bins]
            label = f"{record['filter_label']} nm" if isinstance(record.get("filter_nm"), int) else str(record["filter_label"])
            plt.plot(x, y, linewidth=1.8, label=label, color=colors.get(key, None), alpha=0.95)
            plotted += 1
        if plotted == 0:
            plt.close()
            continue
        plt.title(f"Spectrometru in cutie - media pe intervale de 10 nm\n{sample_id}", fontsize=13)
        plt.xlabel("Lungime de unda (nm)")
        plt.ylabel("Intensitate medie in interval de 10 nm")
        plt.grid(True, alpha=0.24)
        plt.legend(ncol=4, fontsize=8)
        plt.tight_layout()
        out = GRAPH_DIR / f"spectrometru_10nm_{safe_name(sample_id)}.png"
        plt.savefig(out, dpi=180)
        plt.close()
        paths.append(str(out))
    return paths


def build_camera_comparison_rows(
    spectrum_lookup: dict[str, dict[int | str, dict[str, Any]]],
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    camera_rows = read_csv_rows(CAMERA_VALUES)
    leaf_rows = [
        row
        for row in camera_rows
        if row.get("sample_role") == "leaf_sample" and row.get("filter_nm") not in {"", None}
    ]
    pairs: list[dict[str, Any]] = []
    by_sample_values: dict[str, dict[str, list[Any]]] = defaultdict(lambda: defaultdict(list))

    for row in leaf_rows:
        sample_id = row["sample_id"]
        filter_nm = int(float(row["filter_nm"]))
        spec_record = spectrum_lookup.get(sample_id, {}).get(filter_nm)
        spec_mean = None
        spec_file = ""
        if spec_record is not None:
            spec_mean = window_mean(spec_record["wavelengths"], spec_record["intensities"], filter_nm)
            spec_file = spec_record["path"].name
        camera_raw_mean = float(row.get("value_0_1_mean") or 0.0)
        camera_raw_median = float(row.get("value_0_1_median") or 0.0)
        camera_white_mean = row.get("current_white_normalized_value_mean")
        camera_white_median = row.get("current_white_normalized_value_median")
        camera_white_mean_f = float(camera_white_mean) if camera_white_mean not in {"", None} else None
        camera_white_median_f = float(camera_white_median) if camera_white_median not in {"", None} else None
        pair = {
            "sample_id": sample_id,
            "condition": row.get("condition", ""),
            "filter_nm": filter_nm,
            "camera_raw_value_mean": round_float(camera_raw_mean),
            "camera_raw_value_median": round_float(camera_raw_median),
            "camera_white_normalized_mean": round_float(camera_white_mean_f),
            "camera_white_normalized_median": round_float(camera_white_median_f),
            "spectrometer_10nm_mean_at_filter": round_float(spec_mean),
            "spectrometer_file": spec_file,
            "comparison_status": "ok" if spec_mean is not None else "missing_spectrometer_filter",
        }
        pairs.append(pair)
        by_sample_values[sample_id]["rows"].append(pair)

    normalized_pairs: list[dict[str, Any]] = []
    correlation_rows: list[dict[str, Any]] = []
    for sample_id, payload in sorted(by_sample_values.items()):
        rows = sorted(payload["rows"], key=lambda item: int(item["filter_nm"]))
        camera_values = [
            float(row["camera_white_normalized_mean"])
            if row.get("camera_white_normalized_mean") not in {"", None}
            else None
            for row in rows
        ]
        spec_values = [
            float(row["spectrometer_10nm_mean_at_filter"])
            if row.get("spectrometer_10nm_mean_at_filter") not in {"", None}
            else None
            for row in rows
        ]
        camera_norm = normalize(camera_values)
        spec_norm = normalize(spec_values)
        xs: list[float] = []
        ys: list[float] = []
        abs_diffs: list[float] = []
        for row, cam_n, spec_n in zip(rows, camera_norm, spec_norm):
            new_row = dict(row)
            new_row["camera_white_norm_shape_0_1"] = round_float(cam_n)
            new_row["spectrometer_shape_0_1"] = round_float(spec_n)
            if cam_n is not None and spec_n is not None:
                diff = abs(cam_n - spec_n)
                new_row["absolute_shape_difference"] = round_float(diff)
                xs.append(cam_n)
                ys.append(spec_n)
                abs_diffs.append(diff)
            else:
                new_row["absolute_shape_difference"] = ""
            normalized_pairs.append(new_row)

        correlation_rows.append(
            {
                "sample_id": sample_id,
                "condition": rows[0].get("condition", "") if rows else "",
                "matched_filter_count": len(xs),
                "pearson_r_camera_vs_spectrometer_shape": round_float(pearson(xs, ys)),
                "mean_absolute_shape_difference": round_float(float(np.mean(abs_diffs)) if abs_diffs else None),
                "missing_filters": ",".join(str(row["filter_nm"]) for row in rows if row["comparison_status"] != "ok"),
            }
        )

    return normalized_pairs, correlation_rows


def plot_comparison_by_sample(pairs: list[dict[str, Any]]) -> str:
    by_sample: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for row in pairs:
        by_sample[row["sample_id"]].append(row)

    sample_ids = sorted(by_sample)
    cols = 2
    rows_n = int(math.ceil(len(sample_ids) / cols))
    fig, axes = plt.subplots(rows_n, cols, figsize=(14, 4.8 * rows_n), sharey=True)
    axes_arr = np.asarray(axes).reshape(rows_n, cols)
    for ax in axes_arr.ravel():
        ax.axis("off")

    for index, sample_id in enumerate(sample_ids):
        ax = axes_arr.ravel()[index]
        ax.axis("on")
        rows = sorted(by_sample[sample_id], key=lambda item: int(item["filter_nm"]))
        xs = [int(row["filter_nm"]) for row in rows]
        cam = [
            float(row["camera_white_norm_shape_0_1"])
            if row.get("camera_white_norm_shape_0_1") not in {"", None}
            else np.nan
            for row in rows
        ]
        spec = [
            float(row["spectrometer_shape_0_1"])
            if row.get("spectrometer_shape_0_1") not in {"", None}
            else np.nan
            for row in rows
        ]
        ax.plot(xs, cam, marker="o", linewidth=2, color="#287a46", label="camera pe masca, normalizata")
        ax.plot(xs, spec, marker="s", linewidth=2, color="#315f8c", label="spectrometru 10 nm, normalizat")
        for x, y, row in zip(xs, spec, rows):
            if row.get("comparison_status") != "ok":
                ax.text(x, 0.05, "lipsa spectru", ha="center", va="bottom", fontsize=8, rotation=90, color="#8a2d21")
        valid_x = [float(a) for a, b in zip(cam, spec) if np.isfinite(a) and np.isfinite(b)]
        valid_y = [float(b) for a, b in zip(cam, spec) if np.isfinite(a) and np.isfinite(b)]
        r = pearson(valid_x, valid_y)
        r_label = f"r={r:.2f}" if r is not None else "r=n/a"
        ax.set_title(f"{sample_id}\n{r_label}", fontsize=10)
        ax.set_xlabel("Filtru / lungime de unda (nm)")
        ax.set_ylabel("Forma normalizata 0-1")
        ax.set_xticks(list(FILTERS))
        ax.grid(True, alpha=0.25)
        ax.legend(fontsize=8)

    fig.suptitle("Comparatie compusa camera vs spectrometru - doar in cutie, fara afara", fontsize=15, y=0.995)
    fig.tight_layout(rect=(0, 0, 1, 0.98))
    out = GRAPH_DIR / "camera_vs_spectrometer_composite_by_sample.png"
    fig.savefig(out, dpi=180)
    plt.close(fig)
    return str(out)


def plot_scatter(pairs: list[dict[str, Any]]) -> str:
    rows = [
        row
        for row in pairs
        if row.get("camera_white_norm_shape_0_1") not in {"", None}
        and row.get("spectrometer_shape_0_1") not in {"", None}
    ]
    fig, ax = plt.subplots(figsize=(8.5, 7))
    colors = {"healthy": "#287a46", "healthy_yellow": "#b99a2f", "unhealthy": "#b84a3a"}
    for condition in sorted(set(row.get("condition", "") for row in rows)):
        subset = [row for row in rows if row.get("condition", "") == condition]
        x = [float(row["camera_white_norm_shape_0_1"]) for row in subset]
        y = [float(row["spectrometer_shape_0_1"]) for row in subset]
        ax.scatter(x, y, label=condition, s=58, alpha=0.88, color=colors.get(condition, None), edgecolor="white", linewidth=0.7)
        for row, xx, yy in zip(subset, x, y):
            ax.text(xx + 0.012, yy + 0.012, str(row["filter_nm"]), fontsize=7)
    all_x = [float(row["camera_white_norm_shape_0_1"]) for row in rows]
    all_y = [float(row["spectrometer_shape_0_1"]) for row in rows]
    r = pearson(all_x, all_y)
    ax.plot([0, 1], [0, 1], linestyle="--", color="#333333", linewidth=1, label="linie ideala")
    ax.set_xlim(-0.05, 1.05)
    ax.set_ylim(-0.05, 1.05)
    ax.set_xlabel("Camera, forma normalizata 0-1")
    ax.set_ylabel("Spectrometru, forma normalizata 0-1")
    ax.set_title(f"Camera vs spectrometru pe filtre potrivite (in cutie, fara afara)\nPearson total r={r:.2f}" if r is not None else "Camera vs spectrometru pe filtre potrivite")
    ax.grid(True, alpha=0.25)
    ax.legend()
    fig.tight_layout()
    out = GRAPH_DIR / "camera_vs_spectrometer_scatter_shape.png"
    fig.savefig(out, dpi=180)
    plt.close(fig)
    return str(out)


def plot_difference_heatmap(pairs: list[dict[str, Any]]) -> str:
    sample_ids = sorted(set(row["sample_id"] for row in pairs))
    matrix = np.full((len(sample_ids), len(FILTERS)), np.nan)
    for row in pairs:
        sample_index = sample_ids.index(row["sample_id"])
        if int(row["filter_nm"]) not in FILTERS:
            continue
        filter_index = FILTERS.index(int(row["filter_nm"]))
        value = row.get("absolute_shape_difference")
        if value not in {"", None}:
            matrix[sample_index, filter_index] = float(value)

    fig, ax = plt.subplots(figsize=(11.5, max(4.2, 0.7 * len(sample_ids) + 2.5)))
    image = ax.imshow(matrix, aspect="auto", cmap="YlGnBu_r", vmin=0, vmax=1)
    ax.set_xticks(range(len(FILTERS)))
    ax.set_xticklabels([str(x) for x in FILTERS])
    ax.set_yticks(range(len(sample_ids)))
    ax.set_yticklabels(sample_ids, fontsize=8)
    ax.set_xlabel("Filtru / lungime de unda (nm)")
    ax.set_title("Diferenta absoluta intre forma camerei si forma spectrometrului\n0 = potrivire mai buna, 1 = diferenta mare")
    for row_index in range(matrix.shape[0]):
        for col_index in range(matrix.shape[1]):
            value = matrix[row_index, col_index]
            text = "NA" if not np.isfinite(value) else f"{value:.2f}"
            ax.text(col_index, row_index, text, ha="center", va="center", fontsize=8, color="#111111")
    fig.colorbar(image, ax=ax, label="diferenta absoluta")
    fig.tight_layout()
    out = GRAPH_DIR / "camera_vs_spectrometer_difference_heatmap.png"
    fig.savefig(out, dpi=180)
    plt.close(fig)
    return str(out)


def make_gallery(graph_paths: list[str]) -> str:
    thumbs: list[tuple[str, Image.Image]] = []
    for raw in graph_paths:
        path = Path(raw)
        if not path.exists():
            continue
        with Image.open(path) as image:
            thumb = image.convert("RGB")
            thumb.thumbnail((620, 420))
            canvas = Image.new("RGB", (660, 500), "white")
            canvas.paste(thumb, ((660 - thumb.width) // 2, 20))
            draw = ImageDraw.Draw(canvas)
            draw.text((18, 455), path.name[:92], fill=(25, 25, 25))
            thumbs.append((path.name, canvas))
    if not thumbs:
        return ""
    cols = 2
    rows = int(math.ceil(len(thumbs) / cols))
    sheet = Image.new("RGB", (cols * 660, rows * 500), "white")
    for index, (_, thumb) in enumerate(thumbs):
        sheet.paste(thumb, ((index % cols) * 660, (index // cols) * 500))
    out = OUT_DIR / "graph_gallery.jpg"
    sheet.save(out, quality=92)
    return str(out)


def main() -> None:
    if OUT_DIR.exists():
        shutil.rmtree(OUT_DIR)
    GRAPH_DIR.mkdir(parents=True, exist_ok=True)

    binned_rows, spectrum_lookup = build_spectrum_rows()
    spectrometer_graphs = plot_spectrometer_per_sample(spectrum_lookup)
    comparison_pairs, correlation_rows = build_camera_comparison_rows(spectrum_lookup)
    comparison_graphs = [
        plot_comparison_by_sample(comparison_pairs),
        plot_scatter(comparison_pairs),
        plot_difference_heatmap(comparison_pairs),
    ]

    write_csv(OUT_DIR / "spectrometer_10nm_binned_indoor_only.csv", binned_rows)
    write_csv(OUT_DIR / "camera_spectrometer_comparison_indoor_only.csv", comparison_pairs)
    write_csv(OUT_DIR / "camera_spectrometer_correlations_indoor_only.csv", correlation_rows)
    gallery = make_gallery(comparison_graphs + spectrometer_graphs)

    if DESKTOP_DIR.exists():
        shutil.rmtree(DESKTOP_DIR)
    shutil.copytree(OUT_DIR, DESKTOP_DIR)

    summary = {
        "mode": "indoor_only_no_afara",
        "data_root": str(INDOOR_ROOT),
        "output_dir": str(OUT_DIR),
        "desktop_copy": str(DESKTOP_DIR),
        "spectrometer_txt_files_used": len({row["relative_path"] for row in binned_rows}),
        "binned_rows_10nm": len(binned_rows),
        "camera_spectrometer_pairs": len(comparison_pairs),
        "sample_correlations": correlation_rows,
        "graphs": {
            "comparison": comparison_graphs,
            "spectrometer_per_set": spectrometer_graphs,
            "gallery": gallery,
        },
        "csv_files": {
            "spectrometer_10nm": str(OUT_DIR / "spectrometer_10nm_binned_indoor_only.csv"),
            "camera_spectrometer_comparison": str(OUT_DIR / "camera_spectrometer_comparison_indoor_only.csv"),
            "correlations": str(OUT_DIR / "camera_spectrometer_correlations_indoor_only.csv"),
        },
    }
    (OUT_DIR / "summary.json").write_text(json.dumps(summary, indent=2), encoding="utf-8")
    (DESKTOP_DIR / "summary.json").write_text(json.dumps(summary, indent=2), encoding="utf-8")
    print(json.dumps(summary, indent=2))


if __name__ == "__main__":
    main()
