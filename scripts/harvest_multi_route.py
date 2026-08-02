#!/usr/bin/env python3
"""Multi-route OA PDF harvester — recovers PDFs the S2-only harvester missed.

Route order (first real PDF wins):
  1. Unpaywall (api.unpaywall.org) for all OA locations.
  2. Direct publisher PDF URL.
  3. Europe PMC render (https://europepmc.org/articles/<PMCxx>?pdf=render)
     — works for MDPI/Nature/Elsevier when the publisher 403s the bot but the
       article was deposited in PMC.
  4. Semantic Scholar openAccessPdf (fallback for DOIs Unpaywall misses).

Usage:
    python scripts/harvest_multi_route.py --doi 10.3390/ma13030560
    python scripts/harvest_multi_route.py --file gold-list.txt
    python scripts/harvest_multi_route.py --unpaywall-blocked
        # re-tries DOIs already marked not_open_access in harvest_manifest.json
    python scripts/harvest_multi_route.py --check-only
"""

from __future__ import annotations

import argparse
import json
import re
import time
from pathlib import Path

import httpx

UNPAYWALL_EMAIL = "harvest@scandiumlabs.dev"
PDF_DIR = Path("literature_output/pdfs")
MANIFEST = Path("literature_output/harvest_manifest.json")
GOLD_LIST = Path("literature_output/gold_harvest_list.json")

UA = {"User-Agent": "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/125.0 Safari/537.36"}


def _is_pdf(data: bytes) -> bool:
    return data[:4] == b"%PDF" and len(data) > 5000


def _get(url: str, timeout: float = 30.0) -> httpx.Response | None:
    try:
        return httpx.get(url, headers=UA, follow_redirects=True, timeout=timeout)
    except Exception:
        return None


def unpaywall_locations(doi: str) -> list[str]:
    """Return candidate OA URLs for a DOI (pdf URLs first)."""
    url = f"https://api.unpaywall.org/v2/{doi}?email={UNPAYWALL_EMAIL}"
    r = _get(url)
    if r is None or r.status_code != 200:
        return []
    try:
        data = r.json()
    except Exception:
        return []
    cands: list[str] = []
    for loc in data.get("oa_locations") or []:
        for field in ("url_for_pdf", "url"):
            u = loc.get(field)
            if u:
                cands.append(u)
    return cands


def s2_oa_url(doi: str) -> str | None:
    url = f"https://api.semanticscholar.org/graph/v1/paper/DOI:{doi}?fields=openAccessPdf"
    r = _get(url)
    if r is None or r.status_code != 200:
        return None
    try:
        return (r.json().get("openAccessPdf") or {}).get("url")
    except Exception:
        return None


def europepmc_for(candidates: list[str]) -> str | None:
    """If any candidate is a PMC article, return the Europe PMC PDF render URL."""
    for u in candidates:
        m = re.search(r"PMC\d+", u)
        if m and "pmc.ncbi.nlm.nih.gov" in u or "/PMC" in u:
            pmc = m.group(0)
            return f"https://europepmc.org/articles/{pmc}?pdf=render"
    return None


def harvest(doi: str) -> dict:
    result = {
        "doi": doi,
        "status": "blocked",
        "url": None,
        "pdf_path": None,
    }
    pdf_path = PDF_DIR / f"{doi.replace('/', '_')}.pdf"
    if pdf_path.exists():
        result["status"] = "already_have"
        result["pdf_path"] = str(pdf_path)
        return result

    cands = unpaywall_locations(doi)
    if not cands:
        s2 = s2_oa_url(doi)
        if s2:
            cands = [s2]

    # 1. direct download attempts
    for u in cands:
        r = _get(u)
        if r is not None and r.status_code == 200 and _is_pdf(r.content):
            pdf_path.write_bytes(r.content)
            result.update(status="downloaded_direct", url=u, pdf_path=str(pdf_path))
            return result

    # 2. Europe PMC render
    epmc = europepmc_for(cands)
    if epmc:
        r = _get(epmc)
        if r is not None and r.status_code == 200 and _is_pdf(r.content):
            pdf_path.write_bytes(r.content)
            result.update(status="downloaded_epmc", url=epmc, pdf_path=str(pdf_path))
            return result

    return result


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--doi", type=str, default="")
    ap.add_argument("--file", type=Path, default=None, help="file with one DOI per line")
    ap.add_argument("--unpaywall-blocked", action="store_true",
                    help="re-try DOIs marked not_open_access in harvest_manifest.json")
    ap.add_argument("--check-only", action="store_true")
    args = ap.parse_args()

    PDF_DIR.mkdir(parents=True, exist_ok=True)

    dois: list[str] = []
    if args.doi:
        dois = [args.doi]
    elif args.file:
        dois = [l.strip() for l in args.file.read_text().splitlines() if l.strip()]
    elif args.unpaywall_blocked:
        manifest = json.loads(MANIFEST.read_text())
        dois = [doi for doi, info in manifest.items() if info.get("status") == "not_open_access"]

    if not dois:
        print("No DOIs to process. Pass --doi, --file, or --unpaywall-blocked.")
        return

    print(f"Harvesting {len(dois)} DOIs (multi-route)...")
    updated = json.loads(MANIFEST.read_text()) if MANIFEST.exists() else {}
    for i, doi in enumerate(dois, 1):
        print(f"  [{i}/{len(dois)}] {doi}", end=" ", flush=True)
        res = harvest(doi)
        print(res["status"])
        entry = updated.setdefault(doi, {})
        entry.update({"status": res["status"], "pdf_path": res["pdf_path"], "source_url": res["url"]})
        if args.check_only:
            continue
        MANIFEST.write_text(json.dumps(updated, indent=2))
        time.sleep(0.5)

    MANIFEST.write_text(json.dumps(updated, indent=2))
    from collections import Counter
    print("Summary:", dict(Counter(v["status"] for v in updated.values())))


if __name__ == "__main__":
    main()
