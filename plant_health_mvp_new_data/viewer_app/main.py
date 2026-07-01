"""Dedicated viewer app for hyperspectral sample inspection."""

from __future__ import annotations

import argparse
import csv
from pathlib import Path
from typing import Any

import numpy as np
from matplotlib.backends.backend_qtagg import FigureCanvasQTAgg as FigureCanvas
from matplotlib.figure import Figure
from PySide6 import QtCore, QtGui, QtWidgets

from ..core.alignment_preview import build_alignment_preview
from ..core.adapters.base import AdapterSample
from ..core.adapters.registry import adapter_for_path
from ..core.band_extraction import normalize_band_for_image
from ..core.loader import load_sample
from ..core.models.sample import SpectralSample
from ..core.roi_tools import pixel_spectrum, roi_average_spectrum
from ..gui.alignment_preview_widget import AlignmentPreviewWidget
from ..gui.simple_style import SIMPLE_DARK_STYLESHEET, set_simple_margins


class ImageLabel(QtWidgets.QLabel):
    """Image label that emits image coordinates on click."""

    clicked = QtCore.Signal(int, int)

    def __init__(self) -> None:
        super().__init__("Load a sample to view bands")
        self.setAlignment(QtCore.Qt.AlignmentFlag.AlignCenter)
        self.setMinimumSize(680, 430)
        self.setStyleSheet("QLabel { background: #111111; border: 1px solid #777777; }")
        self._source_shape: tuple[int, int] | None = None
        self._pixmap_rect = QtCore.QRect()

    def set_array(self, image: np.ndarray) -> None:
        """Display a grayscale/RGB uint8 image."""

        array = np.ascontiguousarray(np.asarray(image, dtype=np.uint8))
        if array.ndim == 2:
            height, width = array.shape
            qimage = QtGui.QImage(array.data, width, height, width, QtGui.QImage.Format.Format_Grayscale8).copy()
        elif array.ndim == 3 and array.shape[2] == 3:
            height, width, _ = array.shape
            qimage = QtGui.QImage(array.data, width, height, width * 3, QtGui.QImage.Format.Format_RGB888).copy()
        else:
            raise ValueError(f"Unsupported display image shape: {array.shape}")
        self._source_shape = (height, width)
        pixmap = QtGui.QPixmap.fromImage(qimage)
        scaled = pixmap.scaled(
            self.size(),
            QtCore.Qt.AspectRatioMode.KeepAspectRatio,
            QtCore.Qt.TransformationMode.SmoothTransformation,
        )
        self.setPixmap(scaled)
        left = (self.width() - scaled.width()) // 2
        top = (self.height() - scaled.height()) // 2
        self._pixmap_rect = QtCore.QRect(left, top, scaled.width(), scaled.height())

    def mousePressEvent(self, event: QtGui.QMouseEvent) -> None:
        """Emit image-space coordinates for pixel inspection."""

        if self._source_shape is None or not self._pixmap_rect.contains(event.position().toPoint()):
            return
        height, width = self._source_shape
        pos = event.position().toPoint()
        rel_x = (pos.x() - self._pixmap_rect.x()) / max(1, self._pixmap_rect.width())
        rel_y = (pos.y() - self._pixmap_rect.y()) / max(1, self._pixmap_rect.height())
        self.clicked.emit(min(width - 1, max(0, int(rel_x * width))), min(height - 1, max(0, int(rel_y * height))))


class SpectrumPlot(QtWidgets.QWidget):
    """Matplotlib spectrum plot widget."""

    def __init__(self) -> None:
        super().__init__()
        self.figure = Figure(figsize=(6, 3), tight_layout=True)
        self.canvas = FigureCanvas(self.figure)
        self.axes = self.figure.add_subplot(111)
        layout = QtWidgets.QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.addWidget(self.canvas)
        self.clear()

    def clear(self) -> None:
        """Clear the spectrum plot."""

        self.axes.clear()
        self.axes.set_title("Pixel / ROI spectrum")
        self.axes.set_xlabel("Wavelength (nm)")
        self.axes.set_ylabel("Value")
        self.axes.grid(True, alpha=0.25)
        self.canvas.draw_idle()

    def plot(self, wavelengths: np.ndarray, values: np.ndarray, label: str) -> None:
        """Plot a single spectrum."""

        self.axes.clear()
        self.axes.plot(wavelengths, values, label=label, linewidth=1.5)
        self.axes.set_title(label)
        self.axes.set_xlabel("Wavelength (nm)")
        self.axes.set_ylabel("Value")
        self.axes.grid(True, alpha=0.25)
        self.axes.legend(loc="best")
        self.canvas.draw_idle()


