#!/usr/bin/env python3
"""Action 2 — scale discovery throughput: query-matrix batch discovery.

Runs OpenAlex across a full matrix of (family × query-type × decade) cells and
logs yield per cell, so discovery becomes a batch job with per-cell yield
tracking instead of one-off per-family runs.

Matrix dimensions:
  * families   — the 8 crystallographic SSB families (sulfide, oxide, garnet,
                 perovskite, nasicon, halide, argyrodite, borohydride) plus
                 hydride/antiperovskite/polymer.
  * query types — ionic conductivity, activation energy, composition screening,
                 combinatorial synthesis, doping series, solid solution.
  * date ranges — decade-bucketed (2000-2009, 2010-2019, 2020-2026).

The combinatorial/doping/solid-solution query types are the Action 3 lever:
they target high-throughput screening papers that report 20-200 compositions
per table. Yield per cell is logged to
``literature_output/query_matrix_yield.json`` so the productive
family×query-type combinations stay visible.

Outputs:
    literature_output/discovery_candidates.json  (merged, source-tagged)
    literature_output/query_matrix_yield.json    (per-cell yield log)

Usage:
    python scripts/query_matrix_discovery.py --persist
    python scripts/query_matrix_discovery.py --max-per-cell 25 --dry-run
    python scripts/query_matrix_discovery.py --only-combinatorial --persist
"""

from __future__ import annotations

import argparse
import json
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

import httpx

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "scripts"))

from ssb_dataset.literature.discovery import compute_relevance  # noqa: E402
from ssb_dataset.schema import Family  # noqa: E402
from harvest_openalex import OUT as DISCOVERY_PATH, merge_into_discovery  # noqa: E402

API = "https://api.openalex.org/works"
MAILTO = "harvest@scandiumlabs.dev"
YIELD_OUT = ROOT / "literature_output" / "query_matrix_yield.json"

FAMILY_QUERY_TYPES: dict[str, list[str]] = {
    "sulfide": ["ionic conductivity", "activation energy", "composition screening",
                "combinatorial synthesis", "doping series", "solid solution series"],
    "oxide": ["ionic conductivity", "activation energy", "composition screening",
              "combinatorial synthesis", "doping series"],
    "garnet": ["ionic conductivity", "activation energy", "doping series",
               "compositional mapping"],
    "perovskite": ["ionic conductivity", "activation energy", "doping series",
                   "compositional mapping"],
    "nasicon": ["ionic conductivity", "activation energy", "composition screening",
                "combinatorial synthesis", "doping series"],
    "halide": ["ionic conductivity", "activation energy", "composition screening",
               "combinatorial synthesis", "doping series"],
    "argyrodite": ["ionic conductivity", "activation energy", "doping series"],
    "borohydride": ["ionic conductivity", "activation energy", "doping series"],
    "hydride": ["ionic conductivity", "activation energy"],
    "antiperovskite": ["ionic conductivity", "activation energy", "doping series"],
    "polymer_composite": ["ionic conductivity", "activation energy", "composition screening"],
}

# Action 3: combinatorial / high-throughput screening query types.
COMBINATORIAL_TYPES = {
    "composition screening", "combinatorial synthesis", "compositional mapping",
    "solid solution series",
}

# Decade-bucketed date ranges (from_year, to_year) inclusive.
DATE_RANGES = [(2000, 2009), (2010, 2019), (2020, 2026)]

# Concrete family anchors so the query is specific, not just family name.
FAMILY_ANCHORS: dict[str, str] = {
    "sulfide": "Li6PS5X OR thio-LISICON OR Li7P3S11 OR sulfide solid electrolyte",
    "oxide": "oxide solid electrolyte lithium",
    "garnet": "LLZO OR Li7La3Zr2O12 OR garnet solid electrolyte",
    "perovskite": "LLTO OR Li3xLa2/3-xTiO3 OR perovskite solid electrolyte",
    "nasicon": "LATP OR Li1.3Al0.3Ti1.7(PO4)3 OR NASICON solid electrolyte",
    "halide": "Li3InCl6 OR Li3YCl6 OR halide solid electrolyte",
    "argyrodite": "Li6PS5Cl OR argyrodite solid electrolyte",
    "borohydride": "LiBH4 OR borohydride solid electrolyte",
    "hydride": "complex hydride ionic conductor",
    "antiperovskite": "Li3OCl OR antiperovskite solid electrolyte",
    "polymer_composite": "PEO composite polymer electrolyte OR polymer ceramic composite",
}


def _abstract(inv: dict | None) -> str:
    if not inv:
        return ""
    words: list[tuple[int, str]] = []
    for word, positions in inv.items():
        words.extend((p, word) for p in positions)
    words.sort()
    return " ".join(w for _, w in words)


