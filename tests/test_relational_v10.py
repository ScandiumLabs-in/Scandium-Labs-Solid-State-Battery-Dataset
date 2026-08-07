"""Tests for v1.0 — relational dataset (material -> experiment -> measurement).

Covers the id schemes, field-level confidence, dopant extraction, and the table
builders from `src/ssb_dataset/db/`. Deterministic, no network, no LLM.
"""

from __future__ import annotations

import pandas as pd
import pytest

from ssb_dataset.db import schema as s
from ssb_dataset.db.build import (
    build_dopants,
    build_experiments_and_measurements,
    build_materials,
    build_papers,
    build_synthesis,
)


# --------------------------------------------------------------------------
# ID schemes
# --------------------------------------------------------------------------

def test_stable_id_deterministic_and_prefix():
    a = s.stable_id("experiment", "Li2OHCl", "10.1/x")
    b = s.stable_id("experiment", "Li2OHCl", "10.1/x")
    c = s.stable_id("experiment", "Li2OHCl", "10.1/y")
    assert a == b
    assert a != c
    assert a.startswith("exp-")
    assert s.stable_id("measurement", "a").startswith("meas-")
    assert s.stable_id("synthesis", "a").startswith("syn-")
    assert s.stable_id("sample", "a").startswith("smp-")
    assert s.stable_id("dopant", "a").startswith("dop-")


def test_paper_id_uses_doi_when_present():
    assert s.paper_id("10.1038/x", "Li2OHCl") == "10.1038/x"
    assert s.paper_id(None, "Li2OHCl").startswith("paper-")


def test_fingerprint_only_populated_fields():
    rec = {"sample_form": "PELLET", "atmosphere": "AR", "sinter_temperature_C": None}
    fp = s.fingerprint(rec, ("sample_form", "atmosphere", "sinter_temperature_C"))
    assert "sinter_temperature_C" not in fp
    assert "sample_form=PELLET" in fp


def test_fingerprint_empty_containers_ignored():
    rec = {"precursors": [], "ball_milling": False, "sintering": False}
    fp = s.fingerprint(rec, ("precursors", "ball_milling", "sintering"))
    assert fp == ""


# --------------------------------------------------------------------------
# Field-level confidence (Phase F)
# --------------------------------------------------------------------------

def test_field_confidences_verified_human_full():
    rec = {
        "temperature_range_measured": {"min_C": 25.0, "max_C": 25.0},
        "ion_transport.measurement_method": "EIS",
        "text_provenance.evidence_sentence": "σ = 1e-4 S/cm at 25 °C",
    }
    f = s.field_confidences(rec, tier="verified_human", extraction_confidence=0.95)
    assert f["value"] == 1.0
    assert f["temperature"] == 1.0
    assert f["method"] == 1.0
    assert f["evidence"] == 1.0
    assert s.overall_confidence(f) == 1.0


def test_field_confidences_extraction_blends():
    rec = {
        "temperature_range_measured": None,
        "ion_transport.measurement_method": None,
        "text_provenance.evidence_sentence": None,
    }
    f = s.field_confidences(rec, tier="low_confidence_extraction", extraction_confidence=0.5)
    assert f["value"] < 1.0
    assert f["temperature"] == 0.0
    assert f["method"] == 0.0
    assert f["evidence"] == 0.0
    assert s.overall_confidence(f) < 1.0


def test_field_confidences_verifed_beats_extraction():
    rec = {"ion_transport.measurement_method": "EIS"}
    fv = s.field_confidences(rec, tier="verified_human", extraction_confidence=0.4)
    fe = s.field_confidences(rec, tier="low_confidence_extraction", extraction_confidence=0.9)
    assert fv["value"] > fe["value"]


# --------------------------------------------------------------------------
# Dopant extraction
# --------------------------------------------------------------------------

def test_extract_dopants_colon_annotation():
    assert "Ta" in s.extract_dopants("Li7La3Zr2O12:Ta")


def test_extract_dopants_ignores_ratios():
    assert s.extract_dopants("Li2S-P2S5(70:30)glass") == []


