"""SpectraLeaf desktop control center.

Fresh PySide GUI for the project:

* one organized desktop window
* ESP32 connection, light, filter, preview and capture controls
* automatic capture into the original SpectraLeaf backend
* report/interpretation/graphs/visual outputs loaded from the backend results
"""

from __future__ import annotations

import argparse
import csv
import datetime as dt
import json
import re
import sys
from argparse import Namespace
from pathlib import Path
from typing import Any

from PySide6 import QtCore, QtGui, QtWidgets


ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from plant_health_mvp_new_data.analysis_app.graphs import IndicesGraphWidget, SpectraGraphWidget  # noqa: E402
from plant_health_mvp_new_data.analysis_app.import_wizard import (  # noqa: E402
    ASSIGNMENT_GRAYSCALE,
    MixedImportEntry,
    save_mixed_import_spec,
)
from plant_health_mvp_new_data.analysis_app.readable import (  # noqa: E402
    build_camera_calibration_text,
    build_detailed_report_text,
    build_interpretation_text,
    build_summary_text,
    build_validation_profile_text,
)
from plant_health_mvp_new_data.main import run_pipeline  # noqa: E402
from spectraleaf_esp32_integration.auto_capture_analyze import (  # noqa: E402
    DEFAULT_BANDS,
    capture_session,
    fetch_bytes,
    fetch_json,
    normalize_base_url,
    parse_bands,
)


DEFAULT_DESKTOP_OUTPUT_ROOT = ROOT / "outputs" / "spectraleaf_desktop_sessions"
ROLE_BY_BAND = {
    532: "BLUE",
    556: "GREEN",
    680: "RED",
    725: "RED_EDGE",
    850: "NIR",
    940: "WATER_BAND",
}

STYLE = """
QMainWindow, QWidget {
    background: #111714;
    color: #edf5ef;
    font-family: "Segoe UI";
    font-size: 10.5pt;
}
QFrame#Sidebar {
    background: #0c1210;
    border-right: 1px solid #29362f;
}
QLabel#Brand {
    font-size: 22pt;
    font-weight: 900;
    color: #ffffff;
}
QLabel#Subtitle {
    color: #9fb0a6;
}
QPushButton#Nav {
    text-align: left;
    background: transparent;
    color: #cbd8cf;
    border: 0;
    border-radius: 8px;
    padding: 10px 12px;
    font-weight: 700;
}
QPushButton#Nav:hover {
    background: #1c2821;
}
QPushButton#Nav[active="true"] {
    background: #244a34;
    color: #ffffff;
}
QFrame#Card, QGroupBox {
    background: #18211c;
    border: 1px solid #314239;
    border-radius: 10px;
}
QGroupBox {
    margin-top: 14px;
    padding: 14px 10px 10px 10px;
    font-weight: 900;
    color: #ffffff;
}
QGroupBox::title {
    subcontrol-origin: margin;
    left: 12px;
    padding: 0 6px;
    color: #9edcaf;
}
QLabel#CardTitle {
    color: #9fb0a6;
    font-size: 9.5pt;
    font-weight: 800;
}
QLabel#CardValue {
    color: #ffffff;
    font-size: 19pt;
    font-weight: 900;
}
QLineEdit, QDoubleSpinBox, QSpinBox, QPlainTextEdit, QTextEdit, QTableWidget, QComboBox, QListWidget {
    background: #202a24;
    color: #f5faf6;
    border: 1px solid #43564b;
    border-radius: 6px;
    padding: 5px;
    selection-background-color: #2f8659;
}
QLineEdit:focus, QDoubleSpinBox:focus, QSpinBox:focus, QPlainTextEdit:focus, QTextEdit:focus, QComboBox:focus {
    border: 1px solid #79d99b;
}
QPlainTextEdit, QTextEdit {
    font-family: "Consolas";
    font-size: 9.5pt;
}
QPushButton {
    background: #29352e;
    color: #f5faf6;
    border: 1px solid #53685b;
    border-radius: 7px;
    padding: 8px 12px;
    min-height: 28px;
    font-weight: 800;
}
QPushButton:hover {
    background: #34453b;
}
QPushButton:disabled {
    color: #7b8980;
    background: #202821;
    border-color: #354139;
}
QPushButton#Primary {
    background: #247846;
    border-color: #3fba70;
}
QPushButton#Primary:hover {
    background: #2c9155;
}
QPushButton#Blue {
    background: #285f8b;
    border-color: #3d87c4;
}
QPushButton#Subtle {
    background: #1d2520;
    color: #cdd8d0;
}
QTabWidget::pane {
    border: 1px solid #314239;
    background: #151d18;
}
QTabBar::tab {
    background: #202a24;
    border: 1px solid #314239;
    border-bottom: 0;
    padding: 8px 12px;
}
QTabBar::tab:selected {
    background: #2a382f;
}
QHeaderView::section {
    background: #26332b;
    color: #edf5ef;
    border: 1px solid #394b40;
    padding: 6px;
    font-weight: 800;
}
QTableWidget {
    gridline-color: #314239;
    alternate-background-color: #19231e;
}
"""


