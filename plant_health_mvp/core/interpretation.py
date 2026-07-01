"""Cautious plain-language interpretation of spectral index values.

This module does not diagnose plant stress, disease, water status, or nutrient
deficiency. It turns computed scalar indices into short comparative text that
is useful inside the local analysis app.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Mapping

ROUND_DIGITS = 2


@dataclass(frozen=True, slots=True)
class ThresholdBand:
    """One interpretation interval."""

    minimum: float | None
    maximum: float | None
    level: str
    text: str


NDVI_THRESHOLDS: tuple[ThresholdBand, ...] = (
    ThresholdBand(None, 0.0, "non_vegetation", "Valoarea NDVI sugereaza absenta vegetatiei sau un semnal de vegetatie nevalid."),
    ThresholdBand(0.0, 0.2, "low", "Valoarea NDVI sugereaza un semnal vegetal general slab sau o structura foliara activa limitata."),
    ThresholdBand(0.2, 0.5, "medium", "Valoarea NDVI sugereaza o activitate vegetala moderata."),
    ThresholdBand(0.5, None, "high", "Valoarea NDVI sugereaza o activitate vegetala generala puternica si un semnal clar de frunza."),
)

NDRE_THRESHOLDS: tuple[ThresholdBand, ...] = (
    ThresholdBand(None, 0.0, "very_low", "Valoarea NDRE indica un raspuns red-edge foarte slab, care poate reflecta un semnal red-edge limitat."),
    ThresholdBand(0.0, 0.2, "low", "Valoarea NDRE indica un raspuns red-edge relativ slab, care poate reflecta diferente in semnalul legat de clorofila sau un raspuns subtil de stres."),
    ThresholdBand(0.2, None, "high", "Valoarea NDRE indica un raspuns red-edge mai puternic, compatibil cu un semnal vegetal red-edge mai pronuntat."),
)

GNDVI_THRESHOLDS: tuple[ThresholdBand, ...] = (
    ThresholdBand(None, 0.0, "invalid", "Valoarea GNDVI sugereaza un semnal vegetal slab sau nevalid pentru aceasta configuratie."),
    ThresholdBand(0.0, 0.3, "low", "Valoarea GNDVI sugereaza un raspuns vegetativ verde-NIR redus in raport cu aceasta configuratie de masurare."),
    ThresholdBand(0.3, None, "high", "Valoarea GNDVI sugereaza un raspuns verde-NIR mai puternic si un semnal activ de frunza in raport cu aceasta configuratie de masurare."),
)

CI_RE_THRESHOLDS: tuple[ThresholdBand, ...] = (
    ThresholdBand(None, 0.0, "very_low", "Valoarea CI_RE sugereaza un semnal red-edge legat de clorofila foarte redus."),
    ThresholdBand(0.0, 1.0, "low_medium", "Valoarea CI_RE sugereaza un semnal red-edge legat de clorofila redus pana la moderat."),
    ThresholdBand(1.0, None, "high", "Valoarea CI_RE sugereaza un semnal red-edge legat de clorofila mai puternic."),
)

WATER_PROXY_THRESHOLDS: tuple[ThresholdBand, ...] = (
    ThresholdBand(None, 0.05, "low", "Valoarea proxy pentru apa sugereaza un semnal relativ redus legat de apa in aceasta masurare."),
    ThresholdBand(0.05, 0.2, "medium", "Valoarea proxy pentru apa sugereaza un semnal relativ moderat legat de apa in aceasta masurare."),
    ThresholdBand(0.2, None, "high", "Valoarea proxy pentru apa sugereaza un semnal relativ mai puternic legat de apa in aceasta masurare."),
)

INTERPRETED_INDEXES: tuple[str, ...] = ("NDVI", "GNDVI", "NDRE", "CI_RE", "WATER_PROXY")


def interpret_indices(
    indices: Mapping[str, Any],
    average_bands: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    """Return cautious human-readable interpretation for major indices.

    Parameters
    ----------
    indices:
        Mapping of index names to either scalar values or index result
        dictionaries containing a ``value`` key.
    average_bands:
        Optional average band mapping, retained for future interpretation
        improvements. It is not required for the current rule set.
    """

    del average_bands
    normalized = _normalized_values(indices)
    lines = [
        _interpret_line("NDVI", normalized.get("NDVI"), NDVI_THRESHOLDS, "NDVI"),
        _interpret_line("GNDVI", normalized.get("GNDVI"), GNDVI_THRESHOLDS, "GNDVI"),
        _interpret_line("NDRE", normalized.get("NDRE"), NDRE_THRESHOLDS, "NDRE"),
        _interpret_line("CI_RE", normalized.get("CI_RE"), CI_RE_THRESHOLDS, "CI_RE"),
        _interpret_line("Proxy de apa", normalized.get("WATER_PROXY"), WATER_PROXY_THRESHOLDS, "Proxy de apa"),
    ]
    status = _overall_status(lines)
    conclusion = _conclusion(lines)
    return {
        "summary_title": "Interpretare",
        "overall_status": status,
        "lines": lines,
        "conclusion": conclusion,
        "caution": (
            "Acestea sunt interpretari relative deterministe ale unor masurari de aproape. "
            "Nu reprezinta un diagnostic de boala, seceta sau deficienta de nutrienti."
        ),
    }


def _normalized_values(indices: Mapping[str, Any]) -> dict[str, dict[str, Any]]:
    """Extract major index values and reasons from mixed index payloads."""

    values: dict[str, dict[str, Any]] = {}
    for key in ("NDVI", "NDRE", "GNDVI", "CI_RE", "NDWI_850_940", "WATER_PROXY"):
        raw = indices.get(key)
        if isinstance(raw, Mapping):
            values[key] = {
                "value": _coerce_float(raw.get("value")),
                "reason": raw.get("reason") or raw.get("availability_reason") or "",
                "source_label": raw.get("label") or key,
            }
        else:
            values[key] = {"value": _coerce_float(raw), "reason": "", "source_label": key}

    if values.get("WATER_PROXY", {}).get("value") is None:
        values["WATER_PROXY"] = values.get("NDWI_850_940", {"value": None, "reason": "", "source_label": "NDWI_850_940"})
    return values


def _interpret_line(
    label: str,
    entry: Mapping[str, Any] | None,
    thresholds: tuple[ThresholdBand, ...],
    text_label: str,
) -> dict[str, Any]:
    """Interpret one index value."""

    value = None if entry is None else _coerce_float(entry.get("value"))
    reason = "" if entry is None else str(entry.get("reason") or "")
    if value is None:
        return {
            "label": label,
            "value": None,
            "level": "unavailable",
            "interpretation": f"{label} nu este disponibil pentru acest esantion.",
            "reason": reason or "lipseste banda necesara",
        }

    band = _find_threshold(value, thresholds)
    interpretation = f"{text_label} = {_format_value(value)} {_sentence_fragment(band.text, text_label)}"
    if label == "NDRE":
        interpretation += " Acest rezultat trebuie interpretat comparativ, nu ca un diagnostic de sine statator."
    elif label == "CI_RE":
        interpretation += " Este cel mai util pentru comparatie relativa intre esantioane."
    elif label == "Proxy de apa":
        interpretation += " Trataza-l ca pe un indicator aproximativ, nu ca pe o masurare directa a continutului de apa din frunza."
    return {
        "label": label,
        "value": round(value, 6),
        "level": band.level,
        "interpretation": interpretation,
    }


def _find_threshold(value: float, thresholds: tuple[ThresholdBand, ...]) -> ThresholdBand:
    """Return the threshold band containing ``value``."""

    for band in thresholds:
        above_min = band.minimum is None or value >= band.minimum
        below_max = band.maximum is None or value < band.maximum
        if above_min and below_max:
            return band
    return thresholds[-1]


def _sentence_fragment(text: str, text_label: str) -> str:
    """Turn a full threshold sentence into a value-prefixed sentence fragment."""

    lower_text = text.lower()
    prefixes = (
        f"valoarea {text_label.lower()} ",
        f"valoarea {text_label} ",
    )
    for prefix in prefixes:
        if lower_text.startswith(prefix.lower()):
            return text[len(prefix) :]
    return text


def _overall_status(lines: list[dict[str, Any]]) -> str:
    """Build a short status line from interpreted index levels."""

    by_label = {str(line["label"]): line for line in lines}
    ndvi = by_label.get("NDVI", {}).get("level")
    gndvi = by_label.get("GNDVI", {}).get("level")
    missing = sum(1 for line in lines if line.get("level") == "unavailable")
    if missing >= 3:
        return "Interpretarea este limitata deoarece mai multi indici cheie nu sunt disponibili."
    if ndvi == "high" and gndvi == "high":
        return "Semnal vegetal general puternic."
    if ndvi in {"medium", "high"} or gndvi == "high":
        return "Semnal vegetal general moderat spre puternic."
    if ndvi in {"low", "non_vegetation"} and gndvi in {"low", "invalid", "unavailable"}:
        return "Semnal vegetal general slab."
    return "Interpretare relativa limitata, dar utilizabila, a indicilor."


def _conclusion(lines: list[dict[str, Any]]) -> str:
    """Build a cautious combined conclusion."""

    by_label = {str(line["label"]): line for line in lines}
    ndvi = by_label.get("NDVI", {}).get("level")
    gndvi = by_label.get("GNDVI", {}).get("level")
    ndre = by_label.get("NDRE", {}).get("level")
    cire = by_label.get("CI_RE", {}).get("level")
    water = by_label.get("Proxy de apa", {}).get("level")
    missing = sum(1 for line in lines if line.get("level") == "unavailable")

    parts: list[str] = []
    if missing >= 2:
        parts.append("Interpretarea este limitata deoarece unii indici cheie nu sunt disponibili.")
    if ndvi == "high" and gndvi == "high":
        parts.append("Esantionul arata un semnal vegetal general puternic.")
    elif ndvi == "high":
        parts.append("Esantionul arata un semnal vegetal puternic bazat pe NDVI.")
    elif ndvi in {"medium"} or gndvi == "high":
        parts.append("Esantionul arata un semnal vegetal moderat spre util.")
    elif ndvi in {"low", "non_vegetation"}:
        parts.append("Esantionul arata un semnal vegetal slab in indicii disponibili.")

    if ndvi == "high" and ndre in {"very_low", "low"} and cire in {"very_low", "low_medium", "unavailable"}:
        parts.append("Indicatorii sensibili la red-edge sunt mai moderati decat semnalul vegetal general.")
    elif ndre in {"very_low", "low"} or cire in {"very_low", "low_medium"}:
        parts.append("Semnalul sensibil la red-edge este modest si trebuie interpretat comparativ.")

    if water == "low":
        parts.append("Semnalul legat de apa este relativ redus in aceasta masurare.")
    elif water == "medium":
        parts.append("Semnalul legat de apa este moderat in aceasta masurare.")
    elif water == "high":
        parts.append("Semnalul legat de apa este mai puternic in aceasta masurare.")

    if not parts:
        parts.append("Indicii disponibili ofera un semnal relativ, dar nu suficiente dovezi pentru o concluzie puternica.")
    parts.append("Aceste rezultate pot reflecta variatie normala intre esantioane sau diferente fiziologice subtile si ar trebui comparate intre probe.")
    return " ".join(parts)


def _coerce_float(value: Any) -> float | None:
    """Convert a value to float if possible."""

    if value in (None, ""):
        return None
    try:
        number = float(value)
    except (TypeError, ValueError):
        return None
    if number != number:
        return None
    return number


def _format_value(value: float) -> str:
    """Format an index value for interpretation text."""

    return f"{value:.{ROUND_DIGITS}f}"


__all__ = [
    "CI_RE_THRESHOLDS",
    "GNDVI_THRESHOLDS",
    "INTERPRETED_INDEXES",
    "NDRE_THRESHOLDS",
    "NDVI_THRESHOLDS",
    "WATER_PROXY_THRESHOLDS",
    "interpret_indices",
]
