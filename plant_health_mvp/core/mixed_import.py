"""Load mixed image bundles into canonical spectral samples.

The mixed bundle importer combines ordinary RGB images and single-band images
into a single :class:`SpectralSample`. It is intended for pragmatic imports
where each image or channel is assigned an explicit plant-health role and an
approximate wavelength label.

Example JSON spec::

    {
      "sample_id": "leaf_bundle",
      "alignment": {
        "mode": "resize_to_reference",
        "reference": "first",
        "resample": "bilinear"
      },
      "entries": [
        {"path": "rgb.jpg", "type": "rgb"},
        {"path": "nir.png", "type": "grayscale", "role": "NIR", "wavelength": 850}
      ]
    }
"""

from __future__ import annotations

from dataclasses import dataclass
import json
from pathlib import Path
from typing import Any, Mapping, Sequence

import numpy as np
from PIL import Image

from .filename_wavelength import infer_wavelength_from_filename
from .image_alignment import (
    AlignmentTransform,
    apply_alignment_transform,
    compute_alignment_transform,
    normalize_alignment_mode,
    normalize_transform_model,
)
from .models.sample import BandMapping, SpectralSample


RGB_CHANNEL_WAVELENGTHS_NM: dict[str, float] = {
    "R": 650.0,
    "G": 556.0,
    "B": 532.0,
}
"""Approximate wavelength labels used for ordinary RGB display channels."""

RGB_CHANNEL_ROLES: dict[str, str] = {
    "R": "RED",
    "G": "GREEN",
    "B": "BLUE",
}
"""Default role labels for ordinary RGB display channels."""

_CHANNEL_INDEXES: dict[str, int] = {
    "R": 0,
    "RED": 0,
    "0": 0,
    "G": 1,
    "GREEN": 1,
    "1": 1,
    "B": 2,
    "BLUE": 2,
    "2": 2,
}

_RESAMPLE_FILTERS: dict[str, int] = {
    "nearest": Image.Resampling.NEAREST,
    "bilinear": Image.Resampling.BILINEAR,
}


@dataclass(frozen=True, slots=True)
class _LoadedBand:
    """One imported 2D image band plus the metadata needed to describe it."""

    data: np.ndarray
    path: Path
    input_path: str
    entry_index: int
    image_id: str
    role: str
    wavelength_nm: float
    label: str
    source_channel: str | None
    source_channel_index: int | None
    original_shape: tuple[int, int]
    image_mode: str
    image_size: tuple[int, int]


def read_mixed_image_bundle_spec(spec_path: str | Path) -> dict[str, Any]:
    """Read a mixed image bundle JSON spec.

    Parameters
    ----------
    spec_path:
        Path to a JSON file containing an ``entries`` list.

    Returns
    -------
    dict[str, Any]
        The parsed JSON object.
    """

    path = Path(spec_path).expanduser()
    with path.open("r", encoding="utf-8") as handle:
        spec = json.load(handle)
    if not isinstance(spec, dict):
        raise ValueError("Mixed image bundle spec must be a JSON object.")
    return spec


def write_mixed_image_bundle_spec(spec_path: str | Path, spec: Mapping[str, Any]) -> Path:
    """Write a mixed image bundle JSON spec and return the written path."""

    path = Path(spec_path).expanduser()
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as handle:
        json.dump(dict(spec), handle, indent=2, sort_keys=True)
        handle.write("\n")
    return path