class ViewerWindow(QtWidgets.QMainWindow):
    """Dedicated data exploration window with no analysis/report workflow."""

    def __init__(self, initial_input: str = "", initial_wavelengths: str = "", initial_output: str = "") -> None:
        super().__init__()
        self.setWindowTitle("Plant Health Viewer")
        self.resize(1280, 820)
        self.adapter_sample: AdapterSample | None = None
        self.active_sample: SpectralSample | None = None
        self.direct_sample: SpectralSample | None = None
        self.current_display: np.ndarray | None = None
        self.last_spectrum: dict[str, Any] | None = None
        self._build_ui()
        self.input_path.setText(initial_input)
        self.wavelength_path.setText(initial_wavelengths)
        self.output_path.setText(initial_output or str(Path("plant_health_mvp_new_data") / "runs" / "viewer_export"))

    def _build_ui(self) -> None:
        root = QtWidgets.QWidget()
        self.setCentralWidget(root)
        layout = QtWidgets.QHBoxLayout(root)
        set_simple_margins(layout)

        controls = QtWidgets.QWidget()
        controls.setMaximumWidth(350)
        form = QtWidgets.QFormLayout(controls)
        set_simple_margins(form)
        self.input_path = QtWidgets.QLineEdit()
        self.wavelength_path = QtWidgets.QLineEdit()
        self.output_path = QtWidgets.QLineEdit()
        self.sample_combo = QtWidgets.QComboBox()
        self.view_combo = QtWidgets.QComboBox()
        self.view_combo.addItems(["raw", "dark", "white", "reflectance"])
        self.band_slider = QtWidgets.QSlider(QtCore.Qt.Orientation.Horizontal)
        self.band_slider.setEnabled(False)
        self.band_label = QtWidgets.QLabel("Band: -")
        self.roi_x = QtWidgets.QSpinBox()
        self.roi_y = QtWidgets.QSpinBox()
        self.roi_w = QtWidgets.QSpinBox()
        self.roi_h = QtWidgets.QSpinBox()
        for spin in (self.roi_x, self.roi_y, self.roi_w, self.roi_h):
            spin.setRange(0, 100000)
        self.roi_w.setValue(30)
        self.roi_h.setValue(30)
        self.info = QtWidgets.QPlainTextEdit()
        self.info.setReadOnly(True)

        choose = QtWidgets.QPushButton("Load folder")
        choose.clicked.connect(self._choose_folder)
        list_samples = QtWidgets.QPushButton("List samples")
        list_samples.clicked.connect(self._list_samples)
        load = QtWidgets.QPushButton("Load sample")
        load.clicked.connect(self._load_sample)
        inspect_roi = QtWidgets.QPushButton("Check ROI")
        inspect_roi.clicked.connect(self._inspect_roi)
        export_image = QtWidgets.QPushButton("Save image")
        export_image.clicked.connect(self._export_preview)
        export_spectrum = QtWidgets.QPushButton("Save spectrum CSV")
        export_spectrum.clicked.connect(self._export_spectrum)

        form.addRow("Sample", self.input_path)
        form.addRow("", choose)
        form.addRow("Wavelengths", self.wavelength_path)
        form.addRow("Output", self.output_path)
        form.addRow("", list_samples)
        form.addRow("Samples", self.sample_combo)
        form.addRow("", load)
        form.addRow("View", self.view_combo)
        form.addRow("Band", self.band_slider)
        form.addRow("", self.band_label)
        form.addRow("ROI x", self.roi_x)
        form.addRow("ROI y", self.roi_y)
        form.addRow("ROI w", self.roi_w)
        form.addRow("ROI h", self.roi_h)
        form.addRow("", inspect_roi)
        form.addRow("", export_image)
        form.addRow("", export_spectrum)
        form.addRow("Inspector", self.info)

        right = QtWidgets.QSplitter(QtCore.Qt.Orientation.Vertical)
        self.view_tabs = QtWidgets.QTabWidget()
        self.image = ImageLabel()
        self.image.clicked.connect(self._inspect_pixel)
        self.alignment_preview = AlignmentPreviewWidget(show_mask_controls=False)
        self.plot = SpectrumPlot()
        self.view_tabs.addTab(self.image, "Band image")
        self.view_tabs.addTab(self.alignment_preview, "Alignment")
        right.addWidget(self.view_tabs)
        right.addWidget(self.plot)
        right.setSizes([560, 260])
        layout.addWidget(controls)
        layout.addWidget(right, 1)

        self.band_slider.valueChanged.connect(self._update_band)
        self.view_combo.currentTextChanged.connect(self._prepare_active_sample)

    def _choose_folder(self) -> None:
        path = QtWidgets.QFileDialog.getExistingDirectory(self, "Load folder")
        if path:
            self.input_path.setText(path)

    def _list_samples(self) -> None:
        input_text = self.input_path.text().strip()
        input_path = Path(input_text).expanduser() if input_text else None
        if input_path is not None and input_path.is_file() and not input_path.name.lower().endswith((".tar.gz", ".tgz", ".tar")):
            self.sample_combo.clear()
            self.sample_combo.addItem(input_path.name)
            self.info.setPlainText("Found one direct file input.")
            return
        adapter = adapter_for_path(self.input_path.text().strip() or None, self.wavelength_path.text().strip() or None)
        self.sample_combo.clear()
        self.sample_combo.addItems(adapter.list_samples())
        self.info.setPlainText(f"Found {self.sample_combo.count()} sample(s).")

    def _load_sample(self) -> None:
        input_text = self.input_path.text().strip()
        input_path = Path(input_text).expanduser() if input_text else None
        wavelength_path = self.wavelength_path.text().strip() or None
        self.adapter_sample = None
        self.direct_sample = None

        if input_path is not None and input_path.is_file() and not input_path.name.lower().endswith((".tar.gz", ".tgz", ".tar")):
            self.direct_sample = load_sample(input_path, wavelength_path)
            self.active_sample = self.direct_sample
            self.view_combo.setCurrentText("raw")
            self.band_slider.setRange(0, self.active_sample.data.shape[2] - 1)
            self.band_slider.setEnabled(True)
            self._update_band()
            self._refresh_alignment_preview()
            self.info.setPlainText(
                f"Loaded {self.direct_sample.metadata.get('sample_id', input_path.stem)}\n"
                f"Source: {self.direct_sample.source_type}\n"
                f"Cube: {list(self.direct_sample.data.shape) if self.direct_sample.data is not None else '-'}\n"
                f"Alignment: {self.direct_sample.metadata.get('alignment_status', 'not available')}"
            )
            return

        adapter = adapter_for_path(input_text or None, wavelength_path)
        sample_id = self.sample_combo.currentText() or None
        self.adapter_sample = adapter.load_sample(sample_id)
        self._prepare_active_sample()
        self.info.setPlainText(
            f"Loaded {self.adapter_sample.sample_id}\n"
            f"Cube: {list(self.adapter_sample.cube.shape)}\n"
            f"Dark ref: {None if self.adapter_sample.dark_reference is None else list(self.adapter_sample.dark_reference.shape)}\n"
            f"White ref: {None if self.adapter_sample.white_reference is None else list(self.adapter_sample.white_reference.shape)}\n"
            f"Reflectance: {self.adapter_sample.reflectance_cube is not None}"
        )

    def _prepare_active_sample(self) -> None:
        if self.direct_sample is not None:
            self.active_sample = self.direct_sample
            self._refresh_alignment_preview()
            self._update_band()
            return
        if self.adapter_sample is None:
            return
        mode = self.view_combo.currentText()
        cube = {
            "raw": self.adapter_sample.cube,
            "dark": self.adapter_sample.dark_reference,
            "white": self.adapter_sample.white_reference,
            "reflectance": self.adapter_sample.reflectance_cube,
        }.get(mode)
        if cube is None:
            self.info.setPlainText(f"{mode} data is not available for this sample.")
            return
        self.active_sample = SpectralSample(
            source_type=f"{self.adapter_sample.source_type}:{mode}",
            available_wavelengths=np.asarray(self.adapter_sample.wavelengths, dtype=float),
            data=np.asarray(cube),
            metadata=dict(self.adapter_sample.metadata),
        )
        self.band_slider.setRange(0, self.active_sample.data.shape[2] - 1)
        self.band_slider.setEnabled(True)
        self._update_band()
        self._refresh_alignment_preview()

    def _refresh_alignment_preview(self) -> None:
        """Refresh alignment inspection from the active sample metadata."""

        if self.active_sample is None:
            self.alignment_preview.clear()
            return
        preview = build_alignment_preview(self.active_sample)
        self.alignment_preview.set_preview(preview)

    def _update_band(self) -> None:
        if self.active_sample is None or self.active_sample.data is None:
            return
        index = int(self.band_slider.value())
        wavelength = float(self.active_sample.available_wavelengths[index])
        band = self.active_sample.data[:, :, index]
        self.current_display = normalize_band_for_image(band)
        self.image.set_array(self.current_display)
        self.band_label.setText(f"Band {index}: {wavelength:.2f} nm")

    def _inspect_pixel(self, x: int, y: int) -> None:
        if self.active_sample is None:
            return
        spectrum = pixel_spectrum(self.active_sample, x, y)
        self.last_spectrum = {"kind": "pixel", **spectrum}
        wavelengths = np.asarray(spectrum["wavelengths"], dtype=float)
        values = np.asarray(spectrum["values"], dtype=float)
        self.plot.plot(wavelengths, values, f"Pixel ({x}, {y})")
        self.info.setPlainText(f"Pixel ({x}, {y})\nValues at current band: {values[self.band_slider.value()]:.6g}")

    def _inspect_roi(self) -> None:
        if self.active_sample is None:
            return
        spectrum = roi_average_spectrum(
            self.active_sample,
            self.roi_x.value(),
            self.roi_y.value(),
            self.roi_w.value(),
            self.roi_h.value(),
        )
        self.last_spectrum = {"kind": "roi", **spectrum}
        wavelengths = np.asarray(spectrum["wavelengths"], dtype=float)
        values = np.asarray(spectrum["mean_values"], dtype=float)
        self.plot.plot(wavelengths, values, f"ROI {spectrum['bbox']}")
        self.info.setPlainText(f"ROI {spectrum['bbox']}\nPixels: {spectrum['pixel_count']}")

    def _export_preview(self) -> None:
        if self.current_display is None:
            return
        output = Path(self.output_path.text().strip() or "plant_health_mvp_new_data/runs/viewer_export")
        output.mkdir(parents=True, exist_ok=True)
        path = output / f"viewer_band_{self.band_slider.value()}.png"
        from PIL import Image

        Image.fromarray(self.current_display).save(path)
        self.info.setPlainText(f"Saved preview: {path}")

    def _export_spectrum(self) -> None:
        if self.last_spectrum is None:
            return
        output = Path(self.output_path.text().strip() or "plant_health_mvp_new_data/runs/viewer_export")
        output.mkdir(parents=True, exist_ok=True)
        path = output / f"{self.last_spectrum['kind']}_spectrum.csv"
        values = self.last_spectrum.get("values", self.last_spectrum.get("mean_values", []))
        with path.open("w", newline="", encoding="utf-8") as handle:
            writer = csv.writer(handle)
            writer.writerow(["band_index", "wavelength_nm", "value"])
            for index, (wavelength, value) in enumerate(zip(self.last_spectrum["wavelengths"], values)):
                writer.writerow([index, wavelength, value])
        self.info.setPlainText(f"Saved spectrum: {path}")


def launch(argv: list[str] | None = None) -> int:
    """Launch the dedicated viewer app."""

    parser = argparse.ArgumentParser(description="Launch the dedicated hyperspectral viewer app.")
    parser.add_argument("--input", default="")
    parser.add_argument("--wavelengths", default="")
    parser.add_argument("--output", default=str(Path("plant_health_mvp_new_data") / "runs" / "viewer_export"))
    args = parser.parse_args(argv)

    app = QtWidgets.QApplication([])
    app.setStyleSheet(SIMPLE_DARK_STYLESHEET)
    window = ViewerWindow(args.input, args.wavelengths, args.output)
    window.show()
    return app.exec()


def main() -> int:
    """Run the viewer entry point."""

    return launch()


if __name__ == "__main__":
    raise SystemExit(main())
