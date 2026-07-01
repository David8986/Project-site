# Plant Health MVP

This package is the first local MVP for a plant-health multispectral analysis
pipeline. The goal is to work with public spectral or hyperspectral data first,
then later swap in a real 7-band camera source without changing the downstream
analysis logic.

## Setup

```bash
cd plant_health_mvp
python -m venv .venv
.venv\Scripts\activate
pip install -r requirements.txt
```

## Purpose

The pipeline is designed to:

1. Load one sample from a local dataset
2. Inspect available wavelengths
3. Map source wavelengths to the target 7-band set
4. Extract exact, nearest, or interpolated bands where possible
5. Build a simple vegetation mask
6. Compute the average spectrum over vegetation pixels
7. Detect localized suspicious spot / lesion candidates inside the leaf mask
8. Save images, CSV tables, and JSON reports

Target wavelengths:

- 532 nm
- 556 nm
- 650 nm
- 680 nm
- 725 nm
- 850 nm
- 940 nm

## Architecture

The project is split into one shared scientific backend and two separate apps:

```text
plant_health_mvp/
  core/          shared scientific backend
  viewer_app/    dedicated exploration GUI
  analysis_app/  dedicated processing/reporting GUI
```

Both apps import from `plant_health_mvp.core`. Loaders, adapters, calibration,
wavelength mapping, vegetation masking, indices, suspicious-region detection,
ROI helpers, and exports live only in the shared backend.

## Usage

From the repository root:

```bash
python -m plant_health_mvp.main
```

That command runs the full MVP on a deterministic mock hyperspectral cube and
writes outputs to `plant_health_mvp/runs/latest`.

To use a local dataset and a wavelength CSV:

```bash
python -m plant_health_mvp.main --input path/to/sample.npz --wavelengths path/to/wavelengths.csv --output plant_health_mvp/runs/my_sample
```

Wavelength CSVs may be a simple one-column list or a common two-column
`index,wavelength` file.

Supported MVP input formats:

- `.npz` with `cube` or `data`, plus optional `wavelengths` or `available_wavelengths`
- `.npy` with a separate `--wavelengths` CSV
- mixed-image `.json` specs created by the Analysis app import wizard
- RGB image files: `.jpg`, `.jpeg`, `.png`, `.tif`, `.tiff`, `.bmp`
- `.csv` / `.txt` spectral tables
- `.tar.gz` / `.tgz` archives containing Specim/ENVI `capture/*.hdr` and `capture/*.raw`
- extracted Specim/ENVI sample folders containing `capture/*.hdr` and `capture/*.raw`

To run one real dataset sample from the leaf archive:

```bash
python -m plant_health_mvp.main --input "C:\Users\david\Downloads\feuille1.tar.gz" --wavelengths "C:\Users\david\OneDrive\Desktop\wave_lengths .csv" --output plant_health_mvp/runs/feuille1_real
```

To run one extracted sample folder:

```bash
python -m plant_health_mvp.main --input "D:\downloads\feuille1\feuille1_mildiou42_15jan_3dpi_test_2018-01-18_22-07-48" --wavelengths "C:\Users\david\OneDrive\Desktop\wave_lengths .csv" --output plant_health_mvp/runs/feuille1_mildiou42
```

Spot detection knobs are deterministic and explainable:

```bash
python -m plant_health_mvp.main --input "D:\downloads\feuille1\feuille1_mildiou42_15jan_3dpi_test_2018-01-18_22-07-48" --wavelengths "C:\Users\david\OneDrive\Desktop\wave_lengths .csv" --output plant_health_mvp/runs/feuille1_spots --spot-threshold 0.50 --spot-min-area 20 --spot-texture-window 5
```

To run an RGB-only photo, give the image path directly. The app labels the
ordinary RGB channels as approximate display bands: red -> 650 nm, green -> 556
nm, blue -> 532 nm. This is useful for visual masking, RGB averages, overlays,
and simple RGB anomaly candidates, but it is not hyperspectral data and cannot
produce true NDVI, NDRE, NIR, red-edge, or 940 nm water-band measurements.

```bash
python -m plant_health_mvp.main --input "C:\path\to\leaf_photo.jpg" --output plant_health_mvp/runs/my_rgb_photo
```

The analysis app also has a `Choose Image/File` button for JPEG/PNG/TIFF/BMP
inputs. For RGB-only outputs, choose the `RGB-like composite 650/556/532`
background in the overlay tab.

For a mixed visual input such as one RGB photo plus one 850 nm NIR grayscale
image, open the Analysis app and click `Mixed Import Wizard`. Add the RGB file,
add the grayscale file, use `Quick Start: RGB + NIR 850` or manually assign
roles/wavelengths, choose an alignment mode, then save the generated JSON spec.
The app will place that spec path in the sample field; click `Run Analysis`.

The same mixed bundle can be run from the command line:

```bash
python -m plant_health_mvp.main --input "C:\path\to\mixed_import_spec.json" --output plant_health_mvp/runs/my_rgb_nir_bundle
```