def load_mixed_image_bundle(spec_path: str | Path) -> SpectralSample:
    """Load a JSON mixed image bundle spec into a :class:`SpectralSample`.

    RGB entries may provide a ``channels`` or ``channel_map`` value. When no
    channel map is supplied, the importer uses approximate display-channel
    labels: R/RED at 650 nm, G/GREEN at 556 nm, and B/BLUE at 532 nm. Grayscale
    entries require an explicit ``wavelength`` or ``wavelength_nm`` and ``role``.

    Supported alignment modes include ``none``, ``resize_only``,
    ``automatic_ecc``, ``automatic_ecc_affine``, ``automatic_phase_ecc``,
    ``automatic_feature_edge``, ``automatic_contour_mask``, and
    ``automatic_mask_then_ecc``. Automatic modes align each full source image
    globally before vegetation masking and per-pixel analysis.
    """

    spec_file = Path(spec_path).expanduser()
    spec = read_mixed_image_bundle_spec(spec_file)
    base_dir = spec_file.parent
    entries = _entries_from_spec(spec)

    loaded_bands: list[_LoadedBand] = []
    imported_files: list[dict[str, Any]] = []

    for entry_index, entry in enumerate(entries):
        path = _entry_path(entry, base_dir)
        bands = _load_entry_bands(entry, path, entry_index)
        loaded_bands.extend(bands)
        imported_files.append(_imported_file_record(entry, path, bands))

    if not loaded_bands:
        raise ValueError("Mixed image bundle spec did not produce any image bands.")

    alignment = _alignment_config(spec)
    aligned_bands, alignment_metadata = _align_bands(loaded_bands, alignment)
    data = np.stack([band.data for band in aligned_bands], axis=-1).astype(np.float32, copy=False)
    wavelengths = np.asarray([band.wavelength_nm for band in aligned_bands], dtype=float)

    target_bands: dict[str, np.ndarray | None] = {}
    band_status: dict[str, str] = {}
    band_mappings: dict[str, BandMapping] = {}
    used_keys: set[str] = set()
    for band_index, band in enumerate(aligned_bands):
        key = SpectralSample.band_key(band.wavelength_nm)
        if key in used_keys:
            raise ValueError(
                "Mixed image bundle contains duplicate wavelength key "
                f"{key!r}; each imported wavelength must be unique."
            )
        used_keys.add(key)
        target_bands[key] = band.data
        band_status[key] = "exact"
        band_mappings[key] = BandMapping(
            target_wavelength=float(band.wavelength_nm),
            status="exact",
            source_indices=(band_index,),
            source_wavelengths=(float(band.wavelength_nm),),
            weights=(1.0,),
            distance_nm=0.0,
            note=f"Imported from {band.input_path} as role {band.role}.",
        )

    dimensions = {
        "shape": list(data.shape),
        "height": int(data.shape[0]),
        "width": int(data.shape[1]),
        "bands": int(data.shape[2]),
    }
    band_records = [_band_metadata(band, index) for index, band in enumerate(aligned_bands)]
    channel_role_labels = [band.label for band in aligned_bands]

    metadata: dict[str, Any] = {
        "input_path": str(spec_file),
        "mixed_bundle_spec_path": str(spec_file),
        "sample_id": str(spec.get("sample_id") or spec_file.stem),
        "dimensions": dimensions,
        "mock_flag": False,
        "source_type": "mixed_image_bundle",
        "loader_notes": [
            f"Loaded mixed image bundle spec: {spec_file.name}",
            "RGB channels use approximate display-channel wavelength labels.",
        ],
        "imported_files": imported_files,
        "bands": band_records,
        "roles": {band.label: band.role for band in aligned_bands},
        "wavelengths": {band.label: float(band.wavelength_nm) for band in aligned_bands},
        "channel_role_labels": channel_role_labels,
        "channel_wavelength_labels_nm": {
            band.label: float(band.wavelength_nm) for band in aligned_bands
        },
        "alignment": alignment_metadata,
        "alignment_status": alignment_metadata["status"],
        "source_data_kind": "mixed_image_data",
        "analysis_data_kind": "mixed_image_intensity",
        "adapter_used": "mixed_image_bundle_loader",
        "is_reflectance": False,
        "calibration_applied": False,
    }

    return SpectralSample(
        source_type="mixed_image_bundle",
        available_wavelengths=wavelengths,
        data=data,
        target_bands=target_bands,
        band_status=band_status,
        band_mappings=band_mappings,
        metadata=metadata,
    )


def _entries_from_spec(spec: Mapping[str, Any]) -> list[Mapping[str, Any]]:
    """Return normalized image entries from a parsed spec."""

    raw_entries = (
        spec.get("entries")
        or spec.get("images")
        or spec.get("files")
    )
    if raw_entries is None:
        raise ValueError("Mixed image bundle spec must include an 'entries' list.")
    if not isinstance(raw_entries, Sequence) or isinstance(raw_entries, (str, bytes)):
        raise ValueError("Mixed image bundle 'entries' must be a list.")

    entries: list[Mapping[str, Any]] = []
    for index, entry in enumerate(raw_entries):
        if not isinstance(entry, Mapping):
            raise ValueError(f"Mixed image bundle entry {index} must be an object.")
        entries.append(entry)
    return entries


