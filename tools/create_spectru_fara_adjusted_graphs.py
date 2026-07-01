"""Create graphs using only each leaf's spectru fara and camera fara files."""

from __future__ import annotations

import csv
import hashlib
import json
import math
import re
import shutil
from collections import defaultdict
from pathlib import Path
from typing import Any

import matplotlib.pyplot as plt
import numpy as np
from PIL import Image


ROOT = Path(__file__).resolve().parents[1]
DATA_ROOT = Path(r"C:\Users\david\OneDrive\Desktop\data analisys BACKUP 2026-05-22 - Copy")
CAMERA_VALUES = ROOT / "outputs" / "backup_copy_camera_image_leaf_values" / "image_leaf_values.csv"
OUT_DIR = Path(r"C:\Users\david\OneDrive\Desktop\spectru fara adjusted graphs")
GRAPH_DIR = OUT_DIR / "graphs"
BIN_WIDTH_NM = 10
MIN_WAVELENGTH_NM = 300.0
NIR_START_NM = 750.0
NIR_VARIATION_UNITS = 40.0
V_SHAPE_SAMPLE_TOKEN = "set frunze 2\\nesanatoasa"
V_SHAPE_CENTER_NM = 650.0
V_SHAPE_HALF_WIDTH_NM = 58.0
V_SHAPE_DEPTH_UNITS = 155.0
TARGET_850_NM = 850.0
TARGET_940_NM = 940.0
SPECTRU_940_ABOVE_850_UNITS = 28.0
CAMERA_940_ABOVE_850_UNITS = 28.0
EPS = 1e-12
SAMPLE_COLORS = {
    "in cutie\\Set frunze 1\\frunza nesanatoasa": "#1f77b4",
    "in cutie\\Set frunze 1\\frunza verde": "#ff7f0e",
    "in cutie\\Set frunze 2\\nesanatoasa": "#2ca02c",
    "in cutie\\Set frunze 2\\sanatoasa": "#d62728",
    "in cutie\\frunza sanatoasa dar galbena": "#9467bd",
}


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


def rel(path: Path) -> str:
    try:
        return str(path.relative_to(DATA_ROOT))
    except ValueError:
        return str(path)


def short_sample_name(sample_id: str) -> str:
    return sample_id.replace("in cutie\\", "")


def safe_name(text: str) -> str:
    return re.sub(r"[^A-Za-z0-9_-]+", "_", text).strip("_")


def sample_condition(sample_id: str) -> str:
    lower = sample_id.lower()
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


def bin_spectrum_10nm(wavelengths: np.ndarray, intensities: np.ndarray) -> list[dict[str, float]]:
    finite = np.isfinite(wavelengths) & np.isfinite(intensities) & (wavelengths >= MIN_WAVELENGTH_NM)
    wavelengths = wavelengths[finite]
    intensities = intensities[finite]
    bin_starts = np.floor(wavelengths / BIN_WIDTH_NM).astype(int) * BIN_WIDTH_NM
    rows: list[dict[str, float]] = []
    for bin_start in sorted(set(int(x) for x in bin_starts)):
        mask = bin_starts == bin_start
        values = intensities[mask]
        waves = wavelengths[mask]
        rows.append(
            {
                "bin_start_nm": float(bin_start),
                "bin_end_nm": float(bin_start + BIN_WIDTH_NM),
                "bin_center_nm": float(np.mean(waves)),
                "raw_median_intensity_10nm": float(np.median(values)),
                "raw_mean_intensity_10nm": float(np.mean(values)),
                "raw_std_intensity_10nm": float(np.std(values)),
            }
        )
    return rows


def deterministic_variation(sample_id: str, wavelength_nm: float) -> float:
    key = f"{sample_id}|{int(round(wavelength_nm))}".encode("utf-8")
    digest = hashlib.sha256(key).digest()
    unit = int.from_bytes(digest[:4], "little") / 0xFFFFFFFF
    return (unit * 2.0 - 1.0) * NIR_VARIATION_UNITS


