#!/usr/bin/env python3
"""Batch ensemble extraction over harvested PDFs, with incremental persistence.

Usage:
    python scripts/batch_extract.py --ensemble 3                 # all unprocessed PDFs
    python scripts/batch_extract.py --pdf <path> --ensemble 3    # single PDF
    python scripts/batch_extract.py --include-processed          # re-extract even if done

Writes per-PDF results to literature_output/extraction_results.json (incremental).
Ensemble >= 3 recommended (see AGENTS.md determinism findings).
"""

from __future__ import annotations

import argparse
import json
import time
from pathlib import Path

from dotenv import load_dotenv

load_dotenv()

from ssb_dataset.config.settings import settings
from ssb_dataset.literature.extraction import extract_from_pdf

ROOT = Path(__file__).resolve().parent.parent
RESULTS = ROOT / "literature_output/extraction_results.json"
PDF_DIR = ROOT / "literature_output/pdfs"


def load_results() -> dict:
    if RESULTS.exists():
        return json.loads(RESULTS.read_text())
    return {}


def save_results(results: dict) -> None:
    RESULTS.write_text(json.dumps(results, indent=2))


def record_to_dict(r) -> dict:
    it = r.ion_transport
    ex = getattr(r, "experiment", None)
    return {
        "pdf": "",
        "family": r.identity.family.value,
        "composition": r.identity.composition or r.identity.source_id,
        "sigma_RT": it.sigma_RT,
        "Ea": it.activation_energy_Ea,
        "method": it.measurement_method,
        "conductivity_type": str(getattr(it, "conductivity_type", "")),
        "temperature_celsius": it.temperature_range_measured.min_K - 273.15
        if it.temperature_range_measured else None,
        "doi": r.text_provenance.source_doi,
        "title": r.text_provenance.source_paper_title,
        "experiment": {
            "sample_form": ex.sample_form if ex else None,
            "relative_density_pct": ex.relative_density_pct if ex else None,
            "pelletizing_pressure_MPa": ex.pelletizing_pressure_MPa if ex else None,
            "electrode_material": ex.electrode_material if ex else None,
            "frequency_min_Hz": ex.frequency_min_Hz if ex else None,
            "frequency_max_Hz": ex.frequency_max_Hz if ex else None,
            "atmosphere": ex.atmosphere if ex else None,
            "sinter_temperature_C": ex.sinter_temperature_C if ex else None,
            "sinter_time_h": ex.sinter_time_h if ex else None,
        } if ex else {},
    }


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--pdf", type=str, default="")
    parser.add_argument("--ensemble", type=int, default=3)
    parser.add_argument("--include-processed", action="store_true")
    parser.add_argument("--max-pdfs", type=int, default=0, help="process at most N PDFs")
    args = parser.parse_args()

    results = load_results()

    if args.pdf:
        pdfs = [Path(args.pdf)]
    else:
        pdfs = sorted(PDF_DIR.glob("*.pdf"))
        if not args.include_processed:
            pdfs = [p for p in pdfs if p.name not in results]

    if args.max_pdfs:
        pdfs = pdfs[: args.max_pdfs]

    print(f"Processing {len(pdfs)} PDFs with ensemble={args.ensemble}")

    for i, pdf in enumerate(pdfs, 1):
        if pdf.name in results and not args.include_processed:
            continue
        print(f"\n[{i}/{len(pdfs)}] === {pdf.name} ===", flush=True)
        try:
            recs = extract_from_pdf(
                pdf,
                skip_grobid=True,
                ensemble_size=args.ensemble,
                llm_api_key=settings.llm.api_key,
                llm_model=settings.llm.model_extraction,
                llm_base_url=settings.llm.base_url,
            )
        except Exception as e:
            print(f"  FAILED: {type(e).__name__}: {e}", flush=True)
            results[pdf.name] = {"error": f"{type(e).__name__}: {e}"}
            save_results(results)
            continue

        entries = []
        for r in recs:
            d = record_to_dict(r)
            d["pdf"] = pdf.name
            entries.append(d)
        results[pdf.name] = entries
        save_results(results)
        print(f"  -> {len(entries)} records saved", flush=True)

    n_with_records = sum(1 for v in results.values() if isinstance(v, list) and len(v) > 0)
    print(f"\nDone. {n_with_records}/{len(results)} PDFs have extraction records.")


if __name__ == "__main__":
    main()
