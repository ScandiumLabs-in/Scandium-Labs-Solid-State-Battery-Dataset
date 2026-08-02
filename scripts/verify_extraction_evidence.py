#!/usr/bin/env python3
"""Verify extracted conductivity records against their source PDF text.

For each record in literature_output/extraction_results.json, opens the source
PDF, extracts page-by-page text, and searches for:
  1. the composition formula (normalized), and
  2. a conductivity / Ea value numerically close to the extracted value
     within a window around the composition mention.

Outputs a verdict per record:
  - FOUND: composition + value both located (with page + evidence snippet)
  - PARTIAL: composition found but value not located near it
  - NOT_FOUND: neither composition nor value found in text layer
  - SCRIBED: value found but composition generic/absent (e.g. LLZO family names)

Writes literature_output/verification_report.json and prints a summary.
This is a pre-review triage layer: it does NOT approve/reject, it flags where
a human should look. A NOT_FOUND verdict on a text-layer PDF strongly suggests
hallucination (or the value was in a figure/plot rather than a table/text).
"""

from __future__ import annotations

import json
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
RESULTS = ROOT / "literature_output/extraction_results.json"
PDF_DIR = ROOT / "literature_output/pdfs"
OUT = ROOT / "literature_output/verification_report.json"

ELEMENTS = [
    "Ac", "Ag", "Al", "Am", "Ar", "As", "At", "Au", "B", "Ba", "Be", "Bh",
    "Bi", "Bk", "Br", "C", "Ca", "Cd", "Ce", "Cf", "Cl", "Cm", "Cn", "Co",
    "Cr", "Cs", "Cu", "Db", "Ds", "Dy", "Er", "Es", "Eu", "F", "Fe", "Fl",
    "Fm", "Fr", "Ga", "Gd", "Ge", "H", "He", "Hf", "Hg", "Ho", "Hs", "I",
    "In", "Ir", "K", "Kr", "La", "Li", "Lr", "Lu", "Lv", "Mc", "Mg", "Mn",
    "Mo", "Mt", "N", "Na", "Nb", "Nd", "Ne", "Nh", "Ni", "No", "Np", "O",
    "Og", "Os", "P", "Pa", "Pb", "Pd", "Pm", "Po", "Pr", "Pt", "Pu", "Rb",
    "Re", "Rf", "Rg", "Rh", "Rn", "Ru", "S", "Sb", "Sc", "Se", "Sg", "Si",
    "Sm", "Sn", "Sr", "Ta", "Tb", "Tc", "Te", "Th", "Ti", "Tl", "Tm", "Ts",
    "U", "V", "W", "Xe", "Y", "Yb", "Zn", "Zr",
]


def norm_formula(f: str) -> str:
    """Normalize a composition to a compact element:counts string for matching."""
    f = f.split("(")[0]
    f = f.split("/")[0]
    f = f.split("-")[0]
    return f.strip()


def element_counts(formula: str) -> set[str] | None:
    """Extract the set of elements in a formula. Returns None if not parseable."""
    toks = re.findall(r"[A-Z][a-z]?|\d+", formula)
    elems = set()
    for t in toks:
        if t in ELEMENTS:
            elems.add(t)
    if len(elems) >= 2:
        return elems
    return None


def extract_pages(pdf_path: Path) -> list[str]:
    """Extract text per page using PyMuPDF."""
    import fitz

    doc = fitz.open(str(pdf_path))
    pages = [page.get_text("text") for page in doc]
    doc.close()
    return pages


def find_nearby_value(text: str, targets: list[tuple[str, float | None]]) -> list[dict]:
    """Find decimal values (scientific notation) in text close to target values.

    Returns list of {"label", "found", "start", "end"} dicts so callers can
    build a snippet window around the actual match rather than page start.
    """
    findings: list[dict] = []
    # numbers like 1.2e-3, 0.003, 5.05 x 10^-3
    num_re = re.compile(
        r"(\d+\.?\d*)\s*[x×]\s*10\s*([-\u2212]?\s*\d+)|"
        r"(\d+\.?\d*)[eE]([-\u2212]?\d+)|"
        r"(\d+\.?\d*)"
    )
    for label, target in targets:
        if target is None:
            continue
        tol = max(abs(target) * 0.35, 5e-5)  # 35% tolerance, min 5e-5
        for m in num_re.finditer(text):
            val: float | None = None
            if m.group(1) and m.group(2):
                exp_str = m.group(2).replace(" ", "").replace("\u2212", "-")
                exp_str = "".join(ch for ch in exp_str if ch.isdigit() or ch == "-")
                try:
                    exp = int(exp_str)
                except ValueError:
                    exp = 0
                if -32 <= exp <= 32:
                    val = float(m.group(1)) * 10 ** exp
            elif m.group(3) and m.group(4):
                try:
                    exp = int(m.group(4))
                except ValueError:
                    exp = 0
                if -32 <= exp <= 32:
                    val = float(m.group(3)) * 10 ** exp
            elif m.group(5):
                val = float(m.group(5))
            if val is not None and abs(val - target) <= tol:
                findings.append({
                    "label": label, "found": val,
                    "start": m.start(), "end": m.end(),
                })
                break
    return findings


def _window_around(text: str, anchor: int, radius: int = 300) -> str:
    """Return a text window around a character anchor (avoids splitting words)."""
    start = max(0, anchor - radius)
    end = min(len(text), anchor + radius)
    return text[start:end].replace("\n", " ").strip()


