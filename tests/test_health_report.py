"""Tests for Phase C health report + A3 consensus-distribution extensions."""

from __future__ import annotations

import json
from pathlib import Path

import pandas as pd
import pytest

from ssb_dataset.literature.consensus_db import (
    _value_distribution,
    build_consensus_db,
)
from scripts.build_health_report import _load_json, build_health_report


# ---------------------------------------------------------------------------
# A3: consensus distribution fields
# ---------------------------------------------------------------------------

def test_method_distribution_aggregated(tmp_path):
    q = tmp_path / "queue.json"
    q.write_text(json.dumps({"items": [
        {"review_id": "a", "composition": "Li6PS5Cl", "property": "conductivity",
         "value": 1e-3, "unit": "S/cm", "doi": "10.1/a", "status": "approved",
         "measurement_method": "EIS"},
        {"review_id": "b", "composition": "Li6PS5Cl", "property": "conductivity",
         "value": 9e-4, "unit": "S/cm", "doi": "10.1/b", "status": "approved",
         "measurement_method": "EIS"},
        {"review_id": "c", "composition": "Li6PS5Cl", "property": "conductivity",
         "value": 1.1e-3, "unit": "S/cm", "doi": "10.1/c", "status": "approved",
         "measurement_method": "DC"},
    ]}))
    groups = build_consensus_db(str(q), str(tmp_path / "none.parquet"), include_benchmarks=False)
    g = groups["Li6PS5Cl"].to_dict()
    methods = {m["value"]: m["n"] for m in g["method_distribution"]}
    assert methods == {"EIS": 2, "DC": 1}


def test_pressure_density_distributions_from_experiment(tmp_path):
    q = tmp_path / "queue.json"
    q.write_text(json.dumps({"items": [
        {"review_id": "a", "composition": "Li6PS5Cl", "property": "conductivity",
         "value": 1e-3, "unit": "S/cm", "doi": "10.1/a", "status": "approved",
         "experiment": {"pelletizing_pressure_MPa": 300, "relative_density_pct": 97}},
        {"review_id": "b", "composition": "Li6PS5Cl", "property": "conductivity",
         "value": 2e-4, "unit": "S/cm", "doi": "10.1/b", "status": "approved",
         "experiment": {"pelletizing_pressure_MPa": 540, "relative_density_pct": 73}},
    ]}))
    groups = build_consensus_db(str(q), str(tmp_path / "none.parquet"), include_benchmarks=False)
    g = groups["Li6PS5Cl"].to_dict()
    press = {m["value"]: m["n"] for m in g["pressure_distribution"]}
    dens = {m["value"]: m["n"] for m in g["density_distribution"]}
    assert press == {300.0: 1, 540.0: 1}
    assert dens == {97.0: 1, 73.0: 1}


def test_publication_years_from_doi_cache(tmp_path):
    import ssb_dataset.literature.consensus_db as cdb
    # Point the cache loader at a tmp file so the test is hermetic.
    cache = tmp_path / "doi_years_cache.json"
    cache.write_text(json.dumps({"10.1/a": 2020, "10.1/b": 2022}))
    original = cdb._DOI_YEARS_CACHE
    cdb._DOI_YEARS_CACHE = cache
    try:
        q = tmp_path / "queue.json"
        q.write_text(json.dumps({"items": [
            {"review_id": "a", "composition": "Li6PS5Cl", "property": "conductivity",
             "value": 1e-3, "unit": "S/cm", "doi": "10.1/a", "status": "approved"},
            {"review_id": "b", "composition": "Li6PS5Cl", "property": "conductivity",
             "value": 9e-4, "unit": "S/cm", "doi": "10.1/b", "status": "approved"},
        ]}))
        groups = build_consensus_db(str(q), str(tmp_path / "none.parquet"), include_benchmarks=False)
        g = groups["Li6PS5Cl"].to_dict()
        assert g["publication_years"] == [2020, 2022]
        assert g["n_papers"] == 2
    finally:
        cdb._DOI_YEARS_CACHE = original