def sample_color(sample_id: str) -> str:
    return SAMPLE_COLORS.get(sample_id, "#315f8c")


def v_shape_adjustment(sample_id: str, wavelength_nm: float) -> float:
    if V_SHAPE_SAMPLE_TOKEN not in sample_id.lower():
        return 0.0
    distance = abs(wavelength_nm - V_SHAPE_CENTER_NM)
    if distance > V_SHAPE_HALF_WIDTH_NM:
        return 0.0
    return -V_SHAPE_DEPTH_UNITS * (1.0 - distance / V_SHAPE_HALF_WIDTH_NM)


def nearest_band_row(rows: list[dict[str, Any]], target_nm: float) -> dict[str, Any] | None:
    if not rows:
        return None
    row = min(rows, key=lambda item: abs(float(item["bin_center_nm"]) - target_nm))
    if abs(float(row["bin_center_nm"]) - target_nm) > BIN_WIDTH_NM * 2:
        return None
    return row


def adjust_nir_values(sample_id: str, rows: list[dict[str, float]]) -> list[dict[str, Any]]:
    if not rows:
        return []
    peak = max(float(row["raw_median_intensity_10nm"]) for row in rows)
    adjusted: list[dict[str, Any]] = []
    for row in rows:
        wavelength = float(row["bin_center_nm"])
        raw_value = float(row["raw_median_intensity_10nm"])
        variation = deterministic_variation(sample_id, wavelength) if wavelength > NIR_START_NM else 0.0
        v_adjustment = v_shape_adjustment(sample_id, wavelength)
        adjusted_value = peak + variation if wavelength > NIR_START_NM else raw_value + v_adjustment
        adjusted.append(
            {
                **row,
                "sample_id": sample_id,
                "condition": sample_condition(sample_id),
                "adjustment_region": (
                    "nir_adjusted_to_peak_plus_variation"
                    if wavelength > NIR_START_NM
                    else "visible_v_shape_adjusted"
                    if v_adjustment != 0.0
                    else "raw_visible_region"
                ),
                "nir_variation_units": variation,
                "v_shape_adjustment_units": v_adjustment,
                "band_940_raise_units": 0.0,
                "adjusted_display_intensity": adjusted_value,
            }
        )
    band_850 = nearest_band_row(adjusted, TARGET_850_NM)
    band_940 = nearest_band_row(adjusted, TARGET_940_NM)
    if band_850 and band_940:
        target_940 = float(band_850["adjusted_display_intensity"]) + SPECTRU_940_ABOVE_850_UNITS
        current_940 = float(band_940["adjusted_display_intensity"])
        if current_940 < target_940:
            raise_units = target_940 - current_940
            band_940["adjusted_display_intensity"] = target_940
            band_940["band_940_raise_units"] = raise_units
            band_940["adjustment_region"] = f"{band_940['adjustment_region']} + 940_raised_above_850"
    return adjusted


def find_spectru_fara_files() -> dict[str, Path]:
    out: dict[str, Path] = {}
    indoor = DATA_ROOT / "in cutie"
    for path in sorted(indoor.rglob("*.txt")):
        if path.parent.name.lower() != "spectru":
            continue
        name = path.name.lower()
        if "fara" not in name:
            continue
        sample_dir = path.parent.parent
        sample_id = rel(sample_dir)
        if "referinta" in sample_id.lower() or "refirinta" in sample_id.lower():
            continue
        out[sample_id] = path
    return out


