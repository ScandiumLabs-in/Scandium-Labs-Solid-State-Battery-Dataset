"""v1.2 — deterministic paper-metadata enrichment + authors (Phase 10).

Closes the Phase 10 knowledge-graph gap: the v1.0 `papers` table carried only
DOI keys — every title/journal/year was None. This module backfills that
metadata *from data already on disk*, with no network and no LLM, and stamps
a provenance `metadata_source` on every field so nothing is ever fabricated:

  tier 1  literature_output/gold_scored.json     DOI -> {title, year}
           (762 entries, produced by the discovery/mining pipeline)
  tier 2  literature_output/doi_years_cache.json DOI -> year
           (772 entries)
  tier 3  literature_output/crossref_metadata.json DOI -> {title, journal, year}
           (populated only by the opt-in network script; consumed when present)
  tier 4  first-page text of on-disk PDFs        DOI -> title/journal/year
           (format-aware, deterministic: eScholarship/LBL block, Nature-style
            DOI-anchored block, arXiv / Science-Advances / KCerS headers)

Unknown fields stay None — a paper whose metadata cannot be recovered
deterministically is never guessed at.

Also builds the `authors` table (paper_id -> author, ordered) from the same
on-disk sources (only clean, structured author lists — never heuristically
invented names). See scripts/enrich_papers_crossref.py for the opt-in network
route that can upgrade tier-3 coverage when a network is available.
"""

from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parent.parent.parent.parent

# --------------------------------------------------------------------------
# cache loaders
# --------------------------------------------------------------------------


def load_gold_scored_titles() -> dict[str, dict[str, Any]]:
    """DOI -> {title, year, family, relevance} from gold_scored.json."""
    out: dict[str, dict[str, Any]] = {}
    p = ROOT / "literature_output" / "gold_scored.json"
    if not p.exists():
        return out
    try:
        data = json.loads(p.read_text())
    except (json.JSONDecodeError, OSError):
        return out
    if not isinstance(data, list):
        return out
    for g in data:
        doi = (g.get("doi") or "").strip()
        if not doi:
            continue
        rec = {"title": (g.get("title") or "").strip() or None}
        try:
            rec["year"] = int(g["year"]) if g.get("year") is not None else None
        except (TypeError, ValueError):
            rec["year"] = None
        rec["family"] = (g.get("family") or "").strip() or None
        rec["relevance"] = g.get("relevance")
        out[doi] = rec
    return out


def load_doi_years() -> dict[str, int]:
    """DOI -> year from doi_years_cache.json."""
    out: dict[str, int] = {}
    p = ROOT / "literature_output" / "doi_years_cache.json"
    if not p.exists():
        return out
    try:
        data = json.loads(p.read_text())
    except (json.JSONDecodeError, OSError):
        return out
    if not isinstance(data, dict):
        return out
    for doi, y in data.items():
        try:
            out[doi.strip()] = int(y)
        except (TypeError, ValueError):
            continue
    return out


def load_crossref_cache() -> dict[str, dict[str, Any]]:
    """DOI -> {title, journal, year} from the opt-in Crossref cache."""
    p = ROOT / "literature_output" / "crossref_metadata.json"
    if not p.exists():
        return {}
    try:
        data = json.loads(p.read_text())
    except (json.JSONDecodeError, OSError):
        return {}
    out: dict[str, dict[str, Any]] = {}
    if isinstance(data, dict):
        for doi, rec in data.items():
            if not isinstance(rec, dict):
                continue
            out[doi.strip()] = {
                "title": (rec.get("title") or "").strip() or None,
                "journal": (rec.get("journal") or "").strip() or None,
                "year": rec.get("year"),
            }
    return out


def load_metadata_caches() -> dict[str, dict[str, Any]]:
    """Merge tier-1 + tier-2 into DOI -> {title, year} (tier 1 wins)."""
    merged: dict[str, dict[str, Any]] = {}
    for doi, y in load_doi_years().items():
        merged[doi] = {"title": None, "year": y}
    for doi, rec in load_gold_scored_titles().items():
        merged.setdefault(doi, {"title": None, "year": None}).update(rec)
    for doi, rec in load_crossref_cache().items():
        if doi not in merged:
            merged[doi] = {"title": None, "year": None}
        if rec.get("title") and not merged[doi].get("title"):
            merged[doi]["title"] = rec["title"]
        if rec.get("year") and not merged[doi].get("year"):
            merged[doi]["year"] = rec["year"]
    return merged


