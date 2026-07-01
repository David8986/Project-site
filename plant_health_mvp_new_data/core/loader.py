"""Load and normalize multispectral and spectral sample data.

This module is the ingestion layer for the plant-health MVP. It reads source
files, extracts wavelength metadata, and returns a canonical
``SpectralSample`` that downstream code can consume without caring about the
original file format.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any, Sequence
import re
import tarfile

import numpy as np

try:  # pragma: no cover - import fallback for direct execution
    from .models.sample import SpectralSample
    from .filename_wavelength import infer_wavelength_from_filename
    from .mixed_import import load_mixed_image_bundle
except ImportError:  # pragma: no cover
    from models.sample import SpectralSample
    from filename_wavelength import infer_wavelength_from_filename
    from mixed_import import load_mixed_image_bundle


_NUMBER_PATTERN = re.compile(
    r"[-+]?(?:\d*\.\d+|\d+)(?:[eE][-+]?\d+)?"
)

_ENVI_DTYPE_MAP: dict[int, str] = {
    1: "u1",
    2: "i2",
    3: "i4",
    4: "f4",
    5: "f8",
    12: "u2",
    13: "u4",
    14: "i8",
    15: "u8",
}

_KNOWN_FILTER_WAVELENGTHS_NM = {532, 556, 680, 725, 850, 940}
_FILTER_TOKEN_PATTERN = re.compile(r"(?<!\d)(532|556|680|725|850|940)(?!\d)")


def _coerce_path(path: str | Path) -> Path:
    """Return ``path`` as a resolved :class:`Path` without touching the file."""

    return Path(path).expanduser()


def _extract_numeric_tokens(text: str) -> list[float]:
    """Extract numeric values from free-form text in file order."""

    return [float(match.group(0)) for match in _NUMBER_PATTERN.finditer(text)]


def _numeric_rows_from_text(text: str) -> list[list[float]]:
    """Parse numeric cells from a delimited text file row by row."""

    rows: list[list[float]] = []
    for line in text.splitlines():
        stripped = line.strip()
        if not stripped:
            continue

        values: list[float] = []
        for cell in re.split(r"[,\s;]+", stripped):
            if not cell:
                continue
            try:
                values.append(float(cell))
            except ValueError:
                continue
        if values:
            rows.append(values)
    return rows


def _is_index_like(values: np.ndarray) -> bool:
    """Return ``True`` when a column looks like a row index."""

    if values.size < 3:
        return False
    finite_values = values[np.isfinite(values)]
    if finite_values.size != values.size:
        return False
    if not np.allclose(finite_values, np.round(finite_values), atol=1e-6):
        return False
    diffs = np.diff(finite_values)
    return bool(np.allclose(diffs, 1.0, atol=1e-6))


def _extract_wavelength_column(text: str) -> np.ndarray | None:
    """Extract the wavelength column from a multi-column CSV when detectable."""

    rows = _numeric_rows_from_text(text)
    if len(rows) < 2:
        return None

    width = min(len(row) for row in rows)
    if width <= 1:
        return None
    if any(len(row) != width for row in rows):
        return None

    matrix = np.asarray(rows, dtype=float)
    candidate_scores: list[tuple[int, float, int]] = []

    for column_index in range(width):
        column = matrix[:, column_index]
        finite_column = column[np.isfinite(column)]
        if finite_column.size < 2:
            continue

        median = float(np.median(finite_column))
        minimum = float(np.min(finite_column))
        maximum = float(np.max(finite_column))
        wavelength_like = minimum >= 100.0 and maximum <= 2500.0 and median >= 250.0
        index_like = _is_index_like(finite_column)
        score = 0
        if wavelength_like:
            score += 4
        if np.all(np.diff(finite_column) >= 0):
            score += 2
        if not index_like:
            score += 2
        if maximum > 300.0:
            score += 1

        candidate_scores.append((score, median, column_index))

    if not candidate_scores:
        return None

    _, _, chosen_index = max(candidate_scores, key=lambda item: (item[0], item[1], item[2]))
    chosen = matrix[:, chosen_index]
    return np.asarray(chosen[np.isfinite(chosen)], dtype=float)


def _looks_like_wavelength_header(values: Sequence[float]) -> bool:
    """Heuristically determine whether a numeric row is a wavelength header."""

    if len(values) < 2:
        return False

    arr = np.asarray(values, dtype=float)
    if not np.all(np.diff(arr) > 0):
        return False

    return float(np.median(arr)) >= 100.0


def _parse_numeric_table(text: str) -> tuple[np.ndarray, np.ndarray | None, list[str]]:
    """Parse a CSV/TXT spectral table.

    The returned matrix is always numeric. If a wavelength header is detected,
    it is returned separately as the second item in the tuple.
    """

    rows: list[list[float]] = []
    raw_rows: list[list[str]] = []

    for line in text.splitlines():
        stripped = line.strip()
        if not stripped:
            continue
        cells = [cell.strip() for cell in re.split(r"[,\s;]+", stripped) if cell.strip()]
        raw_rows.append(cells)

        numeric_cells: list[float] = []
        for cell in cells:
            try:
                numeric_cells.append(float(cell))
            except ValueError:
                continue
        if numeric_cells:
            rows.append(numeric_cells)

    if not rows:
        return np.empty((0, 0), dtype=float), None, []

    header: np.ndarray | None = None
    notes: list[str] = []

    first_row = raw_rows[0]
    first_numeric = rows[0]

    if len(first_row) != len(first_numeric):
        notes.append("Detected a non-numeric header row; using extracted numeric wavelength values.")
        header = np.asarray(first_numeric, dtype=float)
        rows = rows[1:]
    elif len(rows) > 1 and _looks_like_wavelength_header(first_numeric):
        notes.append("Detected a numeric wavelength header row.")
        header = np.asarray(first_numeric, dtype=float)
        rows = rows[1:]

    if not rows:
        return np.empty((0, 0), dtype=float), header, notes

    width = min(len(row) for row in rows)
    if width == 0:
        return np.empty((0, 0), dtype=float), header, notes

    matrix = np.asarray([row[:width] for row in rows], dtype=float)
    return matrix, header, notes


def _parse_envi_header(text: str) -> dict[str, Any]:
    """Parse the small ENVI header subset needed for this MVP."""

    header: dict[str, Any] = {}
    lines = text.replace("\r\n", "\n").splitlines()
    index = 0
    while index < len(lines):
        line = lines[index].strip()
        index += 1
        if not line or line.upper() == "ENVI" or "=" not in line:
            continue

        key, value = line.split("=", 1)
        key = key.strip().lower()
        value = value.strip()
        if value.startswith("{") and not value.endswith("}"):
            parts = [value]
            while index < len(lines):
                parts.append(lines[index].strip())
                if lines[index].strip().endswith("}"):
                    index += 1
                    break
                index += 1
            value = "\n".join(parts)

        if value.startswith("{") and value.endswith("}"):
            body = value[1:-1]
            numbers = _extract_numeric_tokens(body)
            header[key] = numbers if numbers else body.strip()
            continue

        number_match = _NUMBER_PATTERN.fullmatch(value)
        if number_match:
            numeric = float(value)
            header[key] = int(numeric) if numeric.is_integer() else numeric
        else:
            header[key] = value

    return header


def _envi_dtype(data_type: int, byte_order: int) -> np.dtype:
    """Return the NumPy dtype for an ENVI data type and byte order."""

    dtype_code = _ENVI_DTYPE_MAP.get(int(data_type))
    if dtype_code is None:
        raise ValueError(f"Unsupported ENVI data type: {data_type}")

    endian = "<" if int(byte_order) == 0 else ">"
    dtype = np.dtype(dtype_code)
    if dtype.itemsize == 1:
        return dtype
    return np.dtype(endian + dtype_code)


def _cube_from_envi_bytes(raw_bytes: bytes, header: dict[str, Any]) -> np.ndarray:
    """Decode ENVI raw bytes into a canonical ``(lines, samples, bands)`` cube."""

    samples = int(header["samples"])
    lines = int(header["lines"])
    bands = int(header["bands"])
    interleave = str(header.get("interleave", "")).strip().lower()
    header_offset = int(header.get("header offset", 0))
    dtype = _envi_dtype(int(header["data type"]), int(header.get("byte order", 0)))

    payload = memoryview(raw_bytes)[header_offset:]
    expected_values = samples * lines * bands
    values = np.frombuffer(payload, dtype=dtype, count=expected_values)
    if values.size != expected_values:
        raise ValueError(
            f"ENVI raw size mismatch: expected {expected_values} values, got {values.size}."
        )

    if interleave == "bil":
        return values.reshape((lines, bands, samples)).transpose(0, 2, 1).copy()
    if interleave == "bsq":
        return values.reshape((bands, lines, samples)).transpose(1, 2, 0).copy()
    if interleave == "bip":
        return values.reshape((lines, samples, bands)).copy()

    raise ValueError(f"Unsupported ENVI interleave: {interleave!r}")


def _find_archive_sample_members(
    archive: tarfile.TarFile,
    sample_name: str | None,
) -> tuple[str, str, str, list[str]]:
    """Find the selected sample's main raw/header members inside an archive."""

    member_names = [
        member.name
        for member in archive.getmembers()
        if member.isfile() and "/capture/" in member.name and "/._" not in member.name
    ]

    raw_names = [
        name
        for name in member_names
        if name.lower().endswith(".raw")
        and "/whiteref_" not in name.lower()
        and "/darkref_" not in name.lower()
    ]
    if sample_name:
        raw_names = [name for name in raw_names if sample_name in name]
    raw_names.sort()
    if not raw_names:
        raise FileNotFoundError("No main sample .raw file was found in the archive.")

    raw_name = raw_names[0]
    hdr_name = raw_name[:-4] + ".hdr"
    if hdr_name not in member_names:
        raise FileNotFoundError(f"Header file was not found for archive member: {raw_name}")

    sample_root = raw_name.split("/capture/", 1)[0]
    available_samples = sorted({name.split("/capture/", 1)[0] for name in member_names if name.endswith(".raw")})
    return sample_root, raw_name, hdr_name, available_samples