def test_extract_dopants_ignores_source_ids():
    assert s.extract_dopants("aflow-aflow:019c9366d67e6cca") == []
    assert s.extract_dopants("mp-12345") == []


def test_extract_dopants_doped_qualifier():
    assert s.extract_dopants("Li6.25Al0.25La3Zr2O12 Al-doped") == ["Al"]


# --------------------------------------------------------------------------
# Table builders
# --------------------------------------------------------------------------

def _mk_df(n=3):
    rows = []
    for i in range(n):
        rows.append({
            "identity.material_id": f"Li2OHCl{i}" if i else "Li2OHCl",
            "identity.composition": rows[i - 1]["identity.material_id"] if i else "Li2OHCl",
            "identity.source_db": "literature_mined",
            "identity.confidence_tier": "verified_human",
            "identity.family": "antiperovskite",
            "identity.is_electrolyte_candidate": True,
            "structure.density": 3.0 + i,
            "thermodynamics.band_gap": 4.0,
            "text_provenance.source_doi": "10.1038/x" if i else "10.1038/y",
            "text_provenance.source_paper_title": f"Paper {i}",
            "text_provenance.source_year": 2024,
            "text_provenance.evidence_page": "3",
            "text_provenance.evidence_sentence": f"σ = 1e-4 S/cm (row {i})",
            "text_provenance.extraction_reviewer": "verification-pass-2026-08-01",
            "text_provenance.extraction_confidence_score": 0.9,
            "ion_transport.sigma_RT": 1e-4 + i * 1e-5,
            "ion_transport.activation_energy_Ea": 0.4 + i * 0.1,
            "ion_transport.measurement_method": "EIS",
            "ion_transport.temperature_range_measured": {"min_C": 25.0, "max_C": 25.0},
            "experiment": {
                "sample_form": "PELLET",
                "atmosphere": "AR",
                "sinter_temperature_C": 120.0,
                "pelletizing_pressure_MPa": 480.0,
            },
            "synthesis": {"precursors": ["LiOH", "LiCl"], "solid_state": True},
        })
    df = pd.DataFrame(rows)
    # fix composition: first row references rows[-1] above — patch explicitly
    df.loc[0, "identity.composition"] = "Li2OHCl"
    return df


def test_build_materials_dedupes():
    df = _mk_df()
    mats = build_materials(df)
    assert len(mats) == len(df)  # unique material_ids in this fixture
    assert "material_id" in mats.columns
    assert "source_dbs" in mats.columns


def test_build_materials_prefers_verified_over_dft():
    df = _mk_df(n=2)
    df["identity.material_id"] = ["Li2OHCl", "Li2OHCl"]
    df["identity.confidence_tier"] = ["verified_human", "dft_native"]
    df["identity.source_db"] = ["literature_mined", "materials_project"]
    mats = build_materials(df)
    assert len(mats) == 1
    assert mats["identity.confidence_tier"].iloc[0] == "verified_human"


def test_build_papers_one_per_doi():
    df = _mk_df(n=2)  # two rows, two distinct DOIs in fixture
    papers = build_papers(df)
    assert len(papers) == len(df)
    assert set(papers["paper_id"]) == {"10.1038/x", "10.1038/y"}


def test_build_papers_same_doi_collapses():
    df = _mk_df()
    df["text_provenance.source_doi"] = "10.1038/same"
    papers = build_papers(df)
    assert len(papers) == 1
    assert papers["paper_id"].iloc[0] == "10.1038/same"


def test_experiments_measurements_build():
    df = _mk_df()
    exp, meas = build_experiments_and_measurements(df)
    assert len(exp) == len(df)
    assert len(meas) == 2 * len(df)  # sigma + ea per row
    assert exp["experiment_id"].nunique() == len(exp)
    assert meas["measurement_id"].nunique() == len(meas)
    # property types present
    assert set(meas["property"]) == {"conductivity", "activation_energy"}


def test_experiment_id_stable_across_runs():
    df = _mk_df()
    exp1, _ = build_experiments_and_measurements(df)
    exp2, _ = build_experiments_and_measurements(df)
    assert exp1["experiment_id"].tolist() == exp2["experiment_id"].tolist()


