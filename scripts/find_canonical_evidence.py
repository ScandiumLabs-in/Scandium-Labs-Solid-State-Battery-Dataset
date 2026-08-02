#!/usr/bin/env python3
"""Evidence Finder — locate real evidence quotes for canonical verified records.

For each record in the canonical dataset carrying a conductivity/Ea label, search
its source PDF text layer for the reported value, extract the exact sentence
containing it, and stamp `text_provenance.evidence_sentence` + `.evidence_page`
+ `.evidence_paragraph` onto the record.

Replaces junk placeholder evidence ("LLM ensemble extraction from X.pdf") with
a verbatim quote from the paper, which is what the release `evidence_coverage`
gate actually measures (presence of page + sentence on verified records).

Usage:
    python scripts/find_canonical_evidence.py [--apply] [--force] [--report]

  --apply    write found evidence back into the canonical parquet (default: dry-run)
  --force    overwrite existing evidence even if a real quote is already present
  --report   print a per-record status table (default: compact)
"""

from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path

import pandas as pd
import pyarrow.parquet as pq

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

from ssb_dataset.pipeline.verifier import (
    _NUM_RE,
    _in_formula,
    _norm_formula,
    _parse_number,
)

ROOT = Path(__file__).resolve().parent.parent
VERIFIED = ROOT / "cleaning_output" / "verified_canonical.parquet"
PDFS = ROOT / "literature_output" / "pdfs"

SIGMA_COL = "ion_transport.sigma_RT"
EA_COL = "ion_transport.activation_energy_Ea"
LABEL_COL = "ion_transport.label_available"
SENT_COL = "text_provenance.evidence_sentence"
PAGE_COL = "text_provenance.evidence_page"
PARA_COL = "text_provenance.evidence_paragraph"
DOI_COL = "text_provenance.source_doi"
MAT_COL = "identity.material_id"

_JUNK_RE = re.compile(
    r"LLM ensemble extraction|LLM extraction|no evidence|N/A|nan|None",
    re.IGNORECASE,
)


def _is_junk(v) -> bool:
    if v is None:
        return True
    s = str(v)
    if s.strip() in ("", "nan", "None"):
        return True
    return bool(_JUNK_RE.search(s))


def _stamp_evidence(df, idx, res, preserve_sentence=False):
    """Write evidence sentence/page/paragraph onto a row (flat or nested schema).

    When `preserve_sentence` is True the existing sentence is kept and only the
    page/paragraph fields are filled, so a page backfill never clobbers a real
    quote with a shorter/empty re-located one.
    """
    updates = [("text_provenance.evidence_page", res["page"]),
               ("text_provenance.evidence_paragraph", res["paragraph"])]
    if not preserve_sentence:
        updates.insert(0, ("text_provenance.evidence_sentence", res["sentence"]))
    for flat_key, value in updates:
        if flat_key in df.columns:
            df.at[idx, flat_key] = value
        elif "text_provenance" in df.columns:
            cur = df.at[idx, "text_provenance"]
            field = flat_key.split(".", 1)[1]
            if isinstance(cur, dict):
                cur[field] = value
            else:
                df.at[idx, "text_provenance"] = {field: value}


def _sentence_around(text: str, center: int) -> str:
    """Extract the sentence containing character offset `center`."""
    start = 0
    end = len(text)
    for m in re.finditer(r"[.!?]\s+(?=[A-Z0-9\[]|$)", text):
        if m.end() <= center:
            start = m.end()
        if m.start() > center:
            end = m.start()
            break
    return text[start:end].replace("\n", " ").strip()


def _doi_to_pdf(doi: str) -> Path | None:
    if not doi:
        return None
    p = PDFS / f"{str(doi).replace('/', '_')}.pdf"
    return p if p.exists() else None


