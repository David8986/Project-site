"""Deterministic mock dataset adapter for development and tests."""

from __future__ import annotations

from pathlib import Path

import numpy as np

from ..loader import create_mock_sample, load_wavelength_csv
from .base import AdapterSample, DatasetAdapter


class MockAdapter(DatasetAdapter):
    """Adapter that exposes the built-in deterministic mock hyperspectral cube."""

    adapter_name = "mock_hyperspectral"

    def list_samples(self) -> list[str]:
        """Return the single synthetic sample id."""

        return ["synthetic_mock_sample"]

    def load_sample(self, sample_id: str | None = None) -> AdapterSample:
        """Load the deterministic mock sample through the adapter interface."""

        wavelengths = None
        if self.wavelength_csv is not None and Path(self.wavelength_csv).exists():
            loaded = load_wavelength_csv(self.wavelength_csv)
            if loaded.size:
                wavelengths = loaded

        spectral = create_mock_sample(wavelengths=wavelengths)
        label = sample_id or "synthetic_mock_sample"
        metadata = dict(spectral.metadata)
        metadata.update(
            {
                "adapter_used": self.adapter_name,
                "sample_id": label,
                "source_data_kind": "mock_synthetic_data",
                "analysis_data_kind": "synthetic_reflectance_like_values",
                "calibration_applied": False,
                "calibration": {
                    "calibration_applied": False,
                    "reason": "mock adapter emits synthetic reflectance-like values",
                    "analysis_data_kind": "synthetic_reflectance_like_values",
                },
            }
        )

        return AdapterSample(
            sample_id=label,
            cube=np.asarray(spectral.data),
            wavelengths=np.asarray(spectral.available_wavelengths, dtype=float),
            metadata=metadata,
            dark_reference=None,
            white_reference=None,
            reflectance_cube=np.asarray(spectral.data),
            preview_image=None,
            source_type=spectral.source_type,
            is_reflectance=True,
        )


__all__ = ["MockAdapter"]
