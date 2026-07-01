"""Specim/ENVI dataset adapter."""

from __future__ import annotations

import tarfile
from pathlib import Path
from typing import Any

import numpy as np

from ..calibration import calibrate_reflectance
from ..loader import (
    _cube_from_envi_bytes,
    _find_archive_sample_members,
    _find_directory_sample_files,
    _parse_envi_header,
    _read_archive_member_bytes,
    _read_archive_member_text,
    load_sample,
    load_wavelength_csv,
)
from .base import AdapterSample, DatasetAdapter


class EnviHyperspectralAdapter(DatasetAdapter):
    """Adapter for extracted or archived ENVI hyperspectral captures."""

    adapter_name = "envi_hyperspectral"

    def list_samples(self) -> list[str]:
        """Return sample identifiers from an ENVI archive or directory tree."""

        if self.root_path.is_file() and self.root_path.name.lower().endswith((".tar.gz", ".tgz", ".tar")):
            with tarfile.open(self.root_path, mode="r:*") as archive:
                _, _, _, samples = _find_archive_sample_members(archive, None)
            return samples

        if (self.root_path / "capture").is_dir():
            return [self.root_path.name]

        if self.root_path.is_dir():
            return sorted(
                child.name
                for child in self.root_path.iterdir()
                if child.is_dir() and not child.name.startswith("._") and (child / "capture").is_dir()
            )

        return []

    def load_sample(self, sample_id: str | None = None) -> AdapterSample:
        """Load one ENVI sample and optional dark/white references."""

        if self.root_path.is_file():
            spectral = load_sample(self.root_path, self.wavelength_csv, archive_sample=sample_id)
            sample_label = spectral.metadata.get("archive_member_sample", sample_id or self.root_path.stem)
            dark, white = self._load_archive_references(str(sample_label))
            preview = None
        else:
            sample_path = self.root_path
            if sample_id is not None and self.root_path.name != sample_id:
                sample_path = self.root_path / sample_id
            spectral = load_sample(sample_path, self.wavelength_csv)
            sample_label = spectral.metadata.get("archive_member_sample", sample_path.name)
            dark, white = self._load_directory_references(sample_path)
            preview = self._load_preview_image(sample_path)

        reflectance, calibration_metadata = calibrate_reflectance(spectral.data, dark, white)
        metadata = dict(spectral.metadata)
        metadata.update(
            {
                "adapter_used": self.adapter_name,
                "source_data_kind": "real_dataset_data",
                "sample_id": sample_label,
                "calibration": calibration_metadata,
                "calibration_applied": bool(calibration_metadata.get("calibration_applied")),
                "analysis_data_kind": calibration_metadata.get("analysis_data_kind", "raw_intensity"),
            }
        )

        return AdapterSample(
            sample_id=str(sample_label),
            cube=np.asarray(spectral.data),
            wavelengths=np.asarray(spectral.available_wavelengths, dtype=float),
            metadata=metadata,
            dark_reference=dark,
            white_reference=white,
            reflectance_cube=reflectance if calibration_metadata.get("calibration_applied") else None,
            preview_image=preview,
            source_type=spectral.source_type,
            is_reflectance=bool(calibration_metadata.get("calibration_applied")),
        )

    def _load_directory_references(self, sample_path: Path) -> tuple[np.ndarray | None, np.ndarray | None]:
        """Load DARKREF and WHITEREF captures from an extracted sample folder."""

        capture_dir = sample_path / "capture"
        if not capture_dir.exists():
            return None, None
        dark = self._load_reference_pair(capture_dir, "DARKREF_")
        white = self._load_reference_pair(capture_dir, "WHITEREF_")
        return dark, white

    def _load_reference_pair(self, capture_dir: Path, prefix: str) -> np.ndarray | None:
        """Load one ENVI reference capture by filename prefix."""

        raw_candidates = sorted(
            path for path in capture_dir.glob(f"{prefix}*.raw") if not path.name.startswith("._")
        )
        if not raw_candidates:
            return None
        raw_path = raw_candidates[0]
        hdr_path = raw_path.with_suffix(".hdr")
        if not hdr_path.exists():
            return None
        header = _parse_envi_header(hdr_path.read_text(encoding="utf-8", errors="ignore"))
        return _cube_from_envi_bytes(raw_path.read_bytes(), header)

    def _load_archive_references(self, sample_root: str) -> tuple[np.ndarray | None, np.ndarray | None]:
        """Load DARKREF and WHITEREF captures from an archive sample."""

        if not self.root_path.is_file():
            return None, None
        with tarfile.open(self.root_path, mode="r:*") as archive:
            dark = self._load_archive_reference(archive, sample_root, "DARKREF_")
            white = self._load_archive_reference(archive, sample_root, "WHITEREF_")
        return dark, white

    def _load_archive_reference(
        self,
        archive: tarfile.TarFile,
        sample_root: str,
        prefix: str,
    ) -> np.ndarray | None:
        """Load one archive reference capture by filename prefix."""

        prefix_path = f"{sample_root}/capture/{prefix}".lower()
        raw_names = sorted(
            member.name
            for member in archive.getmembers()
            if member.isfile()
            and member.name.lower().startswith(prefix_path)
            and member.name.lower().endswith(".raw")
            and "/._" not in member.name
        )
        if not raw_names:
            return None
        raw_name = raw_names[0]
        hdr_name = raw_name[:-4] + ".hdr"
        try:
            header_text = _read_archive_member_text(archive, hdr_name)
            raw_bytes = _read_archive_member_bytes(archive, raw_name)
        except FileNotFoundError:
            return None
        return _cube_from_envi_bytes(raw_bytes, _parse_envi_header(header_text))

    def _load_preview_image(self, sample_path: Path) -> np.ndarray | None:
        """Load a preview PNG from an extracted sample when Pillow is available."""

        try:
            from PIL import Image
        except Exception:
            return None
        candidates = sorted(path for path in sample_path.glob("*.png") if not path.name.startswith("._"))
        if not candidates:
            return None
        return np.asarray(Image.open(candidates[0]))


def load_adapter_sample(
    input_path: str | Path,
    wavelength_csv: str | Path | None = None,
    sample_id: str | None = None,
) -> AdapterSample:
    """Convenience loader for ENVI-backed inputs."""

    adapter = EnviHyperspectralAdapter(input_path, wavelength_csv)
    return adapter.load_sample(sample_id)
