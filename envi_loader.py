"""ENVI loading utilities built on Spectral Python."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any

import numpy as np


JUNK_PREFIX = "._"


class EnviLoadError(RuntimeError):
    """Raised when an ENVI header/data pair cannot be opened."""


@dataclass(frozen=True)
class EnviCubeMetadata:
    """Small metadata summary for the desktop viewer."""

    width: int
    height: int
    bands: int
    interleave: str | None
    dtype: str | None


@dataclass
class EnviCube:
    """Thin wrapper around a Spectral Python image object."""

    hdr_path: Path
    raw_path: Path | None
    image: Any
    metadata: dict[str, Any]
    summary: EnviCubeMetadata

    @property
    def shape(self) -> tuple[int, int, int]:
        """Return cube shape as ``(height, width, bands)``."""

        return (self.summary.height, self.summary.width, self.summary.bands)

    def read_band(self, band_index: int) -> np.ndarray:
        """Read one band as a 2D ``float32`` array."""

        self._validate_band_index(band_index)
        try:
            band = self.image.read_band(band_index)
        except AttributeError as exc:
            raise EnviLoadError("This Spectral Python image object cannot read bands.") from exc
        return np.asarray(band, dtype=np.float32)

    def read_pixel_spectrum(self, row: int, col: int) -> np.ndarray:
        """Read one pixel spectrum across all bands."""

        self._validate_pixel(row, col)
        try:
            spectrum = self.image.read_pixel(row, col)
        except AttributeError:
            cube = self._load_full_cube()
            spectrum = cube[row, col, :]
        return np.asarray(spectrum, dtype=np.float32).reshape(-1)

    def read_region(self, row_start: int, row_stop: int, col_start: int, col_stop: int) -> np.ndarray:
        """Read a rectangular region as ``(rows, cols, bands)``.

        ``row_stop`` and ``col_stop`` follow Python slicing semantics and are
        exclusive.
        """

        row_start, row_stop, col_start, col_stop = self._normalize_region(
            row_start, row_stop, col_start, col_stop
        )
        try:
            region = self.image.read_subregion((row_start, row_stop), (col_start, col_stop))
        except AttributeError:
            cube = self._load_full_cube()
            region = cube[row_start:row_stop, col_start:col_stop, :]
        return np.asarray(region, dtype=np.float32)

    def read_roi_mean_spectrum(
        self, row_start: int, row_stop: int, col_start: int, col_stop: int
    ) -> np.ndarray:
        """Return the mean spectrum over a rectangular ROI."""

        region = self.read_region(row_start, row_stop, col_start, col_stop)
        if region.size == 0:
            raise ValueError("The selected ROI is empty.")
        return np.nanmean(region, axis=(0, 1)).astype(np.float32)

    def _load_full_cube(self) -> np.ndarray:
        """Load the entire cube as a fallback for uncommon SpyFile objects."""

        try:
            return np.asarray(self.image.load(), dtype=np.float32)
        except Exception as exc:  # pragma: no cover - depends on external file.
            raise EnviLoadError(f"Unable to load ENVI data array: {exc}") from exc

    def _validate_band_index(self, band_index: int) -> None:
        if band_index < 0 or band_index >= self.summary.bands:
            raise IndexError(f"Band index {band_index} is outside 0..{self.summary.bands - 1}.")

    def _validate_pixel(self, row: int, col: int) -> None:
        if row < 0 or row >= self.summary.height or col < 0 or col >= self.summary.width:
            raise IndexError(
                f"Pixel ({col}, {row}) is outside image bounds "
                f"{self.summary.width}x{self.summary.height}."
            )

    def _normalize_region(
        self, row_start: int, row_stop: int, col_start: int, col_stop: int
    ) -> tuple[int, int, int, int]:
        row_start = max(0, min(self.summary.height, row_start))
        row_stop = max(0, min(self.summary.height, row_stop))
        col_start = max(0, min(self.summary.width, col_start))
        col_stop = max(0, min(self.summary.width, col_stop))

        if row_start > row_stop:
            row_start, row_stop = row_stop, row_start
        if col_start > col_stop:
            col_start, col_stop = col_stop, col_start
        if row_start == row_stop or col_start == col_stop:
            raise ValueError("The selected ROI is empty.")
        return row_start, row_stop, col_start, col_stop


def is_junk_file(path: str | Path) -> bool:
    """Return ``True`` for macOS AppleDouble artifact files such as ``._x.hdr``."""

    return Path(path).name.startswith(JUNK_PREFIX)


def find_matching_raw(hdr_path: str | Path) -> Path | None:
    """Find the raw data file that belongs to an ENVI header.

    The same-stem ``.raw`` file is preferred. If it does not exist, the function
    also checks ``data file`` metadata in the header and then common ENVI data
    extensions with the same stem. Files starting with ``._`` are ignored.
    """

    hdr = Path(hdr_path).expanduser()
    if is_junk_file(hdr):
        return None

    candidates: list[Path] = []
    candidates.extend(hdr.with_suffix(ext) for ext in (".raw", ".RAW", ".img", ".IMG", ".dat", ".DAT"))

    data_file = _read_header_data_file(hdr)
    if data_file:
        candidates.insert(0, hdr.parent / data_file)

    for candidate in candidates:
        if candidate.exists() and not is_junk_file(candidate):
            return candidate
    return None


def open_envi_cube(hdr_path: str | Path) -> EnviCube:
    """Open an ENVI dataset through its ``.hdr`` file using Spectral Python."""

    hdr = Path(hdr_path).expanduser()
    if is_junk_file(hdr):
        raise EnviLoadError(f"Ignoring junk macOS artifact file: {hdr.name}")
    if hdr.suffix.lower() != ".hdr":
        raise EnviLoadError(f"Expected an ENVI .hdr file, got: {hdr}")
    if not hdr.exists():
        raise EnviLoadError(f"Header file does not exist: {hdr}")

    raw = find_matching_raw(hdr)

    try:
        from spectral.io import envi
    except ImportError as exc:  # pragma: no cover - depends on local env.
        raise EnviLoadError(
            "Spectral Python is not installed. Install it with: pip install spectral"
        ) from exc

    try:
        image = envi.open(str(hdr), str(raw) if raw else None)
    except Exception as first_exc:
        if raw is not None:
            try:
                image = envi.open(str(hdr))
            except Exception as second_exc:  # pragma: no cover - external file behavior.
                raise EnviLoadError(
                    f"Failed to open ENVI header/data pair:\n{hdr}\n{raw}\n\n"
                    f"With explicit raw file: {first_exc}\nWithout explicit raw file: {second_exc}"
                ) from second_exc
        else:
            raise EnviLoadError(
                f"Failed to open ENVI header. No matching raw file was found for:\n{hdr}\n\n{first_exc}"
            ) from first_exc

    metadata = dict(getattr(image, "metadata", {}) or {})
    summary = _extract_summary(image, metadata)
    return EnviCube(hdr_path=hdr, raw_path=raw, image=image, metadata=metadata, summary=summary)


def _extract_summary(image: Any, metadata: dict[str, Any]) -> EnviCubeMetadata:
    """Build a normalized metadata summary from a Spectral Python image."""

    shape = getattr(image, "shape", None)
    height = _int_from_any(getattr(image, "nrows", None), metadata.get("lines"))
    width = _int_from_any(getattr(image, "ncols", None), metadata.get("samples"))
    bands = _int_from_any(getattr(image, "nbands", None), metadata.get("bands"))

    if shape is not None and len(shape) >= 3:
        height = height or int(shape[0])
        width = width or int(shape[1])
        bands = bands or int(shape[2])

    if not height or not width or not bands:
        raise EnviLoadError("Could not determine ENVI cube dimensions from the header.")

    interleave = getattr(image, "interleave", None) or metadata.get("interleave")
    dtype = getattr(image, "dtype", None) or metadata.get("data type")
    dtype_text = str(dtype) if dtype is not None else None

    return EnviCubeMetadata(
        width=int(width),
        height=int(height),
        bands=int(bands),
        interleave=str(interleave) if interleave is not None else None,
        dtype=dtype_text,
    )


def _int_from_any(*values: Any) -> int | None:
    for value in values:
        if value is None:
            continue
        try:
            return int(value)
        except (TypeError, ValueError):
            continue
    return None


def _read_header_data_file(hdr_path: Path) -> str | None:
    """Read the optional ``data file`` entry from an ENVI header."""

    try:
        text = hdr_path.read_text(encoding="utf-8", errors="ignore")
    except OSError:
        return None

    for line in text.splitlines():
        if "=" not in line:
            continue
        key, value = line.split("=", 1)
        if key.strip().lower() == "data file":
            return value.strip().strip("{}").strip()
    return None
