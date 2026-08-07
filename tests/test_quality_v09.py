"""Tests for v0.9 — full-canonical quality scoring, anomaly scan, unit audit,
and the first-class experiments table. No network, no LLM."""

from __future__ import annotations

import json

import pandas as pd

from ssb_dataset.quality.anomalies import scan_anomalies
from ssb_dataset.quality.experiments import build_experiments_table, _stable_id
from ssb_dataset.quality.scoring import (
    completeness_score,
    score_canonical_row,
)
from ssb_dataset.quality.unit_audit import audit_units


def _df(**overrides) -> pd.DataFrame:
    base = {
        "identity.material_id": ["Li2OHCl", "Li6PS5Cl", "Li7La3Zr2O12"],
        "identity.family": ["antiperovskite", "sulfide", "garnet"],
        "identity.source_db": ["materials_project"] * 3,
        "identity.confidence_tier": ["dft_native"] * 3,
        "structure.density": [3.0, 2.1, 5.1],
        "structure.volume": [100.0, 300.0, 500.0],
        "thermodynamics.band_gap": [4.0, 2.0, 5.5],
        "thermodynamics.energy_above_hull": [0.0, 0.01, 0.0],
        "thermodynamics.formation_energy_per_atom": [-2.0, -1.5, -3.0],
        "redox.electroneutral": [True, True, True],
        "chemistry.electronegativity_mean": [2.5, 2.4, 1.5],
    }
    base.update(overrides)
    return pd.DataFrame(base)


# --------------------------------------------------------------------------
# Scoring
# --------------------------------------------------------------------------

def test_dft_row_gets_completeness_score():
    df = _df()
    q = score_canonical_row(df.iloc[0].to_dict())
    assert q["quality.kind"] == "completeness"
    assert 0 <= q["quality.score"] <= 100
    assert q["quality.grade"] in ("A+", "A", "B", "C", "D")
    assert q["quality.confidence"] in ("high", "medium", "low")
    assert q["quality.version"] == "v0.9.0"


def test_completeness_rewards_populated_records():
    full = _df()
    sparse = _df()
    sparse["structure.density"] = None
    sparse["structure.volume"] = None
    sparse["thermodynamics.band_gap"] = None
    sparse["thermodynamics.energy_above_hull"] = None
    q_full = completeness_score(full.iloc[0].to_dict())
    q_sparse = completeness_score(sparse.iloc[0].to_dict())
    assert q_full["quality.score"] > q_sparse["quality.score"]


def test_completeness_penalizes_negative_density():
    df = _df()
    df.loc[0, "structure.density"] = -1.0
    q = completeness_score(df.iloc[0].to_dict())
    assert any("density" in f for f in q["quality.flags"])
    assert q["quality.score"] < 100


def test_completeness_penalizes_charge_imbalance():
    df = _df()
    df.loc[0, "redox.electroneutral"] = False
    q = completeness_score(df.iloc[0].to_dict())
    assert any("charge" in f or "electroneutral" in f for f in q["quality.flags"])


def test_experimental_row_uses_trust_ladder():
    df = _df()
    df.loc[0, "identity.confidence_tier"] = "verified_human"
    df.loc[0, "text_provenance.evidence_page"] = "4"
    df.loc[0, "text_provenance.evidence_sentence"] = "σ = 1e-4 S/cm"
    q = score_canonical_row(df.iloc[0].to_dict())
    assert q["quality.kind"] == "experimental"
    assert q["quality.score"] > 0


def test_score_schema_keys_present():
    q = score_canonical_row(_df().iloc[0].to_dict())
    for k in ("quality.score", "quality.flags", "quality.confidence",
              "quality.version"):
        assert k in q


# --------------------------------------------------------------------------
# Anomaly scan
# --------------------------------------------------------------------------

def test_anomaly_scan_passes_clean_data():
    r = scan_anomalies(_df())
    assert r["passed"] is True
    assert r["high_severity_checks_failing"] == 0


def test_anomaly_scan_flags_negative_conductivity():
    df = _df()
    df["ion_transport.sigma_RT"] = [-0.001, 1e-3, 1e-4]
    r = scan_anomalies(df)
    assert r["checks"]["negative_conductivity"]["n"] == 1
    assert r["passed"] is False


def test_anomaly_scan_flags_negative_ea():
    df = _df()
    df["ion_transport.activation_energy_Ea"] = [-0.2, 0.3, None]
    r = scan_anomalies(df)
    assert r["checks"]["negative_activation_energy"]["n"] == 1
    assert r["passed"] is False


