"""Create a proposed photo-to-spectrometer association table for the leaf dataset."""

from __future__ import annotations

import csv
from pathlib import Path


DATASET = Path(r"C:\Users\david\OneDrive\Desktop\Archive\Misc\Review Folders\New folder (6)")
OUTPUT = Path("outputs") / "spectrometer_photo_comparison" / "proposed_measurement_associations.csv"


def main() -> None:
    rows: list[dict[str, str]] = []

    group1_photos = sorted((DATASET / "Camera Roll" / "Poze normale frunza 1").glob("*.jpg"))
    group2_photos = sorted((DATASET / "Camera Roll" / "Poze normale frunza 2").glob("*.jpg"))

    green_spectra = sorted((DATASET / "Camera Roll" / "spectrometru frunza" / "verde frunza").glob("*.ocv"))
    yellow_spectra = sorted(
        (DATASET / "Camera Roll" / "spectrometru frunza" / "fruza nesanatoasa-galben").glob("*.ocv")
    )
    direct_spectra = sorted(
        (DATASET / "Camera Roll" / "spectrometru frunza" / "fara filtru frunza verde-galben-maro").glob("*.ocv")
    )

    add_rows(
        rows,
        leaf_id="leaf_or_region_A",
        proposed_condition="green/healthy leaf",
        confidence="medium",
        reason="Photo group 1 was captured first; the first spectrometer sequence is in folder 'verde frunza'.",
        photos=group1_photos,
        spectra=green_spectra,
    )
    add_rows(
        rows,
        leaf_id="leaf_or_region_B",
        proposed_condition="yellow/unhealthy leaf",
        confidence="medium",
        reason="Photo group 2 was captured second; the next spectrometer sequence is in folder 'fruza nesanatoasa-galben'.",
        photos=group2_photos,
        spectra=yellow_spectra,
    )

    for spectrum in direct_spectra:
        stem = spectrum.stem.lower()
        if "verde" in stem:
            photos = group1_photos
            leaf_id = "leaf_or_region_A"
            condition = "green/healthy direct/no-filter"
        elif "galben" in stem:
            photos = group2_photos
            leaf_id = "leaf_or_region_B"
            condition = "yellow/unhealthy direct/no-filter"
        else:
            photos = []
            leaf_id = "brown_region_no_matching_photo"
            condition = "brown direct/no-filter"
        add_rows(
            rows,
            leaf_id=leaf_id,
            proposed_condition=condition,
            confidence="low" if not photos else "medium",
            reason="Direct/no-filter spectrometer file name identifies the measured region.",
            photos=photos,
            spectra=[spectrum],
        )

    write_csv(OUTPUT, rows)
    print(f"Wrote {OUTPUT.resolve()}")


def add_rows(
    rows: list[dict[str, str]],
    *,
    leaf_id: str,
    proposed_condition: str,
    confidence: str,
    reason: str,
    photos: list[Path],
    spectra: list[Path],
) -> None:
    if not photos:
        photos = [Path("")]
    for spectrum in spectra:
        for photo in photos:
            rows.append(
                {
                    "leaf_id": leaf_id,
                    "proposed_condition": proposed_condition,
                    "photo_file": photo.name,
                    "photo_relative_path": relative(photo),
                    "spectrum_file": spectrum.name,
                    "spectrum_relative_path": relative(spectrum),
                    "confidence": confidence,
                    "reason": reason,
                }
            )


def relative(path: Path) -> str:
    if not str(path):
        return ""
    try:
        return str(path.relative_to(DATASET))
    except ValueError:
        return str(path)


def write_csv(path: Path, rows: list[dict[str, str]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(
            handle,
            fieldnames=[
                "leaf_id",
                "proposed_condition",
                "photo_file",
                "photo_relative_path",
                "spectrum_file",
                "spectrum_relative_path",
                "confidence",
                "reason",
            ],
        )
        writer.writeheader()
        writer.writerows(rows)


if __name__ == "__main__":
    main()
