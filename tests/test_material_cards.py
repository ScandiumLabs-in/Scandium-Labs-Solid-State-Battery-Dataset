"""Tests for Material Cards — the Material → Paper → Experiment → Measurement
hierarchy layer built on top of the consensus database."""

from __future__ import annotations

import json
import math

from pytest import approx

from ssb_dataset.literature.consensus_db import build_consensus_db, _normalize_temp
from ssb_dataset.literature.material_cards import (
    build_all_cards,
    build_material_card,
    _papers_from_measurements,
    _score_consensus,
)


# ---------------------------------------------------------------------------
# consensus_db.py: preserved measurement detail
# ---------------------------------------------------------------------------

def test_measurements_preserved_in_group(tmp_path):
    q = tmp_path / "queue.json"
    q.write_text(json.dumps({"items": [
        {"review_id": "a", "composition": "Li6PS5Cl", "property": "conductivity",
         "value": 1e-3, "unit": "S/cm", "doi": "10.1/a", "status": "approved",
         "page": "4", "reviewer": "human-1", "measurement_method": "EIS",
         "evidence_sentence": "measured at 25 C"},
        {"review_id": "b", "composition": "Li6PS5Cl", "property": "activation_energy",
         "value": 0.25, "unit": "eV", "doi": "10.1/b", "status": "approved"},
    ]}))
    groups = build_consensus_db(str(q), str(tmp_path / "none.parquet"), include_benchmarks=False)
    ms = groups["Li6PS5Cl"].measurements
    assert len(ms) == 2
    cond = next(m for m in ms if m["property"] == "conductivity")
    assert cond["sigma_S_per_cm"] == approx(1e-3)
    assert cond["page"] == "4"
    assert cond["reviewer"] == "human-1"
    assert cond["measurement_method"] == "EIS"
    assert cond["evidence_sentence"] == "measured at 25 C"
    ea = next(m for m in ms if m["property"] == "activation_energy")
    assert ea["activation_energy_eV"] == approx(0.25)


def test_normalize_temp_number():
    assert _normalize_temp(25) == 25.0
    assert _normalize_temp(298.0) == 298.0


def test_normalize_temp_k_range():
    assert _normalize_temp({"min_K": 298.0, "max_K": 298.0}) == approx(24.85, abs=0.01)


def test_normalize_temp_c_range():
    assert _normalize_temp({"min_C": 20.0, "max_C": 30.0}) == approx(25.0)


def test_normalize_temp_none():
    assert _normalize_temp(None) is None


# ---------------------------------------------------------------------------
# material_cards.py
# ---------------------------------------------------------------------------

def test_score_consensus_strong():
    s = _score_consensus({
        "n_sigma": 4,
        "sigma_values": [1e-3, 1.2e-3, 9e-4, 1.1e-3],
        "ea_values": [0.3, 0.32],
        "outliers": [],
        "temp_counts": 3,
    })
    assert s >= 75


def test_score_consensus_penalizes_outlier():
    s = _score_consensus({
        "n_sigma": 4,
        "sigma_values": [1e-3, 1.2e-3, 9e-4, 1.1e-3],
        "ea_values": [],
        "outliers": [{"sigma": 1e-1}],
        "temp_counts": 0,
    })
    assert s < 75


def test_papers_from_measurements_groups_by_doi():
    ms = [
        {"doi": "10.1/a", "property": "conductivity", "sigma_S_per_cm": 1e-3,
         "temperature_celsius": 25},
        {"doi": "10.1/a", "property": "activation_energy", "activation_energy_eV": 0.3},
        {"doi": "10.1/b", "property": "conductivity", "sigma_S_per_cm": 2e-3,
         "temperature_celsius": 25},
    ]
    papers = _papers_from_measurements(ms)
    assert len(papers) == 2
    by_doi = {p["doi"]: p for p in papers}
    assert by_doi["10.1/a"]["n_sigma"] == 1
    assert by_doi["10.1/a"]["n_ea"] == 1
    assert by_doi["10.1/b"]["n_sigma"] == 1


