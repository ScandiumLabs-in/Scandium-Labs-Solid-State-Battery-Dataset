"""Tests for v1.4 — cross-database validation (Phase A).

Covers the deterministic MP<->JARVIS agreement scoring, per-formula-unit
normalization, functional-systematic handling, the canonical validation-block
merge, and the null conventions. No network, no LLM.
"""

from __future__ import annotations

import json
from pathlib import Path

import pandas as pd
import pytest

from scripts import build_canonical_validation as BCV
from ssb_dataset.validation import cross_db as X


def _mp_rows(formula, material_id, fe, gap, density, volume, nsites,
             a=5.0, b=5.0, c=5.0, source="materials_project"):
    return pd.DataFrame([{
        "material_id": material_id,
        "reduced_formula": formula,
        "formation_energy_per_atom": fe,
        "band_gap": gap,
        "density": density,
        "volume": volume,
        "nsites": nsites,
        "lattice_a": a, "lattice_b": b, "lattice_c": c,
        "source_db": source,
    }])


# --------------------------------------------------------------------------
# agreement math
# --------------------------------------------------------------------------

def test_per_property_agreement_abs_mode():
    spec = {"tol": 0.05, "mode": "abs"}
    assert X._per_property_agreement(1.0, 1.02, spec) == pytest.approx(0.6)
    assert X._per_property_agreement(1.0, 1.051, spec) == pytest.approx(0.0)
    assert X._per_property_agreement(1.0, 1.0, spec) == 1.0


def test_per_property_agreement_rel_mode():
    spec = {"tol": 0.05, "mode": "rel"}
    # denom = max(|a|,|b|): 1/21 = 0.0476 rel dev -> below tol -> partial credit
    assert X._per_property_agreement(20.0, 21.0, spec) == pytest.approx(
        1 - 1/21 / 0.05)
    assert X._per_property_agreement(20.0, 25.0, spec) == 0.0  # 25% dev
    # identical values always agree, never divide by zero
    assert X._per_property_agreement(0.0, 0.0, spec) == 1.0


# --------------------------------------------------------------------------
# per-formula-unit normalization
# --------------------------------------------------------------------------

def test_volume_per_fu_normalizes_cell_choice():
    # 4 formula units (8 atoms) in a 160 A3 cell == 1 formula unit (2 atoms) in 40 A3
    assert X._volume_per_fu(160.0, 8.0, "Li2O") == pytest.approx(
        X._volume_per_fu(40.0, 2.0, "Li2O"))


def test_volume_per_fu_formula_count():
    # Li2O = 3 atoms/f.u.; volume per f.u. = volume * 3 / nsites
    assert X._volume_per_fu(30.0, 6.0, "Li2O") == pytest.approx(15.0)


def test_volume_per_fu_bad_inputs():
    assert X._volume_per_fu(float("nan"), 3.0, "Li2O") is None
    assert X._volume_per_fu(30.0, 0.0, "Li2O") is None
    assert X._volume_per_fu(30.0, 3.0, "") is None
    assert X._volume_per_fu(30.0, 3.0, "not-a-formula") is None


# --------------------------------------------------------------------------
# agreement scoring
# --------------------------------------------------------------------------

def test_compute_agreement_emits_both_sides():
    mp = _mp_rows("Li2O", "mp-a", -1.98, 5.24, 2.20, 25.2, 3)
    jv = _mp_rows("Li2O", "jv-a", -1.98, 5.24, 2.20, 25.2, 3, source="jarvis")
    out = X.compute_agreement(mp, jv)
    assert len(out) == 2
    assert set(out["source_db"]) == {"materials_project", "jarvis"}
    assert out["database_count"].tolist() == [2, 2]
    assert out["agreement_score"].tolist() == [1.0, 1.0]
    assert out["rank"].tolist() == [1, 2]


def test_compute_agreement_disagreement_detail():
    mp = _mp_rows("Li2O", "mp-a", -2.0, 5.24, 2.20, 25.2, 3)
    jv = _mp_rows("Li2O", "jv-a", -1.0, 5.24, 2.20, 25.2, 3, source="jarvis")
    out = X.compute_agreement(mp, jv)
    d = json.loads(out.iloc[0]["disagreement"])
    assert d["formation_energy_per_atom"]["agreement"] == 0.0
    assert d["formation_energy_per_atom"]["mp"] == -2.0
    assert d["formation_energy_per_atom"]["jarvis"] == -1.0
    assert d["band_gap"]["agreement"] == 1.0