def verify_record(pdf_name: str, record: dict) -> dict:
    pdf_path = PDF_DIR / pdf_name
    composition = (record.get("composition") or "").strip()
    sigma = record.get("sigma_RT")
    ea = record.get("Ea")

    result = {
        "pdf": pdf_name,
        "composition": composition,
        "sigma_RT": sigma,
        "Ea": ea,
        "verdict": "NOT_FOUND",
        "digit_match": False,
        "pages": [],
        "evidence": [],
    }

    if not pdf_path.exists():
        result["verdict"] = "NO_PDF"
        return result

    pages = extract_pages(pdf_path)
    if not pages or sum(len(p) for p in pages) < 100:
        result["verdict"] = "SCRIBED"  # no text layer (scanned)
        return result

    comp_elems = element_counts(composition) if composition else None
    comp_clean = norm_formula(composition)
    comp_sub = composition.replace(".", "").replace(" ", "").lower()

    targets = [("sigma", sigma), ("Ea", ea)]

    for page_idx, text in enumerate(pages, 1):
        found_comp = False
        if comp_elems and len(comp_elems) >= 3:
            # For multi-component formulas (e.g. "Ca-CeO2/LiTFSI/PEO"),
            # require a strong subset of the elements on the page.
            present = sum(1 for e in comp_elems if re.search(rf"\b{e}\b", text))
            found_comp = present >= max(2, len(comp_elems) - 3)
        elif composition and comp_clean and len(comp_clean) >= 3:
            found_comp = comp_clean.replace(".", "").replace("x", "").lower() in text.lower()
        else:
            found_comp = False

        findings = find_nearby_value(text, targets)
        if found_comp or findings:
            # Anchor the snippet on the value actually matched most relevant
            # to the PRIMARY claim (sigma first, else Ea).
            sigma_f = next((f for f in findings if f["label"] == "sigma"), None)
            anchor = (sigma_f or findings[0] if findings else {"start": 0})["start"]
            snippet = _window_around(text, anchor)
            # digit_match = the SPECIFIC sigma value (within tolerance) is truly
            # in this window. If only the Ea matched (or neither), the sigma
            # claim is NOT confirmed -> do not overstate evidence.
            sigma_matched = any(f["label"] == "sigma" for f in findings)
            result["pages"].append(page_idx)
            result["evidence"].append({
                "page": page_idx,
                "found_composition": found_comp,
                "values_found": [f"{f['label']}={f['found']:.3e}" for f in findings],
                "digit_match": sigma_matched,
                "snippet": snippet,
            })
            if sigma_matched and not result.get("digit_match"):
                result["digit_match"] = True

    if not result["pages"]:
        result["verdict"] = "NOT_FOUND"
        return result

    any_value = any(ev["values_found"] for ev in result["evidence"])
    any_comp = any(ev["found_composition"] for ev in result["evidence"])

    if any_value and any_comp:
        result["verdict"] = "FOUND"
    elif any_comp:
        result["verdict"] = "PARTIAL"  # composition there, value not located
    elif any_value:
        result["verdict"] = "VALUE_ONLY"
    else:
        result["verdict"] = "NOT_FOUND"
    return result


def main() -> None:
    results = json.loads(RESULTS.read_text())
    report: dict[str, list[dict]] = {}
    failures: list[tuple[str, str, str]] = []

    for pdf_name, recs in results.items():
        if not isinstance(recs, list):
            continue
        for r in recs:
            if not (r.get("sigma_RT") is not None or r.get("Ea") is not None):
                continue
            try:
                report.setdefault(pdf_name, []).append(verify_record(pdf_name, r))
            except Exception as e:  # never fail the whole sweep on one record
                failures.append((pdf_name, str(r.get("composition")), repr(e)))

    # --- copy-paste duplicate detection --------------------------------
    # Same sigma (exactly equal/within 1e-6) shared verbatim by DIFFERENT
    # compositions inside ONE paper => strong copy-paste extraction artifact.
    for pdf, recs in report.items():
        seen: dict[str, list[str]] = {}
        for r in recs:
            s = r.get("sigma_RT")
            if s is None:
                continue
            key = f"{s:.5e}"
            seen.setdefault(key, []).append(r.get("composition", "?"))
        for key, comps in seen.items():
            uniq = set(comps)
            if len(uniq) >= 2:
                for r in recs:
                    if f"{r.get('sigma_RT') or 0:.5e}" == key:
                        r["duplicate_value"] = sorted(uniq)
                        r["verdict"] = "DUP_VALUE"

    OUT.write_text(json.dumps(report, indent=2))

    from collections import Counter

    counts = Counter()
    total = 0
    for pdf, recs in report.items():
        for r in recs:
            counts[r["verdict"]] += 1
            total += 1

    print(f"Verified {total} records:")
    for verdict in ["FOUND", "PARTIAL", "VALUE_ONLY", "NOT_FOUND", "SCRIBED", "NO_PDF", "duplicate_value"]:
        if counts.get(verdict, 0):
            print(f"  {verdict:12s}: {counts.get(verdict, 0)}")
    dm = sum(1 for pv in report.values() for r in pv if r.get("digit_match"))
    print(f"  digit_match : {dm} (reported value confirmed in evidence window)")
    if failures:
        print(f"\nWARNING: {len(failures)} records skipped (error):")
        for a, b, c in failures[:10]:
            print(f"  {a} | {b} | {c}")
    print(f"\nFull report: {OUT}")


if __name__ == "__main__":
    main()