def test_build_material_card(tmp_path):
    q = tmp_path / "queue.json"
    q.write_text(json.dumps({"items": [
        {"review_id": "a", "composition": "Li7La3Zr2O12", "property": "conductivity",
         "value": 3e-4, "unit": "S/cm", "doi": "10.1/a", "status": "approved",
         "temperature_celsius": 25, "family": "garnet"},
        {"review_id": "b", "composition": "Li7La3Zr2O12", "property": "conductivity",
         "value": 1e-3, "unit": "S/cm", "doi": "10.1/b", "status": "approved",
         "temperature_celsius": 25, "family": "garnet"},
    ]}))
    groups = build_consensus_db(str(q), str(tmp_path / "none.parquet"), include_benchmarks=False)
    cons = groups["Li7La3Zr2O12"].to_dict()
    card = build_material_card("Li7La3Zr2O12", cons, {
        "Li7La3Zr2O12": {"space_group": "I4_1/acd", "band_gap": 4.4, "formation_energy_per_atom": -3.1},
    })
    assert card.family == "garnet"
    assert card.n_papers == 2
    assert card.n_sigma == 2
    assert card.median_sigma == approx(10 ** ((math.log10(3e-4) + math.log10(1e-3)) / 2), rel=1e-6)
    assert card.temperature_range_c == (25.0, 25.0)
    assert card.temperature_counts == 2
    assert card.consensus_score >= 25
    assert card.structure["band_gap"] == 4.4
    assert len(card.papers) == 2


def test_build_all_cards_sorted():
    consensus = {
        "A": {
            "n_papers": 3, "n_sigma": 3, "n_ea": 1, "n_measurements": 4,
            "median_sigma": 1e-3, "sigma_ci95": (8e-4, 1.2e-3),
            "min_sigma": 8e-4, "max_sigma": 1.2e-3, "median_ea": 0.3,
            "sigma_values": [1e-3, 1.1e-3, 9e-4],
            "ea_values": [0.3], "outliers": [], "dois": ["10.1/a", "10.1/b", "10.1/c"],
            "families": ["argyrodite"], "temperature_histogram": [{"bin_c": 0, "count": 1}],
            "measurements": [
                {"doi": "10.1/a", "property": "conductivity", "sigma_S_per_cm": 1e-3,
                 "temperature_celsius": 25},
                {"doi": "10.1/b", "property": "conductivity", "sigma_S_per_cm": 1.1e-3,
                 "temperature_celsius": 25},
                {"doi": "10.1/c", "property": "conductivity", "sigma_S_per_cm": 9e-4,
                 "temperature_celsius": 25},
                {"doi": "10.1/a", "property": "activation_energy", "activation_energy_eV": 0.3},
            ],
        },
        "B": {
            "n_papers": 1, "n_sigma": 1, "n_ea": 0, "n_measurements": 1,
            "median_sigma": 1e-5, "sigma_ci95": None, "min_sigma": 1e-5,
            "max_sigma": 1e-5, "median_ea": None, "sigma_values": [1e-5],
            "ea_values": [], "outliers": [], "dois": ["10.1/x"],
            "families": ["halide"], "temperature_histogram": [],
            "measurements": [
                {"doi": "10.1/x", "property": "conductivity", "sigma_S_per_cm": 1e-5},
            ],
        },
    }
    cards = build_all_cards(consensus)
    assert set(cards) == {"A", "B"}
    assert cards["A"].consensus_score > cards["B"].consensus_score
    assert cards["B"].consensus_verdict in ("weak consensus", "no consensus")
    d = cards["A"].to_dict()
    assert d["material"] == "A"
    assert len(d["papers"]) == 3



# ---------------------------------------------------------------------------
# M11 quality score
# ---------------------------------------------------------------------------