def search_cell(term: str, max_results: int, date_filter: str | None = None) -> list[dict]:
    """One OpenAlex query; returns candidates shaped for discovery consumers."""
    out: list[dict] = []
    params = {
        "search": term,
        "per-page": max_results,
        "select": ("id,doi,title,abstract_inverted_index,publication_year,"
                   "open_access,type"),
        "mailto": MAILTO,
    }
    if date_filter:
        params["filter"] = date_filter
    for attempt in range(3):
        try:
            r = httpx.get(API, params=params, timeout=30)
            if r.status_code == 429:
                time.sleep(2 ** attempt * 3)
                continue
            r.raise_for_status()
            for w in r.json().get("results", []):
                doi = (w.get("doi") or "").replace("https://doi.org/", "")
                title = w.get("title") or ""
                if not doi or not title:
                    continue
                oa = w.get("open_access") or {}
                out.append({
                    "doi": doi,
                    "title": title,
                    "abstract": _abstract(w.get("abstract_inverted_index"))[:1000],
                    "relevance_score": compute_relevance(
                        title, _abstract(w.get("abstract_inverted_index"))),
                    "oa_url": oa.get("oa_url") or "",
                })
            return out
        except (httpx.HTTPStatusError, httpx.TimeoutException):
            if attempt == 2:
                return out
            time.sleep(2 ** attempt)
    return out


def build_matrix(
    max_per_cell: int,
    only_combinatorial: bool,
    families: list[str] | None = None,
) -> dict[str, dict[str, list[dict]]]:
    """Run the full matrix. Returns {family: {query_type: [papers, ...]}}."""
    matrix: dict[str, dict[str, list[dict]]] = {}
    fams = families or list(FAMILY_QUERY_TYPES)
    for fam in fams:
        cells: dict[str, list[dict]] = {}
        for qtype in FAMILY_QUERY_TYPES[fam]:
            if only_combinatorial and qtype not in COMBINATORIAL_TYPES:
                continue
            hits: dict[str, dict] = {}
            for (y0, y1) in DATE_RANGES:
                term = f"{FAMILY_ANCHORS[fam]} {qtype}"
                date_filter = (f"from_publication_date:{y0}-01-01,"
                               f"to_publication_date:{y1}-12-31")
                for p in search_cell(term, max_per_cell, date_filter):
                    if p["relevance_score"] >= 0.2:
                        hits.setdefault(p["doi"], p)
                time.sleep(0.25)
            keep = sorted(hits.values(),
                          key=lambda x: x["relevance_score"], reverse=True)
            cells[qtype] = keep[:max_per_cell]
        matrix[fam] = cells
    return matrix


def load_yield() -> dict:
    if YIELD_OUT.exists():
        try:
            return json.loads(YIELD_OUT.read_text())
        except json.JSONDecodeError:
            return {}
    return {}


def save_yield(matrix: dict[str, dict[str, list[dict]]], run_id: str) -> None:
    yield_log = load_yield()
    run: dict = {"run_id": run_id, "cells": {}}
    for fam, cells in matrix.items():
        for qtype, papers in cells.items():
            cell_key = f"{fam}|{qtype}"
            run["cells"][cell_key] = {
                "n_candidates": len(papers),
                "n_open_access": sum(1 for p in papers if p.get("oa_url")),
                "top_relevance": (papers[0]["relevance_score"]
                                  if papers else 0.0),
            }
    yield_log[run_id] = run
    YIELD_OUT.write_text(json.dumps(yield_log, indent=2))


def main() -> int:
    ap = argparse.ArgumentParser(description="Query-matrix batch discovery")
    ap.add_argument("--max-per-cell", type=int, default=25)
    ap.add_argument("--persist", action="store_true",
                    help="merge candidates into discovery_candidates.json")
    ap.add_argument("--dry-run", action="store_true",
                    help="report yields without merging or persisting")
    ap.add_argument("--only-combinatorial", action="store_true",
                    help="only combinatorial / high-throughput query types (Action 3)")
    ap.add_argument("--family", action="append", default=None,
                    help="restrict to a family (repeatable)")
    args = ap.parse_args()

    run_id = datetime.now(timezone.utc).strftime("qmatrix-%Y%m%dT%H%M%S")
    print(f"Running query matrix ({run_id})...")
    matrix = build_matrix(args.max_per_cell, args.only_combinatorial,
                          families=args.family)

    total = 0
    print(f"\n{'family':20s} {'query-type':24s} {'n':>5} {'OA':>4} {'top-rel':>7}")
    for fam, cells in matrix.items():
        for qtype, papers in cells.items():
            total += len(papers)
            n_oa = sum(1 for p in papers if p.get("oa_url"))
            top = papers[0]["relevance_score"] if papers else 0.0
            marker = " *" if qtype in COMBINATORIAL_TYPES else ""
            print(f"{fam:20s} {qtype:24s} {len(papers):5d} {n_oa:4d} {top:7.2f}{marker}")

    print(f"\nTotal candidates from matrix run: {total}")

    if args.dry_run:
        print("Dry-run — nothing merged or persisted.")
        return 0

    save_yield(matrix, run_id)
    print(f"Yield log → {YIELD_OUT.name}")

    if args.persist:
        # Reuse harvest_openalex's DOI-merge so the file is never truncated.
        results: dict[Family, list[dict]] = {}
        for fam, cells in matrix.items():
            fam_enum = Family(fam)
            papers: list[dict] = []
            for qtype, ps in cells.items():
                papers.extend(ps)
            results[fam_enum] = papers
        merged = merge_into_discovery(results, DISCOVERY_PATH)
        n_new = sum(len(v) for v in merged.values())
        print(f"\nMerged into {DISCOVERY_PATH.name}: "
              f"{len(merged)} families, {n_new} total candidates.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