def _entry_path(entry: Mapping[str, Any], base_dir: Path) -> Path:
    """Resolve an entry path relative to the spec file."""

    raw_path = entry.get("path") or entry.get("file") or entry.get("source")
    if not raw_path:
        raise ValueError("Mixed image bundle entry is missing a 'path'.")

    path = Path(str(raw_path)).expanduser()
    if not path.is_absolute():
        path = base_dir / path
    if not path.exists():
        raise FileNotFoundError(f"Mixed image bundle file not found: {path}")
    return path


def _image_id(entry: Mapping[str, Any], entry_index: int) -> str:
    """Return a stable source-image id for alignment grouping."""

    raw_id = entry.get("id") or entry.get("image_id") or entry.get("source_image_id")
    if raw_id:
        return str(raw_id)
    return f"image_{entry_index + 1:03d}"


def _load_entry_bands(
    entry: Mapping[str, Any],
    path: Path,
    entry_index: int,
) -> list[_LoadedBand]:
    """Load all bands produced by one spec entry."""

    entry_type = _entry_type(entry)
    if entry_type == "rgb":
        return _load_rgb_entry(entry, path, entry_index)
    if entry_type in {"gray", "greyscale", "grayscale", "single_band"}:
        return [_load_grayscale_entry(entry, path, entry_index)]
    raise ValueError(
        f"Unsupported mixed image entry type {entry_type!r}; "
        "expected 'rgb' or 'grayscale'."
    )


def _entry_type(entry: Mapping[str, Any]) -> str:
    """Infer the entry type when the spec omits an explicit type."""

    value = entry.get("type") or entry.get("kind") or entry.get("source_type")
    if value is None:
        return "rgb" if (entry.get("channels") or entry.get("channel_map")) else "grayscale"
    return str(value).strip().lower()


def _load_rgb_entry(
    entry: Mapping[str, Any],
    path: Path,
    entry_index: int,
) -> list[_LoadedBand]:
    """Load selected channels from one RGB-like image entry."""

    with Image.open(path) as image:
        rgb = image.convert("RGB")
        image_mode = image.mode
        image_size = image.size
        array = np.asarray(rgb, dtype=np.float32) / 255.0

    bands: list[_LoadedBand] = []
    for channel_spec in _rgb_channel_specs(entry):
        channel_name = _channel_name(channel_spec)
        channel_index = _channel_index(channel_name)
        role = _role(channel_spec, RGB_CHANNEL_ROLES[channel_name])
        wavelength = _wavelength(channel_spec, RGB_CHANNEL_WAVELENGTHS_NM[channel_name])
        label = _label(channel_spec, role, wavelength, channel_name)
        band_data = array[:, :, channel_index].astype(np.float32, copy=False)
        bands.append(
            _LoadedBand(
                data=band_data,
                path=path,
                input_path=str(entry.get("path") or entry.get("file") or path),
                entry_index=entry_index,
                image_id=_image_id(entry, entry_index),
                role=role,
                wavelength_nm=wavelength,
                label=label,
                source_channel=channel_name,
                source_channel_index=channel_index,
                original_shape=(int(band_data.shape[0]), int(band_data.shape[1])),
                image_mode=image_mode,
                image_size=(int(image_size[0]), int(image_size[1])),
            )
        )
    return bands


def _load_grayscale_entry(
    entry: Mapping[str, Any],
    path: Path,
    entry_index: int,
) -> _LoadedBand:
    """Load one single-band image entry."""

    role = _role(entry, None)
    wavelength = _wavelength(entry, None)
    label = _label(entry, role, wavelength, None)

    with Image.open(path) as image:
        image_mode = image.mode
        image_size = image.size
        array = _grayscale_array(image)

    return _LoadedBand(
        data=array,
        path=path,
        input_path=str(entry.get("path") or entry.get("file") or path),
        entry_index=entry_index,
        image_id=_image_id(entry, entry_index),
        role=role,
        wavelength_nm=wavelength,
        label=label,
        source_channel=None,
        source_channel_index=None,
        original_shape=(int(array.shape[0]), int(array.shape[1])),
        image_mode=image_mode,
        image_size=(int(image_size[0]), int(image_size[1])),
    )


