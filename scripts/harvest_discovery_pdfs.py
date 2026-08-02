#!/usr/bin/env python3
"""Batch-download OA PDFs for discovery candidates into papers/<family>/.

Usage:
    python scripts/harvest_discovery_pdfs.py --max-per-family 10   # top N by relevance per family
    python scripts/harvest_discovery_pdfs.py --family sulfide       # one family
    python scripts/harvest_discovery_pdfs.py --check-only          # report OA status only

Stores PDFs at papers/<family>/<doi-sanitized>.pdf and writes a manifest JSON
(papers/harvest_manifest.json) tracking doi -> status/pdf_path. Legitimate OA
sources only (arXiv, Europe PMC, SpringerLink, publisher OA via Unpaywall).
"""

from __future__ import annotations

import argparse
import json
import time
from pathlib import Path

from dotenv import load_dotenv

load_dotenv()

from ssb_dataset.literature.extraction import _download_pdf_from_doi

ROOT = Path(__file__).resolve().parent.parent


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--max-per-family", type=int, default=10)
    parser.add_argument("--family", type=str, default="")
    parser.add_argument("--check-only", action="store_true")
    parser.add_argument("--sleep", type=float, default=1.0)
    parser.add_argument(
        "--list",
        type=str,
        default="",
        help="Path to a JSON list of {doi, family, ...} items to harvest instead of discovery candidates.",
    )
    args = parser.parse_args()

    pdf_dir = ROOT / "literature_output/pdfs"
    pdf_dir.mkdir(parents=True, exist_ok=True)

    if args.list:
        items = json.loads(Path(args.list).read_text())
        papers_by_fam: dict[str, list[dict]] = {}
        for it in items:
            papers_by_fam.setdefault(it.get("family", "misc"), []).append(it)
        families = [args.family] if args.family else list(papers_by_fam.keys())
        candidates = papers_by_fam
    else:
        candidates = json.loads(
            (ROOT / "literature_output/discovery_candidates.json").read_text()
        )
        families = [args.family] if args.family else list(candidates.keys())

    manifest = {}

    for fam in families:
        papers = sorted(
            candidates.get(fam, []),
            key=lambda p: p.get("relevance_score", p.get("score", 0)),
            reverse=True,
        )[: args.max_per_family]
        fam_dir = pdf_dir
        print(f"\n=== {fam}: {len(papers)} papers ===")
        for p in papers:
            doi = p["doi"]
            out = pdf_dir / f"{doi.replace('/', '_')}.pdf"
            if out.exists():
                manifest[doi] = {"family": fam, "status": "already_have", "pdf_path": str(out)}
                print(f"  [have] {doi[:45]}  ({out.stat().st_size} bytes)")
                continue
            try:
                _download_pdf_from_doi(doi, out)
                if out.exists():
                    manifest[doi] = {"family": fam, "status": "downloaded", "pdf_path": str(out)}
                    print(f"  [OK]   {doi[:45]}  ({out.stat().st_size} bytes)")
                else:
                    manifest[doi] = {"family": fam, "status": "not_open_access", "pdf_path": None}
                    print(f"  [none] {doi[:45]}")
            except Exception as e:
                manifest[doi] = {"family": fam, "status": f"error: {e}", "pdf_path": None}
                print(f"  [ERR]  {doi[:45]}  {type(e).__name__}")
            time.sleep(args.sleep)

    (ROOT / "literature_output/harvest_manifest.json").write_text(
        json.dumps(manifest, indent=2)
    )
    n_ok = sum(1 for v in manifest.values() if v["status"] in ("downloaded", "already_have"))
    print(f"\nHarvest complete: {n_ok}/{len(manifest)} PDFs available")


if __name__ == "__main__":
    main()
