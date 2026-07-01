"""Mixed RGB/grayscale image import wizard for the analysis app."""

from __future__ import annotations

import json
import math
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Iterable

from PySide6 import QtCore, QtWidgets

from ..core.filename_wavelength import infer_wavelength_from_filename
from ..gui.simple_style import set_simple_margins


SCHEMA_ID = "plant_health_mvp.mixed_image_bundle.v1"
ASSIGNMENT_RGB = "RGB"
ASSIGNMENT_GRAYSCALE = "GRAYSCALE"
ROLE_OPTIONS = ("RED", "GREEN", "BLUE", "NIR", "RED_EDGE", "WATER_BAND", "CUSTOM")
RGB_ROLE_DISPLAY = "RGB"
ALIGNMENT_MODE_OPTIONS: tuple[tuple[str, str], ...] = (
    ("Faza + ECC", "automatic_phase_ecc"),
    ("ECC", "automatic_ecc"),
    ("ECC afin", "automatic_ecc_affine"),
    ("Masca + ECC", "automatic_mask_then_ecc"),
    ("Caracteristici/muchii", "automatic_feature_edge"),
    ("Contur/masca", "automatic_contour_mask"),
    ("Doar redimensionare", "resize_only"),
    ("Niciuna", "none"),
)
TRANSFORM_MODEL_OPTIONS: tuple[tuple[str, str], ...] = (
    ("Afin", "affine"),
    ("Euclidian", "euclidean"),
    ("Translatie", "translation"),
    ("Omografie", "homography"),
)
RGB_CHANNEL_DEFAULTS: tuple[tuple[str, str, float], ...] = (
    ("R", "RED", 650.0),
    ("G", "GREEN", 556.0),
    ("B", "BLUE", 532.0),
)
ROLE_DEFAULT_WAVELENGTHS_NM: dict[str, float] = {
    "RED": 680.0,
    "GREEN": 556.0,
    "BLUE": 532.0,
    "NIR": 850.0,
    "RED_EDGE": 725.0,
    "WATER_BAND": 940.0,
    "CUSTOM": 0.0,
}

_ASSIGNMENT_LABELS = {
    ASSIGNMENT_RGB: "Imagine RGB",
    ASSIGNMENT_GRAYSCALE: "Banda grayscale",
}
_ASSIGNMENT_FROM_LABEL = {label: key for key, label in _ASSIGNMENT_LABELS.items()}
_IMAGE_FILTER = "Imagini (*.png *.jpg *.jpeg *.tif *.tiff *.bmp);;Toate fisierele (*)"


@dataclass(slots=True)
class MixedImportEntry:
    """One source image row in a mixed import specification."""

    path: str | Path
    assignment: str = ASSIGNMENT_GRAYSCALE
    role: str = "NIR"
    wavelength_nm: float | None = 850.0
    custom_role: str = ""
    image_id: str = ""


def build_quick_start_entries(
    rgb_path: str | Path,
    nir_path: str | Path,
    nir_wavelength_nm: float = 850.0,
) -> list[MixedImportEntry]:
    """Return entries for the common RGB-plus-850 nm NIR import case."""

    return [
        MixedImportEntry(path=rgb_path, assignment=ASSIGNMENT_RGB),
        MixedImportEntry(
            path=nir_path,
            assignment=ASSIGNMENT_GRAYSCALE,
            role="NIR",
            wavelength_nm=nir_wavelength_nm,
        ),
    ]


def build_mixed_import_spec(
    entries: Iterable[MixedImportEntry],
    alignment_reference: str | Path | None = None,
    alignment_mode: str = "automatic_phase_ecc",
    transform_model: str = "affine",
) -> dict[str, Any]:
    """Build a versioned JSON-ready mixed image bundle specification."""

    normalized_entries = list(entries)
    if not normalized_entries:
        raise ValueError("Adauga cel putin o imagine inainte sa salvezi specificatia de import mixt.")

    images: list[dict[str, Any]] = []
    bands: list[dict[str, Any]] = []
    seen_ids: set[str] = set()

    for index, entry in enumerate(normalized_entries, start=1):
        image_id = _normalized_image_id(entry.image_id, index)
        if image_id in seen_ids:
            raise ValueError(f"Id duplicat de imagine in specificatia de import mixt: {image_id}")
        seen_ids.add(image_id)

        path_text = _normalized_path_text(entry.path)
        assignment = _normalized_assignment(entry.assignment)
        if assignment == ASSIGNMENT_RGB:
            image, image_bands = _rgb_image_spec(image_id, path_text)
        else:
            image, image_bands = _grayscale_image_spec(image_id, path_text, entry)
        images.append(image)
        bands.extend(image_bands)

    alignment = _alignment_spec(
        alignment_reference,
        images,
        alignment_mode=alignment_mode,
        transform_model=transform_model,
    )
    reference_id = alignment["reference_image_id"]
    for band in bands:
        band["alignment_reference_image_id"] = reference_id

    return {
        "schema": SCHEMA_ID,
        "version": 1,
        "bundle_type": "mixed_image_bundle",
        "created_by": "plant_health_mvp.analysis_app.import_wizard",
        "alignment": alignment,
        "images": images,
        "bands": bands,
        "loader_hints": {
            "band_axis": "last",
            "rgb_channel_order": "RGB",
            "align_to_reference": reference_id is not None,
        },
    }


