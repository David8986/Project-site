"""Tests for global mixed-image alignment helpers."""

from __future__ import annotations

import numpy as np

from plant_health_mvp.core.image_alignment import (
    apply_alignment_transform,
    compare_alignment_methods,
    compute_alignment_transform,
)


def _reference_scene() -> np.ndarray:
    """Create an asymmetric synthetic scene for registration tests."""

    image = np.zeros((80, 90), dtype=np.float32)
    image[18:48, 20:55] = 0.75
    image[42:66, 50:78] = 0.45
    image[25:33, 62:72] = 1.0
    yy, xx = np.mgrid[:80, :90]
    image += 0.2 * (((xx - 30) / 18) ** 2 + ((yy - 48) / 22) ** 2 < 1.0)
    return image


def _shift_image(image: np.ndarray, dx: int, dy: int) -> np.ndarray:
    """Shift an image with zero padding."""

    shifted = np.zeros_like(image)
    src_y0 = max(0, -dy)
    src_y1 = image.shape[0] - max(0, dy)
    src_x0 = max(0, -dx)
    src_x1 = image.shape[1] - max(0, dx)
    dst_y0 = max(0, dy)
    dst_y1 = dst_y0 + (src_y1 - src_y0)
    dst_x0 = max(0, dx)
    dst_x1 = dst_x0 + (src_x1 - src_x0)
    shifted[dst_y0:dst_y1, dst_x0:dst_x1] = image[src_y0:src_y1, src_x0:src_x1]
    return shifted


def _plant_scene() -> np.ndarray:
    """Create a multi-leaf synthetic plant-like scene."""

    import cv2

    image = np.zeros((120, 140), dtype=np.float32)
    cv2.ellipse(image, (45, 50), (18, 35), -28, 0, 360, 0.80, -1)
    cv2.ellipse(image, (88, 60), (22, 32), 18, 0, 360, 0.55, -1)
    cv2.ellipse(image, (65, 88), (26, 16), 8, 0, 360, 1.00, -1)
    cv2.circle(image, (105, 35), 9, 0.70, -1)
    yy, xx = np.mgrid[:120, :140]
    image += 0.08 * np.sin(xx / 8.0) + 0.05 * np.cos(yy / 11.0)
    return np.clip(image, 0.0, 1.0).astype(np.float32)


def _warp_image(image: np.ndarray, *, dx: float = 0.0, dy: float = 0.0, angle: float = 0.0) -> np.ndarray:
    """Warp an image with a small rigid transform."""

    import cv2

    height, width = image.shape
    matrix = cv2.getRotationMatrix2D((width / 2.0, height / 2.0), angle, 1.0)
    matrix[:, 2] += [dx, dy]
    return cv2.warpAffine(image, matrix, (width, height), flags=cv2.INTER_LINEAR, borderValue=0)


def _mae(reference: np.ndarray, moving: np.ndarray) -> float:
    """Mean absolute error helper."""

    if moving.shape != reference.shape:
        padded = np.zeros_like(reference)
        height = min(reference.shape[0], moving.shape[0])
        width = min(reference.shape[1], moving.shape[1])
        padded[:height, :width] = moving[:height, :width]
        moving = padded
    return float(np.mean(np.abs(reference - moving)))


def test_resize_only_alignment_reports_low_confidence_when_shape_changes() -> None:
    """Resize-only alignment should be explicit and low confidence."""

    reference = np.zeros((20, 30), dtype=np.float32)
    moving = np.zeros((10, 15), dtype=np.float32)

    transform = compute_alignment_transform(moving, reference, mode="resize_only")
    aligned = apply_alignment_transform(moving, transform)

    assert aligned.shape == reference.shape
    assert transform.status == "resized"
    assert transform.confidence == 0.25
    assert "low confidence" in transform.warning


def test_ecc_translation_alignment_improves_shifted_scene() -> None:
    """ECC translation should globally align a shifted full-frame scene."""

    reference = _reference_scene()
    moving = _shift_image(reference, dx=5, dy=-3)

    before = float(np.mean(np.abs(reference - moving)))
    transform = compute_alignment_transform(
        moving,
        reference,
        mode="automatic_ecc",
        transform_model="translation",
    )
    aligned = apply_alignment_transform(moving, transform)
    after = float(np.mean(np.abs(reference - aligned)))

    assert transform.status == "aligned"
    assert transform.applied_model == "translation"
    assert after < before * 0.55


