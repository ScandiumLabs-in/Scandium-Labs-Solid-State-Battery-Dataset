#!/usr/bin/env python3
"""AI review sweep: run the deterministic review engine over queue items and
auto-decide the obvious cases. Only uncertain items reach a human.

Pipeline:
    load queue
        -> normalize units (idempotent)
        -> compute cross-paper consensus over PENDING items
        -> evaluate rules per record
        -> score factors
        -> decide (auto_approve / auto_reject / human)

Usage:
    python scripts/ai_review.py                    # dry-run: report only
    python scripts/ai_review.py --apply            # stamp decisions on queue
    python scripts/ai_review.py --show-details     # per-record reasons
"""

from __future__ import annotations

import argparse
import json
from collections import Counter
from pathlib import Path

from dotenv import load_dotenv

load_dotenv()

from ssb_dataset.pipeline.consensus import compute_consensus
from ssb_dataset.pipeline.normalization import normalize_record_units

from ssb_dataset.review import decide, evaluate_rules, score_record
from ssb_dataset.review.decision import Decision, ReviewDecision
from ssb_dataset.review.rules import ReviewContext
from ssb_dataset.review.scorer import ReviewFactors

ROOT = Path(__file__).resolve().parent.parent
QUEUE = ROOT / "review_output/queue.json"
VERIFICATION_REPORT = ROOT / "literature_output/verification_report.json"


def _load_verification_report() -> dict:
    """Load the deterministic evidence-verifier output so the review engine can
    consume the honest signals (sigma_digit_match, duplicate_value) that the
    queue record itself may not carry."""
    if not VERIFICATION_REPORT.exists():
        return {}
    try:
        return json.loads(VERIFICATION_REPORT.read_text())
    except Exception:
        return {}


def _norm(s: str | None) -> str:
    return (s or "").replace(".", "").replace(" ", "").lower()


def _stamp_verification_signals(record: dict, report: dict) -> None:
    """Attach sigma_digit_match / duplicate_value from the deterministic
    evidence verifier, keyed by (paper pdf, composition)."""
    if record.get("sigma_digit_match") is not None or record.get("duplicate_value"):
        return  # already stamped (e.g. re-run after a previous stamp)
    paper = record.get("paper_id")
    comp = record.get("composition")
    if not paper or not comp:
        return
    pdf_key = _norm(paper)
    if not pdf_key.endswith("pdf"):
        pdf_key += "pdf"
    for pepdf, recs in report.items():
        if _norm(pepdf) != pdf_key:
            continue
        for x in recs:
            if _norm(x.get("composition")) == _norm(comp):
                if record.get("sigma_digit_match") is None:
                    record["sigma_digit_match"] = bool(x.get("digit_match"))
                if ("duplicate_value" not in record or not record["duplicate_value"]) and x.get("duplicate_value"):
                    record["duplicate_value"] = x["duplicate_value"]
                return

# family aliases used in the queue -> redflags' family keys
FAMILY_ALIASES = {
    "garnet": "garnet",
    "perovskite": "perovskite",
    "perovskite/llto": "perovskite",
    "sulfide": "sulfide",
    "argyrodite": "sulfide",
    "halide": "halide",
    "nasicon": "nasicon",
    "antiperovskite": "antiperovskite",
    "hydride": "hydride",
    "borohydride": "borohydride",
    "polymer": "polymer_composite",
    "polymer_composite": "polymer_composite",
    "oxide": "oxide",
}


def _alias(family: str | None) -> str:
    return FAMILY_ALIASES.get((family or "").lower(), "")


def build_context(queue: dict) -> ReviewContext:
    items = queue["items"]
    pending = [it for it in items if it.get("status") == "pending"]
    approved = [it for it in items if it.get("status") == "approved"]
    vreport = _load_verification_report()
    for it in pending:
        normalize_record_units(it)
        _stamp_verification_signals(it, vreport)
    consensus = compute_consensus(pending)
    return ReviewContext(
        consensus=consensus,
        approved_records=approved,
        consensus_db=_load_consensus_db(),
        family_alias=_alias,
    )


def _load_consensus_db() -> dict:
    """Load the persistent cross-paper consensus DB if present."""
    path = ROOT / "literature_output/consensus_db.json"
    if not path.exists():
        return {}
    try:
        return json.loads(path.read_text())
    except Exception:
        return {}


def review_record(record: dict, ctx: ReviewContext) -> tuple[list, ReviewFactors, Decision]:
    results = evaluate_rules(record, ctx)
    factors = score_record(record, results, ctx)
    decision = decide(results, factors, record, ctx)
    return results, factors, decision


def run(queue: dict, *, apply: bool = False, details: bool = False) -> Counter:
    ctx = build_context(queue)
    items = queue["items"]
    pending = [it for it in items if it.get("status") == "pending"]

    outcome = Counter()
    auto_notes: list[str] = []
    for it in pending:
        results, factors, decision = review_record(it, ctx)
        outcome[decision.decision.value] += 1
        label = decision.decision.value.upper()
        auto_notes.append(
            f"[{label:12}] {str(it.get('composition'))[:42]:42} "
            f"{str(it.get('property'))[:6]:6} val={it.get('value')} "
            f"score={factors.overall} reasons={decision.reasons}"
        )
        if apply and decision.decision != ReviewDecision.HUMAN:
            it["status"] = "approved" if decision.decision == ReviewDecision.AUTO_APPROVE else "rejected"
            it["reviewer"] = "ai-reviewer"
            it["reviewed_at"] = None
            it["ai_review_note"] = "; ".join(decision.reasons)
            it["ai_review_score"] = factors.overall
            it["ai_review_factors"] = factors.summary()["factors"]
        if details:
            print(f"  {it.get('review_id')} {label} score={factors.overall}")
            for r in results:
                print(f"    {r.status.value:7} {r.rule:22} {r.message}")

    if apply:
        queue["updated_at"] = None
        QUEUE.write_text(json.dumps(queue, indent=2))

    print(f"\nPending: {len(pending)} | decisions: {dict(outcome)}")
    if not apply:
        print("(dry-run — pass --apply to stamp decisions on queue.json)")
    return outcome


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--apply", action="store_true", help="stamp auto-decisions on queue.json")
    parser.add_argument("--show-details", action="store_true", help="print per-record rule results")
    parser.add_argument("--limit", type=int, default=None, help="only review first N pending")
    args = parser.parse_args()

    queue = json.loads(QUEUE.read_text())
    if args.limit:
        n = 0
        for it in queue["items"]:
            if it.get("status") == "pending" and n < args.limit:
                n += 1
            elif it.get("status") == "pending":
                pass  # leave rest untouched for this run
        # review only the first N pending
        pending = [it for it in queue["items"] if it.get("status") == "pending"]
        for it in pending[args.limit:]:
            it["_skip_review"] = True

    run(queue, apply=args.apply, details=args.show_details)


if __name__ == "__main__":
    main()
