"""Vegetation masking helpers for the plant-health multispectral MVP.

The first pass is intentionally simple and explainable:

* use NDVI when both 850 nm and 680 nm bands are available
* use an explicitly labeled NDVI-like fallback when 850 nm and 650 nm are
  available but 680 nm is missing
* otherwise fall back to thresholding the highest available image-like band
* optionally clean the binary mask with pure NumPy morphology helpers

The module works on the canonical :class:`~plant_health_mvp.models.sample.SpectralSample`
container so the rest of the pipeline does not need to know the original
dataset format.
"""

from __future__ import annotations

from typing import Any

import numpy as np

from .models.sample import SpectralSample

_DEFAULT_MORPH_ITERATIONS = 1
_EPS = 1e-8


def _as_bool_mask(values: np.ndarray) -> np.ndarray:
    """Return a contiguous boolean mask array."""

    return np.asarray(values, dtype=bool)


def _image_like_band(band: Any) -> np.ndarray | None:
    """Return a 2D float array for an image-like band, or ``None`` otherwise."""

    if band is None:
        return None

    array = np.asarray(band)
    if array.ndim == 2:
        return np.asarray(array, dtype=float)
    if array.ndim == 3 and 1 in array.shape:
        squeezed = np.squeeze(array)
        if squeezed.ndim == 2:
            return np.asarray(squeezed, dtype=float)
    return None


def _available_image_like_bands(sample: SpectralSample) -> dict[str, np.ndarray]:
    """Return the image-like target bands stored on a sample."""

    image_like: dict[str, np.ndarray] = {}
    for key, band in sample.target_bands.items():
        image = _image_like_band(band)
        if image is not None:
            image_like[str(key)] = image
    return image_like


def _band_key_to_float(key: str) -> float | None:
    """Parse a target-band dictionary key into a wavelength value."""

    try:
        return float(key)
    except (TypeError, ValueError):
        return None


def _parse_band_arrays(image_like_bands: dict[str, np.ndarray]) -> list[tuple[float, str, np.ndarray]]:
    """Return image-like bands sorted by wavelength."""

    parsed: list[tuple[float, str, np.ndarray]] = []
    for key, band in image_like_bands.items():
        wavelength = _band_key_to_float(key)
        if wavelength is None:
            continue
        parsed.append((wavelength, key, band))
    parsed.sort(key=lambda item: item[0])
    return parsed


def _sort_key_for_band(key: str) -> float:
    """Sort band keys numerically when possible, otherwise place them first."""

    wavelength = _band_key_to_float(key)
    return wavelength if wavelength is not None else float("-inf")


def _binary_dilation(mask: np.ndarray, iterations: int = 1) -> np.ndarray:
    """Perform binary dilation using a 3x3 structuring element."""

    result = _as_bool_mask(mask)
    for _ in range(max(0, int(iterations))):
        padded = np.pad(result, 1, mode="constant", constant_values=False)
        neighborhoods = []
        for row_offset in range(3):
            for col_offset in range(3):
                neighborhoods.append(padded[row_offset : row_offset + result.shape[0], col_offset : col_offset + result.shape[1]])
        result = np.any(np.stack(neighborhoods, axis=0), axis=0)
    return result


def _binary_erosion(mask: np.ndarray, iterations: int = 1) -> np.ndarray:
    """Perform binary erosion using a 3x3 structuring element."""

    result = _as_bool_mask(mask)
    for _ in range(max(0, int(iterations))):
        padded = np.pad(result, 1, mode="constant", constant_values=True)
        neighborhoods = []
        for row_offset in range(3):
            for col_offset in range(3):
                neighborhoods.append(padded[row_offset : row_offset + result.shape[0], col_offset : col_offset + result.shape[1]])
        result = np.all(np.stack(neighborhoods, axis=0), axis=0)
    return result


def _binary_opening(mask: np.ndarray, iterations: int = 1) -> np.ndarray:
    """Apply erosion followed by dilation."""

    return _binary_dilation(_binary_erosion(mask, iterations=iterations), iterations=iterations)


def _binary_closing(mask: np.ndarray, iterations: int = 1) -> np.ndarray:
    """Apply dilation followed by erosion."""

    return _binary_erosion(_binary_dilation(mask, iterations=iterations), iterations=iterations)


def _cleanup_mask(mask: np.ndarray, iterations: int = _DEFAULT_MORPH_ITERATIONS) -> np.ndarray:
    """Remove isolated noise and fill small gaps in a binary mask."""

    cleaned = _binary_opening(mask, iterations=iterations)
    cleaned = _binary_closing(cleaned, iterations=iterations)
    return cleaned


def _ndvi_mask(nir: np.ndarray, red: np.ndarray, threshold: float) -> np.ndarray:
    """Compute an NDVI-based vegetation mask."""

    nir_array = np.asarray(nir, dtype=float)
    red_array = np.asarray(red, dtype=float)
    ndvi = (nir_array - red_array) / (nir_array + red_array + _EPS)
    return ndvi > float(threshold)


def _fallback_mask(band: np.ndarray, percentile: float) -> tuple[np.ndarray, float]:
    """Threshold the highest available image-like band by percentile."""

    band_array = np.asarray(band, dtype=float)
    finite_values = band_array[np.isfinite(band_array)]
    if finite_values.size == 0:
        return np.zeros_like(band_array, dtype=bool), float("nan")

    cutoff = float(np.percentile(finite_values, float(percentile)))
    return band_array > cutoff, cutoff


