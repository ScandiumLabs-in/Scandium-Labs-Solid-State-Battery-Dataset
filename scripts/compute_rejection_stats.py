#!/usr/bin/env python3
"""Publish the rejection-rate statistic (guide §5 action 5).

LiIon's methods disclose an explicit exclusion policy; reviewers of any ML
dataset look for the same transparency signal: *how many candidate records were
thrown out during human review, and why?* This script reads the review queue
(all_queue_records.json) and publishes:

  - overall review funnel: submitted / pending / approved / rejected
  - rejection rate = rejected / (approved + rejected)
  - top rejection reasons with counts (categorized deterministically from
    the human review_note text)

Outputs:
  validation_output/rejection_statistics.json   machine-readable
  validation_output/rejection_statistics.md     human-readable

Deterministic. No LLM calls, no network.
"""

from __future__ import annotations

import json
import re
import sys
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

QUEUE = ROOT / "review_output/all_queue_records.json"
OUT_JSON = ROOT / "validation_output/rejection_statistics.json"
OUT_MD = ROOT / "validation_output/rejection_statistics.md"

# Ordered rejection-reason rules. First match wins; order matters (unit errors
# often co-occur with composition/attribution text in the same note).
_REASON_RULES: list[tuple[str, list[re.Pattern]]] = [
    ("duplicate / near-duplicate (incl. DUP_VALUE copy-paste across compositions)",
     [re.compile(r"duplicate", re.I),
      re.compile(r"same paper duplicate", re.I),
      re.compile(r"stale", re.I),
      re.compile(r"DUP_VALUE", re.I)]),
    ("unit error (mS/cm→S/cm or similar 1000×/100× misread)",
     [re.compile(r"unit error", re.I),
      re.compile(r"mS/cm.*S/cm", re.I),
      re.compile(r"\b1000x\b|\b100×\b", re.I),
      re.compile(r"kJ/mol misread", re.I)]),
    ("hallucination / value not in paper",
     [re.compile(r"hallucinat", re.I),
      re.compile(r"not in paper", re.I),
      re.compile(r"value not found", re.I),
      re.compile(r"paper reports no", re.I),
      re.compile(r"fabricated", re.I),
      re.compile(r"unmatched", re.I)]),
    ("composition misattribution",
     [re.compile(r"composition mismatch", re.I),
      re.compile(r"wrong attribution", re.I),
      re.compile(r"attribution", re.I),
      re.compile(r"is for a different", re.I),
      re.compile(r"for a different composition", re.I),
      re.compile(r"wrong composition", re.I)]),
    ("wrong value / correct value is different",
     [re.compile(r"paper Table 2", re.I),
      re.compile(r"paper reports .* not", re.I),
      re.compile(r"is .* not .* eV", re.I),
      re.compile(r"wrong:", re.I),
      re.compile(r"is the known-wrong value", re.I),
      re.compile(r"conflicts with verified", re.I)]),
    ("composition series out of range / hallucinated variants",
     [re.compile(r"x in \{", re.I),
      re.compile(r"compositions are .* only", re.I),
      re.compile(r"no composition specific", re.I)]),
    ("consensus outlier",
     [re.compile(r"consensus outlier", re.I)]),
    ("property mislabeled (Ea stored as conductivity or vice versa)",
     [re.compile(r"mislabeled as conductivity", re.I),
      re.compile(r"mislabeled", re.I),
      re.compile(r"is the activation energy", re.I)]),
    ("unverifiable / no measured value (Ea only in figures, cited not measured)",
     [re.compile(r"unverifiable", re.I),
      re.compile(r"no measured Ea", re.I),
      re.compile(r"not stated in text", re.I),
      re.compile(r"image.*not text", re.I),
      re.compile(r"not text layer", re.I),
      re.compile(r"no Ea in paper", re.I),
      re.compile(r"Ea only in figure", re.I)]),
    ("false positive (regex matched wrong context: vacancy/sampling/activation)",
     [re.compile(r"false positive", re.I),
      re.compile(r"matches vacancy", re.I),
      re.compile(r"matches composition sampling", re.I)]),
    ("computed/simulated value not a measurement (AIMD/DFT/MD barrier)",
     [re.compile(r"AIMD", re.I),
      re.compile(r"computed migration barrier", re.I),
      re.compile(r"DFT", re.I),
      re.compile(r"MD simulation", re.I),
      re.compile(r"is the cited", re.I)]),
    ("out of scope (liquid/electrode/composite context)",
     [re.compile(r"liquid electrolyte", re.I),
      re.compile(r"electrode", re.I),
      re.compile(r"not an electrolyte", re.I),
      re.compile(r"out of scope", re.I)]),
    ("evidence missing / cannot verify",
     [re.compile(r"no evidence", re.I),
      re.compile(r"evidence", re.I),
      re.compile(r"no pdf", re.I),
      re.compile(r"scanned", re.I)]),
]


