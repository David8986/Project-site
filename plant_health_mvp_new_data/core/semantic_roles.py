"""Semantic band-role resolution for target bands."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Mapping

import numpy as np

from .models.sample import SpectralSample


@dataclass(frozen=True, slots=True)
class BandRole:
    """Resolved semantic role for one target band."""

    role: str
    band_key: str | None
    wavelength_nm: float | None
    status: str
    reason: str = ""


DEFAULT_ROLE_PREFERENCES: dict[str, tuple[float, ...]] = {
    "BLUE": (532.0,),
    "RED": (680.0, 650.0),
    "GREEN": (556.0, 532.0),
    "RED_EDGE": (725.0,),
    "NIR": (850.0,),
    "WATER_BAND": (940.0,),
}


def resolve_semantic_roles(
    sample: SpectralSample,
    role_preferences: Mapping[str, tuple[float, ...]] | None = None,
) -> dict[str, BandRole]:
    """Resolve semantic roles using available target bands and fallbacks."""

    preferences = role_preferences or DEFAULT_ROLE_PREFERENCES
    available = {
        float(key): str(key)
        for key, band in sample.target_bands.items()
        if band is not None and _is_float_key(str(key))
    }
    resolved: dict[str, BandRole] = {}
    for role, preferred_wavelengths in preferences.items():
        choice = None
        for wavelength in preferred_wavelengths:
            if float(wavelength) in available:
                choice = (float(wavelength), available[float(wavelength)])
                break
        if choice is None:
            resolved[role] = BandRole(
                role=role,
                band_key=None,
                wavelength_nm=None,
                status="missing",
                reason=f"No available target band for role {role}.",
            )
        else:
            wavelength, key = choice
            resolved[role] = BandRole(role=role, band_key=key, wavelength_nm=wavelength, status="available")
    return resolved


def role_band_array(sample: SpectralSample, roles: Mapping[str, BandRole], role: str) -> np.ndarray | None:
    """Return a role's 2D band array when available."""

    resolved = roles.get(role)
    if resolved is None or resolved.band_key is None:
        return None
    band = sample.target_bands.get(resolved.band_key)
    if band is None:
        return None
    array = np.asarray(band, dtype=float)
    return array if array.ndim == 2 else None


def _is_float_key(key: str) -> bool:
    """Return true when a key can be parsed as a float wavelength."""

    try:
        float(key)
    except ValueError:
        return False
    return True
