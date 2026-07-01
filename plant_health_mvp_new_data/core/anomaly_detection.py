"""Localized suspicious spot and lesion-candidate detection.

This is not a disease classifier. It builds deterministic, explainable
candidate masks from spectral index maps, band-difference maps, local anomaly
scores, and connected components inside the vegetation mask.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Mapping

import numpy as np

from .indices import compute_indices
from .models.sample import SpectralSample
from .semantic_roles import BandRole, resolve_semantic_roles, role_band_array

EPSILON = 1e-8


@dataclass(frozen=True, slots=True)
class SpotDetectionConfig:
    """Configuration for deterministic suspicious spot detection."""

    score_threshold: float = 0.55
    min_area_px: int = 20
    morphology_iterations: int = 1
    texture_window: int = 5
    weights: Mapping[str, float] | None = None

    def resolved_weights(self) -> dict[str, float]:
        """Return default weights plus any caller overrides."""

        defaults = {
            "low_ndvi": 1.0,
            "low_ndre": 1.0,
            "low_gndvi": 0.8,
            "low_nir_red_diff": 0.7,
            "low_rededge_red_diff": 0.7,
            "low_nir_water_diff": 0.4,
            "low_rgb_excess_green": 0.8,
            "low_green_red_diff": 0.6,
            "low_green_blue_diff": 0.4,
            "texture_680": 0.5,
            "texture_725": 0.5,
            "texture_850": 0.4,
        }
        if self.weights:
            defaults.update({key: float(value) for key, value in self.weights.items()})
        return defaults


def _safe_divide(numerator: np.ndarray, denominator: np.ndarray) -> np.ndarray:
    """Safely divide arrays and return finite values only."""

    result = numerator / (denominator + EPSILON)
    return np.where(np.isfinite(result), result, 0.0)


def _valid_values(values: np.ndarray, mask: np.ndarray) -> np.ndarray:
    """Return finite values inside the vegetation mask."""

    selected = np.asarray(values, dtype=float)[mask]
    return selected[np.isfinite(selected)]


def _z_anomaly(values: np.ndarray, mask: np.ndarray, direction: str) -> np.ndarray:
    """Return a 0..1 anomaly map from whole-leaf z scores."""

    selected = _valid_values(values, mask)
    if selected.size == 0:
        return np.zeros_like(values, dtype=float)
    mean = float(np.nanmean(selected))
    std = float(np.nanstd(selected))
    if std <= EPSILON:
        return np.zeros_like(values, dtype=float)
    if direction == "low":
        z_values = (mean - values) / std
    else:
        z_values = (values - mean) / std
    return np.clip(z_values / 3.0, 0.0, 1.0) * mask


def _local_mean(values: np.ndarray, window: int) -> np.ndarray:
    """Compute a simple box-filter mean using NumPy shifts."""

    radius = max(1, int(window) // 2)
    padded = np.pad(values, radius, mode="reflect")
    total = np.zeros_like(values, dtype=float)
    count = 0
    for row_offset in range(2 * radius + 1):
        for col_offset in range(2 * radius + 1):
            total += padded[row_offset : row_offset + values.shape[0], col_offset : col_offset + values.shape[1]]
            count += 1
    return total / float(count)


def _local_std(values: np.ndarray, window: int) -> np.ndarray:
    """Compute local standard deviation in a square window."""

    values_float = np.asarray(values, dtype=float)
    mean = _local_mean(values_float, window)
    mean_sq = _local_mean(values_float * values_float, window)
    variance = np.maximum(mean_sq - mean * mean, 0.0)
    return np.sqrt(variance)


def _binary_dilation(mask: np.ndarray, iterations: int) -> np.ndarray:
    """Dilate a binary mask with a 3x3 structuring element."""

    result = np.asarray(mask, dtype=bool)
    for _ in range(max(0, int(iterations))):
        padded = np.pad(result, 1, mode="constant", constant_values=False)
        stack = [
            padded[row : row + result.shape[0], col : col + result.shape[1]]
            for row in range(3)
            for col in range(3)
        ]
        result = np.any(np.stack(stack, axis=0), axis=0)
    return result


def _binary_erosion(mask: np.ndarray, iterations: int) -> np.ndarray:
    """Erode a binary mask with a 3x3 structuring element."""

    result = np.asarray(mask, dtype=bool)
    for _ in range(max(0, int(iterations))):
        padded = np.pad(result, 1, mode="constant", constant_values=True)
        stack = [
            padded[row : row + result.shape[0], col : col + result.shape[1]]
            for row in range(3)
            for col in range(3)
        ]
        result = np.all(np.stack(stack, axis=0), axis=0)
    return result


def _cleanup_mask(mask: np.ndarray, iterations: int) -> np.ndarray:
    """Open and close a binary mask to remove small speckles and fill gaps."""

    opened = _binary_dilation(_binary_erosion(mask, iterations), iterations)
    return _binary_erosion(_binary_dilation(opened, iterations), iterations)


def _connected_components(mask: np.ndarray) -> tuple[np.ndarray, list[dict[str, Any]]]:
    """Label connected components in a binary mask using 8-connectivity."""

    binary = np.asarray(mask, dtype=bool)
    labels = np.zeros(binary.shape, dtype=np.int32)
    components: list[dict[str, Any]] = []
    next_label = 1

    for start_y, start_x in zip(*np.nonzero(binary)):
        if labels[start_y, start_x] != 0:
            continue
        stack = [(int(start_y), int(start_x))]
        labels[start_y, start_x] = next_label
        pixels: list[tuple[int, int]] = []
        while stack:
            y, x = stack.pop()
            pixels.append((y, x))
            for dy in (-1, 0, 1):
                for dx in (-1, 0, 1):
                    if dy == 0 and dx == 0:
                        continue
                    ny = y + dy
                    nx = x + dx
                    if ny < 0 or nx < 0 or ny >= binary.shape[0] or nx >= binary.shape[1]:
                        continue
                    if binary[ny, nx] and labels[ny, nx] == 0:
                        labels[ny, nx] = next_label
                        stack.append((ny, nx))

        coords = np.asarray(pixels, dtype=int)
        ys = coords[:, 0]
        xs = coords[:, 1]
        components.append(
            {
                "label": next_label,
                "area_px": int(coords.shape[0]),
                "bbox": [int(xs.min()), int(ys.min()), int(xs.max()), int(ys.max())],
                "centroid": [float(xs.mean()), float(ys.mean())],
            }
        )
        next_label += 1

    return labels, components


def _mean_in_mask(values: np.ndarray | None, mask: np.ndarray) -> float | None:
    """Return a masked mean for one band or map."""

    if values is None:
        return None
    selected = np.asarray(values, dtype=float)[mask]
    selected = selected[np.isfinite(selected)]
    if selected.size == 0:
        return None
    return float(np.nanmean(selected))


def _index_maps(bands: Mapping[str, np.ndarray | None]) -> dict[str, np.ndarray]:
    """Build available per-pixel index and band-difference maps."""

    maps: dict[str, np.ndarray] = {}
    nir = bands.get("NIR")
    red = bands.get("RED")
    red_edge = bands.get("RED_EDGE")
    green = bands.get("GREEN")
    water = bands.get("WATER_BAND")

    if nir is not None and red is not None:
        maps["NDVI"] = _safe_divide(nir - red, nir + red)
        maps["NIR_RED_DIFF"] = nir - red
    if nir is not None and red_edge is not None:
        maps["NDRE"] = _safe_divide(nir - red_edge, nir + red_edge)
        maps["NIR_RE_DIFF"] = nir - red_edge
    if nir is not None and green is not None:
        maps["GNDVI"] = _safe_divide(nir - green, nir + green)
    if red_edge is not None and red is not None:
        maps["RE_RED_DIFF"] = red_edge - red
    if nir is not None and water is not None:
        maps["NDWI_850_940"] = _safe_divide(nir - water, nir + water)
        maps["NIR_WATER_DIFF"] = nir - water
    return maps


def detect_suspicious_spots(
    sample: SpectralSample,
    roles: Mapping[str, BandRole] | None = None,
    config: SpotDetectionConfig | None = None,
) -> dict[str, Any]:
    """Detect localized suspicious spot candidates inside the vegetation mask."""

    if sample.mask is None:
        raise ValueError("Spot detection requires a vegetation mask.")
    mask = np.asarray(sample.mask, dtype=bool)
    if not mask.any():
        return _empty_result(config or SpotDetectionConfig(), "vegetation mask is empty")

    resolved_roles = dict(roles or resolve_semantic_roles(sample))
    bands = {role: role_band_array(sample, resolved_roles, role) for role in resolved_roles}
    maps = _index_maps(bands)
    cfg = config or SpotDetectionConfig()
    weights = cfg.resolved_weights()

    anomaly_maps: dict[str, np.ndarray] = {}
    if "NDVI" in maps:
        anomaly_maps["low_ndvi"] = _z_anomaly(maps["NDVI"], mask, "low")
    if "NDRE" in maps:
        anomaly_maps["low_ndre"] = _z_anomaly(maps["NDRE"], mask, "low")
    if "GNDVI" in maps:
        anomaly_maps["low_gndvi"] = _z_anomaly(maps["GNDVI"], mask, "low")
    if "NIR_RED_DIFF" in maps:
        anomaly_maps["low_nir_red_diff"] = _z_anomaly(maps["NIR_RED_DIFF"], mask, "low")
    if "RE_RED_DIFF" in maps:
        anomaly_maps["low_rededge_red_diff"] = _z_anomaly(maps["RE_RED_DIFF"], mask, "low")
    if "NIR_WATER_DIFF" in maps:
        anomaly_maps["low_nir_water_diff"] = _z_anomaly(maps["NIR_WATER_DIFF"], mask, "low")
    red_band = sample.target_bands.get("650")
    green_band = sample.target_bands.get("556")
    blue_band = sample.target_bands.get("532")
    has_rgb_channels = red_band is not None and green_band is not None and blue_band is not None
    if bool(sample.metadata.get("rgb_only")) or has_rgb_channels:
        if red_band is not None and green_band is not None:
            red_array = np.asarray(red_band, dtype=float)
            green_array = np.asarray(green_band, dtype=float)
            anomaly_maps["low_green_red_diff"] = _z_anomaly(green_array - red_array, mask, "low")
        if blue_band is not None and green_band is not None:
            blue_array = np.asarray(blue_band, dtype=float)
            green_array = np.asarray(green_band, dtype=float)
            anomaly_maps["low_green_blue_diff"] = _z_anomaly(green_array - blue_array, mask, "low")
        if red_band is not None and green_band is not None and blue_band is not None:
            red_array = np.asarray(red_band, dtype=float)
            green_array = np.asarray(green_band, dtype=float)
            blue_array = np.asarray(blue_band, dtype=float)
            anomaly_maps["low_rgb_excess_green"] = _z_anomaly((2.0 * green_array) - red_array - blue_array, mask, "low")

    for role, name in (("RED", "texture_680"), ("RED_EDGE", "texture_725"), ("NIR", "texture_850")):
        band = bands.get(role)
        if band is not None:
            anomaly_maps[name] = _z_anomaly(_local_std(band, cfg.texture_window), mask, "high")

    score = np.zeros(mask.shape, dtype=float)
    total_weight = 0.0
    for map_name, anomaly_map in anomaly_maps.items():
        weight = float(weights.get(map_name, 0.0))
        if weight <= 0:
            continue
        score += anomaly_map * weight
        total_weight += weight
    if total_weight > EPSILON:
        score = score / total_weight
    score = np.clip(score, 0.0, 1.0) * mask

    suspicious_mask = score >= float(cfg.score_threshold)
    suspicious_mask = _cleanup_mask(suspicious_mask, cfg.morphology_iterations) & mask
    labels, components = _connected_components(suspicious_mask)

    kept_mask = np.zeros_like(suspicious_mask, dtype=bool)
    kept_components: list[dict[str, Any]] = []
    for component in components:
        if component["area_px"] < int(cfg.min_area_px):
            continue
        component_mask = labels == component["label"]
        kept_mask |= component_mask
        kept_components.append(_measure_component(component, component_mask, sample, maps, mask, score))

    kept_labels, relabeled_components = _connected_components(kept_mask)
    for component, relabeled in zip(kept_components, relabeled_components):
        component["label"] = relabeled["label"]
    for rank, component in enumerate(
        sorted(kept_components, key=lambda item: float(item.get("severity_score", 0.0)), reverse=True),
        start=1,
    ):
        component["severity_rank"] = rank

    return {
        "parameters": {
            "score_threshold": float(cfg.score_threshold),
            "min_area_px": int(cfg.min_area_px),
            "morphology_iterations": int(cfg.morphology_iterations),
            "texture_window": int(cfg.texture_window),
            "weights": weights,
        },
        "roles": {role: _role_to_dict(value) for role, value in resolved_roles.items()},
        "score_map": score,
        "suspicious_mask": kept_mask,
        "labels": kept_labels,
        "spot_count": len(kept_components),
        "spots": kept_components,
        "available_maps": sorted(maps),
        "available_anomaly_maps": sorted(anomaly_maps),
    }


def _measure_component(
    component: dict[str, Any],
    component_mask: np.ndarray,
    sample: SpectralSample,
    maps: Mapping[str, np.ndarray],
    vegetation_mask: np.ndarray,
    score_map: np.ndarray,
) -> dict[str, Any]:
    """Measure one candidate component."""

    mean_bands: dict[str, float | None] = {}
    deltas: dict[str, float | None] = {}
    nearby_deltas: dict[str, float | None] = {}
    background_mask = _nearby_background_mask(component_mask, vegetation_mask)
    for band_key, band in sample.target_bands.items():
        band_mean = _mean_in_mask(band, component_mask)
        leaf_mean = _mean_in_mask(band, vegetation_mask)
        background_mean = _mean_in_mask(band, background_mask)
        mean_bands[f"band_{band_key}"] = band_mean
        deltas[f"band_{band_key}"] = None if band_mean is None or leaf_mean is None else band_mean - leaf_mean
        nearby_deltas[f"band_{band_key}"] = (
            None if band_mean is None or background_mean is None else band_mean - background_mean
        )

    mean_indices = {name: _mean_in_mask(values, component_mask) for name, values in maps.items()}
    background_indices = {name: _mean_in_mask(values, background_mask) for name, values in maps.items()}
    delta_indices = {
        name: None if value is None or background_indices.get(name) is None else value - background_indices[name]
        for name, value in mean_indices.items()
    }
    spot_indices_input = {
        key.replace("band_", ""): value
        for key, value in mean_bands.items()
        if value is not None and key.startswith("band_")
    }
    mean_score = _mean_in_mask(score_map, component_mask) or 0.0
    selected_scores = np.asarray(score_map, dtype=float)[component_mask]
    finite_scores = selected_scores[np.isfinite(selected_scores)]
    max_score = float(np.max(finite_scores)) if finite_scores.size else 0.0
    severity_score = float(mean_score * np.log1p(float(component["area_px"])))

    measured = dict(component)
    measured.update(
        {
            "mean_reflectance": mean_bands,
            "delta_from_leaf_average": deltas,
            "delta_from_nearby_background": nearby_deltas,
            "mean_indices": mean_indices,
            "nearby_background_mean_indices": background_indices,
            "delta_indices_from_nearby_background": delta_indices,
            "scalar_indices_from_spot_mean_bands": compute_indices(spot_indices_input),
            "mean_suspiciousness_score": float(mean_score),
            "max_suspiciousness_score": float(max_score),
            "severity_score": severity_score,
        }
    )
    return measured


def _nearby_background_mask(component_mask: np.ndarray, vegetation_mask: np.ndarray) -> np.ndarray:
    """Return a simple vegetation-only ring around a candidate spot."""

    outer = _binary_dilation(component_mask, iterations=5)
    inner = _binary_dilation(component_mask, iterations=1)
    return outer & ~inner & vegetation_mask


def _role_to_dict(role: BandRole) -> dict[str, Any]:
    """Convert a resolved role to a JSON-friendly dictionary."""

    return {
        "role": role.role,
        "band_key": role.band_key,
        "wavelength_nm": role.wavelength_nm,
        "status": role.status,
        "reason": role.reason,
    }


def _empty_result(config: SpotDetectionConfig, reason: str) -> dict[str, Any]:
    """Return an empty spot result with parameters."""

    return {
        "parameters": {
            "score_threshold": float(config.score_threshold),
            "min_area_px": int(config.min_area_px),
            "morphology_iterations": int(config.morphology_iterations),
            "texture_window": int(config.texture_window),
            "weights": config.resolved_weights(),
        },
        "roles": {},
        "score_map": None,
        "suspicious_mask": None,
        "labels": None,
        "spot_count": 0,
        "spots": [],
        "available_maps": [],
        "available_anomaly_maps": [],
        "reason": reason,
    }


def spot_result_to_report(result: Mapping[str, Any]) -> dict[str, Any]:
    """Return the JSON-friendly part of a spot detection result."""

    return {
        "parameters": result.get("parameters", {}),
        "roles": result.get("roles", {}),
        "spot_count": int(result.get("spot_count", 0)),
        "spots": result.get("spots", []),
        "available_maps": result.get("available_maps", []),
        "available_anomaly_maps": result.get("available_anomaly_maps", []),
        "reason": result.get("reason", ""),
    }


__all__ = ["SpotDetectionConfig", "detect_suspicious_spots", "spot_result_to_report"]
