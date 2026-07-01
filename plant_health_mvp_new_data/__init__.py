"""Plant-health multispectral MVP package.

This package provides the shared data model and package metadata for the
first local MVP of the plant-health analysis pipeline.
"""

from .models.sample import (
    BandMapping,
    SpectralSample,
    TARGET_WAVELENGTHS_NM,
    VALID_STATUSES,
)

__all__ = [
    "BandMapping",
    "SpectralSample",
    "TARGET_WAVELENGTHS_NM",
    "VALID_STATUSES",
]