# --------------------------------------------------------------------------
# deterministic first-page PDF extraction
# --------------------------------------------------------------------------

_ESCHOLARSHIP_KEYS = ("Title", "Permalink", "Journal", "ISSN", "Authors",
                      "Publication Date", "DOI", "Copyright Information")


def _clean_lines(text: str) -> list[str]:
    lines = []
    for ln in (text or "").split("\n"):
        s = " ".join(ln.split())
        if s:
            lines.append(s)
    return lines


def _escaped(doi: str) -> str:
    return re.escape(doi.replace("/", "\\/").replace("-", "\\-"))


def _extract_escholarship(lines: list[str]) -> dict[str, Any] | None:
    """LBL Publications / eScholarship first-page block:

        Title
        <title lines>
        Permalink
        https://escholarship.org/uc/item/...
        Journal
        <journal>
        ...
        Authors
        Ahmed, Faiz
        Chen, Anna
        ...
        Publication Date
        2024-03-11
        DOI
        10.1021/acsaem.3c02858
    """
    try:
        i_title = lines.index("Title")
    except ValueError:
        return None
    out: dict[str, Any] = {"source": "pdf_first_page_escholarship"}
    # collect key -> value spans
    spans: dict[str, tuple[int, int]] = {}
    for key in _ESCHOLARSHIP_KEYS:
        if key in lines:
            start = lines.index(key)
            end = len(lines)
            for other in _ESCHOLARSHIP_KEYS:
                if other != key and other in lines and lines.index(other) > start:
                    end = min(end, lines.index(other))
            spans[key] = (start + 1, end)

    title_span = spans.get("Title")
    if title_span:
        out["title"] = " ".join(lines[title_span[0]:title_span[1]]) or None
    journal_span = spans.get("Journal")
    if journal_span:
        out["journal"] = " ".join(lines[journal_span[0]:journal_span[1]]) or None
    date_span = spans.get("Publication Date")
    if date_span:
        m = re.search(r"(19|20)\d{2}", " ".join(lines[date_span[0]:date_span[1]]))
        if m:
            out["year"] = int(m.group(0))
    authors_span = spans.get("Authors")
    if authors_span:
        raw = [ln for ln in lines[authors_span[0]:authors_span[1]]
               if not ln.startswith("et al.")]
        # "et al." may trail the list — strip it
        out["authors"] = [ln for ln in raw if ln.lower() != "et al."]
    return out


_NATURE_DOI_ANCHOR = re.compile(
    r"(Article|Letter|Article in Press|Nature Communications)\s*"
    r"(?:https?://)?(?:dx\.)?doi\.org/(10\.\S+)\s+(.*)",
    re.IGNORECASE,
)


def _extract_nature_style(lines: list[str], doi: str) -> dict[str, Any] | None:
    """Nature-style first page:

        Article https://doi.org/10.1038/s41467-024-51191-2
        <title lines>
        Received:22August2023
        <author line(s)>
        ...
    """
    out: dict[str, Any] = {"source": "pdf_first_page_nature"}
    doi_variants = {
        doi,
        doi.replace("/", "/"),
        doi.replace("-", "-"),
    }
    joined = " ".join(lines)
    # anchor on the DOI itself if present anywhere in the first lines
    anchor = None
    for i, ln in enumerate(lines[:8]):
        if "doi.org/" in ln or "doi" in ln.lower() and "10." in ln:
            anchor = i
            break
    if anchor is None:
        return None
    rest = lines[anchor + 1:]
    # title = lines until Received/Accepted/copyright or an author signature
    title_lines: list[str] = []
    for ln in rest:
        low = ln.lower()
        if low.startswith(("received:", "accepted:", "published:", "©",
                           "copyright", "check for updates", "correspondence")):
            break
        if "doi.org/" in low and "10." in low:
            continue
        title_lines.append(ln)
        if len(title_lines) >= 8:
            break
    if title_lines:
        # drop journal-brand / "Article in Press" noise that pdfplumber folds
        # into the same line as the DOI (Nature in-Press pages print
        # "Nature Communications https://doi.org/... Article in Press <title>").
        title = " ".join(title_lines).strip()
        for prefix in ("Article in Press", "Article", "Letter", "Brief Communication"):
            if title.lower().startswith(prefix.lower()):
                title = title[len(prefix):].strip(" :,-")
                break
        out["title"] = title or None
    # year from the Received:/Accepted:/Published: date stamp on this page
    for ln in rest + lines[:anchor + 1]:
        for marker in ("Received:", "Accepted:", "Published:", "Published online:"):
            if marker.lower() in ln.lower():
                m = re.search(r"(19|20)\d{2}", ln)
                if m:
                    out["year"] = int(m.group(0))
                    break
    if out.get("title"):
        return out
    return None