def _rgb_channel_specs(entry: Mapping[str, Any]) -> list[Mapping[str, Any]]:
    """Return channel specs for an RGB entry, using defaults when omitted."""

    raw_channels = entry.get("channels") or entry.get("channel_map")
    if raw_channels is None:
        return [
            {"channel": "R", "role": "RED", "wavelength": 650.0},
            {"channel": "G", "role": "GREEN", "wavelength": 556.0},
            {"channel": "B", "role": "BLUE", "wavelength": 532.0},
        ]

    if isinstance(raw_channels, Mapping):
        channel_specs: list[Mapping[str, Any]] = []
        for channel, config in raw_channels.items():
            if isinstance(config, Mapping):
                merged = dict(config)
                merged.setdefault("channel", channel)
            else:
                merged = {"channel": channel, "role": str(config)}
            channel_specs.append(merged)
        return channel_specs

    if isinstance(raw_channels, Sequence) and not isinstance(raw_channels, (str, bytes)):
        channel_specs = []
        for item in raw_channels:
            if isinstance(item, Mapping):
                channel_specs.append(item)
            else:
                channel_specs.append({"channel": item})
        return channel_specs

    raise ValueError("RGB entry 'channels' must be an object or list.")


def _grayscale_array(image: Image.Image) -> np.ndarray:
    """Return a normalized 2D float array for a single-band image."""

    if image.mode in {"1", "L", "I", "I;16", "I;16B", "I;16L", "F"}:
        array = np.asarray(image)
    else:
        array = np.asarray(image.convert("L"))

    if array.ndim != 2:
        array = np.asarray(image.convert("L"))

    normalized = _normalize_intensity_array(array)
    return normalized.astype(np.float32, copy=False)


def _normalize_intensity_array(array: np.ndarray) -> np.ndarray:
    """Normalize integer image data to 0..1 while preserving float arrays."""

    values = np.asarray(array)
    if values.dtype.kind == "b":
        return values.astype(np.float32)
    if values.dtype.kind in {"u", "i"}:
        info = np.iinfo(values.dtype)
        if info.min < 0:
            shifted = values.astype(np.float32) - float(info.min)
            return shifted / float(info.max - info.min)
        return values.astype(np.float32) / float(info.max)

    return values.astype(np.float32, copy=False)


def _channel_name(channel_spec: Mapping[str, Any]) -> str:
    """Return a canonical RGB channel name."""

    raw_channel = (
        channel_spec.get("channel")
        or channel_spec.get("name")
        or channel_spec.get("source_channel")
    )
    if raw_channel is None:
        raise ValueError("RGB channel spec is missing a 'channel'.")

    channel = str(raw_channel).strip().upper()
    if channel not in _CHANNEL_INDEXES:
        raise ValueError(f"Unsupported RGB channel {raw_channel!r}; expected R, G, or B.")

    index = _CHANNEL_INDEXES[channel]
    return ("R", "G", "B")[index]


def _channel_index(channel_name: str) -> int:
    """Return the RGB channel index for ``channel_name``."""

    return _CHANNEL_INDEXES[channel_name]


def _role(config: Mapping[str, Any], default: str | None) -> str:
    """Extract and normalize a semantic role label."""

    value = config.get("role") or config.get("band_role") or default
    if value is None:
        raise ValueError("Mixed image entry is missing a semantic 'role'.")
    return str(value).strip().upper()


def _wavelength(config: Mapping[str, Any], default: float | None) -> float:
    """Extract a wavelength in nanometers."""

    value = config.get("wavelength_nm")
    if value is None:
        value = config.get("wavelength")
    if value is None:
        value = config.get("nm")
    if value is None:
        path_value = config.get("path") or config.get("file") or config.get("source")
        if path_value is not None:
            value = infer_wavelength_from_filename(str(path_value))
    if value is None:
        value = default
    if value is None:
        raise ValueError("Mixed image entry is missing a 'wavelength' in nanometers.")

    wavelength = float(value)
    if not np.isfinite(wavelength) or wavelength <= 0:
        raise ValueError(f"Invalid wavelength value: {value!r}")
    return wavelength