def test_contour_alignment_returns_transform_metadata() -> None:
    """Contour/mask fallback should produce a transform record and aligned shape."""

    reference = _reference_scene()
    moving = _shift_image(reference, dx=-4, dy=6)

    transform = compute_alignment_transform(
        moving,
        reference,
        mode="automatic_contour_mask",
        transform_model="translation",
    )
    aligned = apply_alignment_transform(moving, transform)

    assert aligned.shape == reference.shape
    assert transform.status == "aligned"
    assert transform.applied_model == "translation"
    assert transform.matrix is not None


def test_phase_ecc_alignment_handles_known_translation() -> None:
    """The robust phase+ECC mode should recover a simple full-frame shift."""

    reference = _plant_scene()
    moving = _warp_image(reference, dx=7, dy=-5)

    before = _mae(reference, moving)
    transform = compute_alignment_transform(
        moving,
        reference,
        mode="automatic_phase_ecc",
        transform_model="translation",
    )
    aligned = apply_alignment_transform(moving, transform)
    after = _mae(reference, aligned)

    assert transform.status == "aligned"
    assert transform.stages
    assert transform.quality_after is not None
    assert transform.quality_after > transform.quality_before
    assert after < before * 0.35


def test_ecc_euclidean_alignment_improves_small_rotation() -> None:
    """OpenCV ECC should handle a small rotation plus translation."""

    reference = _plant_scene()
    moving = _warp_image(reference, dx=4, dy=-3, angle=4)

    before = _mae(reference, moving)
    transform = compute_alignment_transform(
        moving,
        reference,
        mode="automatic_ecc",
        transform_model="euclidean",
    )
    aligned = apply_alignment_transform(moving, transform)
    after = _mae(reference, aligned)

    assert transform.status == "aligned"
    assert transform.applied_model == "euclidean"
    assert transform.quality_after is not None
    assert transform.quality_after > transform.quality_before
    assert after < before * 0.5


def test_phase_ecc_alignment_handles_cropped_moving_image() -> None:
    """Phase+ECC should place a cropped moving image into reference space."""

    reference = _plant_scene()
    moving = reference[12:102, 18:125]

    before = _mae(reference, moving)
    transform = compute_alignment_transform(
        moving,
        reference,
        mode="automatic_phase_ecc",
        transform_model="translation",
    )
    aligned = apply_alignment_transform(moving, transform)
    after = _mae(reference, aligned)

    assert aligned.shape == reference.shape
    assert transform.status == "aligned"
    assert transform.overlap_fraction is not None
    assert transform.overlap_fraction > 0.45
    assert after < before * 0.25


def test_phase_ecc_alignment_handles_rgb_nir_like_difference() -> None:
    """Alignment representation should tolerate RGB-like vs NIR-like contrast."""

    reference = _plant_scene()
    yy, xx = np.mgrid[: reference.shape[0], : reference.shape[1]]
    nir_like = np.sqrt(reference) + 0.08 * (((xx - 72) / 30) ** 2 + ((yy - 70) / 22) ** 2 < 1.0)
    nir_like = np.clip(nir_like, 0.0, 1.0).astype(np.float32)
    moving = _warp_image(nir_like, dx=-6, dy=5)

    transform = compute_alignment_transform(
        moving,
        reference,
        mode="automatic_phase_ecc",
        transform_model="translation",
    )
    aligned = apply_alignment_transform(moving, transform)

    assert aligned.shape == reference.shape
    assert transform.status == "aligned"
    assert transform.quality_after is not None
    assert transform.quality_before is not None
    assert transform.quality_after > transform.quality_before


def test_alignment_method_comparison_reports_methods() -> None:
    """The backend should expose a benchmark-friendly method comparison path."""

    reference = _plant_scene()
    moving = _warp_image(reference, dx=7, dy=-5)

    results = compare_alignment_methods(
        moving,
        reference,
        methods=["resize_only", "automatic_phase_ecc"],
        transform_model="translation",
    )

    assert [result["method"] for result in results] == ["resize_only", "automatic_phase_ecc"]
    assert results[1]["success"] is True
    assert results[1]["quality_after"] > results[0]["quality_after"]
