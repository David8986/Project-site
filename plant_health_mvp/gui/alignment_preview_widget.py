"""Reusable Qt widget for visual alignment inspection."""

from __future__ import annotations

import json
from typing import Any, Sequence

import numpy as np
from PySide6 import QtCore, QtGui, QtWidgets

from ..core.alignment_preview import AlignmentPreview
from ..core.visual_overlays import RegionDisplay, render_overlay
from .simple_style import set_simple_margins


class PreviewImageLabel(QtWidgets.QLabel):
    """Dark image label used by the alignment preview widget."""

    def __init__(self, title: str) -> None:
        super().__init__(title)
        self.setAlignment(QtCore.Qt.AlignmentFlag.AlignCenter)
        self.setMinimumSize(240, 200)
        self.setStyleSheet("QLabel { background: #111111; border: 1px solid #777777; color: #eeeeee; }")

    def set_array(self, image: np.ndarray) -> None:
        """Display a uint8 grayscale or RGB image."""

        array = np.ascontiguousarray(np.asarray(image, dtype=np.uint8))
        if array.ndim == 2:
            height, width = array.shape
            qimage = QtGui.QImage(array.data, width, height, width, QtGui.QImage.Format.Format_Grayscale8).copy()
        elif array.ndim == 3 and array.shape[2] == 3:
            height, width, _ = array.shape
            qimage = QtGui.QImage(array.data, width, height, width * 3, QtGui.QImage.Format.Format_RGB888).copy()
        else:
            raise ValueError(f"Unsupported alignment preview image shape: {array.shape}")
        pixmap = QtGui.QPixmap.fromImage(qimage)
        self.setPixmap(
            pixmap.scaled(
                self.size(),
                QtCore.Qt.AspectRatioMode.KeepAspectRatio,
                QtCore.Qt.TransformationMode.SmoothTransformation,
            )
        )


