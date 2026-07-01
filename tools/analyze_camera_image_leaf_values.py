"""Measure leaf-only camera values for the real data analysis image folders."""

from __future__ import annotations

import csv
import json
import math
import os
import re
import sys
from collections import defaultdict
from pathlib import Path
from typing import Any

import cv2
import numpy as np
import xlsxwriter
from PIL import Image, ImageDraw, ImageFont


ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from plant_health_mvp_new_data.core.camera_calibration import build_camera_calibration_section
from plant_health_mvp_new_data.core.models.sample import SpectralSample
from plant_health_mvp_new_data.core.vegetation import build_vegetation_mask


DATA_ROOT = Path(os.environ.get("SPECTRALEAF_DATA_ROOT", r"C:\Users\david\OneDrive\Desktop\data analisys"))
OUT_DIR = Path(os.environ.get("SPECTRALEAF_CAMERA_OUT_DIR", ROOT / "outputs" / "camera_image_leaf_values"))
OVERLAY_DIR = OUT_DIR / "mask_overlays"
FILTER_WAVELENGTHS = (532, 556, 680, 725, 850, 940)
EPS = 1e-8


def rel(path: Path) -> str:
    try:
        return str(path.relative_to(DATA_ROOT))
    except ValueError:
        return str(path)


def round_float(value: Any, digits: int = 6) -> Any:
    try:
        f = float(value)
    except (TypeError, ValueError):
        return ""
    if not math.isfinite(f):
        return ""
    return round(f, digits)


def infer_filter(path: Path) -> int | None:
    match = re.search(r"(532|556|580|650|680|725|850|940|950)", path.stem)
    if not match:
        return None
    value = int(match.group(1))
    if value == 950:
        return 940
    return value


def load_rgb(path: Path) -> np.ndarray:
    with Image.open(path) as image:
        return np.asarray(image.convert("RGB"), dtype=np.float32) / 255.0


def load_filter_band(path: Path) -> np.ndarray:
    rgb = load_rgb(path)
    return np.max(rgb, axis=2).astype(np.float32, copy=False)


def image_groups() -> dict[Path, list[Path]]:
    groups: dict[Path, list[Path]] = defaultdict(list)
    for path in sorted(DATA_ROOT.rglob("*")):
        if path.suffix.lower() not in {".jpg", ".jpeg", ".png", ".tif", ".tiff", ".bmp"}:
            continue
        sample_dir = path.parent.parent if path.parent.name.lower() == "camera" else path.parent
        groups[sample_dir].append(path)
    return dict(groups)


def sample_role(sample_dir: Path) -> str:
    lower = rel(sample_dir).lower()
    if "referinta alba" in lower:
        return "white_reference"
    if "refirinta neagra" in lower or "referinta neagra" in lower:
        return "dark_reference"
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
    if "verde" in lower or "sanatoasa" in lower or "\\san" in lower:
        return "healthy"
    return "leaf_unknown"


def build_group_mask(sample_dir: Path, image_paths: list[Path]) -> tuple[np.ndarray, dict[str, Any]]:
    first = load_rgb(image_paths[0])
    role = sample_role(sample_dir)
    if role != "leaf_sample":
        mask = np.ones(first.shape[:2], dtype=bool)
        return mask, {
            "method": "full_frame_reference",
            "vegetation_pixel_count": int(mask.sum()),
            "area_fraction": 1.0,
            "used_bands": [],
            "fallback_reason": "Reference frame, not a leaf image.",
        }

    target_bands: dict[str, np.ndarray] = {}
    wavelengths: list[float] = []
    arrays: list[np.ndarray] = []
    for path in sorted(image_paths, key=lambda p: (infer_filter(p) or 9999, p.name.lower())):
        wavelength = infer_filter(path)
        if wavelength is None or wavelength not in FILTER_WAVELENGTHS:
            continue
        band = load_filter_band(path)
        target_bands[str(wavelength)] = band
        wavelengths.append(float(wavelength))
        arrays.append(band)

    if not target_bands:
        value = np.max(first, axis=2)
        threshold = np.percentile(value, 80)
        mask = value > threshold
        return mask, {
            "method": "fallback_value_percentile_80",
            "vegetation_pixel_count": int(mask.sum()),
            "area_fraction": float(mask.mean()),
            "used_bands": [],
            "fallback_reason": "No numeric filter images were available for app-style mask.",
        }

    sample = SpectralSample(
        source_type="mixed_image_bundle",
        available_wavelengths=np.asarray(wavelengths, dtype=float),
        data=np.stack(arrays, axis=-1),
        target_bands=target_bands,
        metadata={"source_data_kind": "mixed_image_data", "camera_calibration_eligible": True},
    )
    mask, metadata = build_vegetation_mask(sample)
    if mask is None or int(np.count_nonzero(mask)) == 0:
        value = np.max(first, axis=2)
        threshold = np.percentile(value, 90)
        mask = value > threshold
        metadata = {
            "method": "fallback_value_percentile_90",
            "vegetation_pixel_count": int(mask.sum()),
            "area_fraction": float(mask.mean()),
            "used_bands": [],
            "fallback_reason": "App foreground mask failed; used strict brightness fallback.",
        }
    metadata = dict(metadata)
    metadata["vegetation_pixel_count"] = int(np.count_nonzero(mask))
    metadata["area_fraction"] = float(np.count_nonzero(mask) / mask.size)
    return np.asarray(mask, dtype=bool), metadata