def session_name(raw: str) -> str:
    text = re.sub(r"[^A-Za-z0-9_.-]+", "_", raw.strip()).strip("_")
    return text or f"leaf_{dt.datetime.now().strftime('%Y%m%d_%H%M%S')}"


def band_image_path(session_dir: Path, band: int) -> Path:
    for suffix in (".jpg", ".jpeg", ".png", ".bmp", ".tif", ".tiff"):
        path = session_dir / f"{band}{suffix}"
        if path.exists():
            return path
    raise FileNotFoundError(f"Missing captured image for {band} nm in {session_dir}")


def build_backend_input_spec(session_dir: Path, bands: list[int]) -> Path:
    entries: list[MixedImportEntry] = []
    for band in bands:
        entries.append(
            MixedImportEntry(
                path=band_image_path(session_dir, band),
                assignment=ASSIGNMENT_GRAYSCALE,
                role=ROLE_BY_BAND.get(band, "CUSTOM"),
                custom_role="" if band in ROLE_BY_BAND else f"BAND_{band}",
                wavelength_nm=float(band),
                image_id=f"band_{band}",
            )
        )

    reference_band = 850 if 850 in bands else bands[0]
    return save_mixed_import_spec(
        entries,
        session_dir / "mixed_import_spec.json",
        alignment_reference=f"band_{reference_band}",
        alignment_mode="resize_only",
        transform_model="affine",
    )


class ImagePanel(QtWidgets.QLabel):
    def __init__(self, empty_text: str) -> None:
        super().__init__(empty_text)
        self.setAlignment(QtCore.Qt.AlignmentFlag.AlignCenter)
        self.setMinimumSize(520, 340)
        self.setStyleSheet(
            "QLabel { background: #070b09; border: 1px solid #33463a; "
            "border-radius: 10px; color: #b7c7bd; font-size: 12pt; }"
        )
        self._pixmap: QtGui.QPixmap | None = None
        self._empty_text = empty_text

    def set_bytes(self, raw: bytes) -> None:
        pixmap = QtGui.QPixmap()
        if not pixmap.loadFromData(raw):
            raise ValueError("The returned data is not a valid image.")
        self._pixmap = pixmap
        self._scale()

    def set_image_path(self, path: Path) -> None:
        pixmap = QtGui.QPixmap(str(path))
        if pixmap.isNull():
            self.clear_panel(f"Could not load:\n{path}")
            return
        self._pixmap = pixmap
        self._scale()

    def clear_panel(self, text: str | None = None) -> None:
        self._pixmap = None
        self.clear()
        self.setText(text or self._empty_text)

    def resizeEvent(self, event: QtGui.QResizeEvent) -> None:  # noqa: N802
        super().resizeEvent(event)
        self._scale()

    def _scale(self) -> None:
        if self._pixmap is None:
            return
        self.setPixmap(
            self._pixmap.scaled(
                self.size(),
                QtCore.Qt.AspectRatioMode.KeepAspectRatio,
                QtCore.Qt.TransformationMode.SmoothTransformation,
            )
        )


class CaptureWorker(QtCore.QThread):
    log = QtCore.Signal(str)
    completed = QtCore.Signal(dict)
    failed = QtCore.Signal(str)

    def __init__(
        self,
        *,
        esp32_url: str,
        output_root: Path,
        sample_name_value: str,
        bands: list[int],
        settle_ms: int,
        timeout: float,
        light_mode: str,
        ndvi_threshold: float,
        spot_threshold: float,
        spot_min_area: int,
        spot_texture_window: int,
    ) -> None:
        super().__init__()
        self.esp32_url = esp32_url
        self.output_root = output_root
        self.sample_name_value = sample_name_value
        self.bands = bands
        self.settle_ms = settle_ms
        self.timeout = timeout
        self.light_mode = light_mode
        self.ndvi_threshold = ndvi_threshold
        self.spot_threshold = spot_threshold
        self.spot_min_area = spot_min_area
        self.spot_texture_window = spot_texture_window

    def run(self) -> None:
        try:
            self.output_root.mkdir(parents=True, exist_ok=True)
            self.log.emit("Starting ESP32 capture.")
            session_dir = capture_session(
                esp32_url=self.esp32_url,
                output_root=self.output_root,
                bands=self.bands,
                sample_name=self.sample_name_value,
                settle_ms=self.settle_ms,
                timeout=self.timeout,
                light_mode=self.light_mode,
            )
            self.log.emit(f"Captured images: {session_dir}")

            spec_path = build_backend_input_spec(session_dir, self.bands)
            analysis_dir = session_dir / "analysis"
            self.log.emit("Running original SpectraLeaf backend.")
            artifacts = run_pipeline(
                Namespace(
                    input=spec_path,
                    archive_sample=None,
                    wavelengths=None,
                    output=analysis_dir,
                    save_mock_dataset=False,
                    exact_tolerance=1.0,
                    nearest_tolerance=15.0,
                    interpolation_max_gap=80.0,
                    prefer_interpolation=False,
                    band_profile="profile_7band_default",
                    ndvi_threshold=self.ndvi_threshold,
                    fallback_percentile=70.0,
                    no_mask_cleanup=False,
                    spot_threshold=self.spot_threshold,
                    spot_min_area=self.spot_min_area,
                    spot_texture_window=self.spot_texture_window,
                )
            )
            self.completed.emit(
                {
                    "session_dir": str(session_dir),
                    "analysis_dir": str(analysis_dir),
                    "spec_path": str(spec_path),
                    "artifacts": artifacts,
                }
            )
        except Exception as exc:  # noqa: BLE001
            self.failed.emit(str(exc))


