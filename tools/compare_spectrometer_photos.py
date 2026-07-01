"""Compare normal camera photos with exported spectrometer measurements.

This script is designed for the leaf dataset in:

    C:/Users/david/OneDrive/Desktop/Archive/Misc/Review Folders/New folder (6)

It can run immediately on the JPG photos and OceanView .ocv file names. For
spectral plots and camera-vs-spectrum tables, export the .ocv measurements from
OceanView as CSV files and place them in an input folder, then pass that folder
with --spectra-csv-dir.
"""

from __future__ import annotations

import argparse
import csv
import math
import re
import zipfile
from dataclasses import dataclass
from pathlib import Path

import matplotlib.pyplot as plt
import numpy as np
from PIL import Image


DEFAULT_DATASET = Path(
    r"C:\Users\david\OneDrive\Desktop\Archive\Misc\Review Folders\New folder (6)"
)
DEFAULT_OUTPUT = Path("outputs") / "spectrometer_photo_comparison"
FILTER_WAVELENGTHS = (532, 556, 680, 725, 850, 940)


@dataclass(frozen=True)
class Spectrum:
    path: Path
    wavelengths_nm: np.ndarray
    values: np.ndarray
    metadata: dict[str, str]


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Build photo metrics and optional spectrum comparisons for leaf measurements."
    )
    parser.add_argument("--dataset", type=Path, default=DEFAULT_DATASET)
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    parser.add_argument(
        "--spectra-csv-dir",
        type=Path,
        default=None,
        help="Folder containing spectra exported from OceanView as CSV/TXT.",
    )
    args = parser.parse_args()

    dataset = args.dataset.expanduser()
    output = args.output.expanduser()
    output.mkdir(parents=True, exist_ok=True)

    photo_rows = analyze_photos(dataset)
    ocv_rows = catalog_ocv_files(dataset)

    write_csv(output / "photo_color_metrics.csv", photo_rows)
    write_csv(output / "spectrometer_file_catalog.csv", ocv_rows)
    plot_photo_metrics(photo_rows, output / "photo_color_indices.png")

    spectra: list[Spectrum] = []
    if args.spectra_csv_dir:
        spectra = load_spectra(args.spectra_csv_dir.expanduser())
        if spectra:
            write_csv(output / "exported_spectrum_features.csv", spectrum_feature_rows(spectra))
            plot_spectra(spectra, output / "exported_spectra_overlay.png")
            write_csv(output / "camera_vs_spectrum_template.csv", comparison_template(photo_rows, spectra))

    write_readme(output, dataset, args.spectra_csv_dir, len(photo_rows), len(ocv_rows), len(spectra))
    print(f"Wrote analysis files to: {output.resolve()}")


def analyze_photos(dataset: Path) -> list[dict[str, object]]:
    rows: list[dict[str, object]] = []
    for path in sorted(dataset.rglob("*.jpg")):
        image = Image.open(path).convert("RGB")
        arr = np.asarray(image, dtype=np.float32) / 255.0
        r, g, b = arr[:, :, 0], arr[:, :, 1], arr[:, :, 2]

        # Remove very dark background/shadow pixels and nearly white glare.
        brightness = (r + g + b) / 3.0
        green_dominance = g - np.maximum(r, b)
        mask = (brightness > 0.08) & (brightness < 0.95) & (green_dominance > -0.08)
        if np.count_nonzero(mask) < 500:
            mask = brightness > 0.08

        rr, gg, bb = r[mask], g[mask], b[mask]
        denominator = rr + gg + bb
        safe_denominator = np.where(denominator == 0, np.nan, denominator)
        gcc = np.nanmean(gg / safe_denominator)
        exg = np.nanmean(2.0 * gg - rr - bb)
        vari_denominator = gg + rr - bb
        vari = np.nanmean((gg - rr) / np.where(np.abs(vari_denominator) < 1e-6, np.nan, vari_denominator))

        rows.append(
            {
                "file": path.name,
                "relative_path": str(path.relative_to(dataset)),
                "photo_group": path.parent.name,
                "width": image.width,
                "height": image.height,
                "masked_pixels": int(np.count_nonzero(mask)),
                "mean_r": round_float(np.nanmean(rr)),
                "mean_g": round_float(np.nanmean(gg)),
                "mean_b": round_float(np.nanmean(bb)),
                "gcc_green_chromatic_coordinate": round_float(gcc),
                "exg_excess_green": round_float(exg),
                "vari_visible_atmospherically_resistant_index": round_float(vari),
            }
        )
    return rows


