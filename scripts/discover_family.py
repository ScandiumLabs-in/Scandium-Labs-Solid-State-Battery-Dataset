#!/usr/bin/env python3
"""Re-run discovery for a single family and merge into discovery_candidates.json.

Usage:
    python scripts/discover_family.py oxide            # re-discover one family
    python scripts/discover_family.py --all-missing    # re-run families with 0 candidates
"""

from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path

from dotenv import load_dotenv

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

load_dotenv()

from ssb_dataset.literature.discovery import (
    SEARCH_TERMS,
    _search_term,
    triage_candidates,
)
from ssb_dataset.schema import Family


def load_candidates(path: Path) -> dict[str, list[dict]]:
    if path.exists():
        return json.loads(path.read_text())
    return {}


def save_candidates(data: dict[str, list[dict]], path: Path) -> None:
    path.write_text(json.dumps(data, indent=2))
    print(f"Saved candidates to {path}")


def discover_family(family: Family, api_key: str, max_results: int = 100) -> list[dict]:
    headers = {"x-api-key": api_key} if api_key else {}
    all_papers: list[dict] = []
    for term in SEARCH_TERMS[family]:
        papers = _search_term(term, headers, max_results)
        print(f"  '{term[:50]}' -> {len(papers)} papers")
        all_papers.extend(papers)
    candidates = triage_candidates(all_papers)
    return [_paper_to_dict(c) for c in candidates]


def _paper_to_dict(p) -> dict:
    return {
        "doi": p.doi,
        "title": p.title,
        "abstract": p.abstract,
        "relevance_score": p.relevance_score,
        "family_tags": [f.value for f in p.family_tags],
    }


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("family", nargs="?", help="Family name to re-discover")
    parser.add_argument("--all-missing", action="store_true")
    args = parser.parse_args()

    api_key = os.environ.get("S2_API_KEY", "")
    path = Path("literature_output/discovery_candidates.json")
    data = load_candidates(path)

    families: list[Family]
    if args.all_missing:
        families = [f for f in Family if len(data.get(f.value, [])) == 0]
        print(f"Families with 0 candidates: {[f.value for f in families]}")
    elif args.family:
        families = [Family(args.family)]
    else:
        parser.error("provide a family name or --all-missing")

    for fam in families:
        print(f"\nRe-discovering {fam.value}...")
        cands = discover_family(fam, api_key)
        print(f"  -> {len(cands)} candidates")
        if cands:
            data[fam.value] = cands

    save_candidates(data, path)


if __name__ == "__main__":
    main()
