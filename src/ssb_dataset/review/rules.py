"""Deterministic rule engine for the AI reviewer.

Each rule inspects a review-queue record (plus optional context: consensus
result, already-approved dataset) and returns a RuleResult with status:

    PASS    - no concern, contributes full confidence
    WARNING - minor concern (e.g. missing page, single-source), contributes
              partial confidence, does NOT block auto-approval by itself
    FAIL    - disqualifying (e.g. no evidence, Arrhenius-impossible, negative
              value), blocks auto-approval; drives auto-reject when severe

Design constraints learned from the 53-item ground-truth sweep:
  * A pure composite-score cutoff is insufficient: 20/31 human-approved
    records scored below the old verifier's 80-point reject line.
  * `verifier_consensus` is NOT trustworthy alone: LiBH4-LiI/Al2O3 got 2/2
    model agreement (empty quotes) yet was 10x wrong; Fe-LLZO Ea=0.25 got
    consensus + score 89.5 yet the paper says 0.330 eV.
  * Family-range violations are WARNINGS, not FAILs: verified values like
    Li5.4Al0.1PS4.7Cl1.3 Ea=0.09 eV and the argyrodite σ=0.0067 record are
    real outliers that must not be auto-rejected.
  * Missing evidence (verified_verdict None / no snippet) is a strong reject
    signal when combined with a low LLM-confidence score.
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Callable

from ssb_dataset.pipeline.consensus import (
    MAX_ORDER_SPREAD,
    MIN_N_FOR_CONSENSUS,
    ConsensusResult,
    MaterialConsensus,
)
from ssb_dataset.pipeline.redflags import (
    FAMILY_EA_RANGES,
    FAMILY_SIGMA_RANGES,
    check_arrhenius_consistency,
    check_ea_in_family_range,
    check_sigma_in_family_range,
)

# Families using VTF kinetics where the Arrhenius pre-factor screen does not
# apply (mirrors redflags.VTF_FAMILIES).
VTF_FAMILIES = {"polymer_composite", "polymer"}

# Relative tolerance for comparing the verified (located) value against the
# record's reported value. The verifier's own window tolerance is looser, so
# only a gross mismatch (>=35%) counts as a "different value" flag here.
VERIFIED_VALUE_TOL = 0.35


class RuleStatus(str, Enum):
    PASS = "PASS"
    WARNING = "WARNING"
    FAIL = "FAIL"


@dataclass
class RuleResult:
    rule: str
    status: RuleStatus
    message: str = ""

    def __post_init__(self):
        if isinstance(self.status, str):
            self.status = RuleStatus(self.status)


@dataclass
class ReviewContext:
    """Optional context assembled once per sweep (consensus, approved set)."""

    consensus: ConsensusResult | None = None
    approved_records: list[dict] = field(default_factory=list)
    consensus_db: dict | None = None
    family_alias: Callable[[str], str] = staticmethod(lambda f: (f or "").lower())


def _get_value(record: dict) -> float | None:
    v = record.get("value")
    if isinstance(v, (int, float)):
        return float(v)
    return None


def _get_property(record: dict) -> str:
    return str(record.get("property") or "").lower()


def _is_conductivity(record: dict) -> bool:
    p = _get_property(record)
    return "conductivity" in p or "conduct" in p or str(record.get("unit") or "").lower() in {
        "s/cm",
        "ms/cm",
        "us/cm",
        "ns/cm",
        "s/m",
    }


def _is_activation_energy(record: dict) -> bool:
    p = _get_property(record)
    return "activation" in p or "ea" in p or str(record.get("unit") or "").lower() in {
        "ev",
        "mev",
        "kj/mol",
        "kcal/mol",
    }


def _record_sigma(record: dict) -> float | None:
    """Canonical S/cm value: prefer normalized_sigma, else raw value.

    Property-aware: an activation_energy record (or one carrying an eV/meV
    unit) must never be read as a conductivity, even if a stale normalized
    sigma field is present on the record.
    """
    if _is_activation_energy(record):
        return None
    ns = record.get("normalized_sigma")
    if isinstance(ns, (int, float)) and not (isinstance(ns, float) and math.isnan(ns)):
        return float(ns)
    if _is_conductivity(record):
        return _get_value(record)
    return None


def _record_ea(record: dict) -> float | None:
    ne = record.get("normalized_ea")
    if isinstance(ne, (int, float)) and not (isinstance(ne, float) and math.isnan(ne)):
        return float(ne)
    if _is_activation_energy(record):
        return _get_value(record)
    return None


def _verified_sigma(record: dict) -> float | None:
    for v in record.get("verified_values") or []:
        s = str(v)
        if s.lower().startswith("sigma="):
            try:
                return float(s.split("=", 1)[1])
            except ValueError:
                return None
    return None


def _verified_ea(record: dict) -> float | None:
    for v in record.get("verified_values") or []:
        s = str(v)
        if s.lower().startswith("ea="):
            try:
                return float(s.split("=", 1)[1])
            except ValueError:
                return None
    return None


def _temp_k(record: dict) -> float | None:
    tc = record.get("temperature_celsius")
    if isinstance(tc, (int, float)):
        return float(tc) + 273.15
    return None


# ---------------------------------------------------------------------------
# Rules
# ---------------------------------------------------------------------------

def rule_value_present(record: dict, ctx: ReviewContext) -> RuleResult:
    if _get_value(record) is None or math.isnan(_get_value(record) or 0):
        return RuleResult("value_present", RuleStatus.FAIL, "record has no numeric value")
    return RuleResult("value_present", RuleStatus.PASS)


def rule_value_nonneg(record: dict, ctx: ReviewContext) -> RuleResult:
    v = _get_value(record)
    if v is not None and v < 0:
        return RuleResult("value_nonneg", RuleStatus.FAIL, f"negative value {v}")
    return RuleResult("value_nonneg", RuleStatus.PASS)


def rule_evidence(record: dict, ctx: ReviewContext) -> RuleResult:
    """Evidence located by the verifier (snippet + verdict). Page presence is
    handled by the separate `page` rule."""
    verdict = record.get("verified_verdict")
    snippet = record.get("verified_snippet") or record.get("evidence_sentence")
    if verdict == "FOUND" and bool(snippet):
        return RuleResult("evidence", RuleStatus.PASS)
    if verdict == "NOT_FOUND":
        return RuleResult("evidence", RuleStatus.FAIL, "verifier could not locate the value")
    # No verifier output at all (e.g. raw extraction, no verification pass).
    if not snippet:
        return RuleResult("evidence", RuleStatus.FAIL, "no evidence snippet / verifier verdict")
    return RuleResult("evidence", RuleStatus.WARNING, "verdict missing but snippet present")


def rule_page(record: dict, ctx: ReviewContext) -> RuleResult:
    page = record.get("verified_page")
    if page is not None:
        return RuleResult("page", RuleStatus.PASS, f"page {page}")
    if record.get("page"):
        return RuleResult("page", RuleStatus.PASS, f"page {record['page']}")
    return RuleResult("page", RuleStatus.WARNING, "no page recorded")


def rule_units_normalized(record: dict, ctx: ReviewContext) -> RuleResult:
    """Units must have been normalized; a non-trivial multiplier is fine as
    long as no normalization issues were flagged."""
    issues = record.get("normalization_issues") or []
    if issues:
        return RuleResult("units_normalized", RuleStatus.WARNING, "; ".join(str(i) for i in issues))
    if record.get("sigma_multiplier") is None and record.get("normalized_sigma") is None and _is_conductivity(record):
        return RuleResult("units_normalized", RuleStatus.WARNING, "units not normalized (no multiplier)")
    return RuleResult("units_normalized", RuleStatus.PASS)


def rule_family_range(record: dict, ctx: ReviewContext) -> RuleResult:
    """Family range violation is a WARNING only — several verified records
    legitimately fall outside the static literature window."""
    family = ctx.family_alias(record.get("family"))
    sigma = _record_sigma(record)
    ea = _record_ea(record)
    msgs = []
    if sigma is not None and family:
        flagged, msg = check_sigma_in_family_range(sigma, family)
        if flagged:
            msgs.append(msg)
    if ea is not None and family:
        flagged, msg = check_ea_in_family_range(ea, family)
        if flagged:
            msgs.append(msg)
    if msgs:
        return RuleResult("family_range", RuleStatus.WARNING, "; ".join(msgs))
    return RuleResult("family_range", RuleStatus.PASS)


def rule_arrhenius(record: dict, ctx: ReviewContext) -> RuleResult:
    """Arrhenius pre-factor screen. FAIL only when clearly impossible."""
    sigma = _record_sigma(record)
    ea = _record_ea(record)
    family = ctx.family_alias(record.get("family"))
    if sigma is None or ea is None:
        # Single-property records can't be screened; not a fail.
        return RuleResult("arrhenius", RuleStatus.PASS)
    if family in VTF_FAMILIES:
        return RuleResult("arrhenius", RuleStatus.PASS, "VTF kinetics, screen skipped")
    flagged, msg = check_arrhenius_consistency(
        sigma, ea, family=family, temperature_k=_temp_k(record) or 298.0
    )
    if flagged:
        return RuleResult("arrhenius", RuleStatus.FAIL, msg)
    return RuleResult("arrhenius", RuleStatus.PASS)


def rule_consensus(record: dict, ctx: ReviewContext) -> RuleResult:
    """Outlier against the cross-paper consensus for the same material.

    Only FAILs when the consensus group is well-sampled (n>=3) AND the record
    is a flagrant outlier (>1.5 orders). 2-record groups never fail (either
    value could be the true one)."""
    if not ctx.consensus:
        return RuleResult("consensus", RuleStatus.PASS)
    flagged_ids = {f.get("review_id") for f in ctx.consensus.flagged}
    if record.get("review_id") in flagged_ids:
        note = next((f.get("note", "") for f in ctx.consensus.flagged if f.get("review_id") == record.get("review_id")), "")
        mc: MaterialConsensus | None = ctx.consensus.materials.get(record.get("_consensus_group") or "")
        n = mc.n_sigma if mc else 0
        if n >= 3:
            return RuleResult("consensus", RuleStatus.FAIL, f"consensus outlier (n={n}): {note}")
        return RuleResult("consensus", RuleStatus.WARNING, f"spread vs {n} record(s): {note}")
    return RuleResult("consensus", RuleStatus.PASS)


def rule_consensus_db(record: dict, ctx: ReviewContext) -> RuleResult:
    """Cross-paper consensus from the persistent consensus database.

    Supplements the in-sweep consensus (which only sees the current queue) with
    the accumulated verified dataset: if the material has a well-sampled group
    (n>=3) in the consensus DB and this record's sigma is far from the median,
    flag it. Never FAILs alone (the value may be a legitimate novel report) —
    a strong disagreement surfaces as a WARNING for human eyes.
    """
    if not ctx.consensus_db:
        return RuleResult("consensus_db", RuleStatus.PASS)
    from ssb_dataset.pipeline.fingerprint import group_key

    grp = group_key(str(record.get("composition") or ""))
    if not grp:
        return RuleResult("consensus_db", RuleStatus.PASS)
    entry = ctx.consensus_db.get(grp)
    if not entry or entry.get("n_sigma", 0) < MIN_N_FOR_CONSENSUS:
        return RuleResult("consensus_db", RuleStatus.PASS)

    sigma = _record_sigma(record)
    if sigma is None or sigma <= 0 or not entry.get("median_sigma"):
        return RuleResult("consensus_db", RuleStatus.PASS)

    med = float(entry["median_sigma"])
    delta = abs(math.log10(sigma) - math.log10(med))
    if delta > MAX_ORDER_SPREAD:
        return RuleResult(
            "consensus_db",
            RuleStatus.WARNING,
            f"consensus_db: σ={sigma:.2e} is {10**delta:.0f}x from {grp} "
            f"median {med:.2e} (n={entry['n_sigma']} papers={entry.get('n_papers', 0)})",
        )
    return RuleResult("consensus_db", RuleStatus.PASS)


def rule_duplicate(record: dict, ctx: ReviewContext) -> RuleResult:
    """Same material + same property + same value already approved."""
    if not ctx.approved_records:
        return RuleResult("duplicate", RuleStatus.PASS)
    comp = str(record.get("composition") or "").strip()
    prop = _get_property(record)
    v = _get_value(record)
    if not comp or v is None:
        return RuleResult("duplicate", RuleStatus.PASS)
    for app in ctx.approved_records:
        if str(app.get("composition") or "").strip() == comp and prop == _get_property(app):
            av = app.get("edited_value") if app.get("edited_value") is not None else app.get("value")
            if isinstance(av, (int, float)) and av > 0 and v > 0:
                if abs(math.log10(v) - math.log10(float(av))) < 0.5:
                    return RuleResult("duplicate", RuleStatus.WARNING, "near-duplicate of an approved value")
    return RuleResult("duplicate", RuleStatus.PASS)


def rule_llm_confidence(record: dict, ctx: ReviewContext) -> RuleResult:
    """Extraction confidence. Low confidence alone is a WARNING; only a record
    that is BOTH low-confidence AND missing evidence should be auto-rejected
    (handled at the decision layer)."""
    conf = record.get("confidence")
    if isinstance(conf, (int, float)):
        if conf < 0.5:
            return RuleResult("llm_confidence", RuleStatus.WARNING, f"low extraction confidence {conf}")
    return RuleResult("llm_confidence", RuleStatus.PASS)


def rule_autoflag(record: dict, ctx: ReviewContext) -> RuleResult:
    """The autoflag triage layer (family-range + Arrhenius + consensus) may
    have stamped a high-severity note. Treat as a WARNING here; the specific
    physics/range rules above carry the real signal."""
    sev = record.get("auto_check_severity")
    note = record.get("auto_check_note")
    if sev == "high" and note:
        return RuleResult("autoflag", RuleStatus.WARNING, note)
    return RuleResult("autoflag", RuleStatus.PASS)


def rule_formula_specificity(record: dict, ctx: ReviewContext) -> RuleResult:
    """Substitution-notation compositions (e.g. Li1.3+yAl0.3MxTi1.7-x(PO4)3(M=Zr))
    are generic recipe formulas, not a single measured material. The value may
    be real but it is not tied to one composition, so never auto-approve."""
    import re

    c = str(record.get("composition") or "")
    if re.search(r"\bMx\b|\(M\s*=[A-Za-z]", c):
        return RuleResult("formula_specificity", RuleStatus.FAIL, f"generic substitution formula: {c}")
    return RuleResult("formula_specificity", RuleStatus.PASS)


def rule_digit_match(record: dict, ctx: ReviewContext) -> RuleResult:
    """The deterministic evidence verifier (verify_extraction_evidence.py)
    stamps `sigma_digit_match`: whether the SPECIFIC reported sigma value
    appears in the PDF's evidence window (not merely the Ea or any number).
    A conductivity record whose own sigma value was NOT located cannot be
    verified for that claim -> FAIL (never auto-approve an unconfirmed sigma).
    For Ea records, and for records the deterministic verifier did not stamp,
    the signal is not meaningful so PASS (neutral) — the `evidence` rule
    independently gates the verifier verdict.
    """
    if _is_activation_energy(record):
        return RuleResult("digit_match", RuleStatus.PASS)
    dm = record.get("sigma_digit_match")
    if dm is True:
        return RuleResult("digit_match", RuleStatus.PASS, "sigma value confirmed in PDF evidence")
    if dm is False:
        return RuleResult(
            "digit_match",
            RuleStatus.FAIL,
            "reported sigma NOT located in evidence window (verdict may be FOUND via Ea digit only)",
        )
    # Signal not stamped (no deterministic verifier pass on this record).
    return RuleResult("digit_match", RuleStatus.PASS)


def rule_dup_value(record: dict, ctx: ReviewContext) -> RuleResult:
    """Copy-paste detection from the deterministic verifier: the same sigma
    value shared verbatim by DIFFERENT compositions inside ONE paper is a
    strong extraction-artifact signal (e.g. one table value copied onto every
    dopant variant). Such a record must not be auto-approved; a human must
    reconcile which composition truly carries the value.
    """
    dup = record.get("duplicate_value")
    if not dup:
        return RuleResult("dup_value", RuleStatus.PASS)
    comps = dup if isinstance(dup, list) else [str(dup)]
    return RuleResult(
        "dup_value",
        RuleStatus.FAIL,
        f"same sigma shared by {len(comps)} distinct compositions in this paper: {sorted(comps)}",
    )


def rule_verified_value_match(record: dict, ctx: ReviewContext) -> RuleResult:
    """Gross mismatch between the value the verifier actually located and the
    record's reported value. The verifier's own tolerance is loose, so only a
    >=35% divergence in the same units counts. A FAIL here means the model
    wrote a number the paper does not contain at that magnitude."""
    v = _get_value(record)
    if v is None:
        return RuleResult("verified_value_match", RuleStatus.PASS)
    if _is_conductivity(record):
        located = _verified_sigma(record)
    elif _is_activation_energy(record):
        located = _verified_ea(record)
    else:
        return RuleResult("verified_value_match", RuleStatus.PASS)
    if located is None:
        return RuleResult("verified_value_match", RuleStatus.PASS)
    if _is_activation_energy(record):
        # Ea is an absolute quantity: a >=0.04 eV divergence is a real mismatch
        # (0.25 vs 0.3, 0.22 vs 0.3 are the classic hallucination patterns).
        if abs(located - v) >= 0.04:
            return RuleResult(
                "verified_value_match",
                RuleStatus.WARNING,
                f"verified Ea {located:.3f} eV differs from reported {v:.3f} eV",
            )
        return RuleResult("verified_value_match", RuleStatus.PASS)
    # absolute tolerance so tiny values aren't spuriously flagged
    if abs(located - v) <= max(VERIFIED_VALUE_TOL * abs(v), 5e-5):
        return RuleResult("verified_value_match", RuleStatus.PASS)
    return RuleResult(
        "verified_value_match",
        RuleStatus.WARNING,
        f"verified value {located:.2e} differs from reported {v:.2e}",
    )


ALL_RULES: list[Callable[[dict, ReviewContext], RuleResult]] = [
    rule_value_present,
    rule_value_nonneg,
    rule_evidence,
    rule_page,
    rule_units_normalized,
    rule_family_range,
    rule_arrhenius,
    rule_consensus,
    rule_consensus_db,
    rule_duplicate,
    rule_llm_confidence,
    rule_autoflag,
    rule_formula_specificity,
    rule_digit_match,
    rule_dup_value,
    rule_verified_value_match,
]


def evaluate_rules(record: dict, ctx: ReviewContext | None = None) -> list[RuleResult]:
    ctx = ctx or ReviewContext()
    results = [rule(record, ctx) for rule in ALL_RULES]
    # Deterministic ordering for stable output.
    results.sort(key=lambda r: (r.status.value, r.rule))
    return results
