"""Configurable target-band profiles."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Mapping


@dataclass(frozen=True, slots=True)
class TargetBandProfile:
    """A named set of requested target wavelengths."""

    name: str
    wavelengths_nm: tuple[float, ...]
    roles: Mapping[str, tuple[float, ...]]


PROFILE_7BAND_DEFAULT = TargetBandProfile(
    name="profile_7band_default",
    wavelengths_nm=(532.0, 556.0, 650.0, 680.0, 725.0, 850.0, 940.0),
    roles={
        "BLUE": (532.0,),
        "GREEN": (556.0, 532.0),
        "RED": (680.0, 650.0),
        "RED_EDGE": (725.0,),
        "NIR": (850.0,),
        "WATER_BAND": (940.0,),
    },
)

PROFILE_RGB_IMAGE = TargetBandProfile(
    name="profile_rgb_image",
    wavelengths_nm=(532.0, 556.0, 650.0),
    roles={
        "BLUE": (532.0,),
        "GREEN": (556.0, 532.0),
        "RED": (650.0,),
    },
)

PROFILES: dict[str, TargetBandProfile] = {
    PROFILE_7BAND_DEFAULT.name: PROFILE_7BAND_DEFAULT,
    PROFILE_RGB_IMAGE.name: PROFILE_RGB_IMAGE,
}


def get_profile(name: str = "profile_7band_default") -> TargetBandProfile:
    """Return a target band profile by name."""

    try:
        return PROFILES[name]
    except KeyError as exc:
        raise ValueError(f"Unknown target band profile: {name}") from exc
