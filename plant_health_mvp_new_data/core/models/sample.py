"""Canonical data structures for the plant-health multispectral MVP.

The MVP normalizes any supported source into a single internal representation
so downstream code can stay independent from the original dataset format.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

import numpy as np

TARGET_WAVELENGTHS_NM: tuple[float, ...] = (
    532.0,
    556.0,
    650.0,
    680.0,
    725.0,
    850.0,
    940.0,
)
"""Target wavelengths for the future 7-band camera system."""

VALID_STATUSES: tuple[str, ...] = ("exact", "nearest", "interpolated", "missing")
"""Allowed mapping statuses for each target wavelength."""


@dataclass(slots=True)
class BandMapping:
    """Describe how one target wavelength was sourced from the input data."""

    target_wavelength: float
    status: str
    source_indices: tuple[int, ...] = ()
    source_wavelengths: tuple[float, ...] = ()
    weights: tuple[float, ...] = ()
    distance_nm: float | None = None
    note: str = ""

    def to_dict(self) -> dict[str, Any]:
        """Return a JSON-friendly representation of the mapping."""

        return {
            "target_wavelength": self.target_wavelength,
            "status": self.status,
            "source_indices": list(self.source_indices),
            "source_wavelengths": list(self.source_wavelengths),
            "weights": list(self.weights),
            "distance_nm": self.distance_nm,
            "note": self.note,
        }


@dataclass(slots=True)
class SpectralSample:
    """Normalized sample container used by the rest of the pipeline."""

    source_type: str
    available_wavelengths: np.ndarray
    data: np.ndarray | None
    target_bands: dict[str, np.ndarray | None] = field(default_factory=dict)
    band_status: dict[str, str] = field(default_factory=dict)
    band_mappings: dict[str, BandMapping] = field(default_factory=dict)
    mask: np.ndarray | None = None
    metadata: dict[str, Any] = field(default_factory=dict)

    def is_image_like(self) -> bool:
        """Return ``True`` when the sample stores image-style band data."""

        if self.data is None:
            return False
        return self.data.ndim >= 3

    @staticmethod
    def band_key(wavelength: float) -> str:
        """Convert a wavelength value into the canonical string key."""

        rounded = round(float(wavelength))
        if abs(float(wavelength) - rounded) < 1e-6:
            return str(int(rounded))
        return f"{float(wavelength):g}"

    def to_metadata_dict(self) -> dict[str, Any]:
        """Return a metadata-only dictionary suitable for reporting."""

        return {
            "source_type": self.source_type,
            "available_wavelengths": self.available_wavelengths.tolist(),
            "band_status": dict(self.band_status),
            "band_mappings": {key: mapping.to_dict() for key, mapping in self.band_mappings.items()},
            "metadata": dict(self.metadata),
        }
