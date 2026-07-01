"""PySide6 hyperspectral explorer for dataset inspection and debugging.

The GUI deliberately sits above the analysis core. Dataset-specific loading is
handled by adapters, target-band extraction by ``band_extraction``, vegetation
and suspicious-region analysis by their core modules, and scalar index formulas
by ``indices``. Display stretching and optional destriping are view-only.
"""

from __future__ import annotations

import argparse
import csv
import json
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any, Iterable, Mapping

import numpy as np

try:  # pragma: no cover - exercised by manual GUI launch.
    from matplotlib.backends.backend_qtagg import FigureCanvasQTAgg as FigureCanvas
    from matplotlib.figure import Figure
    from PySide6 import QtCore, QtGui, QtWidgets
except ImportError as exc:  # pragma: no cover
    raise SystemExit(
        "Missing GUI dependencies. Install them with:\n"
        "  python -m pip install -r hyperspectral_viewer_requirements.txt"
    ) from exc

from ..adapters.base import AdapterSample, DatasetAdapter
from ..adapters.registry import adapter_for_path
from ..anomaly_detection import SpotDetectionConfig, detect_suspicious_spots, spot_result_to_report
from ..band_extraction import apply_target_bands
from ..band_profiles import PROFILES, TargetBandProfile, get_profile
from ..indices import build_indices_report, compute_indices
from ..models.sample import BandMapping, SpectralSample
from ..roi_tools import pixel_spectrum, roi_average_spectrum
from ..semantic_roles import BandRole, resolve_semantic_roles, role_band_array
from ..spectrum import compute_average_spectrum
from ..vegetation import apply_vegetation_mask
from ..wavelength_mapping import map_target_wavelengths


APP_STYLESHEET = """
QMainWindow, QWidget {
    background: #f5f6f7;
    color: #1f262c;
    font-size: 10pt;
}
QGroupBox {
    border: 1px solid #c7cdd2;
    border-radius: 6px;
    margin-top: 12px;
    padding: 12px 8px 8px 8px;
    font-weight: 600;
}
QGroupBox::title {
    subcontrol-origin: margin;
    left: 10px;
    padding: 0 4px;
    background: #f5f6f7;
}
QPushButton, QComboBox, QLineEdit, QSpinBox, QDoubleSpinBox {
    min-height: 28px;
    border: 1px solid #aeb6bf;
    border-radius: 6px;
    background: #ffffff;
    color: #1f262c;
    padding: 3px 7px;
}
QPushButton:hover, QComboBox:hover, QLineEdit:hover {
    border-color: #4f7f8f;
}
QPushButton:checked {
    background: #d9eef3;
    border-color: #2d7f95;
}
QPushButton:disabled {
    color: #8a939c;
    background: #eceff1;
}
QPlainTextEdit, QTextEdit, QTableWidget, QListWidget {
    border: 1px solid #c7cdd2;
    border-radius: 6px;
    background: #ffffff;
    color: #1f262c;
}
QLabel#ModeLabel {
    padding: 8px;
    border: 1px solid #b8c1c8;
    border-radius: 6px;
    background: #ffffff;
    color: #1f262c;
}
QSlider::groove:horizontal {
    height: 6px;
    background: #d5dade;
    border-radius: 3px;
}
QSlider::handle:horizontal {
    width: 18px;
    margin: -6px 0;
    border-radius: 9px;
    background: #2f7d95;
}
QTabWidget::pane {
    border: 1px solid #c7cdd2;
    background: #ffffff;
}
QTabBar::tab {
    background: #e7eaed;
    border: 1px solid #c7cdd2;
    padding: 7px 12px;
}
QTabBar::tab:selected {
    background: #ffffff;
}
"""


TARGET_WAVELENGTHS = (532.0, 556.0, 650.0, 680.0, 725.0, 850.0, 940.0)
SEMANTIC_ROLES = ("GREEN", "RED", "RED_EDGE", "NIR", "WATER_BAND")
VIEW_LABELS = {
    "raw": "main raw cube",
    "dark": "dark reference",
    "white": "white reference",
    "reflectance": "calibrated reflectance",
}


@dataclass(slots=True)
class SpectrumRecord:
    """One spectrum line shown/exported by the GUI."""

    name: str
    values: np.ndarray
    wavelengths: np.ndarray
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass(slots=True)
class BandStats:
    """Display and diagnostic statistics for one source band."""

    index: int
    wavelength: float | None
    minimum: float | None
    maximum: float | None
    mean: float | None
    std: float | None
    p1: float | None
    p99: float | None
    dynamic_range: float | None
    striping_score: float | None
    flags: tuple[str, ...]


class ImageCanvas(QtWidgets.QLabel):
    """Image label that maps mouse events back to image coordinates."""

    pixelClicked = QtCore.Signal(int, int)
    roiSelected = QtCore.Signal(int, int, int, int)

    def __init__(self) -> None:
        super().__init__()
        self.setMinimumSize(640, 420)
        self.setAlignment(QtCore.Qt.AlignmentFlag.AlignCenter)
        self.setStyleSheet("QLabel { background: #101214; border: 1px solid #20262b; }")
        self.setMouseTracking(True)
        self._source_shape: tuple[int, int] | None = None
        self._pixmap_rect = QtCore.QRect()
        self._base_pixmap: QtGui.QPixmap | None = None
        self._roi_mode = False
        self._drag_start: QtCore.QPoint | None = None
        self._drag_current: QtCore.QPoint | None = None

    def set_roi_mode(self, enabled: bool) -> None:
        """Toggle rectangular ROI selection mode."""

        self._roi_mode = bool(enabled)
        self._drag_start = None
        self._drag_current = None
        self.update()

    def set_array(self, image: np.ndarray) -> None:
        """Display a uint8 grayscale or RGB array."""

        array = np.ascontiguousarray(image.astype(np.uint8, copy=False))
        if array.ndim == 2:
            height, width = array.shape
            qimage = QtGui.QImage(
                array.data, width, height, width, QtGui.QImage.Format.Format_Grayscale8
            ).copy()
        elif array.ndim == 3 and array.shape[2] == 3:
            height, width, _ = array.shape
            qimage = QtGui.QImage(
                array.data, width, height, width * 3, QtGui.QImage.Format.Format_RGB888
            ).copy()
        else:
            raise ValueError(f"Expected grayscale/RGB display array, got {array.shape}.")

        self._source_shape = (height, width)
        self._base_pixmap = QtGui.QPixmap.fromImage(qimage)
        self._refresh_pixmap()

    def clear(self) -> None:
        """Clear the current image."""

        self._source_shape = None
        self._base_pixmap = None
        self._pixmap_rect = QtCore.QRect()
        self.setPixmap(QtGui.QPixmap())
        self.setText("Load a sample to inspect the cube")

    def resizeEvent(self, event: QtGui.QResizeEvent) -> None:
        super().resizeEvent(event)
        self._refresh_pixmap()

    def paintEvent(self, event: QtGui.QPaintEvent) -> None:
        super().paintEvent(event)
        if self._drag_start is None or self._drag_current is None:
            return
        rect = QtCore.QRect(self._drag_start, self._drag_current).normalized()
        rect = rect.intersected(self._pixmap_rect)
        if rect.isEmpty():
            return
        painter = QtGui.QPainter(self)
        painter.setPen(QtGui.QPen(QtGui.QColor("#00d1ff"), 2))
        painter.setBrush(QtGui.QColor(0, 209, 255, 45))
        painter.drawRect(rect)

    def mousePressEvent(self, event: QtGui.QMouseEvent) -> None:
        if event.button() != QtCore.Qt.MouseButton.LeftButton:
            return
        pos = event.position().toPoint()
        mapped = self._widget_to_image(pos)
        if mapped is None:
            return
        if self._roi_mode:
            self._drag_start = pos
            self._drag_current = pos
            self.update()
        else:
            x, y = mapped
            self.pixelClicked.emit(x, y)

    def mouseMoveEvent(self, event: QtGui.QMouseEvent) -> None:
        if self._roi_mode and self._drag_start is not None:
            self._drag_current = event.position().toPoint()
            self.update()

    def mouseReleaseEvent(self, event: QtGui.QMouseEvent) -> None:
        if (
            event.button() != QtCore.Qt.MouseButton.LeftButton
            or not self._roi_mode
            or self._drag_start is None
        ):
            return
        start = self._widget_to_image(self._drag_start)
        end = self._widget_to_image(event.position().toPoint())
        self._drag_start = None
        self._drag_current = None
        self.update()
        if start is None or end is None:
            return
        x0, y0 = start
        x1, y1 = end
        left, right = sorted((x0, x1))
        top, bottom = sorted((y0, y1))
        self.roiSelected.emit(left, top, right + 1, bottom + 1)

    def _refresh_pixmap(self) -> None:
        if self._base_pixmap is None:
            return
        scaled = self._base_pixmap.scaled(
            self.size(),
            QtCore.Qt.AspectRatioMode.KeepAspectRatio,
            QtCore.Qt.TransformationMode.SmoothTransformation,
        )
        self.setPixmap(scaled)
        x = (self.width() - scaled.width()) // 2
        y = (self.height() - scaled.height()) // 2
        self._pixmap_rect = QtCore.QRect(x, y, scaled.width(), scaled.height())

    def _widget_to_image(self, pos: QtCore.QPoint) -> tuple[int, int] | None:
        if self._source_shape is None or not self._pixmap_rect.contains(pos):
            return None
        height, width = self._source_shape
        rel_x = (pos.x() - self._pixmap_rect.x()) / max(1, self._pixmap_rect.width())
        rel_y = (pos.y() - self._pixmap_rect.y()) / max(1, self._pixmap_rect.height())
        x = min(width - 1, max(0, int(rel_x * width)))
        y = min(height - 1, max(0, int(rel_y * height)))
        return x, y


