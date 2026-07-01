"""Vegetation masking helpers for the plant-health multispectral MVP.

The mask path stays intentionally explainable:

* for filtered camera bundles, first find the physical foreground leaf/object
  so lamp spill and box background are not treated as vegetation
* for calibrated/hyperspectral image data, use NDVI when both 850 nm and
  680 nm bands are available
* use an explicitly labeled NDVI-like fallback when 850 nm and 650 nm are
  available but 680 nm is missing
* otherwise fall back to thresholding the highest available image-like band
* optionally clean the binary mask with pure NumPy/OpenCV morphology helpers

The module works on the canonical :class:`~plant_health_mvp.models.sample.SpectralSample`
container so the rest of the pipeline does not need to know the original
dataset format.
"""

from __future__ import annotations

import math
from typing import Any

import numpy as np

from .models.sample import SpectralSample

try:  # pragma: no cover - exercised when OpenCV is installed locally.
    import cv2  # type: ignore[import-not-found]
except ImportError:  # pragma: no cover - NumPy fallbacks keep the pipeline usable.
    cv2 = None

_DEFAULT_MORPH_ITERATIONS = 1
_EPS = 1e-8
_FOREGROUND_SOURCE_KINDS = {"filtered_camera_image", "mixed_image_data"}
_FOREGROUND_SOURCE_TYPES = {"filtered_camera_image", "mixed_image_bundle"}
_PREFERRED_FOREGROUND_BANDS = ("850", "680", "725", "940", "556", "532", "650")
_MIN_FOREGROUND_AREA_FRACTION = 0.001
_MAX_FOREGROUND_AREA_FRACTION = 0.32


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


def _prefers_foreground_mask(sample: SpectralSample) -> bool:
    """Return true when camera geometry should be segmented before NDVI."""

    source_kind = str(sample.metadata.get("source_data_kind") or "")
    source_type = str(sample.source_type or "")
    return (
        source_kind in _FOREGROUND_SOURCE_KINDS
        or source_type in _FOREGROUND_SOURCE_TYPES
        or bool(sample.metadata.get("camera_calibration_eligible"))
    )


def _robust_normalize_band(band: np.ndarray) -> np.ndarray:
    """Scale a camera band to 0..1 without letting hot pixels dominate."""

    band_array = np.asarray(band, dtype=float)
    finite_values = band_array[np.isfinite(band_array)]
    if finite_values.size == 0:
        return np.zeros_like(band_array, dtype=float)

    low, high = np.percentile(finite_values, [1.0, 99.5])
    if not math.isfinite(float(low)) or not math.isfinite(float(high)) or high - low <= _EPS:
        low = float(np.min(finite_values))
        high = float(np.max(finite_values))
    if high - low <= _EPS:
        return np.zeros_like(band_array, dtype=float)

    normalized = (band_array - float(low)) / (float(high) - float(low))
    normalized = np.nan_to_num(normalized, nan=0.0, posinf=1.0, neginf=0.0)
    return np.clip(normalized, 0.0, 1.0)


