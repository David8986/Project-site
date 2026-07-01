"""Reusable dark-theme Qt/Matplotlib widgets for the analysis app.

The widgets in this module are intentionally narrow and data-driven:

* :class:`SpectraGraphWidget` plots whole-leaf target-band averages and, when
  available, a selected suspicious-region spectrum.
* :class:`HistogramStatsWidget` shows a histogram plus summary statistics for a
  display/background image array.
* :class:`IndicesGraphWidget` compares major vegetation indices for the whole
  leaf and an optional selected region.

Each widget accepts plain report dictionaries so the main window can wire them
in without duplicating parsing logic.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Mapping, Sequence

import numpy as np
from matplotlib.backends.backend_qtagg import FigureCanvasQTAgg as FigureCanvas
from matplotlib.figure import Figure
from PySide6 import QtCore, QtWidgets

from ..core.indices import compute_indices

TARGET_WAVELENGTHS_NM: tuple[int, ...] = (532, 556, 650, 680, 725, 850, 940)
MAJOR_INDICES: tuple[str, ...] = (
    "NDVI",
    "NDRE",
    "GNDVI",
    "CI_RE",
    "NDWI_850_940",
    "SR_RED",
    "SR_RE",
    "GRI",
    "RED_GREEN_RATIO",
)

BACKGROUND = "#202020"
PANEL_BACKGROUND = "#2b2b2b"
PLOT_BACKGROUND = "#111111"
PLOT_BORDER = "#777777"
TEXT = "#eeeeee"
MUTED_TEXT = "#cccccc"
GRID = "#555555"
ACCENT = "#dddddd"
ACCENT_2 = "#aaaaaa"
ACCENT_3 = "#888888"
BAR_EDGE = "#222222"


@dataclass(slots=True)
class SpectrumSeries:
    """A single spectrum line to plot."""

    label: str
    wavelengths_nm: np.ndarray
    values: np.ndarray
    color: str
    marker: str = "o"
    linewidth: float = 1.8


@dataclass(slots=True)
class BandComparisonRow:
    """Whole-leaf and selected-region values for one target band."""

    wavelength_nm: int
    whole_leaf: float | None
    selected_region: float | None


@dataclass(slots=True)
class IndexComparisonRow:
    """Whole-leaf and selected-region values for one index."""

    name: str
    whole_leaf: float | None
    selected_region: float | None


@dataclass(slots=True)
class ImageSummary:
    """Histogram and summary statistics for an image array."""

    image_shape: tuple[int, ...] | None
    value_count: int
    finite_count: int
    minimum: float | None
    maximum: float | None
    mean: float | None
    std: float | None
    histogram_counts: np.ndarray
    histogram_edges: np.ndarray

    @property
    def has_data(self) -> bool:
        """Return whether the summary includes usable values."""

        return self.finite_count > 0


@dataclass(slots=True)
class SpectrumPlotData:
    """Normalized spectrum payload for the spectra tab."""

    series: list[SpectrumSeries]
    rows: list[BandComparisonRow]
    message: str


@dataclass(slots=True)
class IndexPlotData:
    """Normalized index payload for the indices tab."""

    rows: list[IndexComparisonRow]
    message: str


def _is_mapping(value: Any) -> bool:
    return isinstance(value, Mapping)


def _nested_mapping(source: Mapping[str, Any] | None, *path: str) -> Mapping[str, Any] | None:
    current: Any = source
    for key in path:
        if not _is_mapping(current):
            return None
        current = current.get(key)
    return current if _is_mapping(current) else None


def _to_float(value: Any) -> float | None:
    """Convert a report value to ``float`` when possible."""

    if value is None:
        return None
    if isinstance(value, np.ndarray):
        if value.size != 1:
            return None
        return _to_float(value.reshape(-1)[0])
    if isinstance(value, np.generic):
        value = value.item()
    try:
        result = float(value)
    except (TypeError, ValueError):
        return None
    if not np.isfinite(result):
        return None
    return result


def _formatted(value: float | None) -> str:
    if value is None:
        return "n/a"
    return f"{value:.6g}"


def _value_from_candidates(source: Mapping[str, Any] | None, candidates: Sequence[str]) -> float | None:
    """Return the first usable float from a set of candidate keys."""

    if not _is_mapping(source):
        return None
    for key in candidates:
        if key not in source:
            continue
        value = _to_float(source.get(key))
        if value is not None:
            return value
    return None


def _extract_target_band_values(source: Mapping[str, Any] | None) -> dict[str, float | None]:
    """Extract the standard 7 target-band values from a mapping."""

    if not _is_mapping(source):
        return {}

    lookup = {
        532: ("532", "band_532", "mean_band_532"),
        556: ("556", "band_556", "mean_band_556"),
        650: ("650", "band_650", "mean_band_650"),
        680: ("680", "band_680", "mean_band_680"),
        725: ("725", "band_725", "mean_band_725"),
        850: ("850", "band_850", "mean_band_850"),
        940: ("940", "band_940", "mean_band_940"),
    }
    return {str(wavelength): _value_from_candidates(source, candidates) for wavelength, candidates in lookup.items()}


def _extract_calibrated_camera_values(report: Mapping[str, Any] | None) -> dict[str, float | None]:
    """Extract white-reference-corrected camera band values from a report."""

    calibration = _nested_mapping(report, "camera_calibration", "corrected_bands")
    if not _is_mapping(calibration):
        return {}

    values: dict[str, float | None] = {}
    for wavelength in TARGET_WAVELENGTHS_NM:
        item = calibration.get(str(wavelength))
        values[str(wavelength)] = (
            _to_float(item.get("white_normalized_camera"))
            if _is_mapping(item)
            else None
        )
    return values


def _extract_spectrum_arrays(source: Mapping[str, Any] | None) -> tuple[np.ndarray, np.ndarray] | None:
    """Extract an arbitrary spectrum from ``wavelengths``/``values`` style data."""

    if not _is_mapping(source):
        return None

    wavelength_candidates = ("wavelengths_nm", "wavelengths", "x", "band_wavelengths_nm")
    value_candidates = ("values", "spectrum", "intensities", "band_values", "y")

    wavelengths = None
    for key in wavelength_candidates:
        if key in source:
            wavelengths = np.asarray(source.get(key), dtype=float).reshape(-1)
            break

    values = None
    for key in value_candidates:
        if key in source:
            values = np.asarray(source.get(key), dtype=float).reshape(-1)
            break

    if wavelengths is None or values is None or wavelengths.size == 0 or values.size == 0:
        return None

    limit = min(wavelengths.size, values.size)
    wavelengths = wavelengths[:limit]
    values = values[:limit]
    mask = np.isfinite(wavelengths) & np.isfinite(values)
    if not np.any(mask):
        return None
    return wavelengths[mask], values[mask]


def _extract_index_values(source: Mapping[str, Any] | None) -> dict[str, float | None]:
    """Extract values from an index mapping or report section."""

    if not _is_mapping(source):
        return {}

    raw = source.get("indices") if _is_mapping(source.get("indices")) else source
    if not _is_mapping(raw):
        return {}

    values: dict[str, float | None] = {}
    for name in MAJOR_INDICES:
        item = raw.get(name)
        if _is_mapping(item):
            values[name] = _to_float(item.get("value"))
        else:
            values[name] = _to_float(item)
    return values


def _compute_index_values_from_bands(band_values: Mapping[str, float | None]) -> dict[str, float | None]:
    """Compute scalar indices from band averages when an indices section is absent."""

    usable = {key: value for key, value in band_values.items() if value is not None}
    if not usable:
        return {}

    try:
        computed = compute_indices(usable)
    except Exception:
        return {}

    values: dict[str, float | None] = {}
    for name in MAJOR_INDICES:
        item = computed.get(name, {})
        if _is_mapping(item):
            values[name] = _to_float(item.get("value"))
        else:
            values[name] = _to_float(item)
    return values


def _whole_leaf_band_source(report: Mapping[str, Any] | None) -> Mapping[str, Any] | None:
    """Return the most likely whole-leaf band section from a report dict."""

    if not _is_mapping(report):
        return None

    candidates = (
        _nested_mapping(report, "whole_leaf", "average_bands"),
        _nested_mapping(report, "whole_leaf"),
        _nested_mapping(report, "average_bands"),
        report,
    )
    for candidate in candidates:
        if _is_mapping(candidate):
            if any(key in candidate for key in ("whole_leaf", "average_bands", "band_532", "532", "mean_band_532")):
                return candidate
    return report


def _selected_band_source(selected_region: Mapping[str, Any] | None) -> Mapping[str, Any] | None:
    """Return the most likely selected-region band section."""

    if not _is_mapping(selected_region):
        return None

    candidates = (
        _nested_mapping(selected_region, "average_bands"),
        _nested_mapping(selected_region, "whole_leaf", "average_bands"),
        _nested_mapping(selected_region, "bands"),
        selected_region,
    )
    for candidate in candidates:
        if _is_mapping(candidate):
            if any(key in candidate for key in ("wavelengths_nm", "values", "band_532", "532", "mean_band_532")):
                return candidate
    return selected_region


def build_spectrum_plot_data(
    report: Mapping[str, Any] | None,
    selected_region: Mapping[str, Any] | None = None,
) -> SpectrumPlotData:
    """Normalize report data for the spectra tab."""

    whole_band_source = _whole_leaf_band_source(report)
    selected_band_source = _selected_band_source(selected_region)

    whole_bands = _extract_target_band_values(whole_band_source)
    selected_bands = _extract_target_band_values(selected_band_source)

    series: list[SpectrumSeries] = []
    rows: list[BandComparisonRow] = []

    whole_values = np.asarray([whole_bands.get(str(wavelength)) for wavelength in TARGET_WAVELENGTHS_NM], dtype=float)
    if np.isfinite(whole_values).any():
        series.append(
            SpectrumSeries(
                label="Frunza intreaga",
                wavelengths_nm=np.asarray(TARGET_WAVELENGTHS_NM, dtype=float),
                values=whole_values,
                color=ACCENT,
            )
        )

    calibrated_bands = _extract_calibrated_camera_values(report)
    calibrated_values = np.asarray([calibrated_bands.get(str(wavelength)) for wavelength in TARGET_WAVELENGTHS_NM], dtype=float)
    if np.isfinite(calibrated_values).any():
        series.append(
            SpectrumSeries(
                label="Camera corectata cu alb",
                wavelengths_nm=np.asarray(TARGET_WAVELENGTHS_NM, dtype=float),
                values=calibrated_values,
                color=ACCENT_3,
                marker="^",
                linewidth=1.5,
            )
        )

    selected_arrays = _extract_spectrum_arrays(selected_band_source)
    if selected_arrays is not None:
        wavelengths_nm, values = selected_arrays
        series.append(
            SpectrumSeries(
                label="Regiune selectata",
                wavelengths_nm=wavelengths_nm,
                values=values,
                color=ACCENT_2,
                marker="s",
            )
        )
    elif np.isfinite(np.asarray([selected_bands.get(str(wavelength)) for wavelength in TARGET_WAVELENGTHS_NM], dtype=float)).any():
        selected_values = np.asarray([selected_bands.get(str(wavelength)) for wavelength in TARGET_WAVELENGTHS_NM], dtype=float)
        series.append(
            SpectrumSeries(
                label="Regiune selectata",
                wavelengths_nm=np.asarray(TARGET_WAVELENGTHS_NM, dtype=float),
                values=selected_values,
                color=ACCENT_2,
                marker="s",
            )
        )

    for wavelength in TARGET_WAVELENGTHS_NM:
        rows.append(
            BandComparisonRow(
                wavelength_nm=wavelength,
                whole_leaf=whole_bands.get(str(wavelength)),
                selected_region=selected_bands.get(str(wavelength)),
            )
        )

    message = "Whole-leaf target bands ready."
    if len(series) == 1:
        message = "Benzile tinta pentru intreaga frunza sunt pregatite. Nu a fost furnizat niciun spectru pentru regiunea selectata."
    elif not series:
        message = "Nu au fost furnizate date pentru benzile tinta."
    else:
        message = "Benzile tinta pentru intreaga frunza sunt pregatite."

    return SpectrumPlotData(series=series, rows=rows, message=message)


def build_index_plot_data(
    report: Mapping[str, Any] | None,
    selected_region: Mapping[str, Any] | None = None,
) -> IndexPlotData:
    """Normalize report data for the indices tab."""

    whole_leaf_section = _nested_mapping(report, "whole_leaf", "indices") or _nested_mapping(report, "indices") or report
    selected_section = (
        _nested_mapping(selected_region, "indices")
        or _nested_mapping(selected_region, "mean_indices")
        or selected_region
    )

    whole_leaf_values = _extract_index_values(whole_leaf_section)
    if not any(value is not None for value in whole_leaf_values.values()):
        whole_band_source = _whole_leaf_band_source(report)
        whole_band_values = _extract_target_band_values(whole_band_source)
        whole_leaf_values = _compute_index_values_from_bands(whole_band_values)

    selected_values = _extract_index_values(selected_section)
    if not any(value is not None for value in selected_values.values()):
        selected_band_source = _selected_band_source(selected_region)
        selected_band_values = _extract_target_band_values(selected_band_source)
        selected_values = _compute_index_values_from_bands(selected_band_values)

    rows = [
        IndexComparisonRow(
            name=name,
            whole_leaf=whole_leaf_values.get(name),
            selected_region=selected_values.get(name),
        )
        for name in MAJOR_INDICES
        if whole_leaf_values.get(name) is not None or selected_values.get(name) is not None
    ]

    message = "Indicii principali sunt pregatiti."
    if not rows:
        message = "Nu au fost furnizate valori pentru indici."
    elif selected_region is None:
        message = "Indicii pentru intreaga frunza sunt pregatiti. Nu a fost furnizata nicio comparatie pentru regiunea selectata."

    return IndexPlotData(rows=rows, message=message)


def build_image_summary(image: np.ndarray | Sequence[Any] | None) -> ImageSummary:
    """Compute histogram-ready statistics for a display or background image."""

    if image is None:
        empty = np.asarray([], dtype=float)
        return ImageSummary(
            image_shape=None,
            value_count=0,
            finite_count=0,
            minimum=None,
            maximum=None,
            mean=None,
            std=None,
            histogram_counts=empty,
            histogram_edges=empty,
        )

    array = np.asarray(image, dtype=float)
    shape = tuple(int(value) for value in array.shape)
    flattened = array.reshape(-1)
    finite = flattened[np.isfinite(flattened)]
    if finite.size == 0:
        empty = np.asarray([], dtype=float)
        return ImageSummary(
            image_shape=shape,
            value_count=int(flattened.size),
            finite_count=0,
            minimum=None,
            maximum=None,
            mean=None,
            std=None,
            histogram_counts=empty,
            histogram_edges=empty,
        )

    bin_count = min(64, max(16, int(np.sqrt(finite.size))))
    counts, edges = np.histogram(finite, bins=bin_count)
    return ImageSummary(
        image_shape=shape,
        value_count=int(flattened.size),
        finite_count=int(finite.size),
        minimum=float(np.min(finite)),
        maximum=float(np.max(finite)),
        mean=float(np.mean(finite)),
        std=float(np.std(finite)),
        histogram_counts=counts.astype(float),
        histogram_edges=edges.astype(float),
    )


class _BaseGraphWidget(QtWidgets.QWidget):
    """Common styling for the analysis graphs."""

    def __init__(self, title: str, empty_message: str) -> None:
        super().__init__()
        self._title = title
        self._empty_message = empty_message
        self.figure = Figure(figsize=(6.0, 3.8), facecolor=BACKGROUND)
        self.canvas = FigureCanvas(self.figure)
        self.canvas.setSizePolicy(
            QtWidgets.QSizePolicy.Policy.Expanding,
            QtWidgets.QSizePolicy.Policy.Expanding,
        )
        self.axes = self.figure.add_subplot(111)
        self.axes.set_facecolor(PLOT_BACKGROUND)
        self._style_axes()
        layout = QtWidgets.QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(6)
        layout.addWidget(self.canvas, 1)

    def _style_axes(self) -> None:
        """Apply the shared dark theme to the current axes."""

        self.figure.patch.set_facecolor(BACKGROUND)
        self.axes.set_facecolor(PLOT_BACKGROUND)
        self.axes.tick_params(colors=TEXT, labelsize=9)
        for spine in self.axes.spines.values():
            spine.set_color(PLOT_BORDER)
        self.axes.grid(True, color=GRID, alpha=0.35, linewidth=0.8)
        self.axes.title.set_color(TEXT)
        self.axes.xaxis.label.set_color(TEXT)
        self.axes.yaxis.label.set_color(TEXT)

    def _show_empty_state(self, message: str | None = None) -> None:
        """Render a centered empty-state message on the plot."""

        self.axes.clear()
        self._style_axes()
        self.axes.set_axis_off()
        self.axes.text(
            0.5,
            0.5,
            message or self._empty_message,
            ha="center",
            va="center",
            color=MUTED_TEXT,
            fontsize=11,
            transform=self.axes.transAxes,
            wrap=True,
        )
        self.canvas.draw_idle()

    def _finalize_plot(self) -> None:
        """Redraw the canvas after plot updates."""

        self.canvas.draw_idle()


class SpectraGraphWidget(_BaseGraphWidget):
    """Dark spectrum plot with a compact target-band table."""

    def __init__(self, parent: QtWidgets.QWidget | None = None) -> None:
        super().__init__(
            "Spectre",
            "Incarca un raport pentru a vedea spectrul intregii frunze si orice regiune selectata.",
        )
        self.setParent(parent)
        self.band_table = QtWidgets.QTableWidget(0, 4)
        self.band_table.setHorizontalHeaderLabels(["Banda", "Frunza intreaga", "Regiune selectata", "Delta"])
        self.band_table.setEditTriggers(QtWidgets.QAbstractItemView.EditTrigger.NoEditTriggers)
        self.band_table.setSelectionMode(QtWidgets.QAbstractItemView.SelectionMode.NoSelection)
        self.band_table.verticalHeader().setVisible(False)
        self.band_table.horizontalHeader().setStretchLastSection(True)
        self.band_table.setAlternatingRowColors(True)
        self.band_table.setSizePolicy(
            QtWidgets.QSizePolicy.Policy.Expanding,
            QtWidgets.QSizePolicy.Policy.Preferred,
        )
        self.band_table.setMaximumHeight(240)
        self.band_table.setStyleSheet(
            "QTableWidget { background: #20262b; color: #e8eef2; gridline-color: #3a454d; }"
        )
        self.band_table.setWordWrap(False)
        self.layout().addWidget(self.band_table, 0)

    def clear(self) -> None:
        """Reset the widget to its empty state."""

        self.band_table.setRowCount(0)
        self._show_empty_state()

    def set_report(
        self,
        report: Mapping[str, Any] | None,
        *,
        selected_region: Mapping[str, Any] | None = None,
    ) -> None:
        """Populate the plot from a structured report dict."""

        data = build_spectrum_plot_data(report, selected_region)
        self.band_table.setRowCount(0)

        for row_data in data.rows:
            row = self.band_table.rowCount()
            self.band_table.insertRow(row)
            whole = row_data.whole_leaf
            selected = row_data.selected_region
            delta = None if whole is None or selected is None else selected - whole
            values = (
                f"{row_data.wavelength_nm} nm",
                _formatted(whole),
                _formatted(selected),
                _formatted(delta),
            )
            for column, text in enumerate(values):
                item = QtWidgets.QTableWidgetItem(text)
                if column > 0:
                    item.setTextAlignment(
                        QtCore.Qt.AlignmentFlag.AlignRight | QtCore.Qt.AlignmentFlag.AlignVCenter
                    )
                self.band_table.setItem(row, column, item)

        self.axes.clear()
        self._style_axes()
        if not data.series:
            self.band_table.setAlternatingRowColors(False)
            self._show_empty_state(data.message)
            return

        self.band_table.setAlternatingRowColors(True)
        for series in data.series:
            self.axes.plot(
                series.wavelengths_nm,
                series.values,
                color=series.color,
                marker=series.marker,
                linewidth=series.linewidth,
                markersize=5,
                label=series.label,
            )

        self.axes.set_title("Spectre", color=TEXT)
        self.axes.set_xlabel("Lungime de unda (nm)")
        self.axes.set_ylabel("Valoare banda tinta")
        self.axes.legend(frameon=False, labelcolor=TEXT, facecolor=BACKGROUND)
        self.axes.set_xticks(np.asarray(TARGET_WAVELENGTHS_NM, dtype=float))
        self.axes.set_xticklabels([str(value) for value in TARGET_WAVELENGTHS_NM], rotation=0)
        self.axes.margins(x=0.03, y=0.12)
        self.axes.set_axis_on()
        self._style_axes()
        self._finalize_plot()

    set_data = set_report


class HistogramStatsWidget(_BaseGraphWidget):
    """Histogram and statistics widget for display or background images."""

    def __init__(self, parent: QtWidgets.QWidget | None = None) -> None:
        super().__init__("Statistici / Histograma", "Incarca o imagine afisata sau de fundal pentru a inspecta histograma.")
        self.setParent(parent)
        self.summary_label = QtWidgets.QLabel("Nu este incarcata nicio imagine.")
        self.summary_label.setWordWrap(True)
        self.summary_label.setStyleSheet(f"color: {MUTED_TEXT};")

        self.stats_table = QtWidgets.QTableWidget(0, 2)
        self.stats_table.setHorizontalHeaderLabels(["Statistica", "Valoare"])
        self.stats_table.setEditTriggers(QtWidgets.QAbstractItemView.EditTrigger.NoEditTriggers)
        self.stats_table.setSelectionMode(QtWidgets.QAbstractItemView.SelectionMode.NoSelection)
        self.stats_table.verticalHeader().setVisible(False)
        self.stats_table.horizontalHeader().setStretchLastSection(True)
        self.stats_table.setAlternatingRowColors(True)
        self.stats_table.setMaximumHeight(180)
        self.stats_table.setStyleSheet(
            "QTableWidget { background: #20262b; color: #e8eef2; gridline-color: #3a454d; }"
        )

        layout = self.layout()
        layout.addWidget(self.summary_label, 0)
        layout.addWidget(self.stats_table, 0)

    def clear(self) -> None:
        """Reset the widget to its empty state."""

        self.summary_label.setText("Nu este incarcata nicio imagine.")
        self.stats_table.setRowCount(0)
        self._show_empty_state()

    def set_image(self, image: np.ndarray | Sequence[Any] | None, *, label: str | None = None) -> None:
        """Populate the histogram and summary statistics from an image array."""

        summary = build_image_summary(image)
        self.stats_table.setRowCount(0)

        rows = (
            ("Min", summary.minimum),
            ("Max", summary.maximum),
            ("Medie", summary.mean),
            ("Abatere std", summary.std),
        )
        for name, value in rows:
            row = self.stats_table.rowCount()
            self.stats_table.insertRow(row)
            self.stats_table.setItem(row, 0, QtWidgets.QTableWidgetItem(name))
            item = QtWidgets.QTableWidgetItem(_formatted(value))
            item.setTextAlignment(QtCore.Qt.AlignmentFlag.AlignRight | QtCore.Qt.AlignmentFlag.AlignVCenter)
            self.stats_table.setItem(row, 1, item)

        if not summary.has_data:
            self.summary_label.setText(
                label + ": nu exista pixeli fini disponibili." if label else "Nu exista pixeli fini disponibili."
            )
            self._show_empty_state(
                label + ": incarca o imagine pentru a vedea histograma." if label else None
            )
            return

        shape_text = " x ".join(str(part) for part in summary.image_shape or ())
        prefix = f"{label}: " if label else ""
        self.summary_label.setText(
            f"{prefix}{shape_text}, {summary.finite_count} valori finite, "
            f"min {_formatted(summary.minimum)}, max {_formatted(summary.maximum)}"
        )

        self.axes.clear()
        self._style_axes()
        widths = np.diff(np.asarray(summary.histogram_edges, dtype=float))
        self.axes.bar(
            np.asarray(summary.histogram_edges[:-1], dtype=float),
            np.asarray(summary.histogram_counts, dtype=float),
            width=widths,
            align="edge",
            color=ACCENT,
            edgecolor=BAR_EDGE,
            alpha=0.88,
        )
        self.axes.set_title("Histograma", color=TEXT)
        self.axes.set_xlabel("Valoare")
        self.axes.set_ylabel("Pixeli")
        self.axes.margins(x=0.02, y=0.08)
        self._finalize_plot()

    set_data = set_image


class IndicesGraphWidget(_BaseGraphWidget):
    """Grouped-bar comparison for the major vegetation indices."""

    def __init__(self, parent: QtWidgets.QWidget | None = None) -> None:
        super().__init__("Indici", "Incarca un raport pentru a compara indicii principali.")
        self.setParent(parent)
        self.index_table = QtWidgets.QTableWidget(0, 4)
        self.index_table.setHorizontalHeaderLabels(["Indice", "Frunza intreaga", "Regiune selectata", "Delta"])
        self.index_table.setEditTriggers(QtWidgets.QAbstractItemView.EditTrigger.NoEditTriggers)
        self.index_table.setSelectionMode(QtWidgets.QAbstractItemView.SelectionMode.NoSelection)
        self.index_table.verticalHeader().setVisible(False)
        self.index_table.horizontalHeader().setStretchLastSection(True)
        self.index_table.setAlternatingRowColors(True)
        self.index_table.setMaximumHeight(260)
        self.index_table.setStyleSheet(
            "QTableWidget { background: #20262b; color: #e8eef2; gridline-color: #3a454d; }"
        )
        self.message_label = QtWidgets.QLabel("Nu este incarcat niciun raport de indici.")
        self.message_label.setWordWrap(True)
        self.message_label.setStyleSheet(f"color: {MUTED_TEXT};")

        layout = self.layout()
        layout.addWidget(self.message_label, 0)
        layout.addWidget(self.index_table, 0)

    def clear(self) -> None:
        """Reset the widget to its empty state."""

        self.index_table.setRowCount(0)
        self.message_label.setText("Nu este incarcat niciun raport de indici.")
        self._show_empty_state()

    def set_report(
        self,
        report: Mapping[str, Any] | None,
        *,
        selected_region: Mapping[str, Any] | None = None,
    ) -> None:
        """Populate the grouped bar chart from a structured report dict."""

        data = build_index_plot_data(report, selected_region)
        self.index_table.setRowCount(0)

        for row_data in data.rows:
            row = self.index_table.rowCount()
            self.index_table.insertRow(row)
            delta = None
            if row_data.whole_leaf is not None and row_data.selected_region is not None:
                delta = row_data.selected_region - row_data.whole_leaf
            values = (
                row_data.name,
                _formatted(row_data.whole_leaf),
                _formatted(row_data.selected_region),
                _formatted(delta),
            )
            for column, text in enumerate(values):
                item = QtWidgets.QTableWidgetItem(text)
                if column > 0:
                    item.setTextAlignment(
                        QtCore.Qt.AlignmentFlag.AlignRight | QtCore.Qt.AlignmentFlag.AlignVCenter
                    )
                self.index_table.setItem(row, column, item)

        if not data.rows:
            self.message_label.setText(data.message)
            self._show_empty_state(data.message)
            return

        self.message_label.setText(data.message)
        self.axes.clear()
        self._style_axes()

        x_positions = np.arange(len(data.rows), dtype=float)
        width = 0.35
        whole = np.asarray([row.whole_leaf if row.whole_leaf is not None else np.nan for row in data.rows], dtype=float)
        selected = np.asarray([row.selected_region if row.selected_region is not None else np.nan for row in data.rows], dtype=float)
        plotted_whole = np.isfinite(whole).any()
        plotted_selected = np.isfinite(selected).any()

        if plotted_whole:
            self.axes.bar(
                x_positions - (width / 2 if plotted_selected else 0.0),
                whole,
                width=width if plotted_selected else 0.55,
                color=ACCENT,
                edgecolor=BAR_EDGE,
                label="Frunza intreaga",
            )
        if plotted_selected:
            self.axes.bar(
                x_positions + width / 2,
                selected,
                width=width,
                color=ACCENT_2,
                edgecolor=BAR_EDGE,
                label="Regiune selectata",
            )

        self.axes.set_title("Indici principali", color=TEXT)
        self.axes.set_ylabel("Valoare")
        self.axes.set_xticks(x_positions)
        self.axes.set_xticklabels([row.name for row in data.rows], rotation=25, ha="right")
        self.axes.set_xlim(-0.6, max(0.6, len(data.rows) - 0.4))
        self.axes.margins(y=0.14)
        if plotted_selected or plotted_whole:
            self.axes.legend(frameon=False, labelcolor=TEXT, facecolor=BACKGROUND)
        self._finalize_plot()

    set_data = set_report


__all__ = [
    "BandComparisonRow",
    "HistogramStatsWidget",
    "ImageSummary",
    "IndexComparisonRow",
    "IndexPlotData",
    "IndicesGraphWidget",
    "MAJOR_INDICES",
    "SpectrumPlotData",
    "SpectrumSeries",
    "SpectraGraphWidget",
    "TARGET_WAVELENGTHS_NM",
    "build_image_summary",
    "build_index_plot_data",
    "build_spectrum_plot_data",
]
