"""Automatic SpectraLeaf capture + analysis bridge.

This script is the PC-side bridge between the ESP32 firmware and the existing
SpectraLeaf analysis logic.

It can run in two modes:
  1. CLI capture:
       python auto_capture_analyze.py run --esp32 http://192.168.4.1
  2. Local browser app:
       python auto_capture_analyze.py serve --port 8765

The ESP32 is expected to expose:
  GET /status
  GET /capture?band=532
"""

from __future__ import annotations

import argparse
import base64
import datetime as dt
import json
import math
import mimetypes
import re
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any

import numpy as np
from PIL import Image, ImageDraw


ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from plant_health_mvp_new_data.core.camera_calibration import build_camera_calibration_section
from plant_health_mvp_new_data.core.models.sample import SpectralSample
from plant_health_mvp_new_data.core.vegetation import build_vegetation_mask


DEFAULT_BANDS = (532, 556, 680, 725, 850, 940)
DEFAULT_OUTPUT_ROOT = ROOT / "outputs" / "esp32_auto_sessions"
EPS = 1e-9


def now_session_id() -> str:
    return dt.datetime.now().strftime("%Y%m%d_%H%M%S")


def parse_bands(raw: str | None) -> list[int]:
    if not raw:
        return list(DEFAULT_BANDS)
    bands = []
    for item in re.split(r"[,;\s]+", raw.strip()):
        if not item:
            continue
        bands.append(int(float(item)))
    return bands


def fetch_bytes(url: str, timeout: float = 20.0) -> bytes:
    request = urllib.request.Request(url, headers={"User-Agent": "SpectraLeafAutoCapture/1.0"})
    with urllib.request.urlopen(request, timeout=timeout) as response:
        return response.read()


def fetch_json(url: str, timeout: float = 8.0) -> dict[str, Any]:
    data = fetch_bytes(url, timeout=timeout)
    return json.loads(data.decode("utf-8", errors="replace"))


def normalize_base_url(raw: str) -> str:
    raw = raw.strip().rstrip("/")
    if not raw:
        raise ValueError("ESP32 URL is empty")
    if not re.match(r"^https?://", raw, re.I):
        raw = "http://" + raw
    return raw


def image_to_rgb_float(path: Path) -> np.ndarray:
    with Image.open(path) as image:
        return np.asarray(image.convert("RGB"), dtype=np.float32) / 255.0


def image_to_band(path: Path) -> np.ndarray:
    rgb = image_to_rgb_float(path)
    return np.max(rgb, axis=2).astype(np.float32, copy=False)


def resize_band_to_shape(band: np.ndarray, shape: tuple[int, int]) -> np.ndarray:
    if band.shape == shape:
        return band
    image = Image.fromarray(np.clip(band * 255.0, 0, 255).astype(np.uint8))
    image = image.resize((shape[1], shape[0]), Image.Resampling.BILINEAR)
    return np.asarray(image, dtype=np.float32) / 255.0


def finite_stats(values: np.ndarray) -> dict[str, float | None]:
    vals = np.asarray(values, dtype=float)
    vals = vals[np.isfinite(vals)]
    if vals.size == 0:
        return {name: None for name in ("mean", "median", "std", "p05", "p25", "p75", "p95", "min", "max")}
    p05, p25, p75, p95 = np.percentile(vals, [5, 25, 75, 95])
    return {
        "mean": float(np.mean(vals)),
        "median": float(np.median(vals)),
        "std": float(np.std(vals)),
        "p05": float(p05),
        "p25": float(p25),
        "p75": float(p75),
        "p95": float(p95),
        "min": float(np.min(vals)),
        "max": float(np.max(vals)),
    }


def rounded(value: Any, digits: int = 6) -> Any:
    try:
        number = float(value)
    except (TypeError, ValueError):
        return None
    if not math.isfinite(number):
        return None
    return round(number, digits)


def safe_index(first: float | None, second: float | None) -> float | None:
    if first is None or second is None:
        return None
    denom = first + second
    if abs(denom) <= EPS:
        return None
    return (first - second) / denom


def safe_ratio(first: float | None, second: float | None, minus_one: bool = False) -> float | None:
    if first is None or second is None or abs(second) <= EPS:
        return None
    value = first / second
    return value - 1.0 if minus_one else value


def compute_indices(values: dict[str, float | None]) -> dict[str, float | None]:
    band_532 = values.get("532")
    band_556 = values.get("556")
    band_680 = values.get("680")
    band_725 = values.get("725")
    band_850 = values.get("850")
    band_940 = values.get("940")
    return {
        "NDVI_850_680": rounded(safe_index(band_850, band_680)),
        "NDRE_850_725": rounded(safe_index(band_850, band_725)),
        "GNDVI_850_556": rounded(safe_index(band_850, band_556)),
        "CIre_850_725": rounded(safe_ratio(band_850, band_725, minus_one=True)),
        "NDWI_850_940_exploratory": rounded(safe_index(band_850, band_940)),
        "green_ratio_850_532": rounded(safe_ratio(band_850, band_532)),
    }


def build_sample_from_images(image_paths: dict[int, Path]) -> SpectralSample:
    target_bands: dict[str, np.ndarray] = {}
    wavelengths: list[float] = []
    arrays: list[np.ndarray] = []
    reference_shape: tuple[int, int] | None = None
    for band, path in sorted(image_paths.items()):
        arr = image_to_band(path)
        if reference_shape is None:
            reference_shape = arr.shape
        else:
            arr = resize_band_to_shape(arr, reference_shape)
        target_bands[str(band)] = arr
        wavelengths.append(float(band))
        arrays.append(arr)

    data = np.stack(arrays, axis=-1) if arrays else None
    return SpectralSample(
        source_type="mixed_image_bundle",
        available_wavelengths=np.asarray(wavelengths, dtype=float),
        data=data,
        target_bands=target_bands,
        metadata={"source_data_kind": "mixed_image_data", "camera_calibration_eligible": True},
    )


def make_overlay(image_path: Path, mask: np.ndarray, output_path: Path) -> None:
    rgb = (image_to_rgb_float(image_path) * 255).astype(np.uint8)
    if mask.shape != rgb.shape[:2]:
        mask_img = Image.fromarray(mask.astype(np.uint8) * 255)
        mask_img = mask_img.resize((rgb.shape[1], rgb.shape[0]), Image.Resampling.NEAREST)
        mask = np.asarray(mask_img) > 0

    overlay = rgb.copy()
    overlay[~mask] = (overlay[~mask] * 0.28).astype(np.uint8)
    green = np.array([40, 215, 95], dtype=np.float32)
    overlay[mask] = np.clip((overlay[mask].astype(np.float32) * 0.72) + (green * 0.28), 0, 255).astype(np.uint8)
    image = Image.fromarray(overlay)
    draw = ImageDraw.Draw(image)
    draw.rectangle((0, 0, image.width, 46), fill=(0, 0, 0))
    draw.text((14, 14), "SpectraLeaf leaf mask", fill=(255, 255, 255))
    image.save(output_path, quality=92)


