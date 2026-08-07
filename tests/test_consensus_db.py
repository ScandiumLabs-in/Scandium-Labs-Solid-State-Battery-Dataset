"""Tests for the cross-paper consensus database + the consensus_db review rule."""

from __future__ import annotations

import json

import pytest
from pytest import approx

from ssb_dataset.literature.consensus_db import (
    build_consensus_db,
    summary,
    to_parquet,
    _canonical_doi,
    _canonical_ea,
    _canonical_sigma,
    _iter_records,
    _log_ci,
    _temp_bins,
    _agreement_grade,
    _log_stats,
)
from ssb_dataset.review.rules import ReviewContext, rule_consensus_db


# ---------------------------------------------------------------------------
# consensus_db.py helpers
# ---------------------------------------------------------------------------

def test_canonical_sigma_uses_normalized():
    assert _canonical_sigma({"normalized_sigma": 1.2e-3}) == pytest.approx(1.2e-3)


def test_canonical_sigma_from_raw_conductivity():
    rec = {"property": "conductivity", "value": 0.5, "unit": "mS/cm"}
    assert _canonical_sigma(rec) == pytest.approx(5e-4)


def test_canonical_sigma_ignores_ea_record():
    rec = {"property": "activation_energy", "value": 0.3, "unit": "eV"}
    assert _canonical_sigma(rec) is None


def test_canonical_ea_normalized():
    assert _canonical_ea({"normalized_ea": 0.45}) == pytest.approx(0.45)


def test_canonical_ea_from_kj_per_mol():
    rec = {"property": "activation_energy", "value": 30.0, "unit": "kJ/mol"}
    assert _canonical_ea(rec) == pytest.approx(0.3109, rel=1e-2)


def test_log_ci_none_for_small_sample():
    assert _log_ci([1e-3, 2e-3]) is None


def test_log_ci_computes_for_sample():
    ci = _log_ci([1e-4, 2e-4, 5e-4, 8e-4, 1e-3, 2e-3])
    assert ci is not None
    lo, hi = ci
    assert 0 < lo < hi


def test_temp_bins_buckets():
    bins = _temp_bins([25, 30, 75, 80, 110, None])
    assert bins == [
        {"bin_c": 0, "count": 2},
        {"bin_c": 50, "count": 2},
        {"bin_c": 100, "count": 1},
    ]


def test_agreement_grade_ap_plus():
    # all within 0.2 log10 of the median, n>=3 -> A+
    assert _agreement_grade([1e-3, 1.1e-3, 9.5e-4, 1.05e-3]) == "A+"


def test_agreement_grade_a():
    assert _agreement_grade([1e-3, 2e-3, 8e-4]) == "A"


def test_agreement_grade_b():
    assert _agreement_grade([1e-3, 5e-4]) == "B"


def test_agreement_grade_c_single():
    assert _agreement_grade([1e-3]) == "C"


def test_agreement_grade_d_wide_spread():
    # 3 orders of magnitude spread -> D
    assert _agreement_grade([1e-4, 1e-1]) == "D"
    assert _agreement_grade([3e-6, 3e-4, 2e-4, 1e-4]) == "D"


def test_agreement_grade_empty():
    assert _agreement_grade([]) == ""


def test_log_stats_two_samples():
    mad, std, iqr = _log_stats([1e-3, 1e-3])
    assert mad == approx(0.0)
    assert std == approx(0.0)
    assert iqr == approx(0.0)


def test_log_stats_none_under_two():
    assert _log_stats([1e-3]) == (None, None, None)


def test_build_consensus_db_uncertainty_fields(tmp_path):
    q = tmp_path / "queue.json"
    q.write_text(json.dumps({"items": [
        {"review_id": "a", "composition": "Li6PS5Cl", "property": "conductivity",
         "value": 1e-3, "unit": "S/cm", "doi": "10.1/a", "status": "approved"},
        {"review_id": "b", "composition": "Li6PS5Cl", "property": "conductivity",
         "value": 1.1e-3, "unit": "S/cm", "doi": "10.1/b", "status": "approved"},
        {"review_id": "c", "composition": "Li6PS5Cl", "property": "conductivity",
         "value": 9.5e-4, "unit": "S/cm", "doi": "10.1/c", "status": "approved"},
    ]}))
    groups = build_consensus_db(str(q), str(tmp_path / "none.parquet"), include_benchmarks=False)
    cr = groups["Li6PS5Cl"]
    assert cr.agreement_grade == "A+"
    assert cr.sigma_mad_log10 is not None
    assert cr.sigma_std_log10 is not None
    assert cr.sigma_iqr_log10 is not None
    d = cr.to_dict()
    assert d["agreement_grade"] == "A+"
    assert "sigma_std_log10" in d


