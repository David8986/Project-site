"""Dedicated analysis app for vegetation and suspicious-region processing."""

from __future__ import annotations

import argparse
import csv
import json
from argparse import Namespace
from pathlib import Path
from typing import Any

import numpy as np
from PySide6 import QtCore, QtGui, QtWidgets

from .glossary import GlossaryWidget
from .graphs import HistogramStatsWidget, IndicesGraphWidget, SpectraGraphWidget
from .import_wizard import MixedImportDialog
from .readable import (
    build_camera_calibration_text,
    build_detailed_report_text,
    build_interpretation_text,
    build_summary_text,
    build_validation_profile_text,
)
from ..core.alignment_preview import load_alignment_preview_artifacts
from ..core.visual_overlays import (
    RegionDisplay,
    build_composite,
    parse_region_rows,
    read_uint8_image,
    render_overlay,
    save_uint8_image,
)
from ..gui.alignment_preview_widget import AlignmentPreviewWidget
from ..gui.simple_style import SIMPLE_DARK_STYLESHEET, set_simple_margins
from ..main import run_pipeline
from .localization import combo_entries, tr, translate_report_text


DARK_STYLESHEET = SIMPLE_DARK_STYLESHEET


class OverlayImageLabel(QtWidgets.QLabel):
    """Large image label for affected-area candidate overlays."""

    def __init__(self) -> None:
        super().__init__("Ruleaza analiza pentru a afisa masca/spoturile.")
        self.setAlignment(QtCore.Qt.AlignmentFlag.AlignCenter)
        self.setMinimumSize(680, 460)
        self.setStyleSheet("QLabel { background: #111111; border: 1px solid #777777; }")

    def set_array(self, image: np.ndarray) -> None:
        """Display a uint8 RGB image."""

        array = np.ascontiguousarray(np.asarray(image, dtype=np.uint8))
        if array.ndim == 2:
            height, width = array.shape
            qimage = QtGui.QImage(array.data, width, height, width, QtGui.QImage.Format.Format_Grayscale8).copy()
        elif array.ndim == 3 and array.shape[2] == 3:
            height, width, _ = array.shape
            qimage = QtGui.QImage(array.data, width, height, width * 3, QtGui.QImage.Format.Format_RGB888).copy()
        else:
            raise ValueError(f"Unsupported overlay image shape: {array.shape}")
        pixmap = QtGui.QPixmap.fromImage(qimage)
        self.setPixmap(
            pixmap.scaled(
                self.size(),
                QtCore.Qt.AspectRatioMode.KeepAspectRatio,
                QtCore.Qt.TransformationMode.SmoothTransformation,
            )
        )


