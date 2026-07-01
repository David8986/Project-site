"""Build a proxy multispectral table from the filtered/normal camera photos.

This is useful when OceanView is unavailable and .ocv files cannot be exported
to wavelength-intensity CSV. The table uses the proposed per-photo filter order
and the measured leaf pixels from the JPG files as an app-ready substitute.
"""

from __future__ import annotations

import csv
import json
from pathlib import Path


PROJECT_ROOT = Path(r"C:\Users\david\OneDrive\Desktop\Archive\Projects\CodeX")
ANALYSIS_DIR = PROJECT_ROOT / "outputs" / "spectrometer_photo_comparison"
POC_DIR = PROJECT_ROOT / "outputs" / "leaf_analysis_poc"


def main() -> None:
    photo_rows = read_csv(ANALYSIS_DIR / "per_photo_leaf_analysis.csv")
    associations = read_csv(ANALYSIS_DIR / "photo_to_filter_association.csv")
    photo_by_name = {row["photo_file"]: row for row in photo_rows}
    rows: list[dict[str, object]] = []

    for assoc in associations:
        photo = photo_by_name.get(assoc["photo_file"])
        if not photo:
            continue
        label = assoc["proposed_camera_filter_or_light"]
        wavelength = label.replace(" nm", "") if label.endswith(" nm") else ""
        rows.append(
            {
                "photo_group": assoc["photo_group"],
                "leaf_condition": assoc["proposed_leaf_condition"],
                "photo_file": assoc["photo_file"],
                "proxy_filter_or_light": label,
                "proxy_wavelength_nm": wavelength,
                "mean_leaf_brightness": number(photo["mean_value_brightness"]),
                "mean_r": number(photo["mean_r"]),
                "mean_g": number(photo["mean_g"]),
                "mean_b": number(photo["mean_b"]),
                "saturation": number(photo["mean_saturation"]),
                "gcc": number(photo["gcc"]),
                "exg": number(photo["exg"]),
                "vari": number(photo["vari"]),
                "confidence": assoc["confidence"],
                "how_to_use": "Use as proxy band response from camera image, not as true spectrometer intensity.",
            }
        )

    write_csv(POC_DIR / "proxy_multispectral_bands_from_photos.csv", rows)
    write_json(POC_DIR / "proxy_multispectral_bands_from_photos.json", rows)
    print(POC_DIR / "proxy_multispectral_bands_from_photos.csv")
    print(POC_DIR / "proxy_multispectral_bands_from_photos.json")


def read_csv(path: Path) -> list[dict[str, str]]:
    with path.open(newline="", encoding="utf-8") as handle:
        return list(csv.DictReader(handle))


def write_csv(path: Path, rows: list[dict[str, object]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(rows[0].keys()))
        writer.writeheader()
        writer.writerows(rows)


def write_json(path: Path, rows: list[dict[str, object]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(rows, indent=2), encoding="utf-8")


def number(value: object) -> float:
    try:
        return round(float(value), 6)
    except (TypeError, ValueError):
        return 0.0


if __name__ == "__main__":
    main()