def test_compute_agreement_missing_property_never_counts():
    mp = _mp_rows("Li2O", "mp-a", -2.0, float("nan"), 2.20, 25.2, 3)
    jv = _mp_rows("Li2O", "jv-a", -2.0, 5.24, 2.20, 25.2, 3, source="jarvis")
    out = X.compute_agreement(mp, jv)
    d = json.loads(out.iloc[0]["disagreement"])
    assert "band_gap" not in d  # absent, not zero-scored
    assert d["density"]["agreement"] == 1.0


def test_compute_agreement_no_overlap_empty():
    mp = _mp_rows("Li2O", "mp-a", -2.0, 1.0, 2.2, 25.2, 3)
    jv = _mp_rows("LiF", "jv-a", -2.0, 1.0, 2.6, 16.8, 2)
    out = X.compute_agreement(mp, jv)
    assert out.empty


def test_compute_agreement_rank_best_first():
    mp = _mp_rows("Li2O", "mp-a", -2.0, 1.0, 2.2, 25.2, 3)
    jv_best = _mp_rows("Li2O", "jv-best", -2.0, 1.0, 2.2, 25.2, 3, source="jarvis")
    jv_bad = _mp_rows("Li2O", "jv-bad", -1.0, 5.0, 3.5, 30.0, 3, source="jarvis")
    out = X.compute_agreement(mp, pd.concat([jv_best, jv_bad], ignore_index=True))
    best = out[out["material_id"] == "jv-best"].iloc[0]
    bad = out[out["material_id"] == "jv-bad"].iloc[0]
    assert best["agreement_score"] > bad["agreement_score"]
    assert best["rank"] < bad["rank"]


def test_compute_agreement_band_gap_functional_tolerance():
    # OptB88vdW vs PBE gap offset ~0.4 eV must NOT zero the agreement
    mp = _mp_rows("Li2O", "mp-a", -2.0, 5.0, 2.2, 25.2, 3)
    jv = _mp_rows("Li2O", "jv-a", -2.0, 5.4, 2.2, 25.2, 3, source="jarvis")
    out = X.compute_agreement(mp, jv)
    d = json.loads(out.iloc[0]["disagreement"])
    assert d["band_gap"]["agreement"] > 0.0


# --------------------------------------------------------------------------
# report
# --------------------------------------------------------------------------

def test_build_report_empty():
    r = X.build_report(pd.DataFrame())
    assert r["overlap_formulas"] == 0
    assert "excluded_sources" in r


def test_build_report_counts():
    mp = _mp_rows("Li2O", "mp-a", -2.0, 5.24, 2.2, 25.2, 3)
    jv = _mp_rows("Li2O", "jv-a", -2.0, 5.24, 2.2, 25.2, 3, source="jarvis")
    out = X.compute_agreement(mp, jv)
    r = X.build_report(out)
    assert r["overlap_formulas"] == 1
    assert r["mp_records"] == 1
    assert r["jarvis_records"] == 1
    assert "band_gap_note" in r
    assert "formation_energy_per_atom" in r["per_property"]


def test_report_excluded_sources_documented():
    mp = _mp_rows("Li2O", "mp-a", -2.0, 5.24, 2.2, 25.2, 3)
    jv = _mp_rows("Li2O", "jv-a", -2.0, 5.24, 2.2, 25.2, 3, source="jarvis")
    out = X.compute_agreement(mp, jv)
    r = X.build_report(out)
    for src in ("nomad", "cod"):
        assert src in r["excluded_sources"]
        assert r["excluded_sources"][src]  # non-empty honest note


# --------------------------------------------------------------------------
# canonical merge (build_canonical_validation.build_validation_frame)
# --------------------------------------------------------------------------


def _write_canonical(tmp_path, rows):
    canon = pd.DataFrame(rows)
    p = tmp_path / "cleaning_output"
    p.mkdir()
    canon.to_parquet(p / "canonical_dataset.parquet", index=False)