def test_anomaly_scan_flags_charge_imbalance():
    df = _df()
    df.loc[1, "redox.electroneutral"] = False
    r = scan_anomalies(df)
    assert r["checks"]["charge_imbalance"]["n"] == 1


def test_anomaly_scan_flags_duplicate_experiment():
    df = _df()
    df["identity.material_id"] = ["Li2OHCl"] * 3
    df["text_provenance.source_doi"] = ["10.1/a"] * 3
    df["ion_transport.sigma_RT"] = [1e-4, 1e-4, 1e-3]
    r = scan_anomalies(df)
    assert r["checks"]["duplicate_experiment"]["n"] == 2


def test_anomaly_scan_flags_missing_composition():
    df = _df()
    df.loc[0, "identity.material_id"] = ""
    r = scan_anomalies(df)
    assert r["checks"]["missing_composition"]["n"] == 1


# --------------------------------------------------------------------------
# Unit audit
# --------------------------------------------------------------------------

def test_unit_audit_passes_clean():
    r = audit_units(_df())
    assert r["passed"] is True
    assert r["total_invalid"] == 0


def test_unit_audit_flags_out_of_range_sigma():
    df = _df()
    df["ion_transport.sigma_RT"] = [1e-9, 1e3, 1e-4]  # 1e3 S/cm implausible
    r = audit_units(df)
    assert r["checks"]["sigma"]["invalid"] == 1
    assert r["passed"] is False


def test_unit_audit_flags_out_of_range_ea():
    df = _df()
    df["ion_transport.activation_energy_Ea"] = [0.3, 12.0, None]  # 12 eV absurd
    r = audit_units(df)
    assert r["checks"]["activation_energy"]["invalid"] == 1


def test_unit_audit_flags_unit_string_leak():
    df = _df()
    df["ion_transport.sigma_RT"] = ["20 mS/cm", 1e-3, 1e-4]
    r = audit_units(df)
    assert r["checks"]["unit_string_leak"]["n"] == 1
    assert r["passed"] is False


# --------------------------------------------------------------------------
# Experiments table
# --------------------------------------------------------------------------

def test_stable_id_deterministic():
    a = _stable_id("Li2OHCl", "10.1/a", 1e-4, 0.4, 25)
    b = _stable_id("Li2OHCl", "10.1/a", 1e-4, 0.4, 25)
    c = _stable_id("Li2OHCl", "10.1/b", 1e-4, 0.4, 25)
    assert a == b
    assert a != c
    assert a.startswith("exp-")


def test_experiments_promote_measurement_rows():
    df = _df()
    df["ion_transport.sigma_RT"] = [1e-4, 1e-3, None]
    df["experiment"] = [
        {"sample_form": "pellet", "atmosphere": "Ar"},
        {},
        {},
    ]
    exp = build_experiments_table(df)
    # only the σ-carrying / experiment-carrying rows promote
    assert len(exp) == 2
    assert "experiment_id" in exp.columns
    assert "material_id" in exp.columns
    assert "sigma_S_per_cm" in exp.columns
    assert exp.loc[0, "sample_form"] == "pellet"


def test_experiments_exclude_bare_dft_rows():
    df = _df()  # no experiment block, no sigma
    exp = build_experiments_table(df)
    assert len(exp) == 0


def test_experiments_table_material_many_measurements():
    df = _df()
    df["identity.material_id"] = ["Li2OHCl"] * 3  # one material, 3 papers
    df["ion_transport.sigma_RT"] = [1e-4, 1e-4, 1e-4]
    df["text_provenance.source_doi"] = ["10.1/a", "10.1/b", "10.1/c"]
    df["experiment"] = [{"temperature": 25}, {"temperature": 60}, {}]
    exp = build_experiments_table(df)
    assert len(exp) == 3
    # each paper = its own experiment id -> 1 material, N experiments
    assert exp["experiment_id"].nunique() == 3
    assert exp["material_id"].nunique() == 1


# --------------------------------------------------------------------------
# Build-script JSON artifacts (structure contract)
# --------------------------------------------------------------------------

def test_report_artifact_contract(tmp_path):
    """The build script's summaries must serialize + carry the roadmap keys."""
    df = _df()
    q = score_canonical_row(df.iloc[0].to_dict())
    payload = {
        "quality.score": q["quality.score"],
        "quality.flags": q["quality.flags"],
        "quality.confidence": q["quality.confidence"],
        "quality.version": q["quality.version"],
    }
    dumped = json.dumps(payload)
    assert json.loads(dumped) == payload