def _otsu_cutoff(score: np.ndarray) -> float:
    """Return an Otsu threshold for a 0..1 score image."""

    score_array = np.clip(np.asarray(score, dtype=float), 0.0, 1.0)
    finite_values = score_array[np.isfinite(score_array)]
    if finite_values.size == 0:
        return float("nan")
    if float(np.max(finite_values) - np.min(finite_values)) <= _EPS:
        return float(np.mean(finite_values))

    if cv2 is not None:
        score_uint8 = np.nan_to_num(score_array * 255.0, nan=0.0, posinf=255.0, neginf=0.0).astype(np.uint8)
        cutoff, _ = cv2.threshold(score_uint8, 0, 255, cv2.THRESH_BINARY + cv2.THRESH_OTSU)
        return float(cutoff) / 255.0

    histogram, edges = np.histogram(finite_values, bins=256, range=(0.0, 1.0))
    total = int(histogram.sum())
    if total <= 0:
        return float("nan")

    centers = (edges[:-1] + edges[1:]) / 2.0
    weight_background = np.cumsum(histogram, dtype=float)
    weight_foreground = float(total) - weight_background
    moment_background = np.cumsum(histogram * centers, dtype=float)
    total_moment = float(moment_background[-1])

    valid = (weight_background > 0.0) & (weight_foreground > 0.0)
    variance = np.zeros_like(centers, dtype=float)
    mean_background = np.zeros_like(centers, dtype=float)
    mean_foreground = np.zeros_like(centers, dtype=float)
    mean_background[valid] = moment_background[valid] / weight_background[valid]
    mean_foreground[valid] = (total_moment - moment_background[valid]) / weight_foreground[valid]
    variance[valid] = weight_background[valid] * weight_foreground[valid] * (mean_background[valid] - mean_foreground[valid]) ** 2
    return float(centers[int(np.argmax(variance))])


def _threshold_score(score: np.ndarray, strategy: str) -> tuple[np.ndarray, float]:
    """Threshold a foreground score by Otsu or by a named percentile strategy."""

    score_array = np.clip(np.asarray(score, dtype=float), 0.0, 1.0)
    finite_values = score_array[np.isfinite(score_array)]
    if finite_values.size == 0:
        return np.zeros_like(score_array, dtype=bool), float("nan")

    if strategy == "otsu":
        cutoff = _otsu_cutoff(score_array)
    elif strategy.startswith("percentile_"):
        cutoff = float(np.percentile(finite_values, float(strategy.rsplit("_", 1)[-1])))
    else:
        raise ValueError(f"Unknown foreground threshold strategy: {strategy}")

    if not math.isfinite(float(cutoff)):
        return np.zeros_like(score_array, dtype=bool), float("nan")
    return score_array > float(cutoff), float(cutoff)


def _odd_kernel_size(shape: tuple[int, ...], fraction: float, minimum: int, maximum: int) -> int:
    """Choose a stable odd morphology kernel size for the image shape."""

    if not shape:
        return minimum
    base = int(round(float(min(shape[:2])) * float(fraction)))
    base = max(int(minimum), min(int(maximum), base))
    if base % 2 == 0:
        base += 1
    return max(3, base)


def _fill_holes_cv2(mask: np.ndarray) -> np.ndarray:
    """Fill closed holes in a binary mask with OpenCV flood fill."""

    mask_bool = _as_bool_mask(mask)
    if cv2 is None or not np.any(mask_bool):
        return mask_bool

    padded = np.pad(mask_bool, 1, mode="constant", constant_values=False)
    inverse = (~padded).astype(np.uint8) * 255
    flood = inverse.copy()
    flood_mask = np.zeros((flood.shape[0] + 2, flood.shape[1] + 2), dtype=np.uint8)
    cv2.floodFill(flood, flood_mask, (0, 0), 0)
    holes = flood == 255
    filled = padded | holes
    return filled[1:-1, 1:-1]


def _cleanup_foreground_mask(mask: np.ndarray) -> np.ndarray:
    """Use stronger morphology for real camera foreground masks."""

    mask_bool = _as_bool_mask(mask)
    if not np.any(mask_bool):
        return mask_bool

    if cv2 is None:
        return _cleanup_mask(mask_bool, iterations=2)

    open_size = _odd_kernel_size(mask_bool.shape, fraction=0.003, minimum=5, maximum=11)
    close_size = _odd_kernel_size(mask_bool.shape, fraction=0.009, minimum=11, maximum=31)
    opened_kernel = cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (open_size, open_size))
    closed_kernel = cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (close_size, close_size))
    mask_uint8 = mask_bool.astype(np.uint8) * 255
    cleaned = cv2.morphologyEx(mask_uint8, cv2.MORPH_OPEN, opened_kernel)
    cleaned = cv2.morphologyEx(cleaned, cv2.MORPH_CLOSE, closed_kernel)
    return _fill_holes_cv2(cleaned > 0)


