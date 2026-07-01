"""Tests for the analysis-app glossary tab."""

from __future__ import annotations

import os

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6 import QtWidgets

from plant_health_mvp.analysis_app.glossary import GlossaryWidget
from plant_health_mvp.analysis_app.main import AnalysisWindow


def _ensure_qapplication() -> QtWidgets.QApplication:
    app = QtWidgets.QApplication.instance()
    if app is None:
        app = QtWidgets.QApplication([])
    return app


def test_glossary_explains_real_threshold_targets() -> None:
    """Glossary text should name the actual score maps thresholds use."""

    _ensure_qapplication()
    widget = GlossaryWidget()
    widget.set_live_values(
        ndvi_threshold=0.2,
        spot_threshold=0.55,
        spot_min_area=20,
        texture_window=5,
    )
    text = widget.contents_text()

    assert "NDVI &gt; 0.2" in text
    assert "score_map &gt;= 0.55" in text
    assert "weighted_average(anomaly_maps)" in text
    assert "local standard deviation" in text
    assert "reflectance = (raw - dark) / (white - dark)" in text
    assert "exact:" in text
    assert "nearest:" in text
    assert "interpolated:" in text
    assert "missing:" in text


def test_analysis_window_has_glossary_tab_and_live_updates() -> None:
    """The main analysis app should expose the glossary as a dedicated tab."""

    _ensure_qapplication()
    window = AnalysisWindow()
    try:
        tabs = window.centralWidget().layout().itemAt(1).widget()
        tab_names = [tabs.tabText(index) for index in range(tabs.count())]
        assert "Glosar" in tab_names

        window.spot_threshold.setValue(0.7)
        assert "score_map &gt;= 0.7" in window.glossary.contents_text()
    finally:
        window.close()


def test_glossary_has_required_sections_and_alignment_terms() -> None:
    """Glossary should expose the requested section navigation and alignment terms."""

    _ensure_qapplication()
    widget = GlossaryWidget()
    text = widget.contents_text()
    tab_names = [widget.tabs.tabText(index) for index in range(widget.tabs.count())]

    for name in (
        "Pornire rapida",
        "Intrare si import",
        "Aliniere",
        "Vegetatie si masti",
        "Regiuni suspecte",
        "Masuratori si analiza",
        "Indici",
        "Rapoarte si iesiri",
    ):
        assert name in tab_names

    assert "Termen:</b> Translation" in text
    assert "Termen:</b> Euclidean" in text
    assert "Termen:</b> Affine" in text
    assert "Termen:</b> Homography" in text
    assert "Termen:</b> Raw intensity vs reflectance" in text
    assert "Termen:</b> Histogram" in text
    assert "Termen:</b> ROI" in text


def test_glossary_search_filters_cards() -> None:
    """Search should hide unrelated cards without removing content."""

    _ensure_qapplication()
    widget = GlossaryWidget()
    widget.search.setText("homography")

    visible_titles = [
        card.title()
        for card, _filter_text in widget._term_cards  # noqa: SLF001 - UI test checks visible card state.
        if not card.isHidden()
    ]

    assert "Homography" in visible_titles
    assert "Translation" not in visible_titles