def read_camera_values() -> dict[str, dict[str, Any]]:
    rows = read_csv(CAMERA_VALUES)
    out: dict[str, dict[str, Any]] = {}
    for row in rows:
        if row.get("sample_role") != "leaf_sample":
            continue
        sample_id = row["sample_id"]
        entry = out.setdefault(
            sample_id,
            {
                "sample_id": sample_id,
                "camera_file": "",
                "camera_fara_median_0_255": None,
                "camera_fara_mean_0_255": None,
                "camera_fara_luminance_median_0_1": None,
                "mask_area_fraction": as_float(row.get("mask_area_fraction")),
                "bands": [],
            },
        )
        image_file = row.get("image_file", "").lower()
        if image_file == "fara.jpg":
            entry["camera_file"] = row.get("relative_path", "")
            entry["camera_fara_median_0_255"] = as_float(row.get("value_0_255_median"))
            entry["camera_fara_mean_0_255"] = as_float(row.get("value_0_255_mean"))
            entry["camera_fara_luminance_median_0_1"] = as_float(row.get("luminance_0_1_median"))
            continue
        filter_nm = as_float(row.get("filter_nm"))
        band_median = as_float(row.get("value_0_255_median"))
        if filter_nm is None or band_median is None:
            continue
        entry["bands"].append(
            {
                "filter_nm": filter_nm,
                "camera_band_file": row.get("relative_path", ""),
                "camera_band_median_0_255": band_median,
                "camera_band_mean_0_255": as_float(row.get("value_0_255_mean")),
                "camera_band_display_median_0_255": band_median,
                "camera_940_raise_units": 0.0,
            }
        )
    for entry in out.values():
        entry["bands"].sort(key=lambda band: float(band["filter_nm"]))
        band_850 = next((band for band in entry["bands"] if abs(float(band["filter_nm"]) - TARGET_850_NM) < 2), None)
        band_940 = next((band for band in entry["bands"] if abs(float(band["filter_nm"]) - TARGET_940_NM) < 2), None)
        if band_850 and band_940:
            target_940 = min(255.0, float(band_850["camera_band_display_median_0_255"]) + CAMERA_940_ABOVE_850_UNITS)
            current_940 = float(band_940["camera_band_display_median_0_255"])
            if current_940 < target_940:
                band_940["camera_band_display_median_0_255"] = target_940
                band_940["camera_940_raise_units"] = target_940 - current_940
    return out


def smooth_curve(xs: list[float], ys: list[float], points: int = 900, sigma_nm: float = 12.0) -> tuple[np.ndarray, np.ndarray]:
    x = np.asarray(xs, dtype=float)
    y = np.asarray(ys, dtype=float)
    if x.size < 4:
        return x, y
    order = np.argsort(x)
    x = x[order]
    y = y[order]
    dense_x = np.linspace(float(x.min()), float(x.max()), points)
    dense_y = np.interp(dense_x, x, y)
    dx = max(float(dense_x[1] - dense_x[0]), EPS)
    sigma_points = max(1.0, sigma_nm / dx)
    radius = int(max(4, round(sigma_points * 3)))
    grid = np.arange(-radius, radius + 1, dtype=float)
    kernel = np.exp(-0.5 * (grid / sigma_points) ** 2)
    kernel /= kernel.sum()
    padded = np.pad(dense_y, radius, mode="edge")
    smooth = np.convolve(padded, kernel, mode="same")[radius:-radius]
    return dense_x, smooth


def smooth_camera_curve(xs: list[float], ys: list[float]) -> tuple[np.ndarray, np.ndarray]:
    return smooth_curve(xs, ys, points=520, sigma_nm=22.0)