class SpectraLeafApp(QtWidgets.QMainWindow):
    def __init__(self, language: str = "ro") -> None:
        super().__init__()
        self.language = language
        self.current_report: dict[str, Any] = {}
        self.current_analysis_dir: Path | None = None
        self.worker: CaptureWorker | None = None
        self.preview_busy = False
        self.live_timer = QtCore.QTimer(self)
        self.live_timer.setInterval(1800)
        self.live_timer.timeout.connect(self.capture_preview)

        self.setWindowTitle("SpectraLeaf Control Center")
        self.resize(1520, 930)
        self.build_ui()
        self.refresh_bands()
        self.refresh_sessions()
        self.show_page(0)

    def build_ui(self) -> None:
        central = QtWidgets.QWidget()
        self.setCentralWidget(central)
        root = QtWidgets.QHBoxLayout(central)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(0)

        root.addWidget(self.build_sidebar())
        self.stack = QtWidgets.QStackedWidget()
        root.addWidget(self.stack, 1)

        self.stack.addWidget(self.build_dashboard_page())
        self.stack.addWidget(self.build_capture_page())
        self.stack.addWidget(self.build_results_page())
        self.stack.addWidget(self.build_visual_page())
        self.stack.addWidget(self.build_sessions_page())
        self.stack.addWidget(self.build_settings_page())

    def build_sidebar(self) -> QtWidgets.QFrame:
        sidebar = QtWidgets.QFrame()
        sidebar.setObjectName("Sidebar")
        sidebar.setFixedWidth(230)
        layout = QtWidgets.QVBoxLayout(sidebar)
        layout.setContentsMargins(18, 22, 18, 18)
        layout.setSpacing(10)

        brand = QtWidgets.QLabel("SpectraLeaf")
        brand.setObjectName("Brand")
        subtitle = QtWidgets.QLabel("multispectral control")
        subtitle.setObjectName("Subtitle")
        layout.addWidget(brand)
        layout.addWidget(subtitle)
        layout.addSpacing(18)

        self.nav_buttons: list[QtWidgets.QPushButton] = []
        for index, label in enumerate(("Dashboard", "Capture", "Results", "Visual review", "Sessions", "Settings")):
            button = QtWidgets.QPushButton(label)
            button.setObjectName("Nav")
            button.setProperty("active", False)
            button.clicked.connect(lambda _checked=False, page=index: self.show_page(page))
            self.nav_buttons.append(button)
            layout.addWidget(button)

        layout.addStretch(1)
        backup = QtWidgets.QPushButton("Open output folder")
        backup.setObjectName("Subtle")
        backup.clicked.connect(self.open_output_root)
        layout.addWidget(backup)
        return sidebar

    def page_shell(self, title: str, subtitle: str) -> tuple[QtWidgets.QWidget, QtWidgets.QVBoxLayout]:
        page = QtWidgets.QWidget()
        layout = QtWidgets.QVBoxLayout(page)
        layout.setContentsMargins(22, 20, 22, 20)
        layout.setSpacing(14)
        title_label = QtWidgets.QLabel(title)
        title_label.setStyleSheet("font-size: 24pt; font-weight: 900; color: #ffffff;")
        sub_label = QtWidgets.QLabel(subtitle)
        sub_label.setObjectName("Subtitle")
        layout.addWidget(title_label)
        layout.addWidget(sub_label)
        return page, layout

    def card(self, title: str, value: str) -> tuple[QtWidgets.QFrame, QtWidgets.QLabel]:
        frame = QtWidgets.QFrame()
        frame.setObjectName("Card")
        layout = QtWidgets.QVBoxLayout(frame)
        layout.setContentsMargins(14, 12, 14, 12)
        title_label = QtWidgets.QLabel(title)
        title_label.setObjectName("CardTitle")
        value_label = QtWidgets.QLabel(value)
        value_label.setObjectName("CardValue")
        value_label.setWordWrap(True)
        layout.addWidget(title_label)
        layout.addWidget(value_label)
        return frame, value_label

    def group(self, title: str) -> tuple[QtWidgets.QGroupBox, QtWidgets.QFormLayout]:
        box = QtWidgets.QGroupBox(title)
        form = QtWidgets.QFormLayout(box)
        form.setContentsMargins(12, 12, 12, 12)
        form.setSpacing(8)
        return box, form

    def build_dashboard_page(self) -> QtWidgets.QWidget:
        page, layout = self.page_shell("Dashboard", "One place to see hardware state, current session and analysis summary.")
        cards = QtWidgets.QHBoxLayout()
        self.esp_card, self.esp_value = self.card("ESP32", "not checked")
        self.light_card, self.light_value = self.card("Box light", "unknown")
        self.session_card, self.session_value = self.card("Session", "-")
        self.backend_card, self.backend_value = self.card("Backend", "ready")
        for card in (self.esp_card, self.light_card, self.session_card, self.backend_card):
            cards.addWidget(card)
        layout.addLayout(cards)

        actions = QtWidgets.QHBoxLayout()
        for text, slot, name in (
            ("Check ESP32", self.check_esp32, "Blue"),
            ("Preview selected band", self.capture_preview, "Subtle"),
            ("Capture all + analyze", self.run_full_capture, "Primary"),
            ("Load latest session", self.load_latest_session, "Subtle"),
        ):
            button = QtWidgets.QPushButton(text)
            button.setObjectName(name)
            button.clicked.connect(slot)
            actions.addWidget(button)
        actions.addStretch(1)
        layout.addLayout(actions)

        self.dashboard_summary = QtWidgets.QPlainTextEdit()
        self.dashboard_summary.setReadOnly(True)
        self.dashboard_summary.setPlainText("No analysis loaded yet.")
        layout.addWidget(self.dashboard_summary, 1)
        return page

    def build_capture_page(self) -> QtWidgets.QWidget:
        page, layout = self.page_shell("Capture", "Control ESP32, lamp, filter wheel and automatic capture.")
        split = QtWidgets.QHBoxLayout()
        layout.addLayout(split, 1)

        scroll = QtWidgets.QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFixedWidth(470)
        controls = QtWidgets.QWidget()
        controls_layout = QtWidgets.QVBoxLayout(controls)
        controls_layout.setContentsMargins(4, 4, 4, 4)
        controls_layout.setSpacing(10)
        scroll.setWidget(controls)
        split.addWidget(scroll)

        self.esp32_url = QtWidgets.QLineEdit("http://192.168.4.1")
        connection, form = self.group("1. ESP32 connection")
        form.addRow("ESP32 URL", self.esp32_url)
        row = QtWidgets.QHBoxLayout()
        check = QtWidgets.QPushButton("Check")
        check.setObjectName("Blue")
        check.clicked.connect(self.check_esp32)
        bands = QtWidgets.QPushButton("Load bands")
        bands.clicked.connect(self.load_esp32_bands)
        row.addWidget(check)
        row.addWidget(bands)
        form.addRow("", row)
        self.esp32_status = QtWidgets.QPlainTextEdit()
        self.esp32_status.setReadOnly(True)
        self.esp32_status.setMaximumHeight(110)
        form.addRow("Status", self.esp32_status)
        controls_layout.addWidget(connection)

        light, form = self.group("2. Box light")
        self.light_state = QtWidgets.QLabel("unknown")
        self.light_mode = QtWidgets.QComboBox()
        for label, value in (
            ("Auto during capture", "auto"),
            ("Keep current state", "keep"),
            ("Force on", "on"),
            ("Force off", "off"),
        ):
            self.light_mode.addItem(label, value)
        light_row = QtWidgets.QHBoxLayout()
        for text, state in (("On", "on"), ("Off", "off"), ("Toggle", "toggle")):
            button = QtWidgets.QPushButton(text)
            button.setObjectName("Blue" if state == "on" else "Subtle")
            button.clicked.connect(lambda _checked=False, s=state: self.set_light(s))
            light_row.addWidget(button)
        form.addRow("State", self.light_state)
        form.addRow("Capture mode", self.light_mode)
        form.addRow("", light_row)
        controls_layout.addWidget(light)

        camera, form = self.group("3. Filter and preview")
        self.bands_edit = QtWidgets.QLineEdit(",".join(str(band) for band in DEFAULT_BANDS))
        self.band_combo = QtWidgets.QComboBox()
        self.bands_edit.textChanged.connect(self.refresh_bands)
        form.addRow("Bands", self.bands_edit)
        form.addRow("Selected band", self.band_combo)
        row = QtWidgets.QHBoxLayout()
        move = QtWidgets.QPushButton("Move filter")
        move.clicked.connect(self.move_filter)
        preview = QtWidgets.QPushButton("Single preview")
        preview.clicked.connect(self.capture_preview)
        row.addWidget(move)
        row.addWidget(preview)
        form.addRow("", row)
        row = QtWidgets.QHBoxLayout()
        live = QtWidgets.QPushButton("Start live")
        live.setObjectName("Blue")
        live.clicked.connect(self.start_live)
        stop = QtWidgets.QPushButton("Stop live")
        stop.setObjectName("Subtle")
        stop.clicked.connect(self.stop_live)
        row.addWidget(live)
        row.addWidget(stop)
        form.addRow("", row)
        controls_layout.addWidget(camera)

        run, form = self.group("4. Automatic run")
        self.sample_name = QtWidgets.QLineEdit(session_name("leaf_sample"))
        self.output_root = QtWidgets.QLineEdit(str(DEFAULT_DESKTOP_OUTPUT_ROOT))
        output_row = QtWidgets.QHBoxLayout()
        output_row.addWidget(self.output_root, 1)
        choose = QtWidgets.QPushButton("Choose")
        choose.clicked.connect(self.choose_output_root)
        output_row.addWidget(choose)
        self.settle_ms = QtWidgets.QSpinBox()
        self.settle_ms.setRange(0, 10000)
        self.settle_ms.setValue(150)
        self.capture_timeout = QtWidgets.QDoubleSpinBox()
        self.capture_timeout.setRange(3.0, 120.0)
        self.capture_timeout.setValue(20.0)
        self.capture_timeout.setSuffix(" s")
        self.run_button = QtWidgets.QPushButton("Capture all + run backend")
        self.run_button.setObjectName("Primary")
        self.run_button.clicked.connect(self.run_full_capture)
        form.addRow("Sample", self.sample_name)
        form.addRow("Output", output_row)
        form.addRow("Settle", self.settle_ms)
        form.addRow("Timeout", self.capture_timeout)
        form.addRow("", self.run_button)
        controls_layout.addWidget(run)
        controls_layout.addStretch(1)

        right = QtWidgets.QVBoxLayout()
        split.addLayout(right, 1)
        self.preview_panel = ImagePanel("No camera preview yet.")
        self.log = QtWidgets.QPlainTextEdit()
        self.log.setReadOnly(True)
        self.log.setMaximumHeight(180)
        right.addWidget(self.preview_panel, 1)
        right.addWidget(QtWidgets.QLabel("Log"))
        right.addWidget(self.log)
        return page

    def build_results_page(self) -> QtWidgets.QWidget:
        page, layout = self.page_shell("Results", "Backend interpretation, graphs, calibration and raw report.")
        self.result_tabs = QtWidgets.QTabWidget()
        self.summary_text = QtWidgets.QPlainTextEdit()
        self.interpretation_text = QtWidgets.QPlainTextEdit()
        self.calibration_text = QtWidgets.QPlainTextEdit()
        self.detailed_text = QtWidgets.QPlainTextEdit()
        self.json_text = QtWidgets.QPlainTextEdit()
        for edit in (self.summary_text, self.interpretation_text, self.calibration_text, self.detailed_text, self.json_text):
            edit.setReadOnly(True)
        self.spectra_graph = SpectraGraphWidget()
        self.indices_graph = IndicesGraphWidget()
        self.band_table = QtWidgets.QTableWidget(0, 7)
        self.band_table.setHorizontalHeaderLabels(["Band", "Mean", "White norm", "Source comp.", "Spectrometer est.", "Status", "Model"])
        self.band_table.horizontalHeader().setStretchLastSection(True)
        self.result_tabs.addTab(self.summary_text, "Summary")
        self.result_tabs.addTab(self.interpretation_text, "Interpretation")
        self.result_tabs.addTab(self.spectra_graph, "Spectrum")
        self.result_tabs.addTab(self.indices_graph, "Indices")
        self.result_tabs.addTab(self.band_table, "Bands")
        self.result_tabs.addTab(self.calibration_text, "Calibration")
        self.result_tabs.addTab(self.detailed_text, "Full text")
        self.result_tabs.addTab(self.json_text, "JSON")
        layout.addWidget(self.result_tabs, 1)
        return page

    def build_visual_page(self) -> QtWidgets.QWidget:
        page, layout = self.page_shell("Visual review", "Inspect masks, spot maps, spectra images and alignment previews.")
        split = QtWidgets.QHBoxLayout()
        layout.addLayout(split, 1)
        self.visual_list = QtWidgets.QListWidget()
        self.visual_list.setFixedWidth(320)
        self.visual_list.currentItemChanged.connect(self.show_visual_item)
        self.visual_panel = ImagePanel("Run or load an analysis to see visual outputs.")
        split.addWidget(self.visual_list)
        split.addWidget(self.visual_panel, 1)
        return page

    def build_sessions_page(self) -> QtWidgets.QWidget:
        page, layout = self.page_shell("Sessions", "Load old automatic runs or open their folders.")
        actions = QtWidgets.QHBoxLayout()
        for text, slot, name in (
            ("Refresh", self.refresh_sessions, "Subtle"),
            ("Load selected", self.load_selected_session, "Blue"),
            ("Open selected folder", self.open_selected_session, "Subtle"),
            ("Open output root", self.open_output_root, "Subtle"),
        ):
            button = QtWidgets.QPushButton(text)
            button.setObjectName(name)
            button.clicked.connect(slot)
            actions.addWidget(button)
        actions.addStretch(1)
        layout.addLayout(actions)
        self.session_table = QtWidgets.QTableWidget(0, 4)
        self.session_table.setHorizontalHeaderLabels(["Session", "Modified", "Analysis report", "Folder"])
        self.session_table.horizontalHeader().setStretchLastSection(True)
        self.session_table.setSelectionBehavior(QtWidgets.QAbstractItemView.SelectionBehavior.SelectRows)
        self.session_table.cellDoubleClicked.connect(lambda _r, _c: self.load_selected_session())
        layout.addWidget(self.session_table, 1)
        return page

    def build_settings_page(self) -> QtWidgets.QWidget:
        page, layout = self.page_shell("Settings", "Analysis thresholds and project paths.")
        row = QtWidgets.QHBoxLayout()
        layout.addLayout(row)
        backend, form = self.group("Backend thresholds")
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
        self.language_combo.addItem("Romanian", "ro")
        self.language_combo.addItem("English", "en")
        self.language_combo.setCurrentIndex(1 if self.language == "en" else 0)
        self.language_combo.currentIndexChanged.connect(self.reload_report_texts)
        form.addRow("Language", self.language_combo)
        form.addRow("NDVI threshold", self.ndvi_threshold)
        form.addRow("Spot threshold", self.spot_threshold)
        form.addRow("Min spot area", self.spot_min_area)
        form.addRow("Texture window", self.spot_texture)
        row.addWidget(backend)

        notes, note_form = self.group("ESP32 firmware notes")
        text = QtWidgets.QPlainTextEdit()
        text.setReadOnly(True)
        text.setPlainText(
            "Light endpoint:\n"
            "/light?state=on | off | toggle\n\n"
            "Capture endpoint:\n"
            "/capture?band=850&light=auto\n\n"
            "Set LIGHT_PIN in the firmware to the GPIO connected to your transistor."
        )
        note_form.addRow(text)
        row.addWidget(notes, 1)
        layout.addStretch(1)
        return page

    def show_page(self, index: int) -> None:
        self.stack.setCurrentIndex(index)
        for i, button in enumerate(self.nav_buttons):
            button.setProperty("active", i == index)
            button.style().unpolish(button)
            button.style().polish(button)

    def selected_band(self) -> int:
        value = self.band_combo.currentData()
        return int(value if value is not None else 850)

    def esp32_base(self) -> str:
        return normalize_base_url(self.esp32_url.text())

    def output_root_path(self) -> Path:
        return Path(self.output_root.text().strip() or str(DEFAULT_DESKTOP_OUTPUT_ROOT)).expanduser().resolve()

    def capture_light_mode(self) -> str:
        return str(self.light_mode.currentData() or "auto")

    def write_log(self, text: str) -> None:
        self.log.appendPlainText(f"[{dt.datetime.now().strftime('%H:%M:%S')}] {text}")

    def refresh_bands(self) -> None:
        current = self.band_combo.currentData() if hasattr(self, "band_combo") else None
        if not hasattr(self, "band_combo"):
            return
        self.band_combo.blockSignals(True)
        self.band_combo.clear()
        for band in parse_bands(self.bands_edit.text() if hasattr(self, "bands_edit") else ",".join(map(str, DEFAULT_BANDS))):
            self.band_combo.addItem(f"{band} nm", band)
        index = self.band_combo.findData(current if current is not None else 850)
        if index >= 0:
            self.band_combo.setCurrentIndex(index)
        self.band_combo.blockSignals(False)

    def check_esp32(self) -> None:
        try:
            payload = fetch_json(f"{self.esp32_base()}/status", timeout=5)
        except Exception as exc:  # noqa: BLE001
            self.esp_value.setText("offline")
            self.esp32_status.setPlainText(str(exc))
            self.write_log(f"ESP32 check failed: {exc}")
            return
        self.esp_value.setText(payload.get("ip", "online"))
        self.esp32_status.setPlainText(json.dumps(payload, indent=2))
        if "light_on" in payload:
            self.light_value.setText("on" if payload["light_on"] else "off")
            self.light_state.setText("on" if payload["light_on"] else "off")
        self.apply_bands_payload(payload.get("bands"))
        self.write_log("ESP32 is online.")

    def load_esp32_bands(self) -> None:
        try:
            payload = fetch_json(f"{self.esp32_base()}/bands", timeout=5)
        except Exception as exc:  # noqa: BLE001
            self.write_log(f"Could not load bands: {exc}")
            return
        self.apply_bands_payload(payload)
        self.write_log("Loaded bands from ESP32.")

    def apply_bands_payload(self, payload: Any) -> None:
        if not isinstance(payload, list):
            return
        bands = [str(int(float(item["wavelength"]))) for item in payload if isinstance(item, dict) and item.get("wavelength") is not None]
        if bands:
            self.bands_edit.setText(",".join(bands))

    def set_light(self, state: str) -> None:
        try:
            payload = fetch_json(f"{self.esp32_base()}/light?state={state}", timeout=8)
        except Exception as exc:  # noqa: BLE001
            self.write_log(f"Light command failed: {exc}")
            return
        value = "on" if payload.get("light_on") else "off"
        self.light_state.setText(value)
        self.light_value.setText(value)
        self.esp32_status.setPlainText(json.dumps(payload, indent=2))
        self.write_log(f"Light {value}.")

    def move_filter(self) -> None:
        band = self.selected_band()
        try:
            payload = fetch_json(f"{self.esp32_base()}/move?band={band}", timeout=12)
        except Exception as exc:  # noqa: BLE001
            self.write_log(f"Move failed: {exc}")
            return
        self.esp32_status.setPlainText(json.dumps(payload, indent=2))
        self.write_log(f"Moved to {band} nm.")

    def capture_preview(self) -> None:
        if self.preview_busy:
            return
        self.preview_busy = True
        band = self.selected_band()
        try:
            raw = fetch_bytes(f"{self.esp32_base()}/capture?band={band}&light={self.capture_light_mode()}", timeout=20)
            self.preview_panel.set_bytes(raw)
            self.write_log(f"Preview captured at {band} nm.")
        except Exception as exc:  # noqa: BLE001
            self.preview_panel.clear_panel("Preview failed. Check ESP32/camera.")
            self.write_log(f"Preview failed: {exc}")
        finally:
            self.preview_busy = False

    def start_live(self) -> None:
        self.live_timer.start()
        self.capture_preview()
        self.write_log("Live preview started.")

    def stop_live(self) -> None:
        self.live_timer.stop()
        self.write_log("Live preview stopped.")

    def run_full_capture(self) -> None:
        if self.worker is not None and self.worker.isRunning():
            return
        self.stop_live()
        sample = session_name(self.sample_name.text())
        self.sample_name.setText(sample)
        self.run_button.setEnabled(False)
        self.backend_value.setText("running")
        self.worker = CaptureWorker(
            esp32_url=self.esp32_base(),
            output_root=self.output_root_path(),
            sample_name_value=sample,
            bands=parse_bands(self.bands_edit.text()),
            settle_ms=int(self.settle_ms.value()),
            timeout=float(self.capture_timeout.value()),
            light_mode=self.capture_light_mode(),
            ndvi_threshold=float(self.ndvi_threshold.value()),
            spot_threshold=float(self.spot_threshold.value()),
            spot_min_area=int(self.spot_min_area.value()),
            spot_texture_window=int(self.spot_texture.value()),
        )
        self.worker.log.connect(self.write_log)
        self.worker.completed.connect(self.capture_finished)
        self.worker.failed.connect(self.capture_failed)
        self.worker.finished.connect(lambda: self.run_button.setEnabled(True))
        self.worker.start()

    def capture_finished(self, result: dict[str, Any]) -> None:
        self.backend_value.setText("complete")
        analysis_dir = Path(result["analysis_dir"])
        self.load_analysis_dir(analysis_dir)
        self.refresh_sessions()
        self.show_page(2)
        self.write_log(f"Loaded analysis: {analysis_dir}")

    def capture_failed(self, message: str) -> None:
        self.backend_value.setText("error")
        self.write_log(f"Capture failed: {message}")
        QtWidgets.QMessageBox.critical(self, "SpectraLeaf capture failed", message)

    def choose_output_root(self) -> None:
        path = QtWidgets.QFileDialog.getExistingDirectory(self, "Choose automatic output folder", self.output_root.text())
        if path:
            self.output_root.setText(path)
            self.refresh_sessions()

    def refresh_sessions(self) -> None:
        if not hasattr(self, "session_table"):
            return
        root = self.output_root_path()
        root.mkdir(parents=True, exist_ok=True)
        sessions = sorted((p for p in root.iterdir() if p.is_dir()), key=lambda p: p.stat().st_mtime, reverse=True)
        self.session_table.setRowCount(0)
        for session in sessions[:60]:
            row = self.session_table.rowCount()
            self.session_table.insertRow(row)
            report = session / "analysis" / "mapping_report.json"
            values = [
                session.name,
                dt.datetime.fromtimestamp(session.stat().st_mtime).strftime("%Y-%m-%d %H:%M:%S"),
                str(report) if report.exists() else "",
                str(session),
            ]
            for column, value in enumerate(values):
                item = QtWidgets.QTableWidgetItem(value)
                item.setToolTip(value)
                self.session_table.setItem(row, column, item)

    def selected_session_path(self) -> Path | None:
        rows = sorted({item.row() for item in self.session_table.selectedItems()})
        if not rows:
            return None
        item = self.session_table.item(rows[0], 3)
        return Path(item.text()) if item else None

    def load_selected_session(self) -> None:
        session = self.selected_session_path()
        if session is None:
            return
        self.load_analysis_dir(session / "analysis")
        self.show_page(2)

    def load_latest_session(self) -> None:
        self.refresh_sessions()
        if self.session_table.rowCount() == 0:
            return
        self.session_table.selectRow(0)
        self.load_selected_session()

    def open_selected_session(self) -> None:
        session = self.selected_session_path()
        if session is not None:
            QtGui.QDesktopServices.openUrl(QtCore.QUrl.fromLocalFile(str(session)))

    def open_output_root(self) -> None:
        root = self.output_root_path()
        root.mkdir(parents=True, exist_ok=True)
        QtGui.QDesktopServices.openUrl(QtCore.QUrl.fromLocalFile(str(root)))

    def load_analysis_dir(self, analysis_dir: Path) -> None:
        report_path = analysis_dir / "mapping_report.json"
        if not report_path.exists():
            QtWidgets.QMessageBox.warning(self, "No report", f"No mapping_report.json found in:\n{analysis_dir}")
            return
        self.current_analysis_dir = analysis_dir
        self.current_report = json.loads(report_path.read_text(encoding="utf-8"))
        self.session_value.setText(analysis_dir.parent.name)
        self.reload_report_texts()
        self.spectra_graph.set_report(self.current_report)
        self.indices_graph.set_report(self.current_report)
        self.populate_band_table()
        self.populate_visuals()

    def reload_report_texts(self) -> None:
        if not self.current_report:
            return
        self.language = str(self.language_combo.currentData() or "ro")
        self.summary_text.setPlainText(build_summary_text(self.current_report, language=self.language))
        self.interpretation_text.setPlainText(build_interpretation_text(self.current_report, language=self.language))
        self.calibration_text.setPlainText(
            build_camera_calibration_text(self.current_report)
            + "\n\n"
            + build_validation_profile_text(self.current_report)
        )
        self.detailed_text.setPlainText(build_detailed_report_text(self.current_report, language=self.language))
        self.json_text.setPlainText(json.dumps(self.current_report, indent=2, default=str))
        self.dashboard_summary.setPlainText(build_summary_text(self.current_report, language=self.language))

    def populate_band_table(self) -> None:
        self.band_table.setRowCount(0)
        average = self.current_report.get("whole_leaf", {}).get("average_bands", {})
        corrected = self.current_report.get("camera_calibration", {}).get("corrected_bands", {})
        for band in sorted(set(average) | set(corrected), key=lambda item: float(item)):
            row = self.band_table.rowCount()
            self.band_table.insertRow(row)
            corr = corrected.get(str(band), {}) if isinstance(corrected, dict) else {}
            values = [
                str(band),
                self.format_value(average.get(str(band))),
                self.format_value(corr.get("white_normalized_camera")),
                self.format_value(corr.get("source_curve_compensated_camera")),
                self.format_value(corr.get("best_spectrometer_window_intensity")),
                str(corr.get("status") or ""),
                str(corr.get("best_spectrometer_model") or ""),
            ]
            for column, value in enumerate(values):
                self.band_table.setItem(row, column, QtWidgets.QTableWidgetItem(value))

    def populate_visuals(self) -> None:
        self.visual_list.clear()
        self.visual_panel.clear_panel()
        if self.current_analysis_dir is None:
            return
        candidates = [
            ("Vegetation mask", self.current_analysis_dir / "vegetation_mask.png"),
            ("Suspicious mask", self.current_analysis_dir / "suspicious_spot_mask.png"),
            ("Spot labels", self.current_analysis_dir / "spot_labels.png"),
            ("Spot score", self.current_analysis_dir / "spot_score.png"),
            ("Average spectrum", self.current_analysis_dir / "average_spectrum.png"),
            ("Alignment reference", self.current_analysis_dir / "alignment_preview" / "reference_image.png"),
            ("Alignment overlay after", self.current_analysis_dir / "alignment_preview" / "overlay_after_alignment.png"),
            ("Alignment overlay before", self.current_analysis_dir / "alignment_preview" / "overlay_before_alignment.png"),
        ]
        for label, path in candidates:
            if path.exists():
                item = QtWidgets.QListWidgetItem(label)
                item.setData(QtCore.Qt.ItemDataRole.UserRole, str(path))
                self.visual_list.addItem(item)
        if self.visual_list.count():
            self.visual_list.setCurrentRow(0)

    def show_visual_item(self, current: QtWidgets.QListWidgetItem | None, _previous: QtWidgets.QListWidgetItem | None) -> None:
        if current is None:
            return
        self.visual_panel.set_image_path(Path(current.data(QtCore.Qt.ItemDataRole.UserRole)))

    @staticmethod
    def format_value(value: Any) -> str:
        try:
            number = float(value)
        except (TypeError, ValueError):
            return "-"
        return f"{number:.5g}"


def launch(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Launch SpectraLeaf desktop control center.")
    parser.add_argument("--language", choices=("ro", "en"), default="ro")
    args = parser.parse_args(argv)
    app = QtWidgets.QApplication([])
    app.setStyleSheet(STYLE)
    window = SpectraLeafApp(language=args.language)
    window.show()
    return app.exec()


def main() -> int:
    return launch()


if __name__ == "__main__":
    raise SystemExit(main())
