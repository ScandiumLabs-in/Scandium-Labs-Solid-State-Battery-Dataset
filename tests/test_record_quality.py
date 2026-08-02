"""Tests for A3/A4 record quality score + Gold/Silver/Bronze tier assignment."""

from __future__ import annotations

from ssb_dataset.literature.record_quality import (
    QualityTier,
    assign_tier,
    quality_grade,
    score_record,
)


def _complete_record() -> dict:
    return dict(
        reviewer="human-1",
        page="4",
        table_number="1",
        evidence_table_number="2",
        evidence_sentence="sigma = 1e-3 S/cm at 25 C",
        temperature_celsius=25,
        measurement_method="EIS",
        conductivity_type="total",
        sample_form="pellet",
        electrode_material="Au",
        atmosphere="Ar",
        relative_density_pct=97,
        agreement_grade="A+",
        n_papers=4,
        sigma_vs_T_curve=[(298, 1e-3), (313, 2e-3), (333, 4e-3)],
        activation_energy_eV=0.28,
        sigma_S_per_cm=1e-3,
    )


# ── Grade mapping ─────────────────────────────────────────────────────────────


def test_grade_bounds():
    assert quality_grade(95) == "A+"
    assert quality_grade(90) == "A+"
    assert quality_grade(85) == "A"
    assert quality_grade(70) == "B"
    assert quality_grade(50) == "C"
    assert quality_grade(20) == "D"


# ── Complete record reaches Gold ──────────────────────────────────────────────


def test_complete_record_is_gold():
    r = score_record(_complete_record())
    assert r["quality_score"] >= 85
    assert r["quality_tier"] == QualityTier.gold
    assert r["quality_grade"] in ("A+", "A")


def test_gold_requires_human():
    rec = _complete_record()
    rec.pop("reviewer")
    r = score_record(rec)
    assert r["quality_tier"] != QualityTier.gold
    assert r["quality_tier"] == QualityTier.bronze or r["quality_tier"] == QualityTier.rejected


def test_gold_requires_evidence():
    rec = _complete_record()
    rec["page"] = None
    rec["evidence_sentence"] = ""
    r = score_record(rec)
    assert r["quality_tier"] != QualityTier.gold


def test_gold_requires_metadata_pair():
    rec = _complete_record()
    rec.pop("measurement_method")
    r = score_record(rec)
    assert r["quality_tier"] != QualityTier.gold


# ── Silver / Bronze / Rejected ────────────────────────────────────────────────


def test_silver_single_paper_human_verified():
    rec = _complete_record()
    rec["agreement_grade"] = ""
    rec["n_papers"] = 1
    rec["relative_density_pct"] = None
    rec["sample_form"] = None
    rec["electrode_material"] = None
    rec["atmosphere"] = None
    rec["sigma_vs_T_curve"] = []
    rec.pop("activation_energy_eV")
    r = score_record(rec)
    assert r["quality_tier"] == QualityTier.silver


def test_bronze_ai_only_high_score():
    rec = _complete_record()
    rec.pop("reviewer")
    r = score_record(rec)
    # Without a human, AI-only records cap at bronze (or rejected below 80).
    assert r["quality_tier"] in (QualityTier.bronze, QualityTier.rejected)


def test_dft_native_rejected():
    rec = _complete_record()
    rec["confidence_tier"] = "dft_native"
    assert assign_tier(rec) == QualityTier.rejected


def test_queue_rejected_is_rejected():
    rec = _complete_record()
    rec["status"] = "rejected"
    assert assign_tier(rec) == QualityTier.rejected


# ── Components ────────────────────────────────────────────────────────────────


def test_outlier_penalty_applied():
    rec = _complete_record()
    rec["is_outlier"] = True
    r = score_record(rec)
    assert r["quality_components"]["outlier_penalty"] == -10
    assert r["quality_score"] < score_record(_complete_record())["quality_score"]


def test_missing_evidence_caps_score():
    rec = _complete_record()
    rec["page"] = None
    rec["evidence_sentence"] = ""
    rec.pop("reviewer")
    r = score_record(rec)
    assert r["quality_score"] <= 30


def test_evidence_quality_components():
    rec = _complete_record()
    r = score_record(rec)
    assert r["quality_components"]["evidence_quality"] == 20


def test_curve_depth_bonus():
    rec = _complete_record()
    base = score_record(rec)
    rec2 = dict(rec)
    rec2["sigma_vs_T_curve"] = []
    no_curve = score_record(rec2)
    assert base["quality_components"]["depth"] > no_curve["quality_components"]["depth"]


def test_score_bounded_0_100():
    r = score_record(_complete_record())
    assert 0 <= r["quality_score"] <= 100
