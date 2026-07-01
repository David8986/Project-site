"""Spectrum and wavelength helpers for the hyperspectral viewer."""

from __future__ import annotations

import csv
import json
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable

import numpy as np

from envi_loader import is_junk_file


TARGET_BAND_INDICES: dict[int, int] = {
    532: 51,
    556: 60,
    650: 95,
    680: 106,
    725: 123,
    850: 168,
    940: 200,
}

_NUMBER_PATTERN = re.compile(r"[-+]?(?:\d*\.\d+|\d+)(?:[eE][-+]?\d+)?")


@dataclass(frozen=True)
class WavelengthLoadResult:
    """Wavelength CSV load result."""

    wavelengths: np.ndarray
    notes: tuple[str, ...]


def load_wavelength_csv(path: str | Path, expected_bands: int | None = None) -> WavelengthLoadResult:
    """Load a one-column or ``index,wavelength`` CSV into a wavelength array."""

    csv_path = Path(path).expanduser()
    if is_junk_file(csv_path):
        raise ValueError(f"Ignoring junk macOS artifact file: {csv_path.name}")
    if not csv_path.exists():
        raise FileNotFoundError(f"Wavelength CSV does not exist: {csv_path}")

    text = csv_path.read_text(encoding="utf-8-sig", errors="ignore")
    rows = _read_csv_rows(text)
    if not rows:
        raise ValueError("The wavelength CSV did not contain any numeric values.")

    wavelengths, notes = _choose_wavelength_column(rows)
    if wavelengths.size == 0:
        raise ValueError("Could not detect a wavelength column in the CSV.")

    if expected_bands is not None and wavelengths.size != expected_bands:
        notes.append(
            f"CSV has {wavelengths.size} wavelength value(s), but the cube has {expected_bands} band(s)."
        )

    return WavelengthLoadResult(wavelengths=wavelengths.astype(float), notes=tuple(notes))


def wavelength_for_band(wavelengths: np.ndarray | None, band_index: int) -> float | None:
    """Return the wavelength for ``band_index`` when available."""

    if wavelengths is None or band_index < 0 or band_index >= wavelengths.size:
        return None
    value = float(wavelengths[band_index])
    return value if np.isfinite(value) else None


def x_axis_for_spectrum(wavelengths: np.ndarray | None, band_count: int) -> tuple[np.ndarray, str]:
    """Return x values and axis label for plotting a spectrum."""

    if wavelengths is not None and wavelengths.size == band_count:
        return wavelengths.astype(float), "Wavelength (nm)"
    return np.arange(band_count, dtype=float), "Band index"


def normalize_for_display(values: np.ndarray) -> np.ndarray:
    """Normalize a 2D band to 8-bit grayscale using robust percentiles."""

    arr = np.asarray(values, dtype=np.float32)
    finite = arr[np.isfinite(arr)]
    if finite.size == 0:
        return np.zeros(arr.shape, dtype=np.uint8)

    low, high = np.percentile(finite, [1.0, 99.0])
    if not np.isfinite(low) or not np.isfinite(high) or high <= low:
        low = float(np.min(finite))
        high = float(np.max(finite))
    if high <= low:
        return np.zeros(arr.shape, dtype=np.uint8)

    scaled = (arr - low) / (high - low)
    scaled = np.clip(scaled, 0.0, 1.0)
    scaled[~np.isfinite(scaled)] = 0.0
    return (scaled * 255.0).astype(np.uint8)


def save_spectrum_json(
    path: str | Path,
    values: Iterable[float],
    *,
    wavelengths: Iterable[float] | None,
    label: str,
    metadata: dict[str, object] | None = None,
) -> None:
    """Save a spectrum as JSON."""

    values_list = [float(value) if np.isfinite(value) else None for value in values]
    payload: dict[str, object] = {
        "label": label,
        "band_indices": list(range(len(values_list))),
        "values": values_list,
    }
    if wavelengths is not None:
        payload["wavelengths_nm"] = [
            float(value) if np.isfinite(value) else None for value in wavelengths
        ]
    if metadata:
        payload["metadata"] = metadata

    Path(path).write_text(json.dumps(payload, indent=2), encoding="utf-8")


def save_spectrum_csv(
    path: str | Path,
    values: Iterable[float],
    *,
    wavelengths: Iterable[float] | None,
) -> None:
    """Save a spectrum as CSV with band, optional wavelength, and value columns."""

    values_list = list(values)
    wavelength_list = list(wavelengths) if wavelengths is not None else None

    with Path(path).open("w", newline="", encoding="utf-8") as handle:
        writer = csv.writer(handle)
        header = ["band_index"]
        if wavelength_list is not None:
            header.append("wavelength_nm")
        header.append("value")
        writer.writerow(header)

        for index, value in enumerate(values_list):
            row: list[object] = [index]
            if wavelength_list is not None:
                row.append(float(wavelength_list[index]) if index < len(wavelength_list) else "")
            row.append(float(value) if np.isfinite(value) else "")
            writer.writerow(row)


def _read_csv_rows(text: str) -> list[list[float | None]]:
    """Read CSV-ish rows, preserving non-numeric cells as ``None``."""

    rows: list[list[float | None]] = []
    try:
        dialect = csv.Sniffer().sniff(text[:2048]) if "," in text[:2048] else csv.excel
    except csv.Error:
        dialect = csv.excel

    for raw_row in csv.reader(text.splitlines(), dialect=dialect):
        if len(raw_row) <= 1:
            cells = re.split(r"[;\s,]+", raw_row[0].strip()) if raw_row else []
        else:
            cells = raw_row

        parsed: list[float | None] = []
        for cell in cells:
            stripped = cell.strip()
            if not stripped:
                continue
            try:
                parsed.append(float(stripped))
            except ValueError:
                matches = _NUMBER_PATTERN.findall(stripped)
                parsed.append(float(matches[0]) if matches else None)
        if parsed and any(value is not None for value in parsed):
            rows.append(parsed)
    return rows


def _choose_wavelength_column(rows: list[list[float | None]]) -> tuple[np.ndarray, list[str]]:
    """Choose the most wavelength-like column from parsed numeric rows."""

    width = max(len(row) for row in rows)
    matrix = np.full((len(rows), width), np.nan, dtype=float)
    for row_index, row in enumerate(rows):
        for col_index, value in enumerate(row):
            if value is not None:
                matrix[row_index, col_index] = float(value)

    scores: list[tuple[int, float, int]] = []
    for column_index in range(width):
        column = matrix[:, column_index]
        finite = column[np.isfinite(column)]
        if finite.size < 2:
            continue

        minimum = float(np.min(finite))
        maximum = float(np.max(finite))
        median = float(np.median(finite))
        monotonic = bool(np.all(np.diff(finite) >= 0))
        integer_steps = finite.size > 2 and np.allclose(np.diff(finite), 1.0, atol=1e-6)

        score = 0
        if 100.0 <= minimum <= 2500.0 and 100.0 <= maximum <= 2500.0:
            score += 4
        if median >= 250.0:
            score += 3
        if monotonic:
            score += 2
        if not integer_steps:
            score += 2
        scores.append((score, median, column_index))

    if not scores:
        return np.asarray([], dtype=float), []

    _, _, chosen_column = max(scores, key=lambda item: (item[0], item[1], item[2]))
    chosen = matrix[:, chosen_column]
    chosen = chosen[np.isfinite(chosen)]
    notes = [f"Loaded {chosen.size} wavelength value(s) from CSV column {chosen_column + 1}."]
    return chosen, notes