def _extract_arxiv(lines: list[str]) -> dict[str, Any] | None:
    """arXiv first page: title is the first non-empty, non-decorated line."""
    if not lines:
        return None
    first = lines[0]
    if "arxiv" not in first.lower() and "arXiv" not in first:
        return None
    out: dict[str, Any] = {"source": "pdf_first_page_arxiv"}
    # arXiv titles are the first short line that is not a URL/brand
    for ln in lines[1:]:
        low = ln.lower()
        if low.startswith(("arxiv:", "http", "submitted", "submission")):
            continue
        if len(ln.split()) <= 20:
            out["title"] = ln
            return out
    return None


def _extract_kcers(lines: list[str]) -> dict[str, Any] | None:
    """Journal of the Korean Ceramic Society header: journal + year + title."""
    if not lines or "korean ceramic" not in " ".join(lines[:3]).lower():
        return None
    out: dict[str, Any] = {"source": "pdf_first_page_kcers"}
    for ln in lines[:3]:
        if "Korean Ceramic Society" in ln:
            out["journal"] = ln.strip()
    m = re.search(r"(19|20)\d{2}", " ".join(lines[:6]))
    if m:
        out["year"] = int(m.group(0))
    # title follows the vol/no header block
    for i, ln in enumerate(lines):
        if re.search(r"Vol\.?\s*\d+", ln):
            for j in range(i + 1, min(i + 6, len(lines))):
                cand = lines[j]
                if cand and not cand.isdigit():
                    out["title"] = cand
                    return out
    return out


def _extract_science_advances(lines: list[str]) -> dict[str, Any] | None:
    """Science Advances: title after the copyright line."""
    if not lines or "SCIENCE ADVANCES" not in " ".join(lines[:4]).upper():
        return None
    out: dict[str, Any] = {"source": "pdf_first_page_sciadv"}
    for i, ln in enumerate(lines[:8]):
        if "©" in ln or "rights reserved" in ln.lower():
            for j in range(i + 1, min(i + 4, len(lines))):
                if lines[j] and not lines[j].strip().endswith(";"):
                    out["title"] = lines[j]
                    return out
    return None


def extract_first_page_metadata(pdf_path: str | Path, doi: str | None = None) -> dict[str, Any] | None:
    """Deterministically recover {title, journal, year, authors} from the
    first page of an on-disk PDF. Returns {} when nothing is recoverable —
    never guesses."""
    try:
        import pdfplumber
    except ImportError:
        return None
    try:
        with pdfplumber.open(str(pdf_path)) as pdf:
            text = pdf.pages[0].extract_text() or ""
    except Exception:
        return None
    lines = _clean_lines(text)
    if not lines:
        return None
    # DOI-confirmation gate: the on-disk PDF *filename* is NOT a trustworthy
    # identity signal (a mislabeled file would mint a wrong title). A PDF-
    # recovered metadata block is only trusted when the DOI actually appears
    # on the first page (normalized: / vs _ vs whitespace).
    if doi:
        doi_norm = doi.strip().replace("/", " ").replace("_", " ").lower()
        page_norm = " ".join(lines).lower()
        page_norm = page_norm.replace("/", " ").replace("_", " ")
        if doi_norm not in page_norm:
            return None
    extractors = (
        lambda ln: _extract_escholarship(ln),
        lambda ln: _extract_kcers(ln),
        lambda ln: _extract_nature_style(ln, doi) if doi else None,
        _extract_arxiv,
        _extract_science_advances,
    )
    for extractor in extractors:
        try:
            rec = extractor(lines)
        except Exception:
            rec = None
        if rec and any(rec.get(k) for k in ("title", "journal", "year", "authors")):
            return rec
    return None


