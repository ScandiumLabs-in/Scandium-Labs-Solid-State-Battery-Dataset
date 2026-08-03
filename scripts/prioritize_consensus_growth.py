#!/usr/bin/env python3
"""Phase E8 — cross-paper consensus growth queue (the flywheel).

Consensus (≥3 independent papers measuring the same σ) is the dataset's
strongest quality signal, and today only ~20–24 materials have it. For every
material currently at n=1, this script emits a *composition-exact* discovery
query — not a generic family search — so the next discovery run targets the
specific formula that needs a second (and third) paper.

Materials that are already well-known benchmarks (LGPS, LLZO, Li6PS5Cl, LATP,
...) are prioritized even past n≥3 because deep consensus on the dataset's
"unit tests" has outsized credibility for external adopters.

Output:
    literature_output/prioritized_consensus.json
        { ranked: [...], donors: {material: n_papers}, generated_at: ... }

Usage:
    python scripts/prioritize_consensus_growth.py
    python scripts/prioritize_consensus_growth.py --persist
"""

from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
CONSENSUS = ROOT / "literature_output" / "consensus_db.json"
OUT = ROOT / "literature_output" / "prioritized_consensus_growth.json"
# Action 5 — continuous flywheel trigger feed: every newly approved record for
# an already-known composition is stamped here so the next consensus-growth
# sweep re-targets that exact composition immediately instead of waiting for a
# full scheduled pass.
FEED = ROOT / "literature_output" / "consensus_flywheel_feed.json"

# Canonical benchmark formulas; materials containing these get boosted. Match is
# case-insensitive substring to catch "Li10GeP2S12-type (...)" variants.
PRIORITY_SUBSTRINGS = [
    "Li10GeP2S12", "Li7La3Zr2O12", "Li6PS5Cl", "Li1.3Al0.3Ti1.7(PO4)3",
    "Li3InCl6", "Li3YCl6", "LiBH4", "Li3OCl", "Li2ZrCl6", "Li7P3S11",
    "Li3PS4", "PEO",
]


def query_for(material: str) -> str:
    return f'"{" ".join(material.split())}" solid electrolyte ionic conductivity'


def read_feed() -> list[str]:
    """Compositions recently stamped by an approval (Action 5 re-trigger)."""
    if not FEED.exists():
        return []
    try:
        return json.loads(FEED.read_text()).get("compositions", [])
    except (json.JSONDecodeError, OSError):
        return []


def stamp_feed(composition: str, *, source: str = "review") -> None:
    """Append a composition to the continuous flywheel feed (called on approve)."""
    data = read_feed()
    if composition in data:
        return
    data.append(composition)
    FEED.write_text(json.dumps({
        "compositions": data,
        "last_stamp": datetime.now(timezone.utc).isoformat(),
        "source": source,
    }, indent=2))


def clear_feed() -> None:
    """Clear the feed once a sweep has consumed it."""
    if FEED.exists():
        FEED.write_text(json.dumps({"compositions": [], "generated_at": ""}, indent=2))


def prioritize(data: dict | None = None, *, target_n: int = 3) -> list[dict]:
    if data is None:
        data = json.loads(CONSENSUS.read_text())
    fed = set(read_feed())
    targets = []
    for material, info in data.items():
        n = int(info.get("n_papers", 0) or 0)
        if n <= 0:
            continue
        effort = max(target_n - n, 0)
        is_priority = any(s.lower() in material.lower() for s in PRIORITY_SUBSTRINGS)
        is_triggered = material in fed or any(
            material.startswith(f) or f in material for f in fed)
        if effort > 0 or is_priority or is_triggered:
            targets.append({
                "material": material,
                "n_papers": n,
                "additions_needed": effort,
                "is_priority_benchmark": is_priority,
                "recently_gained_record": is_triggered,
                "families": info.get("families", []),
                "query": query_for(material),
            })
    # sort: trigger-feed first, then priority benchmarks, then fewest additions
    targets.sort(
        key=lambda t: (not t["recently_gained_record"],
                       not t["is_priority_benchmark"], t["additions_needed"]),
    )
    return targets


def main() -> int:
    ap = argparse.ArgumentParser(description="Consensus-growth discovery queue")
    ap.add_argument("--persist", action="store_true")
    ap.add_argument("--scale-n", type=int, default=3, help="target n papers per material")
    ap.add_argument("--clear-feed", action="store_true",
                    help="clear the trigger feed after a sweep has consumed it")
    args = ap.parse_args()

    data = json.loads(CONSENSUS.read_text()) if CONSENSUS.exists() else {}
    targets = prioritize(data, target_n=args.scale_n)
    n_triggered = sum(1 for t in targets if t["recently_gained_record"])

    print(f"Consensus-growth queue ({len(targets)} materials to push toward "
          f"n≥{args.scale_n}; {n_triggered} recently gained a record):")
    print(f"{'material':40s} {'n':>3s} {'need':>5s} {'bench':>6s} {'new':>4s}")
    for t in targets:
        print(f"{t['material']:40.40s} {t['n_papers']:>3d} "
              f"{t['additions_needed']:>5d} {'YES' if t['is_priority_benchmark'] else '':>6s} "
              f"{'*' if t['recently_gained_record'] else '':>4s}")

    if args.persist:
        OUT.write_text(json.dumps({
            "scaled_to": [t for t in targets],
            "n_recently_gained": n_triggered,
            "generated_at": datetime.now(timezone.utc).isoformat(),
        }, indent=2))
        print(f"\nPersisted {len(targets)} targets to {OUT}")
    if args.clear_feed:
        clear_feed()
        print("Trigger feed cleared (consumed by this sweep).")
    return 0


if __name__ == "__main__":
    sys.exit(main())