def mask_geometry(mask: np.ndarray) -> dict[str, Any]:
    ys, xs = np.where(mask)
    if xs.size == 0:
        return {
            "mask_bbox_x": "",
            "mask_bbox_y": "",
            "mask_bbox_width": "",
            "mask_bbox_height": "",
            "mask_centroid_x": "",
            "mask_centroid_y": "",
        }
    return {
        "mask_bbox_x": int(xs.min()),
        "mask_bbox_y": int(ys.min()),
        "mask_bbox_width": int(xs.max() - xs.min() + 1),
        "mask_bbox_height": int(ys.max() - ys.min() + 1),
        "mask_centroid_x": round_float(np.mean(xs), 2),
        "mask_centroid_y": round_float(np.mean(ys), 2),
    }


def stats(values: np.ndarray, prefix: str) -> dict[str, Any]:
    vals = np.asarray(values, dtype=float)
    vals = vals[np.isfinite(vals)]
    if vals.size == 0:
        return {f"{prefix}_{name}": "" for name in ("mean", "median", "std", "p05", "p25", "p75", "p95", "min", "max")}
    percentiles = np.percentile(vals, [5, 25, 75, 95])
    return {
        f"{prefix}_mean": round_float(np.mean(vals)),
        f"{prefix}_median": round_float(np.median(vals)),
        f"{prefix}_std": round_float(np.std(vals)),
        f"{prefix}_p05": round_float(percentiles[0]),
        f"{prefix}_p25": round_float(percentiles[1]),
        f"{prefix}_p75": round_float(percentiles[2]),
        f"{prefix}_p95": round_float(percentiles[3]),
        f"{prefix}_min": round_float(np.min(vals)),
        f"{prefix}_max": round_float(np.max(vals)),
    }


def pixel_metrics(path: Path, mask: np.ndarray) -> dict[str, Any]:
    rgb = load_rgb(path)
    if mask.shape != rgb.shape[:2]:
        mask = cv2.resize(mask.astype(np.uint8), (rgb.shape[1], rgb.shape[0]), interpolation=cv2.INTER_NEAREST) > 0
    selected = rgb[mask]
    if selected.size == 0:
        selected = rgb.reshape(-1, 3)

    red = selected[:, 0]
    green = selected[:, 1]
    blue = selected[:, 2]
    brightness = np.max(selected, axis=1)
    min_channel = np.min(selected, axis=1)
    saturation = (brightness - min_channel) / (brightness + EPS)
    luminance = (0.2126 * red) + (0.7152 * green) + (0.0722 * blue)
    total = red + green + blue + EPS
    gcc = green / total
    exg = (2.0 * green) - red - blue
    vari = (green - red) / (green + red - blue + EPS)
    rg_ratio = red / (green + EPS)
    bg_ratio = blue / (green + EPS)

    out: dict[str, Any] = {}
    out.update(stats(red, "r_0_1"))
    out.update(stats(green, "g_0_1"))
    out.update(stats(blue, "b_0_1"))
    out.update(stats(red * 255.0, "r_0_255"))
    out.update(stats(green * 255.0, "g_0_255"))
    out.update(stats(blue * 255.0, "b_0_255"))
    out.update(stats(brightness, "value_0_1"))
    out.update(stats(brightness * 255.0, "value_0_255"))
    out.update(stats(luminance, "luminance_0_1"))
    out.update(stats(saturation, "saturation"))
    out.update(stats(gcc, "gcc"))
    out.update(stats(exg, "exg"))
    out.update(stats(vari, "vari"))
    out.update(stats(rg_ratio, "red_green_ratio"))
    out.update(stats(bg_ratio, "blue_green_ratio"))
    return out


