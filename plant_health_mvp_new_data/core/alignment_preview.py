"""Alignment preview artifacts shared by the viewer and analysis apps.

The mixed-image importer performs alignment on scientific arrays. This module
builds display-only preview images from that same imported sample metadata so
both GUI apps can show the same reference, moving-before, moving-after, and
comparison overlays without duplicating alignment logic.
"""

from __future__ import annotations

from dataclasses import dataclass
import json
from pathlib import Path
from typing import Any, Mapping, Sequence

import numpy as np
from PIL import Image

from .models.sample import SpectralSample
from .visual_overlays import read_uint8_image, save_uint8_image


@dataclass(slots=True)
class AlignmentPreview:
    """Display-only alignment preview package."""

    reference_image: np.ndarray
    moving_before: np.ndarray
    moving_after: np.ndarray
    overlay_before: np.ndarray
    overlay_after: np.ndarray
    metadata: dict[str, Any]


def build_alignment_preview(
    sample: SpectralSample,
    *,
    moving_image_id: str | None = None,
) -> AlignmentPreview | None:
    """Build display images for visually checking mixed-input alignment.

    Returns ``None`` when the sample does not contain mixed-image alignment
    metadata or when there is no non-reference moving image to compare.
    """

    alignment = sample.metadata.get("alignment")
    bands = sample.metadata.get("bands")
    imported_files = sample.metadata.get("imported_files")
    if not isinstance(alignment, Mapping) or not isinstance(bands, Sequence):
        return None
    if not isinstance(imported_files, Sequence):
        return None

    transforms = alignment.get("transforms", [])
    if not isinstance(transforms, Sequence):
        return None

    reference_id = str(alignment.get("reference_image_id") or "")
    moving_record = _choose_moving_record(transforms, moving_image_id)
    if moving_record is None:
        return None
    moving_id = str(moving_record.get("image_id") or "")
    if not reference_id or not moving_id:
        return None

    reference_source = _source_image_for_group(imported_files, reference_id)
    moving_source = _source_image_for_group(imported_files, moving_id)
    moving_after = _aligned_representative_for_group(sample, bands, moving_id)
    reference_after = _aligned_representative_for_group(sample, bands, reference_id)

    reference_gray = _display_gray(reference_after if reference_after is not None else reference_source)
    moving_before_gray = _resize_display(_display_gray(moving_source), reference_gray.shape)
    moving_after_gray = _resize_display(_display_gray(moving_after), reference_gray.shape)

    metadata = {
        "alignment_mode": alignment.get("mode"),
        "transform_model": alignment.get("transform_model"),
        "status": moving_record.get("status") or alignment.get("status"),
        "confidence": moving_record.get("confidence"),
        "reference_image_id": reference_id,
        "moving_image_id": moving_id,
        "reference_shape": alignment.get("reference_shape"),
        "moving_shape": moving_record.get("moving_shape"),
        "output_shape": moving_record.get("output_shape"),
        "warning": moving_record.get("warning") or alignment.get("warning") or "",
        "message": moving_record.get("message") or "",
        "applied_model": moving_record.get("applied_model"),
        "matrix": moving_record.get("matrix"),
        "bands": moving_record.get("bands", []),
    }

    return AlignmentPreview(
        reference_image=_resize_display(_display_rgb(reference_source), reference_gray.shape),
        moving_before=_resize_display(_display_rgb(moving_source), reference_gray.shape),
        moving_after=_resize_display(_display_rgb(moving_after), reference_gray.shape),
        overlay_before=build_alignment_overlay(reference_gray, moving_before_gray),
        overlay_after=build_alignment_overlay(reference_gray, moving_after_gray),
        metadata=metadata,
    )


