#!/usr/bin/env python3
"""Evaluate the AI review engine against the human ground-truth decisions in
review_output/queue.json (reviewer=verification-pass-2026-08-01).

For each such record the engine recomputes rules/score/decision from the
record's own fields (no LLM calls) and compares against the human verdict.
Reports the confusion matrix + key metrics so threshold changes can be
validated reproducibly.

Usage:
    python scripts/calibrate_review_engine.py
"""

from __future__ import annotations

import copy
import json
import sys
from collections import Counter
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

from ssb_dataset.pipeline.consensus import compute_consensus
from ssb_dataset.pipeline.normalization import normalize_record_units
from ssb_dataset.review import decide, evaluate_rules, score_record
from ssb_dataset.review.decision import ReviewDecision
from ssb_dataset.review.rules import ReviewContext

ROOT = Path(__file__).resolve().parent.parent
QUEUE = ROOT / "review_output/queue.json"

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


def alias(family: str | None) -> str:
    return FAMILY_ALIASES.get((family or "").lower(), "")


def main() -> None:
    q = json.loads(QUEUE.read_text())
    items = [i for i in q["items"] if i.get("reviewer") == "verification-pass-2026-08-01"]
    if not items:
        print("No ground-truth items found (reviewer=verification-pass-2026-08-01).")
        return

    # Simulate: all ground-truth records are "pending" for the engine.
    pending = copy.deepcopy(items)
    for it in pending:
        it["status"] = "pending"
        normalize_record_units(it)

    gt = {i["review_id"]: i["status"] for i in items}
    consensus = compute_consensus(pending)
    ctx = ReviewContext(consensus=consensus, approved_records=[], family_alias=alias)

    conf: Counter = Counter()
    details: list[dict] = []
    for it in pending:
        results = evaluate_rules(it, ctx)
        factors = score_record(it, results, ctx)
        d = decide(results, factors, it, ctx)
        conf[(d.decision.value, gt[it["review_id"]])] += 1
        details.append(
            {
                "review_id": it["review_id"],
                "composition": it.get("composition"),
                "property": it.get("property"),
                "value": it.get("value"),
                "human": gt[it["review_id"]],
                "engine": d.decision.value,
                "score": factors.overall,
                "reasons": d.reasons,
            }
        )

    print(f"Ground truth: {len(items)} records (approved {sum(1 for v in gt.values() if v=='approved')}, "
          f"rejected {sum(1 for v in gt.values() if v=='rejected')})")
    print()
    print(f"{'engine decision':16} {'human approved':>14} {'human rejected':>15}")
    for ai in ("auto_approve", "auto_reject", "human"):
        a = conf.get((ai, "approved"), 0)
        r = conf.get((ai, "rejected"), 0)
        print(f"{ai:16} {a:>14} {r:>15}")

    auto = sum(
        conf.get((k, "approved"), 0) + conf.get((k, "rejected"), 0)
        for k in ("auto_approve", "auto_reject")
    )
    ap_a = conf.get(("auto_approve", "approved"), 0)
    ap_r = conf.get(("auto_approve", "rejected"), 0)
    ar_r = conf.get(("auto_reject", "rejected"), 0)
    ar_a = conf.get(("auto_reject", "approved"), 0)
    print(f"\nauto-decided: {auto}/{len(items)} = {auto/len(items)*100:.0f}%")
    if ap_a + ap_r:
        print(f"auto-approve precision: {ap_a}/{ap_a+ap_r} = {ap_a/(ap_a+ap_r)*100:.0f}%")
    if ar_a + ar_r:
        print(f"auto-reject precision:  {ar_r}/{ar_a+ar_r} = {ar_r/(ar_a+ar_r)*100:.0f}%")
    print(f"false rejects (engine rejected, human approved): {ar_a}")
    print(f"false approves (engine approved, human rejected): {ap_r}")
    for d in details:
        if d["engine"] == "auto_approve" and d["human"] == "rejected":
            print(f"  FALSE APPROVE: {d['composition'][:45]:45} {d['property'][:5]:5} val={d['value']} score={d['score']}")
        if d["engine"] == "auto_reject" and d["human"] == "approved":
            print(f"  FALSE REJECT: {d['composition'][:45]:45} {d['property'][:5]:5} val={d['value']} score={d['score']}")

    out = ROOT / "review_output/calibration_report.json"
    out.write_text(json.dumps({
        "n_ground_truth": len(items),
        "confusion": {f"{ai}->{gt}": conf.get((ai, gt), 0) for ai in ("auto_approve", "auto_reject", "human") for gt in ("approved", "rejected")},
        "auto_decided": auto,
        "auto_decided_pct": round(auto / len(items) * 100, 1),
        "auto_approve_precision": round(ap_a / (ap_a + ap_r), 3) if ap_a + ap_r else None,
        "auto_reject_precision": round(ar_r / (ar_a + ar_r), 3) if ar_a + ar_r else None,
        "false_rejects": ar_a,
        "false_approves": ap_r,
    }, indent=2))
    print(f"\nWrote {out}")


if __name__ == "__main__":
    main()