def _canon_rows(validated, unvalidated):
    rows = []
    for i, (mid, comp) in enumerate(validated):
        rows.append({"identity.material_id": mid,
                     "identity.composition": comp,
                     "identity.source_db": "materials_project"})
    for mid in unvalidated:
        rows.append({"identity.material_id": mid,
                     "identity.composition": "Li-only-row",
                     "identity.source_db": "literature_mined"})
    return rows


def test_build_validation_frame_merges(tmp_path, monkeypatch):
    monkeypatch.setattr(BCV, "ROOT", tmp_path)
    monkeypatch.setattr(BCV, "CANONICAL",
                        tmp_path / "cleaning_output/canonical_dataset.parquet")
    monkeypatch.setattr(BCV, "VALIDATION_OUT", tmp_path / "validation_output")
    (tmp_path / "validation_output").mkdir(parents=True)
    _write_canonical(tmp_path, _canon_rows(
        validated=[("mp-a", "Li2O"), ("jv-a", "Li2O")], unvalidated=["lit-1"]))
    mp = _mp_rows("Li2O", "mp-a", -2.0, 1.0, 2.2, 25.2, 3)
    jv = _mp_rows("Li2O", "jv-a", -2.0, 1.0, 2.2, 25.2, 3, source="jarvis")
    vdf = X.compute_agreement(mp, jv)
    vdf.to_parquet(tmp_path / "validation_output/cross_db_validation.parquet",
                   index=False)

    out = BCV.build_validation_frame()
    assert out["validation.database_count"].tolist() == [2, 2, 0]
    assert out.loc[out["identity.material_id"] == "mp-a",
                   "validation.agreement_score"].iloc[0] == 1.0
    assert out.loc[out["identity.material_id"] == "lit-1",
                   "validation.agreement_score"].isna().iloc[0]
    assert out.loc[out["identity.material_id"] == "lit-1",
                   "validation.rank"].isna().iloc[0]
    assert out.loc[out["identity.material_id"] == "lit-1",
                   "validation.database_count"].iloc[0] == 0


def test_build_validation_frame_empty_vdf(tmp_path, monkeypatch):
    monkeypatch.setattr(BCV, "ROOT", tmp_path)
    monkeypatch.setattr(BCV, "CANONICAL",
                        tmp_path / "cleaning_output/canonical_dataset.parquet")
    monkeypatch.setattr(BCV, "VALIDATION_OUT", tmp_path / "validation_output")
    (tmp_path / "validation_output").mkdir(parents=True)
    _write_canonical(tmp_path, _canon_rows(validated=[], unvalidated=["lit-1"]))
    # empty cross-db file -> all rows database_count 0, no exception
    pd.DataFrame().to_parquet(
        tmp_path / "validation_output/cross_db_validation.parquet", index=False)
    out = BCV.build_validation_frame()
    assert out["validation.database_count"].tolist() == [0]
    assert out["validation.agreement_score"].isna().all()


def test_summarize_coverage(tmp_path, monkeypatch):
    monkeypatch.setattr(BCV, "ROOT", tmp_path)
    monkeypatch.setattr(BCV, "CANONICAL",
                        tmp_path / "cleaning_output/canonical_dataset.parquet")
    monkeypatch.setattr(BCV, "VALIDATION_OUT", tmp_path / "validation_output")
    _write_canonical(tmp_path, _canon_rows(
        validated=[("mp-a", "Li2O"), ("jv-a", "Li2O")], unvalidated=["lit-1"]))
    mp = _mp_rows("Li2O", "mp-a", -2.0, 1.0, 2.2, 25.2, 3)
    jv = _mp_rows("Li2O", "jv-a", -2.0, 1.0, 2.2, 25.2, 3, source="jarvis")
    vdf = X.compute_agreement(mp, jv)
    (tmp_path / "validation_output").mkdir(exist_ok=True)
    vdf.to_parquet(tmp_path / "validation_output/cross_db_validation.parquet",
                   index=False)
    out = BCV.build_validation_frame()
    s = BCV.summarize(out)
    assert s["records_validated"] == 2
    assert s["compositions_validated"] == 1
    assert s["database_count_distribution"] == {0: 1, 2: 2}
