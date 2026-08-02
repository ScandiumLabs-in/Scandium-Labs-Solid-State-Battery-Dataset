from __future__ import annotations

from pathlib import Path
from typing import Any

from scandium.ingestion.parser import ParsedPaper


def chunk_paragraph(
    text: str,
    paper_id: str,
    section: str,
    page: int,
    para_num: int,
    chunk_size: int = 500,
    overlap: int = 50,
) -> list[dict[str, Any]]:
    words = text.split()
    chunks: list[dict[str, Any]] = []
    start = 0
    while start < len(words):
        end = start + chunk_size
        chunk_words = words[start:end]
        chunks.append({
            "paper_id": paper_id,
            "section": section,
            "page": page,
            "para_num": para_num,
            "chunk_index": len(chunks),
            "text": " ".join(chunk_words),
            "n_words": len(chunk_words),
        })
        start = end - overlap if end < len(words) else end
    return chunks


def chunk_paper(paper: ParsedPaper, chunk_size: int = 500, overlap: int = 50) -> list[dict[str, Any]]:
    all_chunks: list[dict[str, Any]] = []
    section_map: dict[str, str] = {}
    for s in paper.sections:
        for pnum in range(s.start_para, s.end_para + 1):
            section_map[pnum] = s.name

    for p in paper.paragraphs:
        pnum = p["para_num"]
        section = section_map.get(pnum, "Unknown")
        para_chunks = chunk_paragraph(
            p["text"],
            paper.paper_id,
            section,
            p["page"],
            pnum,
            chunk_size=chunk_size,
            overlap=overlap,
        )
        all_chunks.extend(para_chunks)

    return all_chunks


def build_chunk_metadata(chunks: list[dict[str, Any]], paper: ParsedPaper) -> list[dict[str, Any]]:
    enriched: list[dict[str, Any]] = []
    for c in chunks:
        c["doi"] = paper.metadata.get("doi", "")
        c["title"] = paper.metadata.get("title", "")
        c["year"] = paper.metadata.get("year")
        enriched.append(c)
    return enriched