def _read_archive_member_text(archive: tarfile.TarFile, member_name: str) -> str:
    """Read a text member from a tar archive."""

    extracted = archive.extractfile(member_name)
    if extracted is None:
        raise FileNotFoundError(f"Archive member could not be read: {member_name}")
    return extracted.read().decode("utf-8", errors="ignore")


def _read_archive_member_bytes(archive: tarfile.TarFile, member_name: str) -> bytes:
    """Read a binary member from a tar archive."""

    extracted = archive.extractfile(member_name)
    if extracted is None:
        raise FileNotFoundError(f"Archive member could not be read: {member_name}")
    return extracted.read()


def _find_directory_sample_files(path: Path) -> tuple[Path, Path]:
    """Find the main ENVI raw/header pair inside an extracted sample directory."""

    capture_dir = path / "capture"
    search_root = capture_dir if capture_dir.exists() else path
    raw_files = [
        candidate
        for candidate in search_root.glob("*.raw")
        if not candidate.name.startswith("._")
        and not candidate.name.upper().startswith("WHITEREF_")
        and not candidate.name.upper().startswith("DARKREF_")
    ]
    raw_files.sort(key=lambda candidate: candidate.name.lower())
    if not raw_files:
        raise FileNotFoundError(f"No main ENVI .raw file found in extracted sample directory: {path}")

    raw_path = raw_files[0]
    hdr_path = raw_path.with_suffix(".hdr")
    if not hdr_path.exists():
        raise FileNotFoundError(f"Header file was not found for extracted raw file: {raw_path}")
    return raw_path, hdr_path