def _label(
    config: Mapping[str, Any],
    role: str,
    wavelength_nm: float,
    channel_name: str | None,
) -> str:
    """Build a stable channel/role label for metadata."""

    raw_label = config.get("label") or config.get("name")
    if raw_label:
        return str(raw_label)

    prefix = channel_name if channel_name is not None else role
    return f"{prefix}_{SpectralSample.band_key(wavelength_nm)}"


def _alignment_config(spec: Mapping[str, Any]) -> dict[str, Any]:
    """Normalize alignment config from the bundle spec."""

    raw = spec.get("alignment", {"mode": "resize_to_reference"})
    if raw is None:
        raw = {"mode": "resize_to_reference"}
    if isinstance(raw, str):
        raw = {"mode": raw}
    if not isinstance(raw, Mapping):
        raise ValueError("Mixed image bundle 'alignment' must be a string or object.")

    mode = normalize_alignment_mode(str(raw.get("mode") or "resize_only"))

    resample = str(raw.get("resample") or raw.get("interpolation") or "bilinear").strip().lower()
    if resample not in _RESAMPLE_FILTERS:
        raise ValueError("Alignment resample must be 'nearest' or 'bilinear'.")

    reference = raw.get("reference", None)
    if reference is None:
        reference = raw.get("reference_path", None)
    if reference is None:
        reference = raw.get("reference_image_id", "first")

    return {
        "mode": mode,
        "reference": reference,
        "resample": resample,
        "transform_model": normalize_transform_model(str(raw.get("transform_model") or raw.get("model") or "affine")),
    }


def _align_bands(
    bands: Sequence[_LoadedBand],
    alignment: Mapping[str, Any],
) -> tuple[list[_LoadedBand], dict[str, Any]]:
    """Align full source images globally and return alignment metadata."""

    grouped = _group_bands_by_image(bands)
    reference_group = _reference_group_key(bands, alignment.get("reference", "first"))
    reference_bands = grouped[reference_group]
    reference_image = _representative_image(reference_bands)
    reference_shape = (int(reference_image.shape[0]), int(reference_image.shape[1]))
    mode = str(alignment["mode"])
    resample = str(alignment["resample"])
    transform_model = str(alignment.get("transform_model", "affine"))

    transform_records: list[dict[str, Any]] = []
    aligned: list[_LoadedBand] = []

    for image_id, image_bands in grouped.items():
        representative = _representative_image(image_bands)
        if image_id == reference_group:
            transform = AlignmentTransform(
                requested_mode=mode,
                mode="reference",
                transform_model=transform_model,
                applied_model="identity",
                status="reference",
                success=True,
                reference_shape=reference_shape,
                moving_shape=(int(representative.shape[0]), int(representative.shape[1])),
                output_shape=reference_shape,
                matrix=np.eye(3, dtype=float),
                message="Reference image; no moving transform applied.",
            )
        else:
            transform = compute_alignment_transform(
                representative,
                reference_image,
                mode=mode,
                transform_model=transform_model,
                resample=resample,
            )

        transform_records.append(
            {
                **transform.to_dict(),
                "image_id": image_id,
                "bands": [band.label for band in image_bands],
                "is_reference": image_id == reference_group,
            }
        )

        for band in image_bands:
            aligned_data = (
                np.asarray(band.data, dtype=np.float32)
                if image_id == reference_group
                else apply_alignment_transform(band.data, transform, resample=resample)
            )
            if aligned_data.shape != reference_shape:
                resize_transform = compute_alignment_transform(
                    aligned_data,
                    reference_image,
                    mode="resize_only",
                    transform_model=transform_model,
                    resample=resample,
                )
                aligned_data = apply_alignment_transform(aligned_data, resize_transform, resample=resample)
            aligned.append(
                _LoadedBand(
                    data=np.asarray(aligned_data, dtype=np.float32),
                    path=band.path,
                    input_path=band.input_path,
                    entry_index=band.entry_index,
                    image_id=band.image_id,
                    role=band.role,
                    wavelength_nm=band.wavelength_nm,
                    label=band.label,
                    source_channel=band.source_channel,
                    source_channel_index=band.source_channel_index,
                    original_shape=band.original_shape,
                    image_mode=band.image_mode,
                    image_size=band.image_size,
                )
            )

    non_reference = [record for record in transform_records if not record["is_reference"]]
    if any(record["status"] == "fallback_resize_only" for record in non_reference):
        status = "fallback_resize_only"
    elif any(record["status"] == "aligned" for record in non_reference):
        status = "aligned"
    elif any(record["status"] == "resized" for record in non_reference):
        status = "resized"
    elif mode == "none":
        status = "strict_match"
    else:
        status = "not_required"

    metadata = {
        "mode": mode,
        "transform_model": transform_model,
        "reference": alignment.get("reference", "first"),
        "reference_image_id": reference_group,
        "reference_shape": list(reference_shape),
        "resample": resample,
        "status": status,
        "transforms": transform_records,
        "warning": _alignment_warning(mode, status, transform_records),
    }
    return aligned, metadata


