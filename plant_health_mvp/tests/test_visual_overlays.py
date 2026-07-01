"""Tests for display-only affected-area overlay helpers."""

from __future__ import annotations

import numpy as np

from plant_health_mvp.core.visual_overlays import RegionDisplay, build_composite, render_overlay


def test_render_filled_overlay_marks_suspicious_pixels_red() -> None:
    """Filled overlays should alter only suspicious display pixels."""

    background = np.full((6, 6, 3), 100, dtype=np.uint8)
    mask = np.zeros((6, 6), dtype=np.uint8)
    mask[2:4, 2:4] = 255

    rendered = render_overlay(background, mode="filled", suspicious_mask=mask, opacity=0.5)

    assert rendered.shape == background.shape
    assert rendered[2, 2, 0] > rendered[0, 0, 0]
    np.testing.assert_array_equal(rendered[0, 0], background[0, 0])


def test_render_heatmap_adds_legend_and_uses_score_map() -> None:
    """Heatmap overlays should append a color legend and preserve image height."""

    background = np.full((8, 8, 3), 80, dtype=np.uint8)
    score = np.zeros((8, 8), dtype=np.uint8)
    score[:, 4:] = 255
    vegetation = np.ones((8, 8), dtype=np.uint8) * 255

    rendered = render_overlay(
        background,
        mode="heatmap",
        score_map=score,
        vegetation_mask=vegetation,
        opacity=0.5,
        regions=[RegionDisplay(label=1, bbox=(4, 1, 7, 6))],
    )

    assert rendered.shape[0] == background.shape[0]
    assert rendered.shape[1] > background.shape[1]


def test_render_outline_overlay_uses_subtle_neutral_color() -> None:
    """Outline overlays should stay near-neutral and visually restrained."""

    background = np.full((6, 6, 3), 90, dtype=np.uint8)
    mask = np.zeros((6, 6), dtype=np.uint8)
    mask[2:4, 2:4] = 255

    rendered = render_overlay(
        background,
        mode="outline",
        suspicious_mask=mask,
        show_labels=False,
        show_boxes=False,
    )

    outline_pixel = rendered[2, 2]
    assert outline_pixel.min() >= 185
    assert int(outline_pixel.max()) - int(outline_pixel.min()) <= 15


def test_render_overlay_can_hide_outlines_without_changing_background() -> None:
    """The outline toggle should leave the base image untouched when disabled."""

    background = np.full((6, 6, 3), 90, dtype=np.uint8)
    mask = np.zeros((6, 6), dtype=np.uint8)
    mask[2:4, 2:4] = 255

    rendered = render_overlay(
        background,
        mode="outline",
        suspicious_mask=mask,
        show_outlines=False,
        show_labels=False,
        show_boxes=False,
    )

    np.testing.assert_array_equal(rendered, background)


def test_build_composite_stacks_display_bands() -> None:
    """Composite builder should stack red, green, and blue display bands."""

    red = np.full((2, 2), 10, dtype=np.uint8)
    green = np.full((2, 2), 20, dtype=np.uint8)
    blue = np.full((2, 2), 30, dtype=np.uint8)

    composite = build_composite(red, green, blue)

    assert composite.shape == (2, 2, 3)
    assert composite[0, 0].tolist() == [10, 20, 30]
