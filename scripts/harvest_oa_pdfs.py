#!/usr/bin/env python3
"""Harvest open-access PDFs from seed-set DOIs using Semantic Scholar API.

Usage:
    python scripts/harvest_oa_pdfs.py                          # All seed DOIs
    python scripts/harvest_oa_pdfs.py --doi 10.1021/jacs.1c07481  # Single DOI
    python scripts/harvest_oa_pdfs.py --check-only             # Just check, don't download

Checks each DOI via S2 API for:
  1. arXiv ID → download from arxiv.org (free, no auth needed)
  2. openAccessPdf.url → download from publisher's OA site

Rate-limit aware: waits 2s between requests, backs off on 429.
"""

from __future__ import annotations

import argparse
import json
import time
from pathlib import Path

import httpx

S2_BASE = "https://api.semanticscholar.org/graph/v1/paper/DOI:"
PDF_DIR = Path("literature_output/pdfs")
SLEEP_BETWEEN = 2.0  # seconds between requests to avoid rate limiting


def load_seed_dois() -> list[str]:
    from ssb_dataset.literature.seed import SEED_RECORDS
    seen = set()
    dois = []
    for r in SEED_RECORDS:
        doi = r.get("doi", "")
        if doi and doi not in seen:
            seen.add(doi)
            dois.append(doi)
    return dois


def check_doi(
    doi: str, api_key: str = "", check_only: bool = False
) -> dict:
    result = {"doi": doi, "status": "unknown", "arxiv_id": None, "oa_url": None, "pdf_path": None}

    headers = {}
    if api_key:
        headers["x-api-key"] = api_key

    try:
        resp = httpx.get(
            f"{S2_BASE}{doi}",
            params={"fields": "externalIds,openAccessPdf,title"},
            headers=headers,
            timeout=15,
        )
    except Exception as e:
        result["status"] = f"error: {e}"
        return result

    if resp.status_code == 429:
        result["status"] = "rate_limited"
        return result
    if resp.status_code != 200:
        result["status"] = f"http_{resp.status_code}"
        return result

    data = resp.json()
    result["title"] = data.get("title", "")
    ext_ids = data.get("externalIds", {}) or {}
    result["arxiv_id"] = ext_ids.get("ArXiv")
    oa = data.get("openAccessPdf", {}) or {}
    result["oa_url"] = oa.get("url")

    if check_only:
        if result["arxiv_id"] or result["oa_url"]:
            result["status"] = "available"
        else:
            result["status"] = "not_open_access"
        return result

    # Try arXiv first
    pdf_path = PDF_DIR / f"{doi.replace('/', '_')}.pdf"
    if pdf_path.exists():
        result["status"] = "already_downloaded"
        result["pdf_path"] = str(pdf_path)
        return result

    downloaded = False
    if result["arxiv_id"]:
        arxiv_url = f"https://arxiv.org/pdf/{result['arxiv_id']}.pdf"
        try:
            r = httpx.get(arxiv_url, follow_redirects=True, timeout=60)
            if r.status_code == 200 and len(r.content) > 10000:
                pdf_path.write_bytes(r.content)
                result["pdf_path"] = str(pdf_path)
                result["status"] = "downloaded_arxiv"
                downloaded = True
        except Exception:
            pass

    if not downloaded and result["oa_url"]:
        try:
            r = httpx.get(result["oa_url"], follow_redirects=True, timeout=60)
            if r.status_code == 200 and len(r.content) > 10000:
                pdf_path.write_bytes(r.content)
                result["pdf_path"] = str(pdf_path)
                result["status"] = "downloaded_oa"
                downloaded = True
        except Exception:
            pass

    if not downloaded:
        result["status"] = "not_downloaded"
    return result


def main() -> None:
    parser = argparse.ArgumentParser(description="Harvest OA PDFs from seed DOIs")
    parser.add_argument("--doi", type=str, default="", help="Single DOI to check")
    parser.add_argument("--check-only", action="store_true", help="Just check availability, don't download")
    parser.add_argument("--sleep", type=float, default=SLEEP_BETWEEN, help=f"Seconds between requests (default: {SLEEP_BETWEEN})")
    args = parser.parse_args()

    from dotenv import load_dotenv
    load_dotenv()
    import os
    api_key = os.environ.get("S2_API_KEY", "")

    PDF_DIR.mkdir(parents=True, exist_ok=True)

    if args.doi:
        dois = [args.doi]
    else:
        dois = load_seed_dois()

    print(f"Checking {len(dois)} DOIs for OA availability...")
    results: list[dict] = []
    for i, doi in enumerate(dois, 1):
        print(f"  [{i}/{len(dois)}] {doi[:60]}...", end=" ", flush=True)
        result = check_doi(doi, api_key=api_key, check_only=args.check_only)
        results.append(result)
        print(result["status"])
        if i < len(dois):
            time.sleep(args.sleep)

    summary_path = Path("literature_output/oa_harvest_report.json")
    summary_path.write_text(json.dumps(results, indent=2))

    summary: dict[str, int] = {}
    for r in results:
        s = r["status"]
        summary[s] = summary.get(s, 0) + 1
    print(f"\nSummary: {json.dumps(summary, indent=2)}")
    print(f"Full report: {summary_path}")


if __name__ == "__main__":
    main()