def analyze_session(session_dir: Path, bands: list[int] | None = None) -> dict[str, Any]:
    image_paths: dict[int, Path] = {}
    for path in session_dir.iterdir():
        if path.suffix.lower() not in {".jpg", ".jpeg", ".png", ".bmp", ".tif", ".tiff"}:
            continue
        match = re.search(r"(532|556|680|725|850|940)", path.stem)
        if match:
            image_paths[int(match.group(1))] = path

    if bands:
        image_paths = {band: image_paths[band] for band in bands if band in image_paths}
    if not image_paths:
        raise RuntimeError(f"No band images found in {session_dir}")

    sample = build_sample_from_images(image_paths)
    mask, mask_meta = build_vegetation_mask(sample)
    if mask is None or int(np.count_nonzero(mask)) == 0:
        first = next(iter(image_paths.values()))
        score = image_to_band(first)
        cutoff = np.percentile(score, 90)
        mask = score > cutoff
        mask_meta = {
            "method": "fallback_percentile_90",
            "fallback_reason": "App vegetation mask returned empty; used strict brightness fallback.",
            "threshold": float(cutoff),
        }

    raw_bands: dict[str, dict[str, Any]] = {}
    average_for_calibration: dict[str, float] = {}
    for band, path in sorted(image_paths.items()):
        arr = image_to_band(path)
        local_mask = mask
        if local_mask.shape != arr.shape:
            mask_img = Image.fromarray(local_mask.astype(np.uint8) * 255)
            mask_img = mask_img.resize((arr.shape[1], arr.shape[0]), Image.Resampling.NEAREST)
            local_mask = np.asarray(mask_img) > 0
        selected = arr[local_mask]
        band_stats = finite_stats(selected)
        average_for_calibration[str(band)] = float(band_stats["mean"] or 0.0)
        raw_bands[str(band)] = {
            "image": path.name,
            **{key: rounded(value) for key, value in band_stats.items()},
        }

    calibration = build_camera_calibration_section(
        average_for_calibration,
        {"source_data_kind": "mixed_image_data", "camera_calibration_eligible": True},
    )
    white_norm_values = {
        key: rounded(value.get("white_normalized_camera"))
        for key, value in calibration.get("corrected_bands", {}).items()
        if isinstance(value, dict)
    }
    source_comp_values = {
        key: rounded(value.get("source_curve_compensated_camera"))
        for key, value in calibration.get("corrected_bands", {}).items()
        if isinstance(value, dict)
    }
    spectrometer_estimates = {
        key: rounded(value.get("best_spectrometer_window_intensity"))
        for key, value in calibration.get("corrected_bands", {}).items()
        if isinstance(value, dict)
    }

    raw_mean_values = {key: value["mean"] for key, value in raw_bands.items()}
    overlay_source = image_paths.get(850) or image_paths.get(680) or next(iter(image_paths.values()))
    overlay_path = session_dir / "leaf_mask_overlay.jpg"
    make_overlay(overlay_source, mask, overlay_path)

    result = {
        "session_id": session_dir.name,
        "session_dir": str(session_dir),
        "created_at": dt.datetime.now().isoformat(timespec="seconds"),
        "bands_captured": sorted(image_paths),
        "image_files": {str(band): str(path) for band, path in sorted(image_paths.items())},
        "mask": {
            **mask_meta,
            "pixel_count": int(np.count_nonzero(mask)),
            "area_fraction": rounded(np.count_nonzero(mask) / mask.size),
            "overlay": str(overlay_path),
        },
        "raw_camera_bands": raw_bands,
        "indices": {
            "from_raw_camera_mean": compute_indices(raw_mean_values),
            "from_white_normalized_camera": compute_indices(white_norm_values),
            "from_source_compensated_camera": compute_indices(source_comp_values),
            "from_best_spectrometer_estimate": compute_indices(spectrometer_estimates),
        },
        "calibration": {
            "profile_id": calibration.get("profile_id"),
            "applied": calibration.get("calibration_applied"),
            "corrected_bands": calibration.get("corrected_bands", {}),
            "calibrated_indices": calibration.get("calibrated_indices", {}),
            "warnings": calibration.get("warnings", []),
            "limitations": calibration.get("limitations", []),
            "low_confidence_spectrometer_targets": calibration.get("low_confidence_spectrometer_targets", {}),
        },
    }
    (session_dir / "analysis.json").write_text(json.dumps(result, indent=2), encoding="utf-8")
    write_report(session_dir, result)
    return result


def capture_session(
    esp32_url: str,
    output_root: Path,
    bands: list[int],
    sample_name: str | None = None,
    settle_ms: int = 150,
    timeout: float = 20.0,
    light_mode: str = "auto",
) -> Path:
    esp32_url = normalize_base_url(esp32_url)
    session_name = sample_name or f"esp32_session_{now_session_id()}"
    session_name = re.sub(r"[^A-Za-z0-9_.-]+", "_", session_name).strip("_") or f"esp32_session_{now_session_id()}"
    session_dir = output_root / session_name
    session_dir.mkdir(parents=True, exist_ok=True)

    manifest = {
        "session_id": session_dir.name,
        "esp32_url": esp32_url,
        "bands": bands,
        "created_at": dt.datetime.now().isoformat(timespec="seconds"),
        "captures": [],
    }
    status_error = None
    try:
        manifest["esp32_status_before"] = fetch_json(f"{esp32_url}/status", timeout=8)
    except Exception as exc:  # noqa: BLE001 - we want this recorded for hardware debugging.
        status_error = str(exc)
        manifest["esp32_status_error"] = status_error

    for band in bands:
        query = urllib.parse.urlencode({"band": str(band), "light": str(light_mode or "auto")})
        url = f"{esp32_url}/capture?{query}"
        started = time.time()
        image_bytes = fetch_bytes(url, timeout=timeout)
        out_path = session_dir / f"{band}.jpg"
        out_path.write_bytes(image_bytes)
        manifest["captures"].append(
            {
                "band": band,
                "url": url,
                "file": str(out_path),
                "bytes": len(image_bytes),
                "elapsed_s": round(time.time() - started, 3),
            }
        )
        time.sleep(max(0, settle_ms) / 1000.0)

    (session_dir / "capture_manifest.json").write_text(json.dumps(manifest, indent=2), encoding="utf-8")
    return session_dir


def html_escape(text: Any) -> str:
    return (
        str(text)
        .replace("&", "&amp;")
        .replace("<", "&lt;")
        .replace(">", "&gt;")
        .replace('"', "&quot;")
    )


def fmt(value: Any, digits: int = 4) -> str:
    if value is None:
        return "-"
    try:
        number = float(value)
    except (TypeError, ValueError):
        return html_escape(value)
    if not math.isfinite(number):
        return "-"
    return f"{number:.{digits}f}"