class AnalysisWindow(QtWidgets.QMainWindow):
    """Focused analysis window with no manual band-exploration workflow."""

    def __init__(
        self,
        initial_input: str = "",
        initial_wavelengths: str = "",
        initial_output: str = "",
        initial_language: str = "ro",
    ) -> None:
        super().__init__()
        self.language = "en" if initial_language == "en" else "ro"
        self.setWindowTitle(tr("window_title", self.language))
        self.resize(1350, 860)
        self.artifacts: dict[str, Any] = {}
        self.report: dict[str, Any] = {}
        self.spot_rows: list[dict[str, str]] = []
        self.regions: list[RegionDisplay] = []
        self.current_background_image: np.ndarray | None = None
        self.current_overlay_image: np.ndarray | None = None
        self.selected_region_label: int | None = None
        self.form_labels: dict[str, QtWidgets.QLabel] = {}
        self._build_ui()
        self.language_combo.setCurrentIndex(1 if self.language == "en" else 0)
        self.input_path.setText(initial_input)
        self.wavelength_path.setText(initial_wavelengths)
        self.output_path.setText(initial_output or str(Path("plant_health_mvp_new_data") / "runs" / "analysis_export"))

    def _form_label(self, key: str) -> QtWidgets.QLabel:
        """Create and remember a form label for language switching."""

        label = QtWidgets.QLabel(tr(key, self.language))
        self.form_labels[key] = label
        return label

    def _build_ui(self) -> None:
        root = QtWidgets.QWidget()
        self.setCentralWidget(root)
        layout = QtWidgets.QHBoxLayout(root)
        set_simple_margins(layout)

        controls = QtWidgets.QWidget()
        controls.setMaximumWidth(360)
        form = QtWidgets.QFormLayout(controls)
        set_simple_margins(form)
        self.input_path = QtWidgets.QLineEdit()
        self.wavelength_path = QtWidgets.QLineEdit()
        self.output_path = QtWidgets.QLineEdit()
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
        self.spot_texture = QtWidgets.QSpinBox()
        self.spot_texture.setRange(1, 51)
        self.spot_texture.setValue(5)

        self.language_combo = QtWidgets.QComboBox()
        self.language_combo.addItem(tr("romanian", self.language), "ro")
        self.language_combo.addItem(tr("english", self.language), "en")
        self.language_combo.currentIndexChanged.connect(self._language_changed)
        self.choose_button = QtWidgets.QPushButton(tr("load_sample_folder", self.language))
        self.choose_button.clicked.connect(self._choose_folder)
        self.choose_file_button = QtWidgets.QPushButton(tr("load_image_file", self.language))
        self.choose_file_button.clicked.connect(self._choose_file)
        self.mixed_import_button = QtWidgets.QPushButton(tr("configure_mixed_images", self.language))
        self.mixed_import_button.clicked.connect(self._open_mixed_import_wizard)
        self.choose_wavelengths_button = QtWidgets.QPushButton(tr("load_wavelength_csv", self.language))
        self.choose_wavelengths_button.clicked.connect(self._choose_wavelengths)
        self.choose_output_button = QtWidgets.QPushButton(tr("set_output_folder", self.language))
        self.choose_output_button.clicked.connect(self._choose_output)
        self.run_button = QtWidgets.QPushButton(tr("run_analysis", self.language))
        self.run_button.clicked.connect(self._run_analysis)
        self.reload_outputs_button = QtWidgets.QPushButton(tr("reload_outputs", self.language))
        self.reload_outputs_button.clicked.connect(self._load_outputs)

        form.addRow(self._form_label("language"), self.language_combo)
        form.addRow(self._form_label("sample"), self.input_path)
        form.addRow("", self.choose_button)
        form.addRow("", self.choose_file_button)
        form.addRow("", self.mixed_import_button)
        form.addRow(self._form_label("wavelengths"), self.wavelength_path)
        form.addRow("", self.choose_wavelengths_button)
        form.addRow(self._form_label("output"), self.output_path)
        form.addRow("", self.choose_output_button)
        form.addRow(self._form_label("ndvi_threshold"), self.ndvi_threshold)
        form.addRow(self._form_label("spot_threshold"), self.spot_threshold)
        form.addRow(self._form_label("min_spot_area"), self.spot_min_area)
        form.addRow(self._form_label("texture_window"), self.spot_texture)
        form.addRow("", self.run_button)
        form.addRow("", self.reload_outputs_button)

        right = QtWidgets.QTabWidget()
        self.right_tabs = right
        self.summary = QtWidgets.QPlainTextEdit()
        self.summary.setReadOnly(True)
        self.interpretation_text = QtWidgets.QPlainTextEdit()
        self.interpretation_text.setReadOnly(True)
        self.validation_profile_text = QtWidgets.QPlainTextEdit()
        self.validation_profile_text.setReadOnly(True)
        self.readable_report = QtWidgets.QPlainTextEdit()
        self.readable_report.setReadOnly(True)
        self.spectra_graph = SpectraGraphWidget()
        self.histogram_stats = HistogramStatsWidget()
        self.indices_graph = IndicesGraphWidget()
        self.alignment_preview = AlignmentPreviewWidget(show_mask_controls=True)
        self.glossary = GlossaryWidget()
        self.spots = QtWidgets.QTableWidget(0, 12)
        self._set_spot_headers()
        self.spots.horizontalHeader().setStretchLastSection(True)
        self.spots.setSelectionBehavior(QtWidgets.QAbstractItemView.SelectionBehavior.SelectRows)
        self.spots.itemSelectionChanged.connect(self._spot_selection_changed)
        self.report_text = QtWidgets.QPlainTextEdit()
        self.report_text.setReadOnly(True)
        self.tab_keys = [
            "summary",
            "interpretation",
            "camera_validation",
            "alignment",
            "spectra",
            "histogram",
            "indices",
            "spot_table",
            "mask_spots",
            "text_report",
            "glossary",
            "json",
        ]
        right.addTab(self.summary, tr("summary", self.language))
        right.addTab(self.interpretation_text, tr("interpretation", self.language))
        right.addTab(self.validation_profile_text, tr("camera_validation", self.language))
        right.addTab(self.alignment_preview, tr("alignment", self.language))
        right.addTab(self.spectra_graph, tr("spectra", self.language))
        right.addTab(self.histogram_stats, tr("histogram", self.language))
        right.addTab(self.indices_graph, tr("indices", self.language))
        right.addTab(self.spots, tr("spot_table", self.language))
        right.addTab(self._overlay_tab(), tr("mask_spots", self.language))
        right.addTab(self.readable_report, tr("text_report", self.language))
        right.addTab(self.glossary, tr("glossary", self.language))
        right.addTab(self.report_text, tr("json", self.language))

        layout.addWidget(controls)
        layout.addWidget(right, 1)
        self._refresh_glossary_values()
        self.ndvi_threshold.valueChanged.connect(self._refresh_glossary_values)
        self.spot_threshold.valueChanged.connect(self._refresh_glossary_values)
        self.spot_min_area.valueChanged.connect(self._refresh_glossary_values)
        self.spot_texture.valueChanged.connect(self._refresh_glossary_values)

    def _set_spot_headers(self) -> None:
        """Set localized spot-table headers."""

        self.spots.setHorizontalHeaderLabels(
            [
                tr("spot_label", self.language),
                tr("area", self.language),
                tr("severity_rank", self.language),
                tr("severity_score", self.language),
                tr("centroid_x", self.language),
                tr("centroid_y", self.language),
                tr("bbox", self.language),
                "NDVI",
                "NDRE",
                "GNDVI",
                tr("delta_680_leaf", self.language),
                tr("delta_850_leaf", self.language),
            ]
        )

    def _set_combo_entries(self, combo: QtWidgets.QComboBox, entries: list[tuple[str, str]]) -> None:
        """Replace combo labels while preserving the current data value."""

        current = combo.currentData()
        blocked = combo.blockSignals(True)
        combo.clear()
        for label, value in entries:
            combo.addItem(label, value)
        if current is not None:
            index = combo.findData(current)
            if index >= 0:
                combo.setCurrentIndex(index)
        combo.blockSignals(blocked)

    def _set_background_combo_items(self) -> None:
        """Populate the background selector in the current language."""

        self._set_combo_entries(
            self.background_combo,
            combo_entries(
                [
                    ("background_680", "gray_680"),
                    ("background_725", "gray_725"),
                    ("background_850", "gray_850"),
                    ("background_rgb", "rgb"),
                    ("background_false_color", "false_color"),
                ],
                self.language,
            ),
        )

    def _set_overlay_combo_items(self) -> None:
        """Populate the overlay mode selector in the current language."""

        self._set_combo_entries(
            self.overlay_mode_combo,
            combo_entries(
                [
                    ("mode_outline", "outline"),
                    ("mode_filled", "filled"),
                    ("mode_heatmap", "heatmap"),
                    ("mode_vegetation", "vegetation"),
                    ("mode_background", "background"),
                ],
                self.language,
            ),
        )

    def _language_changed(self) -> None:
        """Switch the displayed UI/report language."""

        self.language = str(self.language_combo.currentData() or "ro")
        self._apply_language()

    def _apply_language(self) -> None:
        """Refresh static labels and visible report text for the selected language."""

        self.setWindowTitle(tr("window_title", self.language))
        for key, label in self.form_labels.items():
            label.setText(tr(key, self.language))
        self.choose_button.setText(tr("load_sample_folder", self.language))
        self.choose_file_button.setText(tr("load_image_file", self.language))
        self.mixed_import_button.setText(tr("configure_mixed_images", self.language))
        self.choose_wavelengths_button.setText(tr("load_wavelength_csv", self.language))
        self.choose_output_button.setText(tr("set_output_folder", self.language))
        self.run_button.setText(tr("run_analysis", self.language))
        self.reload_outputs_button.setText(tr("reload_outputs", self.language))
        self.language_combo.setItemText(0, tr("romanian", self.language))
        self.language_combo.setItemText(1, tr("english", self.language))
        for index, key in enumerate(self.tab_keys):
            self.right_tabs.setTabText(index, tr(key, self.language))
        self._set_spot_headers()
        self._set_background_combo_items()
        self._set_overlay_combo_items()

        if hasattr(self, "background_label"):
            self.background_label.setText(tr("background", self.language))
            self.mode_label.setText(tr("mode", self.language))
            self.opacity_text_label.setText(tr("opacity", self.language))
            self.show_outlines_checkbox.setText(tr("show_outlines", self.language))
            self.show_labels_checkbox.setText(tr("show_labels", self.language))
            self.show_boxes_checkbox.setText(tr("show_boxes", self.language))
            self.show_suspicious_checkbox.setText(tr("show_suspicious_mask", self.language))
            self.show_filled_checkbox.setText(tr("show_red_fill", self.language))
            self.show_vegetation_checkbox.setText(tr("show_leaf_mask", self.language))
            self.refresh_overlay_button.setText(tr("refresh", self.language))
            self.export_current_button.setText(tr("export_current", self.language))
            self.export_all_button.setText(tr("export_all", self.language))

        self._refresh_glossary_values()
        self._refresh_readable_views()
        if self.current_background_image is not None:
            self._refresh_histogram_tab()
        if self.report:
            self._refresh_overlay()

    def _overlay_tab(self) -> QtWidgets.QWidget:
        """Build the suspicious overlay visualization panel."""

        panel = QtWidgets.QWidget()
        layout = QtWidgets.QVBoxLayout(panel)
        set_simple_margins(layout)

        controls = QtWidgets.QGridLayout()
        set_simple_margins(controls)
        self.background_combo = QtWidgets.QComboBox()
        self._set_background_combo_items()
        self.overlay_mode_combo = QtWidgets.QComboBox()
        self._set_overlay_combo_items()
        self.opacity_slider = QtWidgets.QSlider(QtCore.Qt.Orientation.Horizontal)
        self.opacity_slider.setRange(0, 100)
        self.opacity_slider.setValue(45)
        self.opacity_label = QtWidgets.QLabel("45%")
        self.show_outlines_checkbox = QtWidgets.QCheckBox(tr("show_outlines", self.language))
        self.show_outlines_checkbox.setChecked(True)
        self.show_labels_checkbox = QtWidgets.QCheckBox(tr("show_labels", self.language))
        self.show_labels_checkbox.setChecked(False)
        self.show_boxes_checkbox = QtWidgets.QCheckBox(tr("show_boxes", self.language))
        self.show_boxes_checkbox.setChecked(False)
        self.show_suspicious_checkbox = QtWidgets.QCheckBox(tr("show_suspicious_mask", self.language))
        self.show_suspicious_checkbox.setChecked(True)
        self.show_filled_checkbox = QtWidgets.QCheckBox(tr("show_red_fill", self.language))
        self.show_filled_checkbox.setChecked(False)
        self.show_vegetation_checkbox = QtWidgets.QCheckBox(tr("show_leaf_mask", self.language))
        self.show_vegetation_checkbox.setChecked(False)
        self.refresh_overlay_button = QtWidgets.QPushButton(tr("refresh", self.language))
        self.refresh_overlay_button.clicked.connect(self._refresh_overlay)
        self.export_current_button = QtWidgets.QPushButton(tr("export_current", self.language))
        self.export_current_button.clicked.connect(self._export_current_overlay)
        self.export_all_button = QtWidgets.QPushButton(tr("export_all", self.language))
        self.export_all_button.clicked.connect(self._export_all_overlay_modes)

        self.background_label = QtWidgets.QLabel(tr("background", self.language))
        self.mode_label = QtWidgets.QLabel(tr("mode", self.language))
        self.opacity_text_label = QtWidgets.QLabel(tr("opacity", self.language))

        controls.addWidget(self.background_label, 0, 0)
        controls.addWidget(self.background_combo, 0, 1)
        controls.addWidget(self.mode_label, 0, 2)
        controls.addWidget(self.overlay_mode_combo, 0, 3)
        controls.addWidget(self.opacity_text_label, 1, 0)
        controls.addWidget(self.opacity_slider, 1, 1)
        controls.addWidget(self.opacity_label, 1, 2)
        controls.addWidget(self.show_outlines_checkbox, 1, 3)
        controls.addWidget(self.show_labels_checkbox, 1, 4)
        controls.addWidget(self.show_boxes_checkbox, 2, 0)
        controls.addWidget(self.show_suspicious_checkbox, 2, 1)
        controls.addWidget(self.show_filled_checkbox, 2, 2)
        controls.addWidget(self.show_vegetation_checkbox, 2, 3)
        controls.addWidget(self.refresh_overlay_button, 3, 0)
        controls.addWidget(self.export_current_button, 3, 1, 1, 2)
        controls.addWidget(self.export_all_button, 3, 3, 1, 2)
        layout.addLayout(controls)

        self.overlay_image = OverlayImageLabel()
        self.overlay_image.setText(tr("overlay_wait", self.language))
        layout.addWidget(self.overlay_image, 1)
        self.overlay_status = QtWidgets.QPlainTextEdit()
        self.overlay_status.setReadOnly(True)
        self.overlay_status.setMaximumHeight(100)
        layout.addWidget(self.overlay_status)

        self.background_combo.currentTextChanged.connect(self._refresh_overlay)
        self.overlay_mode_combo.currentTextChanged.connect(self._refresh_overlay)
        self.opacity_slider.valueChanged.connect(self._overlay_opacity_changed)
        self.show_outlines_checkbox.stateChanged.connect(self._refresh_overlay)
        self.show_labels_checkbox.stateChanged.connect(self._refresh_overlay)
        self.show_boxes_checkbox.stateChanged.connect(self._refresh_overlay)
        self.show_suspicious_checkbox.stateChanged.connect(self._refresh_overlay)
        self.show_filled_checkbox.stateChanged.connect(self._refresh_overlay)
        self.show_vegetation_checkbox.stateChanged.connect(self._refresh_overlay)
        return panel

    def _choose_folder(self) -> None:
        path = QtWidgets.QFileDialog.getExistingDirectory(self, tr("dialog_sample_folder", self.language))
        if path:
            self.input_path.setText(path)

    def _choose_file(self) -> None:
        path, _ = QtWidgets.QFileDialog.getOpenFileName(
            self,
            tr("dialog_image_file", self.language),
            "",
            (
                f"{tr('supported_files', self.language)} (*.json *.jpg *.jpeg *.png *.tif *.tiff *.bmp *.npz *.npy *.csv *.txt *.tar *.gz);;"
                f"{tr('mixed_specs', self.language)} (*.json);;"
                f"{tr('images', self.language)} (*.jpg *.jpeg *.png *.tif *.tiff *.bmp);;"
                f"{tr('all_files', self.language)} (*)"
            ),
        )
        if path:
            self.input_path.setText(path)

    def _open_mixed_import_wizard(self) -> None:
        """Open the mixed RGB/grayscale import wizard and use the saved spec."""

        current_input = self.input_path.text().strip()
        current_path = Path(current_input) if current_input else None
        if current_path is not None and current_path.suffix:
            initial_dir = current_path.parent
        elif current_path is not None:
            initial_dir = current_path
        else:
            initial_dir = Path.cwd()
        output = self._output_dir()
        default_spec = output / "mixed_import_spec.json"
        dialog = MixedImportDialog(self, initial_directory=initial_dir, output_path=default_spec)
        existing_spec = current_path if current_path is not None and current_path.suffix.lower() == ".json" and current_path.exists() else None
        if existing_spec is not None:
            try:
                dialog.load_spec_path(existing_spec)
            except Exception as exc:
                QtWidgets.QMessageBox.warning(
                    self,
                    tr("mixed_import", self.language),
                    tr("mixed_import_load_failed", self.language) + "\n\n"
                    f"{exc}",
                )
        if dialog.exec() != QtWidgets.QDialog.DialogCode.Accepted:
            return
        spec_path = dialog.result_spec_path()
        if spec_path is None:
            return
        self.input_path.setText(str(spec_path))
        QtWidgets.QMessageBox.information(
            self,
            tr("mixed_input_ready", self.language),
            tr("mixed_input_saved", self.language) + "\n"
            f"{spec_path}",
        )

    def _choose_wavelengths(self) -> None:
        path, _ = QtWidgets.QFileDialog.getOpenFileName(
            self,
            tr("dialog_wavelength_csv", self.language),
            "",
            f"{tr('csv_files', self.language)} (*.csv);;{tr('all_files', self.language)} (*)",
        )
        if path:
            self.wavelength_path.setText(path)

    def _choose_output(self) -> None:
        path = QtWidgets.QFileDialog.getExistingDirectory(self, tr("dialog_output_folder", self.language))
        if path:
            self.output_path.setText(path)

    def _run_analysis(self) -> None:
        output = Path(self.output_path.text().strip() or "plant_health_mvp_new_data/runs/analysis_export")
        args = Namespace(
            input=Path(self.input_path.text().strip()) if self.input_path.text().strip() else None,
            archive_sample=None,
            wavelengths=Path(self.wavelength_path.text().strip()) if self.wavelength_path.text().strip() else None,
            output=output,
            save_mock_dataset=False,
            exact_tolerance=1.0,
            nearest_tolerance=15.0,
            interpolation_max_gap=80.0,
            prefer_interpolation=False,
            band_profile="profile_7band_default",
            ndvi_threshold=float(self.ndvi_threshold.value()),
            fallback_percentile=70.0,
            no_mask_cleanup=False,
            spot_threshold=float(self.spot_threshold.value()),
            spot_min_area=int(self.spot_min_area.value()),
            spot_texture_window=int(self.spot_texture.value()),
        )
        try:
            self.artifacts = run_pipeline(args)
        except Exception as exc:
            QtWidgets.QMessageBox.critical(self, tr("analysis_failed", self.language), str(exc))
            return
        self._load_outputs()

    def _load_outputs(self) -> None:
        output = Path(self.output_path.text().strip() or "plant_health_mvp_new_data/runs/analysis_export")
        report_path = output / "mapping_report.json"
        if not report_path.exists():
            self.report = {}
            self.spots.setRowCount(0)
            self.spot_rows = []
            self.regions = []
            self.selected_region_label = None
            self.current_background_image = None
            self.current_overlay_image = None
            self.summary.setPlainText(f"{tr('no_report', self.language)}\n{report_path}")
            self.interpretation_text.setPlainText("")
            self.validation_profile_text.setPlainText("")
            self.readable_report.setPlainText("")
            self.report_text.setPlainText("")
            self.spectra_graph.clear()
            self.histogram_stats.clear()
            self.indices_graph.clear()
            self.glossary.set_report({})
            self.alignment_preview.clear(f"{tr('no_report', self.language)}\n{report_path}")
            self.overlay_image.clear()
            self.overlay_image.setText(tr("overlay_reload_hint", self.language))
            self.overlay_status.setPlainText(f"{tr('no_report', self.language)}\n{report_path}")
            return
        self.report = json.loads(report_path.read_text(encoding="utf-8"))
        self.current_background_image = None
        self.current_overlay_image = None
        self.report_text.setPlainText(json.dumps(self.report, indent=2, default=str))
        self.glossary.set_report(self.report)
        self._refresh_glossary_values()
        self.selected_region_label = None
        self._load_spots_csv(output / "spots.csv")
        self._refresh_readable_views()
        self._refresh_graphs()
        self._select_available_background(output)
        self._refresh_alignment_preview()
        self._refresh_overlay()

    def _load_spots_csv(self, path: Path) -> None:
        self.spots.setRowCount(0)
        self.spot_rows = []
        self.regions = []
        if not path.exists():
            return
        with path.open("r", newline="", encoding="utf-8") as handle:
            reader = csv.DictReader(handle)
            for row_data in reader:
                self.spot_rows.append(dict(row_data))
                row = self.spots.rowCount()
                self.spots.insertRow(row)
                values = [
                    row_data.get("label", ""),
                    row_data.get("area_px", ""),
                    row_data.get("severity_rank", ""),
                    row_data.get("severity_score", ""),
                    row_data.get("centroid_x", ""),
                    row_data.get("centroid_y", ""),
                    ",".join(
                        [
                            row_data.get("bbox_x_min", ""),
                            row_data.get("bbox_y_min", ""),
                            row_data.get("bbox_x_max", ""),
                            row_data.get("bbox_y_max", ""),
                        ]
                    ),
                    row_data.get("ndvi", ""),
                    row_data.get("ndre", ""),
                    row_data.get("gndvi", ""),
                    row_data.get("delta_leaf_band_680", ""),
                    row_data.get("delta_leaf_band_850", ""),
                ]
                for column, value in enumerate(values):
                    self.spots.setItem(row, column, QtWidgets.QTableWidgetItem(str(value)))
        self.regions = parse_region_rows(self.spot_rows)

    def _refresh_glossary_values(self, *_args: Any) -> None:
        """Update the glossary tab with current control values."""

        if not hasattr(self, "glossary"):
            return
        self.glossary.set_live_values(
            ndvi_threshold=float(self.ndvi_threshold.value()),
            spot_threshold=float(self.spot_threshold.value()),
            spot_min_area=int(self.spot_min_area.value()),
            texture_window=int(self.spot_texture.value()),
        )

    def _spot_selection_changed(self) -> None:
        """Highlight the selected suspicious region in the overlay."""

        selected = self.spots.selectedItems()
        if not selected:
            self.selected_region_label = None
            self._refresh_readable_views()
            self._refresh_graphs()
            self._refresh_alignment_preview()
            self._refresh_overlay()
            return
        row = selected[0].row()
        label_item = self.spots.item(row, 0)
        try:
            self.selected_region_label = None if label_item is None else int(float(label_item.text()))
        except ValueError:
            self.selected_region_label = None
        self._refresh_readable_views()
        self._refresh_graphs()
        self._refresh_alignment_preview()
        self._refresh_overlay()

    def _selected_spot(self) -> dict[str, Any] | None:
        """Return the selected suspicious-region record in report-friendly form."""

        if self.selected_region_label is None:
            return None

        label = int(self.selected_region_label)
        selected: dict[str, Any] = {}
        suspicious = self.report.get("suspicious_regions", {})
        report_spots = suspicious.get("spots", []) if isinstance(suspicious, dict) else []
        if isinstance(report_spots, list):
            for spot in report_spots:
                if not isinstance(spot, dict):
                    continue
                try:
                    if int(float(spot.get("label", -1))) == label:
                        selected.update(spot)
                        break
                except (TypeError, ValueError):
                    continue

        for row in self.spot_rows:
            try:
                if int(float(row.get("label", -1))) == label:
                    selected.update(row)
                    break
            except (TypeError, ValueError):
                continue

        reflectance = selected.get("mean_reflectance")
        if isinstance(reflectance, dict):
            for key, value in reflectance.items():
                if key.startswith("band_"):
                    selected.setdefault(key, value)
                    selected.setdefault(f"mean_{key}", value)

        mean_indices = selected.get("mean_indices")
        if isinstance(mean_indices, dict):
            for key, value in mean_indices.items():
                selected.setdefault(key, value)
                selected.setdefault(str(key).lower(), value)

        return selected or None

    def _refresh_readable_views(self) -> None:
        """Refresh human-readable summary and report tabs."""

        selected = self._selected_spot()
        if not self.report:
            self.summary.setPlainText(tr("no_analysis_report", self.language))
            self.interpretation_text.setPlainText("")
            self.validation_profile_text.setPlainText("")
            self.readable_report.setPlainText("")
            return
        self.summary.setPlainText(build_summary_text(self.report, selected_spot=selected, language=self.language))
        self.interpretation_text.setPlainText(build_interpretation_text(self.report, language=self.language))
        self.validation_profile_text.setPlainText(
            translate_report_text(
                "\n\n".join(
                    [
                        build_camera_calibration_text(self.report),
                        build_validation_profile_text(self.report),
                    ]
                ),
                self.language,
            )
        )
        self.readable_report.setPlainText(
            build_detailed_report_text(self.report, selected_spot=selected, language=self.language)
        )

    def _refresh_graphs(self) -> None:
        """Refresh graph tabs from the current report and selected region."""

        selected = self._selected_spot()
        self.spectra_graph.set_report(self.report, selected_region=selected)
        self.indices_graph.set_report(self.report, selected_region=selected)
        self._refresh_histogram_tab()

    def _refresh_alignment_preview(self) -> None:
        """Refresh the Alignment tab from shared exported preview artifacts."""

        preview = load_alignment_preview_artifacts(self._output_dir())
        if preview is None:
            alignment = self.report.get("source", {}).get("alignment") if self.report else None
            message = tr("no_alignment_preview", self.language)
            if alignment:
                message += f"\n\n{tr('alignment_metadata', self.language)}:\n" + json.dumps(alignment, indent=2, default=str)
            self.alignment_preview.clear(message)
            return

        output = self._output_dir()
        suspicious_mask = self._load_optional_image(output / "suspicious_spot_mask.png")
        if suspicious_mask is None:
            suspicious_mask = self._load_optional_image(output / "spot_labels.png")
        self.alignment_preview.set_preview(
            preview,
            vegetation_mask=self._load_optional_image(output / "vegetation_mask.png"),
            suspicious_mask=suspicious_mask,
            regions=self.regions,
            selected_label=self.selected_region_label,
        )

    def _refresh_histogram_tab(self) -> None:
        """Refresh the histogram tab from the current display background."""

        if self.current_background_image is None:
            self.histogram_stats.clear()
            return
        self.histogram_stats.set_image(self.current_background_image, label=self.background_combo.currentText())

    def _overlay_opacity_changed(self, value: int) -> None:
        """Update opacity label and render overlay."""

        self.opacity_label.setText(f"{int(value)}%")
        self._refresh_overlay()

    def _output_dir(self) -> Path:
        """Return the current analysis output directory."""

        return Path(self.output_path.text().strip() or "plant_health_mvp_new_data/runs/analysis_export")

    def _refresh_overlay(self) -> None:
        """Render the selected display-only affected-area candidate overlay."""

        output = self._output_dir()
        try:
            background = self._load_background_image(output)
            suspicious_mask = self._load_optional_image(output / "suspicious_spot_mask.png")
            if suspicious_mask is None:
                suspicious_mask = self._load_optional_image(output / "spot_labels.png")
            score_map = self._load_optional_image(output / "spot_score.png")
            vegetation_mask = self._load_optional_image(output / "vegetation_mask.png")
            mode = self._overlay_mode_key()
            overlay = render_overlay(
                background,
                mode=mode,
                suspicious_mask=suspicious_mask,
                score_map=score_map,
                vegetation_mask=vegetation_mask,
                regions=self.regions,
                opacity=float(self.opacity_slider.value()) / 100.0,
                show_outlines=self.show_outlines_checkbox.isChecked(),
                show_labels=self.show_labels_checkbox.isChecked(),
                show_boxes=self.show_boxes_checkbox.isChecked(),
                show_suspicious_mask=self.show_suspicious_checkbox.isChecked(),
                show_filled_overlay=self.show_filled_checkbox.isChecked(),
                show_vegetation_mask=self.show_vegetation_checkbox.isChecked(),
                selected_label=self.selected_region_label,
            )
        except Exception as exc:
            if hasattr(self, "overlay_status"):
                self.overlay_status.setPlainText(f"{tr('overlay_unavailable', self.language)}: {exc}")
            if hasattr(self, "histogram_stats"):
                self.histogram_stats.clear()
            return

        self.current_background_image = background
        self.current_overlay_image = overlay
        self.overlay_image.set_array(overlay)
        self._refresh_histogram_tab()
        self.overlay_status.setPlainText(
            json.dumps(
                {
                    "wording": tr("overlay_wording", self.language),
                    "background": self.background_combo.currentText(),
                    "mode": self.overlay_mode_combo.currentText(),
                    "show_outlines": self.show_outlines_checkbox.isChecked(),
                    "show_suspicious_mask": self.show_suspicious_checkbox.isChecked(),
                    "show_filled_overlay": self.show_filled_checkbox.isChecked(),
                    "show_vegetation_mask": self.show_vegetation_checkbox.isChecked(),
                    "regions": len(self.regions),
                    "selected_region": self.selected_region_label,
                    "output_folder": str(output),
                },
                indent=2,
            )
        )

    def _overlay_mode_key(self) -> str:
        """Map UI text to core overlay mode."""

        return str(self.overlay_mode_combo.currentData() or "outline")

    def _load_background_image(self, output: Path) -> np.ndarray:
        """Load the selected display background from exported band images."""

        bands = output / "bands"
        choice = str(self.background_combo.currentData() or "")
        if choice == "gray_680":
            return read_uint8_image(bands / "band_680.png")
        if choice == "gray_725":
            return read_uint8_image(bands / "band_725.png")
        if choice == "gray_850":
            return read_uint8_image(bands / "band_850.png")
        if choice == "rgb":
            return build_composite(
                read_uint8_image(bands / "band_650.png"),
                read_uint8_image(bands / "band_556.png"),
                read_uint8_image(bands / "band_532.png"),
            )
        if choice == "false_color":
            return build_composite(
                read_uint8_image(bands / "band_850.png"),
                read_uint8_image(bands / "band_725.png"),
                read_uint8_image(bands / "band_680.png"),
            )
        raise ValueError(f"{tr('unknown_background', self.language)}: {self.background_combo.currentText()}")

    def _select_available_background(self, output: Path) -> None:
        """Choose a background option that exists for the current output folder."""

        bands = output / "bands"
        needs = {
            "gray_680": ("band_680.png",),
            "gray_725": ("band_725.png",),
            "gray_850": ("band_850.png",),
            "rgb": ("band_650.png", "band_556.png", "band_532.png"),
            "false_color": ("band_850.png", "band_725.png", "band_680.png"),
        }
        current = str(self.background_combo.currentData() or "")
        if all((bands / name).exists() for name in needs.get(current, ())):
            return

        preferred = (
            "rgb",
            "gray_680",
            "gray_850",
            "gray_725",
            "false_color",
        )
        for key in preferred:
            if all((bands / name).exists() for name in needs[key]):
                blocked = self.background_combo.blockSignals(True)
                index = self.background_combo.findData(key)
                if index >= 0:
                    self.background_combo.setCurrentIndex(index)
                self.background_combo.blockSignals(blocked)
                return

    def _load_optional_image(self, path: Path) -> np.ndarray | None:
        """Load an optional display image."""

        if not path.exists():
            return None
        return read_uint8_image(path)

    def _export_current_overlay(self) -> None:
        """Export the currently displayed overlay image."""

        if self.current_overlay_image is None:
            self._refresh_overlay()
        if self.current_overlay_image is None:
            return
        output = self._output_dir() / "visualizations"
        name = self._visualization_file_stem(self.overlay_mode_combo.currentText(), self.background_combo.currentText())
        path = save_uint8_image(self.current_overlay_image, output / f"{name}.png")
        self.overlay_status.setPlainText(f"{tr('saved_current_overlay', self.language)}\n{path}")

    def _export_all_overlay_modes(self) -> None:
        """Export background, outline, filled mask, and heatmap visualization images."""

        output = self._output_dir()
        vis_dir = output / "visualizations"
        try:
            background = self._load_background_image(output)
            suspicious_mask = self._load_optional_image(output / "suspicious_spot_mask.png")
            if suspicious_mask is None:
                suspicious_mask = self._load_optional_image(output / "spot_labels.png")
            score_map = self._load_optional_image(output / "spot_score.png")
            vegetation_mask = self._load_optional_image(output / "vegetation_mask.png")
            opacity = float(self.opacity_slider.value()) / 100.0
            stem = self._visualization_file_stem("background", self.background_combo.currentText())
            saved = [save_uint8_image(background, vis_dir / f"{stem}.png")]
            for mode in ("outline", "filled", "heatmap", "vegetation"):
                image = render_overlay(
                    background,
                    mode=mode,
                    suspicious_mask=suspicious_mask,
                    score_map=score_map,
                    vegetation_mask=vegetation_mask,
                    regions=self.regions,
                    opacity=opacity,
                    show_outlines=self.show_outlines_checkbox.isChecked(),
                    show_labels=self.show_labels_checkbox.isChecked(),
                    show_boxes=self.show_boxes_checkbox.isChecked(),
                    show_suspicious_mask=self.show_suspicious_checkbox.isChecked(),
                    show_filled_overlay=self.show_filled_checkbox.isChecked(),
                    show_vegetation_mask=self.show_vegetation_checkbox.isChecked() or mode == "vegetation",
                    selected_label=self.selected_region_label,
                )
                saved.append(save_uint8_image(image, vis_dir / f"{stem}_{mode}.png"))
        except Exception as exc:
            self.overlay_status.setPlainText(f"{tr('export_failed', self.language)}: {exc}")
            return
        self.overlay_status.setPlainText(f"{tr('saved_visualizations', self.language)}\n" + "\n".join(str(path) for path in saved))

    @staticmethod
    def _visualization_file_stem(mode: str, background: str) -> str:
        """Build a safe visualization filename stem."""

        raw = f"{mode}_{background}".lower()
        allowed = [char if char.isalnum() else "_" for char in raw]
        return "_".join("".join(allowed).split("_"))


def launch(argv: list[str] | None = None) -> int:
    """Launch the dedicated analysis app."""

    parser = argparse.ArgumentParser(description="Lanseaza aplicatia de analiza a sanatatii plantelor.")
    parser.add_argument("--input", default="")
    parser.add_argument("--wavelengths", default="")
    parser.add_argument("--output", default=str(Path("plant_health_mvp_new_data") / "runs" / "analysis_export"))
    parser.add_argument("--language", choices=("ro", "en"), default="ro")
    args = parser.parse_args(argv)

    app = QtWidgets.QApplication([])
    app.setStyleSheet(DARK_STYLESHEET)
    window = AnalysisWindow(args.input, args.wavelengths, args.output, initial_language=args.language)
    window.show()
    return app.exec()


def main() -> int:
    """Run the analysis app entry point."""

    return launch()


if __name__ == "__main__":
    raise SystemExit(main())