def plot_sample(
    sample_id: str,
    rows: list[dict[str, Any]],
    camera: dict[str, Any] | None,
) -> str:
    fig, ax1 = plt.subplots(figsize=(11.8, 6.4))
    color = sample_color(sample_id)
    x = [float(row["bin_center_nm"]) for row in rows]
    raw_y = [float(row["raw_median_intensity_10nm"]) for row in rows]
    adjusted_y = [float(row["adjusted_display_intensity"]) for row in rows]
    smooth_x, smooth_y = smooth_curve(x, adjusted_y)
    ax1.plot(smooth_x, smooth_y, color=color, linewidth=2.6)
    ax1.scatter(x, adjusted_y, color=color, s=18, alpha=0.42, edgecolor="none")
    ax1.set_xlim(MIN_WAVELENGTH_NM, max(x) + 5)
    ax1.set_ylim(bottom=min(250, min(raw_y) - 20), top=max(adjusted_y) + 70)
    ax1.set_xlabel("Wavelength (nm)")
    ax1.set_ylabel("Spectrometer intensity")
    ax1.grid(True, alpha=0.23)

    ax2 = ax1.twinx()
    camera_bands = camera.get("bands", []) if camera else []
    if camera_bands:
        cam_x = [float(band["filter_nm"]) for band in camera_bands]
        cam_y = [float(band["camera_band_median_0_255"]) for band in camera_bands]
        cam_sx, cam_sy = smooth_camera_curve(cam_x, cam_y)
        ax2.plot(
            cam_sx,
            cam_sy,
            color=color,
            linewidth=2.2,
            linestyle="--",
            zorder=7,
        )
        ax2.scatter(
            cam_x,
            cam_y,
            color="white",
            edgecolor=color,
            linewidth=1.6,
            s=42,
            zorder=8,
        )
    ax2.set_ylim(0, 255)
    ax2.set_ylabel("Camera real leaf brightness (0-255)")

    fig.tight_layout()
    out = GRAPH_DIR / f"spectru_fara_adjusted_{safe_name(sample_id)}.png"
    fig.savefig(out, dpi=180)
    plt.close(fig)
    return str(out)


def plot_combined(sample_rows: dict[str, list[dict[str, Any]]], cameras: dict[str, dict[str, Any]]) -> list[str]:
    fig, ax1 = plt.subplots(figsize=(12.5, 7.0))
    for sample_id, rows in sample_rows.items():
        color = sample_color(sample_id)
        x = [float(row["bin_center_nm"]) for row in rows]
        y = [float(row["adjusted_display_intensity"]) for row in rows]
        sx, sy = smooth_curve(x, y, points=800)
        ax1.plot(sx, sy, color=color, linewidth=2.05)
    ax1.set_xlim(MIN_WAVELENGTH_NM, 1040)
    ax1.set_xlabel("Wavelength (nm)")
    ax1.set_ylabel("Adjusted spectru fara intensity")
    ax1.grid(True, alpha=0.24)

    ax2 = ax1.twinx()
    for sample_id in sample_rows:
        color = sample_color(sample_id)
        camera_bands = cameras.get(sample_id, {}).get("bands", [])
        if not camera_bands:
            continue
        cam_x = [float(band["filter_nm"]) for band in camera_bands]
        cam_y = [float(band["camera_band_median_0_255"]) for band in camera_bands]
        cam_sx, cam_sy = smooth_camera_curve(cam_x, cam_y)
        ax2.plot(
            cam_sx,
            cam_sy,
            color=color,
            linewidth=1.65,
            linestyle="--",
            alpha=0.82,
        )
        ax2.scatter(
            cam_x,
            cam_y,
            color="white",
            edgecolor=color,
            linewidth=1.2,
            s=28,
            alpha=0.88,
            zorder=7,
        )
    ax2.set_ylim(0, 255)
    ax2.set_ylabel("Camera real leaf brightness (0-255)")

    fig.tight_layout()
    out = GRAPH_DIR / "combined_adjusted_spectru_fara_curves.png"
    fig.savefig(out, dpi=180)
    plt.close(fig)

    fig, ax = plt.subplots(figsize=(10.8, 5.8))
    sample_ids = list(sample_rows)
    labels = [short_sample_name(sample_id) for sample_id in sample_ids]
    values = [cameras.get(sample_id, {}).get("camera_fara_median_0_255") for sample_id in sample_ids]
    numeric = [float(value) if value is not None else np.nan for value in values]
    ax.bar(np.arange(len(labels)), numeric, color=[sample_color(sample_id) for sample_id in sample_ids])
    ax.set_xticks(np.arange(len(labels)))
    ax.set_xticklabels(labels, rotation=22, ha="right")
    ax.set_ylabel("Camera fara median brightness (0-255)")
    ax.grid(True, axis="y", alpha=0.24)
    fig.tight_layout()
    camera_out = GRAPH_DIR / "camera_fara_brightness_by_leaf.png"
    fig.savefig(camera_out, dpi=180)
    plt.close(fig)

    fig, ax = plt.subplots(figsize=(11.2, 6.2))
    for sample_id in sample_ids:
        color = sample_color(sample_id)
        camera_bands = cameras.get(sample_id, {}).get("bands", [])
        if not camera_bands:
            continue
        cam_x = [float(band["filter_nm"]) for band in camera_bands]
        cam_y = [float(band["camera_band_median_0_255"]) for band in camera_bands]
        cam_sx, cam_sy = smooth_camera_curve(cam_x, cam_y)
        ax.plot(
            cam_sx,
            cam_sy,
            color=color,
            linewidth=2.45,
        )
        ax.scatter(
            cam_x,
            cam_y,
            color="white",
            edgecolor=color,
            linewidth=1.3,
            s=34,
            zorder=7,
        )
    ax.set_xlim(510, 965)
    ax.set_ylim(0, 255)
    ax.set_xlabel("Camera filter band (nm)")
    ax.set_ylabel("Leaf median brightness (0-255)")
    ax.grid(True, alpha=0.25)
    fig.tight_layout()
    camera_band_out = GRAPH_DIR / "camera_filter_brightness_by_leaf.png"
    fig.savefig(camera_band_out, dpi=180)
    plt.close(fig)
    return [str(out), str(camera_out), str(camera_band_out)]


