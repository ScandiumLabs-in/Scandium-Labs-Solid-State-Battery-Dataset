"""Tests for the deterministic experiment-condition extractor (M6/Phase 2.2)."""

from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

import pytest

from src.ssb_dataset.pipeline.experiment_extract import (
    _eis_frequency_range, extract_conditions,
)


@pytest.mark.parametrize("text,expected", [
    # superscript-10 pair with soft hyphens (the nasicon/acsaem form)
    ("frequency from \u00ad10\u20132 to \u00ad106\u00a0Hz", (0.01, 1e6)),
    ("from 0.01 to 10\u2076 Hz", (0.01, 1e6)),
    ("0.01 to 106 Hz", (0.01, 1e6)),
    ("1 Hz - 7 MHz", (1.0, 7e6)),
    ("between 10 mHz and 1 MHz", (0.01, 1e6)),
    ("1 MHz - 1 Hz", (1.0, 1e6)),  # reversed → corrected to min≤max
    ("swept from 10 mHz to 10 MHz", (0.01, 1e7)),
])
def test_eis_frequency_range(text, expected):
    assert _eis_frequency_range(text) == pytest.approx(expected)


def test_eis_frequency_rejects_nmr():
    # NMR MAS nuclei must never be captured as EIS frequency
    assert _eis_frequency_range("73.58 MHz (6Li) MAS spinning") == (None, None)


@pytest.mark.parametrize("field", [
    "sample_form", "pellet_diameter_mm", "thickness_mm", "relative_density_pct",
    "pelletizing_pressure_MPa", "electrode_material", "frequency_min_Hz",
    "frequency_max_Hz", "atmosphere", "sinter_temperature_C", "sinter_time_h",
    "annealing_temperature_C", "instrument", "equivalent_circuit", "dc_bias_V",
])
def test_extract_result_fields_present(field):
    # every M6 field must exist on the dataclass (default None)
    r = extract_conditions.__annotations__  # touching def
    from src.ssb_dataset.pipeline.experiment_extract import ExtractResult
    assert field in ExtractResult.__dataclass_fields__


def _make_pdf(tmp_path, text):
    import fitz
    p = fitz.open()
    page = p.new_page()
    # insert_text doesn't wrap; chunk into short lines so nothing is clipped
    chunks = [text[i:i + 80] for i in range(0, len(text), 80)]
    for i, ch in enumerate(chunks):
        page.insert_text((72, 72 + i * 14), ch, fontsize=9)
    out = tmp_path / "t.pdf"
    p.save(str(out))
    p.close()
    return out


def test_extract_conditions_pellet(tmp_path):
    pdf = _make_pdf(tmp_path, (
        "The pellet diameter was 10 mm, thickness 2.5 mm, uniaxially pressed "
        "at 300 MPa, relative density 96%, electrode Au, "
        "impedance from 0.01 to 106 Hz under Ar, sintered at 1100 C for 12 h."
    ))
    r = extract_conditions(pdf)
    assert r.sample_form == "PELLET"
    assert r.pelletizing_pressure_MPa == pytest.approx(300)
    assert r.pellet_diameter_mm == pytest.approx(10)
    assert r.thickness_mm == pytest.approx(2.5)
    assert r.relative_density_pct == pytest.approx(96)
    assert r.frequency_min_Hz == pytest.approx(0.01)
    assert r.frequency_max_Hz == pytest.approx(1e6)
    assert r.atmosphere == "AR"
    assert r.sinter_temperature_C == pytest.approx(1100)
    assert r.sinter_time_h == pytest.approx(12)


def test_electrode_material_vs_deposition(tmp_path):
    pdf = _make_pdf(tmp_path, (
        "Gold electrodes were sputtered onto both faces of the pellet; "
        "electrochemical impedance was measured from 1 Hz to 1 MHz in air."
    ))
    r = extract_conditions(pdf)
    assert r.electrode_material == "AU"
    assert r.electrode_deposition == "SPUTTERED"


def test_controlled_vocab_sample_form_and_atmosphere(tmp_path):
    pdf = _make_pdf(tmp_path, (
        "A thin film was prepared under argon atmosphere inside a glovebox; "
        "conductivity was measured by impedance spectroscopy."
    ))
    r = extract_conditions(pdf)
    assert r.sample_form == "THIN_FILM"
    assert r.atmosphere == "AR"  # longest disambiguation (argon/Ar) wins


def test_suspicious_value_flagged(tmp_path):
    pdf = _make_pdf(tmp_path, (
        "The pellet diameter was 55 mm, pressed at 3 MPa, thickness 0.004 mm; "
        "impedance measured from 1 Hz to 1 MHz under N2."
    ))
    r = extract_conditions(pdf)
    assert r.pellet_diameter_mm == pytest.approx(55)
    assert any("pellet_diameter" in s for s in r.suspicious)
    assert any("pelletizing_pressure" in s for s in r.suspicious)
    assert any("thickness" in s for s in r.suspicious)
    assert r.atmosphere == "N2"


def test_equivalent_circuit_disabled(tmp_path):
    # equivalent_circuit is intentionally not stamped from the text layer yet
    # (capture produced prose garbage); it must always be None for now.
    from src.ssb_dataset.pipeline.experiment_extract import (
        _clean_circuit, _looks_like_circuit,
    )
# helpers exist and correctly discriminate a real circuit from prose
    assert _looks_like_circuit("R(CPE)(R||CPE)")
    assert not _looks_like_circuit("model and scheme of int")
    pdf = _make_pdf(tmp_path, (
        "Impedance was measured and fitted to the equivalent circuit "
        "R(CPE)(R||CPE) using a custom routine in air."
    ))
    r = extract_conditions(pdf)
    assert r.equivalent_circuit is None


def test_extract_rejects_hydrogen_pressure(tmp_path):
    # H2-storage pressure must not be captured as pelletizing pressure
    pdf = _make_pdf(tmp_path, (
        "hydrogen storage under H2 pressure of 50 bar and 150000 MPa lattice "
        "is unstable; pellet pressed; conductivity measured."
    ))
    r = extract_conditions(pdf)
    assert r.pelletizing_pressure_MPa is None