def _rgb_excess_green_mask(red: np.ndarray, green: np.ndarray, blue: np.ndarray, percentile: float) -> tuple[np.ndarray, float]:
    """Build an RGB-only vegetation mask from excess green."""

    red_array = np.asarray(red, dtype=float)
    green_array = np.asarray(green, dtype=float)
    blue_array = np.asarray(blue, dtype=float)
    excess_green = (2.0 * green_array) - red_array - blue_array
    finite_values = excess_green[np.isfinite(excess_green)]
    if finite_values.size == 0:
        return np.zeros_like(excess_green, dtype=bool), float("nan")
    cutoff = float(np.percentile(finite_values, float(percentile)))
    return excess_green > cutoff, cutoff


def build_vegetation_mask(
    sample: SpectralSample,
    ndvi_threshold: float = 0.2,
    fallback_percentile: float = 70.0,
    cleanup: bool = True,
) -> tuple[np.ndarray | None, dict[str, Any]]:
    """Build a vegetation mask for a spectral sample.

    The preferred path is NDVI from the 850 nm and 680 nm target bands. When
    those bands are unavailable, the function falls back to the highest
    available image-like band and thresholds it by percentile. If no usable
    image-like band is present, the function returns ``(None, metadata)``.
    """

    image_like_bands = _available_image_like_bands(sample)
    available_band_keys = sorted(image_like_bands.keys(), key=_sort_key_for_band)

    metadata: dict[str, Any] = {
        "method": None,
        "ndvi_threshold": float(ndvi_threshold),
        "fallback_percentile": float(fallback_percentile),
        "cleanup": bool(cleanup),
        "available_image_like_bands": available_band_keys,
        "used_bands": [],
        "fallback_reason": "",
        "band_shape": None,
        "vegetation_pixel_count": 0,
    }

    nir = image_like_bands.get("850")
    red = image_like_bands.get("680")
    red_fallback = image_like_bands.get("650")
    mask: np.ndarray | None = None

    if bool(sample.metadata.get("rgb_only")) and all(key in image_like_bands for key in ("650", "556", "532")):
        mask, cutoff = _rgb_excess_green_mask(
            image_like_bands["650"],
            image_like_bands["556"],
            image_like_bands["532"],
            percentile=fallback_percentile,
        )
        metadata["method"] = "rgb_excess_green"
        metadata["used_bands"] = ["532", "556", "650"]
        metadata["band_shape"] = list(mask.shape)
        metadata["rgb_expression"] = "(2 * 556) - 650 - 532"
        metadata["percentile_cutoff"] = cutoff
        metadata["fallback_reason"] = (
            "RGB-only input does not contain 850 nm and 680 nm for NDVI. "
            "Used excess-green thresholding on the approximate RGB channels."
        )
    elif nir is not None and red is not None:
        mask = _ndvi_mask(nir, red, threshold=ndvi_threshold)
        metadata["method"] = "ndvi"
        metadata["used_bands"] = ["680", "850"]
        metadata["band_shape"] = list(mask.shape)
        metadata["ndvi_expression"] = "(850 - 680) / (850 + 680 + eps)"
    elif nir is not None and red_fallback is not None:
        mask = _ndvi_mask(nir, red_fallback, threshold=ndvi_threshold)
        metadata["method"] = "ndvi_like_red_fallback"
        metadata["used_bands"] = ["650", "850"]
        metadata["band_shape"] = list(mask.shape)
        metadata["ndvi_expression"] = "(850 - 650) / (850 + 650 + eps)"
        metadata["fallback_reason"] = (
            "680 nm RED was missing. Used 650 nm RED fallback with 850 nm NIR, "
            "so this mask is NDVI-like rather than narrowband NDVI."
        )
    else:
        parsed = _parse_band_arrays(image_like_bands)
        if not parsed:
            metadata["method"] = "missing"
            metadata["fallback_reason"] = "No image-like target bands were available."
            return None, metadata

        highest_wavelength, highest_key, highest_band = parsed[-1]
        mask, cutoff = _fallback_mask(highest_band, percentile=fallback_percentile)
        metadata["method"] = "percentile_threshold"
        metadata["used_bands"] = [highest_key]
        metadata["band_shape"] = list(mask.shape)
        metadata["fallback_reason"] = (
            f"Missing one or both of 850 nm and 680 nm. Used highest available image-like band at {highest_wavelength:g} nm."
        )
        metadata["percentile_cutoff"] = cutoff

    if mask is None:
        metadata["method"] = "missing"
        metadata["fallback_reason"] = "Mask generation failed unexpectedly."
        return None, metadata

    mask = _as_bool_mask(mask)
    if cleanup:
        mask = _cleanup_mask(mask, iterations=_DEFAULT_MORPH_ITERATIONS)

    metadata["band_shape"] = list(mask.shape)
    metadata["vegetation_pixel_count"] = int(np.count_nonzero(mask))
    metadata["mask_dtype"] = str(mask.dtype)
    return mask, metadata


def apply_vegetation_mask(sample: SpectralSample, **kwargs: Any) -> SpectralSample:
    """Compute a vegetation mask and store it on the provided sample."""

    mask, metadata = build_vegetation_mask(sample, **kwargs)
    sample.mask = mask
    sample.metadata["vegetation_mask"] = metadata
    return sample