def read_spectrum(path: Path) -> tuple[np.ndarray, np.ndarray] | None:
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
        return None
    arr = np.asarray(pairs, dtype=float)
    return arr[:, 0], arr[:, 1]


def spectrometer_window(path: Path, wavelength: int, half_width: float = 10.0) -> float | None:
    parsed = read_spectrum(path)
    if parsed is None:
        return None
    waves, intensities = parsed
    window = (waves >= wavelength - half_width) & (waves <= wavelength + half_width) & np.isfinite(intensities)
    if not np.any(window):
        return None
    return float(np.nanmedian(intensities[window]))


def match_spectrum_file(sample_dir: Path, wavelength: int | None, filter_name: str) -> Path | None:
    spectrum_dir = sample_dir / "spectru"
    if not spectrum_dir.exists():
        return None
    candidates = list(spectrum_dir.glob("*.txt"))
    if not candidates:
        return None
    if wavelength is not None:
        exact = [p for p in candidates if infer_filter(p) == wavelength]
        if exact:
            return sorted(exact, key=lambda p: len(p.name))[0]
    if filter_name == "fara":
        no_filter = [p for p in candidates if "fara" in p.name.lower()]
        if no_filter:
            return sorted(no_filter, key=lambda p: len(p.name))[0]
    return None


def safe_index(a: float | None, b: float | None) -> Any:
    if a is None or b is None:
        return ""
    denom = a + b
    if abs(denom) < EPS:
        return ""
    return round_float((a - b) / denom)


def ratio(a: float | None, b: float | None) -> Any:
    if a is None or b is None or abs(b) < EPS:
        return ""
    return round_float(a / b)


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