def _component_selection_score(
    area_fraction: float,
    fill_ratio: float,
    centroid: tuple[float, float],
    shape: tuple[int, int],
    touches_edge: bool,
) -> float:
    """Rank foreground components by plausible leaf/object geometry."""

    height, width = shape
    ideal_fraction = 0.055
    size_score = 1.0 - min(abs(math.log((area_fraction + _EPS) / ideal_fraction)) / math.log(12.0), 1.0)
    center_distance = math.hypot(centroid[0] - (width / 2.0), centroid[1] - (height / 2.0))
    max_distance = max(math.hypot(width / 2.0, height / 2.0), _EPS)
    centrality = 1.0 - min(center_distance / max_distance, 1.0)
    solidity_like = min(max(fill_ratio, 0.0) / 0.55, 1.0)
    area_presence = min(area_fraction / 0.03, 1.0)
    score = (0.45 * size_score) + (0.25 * centrality) + (0.20 * solidity_like) + (0.10 * area_presence)
    if touches_edge:
        score -= 0.35
    return float(score)


def _select_foreground_component(mask: np.ndarray) -> tuple[np.ndarray | None, dict[str, Any]]:
    """Keep the best connected foreground component and reject light spill."""

    mask_bool = _as_bool_mask(mask)
    height, width = mask_bool.shape
    total_pixels = max(1, int(mask_bool.size))

    if not np.any(mask_bool):
        return None, {"reason": "empty_threshold_mask", "components_considered": 0}

    if cv2 is None:
        area = int(np.count_nonzero(mask_bool))
        area_fraction = float(area / total_pixels)
        if _MIN_FOREGROUND_AREA_FRACTION <= area_fraction <= _MAX_FOREGROUND_AREA_FRACTION:
            return mask_bool, {
                "reason": "opencv_unavailable_used_whole_mask",
                "components_considered": 1,
                "component_area": area,
                "area_fraction": area_fraction,
            }
        return None, {
            "reason": "opencv_unavailable_mask_area_out_of_range",
            "components_considered": 1,
            "component_area": area,
            "area_fraction": area_fraction,
        }

    labels_count, labels, stats, centroids = cv2.connectedComponentsWithStats(mask_bool.astype(np.uint8), connectivity=8)
    candidates: list[dict[str, Any]] = []
    rejected: list[dict[str, Any]] = []

    for label in range(1, labels_count):
        x = int(stats[label, cv2.CC_STAT_LEFT])
        y = int(stats[label, cv2.CC_STAT_TOP])
        component_width = int(stats[label, cv2.CC_STAT_WIDTH])
        component_height = int(stats[label, cv2.CC_STAT_HEIGHT])
        area = int(stats[label, cv2.CC_STAT_AREA])
        area_fraction = float(area / total_pixels)
        bbox_area = max(1, component_width * component_height)
        fill_ratio = float(area / bbox_area)
        centroid = (float(centroids[label][0]), float(centroids[label][1]))
        touches_edge = bool(x <= 1 or y <= 1 or x + component_width >= width - 1 or y + component_height >= height - 1)
        record = {
            "label": int(label),
            "bbox": [x, y, component_width, component_height],
            "component_area": area,
            "area_fraction": area_fraction,
            "fill_ratio": fill_ratio,
            "centroid": [centroid[0], centroid[1]],
            "touches_edge": touches_edge,
        }

        if area_fraction < _MIN_FOREGROUND_AREA_FRACTION:
            record["reject_reason"] = "too_small"
            rejected.append(record)
            continue
        if area_fraction > _MAX_FOREGROUND_AREA_FRACTION:
            record["reject_reason"] = "too_large_for_single_leaf"
            rejected.append(record)
            continue

        record["selection_score"] = _component_selection_score(
            area_fraction=area_fraction,
            fill_ratio=fill_ratio,
            centroid=centroid,
            shape=(height, width),
            touches_edge=touches_edge,
        )
        candidates.append(record)

    if not candidates:
        return None, {
            "reason": "no_component_in_expected_leaf_area_range",
            "components_considered": int(max(0, labels_count - 1)),
            "rejected_components": rejected[:6],
        }

    best = max(candidates, key=lambda item: float(item["selection_score"]))
    component_mask = labels == int(best["label"])
    component_mask = _fill_holes_cv2(component_mask)
    return component_mask, {
        "reason": "selected_best_component",
        "components_considered": int(max(0, labels_count - 1)),
        "selected_component": {key: value for key, value in best.items() if key != "label"},
        "rejected_components": rejected[:6],
    }


