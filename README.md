# FANSOR SPEDITION Website

Static bilingual website for FANSOR SPEDITION, a Suceava-based road freight transport company.

## Structure

- `ro/` Romanian pages
- `en/` English pages
- `styles.css` shared styles
- `script.js` shared navigation, language switcher, contact placeholders, and form demo logic
- `assets/` shared visuals and brand assets

Romanian is the default language. The root `index.html` redirects to `ro/index.html`, which also makes the project work cleanly on GitHub Pages.

## Local preview

Open the project with Live Server or run a simple static server:

```bash
python -m http.server 4173
```

Then visit:

- `http://127.0.0.1:4173/`
- `http://127.0.0.1:4173/ro/index.html`
- `http://127.0.0.1:4173/en/index.html`

## Hyperspectral Explorer

This repository also includes a local Python desktop explorer for ENVI
hyperspectral plant-health datasets.

Install the viewer dependencies:

```bash
python -m pip install -r hyperspectral_viewer_requirements.txt
```

Launch it from the repository root:

```bash
python viewer.py
```

The explorer can open a dataset root, an extracted sample folder, or a direct
`feuille...hdr` file. It loads samples through the adapter layer, ignores
`._*` macOS artifact files, and uses `wave_lengths.csv` when supplied.

In the GUI you can:

- browse all source bands and target wavelengths
- switch between raw, dark, white, and calibrated reflectance views
- inspect grayscale, false-color vegetation, and RGB-like composites
- click pixels and compare ROI A / ROI B spectra
- run vegetation and suspicious-region debugging overlays
- inspect NDVI, NDRE, GNDVI, CI_RE, water proxy, and raw index components
- diagnose edge bands, low dynamic range, and possible striping
- export displayed images, spectra, reports, and suspicious-region tables

Calibration uses the core analysis function and applies:

```text
reflectance = (raw - dark) / (white - dark)
```

Display stretching, histogram equalization, and destriping previews are
display-only; they do not alter the scientific values used for spectra,
indices, ROI averages, or exports.

See `HYPERSPECTRAL_VIEWER.md` and `plant_health_mvp/README.md` for more detail.

## GitHub Pages

This repo is prepared for project-site hosting from the repository root.

Expected public URL:

`https://david8986.github.io/Project-site/`

Notes:

- the root entry redirects to the Romanian homepage
- all page links are relative, so the site also works from a subfolder
- the language switcher preserves the current filename between `ro/` and `en/`

## Contact placeholders

Replace the placeholder phone, email, address, and business-hours values in `script.js` after the client confirms the final public contact pack.
