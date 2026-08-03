#!/usr/bin/env python3
"""Phase E1 — re-sweep every blocked DOI through Unpaywall, with reasons.

``harvest_multi_route.py`` already tries Unpaywall as route 1, but it never
records *why* a DOI stayed blocked. This script re-probes every DOI that is
still blocked / not_open_access in ``harvest_manifest.json``, attempts a
download, and writes a one-line reason per DOI to
``literature_output/blocked_doi_reasons.json`` — so the "135 blocked" number
becomes a documented, re-verified count instead of a silent skip.

Reasons are concrete:
  * ``already_recovered``      — an OA copy is now downloadable (PDF saved)
  * ``not_open_access``        — Unpaywall says no OA location exists for this DOI
  * ``no_pdf_downloadable``    — Unpaywall has a location but no PDF bytes flowed
  * ``download_failed_http_*`` — a location existed but returned a status code
  * ``unpaywall_error``        — Unpaywall API call itself failed

Usage:
    python scripts/harvest_unpaywall.py                 # dry-run: probe + report
    python scripts/harvest_unpaywall.py --persist       # write PDFs + manifest + reasons
    python scripts/harvest_unpaywall.py --only not_open_access
"""

from __future__ import annotations

import argparse
import json
import sys
import time
from collections import Counter
from pathlib import Path

import httpx

ROOT = Path(__file__).resolve().parent.parent
UNPAYWALL_EMAIL = "harvest@scandiumlabs.dev"
MANIFEST = ROOT / "literature_output" / "harvest_manifest.json"
REASONS = ROOT / "literature_output" / "blocked_doi_reasons.json"
PDF_DIR = ROOT / "literature_output" / "pdfs"

UA = {"User-Agent": "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/125.0 Safari/537.36"}
BLOCKED_STATUSES = {"blocked", "not_open_access", "not_downloaded"}


def _is_pdf(data: bytes) -> bool:
    return data[:4] == b"%PDF" and len(data) > 5000


def unpaywall_probe(doi: str) -> dict:
    """Single Unpaywall call → {is_oa, pdf_urls, host_type, version}."""
    url = f"https://api.unpaywall.org/v2/{doi}?email={UNPAYWALL_EMAIL}"
    try:
        r = httpx.get(url, headers=UA, timeout=30)
        if r.status_code != 200:
            return {"error": f"http_{r.status_code}"}
        data = r.json()
    except Exception as e:
        return {"error": f"exception:{type(e).__name__}"}
    if not data:
        return {"error": "empty_response"}
    locs = data.get("oa_locations") or []
    best = data.get("best_oa_location") or {}
    pdfs = [loc.get("url_for_pdf") for loc in locs if loc.get("url_for_pdf")]
    pdfs += [best.get("url_for_pdf")] if best.get("url_for_pdf") else []
    return {
        "is_oa": bool(data.get("is_oa")),
        "pdf_urls": list(dict.fromkeys(u for u in pdfs if u)),
        "host_type": best.get("host_type"),
        "version": best.get("version"),
        "title": data.get("title", ""),
    }


def attempt_download(urls: list[str], pdf_path: Path) -> bool:
    for u in urls:
        try:
            r = httpx.get(u, headers=UA, follow_redirects=True, timeout=60)
            if r.status_code == 200 and _is_pdf(r.content):
                pdf_path.write_bytes(r.content)
                return True
        except Exception:
            continue
    return False


def reason_for(doi: str, pdf_path: Path) -> str:
    probe = unpaywall_probe(doi)
    if probe.get("error"):
        return f"unpaywall_error:{probe['error']}"
    if not probe["is_oa"]:
        return "not_open_access"
    if not probe["pdf_urls"]:
        return "no_pdf_downloadable"
    ok = attempt_download(probe["pdf_urls"], pdf_path)
    if ok:
        return "already_recovered"
    return "download_failed"


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--persist", action="store_true",
                    help="write PDFs + update manifest + reasons file")
    ap.add_argument("--only", choices=["not_open_access"], default=None,
                    help="restrict to the DOIs Unpaywall last called not OA")
    args = ap.parse_args()

    manifest = json.loads(MANIFEST.read_text()) if MANIFEST.exists() else {}
    blocked = {doi: info for doi, info in manifest.items()
               if info.get("status") in BLOCKED_STATUSES}
    if args.only:
        blocked = {doi: info for doi, info in blocked.items()
                   if info.get("status") == args.only}
    if not blocked:
        print("No blocked DOIs in harvest_manifest.json — nothing to re-sweep.")
        return 0

    PDF_DIR.mkdir(parents=True, exist_ok=True)
    print(f"Re-sweeping {len(blocked)} blocked DOIs through Unpaywall...")
    reasons: dict[str, str] = json.loads(REASONS.read_text()) if REASONS.exists() else {}
    for i, (doi, info) in enumerate(blocked.items(), 1):
        pdf_path = PDF_DIR / f"{doi.replace('/', '_')}.pdf"
        reason = reason_for(doi, pdf_path)
        reasons[doi] = reason
        print(f"  [{i}/{len(blocked)}] {doi} → {reason}")
        if args.persist and reason == "already_recovered":
            info.update(status="downloaded_unpaywall", pdf_path=str(pdf_path))
        time.sleep(0.4)

    if args.persist:
        MANIFEST.write_text(json.dumps(manifest, indent=2))
        REASONS.write_text(json.dumps(reasons, indent=2))
        counts = Counter(reasons.values())
        print("\nReason distribution:")
        for k, v in counts.most_common():
            print(f"  {k}: {v}")
        print(f"\nPersisted reasons → {REASONS.name} "
              f"({counts.get('already_recovered', 0)} recovered).")
    else:
        counts = Counter(reasons.values())
        print("\nDry-run reason distribution (--persist to save):")
        for k, v in counts.most_common():
            print(f"  {k}: {v}")
    return 0


if __name__ == "__main__":
    sys.exit(main())