def catalog_ocv_files(dataset: Path) -> list[dict[str, object]]:
    rows: list[dict[str, object]] = []
    seen_hash_names: set[tuple[str, int]] = set()
    for path in sorted(dataset.rglob("*.ocv")):
        if path.parts[-2:] and "New folder" in path.parts:
            duplicate_hint = "possible duplicate copy"
        else:
            duplicate_hint = ""
        metadata = infer_measurement_metadata(path)
        rows.append(
            {
                "file": path.name,
                "relative_path": str(path.relative_to(dataset)),
                "size_bytes": path.stat().st_size,
                "is_oceanview_zip_container": zipfile.is_zipfile(path),
                "duplicate_hint": duplicate_hint,
                **metadata,
            }
        )
        seen_hash_names.add((path.name, path.stat().st_size))
    return rows


def infer_measurement_metadata(path: Path) -> dict[str, str]:
    stem_text = path.stem.lower()
    parent_text = path.parent.name.lower()
    text = f"{parent_text} {stem_text}"
    wavelength = ""
    for value in FILTER_WAVELENGTHS:
        if re.search(rf"(^|[^0-9]){value}([^0-9]|$)", text):
            wavelength = str(value)
            break

    if "maro" in stem_text:
        condition = "brown leaf area"
    elif "galben" in stem_text or "_g_" in stem_text or stem_text.startswith("f_g"):
        condition = "yellow/unhealthy leaf"
    elif "verde" in stem_text or "_v_" in stem_text or stem_text.startswith("f_v"):
        condition = "green/healthy leaf"
    elif any(token in text for token in ("galben", "_g_", " f g", "f_g", "nesanatoasa")):
        condition = "yellow/unhealthy leaf"
    elif any(token in text for token in ("verde", "_v_", " f v", "f_v")):
        condition = "green/healthy leaf"
    elif "uvvis" in text or "uv vis" in text:
        condition = "outside/UV-VIS reference"
    else:
        condition = "unknown"

    if "spectru" in text and "intreg" in text:
        measurement = "full spectrum"
    elif "fara filtru" in text or "farafiltru" in text or "direct" in text:
        measurement = "direct/no filter"
    elif wavelength:
        measurement = "filtered"
    else:
        measurement = "unknown"

    return {
        "leaf_condition": condition,
        "measurement_type": measurement,
        "filter_nm": wavelength,
    }


def load_spectra(folder: Path) -> list[Spectrum]:
    spectra: list[Spectrum] = []
    for path in sorted(folder.rglob("*")):
        if path.suffix.lower() not in {".csv", ".txt", ".tsv"}:
            continue
        parsed = parse_spectrum_csv(path)
        if parsed is not None:
            spectra.append(parsed)
    return spectra


def parse_spectrum_csv(path: Path) -> Spectrum | None:
    rows: list[list[float]] = []
    text = path.read_text(encoding="utf-8-sig", errors="ignore")
    delimiter = "\t" if path.suffix.lower() == ".tsv" else None
    for raw in csv.reader(text.splitlines(), delimiter=delimiter or ","):
        if len(raw) <= 1:
            raw = re.split(r"[;,\t ]+", raw[0].strip()) if raw else []
        values: list[float] = []
        for cell in raw:
            try:
                values.append(float(cell.strip()))
            except ValueError:
                pass
        if len(values) >= 2:
            rows.append(values)

    if len(rows) < 5:
        return None

    width = max(len(row) for row in rows)
    matrix = np.full((len(rows), width), np.nan, dtype=np.float32)
    for row_index, row in enumerate(rows):
        for col_index, value in enumerate(row):
            matrix[row_index, col_index] = value

    wavelength_col = choose_wavelength_column(matrix)
    if wavelength_col is None:
        return None

    value_col = 1 if wavelength_col == 0 else 0
    wavelengths = matrix[:, wavelength_col]
    values = matrix[:, value_col]
    valid = np.isfinite(wavelengths) & np.isfinite(values)
    if np.count_nonzero(valid) < 5:
        return None

    return Spectrum(
        path=path,
        wavelengths_nm=wavelengths[valid].astype(float),
        values=values[valid].astype(float),
        metadata=infer_measurement_metadata(path),
    )


