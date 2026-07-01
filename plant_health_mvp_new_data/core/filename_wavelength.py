"""Helpers for inferring wavelength labels from image filenames."""

from __future__ import annotations

import re
from pathlib import Path


_DIGIT_PATTERN = re.compile(r"\d")


def infer_wavelength_from_filename(path: str | Path) -> float | None:
    """Return the first three digits found in the filename stem as a wavelength.

    This matches the mixed-image naming convention where files such as
    ``850_leaf.png`` or ``nir850_capture.jpg`` encode the wavelength in the
    filename itself.
    """

    stem = Path(path).stem
    digits = "".join(match.group(0) for match in _DIGIT_PATTERN.finditer(stem))
    if len(digits) < 3:
        return None
    return float(digits[:3])


__all__ = ["infer_wavelength_from_filename"]
