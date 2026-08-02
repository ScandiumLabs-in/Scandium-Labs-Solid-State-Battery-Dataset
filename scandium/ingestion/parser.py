from __future__ import annotations

import re
from pathlib import Path
from typing import Any

import fitz

SECTION_PATTERNS = [
    r"^\s*(Abstract)\s*$",
    r"^\s*(?:\d+\.?|I+\.?|IV+\.?|V+\.?)?\s*(Introduction|Background)\s*$",
    r"^\s*(?:\d+\.?)?\s*(Experimental|Methods|Methodology|Materials and Methods|Synthesis|Characterization)\s*$",
    r"^\s*(?:\d+\.?)?\s*(Results and Discussion|Results)\s*$",
    r"^\s*(?:\d+\.?)?\s*(Discussion)\s*$",
    r"^\s*(?:\d+\.?)?\s*(Conclusion|Conclusions|Summary)\s*$",
    r"^\s*(?:\d+\.?)?\s*(Acknowledgments?|Acknowledgements?)\s*$",
    r"^\s*(References|Bibliography)\s*$",
    r"^\s*(Supporting Information|Supplementary|Appendix)\s*$",
]

FIGURE_CAPTION_PATTERN = re.compile(
    r"^(Fig(?:ure)?\.?\s*\d+[\.:]\s*.+)$", re.IGNORECASE
)
TABLE_CAPTION_PATTERN = re.compile(
    r"^(Table\s+\d+[\.:]\s*.+)$", re.IGNORECASE
)
DOI_PATTERN = re.compile(r"10\.\d{4,}/[-._;()/:\w]+")
YEAR_PATTERN = re.compile(r"\b(19|20)\d{2}\b")


class PaperSection:
    def __init__(self, name: str, page: int, start_para: int):
        self.name = name
        self.page = page
        self.start_para = start_para
        self.end_para: int = start_para
        self.paragraphs: list[str] = []

    def to_dict(self) -> dict[str, Any]:
        return {
            "name": self.name,
            "page": self.page,
            "start_para": self.start_para,
            "end_para": self.end_para,
            "text": "\n".join(self.paragraphs),
        }


class ParsedPaper:
    def __init__(self, path: Path):
        self.path = path
        self.paper_id = path.stem
        self.pages: list[int] = []
        self.raw_text: str = ""
        self.sections: list[PaperSection] = []
        self.tables: list[dict[str, Any]] = []
        self.figures: list[dict[str, Any]] = []
        self.references: list[str] = []
        self.metadata: dict[str, Any] = {}
        self.paragraphs: list[dict[str, Any]] = []

    def to_dict(self) -> dict[str, Any]:
        return {
            "paper_id": self.paper_id,
            "metadata": self.metadata,
            "sections": [s.to_dict() for s in self.sections],
            "tables": self.tables,
            "figures": self.figures,
            "references": self.references,
            "paragraphs": self.paragraphs,
            "full_text_len": len(self.raw_text),
        }


INLINE_SECTION_PATTERN = re.compile(
    r"^(?:\d+\.?\s*)?(Abstract|Introduction|Background|Experimental|Methods|Methodology|"
    r"Materials and Methods|Synthesis|Characterization|Results and Discussion|Results|"
    r"Discussion|Conclusion|Conclusions|Summary|Acknowledgments?|Acknowledgements?|"
    r"References|Bibliography|Supplementary|Appendix)\s"
)


def normalize_line(line: str) -> str:
    line = re.sub(r"\s+", " ", line).strip()
    line = line.replace("\u00ad", "")
    return line


def is_section_header(line: str) -> str | None:
    cleaned = normalize_line(line)
    if not cleaned:
        return None
    for pattern in SECTION_PATTERNS:
        m = re.match(pattern, cleaned)
        if m:
            return m.group(1)
    return None


def split_inline_section(text: str) -> tuple[str | None, str]:
    m = INLINE_SECTION_PATTERN.match(text)
    if m:
        return m.group(1), text[m.end():].strip()
    return None, text


def is_figure_caption(line: str) -> str | None:
    m = FIGURE_CAPTION_PATTERN.match(normalize_line(line))
    return m.group(0) if m else None


def is_table_caption(line: str) -> str | None:
    m = TABLE_CAPTION_PATTERN.match(normalize_line(line))
    return m.group(0) if m else None


def extract_references(lines: list[str]) -> list[str]:
    refs: list[str] = []
    capturing = False
    buffer = ""
    for line in lines:
        cleaned = normalize_line(line)
        if not cleaned:
            continue
        if re.match(r"^\[\d+\]", cleaned) or re.match(r"^\d+\.", cleaned):
            if buffer:
                refs.append(buffer)
            buffer = cleaned
            capturing = True
        elif capturing:
            buffer += " " + cleaned
    if buffer:
        refs.append(buffer)
    return refs


def extract_metadata(text: str, first_page_text: str) -> dict[str, Any]:
    meta: dict[str, Any] = {}
    doi_match = DOI_PATTERN.search(text)
    if doi_match:
        meta["doi"] = doi_match.group(0).rstrip(".,;")

    title_candidates = re.findall(r"^[A-Z][A-Za-z\s,;:\-()/0-9εμθ]{20,200}$", first_page_text[:2000], re.MULTILINE)
    if title_candidates:
        meta["title"] = max(title_candidates, key=len).strip()
    if meta.get("title") and ("Copyright" in meta["title"] or "open access" in meta["title"].lower()):
        title_candidates = [c for c in title_candidates
                           if "Copyright" not in c and "open access" not in c.lower()]
        if title_candidates:
            meta["title"] = max(title_candidates, key=len).strip()

    years = YEAR_PATTERN.findall(text)
    if years:
        meta["year"] = int(years[0])

    lines = first_page_text.split("\n")
    author_candidates = [l.strip() for l in lines if "," in l and len(l.strip()) < 300]
    if author_candidates:
        meta["authors"] = author_candidates[0]
    return meta


