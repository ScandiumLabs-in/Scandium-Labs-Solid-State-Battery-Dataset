"""Tests for the AI review engine (rules, scorer, decision).

These are deterministic — no LLM calls. Fixtures mimic queue records carrying
the fields the verifier/autoflag layers stamp.
"""

from __future__ import annotations

import pytest

from ssb_dataset.pipeline.consensus import compute_consensus
from ssb_dataset.review import decide, evaluate_rules, score_record
from ssb_dataset.review.decision import ReviewDecision
from ssb_dataset.review.rules import ReviewContext, RuleStatus
from ssb_dataset.review.scorer import ReviewFactors


def _rec(**kw):
    base = {
        "review_id": "r1",
        "composition": "Li2ZrCl6",
        "family": "halide",
        "property": "conductivity",
        "value": 0.00081,
        "unit": "S/cm",
        "confidence": 0.7,
        "status": "pending",
    }
    base.update(kw)
    return base


def _clean_rec(**kw):
    """A record with all the verified/autoflag fields stamped, as the real
    pipeline produces them."""
    r = _rec(
        normalized_sigma=0.00081,
        sigma_multiplier=1.0,
        normalization_issues=[],
        verified_verdict="FOUND",
        verified_snippet="0.81 mS cm-1 at room temperature",
        verified_page=3,
        verified_values=["sigma=8.100e-04"],
        verifier_consensus=True,
        auto_check_severity=None,
        auto_check_note=None,
    )
    r.update(kw)
    return r


def _ctx(records=None):
    records = records or []
    if records:
        from ssb_dataset.pipeline.normalization import normalize_record_units

        for r in records:
            normalize_record_units(r)
        consensus = compute_consensus(records)
    else:
        consensus = None
    return ReviewContext(
        consensus=consensus,
        approved_records=[],
        pending_records=records,
        family_alias=lambda f: (f or "").lower(),
    )


# ---------------------------------------------------------------------------
# Rule engine
# ---------------------------------------------------------------------------

def test_clean_record_all_pass():
    rec = _clean_rec()
    results = evaluate_rules(rec, _ctx())
    statuses = {r.rule: r.status for r in results}
    assert all(s == RuleStatus.PASS for s in statuses.values()), statuses


def test_missing_value_is_fail():
    rec = _clean_rec(value=None)
    results = evaluate_rules(rec, _ctx())
    s = {r.rule: r.status for r in results}
    assert s["value_present"] == RuleStatus.FAIL


def test_negative_value_is_fail():
    rec = _clean_rec(value=-1e-3)
    results = evaluate_rules(rec, _ctx())
    s = {r.rule: r.status for r in results}
    assert s["value_nonneg"] == RuleStatus.FAIL


def test_no_evidence_is_fail():
    rec = _clean_rec(verified_verdict=None, verified_snippet=None, verified_page=None)
    results = evaluate_rules(rec, _ctx())
    s = {r.rule: r.status for r in results}
    assert s["evidence"] == RuleStatus.FAIL


def test_evidence_but_no_page_is_warning():
    rec = _clean_rec(verified_page=None)
    results = evaluate_rules(rec, _ctx())
    s = {r.rule: r.status for r in results}
    assert s["evidence"] == RuleStatus.PASS
    assert s["page"] == RuleStatus.WARNING


def test_family_range_violation_is_warning_not_fail():
    """Verified low-Ea argyrodite (0.09 eV) must not be a FAIL."""
    rec = _clean_rec(
        composition="Li5.4Al0.1PS4.7Cl1.3",
        family="argyrodite",
        property="activation_energy",
        value=0.09,
        unit="eV",
        normalized_ea=0.09,
        verified_values=["Ea=1.000e-01"],
    )
    results = evaluate_rules(rec, _ctx())
    s = {r.rule: r.status for r in results}
    assert s["family_range"] == RuleStatus.WARNING
    assert s["arrhenius"] != RuleStatus.FAIL