def test_iter_records_dedup(tmp_path):
    q = tmp_path / "queue.json"
    q.write_text(json.dumps({"items": [
        {"review_id": "r1", "composition": "Li6PS5Cl", "property": "conductivity",
         "value": 0.001, "unit": "S/cm", "doi": "10.1/a", "status": "approved"},
        # duplicate of r1 (different review_id, same material+doi+value) -> skipped
        {"review_id": "r2", "composition": "Li6PS5Cl", "property": "conductivity",
         "value": 0.001, "unit": "S/cm", "doi": "10.1/a", "status": "approved"},
        # not approved -> skipped
        {"review_id": "r3", "composition": "Li6PS5Cl", "property": "conductivity",
         "value": 0.002, "unit": "S/cm", "doi": "10.1/a", "status": "pending"},
    ]}))
    recs = _iter_records(str(q), str(tmp_path / "none.parquet"))
    assert len(recs) == 1
    assert recs[0]["value"] == 0.001


def test_iter_records_dedup_underscore_doi_form(tmp_path):
    q = tmp_path / "queue.json"
    q.write_text(json.dumps({"items": [
        {"review_id": "r1", "composition": "Li6PS5Cl", "property": "conductivity",
         "value": 0.001, "unit": "S/cm", "doi": "10.1002/anie.200701144", "status": "approved"},
        # same paper in filename-safe underscore form -> same logical DOI, deduped
        {"review_id": "r2", "composition": "Li6PS5Cl", "property": "conductivity",
         "value": 0.001, "unit": "S/cm", "doi": "10.1002_anie.200701144", "status": "approved"},
    ]}))
    recs = _iter_records(str(q), str(tmp_path / "none.parquet"))
    assert len(recs) == 1
    assert recs[0]["doi"] == "10.1002/anie.200701144"


def test_canonical_doi_collapses_underscore_form():
    assert _canonical_doi("10.1021/acsenergylett.8b00249") == "10.1021/acsenergylett.8b00249"
    assert _canonical_doi("10.1021_acsenergylett.8b00249") == "10.1021/acsenergylett.8b00249"
    assert _canonical_doi("10.1002_anie.200701144") == "10.1002/anie.200701144"
    assert _canonical_doi("") == ""
    assert _canonical_doi("unknown") == "unknown"


def test_n_papers_does_not_count_doi_forms_twice(tmp_path):
    q = tmp_path / "queue.json"
    q.write_text(json.dumps({"items": [
        {"review_id": "a", "composition": "Li6PS5Cl", "property": "conductivity",
         "value": 1e-3, "unit": "S/cm", "doi": "10.1021_acs.chemmater.3c01831", "status": "approved"},
        {"review_id": "b", "composition": "Li6PS5Cl", "property": "conductivity",
         "value": 2e-3, "unit": "S/cm", "doi": "10.1021/acs.chemmater.3c01831", "status": "approved"},
        {"review_id": "c", "composition": "Li6PS5Cl", "property": "conductivity",
         "value": 5e-4, "unit": "S/cm", "doi": "10.1038/srep18053", "status": "approved"},
    ]}))
    groups = build_consensus_db(str(q), str(tmp_path / "none.parquet"), include_benchmarks=False)
    cr = groups["Li6PS5Cl"]
    assert cr.n_sigma == 3
    assert cr.n_papers == 2
    assert set(cr.doiss) == {"10.1021/acs.chemmater.3c01831", "10.1038/srep18053"}


def test_build_consensus_db_groups_and_medians(tmp_path):
    q = tmp_path / "queue.json"
    q.write_text(json.dumps({"items": [
        {"review_id": "a", "composition": "Li6PS5Cl", "property": "conductivity",
         "value": 1e-3, "unit": "S/cm", "doi": "10.1/a", "status": "approved",
         "temperature_celsius": 25},
        {"review_id": "b", "composition": "Li6PS5Cl", "property": "conductivity",
         "value": 2e-3, "unit": "S/cm", "doi": "10.1/b", "status": "approved",
         "temperature_celsius": 25},
        {"review_id": "c", "composition": "Li6PS5Cl", "property": "conductivity",
         "value": 5e-4, "unit": "S/cm", "doi": "10.1/c", "status": "approved",
         "temperature_celsius": 75},
        {"review_id": "d", "composition": "Li7La3Zr2O12", "property": "conductivity",
         "value": 3e-4, "unit": "S/cm", "doi": "10.1/d", "status": "approved"},
    ]}))
    groups = build_consensus_db(str(q), str(tmp_path / "none.parquet"), include_benchmarks=False)
    assert set(groups) == {"Li6PS5Cl", "Li7La3Zr2O12"}
    cr = groups["Li6PS5Cl"]
    assert cr.n_sigma == 3
    assert cr.n_papers == 3
    assert cr.median_sigma == pytest.approx(1e-3)
    assert cr.sigma_ci95 is not None
    assert cr.temp_bins == [{"bin_c": 0, "count": 2}, {"bin_c": 50, "count": 1}]
    assert cr.median_ea is None