def test_value_distribution_ignores_empty():
    ms = [{"x": 1}, {"x": None}, {"x": ""}, {"x": 1}]
    assert _value_distribution(ms, "x") == [{"value": 1, "n": 2}]


# ---------------------------------------------------------------------------
# Phase C: health report
# ---------------------------------------------------------------------------

@pytest.fixture
def fake_dataset(tmp_path, monkeypatch):
    import scripts.build_health_report as hr
    canon = tmp_path / "canonical.parquet"
    pd.DataFrame({
        "identity.composition": ["A", "B", "C", "D"],
        "identity.family": ["garnet", "garnet", "halide", "sulfide"],
        "ion_transport.label_available": [True, True, True, True],
        "ion_transport.sigma_RT": [1e-3, 2e-3, 3e-3, 4e-3],
        "ion_transport.temperature_range_measured": [298, 298, 298, None],
        "ion_transport.measurement_method": ["EIS", None, "EIS", None],
        "ion_transport.conductivity_type": ["total", "bulk", "total", "bulk"],
        "experiment": [
            {"pelletizing_pressure_MPa": 300},
            {}, {}, {},
        ],
        "text_provenance.evidence_page": ["3", None, "5", None],
        "text_provenance.evidence_sentence": ["a", "b", None, None],
    }).to_parquet(canon)
    monkeypatch.setattr(hr, "CANONICAL", canon)
    monkeypatch.setattr(hr, "CONSENSUS", tmp_path / "consensus.json")
    monkeypatch.setattr(hr, "CARDS", tmp_path / "cards.json")
    monkeypatch.setattr(hr, "QUEUE", tmp_path / "queue.json")
    return hr


def test_coverage_percentages(fake_dataset):
    hr = fake_dataset
    df = pd.read_parquet(hr.CANONICAL)
    cov = hr.coverage(df)
    assert cov["temperature_celsius"] == 75.0
    assert cov["measurement_method"] == 50.0
    assert cov["pelletizing_pressure_MPa"] == 25.0
    assert cov["page"] == 50.0
    assert cov["evidence_sentence"] == 50.0


def test_family_balance(fake_dataset):
    hr = fake_dataset
    df = pd.read_parquet(hr.CANONICAL)
    assert hr.family_balance(df) == {"garnet": 2, "halide": 1, "sulfide": 1}


def test_build_health_report_aggregates(fake_dataset):
    hr = fake_dataset
    hr.CONSENSUS.write_text(json.dumps({
        "Li6PS5Cl": {"n_sigma": 3, "n_ea": 1, "n_papers": 3, "agreement_grade": "A+",
                     "publication_years": [2022], "sigma_by_temp": [{"temp_c": 25}],
                     "outliers": []},
    }))
    hr.CARDS.write_text(json.dumps({
        "Li6PS5Cl": {"quality_score": 62, "quality_grade": "C"},
    }))
    hr.QUEUE.write_text(json.dumps({"items": [
        {"status": "pending"}, {"status": "approved"}, {"status": "rejected"},
        {"status": "approved", "experiment": {"sample_form": "pellet"}},
    ]}))
    rep = hr.build_health_report()
    assert rep["verified_records"] == 4
    assert rep["materials_total"] == 1
    assert rep["materials_with_consensus_n3"] == 1
    assert rep["materials_with_pub_years"] == 1
    assert rep["queue_with_experiment_block"] == 1
    assert rep["queue_pending"] == 1
    assert rep["quality_score_avg"] == 62.0


def test_render_markdown_smoke(fake_dataset):
    rep = fake_dataset.build_health_report()
    md = fake_dataset.render_markdown(rep)
    assert "Field coverage" in md
    assert "Missing-data report" in md
    assert "Family balance" in md