def test_below_conservative_floor_routes_to_human():
    """A NASICON sigma under the review engine's conservative floor must
    WARNING (→ human), even though the shared red-flag detector floor was
    widened. This is the Li3Zr2Si2PO12 class: 3.59e-6 vs the true 3.59e-3
    (mS/cm) is a 1000x unit error that must never auto-approve."""
    rec = _clean_rec(
        composition="Li3Zr2Si2PO12",
        family="nasicon",
        property="conductivity",
        value=3.59e-06,
        unit="S/cm",
        normalized_sigma=3.59e-06,
        verified_values=["sigma=8.750e-06"],
    )
    results = evaluate_rules(rec, _ctx())
    s = {r.rule: r.status for r in results}
    assert s["family_range"] == RuleStatus.WARNING
    factors = score_record(rec, results, _ctx())
    decision = decide(results, factors, rec, _ctx())
    assert decision.decision == ReviewDecision.HUMAN


def test_verified_low_sigma_record_still_passes_detector_floor():
    """A genuinely-verified low-sigma record (Li4GeS4, 2.9e-6 sulfide) must not
    be a FAIL for the red-flag detector (widened shared floor) AND must stay
    human-reviewable via the strict engine floor, not auto-rejected."""
    from ssb_dataset.pipeline.redflags import check_sigma_in_family_range

    flagged_detector, _ = check_sigma_in_family_range(2.9e-06, "sulfide")
    assert not flagged_detector  # widened detector floor tolerates it
    rec = _clean_rec(
        composition="Li4GeS4",
        family="sulfide",
        property="conductivity",
        value=2.9e-06,
        unit="S/cm",
        normalized_sigma=2.9e-06,
    )
    results = evaluate_rules(rec, _ctx())
    s = {r.rule: r.status for r in results}
    assert s["family_range"] == RuleStatus.WARNING
    assert s["evidence"] == RuleStatus.PASS


def test_same_paper_pending_duplicate_blocks_auto_approve():
    """Two identical rows from the SAME paper (same composition, same property,
    same value) must WARNING on the duplicate rule and never both auto-approve.
    This is the double-extraction class the DUP_VALUE detector misses (it only
    fires for identical sigmas across *different* compositions)."""
    rec = _clean_rec(
        composition="Li0.375Sr0.4375Ta0.75Zr0.25O3",
        property="conductivity",
        value=0.0012,
        paper_id="10.48550_arxiv.2204.00091",
    )
    sibling = _clean_rec(
        review_id="r_sibling",
        composition="Li0.375Sr0.4375Ta0.75Zr0.25O3",
        property="conductivity",
        value=0.0012,
        paper_id="10.48550_arxiv.2204.00091",
    )
    ctx = _ctx([rec, sibling])
    results = evaluate_rules(rec, ctx)
    s = {r.rule: r.status for r in results}
    assert s["duplicate"] == RuleStatus.WARNING
    factors = score_record(rec, results, ctx)
    decision = decide(results, factors, rec, ctx)
    assert decision.decision != ReviewDecision.AUTO_APPROVE


def test_cross_paper_same_value_is_not_duplicate():
    """Same material + same value from a DIFFERENT paper is consensus, never a
    duplicate (C3 design rule). It must PASS the duplicate rule so it can
    auto-approve."""
    rec = _clean_rec(
        composition="Li7La3Zr2O12",
        property="activation_energy",
        value=0.36,
        paper_id="10.1021_acsenergylett.8b00249",
    )
    approved = _clean_rec(
        review_id="r_approved",
        composition="Li7La3Zr2O12",
        property="activation_energy",
        value=0.4,
        paper_id="10.1038_s41467-022-35287-1",
        status="approved",
    )
    ctx = ReviewContext(
        consensus=None,
        approved_records=[approved],
        pending_records=[],
        family_alias=lambda f: (f or "").lower(),
    )
    results = evaluate_rules(rec, ctx)
    s = {r.rule: r.status for r in results}
    assert s["duplicate"] == RuleStatus.PASS


def test_generic_substitution_formula_is_fail():
    rec = _clean_rec(composition="Li1.3+yAl0.3MxTi1.7-x(PO4)3(M=Zr)")
    results = evaluate_rules(rec, _ctx())
    s = {r.rule: r.status for r in results}
    assert s["formula_specificity"] == RuleStatus.FAIL


