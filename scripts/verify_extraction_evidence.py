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


def _has_unit_context(text: str, start: int, end: int, label: str) -> bool:
    """Require a unit / quantity token within a small window of the matched
    number, so coincidental figures (cycle rates, x-fractions, impedance in Ω,
    temperatures) are not mistaken for the reported conductivity or activation
    energy.

    The nanolett Ea leak: the paper reports Ea only in figure panels, while the
    text carries "0.2C" cycle rates and "x = 0.2" substitution fractions. The
    old matcher anchored the Ea claim on those numbers. Unit context rejects
    them and routes the record to a human instead of auto-approving it."""
    if label == "sigma":
        pats = (
            r"s/cm", r"s[∙· ]*cm", r"cm\s*-\s*1", r"cm\u22121", r"cm\u207b", r"cm⁻¹",
            r"m\s*s/cm", r"mS", r"µ\s*s", r"u\s*s/cm", r"n\s*s/cm", r"\u00b5s",
            r"Ω", r"ohm", r"s/m", r"conductiv", r"σ", r"\bs/cm\b",
        )
    else:  # Ea
        # NOTE: `mev` is deliberately NOT a valid Ea unit context. A value like
        # "0.1 meV" (e.g. a neutron-spectrometer energy resolution) is 1e-4 eV,
        # not 0.1 eV — numerically equal literals are coincidence, and a real
        # meV-scale Ea (e.g. 430 meV = 0.43 eV) never matches an eV-scaled
        # target anyway. `(?<![a-z])ev\b` rejects the "eV" inside "meV" (a
        # preceding letter) while still matching standalone "eV"/"0.43eV".
        pats = (
            r"(?<![a-z])ev\b", r"kj/mol", r"kcal", r"activation", r"barrier", r"\bea\b",
        )
    window = text[max(0, start - 20):min(len(text), end + 20)]
    return any(re.search(p, window, re.IGNORECASE) for p in pats)


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
        # Relative tolerance with a small absolute floor. The old 5e-5 floor
        # let bare axis ticks ("0", "0.000") match tiny sigma targets
        # (e.g. 2.55e-6), stamping a false `sigma=0.000e+00` digit-match that
        # a 1000x unit-error record sailed through on. A found value of 0 is
        # never a real conductivity or activation energy, so it is rejected
        # outright here.
        tol = max(abs(target) * 0.35, 1e-7)
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
            if val is not None and val != 0.0 and abs(val - target) <= tol:
                if not _has_unit_context(text, m.start(), m.end(), label):
                    continue  # coincidental number, not a real Ea/sigma value
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


def _parse_matched(m: re.Match) -> float | None:
    """Parse a number from the shared scientific-notation regex. Mirrors the
    value-extraction logic in `find_nearby_value`."""
    if m.group(1) and m.group(2):
        exp_str = m.group(2).replace(" ", "").replace("\u2212", "-")
        exp_str = "".join(ch for ch in exp_str if ch.isdigit() or ch == "-")
        try:
            exp = int(exp_str)
        except ValueError:
            exp = 0
        if -32 <= exp <= 32:
            return float(m.group(1)) * 10 ** exp
    elif m.group(3) and m.group(4):
        try:
            exp = int(m.group(4))
        except ValueError:
            exp = 0
        if -32 <= exp <= 32:
            return float(m.group(3)) * 10 ** exp
    elif m.group(5):
        return float(m.group(5))
    return None


def _verify_scanned_with_vision(pdf_path: Path, pdf_name: str,
                                composition: str, sigma: float | None,
                                ea: float | None) -> dict:
    """Phase E5 — OCR fallback for scanned PDFs (empty text layer).

    Renders each page, transcribes it via the configured vision provider
    (tesseract / ollama / groq), and runs the same matcher the text path uses.
    The verdict is evidence-backed (FOUND / PARTIAL / NOT_FOUND) instead of an
    unconditional SCRIBED stamp, so scanned records can leave needs_review limbo.
    """
    result = {
        "pdf": pdf_name,
        "composition": composition,
        "sigma_RT": sigma,
        "Ea": ea,
        "verdict": "SCRIBED",
        "digit_match": False,
        "pages": [],
        "evidence": [],
        "vision": True,
    }
    try:
        from ssb_dataset.pipeline.verifier import vision_locate_evidence
        ev = vision_locate_evidence(pdf_path, composition, sigma, ea)
    except Exception:
        ev = None
    if ev is None:
        result["note"] = "vision provider not configured or no evidence found"
        return result

    # OCR noise guard: the vision matcher matches numbers by value tolerance
    # alone; the text path additionally requires a conductivity/Ea unit in
    # context. Apply the same guard to the OCR window so a coincidental number
    # (e.g. "0.12 times the cross-sectional area" matching a uS/cm variant)
    # does not stamp a false sigma FOUND.
    sigma_ok = bool(ev.found_sigma and ev.sigma_in_window)
    if sigma_ok and sigma is not None:
        w = ev.sigma_in_window
        # find the matched number position inside the window and require unit ctx
        def _within_target(m: re.Match) -> bool:
            v = _parse_matched(m)
            return v is not None and abs(v - sigma) <= max(abs(sigma) * 0.35, 1e-7)
        sigma_ok = any(
            _has_unit_context(w, m.start(), m.end(), "sigma")
            for m in re.finditer(
                r"(\d+\.?\d*)\s*[x×]\s*10\s*([-\u2212]?\s*\d+)|"
                r"(\d+\.?\d*)[eE]([-\u2212]?\d+)|"
                r"(\d+\.?\d*)", w)
            if _within_target(m)
        )
    ea_ok = bool(ev.found_ea and ev.ea_in_window)

    result["pages"] = [ev.page]
    result["evidence"] = [{
        "page": ev.page,
        "found_composition": ev.found_composition,
        "values_found": (
            ["sigma" if sigma_ok else None,
             "Ea" if ea_ok else None]
            or []
        ),
        "digit_match": sigma_ok,
        "snippet": ev.window,
        "source": "vision",
    }]
    if sigma_ok:
        result["digit_match"] = True

    if sigma_ok and ev.found_composition:
        result["verdict"] = "FOUND"
    elif ev.found_composition or ea_ok or sigma_ok:
        result["verdict"] = "PARTIAL"
    else:
        result["verdict"] = "NOT_FOUND"
    return result


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
        # no text layer (scanned) — Phase E5: try the vision OCR path before
        # stamping an unconditional SCRIBED verdict.
        return _verify_scanned_with_vision(pdf_path, pdf_name, composition, sigma, ea)

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