def write_report(session_dir: Path, result: dict[str, Any]) -> Path:
    rows = []
    for band, values in result["raw_camera_bands"].items():
        corrected = result["calibration"]["corrected_bands"].get(band, {})
        rows.append(
            "<tr>"
            f"<td>{band}</td>"
            f"<td>{fmt(values.get('mean'))}</td>"
            f"<td>{fmt(values.get('median'))}</td>"
            f"<td>{fmt(corrected.get('white_normalized_camera'))}</td>"
            f"<td>{fmt(corrected.get('source_curve_compensated_camera'))}</td>"
            f"<td>{fmt(corrected.get('best_spectrometer_window_intensity'), 2)}</td>"
            f"<td>{html_escape(corrected.get('best_spectrometer_model', ''))}</td>"
            "</tr>"
        )

    image_cards = []
    for band, path in sorted(result["image_files"].items(), key=lambda item: int(item[0])):
        image_cards.append(
            f"<figure><img src='{Path(path).name}' alt='{band} nm capture'><figcaption>{band} nm</figcaption></figure>"
        )

    warnings = result["calibration"].get("warnings") or []
    warning_html = "".join(f"<li>{html_escape(item)}</li>" for item in warnings)
    indices = result["indices"]
    index_rows = []
    for source, values in indices.items():
        for name, value in values.items():
            index_rows.append(f"<tr><td>{html_escape(source)}</td><td>{html_escape(name)}</td><td>{fmt(value)}</td></tr>")

    html = f"""<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>SpectraLeaf ESP32 Session {html_escape(result['session_id'])}</title>
  <style>
    body {{ margin: 0; font-family: Segoe UI, Arial, sans-serif; background: #f5f6f2; color: #17211b; }}
    header, main {{ max-width: 1180px; margin: 0 auto; padding: 24px; }}
    header {{ background: #fff; border-bottom: 1px solid #d9ded5; }}
    h1 {{ margin: 0 0 8px; }}
    .grid {{ display: grid; grid-template-columns: repeat(auto-fit, minmax(170px, 1fr)); gap: 12px; }}
    .card, table, figure {{ background: #fff; border: 1px solid #d9ded5; border-radius: 8px; }}
    .card {{ padding: 14px; }}
    .value {{ font-size: 28px; font-weight: 800; color: #23734a; }}
    table {{ width: 100%; border-collapse: collapse; overflow: hidden; }}
    th, td {{ padding: 9px; border-bottom: 1px solid #e4e8e0; text-align: left; font-size: 13px; }}
    th {{ color: #5f6b62; }}
    figure {{ margin: 0; overflow: hidden; }}
    figure img {{ width: 100%; display: block; background: #fff; }}
    figcaption {{ padding: 8px 10px; font-weight: 700; }}
    .overlay {{ max-width: 760px; width: 100%; border: 1px solid #d9ded5; border-radius: 8px; }}
    pre {{ white-space: pre-wrap; background: #eef1eb; padding: 14px; border-radius: 8px; }}
  </style>
</head>
<body>
  <header>
    <h1>SpectraLeaf automatic ESP32 analysis</h1>
    <p>Session: {html_escape(result['session_id'])}</p>
  </header>
  <main>
    <section class="grid">
      <div class="card"><strong>Captured bands</strong><div class="value">{len(result['bands_captured'])}</div></div>
      <div class="card"><strong>Leaf mask area</strong><div class="value">{fmt(result['mask']['area_fraction'], 3)}</div></div>
      <div class="card"><strong>Calibration</strong><div class="value">{'on' if result['calibration'].get('applied') else 'off'}</div></div>
    </section>

    <h2>Captures</h2>
    <section class="grid">{''.join(image_cards)}</section>

    <h2>Leaf mask</h2>
    <img class="overlay" src="leaf_mask_overlay.jpg" alt="Leaf mask overlay">

    <h2>Band values</h2>
    <table>
      <thead><tr><th>Band</th><th>Raw mean</th><th>Raw median</th><th>White normalized</th><th>Source compensated</th><th>Spectrometer estimate</th><th>Model</th></tr></thead>
      <tbody>{''.join(rows)}</tbody>
    </table>

    <h2>Indices</h2>
    <table>
      <thead><tr><th>Source</th><th>Index</th><th>Value</th></tr></thead>
      <tbody>{''.join(index_rows)}</tbody>
    </table>

    <h2>Calibration warnings</h2>
    <ul>{warning_html or '<li>No warnings.</li>'}</ul>

    <h2>Raw JSON</h2>
    <pre>{html_escape(json.dumps(result, indent=2))}</pre>
  </main>
</body>
</html>"""
    out = session_dir / "report.html"
    out.write_text(html, encoding="utf-8")
    return out


def session_summary(session_dir: Path) -> dict[str, Any]:
    analysis_path = session_dir / "analysis.json"
    result: dict[str, Any] = {}
    if analysis_path.exists():
        try:
            result = json.loads(analysis_path.read_text(encoding="utf-8"))
        except json.JSONDecodeError:
            result = {}

    stat = session_dir.stat()
    bands = result.get("bands_captured") or []
    mask = result.get("mask") if isinstance(result.get("mask"), dict) else {}
    return {
        "session_id": session_dir.name,
        "modified_at": dt.datetime.fromtimestamp(stat.st_mtime).isoformat(timespec="seconds"),
        "bands_captured": bands,
        "mask_area_fraction": mask.get("area_fraction"),
        "report_url": f"/sessions/{session_dir.name}/report.html" if (session_dir / "report.html").exists() else None,
        "analysis_url": f"/sessions/{session_dir.name}/analysis.json" if analysis_path.exists() else None,
        "session_url": f"/sessions/{session_dir.name}/",
    }