def test_general_formula_with_x_is_not_flagged():
    """A real general formula like Li6.5La3-xBaxZr1.5-xTa0.5+xO12 has no
    substitution-element notation and must NOT be flagged."""
    rec = _clean_rec(composition="Li6.5La3-xBaxZr1.5-xTa0.5+xO12")
    results = evaluate_rules(rec, _ctx())
    s = {r.rule: r.status for r in results}
    assert s["formula_specificity"] == RuleStatus.PASS


def test_ea_verified_value_mismatch_is_warning():
    """0.22 vs a located 0.20 is inside tolerance; 0.25 vs 0.30 is not."""
    rec = _clean_rec(
        property="activation_energy",
        value=0.25,
        unit="eV",
        verified_values=["Ea=3.000e-01"],
    )
    results = evaluate_rules(rec, _ctx())
    s = {r.rule: r.status for r in results}
    assert s["verified_value_match"] == RuleStatus.WARNING


def test_ea_verified_value_close_is_pass():
    rec = _clean_rec(
        property="activation_energy",
        value=0.22,
        unit="eV",
        verified_values=["Ea=2.000e-01"],
    )
    results = evaluate_rules(rec, _ctx())
    s = {r.rule: r.status for r in results}
    assert s["verified_value_match"] == RuleStatus.PASS


def test_consensus_outlier_well_sampled_is_fail():
    """A >1.5-order outlier in an n>=3 group is a FAIL."""
    good = _clean_rec(review_id="g1", composition="Li6PS5Cl", value=1e-3, normalized_sigma=1e-3)
    good2 = _clean_rec(review_id="g2", composition="Li6PS5Cl", value=2e-3, normalized_sigma=2e-3)
    good3 = _clean_rec(review_id="g3", composition="Li6PS5Cl", value=1.5e-3, normalized_sigma=1.5e-3)
    outlier = _clean_rec(
        review_id="o1", composition="Li6PS5Cl", value=1e-7, normalized_sigma=1e-7
    )
    records = [good, good2, good3, outlier]
    ctx = _ctx(records)
    results = evaluate_rules(outlier, ctx)
    s = {r.rule: r.status for r in results}
    assert s["consensus"] == RuleStatus.FAIL
    # the in-group members are not flagged
    results_g = evaluate_rules(good, ctx)
    assert {r.rule: r.status for r in results_g}["consensus"] == RuleStatus.PASS


def test_consensus_two_record_group_never_fails():
    """2-record groups span orders of magnitude legitimately — never FAIL."""
    a = _clean_rec(review_id="a1", composition="Li2ZrCl6", value=0.00081, normalized_sigma=0.00081)
    b = _clean_rec(review_id="a2", composition="Li2ZrCl6", value=5.81e-7, normalized_sigma=5.81e-7)
    records = [a, b]
    ctx = _ctx(records)
    for r in (a, b):
        s = {rr.rule: rr.status for rr in evaluate_rules(r, ctx)}
        assert s["consensus"] != RuleStatus.FAIL, r["review_id"]


# ---------------------------------------------------------------------------
# Scorer
# ---------------------------------------------------------------------------

def test_clean_record_scores_high():
    rec = _clean_rec()
    results = evaluate_rules(rec, _ctx())
    factors = score_record(rec, results, _ctx())
    assert factors.overall >= 85


def test_missing_evidence_scores_low():
    rec = _clean_rec(verified_verdict=None, verified_snippet=None)
    results = evaluate_rules(rec, _ctx())
    factors = score_record(rec, results, _ctx())
    # evidence factor fully penalized; overall well below auto-approve bar
    assert factors.factors["evidence"] < 0.2
    assert factors.overall < 80
    # and the decision layer auto-rejects on missing evidence
    d = decide(results, factors, rec, _ctx())
    assert d.decision == ReviewDecision.AUTO_REJECT


def test_factors_expose_breakdown():
    rec = _clean_rec()
    results = evaluate_rules(rec, _ctx())
    factors = score_record(rec, results, _ctx())
    assert set(["evidence", "physics", "units", "family", "consensus", "duplicate", "extraction", "page"]) <= set(factors.factors)


# ---------------------------------------------------------------------------
# Decision engine
# ---------------------------------------------------------------------------

def test_clean_record_auto_approves():
    rec = _clean_rec()
    results = evaluate_rules(rec, _ctx())
    factors = score_record(rec, results, _ctx())
    d = decide(results, factors, rec, _ctx())
    assert d.decision == ReviewDecision.AUTO_APPROVE