def choose_wavelength_column(matrix: np.ndarray) -> int | None:
    best: tuple[int, int] | None = None
    for col_index in range(matrix.shape[1]):
        column = matrix[:, col_index]
        finite = column[np.isfinite(column)]
        if finite.size < 5:
            continue
        score = 0
        if 180 <= float(np.nanmin(finite)) <= 450:
            score += 2
        if 650 <= float(np.nanmax(finite)) <= 1100:
            score += 2
        if np.all(np.diff(finite) >= 0):
            score += 2
        if 300 <= float(np.nanmedian(finite)) <= 900:
            score += 2
        candidate = (score, col_index)
        if best is None or candidate > best:
            best = candidate
    return best[1] if best and best[0] >= 4 else None


def spectrum_feature_rows(spectra: list[Spectrum]) -> list[dict[str, object]]:
    rows: list[dict[str, object]] = []
    for spectrum in spectra:
        row: dict[str, object] = {
            "file": spectrum.path.name,
            "relative_path": str(spectrum.path),
            **spectrum.metadata,
            "max_intensity": round_float(np.nanmax(spectrum.values)),
            "mean_intensity": round_float(np.nanmean(spectrum.values)),
        }
        for wavelength in FILTER_WAVELENGTHS:
            row[f"intensity_at_{wavelength}nm"] = round_float(interpolate_at(spectrum, wavelength))
        row["ratio_850_680"] = round_float(safe_ratio(interpolate_at(spectrum, 850), interpolate_at(spectrum, 680)))
        row["ratio_725_680"] = round_float(safe_ratio(interpolate_at(spectrum, 725), interpolate_at(spectrum, 680)))
        rows.append(row)
    return rows


def comparison_template(photo_rows: list[dict[str, object]], spectra: list[Spectrum]) -> list[dict[str, object]]:
    rows: list[dict[str, object]] = []
    photo_summary = summarize_photo_groups(photo_rows)
    for spectrum in spectra:
        condition = spectrum.metadata.get("leaf_condition", "unknown")
        likely_photo_group = "Poze normale frunza 1" if "green" in condition else "Poze normale frunza 2"
        photo = photo_summary.get(likely_photo_group, {})
        rows.append(
            {
                "spectrum_file": spectrum.path.name,
                "leaf_condition": condition,
                "filter_nm": spectrum.metadata.get("filter_nm", ""),
                "likely_photo_group": likely_photo_group,
                "photo_mean_gcc": photo.get("mean_gcc_green_chromatic_coordinate", ""),
                "photo_mean_exg": photo.get("mean_exg_excess_green", ""),
                "photo_mean_vari": photo.get("mean_vari_visible_atmospherically_resistant_index", ""),
                "spectrum_i_680": round_float(interpolate_at(spectrum, 680)),
                "spectrum_i_850": round_float(interpolate_at(spectrum, 850)),
                "spectrum_ratio_850_680": round_float(
                    safe_ratio(interpolate_at(spectrum, 850), interpolate_at(spectrum, 680))
                ),
            }
        )
    return rows


def summarize_photo_groups(photo_rows: list[dict[str, object]]) -> dict[str, dict[str, float]]:
    grouped: dict[str, list[dict[str, object]]] = {}
    for row in photo_rows:
        grouped.setdefault(str(row["photo_group"]), []).append(row)

    summaries: dict[str, dict[str, float]] = {}
    for group, rows in grouped.items():
        summary: dict[str, float] = {}
        for key in (
            "gcc_green_chromatic_coordinate",
            "exg_excess_green",
            "vari_visible_atmospherically_resistant_index",
        ):
            values = [float(row[key]) for row in rows if row.get(key) not in ("", None)]
            summary[f"mean_{key}"] = round_float(np.nanmean(values)) if values else math.nan
        summaries[group] = summary
    return summaries


