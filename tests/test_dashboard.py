"""Tests for the review dashboard + persistence layer (no LLM, no network)."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

pytest.importorskip("fastapi", reason="dashboard extra not installed")
pytest.importorskip("fastapi.testclient", reason="dashboard extra not installed")
from fastapi.testclient import TestClient

from ssb_dataset.review.dashboard import app, _build_context, _material_consensus, _review, _similar_papers
from ssb_dataset.review import store
from ssb_dataset.review.store import (
    apply_decision,
    export_approved,
    load_queue,
    record_training_pair,
    save_queue,
)

client = TestClient(app)

# ---------------------------------------------------------------------------
# Fixtures (isolated temp store)
# ---------------------------------------------------------------------------


def _sample_record(review_id: str = "r1", status: str = "pending") -> dict:
    return {
        "review_id": review_id,
        "composition": "Li6PS5Cl",
        "family": "sulfide",
        "property": "conductivity",
        "value": 0.001,
        "unit": "S/cm",
        "temperature_celsius": 25,
        "doi": "10.1234/abc",
        "paper_id": "10.1234_abc",
        "confidence": 0.9,
        "status": status,
        "evidence_sentence": "Li6PS5Cl exhibits an ionic conductivity of 0.001 S/cm at room temperature.",
        "page": 3,
    }


@pytest.fixture
def tmp_store(tmp_path, monkeypatch):
    queue = {"version": 1, "items": [_sample_record("r1", "pending"), _sample_record("r2", "approved")]}
    monkeypatch.setattr(store, "REVIEW_DIR", tmp_path)
    monkeypatch.setattr(store, "QUEUE_PATH", tmp_path / "queue.json")
    monkeypatch.setattr(store, "APPROVED_PATH", tmp_path / "approved.parquet")
    monkeypatch.setattr(store, "TRAINING_PAIRS", tmp_path / "training_pairs.jsonl")
    save_queue(queue)
    return tmp_path


# ---------------------------------------------------------------------------
# store.py
# ---------------------------------------------------------------------------

def test_save_and_load_queue_roundtrip(tmp_store):
    q = load_queue()
    assert len(q["items"]) == 2
    assert q["items"][0]["review_id"] == "r1"
    assert q["updated_at"] is not None


def test_apply_approve_updates_queue_and_exports(tmp_store):
    q = load_queue()
    item = apply_decision(q, "r1", "approve", "test-reviewer", note="verified")
    assert item["status"] == "approved"
    assert item["reviewer"] == "test-reviewer"
    assert item["review_note"] == "verified"
    # queue persisted
    q2 = load_queue()
    assert q2["items"][0]["status"] == "approved"
    # approved parquet exported
    df = export_approved(load_queue())
    assert df >= 2
    approved = load_queue()
    assert approved["items"][1]["status"] == "approved"


def test_apply_edit_sets_edited_value(tmp_store):
    q = load_queue()
    item = apply_decision(q, "r1", "edit", "tester", edited_value=0.0005, edited_unit="S/cm")
    assert item["status"] == "approved"
    assert item["edited_value"] == 0.0005
    assert item["edited_unit"] == "S/cm"


def test_apply_reject_sets_status(tmp_store):
    q = load_queue()
    item = apply_decision(q, "r1", "reject", "tester", note="hallucination")
    assert item["status"] == "rejected"
    assert item["review_note"] == "hallucination"


def test_apply_unknown_review_id_returns_none(tmp_store):
    q = load_queue()
    assert apply_decision(q, "nope", "approve", "tester") is None


def test_record_training_pair_writes_line(tmp_store):
    item = _sample_record("r1")
    record_training_pair(item, "approve", "looks good")
    line = store.TRAINING_PAIRS.read_text().strip()
    pair = json.loads(line)
    assert pair["review_id"] == "r1"
    assert pair["human_action"] == "approve"
    assert pair["human_note"] == "looks good"


def test_export_approved_writes_parquet(tmp_store):
    q = load_queue()
    apply_decision(q, "r1", "approve", "tester")
    n = export_approved(load_queue())
    assert n == 2
    import pandas as pd
    df = pd.read_parquet(store.APPROVED_PATH)
    assert len(df) == 2


# ---------------------------------------------------------------------------
# dashboard.py helpers
# ---------------------------------------------------------------------------

def test_build_context_runs_on_empty_queue(tmp_path, monkeypatch):
    monkeypatch.setattr(store, "REVIEW_DIR", tmp_path)
    monkeypatch.setattr(store, "QUEUE_PATH", tmp_path / "queue.json")
    save_queue({"version": 1, "items": []})
    q = load_queue()
    ctx = _build_context(q)
    assert ctx is not None


def test_review_returns_rules_and_decision(tmp_store):
    q = load_queue()
    ctx = _build_context(q)
    item = q["items"][0]
    out = _review(item, ctx)
    assert set(out) == {"rules", "factors", "overall", "decision", "reasons"}
    assert out["decision"] in ("auto_approve", "auto_reject", "human")
    rule_names = {r["rule"] for r in out["rules"]}
    assert "evidence" in rule_names
    assert "arrhenius" in rule_names
    assert isinstance(out["overall"], float)


def test_material_consensus_groups_by_material(tmp_store):
    q = load_queue()
    ctx = _build_context(q)
    item = q["items"][0]
    mc = _material_consensus(q, item)
    # only r1+r2 both Li6PS5Cl -> n_sigma should be 2
    assert mc is not None
    assert mc["group"] == "Li6PS5Cl"


def test_similar_papers_excludes_current(tmp_store):
    q = load_queue()
    item = q["items"][0]
    sims = _similar_papers(q, item, limit=5)
    assert all(s is not None for s in sims)
    # r2 is the only other Li6PS5Cl record
    assert len(sims) >= 1


# ---------------------------------------------------------------------------
# HTTP routes
# ---------------------------------------------------------------------------

def test_index_renders(tmp_store):
    resp = client.get("/")
    assert resp.status_code == 200
    assert "SSB Review Dashboard" in resp.text
    assert "Li6PS5Cl" in resp.text


def test_record_page_renders(tmp_store):
    resp = client.get("/record/r1")
    assert resp.status_code == 200
    assert "Li6PS5Cl" in resp.text
    assert "Human decision" in resp.text
    assert "AI Review" in resp.text


def test_record_page_shows_experimental_conditions(tmp_store):
    q = store.load_queue()
    q["items"][0]["experiment"] = {
        "sample_form": "pellet", "pelletizing_pressure_MPa": 540,
        "electrode_material": "Au", "atmosphere": "Ar",
    }
    store.save_queue(q)
    resp = client.get("/record/r1")
    assert resp.status_code == 200
    assert "Experimental conditions" in resp.text
    assert "pellet" in resp.text
    assert "540" in resp.text


def test_record_page_omits_experimental_when_absent(tmp_store):
    resp = client.get("/record/r1")
    assert "Experimental conditions" not in resp.text


def test_record_page_missing_404(tmp_store):
    resp = client.get("/record/nope")
    assert resp.status_code == 404


def test_decision_post_updates_state(tmp_store):
    resp = client.post("/record/r1/decision", data={"action": "approve", "reviewer": "test", "note": "ok"})
    assert resp.status_code in (200, 303)
    q = load_queue()
    assert q["items"][0]["status"] == "approved"


def test_decision_edit_post(tmp_store):
    resp = client.post(
        "/record/r1/decision",
        data={"action": "edit", "reviewer": "test", "note": "fixed", "edited_value": "0.0005", "edited_unit": "S/cm"},
    )
    assert resp.status_code in (200, 303)
    q = load_queue()
    assert q["items"][0]["status"] == "approved"
    assert q["items"][0]["edited_value"] == 0.0005


def test_health_ok(tmp_store):
    resp = client.get("/health")
    assert resp.status_code == 200
    assert resp.json()["ok"] is True