APP_HTML = """<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>SpectraLeaf ESP32 Auto Capture</title>
  <style>
    :root { --bg:#f5f6f2; --panel:#fff; --ink:#17211b; --muted:#5f6b62; --line:#d9ded5; --green:#23734a; --blue:#295f8f; --red:#a64536; }
    * { box-sizing: border-box; }
    body { margin:0; font-family: Segoe UI, Arial, sans-serif; background:var(--bg); color:var(--ink); }
    header, main { max-width: 1120px; margin: 0 auto; padding: 24px; }
    header { background: #fff; border-bottom: 1px solid var(--line); }
    h1 { margin: 0 0 8px; font-size: 30px; }
    p { color: var(--muted); line-height: 1.45; }
    .panel { background:var(--panel); border:1px solid var(--line); border-radius:8px; padding:18px; margin:18px 0; }
    .row { display:grid; grid-template-columns: 1.3fr .7fr .7fr auto; gap:10px; align-items:end; }
    label { display:grid; gap:6px; font-weight:700; font-size:13px; color:var(--muted); }
    input { min-height:40px; border:1px solid var(--line); border-radius:6px; padding:8px 10px; font-size:14px; }
    button { min-height:40px; border:0; border-radius:6px; padding:9px 14px; background:#173324; color:#fff; font-weight:800; cursor:pointer; }
    button.secondary { background:var(--blue); }
    button:disabled { opacity:.5; cursor:not-allowed; }
    pre { white-space:pre-wrap; word-break:break-word; background:#eef1eb; padding:14px; border-radius:8px; max-height:380px; overflow:auto; }
    table { width:100%; border-collapse:collapse; background:#fff; }
    th, td { padding:9px 8px; border-bottom:1px solid #e4e8e0; text-align:left; font-size:13px; }
    .ok { color:var(--green); font-weight:800; }
    .bad { color:var(--red); font-weight:800; }
    .links a { display:inline-block; margin: 6px 10px 6px 0; color:var(--blue); font-weight:800; }
    @media (max-width: 850px) { .row { grid-template-columns: 1fr; } }
  </style>
</head>
<body>
  <header>
    <h1>SpectraLeaf ESP32 automatic capture</h1>
    <p>This page tells the ESP32 to move through the filter bands, capture each image, run the leaf mask and calibration, then save a report.</p>
  </header>
  <main>
    <section class="panel">
      <div class="row">
        <label>ESP32 URL<input id="esp32" value="http://192.168.4.1"></label>
        <label>Sample name<input id="sample" value=""></label>
        <label>Bands<input id="bands" value="532,556,680,725,850,940"></label>
        <button id="run">Capture + analyze</button>
      </div>
      <p id="status">Idle.</p>
      <div class="links" id="links"></div>
    </section>

    <section class="panel">
      <h2>Results</h2>
      <div id="summary"></div>
    </section>

    <section class="panel">
      <h2>Log</h2>
      <pre id="log"></pre>
    </section>
  </main>
  <script>
    const run = document.getElementById("run");
    const log = document.getElementById("log");
    const status = document.getElementById("status");
    const summary = document.getElementById("summary");
    const links = document.getElementById("links");

    function addLog(text) {
      log.textContent += text + "\\n";
      log.scrollTop = log.scrollHeight;
    }

    function fmt(value) {
      if (value === null || value === undefined || Number.isNaN(Number(value))) return "-";
      return Number(value).toFixed(4);
    }

    function renderResult(result) {
      const bands = Object.entries(result.raw_camera_bands || {});
      const rows = bands.map(([band, values]) => {
        const corrected = (result.calibration.corrected_bands || {})[band] || {};
        return `<tr><td>${band}</td><td>${fmt(values.mean)}</td><td>${fmt(values.median)}</td><td>${fmt(corrected.white_normalized_camera)}</td><td>${fmt(corrected.source_curve_compensated_camera)}</td><td>${fmt(corrected.best_spectrometer_window_intensity)}</td></tr>`;
      }).join("");
      summary.innerHTML = `
        <p><span class="ok">Done:</span> ${result.session_id}</p>
        <p>Leaf mask area: ${fmt(result.mask.area_fraction)} | pixels: ${result.mask.pixel_count}</p>
        <table><thead><tr><th>Band</th><th>Raw mean</th><th>Raw median</th><th>White normalized</th><th>Source compensated</th><th>Spectrometer estimate</th></tr></thead><tbody>${rows}</tbody></table>
      `;
      links.innerHTML = `<a href="${result.report_url}" target="_blank">Open report</a><a href="${result.analysis_url}" target="_blank">Open analysis JSON</a><a href="${result.session_url}" target="_blank">Open session folder view</a>`;
    }

    run.addEventListener("click", async () => {
      run.disabled = true;
      log.textContent = "";
      links.innerHTML = "";
      summary.innerHTML = "";
      status.textContent = "Running capture...";
      addLog("Starting automatic capture.");
      try {
        const body = {
          esp32_url: document.getElementById("esp32").value,
          sample_name: document.getElementById("sample").value,
          bands: document.getElementById("bands").value,
        };
        const response = await fetch("/api/run", {
          method: "POST",
          headers: {"Content-Type": "application/json"},
          body: JSON.stringify(body),
        });
        const payload = await response.json();
        if (!response.ok) throw new Error(payload.error || "Capture failed");
        addLog(JSON.stringify(payload, null, 2));
        renderResult(payload);
        status.textContent = "Done.";
      } catch (error) {
        status.innerHTML = `<span class="bad">Error:</span> ${error.message}`;
        addLog(error.stack || error.message);
      } finally {
        run.disabled = false;
      }
    });
  </script>
</body>
</html>
"""


