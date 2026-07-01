# Spectrometer vs Photo Comparison

Dataset: `C:\Users\david\OneDrive\Desktop\Archive\Misc\Review Folders\New folder (6)`

Generated:

- `photo_color_metrics.csv`: color features from the normal camera photos.
- `photo_color_indices.png`: quick visual comparison of photo groups.
- `spectrometer_file_catalog.csv`: inferred labels from `.ocv` file names.

Counts:

- Photos analyzed: 14
- `.ocv` spectrometer containers cataloged: 50
- Exported spectrum CSV files analyzed: 0

No exported spectrum CSV folder was provided yet.

To compare spectrometer curves with photos, export the OceanView measurements as
CSV/TXT first. A useful export has at least two numeric columns:

```text
wavelength_nm,intensity
400.12,123.4
400.50,124.8
```

Then run:

```powershell
python tools/compare_spectrometer_photos.py --spectra-csv-dir "C:\path\to\exported\spectra"
```

The script will add:

- `exported_spectrum_features.csv`
- `exported_spectra_overlay.png`
- `camera_vs_spectrum_template.csv`