def load_wavelength_csv(path: str | Path) -> np.ndarray:
    """Load wavelength values from a CSV or plain-text file.

    The parser is intentionally forgiving: it accepts comma, semicolon, or
    newline separated content, ignores non-numeric tokens, detects common
    two-column ``index,wavelength`` files, preserves file order, and returns an
    empty float array for empty files.
    """

    csv_path = _coerce_path(path)
    if not csv_path.exists():
        raise FileNotFoundError(f"Wavelength CSV not found: {csv_path}")

    text = csv_path.read_text(encoding="utf-8", errors="ignore")
    if not text.strip():
        return np.array([], dtype=float)

    wavelength_column = _extract_wavelength_column(text)
    if wavelength_column is not None:
        return wavelength_column

    values = _extract_numeric_tokens(text)
    return np.asarray(values, dtype=float)


def _make_metadata(
    *,
    input_path: str | Path | None,
    dimensions: dict[str, Any],
    mock_flag: bool,
    loader_notes: Sequence[str],
    extra: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Build the standard metadata payload for a loaded sample."""

    metadata: dict[str, Any] = {
        "input_path": None if input_path is None else str(_coerce_path(input_path)),
        "dimensions": dimensions,
        "mock_flag": bool(mock_flag),
        "loader_notes": list(loader_notes),
    }
    if extra:
        metadata.update(extra)
    return metadata


def _load_wavelengths_for_band_count(
    band_count: int,
    wavelength_csv: str | Path | None,
    notes: list[str],
) -> np.ndarray:
    """Resolve wavelengths for a band axis, falling back when necessary."""

    if wavelength_csv is not None:
        wavelengths = load_wavelength_csv(wavelength_csv)
        if wavelengths.size:
            if wavelengths.size != band_count:
                notes.append(
                    "Wavelength CSV length did not match band count; "
                    "falling back to index-based wavelengths."
                )
            else:
                return wavelengths.astype(float, copy=False)

    notes.append("No usable wavelength source was available; using band indices as fallback.")
    return np.arange(band_count, dtype=float)


def _load_npz_sample(
    path: Path,
    wavelength_csv: str | Path | None,
) -> SpectralSample:
    """Load a sample from an NPZ archive."""

    notes: list[str] = [f"Loaded NPZ archive: {path.name}"]
    with np.load(path, allow_pickle=True) as archive:
        data_key = "cube" if "cube" in archive.files else "data" if "data" in archive.files else None
        if data_key is None:
            raise KeyError("NPZ archive must contain a 'cube' or 'data' array.")

        data = np.asarray(archive[data_key])

        wavelength_key = (
            "wavelengths"
            if "wavelengths" in archive.files
            else "available_wavelengths"
            if "available_wavelengths" in archive.files
            else None
        )
        if wavelength_key is not None:
            wavelengths = np.asarray(archive[wavelength_key], dtype=float)
            notes.append(f"Using wavelengths from NPZ key '{wavelength_key}'.")
        else:
            band_count = data.shape[-1] if data.ndim >= 2 else int(data.size)
            wavelengths = _load_wavelengths_for_band_count(band_count, wavelength_csv, notes)

    source_type = "hyperspectral_cube" if data.ndim >= 3 else "spectral_table"
    dimensions = {
        "shape": list(data.shape),
        "bands": int(data.shape[-1]) if data.ndim >= 2 else int(data.size),
    }

    return SpectralSample(
        source_type=source_type,
        available_wavelengths=np.asarray(wavelengths, dtype=float),
        data=data,
        metadata=_make_metadata(
            input_path=path,
            dimensions=dimensions,
            mock_flag=False,
            loader_notes=notes,
        ),
    )


def _load_npy_sample(
    path: Path,
    wavelength_csv: str | Path | None,
) -> SpectralSample:
    """Load a sample from an NPY file."""

    notes: list[str] = [f"Loaded NPY array: {path.name}"]
    data = np.asarray(np.load(path, allow_pickle=True))
    band_count = data.shape[-1] if data.ndim >= 2 else int(data.size)
    wavelengths = _load_wavelengths_for_band_count(band_count, wavelength_csv, notes)
    source_type = "hyperspectral_cube" if data.ndim >= 3 else "spectral_table"

    dimensions = {
        "shape": list(data.shape),
        "bands": band_count,
    }

    return SpectralSample(
        source_type=source_type,
        available_wavelengths=np.asarray(wavelengths, dtype=float),
        data=data,
        metadata=_make_metadata(
            input_path=path,
            dimensions=dimensions,
            mock_flag=False,
            loader_notes=notes,
        ),
    )


def _infer_known_filter_wavelength(path: Path) -> float | None:
    """Return a calibrated filter wavelength encoded in a camera filename."""

    match = _FILTER_TOKEN_PATTERN.search(path.stem)
    if not match:
        return None
    inferred = infer_wavelength_from_filename(path)
    if inferred is None:
        return float(match.group(1))
    rounded = int(round(float(inferred)))
    if rounded in _KNOWN_FILTER_WAVELENGTHS_NM:
        return float(rounded)
    return float(match.group(1))


def _load_rgb_image_sample(path: Path) -> SpectralSample:
    """Load a normal RGB image as a three-band, RGB-only sample.

    The channel-to-wavelength labels are approximate display-channel labels:
    red -> 650 nm, green -> 556 nm, blue -> 532 nm. They are not calibrated
    narrowband spectral measurements.
    """

    try:
        from PIL import Image
    except ImportError as exc:  # pragma: no cover - requirements include Pillow
        raise ImportError("Pillow is required to load RGB image files.") from exc

    notes = [
        f"Loaded RGB image: {path.name}",
        "RGB channels were labeled as approximate 650/556/532 nm display bands.",
        "This is RGB-only data: NIR, red-edge, and water-sensitive bands are unavailable.",
    ]
    with Image.open(path) as image:
        rgb = image.convert("RGB")
        data = np.asarray(rgb, dtype=np.float32) / 255.0

    filter_wavelength = _infer_known_filter_wavelength(path)
    if filter_wavelength is not None:
        value_band = np.max(data, axis=2).astype(np.float32, copy=False)
        filtered_data = value_band[:, :, np.newaxis]
        wavelength_key = int(round(filter_wavelength))
        filtered_notes = [
            f"Loaded filtered camera image: {path.name}",
            f"Detected {wavelength_key} nm filter label from the filename.",
            "Pixel values use HSV value / max-channel intensity to match the real calibration analysis.",
            "Reference correction is applied in the report after the vegetation average is computed.",
        ]
        dimensions = {
            "shape": list(filtered_data.shape),
            "height": int(filtered_data.shape[0]),
            "width": int(filtered_data.shape[1]),
            "bands": 1,
            "filter_wavelength_nm": float(wavelength_key),
            "source_rgb_shape": list(data.shape),
        }

        return SpectralSample(
            source_type="filtered_camera_image",
            available_wavelengths=np.asarray([float(wavelength_key)], dtype=float),
            data=filtered_data,
            metadata=_make_metadata(
                input_path=path,
                dimensions=dimensions,
                mock_flag=False,
                loader_notes=filtered_notes,
                extra={
                    "sample_id": path.stem,
                    "source_data_kind": "filtered_camera_image",
                    "analysis_data_kind": "raw_filtered_camera_value_intensity",
                    "adapter_used": "filtered_camera_image_loader",
                    "rgb_only": False,
                    "is_reflectance": False,
                    "calibration_applied": False,
                    "camera_calibration_eligible": True,
                    "camera_filter_wavelength_nm": float(wavelength_key),
                    "camera_value_channel": "max(R,G,B)",
                    "camera_calibration_profile_id": "spectraleaf_camera_calibration_2026_05",
                    "spectral_limitations": (
                        "This single JPG contains one filtered camera band. It can be reference-corrected, "
                        "but vegetation indices that need other bands require matching filter photos."
                    ),
                },
            ),
        )

    wavelengths = np.asarray([650.0, 556.0, 532.0], dtype=float)
    dimensions = {
        "shape": list(data.shape),
        "height": int(data.shape[0]),
        "width": int(data.shape[1]),
        "bands": 3,
        "channel_order": ["R", "G", "B"],
    }

    return SpectralSample(
        source_type="rgb_image",
        available_wavelengths=wavelengths,
        data=data,
        metadata=_make_metadata(
            input_path=path,
            dimensions=dimensions,
            mock_flag=False,
            loader_notes=notes,
            extra={
                "sample_id": path.stem,
                "source_data_kind": "rgb_image_data",
                "analysis_data_kind": "rgb_intensity",
                "adapter_used": "rgb_image_loader",
                "rgb_only": True,
                "is_reflectance": False,
                "calibration_applied": False,
                "channel_wavelength_labels_nm": {"R": 650.0, "G": 556.0, "B": 532.0},
                "spectral_limitations": (
                    "RGB images do not contain true NIR, red-edge, or 940 nm water-band data. "
                    "NDVI/NDRE/water indices cannot be computed from this input."
                ),
            },
        ),
    )


def _load_table_sample(
    path: Path,
    wavelength_csv: str | Path | None,
) -> SpectralSample:
    """Load a spectral table from CSV or TXT."""

    notes: list[str] = [f"Loaded spectral table: {path.name}"]
    text = path.read_text(encoding="utf-8", errors="ignore")
    matrix, header, parse_notes = _parse_numeric_table(text)
    notes.extend(parse_notes)

    if matrix.size == 0:
        raise ValueError(f"No numeric spectral data could be parsed from {path}")

    wavelengths: np.ndarray
    if header is not None and header.size:
        wavelengths = np.asarray(header, dtype=float)
    else:
        wavelengths = _load_wavelengths_for_band_count(matrix.shape[1], wavelength_csv, notes)

    if wavelengths.size != matrix.shape[1]:
        notes.append(
            "Resolved wavelength count did not match the parsed table width; "
            "falling back to index-based wavelengths."
        )
        wavelengths = np.arange(matrix.shape[1], dtype=float)

    dimensions = {
        "shape": list(matrix.shape),
        "samples": int(matrix.shape[0]),
        "bands": int(matrix.shape[1]),
    }

    return SpectralSample(
        source_type="spectral_table",
        available_wavelengths=np.asarray(wavelengths, dtype=float),
        data=matrix,
        metadata=_make_metadata(
            input_path=path,
            dimensions=dimensions,
            mock_flag=False,
            loader_notes=notes,
        ),
    )


def _load_envi_tar_sample(
    path: Path,
    wavelength_csv: str | Path | None,
    sample_name: str | None = None,
) -> SpectralSample:
    """Load the first matching Specim/ENVI hyperspectral sample from a tar archive."""

    notes: list[str] = [f"Loaded ENVI sample from archive: {path.name}"]
    with tarfile.open(path, mode="r:*") as archive:
        sample_root, raw_name, hdr_name, available_samples = _find_archive_sample_members(
            archive,
            sample_name,
        )
        header_text = _read_archive_member_text(archive, hdr_name)
        header = _parse_envi_header(header_text)
        raw_bytes = _read_archive_member_bytes(archive, raw_name)

    cube = _cube_from_envi_bytes(raw_bytes, header)
    header_wavelengths = np.asarray(header.get("wavelength", []), dtype=float)
    wavelengths = header_wavelengths
    if wavelength_csv is not None:
        csv_wavelengths = load_wavelength_csv(wavelength_csv)
        if csv_wavelengths.size == cube.shape[-1]:
            wavelengths = csv_wavelengths
            notes.append("Using wavelengths from supplied CSV lookup table.")
        else:
            notes.append("Supplied wavelength CSV did not match band count; using wavelengths from ENVI header.")

    if wavelengths.size != cube.shape[-1]:
        wavelengths = np.arange(cube.shape[-1], dtype=float)
        notes.append("No usable wavelength list matched the cube band count; using band indices.")

    dimensions = {
        "shape": list(cube.shape),
        "height": int(cube.shape[0]),
        "width": int(cube.shape[1]),
        "bands": int(cube.shape[2]),
        "envi_samples": int(header.get("samples", cube.shape[1])),
        "envi_lines": int(header.get("lines", cube.shape[0])),
        "envi_interleave": str(header.get("interleave", "")),
        "envi_data_type": int(header.get("data type", -1)),
    }

    return SpectralSample(
        source_type="hyperspectral_cube",
        available_wavelengths=np.asarray(wavelengths, dtype=float),
        data=cube,
        metadata=_make_metadata(
            input_path=path,
            dimensions=dimensions,
            mock_flag=False,
            loader_notes=notes,
            extra={
                "source_data_kind": "real_dataset_data",
                "archive_member_sample": sample_root,
                "archive_raw_member": raw_name,
                "archive_hdr_member": hdr_name,
                "available_archive_samples": available_samples,
                "selected_sample_note": "First matching main sample raw file in archive unless --archive-sample is supplied.",
                "sensor_type": header.get("sensor type"),
            },
        ),
    )


def _load_envi_directory_sample(
    path: Path,
    wavelength_csv: str | Path | None,
) -> SpectralSample:
    """Load a Specim/ENVI sample from an extracted sample directory."""

    notes: list[str] = [f"Loaded ENVI sample from extracted directory: {path.name}"]
    raw_path, hdr_path = _find_directory_sample_files(path)
    header_text = hdr_path.read_text(encoding="utf-8", errors="ignore")
    header = _parse_envi_header(header_text)
    raw_bytes = raw_path.read_bytes()
    cube = _cube_from_envi_bytes(raw_bytes, header)

    header_wavelengths = np.asarray(header.get("wavelength", []), dtype=float)
    wavelengths = header_wavelengths
    if wavelength_csv is not None:
        csv_wavelengths = load_wavelength_csv(wavelength_csv)
        if csv_wavelengths.size == cube.shape[-1]:
            wavelengths = csv_wavelengths
            notes.append("Using wavelengths from supplied CSV lookup table.")
        else:
            notes.append("Supplied wavelength CSV did not match band count; using wavelengths from ENVI header.")

    if wavelengths.size != cube.shape[-1]:
        wavelengths = np.arange(cube.shape[-1], dtype=float)
        notes.append("No usable wavelength list matched the cube band count; using band indices.")

    dimensions = {
        "shape": list(cube.shape),
        "height": int(cube.shape[0]),
        "width": int(cube.shape[1]),
        "bands": int(cube.shape[2]),
        "envi_samples": int(header.get("samples", cube.shape[1])),
        "envi_lines": int(header.get("lines", cube.shape[0])),
        "envi_interleave": str(header.get("interleave", "")),
        "envi_data_type": int(header.get("data type", -1)),
    }

    return SpectralSample(
        source_type="hyperspectral_cube",
        available_wavelengths=np.asarray(wavelengths, dtype=float),
        data=cube,
        metadata=_make_metadata(
            input_path=path,
            dimensions=dimensions,
            mock_flag=False,
            loader_notes=notes,
            extra={
                "source_data_kind": "real_dataset_data",
                "extracted_sample_directory": str(path),
                "raw_file": str(raw_path),
                "hdr_file": str(hdr_path),
                "archive_member_sample": path.name,
                "selected_sample_note": "Loaded directly from an extracted ENVI sample directory.",
                "sensor_type": header.get("sensor type"),
            },
        ),
    )


def create_mock_sample(
    size: tuple[int, int] = (96, 96),
    wavelengths: Sequence[float] | None = None,
) -> SpectralSample:
    """Create a deterministic synthetic hyperspectral sample.

    The mock scene uses a soil background and a leaf-like elliptical vegetation
    region so that downstream masking and spectrum logic can be exercised
    without real hardware.
    """

    if wavelengths is None:
        wavelengths = (500.0, 532.0, 555.0, 650.0, 681.0, 724.0, 850.0, 905.0)

    wavelength_array = np.asarray(list(wavelengths), dtype=float)
    height, width = size
    yy, xx = np.mgrid[0:height, 0:width]

    # Elliptical vegetation region with deterministic placement and shape.
    cx = width * 0.55
    cy = height * 0.50
    rx = width * 0.25
    ry = height * 0.18
    vegetation_mask = ((xx - cx) / rx) ** 2 + ((yy - cy) / ry) ** 2 <= 1.0

    # Spatially varying but deterministic background for visual debugging.
    soil_base = 0.18 + 0.00055 * (xx / max(width - 1, 1)) + 0.00035 * (yy / max(height - 1, 1))
    veg_base = 0.04 + 0.00015 * (xx / max(width - 1, 1))

    band_values: list[np.ndarray] = []
    for wavelength in wavelength_array:
        if wavelength < 600.0:
            veg_reflectance = 0.08 + 0.00006 * (wavelength - 500.0)
            soil_reflectance = soil_base + 0.00003 * (wavelength - 500.0)
        elif wavelength < 700.0:
            veg_reflectance = 0.05 + 0.0004 * (wavelength - 600.0)
            soil_reflectance = soil_base + 0.000035 * (wavelength - 500.0)
        elif wavelength < 760.0:
            veg_reflectance = 0.22 + 0.0022 * (wavelength - 700.0)
            soil_reflectance = soil_base + 0.00004 * (wavelength - 500.0)
        else:
            veg_reflectance = 0.50 + 0.00004 * (wavelength - 760.0)
            soil_reflectance = soil_base + 0.000045 * (wavelength - 500.0)

        veg_plane = veg_base + veg_reflectance
        soil_plane = soil_reflectance
        band = np.where(vegetation_mask, veg_plane, soil_plane)
        band += 0.004 * np.sin((xx + wavelength / 11.0) / 13.0)
        band += 0.003 * np.cos((yy + wavelength / 17.0) / 15.0)
        band_values.append(band.astype(np.float32))

    cube = np.stack(band_values, axis=-1)
    dimensions = {
        "shape": list(cube.shape),
        "height": int(height),
        "width": int(width),
        "bands": int(cube.shape[-1]),
    }

    return SpectralSample(
        source_type="hyperspectral_cube",
        available_wavelengths=wavelength_array,
        data=cube,
        metadata=_make_metadata(
            input_path=None,
            dimensions=dimensions,
            mock_flag=True,
            loader_notes=[
                "Created deterministic mock hyperspectral cube.",
                "Contains soil background and a leaf-like elliptical vegetation region.",
            ],
        ),
    )


def save_mock_dataset(output_dir: str | Path) -> tuple[Path, Path]:
    """Persist a deterministic mock dataset and its wavelength CSV."""

    out_dir = _coerce_path(output_dir)
    out_dir.mkdir(parents=True, exist_ok=True)

    sample = create_mock_sample()
    npz_path = out_dir / "mock_sample.npz"
    csv_path = out_dir / "wavelengths.csv"

    np.savez_compressed(
        npz_path,
        cube=sample.data,
        wavelengths=sample.available_wavelengths,
    )
    np.savetxt(csv_path, sample.available_wavelengths.reshape(-1, 1), fmt="%.6f", delimiter=",")

    return npz_path, csv_path


def load_sample(
    input_path: str | Path | None,
    wavelength_csv: str | Path | None = None,
    archive_sample: str | None = None,
) -> SpectralSample:
    """Load a source sample or create a deterministic mock sample.

    Parameters
    ----------
    input_path:
        Path to an ``.npz``, ``.npy``, mixed-import ``.json`` spec, RGB image,
        ``.csv``, ``.txt``, or ``.tar.gz`` input file. When ``None``, a
        synthetic mock sample is generated in memory.
    wavelength_csv:
        Optional wavelength list used when the source file does not contain a
        usable wavelength axis.
    """

    if input_path is None:
        return create_mock_sample()

    path = _coerce_path(input_path)
    if not path.exists():
        raise FileNotFoundError(f"Input file not found: {path}")

    if path.is_dir():
        return _load_envi_directory_sample(path, wavelength_csv)

    if path.name.lower().endswith((".tar.gz", ".tgz", ".tar")):
        return _load_envi_tar_sample(path, wavelength_csv, sample_name=archive_sample)

    suffix = path.suffix.lower()
    if suffix == ".npz":
        return _load_npz_sample(path, wavelength_csv)
    if suffix == ".npy":
        return _load_npy_sample(path, wavelength_csv)
    if suffix == ".json":
        return load_mixed_image_bundle(path)
    if suffix in {".jpg", ".jpeg", ".png", ".tif", ".tiff", ".bmp"}:
        return _load_rgb_image_sample(path)
    if suffix in {".csv", ".txt"}:
        return _load_table_sample(path, wavelength_csv)

    raise ValueError(f"Unsupported input format: {path.suffix}")