def test_missing_value_auto_rejects():
    rec = _clean_rec(value=None)
    results = evaluate_rules(rec, _ctx())
    factors = score_record(rec, results, _ctx())
    d = decide(results, factors, rec, _ctx())
    assert d.decision == ReviewDecision.AUTO_REJECT


def test_generic_formula_auto_rejects():
    rec = _clean_rec(composition="Li1.3+yAl0.3MxTi1.7-x(PO4)3(M=Zr)")
    results = evaluate_rules(rec, _ctx())
    factors = score_record(rec, results, _ctx())
    d = decide(results, factors, rec, _ctx())
    assert d.decision == ReviewDecision.AUTO_REJECT


def test_liquid_electrolyte_solvent_is_scope_fail():
    """LiFSI-DTDL/DME/BFE are liquid electrolyte solutions (wrong family tags
    like hydride/sulfide made family_range pass trivially) — out of scope."""
    for c in ("LiFSI-DTDL", "LiFSI-DME", "LiFSI/BFE"):
        rec = _clean_rec(composition=c)
        results = evaluate_rules(rec, _ctx())
        s = {r.rule: r.status for r in results}
        assert s["scope"] == RuleStatus.FAIL, c
        d = decide(results, score_record(rec, results, _ctx()), rec, _ctx())
        assert d.decision == ReviewDecision.AUTO_REJECT, c


def test_metal_alloy_electrode_is_scope_fail():
    """Li-Mg alloy electrode compositions (no anion framework) — out of scope."""
    for c in ("Li0.9Mg0.1", "Li0.8Mg0.2", "Li0.95Mg0.05"):
        rec = _clean_rec(composition=c)
        results = evaluate_rules(rec, _ctx())
        s = {r.rule: r.status for r in results}
        assert s["scope"] == RuleStatus.FAIL, c
        d = decide(results, score_record(rec, results, _ctx()), rec, _ctx())
        assert d.decision == ReviewDecision.AUTO_REJECT, c


def test_real_electrolyte_composition_is_scope_pass():
    """Normal solid-electrolyte families must never trip the scope rule."""
    for c in (
        "Li2ZrCl6",
        "Li6PS5Cl",
        "Li7La3Zr2O12",
        "Li1.3Al0.3Ti1.7(PO4)3",
        "PEO-LiTFSI",
        "Al2O3-PEO-LiTFSI",
        "Li2Te-LiTe3",
        "Mg(BH4)2",
    ):
        rec = _clean_rec(composition=c)
        results = evaluate_rules(rec, _ctx())
        s = {r.rule: r.status for r in results}
        assert s["scope"] == RuleStatus.PASS, c


def test_family_range_warning_goes_to_human():
    """A family-range violation (even with high score) must go to human, never
    auto-approve — the 0.09 eV argyrodite is real but needs eyes."""
    rec = _clean_rec(
        composition="Li5.4Al0.1PS4.7Cl1.3",
        family="argyrodite",
        property="activation_energy",
        value=0.09,
        unit="eV",
        normalized_ea=0.09,
        verified_values=["Ea=1.000e-01"],
        verifier_consensus=True,
    )
    results = evaluate_rules(rec, _ctx())
    factors = score_record(rec, results, _ctx())
    d = decide(results, factors, rec, _ctx())
    assert d.decision == ReviewDecision.HUMAN


def test_verified_value_mismatch_goes_to_human():
    rec = _clean_rec(
        property="activation_energy",
        value=0.25,
        unit="eV",
        verified_values=["Ea=3.000e-01"],
    )
    results = evaluate_rules(rec, _ctx())
    factors = score_record(rec, results, _ctx())
    d = decide(results, factors, rec, _ctx())
    assert d.decision == ReviewDecision.HUMAN


def test_low_score_missing_evidence_auto_rejects():
    rec = _clean_rec(
        verified_verdict=None,
        verified_snippet=None,
        verified_page=None,
        confidence=0.3,
        value=0.00012,
    )
    results = evaluate_rules(rec, _ctx())
    factors = score_record(rec, results, _ctx())
    d = decide(results, factors, rec, _ctx())
    assert d.decision == ReviewDecision.AUTO_REJECT
