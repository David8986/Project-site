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
from .readable import build_detailed_report_text, build_interpretation_text, build_summary_text
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

    def __init__(self, initial_input: str = "", initial_wavelengths: str = "", initial_output: str = "") -> None:
        super().__init__()
        self.setWindowTitle("Analiza sanatatii plantelor")
        self.resize(1350, 860)
        self.artifacts: dict[str, Any] = {}
        self.report: dict[str, Any] = {}
        self.spot_rows: list[dict[str, str]] = []
        self.regions: list[RegionDisplay] = []
        self.current_background_image: np.ndarray | None = None
        self.current_overlay_image: np.ndarray | None = None
        self.selected_region_label: int | None = None
        self._build_ui()
        self.input_path.setText(initial_input)
        self.wavelength_path.setText(initial_wavelengths)
        self.output_path.setText(initial_output or str(Path("plant_health_mvp") / "runs" / "analysis_export"))

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

        choose = QtWidgets.QPushButton("Incarca folder esantion")
        choose.clicked.connect(self._choose_folder)
        choose_file = QtWidgets.QPushButton("Incarca imagine/fisier")
        choose_file.clicked.connect(self._choose_file)
        mixed_import = QtWidgets.QPushButton("Configurare imagini mixte")
        mixed_import.clicked.connect(self._open_mixed_import_wizard)
        choose_wavelengths = QtWidgets.QPushButton("Incarca CSV lungimi de unda")
        choose_wavelengths.clicked.connect(self._choose_wavelengths)
        choose_output = QtWidgets.QPushButton("Seteaza folder iesire")
        choose_output.clicked.connect(self._choose_output)
        run = QtWidgets.QPushButton("Ruleaza analiza")
        run.clicked.connect(self._run_analysis)
        reload_outputs = QtWidgets.QPushButton("Reincarca iesirile")
        reload_outputs.clicked.connect(self._load_outputs)

        form.addRow("Esantion", self.input_path)
        form.addRow("", choose)
        form.addRow("", choose_file)
        form.addRow("", mixed_import)
        form.addRow("Lungimi de unda", self.wavelength_path)
        form.addRow("", choose_wavelengths)
        form.addRow("Iesire", self.output_path)
        form.addRow("", choose_output)
        form.addRow("Prag NDVI", self.ndvi_threshold)
        form.addRow("Prag spot", self.spot_threshold)
        form.addRow("Arie minima spot", self.spot_min_area)
        form.addRow("Fereastra textura", self.spot_texture)
        form.addRow("", run)
        form.addRow("", reload_outputs)

        right = QtWidgets.QTabWidget()
        self.summary = QtWidgets.QPlainTextEdit()
        self.summary.setReadOnly(True)
        self.interpretation_text = QtWidgets.QPlainTextEdit()
        self.interpretation_text.setReadOnly(True)
        self.readable_report = QtWidgets.QPlainTextEdit()
        self.readable_report.setReadOnly(True)
        self.spectra_graph = SpectraGraphWidget()
        self.histogram_stats = HistogramStatsWidget()
        self.indices_graph = IndicesGraphWidget()
        self.alignment_preview = AlignmentPreviewWidget(show_mask_controls=True)
        self.glossary = GlossaryWidget()
        self.spots = QtWidgets.QTableWidget(0, 12)
        self.spots.setHorizontalHeaderLabels(
            [
                "eticheta",
                "arie",
                "rang severitate",
                "scor severitate",
                "centroid x",
                "centroid y",
                "bbox",
                "NDVI",
                "NDRE",
                "GNDVI",
                "delta 680 frunza",
                "delta 850 frunza",
            ]
        )
        self.spots.horizontalHeader().setStretchLastSection(True)
        self.spots.setSelectionBehavior(QtWidgets.QAbstractItemView.SelectionBehavior.SelectRows)
        self.spots.itemSelectionChanged.connect(self._spot_selection_changed)
        self.report_text = QtWidgets.QPlainTextEdit()
        self.report_text.setReadOnly(True)
        right.addTab(self.summary, "Rezumat")
        right.addTab(self.interpretation_text, "Interpretare")
        right.addTab(self.alignment_preview, "Aliniere")
        right.addTab(self.spectra_graph, "Spectre")
        right.addTab(self.histogram_stats, "Histograma")
        right.addTab(self.indices_graph, "Indici")
        right.addTab(self.spots, "Tabel spoturi")
        right.addTab(self._overlay_tab(), "Masca / spoturi")
        right.addTab(self.readable_report, "Raport text")
        right.addTab(self.glossary, "Glosar")
        right.addTab(self.report_text, "JSON")

        layout.addWidget(controls)
        layout.addWidget(right, 1)
        self._refresh_glossary_values()
        self.ndvi_threshold.valueChanged.connect(self._refresh_glossary_values)
        self.spot_threshold.valueChanged.connect(self._refresh_glossary_values)
        self.spot_min_area.valueChanged.connect(self._refresh_glossary_values)
        self.spot_texture.valueChanged.connect(self._refresh_glossary_values)

    def _overlay_tab(self) -> QtWidgets.QWidget:
        """Build the suspicious overlay visualization panel."""

        panel = QtWidgets.QWidget()
        layout = QtWidgets.QVBoxLayout(panel)
        set_simple_margins(layout)

        controls = QtWidgets.QGridLayout()
        set_simple_margins(controls)
        self.background_combo = QtWidgets.QComboBox()
        self.background_combo.addItems(
            [
                "680 nm gri",
                "725 nm gri",
                "850 nm gri",
                "RGB 650/556/532",
                "Culoare falsa 850/725/680",
            ]
        )
        self.overlay_mode_combo = QtWidgets.QComboBox()
        self.overlay_mode_combo.addItems(
            [
                "Contur",
                "Masca rosie umpluta",
                "Harta termica",
                "Vegetatie",
                "Doar imagine",
            ]
        )
        self.opacity_slider = QtWidgets.QSlider(QtCore.Qt.Orientation.Horizontal)
        self.opacity_slider.setRange(0, 100)
        self.opacity_slider.setValue(45)
        self.opacity_label = QtWidgets.QLabel("45%")
        self.show_outlines_checkbox = QtWidgets.QCheckBox("Arata contururile")
        self.show_outlines_checkbox.setChecked(True)
        self.show_labels_checkbox = QtWidgets.QCheckBox("Arata etichetele")
        self.show_labels_checkbox.setChecked(False)
        self.show_boxes_checkbox = QtWidgets.QCheckBox("Arata casetele")
        self.show_boxes_checkbox.setChecked(False)
        self.show_suspicious_checkbox = QtWidgets.QCheckBox("Arata masca spoturilor")
        self.show_suspicious_checkbox.setChecked(True)
        self.show_filled_checkbox = QtWidgets.QCheckBox("Arata umplerea rosie")
        self.show_filled_checkbox.setChecked(False)
        self.show_vegetation_checkbox = QtWidgets.QCheckBox("Arata masca frunzei")
        self.show_vegetation_checkbox.setChecked(False)
        refresh = QtWidgets.QPushButton("Actualizeaza")
        refresh.clicked.connect(self._refresh_overlay)
        export_current = QtWidgets.QPushButton("Exporta vizualizarea curenta")
        export_current.clicked.connect(self._export_current_overlay)
        export_all = QtWidgets.QPushButton("Exporta toate vizualizarile")
        export_all.clicked.connect(self._export_all_overlay_modes)

        controls.addWidget(QtWidgets.QLabel("Fundal"), 0, 0)
        controls.addWidget(self.background_combo, 0, 1)
        controls.addWidget(QtWidgets.QLabel("Mod"), 0, 2)
        controls.addWidget(self.overlay_mode_combo, 0, 3)
        controls.addWidget(QtWidgets.QLabel("Opacitate"), 1, 0)
        controls.addWidget(self.opacity_slider, 1, 1)
        controls.addWidget(self.opacity_label, 1, 2)
        controls.addWidget(self.show_outlines_checkbox, 1, 3)
        controls.addWidget(self.show_labels_checkbox, 1, 4)
        controls.addWidget(self.show_boxes_checkbox, 2, 0)
        controls.addWidget(self.show_suspicious_checkbox, 2, 1)
        controls.addWidget(self.show_filled_checkbox, 2, 2)
        controls.addWidget(self.show_vegetation_checkbox, 2, 3)
        controls.addWidget(refresh, 3, 0)
        controls.addWidget(export_current, 3, 1, 1, 2)
        controls.addWidget(export_all, 3, 3, 1, 2)
        layout.addLayout(controls)

        self.overlay_image = OverlayImageLabel()
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
        path = QtWidgets.QFileDialog.getExistingDirectory(self, "Incarca folder esantion")
        if path:
            self.input_path.setText(path)

    def _choose_file(self) -> None:
        path, _ = QtWidgets.QFileDialog.getOpenFileName(
            self,
            "Incarca imagine/fisier",
            "",
            "Fisiere suportate (*.json *.jpg *.jpeg *.png *.tif *.tiff *.bmp *.npz *.npy *.csv *.txt *.tar *.gz);;Specificatii import mixt (*.json);;Imagini (*.jpg *.jpeg *.png *.tif *.tiff *.bmp);;Toate fisierele (*)",
        )
        if path:
            self.input_path.setText(path)

    def _open_mixed_import_wizard(self) -> None:
        """Open the mixed RGB/grayscale import wizard and use the saved spec."""

        current_input = self.input_path.text().strip()
        initial_dir = Path(current_input).parent if current_input else Path.cwd()
        output = self._output_dir()
        default_spec = output / "mixed_import_spec.json"
        dialog = MixedImportDialog(self, initial_directory=initial_dir, output_path=default_spec)
        if dialog.exec() != QtWidgets.QDialog.DialogCode.Accepted:
            return
        spec_path = dialog.result_spec_path()
        if spec_path is None:
            return
        self.input_path.setText(str(spec_path))
        QtWidgets.QMessageBox.information(
            self,
            "Import mixt pregatit",
            "Specificatia de intrare mixta a fost salvata.\n\nRuleaza analiza si se va incarca:\n"
            f"{spec_path}",
        )

    def _choose_wavelengths(self) -> None:
        path, _ = QtWidgets.QFileDialog.getOpenFileName(self, "Incarca CSV lungimi de unda", "", "Fisiere CSV (*.csv);;Toate fisierele (*)")
        if path:
            self.wavelength_path.setText(path)

    def _choose_output(self) -> None:
        path = QtWidgets.QFileDialog.getExistingDirectory(self, "Seteaza folder iesire")
        if path:
            self.output_path.setText(path)

    def _run_analysis(self) -> None:
        output = Path(self.output_path.text().strip() or "plant_health_mvp/runs/analysis_export")
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
            QtWidgets.QMessageBox.critical(self, "Analiza a esuat", str(exc))
            return
        self._load_outputs()

    def _load_outputs(self) -> None:
        output = Path(self.output_path.text().strip() or "plant_health_mvp/runs/analysis_export")
        report_path = output / "mapping_report.json"
        if not report_path.exists():
            self.report = {}
            self.spots.setRowCount(0)
            self.spot_rows = []
            self.regions = []
            self.selected_region_label = None
            self.current_background_image = None
            self.current_overlay_image = None
            self.summary.setPlainText(f"Nu a fost gasit inca niciun raport:\n{report_path}")
            self.interpretation_text.setPlainText("")
            self.readable_report.setPlainText("")
            self.report_text.setPlainText("")
            self.spectra_graph.clear()
            self.histogram_stats.clear()
            self.indices_graph.clear()
            self.glossary.set_report({})
            self.alignment_preview.clear(f"Nu a fost gasita inca nicio previzualizare de aliniere:\n{report_path}")
            self.overlay_image.clear()
            self.overlay_image.setText("Ruleaza analiza sau reincarca un folder de iesire pentru a vedea suprapunerile suspecte.")
            self.overlay_status.setPlainText(f"Nu a fost gasit inca niciun raport:\n{report_path}")
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
            self.summary.setPlainText("Nu este incarcat niciun raport de analiza.")
            self.interpretation_text.setPlainText("")
            self.readable_report.setPlainText("")
            return
        self.summary.setPlainText(build_summary_text(self.report, selected_spot=selected))
        self.interpretation_text.setPlainText(build_interpretation_text(self.report))
        self.readable_report.setPlainText(build_detailed_report_text(self.report, selected_spot=selected))

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
            message = "Nu este disponibila nicio previzualizare de aliniere pentru imagini mixte."
            if alignment:
                message += "\n\nMetadate aliniere:\n" + json.dumps(alignment, indent=2, default=str)
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

        return Path(self.output_path.text().strip() or "plant_health_mvp/runs/analysis_export")

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
                self.overlay_status.setPlainText(f"Suprapunerea nu este disponibila: {exc}")
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
                    "wording": "Suprapunere suspecta / candidati de zone afectate, nu un diagnostic.",
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

        text = self.overlay_mode_combo.currentText().lower()
        if "umpluta" in text:
            return "filled"
        if "termica" in text:
            return "heatmap"
        if "vegetatie" in text:
            return "vegetation"
        if "fundal" in text or "doar imagine" in text:
            return "background"
        return "outline"

    def _load_background_image(self, output: Path) -> np.ndarray:
        """Load the selected display background from exported band images."""

        bands = output / "bands"
        choice = self.background_combo.currentText()
        if choice.startswith("680"):
            return read_uint8_image(bands / "band_680.png")
        if choice.startswith("725"):
            return read_uint8_image(bands / "band_725.png")
        if choice.startswith("850"):
            return read_uint8_image(bands / "band_850.png")
        if choice.startswith("RGB"):
            return build_composite(
                read_uint8_image(bands / "band_650.png"),
                read_uint8_image(bands / "band_556.png"),
                read_uint8_image(bands / "band_532.png"),
            )
        if choice.startswith("Culoare falsa"):
            return build_composite(
                read_uint8_image(bands / "band_850.png"),
                read_uint8_image(bands / "band_725.png"),
                read_uint8_image(bands / "band_680.png"),
            )
        raise ValueError(f"Optiune de fundal necunoscuta: {choice}")

    def _select_available_background(self, output: Path) -> None:
        """Choose a background option that exists for the current output folder."""

        bands = output / "bands"
        needs = {
            "680 nm gri": ("band_680.png",),
            "725 nm gri": ("band_725.png",),
            "850 nm gri": ("band_850.png",),
            "RGB 650/556/532": ("band_650.png", "band_556.png", "band_532.png"),
            "Culoare falsa 850/725/680": ("band_850.png", "band_725.png", "band_680.png"),
        }
        current = self.background_combo.currentText()
        if all((bands / name).exists() for name in needs.get(current, ())):
            return

        preferred = (
            "RGB 650/556/532",
            "680 nm gri",
            "850 nm gri",
            "725 nm gri",
            "Culoare falsa 850/725/680",
        )
        for label in preferred:
            if all((bands / name).exists() for name in needs[label]):
                blocked = self.background_combo.blockSignals(True)
                self.background_combo.setCurrentText(label)
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
        self.overlay_status.setPlainText(f"A fost salvata suprapunerea suspecta curenta:\n{path}")

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
            self.overlay_status.setPlainText(f"Exportul a esuat: {exc}")
            return
        self.overlay_status.setPlainText("Vizualizari salvate:\n" + "\n".join(str(path) for path in saved))

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
    parser.add_argument("--output", default=str(Path("plant_health_mvp") / "runs" / "analysis_export"))
    args = parser.parse_args(argv)

    app = QtWidgets.QApplication([])
    app.setStyleSheet(DARK_STYLESHEET)
    window = AnalysisWindow(args.input, args.wavelengths, args.output)
    window.show()
    return app.exec()


def main() -> int:
    """Run the analysis app entry point."""

    return launch()


if __name__ == "__main__":
    raise SystemExit(main())
