"""Calibration helpers for hyperspectral cubes."""

from __future__ import annotations

from typing import Any

import numpy as np


def _reference_plane(reference: np.ndarray | None) -> np.ndarray | None:
    """Collapse reference captures to a broadcastable mean plane."""

    if reference is None:
        return None
    array = np.asarray(reference, dtype=np.float32)
    if array.ndim == 3:
        return np.nanmean(array, axis=0, keepdims=True)
    if array.ndim == 2:
        return array[np.newaxis, :, :]
    return None


def calibrate_reflectance(
    cube: np.ndarray,
    dark_reference: np.ndarray | None,
    white_reference: np.ndarray | None,
    *,
    clip: bool = True,
    epsilon: float = 1e-6,
) -> tuple[np.ndarray, dict[str, Any]]:
    """Apply dark/white reflectance calibration when references exist.

    Invalid denominators are left as ``NaN`` in the calibrated cube so later
    scientific calculations can ignore them instead of silently treating them
    as real reflectance values. Display normalization remains a separate output
    concern.
    """

    if dark_reference is None or white_reference is None:
        return np.asarray(cube), {
            "calibration_applied": False,
            "reason": "missing dark or white reference",
            "analysis_data_kind": "raw_intensity",
        }

    cube_array = np.asarray(cube, dtype=np.float32)
    dark = _reference_plane(dark_reference)
    white = _reference_plane(white_reference)
    if dark is None or white is None:
        return cube_array, {
            "calibration_applied": False,
            "reason": "unsupported reference shape",
            "analysis_data_kind": "raw_intensity",
        }

    denominator = white - dark
    valid_denominator = np.isfinite(denominator) & (np.abs(denominator) > float(epsilon))
    invalid_denominator_count = int(np.size(denominator) - np.count_nonzero(valid_denominator))
    safe_denominator = np.where(valid_denominator, denominator, np.nan)

    reflectance = (cube_array - dark) / safe_denominator
    finite_before_clip = np.isfinite(reflectance)
    invalid_reflectance_count = int(reflectance.size - np.count_nonzero(finite_before_clip))
    negative_reflectance_count = int(np.count_nonzero(finite_before_clip & (reflectance < 0)))
    high_reflectance_count = int(np.count_nonzero(finite_before_clip & (reflectance > 1.0)))

    if clip:
        reflectance = np.clip(reflectance, 0.0, 1.5)

    return reflectance.astype(np.float32, copy=False), {
        "calibration_applied": True,
        "analysis_data_kind": "calibrated_reflectance",
        "formula": "(raw - dark) / (white - dark)",
        "clip": bool(clip),
        "epsilon": float(epsilon),
        "dark_reference_shape": list(np.asarray(dark_reference).shape),
        "white_reference_shape": list(np.asarray(white_reference).shape),
        "invalid_denominator_count": invalid_denominator_count,
        "invalid_reflectance_count": invalid_reflectance_count,
        "negative_reflectance_count_before_clip": negative_reflectance_count,
        "reflectance_above_one_count_before_clip": high_reflectance_count,
    }
