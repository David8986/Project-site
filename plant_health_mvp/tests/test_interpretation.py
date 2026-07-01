"""Tests for cautious spectral-index interpretation text."""

from __future__ import annotations

from plant_health_mvp.core.interpretation import interpret_indices


def test_interpret_indices_describes_strong_general_signal_cautiously() -> None:
    """Example values should produce useful but non-diagnostic language."""

    result = interpret_indices(
        {
            "NDVI": {"value": 0.70},
            "GNDVI": {"value": 0.44},
            "NDRE": {"value": 0.08},
            "CI_RE": {"value": 0.19},
            "NDWI_850_940": {"value": 0.03},
        }
    )

    assert result["summary_title"] == "Interpretare"
    assert result["overall_status"] == "Semnal vegetal general puternic."
    assert any(
        line["label"] == "NDVI" and "activitate vegetala generala puternica" in line["interpretation"]
        for line in result["lines"]
    )
    assert any(
        line["label"] == "Proxy de apa" and "semnal relativ redus legat de apa" in line["interpretation"]
        for line in result["lines"]
    )
    assert "Indicatorii sensibili la red-edge sunt mai moderati" in result["conclusion"]
    assert "Semnalul legat de apa este relativ redus" in result["conclusion"]
    assert "Nu reprezinta un diagnostic de boala" in result["caution"]


def test_interpret_indices_handles_missing_values() -> None:
    """Missing major indices should be marked unavailable with a reason."""

    result = interpret_indices({"NDVI": {"value": None, "reason": "missing required band"}})

    ndvi = next(line for line in result["lines"] if line["label"] == "NDVI")
    assert ndvi["value"] is None
    assert ndvi["level"] == "unavailable"
    assert ndvi["reason"] == "missing required band"
    assert "nu este disponibil pentru acest esantion" in ndvi["interpretation"]
    assert "Interpretarea este limitata" in result["conclusion"]