class AlignmentPreviewWidget(QtWidgets.QWidget):
    """Show before/after global alignment previews and metadata."""

    def __init__(self, *, show_mask_controls: bool = False) -> None:
        super().__init__()
        self.preview: AlignmentPreview | None = None
        self.vegetation_mask: np.ndarray | None = None
        self.suspicious_mask: np.ndarray | None = None
        self.regions: list[RegionDisplay] = []
        self.selected_label: int | None = None
        self._build_ui(show_mask_controls)

    def _build_ui(self, show_mask_controls: bool) -> None:
        layout = QtWidgets.QVBoxLayout(self)
        set_simple_margins(layout)

        controls = QtWidgets.QHBoxLayout()
        set_simple_margins(controls)
        self.mode_combo = QtWidgets.QComboBox()
        self.mode_combo.addItems(
            [
                "Alaturat",
                "Suprapunere inainte",
                "Suprapunere dupa",
            ]
        )
        self.opacity_slider = QtWidgets.QSlider(QtCore.Qt.Orientation.Horizontal)
        self.opacity_slider.setRange(0, 100)
        self.opacity_slider.setValue(55)
        self.opacity_label = QtWidgets.QLabel("55%")
        self.show_vegetation = QtWidgets.QCheckBox("Arata masca frunzei")
        self.show_suspicious = QtWidgets.QCheckBox("Arata liniile spoturilor")
        self.show_boxes = QtWidgets.QCheckBox("Arata casetele")
        self.show_vegetation.setVisible(show_mask_controls)
        self.show_suspicious.setVisible(show_mask_controls)
        self.show_boxes.setVisible(show_mask_controls)

        controls.addWidget(QtWidgets.QLabel("Vizualizare"))
        controls.addWidget(self.mode_combo)
        controls.addWidget(QtWidgets.QLabel("Opacitate"))
        controls.addWidget(self.opacity_slider)
        controls.addWidget(self.opacity_label)
        controls.addWidget(self.show_vegetation)
        controls.addWidget(self.show_suspicious)
        controls.addWidget(self.show_boxes)
        controls.addStretch(1)
        layout.addLayout(controls)

        self.side_by_side = QtWidgets.QWidget()
        grid = QtWidgets.QGridLayout(self.side_by_side)
        set_simple_margins(grid)
        self.reference = PreviewImageLabel("Referinta")
        self.before = PreviewImageLabel("Inainte")
        self.after = PreviewImageLabel("Dupa")
        grid.addWidget(QtWidgets.QLabel("Referinta"), 0, 0)
        grid.addWidget(QtWidgets.QLabel("Inainte"), 0, 1)
        grid.addWidget(QtWidgets.QLabel("Dupa"), 0, 2)
        grid.addWidget(self.reference, 1, 0)
        grid.addWidget(self.before, 1, 1)
        grid.addWidget(self.after, 1, 2)
        grid.setColumnStretch(0, 1)
        grid.setColumnStretch(1, 1)
        grid.setColumnStretch(2, 1)

        self.comparison = PreviewImageLabel("Suprapunere")
        self.comparison.setMinimumSize(720, 380)
        layout.addWidget(self.side_by_side, 1)
        layout.addWidget(self.comparison, 1)

        self.metadata = QtWidgets.QPlainTextEdit()
        self.metadata.setReadOnly(True)
        self.metadata.setMaximumHeight(155)
        layout.addWidget(self.metadata)

        self.mode_combo.currentTextChanged.connect(self._refresh)
        self.opacity_slider.valueChanged.connect(self._opacity_changed)
        self.show_vegetation.stateChanged.connect(self._refresh)
        self.show_suspicious.stateChanged.connect(self._refresh)
        self.show_boxes.stateChanged.connect(self._refresh)
        self.clear()

    def clear(self, message: str = "Nu este disponibila inca nicio previzualizare de aliniere pentru imagini mixte.") -> None:
        """Clear the widget and show an explanatory message."""

        self.preview = None
        for label in (self.reference, self.before, self.after, self.comparison):
            label.clear()
            label.setText(message)
        self.metadata.setPlainText(message)

    def set_preview(
        self,
        preview: AlignmentPreview | None,
        *,
        vegetation_mask: np.ndarray | None = None,
        suspicious_mask: np.ndarray | None = None,
        regions: Sequence[RegionDisplay] = (),
        selected_label: int | None = None,
    ) -> None:
        """Load a preview package and optional downstream analysis masks."""

        self.preview = preview
        self.vegetation_mask = vegetation_mask
        self.suspicious_mask = suspicious_mask
        self.regions = list(regions)
        self.selected_label = selected_label
        if preview is None:
            self.clear()
            return
        self.metadata.setPlainText(json.dumps(preview.metadata, indent=2, default=str))
        self._refresh()

    def _opacity_changed(self, value: int) -> None:
        self.opacity_label.setText(f"{int(value)}%")
        self._refresh()

    def _refresh(self) -> None:
        """Render the current comparison mode."""

        if self.preview is None:
            return
        after = self._after_with_optional_masks()
        self.reference.set_array(self.preview.reference_image)
        self.before.set_array(self.preview.moving_before)
        self.after.set_array(after)

        mode = self.mode_combo.currentText().lower()
        if mode.startswith("suprapunere inainte"):
            self.side_by_side.hide()
            self.comparison.show()
            self.comparison.set_array(self.preview.overlay_before)
        elif mode.startswith("suprapunere dupa"):
            self.side_by_side.hide()
            self.comparison.show()
            comparison = self.preview.overlay_after
            if self.show_vegetation.isChecked() or self.show_suspicious.isChecked():
                comparison = render_overlay(
                    comparison,
                    mode="outline",
                    suspicious_mask=self.suspicious_mask if self.show_suspicious.isChecked() else None,
                    vegetation_mask=self.vegetation_mask,
                    regions=self.regions if self.show_suspicious.isChecked() else (),
                    opacity=float(self.opacity_slider.value()) / 100.0,
                    show_outlines=self.show_suspicious.isChecked(),
                    show_labels=False,
                    show_boxes=self.show_boxes.isChecked(),
                    show_suspicious_mask=self.show_suspicious.isChecked(),
                    show_vegetation_mask=self.show_vegetation.isChecked(),
                    selected_label=self.selected_label,
                )
            self.comparison.set_array(comparison)
        else:
            self.comparison.hide()
            self.side_by_side.show()

    def _after_with_optional_masks(self) -> np.ndarray:
        """Return the aligned moving image with optional downstream overlays."""

        if self.preview is None:
            return np.zeros((1, 1, 3), dtype=np.uint8)
        if not (self.show_vegetation.isChecked() or self.show_suspicious.isChecked()):
            return self.preview.moving_after
        return render_overlay(
            self.preview.moving_after,
            mode="outline",
            suspicious_mask=self.suspicious_mask if self.show_suspicious.isChecked() else None,
            vegetation_mask=self.vegetation_mask,
            regions=self.regions if self.show_suspicious.isChecked() else (),
            opacity=float(self.opacity_slider.value()) / 100.0,
            show_outlines=self.show_suspicious.isChecked(),
            show_labels=False,
            show_boxes=self.show_boxes.isChecked(),
            show_suspicious_mask=self.show_suspicious.isChecked(),
            show_vegetation_mask=self.show_vegetation.isChecked(),
            selected_label=self.selected_label,
        )


__all__ = ["AlignmentPreviewWidget", "PreviewImageLabel"]
