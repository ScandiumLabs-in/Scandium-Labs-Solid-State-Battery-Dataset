"""Decision engine for the AI reviewer.

Combines the multi-factor score with the rule PASS/WARNING/FAIL results into
one of:

    auto_approve  - evidence verified, all FAIL rules absent, score high
    auto_reject   - a disqualifying condition is present (missing evidence +
                    low confidence, impossible Arrhenius, negative value)
    human         - everything else

Calibration rule (from the 53-item ground-truth sweep):
    * never auto-approve on score + consensus alone (Fe-LLZO Ea=0.25 had
      score 89.5 + consensus but paper says 0.330 eV);
    * never auto-reject purely on a family-range violation (verified records
      like Li5.4Al0.1PS4.7Cl1.3 Ea=0.09 legitimately fall outside);
    * auto-reject requires a *combination* of independent weak signals
      (e.g. missing evidence AND low extraction confidence), or one strong
      disqualifier (negative value, no numeric value, generic substitution
      formula, or an out-of-scope liquid-electrolyte/alloy-electrode
      composition).
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum

from .rules import RuleStatus, ReviewContext
from .scorer import ReviewFactors

# Auto-approve requires overall score above this AND zero FAIL rules.
AUTO_APPROVE_MIN = 85.0
# Auto-reject fires when overall is below this and a weak-signal combination
# is present (never on score alone).
AUTO_REJECT_MAX = 55.0


class ReviewDecision(str, Enum):
    AUTO_APPROVE = "auto_approve"
    AUTO_REJECT = "auto_reject"
    HUMAN = "human"

    def __str__(self) -> str:  # pragma: no cover
        return self.value


@dataclass
class Decision:
    decision: ReviewDecision
    reasons: list[str] = field(default_factory=list)
    score: float = 0.0
    factors: ReviewFactors | None = None


def _rule(results, name):
    for r in results:
        if r.rule == name:
            return r
    return None


def decide(
    results,
    factors: ReviewFactors,
    record: dict,
    ctx: ReviewContext | None = None,
) -> Decision:
    """Return the auto-decision for a record given its rule results + score."""
    reasons: list[str] = []
    score = factors.overall

    has_fail = {r.rule for r in results if r.status == RuleStatus.FAIL}
    fail_messages = [r.message for r in results if r.status == RuleStatus.FAIL]

    # ---- Strong disqualifiers: auto-reject regardless of score -------------
    r_ev = _rule(results, "evidence")
    if r_ev and r_ev.status == RuleStatus.FAIL:
        return Decision(
            ReviewDecision.AUTO_REJECT,
            [f"no verifiable evidence ({r_ev.message})"],
            score,
            factors,
        )
    r_val = _rule(results, "value_present")
    if r_val and r_val.status == RuleStatus.FAIL:
        return Decision(
            ReviewDecision.AUTO_REJECT,
            [f"no numeric value ({r_val.message})"],
            score,
            factors,
        )
    r_neg = _rule(results, "value_nonneg")
    if r_neg and r_neg.status == RuleStatus.FAIL:
        return Decision(
            ReviewDecision.AUTO_REJECT,
            [f"negative value ({r_neg.message})"],
            score,
            factors,
        )
    r_arr = _rule(results, "arrhenius")
    if r_arr and r_arr.status == RuleStatus.FAIL:
        return Decision(
            ReviewDecision.AUTO_REJECT,
            [f"Arrhenius-impossible ({r_arr.message})"],
            score,
            factors,
        )
    r_cons = _rule(results, "consensus")
    if r_cons and r_cons.status == RuleStatus.FAIL:
        return Decision(
            ReviewDecision.AUTO_REJECT,
            [f"well-sampled consensus outlier ({r_cons.message})"],
            score,
            factors,
        )
    r_formula = _rule(results, "formula_specificity")
    if r_formula and r_formula.status == RuleStatus.FAIL:
        return Decision(
            ReviewDecision.AUTO_REJECT,
            [f"generic substitution formula ({r_formula.message})"],
            score,
            factors,
        )
    r_scope = _rule(results, "scope")
    if r_scope and r_scope.status == RuleStatus.FAIL:
        return Decision(
            ReviewDecision.AUTO_REJECT,
            [f"out of solid-electrolyte scope ({r_scope.message})"],
            score,
            factors,
        )

    # ---- Auto-approve: zero FAIL rules + high score + all-clear on the
    #      evidence/family/value-match warnings ------------------------------
    r_ev = _rule(results, "evidence")
    evidence_ok = r_ev and r_ev.status == RuleStatus.PASS
    # The four warning rules that must be CLEAR for auto-approve: family
    # range, verified-value match, the autoflag triage layer, and duplicate.
    # A violation in any of them means the record needs human eyes even if the
    # score is high (e.g. Fe-LLZO Ea=0.22 where even the verifier located a
    # wrong value; or a same-paper duplicate that would double-count the row).
    all_clear = all(
        _rule(results, name) is not None and _rule(results, name).status == RuleStatus.PASS
        for name in ("family_range", "verified_value_match", "autoflag", "duplicate")
    )
    if not has_fail and evidence_ok and all_clear and score >= AUTO_APPROVE_MIN:
        reasons = ["all rules pass", f"overall {score:.1f} >= {AUTO_APPROVE_MIN}"]
        return Decision(ReviewDecision.AUTO_APPROVE, reasons, score, factors)

    # ---- Weak-signal auto-reject -------------------------------------------
    # Missing evidence + low extraction confidence is a strong hallucination
    # signal (the model wrote a number that could not be located).
    r_conf = _rule(results, "llm_confidence")
    low_conf = r_conf and r_conf.status == RuleStatus.WARNING
    r_page = _rule(results, "page")
    no_page = r_page and r_page.status == RuleStatus.WARNING

    if score < AUTO_REJECT_MAX:
        reasons = [f"overall {score:.1f} < {AUTO_REJECT_MAX}"]
        if not evidence_ok:
            reasons.append("evidence not verified")
        if low_conf:
            reasons.append("low extraction confidence")
        if no_page:
            reasons.append("no page recorded")
        # require at least one supporting signal so a low score alone (e.g.
        # a genuine but under-documented value) is not auto-rejected
        if not evidence_ok or low_conf or no_page:
            return Decision(ReviewDecision.AUTO_REJECT, reasons, score, factors)

    return Decision(ReviewDecision.HUMAN, reasons, score, factors)