def test_identical_condition_rows_collapse_experiment():
    """Two rows from the same paper + same conditions + same sigma must map to
    ONE experiment and ONE measurement (the relational model never emits
    duplicate entities for a duplicated source record)."""
    df = _mk_df(n=2)
    df["identity.material_id"] = "Li2OHCl"
    df["text_provenance.source_doi"] = "10.1038/same"
    df["ion_transport.sigma_RT"] = [1e-4, 1e-4]
    df["ion_transport.activation_energy_Ea"] = [0.4, 0.4]
    df["experiment"] = [{"sample_form": "PELLET", "atmosphere": "AR"}] * 2
    exp, meas = build_experiments_and_measurements(df)
    assert exp["experiment_id"].nunique() == 1
    # same values -> 1 conductivity + 1 ea measurement
    assert len(meas) == 2


def test_distinct_conditions_stay_distinct_experiments():
    """The roadmap's core guarantee: two experiments reporting different σ for
    the same material must never overwrite each other."""
    df = _mk_df(n=2)
    df["identity.material_id"] = "Li2OHCl"
    df["text_provenance.source_doi"] = "10.1038/same"
    df["ion_transport.sigma_RT"] = [8e-4, 3e-4]  # the roadmap's example values
    df["experiment"] = [
        {"sample_form": "PELLET", "atmosphere": "AR", "sinter_temperature_C": 120.0},
        {"sample_form": "PELLET", "atmosphere": "AR", "sinter_temperature_C": 200.0},
    ]
    exp, meas = build_experiments_and_measurements(df)
    assert exp["experiment_id"].nunique() == 2
    assert sorted(exp["sinter_temperature_C"].tolist()) == [120.0, 200.0]
    # both σ values preserved as separate measurements
    sigmas = sorted(meas[meas["property"] == "conductivity"]["value"].tolist())
    assert sigmas == [3e-4, 8e-4]


def test_field_confidence_columns_present():
    df = _mk_df()
    _, meas = build_experiments_and_measurements(df)
    for col in ("confidence_value", "confidence_temperature",
                "confidence_method", "confidence_evidence", "confidence"):
        assert col in meas.columns
    assert meas["confidence_value"].between(0, 1).all()


def test_bare_dft_rows_excluded():
    df = _mk_df()
    df["ion_transport.sigma_RT"] = None
    df["ion_transport.activation_energy_Ea"] = None
    df["experiment"] = [{}] * len(df)
    exp, meas = build_experiments_and_measurements(df)
    assert len(exp) == 0
    assert len(meas) == 0


def test_build_synthesis_sparse():
    df = _mk_df()
    syn = build_synthesis(df)
    assert len(syn) == len(df)
    assert syn["synthesis_id"].nunique() == len(syn)
    assert "sinter_temperature_C" in syn.columns


def test_build_synthesis_skips_empty():
    df = _mk_df()
    df["synthesis"] = [{}] * len(df)
    df["experiment"] = [{}] * len(df)
    syn = build_synthesis(df)
    assert len(syn) == 0


def test_build_dopants():
    df = _mk_df()
    df.loc[0, "identity.material_id"] = "Li7La3Zr2O12:Ta"
    dop = build_dopants(df)
    # the fixture's annotated material must be present (benchmark inventory
    # may contribute additional annotated names)
    ta = dop[dop["material_id"] == "Li7La3Zr2O12:Ta"]
    assert len(ta) == 1
    assert ta["dopant"].iloc[0] == "Ta"
    assert ta["dopant_id"].iloc[0].startswith("dop-")


def test_measurement_provenance_chain_present():
    df = _mk_df()
    _, meas = build_experiments_and_measurements(df)
    m0 = meas.iloc[0]
    assert m0["paper_id"] == "10.1038/y"
    assert m0["evidence_page"] == "3"
    assert m0["reviewer"] == "verification-pass-2026-08-01"
    assert m0["confidence_tier"] == "verified_human"
