#!/usr/bin/env python3
"""Write a human-readable verification summary from the AI review sweep.

Reads literature_output/verification_results.json and review_output/queue.json
and writes review_output/verification_summary.md — the human's entry point for
the QC pass. Groups records by auto-decision and lists per-record evidence,
model agreement, and flags.

Usage:
    python scripts/verification_summary.py
"""

from __future__ import annotations

import json
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
RESULTS = ROOT / "literature_output/verification_results.json"
QUEUE = ROOT / "review_output/queue.json"
OUT = ROOT / "review_output/verification_summary.md"

DECISION_LABELS = {
    "auto_approve": "auto-approve (no human needed)",
    "spot_check": "quick spot check",
    "needs_review": "full human review",
    "reject": "reject or re-extract",
}


def main() -> None:
    res = json.loads(RESULTS.read_text())
    queue = json.loads(QUEUE.read_text())
    by_id = {i.get("evidence_id"): i for i in queue["items"]}

    lines: list[str] = []
    lines.append("# Verification Summary")
    lines.append("")
    lines.append(f"- Records swept: **{len(res)}**")
    lines.append(f"- Generated: from `{RESULTS}` and `{QUEUE}`")
    lines.append("")

    counts = Counter(r["decision"] for r in res)
    lines.append("## Auto-decision distribution")
    lines.append("")
    for dec in ["auto_approve", "spot_check", "needs_review", "reject"]:
        n = counts.get(dec, 0)
        lines.append(f"- **{dec}** ({DECISION_LABELS.get(dec, '')}): {n}")
    lines.append("")

    # Top records by score
    lines.append("## Highest-confidence records")
    lines.append("")
    lines.append("| Score | Decision | Composition | Property | Value | Agreement | Literature | Flags |")
    lines.append("|-------|----------|-------------|----------|-------|-----------|------------|-------|")
    for r in sorted(res, key=lambda x: -x["score"])[:15]:
        flags = "; ".join(r["notes"])[:40] or "—"
        lines.append(
            f"| {r['score']:.1f} | {r['decision']} | {r['composition']} | "
            f"{r['property']} | {r['value']!r} | {r['n_agree']}/{r['n_models']} | "
            f"{r['literature']} | {flags} |"
        )
    lines.append("")

    # Human review queue (spot_check + needs_review)
    review_tier = [r for r in res if r["decision"] in ("spot_check", "needs_review")]
    lines.append(f"## Human review queue ({len(review_tier)} records)")
    lines.append("")
    for r in sorted(review_tier, key=lambda x: -x["score"]):
        it = by_id.get(r["evidence_id"]) or {}
        lines.append(f"### {r['composition']} — {r['property']} = {r['value']!r}  "
                     f"(score {r['score']:.1f}, {r['decision']})")
        lines.append(f"- paper: `{r['paper_id']}`  page {r['evidence_page']}")
        lines.append(f"- model agreement: {r['n_agree']}/{r['n_models']}  literature: {r['literature']}")
        if r["physics_notes"]:
            lines.append(f"- physics: {'; '.join(r['physics_notes'])}")
        verdict_lines = []
        for vd in r["verdicts"]:
            raw = vd.get("raw") or {}
            q = (vd.get("quote") or raw.get("sigma_quote") or raw.get("ea_quote") or "")[:120]
            verdict_lines.append(
                f"  - {vd['model']}: sigma={raw.get('sigma_found')} ea={raw.get('ea_found')} "
                f"comp={raw.get('composition_found')} quote=\"{q}\""
            )
        if verdict_lines:
            lines.append("  Verdicts:")
            lines.extend(verdict_lines)
        if r["evidence_window"]:
            lines.append(f"  Evidence: {r['evidence_window'][:200]}")
        lines.append("")

    # Rejects: break down by cause
    lines.append("## Rejected records by cause")
    lines.append("")
    reasons: dict[str, list] = {}
    for r in res:
        if r["decision"] != "reject":
            continue
        if not r["physics_ok"]:
            key = "physics/range fail"
        elif r["literature"] == "conflict":
            key = "conflicts benchmark"
        elif r["evidence_present"] is False:
            key = "no evidence located"
        elif r["n_models"] > 0 and r["n_agree"] == 0:
            key = "models disagree / value not confirmed"
        else:
            key = "weak evidence / low agreement"
        reasons.setdefault(key, []).append(r)
    for key, recs in sorted(reasons.items(), key=lambda kv: -len(kv[1])):
        lines.append(f"### {key}: {len(recs)}")
        for r in recs:
            lines.append(f"- `{r['composition']}` {r['property']}={r['value']!r} "
                         f"(score {r['score']:.1f}, agree {r['n_agree']}/{r['n_models']})")
        lines.append("")

    OUT.write_text("\n".join(lines))
    print(f"Wrote {OUT} ({len(lines)} lines)")


if __name__ == "__main__":
    main()