def write_mixed_import_spec(spec: dict[str, Any], output_path: str | Path) -> Path:
    """Write a mixed import spec dictionary to JSON and return its path."""

    path = _json_output_path(output_path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(spec, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return path


def load_mixed_import_spec(path: str | Path) -> dict[str, Any]:
    """Load and lightly validate a mixed image bundle JSON spec."""

    spec_path = _json_output_path(path)
    data = json.loads(spec_path.read_text(encoding="utf-8"))
    if not isinstance(data, dict):
        raise ValueError("Specificatia de import mixt trebuie sa fie un obiect JSON.")
    if data.get("schema") != SCHEMA_ID and data.get("bundle_type") != "mixed_image_bundle":
        raise ValueError("Fisierul JSON ales nu pare sa fie o specificatie de import mixt.")
    return data


def entries_from_mixed_import_spec(spec: dict[str, Any]) -> list[MixedImportEntry]:
    """Recover editable dialog rows from an existing mixed import spec."""

    raw_images = spec.get("images")
    if not isinstance(raw_images, list):
        raise ValueError("Specificatia de import mixt nu contine lista 'images'.")

    entries: list[MixedImportEntry] = []
    for index, raw_image in enumerate(raw_images, start=1):
        if not isinstance(raw_image, dict):
            raise ValueError(f"Imaginea {index} din specificatie nu este un obiect JSON.")

        path = raw_image.get("path")
        if not path:
            raise ValueError(f"Imaginea {index} din specificatie nu are campul 'path'.")

        image_id = str(raw_image.get("id") or f"image_{index:03d}")
        assignment_text = str(raw_image.get("assignment") or "").lower()
        if assignment_text == "rgb":
            entries.append(
                MixedImportEntry(
                    path=str(path),
                    assignment=ASSIGNMENT_RGB,
                    role=RGB_ROLE_DISPLAY,
                    wavelength_nm=None,
                    image_id=image_id,
                )
            )
            continue

        if assignment_text != "grayscale":
            raise ValueError(f"Tip de imagine neacceptat in specificatie: {assignment_text or '(gol)'}")

        role, custom_role = _editable_role_from_spec(raw_image)
        entries.append(
            MixedImportEntry(
                path=str(path),
                assignment=ASSIGNMENT_GRAYSCALE,
                role=role,
                wavelength_nm=_optional_float(raw_image.get("wavelength_nm")),
                custom_role=custom_role,
                image_id=image_id,
            )
        )

    return entries


def alignment_settings_from_mixed_import_spec(spec: dict[str, Any]) -> dict[str, str | None]:
    """Return editable alignment settings from an existing mixed import spec."""

    alignment = spec.get("alignment")
    if not isinstance(alignment, dict):
        alignment = {}
    return {
        "mode": str(alignment.get("mode") or "automatic_phase_ecc"),
        "transform_model": str(alignment.get("transform_model") or "affine"),
        "reference_image_id": str(alignment.get("reference_image_id") or "") or None,
    }


def save_mixed_import_spec(
    entries: Iterable[MixedImportEntry],
    output_path: str | Path,
    alignment_reference: str | Path | None = None,
    alignment_mode: str = "automatic_phase_ecc",
    transform_model: str = "affine",
) -> Path:
    """Build and save a mixed import specification in one call."""

    spec = build_mixed_import_spec(
        entries,
        alignment_reference=alignment_reference,
        alignment_mode=alignment_mode,
        transform_model=transform_model,
    )
    return write_mixed_import_spec(spec, output_path)


class MixedImportDialog(QtWidgets.QDialog):
    """Dialog for collecting mixed RGB and grayscale band image files."""

    savedSpecPath = QtCore.Signal(str)

    _COL_FILE = 0
    _COL_ASSIGNMENT = 1
    _COL_ROLE = 2
    _COL_WAVELENGTH = 3
    _COL_CUSTOM_ROLE = 4

    def __init__(
        self,
        parent: QtWidgets.QWidget | None = None,
        initial_directory: str | Path | None = None,
        output_path: str | Path | None = None,
    ) -> None:
        super().__init__(parent)
        self.setWindowTitle("Import imagini mixte")
        self.resize(860, 520)
        self._initial_directory = Path(initial_directory).expanduser() if initial_directory else Path.cwd()
        self._saved_spec_path: Path | None = None
        self._build_ui(output_path)

    def result_spec_path(self) -> Path | None:
        """Return the spec path saved by this dialog, if one has been saved."""

        return self._saved_spec_path

    @property
    def spec_path(self) -> Path | None:
        """Return the spec path saved by this dialog, if one has been saved."""

        return self.result_spec_path()

    def add_image_paths(
        self,
        paths: Iterable[str | Path],
        assignment: str | None = None,
        role: str | None = None,
        wavelength_nm: float | None = None,
    ) -> None:
        """Append image paths to the table using sensible default band metadata."""

        for raw_path in paths:
            row_assignment = _normalized_assignment(assignment) if assignment else self._default_assignment()
            row_role = role or (RGB_ROLE_DISPLAY if row_assignment == ASSIGNMENT_RGB else "NIR")
            row_wavelength = wavelength_nm
            if row_wavelength is None and row_assignment != ASSIGNMENT_RGB:
                row_wavelength = infer_wavelength_from_filename(raw_path)
            if row_wavelength is None:
                row_wavelength = ROLE_DEFAULT_WAVELENGTHS_NM.get(row_role, 850.0)
            self._append_entry(
                MixedImportEntry(
                    path=raw_path,
                    assignment=row_assignment,
                    role=row_role,
                    wavelength_nm=row_wavelength,
                )
            )
        self._refresh_alignment_reference()

    def set_entries(self, entries: Iterable[MixedImportEntry]) -> None:
        """Replace the current table rows with the provided import entries."""

        self.table.setRowCount(0)
        for entry in entries:
            self._append_entry(entry)
        self._refresh_alignment_reference()

    def load_spec_path(self, spec_path: str | Path) -> Path:
        """Load an existing mixed import spec into the editable table."""

        path = _json_output_path(spec_path)
        spec = load_mixed_import_spec(path)
        self.set_entries(entries_from_mixed_import_spec(spec))
        settings = alignment_settings_from_mixed_import_spec(spec)
        self._set_combo_data(self.alignment_mode, settings["mode"])
        self._set_combo_data(self.transform_model, settings["transform_model"])
        if settings["reference_image_id"] is not None:
            self._select_alignment_reference(str(settings["reference_image_id"]))
        else:
            self.alignment_reference.setCurrentIndex(0)
        self._saved_spec_path = path
        self.spec_path_edit.setText(str(path))
        return path

    def apply_quick_start(
        self,
        rgb_path: str | Path | None = None,
        nir_path: str | Path | None = None,
    ) -> None:
        """Apply the RGB-plus-NIR-850 preset to paths or to the first two rows."""

        if rgb_path is None and nir_path is None and self.table.rowCount() >= 2:
            entries = self._collect_entries()
            entries[0].assignment = ASSIGNMENT_RGB
            entries[0].role = RGB_ROLE_DISPLAY
            entries[0].wavelength_nm = ROLE_DEFAULT_WAVELENGTHS_NM["RED"]
            entries[1].assignment = ASSIGNMENT_GRAYSCALE
            entries[1].role = "NIR"
            entries[1].wavelength_nm = 850.0
            self.set_entries(entries)
            self._select_alignment_reference("image_001")
            return

        if rgb_path is None:
            rgb_path = self._choose_single_image("Alege imaginea RGB")
        if not rgb_path:
            return
        if nir_path is None:
            nir_path = self._choose_single_image("Alege imaginea benzii NIR 850")
        if not nir_path:
            return

        self.set_entries(build_quick_start_entries(rgb_path, nir_path))
        self._select_alignment_reference("image_001")

    def current_spec(self) -> dict[str, Any]:
        """Return the current table contents as a mixed image bundle spec."""

        return build_mixed_import_spec(
            self._collect_entries(),
            alignment_reference=self.alignment_reference.currentData(),
            alignment_mode=str(self.alignment_mode.currentData()),
            transform_model=str(self.transform_model.currentData()),
        )

    def save_current_spec(self, output_path: str | Path | None = None) -> Path:
        """Validate and save the current spec, returning the saved JSON path."""

        target = output_path or self.spec_path_edit.text().strip()
        if not target:
            raise ValueError("Alege unde sa salvezi specificatia de import mixt.")
        saved_path = write_mixed_import_spec(self.current_spec(), target)
        self._saved_spec_path = saved_path
        self.spec_path_edit.setText(str(saved_path))
        self.savedSpecPath.emit(str(saved_path))
        return saved_path

    def _build_ui(self, output_path: str | Path | None) -> None:
        layout = QtWidgets.QVBoxLayout(self)
        set_simple_margins(layout)

        intro = QtWidgets.QLabel(
            "Adauga fisiere imagine. Marcheaza imagine RGB sau banda grayscale. Salveaza un fisier JSON."
        )
        intro.setWordWrap(True)
        layout.addWidget(intro)

        toolbar = QtWidgets.QHBoxLayout()
        set_simple_margins(toolbar)
        add = QtWidgets.QPushButton("Adauga imagini")
        add.clicked.connect(self._choose_images)
        replace = QtWidgets.QPushButton("Inlocuieste fisier")
        replace.clicked.connect(self._replace_selected_image)
        remove = QtWidgets.QPushButton("Elimina selectia")
        remove.clicked.connect(self._remove_selected)
        quick = QtWidgets.QPushButton("Foloseste RGB + NIR")
        quick.clicked.connect(lambda: self.apply_quick_start())
        load_existing = QtWidgets.QPushButton("Deschide JSON existent")
        load_existing.clicked.connect(self._choose_existing_spec)
        toolbar.addWidget(add)
        toolbar.addWidget(replace)
        toolbar.addWidget(remove)
        toolbar.addWidget(quick)
        toolbar.addWidget(load_existing)
        toolbar.addStretch(1)
        layout.addLayout(toolbar)

        self.table = QtWidgets.QTableWidget(0, 5)
        self.table.setHorizontalHeaderLabels(["Fisier imagine", "Tip", "Rol", "Lungime de unda", "Rol personalizat"])
        self.table.horizontalHeader().setStretchLastSection(True)
        self.table.verticalHeader().setVisible(False)
        self.table.setSelectionBehavior(QtWidgets.QAbstractItemView.SelectionBehavior.SelectRows)
        self.table.setAlternatingRowColors(True)
        layout.addWidget(self.table, stretch=1)

        form = QtWidgets.QFormLayout()
        set_simple_margins(form)
        self.alignment_mode = QtWidgets.QComboBox()
        for label, value in ALIGNMENT_MODE_OPTIONS:
            self.alignment_mode.addItem(label, value)
        self.alignment_mode.setToolTip(
            "Modurile automate aliniaza global imaginea completa inainte de analiza. Doar redimensionare are incredere scazuta."
        )
        form.addRow("Mod aliniere", self.alignment_mode)

        self.transform_model = QtWidgets.QComboBox()
        for label, value in TRANSFORM_MODEL_OPTIONS:
            self.transform_model.addItem(label, value)
        self.transform_model.setToolTip("Modelul de transformare folosit de modurile automate de aliniere.")
        form.addRow("Model transformare", self.transform_model)

        self.alignment_reference = QtWidgets.QComboBox()
        self.alignment_reference.addItem("Fara referinta", None)
        form.addRow("Referinta aliniere", self.alignment_reference)

        spec_row = QtWidgets.QHBoxLayout()
        self.spec_path_edit = QtWidgets.QLineEdit()
        default_output = output_path or Path("plant_health_mvp_new_data") / "runs" / "mixed_import_spec.json"
        self.spec_path_edit.setText(str(default_output))
        choose_spec = QtWidgets.QPushButton("Alege fisier")
        choose_spec.clicked.connect(self._choose_spec_path)
        spec_row.addWidget(self.spec_path_edit, stretch=1)
        spec_row.addWidget(choose_spec)
        form.addRow("Specificatie JSON", spec_row)
        layout.addLayout(form)

        buttons = QtWidgets.QHBoxLayout()
        set_simple_margins(buttons)
        buttons.addStretch(1)
        cancel = QtWidgets.QPushButton("Anuleaza")
        cancel.clicked.connect(self.reject)
        save = QtWidgets.QPushButton("Salveaza JSON")
        save.clicked.connect(self._save_clicked)
        save.setDefault(True)
        buttons.addWidget(cancel)
        buttons.addWidget(save)
        layout.addLayout(buttons)

    def _append_entry(self, entry: MixedImportEntry) -> None:
        row = self.table.rowCount()
        self.table.insertRow(row)

        path_text = _normalized_path_text(entry.path)
        item = QtWidgets.QTableWidgetItem(Path(path_text).name)
        item.setData(
            QtCore.Qt.ItemDataRole.UserRole,
            {
                "path": path_text,
                "image_id": str(entry.image_id or ""),
            },
        )
        item.setToolTip(path_text)
        item.setFlags(item.flags() & ~QtCore.Qt.ItemFlag.ItemIsEditable)
        self.table.setItem(row, self._COL_FILE, item)

        assignment = _normalized_assignment(entry.assignment)
        assignment_combo = QtWidgets.QComboBox()
        for key, label in _ASSIGNMENT_LABELS.items():
            assignment_combo.addItem(label, key)
        assignment_combo.setCurrentIndex(max(0, assignment_combo.findData(assignment)))
        assignment_combo.currentTextChanged.connect(self._assignment_changed_for_sender)
        self.table.setCellWidget(row, self._COL_ASSIGNMENT, assignment_combo)

        role_combo = QtWidgets.QComboBox()
        if assignment == ASSIGNMENT_RGB:
            role_combo.addItem(RGB_ROLE_DISPLAY)
            role_combo.addItems(ROLE_OPTIONS)
            role_combo.setCurrentText(RGB_ROLE_DISPLAY)
        else:
            role_combo.addItems(ROLE_OPTIONS)
            role_combo.setCurrentText(_normalized_role(entry.role))
        role_combo.currentTextChanged.connect(self._role_changed_for_sender)
        self.table.setCellWidget(row, self._COL_ROLE, role_combo)

        wavelength = entry.wavelength_nm
        if wavelength is None and assignment != ASSIGNMENT_RGB:
            wavelength = infer_wavelength_from_filename(path_text)
        if wavelength is None:
            wavelength = ROLE_DEFAULT_WAVELENGTHS_NM.get(role_combo.currentText(), 850.0)
        wavelength_spin = QtWidgets.QDoubleSpinBox()
        wavelength_spin.setRange(0.0, 3000.0)
        wavelength_spin.setDecimals(1)
        wavelength_spin.setSingleStep(5.0)
        wavelength_spin.setSuffix(" nm")
        wavelength_spin.setValue(float(wavelength))
        self.table.setCellWidget(row, self._COL_WAVELENGTH, wavelength_spin)

        custom_role = QtWidgets.QLineEdit(entry.custom_role)
        custom_role.setPlaceholderText("Rol personalizat")
        self.table.setCellWidget(row, self._COL_CUSTOM_ROLE, custom_role)
        self._sync_row_controls(row)

    def _collect_entries(self) -> list[MixedImportEntry]:
        entries: list[MixedImportEntry] = []
        for row in range(self.table.rowCount()):
            item = self.table.item(row, self._COL_FILE)
            if item is None:
                continue
            assignment_combo = self.table.cellWidget(row, self._COL_ASSIGNMENT)
            role_combo = self.table.cellWidget(row, self._COL_ROLE)
            wavelength_spin = self.table.cellWidget(row, self._COL_WAVELENGTH)
            custom_role = self.table.cellWidget(row, self._COL_CUSTOM_ROLE)
            if not isinstance(assignment_combo, QtWidgets.QComboBox):
                continue
            if not isinstance(role_combo, QtWidgets.QComboBox):
                continue
            if not isinstance(wavelength_spin, QtWidgets.QDoubleSpinBox):
                continue
            if not isinstance(custom_role, QtWidgets.QLineEdit):
                continue
            path_text, image_id = self._file_item_payload(item)
            entries.append(
                MixedImportEntry(
                    path=path_text,
                    assignment=str(assignment_combo.currentData()),
                    role=role_combo.currentText(),
                    wavelength_nm=float(wavelength_spin.value()),
                    custom_role=custom_role.text().strip(),
                    image_id=image_id,
                )
            )
        return entries

    def _default_assignment(self) -> str:
        return ASSIGNMENT_RGB if self.table.rowCount() == 0 else ASSIGNMENT_GRAYSCALE

    def _choose_images(self) -> None:
        paths, _ = QtWidgets.QFileDialog.getOpenFileNames(
            self,
            "Adauga imagini",
            str(self._initial_directory),
            _IMAGE_FILTER,
        )
        if paths:
            self.add_image_paths(paths)

    def _choose_single_image(self, title: str) -> str | None:
        path, _ = QtWidgets.QFileDialog.getOpenFileName(self, title, str(self._initial_directory), _IMAGE_FILTER)
        return path or None

    def _choose_existing_spec(self) -> None:
        path, _ = QtWidgets.QFileDialog.getOpenFileName(
            self,
            "Deschide specificatie de import mixt",
            self.spec_path_edit.text().strip() or str(self._initial_directory),
            "JSON files (*.json);;All files (*)",
        )
        if not path:
            return
        try:
            self.load_spec_path(path)
        except Exception as exc:
            QtWidgets.QMessageBox.warning(self, "Import mixt", str(exc))

    def _choose_spec_path(self) -> None:
        path, _ = QtWidgets.QFileDialog.getSaveFileName(
            self,
            "Salveaza specificatia de import mixt",
            self.spec_path_edit.text().strip(),
            "JSON files (*.json);;All files (*)",
        )
        if path:
            self.spec_path_edit.setText(str(_json_output_path(path)))

    def _replace_selected_image(self) -> None:
        selected_rows = sorted({index.row() for index in self.table.selectedIndexes()})
        if len(selected_rows) != 1:
            QtWidgets.QMessageBox.information(self, "Import mixt", "Selecteaza exact un rand de imagine de inlocuit.")
            return

        row = selected_rows[0]
        item = self.table.item(row, self._COL_FILE)
        if item is None:
            return
        current_path, image_id = self._file_item_payload(item)
        start_dir = str(Path(current_path).parent) if current_path else str(self._initial_directory)
        path, _ = QtWidgets.QFileDialog.getOpenFileName(self, "Inlocuieste fisierul imaginii", start_dir, _IMAGE_FILTER)
        if not path:
            return

        normalized = _normalized_path_text(path)
        item.setText(Path(normalized).name)
        item.setToolTip(normalized)
        item.setData(QtCore.Qt.ItemDataRole.UserRole, {"path": normalized, "image_id": image_id})

        assignment_combo = self.table.cellWidget(row, self._COL_ASSIGNMENT)
        wavelength_spin = self.table.cellWidget(row, self._COL_WAVELENGTH)
        inferred = infer_wavelength_from_filename(normalized)
        if (
            inferred is not None
            and isinstance(assignment_combo, QtWidgets.QComboBox)
            and assignment_combo.currentData() != ASSIGNMENT_RGB
            and isinstance(wavelength_spin, QtWidgets.QDoubleSpinBox)
        ):
            wavelength_spin.setValue(float(inferred))
        self._refresh_alignment_reference()

    def _remove_selected(self) -> None:
        selected_rows = sorted({index.row() for index in self.table.selectedIndexes()})
        if not selected_rows:
            return
        kept = [
            entry
            for row, entry in enumerate(self._collect_entries())
            if row not in selected_rows
        ]
        self.set_entries(kept)

    def _save_clicked(self) -> None:
        try:
            saved_path = self.save_current_spec()
        except Exception as exc:
            QtWidgets.QMessageBox.warning(self, "Import mixt", str(exc))
            return
        QtWidgets.QMessageBox.information(self, "Import mixt", f"Specificatie salvata:\n{saved_path}")
        self.accept()

    def _assignment_changed_for_sender(self) -> None:
        sender = self.sender()
        row = self._row_for_widget(sender)
        if row >= 0:
            self._sync_row_controls(row)

    def _role_changed_for_sender(self) -> None:
        sender = self.sender()
        row = self._row_for_widget(sender)
        if row < 0:
            return
        role_combo = self.table.cellWidget(row, self._COL_ROLE)
        wavelength_spin = self.table.cellWidget(row, self._COL_WAVELENGTH)
        if isinstance(role_combo, QtWidgets.QComboBox) and isinstance(wavelength_spin, QtWidgets.QDoubleSpinBox):
            default = ROLE_DEFAULT_WAVELENGTHS_NM.get(role_combo.currentText(), 0.0)
            if default > 0.0:
                wavelength_spin.setValue(default)
        self._sync_row_controls(row)

    def _sync_row_controls(self, row: int) -> None:
        assignment_combo = self.table.cellWidget(row, self._COL_ASSIGNMENT)
        role_combo = self.table.cellWidget(row, self._COL_ROLE)
        wavelength_spin = self.table.cellWidget(row, self._COL_WAVELENGTH)
        custom_role = self.table.cellWidget(row, self._COL_CUSTOM_ROLE)
        if not isinstance(assignment_combo, QtWidgets.QComboBox):
            return
        if not isinstance(role_combo, QtWidgets.QComboBox):
            return
        if not isinstance(wavelength_spin, QtWidgets.QDoubleSpinBox):
            return
        if not isinstance(custom_role, QtWidgets.QLineEdit):
            return

        is_rgb = assignment_combo.currentData() == ASSIGNMENT_RGB
        if is_rgb:
            if role_combo.findText(RGB_ROLE_DISPLAY) < 0:
                role_combo.insertItem(0, RGB_ROLE_DISPLAY)
            role_combo.setCurrentText(RGB_ROLE_DISPLAY)
        else:
            rgb_index = role_combo.findText(RGB_ROLE_DISPLAY)
            if rgb_index >= 0:
                role_combo.removeItem(rgb_index)
            if role_combo.currentText() not in ROLE_OPTIONS:
                role_combo.setCurrentText("NIR")
        role_combo.setEnabled(not is_rgb)
        wavelength_spin.setEnabled(not is_rgb)
        custom_role.setEnabled((not is_rgb) and role_combo.currentText() == "CUSTOM")
        if is_rgb:
            role_combo.setToolTip("Imaginile RGB mapeaza canalele la benzile RED, GREEN si BLUE.")
            wavelength_spin.setToolTip("Canalele RGB folosesc implicit 650, 556 si 532 nm.")
            custom_role.setToolTip("Rolul personalizat este folosit doar pentru randurile grayscale.")
        else:
            role_combo.setToolTip("")
            wavelength_spin.setToolTip("")
            custom_role.setToolTip("")

    def _row_for_widget(self, widget: QtCore.QObject | None) -> int:
        if widget is None:
            return -1
        for row in range(self.table.rowCount()):
            for column in (self._COL_ASSIGNMENT, self._COL_ROLE, self._COL_WAVELENGTH, self._COL_CUSTOM_ROLE):
                if self.table.cellWidget(row, column) is widget:
                    return row
        return -1

    def _refresh_alignment_reference(self) -> None:
        previous = self.alignment_reference.currentData()
        self.alignment_reference.clear()
        self.alignment_reference.addItem("Fara referinta de aliniere", None)
        for index, entry in enumerate(self._collect_entries(), start=1):
            image_id = _normalized_image_id(entry.image_id, index)
            label = f"{image_id}: {Path(str(entry.path)).name}"
            self.alignment_reference.addItem(label, image_id)
        if previous is not None:
            self._select_alignment_reference(str(previous))

    def _select_alignment_reference(self, image_id: str) -> None:
        index = self.alignment_reference.findData(image_id)
        if index >= 0:
            self.alignment_reference.setCurrentIndex(index)

    def _set_combo_data(self, combo: QtWidgets.QComboBox, value: str | None) -> None:
        index = combo.findData(value)
        if index >= 0:
            combo.setCurrentIndex(index)

    def _file_item_payload(self, item: QtWidgets.QTableWidgetItem) -> tuple[str, str]:
        payload = item.data(QtCore.Qt.ItemDataRole.UserRole)
        if isinstance(payload, dict):
            return str(payload.get("path") or ""), str(payload.get("image_id") or "")
        return str(payload or ""), ""


def _rgb_image_spec(image_id: str, path_text: str) -> tuple[dict[str, Any], list[dict[str, Any]]]:
    channels: list[dict[str, Any]] = []
    bands: list[dict[str, Any]] = []
    for channel, role, wavelength in RGB_CHANNEL_DEFAULTS:
        channel_spec = {
            "channel": channel,
            "role": role,
            "role_label": role,
            "wavelength_nm": wavelength,
        }
        channels.append(channel_spec)
        bands.append(
            {
                "id": f"{image_id}_{channel.lower()}",
                "source_image_id": image_id,
                "path": path_text,
                "assignment": "rgb_channel",
                "source_channel": channel,
                "role": role,
                "role_label": role,
                "wavelength_nm": wavelength,
            }
        )
    return (
        {
            "id": image_id,
            "path": path_text,
            "assignment": "rgb",
            "role": "RGB",
            "channels": channels,
        },
        bands,
    )


def _grayscale_image_spec(
    image_id: str,
    path_text: str,
    entry: MixedImportEntry,
) -> tuple[dict[str, Any], list[dict[str, Any]]]:
    role = _normalized_role(entry.role)
    role_label = _role_label(role, entry.custom_role)
    wavelength = entry.wavelength_nm
    if wavelength is None:
        wavelength = infer_wavelength_from_filename(path_text)
    if wavelength is None:
        wavelength = ROLE_DEFAULT_WAVELENGTHS_NM.get(role, 850.0)
    wavelength = _validated_wavelength(wavelength, role_label)
    image = {
        "id": image_id,
        "path": path_text,
        "assignment": "grayscale",
        "role": role,
        "role_label": role_label,
        "wavelength_nm": wavelength,
    }
    band = {
        "id": f"{image_id}_gray",
        "source_image_id": image_id,
        "path": path_text,
        "assignment": "grayscale",
        "source_channel": "L",
        "role": role,
        "role_label": role_label,
        "wavelength_nm": wavelength,
    }
    if role == "CUSTOM":
        image["custom_role"] = role_label
        band["custom_role"] = role_label
    return image, [band]


def _alignment_spec(
    alignment_reference: str | Path | None,
    images: list[dict[str, Any]],
    *,
    alignment_mode: str,
    transform_model: str,
) -> dict[str, Any]:
    base = {
        "mode": str(alignment_mode),
        "transform_model": str(transform_model),
    }
    if alignment_reference is None or str(alignment_reference).strip() == "":
        return {**base, "reference_image_id": None, "reference_path": None, "reference": "first"}

    reference_text = str(alignment_reference)
    reference_path = _maybe_normalized_path(reference_text)
    for image in images:
        if reference_text == image["id"] or reference_text == image["path"]:
            return {**base, "reference_image_id": image["id"], "reference_path": image["path"], "reference": image["id"]}
        if reference_path is not None and reference_path == image["path"]:
            return {**base, "reference_image_id": image["id"], "reference_path": image["path"], "reference": image["id"]}

    raise ValueError(f"Alignment reference does not match an imported image: {alignment_reference}")


def _role_label(role: str, custom_role: str) -> str:
    if role != "CUSTOM":
        return role
    label = custom_role.strip()
    if not label:
        raise ValueError("Randurile cu rol personalizat au nevoie de o eticheta pentru rol.")
    return label


def _editable_role_from_spec(image: dict[str, Any]) -> tuple[str, str]:
    """Return a dialog role/custom-role pair from a grayscale image spec."""

    raw_role = str(image.get("role") or "").strip()
    normalized_role = raw_role.upper().replace(" ", "_").replace("-", "_")
    role_label = str(image.get("role_label") or image.get("custom_role") or raw_role or "CUSTOM").strip()
    custom_role = str(image.get("custom_role") or "").strip()

    if normalized_role in ROLE_OPTIONS:
        if normalized_role == "CUSTOM":
            return "CUSTOM", custom_role or role_label
        return normalized_role, ""
    return "CUSTOM", custom_role or role_label or raw_role


def _optional_float(value: Any) -> float | None:
    try:
        number = float(value)
    except (TypeError, ValueError):
        return None
    return number if math.isfinite(number) else None


def _validated_wavelength(wavelength_nm: float | None, role_label: str) -> float:
    if wavelength_nm is None:
        raise ValueError(f"Seteaza o lungime de unda pentru {role_label}.")
    wavelength = float(wavelength_nm)
    if not math.isfinite(wavelength) or wavelength <= 0.0:
        raise ValueError(f"Seteaza o lungime de unda pozitiva pentru {role_label}.")
    return wavelength


def _normalized_assignment(assignment: str | None) -> str:
    if assignment is None:
        return ASSIGNMENT_GRAYSCALE
    text = str(assignment).strip()
    text = _ASSIGNMENT_FROM_LABEL.get(text, text)
    normalized = text.upper().replace(" ", "_")
    if normalized in {"RGB_IMAGE", "RGB"}:
        return ASSIGNMENT_RGB
    if normalized in {"GRAYSCALE", "GRAYSCALE_BAND", "GREYSCALE", "GRAY", "GREY"}:
        return ASSIGNMENT_GRAYSCALE
    raise ValueError(f"Unsupported mixed import assignment: {assignment}")


def _normalized_role(role: str | None) -> str:
    if role is None:
        return "CUSTOM"
    normalized = str(role).strip().upper().replace(" ", "_").replace("-", "_")
    if normalized not in ROLE_OPTIONS:
        raise ValueError(f"Unsupported band role: {role}")
    return normalized


def _normalized_image_id(image_id: str, index: int) -> str:
    text = image_id.strip() if image_id else ""
    return text or f"image_{index:03d}"


def _normalized_path_text(path: str | Path) -> str:
    text = str(path).strip()
    if not text:
        raise ValueError("Image path cannot be empty.")
    raw_path = Path(text).expanduser()
    try:
        return str(raw_path.resolve(strict=False))
    except OSError:
        return str(raw_path)


def _maybe_normalized_path(path: str) -> str | None:
    try:
        return _normalized_path_text(path)
    except (OSError, ValueError):
        return None


def _json_output_path(output_path: str | Path) -> Path:
    path = Path(output_path).expanduser()
    if path.suffix.lower() != ".json":
        path = path.with_suffix(".json")
    try:
        return path.resolve(strict=False)
    except OSError:
        return path
