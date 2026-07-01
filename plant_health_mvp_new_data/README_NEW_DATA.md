# Plant Health MVP - New Data Copy

This is a copied version of the picture-analysis app. The original
`plant_health_mvp` folder was left unchanged.

What is different here:

- Reports now include a `validation_profile` section based on the real
  camera/spectrometer analysis.
- Filter-named photos such as `532.jpg`, `680.jpg`, `850.jpg`, and `940.jpg`
  are loaded as real one-band camera measurements instead of ordinary RGB
  photos.
- Reports now include a `camera_calibration` section and a
  `camera_calibration.csv` file with white-reference-corrected camera values,
  validated spectrometer-window estimates, and the model used for each band.
- The stronger calibration is trained from the app's own leaf-mask band
  averages, not from a separate brightness script. Spectrometer targets use a
  robust median inside a +/-10 nm window around each filter.
- Full filter sets use guarded multiband ridge regression when leave-one-leaf-
  out validation beats the baseline. Bands that do not validate fall back to a
  safer single-band model instead of overfitting.
- The analysis GUI has a `Validare camera` tab that explains how the current
  image should be interpreted against the real measurements and shows the
  calibration correction.
- The default output folder is `plant_health_mvp_new_data/runs/...` so it does
  not overwrite outputs from the original app.
- The bundled validation data lives in `data/real_validation`.

Run the copied analysis app from the project root:

```bat
PLANT_HEALTH_ANALYSIS_NEW_DATA.bat
```

Or directly:

```bat
python -m plant_health_mvp_new_data.analysis_app.main
```

For a single image:

```bat
python -m plant_health_mvp_new_data.main --input "C:\path\to\leaf_photo.jpg" --output "plant_health_mvp_new_data\runs\my_photo"
```

The app still treats RGB-only photos carefully: they are useful for masking,
visible color features, and visual overlays, but they are not true NIR or
red-edge measurements unless you also import separate filtered/NIR images.

For the current dataset, the camera dark reference is recorded but guarded:
it is not subtracted when it would create non-physical negative reflectance.
The primary correction is therefore white-reference normalization plus a
validated regression/single-band model derived from the matched real
measurements.
