"""AI review engine.

Deterministic, LLM-free layer that turns a review-queue record into an
auto-decision. Complements (and builds on) the evidence verifier:
the verifier locates + quotes evidence; this package decides.

Layers:
  rules.py    - PASS/WARNING/FAIL per-rule checks (evidence, physics, units,
                consensus, duplicates, family range).
  scorer.py   - multi-factor confidence model (0..100) combining rule results.
  decision.py - threshold logic: AUTO APPROVE / AUTO REJECT / HUMAN.

The thresholds are calibrated against the human ground-truth decisions in
review_output/queue.json (reviewer=verification-pass-2026-08-01).
"""

from __future__ import annotations

from .rules import RuleResult, RuleStatus, evaluate_rules
from .scorer import ReviewFactors, score_record
from .decision import ReviewDecision, decide

__all__ = [
    "RuleResult",
    "RuleStatus",
    "evaluate_rules",
    "ReviewFactors",
    "score_record",
    "ReviewDecision",
    "decide",
]