def overlay_for_sample(sample_dir: Path, image_paths: list[Path], mask: np.ndarray, metadata: dict[str, Any]) -> str:
    if sample_role(sample_dir) != "leaf_sample":
        return ""
    preferred = None
    for name in ("fara.jpg", "850.jpg", "680.jpg", "725.jpg", "532.jpg"):
        for path in image_paths:
            if path.name.lower() == name:
                preferred = path
                break
        if preferred is not None:
            break
    if preferred is None:
        preferred = image_paths[0]

    rgb = (load_rgb(preferred) * 255.0).astype(np.uint8)
    if mask.shape != rgb.shape[:2]:
        mask = cv2.resize(mask.astype(np.uint8), (rgb.shape[1], rgb.shape[0]), interpolation=cv2.INTER_NEAREST) > 0

    overlay = rgb.copy()
    overlay[~mask] = (overlay[~mask] * 0.28).astype(np.uint8)
    green = np.array([40, 210, 95], dtype=np.float32)
    overlay[mask] = np.clip((overlay[mask].astype(np.float32) * 0.74) + (green * 0.26), 0, 255).astype(np.uint8)
    contours, _ = cv2.findContours(mask.astype(np.uint8), cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
    cv2.drawContours(overlay, contours, -1, (25, 255, 90), 3)

    image = Image.fromarray(overlay)
    draw = ImageDraw.Draw(image)
    label = f"{rel(sample_dir)} | area={metadata.get('area_fraction', 0):.3f} | {metadata.get('method')}"
    draw.rectangle((0, 0, image.width, 42), fill=(0, 0, 0))
    draw.text((14, 12), label, fill=(255, 255, 255))
    out_name = re.sub(r"[^A-Za-z0-9_-]+", "_", rel(sample_dir)).strip("_") + "_mask_overlay.jpg"
    out_path = OVERLAY_DIR / out_name
    out_path.parent.mkdir(parents=True, exist_ok=True)
    image.save(out_path, quality=92)
    return str(out_path)


def make_contact_sheet(overlay_paths: list[str]) -> Path | None:
    if not overlay_paths:
        return None
    thumbs = []
    for raw in overlay_paths:
        path = Path(raw)
        if not path.exists():
            continue
        with Image.open(path) as image:
            thumb = image.convert("RGB")
            thumb.thumbnail((520, 320))
            canvas = Image.new("RGB", (540, 360), "white")
            canvas.paste(thumb, ((540 - thumb.width) // 2, 20))
            thumbs.append(canvas)
    if not thumbs:
        return None
    cols = 2
    rows = int(math.ceil(len(thumbs) / cols))
    sheet = Image.new("RGB", (cols * 540, rows * 360), "white")
    for index, thumb in enumerate(thumbs):
        x = (index % cols) * 540
        y = (index // cols) * 360
        sheet.paste(thumb, (x, y))
    out_path = OUT_DIR / "leaf_mask_contact_sheet.jpg"
    sheet.save(out_path, quality=92)
    return out_path


def add_calibration_to_rows(rows: list[dict[str, Any]], average_bands: dict[str, float]) -> dict[str, Any]:
    calibration = build_camera_calibration_section(
        average_bands,
        {"source_data_kind": "mixed_image_data", "camera_calibration_eligible": True},
    )
    corrected = calibration.get("corrected_bands", {})
    for row in rows:
        wavelength = row.get("filter_nm")
        if wavelength in ("", None):
            continue
        item = corrected.get(str(int(wavelength)), {}) if isinstance(corrected, dict) else {}
        if not isinstance(item, dict):
            continue
        for key in (
            "white_reference_brightness",
            "white_normalized_camera",
            "source_curve_compensated_camera",
            "source_curve_compensation_multiplier_vs_850",
            "source_curve_reliability_weight",
            "source_curve_status",
            "spectrometer_target_reliability",
            "dark_white_reflectance_proxy",
            "dark_white_status",
            "best_spectrometer_window_intensity",
            "best_spectrometer_model",
            "single_band_leave_one_leaf_out_rmse",
        ):
            row[f"app_calibration_{key}"] = item.get(key, "")
    return calibration


def build_sample_summary(rows: list[dict[str, Any]], mask_records: list[dict[str, Any]]) -> list[dict[str, Any]]:
    by_sample: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for row in rows:
        if row.get("sample_role") == "leaf_sample":
            by_sample[str(row["sample_id"])].append(row)
    mask_by_sample = {str(row["sample_id"]): row for row in mask_records}

    summaries: list[dict[str, Any]] = []
    for sample_id, sample_rows in sorted(by_sample.items()):
        first = sample_rows[0]
        summary: dict[str, Any] = {
            "sample_id": sample_id,
            "condition": first.get("condition", ""),
            "image_count": len(sample_rows),
            "mask_pixels": mask_by_sample.get(sample_id, {}).get("mask_pixels", ""),
            "mask_area_fraction": mask_by_sample.get(sample_id, {}).get("mask_area_fraction", ""),
            "mask_method": mask_by_sample.get(sample_id, {}).get("mask_method", ""),
        }
        mean_by_band: dict[int, float] = {}
        median_by_band: dict[int, float] = {}
        white_mean_by_band: dict[int, float] = {}
        white_median_by_band: dict[int, float] = {}
        best_spec_by_band: dict[int, float] = {}
        for row in sample_rows:
            wavelength = row.get("filter_nm")
            if wavelength in ("", None):
                continue
            wavelength = int(wavelength)
            mean_by_band[wavelength] = float(row.get("value_0_1_mean") or 0.0)
            median_by_band[wavelength] = float(row.get("value_0_1_median") or 0.0)
            app_white = row.get("app_calibration_white_normalized_camera")
            best_spec = row.get("app_calibration_best_spectrometer_window_intensity")
            if app_white not in ("", None):
                white_mean_by_band[wavelength] = float(app_white)
            current_white_mean = row.get("current_white_normalized_value_mean")
            current_white_median = row.get("current_white_normalized_value_median")
            if current_white_mean not in ("", None):
                white_mean_by_band[wavelength] = float(current_white_mean)
            if current_white_median not in ("", None):
                white_median_by_band[wavelength] = float(current_white_median)
            if best_spec not in ("", None):
                best_spec_by_band[wavelength] = float(best_spec)
        for wavelength in FILTER_WAVELENGTHS:
            summary[f"raw_mean_{wavelength}"] = round_float(mean_by_band.get(wavelength))
            summary[f"raw_median_{wavelength}"] = round_float(median_by_band.get(wavelength))
            summary[f"white_norm_mean_{wavelength}"] = round_float(white_mean_by_band.get(wavelength))
            summary[f"white_norm_median_{wavelength}"] = round_float(white_median_by_band.get(wavelength))
            summary[f"best_spectrometer_estimate_{wavelength}"] = round_float(best_spec_by_band.get(wavelength))
        summary["NDVI_like_raw_mean_850_680"] = safe_index(mean_by_band.get(850), mean_by_band.get(680))
        summary["NDRE_like_raw_mean_850_725"] = safe_index(mean_by_band.get(850), mean_by_band.get(725))
        summary["GNDVI_like_raw_mean_850_556"] = safe_index(mean_by_band.get(850), mean_by_band.get(556))
        summary["raw_ratio_850_680"] = ratio(mean_by_band.get(850), mean_by_band.get(680))
        summary["NDVI_like_white_norm_mean_850_680"] = safe_index(white_mean_by_band.get(850), white_mean_by_band.get(680))
        summary["NDRE_like_white_norm_mean_850_725"] = safe_index(white_mean_by_band.get(850), white_mean_by_band.get(725))
        summary["GNDVI_like_white_norm_mean_850_556"] = safe_index(white_mean_by_band.get(850), white_mean_by_band.get(556))
        summary["white_norm_ratio_850_680"] = ratio(white_mean_by_band.get(850), white_mean_by_band.get(680))
        summary["NDVI_like_best_spec_850_680"] = safe_index(best_spec_by_band.get(850), best_spec_by_band.get(680))
        summary["NDRE_like_best_spec_850_725"] = safe_index(best_spec_by_band.get(850), best_spec_by_band.get(725))
        summaries.append(summary)
    return summaries


def write_workbook(
    workbook_path: Path,
    image_rows: list[dict[str, Any]],
    summary_rows: list[dict[str, Any]],
    reference_rows: list[dict[str, Any]],
    mask_rows: list[dict[str, Any]],
) -> None:
    workbook_path.parent.mkdir(parents=True, exist_ok=True)
    wb = xlsxwriter.Workbook(str(workbook_path))
    header_fmt = wb.add_format({"bold": True, "bg_color": "#DDEBDB", "border": 1, "text_wrap": True})
    note_fmt = wb.add_format({"text_wrap": True, "valign": "top"})
    num_fmt = wb.add_format({"num_format": "0.0000"})

    def add_sheet(name: str, rows: list[dict[str, Any]], freeze: bool = True) -> None:
        ws = wb.add_worksheet(name[:31])
        if not rows:
            ws.write(0, 0, "No rows")
            return
        headers: list[str] = []
        for row in rows:
            for key in row:
                if key not in headers:
                    headers.append(key)
        for col, header in enumerate(headers):
            ws.write(0, col, header, header_fmt)
            ws.set_column(col, col, min(max(len(header) + 2, 10), 28), num_fmt if any(token in header for token in ("mean", "median", "std", "p05", "p95", "ratio", "ND")) else None)
        for row_index, row in enumerate(rows, start=1):
            for col, header in enumerate(headers):
                value = row.get(header, "")
                ws.write(row_index, col, value)
        ws.autofilter(0, 0, len(rows), len(headers) - 1)
        if freeze:
            ws.freeze_panes(1, 0)

    notes = [
        {
            "item": "What was measured",
            "value": "Every JPG in the real data folder. Leaf samples use a shared app-style foreground mask per sample. Reference images use the full frame.",
        },
        {
            "item": "Main camera value",
            "value": "value_0_1 is max(R,G,B), the same filtered-camera intensity basis used by the app calibration profile.",
        },
        {
            "item": "Median vs mean",
            "value": "Median is more robust to hot pixels and glare. Mean matches the app's average-band calibration path more closely.",
        },
        {
            "item": "White normalization",
            "value": "current_white_normalized_* divides each leaf camera value by the matching white reference image from this dataset.",
        },
        {
            "item": "Spectrometer estimate",
            "value": "app_calibration_best_spectrometer_window_intensity is the app calibration estimate trained against spectrometer +/-10 nm windows. 940 nm is low-confidence/excluded where the calibration profile marks it that way.",
        },
    ]

    add_sheet("Summary", summary_rows)
    add_sheet("Image metrics", image_rows)
    add_sheet("References", reference_rows)
    add_sheet("Mask QA", mask_rows)
    add_sheet("Notes", notes, freeze=False)
    ws = wb.get_worksheet_by_name("Notes")
    if ws is not None:
        ws.set_column(0, 0, 24)
        ws.set_column(1, 1, 120, note_fmt)
    wb.close()


def main() -> None:
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    groups = image_groups()
    image_rows: list[dict[str, Any]] = []
    reference_rows: list[dict[str, Any]] = []
    mask_rows: list[dict[str, Any]] = []
    overlays: list[str] = []

    masks: dict[Path, tuple[np.ndarray, dict[str, Any]]] = {}
    for sample_dir, paths in sorted(groups.items(), key=lambda item: rel(item[0]).lower()):
        mask, metadata = build_group_mask(sample_dir, paths)
        masks[sample_dir] = (mask, metadata)
        geom = mask_geometry(mask)
        overlay = overlay_for_sample(sample_dir, paths, mask, metadata)
        if overlay:
            overlays.append(overlay)
        mask_rows.append(
            {
                "sample_id": rel(sample_dir),
                "sample_role": sample_role(sample_dir),
                "condition": sample_condition(sample_dir),
                "mask_method": metadata.get("method", ""),
                "mask_pixels": int(np.count_nonzero(mask)),
                "mask_area_fraction": round_float(np.count_nonzero(mask) / mask.size),
                "used_bands": ",".join(str(x) for x in metadata.get("used_bands", []) or []),
                "foreground_score": metadata.get("foreground_score", ""),
                "threshold_strategy": metadata.get("threshold_strategy", ""),
                "threshold_cutoff_normalized": round_float(metadata.get("threshold_cutoff_normalized")),
                "fallback_reason": metadata.get("fallback_reason", ""),
                "overlay_path": overlay,
                **geom,
            }
        )

    contact_sheet = make_contact_sheet(overlays)

    white_refs_mean: dict[int, float] = {}
    white_refs_median: dict[int, float] = {}
    dark_value_mean: float | None = None
    dark_value_median: float | None = None

    for sample_dir, paths in groups.items():
        if sample_role(sample_dir) == "white_reference":
            mask, _ = masks[sample_dir]
            for path in paths:
                wavelength = infer_filter(path)
                if wavelength is None:
                    continue
                metrics = pixel_metrics(path, mask)
                white_refs_mean[wavelength] = float(metrics["value_0_1_mean"])
                white_refs_median[wavelength] = float(metrics["value_0_1_median"])
        elif sample_role(sample_dir) == "dark_reference":
            mask, _ = masks[sample_dir]
            dark_paths = [p for p in paths if p.name.lower().startswith("fara")]
            if dark_paths:
                metrics = pixel_metrics(dark_paths[0], mask)
                dark_value_mean = float(metrics["value_0_1_mean"])
                dark_value_median = float(metrics["value_0_1_median"])

    for sample_dir, paths in sorted(groups.items(), key=lambda item: rel(item[0]).lower()):
        mask, metadata = masks[sample_dir]
        role = sample_role(sample_dir)
        condition = sample_condition(sample_dir)
        group_rows: list[dict[str, Any]] = []
        average_bands_for_calibration: dict[str, float] = {}

        for path in sorted(paths, key=lambda p: (infer_filter(p) or 9999, p.name.lower())):
            wavelength = infer_filter(path)
            filter_label = str(wavelength) if wavelength is not None else path.stem.lower()
            metrics = pixel_metrics(path, mask)
            spectrum_path = match_spectrum_file(sample_dir, wavelength, filter_label)
            spec_window = None
            if spectrum_path is not None and wavelength is not None:
                spec_window = spectrometer_window(spectrum_path, wavelength)

            white_mean = white_refs_mean.get(wavelength) if wavelength is not None else None
            white_median = white_refs_median.get(wavelength) if wavelength is not None else None
            value_mean = float(metrics.get("value_0_1_mean") or 0.0)
            value_median = float(metrics.get("value_0_1_median") or 0.0)
            if role == "leaf_sample" and wavelength is not None:
                average_bands_for_calibration[str(wavelength)] = value_mean

            row: dict[str, Any] = {
                "sample_id": rel(sample_dir),
                "sample_role": role,
                "condition": condition,
                "image_file": path.name,
                "relative_path": rel(path),
                "filter_label": filter_label,
                "filter_nm": wavelength if wavelength is not None else "",
                "width_px": int(load_rgb(path).shape[1]),
                "height_px": int(load_rgb(path).shape[0]),
                "file_size_bytes": path.stat().st_size,
                "mask_method": metadata.get("method", ""),
                "mask_pixels": int(np.count_nonzero(mask)),
                "mask_area_fraction": round_float(np.count_nonzero(mask) / mask.size),
                "matched_spectrum_file": rel(spectrum_path) if spectrum_path is not None else "",
                "spectrometer_window_median_at_filter": round_float(spec_window),
                "current_white_reference_value_mean": round_float(white_mean),
                "current_white_reference_value_median": round_float(white_median),
                "current_dark_reference_value_mean": round_float(dark_value_mean),
                "current_dark_reference_value_median": round_float(dark_value_median),
                "current_white_normalized_value_mean": round_float(value_mean / white_mean) if white_mean and white_mean > EPS and role == "leaf_sample" else "",
                "current_white_normalized_value_median": round_float(value_median / white_median) if white_median and white_median > EPS and role == "leaf_sample" else "",
                "current_dark_white_reflectance_mean": (
                    round_float((value_mean - dark_value_mean) / (white_mean - dark_value_mean))
                    if role == "leaf_sample"
                    and white_mean is not None
                    and dark_value_mean is not None
                    and abs(white_mean - dark_value_mean) > EPS
                    else ""
                ),
                **mask_geometry(mask),
                **metrics,
            }
            if role == "white_reference":
                reference_rows.append({**row, "reference_kind": "white"})
            elif role == "dark_reference":
                reference_rows.append({**row, "reference_kind": "dark"})
            group_rows.append(row)

        if role == "leaf_sample":
            add_calibration_to_rows(group_rows, average_bands_for_calibration)

        image_rows.extend(group_rows)

    summary_rows = build_sample_summary(image_rows, mask_rows)

    image_csv = OUT_DIR / "image_leaf_values.csv"
    summary_csv = OUT_DIR / "sample_summary.csv"
    reference_csv = OUT_DIR / "reference_values.csv"
    mask_csv = OUT_DIR / "mask_quality.csv"
    workbook_path = OUT_DIR / "camera_leaf_image_values.xlsx"
    summary_json = OUT_DIR / "analysis_summary.json"

    write_csv(image_csv, image_rows)
    write_csv(summary_csv, summary_rows)
    write_csv(reference_csv, reference_rows)
    write_csv(mask_csv, mask_rows)
    write_workbook(workbook_path, image_rows, summary_rows, reference_rows, mask_rows)

    summary_payload = {
        "data_root": str(DATA_ROOT),
        "output_dir": str(OUT_DIR),
        "image_count": len(image_rows),
        "leaf_sample_count": len(summary_rows),
        "reference_image_count": len(reference_rows),
        "mask_contact_sheet": str(contact_sheet) if contact_sheet is not None else "",
        "workbook": str(workbook_path),
        "csv_files": {
            "image_leaf_values": str(image_csv),
            "sample_summary": str(summary_csv),
            "reference_values": str(reference_csv),
            "mask_quality": str(mask_csv),
        },
    }
    summary_json.write_text(json.dumps(summary_payload, indent=2), encoding="utf-8")
    print(json.dumps(summary_payload, indent=2))


if __name__ == "__main__":
    main()
