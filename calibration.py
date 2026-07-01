"""Calibration helpers for ENVI hyperspectral imagery."""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np


@dataclass(frozen=True)
class CalibrationResult:
    """Calibrated reflectance data with human-readable warnings."""

    values: np.ndarray
    warnings: tuple[str, ...]


def calibrated_reflectance(
    sample: np.ndarray,
    dark: np.ndarray,
    white: np.ndarray,
    *,
    epsilon: float = 1e-12,
) -> CalibrationResult:
    """Compute reflectance using ``R = (I - D) / (W - D)`` safely.

    Invalid denominator pixels and non-finite inputs are returned as ``NaN``.
    The function accepts bands, spectra, or image regions as long as all three
    arrays have the same shape.
    """

    sample_arr = np.asarray(sample, dtype=np.float32)
    dark_arr = np.asarray(dark, dtype=np.float32)
    white_arr = np.asarray(white, dtype=np.float32)

    if sample_arr.shape != dark_arr.shape or sample_arr.shape != white_arr.shape:
        raise ValueError(
            "Sample, dark reference, and white reference must have identical "
            f"shapes; got {sample_arr.shape}, {dark_arr.shape}, {white_arr.shape}."
        )

    denominator = white_arr - dark_arr
    finite_inputs = (
        np.isfinite(sample_arr)
        & np.isfinite(dark_arr)
        & np.isfinite(white_arr)
        & np.isfinite(denominator)
    )
    valid_denominator = np.abs(denominator) > epsilon
    valid = finite_inputs & valid_denominator

    result = np.full(sample_arr.shape, np.nan, dtype=np.float32)
    np.divide(sample_arr - dark_arr, denominator, out=result, where=valid)

    warnings: list[str] = []
    invalid_input_count = int(np.size(sample_arr) - np.count_nonzero(finite_inputs))
    invalid_denominator_count = int(np.count_nonzero(finite_inputs & ~valid_denominator))
    invalid_result_count = int(np.count_nonzero(~np.isfinite(result)))

    if invalid_input_count:
        warnings.append(f"{invalid_input_count} value(s) had non-finite raw/reference inputs.")
    if invalid_denominator_count:
        warnings.append(
            f"{invalid_denominator_count} value(s) had an unsafe white-dark denominator."
        )
    if invalid_result_count:
        warnings.append(f"{invalid_result_count} calibrated value(s) are NaN/Inf.")

    return CalibrationResult(values=result, warnings=tuple(warnings))


def calibration_ready(sample_shape: tuple[int, int, int], *reference_shapes: tuple[int, int, int]) -> bool:
    """Return ``True`` when every reference cube matches the sample cube shape."""

    return all(shape == sample_shape for shape in reference_shapes)
