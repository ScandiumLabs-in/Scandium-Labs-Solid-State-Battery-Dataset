"""Multi-factor confidence scoring for the AI reviewer.

Converts the rule results + record fields into a single 0..100 confidence and
a per-factor breakdown. The score is a *screening* signal only — the decision
engine (decision.py) combines it with the hard PASS/WARNING/FAIL rule results.

Factor weights are mirrored from the evidence verifier's composite score so
the two layers stay coherent:
    evidence 25 | physics 20 | units 10 | family 10
    consensus 10 | duplicate 10 | extraction 8 | page 7
    verified_value_match (bonus)  — but only additive up to 100.
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field

from .rules import ReviewContext, RuleResult, RuleStatus

_FACTOR_RULES: dict[str, list[str]] = {
    "evidence": ["evidence"],
    "physics": ["arrhenius"],
    "units": ["units_normalized"],
    "family": ["family_range"],
    "consensus": ["consensus", "consensus_db"],
    "duplicate": ["duplicate"],
    "extraction": ["llm_confidence"],
    "page": ["page"],
    "digit_match": ["digit_match"],
    "dup_value": ["dup_value"],
}

# base weight per factor (out of 100 before verified-match bonus)
_FACTOR_WEIGHTS: dict[str, float] = {
    "evidence": 25.0,
    "physics": 18.0,
    "units": 9.0,
    "family": 9.0,
    "consensus": 10.0,
    "duplicate": 9.0,
    "extraction": 8.0,
    "page": 6.0,
    "digit_match": 5.0,
    "dup_value": 5.0,
}

_PASS_VALUE = 1.0
_WARN_VALUE = 0.55
_FAIL_VALUE = 0.15


@dataclass
class ReviewFactors:
    """Per-factor confidence and the overall composite."""

    factors: dict[str, float] = field(default_factory=dict)
    warnings: list[str] = field(default_factory=list)
    fails: list[str] = field(default_factory=list)
    overall: float = 0.0

    def summary(self) -> dict:
        return {
            "overall": round(self.overall, 1),
            "factors": {k: round(v, 2) for k, v in sorted(self.factors.items())},
            "warnings": self.warnings,
            "fails": self.fails,
        }


def _rule_status_for(record: dict, rule_name: str, results: list[RuleResult]) -> RuleStatus | None:
    for r in results:
        if r.rule == rule_name:
            return r.status
    return None


def _scale(status: RuleStatus | None) -> float:
    if status is None:
        return 0.5  # rule not applicable -> neutral
    if status == RuleStatus.PASS:
        return _PASS_VALUE
    if status == RuleStatus.WARNING:
        return _WARN_VALUE
    return _FAIL_VALUE


def score_record(
    record: dict,
    results: list[RuleResult],
    ctx: ReviewContext | None = None,
) -> ReviewFactors:
    """Compute the multi-factor confidence for a record given its rule results.

    All rule results carry weight regardless of applicability (a skipped rule
    scores neutral), so the composite is comparable across records.
    """
    factors: dict[str, float] = {}
    total = 0.0
    for factor, rules in _FACTOR_RULES.items():
        # Conditional factors carry weight only when the deterministic signal
        # was actually stamped for this record. An unstamped record is neither
        # confirmed nor refuted, so it must not gain the full pass weight.
        weight = _FACTOR_WEIGHTS[factor]
        if factor == "digit_match" and record.get("sigma_digit_match") is None:
            weight = 0.0
        elif factor == "dup_value" and not record.get("duplicate_value"):
            weight = 0.0
        # A factor's score is the min over its rules (worst rule dominates),
        # scaled by the factor weight.
        statuses = [_rule_status_for(record, r, results) for r in rules]
        worst = min((_scale(s) for s in statuses), default=0.5)
        factors[factor] = worst
        total += weight * worst

    warnings = [r.message for r in results if r.status == RuleStatus.WARNING]
    fails = [r.message for r in results if r.status == RuleStatus.FAIL]

    # A gross verified-value mismatch caps the score (but does not add a FAIL:
    # the verifier's located value can differ for legitimate reasons like
    # the paper reporting a different but valid number).
    reduced_total = total
    for r in results:
        if r.rule == "verified_value_match" and r.status == RuleStatus.WARNING:
            reduced_total = min(total, 82.0)

    # Cap at 100 (bonus rounding safety).
    overall = round(min(reduced_total, 100.0), 1)
    return ReviewFactors(factors=factors, warnings=warnings, fails=fails, overall=overall)
