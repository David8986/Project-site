"""Role-aware scalar indices for mixed spectral/RGB band sources.

This module works from average band values plus optional report-style metadata.
It keeps the fixed-wavelength index API separate while making source quality
visible when a role is backed by an approximate RGB channel.
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from math import isfinite
from typing import Any

ROUND_DIGITS = 6
EPSILON = 1e-12

BandValues = Mapping[Any, Any]
IndexResult = dict[str, Any]

ROLE_PREFERENCES: dict[str, tuple[str, ...]] = {
    "RED": ("680", "650"),
    "GREEN": ("556", "532"),
    "RED_EDGE": ("725",),
    "NIR": ("850",),
    "WATER_BAND": ("940",),
}

CANONICAL_INDEX_KEYS = ("NDVI", "NDRE", "GNDVI", "WATER_PROXY")


@dataclass(frozen=True, slots=True)
class RoleSource:
    """Average-band source resolved for one semantic role."""

    role: str
    band_key: str | None
    wavelength_nm: float | None
    value: float | None
    status: str
    reason: str = ""
    source_note: str = ""
    approximate_source: bool = False

    @property
    def available(self) -> bool:
        """Return true when the role has a usable average value."""

        return self.status == "available" and self.value is not None

    def to_dict(self) -> dict[str, Any]:
        """Return a JSON-ready representation of this source."""

        return {
            "role": self.role,
            "band_key": self.band_key,
            "wavelength_nm": _round_value(self.wavelength_nm),
            "value": _round_value(self.value),
            "status": self.status,
            "reason": self.reason,
            "source_note": self.source_note,
            "approximate_source": self.approximate_source,
        }


def compute_role_aware_indices(
    avg_bands: BandValues,
    metadata: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    """Compute role-aware indices from average band values.

    The returned structure includes resolved semantic roles, per-index
    availability, and source wording that distinguishes proper spectral NDVI
    from NDVI-like mixed calculations that use an approximate RGB red channel.
    """

    metadata = metadata or {}
    lookup = _average_lookup(avg_bands)
    roles = _resolve_roles(lookup, metadata)
    nir = roles["NIR"]

    ndvi_red = _select_ndvi_red(lookup, roles, metadata)
    indices: dict[str, IndexResult] = {
        "NDVI": _normalized_difference(
            index_name="NDVI",
            label=_ndvi_label(ndvi_red, metadata),
            formula="(NIR - RED) / (NIR + RED)",
            first=nir,
            second=ndvi_red,
            required_roles=("NIR", "RED"),
            metadata=metadata,
            approximate=_is_ndvi_like(ndvi_red),
        ),
        "NDRE": _normalized_difference(
            index_name="NDRE",
            label="NDRE (red-edge + NIR)",
            formula="(NIR - RED_EDGE) / (NIR + RED_EDGE)",
            first=nir,
            second=roles["RED_EDGE"],
            required_roles=("NIR", "RED_EDGE"),
            metadata=metadata,
        ),
        "GNDVI": _normalized_difference(
            index_name="GNDVI",
            label="GNDVI (green + NIR)",
            formula="(NIR - GREEN) / (NIR + GREEN)",
            first=nir,
            second=roles["GREEN"],
            required_roles=("NIR", "GREEN"),
            metadata=metadata,
        ),
        "WATER_PROXY": _normalized_difference(
            index_name="WATER_PROXY",
            label="Water proxy (water band + NIR)",
            formula="(NIR - WATER_BAND) / (NIR + WATER_BAND)",
            first=nir,
            second=roles["WATER_BAND"],
            required_roles=("NIR", "WATER_BAND"),
            metadata=metadata,
        ),
    }

    return {
        "indices": indices,
        "roles": {role: source.to_dict() for role, source in roles.items()},
        "availability_summary": _availability_summary(indices),
        "index_aliases": {"NDWI_850_940": "WATER_PROXY"},
    }


def _normalized_difference(
    *,
    index_name: str,
    label: str,
    formula: str,
    first: RoleSource,
    second: RoleSource,
    required_roles: tuple[str, str],
    metadata: Mapping[str, Any],
    approximate: bool = False,
) -> IndexResult:
    """Compute ``(first - second) / (first + second)`` with availability detail."""

    roles = (first, second)
    base = {
        "label": label,
        "formula": formula,
        "required_roles": list(required_roles),
        "bands_used": _bands_used(roles),
        "wavelengths_nm": _wavelengths_used(roles),
        "source_notes": _source_notes(roles, metadata),
        "approximate": bool(approximate or any(role.approximate_source for role in roles)),
    }
    base["source_note"] = "; ".join(base["source_notes"])

    missing = [role for role in roles if not role.available]
    if missing:
        reasons = [_missing_reason(role) for role in missing]
        return {
            **base,
            "status": "unavailable",
            "available": False,
            "value": None,
            "components": _components(first, second),
            "missing_roles": [role.role for role in missing],
            "reason": _short_missing_reason(missing),
            "reasons": reasons,
        }

    numerator = float(first.value) - float(second.value)
    denominator = float(first.value) + float(second.value)
    components = _components(first, second, numerator=numerator, denominator=denominator)
    if abs(denominator) <= EPSILON:
        return {
            **base,
            "status": "unavailable",
            "available": False,
            "value": None,
            "components": components,
            "missing_roles": [],
            "reason": "division by zero",
            "reasons": [f"{index_name} denominator is zero."],
        }

    return {
        **base,
        "status": "available",
        "available": True,
        "value": _round_value(numerator / denominator),
        "components": components,
        "missing_roles": [],
        "reason": "",
        "reasons": [],
    }


def _select_ndvi_red(
    lookup: Mapping[str, Any],
    roles: Mapping[str, RoleSource],
    metadata: Mapping[str, Any],
) -> RoleSource:
    """Prefer proper 680 nm red for NDVI, then fall back to the RED role."""

    proper_red_value = _lookup_value(lookup, "680")
    if proper_red_value is not None:
        return _source_from_band(
            role="RED",
            band_key="680",
            value=proper_red_value,
            metadata=metadata,
            fallback_note="Proper NDVI red band at 680 nm.",
        )
    return roles["RED"]


def _ndvi_label(red: RoleSource, metadata: Mapping[str, Any]) -> str:
    """Return the clearest NDVI label for the chosen red source."""

    band_key = _canonical_band_key(red.band_key)
    if band_key == "680":
        return "NDVI (proper 680 nm red + NIR)"
    if _is_rgb_red(red, metadata):
        return "NDVI-like (RGB red + NIR)"
    if red.band_key is not None:
        return f"NDVI-like ({red.band_key} nm red + NIR)"
    return "NDVI-like (red + NIR)"


def _is_ndvi_like(red: RoleSource) -> bool:
    """Return true when NDVI is using a non-680 red source."""

    return _canonical_band_key(red.band_key) != "680"


def _resolve_roles(
    lookup: Mapping[str, Any],
    metadata: Mapping[str, Any],
) -> dict[str, RoleSource]:
    """Resolve all semantic roles from metadata first, then band availability."""

    role_metadata = _role_metadata(metadata)
    roles: dict[str, RoleSource] = {}
    for role in ROLE_PREFERENCES:
        raw_role = _mapping_get_casefold(role_metadata, role)
        if raw_role is None:
            roles[role] = _infer_role(role, lookup, metadata)
        else:
            roles[role] = _source_from_role_metadata(role, raw_role, lookup, metadata)
    return roles


def _infer_role(
    role: str,
    lookup: Mapping[str, Any],
    metadata: Mapping[str, Any],
) -> RoleSource:
    """Infer a role from standard wavelength preferences."""

    for band_key in ROLE_PREFERENCES[role]:
        value = _lookup_value(lookup, band_key)
        if value is not None:
            return _source_from_band(role=role, band_key=band_key, value=value, metadata=metadata)

    return RoleSource(
        role=role,
        band_key=None,
        wavelength_nm=None,
        value=None,
        status="missing",
        reason=f"No average band value was available for role {role}.",
        source_note="",
        approximate_source=False,
    )


def _source_from_role_metadata(
    role: str,
    raw_role: Any,
    lookup: Mapping[str, Any],
    metadata: Mapping[str, Any],
) -> RoleSource:
    """Build a role source from report-style role metadata."""

    band_key = _role_band_key(raw_role)
    wavelength = _role_wavelength(raw_role, band_key)
    status = str(_field(raw_role, "status", default="available") or "available").strip().casefold()
    reason = str(_field(raw_role, "reason", default="") or "")
    source_note = str(
        _field(raw_role, "source_note", "source_notes", "note", "source", default="") or ""
    )

    if band_key is None and wavelength is not None:
        band_key = _canonical_band_key(str(wavelength))
    value = _lookup_value(lookup, band_key) if band_key is not None else None
    if status == "available" and value is None:
        status = "missing"
        reason = reason or f"No average value was available for role {role} at band {band_key}."
    elif status != "available" and not reason:
        reason = f"Role {role} was marked {status}."

    approximate = _truthy(_field(raw_role, "approximate_source", "approximate", default=False))
    source = _source_from_band(
        role=role,
        band_key=band_key,
        value=value,
        metadata=metadata,
        status=status,
        reason=reason,
        fallback_note=source_note,
        approximate_source=approximate,
    )
    if wavelength is not None and source.wavelength_nm is None:
        return RoleSource(
            role=source.role,
            band_key=source.band_key,
            wavelength_nm=wavelength,
            value=source.value,
            status=source.status,
            reason=source.reason,
            source_note=source.source_note,
            approximate_source=source.approximate_source,
        )
    return source


def _source_from_band(
    *,
    role: str,
    band_key: str | None,
    value: float | None,
    metadata: Mapping[str, Any],
    status: str = "available",
    reason: str = "",
    fallback_note: str = "",
    approximate_source: bool = False,
) -> RoleSource:
    """Create role-source details for a known band key."""

    wavelength = _band_wavelength(band_key)
    mapping = _mapping_for_band(metadata, band_key)
    status = str(status).strip().casefold()
    note_parts: list[str] = []
    if fallback_note:
        note_parts.append(fallback_note)
    mapping_note = _mapping_note(mapping)
    if mapping_note:
        note_parts.append(mapping_note)

    source = RoleSource(
        role=role,
        band_key=None if band_key is None else str(band_key),
        wavelength_nm=wavelength,
        value=value,
        status=status,
        reason=reason,
        source_note=" ".join(_dedupe(note_parts)),
        approximate_source=bool(approximate_source),
    )

    if _is_rgb_role(source, metadata):
        rgb_note = _rgb_note(source)
        return RoleSource(
            role=source.role,
            band_key=source.band_key,
            wavelength_nm=source.wavelength_nm,
            value=source.value,
            status=source.status,
            reason=source.reason,
            source_note=" ".join(_dedupe([source.source_note, rgb_note])),
            approximate_source=True,
        )
    return source


def _role_metadata(metadata: Mapping[str, Any]) -> Mapping[str, Any]:
    """Return the first role mapping found in common metadata containers."""

    for container in _metadata_containers(metadata):
        for key in ("roles", "band_roles", "semantic_roles"):
            value = container.get(key)
            if isinstance(value, Mapping):
                return value
        spot_detection = container.get("spot_detection")
        if isinstance(spot_detection, Mapping):
            roles = spot_detection.get("roles")
            if isinstance(roles, Mapping):
                return roles
    return {}


def _mapping_for_band(metadata: Mapping[str, Any], band_key: str | None) -> Mapping[str, Any]:
    """Return mapping metadata for a target band when available."""

    if band_key is None:
        return {}
    canonical = _canonical_band_key(band_key)
    for container in _metadata_containers(metadata):
        mapping_candidates = (
            container.get("mapping"),
            container.get("band_mapping"),
            container.get("band_mappings"),
            container.get("target_band_mapping"),
        )
        mapping_summary = container.get("mapping_summary")
        if isinstance(mapping_summary, Mapping):
            mapping_candidates += (mapping_summary.get("per_target"),)
        for mapping in mapping_candidates:
            if not isinstance(mapping, Mapping):
                continue
            for key, value in mapping.items():
                if _canonical_band_key(key) == canonical and isinstance(value, Mapping):
                    return value
    return {}


def _metadata_containers(metadata: Mapping[str, Any]) -> list[Mapping[str, Any]]:
    """Return top-level and nested metadata dictionaries to inspect."""

    containers: list[Mapping[str, Any]] = [metadata]
    nested = metadata.get("metadata")
    if isinstance(nested, Mapping):
        containers.append(nested)
    return containers


def _average_lookup(avg_bands: BandValues) -> dict[str, Any]:
    """Build a case-insensitive, prefix-tolerant average-band lookup."""

    lookup: dict[str, Any] = {}
    for key, value in avg_bands.items():
        for candidate in _key_candidates(key):
            lookup.setdefault(candidate, value)
    return lookup


def _lookup_value(lookup: Mapping[str, Any], key: str | None) -> float | None:
    """Return a finite float for a band key, accepting common key variants."""

    if key is None:
        return None
    for candidate in _key_candidates(key):
        if candidate not in lookup:
            continue
        try:
            value = float(lookup[candidate])
        except (TypeError, ValueError):
            return None
        return value if isfinite(value) else None
    return None


def _key_candidates(key: Any) -> tuple[str, ...]:
    """Return lookup variants for numeric and ``band_``-prefixed keys."""

    raw = str(key)
    candidates = [raw, raw.lower(), raw.upper()]
    if raw.lower().startswith("band_"):
        stripped = raw[5:]
        candidates.extend([stripped, stripped.lower(), stripped.upper()])
    else:
        candidates.append(f"band_{raw}")

    canonical = _canonical_band_key(raw)
    if canonical:
        candidates.extend([canonical, f"band_{canonical}"])
    return tuple(_dedupe(candidates))


def _canonical_band_key(key: Any) -> str:
    """Return a normalized numeric band key when possible."""

    if key is None:
        return ""
    text = str(key)
    if text.lower().startswith("band_"):
        text = text[5:]
    try:
        value = float(text)
    except ValueError:
        return text
    rounded = round(value)
    if abs(value - rounded) < 1e-6:
        return str(int(rounded))
    return f"{value:g}"


def _band_wavelength(band_key: str | None) -> float | None:
    """Return numeric wavelength from a band key when it is wavelength-like."""

    canonical = _canonical_band_key(band_key)
    if not canonical:
        return None
    try:
        return float(canonical)
    except ValueError:
        return None


def _role_band_key(raw_role: Any) -> str | None:
    """Extract a band key from role metadata."""

    if isinstance(raw_role, (str, int, float)):
        return _canonical_band_key(raw_role)
    value = _field(
        raw_role,
        "band_key",
        "band",
        "band_id",
        "key",
        "target_band",
        "target_wavelength",
        "wavelength_nm",
        "wavelength",
        default=None,
    )
    if value is None:
        return None
    return _canonical_band_key(value)


def _role_wavelength(raw_role: Any, band_key: str | None) -> float | None:
    """Extract a role wavelength, falling back to the band key."""

    value = _field(raw_role, "wavelength_nm", "wavelength", "target_wavelength", default=None)
    if value is None:
        return _band_wavelength(band_key)
    try:
        wavelength = float(value)
    except (TypeError, ValueError):
        return _band_wavelength(band_key)
    return wavelength if isfinite(wavelength) else None


def _field(raw: Any, *names: str, default: Any = None) -> Any:
    """Read the first present field from a mapping or object."""

    for name in names:
        if isinstance(raw, Mapping) and name in raw:
            return raw[name]
        if hasattr(raw, name):
            return getattr(raw, name)
    return default


def _mapping_get_casefold(mapping: Mapping[str, Any], key: str) -> Any:
    """Return a mapping value with case-insensitive string matching."""

    if key in mapping:
        return mapping[key]
    folded = key.casefold()
    for item_key, value in mapping.items():
        if str(item_key).casefold() == folded:
            return value
    return None


def _is_rgb_role(source: RoleSource, metadata: Mapping[str, Any]) -> bool:
    """Return true when a role appears to come from an approximate RGB channel."""

    if not source.band_key:
        return False
    text = _source_text(source, metadata)
    has_rgb_text = "rgb" in text or "display" in text or "channel" in text
    if source.role == "RED" and _canonical_band_key(source.band_key) == "650" and has_rgb_text:
        return True
    if (
        source.role == "GREEN"
        and _canonical_band_key(source.band_key) in {"556", "532"}
        and has_rgb_text
    ):
        return True
    if (
        any(container.get("rgb_only") for container in _metadata_containers(metadata))
        and source.role in {"RED", "GREEN"}
    ):
        return True
    return False


def _is_rgb_red(source: RoleSource, metadata: Mapping[str, Any]) -> bool:
    """Return true when the red source is specifically RGB red."""

    return (
        source.role == "RED"
        and _canonical_band_key(source.band_key) == "650"
        and _is_rgb_role(source, metadata)
    )


def _source_text(source: RoleSource, metadata: Mapping[str, Any]) -> str:
    """Collect source wording for fuzzy RGB/source-quality detection."""

    parts = [source.source_note, source.reason]
    for container in _metadata_containers(metadata):
        parts.extend(
            [
                str(container.get("source_type", "")),
                str(container.get("source_data_kind", "")),
                str(container.get("analysis_data_kind", "")),
                str(container.get("spectral_limitations", "")),
            ]
        )
        notes = container.get("loader_notes", [])
        if isinstance(notes, (list, tuple)):
            parts.extend(str(note) for note in notes)
        labels = container.get("channel_wavelength_labels_nm")
        if isinstance(labels, Mapping) and source.role in {"RED", "GREEN"}:
            parts.append("rgb channel wavelength labels")
    return " ".join(parts).casefold()


def _rgb_note(source: RoleSource) -> str:
    """Return a standard note for approximate RGB channel sources."""

    if source.role == "RED":
        return "RED uses approximate RGB red/channel 650 source; not a calibrated narrowband red measurement."
    if source.role == "GREEN":
        return "GREEN uses an approximate RGB/display-channel label; not a calibrated narrowband green measurement."
    return "Source uses an approximate RGB/display-channel label."


def _mapping_note(mapping: Mapping[str, Any]) -> str:
    """Summarize mapping metadata for source notes."""

    if not mapping:
        return ""
    note = str(mapping.get("note") or "")
    status = str(mapping.get("status") or "")
    source_wavelength = mapping.get("source_wavelength", None)
    if source_wavelength is None:
        wavelengths = mapping.get("source_wavelengths")
        if isinstance(wavelengths, (list, tuple)) and wavelengths:
            source_wavelength = wavelengths[0]
    if note:
        return note
    if status and status not in {"available", "exact"}:
        return f"Band mapping status is {status}."
    if source_wavelength is not None:
        try:
            wavelength = float(source_wavelength)
        except (TypeError, ValueError):
            return f"Source wavelength {source_wavelength} nm."
        return f"Source wavelength {wavelength:g} nm."
    return ""


def _source_notes(roles: tuple[RoleSource, ...], metadata: Mapping[str, Any]) -> list[str]:
    """Return deduplicated source notes for roles used by an index."""

    notes: list[str] = []
    for role in roles:
        if role.source_note:
            notes.append(role.source_note)
        elif role.band_key is not None:
            notes.append(f"{role.role} uses average band {role.band_key}.")
        elif role.reason:
            notes.append(role.reason)
        if _is_rgb_role(role, metadata):
            rgb_note = _rgb_note(role)
            if rgb_note not in role.source_note:
                notes.append(rgb_note)
    return _dedupe(notes)


def _bands_used(roles: tuple[RoleSource, ...]) -> dict[str, str | int | float | None]:
    """Return role-to-band-key details with numeric keys when clean."""

    return {role.role: _display_band_key(role.band_key) for role in roles}


def _wavelengths_used(roles: tuple[RoleSource, ...]) -> dict[str, float | None]:
    """Return role-to-wavelength details."""

    return {role.role: _round_value(role.wavelength_nm) for role in roles}


def _display_band_key(band_key: str | None) -> str | int | float | None:
    """Return a compact band key suitable for reports."""

    if band_key is None:
        return None
    canonical = _canonical_band_key(band_key)
    try:
        value = float(canonical)
    except ValueError:
        return band_key
    rounded = round(value)
    return int(rounded) if abs(value - rounded) < 1e-6 else value


def _components(
    first: RoleSource,
    second: RoleSource,
    numerator: float | None = None,
    denominator: float | None = None,
) -> dict[str, float | None]:
    """Return rounded component values for an index result."""

    return {
        first.role: _round_value(first.value),
        second.role: _round_value(second.value),
        f"{first.role}_minus_{second.role}": _round_value(numerator),
        f"{first.role}_plus_{second.role}": _round_value(denominator),
        "numerator": _round_value(numerator),
        "denominator": _round_value(denominator),
    }


def _missing_reason(role: RoleSource) -> str:
    """Return a human-readable missing-role reason."""

    if role.reason:
        return role.reason
    return f"Missing required role {role.role}."


def _short_missing_reason(missing: list[RoleSource]) -> str:
    """Return a compact missing-role summary."""

    names = ", ".join(role.role for role in missing)
    suffix = "s" if len(missing) > 1 else ""
    return f"missing required role{suffix}: {names}"


def _availability_summary(indices: Mapping[str, IndexResult]) -> dict[str, Any]:
    """Build a compact availability summary for canonical indices."""

    available_indices = [
        name
        for name in CANONICAL_INDEX_KEYS
        if indices.get(name, {}).get("available") is True
    ]
    unavailable_indices = [
        name
        for name in CANONICAL_INDEX_KEYS
        if indices.get(name, {}).get("available") is not True
    ]
    return {
        "total": len(CANONICAL_INDEX_KEYS),
        "available": len(available_indices),
        "unavailable": len(unavailable_indices),
        "available_count": len(available_indices),
        "unavailable_count": len(unavailable_indices),
        "available_indices": available_indices,
        "unavailable_indices": unavailable_indices,
        "by_index": {
            name: indices.get(name, {}).get("status", "unavailable")
            for name in CANONICAL_INDEX_KEYS
        },
        "unavailable_reasons": {
            name: indices[name].get("reason", "")
            for name in unavailable_indices
            if name in indices
        },
    }


def _round_value(value: float | int | None) -> float | None:
    """Round numeric output while preserving missing values."""

    if value is None:
        return None
    return round(float(value), ROUND_DIGITS)


def _truthy(value: Any) -> bool:
    """Return a permissive boolean for metadata flags."""

    if isinstance(value, str):
        return value.strip().casefold() in {"1", "true", "yes", "y"}
    return bool(value)


def _dedupe(values: list[str] | tuple[str, ...]) -> list[str]:
    """Return non-empty strings while preserving order."""

    seen: set[str] = set()
    result: list[str] = []
    for value in values:
        if not value:
            continue
        if value in seen:
            continue
        seen.add(value)
        result.append(value)
    return result


__all__ = ["compute_role_aware_indices"]