APP_HTML = r"""<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>SpectraLeaf Automation Dashboard</title>
  <style>
    :root {
      --bg: #f4f5f0;
      --panel: #ffffff;
      --ink: #17211b;
      --muted: #627066;
      --line: #d8ded4;
      --green: #23734a;
      --blue: #265d8d;
      --amber: #9a6a12;
      --red: #a64536;
      --soft-green: #e7f1ea;
      --soft-blue: #e8eef5;
      --soft-amber: #f5eedf;
    }
    * { box-sizing: border-box; }
    body { margin: 0; font-family: Segoe UI, Arial, sans-serif; background: var(--bg); color: var(--ink); }
    header { background: #ffffff; border-bottom: 1px solid var(--line); }
    header .inner, main { max-width: 1280px; margin: 0 auto; padding: 22px; }
    h1 { margin: 0 0 6px; font-size: 30px; }
    h2 { margin: 0 0 14px; font-size: 18px; }
    h3 { margin: 0 0 10px; font-size: 15px; }
    p { margin: 6px 0; color: var(--muted); line-height: 1.45; }
    button, input, select { font: inherit; }
    input, select {
      width: 100%;
      min-height: 40px;
      border: 1px solid var(--line);
      border-radius: 6px;
      padding: 8px 10px;
      background: #ffffff;
      color: var(--ink);
    }
    label { display: grid; gap: 6px; color: var(--muted); font-size: 13px; font-weight: 700; }
    button {
      min-height: 40px;
      border: 0;
      border-radius: 6px;
      padding: 9px 14px;
      background: #173324;
      color: #ffffff;
      font-weight: 800;
      cursor: pointer;
    }
    button.secondary { background: var(--blue); }
    button.warning { background: var(--amber); }
    button.ghost { background: #eef1eb; color: var(--ink); border: 1px solid var(--line); }
    button.danger { background: var(--red); }
    button:disabled { opacity: .52; cursor: not-allowed; }
    .layout { display: grid; grid-template-columns: minmax(320px, 420px) 1fr; gap: 18px; align-items: start; }
    .panel { background: var(--panel); border: 1px solid var(--line); border-radius: 8px; padding: 16px; margin-bottom: 18px; }
    .grid { display: grid; gap: 12px; }
    .grid.two { grid-template-columns: repeat(2, minmax(0, 1fr)); }
    .grid.three { grid-template-columns: repeat(3, minmax(0, 1fr)); }
    .actions { display: flex; flex-wrap: wrap; gap: 8px; align-items: center; }
    .status-line { display: flex; gap: 8px; align-items: center; flex-wrap: wrap; margin-top: 10px; }
    .pill { display: inline-flex; align-items: center; gap: 6px; min-height: 28px; padding: 4px 9px; border-radius: 999px; border: 1px solid var(--line); background: #f8faf6; color: var(--muted); font-size: 12px; font-weight: 800; }
    .pill.ok { color: var(--green); background: var(--soft-green); }
    .pill.bad { color: var(--red); background: #f7e7e4; }
    .pill.live { color: var(--blue); background: var(--soft-blue); }
    .metric-grid { display: grid; grid-template-columns: repeat(4, minmax(0, 1fr)); gap: 12px; }
    .metric { background: #fbfcf8; border: 1px solid var(--line); border-radius: 8px; padding: 12px; }
    .metric strong { display: block; color: var(--muted); font-size: 12px; }
    .metric span { display: block; margin-top: 6px; font-size: 24px; font-weight: 900; color: var(--green); }
    .band-buttons { display: grid; grid-template-columns: repeat(3, minmax(0, 1fr)); gap: 8px; }
    .band-buttons button { background: #eef1eb; color: var(--ink); border: 1px solid var(--line); }
    .band-buttons button.active { background: var(--green); color: #ffffff; border-color: var(--green); }
    .preview-wrap { background: #101512; border-radius: 8px; min-height: 260px; display: grid; place-items: center; overflow: hidden; border: 1px solid #25302a; }
    .preview-wrap img { max-width: 100%; width: 100%; display: block; object-fit: contain; background: #111; }
    .preview-empty { color: #d6ded7; padding: 18px; text-align: center; }
    .gallery { display: grid; grid-template-columns: repeat(auto-fit, minmax(130px, 1fr)); gap: 10px; }
    figure { margin: 0; border: 1px solid var(--line); border-radius: 8px; overflow: hidden; background: #ffffff; }
    figure img { width: 100%; display: block; aspect-ratio: 4 / 3; object-fit: cover; background: #f1f3ef; }
    figcaption { padding: 7px 9px; font-size: 12px; font-weight: 800; color: var(--muted); }
    table { width: 100%; border-collapse: collapse; background: #ffffff; border: 1px solid var(--line); border-radius: 8px; overflow: hidden; }
    th, td { padding: 8px; border-bottom: 1px solid #e6e9e2; text-align: left; font-size: 13px; }
    th { color: var(--muted); background: #fafbf8; }
    tr:last-child td { border-bottom: 0; }
    .links a { display: inline-block; margin: 6px 10px 6px 0; color: var(--blue); font-weight: 800; }
    pre { margin: 0; white-space: pre-wrap; word-break: break-word; background: #eef1eb; padding: 12px; border-radius: 8px; max-height: 240px; overflow: auto; font-size: 12px; }
    .session-list { display: grid; gap: 8px; }
    .session-item { display: grid; grid-template-columns: 1fr auto; gap: 10px; align-items: center; border: 1px solid var(--line); border-radius: 8px; padding: 10px; background: #fbfcf8; }
    .session-item a { color: var(--blue); font-weight: 800; text-decoration: none; }
    .small { font-size: 12px; color: var(--muted); }
    .hidden { display: none !important; }
    @media (max-width: 1050px) {
      .layout { grid-template-columns: 1fr; }
      .metric-grid { grid-template-columns: repeat(2, minmax(0, 1fr)); }
    }
    @media (max-width: 680px) {
      header .inner, main { padding: 16px; }
      .grid.two, .grid.three { grid-template-columns: 1fr; }
      .metric-grid { grid-template-columns: 1fr; }
      .band-buttons { grid-template-columns: repeat(2, minmax(0, 1fr)); }
    }
  </style>
</head>
<body>
  <header>
    <div class="inner">
      <h1>SpectraLeaf automation dashboard</h1>
      <p>Control the ESP32, preview the camera, capture all filter bands, run the leaf analysis, and open saved reports from one place.</p>
      <div class="status-line">
        <span class="pill ok" id="bridge-pill">Bridge online</span>
        <span class="pill" id="esp-pill">ESP32 not checked</span>
        <span class="pill" id="live-pill">Live preview off</span>
      </div>
    </div>
  </header>

  <main>
    <div class="layout">
      <section>
        <div class="panel">
          <h2>Connection</h2>
          <div class="grid">
            <label>ESP32 URL
              <input id="esp32" value="http://192.168.4.1" autocomplete="off">
            </label>
            <div class="grid two">
              <button id="check">Check ESP32</button>
              <button class="secondary" id="load-bands">Load bands</button>
            </div>
            <pre id="esp32-status">No ESP32 status yet.</pre>
          </div>
        </div>

        <div class="panel">
          <h2>Filter control</h2>
          <label>Capture bands
            <input id="bands" value="532,556,680,725,850,940">
          </label>
          <div class="band-buttons" id="band-buttons"></div>
          <div class="grid two" style="margin-top: 12px;">
            <button class="ghost" id="move">Move only</button>
            <button class="secondary" id="single">Single capture</button>
          </div>
        </div>

        <div class="panel">
          <h2>Automatic run</h2>
          <div class="grid">
            <label>Sample name
              <input id="sample" placeholder="leaf_healthy_01">
            </label>
            <div class="grid two">
              <label>Settle time ms
                <input id="settle" type="number" value="150" min="0">
              </label>
              <label>Timeout seconds
                <input id="timeout" type="number" value="20" min="3">
              </label>
            </div>
            <button id="run">Capture all bands + analyze</button>
          </div>
          <p id="run-status">Ready.</p>
        </div>

        <div class="panel">
          <h2>Saved sessions</h2>
          <div class="actions">
            <button class="ghost" id="refresh-sessions">Refresh</button>
            <a href="/sessions/" target="_blank" class="small">Open folder view</a>
          </div>
          <div class="session-list" id="sessions"></div>
        </div>
      </section>

      <section>
        <div class="panel">
          <h2>Live camera</h2>
          <div class="actions">
            <button id="live" class="warning">Start live preview</button>
            <button id="stop-live" class="ghost">Stop</button>
            <span class="small" id="selected-band-label">Selected band: 850 nm</span>
          </div>
          <div class="preview-wrap" style="margin-top: 12px;">
            <img id="preview" alt="ESP32 camera preview" class="hidden">
            <div class="preview-empty" id="preview-empty">No preview yet. Choose a band and press Single capture or Start live preview.</div>
          </div>
        </div>

        <div class="panel">
          <h2>Current analysis</h2>
          <div class="metric-grid" id="metrics">
            <div class="metric"><strong>Session</strong><span>-</span></div>
            <div class="metric"><strong>Bands</strong><span>-</span></div>
            <div class="metric"><strong>Mask area</strong><span>-</span></div>
            <div class="metric"><strong>Calibration</strong><span>-</span></div>
          </div>
          <div class="links" id="links"></div>
        </div>

        <div class="panel hidden" id="capture-panel">
          <h2>Captured images</h2>
          <div class="gallery" id="gallery"></div>
        </div>

        <div class="panel hidden" id="mask-panel">
          <h2>Leaf mask</h2>
          <div class="preview-wrap">
            <img id="mask-image" alt="Leaf mask overlay">
          </div>
        </div>

        <div class="panel hidden" id="bands-panel">
          <h2>Band values</h2>
          <div id="band-table"></div>
        </div>

        <div class="panel hidden" id="indices-panel">
          <h2>Indices</h2>
          <div id="indices-table"></div>
        </div>

        <div class="panel">
          <h2>Log</h2>
          <pre id="log"></pre>
        </div>
      </section>
    </div>
  </main>

  <script>
    const DEFAULT_BANDS = [532, 556, 680, 725, 850, 940];
    let selectedBand = 850;
    let liveTimer = null;

    const els = {
      esp32: document.getElementById("esp32"),
      bands: document.getElementById("bands"),
      sample: document.getElementById("sample"),
      settle: document.getElementById("settle"),
      timeout: document.getElementById("timeout"),
      bandButtons: document.getElementById("band-buttons"),
      status: document.getElementById("esp32-status"),
      espPill: document.getElementById("esp-pill"),
      livePill: document.getElementById("live-pill"),
      selectedBandLabel: document.getElementById("selected-band-label"),
      preview: document.getElementById("preview"),
      previewEmpty: document.getElementById("preview-empty"),
      run: document.getElementById("run"),
      runStatus: document.getElementById("run-status"),
      metrics: document.getElementById("metrics"),
      links: document.getElementById("links"),
      gallery: document.getElementById("gallery"),
      capturePanel: document.getElementById("capture-panel"),
      maskPanel: document.getElementById("mask-panel"),
      maskImage: document.getElementById("mask-image"),
      bandsPanel: document.getElementById("bands-panel"),
      bandTable: document.getElementById("band-table"),
      indicesPanel: document.getElementById("indices-panel"),
      indicesTable: document.getElementById("indices-table"),
      sessions: document.getElementById("sessions"),
      log: document.getElementById("log"),
    };

    function api(path, params = {}) {
      const url = new URL(path, window.location.origin);
      Object.entries(params).forEach(([key, value]) => {
        if (value !== undefined && value !== null && String(value).length) url.searchParams.set(key, value);
      });
      return url.toString();
    }

    function addLog(text) {
      const timestamp = new Date().toLocaleTimeString();
      els.log.textContent += `[${timestamp}] ${text}\n`;
      els.log.scrollTop = els.log.scrollHeight;
    }

    function fmt(value, digits = 4) {
      if (value === null || value === undefined || Number.isNaN(Number(value))) return "-";
      return Number(value).toFixed(digits);
    }

    function parseBands() {
      const bands = els.bands.value.split(/[,;\s]+/).map((item) => Number(item)).filter((item) => Number.isFinite(item));
      return bands.length ? bands : DEFAULT_BANDS;
    }

    function setEspStatus(ok, text) {
      els.espPill.textContent = text;
      els.espPill.className = ok ? "pill ok" : "pill bad";
    }

    function setLiveStatus(active) {
      els.livePill.textContent = active ? "Live preview on" : "Live preview off";
      els.livePill.className = active ? "pill live" : "pill";
    }

    function renderBandButtons() {
      const bands = parseBands();
      els.bandButtons.innerHTML = bands.map((band) => (
        `<button type="button" data-band="${band}" class="${band === selectedBand ? "active" : ""}">${band} nm</button>`
      )).join("");
      els.selectedBandLabel.textContent = `Selected band: ${selectedBand} nm`;
      els.bandButtons.querySelectorAll("button").forEach((button) => {
        button.addEventListener("click", () => {
          selectedBand = Number(button.dataset.band);
          renderBandButtons();
        });
      });
    }

    async function fetchJson(url, options) {
      const response = await fetch(url, options);
      const payload = await response.json();
      if (!response.ok) throw new Error(payload.error || `HTTP ${response.status}`);
      return payload;
    }

    async function checkEsp32() {
      addLog("Checking ESP32 status.");
      try {
        const payload = await fetchJson(api("/api/esp32/status", { esp32_url: els.esp32.value }));
        els.status.textContent = JSON.stringify(payload, null, 2);
        setEspStatus(true, `ESP32 connected: ${payload.ip || "ok"}`);
        if (payload.current_band && Number(payload.current_band) > 0) selectedBand = Number(payload.current_band);
        renderBandButtons();
      } catch (error) {
        els.status.textContent = error.message;
        setEspStatus(false, "ESP32 not connected");
        addLog(`ESP32 error: ${error.message}`);
      }
    }

    async function loadBandsFromEsp32() {
      addLog("Loading band positions from ESP32.");
      try {
        const payload = await fetchJson(api("/api/esp32/bands", { esp32_url: els.esp32.value }));
        const bands = (payload.bands || []).map((item) => item.wavelength).filter(Boolean);
        if (bands.length) {
          els.bands.value = bands.join(",");
          selectedBand = bands.includes(selectedBand) ? selectedBand : bands[0];
          renderBandButtons();
        }
        els.status.textContent = JSON.stringify(payload, null, 2);
      } catch (error) {
        addLog(`Band load error: ${error.message}`);
      }
    }

    async function moveSelectedBand() {
      addLog(`Moving ESP32 to ${selectedBand} nm.`);
      const payload = await fetchJson(api("/api/esp32/move", { esp32_url: els.esp32.value, band: selectedBand }));
      els.status.textContent = JSON.stringify(payload, null, 2);
      addLog(`Move done: ${selectedBand} nm.`);
    }

    function capturePreview() {
      const src = api("/api/esp32/preview", {
        esp32_url: els.esp32.value,
        band: selectedBand,
        t: Date.now(),
      });
      els.preview.onload = () => {
        els.preview.classList.remove("hidden");
        els.previewEmpty.classList.add("hidden");
      };
      els.preview.onerror = () => {
        els.preview.classList.add("hidden");
        els.previewEmpty.classList.remove("hidden");
        els.previewEmpty.textContent = "Preview failed. Check the ESP32 URL, camera, and Wi-Fi connection.";
        addLog("Preview failed.");
      };
      els.preview.src = src;
      addLog(`Requested preview capture at ${selectedBand} nm.`);
    }

    function startLive() {
      stopLive(false);
      capturePreview();
      liveTimer = window.setInterval(capturePreview, 1800);
      setLiveStatus(true);
      addLog("Live preview started.");
    }

    function stopLive(writeLog = true) {
      if (liveTimer) window.clearInterval(liveTimer);
      liveTimer = null;
      setLiveStatus(false);
      if (writeLog) addLog("Live preview stopped.");
    }

    function fileName(path) {
      return String(path).split(/[\\/]/).pop();
    }

    function renderMetrics(result) {
      const applied = result.calibration && result.calibration.applied ? "on" : "off";
      els.metrics.innerHTML = `
        <div class="metric"><strong>Session</strong><span>${result.session_id || "-"}</span></div>
        <div class="metric"><strong>Bands</strong><span>${(result.bands_captured || []).length}</span></div>
        <div class="metric"><strong>Mask area</strong><span>${fmt(result.mask && result.mask.area_fraction, 3)}</span></div>
        <div class="metric"><strong>Calibration</strong><span>${applied}</span></div>
      `;
      els.links.innerHTML = `
        <a href="${result.report_url}" target="_blank">Open report</a>
        <a href="${result.analysis_url}" target="_blank">Open analysis JSON</a>
        <a href="${result.session_url}" target="_blank">Open session files</a>
      `;
    }

    function renderGallery(result) {
      const files = result.image_files || {};
      const base = result.session_url || "";
      els.gallery.innerHTML = Object.entries(files).sort((a, b) => Number(a[0]) - Number(b[0])).map(([band, path]) => (
        `<figure><img src="${base}${fileName(path)}?t=${Date.now()}" alt="${band} nm"><figcaption>${band} nm</figcaption></figure>`
      )).join("");
      els.capturePanel.classList.toggle("hidden", !Object.keys(files).length);
      els.maskImage.src = `${base}leaf_mask_overlay.jpg?t=${Date.now()}`;
      els.maskPanel.classList.remove("hidden");
    }

    function renderBandTable(result) {
      const corrected = (result.calibration && result.calibration.corrected_bands) || {};
      const rows = Object.entries(result.raw_camera_bands || {}).sort((a, b) => Number(a[0]) - Number(b[0])).map(([band, values]) => {
        const cal = corrected[band] || {};
        return `<tr>
          <td>${band}</td>
          <td>${fmt(values.mean)}</td>
          <td>${fmt(values.median)}</td>
          <td>${fmt(values.std)}</td>
          <td>${fmt(cal.white_normalized_camera)}</td>
          <td>${fmt(cal.source_curve_compensated_camera)}</td>
          <td>${fmt(cal.best_spectrometer_window_intensity, 2)}</td>
        </tr>`;
      }).join("");
      els.bandTable.innerHTML = `<table><thead><tr><th>Band</th><th>Raw mean</th><th>Raw median</th><th>Std</th><th>White norm</th><th>Source comp.</th><th>Spectrometer estimate</th></tr></thead><tbody>${rows}</tbody></table>`;
      els.bandsPanel.classList.toggle("hidden", !rows);
    }

    function renderIndices(result) {
      const rows = [];
      Object.entries(result.indices || {}).forEach(([source, values]) => {
        Object.entries(values || {}).forEach(([name, value]) => rows.push(`<tr><td>${source}</td><td>${name}</td><td>${fmt(value)}</td></tr>`));
      });
      els.indicesTable.innerHTML = `<table><thead><tr><th>Source</th><th>Index</th><th>Value</th></tr></thead><tbody>${rows.join("")}</tbody></table>`;
      els.indicesPanel.classList.toggle("hidden", !rows.length);
    }

    function renderResult(result) {
      renderMetrics(result);
      renderGallery(result);
      renderBandTable(result);
      renderIndices(result);
    }

    async function runAutomaticCapture() {
      stopLive(false);
      els.run.disabled = true;
      els.runStatus.textContent = "Capturing all bands, then analyzing the leaf.";
      addLog("Starting full automatic capture and analysis.");
      try {
        const payload = await fetchJson("/api/run", {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({
            esp32_url: els.esp32.value,
            sample_name: els.sample.value,
            bands: els.bands.value,
            settle_ms: Number(els.settle.value || 150),
            timeout: Number(els.timeout.value || 20),
          }),
        });
        renderResult(payload);
        await refreshSessions();
        els.runStatus.textContent = "Done.";
        addLog(`Analysis complete: ${payload.session_id}`);
      } catch (error) {
        els.runStatus.textContent = `Error: ${error.message}`;
        addLog(`Run failed: ${error.message}`);
      } finally {
        els.run.disabled = false;
      }
    }

    async function refreshSessions() {
      try {
        const payload = await fetchJson("/api/sessions");
        const sessions = payload.sessions || [];
        els.sessions.innerHTML = sessions.length ? sessions.map((session) => `
          <div class="session-item">
            <div>
              <a href="${session.report_url || session.session_url}" target="_blank">${session.session_id}</a>
              <div class="small">${session.modified_at} | bands: ${(session.bands_captured || []).join(", ") || "-"}</div>
            </div>
            <a class="small" href="${session.session_url}" target="_blank">files</a>
          </div>
        `).join("") : `<p>No sessions saved yet.</p>`;
      } catch (error) {
        els.sessions.innerHTML = `<p>Could not load sessions: ${error.message}</p>`;
      }
    }

    document.getElementById("check").addEventListener("click", checkEsp32);
    document.getElementById("load-bands").addEventListener("click", loadBandsFromEsp32);
    document.getElementById("move").addEventListener("click", () => moveSelectedBand().catch((error) => addLog(`Move failed: ${error.message}`)));
    document.getElementById("single").addEventListener("click", capturePreview);
    document.getElementById("live").addEventListener("click", startLive);
    document.getElementById("stop-live").addEventListener("click", () => stopLive(true));
    document.getElementById("run").addEventListener("click", runAutomaticCapture);
    document.getElementById("refresh-sessions").addEventListener("click", refreshSessions);
    els.bands.addEventListener("change", renderBandButtons);
    renderBandButtons();
    refreshSessions();
    fetchJson("/api/health").then((payload) => addLog(`Bridge ready. Output: ${payload.output_root}`)).catch(() => {});
  </script>
</body>
</html>
"""