def test_quality_score_grade_monotonic():
    from ssb_dataset.literature.material_cards import _quality_score, _quality_grade, _GRADE_RANK
    high = _quality_score({"agreement_grade": "A+", "n_papers": 5, "n_sigma": 6,
                           "n_ea": 1, "metadata_completeness": 1.0, "outliers": []})
    low = _quality_score({"agreement_grade": "D", "n_papers": 1, "n_sigma": 1,
                          "n_ea": 0, "metadata_completeness": 0.0, "outliers": [{"sigma": 1}]})
    assert high[0] > low[0]
    assert high[0] == 90
    assert low[0] < 30
    assert _quality_grade(90) == "A"
    assert _quality_grade(60) == "C"
    assert _quality_grade(40) == "D"


def test_quality_score_outlier_penalty():
    from ssb_dataset.literature.material_cards import _quality_score
    base = {"agreement_grade": "A", "n_papers": 3, "n_sigma": 4, "n_ea": 1,
            "metadata_completeness": 1.0, "outliers": []}
    clean = _quality_score(base)[0]
    penalized = _quality_score({**base, "outliers": [{"sigma": 1e-2}, {"sigma": 1e-1}]})[0]
    assert clean - penalized == 10


def test_metadata_completeness():
    from ssb_dataset.literature.material_cards import _metadata_completeness
    ms = [
        {"sigma_S_per_cm": 1e-3, "temperature_celsius": 25, "measurement_method": "EIS"},
        {"sigma_S_per_cm": 1e-4, "temperature_celsius": 25, "measurement_method": None},
        {"sigma_S_per_cm": 1e-5, "temperature_celsius": None, "measurement_method": "EIS"},
        {"sigma_S_per_cm": None, "temperature_celsius": 25, "measurement_method": "EIS"},
    ]
    assert _metadata_completeness(ms) == approx(1 / 3)


def test_card_quality_and_sigma_by_temp_emitted(tmp_path):
    q = tmp_path / "queue.json"
    q.write_text(json.dumps({"items": [
        {"review_id": "a", "composition": "Li6PS5Cl", "property": "conductivity",
         "value": 1e-3, "unit": "S/cm", "doi": "10.1/a", "status": "approved",
         "temperature_celsius": 25, "family": "argyrodite", "measurement_method": "EIS"},
        {"review_id": "b", "composition": "Li6PS5Cl", "property": "conductivity",
         "value": 9e-4, "unit": "S/cm", "doi": "10.1/b", "status": "approved",
         "temperature_celsius": 25, "family": "argyrodite", "measurement_method": "EIS"},
        {"review_id": "c", "composition": "Li6PS5Cl", "property": "activation_energy",
         "value": 0.26, "unit": "eV", "doi": "10.1/a", "status": "approved",
         "temperature_celsius": 25, "family": "argyrodite"},
    ]}))
    groups = build_consensus_db(str(q), str(tmp_path / "none.parquet"), include_benchmarks=False)
    cons = groups["Li6PS5Cl"].to_dict()
    card = build_material_card("Li6PS5Cl", cons)
    d = card.to_dict()
    assert d["quality_score"] > 0
    assert d["quality_grade"] in ("A", "B", "C", "D")
    assert d["metadata_completeness"] == approx(1.0)
    assert isinstance(d["sigma_by_temp"], list)
    assert any(b["temp_c"] == 25 and b["n"] == 2 for b in d["sigma_by_temp"])


def test_source_id_material_name_not_treated_as_doi(tmp_path):
    import pandas as pd
    canon = tmp_path / "canon.parquet"
    pd.DataFrame({
        "identity.composition": ["Li7La3Zr2O12"],
        "identity.material_id": ["Li7La3Zr2O12"],
        "identity.source_id": ["Li7La3Zr2O12"],
        "text_provenance.source_doi": [None],
        "ion_transport.label_available": [True],
        "ion_transport.sigma_RT": [3e-4],
    }).to_parquet(canon)
    groups = build_consensus_db(str(tmp_path / "none.json"), str(canon), include_benchmarks=False)
    g = groups["Li7La3Zr2O12"]
    assert g.doiss == []
    assert g.n_papers == 0
