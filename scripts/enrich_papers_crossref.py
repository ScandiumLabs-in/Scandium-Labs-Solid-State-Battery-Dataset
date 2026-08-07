"""v1.2 — optional Crossref enrichment for the papers table (Phase 10).

The deterministic tier (ssb_dataset.db.papers) recovers title/journal/year
from on-disk caches + PDF first pages. This script is the *opt-in network
route*: it queries the Crossref REST API for any paper whose metadata is
still unknown and persists results to:

    literature_output/crossref_metadata.json   DOI -> {title, journal, year}

Run it whenever a network is available; the release gates never require it
(the deterministic floor alone passes). Idempotent and resumable — re-running
only queries DOIs not already cached.

Usage:
    python scripts/enrich_papers_crossref.py [--refresh] [--limit N]
"""

from __future__ import annotations

import argparse
import json
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
CACHE = ROOT / "literature_output" / "crossref_metadata.json"

# Crossref politely asks for a mailto; make it configurable via env so the
# DOI is never hardcoded to a personal address.
MAILTO = None  # set CROSSREF_MAILTO env var to get a faster polite pool


def _load_cache() -> dict:
    if CACHE.exists():
        try:
            return json.loads(CACHE.read_text())
        except (json.JSONDecodeError, OSError):
            return {}
    return {}


def _save_cache(cache: dict) -> None:
    CACHE.parent.mkdir(exist_ok=True)
    CACHE.write_text(json.dumps(cache, indent=2, sort_keys=True))


def _crossref(doi: str, refresh: bool) -> dict | None:
    import urllib.error
    import urllib.parse
    import urllib.request

    url = "https://api.crossref.org/works/" + urllib.parse.quote(doi)
    if MAILTO:
        url += "?mailto=" + MAILTO
    req = urllib.request.Request(url, headers={"User-Agent": "scandium-ssb-dataset/1.2 (metadata enrichment)"})
    try:
        with urllib.request.urlopen(req, timeout=30) as resp:
            body = json.loads(resp.read().decode())
    except (urllib.error.HTTPError, urllib.error.URLError, TimeoutError, OSError):
        return None
    msg = (body or {}).get("message", {})
    title = None
    if msg.get("title"):
        title = " ".join(str(t) for t in msg["title"]).strip() or None
    journal = None
    if msg.get("container-title"):
        journal = " ".join(str(j) for j in msg["container-title"]).strip() or None
    year = None
    for key in ("published-print", "published-online", "issued", "created"):
        d = msg.get(key, {}).get("date-parts", [])
        if d and d[0] and d[0][0]:
            try:
                year = int(d[0][0])
                break
            except (TypeError, ValueError):
                continue
    if not any((title, journal, year)):
        return None
    return {"title": title, "journal": journal, "year": year}


def main() -> int:
    global MAILTO
    import os

    import pandas as pd

    parser = argparse.ArgumentParser(description="Crossref metadata enrichment for the papers table")
    parser.add_argument("--refresh", action="store_true",
                        help="re-query DOIs already in the cache")
    parser.add_argument("--limit", type=int, default=0,
                        help="max DOIs to query this run (0 = all)")
    args = parser.parse_args()
    MAILTO = os.environ.get("CROSSREF_MAILTO")

    from ssb_dataset.db import papers as P

    caches = P.load_metadata_caches()
    papers = pd.read_parquet(ROOT / "relational_output" / "papers.parquet")
    already = _load_cache()
    to_query: list[str] = []
    for doi in papers["doi"]:
        if not doi:
            continue
        if args.refresh or doi not in already:
            to_query.append(str(doi))
    if args.limit:
        to_query = to_query[: args.limit]

    if not to_query:
        print("No DOIs to query (all cached or already covered).")
        return 0

    print(f"Querying Crossref for {len(to_query)} DOIs (network) ...")
    updated = 0
    for i, doi in enumerate(to_query, 1):
        rec = _crossref(doi, args.refresh)
        if rec:
            already[doi] = rec
            updated += 1
        if i % 10 == 0:
            _save_cache(already)
            print(f"  ... {i}/{len(to_query)} ({updated} updated)")
        time.sleep(1.0)  # polite pool
    _save_cache(already)
    print(f"Done: {updated}/{len(to_query)} DOIs enriched -> {CACHE.name}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