class AutoCaptureHandler(BaseHTTPRequestHandler):
    output_root: Path = DEFAULT_OUTPUT_ROOT

    def log_message(self, fmt_text: str, *args: Any) -> None:
        sys.stderr.write("[%s] %s\n" % (self.log_date_time_string(), fmt_text % args))

    def send_json(self, code: int, payload: dict[str, Any]) -> None:
        raw = json.dumps(payload, indent=2).encode("utf-8")
        self.send_response(code)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(raw)))
        self.end_headers()
        self.wfile.write(raw)

    def send_text(self, code: int, text: str, content_type: str = "text/html; charset=utf-8") -> None:
        raw = text.encode("utf-8")
        self.send_response(code)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(raw)))
        self.end_headers()
        self.wfile.write(raw)

    def send_binary(self, code: int, raw: bytes, content_type: str) -> None:
        self.send_response(code)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(raw)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(raw)

    def query_value(self, parsed: urllib.parse.ParseResult, name: str, default: str = "") -> str:
        return urllib.parse.parse_qs(parsed.query).get(name, [default])[0]

    def do_GET(self) -> None:  # noqa: N802 - stdlib API.
        parsed = urllib.parse.urlparse(self.path)
        if parsed.path == "/":
            self.send_text(HTTPStatus.OK, APP_HTML)
            return
        if parsed.path.startswith("/sessions/"):
            self.serve_session_file(parsed.path)
            return
        if parsed.path == "/api/health":
            self.send_json(HTTPStatus.OK, {"ok": True, "output_root": str(self.output_root)})
            return
        if parsed.path == "/api/sessions":
            sessions = sorted((p for p in self.output_root.glob("*") if p.is_dir()), key=lambda p: p.stat().st_mtime, reverse=True)
            self.send_json(HTTPStatus.OK, {"sessions": [session_summary(p) for p in sessions[:40]]})
            return
        if parsed.path == "/api/esp32/status":
            self.handle_esp32_status(parsed)
            return
        if parsed.path == "/api/esp32/bands":
            self.handle_esp32_bands(parsed)
            return
        if parsed.path == "/api/esp32/move":
            self.handle_esp32_move(parsed)
            return
        if parsed.path == "/api/esp32/light":
            self.handle_esp32_light(parsed)
            return
        if parsed.path == "/api/esp32/preview":
            self.handle_esp32_preview(parsed)
            return
        self.send_json(HTTPStatus.NOT_FOUND, {"error": "Not found"})

    def do_POST(self) -> None:  # noqa: N802 - stdlib API.
        parsed = urllib.parse.urlparse(self.path)
        if parsed.path != "/api/run":
            self.send_json(HTTPStatus.NOT_FOUND, {"error": "Not found"})
            return
        try:
            length = int(self.headers.get("Content-Length", "0"))
            raw = self.rfile.read(length)
            body = json.loads(raw.decode("utf-8") or "{}")
            bands = parse_bands(str(body.get("bands") or ""))
            session_dir = capture_session(
                esp32_url=str(body.get("esp32_url") or ""),
                output_root=self.output_root,
                bands=bands,
                sample_name=str(body.get("sample_name") or "").strip() or None,
                settle_ms=int(body.get("settle_ms") or 150),
                timeout=float(body.get("timeout") or 20.0),
                light_mode=str(body.get("light_mode") or "auto"),
            )
            result = analyze_session(session_dir, bands=bands)
            result["report_url"] = f"/sessions/{session_dir.name}/report.html"
            result["analysis_url"] = f"/sessions/{session_dir.name}/analysis.json"
            result["session_url"] = f"/sessions/{session_dir.name}/"
            self.send_json(HTTPStatus.OK, result)
        except Exception as exc:  # noqa: BLE001 - UI should show hardware errors.
            self.send_json(HTTPStatus.INTERNAL_SERVER_ERROR, {"error": str(exc)})

    def handle_esp32_status(self, parsed: urllib.parse.ParseResult) -> None:
        try:
            esp32_url = normalize_base_url(self.query_value(parsed, "esp32_url"))
            self.send_json(HTTPStatus.OK, fetch_json(f"{esp32_url}/status", timeout=5))
        except Exception as exc:  # noqa: BLE001 - dashboard should show connection errors.
            self.send_json(HTTPStatus.BAD_GATEWAY, {"ok": False, "error": str(exc)})

    def handle_esp32_bands(self, parsed: urllib.parse.ParseResult) -> None:
        try:
            esp32_url = normalize_base_url(self.query_value(parsed, "esp32_url"))
            payload = fetch_json(f"{esp32_url}/bands", timeout=5)
            self.send_json(HTTPStatus.OK, {"ok": True, "bands": payload})
        except Exception as exc:  # noqa: BLE001
            self.send_json(HTTPStatus.BAD_GATEWAY, {"ok": False, "error": str(exc)})

    def handle_esp32_move(self, parsed: urllib.parse.ParseResult) -> None:
        try:
            esp32_url = normalize_base_url(self.query_value(parsed, "esp32_url"))
            band = self.query_value(parsed, "band")
            if not band:
                raise ValueError("Missing band")
            payload = fetch_json(f"{esp32_url}/move?band={urllib.parse.quote(band)}", timeout=12)
            self.send_json(HTTPStatus.OK, payload)
        except Exception as exc:  # noqa: BLE001
            self.send_json(HTTPStatus.BAD_GATEWAY, {"ok": False, "error": str(exc)})

    def handle_esp32_light(self, parsed: urllib.parse.ParseResult) -> None:
        try:
            esp32_url = normalize_base_url(self.query_value(parsed, "esp32_url"))
            state = self.query_value(parsed, "state")
            if not state:
                raise ValueError("Missing state")
            payload = fetch_json(f"{esp32_url}/light?state={urllib.parse.quote(state)}", timeout=8)
            self.send_json(HTTPStatus.OK, payload)
        except Exception as exc:  # noqa: BLE001
            self.send_json(HTTPStatus.BAD_GATEWAY, {"ok": False, "error": str(exc)})

    def handle_esp32_preview(self, parsed: urllib.parse.ParseResult) -> None:
        try:
            esp32_url = normalize_base_url(self.query_value(parsed, "esp32_url"))
            band = self.query_value(parsed, "band", "850")
            light_mode = self.query_value(parsed, "light_mode", "auto")
            query = urllib.parse.urlencode({"band": band, "light": light_mode})
            raw = fetch_bytes(f"{esp32_url}/capture?{query}", timeout=20)
            self.send_binary(HTTPStatus.OK, raw, "image/jpeg")
        except Exception as exc:  # noqa: BLE001
            self.send_json(HTTPStatus.BAD_GATEWAY, {"ok": False, "error": str(exc)})

    def serve_session_file(self, request_path: str) -> None:
        relative = request_path.removeprefix("/sessions/").strip("/")
        if not relative:
            sessions = sorted((p for p in self.output_root.glob("*") if p.is_dir()), reverse=True)
            links = "".join(f"<li><a href='/sessions/{p.name}/report.html'>{p.name}</a></li>" for p in sessions)
            self.send_text(HTTPStatus.OK, f"<h1>SpectraLeaf sessions</h1><ul>{links}</ul>")
            return

        target = (self.output_root / relative).resolve()
        root = self.output_root.resolve()
        if root not in target.parents and target != root:
            self.send_json(HTTPStatus.FORBIDDEN, {"error": "Forbidden"})
            return
        if target.is_dir():
            files = sorted(target.iterdir())
            links = "".join(f"<li><a href='{urllib.parse.quote(item.name)}'>{item.name}</a></li>" for item in files)
            self.send_text(HTTPStatus.OK, f"<h1>{html_escape(target.name)}</h1><ul>{links}</ul>")
            return
        if not target.exists():
            self.send_json(HTTPStatus.NOT_FOUND, {"error": "File not found"})
            return
        content_type = mimetypes.guess_type(str(target))[0] or "application/octet-stream"
        raw = target.read_bytes()
        self.send_response(HTTPStatus.OK)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(raw)))
        self.end_headers()
        self.wfile.write(raw)


