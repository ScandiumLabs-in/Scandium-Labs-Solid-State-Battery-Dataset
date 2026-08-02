#!/usr/bin/env python3
"""Expand the benchmark inventory (150 -> ~300) using ONLY title-verified DOIs
sourced from real Semantic Scholar discovery candidates.

A composition is only added to the rich benchmark module if a candidate paper
title literally contains the normalized composition string (or a verified
alias). This guarantees every new DOI is a real, on-topic paper — never a
guessed or misremembered identifier.

Writes new entries into benchmark_materials.py (the single source of truth) as
family-organized rich entries. benchmark_inventory.py derives its flat dict
from there automatically.

Usage:
    python scripts/expand_benchmark_inventory.py          # dry run (prints additions)
    python scripts/expand_benchmark_inventory.py --write  # write to benchmark_materials.py
"""

from __future__ import annotations

import json
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
CANDIDATES = ROOT / "literature_output/discovery_candidates.json"
INVENTORY = ROOT / "src/ssb_dataset/literature/benchmark_materials.py"

# Target compositions to add, keyed by family. Values are the sigma/Ea targets
# from canonical literature (these are *verification targets*, flagged as such).
TARGETS: dict[str, dict[str, dict]] = {
    "sulfide": {
        "Li7P3S11": {"sigma_S_per_cm": 1.7e-2, "Ea_eV": 0.18},
        "Li10SnP2S12": {"sigma_S_per_cm": 1.4e-2, "Ea_eV": 0.24},
        "Li4SnS4": {"sigma_S_per_cm": 1.4e-4, "Ea_eV": 0.35},
    },
    "garnet": {
        "Li6.75La3Zr1.75Ta0.25O12": {"sigma_S_per_cm": 1.0e-3, "Ea_eV": 0.34},
        "Li6.25Al0.25La3Zr2O12": {"sigma_S_per_cm": 4.0e-4, "Ea_eV": 0.32},
    },
    "halide": {},
    "nasicon": {},
    "borohydride": {
        "LiBH4-LiI": {"sigma_S_per_cm": 1.0e-4, "Ea_eV": 0.60},
        "LiBH4-MgO": {"sigma_S_per_cm": 2.86e-4, "Ea_eV": None},
    },
    "polymer_composite": {
        "PEO-LiClO4": {"sigma_S_per_cm": 1.0e-6, "Ea_eV": 1.0},
    },
    "antiperovskite": {
        "Li3SI": {"sigma_S_per_cm": 1.0e-3, "Ea_eV": 0.25},
    },
    "hydride": {},
}

ALIASES: dict[str, list[str]] = {
    "Li7P3S11": ["Li7P3S11", "Li7P3S"],
    "Li10SnP2S12": ["Li10SnP2S12"],
    "Li4SnS4": ["Li4SnS4"],
    "Li6.75La3Zr1.75Ta0.25O12": ["Li6.75La3Zr1.75Ta0.25O12"],
    "Li6.25Al0.25La3Zr2O12": ["Li6.25Al0.25La3Zr2O12", "Li6.25Al0.25La3Zr2O12"],
    "LiBH4-LiI": ["LiBH4-LiI"],
    "LiBH4-MgO": ["LiBH4-MgO"],
    "PEO-LiClO4": ["PEO-LiClO4", "PEO-LiClO4"],
    "Li3SI": ["Li3SI"],
}

# Direct-additions from targeted per-composition discovery
# (literature_output/benchmark_target_discovery.json). DOIs were title-verified
# by an S2 search whose result title contained the composition string.
TARGET_DISCOVERY_FILE = ROOT / "literature_output/benchmark_target_discovery.json"


def norm(s: str) -> str:
    """Remove non-alphanumeric chars for case-insensitive matching."""
    return re.sub(r"[^a-z0-9]", "", s.lower())


def find_doi_for_comp(comp: str, family: str, candidates: dict) -> str | None:
    comp_n = norm(comp)
    aliases = [norm(a) for a in ALIASES.get(comp, [comp])]
    for p in candidates.get(family, []):
        title_n = norm(p.get("title", ""))
        for a in aliases:
            if a and a in title_n:
                return p["doi"]
    # fall back to searching all families
    for fam, papers in candidates.items():
        for p in papers:
            title_n = norm(p.get("title", ""))
            for a in aliases:
                if a and a in title_n:
                    return p["doi"]
    return None


def main() -> None:
    import argparse

    parser = argparse.ArgumentParser()
    parser.add_argument("--write", action="store_true")
    args = parser.parse_args()

    candidates = json.loads(CANDIDATES.read_text())

    # Dedup against what's already in the inventory module
    import ssb_dataset.literature.benchmark_materials as rich

    existing_in_inventory = {e["formula"] for e in rich.iter_benchmark_entries()}

    additions: list[tuple[str, dict]] = []
    for family, comps in TARGETS.items():
        for comp, vals in comps.items():
            if comp in existing_in_inventory:
                continue
            doi = find_doi_for_comp(comp, family, candidates)
            if doi:
                additions.append((comp, {**vals, "doi": doi, "family": family}))
                print(f"  ADD {comp:32s} {doi}")
            else:
                print(f"  SKIP {comp:32s} (no title-verified candidate)")

    # Merge targeted-discovery additions (already title-verified by S2 search)
    if TARGET_DISCOVERY_FILE.exists():
        targ = json.loads(TARGET_DISCOVERY_FILE.read_text())
        existing = {c for c, _ in additions} | set(existing_in_inventory) | set(TARGETS)
        for family, comps in targ.items():
            for comp, spec in comps.items():
                if spec.get("doi") and comp not in existing:
                    additions.append(
                        (comp, {"sigma_S_per_cm": spec["sigma_S_per_cm"],
                                "Ea_eV": spec.get("Ea_eV"),
                                "doi": spec["doi"], "family": family})
                    )
                    print(f"  ADD {comp:32s} {spec['doi']}  [targeted]")

    if args.write and additions:
        from datetime import datetime

        now = datetime.now().strftime("%Y-%m-%d")
        blocks: dict[str, list[str]] = {}
        for comp, d in additions:
            family = (d.get("family") or "sulfide").replace("_", "")
            note = (d.get("family") or "sulfide").replace("_", " ")
            blocks.setdefault(family, []).append(
                "        {\n"
                f"            \"formula\": {json.dumps(comp)},\n"
                f"            \"sigma_S_per_cm\": {d['sigma_S_per_cm']!r},\n"
                f"            \"Ea_eV\": {d.get('Ea_eV')!r},\n"
                f"            \"doi\": {json.dumps(d['doi'])},\n"
                "            \"crystal_system\": None,\n"
                "            \"space_group\": None,\n"
                "            \"method\": \"EIS\",\n"
                "            \"confidence\": \"needs-verification\",\n"
                "            \"status\": \"target\",\n"
                f"            \"note\": {json.dumps(note + ' (title-verified via discovery, ' + now + ').')},\n"
                "            \"family\": " + json.dumps(family) + ",\n"
                "            \"temperature_c\": 25,\n"
                "        },\n"
            )
        text = INVENTORY.read_text()
        total = 0
        for family, block in blocks.items():
            marker = f'    "{family}": ['
            if marker in text:
                insert = "".join(block)
                new = text.replace(marker, marker + "\n" + insert, 1)
                INVENTORY.write_text(new)
                text = new
                total += len(block)
            else:
                print(f"  ! family marker {marker!r} not found — skipping {len(block)} additions")
        print(f"\nWrote {total} additions to {INVENTORY}")
    else:
        print(f"\nDry run: {len(additions)} additions ready (use --write)")


if __name__ == "__main__":
    main()
