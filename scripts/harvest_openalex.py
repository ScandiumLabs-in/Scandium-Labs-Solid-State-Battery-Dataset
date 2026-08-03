#!/usr/bin/env python3
"""OpenAlex discovery route — merges new candidates into discovery_candidates.json.

Semantic Scholar is metadata-only and rate-limits hard on targeted materials
searches (see discover_benchmark_openalex.py's original rationale). OpenAlex is
a free, keyless (~100k req/day polite pool with ``mailto``) alternative that
indexes far more materials-science venues and exposes an OA URL per work — so it
finds candidate papers Semantic Scholar's search misses.

Runs the same per-family SEARCH_TERMS as Semantic Scholar discovery, but tags
every candidate with its source so yield-per-source stays comparable:

    literature_output/discovery_candidates.json
        { family: [ {doi, title, abstract, relevance_score, source, oa_url}, ... ] }

Merging is by DOI: an existing candidate from another source keeps its entry and
gets a ``sources`` list appended; a new DOI is appended. The file is never
truncated, so re-running adds to (never destroys) prior discovery.

Usage:
    python scripts/harvest_openalex.py                 # merge OpenAlex candidates
    python scripts/harvest_openalex.py --max-per-family 50
"""

from __future__ import annotations

import argparse
import json
import sys
import time
from pathlib import Path

import httpx

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from ssb_dataset.literature.discovery import (  # noqa: E402
    SEARCH_TERMS,
    compute_relevance,
)
from ssb_dataset.schema import Family  # noqa: E402

API = "https://api.openalex.org/works"
OUT = ROOT / "literature_output" / "discovery_candidates.json"
MAILTO = "harvest@scandiumlabs.dev"


def _abstract(inv: dict[str, list[int]] | None) -> str:
    """Rebuild a plain-text abstract from OpenAlex's inverted index."""
    if not inv:
        return ""
    words: list[tuple[int, str]] = []
    for word, positions in inv.items():
        words.extend((p, word) for p in positions)
    words.sort()
    return " ".join(w for _, w in words)


def search_openalex(term: str, max_results: int) -> list[dict]:
    """Search OpenAlex works; return the shape discovery consumers expect."""
    out: list[dict] = []
    params = {
        "search": term,
        "per-page": max_results,
        "select": ("id,doi,title,abstract_inverted_index,publication_year,"
                   "open_access,type"),
        "mailto": MAILTO,
    }
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


def merge_into_discovery(
    results: dict[Family, list[dict]],
    candidates_path: str | Path = OUT,
) -> dict[str, list[dict]]:
    """Merge OpenAlex results into the persistent discovery file by DOI.

    Existing entries keep their ``source`` and gain an appended ``sources``
    list; brand-new DOIs are appended with ``source: "openalex"``. Returns the
    merged in-memory structure and persists it.
    """
    path = Path(candidates_path)
    merged: dict[str, list[dict]] = {}
    if path.exists():
        try:
            merged = json.loads(path.read_text())
        except json.JSONDecodeError:
            merged = {}

    for fam, papers in results.items():
        key = fam.value
        existing = merged.get(key, [])
        by_doi = {p.get("doi"): p for p in existing}
        for p in papers:
            doi = p.get("doi")
            if not doi:
                continue
            if doi in by_doi:
                srcs = by_doi[doi].setdefault("sources", [by_doi[doi].get("source", "semantic_scholar")])
                if "openalex" not in srcs:
                    srcs.append("openalex")
            else:
                by_doi[doi] = {**p, "source": "openalex", "sources": ["openalex"]}
        merged[key] = sorted(by_doi.values(),
                             key=lambda x: x.get("relevance_score", 0.0),
                             reverse=True)
    path.write_text(json.dumps(merged, indent=2))
    return merged


def main() -> int:
    ap = argparse.ArgumentParser(description="OpenAlex discovery + merge")
    ap.add_argument("--max-per-family", type=int, default=50)
    ap.add_argument("--persist", action="store_true",
                    help="merge into discovery_candidates.json (default: report only)")
    args = ap.parse_args()

    results: dict[Family, list[dict]] = {}
    total_new = 0
    for family, terms in SEARCH_TERMS.items():
        hits: dict[str, dict] = {}
        for term in terms:
            for p in search_openalex(term, args.max_per_family // len(terms) + 1):
                hits.setdefault(p["doi"], p)
            time.sleep(0.4)
        keep = [p for p in hits.values() if p["relevance_score"] >= 0.2]
        keep.sort(key=lambda x: x["relevance_score"], reverse=True)
        results[family] = keep[:args.max_per_family]
        total_new += len(keep)
        print(f"  {family.value:18s} → {len(keep)} relevant candidates")

    if args.persist:
        merged = merge_into_discovery(results)
        n_sources = {
            src: sum(
                1
                for papers in merged.values()
                for p in papers
                if "openalex" in p.get("sources", [])
            )
            for src in ["openalex", "semantic_scholar"]
        }
        print(f"\nMerged into {OUT}: {total_new} fresh OpenAlex candidates "
              f"(now {len(merged)} families, {n_sources['openalex']} have an "
              f"OpenAlex source tag).")
    return 0


if __name__ == "__main__":
    sys.exit(main())