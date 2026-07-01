"""Display-only affected-area overlay helpers.

These functions work on already-normalized display images. They do not alter
scientific reflectance, index, mask, or anomaly values.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any, Mapping, Sequence

import numpy as np


@dataclass(frozen=True, slots=True)
class RegionDisplay:
    """Display metadata for one suspicious region."""

    label: int
    bbox: tuple[int, int, int, int]
    centroid: tuple[float, float] | None = None


def read_uint8_image(path: str | Path) -> np.ndarray:
    """Read an image file as a uint8 RGB or grayscale array."""

    from PIL import Image

    image = Image.open(path)
    if image.mode in {"L", "I;16", "I"}:
        return np.asarray(image.convert("L"), dtype=np.uint8)
    return np.asarray(image.convert("RGB"), dtype=np.uint8)


def save_uint8_image(image: np.ndarray, path: str | Path) -> Path:
    """Save a uint8 grayscale or RGB image."""

    from PIL import Image

    output = Path(path)
    output.parent.mkdir(parents=True, exist_ok=True)
    array = np.asarray(image, dtype=np.uint8)
    Image.fromarray(array).save(output)
    return output


def ensure_rgb(image: np.ndarray) -> np.ndarray:
    """Return a 3-channel uint8 display image."""

    array = np.asarray(image, dtype=np.uint8)
    if array.ndim == 2:
        return np.repeat(array[:, :, None], 3, axis=2)
    if array.ndim == 3 and array.shape[2] == 3:
        return array
    raise ValueError(f"Expected grayscale or RGB display image, got {array.shape}.")


def build_composite(red: np.ndarray, green: np.ndarray, blue: np.ndarray) -> np.ndarray:
    """Build an RGB display composite from three uint8 band images."""

    return np.stack(
        [
            np.asarray(red, dtype=np.uint8),
            np.asarray(green, dtype=np.uint8),
            np.asarray(blue, dtype=np.uint8),
        ],
        axis=-1,
    )


def parse_region_rows(rows: Sequence[Mapping[str, Any]]) -> list[RegionDisplay]:
    """Parse rows from ``spots.csv`` into overlay display regions."""

    regions: list[RegionDisplay] = []
    for row in rows:
        try:
            label = int(float(row.get("label", 0)))
            bbox = (
                int(float(row.get("bbox_x_min", 0))),
                int(float(row.get("bbox_y_min", 0))),
                int(float(row.get("bbox_x_max", 0))),
                int(float(row.get("bbox_y_max", 0))),
            )
            centroid = (
                float(row["centroid_x"]),
                float(row["centroid_y"]),
            )
        except (KeyError, TypeError, ValueError):
            continue
        if label > 0:
            regions.append(RegionDisplay(label=label, bbox=bbox, centroid=centroid))
    return regions


def render_overlay(
    background: np.ndarray,
    *,
    mode: str,
    suspicious_mask: np.ndarray | None = None,
    score_map: np.ndarray | None = None,
    vegetation_mask: np.ndarray | None = None,
    regions: Sequence[RegionDisplay] = (),
    opacity: float = 0.45,
    show_outlines: bool = True,
    show_labels: bool = True,
    show_boxes: bool = True,
    show_suspicious_mask: bool = True,
    show_filled_overlay: bool = False,
    show_vegetation_mask: bool = False,
    selected_label: int | None = None,
) -> np.ndarray:
    """Render a display overlay on top of a background image.

    ``show_outlines`` controls the suspicious-mask boundary in outline mode and
    in the annotation pass used by filled and heatmap views. Existing callers
    can omit it and retain the previous behavior.
    """

    mode_key = mode.lower().strip()
    base = ensure_rgb(background).astype(np.float32)
    alpha = float(np.clip(opacity, 0.0, 1.0))

    if not show_suspicious_mask:
        suspicious_mask = None
        regions = ()

    if show_vegetation_mask and mode_key not in {"heatmap", "vegetation"}:
        base = _apply_vegetation_mask(base, vegetation_mask, opacity=min(alpha, 0.35)).astype(np.float32)

    if mode_key == "background":
        rendered = base.astype(np.uint8)
    elif mode_key == "filled":
        rendered = _apply_filled_mask(base, suspicious_mask, alpha)
    elif mode_key == "heatmap":
        rendered = _apply_heatmap(base, score_map, vegetation_mask, alpha)
    elif mode_key == "vegetation":
        rendered = _apply_vegetation_mask(base, vegetation_mask, alpha)
    elif mode_key == "outline":
        rendered = _apply_filled_mask(base, suspicious_mask, min(alpha, 0.35)) if show_filled_overlay else base.astype(np.uint8)
    else:
        raise ValueError(f"Unknown overlay mode: {mode}")

    if mode_key in {"outline", "filled", "heatmap", "vegetation"}:
        rendered = _draw_region_annotations(
            rendered,
            suspicious_mask=suspicious_mask,
            regions=regions,
            show_outlines=show_outlines,
            show_labels=show_labels,
            show_boxes=show_boxes,
            selected_label=selected_label,
        )
    if mode_key == "heatmap":
        rendered = _append_heatmap_legend(rendered)
    return rendered


def _as_bool_mask(mask: np.ndarray | None, shape: tuple[int, int]) -> np.ndarray:
    """Return a boolean display mask with the requested image shape."""

    if mask is None:
        return np.zeros(shape, dtype=bool)
    array = np.asarray(mask)
    if array.ndim == 3:
        array = array[:, :, 0]
    if array.shape[:2] != shape:
        raise ValueError(f"Mask shape {array.shape[:2]} does not match background {shape}.")
    return array > 0


def _score01(score_map: np.ndarray | None, shape: tuple[int, int]) -> np.ndarray:
    """Return a 0..1 display score map."""

    if score_map is None:
        return np.zeros(shape, dtype=float)
    score = np.asarray(score_map, dtype=float)
    if score.ndim == 3:
        score = score[:, :, 0]
    if score.shape[:2] != shape:
        raise ValueError(f"Score shape {score.shape[:2]} does not match background {shape}.")
    if score.max(initial=0) > 1.0:
        score = score / 255.0
    return np.clip(score, 0.0, 1.0)


def _apply_filled_mask(background: np.ndarray, mask: np.ndarray | None, opacity: float) -> np.ndarray:
    """Overlay suspicious pixels in translucent red."""

    rendered = background.copy()
    mask_bool = _as_bool_mask(mask, background.shape[:2])
    red = np.array([255.0, 28.0, 36.0], dtype=np.float32)
    rendered[mask_bool] = (1.0 - opacity) * rendered[mask_bool] + opacity * red
    return np.clip(rendered, 0.0, 255.0).astype(np.uint8)


def _apply_vegetation_mask(background: np.ndarray, mask: np.ndarray | None, opacity: float) -> np.ndarray:
    """Overlay vegetation pixels in translucent green/teal."""

    rendered = background.copy()
    mask_bool = _as_bool_mask(mask, background.shape[:2])
    green = np.array([50.0, 190.0, 115.0], dtype=np.float32)
    rendered[mask_bool] = (1.0 - opacity) * rendered[mask_bool] + opacity * green
    return np.clip(rendered, 0.0, 255.0).astype(np.uint8)


def _apply_heatmap(
    background: np.ndarray,
    score_map: np.ndarray | None,
    vegetation_mask: np.ndarray | None,
    opacity: float,
) -> np.ndarray:
    """Overlay a green/yellow/orange/red anomaly heatmap."""

    score = _score01(score_map, background.shape[:2])
    valid = _as_bool_mask(vegetation_mask, background.shape[:2]) if vegetation_mask is not None else np.ones(score.shape, bool)
    heatmap = _score_to_rgb(score).astype(np.float32)
    rendered = background.copy()
    rendered[valid] = (1.0 - opacity) * rendered[valid] + opacity * heatmap[valid]
    return np.clip(rendered, 0.0, 255.0).astype(np.uint8)


def _score_to_rgb(score: np.ndarray) -> np.ndarray:
    """Map 0..1 scores to green/yellow/orange/red display colors."""

    stops = np.array(
        [
            [32, 150, 80],
            [245, 220, 65],
            [245, 135, 35],
            [220, 35, 35],
        ],
        dtype=float,
    )
    values = np.clip(np.asarray(score, dtype=float), 0.0, 1.0)
    scaled = values * (len(stops) - 1)
    low = np.floor(scaled).astype(int)
    high = np.clip(low + 1, 0, len(stops) - 1)
    frac = scaled - low
    colors = stops[low] * (1.0 - frac[..., None]) + stops[high] * frac[..., None]
    return np.clip(colors, 0, 255).astype(np.uint8)


def _draw_region_annotations(
    image: np.ndarray,
    *,
    suspicious_mask: np.ndarray | None,
    regions: Sequence[RegionDisplay],
    show_outlines: bool,
    show_labels: bool,
    show_boxes: bool,
    selected_label: int | None,
) -> np.ndarray:
    """Draw outlines, optional boxes, and labels."""

    from PIL import Image, ImageDraw

    rendered = np.asarray(image, dtype=np.uint8).copy()
    outline_color = np.array([218, 222, 220], dtype=np.uint8)
    selected_color = np.array([255, 255, 250], dtype=np.uint8)
    if show_outlines:
        rendered = _draw_mask_contours(
            rendered,
            _as_bool_mask(suspicious_mask, rendered.shape[:2]),
            tuple(int(value) for value in outline_color),
            thickness=1,
        )

    pil = Image.fromarray(rendered)
    draw = ImageDraw.Draw(pil)
    for region in regions:
        is_selected = selected_label is not None and int(region.label) == int(selected_label)
        color = tuple(int(value) for value in (selected_color if is_selected else outline_color))
        width = 2 if is_selected else 1
        x0, y0, x1, y1 = region.bbox
        if show_boxes or is_selected:
            draw.rectangle([x0, y0, x1, y1], outline=color, width=width)
        if show_labels:
            label_text = f"ID {region.label}"
            text_y = max(0, y0 - 14)
            draw.rounded_rectangle([x0, text_y, x0 + 40, text_y + 13], radius=3, fill=(24, 27, 27))
            draw.text((x0 + 3, text_y + 1), label_text, fill=color)
    return np.asarray(pil, dtype=np.uint8)


def _draw_mask_contours(
    image: np.ndarray,
    mask: np.ndarray,
    color: tuple[int, int, int],
    thickness: int,
) -> np.ndarray:
    """Draw anti-aliased contours when OpenCV is available."""

    if not mask.any():
        return image
    try:
        import cv2

        rendered = np.asarray(image, dtype=np.uint8).copy()
        contours, _ = cv2.findContours(mask.astype(np.uint8), cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
        cv2.drawContours(rendered, contours, -1, color, int(thickness), lineType=cv2.LINE_AA)
        return rendered
    except Exception:
        rendered = image.copy()
        outline = _outline_from_mask(mask, thickness=thickness)
        rendered[outline] = np.asarray(color, dtype=np.uint8)
        return rendered


def _outline_from_mask(mask: np.ndarray, thickness: int = 1) -> np.ndarray:
    """Return a boundary mask from a binary mask."""

    if not mask.any():
        return np.zeros_like(mask, dtype=bool)
    eroded = mask.copy()
    for _ in range(max(1, int(thickness))):
        padded = np.pad(eroded, 1, mode="constant", constant_values=False)
        neighborhoods = [
            padded[row : row + eroded.shape[0], col : col + eroded.shape[1]]
            for row in range(3)
            for col in range(3)
        ]
        eroded = np.all(np.stack(neighborhoods, axis=0), axis=0)
    return mask & ~eroded


def _append_heatmap_legend(image: np.ndarray) -> np.ndarray:
    """Append a small low/high heatmap color legend."""

    from PIL import Image, ImageDraw

    height = image.shape[0]
    legend_width = 84
    pad = 10
    output = np.full((height, image.shape[1] + legend_width, 3), 245, dtype=np.uint8)
    output[:, : image.shape[1], :] = image

    gradient_height = max(1, height - 2 * pad)
    gradient = np.linspace(1.0, 0.0, gradient_height)[:, None]
    colors = _score_to_rgb(gradient)
    output[pad : pad + gradient_height, image.shape[1] + 14 : image.shape[1] + 34, :] = colors

    pil = Image.fromarray(output)
    draw = ImageDraw.Draw(pil)
    x = image.shape[1] + 40
    draw.text((x, pad), "High", fill=(40, 40, 40))
    draw.text((x, height // 2 - 7), "Med", fill=(40, 40, 40))
    draw.text((x, height - pad - 14), "Low", fill=(40, 40, 40))
    return np.asarray(pil, dtype=np.uint8)


__all__ = [
    "RegionDisplay",
    "build_composite",
    "ensure_rgb",
    "parse_region_rows",
    "read_uint8_image",
    "render_overlay",
    "save_uint8_image",
]