def plot_photo_metrics(rows: list[dict[str, object]], output: Path) -> None:
    if not rows:
        return
    groups = sorted({str(row["photo_group"]) for row in rows})
    metrics = [
        ("gcc_green_chromatic_coordinate", "GCC"),
        ("exg_excess_green", "ExG"),
        ("vari_visible_atmospherically_resistant_index", "VARI"),
    ]
    x = np.arange(len(groups))
    width = 0.24

    fig, ax = plt.subplots(figsize=(9, 5))
    for index, (key, label) in enumerate(metrics):
        values = []
        for group in groups:
            group_values = [float(row[key]) for row in rows if row["photo_group"] == group]
            values.append(float(np.nanmean(group_values)))
        ax.bar(x + (index - 1) * width, values, width=width, label=label)
    ax.set_xticks(x)
    ax.set_xticklabels(groups, rotation=10)
    ax.set_title("Normal camera color indices by photo group")
    ax.legend()
    ax.grid(axis="y", alpha=0.25)
    fig.tight_layout()
    fig.savefig(output, dpi=160)
    plt.close(fig)


def plot_spectra(spectra: list[Spectrum], output: Path) -> None:
    fig, ax = plt.subplots(figsize=(10, 6))
    for spectrum in spectra:
        values = spectrum.values
        finite = values[np.isfinite(values)]
        if finite.size == 0:
            continue
        normalized = values / np.nanmax(np.abs(finite))
        label = f"{spectrum.path.stem} ({spectrum.metadata.get('leaf_condition', 'unknown')})"
        ax.plot(spectrum.wavelengths_nm, normalized, linewidth=1.4, label=label)
    for wavelength in FILTER_WAVELENGTHS:
        ax.axvline(wavelength, color="black", linewidth=0.5, alpha=0.15)
    ax.set_xlabel("Wavelength (nm)")
    ax.set_ylabel("Normalized intensity")
    ax.set_title("Exported spectrometer spectra")
    ax.grid(alpha=0.25)
    ax.legend(fontsize=7)
    fig.tight_layout()
    fig.savefig(output, dpi=160)
    plt.close(fig)


def interpolate_at(spectrum: Spectrum, wavelength: float) -> float:
    if spectrum.wavelengths_nm.size < 2:
        return math.nan
    return float(np.interp(wavelength, spectrum.wavelengths_nm, spectrum.values))


def safe_ratio(numerator: float, denominator: float) -> float:
    if not np.isfinite(numerator) or not np.isfinite(denominator) or abs(denominator) < 1e-12:
        return math.nan
    return float(numerator / denominator)


def write_csv(path: Path, rows: list[dict[str, object]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    if not rows:
        path.write_text("", encoding="utf-8")
        return
    fieldnames: list[str] = []
    for row in rows:
        for key in row:
            if key not in fieldnames:
                fieldnames.append(key)
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)


def write_readme(
    output: Path,
    dataset: Path,
    spectra_csv_dir: Path | None,
    photo_count: int,
    ocv_count: int,
    spectrum_count: int,
) -> None:
    spectra_note = (
        f"Loaded {spectrum_count} exported spectra from {spectra_csv_dir}."
        if spectra_csv_dir
        else "No exported spectrum CSV folder was provided yet."
    )
    text = f"""# Spectrometer vs Photo Comparison

Dataset: `{dataset}`

Generated:

- `photo_color_metrics.csv`: color features from the normal camera photos.
- `photo_color_indices.png`: quick visual comparison of photo groups.
- `spectrometer_file_catalog.csv`: inferred labels from `.ocv` file names.

Counts:

- Photos analyzed: {photo_count}
- `.ocv` spectrometer containers cataloged: {ocv_count}
- Exported spectrum CSV files analyzed: {spectrum_count}

{spectra_note}

To compare spectrometer curves with photos, export the OceanView measurements as
CSV/TXT first. A useful export has at least two numeric columns:

```text
wavelength_nm,intensity
400.12,123.4
400.50,124.8
```

Then run:

```powershell
python tools/compare_spectrometer_photos.py --spectra-csv-dir "C:\\path\\to\\exported\\spectra"
```

The script will add:

- `exported_spectrum_features.csv`
- `exported_spectra_overlay.png`
- `camera_vs_spectrum_template.csv`
"""
    (output / "README.md").write_text(text, encoding="utf-8")


def round_float(value: object, digits: int = 6) -> float:
    try:
        number = float(value)
    except (TypeError, ValueError):
        return math.nan
    return round(number, digits) if math.isfinite(number) else math.nan


if __name__ == "__main__":
    main()