def build_alignment_overlay(reference: np.ndarray, moving: np.ndarray, *, opacity: float = 0.55) -> np.ndarray:
    """Build a red/green comparison overlay for alignment inspection.

    The reference image is shown in green/cyan and the moving image in red.
    Yellow/gray areas indicate stronger overlap.
    """

    ref = _normalize_uint8(reference)
    mov = _resize_display(_normalize_uint8(moving), ref.shape)
    alpha = float(np.clip(opacity, 0.0, 1.0))
    output = np.zeros((*ref.shape, 3), dtype=np.float32)
    output[:, :, 0] = mov.astype(np.float32)
    output[:, :, 1] = ref.astype(np.float32)
    output[:, :, 2] = (1.0 - alpha) * ref.astype(np.float32)
    return np.clip(output, 0, 255).astype(np.uint8)


def export_alignment_preview_artifacts(sample: SpectralSample, output_dir: str | Path) -> dict[str, Any]:
    """Save shared alignment preview images beside analysis outputs."""

    preview = build_alignment_preview(sample)
    if preview is None:
        return {}

    folder = Path(output_dir) / "alignment_preview"
    paths = {
        "reference_image": save_uint8_image(preview.reference_image, folder / "reference_image.png"),
        "moving_before": save_uint8_image(preview.moving_before, folder / "moving_before_alignment.png"),
        "moving_after": save_uint8_image(preview.moving_after, folder / "moving_after_alignment.png"),
        "overlay_before": save_uint8_image(preview.overlay_before, folder / "overlay_before_alignment.png"),
        "overlay_after": save_uint8_image(preview.overlay_after, folder / "overlay_after_alignment.png"),
    }
    metadata_path = folder / "alignment_preview.json"
    metadata_path.parent.mkdir(parents=True, exist_ok=True)
    metadata_path.write_text(json.dumps(preview.metadata, indent=2, default=str) + "\n", encoding="utf-8")
    return {
        "directory": str(folder),
        "metadata": str(metadata_path),
        **{key: str(path) for key, path in paths.items()},
    }


def load_alignment_preview_artifacts(output_dir: str | Path) -> AlignmentPreview | None:
    """Load previously exported alignment preview artifacts."""

    folder = Path(output_dir) / "alignment_preview"
    metadata_path = folder / "alignment_preview.json"
    required = {
        "reference_image": folder / "reference_image.png",
        "moving_before": folder / "moving_before_alignment.png",
        "moving_after": folder / "moving_after_alignment.png",
        "overlay_before": folder / "overlay_before_alignment.png",
        "overlay_after": folder / "overlay_after_alignment.png",
    }
    if not metadata_path.exists() or not all(path.exists() for path in required.values()):
        return None
    metadata = json.loads(metadata_path.read_text(encoding="utf-8"))
    return AlignmentPreview(
        reference_image=read_uint8_image(required["reference_image"]),
        moving_before=read_uint8_image(required["moving_before"]),
        moving_after=read_uint8_image(required["moving_after"]),
        overlay_before=read_uint8_image(required["overlay_before"]),
        overlay_after=read_uint8_image(required["overlay_after"]),
        metadata=metadata,
    )


def _choose_moving_record(
    transforms: Sequence[Any],
    moving_image_id: str | None,
) -> Mapping[str, Any] | None:
    """Return the transform record for the moving image to preview."""

    candidates = [item for item in transforms if isinstance(item, Mapping) and not item.get("is_reference")]
    if not candidates:
        return None
    if moving_image_id:
        for record in candidates:
            if str(record.get("image_id")) == str(moving_image_id):
                return record
    return candidates[0]


def _source_image_for_group(imported_files: Sequence[Any], image_id: str) -> np.ndarray:
    """Load the original source image for an imported image group."""

    for record in imported_files:
        if not isinstance(record, Mapping) or str(record.get("image_id")) != image_id:
            continue
        path = record.get("path") or record.get("input_path")
        if not path:
            break
        with Image.open(Path(str(path)).expanduser()) as image:
            if str(record.get("type", "")).lower() == "rgb":
                return np.asarray(image.convert("RGB"), dtype=np.uint8)
            return np.asarray(image.convert("L"), dtype=np.uint8)
    raise ValueError(f"Could not load alignment preview source image {image_id!r}.")