def _foreground_score_candidates(image_like_bands: dict[str, np.ndarray]) -> list[tuple[str, list[str], np.ndarray, float]]:
    """Build foreground score candidates from real filtered camera bands."""

    candidates: list[tuple[str, list[str], np.ndarray, float]] = []
    seen_keys: set[str] = set()
    for order, key in enumerate(_PREFERRED_FOREGROUND_BANDS):
        band = image_like_bands.get(key)
        if band is None:
            continue
        seen_keys.add(key)
        priority = max(0.0, 1.0 - (0.04 * order))
        candidates.append((f"{key}_nm_intensity", [key], _robust_normalize_band(band), priority))

    parsed = _parse_band_arrays(image_like_bands)
    normalized_bands = []
    normalized_keys = []
    for _, key, band in parsed:
        if key not in seen_keys:
            seen_keys.add(key)
        normalized_bands.append(_robust_normalize_band(band))
        normalized_keys.append(key)

    if len(normalized_bands) >= 2:
        stack = np.stack(normalized_bands, axis=0)
        candidates.append(("multi_band_max_intensity", list(normalized_keys), np.max(stack, axis=0), 0.72))
        candidates.append(("multi_band_mean_intensity", list(normalized_keys), np.mean(stack, axis=0), 0.68))

    return candidates


def _foreground_candidate_from_score(
    score_name: str,
    used_bands: list[str],
    score: np.ndarray,
    threshold_strategy: str,
    priority: float,
    cleanup: bool,
) -> tuple[np.ndarray, dict[str, Any]] | None:
    """Create and score one foreground-mask candidate."""

    raw_mask, cutoff = _threshold_score(score, threshold_strategy)
    if not np.any(raw_mask):
        return None

    candidate_mask = _cleanup_foreground_mask(raw_mask) if cleanup else _as_bool_mask(raw_mask)
    component_mask, component_metadata = _select_foreground_component(candidate_mask)
    if component_mask is None:
        return None

    final_mask = _cleanup_foreground_mask(component_mask) if cleanup else _as_bool_mask(component_mask)
    final_pixels = int(np.count_nonzero(final_mask))
    final_area_fraction = float(final_pixels / max(1, final_mask.size))
    component_score = float(
        component_metadata.get("selected_component", {}).get("selection_score", 0.0)
        if isinstance(component_metadata.get("selected_component"), dict)
        else 0.0
    )
    quality_score = component_score + (0.18 * priority)

    return final_mask, {
        "score_name": score_name,
        "used_bands": used_bands,
        "threshold_strategy": threshold_strategy,
        "threshold_cutoff_normalized": cutoff,
        "component_selection": component_metadata,
        "vegetation_pixel_count": final_pixels,
        "area_fraction": final_area_fraction,
        "quality_score": quality_score,
    }


