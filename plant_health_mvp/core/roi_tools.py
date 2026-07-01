"""ROI and pixel inspection helpers."""

from __future__ import annotations

from typing import Any

import numpy as np

from .indices import compute_indices
from .models.sample import SpectralSample


def pixel_spectrum(sample: SpectralSample, x: int, y: int) -> dict[str, Any]:
    """Return the full source spectrum at one pixel."""

    if sample.data is None or sample.data.ndim != 3:
        raise ValueError("Pixel spectra require image-like cube data.")
    height, width, _ = sample.data.shape
    if x < 0 or y < 0 or x >= width or y >= height:
        raise ValueError(f"Pixel is outside image bounds: {(x, y)}")
    return {
        "x": int(x),
        "y": int(y),
        "wavelengths": np.asarray(sample.available_wavelengths, dtype=float).tolist(),
        "values": np.asarray(sample.data[y, x, :], dtype=float).tolist(),
    }


def roi_average_spectrum(sample: SpectralSample, x: int, y: int, width: int, height: int) -> dict[str, Any]:
    """Return the average full spectrum inside a rectangular ROI."""

    if sample.data is None or sample.data.ndim != 3:
        raise ValueError("ROI spectra require image-like cube data.")
    image_height, image_width, _ = sample.data.shape
    x0 = max(0, int(x))
    y0 = max(0, int(y))
    x1 = min(image_width, x0 + max(1, int(width)))
    y1 = min(image_height, y0 + max(1, int(height)))
    roi = sample.data[y0:y1, x0:x1, :]
    return {
        "bbox": [x0, y0, x1, y1],
        "pixel_count": int(roi.shape[0] * roi.shape[1]),
        "wavelengths": np.asarray(sample.available_wavelengths, dtype=float).tolist(),
        "mean_values": np.nanmean(roi.astype(float), axis=(0, 1)).tolist(),
    }


def roi_target_band_averages(
    sample: SpectralSample,
    x: int,
    y: int,
    width: int,
    height: int,
    *,
    vegetation_only: bool = False,
) -> dict[str, Any]:
    """Return target-band averages inside a rectangular ROI."""

    bbox = _clamped_bbox(sample, x, y, width, height)
    x0, y0, x1, y1 = bbox
    roi_mask = np.ones((y1 - y0, x1 - x0), dtype=bool)
    if vegetation_only and sample.mask is not None:
        roi_mask = np.asarray(sample.mask, dtype=bool)[y0:y1, x0:x1]

    averages: dict[str, float | None] = {}
    for band_key, band in sample.target_bands.items():
        if band is None:
            averages[str(band_key)] = None
            continue
        array = np.asarray(band, dtype=float)
        if array.ndim != 2:
            averages[str(band_key)] = None
            continue
        values = array[y0:y1, x0:x1][roi_mask]
        values = values[np.isfinite(values)]
        averages[str(band_key)] = None if values.size == 0 else float(np.nanmean(values))

    return {
        "bbox": bbox,
        "vegetation_only": bool(vegetation_only),
        "pixel_count": int(np.count_nonzero(roi_mask)),
        "average_bands": averages,
        "indices": compute_indices(averages),
    }


def compare_roi_to_leaf(
    sample: SpectralSample,
    x: int,
    y: int,
    width: int,
    height: int,
    leaf_average_bands: dict[str, float | None],
    *,
    vegetation_only: bool = False,
) -> dict[str, Any]:
    """Compare one rectangular ROI against whole-leaf average target bands."""

    roi = roi_target_band_averages(sample, x, y, width, height, vegetation_only=vegetation_only)
    roi_bands = roi["average_bands"]
    deltas = {
        str(key): (
            None
            if roi_bands.get(str(key)) is None or leaf_average_bands.get(str(key)) is None
            else float(roi_bands[str(key)]) - float(leaf_average_bands[str(key)])
        )
        for key in sorted(set(roi_bands) | set(leaf_average_bands), key=lambda item: float(item))
    }
    roi["delta_from_leaf_average"] = deltas
    return roi


def _clamped_bbox(sample: SpectralSample, x: int, y: int, width: int, height: int) -> list[int]:
    """Return an image-bounds-clamped ROI box as [x0, y0, x1, y1]."""

    if sample.data is None or sample.data.ndim != 3:
        raise ValueError("ROI spectra require image-like cube data.")
    image_height, image_width, _ = sample.data.shape
    x0 = max(0, int(x))
    y0 = max(0, int(y))
    x1 = min(image_width, x0 + max(1, int(width)))
    y1 = min(image_height, y0 + max(1, int(height)))
    return [x0, y0, x1, y1]


__all__ = [
    "compare_roi_to_leaf",
    "pixel_spectrum",
    "roi_average_spectrum",
    "roi_target_band_averages",
]