def detect_section(text: str, start: int, end: int, lines: list[str], page: int) -> list[PaperSection]:
    sections: list[PaperSection] = []
    current_section: PaperSection | None = None

    for i in range(start, end):
        if i >= len(lines):
            break
        line = lines[i]
        header = is_section_header(line)
        if header:
            if current_section:
                current_section.end_para = i - 1
                sections.append(current_section)
            current_section = PaperSection(header, page, i)
        elif current_section:
            cleaned = normalize_line(line)
            if cleaned:
                current_section.paragraphs.append(cleaned)

    if current_section:
        current_section.end_para = end
        sections.append(current_section)

    return sections


def parse_paper(pdf_path: str | Path) -> ParsedPaper:
    path = Path(pdf_path)
    paper = ParsedPaper(path)
    doc = fitz.open(str(path))

    PAGE_NUM_PATTERN = re.compile(r"^\d{1,2}$")
    SECTION_HEADER_START = re.compile(
        r"^(?:\d+\.?\s*)?(?:Abstract|Introduction|Background|Experimental|Methods|Methodology|"
        r"Materials and Methods|Synthesis|Characterization|Results and Discussion|Results|"
        r"Discussion|Conclusion|Conclusions|Summary|Acknowledgments?|Acknowledgements?|"
        r"References|Bibliography|Supplementary|Appendix)"
    )

    all_lines: list[str] = []
    paragraphs: list[dict[str, Any]] = []
    all_text_parts: list[str] = []
    first_page_text = ""

    def flush_para(para: list[str], page: int) -> None:
        if not para:
            return
        para_text = " ".join(para)
        paragraphs.append({
            "page": page,
            "para_num": len(paragraphs) + 1,
            "text": para_text,
        })
        all_lines.append(para_text)
        para.clear()

    for page_num, page in enumerate(doc, 1):
        text = page.get_text()
        if page_num == 1:
            first_page_text = text
        all_text_parts.append(text)
        page_lines = text.split("\n")
        para: list[str] = []
        for raw_line in page_lines:
            cleaned = normalize_line(raw_line)
            if not cleaned:
                flush_para(para, page_num)
                continue
            if PAGE_NUM_PATTERN.match(cleaned):
                flush_para(para, page_num)
                continue
            if is_section_header(cleaned):
                flush_para(para, page_num)
                para.append(cleaned)
                flush_para(para, page_num)
                continue
            if SECTION_HEADER_START.match(cleaned):
                flush_para(para, page_num)
                header, remainder = split_inline_section(cleaned)
                if header:
                    paragraph = {
                        "page": page_num,
                        "para_num": len(paragraphs) + 1,
                        "text": header,
                        "is_section_header": True,
                    }
                    paragraphs.append(paragraph)
                    all_lines.append(header)
                    if remainder:
                        paragraphs.append({
                            "page": page_num,
                            "para_num": len(paragraphs) + 1,
                            "text": remainder,
                            "is_section_header": False,
                        })
                        all_lines.append(remainder)
                    continue
            para.append(cleaned)
        flush_para(para, page_num)

    paper.raw_text = "".join(all_text_parts)
    paper.pages = list(range(1, len(doc) + 1))
    paper.paragraphs = paragraphs
    paper.metadata = extract_metadata(paper.raw_text, first_page_text)
    _sections: list[PaperSection] = []
    current: PaperSection | None = None
    for p in paper.paragraphs:
        is_header = p.get("is_section_header", False)
        if is_header:
            if current:
                _sections.append(current)
            current = PaperSection(p["text"], p["page"], p["para_num"])
        elif current:
            current.paragraphs.append(p["text"])
            current.end_para = p["para_num"]
    if current:
        _sections.append(current)
    paper.sections = _sections

    sections = detect_section(
        paper.raw_text, 0, len(all_lines), all_lines, 1
    )
    paper.sections = sections

    for line_text in all_lines:
        cap = is_figure_caption(line_text)
        if cap:
            paper.figures.append({"caption": cap})
        cap = is_table_caption(line_text)
        if cap:
            paper.tables.append({"caption": cap})

    paper.references = extract_references(all_lines)

    doc.close()
    return paper


def save_paper(paper: ParsedPaper, output_dir: str | Path = "scandium_output") -> Path:
    out = Path(output_dir) / paper.paper_id
    out.mkdir(parents=True, exist_ok=True)

    import json
    (out / "metadata.json").write_text(json.dumps(paper.metadata, indent=2))
    (out / "sections.json").write_text(
        json.dumps([s.to_dict() for s in paper.sections], indent=2)
    )
    (out / "tables.json").write_text(json.dumps(paper.tables, indent=2))
    (out / "figures.json").write_text(json.dumps(paper.figures, indent=2))
    (out / "references.json").write_text(json.dumps(paper.references, indent=2))
    (out / "full_text.txt").write_text(paper.raw_text)
    (out / "paper.json").write_text(json.dumps(paper.to_dict(), indent=2))

    return out
