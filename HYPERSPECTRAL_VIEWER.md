# Hyperspectral ENVI Explorer

Local desktop explorer for ENVI-style `.hdr` + `.raw` hyperspectral data and
plant-health dataset debugging.

## Setup

```bash
python -m pip install -r hyperspectral_viewer_requirements.txt
```

The spectrum graphs use `matplotlib` embedded inside the `PySide6` desktop
window. The ENVI data itself is loaded with `spectral`.

## Run

```bash
python viewer.py
```

## Workflow

1. Open a dataset root, extracted sample folder, or a direct `feuille...hdr`.
2. Load `wave_lengths.csv` when the header wavelength list is missing or less reliable.
3. Click **List samples**, then **Load selected**.
4. Browse grayscale bands, RGB-like composites, and false-color vegetation composites.
5. Switch between raw, dark, white, and calibrated reflectance views.
6. Click pixels for full spectra, or enable ROI mode and drag ROI A / ROI B.
7. Run vegetation + suspicious-region analysis to show masks, spot labels, indices, and whole-leaf spectra.
8. Use the quality tab to inspect low dynamic range, edge-band, and possible striping warnings.
9. Export displayed images, spectra, reports, and suspicious-region tables.

The GUI calls the core analysis package instead of duplicating scientific logic:

- adapters load datasets and ignore `._*` files
- calibration computes reflectance as `(raw - dark) / (white - dark)`
- target-band mapping and semantic roles resolve wavelengths
- vegetation masking, suspicious-region detection, and indices come from `plant_health_mvp`

Confirmed target buttons:

| Wavelength | Band index |
| --- | ---: |
| 532 nm | 51 |
| 556 nm | 60 |
| 650 nm | 95 |
| 680 nm | 106 |
| 725 nm | 123 |
| 850 nm | 168 |
| 940 nm | 200 |

Semantic role buttons:

- `GREEN`
- `RED`
- `RED_EDGE`
- `NIR`
- `WATER_BAND`

## Current Limitations

- Suspicious-region detection is deterministic debugging logic, not diagnosis.
- Display destriping and histogram equalization are preview-only and never alter scientific values.
- Very large datasets are currently loaded into memory by the adapter layer.
- Calibration depends on matching dark/white references being discoverable by the adapter.