def _filtered_camera_foreground_mask(
    image_like_bands: dict[str, np.ndarray],
    cleanup: bool,
) -> tuple[np.ndarray | None, dict[str, Any]]:
    """Find the actual leaf foreground in filtered camera images."""

    candidates: list[tuple[np.ndarray, dict[str, Any]]] = []
    attempts: list[dict[str, Any]] = []
    for score_name, used_bands, score, priority in _foreground_score_candidates(image_like_bands):
        for threshold_strategy in ("otsu", "percentile_90", "percentile_95"):
            candidate = _foreground_candidate_from_score(
                score_name=score_name,
                used_bands=used_bands,
                score=score,
                threshold_strategy=threshold_strategy,
                priority=priority,
                cleanup=cleanup,
            )
            if candidate is None:
                attempts.append(
                    {
                        "score_name": score_name,
                        "used_bands": used_bands,
                        "threshold_strategy": threshold_strategy,
                        "status": "rejected",
                    }
                )
                continue
            candidates.append(candidate)
            attempts.append(
                {
                    "score_name": score_name,
                    "used_bands": used_bands,
                    "threshold_strategy": threshold_strategy,
                    "status": "accepted",
                    "area_fraction": candidate[1]["area_fraction"],
                    "quality_score": candidate[1]["quality_score"],
                }
            )

    if not candidates:
        return None, {
            "method": "filtered_camera_foreground",
            "fallback_reason": (
                "Foreground segmentation could not isolate one plausible leaf component; "
                "falling back to spectral threshold logic."
            ),
            "foreground_attempts": attempts[:12],
        }

    mask, best = max(candidates, key=lambda item: float(item[1]["quality_score"]))
    return mask, {
        "method": "filtered_camera_foreground",
        "used_bands": best["used_bands"],
        "foreground_score": best["score_name"],
        "threshold_strategy": best["threshold_strategy"],
        "threshold_cutoff_normalized": best["threshold_cutoff_normalized"],
        "component_selection": best["component_selection"],
        "foreground_candidate_count": len(candidates),
        "foreground_attempts": attempts[:12],
        "fallback_reason": (
            "Filtered camera image data was segmented as a foreground object first. "
            "This avoids selecting lamp spill or the inside of the box as vegetation."
        ),
    }


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

    For real filtered camera images, the preferred path is foreground-object
    segmentation because the box light can produce high NDVI-like contrast in
    the background. For other image-like data, the preferred path is NDVI from
    the 850 nm and 680 nm target bands. When those bands are unavailable, the
    function falls back to the highest available image-like band and thresholds
    it by percentile. If no usable image-like band is present, the function
    returns ``(None, metadata)``.
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
    mask_already_cleaned = False

    if _prefers_foreground_mask(sample):
        mask, foreground_metadata = _filtered_camera_foreground_mask(image_like_bands, cleanup=cleanup)
        metadata.update(foreground_metadata)
        if mask is not None:
            metadata["band_shape"] = list(mask.shape)
            mask_already_cleaned = bool(cleanup)

    if mask is None and bool(sample.metadata.get("rgb_only")) and all(key in image_like_bands for key in ("650", "556", "532")):
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
    elif mask is None and nir is not None and red is not None:
        mask = _ndvi_mask(nir, red, threshold=ndvi_threshold)
        metadata["method"] = "ndvi"
        metadata["used_bands"] = ["680", "850"]
        metadata["band_shape"] = list(mask.shape)
        metadata["ndvi_expression"] = "(850 - 680) / (850 + 680 + eps)"
    elif mask is None and nir is not None and red_fallback is not None:
        mask = _ndvi_mask(nir, red_fallback, threshold=ndvi_threshold)
        metadata["method"] = "ndvi_like_red_fallback"
        metadata["used_bands"] = ["650", "850"]
        metadata["band_shape"] = list(mask.shape)
        metadata["ndvi_expression"] = "(850 - 650) / (850 + 650 + eps)"
        metadata["fallback_reason"] = (
            "680 nm RED was missing. Used 650 nm RED fallback with 850 nm NIR, "
            "so this mask is NDVI-like rather than narrowband NDVI."
        )
    elif mask is None:
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
    if cleanup and not mask_already_cleaned:
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
