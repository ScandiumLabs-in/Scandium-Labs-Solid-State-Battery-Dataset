#!/usr/bin/env python3
"""Verification assistant: check every review item against the source PDF text.

For each pending review item, this script extracts the evidence needed for a
human to make a <10s decision:

  * whether the value string appears in the paper text at all
  * the unit token (S/cm vs mS/cm etc.) in the surrounding context
  * whether the value sits inside a table caption whose unit is known
  * family-range consistency
  * a suggested verdict (approve / unit-fix / reject / verify-manually)

Usage:
  python scripts/verify_evidence.py [--paper PAPER_ID] [--min-conf 0.5]
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
from resolve_evidence import (
    _load_page_texts,
    _normalize_map,
    _value_regex,
    SCANDIUM_DIR,
    DEFAULT_PDF_DIR,
)

QUEUE_PATH = Path("review_output/queue.json")

# Families we know and their plausible RT conductivity ranges (S/cm).
FAMILY_SIGMA_RANGE = {
    "sulfide": (1e-5, 1e-1),
    "argyrodite": (1e-5, 1e-1),
    "garnet": (1e-6, 1e-2),
    "nasicon": (1e-6, 1e-2),
    "perovskite": (1e-8, 1e-3),
    "antiperovskite": (1e-8, 1e-4),
    "polymer_composite": (1e-8, 1e-3),
}
FAMILY_EA_RANGE = {
    "sulfide": (0.1, 0.4),
    "argyrodite": (0.1, 0.4),
    "garnet": (0.2, 0.6),
    "nasicon": (0.2, 0.5),
    "perovskite": (0.2, 0.6),
    "antiperovskite": (0.2, 0.6),
    "polymer_composite": (0.3, 1.0),
}

# Known table units by paper (from caption inspection). A value whose unit is
# stored as S/cm but appears inside a table labelled mS/cm is a 1000x error.
TABLE_UNITS: dict[str, str] = {
    "sulfide_preprint": "mS/cm",   # Table 1 caption: "Conductivity (mS/cm)"
}


def _fmt(v, u=""):
    if v is None:
        return "—"
    if isinstance(v, float):
        if abs(v) >= 1e4 or (abs(v) < 1e-3 and v != 0):
            return f"{v:.2e}"
        return f"{v:.4g}"
    return str(v)


def _contexts_around(txt: str, value: float, radius: int = 90) -> list[str]:
    """Return text windows around occurrences of value in raw text."""
    norm, off = _normalize_map(txt)
    rx = _value_regex(value)
    seen = set()
    windows = []
    for m in rx.finditer(norm):
        # ensure standalone token
        start = m.start()
        before = norm[start - 1] if start > 0 else " "
        after = norm[m.end()] if m.end() < len(norm) else " "
        if before.isdigit() or before.isalpha() or after.isdigit() or after.isalpha():
            continue
        o = off[start]
        # de-dup overlapping windows
        bucket = o // (radius * 2)
        if bucket in seen:
            continue
        seen.add(bucket)
        windows.append(re.sub(r"\s+", " ", txt[max(0, o - radius): o + radius]).strip())
        if len(windows) >= 3:
            break
    return windows


def _unit_token_in(window: str) -> list[str]:
    """Detect unit tokens present in a text window."""
    toks = []
    for pat, label in [
        (r"mS\s*/\s*cm|mS\s*cm|mS/cm", "mS/cm"),
        (r"(?<![mμu])S\s*/\s*cm|(?<![mμu])S\s*cm|S/cm", "S/cm"),
        (r"μS\s*/\s*cm|µS\s*/\s*cm|uS\s*/\s*cm", "uS/cm"),
        (r"eV", "eV"),
        (r"°\s*C|°\s*Ϲ|oC|\u2103", "°C"),
        (r"MPa", "MPa"),
    ]:
        if re.search(pat, window, re.I):
            toks.append(label)
    return toks


def verify_item(item: dict, page_texts: list[str], full_text: str, tables: list[dict]) -> dict:
    paper = item.get("paper_id", "")
    value = item.get("value")
    prop = item.get("property", "")
    material = item.get("composition") or ""
    family = (item.get("family") or "").lower()

    result = {
        "value": value,
        "property": prop,
        "stored_unit": item.get("unit"),
        "found_in_text": False,
        "n_occurrences": 0,
        "page": item.get("page"),
        "contexts": [],
        "unit_tokens_in_text": [],
        "unit_flag": None,
        "range_hint": None,
        "suggestion": "verify-manually",
        "reasons": [],
    }

    if value is None:
        result["reasons"].append("no value")
        return result

    try:
        value_f = float(value)
    except (TypeError, ValueError):
        result["reasons"].append("non-numeric value")
        return result

    # 1. search full text
    all_text = full_text
    all_windows = _contexts_around(all_text, value_f)
    result["n_occurrences"] = len(all_windows)
    if all_windows:
        result["found_in_text"] = True
        result["contexts"] = all_windows[:3]
        for w in all_windows:
            result["unit_tokens_in_text"].extend(_unit_token_in(w))
        result["unit_tokens_in_text"] = list(dict.fromkeys(result["unit_tokens_in_text"]))

    # 2. page-level: search PDF page texts
    if not result["found_in_text"] and page_texts:
        rx = _value_regex(value_f)
        norm_pages = [_normalize_map(p)[0] for p in page_texts]
        for i, np in enumerate(norm_pages):
            m = rx.search(np)
            if m and not (m.group() and (m.start() > 0 and np[m.start() - 1].isdigit())):
                result["found_in_text"] = True
                result["page"] = i + 1
                break

    # 3. unit sanity: is the value inside a known table with different unit?
    table_unit = TABLE_UNITS.get(paper)
    if table_unit and result["found_in_text"]:
        stored = (item.get("unit") or "").lower().replace(" ", "")
        if stored and "m" not in stored and stored.endswith("s/cm"):
            result["unit_flag"] = (
                f"stored as S/cm but paper table is {table_unit} "
                f"(likely {table_unit}; divide by 1000 → {_fmt(value_f / 1000, 'S/cm')})"
            )

    # 4. family range consistency
    rng = FAMILY_SIGMA_RANGE if prop == "conductivity" else FAMILY_EA_RANGE
    lo, hi = rng.get(family, (None, None))
    if lo and hi:
        if value_f < lo or value_f > hi:
            result["range_hint"] = f"outside {family} range [{_fmt(lo)}–{_fmt(hi)}]"

    # 5. suggestion
    reasons = result["reasons"]
    if not result["found_in_text"]:
        if item.get("confidence", 0) >= 0.85:
            reasons.append("value NOT found in paper text at high confidence → likely hallucination")
            result["suggestion"] = "reject"
        else:
            reasons.append("value not found in text (low conf) — manual check")
            result["suggestion"] = "reject"
    elif result["unit_flag"]:
        reasons.append(f"unit mismatch: {result['unit_flag']}")
        result["suggestion"] = "unit-fix"
    elif result["range_hint"]:
        reasons.append(result["range_hint"])
        if result["range_hint"].startswith("outside"):
            result["suggestion"] = "verify-manually"
    else:
        reasons.append("value found in paper text with plausible units")
        result["suggestion"] = "approve"

    return result


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--paper", default=None, help="only this paper_id")
    parser.add_argument("--min-conf", type=float, default=0.0)
    args = parser.parse_args()

    queue = json.loads(QUEUE_PATH.read_text())
    items = queue["items"]

    # group by paper, load artifacts once
    from collections import defaultdict
    by_paper: dict[str, list[dict]] = defaultdict(list)
    for item in items:
        if args.paper and item.get("paper_id") != args.paper:
            continue
        if item.get("confidence", 0) < args.min_conf:
            continue
        by_paper[item.get("paper_id", "")].append(item)

    summary_counts = {
        "approve": 0, "unit-fix": 0, "reject": 0, "verify-manually": 0,
    }

    for paper in sorted(by_paper):
        full_text = ""
        ft_path = SCANDIUM_DIR / paper / "full_text.txt"
        if ft_path.exists():
            full_text = ft_path.read_text()
        tables = []
        tabs_path = SCANDIUM_DIR / paper / "tables.json"
        if tabs_path.exists():
            try:
                tables = json.loads(tabs_path.read_text())
            except Exception:
                tables = []
        page_texts = _load_page_texts(DEFAULT_PDF_DIR / f"{paper}.pdf")

        print("\n" + "=" * 66)
        print(f"PAPER: {paper}  ({len(page_texts)} pdf pages)")
        print("=" * 66)

        for item in by_paper[paper]:
            r = verify_item(item, page_texts, full_text, tables)
            summary_counts[r["suggestion"]] = summary_counts.get(r["suggestion"], 0) + 1
            print("\n" + "-" * 62)
            print(f"{r['property'].upper():18s} {item.get('composition')}  "
                  f"val={_fmt(r['value'], r['stored_unit'])}  conf={item.get('confidence')}")
            print(f"  → SUGGESTION: {r['suggestion'].upper()}")
            for reason in r["reasons"]:
                print(f"    • {reason}")
            if r["contexts"]:
                print(f"  occurrences: {r['n_occurrences']} (page {r['page']})")
                for w in r["contexts"][:2]:
                    print(f"    ctx: {w[:160]}")
            if r["unit_tokens_in_text"]:
                print(f"  units in text: {', '.join(r['unit_tokens_in_text'])}")

    print("\n" + "=" * 66)
    print("SUMMARY")
    print("=" * 66)
    for k, v in summary_counts.items():
        print(f"  {k:16s}: {v}")


if __name__ == "__main__":
    main()
