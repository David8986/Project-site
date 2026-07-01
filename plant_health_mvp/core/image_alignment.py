"""Global image-registration helpers for mixed-image analysis.

The functions here align complete image frames before vegetation masking or
per-pixel spectral analysis. They operate on 2D float arrays and keep the
result metadata explicit so reports can distinguish real registration from
resize-only fallback.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Mapping, Sequence

import numpy as np
from PIL import Image


VALID_ALIGNMENT_MODES = {
    "none",
    "resize_only",
    "automatic_ecc",
    "automatic_ecc_affine",
    "automatic_phase_ecc",
    "automatic_feature_edge",
    "automatic_contour_mask",
    "automatic_mask_then_ecc",
}

VALID_TRANSFORM_MODELS = {"translation", "euclidean", "affine", "homography"}

_RESAMPLE_FILTERS: dict[str, int] = {
    "nearest": Image.Resampling.NEAREST,
    "bilinear": Image.Resampling.BILINEAR,
}


@dataclass(frozen=True, slots=True)
class AlignmentTransform:
    """A computed global transform from one moving image to the reference."""

    requested_mode: str
    mode: str
    transform_model: str
    applied_model: str
    status: str
    success: bool
    reference_shape: tuple[int, int]
    moving_shape: tuple[int, int]
    output_shape: tuple[int, int]
    matrix: np.ndarray | None = None
    pre_resize: bool = False
    inverse_map: bool = False
    confidence: float | None = None
    quality_before: float | None = None
    quality_after: float | None = None
    overlap_fraction: float | None = None
    stages: tuple[dict[str, Any], ...] = field(default_factory=tuple)
    warning: str = ""
    message: str = ""

    def to_dict(self) -> dict[str, Any]:
        """Return JSON-friendly metadata for reports."""

        return {
            "requested_mode": self.requested_mode,
            "mode": self.mode,
            "transform_model": self.transform_model,
            "applied_model": self.applied_model,
            "status": self.status,
            "success": bool(self.success),
            "reference_shape": list(self.reference_shape),
            "moving_shape": list(self.moving_shape),
            "output_shape": list(self.output_shape),
            "matrix": None if self.matrix is None else np.asarray(self.matrix, dtype=float).tolist(),
            "pre_resize": bool(self.pre_resize),
            "inverse_map": bool(self.inverse_map),
            "confidence": None if self.confidence is None else float(self.confidence),
            "quality_before": None if self.quality_before is None else float(self.quality_before),
            "quality_after": None if self.quality_after is None else float(self.quality_after),
            "overlap_fraction": None if self.overlap_fraction is None else float(self.overlap_fraction),
            "stages": _json_safe_stages(self.stages),
            "warning": self.warning,
            "message": self.message,
        }


def normalize_alignment_mode(mode: str | None) -> str:
    """Normalize user-facing alignment mode names."""

    text = (mode or "resize_only").strip().lower().replace(" ", "_").replace("-", "_")
    aliases = {
        "resize": "resize_only",
        "resize_to_reference": "resize_only",
        "strict": "none",
        "no_resize": "none",
        "ecc": "automatic_ecc",
        "automatic": "automatic_ecc",
        "ecc_affine": "automatic_ecc_affine",
        "affine_ecc": "automatic_ecc_affine",
        "phase": "automatic_phase_ecc",
        "phase_ecc": "automatic_phase_ecc",
        "masked_phase_ecc": "automatic_phase_ecc",
        "feature": "automatic_feature_edge",
        "feature_edge": "automatic_feature_edge",
        "edge": "automatic_feature_edge",
        "contour": "automatic_contour_mask",
        "mask": "automatic_contour_mask",
        "contour_mask": "automatic_contour_mask",
        "mask_ecc": "automatic_mask_then_ecc",
        "mask_then_ecc": "automatic_mask_then_ecc",
        "contour_then_ecc": "automatic_mask_then_ecc",
    }
    normalized = aliases.get(text, text)
    if normalized not in VALID_ALIGNMENT_MODES:
        raise ValueError(f"Unsupported alignment mode: {mode}")
    return normalized


def normalize_transform_model(model: str | None) -> str:
    """Normalize user-facing transform model names."""

    text = (model or "affine").strip().lower().replace(" ", "_").replace("-", "_")
    aliases = {
        "rigid": "euclidean",
        "similarity": "euclidean",
        "partial_affine": "euclidean",
        "projective": "homography",
    }
    normalized = aliases.get(text, text)
    if normalized not in VALID_TRANSFORM_MODELS:
        raise ValueError(f"Unsupported transform model: {model}")
    return normalized


def compute_alignment_transform(
    moving: np.ndarray,
    reference: np.ndarray,
    *,
    mode: str = "resize_only",
    transform_model: str = "affine",
    resample: str = "bilinear",
) -> AlignmentTransform:
    """Compute a global transform that maps ``moving`` into ``reference`` space."""

    mode_key = normalize_alignment_mode(mode)
    model_key = normalize_transform_model(transform_model)
    if resample not in _RESAMPLE_FILTERS:
        raise ValueError("Alignment resample must be 'nearest' or 'bilinear'.")

    reference_array = _as_float_2d(reference)
    moving_array = _as_float_2d(moving)
    reference_shape = _shape2(reference_array)
    moving_shape = _shape2(moving_array)

    if mode_key == "none":
        if moving_shape != reference_shape:
            raise ValueError(
                "Mixed image bundle contains mismatched shapes and alignment mode is 'none': "
                f"{moving_shape} != {reference_shape}."
            )
        return AlignmentTransform(
            requested_mode=mode_key,
            mode=mode_key,
            transform_model=model_key,
            applied_model="identity",
            status="strict_match",
            success=True,
            reference_shape=reference_shape,
            moving_shape=moving_shape,
            output_shape=reference_shape,
            matrix=np.eye(3, dtype=float),
            message="No alignment transform requested; shapes already match.",
        )

    if mode_key == "resize_only":
        return _resize_transform(mode_key, model_key, reference_shape, moving_shape)

    resized_moving = moving_array
    pre_resize = moving_shape != reference_shape
    if pre_resize and mode_key not in {"automatic_phase_ecc", "automatic_mask_then_ecc"}:
        resized_moving = resize_image(moving_array, reference_shape, resample=resample)

    try:
        if mode_key in {"automatic_ecc", "automatic_ecc_affine"}:
            return _ecc_transform(
                resized_moving,
                reference_array,
                requested_mode=mode_key,
                model="affine" if mode_key == "automatic_ecc_affine" else model_key,
                moving_shape=moving_shape,
                pre_resize=pre_resize,
            )
        if mode_key == "automatic_phase_ecc":
            return _phase_then_ecc_transform(
                moving_array,
                reference_array,
                requested_mode=mode_key,
                model=model_key,
                resample=resample,
            )
        if mode_key == "automatic_feature_edge":
            return _feature_edge_transform(
                resized_moving,
                reference_array,
                requested_mode=mode_key,
                model=model_key,
                moving_shape=moving_shape,
                pre_resize=pre_resize,
            )
        if mode_key == "automatic_contour_mask":
            return _contour_mask_transform(
                resized_moving,
                reference_array,
                requested_mode=mode_key,
                model=model_key,
                moving_shape=moving_shape,
                pre_resize=pre_resize,
            )
        if mode_key == "automatic_mask_then_ecc":
            return _mask_then_ecc_transform(
                moving_array,
                reference_array,
                requested_mode=mode_key,
                model=model_key,
                resample=resample,
            )
    except Exception as exc:  # noqa: BLE001 - alignment fallback should keep import usable.
        fallback = _resize_transform(mode_key, model_key, reference_shape, moving_shape)
        return AlignmentTransform(
            requested_mode=mode_key,
            mode="resize_only",
            transform_model=model_key,
            applied_model="resize_only",
            status="fallback_resize_only",
            success=False,
            reference_shape=reference_shape,
            moving_shape=moving_shape,
            output_shape=reference_shape,
            matrix=fallback.matrix,
            pre_resize=moving_shape != reference_shape,
            confidence=0.0,
            warning=(
                f"Automatic alignment mode {mode_key} failed and fell back to resize-only. "
                "Treat alignment confidence as low."
            ),
            message=str(exc),
        )

    return _resize_transform(mode_key, model_key, reference_shape, moving_shape)


def apply_alignment_transform(
    image: np.ndarray,
    transform: AlignmentTransform,
    *,
    resample: str = "bilinear",
) -> np.ndarray:
    """Apply a computed global transform to one full-frame image band."""

    if resample not in _RESAMPLE_FILTERS:
        raise ValueError("Alignment resample must be 'nearest' or 'bilinear'.")

    array = _as_float_2d(image)
    if transform.stages:
        return _apply_alignment_stages(array, transform, resample=resample)

    if transform.applied_model in {"identity", "none"} and _shape2(array) == transform.output_shape:
        return array.astype(np.float32, copy=False)

    working = array
    if transform.pre_resize or _shape2(working) != transform.reference_shape:
        working = resize_image(working, transform.reference_shape, resample=resample)

    if transform.applied_model in {"resize_only", "identity"} or transform.matrix is None:
        return working.astype(np.float32, copy=False)

    try:
        import cv2
    except ImportError as exc:  # pragma: no cover - requirements include OpenCV.
        raise RuntimeError("opencv-python is required for automatic image alignment.") from exc

    height, width = transform.output_shape
    flags = _cv2_interp(resample)
    if transform.inverse_map:
        flags |= cv2.WARP_INVERSE_MAP

    matrix = np.asarray(transform.matrix, dtype=np.float32)
    if transform.applied_model == "homography":
        aligned = cv2.warpPerspective(
            working.astype(np.float32),
            matrix,
            (width, height),
            flags=flags,
            borderMode=cv2.BORDER_CONSTANT,
            borderValue=0,
        )
    else:
        aligned = cv2.warpAffine(
            working.astype(np.float32),
            matrix[:2, :],
            (width, height),
            flags=flags,
            borderMode=cv2.BORDER_CONSTANT,
            borderValue=0,
        )
    return np.asarray(aligned, dtype=np.float32)


def compare_alignment_methods(
    moving: np.ndarray,
    reference: np.ndarray,
    *,
    methods: Sequence[str] | None = None,
    transform_model: str = "affine",
    resample: str = "bilinear",
) -> list[dict[str, Any]]:
    """Compare alignment methods for the same image pair.

    The function is intentionally programmatic so tests and later UI panels can
    benchmark registration choices without duplicating registration code.
    """

    method_names = list(methods or (
        "resize_only",
        "automatic_phase_ecc",
        "automatic_ecc",
        "automatic_feature_edge",
        "automatic_contour_mask",
        "automatic_mask_then_ecc",
    ))
    results: list[dict[str, Any]] = []
    for method in method_names:
        try:
            transform = compute_alignment_transform(
                moving,
                reference,
                mode=method,
                transform_model=transform_model,
                resample=resample,
            )
            aligned = apply_alignment_transform(moving, transform, resample=resample)
            quality = _quality_metrics(_as_float_2d(reference), _as_float_2d(aligned))
            results.append(
                {
                    "method": method,
                    "transform_model": transform.transform_model,
                    "status": transform.status,
                    "success": bool(transform.success),
                    "confidence": transform.confidence,
                    "quality_before": transform.quality_before,
                    "quality_after": transform.quality_after or quality["similarity"],
                    "overlap_fraction": transform.overlap_fraction or quality["overlap_fraction"],
                    "matrix": None if transform.matrix is None else np.asarray(transform.matrix, dtype=float).tolist(),
                    "warning": transform.warning,
                    "message": transform.message,
                }
            )
        except Exception as exc:  # noqa: BLE001 - comparison should keep going.
            results.append(
                {
                    "method": method,
                    "transform_model": transform_model,
                    "status": "failed",
                    "success": False,
                    "confidence": 0.0,
                    "quality_before": None,
                    "quality_after": None,
                    "overlap_fraction": None,
                    "matrix": None,
                    "warning": str(exc),
                    "message": str(exc),
                }
            )
    return results


def resize_image(image: np.ndarray, shape: tuple[int, int], *, resample: str = "bilinear") -> np.ndarray:
    """Resize a 2D float image to ``shape`` as ``(height, width)``."""

    height, width = shape
    pil = Image.fromarray(_as_float_2d(image).astype(np.float32), mode="F")
    resized = pil.resize((int(width), int(height)), resample=_RESAMPLE_FILTERS[resample])
    return np.asarray(resized, dtype=np.float32)


def _resize_transform(
    requested_mode: str,
    model: str,
    reference_shape: tuple[int, int],
    moving_shape: tuple[int, int],
) -> AlignmentTransform:
    """Return a resize-only transform record."""

    changed = moving_shape != reference_shape
    status = "resized" if changed else "not_required"
    warning = "resize-only alignment is low confidence; no image-content registration was performed"
    if not changed:
        warning = ""
    return AlignmentTransform(
        requested_mode=requested_mode,
        mode="resize_only",
        transform_model=model,
        applied_model="resize_only",
        status=status,
        success=True,
        reference_shape=reference_shape,
        moving_shape=moving_shape,
        output_shape=reference_shape,
        matrix=_scale_matrix(moving_shape, reference_shape),
        pre_resize=changed,
        confidence=0.25 if changed else 1.0,
        warning=warning,
        message="Resized moving image to reference shape." if changed else "Shapes already match.",
    )


def _phase_then_ecc_transform(
    moving: np.ndarray,
    reference: np.ndarray,
    *,
    requested_mode: str,
    model: str,
    resample: str,
) -> AlignmentTransform:
    """Run coarse phase correlation followed by ECC fine alignment."""

    reference_shape = _shape2(reference)
    moving_shape = _shape2(moving)
    coarse_matrix, coarse_confidence, coarse_message, coarse_warning = _phase_translation_matrix(moving, reference)
    coarse_stage = _stage_record(
        name="coarse_phase_cross_correlation",
        matrix=coarse_matrix,
        applied_model="translation",
        inverse_map=False,
        output_shape=reference_shape,
        confidence=coarse_confidence,
        message=coarse_message,
        warning=coarse_warning,
    )
    coarse_aligned = _warp_with_stage(moving, coarse_stage, reference_shape, resample=resample)

    fine_transform = _ecc_transform(
        coarse_aligned,
        reference,
        requested_mode=requested_mode,
        model=model,
        moving_shape=reference_shape,
        pre_resize=False,
    )
    stages = (coarse_stage, *_transform_to_stages(fine_transform, stage_name="fine_ecc"))
    aligned = _apply_stages_to_array(moving, stages, reference_shape, resample=resample)
    before = _quality_metrics(reference, _resize_or_canvas(moving, reference_shape, resample=resample))
    after = _quality_metrics(reference, aligned)
    confidence = _combined_confidence([coarse_confidence, fine_transform.confidence, after["similarity"]])
    warning = _quality_warning(after, before)
    if coarse_warning:
        warning = "; ".join(item for item in (coarse_warning, warning) if item)

    return AlignmentTransform(
        requested_mode=requested_mode,
        mode=requested_mode,
        transform_model=model,
        applied_model=f"phase_then_{fine_transform.applied_model}",
        status="aligned",
        success=True,
        reference_shape=reference_shape,
        moving_shape=moving_shape,
        output_shape=reference_shape,
        matrix=_effective_stage_matrix(stages),
        pre_resize=False,
        confidence=confidence,
        quality_before=before["similarity"],
        quality_after=after["similarity"],
        overlap_fraction=after["overlap_fraction"],
        stages=stages,
        warning=warning,
        message=(
            "Coarse phase cross-correlation estimated the initial crop/translation shift; "
            "OpenCV ECC refined the global alignment."
        ),
    )


def _mask_then_ecc_transform(
    moving: np.ndarray,
    reference: np.ndarray,
    *,
    requested_mode: str,
    model: str,
    resample: str,
) -> AlignmentTransform:
    """Run foreground contour/mask alignment followed by ECC fine alignment."""

    reference_shape = _shape2(reference)
    moving_shape = _shape2(moving)
    coarse = _contour_mask_transform(
        moving,
        reference,
        requested_mode=requested_mode,
        model="translation" if model == "translation" else "euclidean",
        moving_shape=moving_shape,
        pre_resize=False,
    )
    coarse_stage = _stage_record(
        name="coarse_contour_mask",
        matrix=np.asarray(coarse.matrix, dtype=float),
        applied_model=coarse.applied_model,
        inverse_map=False,
        output_shape=reference_shape,
        confidence=coarse.confidence,
        message=coarse.message,
        warning=coarse.warning,
    )
    coarse_aligned = _warp_with_stage(moving, coarse_stage, reference_shape, resample=resample)
    fine_transform = _ecc_transform(
        coarse_aligned,
        reference,
        requested_mode=requested_mode,
        model=model,
        moving_shape=reference_shape,
        pre_resize=False,
    )
    stages = (coarse_stage, *_transform_to_stages(fine_transform, stage_name="fine_ecc"))
    aligned = _apply_stages_to_array(moving, stages, reference_shape, resample=resample)
    before = _quality_metrics(reference, _resize_or_canvas(moving, reference_shape, resample=resample))
    after = _quality_metrics(reference, aligned)
    warning = _quality_warning(after, before)

    return AlignmentTransform(
        requested_mode=requested_mode,
        mode=requested_mode,
        transform_model=model,
        applied_model=f"mask_then_{fine_transform.applied_model}",
        status="aligned",
        success=True,
        reference_shape=reference_shape,
        moving_shape=moving_shape,
        output_shape=reference_shape,
        matrix=_effective_stage_matrix(stages),
        pre_resize=False,
        confidence=_combined_confidence([coarse.confidence, fine_transform.confidence, after["similarity"]]),
        quality_before=before["similarity"],
        quality_after=after["similarity"],
        overlap_fraction=after["overlap_fraction"],
        stages=stages,
        warning=warning,
        message="Foreground contour/mask alignment provided a coarse transform; OpenCV ECC refined it.",
    )


def _ecc_transform(
    moving: np.ndarray,
    reference: np.ndarray,
    *,
    requested_mode: str,
    model: str,
    moving_shape: tuple[int, int],
    pre_resize: bool,
) -> AlignmentTransform:
    """Compute an ECC registration transform."""

    import cv2

    motion_type, applied_model, initial = _ecc_motion(model)
    reference_norm = _normalize01(reference).astype(np.float32)
    moving_norm = _normalize01(moving).astype(np.float32)
    criteria = (
        cv2.TERM_CRITERIA_EPS | cv2.TERM_CRITERIA_COUNT,
        80,
        1e-6,
    )
    confidence, warp_matrix = cv2.findTransformECC(
        reference_norm,
        moving_norm,
        initial,
        motion_type,
        criteria,
        None,
        5,
    )
    matrix = _homogeneous_matrix(warp_matrix, applied_model)
    stage = _stage_record(
        name="ecc",
        matrix=matrix,
        applied_model=applied_model,
        inverse_map=True,
        output_shape=_shape2(reference),
        confidence=float(confidence),
        message="OpenCV ECC fine alignment.",
    )
    aligned = _warp_with_stage(moving, stage, _shape2(reference), resample="bilinear")
    before = _quality_metrics(reference, moving)
    after = _quality_metrics(reference, aligned)
    return AlignmentTransform(
        requested_mode=requested_mode,
        mode=requested_mode,
        transform_model=model,
        applied_model=applied_model,
        status="aligned",
        success=True,
        reference_shape=_shape2(reference),
        moving_shape=moving_shape,
        output_shape=_shape2(reference),
        matrix=matrix,
        pre_resize=pre_resize,
        inverse_map=True,
        confidence=float(confidence),
        quality_before=before["similarity"],
        quality_after=after["similarity"],
        overlap_fraction=after["overlap_fraction"],
        warning=_quality_warning(after, before),
        message="Aligned moving image to reference with ECC.",
    )


def _feature_edge_transform(
    moving: np.ndarray,
    reference: np.ndarray,
    *,
    requested_mode: str,
    model: str,
    moving_shape: tuple[int, int],
    pre_resize: bool,
) -> AlignmentTransform:
    """Compute an ORB feature transform on edge-enhanced images."""

    import cv2

    reference_u8 = _edge_enhanced_uint8(reference)
    moving_u8 = _edge_enhanced_uint8(moving)
    orb = cv2.ORB_create(nfeatures=1200)
    ref_keypoints, ref_descriptors = orb.detectAndCompute(reference_u8, None)
    mov_keypoints, mov_descriptors = orb.detectAndCompute(moving_u8, None)
    if ref_descriptors is None or mov_descriptors is None:
        raise ValueError("Feature alignment found too few descriptors.")

    matcher = cv2.BFMatcher(cv2.NORM_HAMMING, crossCheck=True)
    matches = matcher.match(mov_descriptors, ref_descriptors)
    if len(matches) < 4:
        raise ValueError("Feature alignment found too few matches.")
    matches = sorted(matches, key=lambda item: item.distance)[: min(80, len(matches))]

    moving_points = np.float32([mov_keypoints[item.queryIdx].pt for item in matches])
    reference_points = np.float32([ref_keypoints[item.trainIdx].pt for item in matches])
    matrix, applied_model, inlier_count = _estimate_transform_from_points(
        moving_points,
        reference_points,
        model,
    )
    if matrix is None:
        raise ValueError("Feature alignment could not estimate a transform.")
    confidence = float(inlier_count) / float(max(1, len(matches)))
    stage = _stage_record(
        name="feature_edge",
        matrix=matrix,
        applied_model=applied_model,
        inverse_map=False,
        output_shape=_shape2(reference),
        confidence=confidence,
        message=f"ORB edge-feature transform with {inlier_count} inliers.",
    )
    aligned = _warp_with_stage(moving, stage, _shape2(reference), resample="bilinear")
    before = _quality_metrics(reference, moving)
    after = _quality_metrics(reference, aligned)
    return AlignmentTransform(
        requested_mode=requested_mode,
        mode=requested_mode,
        transform_model=model,
        applied_model=applied_model,
        status="aligned",
        success=True,
        reference_shape=_shape2(reference),
        moving_shape=moving_shape,
        output_shape=_shape2(reference),
        matrix=matrix,
        pre_resize=pre_resize,
        confidence=confidence,
        quality_before=before["similarity"],
        quality_after=after["similarity"],
        overlap_fraction=after["overlap_fraction"],
        warning=_quality_warning(after, before),
        message=f"Aligned moving image to reference with ORB edge features using {inlier_count} inliers.",
    )


def _contour_mask_transform(
    moving: np.ndarray,
    reference: np.ndarray,
    *,
    requested_mode: str,
    model: str,
    moving_shape: tuple[int, int],
    pre_resize: bool,
) -> AlignmentTransform:
    """Compute a simple whole-mask contour transform."""

    ref_stats = _mask_stats(reference)
    mov_stats = _mask_stats(moving)
    dx = ref_stats["centroid"][0] - mov_stats["centroid"][0]
    dy = ref_stats["centroid"][1] - mov_stats["centroid"][1]

    if model == "translation":
        matrix = np.asarray([[1.0, 0.0, dx], [0.0, 1.0, dy], [0.0, 0.0, 1.0]], dtype=float)
        applied_model = "translation"
    else:
        scale = 1.0
        if mov_stats["area"] > 0 and ref_stats["area"] > 0:
            scale = float(np.sqrt(ref_stats["area"] / mov_stats["area"]))
        angle = ref_stats["angle_degrees"] - mov_stats["angle_degrees"]
        matrix = _similarity_about_centroid(
            center=mov_stats["centroid"],
            target_center=ref_stats["centroid"],
            angle_degrees=angle,
            scale=scale,
        )
        applied_model = "euclidean"

    stage = _stage_record(
        name="contour_mask",
        matrix=matrix,
        applied_model=applied_model,
        inverse_map=False,
        output_shape=_shape2(reference),
        confidence=0.6,
        message="Foreground contour/mask moment transform.",
    )
    aligned = _warp_with_stage(moving, stage, _shape2(reference), resample="bilinear")
    before = _quality_metrics(reference, moving if _shape2(moving) == _shape2(reference) else _resize_or_canvas(moving, _shape2(reference)))
    after = _quality_metrics(reference, aligned)
    return AlignmentTransform(
        requested_mode=requested_mode,
        mode=requested_mode,
        transform_model=model,
        applied_model=applied_model,
        status="aligned",
        success=True,
        reference_shape=_shape2(reference),
        moving_shape=moving_shape,
        output_shape=_shape2(reference),
        matrix=matrix,
        pre_resize=pre_resize,
        confidence=0.6,
        quality_before=before["similarity"],
        quality_after=after["similarity"],
        overlap_fraction=after["overlap_fraction"],
        warning=_quality_warning(after, before),
        message="Aligned moving image to reference with foreground contour/mask moments.",
    )


def _phase_translation_matrix(
    moving: np.ndarray,
    reference: np.ndarray,
) -> tuple[np.ndarray, float, str, str]:
    """Estimate a coarse source-to-reference translation with phase correlation."""

    reference_shape = _shape2(reference)
    moving_canvas = _place_on_canvas(moving, reference_shape)
    reference_norm = _alignment_representation(reference)
    moving_norm = _alignment_representation(moving_canvas)
    reference_mask = _foreground_mask(reference_norm)
    moving_mask = _foreground_mask(moving_norm)
    overlap_estimate = _mask_overlap_estimate(reference_mask, moving_mask)

    try:
        from skimage.registration import phase_cross_correlation

        result = phase_cross_correlation(
            reference_norm,
            moving_norm,
            reference_mask=reference_mask,
            moving_mask=moving_mask,
            overlap_ratio=0.2,
        )
        shift = np.asarray(result[0] if isinstance(result, tuple) else result, dtype=float).ravel()
        if shift.size < 2 or not np.all(np.isfinite(shift[:2])):
            raise ValueError("scikit-image phase cross-correlation returned an invalid shift.")
        dy, dx = float(shift[0]), float(shift[1])
        confidence = min(1.0, max(0.0, overlap_estimate))
        return (
            np.asarray([[1.0, 0.0, dx], [0.0, 1.0, dy], [0.0, 0.0, 1.0]], dtype=float),
            confidence,
            f"scikit-image masked phase cross-correlation estimated shift dx={dx:.3f}, dy={dy:.3f}.",
            "" if overlap_estimate >= 0.03 else "low estimated overlap for masked phase correlation",
        )
    except ImportError:
        pass
    except Exception as exc:  # noqa: BLE001 - fallback to OpenCV phase correlation.
        skimage_warning = f"scikit-image masked phase correlation failed: {exc}"
    else:
        skimage_warning = ""

    import cv2

    window = cv2.createHanningWindow((reference_shape[1], reference_shape[0]), cv2.CV_32F)
    shift_xy, response = cv2.phaseCorrelate(
        reference_norm.astype(np.float32),
        moving_norm.astype(np.float32),
        window,
    )
    dx = -float(shift_xy[0])
    dy = -float(shift_xy[1])
    warning = skimage_warning if "skimage_warning" in locals() else "scikit-image is unavailable; used OpenCV phaseCorrelate fallback"
    if overlap_estimate < 0.03:
        warning = "; ".join(item for item in (warning, "low estimated overlap for phase correlation") if item)
    return (
        np.asarray([[1.0, 0.0, dx], [0.0, 1.0, dy], [0.0, 0.0, 1.0]], dtype=float),
        float(np.clip(response, 0.0, 1.0)),
        f"OpenCV phase correlation estimated shift dx={dx:.3f}, dy={dy:.3f}.",
        warning,
    )


def _alignment_representation(image: np.ndarray) -> np.ndarray:
    """Return an alignment-friendly representation resilient to RGB/NIR contrast."""

    import cv2

    norm = _normalize01(image).astype(np.float32)
    u8 = np.asarray(np.clip(norm * 255.0, 0.0, 255.0), dtype=np.uint8)
    blur = cv2.GaussianBlur(u8, (3, 3), 0)
    edges = cv2.Canny(blur, 40, 120).astype(np.float32) / 255.0
    return np.clip(0.65 * norm + 0.35 * edges, 0.0, 1.0).astype(np.float32)


def _place_on_canvas(image: np.ndarray, shape: tuple[int, int]) -> np.ndarray:
    """Place ``image`` on a top-left canvas with the reference shape."""

    source = _as_float_2d(image)
    canvas = np.zeros(shape, dtype=np.float32)
    height = min(shape[0], source.shape[0])
    width = min(shape[1], source.shape[1])
    if height > 0 and width > 0:
        canvas[:height, :width] = source[:height, :width]
    return canvas


def _resize_or_canvas(image: np.ndarray, shape: tuple[int, int], *, resample: str = "bilinear") -> np.ndarray:
    """Return a same-shape comparison image without pretending it is registered."""

    array = _as_float_2d(image)
    if _shape2(array) == shape:
        return array
    if array.shape[0] <= shape[0] and array.shape[1] <= shape[1]:
        return _place_on_canvas(array, shape)
    return resize_image(array, shape, resample=resample)


def _foreground_mask(image: np.ndarray) -> np.ndarray:
    """Build a loose foreground mask for overlap-aware alignment metrics."""

    values = _normalize01(image)
    finite = values[np.isfinite(values)]
    if finite.size == 0:
        return np.zeros(values.shape, dtype=bool)
    threshold = max(0.02, float(np.percentile(finite, 60.0)) * 0.5)
    return values > threshold


def _mask_overlap_estimate(reference_mask: np.ndarray, moving_mask: np.ndarray) -> float:
    """Estimate binary-mask overlap fraction."""

    union = np.logical_or(reference_mask, moving_mask)
    if not union.any():
        return 0.0
    return float(np.count_nonzero(np.logical_and(reference_mask, moving_mask)) / np.count_nonzero(union))


def _quality_metrics(reference: np.ndarray, moving_aligned: np.ndarray) -> dict[str, float]:
    """Return simple similarity and overlap metrics for alignment quality."""

    ref = _normalize01(reference).astype(np.float32)
    mov = _normalize01(_resize_or_canvas(moving_aligned, _shape2(ref))).astype(np.float32)
    mask = np.isfinite(ref) & np.isfinite(mov)
    ref_mask = _foreground_mask(ref)
    mov_mask = _foreground_mask(mov)
    overlap = _mask_overlap_estimate(ref_mask, mov_mask)
    if not mask.any():
        return {"similarity": 0.0, "overlap_fraction": overlap}
    ref_values = ref[mask]
    mov_values = mov[mask]
    if float(np.std(ref_values)) < 1e-8 or float(np.std(mov_values)) < 1e-8:
        mae = float(np.mean(np.abs(ref_values - mov_values)))
        return {"similarity": float(np.clip(1.0 - mae, 0.0, 1.0)), "overlap_fraction": overlap}
    corr = float(np.corrcoef(ref_values, mov_values)[0, 1])
    similarity = float(np.clip((corr + 1.0) / 2.0, 0.0, 1.0))
    return {"similarity": similarity, "overlap_fraction": overlap}


def _quality_warning(after: Mapping[str, float], before: Mapping[str, float]) -> str:
    """Return a warning when alignment quality looks weak."""

    warnings: list[str] = []
    if after["overlap_fraction"] < 0.03:
        warnings.append("estimated overlap is very low; alignment may be unreliable")
    if after["similarity"] < 0.35:
        warnings.append("after-alignment similarity is low")
    if after["similarity"] + 0.01 < before["similarity"]:
        warnings.append("alignment quality metric worsened after registration")
    return "; ".join(warnings)


def _combined_confidence(values: Sequence[float | None]) -> float:
    """Combine stage confidence values conservatively."""

    usable = [float(value) for value in values if value is not None and np.isfinite(float(value))]
    if not usable:
        return 0.0
    return float(np.clip(np.mean(usable), 0.0, 1.0))


def _stage_record(
    *,
    name: str,
    matrix: np.ndarray,
    applied_model: str,
    inverse_map: bool,
    output_shape: tuple[int, int],
    confidence: float | None = None,
    message: str = "",
    warning: str = "",
) -> dict[str, Any]:
    """Build one JSON-friendly alignment stage record."""

    return {
        "name": name,
        "matrix": np.asarray(matrix, dtype=float),
        "applied_model": applied_model,
        "inverse_map": bool(inverse_map),
        "output_shape": tuple(int(v) for v in output_shape),
        "confidence": None if confidence is None else float(confidence),
        "message": message,
        "warning": warning,
    }


def _transform_to_stages(transform: AlignmentTransform, *, stage_name: str) -> tuple[dict[str, Any], ...]:
    """Convert a single-stage transform into stage records."""

    if transform.stages:
        return transform.stages
    if transform.matrix is None:
        return ()
    return (
        _stage_record(
            name=stage_name,
            matrix=transform.matrix,
            applied_model=transform.applied_model,
            inverse_map=transform.inverse_map,
            output_shape=transform.output_shape,
            confidence=transform.confidence,
            message=transform.message,
            warning=transform.warning,
        ),
    )


def _apply_alignment_stages(
    image: np.ndarray,
    transform: AlignmentTransform,
    *,
    resample: str,
) -> np.ndarray:
    """Apply all stages stored on a multi-stage transform."""

    return _apply_stages_to_array(image, transform.stages, transform.output_shape, resample=resample)


def _apply_stages_to_array(
    image: np.ndarray,
    stages: Sequence[Mapping[str, Any]],
    output_shape: tuple[int, int],
    *,
    resample: str,
) -> np.ndarray:
    """Apply stage records sequentially."""

    result = _as_float_2d(image)
    current_shape = output_shape
    for stage in stages:
        current_shape = tuple(stage.get("output_shape", current_shape))  # type: ignore[arg-type]
        result = _warp_with_stage(result, stage, current_shape, resample=resample)
    if _shape2(result) != output_shape:
        result = resize_image(result, output_shape, resample=resample)
    return result.astype(np.float32, copy=False)


def _warp_with_stage(
    image: np.ndarray,
    stage: Mapping[str, Any],
    output_shape: tuple[int, int],
    *,
    resample: str,
) -> np.ndarray:
    """Warp an image according to one stage record."""

    import cv2

    array = _as_float_2d(image)
    height, width = output_shape
    flags = _cv2_interp(resample)
    if bool(stage.get("inverse_map", False)):
        flags |= cv2.WARP_INVERSE_MAP
    matrix = np.asarray(stage["matrix"], dtype=np.float32)
    if str(stage.get("applied_model")) == "homography":
        warped = cv2.warpPerspective(
            array.astype(np.float32),
            matrix,
            (width, height),
            flags=flags,
            borderMode=cv2.BORDER_CONSTANT,
            borderValue=0,
        )
    else:
        warped = cv2.warpAffine(
            array.astype(np.float32),
            matrix[:2, :],
            (width, height),
            flags=flags,
            borderMode=cv2.BORDER_CONSTANT,
            borderValue=0,
        )
    return np.asarray(warped, dtype=np.float32)


def _effective_stage_matrix(stages: Sequence[Mapping[str, Any]]) -> np.ndarray | None:
    """Return an approximate source-to-reference matrix for report readability."""

    effective = np.eye(3, dtype=float)
    for stage in stages:
        matrix = np.asarray(stage.get("matrix"), dtype=float)
        if matrix.shape == (2, 3):
            matrix = _homogeneous_matrix(matrix, str(stage.get("applied_model", "affine")))
        if matrix.shape != (3, 3):
            return None
        if bool(stage.get("inverse_map", False)):
            try:
                matrix = np.linalg.inv(matrix)
            except np.linalg.LinAlgError:
                return None
        effective = matrix @ effective
    return effective


def _json_safe_stages(stages: Sequence[Mapping[str, Any]]) -> list[dict[str, Any]]:
    """Convert stage records to JSON-safe values."""

    safe: list[dict[str, Any]] = []
    for stage in stages:
        safe.append(
            {
                str(key): (
                    np.asarray(value, dtype=float).tolist()
                    if isinstance(value, np.ndarray)
                    else list(value)
                    if isinstance(value, tuple)
                    else value
                )
                for key, value in stage.items()
            }
        )
    return safe


def _estimate_transform_from_points(
    moving_points: np.ndarray,
    reference_points: np.ndarray,
    model: str,
) -> tuple[np.ndarray | None, str, int]:
    """Estimate a transform from matched point pairs."""

    import cv2

    if model == "homography" and len(moving_points) >= 4:
        matrix, inliers = cv2.findHomography(moving_points, reference_points, cv2.RANSAC, 4.0)
        return (None if matrix is None else np.asarray(matrix, dtype=float)), "homography", _inlier_count(inliers)
    if model == "affine" and len(moving_points) >= 3:
        affine, inliers = cv2.estimateAffine2D(moving_points, reference_points, method=cv2.RANSAC, ransacReprojThreshold=4.0)
        return (None if affine is None else _homogeneous_matrix(affine, "affine")), "affine", _inlier_count(inliers)
    if model == "euclidean" and len(moving_points) >= 2:
        affine, inliers = cv2.estimateAffinePartial2D(
            moving_points,
            reference_points,
            method=cv2.RANSAC,
            ransacReprojThreshold=4.0,
        )
        return (None if affine is None else _homogeneous_matrix(affine, "euclidean")), "euclidean", _inlier_count(inliers)

    deltas = reference_points - moving_points
    if deltas.size == 0:
        return None, "translation", 0
    dx, dy = np.median(deltas, axis=0)
    matrix = np.asarray([[1.0, 0.0, dx], [0.0, 1.0, dy], [0.0, 0.0, 1.0]], dtype=float)
    return matrix, "translation", len(moving_points)


def _mask_stats(image: np.ndarray) -> dict[str, Any]:
    """Return foreground mask moment statistics for contour fallback."""

    import cv2

    u8 = _normalize_uint8(image)
    _, mask = cv2.threshold(u8, 0, 255, cv2.THRESH_BINARY + cv2.THRESH_OTSU)
    if np.count_nonzero(mask) > mask.size * 0.75:
        mask = cv2.bitwise_not(mask)
    contours, _ = cv2.findContours(mask, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
    if not contours:
        raise ValueError("Contour alignment could not find a foreground mask.")
    contour = max(contours, key=cv2.contourArea)
    moments = cv2.moments(contour)
    if abs(moments["m00"]) < 1e-8:
        raise ValueError("Contour alignment foreground area is empty.")
    cx = moments["m10"] / moments["m00"]
    cy = moments["m01"] / moments["m00"]
    angle = 0.0
    if len(contour) >= 5:
        (_, _), (_, _), angle = cv2.fitEllipse(contour)
    return {
        "centroid": (float(cx), float(cy)),
        "area": float(cv2.contourArea(contour)),
        "angle_degrees": float(angle),
    }


def _similarity_about_centroid(
    *,
    center: tuple[float, float],
    target_center: tuple[float, float],
    angle_degrees: float,
    scale: float,
) -> np.ndarray:
    """Build a moving-to-reference similarity transform."""

    import cv2

    affine = cv2.getRotationMatrix2D(center, angle_degrees, scale)
    moved_center = np.asarray([affine[0, 0] * center[0] + affine[0, 1] * center[1] + affine[0, 2],
                               affine[1, 0] * center[0] + affine[1, 1] * center[1] + affine[1, 2]])
    target = np.asarray(target_center, dtype=float)
    affine[:, 2] += target - moved_center
    return _homogeneous_matrix(affine, "euclidean")


def _ecc_motion(model: str) -> tuple[int, str, np.ndarray]:
    """Return OpenCV ECC motion type and initial matrix."""

    import cv2

    if model == "translation":
        return cv2.MOTION_TRANSLATION, "translation", np.eye(2, 3, dtype=np.float32)
    if model == "euclidean":
        return cv2.MOTION_EUCLIDEAN, "euclidean", np.eye(2, 3, dtype=np.float32)
    if model == "homography":
        return cv2.MOTION_HOMOGRAPHY, "homography", np.eye(3, 3, dtype=np.float32)
    return cv2.MOTION_AFFINE, "affine", np.eye(2, 3, dtype=np.float32)


def _homogeneous_matrix(matrix: np.ndarray, applied_model: str) -> np.ndarray:
    """Return a 3x3 transform matrix."""

    arr = np.asarray(matrix, dtype=float)
    if applied_model == "homography":
        return arr.reshape(3, 3)
    if arr.shape == (2, 3):
        return np.vstack([arr, np.asarray([0.0, 0.0, 1.0])])
    return arr


def _scale_matrix(source_shape: tuple[int, int], target_shape: tuple[int, int]) -> np.ndarray:
    """Return an approximate source-to-target scale matrix."""

    src_h, src_w = source_shape
    dst_h, dst_w = target_shape
    sx = float(dst_w) / float(max(1, src_w))
    sy = float(dst_h) / float(max(1, src_h))
    return np.asarray([[sx, 0.0, 0.0], [0.0, sy, 0.0], [0.0, 0.0, 1.0]], dtype=float)


def _as_float_2d(image: np.ndarray) -> np.ndarray:
    """Return a 2D float array."""

    array = np.asarray(image, dtype=np.float32)
    if array.ndim != 2:
        raise ValueError(f"Alignment expects a 2D image band, got {array.shape}.")
    return array


def _shape2(image: np.ndarray) -> tuple[int, int]:
    """Return an image shape as ``(height, width)``."""

    return int(image.shape[0]), int(image.shape[1])


def _normalize01(image: np.ndarray) -> np.ndarray:
    """Normalize an image to 0..1 for registration."""

    values = _as_float_2d(image)
    finite = values[np.isfinite(values)]
    if finite.size == 0:
        return np.zeros(values.shape, dtype=np.float32)
    min_value = float(np.min(finite))
    max_value = float(np.max(finite))
    if np.isclose(min_value, max_value):
        return np.zeros(values.shape, dtype=np.float32)
    normalized = (values - min_value) / (max_value - min_value)
    return np.clip(np.nan_to_num(normalized, nan=0.0), 0.0, 1.0)


def _normalize_uint8(image: np.ndarray) -> np.ndarray:
    """Normalize an image to uint8."""

    return np.asarray(np.clip(_normalize01(image) * 255.0, 0.0, 255.0), dtype=np.uint8)


def _edge_enhanced_uint8(image: np.ndarray) -> np.ndarray:
    """Return a Canny edge-enhanced uint8 image for feature alignment."""

    import cv2

    u8 = _normalize_uint8(image)
    edges = cv2.Canny(u8, 50, 150)
    return cv2.addWeighted(u8, 0.55, edges, 0.45, 0)


def _cv2_interp(resample: str) -> int:
    """Return an OpenCV interpolation flag."""

    import cv2

    return cv2.INTER_NEAREST if resample == "nearest" else cv2.INTER_LINEAR


def _inlier_count(inliers: np.ndarray | None) -> int:
    """Return a robust inlier count from an OpenCV mask."""

    if inliers is None:
        return 0
    return int(np.count_nonzero(inliers))


__all__ = [
    "AlignmentTransform",
    "VALID_ALIGNMENT_MODES",
    "VALID_TRANSFORM_MODELS",
    "apply_alignment_transform",
    "compare_alignment_methods",
    "compute_alignment_transform",
    "normalize_alignment_mode",
    "normalize_transform_model",
    "resize_image",
]
