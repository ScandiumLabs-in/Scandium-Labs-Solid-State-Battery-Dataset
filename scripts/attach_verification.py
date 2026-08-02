#!/usr/bin/env python3
"""Merge verification evidence into pending review queue items.

For each pending item in review_output/queue.json, attaches:
  - verified_page: page number(s) where the value/composition was found
  - verified_values: values actually matched in the source text
  - verified_snippet: source-text excerpt for quick human confirmation

Uses literature_output/verification_report.json produced by
scripts/verify_extraction_evidence.py.

Usage:
    python scripts/attach_verification.py
"""

from __future__ import annotations

import json
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
QUEUE = ROOT / "review_output/queue.json"
REPORT = ROOT / "literature_output/verification_report.json"


def _pdf_to_paper_id(pdf: str) -> str:
    return Path(pdf).stem


def _match_score(value: float, found: list[str], prop: str) -> bool:
    label = "sigma" if prop == "conductivity" else "Ea"
    for f in found:
        if f.startswith(label + "="):
            return True
    return False


def main() -> None:
    queue = json.loads(QUEUE.read_text())
    report = json.loads(REPORT.read_text())

    # Build lookup: (paper_id, composition, prop) -> best evidence
    lookup: dict[tuple[str, str, str], dict] = {}
    for pdf, recs in report.items():
        paper_id = _pdf_to_paper_id(pdf)
        for r in recs:
            for ev in r.get("evidence", []):
                for f in ev.get("values_found", []):
                    prop = "conductivity" if f.startswith("sigma") else "activation_energy"
                    comp = r.get("composition") or ""
                    key = (paper_id, comp, prop)
                    if key not in lookup or len(lookup[key]["snippet"]) < len(ev.get("snippet", "")):
                        lookup[key] = {
                            "page": ev["page"],
                            "values_found": ev.get("values_found", []),
                            "snippet": ev.get("snippet", ""),
                            "verdict": r.get("verdict"),
                        }

    updated = 0
    for item in queue["items"]:
        if item.get("status") != "pending":
            continue
        prop = item.get("property", "")
        comp = item.get("composition") or ""
        paper_id = item.get("paper_id") or ""
        key = (paper_id, comp, prop)
        if key not in lookup:
            continue
        ev = lookup[key]
        item["verified_page"] = ev["page"]
        item["verified_values"] = ev["values_found"]
        item["verified_snippet"] = ev["snippet"][:400]
        item["verified_verdict"] = ev["verdict"]
        if not item.get("page"):
            item["page"] = str(ev["page"])
        updated += 1

    queue["updated_at"] = None
    QUEUE.write_text(json.dumps(queue, indent=2))
    n_pending = sum(1 for i in queue["items"] if i.get("status") == "pending")
    print(f"Attached verification evidence to {updated} of {n_pending} pending items")


if __name__ == "__main__":
    main()