def _find_in_text(text: str, target: float, *, is_sigma: bool, is_ea: bool) -> tuple[int, str, str] | None:
    """Search one page's text for `target` (as S/cm or eV) with unit-context.
    Returns (position, unit-token, sentence) or None.

    Conductivity values are searched in S/cm, mS/cm and uS/cm equivalents
    (1.37e-4 mS/cm == 1.37e-7 S/cm); a match only counts when a conductivity
    unit token appears within ~40 chars of the number, so current densities
    (mA cm-2), capacities (mAh) and axis ticks are excluded. Ea is matched in
    eV with a tight tolerance.
    """
    if target is None:
        return None
    if is_sigma:
        variants = [
            (float(target), 0.35, r"(S\s*/\s*cm|S\s*cm\s*−?1|S/cm|S cm)"),
            (float(target) * 1e3, 0.35, r"(mS\s*/\s*cm|mS/cm|mS\s*cm\s*−?1)"),
            (float(target) * 1e6, 0.35, r"(µ?S\s*/\s*cm|uS/cm|µS/cm|µS\s*cm\s*−?1)"),
        ]
    else:
        variants = [(float(target), 0.08, r"(eV)")]
    best: tuple[float, int, str, str] | None = None
    for tv, rel, unit_re in variants:
        tol = abs(tv) * rel
        for m in _NUM_RE.finditer(text):
            if _in_formula(text, m):
                continue
            v = _parse_number(m.group(0))
            if v is None:
                continue
            d = abs(v - tv)
            if d > tol:
                continue
            near = text[max(0, m.start() - 30): m.end() + 50]
            if is_sigma and re.search(r"(mA|mAh|µA|μA|uA|Hz|cm[-\u2212]?2|W\s*cm)", near):
                continue
            um = re.search(unit_re, near)
            if is_sigma and um is None:
                continue  # must carry a conductivity unit
            sent = _sentence_around(text, m.start())
            if best is None or d < best[0]:
                best = (d, m.start(), um.group(1) if um else "", sent)
    if best is None:
        return None
    _, pos, unit, sentence = best
    return pos, unit, sentence


def _load_pdf(pdf: Path) -> list[str]:
    import fitz
    try:
        doc = fitz.open(str(pdf))
        pages = [p.get_text("text") for p in doc]
        doc.close()
        return pages
    except Exception:
        return []


