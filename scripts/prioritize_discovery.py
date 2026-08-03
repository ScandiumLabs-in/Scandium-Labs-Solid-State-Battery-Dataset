#!/usr/bin/env python3
"""Phase E4 — family-deficit-weighted discovery queue (repeatable, not ad hoc).

Instead of running the same search terms for every family, this script computes
each family's (verified-label share) vs (v2.0 benchmark target share, i.e. the
BENCHMARK_MATERIALS composition) and ranks discovery queries by how far below
target each family sits. The output is the literal to-do list for the next
literature-discovery run — persist it, then feed each query into the Semantic
Scholar / OpenAlex discovery routes.

Deficit math (higher = more urgent):
    target_share[family] = len(BENCHMARK_MATERIALS[family]) / total_targets
    current_share[family] = verified_labels[family] / total_verified
    deficit[family] = target_share - current_share

Sulfide sub-family queries (E4 targeting) are always appended because sulfides
are the highest-value, most under-covered family in the verified set.

Output:
    literature_output/prioritized_discovery.json
        { ranked: [...], deficit_per_family: {...}, generated_at: ... }

Usage:
    python scripts/prioritize_discovery.py
    python scripts/prioritize_discovery.py --from-report release_report.json
"""

from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from ssb_dataset.literature.benchmark_materials import BENCHMARK_MATERIALS  # noqa: E402
from ssb_dataset.literature.discovery import SEARCH_TERMS  # noqa: E402
from ssb_dataset.schema import Family  # noqa: E402

OUT = ROOT / "literature_output" / "prioritized_discovery.json"

# Targeted sulfide sub-family queries (Phase E4): the well-studied sub-families
# most likely to have multiple independent papers on the same composition —
# which also feeds cross-paper consensus (Phase E8).
SULFIDE_QUERIES = [
    "Li10GeP2S12 type solid electrolyte ionic conductivity",
    "Li10GeP2S12 LGPS sulfide electrolyte conductivity",
    "Li6PS5Cl argyrodite conductivity",
    "Li6PS5Br argyrodite conductivity",
    "Li6PS5I argyrodite conductivity",
    "thio-LISICON Li4GeS4 Li ion conductor",
    "Li7P3S11 glass ceramic sulfide electrolyte",
    "Li3PS4 sulfide solid electrolyte",
    "Li6P1S5Br argyrodite",
    "Li4SnS4 sulfide electrolyte",
]

# Families that report into the same bucket in benchmark_materials (oxide and
# unknown aren't targets; unknown is not an electrolyte family).
FAMILY_KEY = {f.value for f in Family}


def _target_shares() -> dict[str, float]:
    counts = {k: len(v) for k, v in BENCHMARK_MATERIALS.items() if k in FAMILY_KEY}
    total = sum(counts.values())
    return {k: c / total for k, c in counts.items() if total}


def _current_shares(report: dict) -> dict[str, float]:
    dist = report.get("family_distribution", {}) or {}
    total = sum(dist.values())
    return {k: v / total for k, v in dist.items() if total}


def compute_deficits(report: dict | None = None) -> tuple[dict[str, float], dict[str, float]]:
    targets = _target_shares()
    if report is None:
        report = {}
    current = _current_shares(report)
    deficits = {
        fam: targets.get(fam, 0.0) - current.get(fam, 0.0)
        for fam in set(targets) | set(current)
    }
    return deficits, current


def build_queue(report: dict | None = None) -> list[dict]:
    deficits, current = compute_deficits(report)
    ranked = sorted(deficits, key=lambda f: deficits[f], reverse=True)
    queue = []
    for fam in ranked:
        entry = {
            "family": fam,
            "deficit": round(deficits[fam], 4),
            "target_share": round(deficits[fam] + current.get(fam, 0.0), 4),
            "current_share": round(current.get(fam, 0.0), 4),
            "queries": list(SEARCH_TERMS.get(Family(fam), [])) if fam in Family._value2member_map_ else [],
        }
        if fam in ("sulfide", "argyrodite"):
            entry["queries"] = SULFIDE_QUERIES
        queue.append(entry)
    return queue


def main() -> int:
    ap = argparse.ArgumentParser(description="Family-deficit-weighted discovery queue")
    ap.add_argument("--from-report", type=Path,
                    default=ROOT / "release_report.json",
                    help="release report with family_distribution (default release_report.json)")
    ap.add_argument("--persist", action="store_true")
    args = ap.parse_args()

    report = {}
    if args.from_report.exists():
        try:
            report = json.loads(args.from_report.read_text())
        except json.JSONDecodeError:
            report = {}

    queue = build_queue(report)
    print("Discovery queue ranked by family deficit (highest = most urgent):")
    print(f"{'family':20s} {'deficit':>8s} {'current':>9s} {'target':>8s}")
    for e in queue:
        print(f"{e['family']:20s} {e['deficit']:>8.4f} "
              f"{e['current_share']:>9.4f} {e['target_share']:>8.4f}")

    if args.persist:
        OUT.write_text(json.dumps({
            "ranked": queue,
            "generated_at": datetime.now(timezone.utc).isoformat(),
        }, indent=2))
        print(f"\nPersisted to {OUT}")
    return 0


if __name__ == "__main__":
    sys.exit(main())