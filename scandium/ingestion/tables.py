from __future__ import annotations

import re
from pathlib import Path
from typing import Any

import fitz
import pdfplumber

TABLE_HEADER = re.compile(r"^(Table\s+\d+[\.:]?\s*.+)$", re.IGNORECASE)
SECTION_BREAK = re.compile(
    r"^(?:Fig(?:ure)?\.?\s+\d+|"
    r"(?:\d+\.?\s*)?(?:Introduction|Experimental|Methods|Results|Discussion|Conclusion|"
    r"Acknowledgments?|References|Supplementary)\b)",
    re.IGNORECASE,
)
PAGE_NUM = re.compile(r"^\d{1,2}$")
IS_NUMERIC = re.compile(r"^[\d.\-,–]+$")
IS_UNIT = re.compile(r"^\(.+\)$")
HAS_REF = re.compile(r"\[.*\]")


def extract_text_lines(pdf_path: str | Path) -> list[dict[str, Any]]:
    lines: list[dict[str, Any]] = []
    with fitz.open(str(pdf_path)) as doc:
        for page_num, page in enumerate(doc, 1):
            text = page.get_text()
            for raw in text.split("\n"):
                cleaned = raw.strip()
                if not cleaned or PAGE_NUM.match(cleaned):
                    continue
                lines.append({"page": page_num, "text": cleaned})
    return lines


def detect_tables(lines: list[dict[str, Any]]) -> list[dict[str, Any]]:
    tables: list[dict[str, Any]] = []
    i = 0
    while i < len(lines):
        m = TABLE_HEADER.match(lines[i]["text"])
        if not m:
            i += 1
            continue
        caption = m.group(1)
        header: list[str] = []
        data: list[str] = []
        in_header = True
        j = i + 1
        while j < len(lines):
            text = lines[j]["text"]
            if TABLE_HEADER.match(text) and text != caption:
                break
            if SECTION_BREAK.match(text) and data:
                break
            if in_header:
                if text.startswith(("Note:", "Values are")) and data:
                    break
                if IS_UNIT.match(text):
                    header.append(text)
                elif len(header) >= 2 and IS_NUMERIC.match(text[0]):
                    in_header = False
                    data.append(text)
                elif text.strip():
                    header.append(text)
                else:
                    break
            else:
                if text.startswith(("Fig", "Figure")):
                    break
                if SECTION_BREAK.match(text):
                    break
                data.append(text)
            j += 1
        if data:
            n_cols = infer_cols(data)
            rows = group_rows(data, n_cols)
            if rows:
                tables.append({
                    "caption": caption,
                    "page": lines[i]["page"],
                    "n_cols": n_cols,
                    "n_rows": len(rows),
                    "headers": reconstruct_headers(header, n_cols),
                    "rows": rows,
                })
            i = j
        else:
            i += 1
    return tables


def infer_cols(data: list[str]) -> int:
    best_n = 5
    best_score = -1.0
    for n in range(2, 11):
        if len(data) < n * 2:
            continue
        n_rows = len(data) // n
        leftovers = len(data) - n_rows * n
        completeness = 1.0 - leftovers / max(len(data), 1)
        consistency = 0.0
        for r in range(n_rows):
            row = [data[r * n + c] for c in range(n)]
            first = row[0]
            last = row[-1]
            if IS_NUMERIC.match(first) or first == "-" or HAS_REF.match(first):
                consistency += 1.0
            if IS_NUMERIC.match(last) or last == "-":
                pass
            else:
                consistency += 0.5
        avg_consistency = consistency / max(n_rows, 1)
        score = completeness * 0.4 + avg_consistency * 0.6
        if score > best_score:
            best_score = score
            best_n = n
    return best_n


def group_rows(cells: list[str], n_cols: int) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for i in range(0, len(cells) - n_cols + 1, n_cols):
        row = {}
        for j in range(n_cols):
            row[f"col_{j}"] = cells[i + j].strip()
        rows.append(row)
    return rows


def reconstruct_headers(header_lines: list[str], n_cols: int) -> list[str]:
    is_unit = [bool(IS_UNIT.match(h)) for h in header_lines]
    if sum(is_unit) and n_cols > 0:
        unit_indices = [i for i, u in enumerate(is_unit) if u]
        headers: list[str] = []
        prev = 0
        for ui in unit_indices:
            name_parts = " ".join(header_lines[prev:ui]).strip()
            unit = header_lines[ui].strip()
            if name_parts:
                headers.append(f"{name_parts} {unit}")
            else:
                headers.append(unit)
            prev = ui + 1
        for h in header_lines[prev:]:
            headers.append(h.strip())
        while len(headers) < n_cols:
            headers.append("")
        return headers[:n_cols]
    merged = " ".join(header_lines)
    parts = merged.split()
    if len(parts) <= n_cols:
        return (parts + [""] * n_cols)[:n_cols]
    per_col = max(1, len(parts) // n_cols)
    headers = []
    for i in range(n_cols):
        s = i * per_col
        e = s + per_col if i < n_cols - 1 else len(parts)
        headers.append(" ".join(parts[s:e]))
    return headers


def extract_tables(pdf_path: str | Path) -> list[dict[str, Any]]:
    lines = extract_text_lines(pdf_path)
    tables = detect_tables(lines)
    if tables:
        return tables
    return _fallback_pdfplumber(pdf_path)


def _fallback_pdfplumber(pdf_path: str | Path) -> list[dict[str, Any]]:
    tables: list[dict[str, Any]] = []
    with pdfplumber.open(str(pdf_path)) as pdf:
        for page_num, page in enumerate(pdf.pages, 1):
            for table in page.extract_tables() or []:
                if not table or len(table) < 2:
                    continue
                header = table[0]
                rows = []
                for row in table[1:]:
                    rd: dict[str, Any] = {}
                    for j, cell in enumerate(row):
                        cn = str(header[j]) if j < len(header) and header[j] else f"col_{j}"
                        rd[cn] = str(cell).strip() if cell else ""
                    rows.append(rd)
                tables.append({
                    "caption": "",
                    "page": page_num,
                    "n_cols": len(header),
                    "n_rows": len(rows),
                    "headers": [str(h).strip() if h else "" for h in header],
                    "rows": rows,
                })
    return tables


def tables_to_markdown(tables: list[dict[str, Any]]) -> str:
    parts: list[str] = []
    for t in tables:
        if t.get("caption"):
            parts.append(f"**{t['caption']}**")
        h = t.get("headers", [])
        if h:
            parts.append("| " + " | ".join(h) + " |")
            parts.append("| " + " | ".join("---" for _ in h) + " |")
        for row in t.get("rows", []):
            cells = [row.get(f"col_{j}", "") for j in range(len(h) or len(next(iter(t["rows"]), {})))]
            parts.append("| " + " | ".join(cells) + " |")
        parts.append("")
    return "\n".join(parts)
