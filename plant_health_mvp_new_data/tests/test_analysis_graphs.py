"""Focused tests for the analysis-app graph helpers and widgets."""

from __future__ import annotations

import os

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import numpy as np
from PySide6 import QtWidgets

from plant_health_mvp.analysis_app.graphs import (
    HistogramStatsWidget,
    IndicesGraphWidget,
    SpectraGraphWidget,
    build_image_summary,
    build_index_plot_data,
    build_spectrum_plot_data,
)


def _ensure_qapplication() -> QtWidgets.QApplication:
    app = QtWidgets.QApplication.instance()
    if app is None:
        app = QtWidgets.QApplication([])
    return app


def _sample_report() -> dict[str, object]:
    return {
        "whole_leaf": {
            "average_bands": {
                "band_532": 0.20,
                "band_556": 0.30,
                "band_650": 0.40,
                "band_680": 0.50,
                "band_725": 0.60,
                "band_850": 0.80,
                "band_940": 0.70,
            },
            "indices": {
                "NDVI": {"value": 0.230769},
                "NDRE": {"value": 0.142857},
                "GNDVI": {"value": 0.454545},
                "CI_RE": {"value": 0.333333},
            },
        }
    }


def _sample_selected_region() -> dict[str, object]:
    return {
        "label": 7,
        "mean_band_532": 0.11,
        "mean_band_556": 0.21,
        "mean_band_650": 0.31,
        "mean_band_680": 0.41,
        "mean_band_725": 0.51,
        "mean_band_850": 0.71,
        "mean_band_940": 0.61,
    }


def test_build_spectrum_plot_data_uses_whole_leaf_and_selected_region() -> None:
    """Spectrum data should normalize the report and selected-region rows."""

    data = build_spectrum_plot_data(_sample_report(), _sample_selected_region())

    assert len(data.series) == 2
    assert data.series[0].label == "Frunza intreaga"
    assert data.series[1].label == "Regiune selectata"
    assert len(data.rows) == 7
    assert data.rows[0].whole_leaf == 0.2
    assert data.rows[0].selected_region == 0.11


def test_build_index_plot_data_can_compute_selected_region_values_from_bands() -> None:
    """Index data should compare whole leaf values against a selected region."""

    data = build_index_plot_data(_sample_report(), _sample_selected_region())

    assert data.rows
    ndvi = next(row for row in data.rows if row.name == "NDVI")
    assert ndvi.whole_leaf == 0.230769
    assert ndvi.selected_region is not None
    assert ndvi.selected_region != ndvi.whole_leaf


def test_build_image_summary_reports_basic_statistics() -> None:
    """Histogram summaries should report finite-pixel statistics."""

    image = np.array([[1.0, 2.0, np.nan], [3.0, 4.0, 5.0]], dtype=float)
    summary = build_image_summary(image)

    assert summary.image_shape == (2, 3)
    assert summary.finite_count == 5
    assert summary.minimum == 1.0
    assert summary.maximum == 5.0
    assert round(summary.mean or 0.0, 6) == 3.0
    assert summary.histogram_counts.size > 0


def test_widgets_construct_and_populate() -> None:
    """The Qt widgets should construct and accept data without a GUI session."""

    _ensure_qapplication()

    spectra = SpectraGraphWidget()
    spectra.set_report(_sample_report(), selected_region=_sample_selected_region())
    assert spectra.band_table.rowCount() == 7

    histogram = HistogramStatsWidget()
    histogram.set_image(np.arange(16, dtype=float).reshape(4, 4), label="Display")
    assert histogram.stats_table.rowCount() == 4

    indices = IndicesGraphWidget()
    indices.set_report(_sample_report(), selected_region=_sample_selected_region())
    assert indices.index_table.rowCount() > 0