class PlotWidget(QtWidgets.QWidget):
    """Small matplotlib wrapper for spectra and histograms."""

    def __init__(self, title: str) -> None:
        super().__init__()
        self.figure = Figure(figsize=(5.5, 2.8), tight_layout=True, facecolor="white")
        self.canvas = FigureCanvas(self.figure)
        self.axes = self.figure.add_subplot(111)
        self.has_data = False
        layout = QtWidgets.QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.addWidget(self.canvas)
        self.clear(title)

    def clear(self, title: str) -> None:
        """Clear the plot."""

        self.axes.clear()
        self.axes.set_title(title)
        self.axes.grid(True, alpha=0.25)
        self.has_data = False
        self.canvas.draw_idle()

    def plot_spectra(self, records: Iterable[SpectrumRecord], *, title: str, y_label: str) -> None:
        """Plot one or more spectra."""

        self.axes.clear()
        plotted = False
        for record in records:
            x_values = record.wavelengths
            x_label = "Wavelength (nm)"
            if x_values.size != record.values.size:
                x_values = np.arange(record.values.size, dtype=float)
                x_label = "Band index"
            self.axes.plot(x_values, record.values, linewidth=1.5, label=record.name)
            plotted = True
        self.axes.set_title(title)
        self.axes.set_xlabel(x_label if plotted else "Band index")
        self.axes.set_ylabel(y_label)
        self.axes.grid(True, alpha=0.25)
        if plotted:
            self.axes.legend(loc="best")
        self.has_data = plotted
        self.canvas.draw_idle()

    def plot_histogram(self, values: np.ndarray, *, title: str) -> None:
        """Plot a finite-value histogram."""

        finite = np.asarray(values, dtype=float)
        finite = finite[np.isfinite(finite)]
        self.axes.clear()
        if finite.size:
            self.axes.hist(finite, bins=80, color="#2f7d95", alpha=0.82)
        self.axes.set_title(title)
        self.axes.set_xlabel("Value")
        self.axes.set_ylabel("Pixels")
        self.axes.grid(True, alpha=0.25)
        self.has_data = bool(finite.size)
        self.canvas.draw_idle()

    def save_png(self, path: str | Path) -> None:
        """Save the figure as PNG."""

        self.figure.savefig(path, dpi=160, bbox_inches="tight")