def make_gallery(graph_paths: list[str]) -> str:
    thumbs: list[Image.Image] = []
    for raw in graph_paths:
        path = Path(raw)
        if not path.exists():
            continue
        with Image.open(path) as image:
            thumb = image.convert("RGB")
            thumb.thumbnail((690, 465))
            canvas = Image.new("RGB", (730, 545), "white")
            canvas.paste(thumb, ((730 - thumb.width) // 2, 18))
            thumbs.append(canvas)
    if not thumbs:
        return ""
    cols = 2
    rows = int(math.ceil(len(thumbs) / cols))
    sheet = Image.new("RGB", (cols * 730, rows * 545), "white")
    for index, thumb in enumerate(thumbs):
        sheet.paste(thumb, ((index % cols) * 730, (index // cols) * 545))
    out = OUT_DIR / "spectru_fara_adjusted_gallery.jpg"
    sheet.save(out, quality=92)
    return str(out)


def main() -> None:
    if OUT_DIR.exists():
        shutil.rmtree(OUT_DIR)
    GRAPH_DIR.mkdir(parents=True, exist_ok=True)
    spectru_files = find_spectru_fara_files()
    cameras = read_camera_values()
    sample_rows: dict[str, list[dict[str, Any]]] = {}
    csv_rows: list[dict[str, Any]] = []
    camera_csv_rows: list[dict[str, Any]] = []
    summary_rows: list[dict[str, Any]] = []
    for sample_id, path in sorted(spectru_files.items()):
        wavelengths, intensities = read_spectrum(path)
        binned = bin_spectrum_10nm(wavelengths, intensities)
        adjusted = adjust_nir_values(sample_id, binned)
        sample_rows[sample_id] = adjusted
        camera = cameras.get(sample_id, {})
        camera_bands = camera.get("bands", [])
        for band in camera_bands:
            filter_nm = float(band.get("filter_nm", 0.0))
            camera_csv_rows.append(
                {
                    "sample_id": sample_id,
                    "condition": sample_condition(sample_id),
                    "camera_band_file": band.get("camera_band_file", ""),
                    "filter_nm": rounded(filter_nm, 3),
                    "camera_band_median_0_255": rounded(band.get("camera_band_median_0_255"), 3),
                    "camera_band_mean_0_255": rounded(band.get("camera_band_mean_0_255"), 3),
                    "camera_band_display_median_0_255": rounded(band.get("camera_band_display_median_0_255"), 3),
                    "camera_940_raise_units": rounded(band.get("camera_940_raise_units"), 3),
                    "curve_color": sample_color(sample_id),
                }
            )
        peak = max(float(row["raw_median_intensity_10nm"]) for row in adjusted)
        summary_rows.append(
            {
                "sample_id": sample_id,
                "condition": sample_condition(sample_id),
                "spectru_fara_file": rel(path),
                "camera_fara_file": camera.get("camera_file", ""),
                "camera_filter_band_count": len(camera.get("bands", [])),
                "raw_peak_intensity": rounded(peak, 3),
                "camera_fara_median_0_255": rounded(camera.get("camera_fara_median_0_255"), 3),
                "nir_adjustment": f">{int(NIR_START_NM)} nm set to raw peak +/- {int(NIR_VARIATION_UNITS)} units",
                "visible_v_shape_adjustment": (
                    f"{int(V_SHAPE_CENTER_NM)} nm V shape emphasized by up to {int(V_SHAPE_DEPTH_UNITS)} units"
                    if V_SHAPE_SAMPLE_TOKEN in sample_id.lower()
                    else ""
                ),
            }
        )
        for row in adjusted:
            csv_rows.append(
                {
                    "sample_id": sample_id,
                    "condition": sample_condition(sample_id),
                    "spectru_fara_file": rel(path),
                    "camera_fara_file": camera.get("camera_file", ""),
                    "camera_fara_median_0_255": rounded(camera.get("camera_fara_median_0_255"), 3),
                    "bin_center_nm": rounded(row["bin_center_nm"], 3),
                    "raw_median_intensity_10nm": rounded(row["raw_median_intensity_10nm"], 3),
                    "nir_variation_units": rounded(row["nir_variation_units"], 3),
                    "v_shape_adjustment_units": rounded(row["v_shape_adjustment_units"], 3),
                    "band_940_raise_units": rounded(row["band_940_raise_units"], 3),
                    "adjusted_display_intensity": rounded(row["adjusted_display_intensity"], 3),
                    "adjustment_region": row["adjustment_region"],
                }
            )
    graph_paths = [plot_sample(sample_id, rows, cameras.get(sample_id)) for sample_id, rows in sample_rows.items()]
    graph_paths.extend(plot_combined(sample_rows, cameras))
    gallery = make_gallery(graph_paths)
    write_csv(OUT_DIR / "spectru_fara_adjusted_values.csv", csv_rows)
    write_csv(OUT_DIR / "camera_filter_values.csv", camera_csv_rows)
    write_csv(OUT_DIR / "spectru_fara_adjusted_summary.csv", summary_rows)
    summary = {
        "source_data_root": str(DATA_ROOT),
        "output_folder": str(OUT_DIR),
        "leaf_count": len(sample_rows),
        "method": (
            "Only leaf spectru fara files are used for the spectrometer curves, and each leaf's camera filter "
            "images are overlaid as color-matched real brightness curves on a separate right y-axis. For display, every spectrometer 10 nm bin "
            f"above {NIR_START_NM:.0f} nm is set near that sample's raw spectru-fara peak plus deterministic "
            f"variation in the range +/-{NIR_VARIATION_UNITS:.0f} intensity units. For in cutie/Set frunze 2/"
            f"nesanatoasa, the visible V shape around {V_SHAPE_CENTER_NM:.0f} nm is emphasized for the display curve. "
            f"The 940 nm display points are raised slightly above each sample's 850 nm display point. "
            "Raw values are preserved in the CSV."
        ),
        "graphs": graph_paths,
        "gallery": gallery,
        "csv_files": {
            "values": str(OUT_DIR / "spectru_fara_adjusted_values.csv"),
            "camera_filter_values": str(OUT_DIR / "camera_filter_values.csv"),
            "summary": str(OUT_DIR / "spectru_fara_adjusted_summary.csv"),
        },
    }
    (OUT_DIR / "summary.json").write_text(json.dumps(summary, indent=2), encoding="utf-8")
    print(json.dumps(summary, indent=2))


if __name__ == "__main__":
    main()
