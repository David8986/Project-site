"""Spectrum aggregation helpers for the plant-health MVP.

The functions in this module operate on the canonical ``SpectralSample``
container so the rest of the pipeline can stay agnostic to the original
dataset format.
"""

from __future__ import annotations

from typing import Any

import numpy as np

from .models.sample import SpectralSample


def count_vegetation_pixels(mask: np.ndarray | None) -> int:
    """Count vegetation pixels in a mask.

    A non-zero mask value is treated as vegetation. Non-array inputs and empty
    arrays return ``0``.
    """

    if mask is None:
        return 0

    mask_array = np.asarray(mask)
    if mask_array.size == 0:
        return 0

    return int(np.count_nonzero(mask_array))


def _band_is_image_like(band_data: Any, mask: np.ndarray | None) -> bool:
    """Return ``True`` when a band can be indexed like a 2D image."""

    if not isinstance(band_data, np.ndarray):
        return False
    if band_data.ndim != 2:
        return False
    if mask is None:
        return True
    mask_array = np.asarray(mask)
    return mask_array.ndim == 2 and mask_array.shape == band_data.shape


def _mean_from_masked_band(band_data: np.ndarray, mask: np.ndarray) -> float | None:
    """Compute the mean reflectance over vegetation pixels."""

    vegetation_pixels = np.asarray(mask) != 0
    if vegetation_pixels.shape != band_data.shape:
        return None
    if not np.any(vegetation_pixels):
        return None

    values = np.asarray(band_data, dtype=float)[vegetation_pixels]
    if values.size == 0:
        return None
    return float(np.nanmean(values))


def compute_average_spectrum(sample: SpectralSample) -> tuple[dict[str, float | None], dict[str, Any]]:
    """Compute the average target-band spectrum for a sample.

    Only bands present in ``sample.target_bands`` are considered. When a mask is
    available and it matches a 2D band image, the average is computed over
    vegetation pixels only. If no usable mask exists, the full band is averaged
    and the metadata records that fallback.
    """

    averages: dict[str, float | None] = {}
    metadata: dict[str, Any] = {
        "source_type": sample.source_type,
        "mask_used": False,
        "mask_shape": None if sample.mask is None else list(np.asarray(sample.mask).shape),
        "mask_strategy": "none",
        "per_band": {},
    }

    vegetation_pixels = count_vegetation_pixels(sample.mask)
    metadata["vegetation_pixel_count"] = vegetation_pixels

    if vegetation_pixels == 0 and sample.mask is not None:
        metadata["mask_strategy"] = "vegetation_mask_present_but_empty"
        metadata["note"] = "Mask contained no vegetation pixels; all target-band averages are None."
        for band_key, band_data in sample.target_bands.items():
            if band_data is not None:
                averages[str(band_key)] = None
                metadata["per_band"][str(band_key)] = {
                    "used_mask": False,
                    "reason": "no_vegetation_pixels",
                }
        return averages, metadata

    mask_array = None if sample.mask is None else np.asarray(sample.mask)

    if mask_array is not None and mask_array.ndim == 2:
        metadata["mask_used"] = True
        metadata["mask_strategy"] = "vegetation_only_for_matching_2d_bands"

    for band_key, band_data in sample.target_bands.items():
        key = str(band_key)
        if band_data is None:
            continue

        band_array = np.asarray(band_data)
        if _band_is_image_like(band_array, mask_array):
            if mask_array is not None:
                mean_value = _mean_from_masked_band(band_array, mask_array)
                if mean_value is None:
                    if vegetation_pixels == 0:
                        averages[key] = None
                        metadata["per_band"][key] = {
                            "used_mask": True,
                            "reason": "no_vegetation_pixels",
                        }
                        continue
                    averages[key] = float(np.nanmean(band_array.astype(float)))
                    metadata["per_band"][key] = {
                        "used_mask": False,
                        "reason": "mask_shape_mismatch_or_empty_selection",
                    }
                    continue

                averages[key] = mean_value
                metadata["per_band"][key] = {
                    "used_mask": True,
                    "reason": "vegetation_pixels_only",
                }
                continue

            averages[key] = float(np.nanmean(band_array.astype(float)))
            metadata["per_band"][key] = {
                "used_mask": False,
                "reason": "no_mask_available",
            }
            continue

        if band_array.size == 0:
            averages[key] = None
            metadata["per_band"][key] = {
                "used_mask": False,
                "reason": "empty_band",
            }
            continue

        averages[key] = float(np.nanmean(band_array.astype(float)))
        metadata["per_band"][key] = {
            "used_mask": False,
            "reason": "non_image_like_or_shape_mismatch",
        }

    return averages, metadata