def _group_bands_by_image(bands: Sequence[_LoadedBand]) -> dict[str, list[_LoadedBand]]:
    """Group loaded bands by source image id while preserving order."""

    grouped: dict[str, list[_LoadedBand]] = {}
    for band in bands:
        grouped.setdefault(band.image_id, []).append(band)
    return grouped


def _reference_group_key(bands: Sequence[_LoadedBand], reference: Any) -> str:
    """Resolve an alignment reference to a source-image group key."""

    if reference in (None, "first"):
        return bands[0].image_id
    if isinstance(reference, Sequence) and not isinstance(reference, (str, bytes)):
        return bands[0].image_id

    reference_text = str(reference)
    for band in bands:
        if reference_text in {
            band.image_id,
            band.label,
            band.role,
            band.input_path,
            band.path.name,
            str(band.path),
        }:
            return band.image_id

    raise ValueError(f"Could not resolve alignment reference {reference!r}.")


def _representative_image(bands: Sequence[_LoadedBand]) -> np.ndarray:
    """Return one grayscale representative for a source image group."""

    for preferred_role in ("GREEN", "RED", "NIR"):
        for band in bands:
            if band.role == preferred_role:
                return np.asarray(band.data, dtype=np.float32)
    stack = np.stack([np.asarray(band.data, dtype=np.float32) for band in bands], axis=0)
    return np.nanmean(stack, axis=0).astype(np.float32)


def _alignment_warning(mode: str, status: str, records: Sequence[Mapping[str, Any]]) -> str:
    """Build a compact alignment warning for reports."""

    warnings = [str(record.get("warning")) for record in records if record.get("warning")]
    if mode == "resize_only" or status == "resized":
        warnings.append("resize-only alignment is low confidence; no automatic registration was performed")
    if status == "fallback_resize_only":
        warnings.append("one or more automatic image registrations failed and fell back to resize-only")
    return "; ".join(dict.fromkeys(warnings))


def _imported_file_record(
    entry: Mapping[str, Any],
    path: Path,
    bands: Sequence[_LoadedBand],
) -> dict[str, Any]:
    """Build a metadata record for one imported source file."""

    return {
        "path": str(path),
        "input_path": str(entry.get("path") or entry.get("file") or path),
        "entry_index": int(bands[0].entry_index) if bands else None,
        "image_id": bands[0].image_id if bands else None,
        "type": _entry_type(entry),
        "image_mode": bands[0].image_mode if bands else None,
        "image_size": list(bands[0].image_size) if bands else None,
        "bands": [band.label for band in bands],
    }


def _band_metadata(band: _LoadedBand, band_index: int) -> dict[str, Any]:
    """Return a JSON-friendly metadata record for one imported band."""

    return {
        "index": int(band_index),
        "image_id": band.image_id,
        "label": band.label,
        "role": band.role,
        "wavelength_nm": float(band.wavelength_nm),
        "path": str(band.path),
        "input_path": band.input_path,
        "source_channel": band.source_channel,
        "source_channel_index": band.source_channel_index,
        "original_shape": list(band.original_shape),
        "aligned_shape": [int(band.data.shape[0]), int(band.data.shape[1])],
    }


__all__ = [
    "RGB_CHANNEL_ROLES",
    "RGB_CHANNEL_WAVELENGTHS_NM",
    "load_mixed_image_bundle",
    "read_mixed_image_bundle_spec",
    "write_mixed_image_bundle_spec",
]
