#!/usr/bin/env python3
"""Deterministic metadata backfill for the verified experimental records.

Closes two release gates without any LLM call:

  - metadata_completeness: scans each record's source PDF text layer with
    priority-ordered method patterns (`src/ssb_dataset/pipeline/methods.py`)
    and stamps `ion_transport.measurement_method`. Covers EIS / DC
    polarization / four-point probe / van der Pauw / galvanostatic /
    potentiostatic / GITT / AC conductivity / NMR / DFT / AIMD / MD.
  - evidence_coverage: uses `verifier.locate_evidence` to recover the
    evidence page for records that already carry an evidence sentence but
    lack a page number.

Idempotent: only fills fields that are currently missing; never overwrites
human-entered values.

Usage:
  python scripts/backfill_metadata.py --dry-run      # report what would change
  python scripts/backfill_metadata.py --apply        # stamp into canonical parquet
  python scripts/backfill_metadata.py --apply --out path.parquet
"""

from __future__ import annotations

import argparse
from pathlib import Path

import pandas as pd
import pyarrow as pa
import pyarrow.parquet as pq

import sys

BASE = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(BASE))
sys.path.insert(0, str(BASE / "src"))

from ssb_dataset.pipeline.methods import extract_measurement_method_from_pdf
from ssb_dataset.pipeline.verifier import locate_evidence

CANONICAL = BASE / "cleaning_output" / "canonical_dataset.parquet"
PDFS = BASE / "literature_output" / "pdfs"

SIGMA_COL = "ion_transport.sigma_RT"
EA_COL = "ion_transport.activation_energy_Ea"
METHOD_COL = "ion_transport.measurement_method"
PAGE_COL = "text_provenance.evidence_page"
SENT_COL = "text_provenance.evidence_sentence"


def doi_to_pdf(doi: str) -> Path | None:
    """Map a DOI to the harvested PDF filename (DOI / -> _)."""
    if not doi:
        return None
    candidate = PDFS / f"{str(doi).replace('/', '_')}.pdf"
    return candidate if candidate.exists() else None


def _has(v) -> bool:
    return v is not None and str(v) not in ("", "nan", "None")


def backfill(df: pd.DataFrame, *, apply: bool) -> dict:
    """Return (rows_changed_method, rows_changed_page, could_not_scan)."""
    method_changed = 0
    page_changed = 0
    no_pdf = 0
    no_text = 0
    summary: dict = {"method_filled": [], "page_filled": [], "no_pdf": [], "no_text": []}

    labelled_idx = df[df["ion_transport.label_available"] == True].index

    for idx in labelled_idx:
        row = df.loc[idx]
        doi = row.get("text_provenance.source_doi") or row.get("identity.source_id") or ""
        pdf = doi_to_pdf(doi)

        # --- measurement method ---
        if not _has(row.get(METHOD_COL)):
            if pdf is None:
                no_pdf += 1
                summary["no_pdf"].append(str(row.get("identity.material_id")))
            else:
                match = extract_measurement_method_from_pdf(pdf)
                if match.measurement_method is None:
                    no_text += 1
                    summary["no_text"].append(str(row.get("identity.material_id")))
                elif apply:
                    df.at[idx, METHOD_COL] = match.measurement_method
                    method_changed += 1
                    summary["method_filled"].append(
                        (str(row.get("identity.material_id")), match.measurement_method)
                    )
                else:
                    method_changed += 1
                    summary["method_filled"].append(
                        (str(row.get("identity.material_id")), match.measurement_method)
                    )

        # --- evidence page (only when we have a sentence but no page) ---
        if _has(row.get(SENT_COL)) and not _has(row.get(PAGE_COL)):
            if pdf is None:
                continue
            comp = row.get("identity.material_id") or ""
            sigma = row.get(SIGMA_COL)
            ea = row.get(EA_COL)
            ev = locate_evidence(pdf, comp, float(sigma) if sigma is not None else None,
                                 float(ea) if ea is not None else None)
            if ev is not None and ev.page:
                if apply:
                    df.at[idx, PAGE_COL] = ev.page
                page_changed += 1
                summary["page_filled"].append(
                    (str(row.get("identity.material_id")), ev.page)
                )

    return {
        "method_changed": method_changed,
        "page_changed": page_changed,
        "no_pdf": no_pdf,
        "no_text": no_text,
        "method_filled": summary["method_filled"],
        "page_filled": summary["page_filled"],
    }


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--apply", action="store_true")
    parser.add_argument("--out", type=Path, default=CANONICAL)
    args = parser.parse_args()

    df = pd.read_parquet(CANONICAL)
    res = backfill(df, apply=args.apply)
    print(f"records scanned (verified): {int((df['ion_transport.label_available'] == True).sum())}")
    print(f"measurement_method filled: {res['method_changed']}")
    print(f"  no PDF available: {res['no_pdf']}   no text layer: {res['no_text']}")
    print(f"evidence page filled: {res['page_changed']}")
    if args.apply:
        pq.write_table(pa.Table.from_pandas(df), args.out)
        print(f"written -> {args.out}")
    else:
        print("dry-run (--apply to write)")

    if res["method_filled"]:
        print("\n  method fills:")
        for mid, m in res["method_filled"]:
            print(f"    {mid}: {m}")


if __name__ == "__main__":
    main()