def _categorize(note: str) -> str:
    if not note:
        return "no review note"
    for label, pats in _REASON_RULES:
        if any(p.search(note) for p in pats):
            return label
    return "other"


def compute(queue: list[dict]) -> dict:
    status = Counter(r.get("status") for r in queue)
    approved = status.get("approved", 0)
    rejected = status.get("rejected", 0)
    pending = status.get("pending", 0)
    decided = approved + rejected
    rejection_rate = (rejected / decided) if decided else None

    rej_reasons: Counter[str] = Counter()
    for r in queue:
        if r.get("status") == "rejected":
            note = r.get("review_note") or r.get("issues") or ""
            rej_reasons[_categorize(str(note))] += 1

    return {
        "methodology": (
            "Rejection statistic computed from the human review queue "
            "(all_queue_records.json). Rejection rate = rejected / "
            "(approved + rejected). Reasons are categorized deterministically "
            "from the human review note text."
        ),
        "funnel": {
            "submitted": len(queue),
            "approved": approved,
            "rejected": rejected,
            "pending": pending,
            "decided": decided,
        },
        "rejection_rate": rejection_rate,
        "rejection_rate_pct": round(rejection_rate * 100, 1)
        if rejection_rate is not None else None,
        "top_rejection_reasons": rej_reasons.most_common(10),
        "n_rejected_with_note": sum(
            1 for r in queue if r.get("status") == "rejected"
            and (r.get("review_note") or r.get("issues"))),
    }


def main() -> None:
    queue = json.loads(QUEUE.read_text())
    report = compute(queue)
    OUT_JSON.parent.mkdir(parents=True, exist_ok=True)
    OUT_JSON.write_text(json.dumps(report, indent=2))

    rr = report["rejection_rate_pct"]
    lines = [
        "# Rejection-rate statistic (guide §5 action 5)",
        "",
        report["methodology"],
        "",
        "## Review funnel",
        "",
        "| stage | count |",
        "|---|---|",
        f"| submitted | {report['funnel']['submitted']} |",
        f"| approved | {report['funnel']['approved']} |",
        f"| rejected | {report['funnel']['rejected']} |",
        f"| pending | {report['funnel']['pending']} |",
        "",
        f"**Rejection rate: {rr}%** "
        f"({report['funnel']['rejected']}/{report['funnel']['decided']} "
        f"decided records rejected).",
        "",
        "## Top rejection reasons",
        "",
        "| reason | n |",
        "|---|---|",
    ]
    for reason, n in report["top_rejection_reasons"]:
        lines.append(f"| {reason} | {n} |")
    OUT_MD.write_text("\n".join(lines) + "\n")

    print(f"wrote {OUT_JSON}")
    print(f"wrote {OUT_MD}")
    print(f"rejection rate: {rr}% "
          f"({report['funnel']['rejected']}/{report['funnel']['decided']})")
    for reason, n in report["top_rejection_reasons"][:5]:
        print(f"  - {reason}: {n}")


if __name__ == "__main__":
    main()