def _aligned_representative_for_group(
    sample: SpectralSample,
    band_records: Sequence[Any],
    image_id: str,
) -> np.ndarray | None:
    """Build an aligned display representative for one source image group."""

    if sample.data is None or sample.data.ndim < 3:
        return None

    records = [
        item for item in band_records
        if isinstance(item, Mapping) and str(item.get("image_id")) == image_id
    ]
    if not records:
        return None

    role_to_index: dict[str, int] = {}
    indexes: list[int] = []
    for record in records:
        try:
            index = int(record.get("index"))
        except (TypeError, ValueError):
            continue
        if 0 <= index < sample.data.shape[-1]:
            indexes.append(index)
            role = str(record.get("role", "")).upper()
            if role:
                role_to_index[role] = index

    if {"RED", "GREEN", "BLUE"}.issubset(role_to_index):
        return np.stack(
            [
                _normalize_uint8(sample.data[:, :, role_to_index["RED"]]),
                _normalize_uint8(sample.data[:, :, role_to_index["GREEN"]]),
                _normalize_uint8(sample.data[:, :, role_to_index["BLUE"]]),
            ],
            axis=-1,
        )
    if not indexes:
        return None
    stack = np.stack([np.asarray(sample.data[:, :, index], dtype=float) for index in indexes], axis=0)
    return _normalize_uint8(np.nanmean(stack, axis=0))


def _display_gray(image: np.ndarray | None) -> np.ndarray:
    """Return a uint8 grayscale display image."""

    if image is None:
        raise ValueError("Alignment preview image is missing.")
    array = np.asarray(image)
    if array.ndim == 3:
        rgb = array[:, :, :3].astype(float)
        return _normalize_uint8(0.299 * rgb[:, :, 0] + 0.587 * rgb[:, :, 1] + 0.114 * rgb[:, :, 2])
    return _normalize_uint8(array)


def _display_rgb(image: np.ndarray | None) -> np.ndarray:
    """Return a uint8 RGB display image."""

    gray = _display_gray(image)
    array = np.asarray(image) if image is not None else gray
    if array.ndim == 3 and array.shape[2] >= 3:
        return np.asarray(array[:, :, :3], dtype=np.uint8)
    return np.repeat(gray[:, :, None], 3, axis=2)


def _resize_display(image: np.ndarray, shape: tuple[int, int]) -> np.ndarray:
    """Resize a display image to ``shape`` as ``(height, width)``."""

    array = np.asarray(image, dtype=np.uint8)
    if array.shape[:2] == shape:
        return array
    pil = Image.fromarray(array)
    resized = pil.resize((int(shape[1]), int(shape[0])), resample=Image.Resampling.BILINEAR)
    return np.asarray(resized, dtype=np.uint8)


def _normalize_uint8(image: np.ndarray) -> np.ndarray:
    """Normalize arbitrary numeric image data to uint8 for display only."""

    array = np.asarray(image, dtype=float)
    if array.dtype == np.uint8:
        return array
    finite = array[np.isfinite(array)]
    if finite.size == 0:
        return np.zeros(array.shape, dtype=np.uint8)
    low = float(np.percentile(finite, 1.0))
    high = float(np.percentile(finite, 99.0))
    if high <= low:
        high = float(np.max(finite))
        low = float(np.min(finite))
    if high <= low:
        return np.zeros(array.shape, dtype=np.uint8)
    scaled = (array - low) / (high - low)
    return np.clip(scaled * 255.0, 0.0, 255.0).astype(np.uint8)


__all__ = [
    "AlignmentPreview",
    "build_alignment_overlay",
    "build_alignment_preview",
    "export_alignment_preview_artifacts",
    "load_alignment_preview_artifacts",
]
