"""Dataset adapter base interfaces.

Adapters isolate dataset-specific file parsing from the analysis pipeline.
Core modules should work with ``AdapterSample`` or ``SpectralSample`` instead
of depending on folder names or a particular camera layout.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import numpy as np

from ..models.sample import SpectralSample


@dataclass(slots=True)
class AdapterSample:
    """A dataset-agnostic sample returned by a dataset adapter."""

    sample_id: str
    cube: np.ndarray
    wavelengths: np.ndarray
    metadata: dict[str, Any] = field(default_factory=dict)
    dark_reference: np.ndarray | None = None
    white_reference: np.ndarray | None = None
    reflectance_cube: np.ndarray | None = None
    preview_image: np.ndarray | None = None
    source_type: str = "hyperspectral_cube"
    is_reflectance: bool = False

    def to_spectral_sample(self, use_reflectance: bool = True) -> SpectralSample:
        """Convert to the canonical pipeline sample object."""

        data = self.reflectance_cube if use_reflectance else None
        if data is None:
            data = self.cube

        metadata = dict(self.metadata)
        metadata.update(
            {
                "adapter_sample_id": self.sample_id,
                "adapter_source_type": self.source_type,
                "has_dark_reference": self.dark_reference is not None,
                "has_white_reference": self.white_reference is not None,
                "is_reflectance": bool(use_reflectance and (self.is_reflectance or metadata.get("calibration_applied"))),
            }
        )

        return SpectralSample(
            source_type=self.source_type,
            available_wavelengths=np.asarray(self.wavelengths, dtype=float),
            data=np.asarray(data),
            metadata=metadata,
        )


class DatasetAdapter(ABC):
    """Base class for dataset-specific adapters."""

    adapter_name = "base"

    def __init__(self, root_path: str | Path, wavelength_csv: str | Path | None = None) -> None:
        self.root_path = Path(root_path).expanduser()
        self.wavelength_csv = None if wavelength_csv is None else Path(wavelength_csv).expanduser()

    @abstractmethod
    def list_samples(self) -> list[str]:
        """Return dataset sample identifiers available from this adapter."""

    @abstractmethod
    def load_sample(self, sample_id: str | None = None) -> AdapterSample:
        """Load one sample by identifier, or a sensible default sample."""
