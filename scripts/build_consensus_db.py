#!/usr/bin/env python3
"""Build the cross-paper consensus database (Scandium Stage 3 / M5).

Aggregates every verified label (approved queue + canonical dataset + benchmark
inventory) into per-material consensus statistics and persists them as
literature_output/consensus_db.parquet (tabular) + consensus_db.json (full).

Usage:
    python scripts/build_consensus_db.py                 # offline, deterministic
    python scripts/build_consensus_db.py --enrich-dois   # + Crossref journal/year lookup
"""

from __future__ import annotations

import argparse
import json
import time
from pathlib import Path

import httpx

from ssb_dataset.literature.consensus_db import (
    build_consensus_db,
    summary,
    to_parquet,
    _register_doi_meta,
)

ROOT = Path(__file__).resolve().parent.parent
OUT_JSON = ROOT / "literature_output/consensus_db.json"
OUT_PARQUET = ROOT / "literature_output/consensus_db.parquet"


def _collect_dois(groups) -> set[str]:
    dois: set[str] = set()
    for cr in groups.values():
        dois.update(cr.doiss)
    return dois


def enrich_doi_meta(dois: set[str], timeout: float = 15.0) -> dict[str, dict]:
    """Crossref lookup for journal + year per DOI (best-effort, rate-limited).

    Resolves the filename-safe underscore form (10.1021_acs...) to the canonical
    slash form (10.1021/acs...) before querying Crossref. Populates the in-memory
    DOI metadata map used by the consensus aggregator."""
    from ssb_dataset.config.settings import settings
    from ssb_dataset.literature.consensus_db import _doi_variants

    mailto = settings.crossref.mailto
    meta: dict[str, dict] = {}
    for i, doi in enumerate(sorted(dois)):
        canon = None
        for cand in _doi_variants(doi):
            try:
                resp = httpx.get(
                    f"https://api.crossref.org/works/{cand}",
                    params={"mailto": mailto},
                    timeout=timeout,
                )
                if resp.status_code == 200:
                    canon = cand
                    break
                time.sleep(0.1)
            except Exception:
                break
        if canon is None:
            continue
        try:
            resp = httpx.get(
                f"https://api.crossref.org/works/{canon}",
                params={"mailto": mailto},
                timeout=timeout,
            )
            if resp.status_code == 200:
                msg = resp.json().get("message", {})
                year = None
                ip = msg.get("issued", {}).get("date-parts", [[None]])
                if ip and ip[0] and ip[0][0]:
                    year = int(ip[0][0])
                meta[canon] = {
                    "journal": (msg.get("container-title") or [None])[0],
                    "title": (msg.get("title") or [None])[0],
                    "year": year,
                }
            time.sleep(0.2)
        except Exception:
            pass
    return meta


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--enrich-dois", action="store_true",
                        help="fetch missing journal/year metadata from Crossref")
    args = parser.parse_args()

    groups = build_consensus_db(
        queue_path=str(ROOT / "review_output/queue.json"),
        canonical_path=str(ROOT / "cleaning_output/canonical_dataset.parquet"),
    )

    if args.enrich_dois:
        dois = _collect_dois(groups)
        print(f"Resolving {len(dois)} DOIs via Crossref...")
        meta = enrich_doi_meta(dois)
        _register_doi_meta(meta)
        print(f"  registered metadata for {len(meta)} DOIs")
        # rebuild so the enrichment feeds publication_years/journals
        groups = build_consensus_db(
            queue_path=str(ROOT / "review_output/queue.json"),
            canonical_path=str(ROOT / "cleaning_output/canonical_dataset.parquet"),
        )

    payload = {grp: cr.to_dict() for grp, cr in sorted(groups.items())}
    OUT_JSON.write_text(json.dumps(payload, indent=2))
    to_parquet(groups, str(OUT_PARQUET))
    print(f"Wrote {len(groups)} materials -> {OUT_JSON}")
    print(json.dumps(summary(groups), indent=2))


if __name__ == "__main__":
    main()