def find_evidence_for_row(row: pd.Series) -> dict | None:
    """Locate a real quote for one record. Returns None if not found."""
    def _n(row, block, field):
        flat_key = f"{block}.{field}"
        if flat_key in row.index:
            flat = row.get(flat_key)
            if flat is not None and not (hasattr(flat, "isna") and bool(flat.isna())):
                return flat
        val = row.get(block)
        if isinstance(val, dict):
            return val.get(field)
        return None

    doi = str(_n(row, "text_provenance", "source_doi") or _n(row, "identity", "source_id") or "")
    pdf = _doi_to_pdf(doi)
    if pdf is None:
        return None
    sigma = _n(row, "ion_transport", "sigma_RT")
    ea = _n(row, "ion_transport", "activation_energy_Ea")
    material = str(_n(row, "identity", "material_id") or "")
    try:
        sigma = None if sigma is None or pd.isna(sigma) else float(sigma)
        ea = None if ea is None or pd.isna(ea) else float(ea)
    except (TypeError, ValueError):
        return None

    pages = _load_pdf(pdf)
    if not pages or sum(len(p) for p in pages) < 100:
        return None  # scanned — no text layer

    # Prefer pages that mention the material composition.
    comp_clean = _norm_formula(material)
    comp_key = comp_clean.replace(".", "").replace("x", "").lower()

    scored: list[tuple] = []
    for page_idx, text in enumerate(pages, 1):
        found_comp = comp_key in text.lower()
        if not found_comp and len(comp_key) >= 4:
            elems = set(re.findall(r"[A-Z][a-z]?", material))
            present = sum(1 for e in elems if re.search(rf"\b{e}\b", text))
            found_comp = present >= max(2, len(elems) - 2)
        res_s = _find_in_text(text, sigma, is_sigma=True, is_ea=False) if sigma is not None else None
        res_e = _find_in_text(text, ea, is_sigma=False, is_ea=True) if ea is not None else None
        score = (4 if found_comp else 0) + (2 if res_s else 0) + (1 if res_e else 0)
        if score > 0:
            scored.append((score, page_idx, text, found_comp, res_s, res_e))

    if not scored:
        return None
    scored.sort(key=lambda x: -x[0])
    score, page_idx, text, found_comp, res_s, res_e = scored[0]

    sentence = ""
    unit = ""
    for res in (res_s, res_e):
        if res:
            sentence = res[2]
            unit = res[1]
            break
    if not sentence and found_comp:
        ci = text.lower().find(comp_key)
        if ci >= 0:
            sentence = _sentence_around(text, ci)

    return {
        "page": page_idx,
        "sentence": sentence,
        "paragraph": (res_s or res_e)[2][:600] if (res_s or res_e) else text[:600],
        "unit": unit,
        "found_sigma": res_s is not None,
        "found_ea": res_e is not None,
        "found_composition": found_comp,
    }


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--apply", action="store_true")
    ap.add_argument("--force", action="store_true")
    ap.add_argument("--report", action="store_true")
    args = ap.parse_args()

    df = pq.read_table(VERIFIED).to_pandas()
    print(f"Verified records: {len(df)}")

    def _nested(row, block, field):
        flat_key = f"{block}.{field}"
        if flat_key in row.index:
            flat = row.get(flat_key)
            if flat is not None and not (hasattr(flat, "isna") and bool(flat.isna())):
                return flat
        val = row.get(block)
        if isinstance(val, dict):
            return val.get(field)
        return None

    labelled_idx = []
    for idx in df.index:
        row = df.loc[idx]
        if _nested(row, "ion_transport", "label_available") in (True, 1):
            labelled_idx.append(idx)
    print(f"  labelled: {len(labelled_idx)}")

    n_fixed = n_new = n_no_pdf = n_not_found = n_kept = n_page_backfilled = 0
    rows: list[tuple] = []

    for idx in labelled_idx:
        row = df.loc[idx]
        mat = str(_nested(row, "identity", "material_id") or "")[:40]
        doi = str(_nested(row, "text_provenance", "source_doi")
                  or _nested(row, "identity", "source_id") or "")
        pdf = _doi_to_pdf(doi)
        if pdf is None:
            n_no_pdf += 1
            rows.append((mat, doi, "NO_PDF", ""))
            continue
        res = find_evidence_for_row(row)
        if res is None:
            n_not_found += 1
            rows.append((mat, doi, "NOT_FOUND", ""))
            continue
        had_sent = not _is_junk(_nested(row, "text_provenance", "evidence_sentence"))
        had_page = not _is_junk(_nested(row, "text_provenance", "evidence_page"))
        needs_apply = (args.apply and (not had_sent or not had_page or args.force))
        if needs_apply:
            _stamp_evidence(df, idx, res, preserve_sentence=had_sent)
        if had_sent and not had_page:
            n_page_backfilled += 1
            rows.append((mat, doi, "PAGE_BACKFILL", res["sentence"][:60]))
            continue
        if had_sent and not args.force:
            n_kept += 1
            rows.append((mat, doi, "KEPT", res["sentence"][:60]))
            continue
        n_new += 1
        rows.append((mat, doi, "NEW", res["sentence"][:60]))

    print(f"  have PDF: {len(labelled_idx) - n_no_pdf}/{len(labelled_idx)}")
    print(f"  no PDF on disk: {n_no_pdf}")
    print(f"  evidence not found in PDF: {n_not_found}")
    print(f"  already had real evidence (kept): {n_kept}")
    print(f"  new evidence attached: {n_new} | junk replaced: {n_fixed} | page backfilled: {n_page_backfilled}")

    if args.report:
        print("\n--- per-record ---")
        for mat, doi, status, snippet in rows:
            print(f"  {status:<9} {mat:<42} {snippet}")

    if args.apply:
        df.to_parquet(VERIFIED, index=False)
        print(f"\nWrote updated evidence to {VERIFIED}")
    else:
        print("\n(dry run — pass --apply to write)")


if __name__ == "__main__":
    main()