# --------------------------------------------------------------------------
# papers enrichment
# --------------------------------------------------------------------------


def enrich_papers(
    papers: "pd.DataFrame",
    *,
    pdf_dir: str | Path | None = None,
    caches: dict[str, dict[str, Any]] | None = None,
) -> "pd.DataFrame":
    """Fill title/journal/year (+ a provenance metadata_source column) on the
    papers table. Tier order: caches -> on-disk PDF first page. A field is
    only written when recovered deterministically; unknown stays None."""
    import pandas as pd

    if caches is None:
        caches = load_metadata_caches()

    out = papers.copy()
    if "title" not in out.columns:
        out["title"] = None
    if "journal" not in out.columns:
        out["journal"] = None
    if "year" not in out.columns:
        out["year"] = None
    out["metadata_source"] = None

    pdf_dir_p = Path(pdf_dir) if pdf_dir else ROOT / "literature_output" / "pdfs"
    pdf_files: dict[str, Path] = {}
    if pdf_dir_p.is_dir():
        for f in pdf_dir_p.glob("*.pdf"):
            doi_like = f.stem.replace("_", "/")
            pdf_files[doi_like] = f

    # deterministic iteration order
    for idx, row in out.iterrows():
        doi = str(row.get("doi") or "").strip()
        if not doi:
            continue
        src = []
        cache = caches.get(doi)
        if cache:
            if cache.get("title") and not out.at[idx, "title"]:
                out.at[idx, "title"] = cache["title"]
                src.append("cache")
            if cache.get("year") and not out.at[idx, "year"]:
                out.at[idx, "year"] = int(cache["year"])
                if "cache" not in src:
                    src.append("cache")
            if cache.get("journal") and not out.at[idx, "journal"]:
                out.at[idx, "journal"] = cache["journal"]
                if "cache" not in src:
                    src.append("cache")
        pdf = pdf_files.get(doi)
        if pdf:
            meta = extract_first_page_metadata(pdf, doi=doi)
            if meta:
                for k in ("title", "journal", "year"):
                    val = meta.get(k)
                    if not val:
                        continue
                    current = out.at[idx, k]
                    empty = current in (None, "") or (
                        isinstance(current, float) and current != current)
                    if empty:
                        out.at[idx, k] = int(val) if k == "year" else val
                src.append(meta.get("source", "pdf_first_page"))
        if src:
            out.at[idx, "metadata_source"] = ",".join(sorted(set(src)))
    return out


# --------------------------------------------------------------------------
# authors table (Phase 10)
# --------------------------------------------------------------------------


def build_authors(
    papers: "pd.DataFrame",
    *,
    pdf_dir: str | Path | None = None,
) -> "pd.DataFrame":
    """One row per (paper_id, author-position) recovered deterministically.

    Only clean structured author lists count (eScholarship/LBL blocks today);
    free-text first-page name blocks are NOT parsed heuristically, so the
    table is honest: sparse, but every name is a real extracted author.
    """
    import pandas as pd

    from ssb_dataset.db import schema as s

    pdf_dir_p = Path(pdf_dir) if pdf_dir else ROOT / "literature_output" / "pdfs"
    pdf_files: dict[str, Path] = {}
    if pdf_dir_p.is_dir():
        for f in pdf_dir_p.glob("*.pdf"):
            pdf_files[f.stem.replace("_", "/")] = f

    rows: list[dict[str, Any]] = []
    for _, prow in papers.iterrows():
        doi = str(prow.get("doi") or "").strip()
        if not doi:
            continue
        pdf = pdf_files.get(doi)
        if not pdf:
            continue
        meta = extract_first_page_metadata(pdf, doi=doi)
        if not meta or not meta.get("authors"):
            continue
        for pos, author in enumerate(meta["authors"], start=1):
            rows.append({
                "author_id": s.stable_id("author", doi, author, pos),
                "paper_id": doi,
                "author": author,
                "author_position": pos,
                "metadata_source": meta.get("source", "pdf_first_page"),
            })
    df = pd.DataFrame(rows)
    if not df.empty:
        df = df.drop_duplicates(subset=["author_id"], keep="first")
    return df
