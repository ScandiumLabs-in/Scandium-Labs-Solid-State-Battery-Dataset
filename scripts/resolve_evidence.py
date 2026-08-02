#!/usr/bin/env python3
"""Re-resolve evidence context (sentence/page/section/table) for review items.

Many queue items lost their provenance during extraction because the LLM's
source/notes text was empty. This script works offline, using the persisted
per-paper artifacts (full_text.txt, sections.json, tables.json) and the source
PDFs, to re-attach:

  evidence_sentence - the sentence containing the extracted value + material
  page              - PDF page number (via pdfplumber page-level search)
  section           - section name (via paragraph ranges in sections.json)
  table_number      - table that contains the value (via tables.json captions)

Usage:
  python scripts/resolve_evidence.py [--force] [--pdf-dir literature_output/pdfs]

It updates review_output/queue.json in place. Items that already have a
resolved sentence are skipped unless --force is given.
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path

REVIEW_DIR = Path("review_output")
QUEUE_PATH = REVIEW_DIR / "queue.json"
SCANDIUM_DIR = Path("scandium_output")
DEFAULT_PDF_DIR = Path("literature_output/pdfs")

NON_CONTENT_SECTIONS = {
    "references", "bibliography", "acknowledgements", "acknowledgments",
    "supplementary", "appendix", "supporting information",
}

# Units to normalize in the raw text so value-string matching is robust.
UNIT_ALIASES = [
    (r"s\s*/\s*cm", "S/cm"),
    (r"mS\s*/\s*cm", "mS/cm"),
    (r"μS\s*/\s*cm", "uS/cm"),
    (r"eV", "eV"),
]


def _load_paper_artifacts(paper_id: str) -> tuple[str, list[dict], list[dict]]:
    """Return (full_text, sections, tables) for a paper, or empty if absent."""
    pdir = SCANDIUM_DIR / paper_id
    full_text = ""
    ft_path = pdir / "full_text.txt"
    if ft_path.exists():
        full_text = ft_path.read_text()

    sections: list[dict] = []
    sec_path = pdir / "sections.json"
    if sec_path.exists():
        try:
            sections = json.loads(sec_path.read_text())
        except Exception:
            sections = []

    tables: list[dict] = []
    tabs_path = pdir / "tables.json"
    if tabs_path.exists():
        try:
            tables = json.loads(tabs_path.read_text())
        except Exception:
            tables = []

    return full_text, sections, tables


def _normalize(text: str) -> str:
    """Lowercase and collapse whitespace for matching."""
    return re.sub(r"\s+", " ", text.lower()).strip()


def _normalize_map(text: str) -> tuple[str, list[int]]:
    """Normalize text for matching, returning (normalized, index_map).

    index_map[i] = original character offset of normalized[i]. Unicode minus,
    multiplication signs, and whitespace runs are collapsed to ASCII tokens so
    value matching is robust across PDF renderings.
    """
    out_chars: list[str] = []
    out_offsets: list[int] = []
    i = 0
    n = len(text)
    while i < n:
        c = text[i]
        if c in "\u2212\u2010\u2011\u2012\u2013\u2014":  # minus-like dashes
            out_chars.append("-")
            out_offsets.append(i)
            i += 1
        elif c in "\u00d7\u00b7\u22c5\uf0d7":  # × · ⋅
            out_chars.append("x")
            out_offsets.append(i)
            i += 1
        elif c in " \t\r\n\f":
            # collapse whitespace runs to a single space
            if out_chars and out_chars[-1] != " ":
                out_chars.append(" ")
                out_offsets.append(i)
            while i < n and text[i] in " \t\r\n\f":
                i += 1
        else:
            out_chars.append(c)
            out_offsets.append(i)
            i += 1
    return "".join(out_chars), out_offsets


def _value_patterns(value: float) -> list[str]:
    """Generate normalized textual representations of a value for matching."""
    patterns: set[str] = set()
    # plain significant-digit forms
    for prec in (6, 5, 4, 3, 2):
        patterns.add(f"{value:.{prec}g}")

    # scientific notation variants (operators normalized to 'x' / 'e')
    try:
        mant, exp_s = f"{value:e}".split("e")
        exp = int(exp_s)
    except (ValueError, IndexError):
        mant, exp = "0", 0

    # generate all mantissa precision forms: 3, 3.0, 3.00, 3.000, ...
    mantissas: set[str] = set()
    mantissas.add(mant.rstrip("0").rstrip("."))
    mantissas.add(mant)
    frac = mant.split(".")[1] if "." in mant else ""
    for keep in range(1, len(frac) + 1):
        mantissas.add(f"{mant.split('.')[0]}.{frac[:keep]}")

    for m in sorted(mantissas):
        for e in {str(exp), str(abs(exp))}:
            sign = "-" if exp < 0 else ""
            patterns.add(f"{m}e{exp}")
            patterns.add(f"{m}E{exp}")
            patterns.add(f"{m}e{sign}{e}")
            patterns.add(f"{m}E{sign}{e}")
            patterns.add(f"{m}x10{sign}{e}")
            patterns.add(f"{m}*10{sign}{e}")
            patterns.add(f"{m} 10{sign}{e}")
            patterns.add(f"{m}x10^({sign}{e})")
            patterns.add(f"{m}x10^({e})")
            # allow the mantissa to carry the exponent shift (e.g. 3.0 -> 3e0)
            patterns.add(f"{m}x10{e}")

    # plain decimal expansion (e.g. 6.48e-05 -> 0.0000648)
    if value != 0 and abs(value) < 1e-2:
        try:
            patterns.add(f"{value:.10f}".rstrip("0").rstrip("."))
        except Exception:
            pass

    patterns.discard("")
    return sorted(patterns)


def _value_regex(value: float):
    """Compile a regex matching any normalized rendering of value.

    The normalized text keeps single spaces (e.g. '3.0 x 10-6'), so we build the
    pattern component-wise with flexible whitespace between parts.
    """
    if value == 0:
        return re.compile(r"\b0\b")

    # plain decimal + simple scientific forms (no spaces)
    simple = "|".join(
        re.escape(p) for p in _value_patterns(value)
    )

    # structural forms:  MANT [x|e|*] 10 [-] EXP   and   MANT e [-] EXP
    try:
        mant, exp_s = f"{value:e}".split("e")
        exp = int(exp_s)
    except (ValueError, IndexError):
        return re.compile(simple)

    frac = mant.split(".")[1] if "." in mant else ""
    mantissas = {mant.rstrip("0").rstrip("."), mant}
    for keep in range(1, len(frac) + 1):
        mantissas.add(f"{mant.split('.')[0]}.{frac[:keep]}")
    mant_esc = [re.escape(m) for m in sorted(mantissas)]

    sign = "-" if exp < 0 else ""
    exp_esc = re.escape(str(abs(exp)))

    ws = r"\s*"
    structural = []
    for me in mant_esc:
        # MANT x 10 [-] EXP   (x, * or omitted operator)
        structural.append(
            rf"{me}{ws}(?:x|\\*)?{ws}10{ws}-?{ws}{exp_esc}"
        )
        # MANT e [-] EXP
        structural.append(rf"{me}{ws}[eE]{ws}-?{ws}{exp_esc}")
    all_parts = [simple] + structural
    return re.compile("|".join(f"(?:{p})" for p in all_parts))


def _find_value_matches(value: float, text: str) -> list[int]:
    """Find character offsets where the value appears in text (as word)."""
    norm_text, offsets = _normalize_map(text)
    rx = _value_regex(value)
    candidates = []
    for m in rx.finditer(norm_text):
        start = m.start()
        before = norm_text[start - 1] if start > 0 else " "
        after = norm_text[m.end()] if m.end() < len(norm_text) else " "
        if not (before.isdigit() or before.isalpha() or after.isdigit() or after.isalpha()):
            candidates.append(offsets[start])
    return sorted(set(candidates))


def _sentence_window(text: str, offset: int, radius: int = 200) -> str:
    """Return a readable sentence window around an offset in the text."""
    start = max(0, offset - radius)
    end = min(len(text), offset + radius)
    window = re.sub(r"\s+", " ", text[start:end]).strip()
    # try to expand to sentence boundaries
    for sep in [". ", ".\n", ";\n"]:
        idx = window.find(sep, radius // 2)
        if idx > 0:
            window = window[: idx + 1]
            break
    return window


def _load_page_texts(pdf_path: Path, per_pdf_timeout: int = 30) -> list[str]:
    """Extract text for every page of a PDF once ([] if not available).

    Some PDFs make pdfplumber hang on a specific page, so we guard the whole
    extraction with a SIGALRM-based timeout and return what we have.
    """
    if not pdf_path.exists():
        return []
    try:
        import pdfplumber
    except ImportError:
        return []

    import signal

    texts: list[str] = []

    def _handler(signum, frame):
        raise TimeoutError(f"pdfplumber exceeded {per_pdf_timeout}s: {pdf_path.name}")

    old_handler = signal.getsignal(signal.SIGALRM)
    try:
        signal.signal(signal.SIGALRM, _handler)
        signal.alarm(per_pdf_timeout)
        try:
            with pdfplumber.open(pdf_path) as pdf:
                for page in pdf.pages:
                    texts.append(page.extract_text() or "")
        except TimeoutError:
            return texts
        finally:
            signal.alarm(0)
    except Exception:
        return texts
    finally:
        signal.signal(signal.SIGALRM, old_handler)
    return texts


def _find_page(page_texts: list[str], value: float, material: str) -> int | None:
    """Find the page containing the value (page-level search over cached texts)."""
    rx = _value_regex(value)
    for i, txt in enumerate(page_texts):
        if not txt:
            continue
        if rx.search(txt):
            return i + 1
    return None


def _find_table_number(value: float, material: str, tables: list[dict]) -> int | None:
    """Find which table caption contains both the material and (roughly) value."""
    rx = _value_regex(value)
    for table in tables:
        caption = _normalize(table.get("caption", ""))
        if not caption:
            continue
        if material and material.lower().replace(" ", "") not in caption.replace(" ", ""):
            continue
        if rx.search(caption):
            m = re.search(r"table\s*(\d+)", caption)
            if m:
                return int(m.group(1))
    return None


def _find_section(full_text: str, sections: list[dict], offset: int) -> str:
    """Map a character offset in full_text to a section name.

    sections.json stores start_para/end_para, so we approximate by finding the
    section whose start_para region precedes the offset. Simpler: locate which
    section's text most likely contains this region by scanning section texts.
    """
    # Cheap approach: check if any section text contains the value region by
    # matching the offset's local text. Fall back to nearest section start.
    # Since full_text is the concatenation of paragraphs, use the section whose
    # text is closest to the offset via sliding match: find all section start
    # offsets in full_text by matching the first 40 chars of each section.
    best_section = None
    best_offset = -1
    for sec in sections:
        name = sec.get("name", "")
        if not name or name.lower().strip() in NON_CONTENT_SECTIONS:
            continue
        sec_text = sec.get("text", "")
        if not sec_text:
            continue
        probe = _normalize(sec_text[:60])
        if not probe:
            continue
        idx = _normalize(full_text).find(probe)
        if idx >= 0 and (best_offset < 0 or idx <= offset):
            best_offset = idx
            best_section = name
    return best_section or "Unknown"


def _resolve_item_text(
    item: dict,
    full_text: str,
    sections: list[dict],
    tables: list[dict],
    page_texts: list[str],
) -> None:
    """Resolve sentence/page/section/table for a single item (in-place)."""
    value = item.get("value")
    if value is None:
        return
    try:
        value_f = float(value)
    except (TypeError, ValueError):
        return
    material = item.get("composition") or ""

    # 1. Find value in full_text; if absent, search across section texts.
    offsets = _find_value_matches(value_f, full_text) if full_text else []
    search_text = full_text
    if not offsets and sections:
        for sec in sections:
            if sec.get("text"):
                offsets.extend(_find_value_matches(value_f, sec["text"]))
        search_text = "\n".join(s.get("text", "") for s in sections if s.get("text"))

    # 2. Fall back to table captions (which may hold tabular data as text).
    if not offsets and tables:
        table_text = "\n".join(t.get("caption", "") for t in tables)
        if table_text:
            offsets = _find_value_matches(value_f, table_text)
            search_text = table_text

    if not offsets:
        return

    # Prefer an offset near the material mention.
    best_offset = offsets[0]
    if material:
        mat_norm = material.lower().replace(" ", "")
        mat_idx = _normalize(search_text).find(mat_norm)
        if mat_idx >= 0:
            best_offset = min(offsets, key=lambda o: abs(o - mat_idx))

    item["evidence_sentence"] = _sentence_window(search_text, best_offset)

    if item.get("page") is None:
        item["page"] = _find_page(page_texts, value_f, material)

    if item.get("section") in (None, "", "Unknown"):
        item["section"] = _find_section(search_text, sections, best_offset)

    if item.get("table_number") is None and tables:
        item["table_number"] = _find_table_number(value_f, material, tables)


def resolve_item(item: dict, pdf_dir: Path) -> dict:
    """Resolve provenance for a single queue item (in-place, returns it)."""
    paper_id = item.get("paper_id", "")
    if not paper_id:
        return item

    full_text, sections, tables = _load_paper_artifacts(paper_id)
    if not full_text and not sections:
        return item

    page_texts = _load_page_texts(pdf_dir / f"{paper_id}.pdf")
    _resolve_item_text(item, full_text, sections, tables, page_texts)
    return item


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--force", action="store_true", help="re-resolve even if sentence exists")
    parser.add_argument("--pdf-dir", type=Path, default=DEFAULT_PDF_DIR)
    args = parser.parse_args()

    if not QUEUE_PATH.exists():
        print("Queue not found. Run `python scripts/review.py build` first.")
        sys.exit(1)

    queue = json.loads(QUEUE_PATH.read_text())
    items = queue.get("items", [])
    resolved = 0
    missing_sentence_before = sum(
        1 for i in items if not i.get("evidence_sentence")
    )

    # Batch by paper: load artifacts + PDF page texts once per paper.
    from collections import defaultdict

    by_paper: dict[str, list[dict]] = defaultdict(list)
    for item in items:
        already = item.get("evidence_sentence") and not args.force
        if already:
            continue
        by_paper[item.get("paper_id", "")].append(item)

    for paper_id, paper_items in by_paper.items():
        if not paper_id:
            continue
        full_text, sections, tables = _load_paper_artifacts(paper_id)
        if not full_text and not sections:
            continue
        page_texts = _load_page_texts(args.pdf_dir / f"{paper_id}.pdf")
        for item in paper_items:
            before = (item.get("evidence_sentence"), item.get("page"),
                      item.get("section"), item.get("table_number"))
            _resolve_item_text(item, full_text, sections, tables, page_texts)
            after = (item.get("evidence_sentence"), item.get("page"),
                     item.get("section"), item.get("table_number"))
            if after != before:
                resolved += 1

    QUEUE_PATH.write_text(json.dumps(queue, indent=2))

    missing_sentence_after = sum(
        1 for i in items if not i.get("evidence_sentence")
    )
    print(f"Resolved/updated: {resolved} items")
    print(f"Missing evidence sentence: {missing_sentence_before} -> {missing_sentence_after}")
    print(f"Queue saved to {QUEUE_PATH}")


if __name__ == "__main__":
    main()