def test_build_consensus_db_outlier_flag(tmp_path):
    q = tmp_path / "queue.json"
    q.write_text(json.dumps({"items": [
        {"review_id": "a", "composition": "Li6PS5Cl", "property": "conductivity",
         "value": 1e-3, "unit": "S/cm", "doi": "10.1/a", "status": "approved"},
        {"review_id": "b", "composition": "Li6PS5Cl", "property": "conductivity",
         "value": 2e-3, "unit": "S/cm", "doi": "10.1/b", "status": "approved"},
        {"review_id": "c", "composition": "Li6PS5Cl", "property": "conductivity",
         "value": 5e-4, "unit": "S/cm", "doi": "10.1/c", "status": "approved"},
        # 100x off -> outlier
        {"review_id": "d", "composition": "Li6PS5Cl", "property": "conductivity",
         "value": 1e-1, "unit": "S/cm", "doi": "10.1/d", "status": "approved"},
    ]}))
    groups = build_consensus_db(str(q), str(tmp_path / "none.parquet"), include_benchmarks=False)
    assert len(groups["Li6PS5Cl"].outliers) == 1
    assert groups["Li6PS5Cl"].outliers[0]["sigma"] == pytest.approx(1e-1)


def test_summary_counts(tmp_path):
    q = tmp_path / "queue.json"
    q.write_text(json.dumps({"items": [
        {"review_id": "a", "composition": "Li6PS5Cl", "property": "conductivity",
         "value": 1e-3, "unit": "S/cm", "doi": "10.1/a", "status": "approved"},
        {"review_id": "b", "composition": "Li7La3Zr2O12", "property": "conductivity",
         "value": 3e-4, "unit": "S/cm", "doi": "10.1/b", "status": "approved"},
    ]}))
    groups = build_consensus_db(str(q), str(tmp_path / "none.parquet"), include_benchmarks=False)
    s = summary(groups)
    assert s["materials_total"] == 2
    assert s["total_sigma_records"] == 2
    assert s["materials_with_consensus_n3"] == 0


def test_to_parquet(tmp_path):
    q = tmp_path / "queue.json"
    q.write_text(json.dumps({"items": [
        {"review_id": "a", "composition": "Li6PS5Cl", "property": "conductivity",
         "value": 1e-3, "unit": "S/cm", "doi": "10.1/a", "status": "approved"},
    ]}))
    groups = build_consensus_db(str(q), str(tmp_path / "none.parquet"), include_benchmarks=False)
    out = tmp_path / "db.parquet"
    to_parquet(groups, str(out))
    assert out.exists()
    import pandas as pd
    df = pd.read_parquet(out)
    assert "group" in df.columns
    assert len(df) == 1


# ---------------------------------------------------------------------------
# review rule: consensus_db
# ---------------------------------------------------------------------------

def _ctx(db):
    return ReviewContext(consensus_db=db)


def test_rule_consensus_db_pass_within_range():
    ctx = _ctx({"Li6PS5Cl": {"n_sigma": 3, "median_sigma": 1e-3, "n_papers": 3}})
    rec = {"composition": "Li6PS5Cl", "property": "conductivity",
           "value": 1e-3, "unit": "S/cm", "normalized_sigma": 1e-3}
    r = rule_consensus_db(rec, ctx)
    assert r.status.value == "PASS"


def test_rule_consensus_db_warning_outlier():
    ctx = _ctx({"Li6PS5Cl": {"n_sigma": 3, "median_sigma": 1e-3, "n_papers": 3}})
    rec = {"composition": "Li6PS5Cl", "property": "conductivity",
           "value": 1e-1, "unit": "S/cm", "normalized_sigma": 1e-1}
    r = rule_consensus_db(rec, ctx)
    assert r.status.value == "WARNING"
    assert "100x" in r.message


def test_rule_consensus_db_pass_undersampled_group():
    ctx = _ctx({"Li6PS5Cl": {"n_sigma": 2, "median_sigma": 1e-3, "n_papers": 2}})
    rec = {"composition": "Li6PS5Cl", "property": "conductivity",
           "value": 1e-1, "unit": "S/cm", "normalized_sigma": 1e-1}
    r = rule_consensus_db(rec, ctx)
    assert r.status.value == "PASS"


def test_rule_consensus_db_no_db_passes():
    rec = {"composition": "Li6PS5Cl", "property": "conductivity",
           "value": 1e-1, "unit": "S/cm"}
    r = rule_consensus_db(rec, ReviewContext())
    assert r.status.value == "PASS"