class MainWindow(QtWidgets.QMainWindow):
    """Adapter-driven hyperspectral inspection window."""

    def __init__(
        self,
        initial_input: str = "",
        initial_wavelengths: str = "",
        initial_output: str = "",
    ) -> None:
        super().__init__()
        self.setWindowTitle("Plant Health Hyperspectral Explorer")
        self.resize(1500, 930)

        self.adapter: DatasetAdapter | None = None
        self.adapter_sample: AdapterSample | None = None
        self.profile: TargetBandProfile = get_profile("profile_7band_default")
        self.active_sample: SpectralSample | None = None
        self.analysis_sample: SpectralSample | None = None
        self.roles: dict[str, BandRole] = {}
        self.current_band_image: np.ndarray | None = None
        self.current_display_image: np.ndarray | None = None
        self.pixel_records: list[SpectrumRecord] = []
        self.roi_records: dict[str, SpectrumRecord] = {}
        self.whole_leaf_record: SpectrumRecord | None = None
        self.indices_report: dict[str, Any] = {}
        self.spot_result: dict[str, Any] | None = None
        self.band_stats_cache: dict[str, list[BandStats]] = {}

        self._build_ui()
        self._connect_signals()
        self.image_canvas.clear()

        if initial_input:
            self.dataset_path.setText(initial_input)
        if initial_wavelengths:
            self.wavelength_path.setText(initial_wavelengths)
        self.output_path.setText(initial_output or str(Path("plant_health_mvp_new_data") / "runs" / "gui_export"))

    def _build_ui(self) -> None:
        root = QtWidgets.QWidget()
        layout = QtWidgets.QHBoxLayout(root)
        layout.setContentsMargins(12, 12, 12, 12)
        self.setCentralWidget(root)

        splitter = QtWidgets.QSplitter(QtCore.Qt.Orientation.Horizontal)
        splitter.setChildrenCollapsible(False)
        layout.addWidget(splitter)

        self.left_tabs = QtWidgets.QTabWidget()
        self.left_tabs.setMinimumWidth(360)
        self.left_tabs.setMaximumWidth(470)
        self.left_tabs.addTab(self._dataset_panel(), "Dataset")
        self.left_tabs.addTab(self._controls_panel(), "Band")
        self.left_tabs.addTab(self._analysis_panel(), "Analysis")
        self.left_tabs.addTab(self._export_panel(), "Export")
        splitter.addWidget(self.left_tabs)

        right = QtWidgets.QWidget()
        right_layout = QtWidgets.QVBoxLayout(right)
        right_layout.setContentsMargins(8, 0, 0, 0)
        right_splitter = QtWidgets.QSplitter(QtCore.Qt.Orientation.Vertical)
        right_splitter.setChildrenCollapsible(False)
        self.image_canvas = ImageCanvas()
        right_splitter.addWidget(self.image_canvas)
        self.info_tabs = QtWidgets.QTabWidget()
        self.info_tabs.setMinimumHeight(300)
        self.info_tabs.addTab(self._spectrum_panel(), "Spectra")
        self.info_tabs.addTab(self._stats_panel(), "Stats / Histogram")
        self.info_tabs.addTab(self._quality_panel(), "Quality")
        self.info_tabs.addTab(self._indices_panel(), "Indices")
        self.info_tabs.addTab(self._spots_panel(), "Suspicious regions")
        right_splitter.addWidget(self.info_tabs)
        right_splitter.setSizes([620, 310])
        right_layout.addWidget(right_splitter)
        splitter.addWidget(right)
        splitter.setSizes([400, 1100])

    def _dataset_panel(self) -> QtWidgets.QWidget:
        panel = QtWidgets.QWidget()
        layout = QtWidgets.QVBoxLayout(panel)
        form = QtWidgets.QFormLayout()
        self.dataset_path = QtWidgets.QLineEdit()
        self.wavelength_path = QtWidgets.QLineEdit()
        self.output_path = QtWidgets.QLineEdit()
        self.adapter_combo = QtWidgets.QComboBox()
        self.adapter_combo.addItems(["Auto / ENVI adapter", "Mock adapter"])
        self.profile_combo = QtWidgets.QComboBox()
        self.profile_combo.addItems(sorted(PROFILES))
        form.addRow("Dataset root or .hdr", self.dataset_path)
        form.addRow("Wavelength CSV", self.wavelength_path)
        form.addRow("Output folder", self.output_path)
        form.addRow("Adapter", self.adapter_combo)
        form.addRow("Band profile", self.profile_combo)
        layout.addLayout(form)

        buttons = QtWidgets.QGridLayout()
        self.choose_dataset_button = QtWidgets.QPushButton("Open dataset root")
        self.choose_hdr_button = QtWidgets.QPushButton("Open sample .hdr")
        self.choose_wavelength_button = QtWidgets.QPushButton("Load wavelength CSV")
        self.list_samples_button = QtWidgets.QPushButton("List samples")
        self.load_sample_button = QtWidgets.QPushButton("Load selected")
        self.load_mock_button = QtWidgets.QPushButton("Load mock")
        buttons.addWidget(self.choose_dataset_button, 0, 0)
        buttons.addWidget(self.choose_hdr_button, 0, 1)
        buttons.addWidget(self.choose_wavelength_button, 1, 0)
        buttons.addWidget(self.list_samples_button, 1, 1)
        buttons.addWidget(self.load_sample_button, 2, 0)
        buttons.addWidget(self.load_mock_button, 2, 1)
        layout.addLayout(buttons)

        self.sample_table = QtWidgets.QTableWidget(0, 6)
        self.sample_table.setHorizontalHeaderLabels(
            ["sample id", "main", "dark", "white", "preview", "wavelengths"]
        )
        self.sample_table.horizontalHeader().setStretchLastSection(True)
        self.sample_table.setSelectionBehavior(QtWidgets.QAbstractItemView.SelectionBehavior.SelectRows)
        self.sample_table.setEditTriggers(QtWidgets.QAbstractItemView.EditTrigger.NoEditTriggers)
        layout.addWidget(self.sample_table, 2)

        self.metadata_text = QtWidgets.QPlainTextEdit()
        self.metadata_text.setReadOnly(True)
        layout.addWidget(self.metadata_text, 2)
        return panel

    def _controls_panel(self) -> QtWidgets.QWidget:
        panel = QtWidgets.QWidget()
        layout = QtWidgets.QVBoxLayout(panel)

        view_group = QtWidgets.QGroupBox("Current view")
        view_layout = QtWidgets.QVBoxLayout(view_group)
        self.view_combo = QtWidgets.QComboBox()
        self.view_combo.addItem("Main raw cube", "raw")
        self.view_combo.addItem("Dark reference", "dark")
        self.view_combo.addItem("White reference", "white")
        self.view_combo.addItem("Calibrated reflectance", "reflectance")
        self.mode_label = QtWidgets.QLabel("No sample loaded")
        self.mode_label.setObjectName("ModeLabel")
        self.mode_label.setWordWrap(True)
        view_layout.addWidget(self.view_combo)
        view_layout.addWidget(self.mode_label)
        layout.addWidget(view_group)

        band_group = QtWidgets.QGroupBox("Band browser")
        band_layout = QtWidgets.QVBoxLayout(band_group)
        self.display_mode_combo = QtWidgets.QComboBox()
        self.display_mode_combo.addItems(["Raw display", "Min/max stretch", "Percentile stretch", "Histogram equalization"])
        self.image_mode_combo = QtWidgets.QComboBox()
        self.image_mode_combo.addItems(["Grayscale band", "False-color vegetation", "RGB-like approximation"])
        self.destripe_toggle = QtWidgets.QCheckBox("Display-only destriping preview")
        self.vegetation_overlay_toggle = QtWidgets.QCheckBox("Vegetation overlay")
        self.spot_overlay_toggle = QtWidgets.QCheckBox("Suspicious-region overlay")
        self.band_label = QtWidgets.QLabel("Band: -")
        self.band_slider = QtWidgets.QSlider(QtCore.Qt.Orientation.Horizontal)
        self.band_slider.setEnabled(False)
        band_layout.addWidget(self.image_mode_combo)
        band_layout.addWidget(self.display_mode_combo)
        band_layout.addWidget(self.destripe_toggle)
        band_layout.addWidget(self.vegetation_overlay_toggle)
        band_layout.addWidget(self.spot_overlay_toggle)
        band_layout.addWidget(self.band_label)
        band_layout.addWidget(self.band_slider)

        quick_grid = QtWidgets.QGridLayout()
        self.target_buttons: dict[float, QtWidgets.QPushButton] = {}
        for index, wavelength in enumerate(TARGET_WAVELENGTHS):
            button = QtWidgets.QPushButton(f"{wavelength:g} nm")
            self.target_buttons[wavelength] = button
            quick_grid.addWidget(button, index // 2, index % 2)
        band_layout.addLayout(quick_grid)

        role_grid = QtWidgets.QGridLayout()
        self.role_buttons: dict[str, QtWidgets.QPushButton] = {}
        for index, role in enumerate(SEMANTIC_ROLES):
            button = QtWidgets.QPushButton(role)
            self.role_buttons[role] = button
            role_grid.addWidget(button, index // 2, index % 2)
        band_layout.addLayout(role_grid)
        layout.addWidget(band_group)

        roi_group = QtWidgets.QGroupBox("Pixel / ROI")
        roi_layout = QtWidgets.QVBoxLayout(roi_group)
        self.roi_mode_toggle = QtWidgets.QPushButton("Drag rectangle ROI")
        self.roi_mode_toggle.setCheckable(True)
        self.roi_target_combo = QtWidgets.QComboBox()
        self.roi_target_combo.addItems(["ROI A", "ROI B", "Suspicious region"])
        self.pixel_summary = QtWidgets.QLabel("Click a pixel for its spectrum.")
        self.pixel_summary.setWordWrap(True)
        self.roi_summary = QtWidgets.QLabel("Drag ROI A and ROI B to compare spectra.")
        self.roi_summary.setWordWrap(True)
        roi_layout.addWidget(self.roi_mode_toggle)
        roi_layout.addWidget(self.roi_target_combo)
        roi_layout.addWidget(self.pixel_summary)
        roi_layout.addWidget(self.roi_summary)
        layout.addWidget(roi_group)
        layout.addStretch()
        return panel

    def _analysis_panel(self) -> QtWidgets.QWidget:
        panel = QtWidgets.QWidget()
        layout = QtWidgets.QVBoxLayout(panel)
        self.run_analysis_button = QtWidgets.QPushButton("Run vegetation + suspicious-region analysis")
        layout.addWidget(self.run_analysis_button)
        form = QtWidgets.QFormLayout()
        self.ndvi_threshold = QtWidgets.QDoubleSpinBox()
        self.ndvi_threshold.setRange(-1.0, 1.0)
        self.ndvi_threshold.setSingleStep(0.05)
        self.ndvi_threshold.setValue(0.2)
        self.spot_threshold = QtWidgets.QDoubleSpinBox()
        self.spot_threshold.setRange(0.0, 1.0)
        self.spot_threshold.setSingleStep(0.05)
        self.spot_threshold.setValue(0.55)
        self.spot_min_area = QtWidgets.QSpinBox()
        self.spot_min_area.setRange(1, 100000)
        self.spot_min_area.setValue(20)
        self.spot_texture_window = QtWidgets.QSpinBox()
        self.spot_texture_window.setRange(1, 51)
        self.spot_texture_window.setValue(5)
        form.addRow("NDVI mask threshold", self.ndvi_threshold)
        form.addRow("Spot score threshold", self.spot_threshold)
        form.addRow("Min spot area", self.spot_min_area)
        form.addRow("Texture window", self.spot_texture_window)
        layout.addLayout(form)
        self.analysis_text = QtWidgets.QPlainTextEdit()
        self.analysis_text.setReadOnly(True)
        layout.addWidget(self.analysis_text)
        return panel

    def _export_panel(self) -> QtWidgets.QWidget:
        panel = QtWidgets.QWidget()
        layout = QtWidgets.QVBoxLayout(panel)
        self.export_image_button = QtWidgets.QPushButton("Save displayed image PNG")
        self.export_spectrum_plot_button = QtWidgets.QPushButton("Save spectrum plot PNG")
        self.export_pixel_button = QtWidgets.QPushButton("Save clicked spectrum CSV/JSON")
        self.export_roi_button = QtWidgets.QPushButton("Save ROI spectra CSV/JSON")
        self.export_report_button = QtWidgets.QPushButton("Save sample analysis report JSON")
        self.export_spots_button = QtWidgets.QPushButton("Save suspicious-region table CSV")
        for button in (
            self.export_image_button,
            self.export_spectrum_plot_button,
            self.export_pixel_button,
            self.export_roi_button,
            self.export_report_button,
            self.export_spots_button,
        ):
            layout.addWidget(button)
        self.export_text = QtWidgets.QPlainTextEdit()
        self.export_text.setReadOnly(True)
        layout.addWidget(self.export_text)
        return panel

    def _spectrum_panel(self) -> QtWidgets.QWidget:
        panel = QtWidgets.QWidget()
        layout = QtWidgets.QVBoxLayout(panel)
        self.spectrum_plot = PlotWidget("Spectra")
        self.target_values_table = QtWidgets.QTableWidget(0, 4)
        self.target_values_table.setHorizontalHeaderLabels(["kind", "name", "band/wavelength", "value"])
        self.target_values_table.horizontalHeader().setStretchLastSection(True)
        layout.addWidget(self.spectrum_plot, 2)
        layout.addWidget(self.target_values_table, 1)
        return panel

    def _stats_panel(self) -> QtWidgets.QWidget:
        panel = QtWidgets.QWidget()
        layout = QtWidgets.QVBoxLayout(panel)
        self.histogram_plot = PlotWidget("Current band histogram")
        self.band_stats_text = QtWidgets.QPlainTextEdit()
        self.band_stats_text.setReadOnly(True)
        self.edge_strip = QtWidgets.QScrollArea()
        self.edge_strip.setWidgetResizable(True)
        self.edge_strip_container = QtWidgets.QWidget()
        self.edge_strip_layout = QtWidgets.QHBoxLayout(self.edge_strip_container)
        self.edge_strip_layout.setContentsMargins(4, 4, 4, 4)
        self.edge_strip.setWidget(self.edge_strip_container)
        layout.addWidget(self.histogram_plot, 2)
        layout.addWidget(self.band_stats_text, 1)
        layout.addWidget(QtWidgets.QLabel("Edge-band comparison strip: 0, 1, 2, 5, 10, 20"))
        layout.addWidget(self.edge_strip, 1)
        return panel

    def _quality_panel(self) -> QtWidgets.QWidget:
        panel = QtWidgets.QWidget()
        layout = QtWidgets.QVBoxLayout(panel)
        self.refresh_quality_button = QtWidgets.QPushButton("Refresh per-band diagnostics")
        self.quality_table = QtWidgets.QTableWidget(0, 10)
        self.quality_table.setHorizontalHeaderLabels(
            ["band", "nm", "min", "max", "mean", "std", "p1", "p99", "stripe", "flags"]
        )
        self.quality_table.horizontalHeader().setStretchLastSection(True)
        self.quality_text = QtWidgets.QPlainTextEdit()
        self.quality_text.setReadOnly(True)
        layout.addWidget(self.refresh_quality_button)
        layout.addWidget(self.quality_table, 3)
        layout.addWidget(self.quality_text, 1)
        return panel

    def _indices_panel(self) -> QtWidgets.QWidget:
        panel = QtWidgets.QWidget()
        layout = QtWidgets.QVBoxLayout(panel)
        self.indices_text = QtWidgets.QPlainTextEdit()
        self.indices_text.setReadOnly(True)
        layout.addWidget(self.indices_text)
        return panel

    def _spots_panel(self) -> QtWidgets.QWidget:
        panel = QtWidgets.QWidget()
        layout = QtWidgets.QVBoxLayout(panel)
        self.spots_table = QtWidgets.QTableWidget(0, 6)
        self.spots_table.setHorizontalHeaderLabels(["label", "area", "centroid", "bbox", "NDVI", "NDRE"])
        self.spots_table.horizontalHeader().setStretchLastSection(True)
        self.spot_detail_text = QtWidgets.QPlainTextEdit()
        self.spot_detail_text.setReadOnly(True)
        layout.addWidget(self.spots_table, 2)
        layout.addWidget(self.spot_detail_text, 2)
        return panel

    def _connect_signals(self) -> None:
        self.choose_dataset_button.clicked.connect(self._choose_dataset_root)
        self.choose_hdr_button.clicked.connect(self._choose_hdr)
        self.choose_wavelength_button.clicked.connect(self._choose_wavelength_csv)
        self.list_samples_button.clicked.connect(self._list_samples)
        self.load_sample_button.clicked.connect(self._load_selected_sample)
        self.load_mock_button.clicked.connect(self._load_mock)
        self.profile_combo.currentTextChanged.connect(self._profile_changed)
        self.view_combo.currentIndexChanged.connect(self._refresh_after_view_change)
        self.display_mode_combo.currentIndexChanged.connect(self._update_image)
        self.image_mode_combo.currentIndexChanged.connect(self._update_image)
        self.destripe_toggle.toggled.connect(self._update_image)
        self.vegetation_overlay_toggle.toggled.connect(self._update_image)
        self.spot_overlay_toggle.toggled.connect(self._update_image)
        self.band_slider.valueChanged.connect(self._update_image)
        self.image_canvas.pixelClicked.connect(self._inspect_pixel)
        self.image_canvas.roiSelected.connect(self._inspect_roi)
        self.roi_mode_toggle.toggled.connect(self.image_canvas.set_roi_mode)
        self.run_analysis_button.clicked.connect(self._run_analysis)
        self.refresh_quality_button.clicked.connect(self._refresh_quality_table)
        self.spots_table.cellClicked.connect(self._spot_table_clicked)
        self.export_image_button.clicked.connect(self._export_current_image)
        self.export_spectrum_plot_button.clicked.connect(self._export_spectrum_plot)
        self.export_pixel_button.clicked.connect(self._export_pixel_spectra)
        self.export_roi_button.clicked.connect(self._export_roi_spectra)
        self.export_report_button.clicked.connect(self._export_report)
        self.export_spots_button.clicked.connect(self._export_spots_csv)

        for wavelength, button in self.target_buttons.items():
            button.clicked.connect(lambda checked=False, value=wavelength: self._jump_to_wavelength(value))
        for role, button in self.role_buttons.items():
            button.clicked.connect(lambda checked=False, value=role: self._jump_to_role(value))

    def _choose_dataset_root(self) -> None:
        path = QtWidgets.QFileDialog.getExistingDirectory(self, "Choose dataset root or sample folder")
        if path:
            self.dataset_path.setText(path)
            self._list_samples()

    def _choose_hdr(self) -> None:
        path, _ = QtWidgets.QFileDialog.getOpenFileName(
            self, "Choose ENVI sample header", "", "ENVI header (*.hdr);;All files (*.*)"
        )
        if not path:
            return
        hdr = Path(path)
        sample_root = hdr.parent.parent if hdr.parent.name.lower() == "capture" else hdr.parent
        self.dataset_path.setText(str(sample_root))
        self._list_samples()
        self._load_selected_sample()

    def _choose_wavelength_csv(self) -> None:
        path, _ = QtWidgets.QFileDialog.getOpenFileName(
            self, "Choose wavelength CSV", "", "CSV/Text files (*.csv *.txt);;All files (*.*)"
        )
        if path:
            self.wavelength_path.setText(path)

    def _profile_changed(self, profile_name: str) -> None:
        self.profile = get_profile(profile_name)
        if self.adapter_sample is not None:
            self._prepare_active_sample()
            self._update_image()

    def _list_samples(self) -> None:
        try:
            self.adapter = self._make_adapter()
            sample_ids = self.adapter.list_samples()
        except Exception as exc:
            self._show_error("Could not list samples", str(exc))
            return

        self.sample_table.setRowCount(0)
        for sample_id in sample_ids or ["default"]:
            self._append_sample_row(sample_id)
        self.metadata_text.setPlainText(f"Adapter: {self.adapter.adapter_name}\nSamples: {len(sample_ids)}")

    def _load_selected_sample(self) -> None:
        if self.adapter is None:
            self._list_samples()
        if self.adapter is None:
            return
        row = self.sample_table.currentRow()
        sample_id = None
        if row >= 0:
            item = self.sample_table.item(row, 0)
            sample_id = item.text() if item is not None and item.text() != "default" else None
        try:
            self.adapter_sample = self.adapter.load_sample(sample_id)
        except Exception as exc:
            self._show_error("Could not load sample", str(exc))
            return

        self.band_stats_cache.clear()
        self.pixel_records.clear()
        self.roi_records.clear()
        self.whole_leaf_record = None
        self.indices_report = {}
        self.spot_result = None
        self.analysis_sample = None
        self._prepare_active_sample()
        self._configure_band_slider()
        self._update_dataset_metadata()
        self._update_image()
        self._refresh_quality_table()
        self.statusBar().showMessage(f"Loaded sample: {self.adapter_sample.sample_id}", 6000)

    def _load_mock(self) -> None:
        self.dataset_path.setText("mock")
        self.adapter_combo.setCurrentText("Mock adapter")
        self._list_samples()
        self._load_selected_sample()

    def _make_adapter(self) -> DatasetAdapter:
        wavelength_csv = self.wavelength_path.text().strip() or None
        adapter_choice = self.adapter_combo.currentText()
        if adapter_choice == "Mock adapter":
            return adapter_for_path("mock", wavelength_csv)
        path_text = self.dataset_path.text().strip()
        if not path_text:
            return adapter_for_path("mock", wavelength_csv)
        root = Path(path_text).expanduser()
        if root.suffix.lower() == ".hdr":
            root = root.parent.parent if root.parent.name.lower() == "capture" else root.parent
        return adapter_for_path(root, wavelength_csv)

    def _append_sample_row(self, sample_id: str) -> None:
        row = self.sample_table.rowCount()
        self.sample_table.insertRow(row)
        info = self._sample_file_info(sample_id)
        values = [
            sample_id,
            "yes" if info.get("main") else "?",
            "yes" if info.get("dark") else "no",
            "yes" if info.get("white") else "no",
            "yes" if info.get("preview") else "no",
            info.get("wavelengths", "adapter/csv"),
        ]
        for column, value in enumerate(values):
            self.sample_table.setItem(row, column, QtWidgets.QTableWidgetItem(str(value)))
        if row == 0:
            self.sample_table.selectRow(0)

    def _sample_file_info(self, sample_id: str) -> dict[str, Any]:
        root_text = self.dataset_path.text().strip()
        if not root_text:
            return {}
        root = Path(root_text).expanduser()
        sample_root = root / sample_id if root.is_dir() and (root / sample_id).is_dir() else root
        capture_dir = sample_root / "capture" if (sample_root / "capture").is_dir() else sample_root
        if not capture_dir.exists():
            return {}
        files = [path.name for path in capture_dir.iterdir() if path.is_file() and not path.name.startswith("._")]
        lower = [name.lower() for name in files]
        return {
            "main": any(name.endswith(".raw") and not name.startswith(("darkref_", "whiteref_")) for name in lower),
            "dark": any(name.startswith("darkref_") and name.endswith(".raw") for name in lower),
            "white": any(name.startswith("whiteref_") and name.endswith(".raw") for name in lower),
            "preview": any(name.endswith((".png", ".jpg", ".jpeg")) for name in lower),
            "wavelengths": "csv" if self.wavelength_path.text().strip() else "header/csv",
        }

    def _prepare_active_sample(self) -> None:
        if self.adapter_sample is None:
            self.active_sample = None
            self.roles = {}
            return
        data = self._current_cube(require=False)
        if data is None:
            data = self.adapter_sample.cube
        metadata = dict(self.adapter_sample.metadata)
        metadata["current_view"] = self._view_mode()
        self.active_sample = SpectralSample(
            source_type=self.adapter_sample.source_type,
            available_wavelengths=np.asarray(self.adapter_sample.wavelengths, dtype=float),
            data=np.asarray(data),
            metadata=metadata,
        )
        mappings = map_target_wavelengths(self.active_sample.available_wavelengths, self.profile.wavelengths_nm)
        apply_target_bands(self.active_sample, mappings)
        self.roles = resolve_semantic_roles(self.active_sample, self.profile.roles)

    def _configure_band_slider(self) -> None:
        cube = self._current_cube(require=False)
        if cube is None or cube.ndim != 3:
            self.band_slider.setEnabled(False)
            return
        self.band_slider.blockSignals(True)
        self.band_slider.setRange(0, cube.shape[2] - 1)
        self.band_slider.setValue(min(self.band_slider.value(), cube.shape[2] - 1))
        self.band_slider.blockSignals(False)
        self.band_slider.setEnabled(True)

    def _refresh_after_view_change(self) -> None:
        self._prepare_active_sample()
        self._configure_band_slider()
        self._update_image()
        self._refresh_quality_table()

    def _current_cube(self, *, require: bool = True) -> np.ndarray | None:
        if self.adapter_sample is None:
            if require:
                raise RuntimeError("No sample is loaded.")
            return None
        mode = self._view_mode()
        cube: np.ndarray | None
        if mode == "raw":
            cube = self.adapter_sample.cube
        elif mode == "dark":
            cube = self.adapter_sample.dark_reference
        elif mode == "white":
            cube = self.adapter_sample.white_reference
        elif mode == "reflectance":
            cube = self.adapter_sample.reflectance_cube
        else:
            cube = None
        if cube is None and require:
            raise RuntimeError(self._view_unavailable_reason(mode))
        return None if cube is None else np.asarray(cube)

    def _view_mode(self) -> str:
        return str(self.view_combo.currentData())

    def _view_unavailable_reason(self, mode: str) -> str:
        if self.adapter_sample is None:
            return "No sample is loaded."
        if mode == "dark":
            return "Dark reference is not loaded for this sample."
        if mode == "white":
            return "White reference is not loaded for this sample."
        if mode == "reflectance":
            calibration = self.adapter_sample.metadata.get("calibration", {})
            reason = calibration.get("reason", "missing or invalid dark/white references")
            return f"Calibrated reflectance is unavailable: {reason}."
        return "The requested view is unavailable."

    def _update_dataset_metadata(self) -> None:
        if self.adapter_sample is None:
            return
        sample = self.adapter_sample
        wavelengths = np.asarray(sample.wavelengths, dtype=float)
        finite = wavelengths[np.isfinite(wavelengths)]
        shape = list(np.asarray(sample.cube).shape)
        metadata = {
            "sample_id": sample.sample_id,
            "source_type": sample.source_type,
            "cube_shape": shape,
            "wavelength_count": int(wavelengths.size),
            "wavelength_range_nm": None
            if finite.size == 0
            else [float(np.min(finite)), float(np.max(finite))],
            "has_dark_reference": sample.dark_reference is not None,
            "has_white_reference": sample.white_reference is not None,
            "has_reflectance": sample.reflectance_cube is not None,
            "current_view": VIEW_LABELS.get(self._view_mode()),
            "interleave": sample.metadata.get("envi_interleave"),
            "dtype": sample.metadata.get("envi_data_type"),
            "calibration": sample.metadata.get("calibration"),
            "target_profile": self.profile.name,
            "edge_band_warning": "Bands near the first/last 5 positions are flagged as low-confidence edge bands.",
            "metadata": sample.metadata,
        }
        self.metadata_text.setPlainText(json.dumps(metadata, indent=2, default=str))

    def _update_image(self) -> None:
        if self.adapter_sample is None:
            self.image_canvas.clear()
            return
        try:
            cube = self._current_cube()
        except Exception as exc:
            self.image_canvas.clear()
            self.mode_label.setText(f"Showing: {VIEW_LABELS.get(self._view_mode())}\n{exc}")
            return
        if cube.ndim != 3:
            self.image_canvas.clear()
            self.mode_label.setText(f"Current view is not a 3D cube: {cube.shape}")
            return

        self._prepare_active_sample()
        mode = self.image_mode_combo.currentText()
        try:
            if mode == "False-color vegetation":
                display = self._composite_image(("NIR", "RED_EDGE", "RED"))
                self.current_band_image = None
            elif mode == "RGB-like approximation":
                display = self._composite_image(("RED_650", "GREEN_556", "BLUE_532"))
                self.current_band_image = None
            else:
                band_index = int(self.band_slider.value())
                band = np.asarray(cube[:, :, band_index], dtype=float)
                if self.destripe_toggle.isChecked():
                    band = self._destriped_preview(band)
                self.current_band_image = band
                display = self._normalize_for_display(band)
                self._update_band_stats_ui(band_index, band)
                self.histogram_plot.plot_histogram(band, title=f"Band {band_index} histogram")
        except Exception as exc:
            self.image_canvas.clear()
            self.mode_label.setText(str(exc))
            return

        display = self._apply_overlays(display)
        self.current_display_image = display
        self.image_canvas.set_array(display)
        self._update_band_label()
        self._update_mode_label()
        self._update_edge_strip()

    def _update_band_label(self) -> None:
        cube = self._current_cube(require=False)
        if cube is None or cube.ndim != 3:
            self.band_label.setText("Band: -")
            return
        index = int(self.band_slider.value())
        wavelength = self._wavelength_for_index(index)
        suffix = "" if wavelength is None else f" / {wavelength:.2f} nm"
        self.band_label.setText(f"Band {index} / {cube.shape[2] - 1}{suffix}")

    def _update_mode_label(self) -> None:
        if self.adapter_sample is None:
            self.mode_label.setText("No sample loaded")
            return
        mode = self._view_mode()
        calibration = self.adapter_sample.metadata.get("calibration", {})
        warnings = []
        if mode != "reflectance":
            warnings.append("Analysis values may be raw counts unless reflectance is selected/available.")
        if calibration and not calibration.get("calibration_applied") and mode == "reflectance":
            warnings.append(str(calibration.get("reason", "Calibration unavailable.")))
        text = f"Showing: {VIEW_LABELS.get(mode, mode)}\nSample: {self.adapter_sample.sample_id}"
        if warnings:
            text += "\n" + "\n".join(warnings)
        self.mode_label.setText(text)

    def _composite_image(self, roles_or_keys: tuple[str, str, str]) -> np.ndarray:
        if self.active_sample is None:
            raise RuntimeError("No active sample is prepared.")
        channels: list[np.ndarray] = []
        for role_or_key in roles_or_keys:
            if role_or_key == "RED_650":
                band = self._band_for_target_wavelength(650.0)
            elif role_or_key == "GREEN_556":
                band = self._band_for_target_wavelength(556.0)
            elif role_or_key == "BLUE_532":
                band = self._band_for_target_wavelength(532.0)
            else:
                band = role_band_array(self.active_sample, self.roles, role_or_key)
            if band is None:
                raise RuntimeError(f"Composite cannot be built: missing {role_or_key}.")
            channels.append(self._normalize_for_display(np.asarray(band, dtype=float)))
        return np.stack(channels, axis=-1).astype(np.uint8)

    def _band_for_target_wavelength(self, wavelength: float) -> np.ndarray | None:
        if self.active_sample is None:
            return None
        mapping = self._mapping_for_wavelength(wavelength)
        if mapping is None or not mapping.source_indices:
            return None
        key = str(int(wavelength)) if float(wavelength).is_integer() else f"{wavelength:g}"
        band = self.active_sample.target_bands.get(key)
        return None if band is None else np.asarray(band, dtype=float)

    def _mapping_for_wavelength(self, wavelength: float) -> BandMapping | None:
        if self.active_sample is None:
            return None
        key = str(int(wavelength)) if float(wavelength).is_integer() else f"{wavelength:g}"
        return self.active_sample.band_mappings.get(key)

    def _normalize_for_display(self, band: np.ndarray) -> np.ndarray:
        values = np.asarray(band, dtype=float)
        finite = values[np.isfinite(values)]
        if finite.size == 0:
            return np.zeros(values.shape, dtype=np.uint8)
        mode = self.display_mode_combo.currentText()
        if mode == "Raw display":
            clipped = np.clip(values, 0, 255)
            clipped[~np.isfinite(clipped)] = 0
            return clipped.astype(np.uint8)
        if mode == "Min/max stretch":
            low = float(np.min(finite))
            high = float(np.max(finite))
        else:
            low, high = np.percentile(finite, [1.0, 99.0])
        if high <= low:
            return np.zeros(values.shape, dtype=np.uint8)
        scaled = np.clip((values - low) / (high - low), 0.0, 1.0)
        scaled[~np.isfinite(scaled)] = 0.0
        if mode == "Histogram equalization":
            scaled = self._equalize_display(scaled)
        return (scaled * 255.0).astype(np.uint8)

    def _equalize_display(self, scaled: np.ndarray) -> np.ndarray:
        finite = scaled[np.isfinite(scaled)]
        if finite.size == 0:
            return np.zeros_like(scaled)
        hist, bins = np.histogram(finite, bins=256, range=(0.0, 1.0), density=False)
        cdf = hist.cumsum().astype(float)
        if cdf[-1] <= 0:
            return scaled
        cdf /= cdf[-1]
        equalized = np.interp(np.clip(scaled, 0, 1).ravel(), bins[:-1], cdf).reshape(scaled.shape)
        equalized[~np.isfinite(equalized)] = 0.0
        return equalized

    def _destriped_preview(self, band: np.ndarray) -> np.ndarray:
        values = np.asarray(band, dtype=float).copy()
        col_median = np.nanmedian(values, axis=0)
        global_median = float(np.nanmedian(values))
        correction = col_median - global_median
        return values - correction[np.newaxis, :]

    def _apply_overlays(self, display: np.ndarray) -> np.ndarray:
        if display.ndim == 2:
            rgb = np.stack([display, display, display], axis=-1).astype(np.float32)
        else:
            rgb = display.astype(np.float32)
        analysis_sample = self.analysis_sample
        if analysis_sample is not None and self.vegetation_overlay_toggle.isChecked() and analysis_sample.mask is not None:
            mask = np.asarray(analysis_sample.mask, dtype=bool)
            if mask.shape == rgb.shape[:2]:
                rgb[mask] = (0.72 * rgb[mask]) + (0.28 * np.array([40, 210, 90]))
        if self.spot_overlay_toggle.isChecked() and self.spot_result is not None:
            mask = self.spot_result.get("suspicious_mask")
            if mask is not None:
                spot_mask = np.asarray(mask, dtype=bool)
                if spot_mask.shape == rgb.shape[:2]:
                    rgb[spot_mask] = (0.45 * rgb[spot_mask]) + (0.55 * np.array([255, 40, 40]))
            labels = self.spot_result.get("labels")
            if labels is not None:
                rgb = self._draw_label_boxes(rgb, np.asarray(labels))
        return np.clip(rgb, 0, 255).astype(np.uint8)

    def _draw_label_boxes(self, rgb: np.ndarray, labels: np.ndarray) -> np.ndarray:
        output = rgb.copy()
        for label in np.unique(labels):
            if label <= 0:
                continue
            ys, xs = np.nonzero(labels == label)
            if ys.size == 0:
                continue
            x0, x1 = int(xs.min()), int(xs.max())
            y0, y1 = int(ys.min()), int(ys.max())
            output[y0 : y1 + 1, [x0, x1], :] = [255, 230, 0]
            output[[y0, y1], x0 : x1 + 1, :] = [255, 230, 0]
        return output

    def _update_band_stats_ui(self, band_index: int, band: np.ndarray) -> None:
        stats = self._stats_for_band(band_index, band)
        self.band_stats_text.setPlainText(
            "\n".join(
                [
                    f"band: {stats.index}",
                    f"wavelength: {'' if stats.wavelength is None else f'{stats.wavelength:.3f} nm'}",
                    f"min: {self._fmt(stats.minimum)}",
                    f"max: {self._fmt(stats.maximum)}",
                    f"mean: {self._fmt(stats.mean)}",
                    f"std: {self._fmt(stats.std)}",
                    f"p1/p99: {self._fmt(stats.p1)} / {self._fmt(stats.p99)}",
                    f"dynamic range: {self._fmt(stats.dynamic_range)}",
                    f"striping score: {self._fmt(stats.striping_score)}",
                    f"flags: {', '.join(stats.flags) if stats.flags else 'none'}",
                ]
            )
        )

    def _stats_for_band(self, band_index: int, band: np.ndarray) -> BandStats:
        values = np.asarray(band, dtype=float)
        finite = values[np.isfinite(values)]
        flags: list[str] = []
        wavelength = self._wavelength_for_index(band_index)
        cube = self._current_cube(require=False)
        band_count = 0 if cube is None or cube.ndim != 3 else cube.shape[2]
        if band_index < 5 or (band_count and band_index >= band_count - 5):
            flags.append("edge-band")
        if finite.size == 0:
            return BandStats(band_index, wavelength, None, None, None, None, None, None, None, None, tuple(flags + ["no-finite-values"]))
        minimum = float(np.min(finite))
        maximum = float(np.max(finite))
        mean = float(np.mean(finite))
        std = float(np.std(finite))
        p1, p99 = [float(value) for value in np.percentile(finite, [1.0, 99.0])]
        dynamic_range = p99 - p1
        stripe_score = self._stripe_score(values, std)
        if dynamic_range <= max(1e-9, abs(mean) * 0.002):
            flags.append("low-dynamic-range")
        if stripe_score is not None and stripe_score > 0.18:
            flags.append("possible-striping")
        return BandStats(
            band_index,
            wavelength,
            minimum,
            maximum,
            mean,
            std,
            p1,
            p99,
            dynamic_range,
            stripe_score,
            tuple(flags),
        )

    def _stripe_score(self, values: np.ndarray, std: float) -> float | None:
        if values.ndim != 2 or std <= 1e-12:
            return None
        col_means = np.nanmean(values, axis=0)
        row_means = np.nanmean(values, axis=1)
        return float(max(np.nanstd(col_means), np.nanstd(row_means)) / (std + 1e-12))

    def _refresh_quality_table(self) -> None:
        cube = self._current_cube(require=False)
        if cube is None or cube.ndim != 3:
            self.quality_table.setRowCount(0)
            self.quality_text.setPlainText("Load a 3D cube to compute quality diagnostics.")
            return
        mode = self._view_mode()
        stats = self.band_stats_cache.get(mode)
        if stats is None:
            stats = [self._stats_for_band(index, cube[:, :, index]) for index in range(cube.shape[2])]
            self.band_stats_cache[mode] = stats
        self.quality_table.setRowCount(0)
        for stat in stats:
            row = self.quality_table.rowCount()
            self.quality_table.insertRow(row)
            values = [
                stat.index,
                "" if stat.wavelength is None else f"{stat.wavelength:.2f}",
                self._fmt(stat.minimum),
                self._fmt(stat.maximum),
                self._fmt(stat.mean),
                self._fmt(stat.std),
                self._fmt(stat.p1),
                self._fmt(stat.p99),
                self._fmt(stat.striping_score),
                ", ".join(stat.flags),
            ]
            for column, value in enumerate(values):
                self.quality_table.setItem(row, column, QtWidgets.QTableWidgetItem(str(value)))
        flagged = [stat for stat in stats if stat.flags]
        note = [
            f"View: {VIEW_LABELS.get(mode, mode)}",
            f"Computed diagnostics for {len(stats)} bands.",
            f"Flagged bands: {len(flagged)}",
        ]
        if mode != "reflectance":
            note.append("Note: diagnostics and indices on this view use raw/reference counts, not reflectance.")
        note.append("Low-confidence edge bands are informational; inspect them before using them scientifically.")
        self.quality_text.setPlainText("\n".join(note))

    def _update_edge_strip(self) -> None:
        while self.edge_strip_layout.count():
            item = self.edge_strip_layout.takeAt(0)
            if item.widget():
                item.widget().deleteLater()
        cube = self._current_cube(require=False)
        if cube is None or cube.ndim != 3:
            return
        for index in [0, 1, 2, 5, 10, 20]:
            if index >= cube.shape[2]:
                continue
            thumb = self._normalize_for_display(cube[:, :, index])
            label = QtWidgets.QLabel(f"{index}")
            label.setAlignment(QtCore.Qt.AlignmentFlag.AlignCenter)
            qimage = QtGui.QImage(thumb.data, thumb.shape[1], thumb.shape[0], thumb.shape[1], QtGui.QImage.Format.Format_Grayscale8).copy()
            label.setPixmap(QtGui.QPixmap.fromImage(qimage).scaled(120, 80, QtCore.Qt.AspectRatioMode.KeepAspectRatio))
            self.edge_strip_layout.addWidget(label)
        self.edge_strip_layout.addStretch()

    def _inspect_pixel(self, x: int, y: int) -> None:
        if self.active_sample is None:
            return
        labels = self.spot_result.get("labels") if self.spot_result is not None else None
        if labels is not None and np.asarray(labels).shape[:2] == self.active_sample.data.shape[:2]:
            label = int(np.asarray(labels)[y, x])
            if label > 0:
                self._inspect_spot_label(label)
        try:
            result = pixel_spectrum(self.active_sample, x, y)
        except Exception as exc:
            self._show_error("Could not inspect pixel", str(exc))
            return
        values = np.asarray(result["values"], dtype=float)
        wavelengths = np.asarray(result["wavelengths"], dtype=float)
        record = SpectrumRecord(f"Pixel ({x}, {y})", values, wavelengths, {"x": x, "y": y})
        self.pixel_records = [record]
        self._refresh_spectrum_plot()
        self._fill_target_values(record)
        self.pixel_summary.setText(f"Pixel ({x}, {y}) plotted. {self._target_value_summary(values)}")

    def _inspect_roi(self, x0: int, y0: int, x1: int, y1: int) -> None:
        if self.active_sample is None:
            return
        label = self.roi_target_combo.currentText()
        try:
            result = roi_average_spectrum(self.active_sample, x0, y0, x1 - x0, y1 - y0)
        except Exception as exc:
            self._show_error("Could not inspect ROI", str(exc))
            return
        values = np.asarray(result["mean_values"], dtype=float)
        wavelengths = np.asarray(result["wavelengths"], dtype=float)
        record = SpectrumRecord(
            label,
            values,
            wavelengths,
            {"bbox": result["bbox"], "pixel_count": result["pixel_count"]},
        )
        self.roi_records[label] = record
        self._refresh_spectrum_plot()
        self._fill_target_values(record)
        self.roi_summary.setText(
            f"{label}: bbox={result['bbox']} pixels={result['pixel_count']} {self._target_value_summary(values)}"
        )

    def _refresh_spectrum_plot(self) -> None:
        records: list[SpectrumRecord] = []
        records.extend(self.pixel_records)
        records.extend(self.roi_records.values())
        if self.whole_leaf_record is not None:
            records.append(self.whole_leaf_record)
        self.spectrum_plot.plot_spectra(records, title="Pixel / ROI / whole-leaf spectra", y_label=VIEW_LABELS.get(self._view_mode(), "value"))

    def _fill_target_values(self, record: SpectrumRecord) -> None:
        self.target_values_table.setRowCount(0)
        for wavelength in TARGET_WAVELENGTHS:
            mapping = self._mapping_for_wavelength(wavelength)
            if mapping is None or not mapping.source_indices:
                self._append_value_row("target", f"{wavelength:g} nm", "missing", None)
                continue
            source = int(mapping.source_indices[0])
            value = record.values[source] if source < record.values.size else np.nan
            self._append_value_row("target", f"{wavelength:g} nm", f"band {source}", value)
        for role, resolved in self.roles.items():
            if resolved.band_key is None:
                self._append_value_row("role", role, "missing", None)
                continue
            mapping = self.active_sample.band_mappings.get(resolved.band_key) if self.active_sample else None
            source = None if mapping is None or not mapping.source_indices else int(mapping.source_indices[0])
            value = None if source is None or source >= record.values.size else record.values[source]
            self._append_value_row("role", role, f"{resolved.wavelength_nm:g} nm / band {source}", value)

    def _append_value_row(self, kind: str, name: str, band_text: str, value: float | None) -> None:
        row = self.target_values_table.rowCount()
        self.target_values_table.insertRow(row)
        for column, text in enumerate([kind, name, band_text, self._fmt(value)]):
            self.target_values_table.setItem(row, column, QtWidgets.QTableWidgetItem(str(text)))

    def _target_value_summary(self, values: np.ndarray) -> str:
        parts = []
        for wavelength in (680.0, 725.0, 850.0, 940.0):
            mapping = self._mapping_for_wavelength(wavelength)
            if mapping is None or not mapping.source_indices:
                continue
            index = int(mapping.source_indices[0])
            if index < values.size:
                parts.append(f"{wavelength:g}={self._fmt(values[index])}")
        return " ".join(parts)

    def _run_analysis(self) -> None:
        if self.adapter_sample is None:
            return
        analysis_mode = "reflectance" if self.adapter_sample.reflectance_cube is not None else "raw"
        current_mode = self._view_mode()
        index = self.view_combo.findData(analysis_mode)
        if index >= 0:
            self.view_combo.setCurrentIndex(index)
        self._prepare_active_sample()
        if self.active_sample is None:
            return
        try:
            apply_vegetation_mask(self.active_sample, ndvi_threshold=float(self.ndvi_threshold.value()))
            avg_bands, spectrum_metadata = compute_average_spectrum(self.active_sample)
            self.indices_report = build_indices_report(self.active_sample, avg_bands, spectrum_metadata)
            self.spot_result = detect_suspicious_spots(
                self.active_sample,
                self.roles,
                SpotDetectionConfig(
                    score_threshold=float(self.spot_threshold.value()),
                    min_area_px=int(self.spot_min_area.value()),
                    texture_window=int(self.spot_texture_window.value()),
                ),
            )
            self.analysis_sample = self.active_sample
        except Exception as exc:
            self._show_error("Analysis failed", str(exc))
            return
        self.whole_leaf_record = self._whole_leaf_spectrum_record()
        self._refresh_spectrum_plot()
        self._refresh_indices_text()
        self._refresh_spot_table()
        self._update_image()
        self.analysis_text.setPlainText(json.dumps(spot_result_to_report(self.spot_result), indent=2, default=str))
        self.statusBar().showMessage(f"Analysis ran on {VIEW_LABELS.get(analysis_mode)}.", 6000)
        if current_mode != analysis_mode:
            self.left_tabs.setCurrentWidget(self.left_tabs.widget(2))

    def _whole_leaf_spectrum_record(self) -> SpectrumRecord | None:
        sample = self.analysis_sample
        if sample is None or sample.mask is None or sample.data is None:
            return None
        mask = np.asarray(sample.mask, dtype=bool)
        if not mask.any():
            return None
        values = np.nanmean(sample.data[mask, :].astype(float), axis=0)
        return SpectrumRecord("Whole leaf", values, np.asarray(sample.available_wavelengths, dtype=float), {"mask": "vegetation"})

    def _refresh_indices_text(self) -> None:
        if not self.indices_report:
            self.indices_text.setPlainText("Run analysis to compute whole-leaf and selected-target indices.")
            return
        selected = {
            key: self.indices_report.get("indices", {}).get(key)
            for key in ("NDVI", "NDRE", "GNDVI", "CI_RE", "NDWI_850_940", "NIR_RED_DIFF", "NIR_RED_SUM")
        }
        payload = {
            "current_view": VIEW_LABELS.get(self._view_mode()),
            "whole_leaf_average_target_bands": self.indices_report.get("average_bands"),
            "selected_indices": selected,
            "full_report": self.indices_report,
        }
        self.indices_text.setPlainText(json.dumps(payload, indent=2, default=str))

    def _refresh_spot_table(self) -> None:
        self.spots_table.setRowCount(0)
        if self.spot_result is None:
            return
        for spot in self.spot_result.get("spots", []):
            row = self.spots_table.rowCount()
            self.spots_table.insertRow(row)
            indices = spot.get("mean_indices", {})
            values = [
                spot.get("label"),
                spot.get("area_px"),
                spot.get("centroid"),
                spot.get("bbox"),
                self._fmt(indices.get("NDVI")),
                self._fmt(indices.get("NDRE")),
            ]
            for column, value in enumerate(values):
                self.spots_table.setItem(row, column, QtWidgets.QTableWidgetItem(str(value)))

    def _spot_table_clicked(self, row: int, _column: int) -> None:
        item = self.spots_table.item(row, 0)
        if item is None:
            return
        try:
            self._inspect_spot_label(int(item.text()))
        except ValueError:
            return

    def _inspect_spot_label(self, label: int) -> None:
        if self.spot_result is None or self.active_sample is None:
            return
        spots = [spot for spot in self.spot_result.get("spots", []) if int(spot.get("label", -1)) == int(label)]
        if not spots:
            return
        spot = spots[0]
        labels = self.spot_result.get("labels")
        if labels is not None and self.active_sample.data is not None:
            mask = np.asarray(labels) == int(label)
            if mask.any():
                values = np.nanmean(self.active_sample.data[mask, :].astype(float), axis=0)
                self.roi_records["Suspicious region"] = SpectrumRecord(
                    f"Spot {label}", values, np.asarray(self.active_sample.available_wavelengths, dtype=float), spot
                )
                self._refresh_spectrum_plot()
        self.spot_detail_text.setPlainText(json.dumps(spot, indent=2, default=str))

    def _jump_to_wavelength(self, wavelength: float) -> None:
        mapping = self._mapping_for_wavelength(wavelength)
        if mapping is None or not mapping.source_indices:
            self.statusBar().showMessage(f"No source band is mapped for {wavelength:g} nm.", 5000)
            return
        self.image_mode_combo.setCurrentText("Grayscale band")
        self.band_slider.setValue(int(mapping.source_indices[0]))

    def _jump_to_role(self, role: str) -> None:
        resolved = self.roles.get(role)
        if resolved is None or resolved.band_key is None:
            self.statusBar().showMessage(f"Role {role} is not available for this profile/sample.", 5000)
            return
        mapping = self.active_sample.band_mappings.get(resolved.band_key) if self.active_sample else None
        if mapping is not None and mapping.source_indices:
            self.image_mode_combo.setCurrentText("Grayscale band")
            self.band_slider.setValue(int(mapping.source_indices[0]))

    def _wavelength_for_index(self, index: int) -> float | None:
        if self.adapter_sample is None:
            return None
        wavelengths = np.asarray(self.adapter_sample.wavelengths, dtype=float)
        if index < 0 or index >= wavelengths.size:
            return None
        value = float(wavelengths[index])
        return value if np.isfinite(value) else None

    def _export_current_image(self) -> None:
        if self.current_display_image is None:
            self._show_error("No image to export", "Display a band or composite first.")
            return
        path = self._save_path("Save displayed image", "PNG image (*.png)", ".png")
        if path is None:
            return
        try:
            from matplotlib import image as mpimg

            mpimg.imsave(path, self.current_display_image)
        except Exception as exc:
            self._show_error("Export failed", str(exc))
            return
        self._append_export(f"Saved image: {path}")

    def _export_spectrum_plot(self) -> None:
        if not self.spectrum_plot.has_data:
            self._show_error("No plot to export", "Click a pixel, select ROI, or run analysis first.")
            return
        path = self._save_path("Save spectrum plot", "PNG image (*.png)", ".png")
        if path is None:
            return
        self.spectrum_plot.save_png(path)
        self._append_export(f"Saved spectrum plot: {path}")

    def _export_pixel_spectra(self) -> None:
        if not self.pixel_records:
            self._show_error("No clicked spectrum", "Click a pixel first.")
            return
        self._export_spectrum_records(self.pixel_records, "clicked_spectrum")

    def _export_roi_spectra(self) -> None:
        if not self.roi_records:
            self._show_error("No ROI spectra", "Select ROI A or ROI B first.")
            return
        self._export_spectrum_records(list(self.roi_records.values()), "roi_spectra")

    def _export_spectrum_records(self, records: list[SpectrumRecord], stem: str) -> None:
        path = self._save_path(f"Save {stem}", "JSON file (*.json);;CSV file (*.csv)", ".json")
        if path is None:
            return
        if path.suffix.lower() == ".csv":
            with path.open("w", newline="", encoding="utf-8") as handle:
                writer = csv.writer(handle)
                writer.writerow(["record", "band_index", "wavelength_nm", "value"])
                for record in records:
                    for index, value in enumerate(record.values):
                        wavelength = record.wavelengths[index] if index < record.wavelengths.size else ""
                        writer.writerow([record.name, index, wavelength, value])
        else:
            payload = [
                {
                    "name": record.name,
                    "wavelengths_nm": record.wavelengths.tolist(),
                    "values": record.values.tolist(),
                    "metadata": record.metadata,
                }
                for record in records
            ]
            path.write_text(json.dumps(payload, indent=2, default=str), encoding="utf-8")
        self._append_export(f"Saved spectra: {path}")

    def _export_report(self) -> None:
        path = self._save_path("Save sample analysis report", "JSON file (*.json)", ".json")
        if path is None:
            return
        payload = {
            "sample_metadata": self.adapter_sample.metadata if self.adapter_sample is not None else {},
            "active_view": VIEW_LABELS.get(self._view_mode()),
            "profile": self.profile.name,
            "target_mappings": {
                key: mapping.to_dict()
                for key, mapping in (self.active_sample.band_mappings.items() if self.active_sample else [])
            },
            "roles": {role: asdict(value) for role, value in self.roles.items()},
            "indices_report": self.indices_report,
            "spot_report": spot_result_to_report(self.spot_result) if self.spot_result is not None else {},
            "quality_summary": self.quality_text.toPlainText(),
        }
        path.write_text(json.dumps(payload, indent=2, default=str), encoding="utf-8")
        self._append_export(f"Saved report: {path}")

    def _export_spots_csv(self) -> None:
        if self.spot_result is None:
            self._show_error("No suspicious regions", "Run analysis first.")
            return
        path = self._save_path("Save suspicious-region table", "CSV file (*.csv)", ".csv")
        if path is None:
            return
        with path.open("w", newline="", encoding="utf-8") as handle:
            writer = csv.writer(handle)
            writer.writerow(["label", "area_px", "centroid_x", "centroid_y", "bbox", "ndvi", "ndre", "gndvi"])
            for spot in self.spot_result.get("spots", []):
                centroid = spot.get("centroid", ["", ""])
                indices = spot.get("mean_indices", {})
                writer.writerow(
                    [
                        spot.get("label"),
                        spot.get("area_px"),
                        centroid[0] if len(centroid) else "",
                        centroid[1] if len(centroid) > 1 else "",
                        spot.get("bbox"),
                        indices.get("NDVI"),
                        indices.get("NDRE"),
                        indices.get("GNDVI"),
                    ]
                )
        self._append_export(f"Saved suspicious-region CSV: {path}")

    def _save_path(self, title: str, filter_text: str, default_suffix: str) -> Path | None:
        start = self.output_path.text().strip() or str(Path("plant_health_mvp_new_data") / "runs" / "gui_export")
        Path(start).mkdir(parents=True, exist_ok=True)
        path, _ = QtWidgets.QFileDialog.getSaveFileName(self, title, start, filter_text)
        if not path:
            return None
        result = Path(path)
        if not result.suffix:
            result = result.with_suffix(default_suffix)
        return result

    def _append_export(self, line: str) -> None:
        self.export_text.appendPlainText(line)
        self.statusBar().showMessage(line, 5000)

    @staticmethod
    def _fmt(value: Any) -> str:
        if value is None:
            return ""
        try:
            numeric = float(value)
        except (TypeError, ValueError):
            return str(value)
        if not np.isfinite(numeric):
            return ""
        return f"{numeric:.6g}"

    def _show_error(self, title: str, message: str) -> None:
        QtWidgets.QMessageBox.critical(self, title, message)


def launch_gui(argv: list[str] | None = None) -> int:
    """Launch the GUI application."""

    parser = argparse.ArgumentParser()
    parser.add_argument("--input", default="")
    parser.add_argument("--wavelengths", default="")
    parser.add_argument("--output", default=str(Path("plant_health_mvp_new_data") / "runs" / "gui_export"))
    args = parser.parse_args(argv)

    app = QtWidgets.QApplication([])
    app.setStyle("Fusion")
    app.setStyleSheet(APP_STYLESHEET)
    window = MainWindow(
        initial_input=args.input,
        initial_wavelengths=args.wavelengths,
        initial_output=args.output,
    )
    window.show()
    return app.exec()
