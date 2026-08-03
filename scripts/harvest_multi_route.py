#!/usr/bin/env python3
"""Multi-route OA PDF harvester — recovers PDFs the S2-only harvester missed.

Route order (first real PDF wins):
  1. Unpaywall (api.unpaywall.org) for all OA locations.
  2. OpenAlex OA URL (free, no key) for works Unpaywall misses.
  3. Direct publisher PDF URL.
  4. Europe PMC render (https://europepmc.org/articles/<PMCxx>?pdf=render)
     — works for MDPI/Nature/Elsevier when the publisher 403s the bot but the
       article was deposited in PMC.
  5. CORE API (needs CORE_API_KEY; free tier) for repository OA copies.
  6. BASE (Bielefeld Academic Search Engine) as a final landing-page hop.
  7. Semantic Scholar openAccessPdf (fallback for DOIs Unpaywall misses).

  DOAJ pre-check: ``venue_is_oa()`` confirms a DOI's venue is genuinely OA so we
  know a failed harvest is a route problem, not a wasted attempt on a paywall.

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


def openalex_oa_url(doi: str) -> str | None:
    """Phase E1: free OpenAlex route for works Unpaywall returns nothing for."""
    try:
        r = httpx.get(
            "https://api.openalex.org/works/https://doi.org/" + doi,
            params={"select": "open_access", "mailto": UNPAYWALL_EMAIL},
            headers=UA, follow_redirects=True, timeout=30,
        )
        if r.status_code == 200:
            oa = (r.json().get("open_access") or {})
            return oa.get("oa_url") or oa.get("oa_pdf_url")
    except Exception:
        pass
    return None


def venue_is_oa(doi: str) -> bool | None:
    """DOAJ pre-check: is this DOI's venue a genuinely open-access journal?

    None means DOAJ couldn't confirm either way (hybrid/OA-article-not-journal
    cases) — callers treat None as "don't know", not "paywalled".
    """
    try:
        r = httpx.get(
            "https://doaj.org/api/search/articles/" + doi,
            headers=UA, timeout=30,
        )
        if r.status_code != 200:
            return None
        data = r.json()
        if not data.get("results"):
            return None
        bib = data["results"][0].get("bibjson") or {}
        if bib.get("journal") and bib["journal"].get("oa_status"):
            return True
        return bool(data["results"][0].get("oa_status"))
    except Exception:
        return None


def core_oa_url(doi: str) -> str | None:
    """CORE API route (free tier, needs CORE_API_KEY)."""
    import os
    key = os.environ.get("CORE_API_KEY", "")
    if not key:
        return None
    try:
        r = httpx.post(
            "https://api.core.ac.uk/v3/search/works",
            headers={"Authorization": f"Bearer {key}",
                     "Content-Type": "application/json"},
            json={"q": f"doi:\"{doi}\"", "limit": 5},
            timeout=30,
        )
        if r.status_code != 200:
            return None
        for rec in r.json().get("results", []):
            for field in ("downloadUrl", "link", "fullTextIdentifier"):
                u = (rec.get(field) or "").strip()
                if u:
                    return u
    except Exception:
        pass
    return None


def base_landing_url(doi: str) -> str | None:
    """BASE search → first hit's landing URL (free, no key). TGrep-geometry."""
    try:
        r = httpx.get(
            "https://api.base-search.net/cgi-bin/BaseHttpSearchInterface.fcgi",
            params={"func": "PerformSearch", "query": f'doi:"{doi}"',
                    "format": "jsonv1", "hits": "5"},
            headers=UA, timeout=30,
        )
        if r.status_code != 200:
            return None
        hits = (((r.json().get("response") or {}).get("docs") or {})
                .get("result") or [])
        for hit in hits:
            ids = hit.get("dc:identifier") or hit.get("fulltextURL")
            if isinstance(ids, list) and ids:
                return str(ids[0])
            if ids:
                return str(ids)
    except Exception:
        pass
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
        "reason": None,
        "venue_oa": None,
    }
    pdf_path = PDF_DIR / f"{doi.replace('/', '_')}.pdf"
    if pdf_path.exists():
        result["status"] = "already_have"
        result["pdf_path"] = str(pdf_path)
        return result

    result["venue_oa"] = venue_is_oa(doi)

    cands = unpaywall_locations(doi)
    if not cands:
        oa = openalex_oa_url(doi)
        if oa:
            cands = [oa]
    if not cands:
        s2 = s2_oa_url(doi)
        if s2:
            cands = [s2]

    # 1. direct download attempts (Unpaywall / OpenAlex / S2 URLs)
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

    # 3. CORE (free tier, key-gated) repository copies
    core = core_oa_url(doi)
    if core:
        r = _get(core)
        if r is not None and r.status_code == 200 and _is_pdf(r.content):
            pdf_path.write_bytes(r.content)
            result.update(status="downloaded_core", url=core, pdf_path=str(pdf_path))
            return result

    # 4. BASE landing page → follow any PDF-looking link on it
    base = base_landing_url(doi)
    if base:
        r = _get(base)
        if r is not None and r.status_code == 200 and _is_pdf(r.content):
            pdf_path.write_bytes(r.content)
            result.update(status="downloaded_base", url=base, pdf_path=str(pdf_path))
            return result

    result["reason"] = (
        "not_open_access" if result["venue_oa"] is False
        else "no_oa_route_reachable"
    )
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
        print(res["status"] + (f" ({res['reason']})" if res.get("reason") else ""))
        entry = updated.setdefault(doi, {})
        entry.update({"status": res["status"], "pdf_path": res["pdf_path"],
                      "source_url": res["url"], "venue_oa": res["venue_oa"]})
        if res.get("reason"):
            entry["reason"] = res["reason"]
        if args.check_only:
            continue
        MANIFEST.write_text(json.dumps(updated, indent=2))
        time.sleep(0.5)

    MANIFEST.write_text(json.dumps(updated, indent=2))
    from collections import Counter
    print("Summary:", dict(Counter(v["status"] for v in updated.values())))


if __name__ == "__main__":
    main()