For RGB + NIR input, the app can compute vegetation masking, suspicious-region
analysis, GNDVI-style values, and an explicitly labeled `NDVI-like (RGB red +
NIR)` value. It will not fake unavailable outputs such as NDRE or the 940 nm
water proxy; reports list those as unavailable with reasons.

Mixed-image alignment runs before vegetation masking and before suspicious
region analysis. Available modes are:

- `Automatic ECC`, which optimizes a global transform between the moving image
  and the reference image
- `Automatic feature/edge`, which uses edge-enhanced ORB feature matching
- `Automatic contour/mask`, which aligns broad foreground shape/mask moments
- `Resize only`, which only matches dimensions and is reported as low confidence
- `None`, which requires images to already have the same dimensions

The report records the reference image, selected alignment mode, transform
model, status, confidence where available, and transform matrix. If automatic
alignment fails, the importer falls back to resize-only and reports a warning
instead of silently pretending registration succeeded.

To process a whole folder of supported samples:

```bash
python -m plant_health_mvp.batch --input-folder "C:\Users\david\Downloads" --wavelengths "C:\Users\david\OneDrive\Desktop\wave_lengths .csv" --output plant_health_mvp/runs/batch_downloads
```

Each sample writes its own subfolder with band images, `band_mapping.csv`,
`indices_report.csv`, the JSON equivalents, spot outputs, and any
vegetation/spectrum outputs.
The batch command names folders like `001__sample_name__a1b2c3d4` so they are
easy to match back to the source sample and do not collide. It also writes
`batch_summary.csv` and `batch_summary.json` in the output folder.

To save a reusable mock dataset:

```bash
python -m plant_health_mvp.main --save-mock-dataset
```

## Viewer App

The viewer app is for manual inspection and debugging. It opens a dataset/sample,
browses source bands, switches between raw/dark/white/reflectance views, plots
pixel and ROI spectra, and exports simple preview images or spectra. It is not
the batch/reporting workflow.

Launch it from the repository root:

```bash
python -m plant_health_mvp.viewer_app.main --input "D:\downloads\feuille1\feuille1_mildiou42_15jan_3dpi_test_2018-01-18_22-07-48" --wavelengths "C:\Users\david\OneDrive\Desktop\wave_lengths .csv" --output plant_health_mvp/runs/viewer_export
```

Or double-click:

```text
PLANT_HEALTH_VIEWER.bat
```

## Main Analysis App

The analysis app is for processing. It loads a sample, runs vegetation masking,
computes whole-leaf spectra and indices, detects suspicious regions, shows the
region table, displays affected-area candidate overlays, and exports JSON/CSV
reports. It intentionally does not include deep manual band exploration.

Launch it from the repository root:

```bash
python -m plant_health_mvp.analysis_app.main --input "D:\downloads\feuille1\feuille1_mildiou42_15jan_3dpi_test_2018-01-18_22-07-48" --wavelengths "C:\Users\david\OneDrive\Desktop\wave_lengths .csv" --output plant_health_mvp/runs/analysis_export
```

Or double-click:

```text
PLANT_HEALTH_ANALYSIS.bat
```

In the `Overlay / Visualization` tab you can choose:

- background: 680 nm, 725 nm, 850 nm, RGB-like 650/556/532, or false-color 850/725/680
- mode: outline overlay, filled suspicious mask overlay, anomaly heatmap,
  vegetation mask, or background only
- overlay opacity
- subtle contour outlines, suspicious mask, filled overlay, vegetation mask,
  labels, and bounding boxes on/off

The default suspicious-region visualization is the outline overlay. It uses a
thin neutral gray/white contour boundary so affected-area candidates stay
visible without hiding the leaf. Bounding boxes and labels are optional and are
off by default for a cleaner first view. The filled red overlay, vegetation-mask
overlay, and anomaly heatmap remain available for stronger inspection views.

The analysis workspace also includes:

- `Summary`, a short human-readable deterministic analysis summary
- `Spectra`, with whole-leaf and selected-region target-band curves
- `Stats / Histogram`, with display-image histograms and basic statistics
- `Indices`, with whole-leaf and selected-region major index values
- `Suspicious Regions`, the connected-component table
- `Readable Report`, a longer human-friendly report
- `Glossary`, in-app explanations of controls, thresholds, graphs, data modes,
  band mapping, indices, ROI terms, and outputs
- `JSON Report`, the structured report for downstream tools

These are display-only affected-area candidate visualizations. They use the
already computed suspicious mask, connected components, and anomaly score map;
they do not change scientific reflectance or index values. Export buttons save
the current visualization or the full set of background/outline/fill/heatmap
images under the output folder's `visualizations/` directory.

The old `python -m plant_health_mvp.gui_app` command now opens the viewer app
for compatibility. Prefer the explicit viewer/analysis commands above.

## Mock-data fallback

If no real dataset is available, the app should fall back to a small local mock
sample through `MockAdapter` so the band-mapping and extraction path can still
run. Vegetation masking and average-spectrum extraction are skipped for
synthetic no-input runs in the CLI so reports do not imply that mock values are
biological measurements.