def command_run(args: argparse.Namespace) -> None:
    bands = parse_bands(args.bands)
    output_root = Path(args.output).expanduser().resolve()
    session_dir = capture_session(
        esp32_url=args.esp32,
        output_root=output_root,
        bands=bands,
        sample_name=args.sample,
        settle_ms=args.settle_ms,
        timeout=args.timeout,
        light_mode=args.light_mode,
    )
    result = analyze_session(session_dir, bands=bands)
    print(json.dumps({
        "session_dir": str(session_dir),
        "report": str(session_dir / "report.html"),
        "analysis": str(session_dir / "analysis.json"),
        "bands": result["bands_captured"],
    }, indent=2))


def command_analyze(args: argparse.Namespace) -> None:
    session_dir = Path(args.session).expanduser().resolve()
    result = analyze_session(session_dir, bands=parse_bands(args.bands) if args.bands else None)
    print(json.dumps({
        "session_dir": str(session_dir),
        "report": str(session_dir / "report.html"),
        "analysis": str(session_dir / "analysis.json"),
        "bands": result["bands_captured"],
    }, indent=2))


def command_serve(args: argparse.Namespace) -> None:
    output_root = Path(args.output).expanduser().resolve()
    output_root.mkdir(parents=True, exist_ok=True)
    AutoCaptureHandler.output_root = output_root
    server = ThreadingHTTPServer((args.host, args.port), AutoCaptureHandler)
    print(f"SpectraLeaf auto capture app: http://{args.host}:{args.port}")
    print(f"Session output root: {output_root}")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\nStopping.")


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="SpectraLeaf ESP32 automatic capture and analysis")
    sub = parser.add_subparsers(dest="command", required=True)

    run = sub.add_parser("run", help="Capture all bands from ESP32 and analyze them")
    run.add_argument("--esp32", required=True, help="ESP32 base URL, e.g. http://192.168.4.1")
    run.add_argument("--bands", default=",".join(str(item) for item in DEFAULT_BANDS))
    run.add_argument("--sample", default=None, help="Optional session/sample name")
    run.add_argument("--output", default=str(DEFAULT_OUTPUT_ROOT))
    run.add_argument("--settle-ms", type=int, default=150)
    run.add_argument("--timeout", type=float, default=20.0)
    run.add_argument("--light-mode", choices=("auto", "keep", "on", "off"), default="auto")
    run.set_defaults(func=command_run)

    analyze = sub.add_parser("analyze", help="Analyze an already captured session folder")
    analyze.add_argument("session", help="Folder with 532.jpg, 556.jpg, ...")
    analyze.add_argument("--bands", default=None)
    analyze.set_defaults(func=command_analyze)

    serve = sub.add_parser("serve", help="Run local browser app for capture + analysis")
    serve.add_argument("--host", default="127.0.0.1")
    serve.add_argument("--port", type=int, default=8765)
    serve.add_argument("--output", default=str(DEFAULT_OUTPUT_ROOT))
    serve.set_defaults(func=command_serve)
    return parser


def main() -> None:
    parser = build_parser()
    args = parser.parse_args()
    args.func(args)


if __name__ == "__main__":
    main()
