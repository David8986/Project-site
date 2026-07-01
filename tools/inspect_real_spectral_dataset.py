"""Light inspection for the real leaf spectral/camera dataset."""

from __future__ import annotations

import csv
import re
from pathlib import Path

import numpy as np


DATA_ROOT = Path(r"C:\Users\david\OneDrive\Desktop\data analisys")
OUT_DIR = Path(r"C:\Users\david\OneDrive\Desktop\Archive\Projects\CodeX\outputs\real_data_inspection")


def main() -> None:
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    rows = []
    for path in sorted(DATA_ROOT.rglob("*.txt")):
        spectrum = read_spectrum(path)
        if spectrum is None:
            continue
        wavelengths, intensities = spectrum
        finite = intensities[np.isfinite(intensities)]
        rows.append(
            {
                "relative_path": str(path.relative_to(DATA_ROOT)),
                "file": path.name,
                "environment": path.relative_to(DATA_ROOT).parts[0],
                "role": infer_role(path),
                "filter_nm_from_name": infer_filter(path.name),
                "points": len(wavelengths),
                "wavelength_min": round(float(np.nanmin(wavelengths)), 3),
                "wavelength_max": round(float(np.nanmax(wavelengths)), 3),
                "intensity_min": round(float(np.nanmin(finite)), 3),
                "intensity_max": round(float(np.nanmax(finite)), 3),
                "intensity_mean": round(float(np.nanmean(finite)), 3),
                "peak_wavelength_nm": round(float(wavelengths[np.nanargmax(intensities)]), 3),
                "peak_intensity": round(float(np.nanmax(intensities)), 3),
                "i_532": round(float(np.interp(532, wavelengths, intensities)), 3),
                "i_556": round(float(np.interp(556, wavelengths, intensities)), 3),
                "i_680": round(float(np.interp(680, wavelengths, intensities)), 3),
                "i_725": round(float(np.interp(725, wavelengths, intensities)), 3),
                "i_850": round(float(np.interp(850, wavelengths, intensities)), 3),
                "i_940": round(float(np.interp(940, wavelengths, intensities)), 3),
            }
        )

    out = OUT_DIR / "spectral_file_inventory.csv"
    with out.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(rows[0].keys()))
        writer.writeheader()
        writer.writerows(rows)
    print(f"parsed_spectra={len(rows)}")
    print(out)


def read_spectrum(path: Path) -> tuple[np.ndarray, np.ndarray] | None:
    text = path.read_text(encoding="utf-8", errors="ignore").splitlines()
    start = 0
    for index, line in enumerate(text):
        if "Begin Spectral Data" in line:
            start = index + 1
            break
    pairs = []
    for line in text[start:]:
        nums = re.findall(r"[-+]?(?:\d*\.\d+|\d+)(?:[eE][-+]?\d+)?", line)
        if len(nums) >= 2:
            pairs.append((float(nums[0]), float(nums[1])))
    if len(pairs) < 10:
        return None
    arr = np.asarray(pairs, dtype=float)
    return arr[:, 0], arr[:, 1]


def infer_filter(name: str) -> str:
    match = re.search(r"(532|556|580|680|725|850|940|950)", name)
    if match:
        return match.group(1)
    if "fara" in name.lower() or "filtru" in name.lower():
        return "none"
    return ""


def infer_role(path: Path) -> str:
    low = str(path).lower()
    if "referinta alba" in low or "refalb" in low:
        return "white_reference"
    if "referinta neagra" in low or "refnegru" in low or "refirinta neagra" in low:
        return "dark_reference"
    if "soare" in low or "sursa" in low:
        return "source_light"
    if "sanatoasa" in low or "\\san\\" in low or "frunza verde" in low:
        return "healthy_leaf"
    if "nesan" in low:
        return "unhealthy_leaf"
    return "sample_or_unknown"


if __name__ == "__main__":
    main()