## Expected outputs

The MVP should write:

- extracted band images
- a vegetation mask image
- `spot_score.png`, `suspicious_spot_mask.png`, `spot_labels.png`
- `spots.csv` with per-spot measurements
- a JSON report with:
  - `report_schema="plant_health_analysis_v2"`
  - available wavelengths
  - source-to-target band mapping
  - semantic band-role resolution
  - missing bands
  - average vegetation spectrum
  - vegetation pixel count
  - adapter used and calibration status
  - whether analysis used raw intensity or calibrated reflectance
  - spot detection parameters and per-spot measurements
  - report warnings and low-confidence mapping notes
  - sample metadata
- an `indices_report.json` file with average band values, index formulas,
  raw components, and scalar vegetation-index values
- CSV versions, `band_mapping.csv`, `average_bands.csv`, `summary_report.csv`,
  `spots.csv`, and `indices_report.csv`, for easier
  reading in Excel or Google Sheets

## Dataset adapters

Dataset-specific parsing belongs in `core/adapters/`. The current
`EnviHyperspectralAdapter` supports extracted or archived ENVI-style
`.hdr` + `.raw` samples and ignores macOS sidecar files beginning with `._`.
`MockAdapter` provides a deterministic synthetic cube for development and tests.

Adapters expose:

- sample id
- cube data
- wavelength list
- metadata
- optional dark and white references
- optional preview image
- source type
- whether calibrated reflectance is available

The rest of the app works through the adapter output and the canonical
`SpectralSample`, so future datasets can have different wavelength ranges, band
counts, and folder layouts.

To add a future adapter:

1. Create a new class that implements `DatasetAdapter`.
2. Keep dataset-specific file discovery and parsing inside that adapter.
3. Return an `AdapterSample` with cube data and wavelengths.
4. Register the adapter in `core/adapters/registry.py`.
5. Let the existing mapping, calibration, vegetation, spot, index, and export
   modules run unchanged.

## Band profiles and semantic roles

Target wavelengths are configured through `core/band_profiles.py`. The default
profile is `profile_7band_default`:

```text
532, 556, 650, 680, 725, 850, 940
```

Spot detection uses semantic roles from `core/semantic_roles.py` where possible:

- `RED` prefers 680 nm and falls back to 650 nm
- `GREEN` prefers 556 nm and falls back to 532 nm
- `RED_EDGE` prefers 725 nm
- `NIR` prefers 850 nm
- `WATER_BAND` prefers 940 nm

This keeps the detector usable on future datasets that do not exactly match the
current seven target wavelengths.

## Future camera input

The future 7-band camera adapter should plug in as another `DatasetAdapter` and
populate an `AdapterSample` or the shared `SpectralSample` model. Everything
after that should keep working against the normalized internal representation.

Concretely, a future camera loader should create:

- `source_type="future_camera_capture"`
- `available_wavelengths=np.array([532, 556, 650, 680, 725, 850, 940])`
- `data` shaped `(height, width, 7)` in the same band order
- metadata with camera exposure, gain, calibration, capture time, and panel reference details

## Package contract

Shared sample types live in `core/models/sample.py` and define:

- `TARGET_WAVELENGTHS_NM`
- `VALID_STATUSES`
- `BandMapping`
- `SpectralSample`

Adapter interfaces live in:

- `core/adapters/base.py`
- `core/adapters/envi_adapter.py`
- `core/adapters/mock_adapter.py`
- `core/adapters/registry.py`

Compatibility shims remain at the old import paths, for example
`plant_health_mvp.loader`, so older scripts can keep running while new app code
uses `plant_health_mvp.core`.

## Reflectance calibration

If a sample includes DARKREF and WHITEREF cubes, the ENVI adapter calibrates the
main cube before analysis:

```text
R = (I - D) / (W - D)
```

The report records whether calibration was applied and whether the analysis used
`calibrated_reflectance`, `raw_intensity`, or synthetic mock values. Invalid
dark/white denominators are reported, and those calibrated pixels are kept as
`NaN` so scientific averages can ignore them. PNG export still uses display-only
normalization and does not change the scientific values.

## Suspicious-region detection

The suspicious-region detector is deterministic candidate finding, not disease
diagnosis. It combines role-based index maps, band-difference maps, whole-leaf
z-score anomalies, and simple local texture. The output mask is thresholded,
cleaned with morphology, labeled into connected components, and exported with:

- area
- centroid
- bounding box
- mean target-band reflectance
- mean local indices
- deltas from whole-leaf average
- deltas from a nearby vegetation background ring
- severity score and rank

## Current limitations

- No AI classifier or diagnosis is included.
- Thresholds are deterministic defaults and should be tuned per dataset.
- Nearby background comparison is a simple ring around each candidate, not a
  botanically validated healthy-control selection.
- Whole-leaf averages are still exported, but localized regions are the better
  place to inspect early or uneven symptoms.
- New datasets should be added through adapters instead of patching core
  analysis modules.
