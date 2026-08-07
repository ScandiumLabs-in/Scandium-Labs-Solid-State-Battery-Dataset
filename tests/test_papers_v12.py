"""Tests for v1.2 — papers metadata enrichment + authors table (Phase 10).

Covers the deterministic backfill of papers title/journal/year from on-disk
caches and the DOI-confirmation gate for PDF first-page recovery, plus the
authors table. No network, no LLM.
"""

from __future__ import annotations

import pandas as pd

from ssb_dataset.db import papers as P
from ssb_dataset.db import schema as s


# --------------------------------------------------------------------------
# cache loaders
# --------------------------------------------------------------------------

def test_load_gold_scored_titles(tmp_path, monkeypatch):
    cache = tmp_path / "literature_output"
    cache.mkdir()
    (cache / "gold_scored.json").write_text(
        '[{"doi": "10.1/x", "title": "A paper", "year": 2020, "family": "oxide"}]')
    monkeypatch.setattr(P, "ROOT", tmp_path)
    out = P.load_gold_scored_titles()
    assert out["10.1/x"]["title"] == "A paper"
    assert out["10.1/x"]["year"] == 2020


def test_load_doi_years_shape():
    years = P.load_doi_years()
    assert isinstance(years, dict)
    assert all(isinstance(y, int) for y in years.values())


def test_load_metadata_caches_merges():
    merged = P.load_metadata_caches()
    assert isinstance(merged, dict)
    for rec in merged.values():
        assert "title" in rec and "year" in rec


def test_load_crossref_cache_empty_when_absent(tmp_path, monkeypatch):
    monkeypatch.setattr(P, "ROOT", tmp_path)
    assert P.load_crossref_cache() == {}


def test_load_crossref_cache_parses(tmp_path, monkeypatch):
    (tmp_path / "literature_output").mkdir()
    (tmp_path / "literature_output" / "crossref_metadata.json").write_text(
        '{"10.1/x": {"title": "T", "journal": "J", "year": 2019}}')
    monkeypatch.setattr(P, "ROOT", tmp_path)
    out = P.load_crossref_cache()
    assert out["10.1/x"] == {"title": "T", "journal": "J", "year": 2019}


# --------------------------------------------------------------------------
# papers enrichment
# --------------------------------------------------------------------------

def _mk_papers():
    return pd.DataFrame([
        {"paper_id": "10.1/known", "doi": "10.1/known",
         "title": None, "journal": None, "year": None},
        {"paper_id": "10.2/unknown", "doi": "10.2/unknown",
         "title": None, "journal": None, "year": None},
    ])


def test_enrich_papers_from_caches():
    papers = _mk_papers()
    caches = {"10.1/known": {"title": "Found title", "year": 2021, "journal": None}}
    out = P.enrich_papers(papers, caches=caches, pdf_dir=None)
    row = out[out["doi"] == "10.1/known"].iloc[0]
    assert row["title"] == "Found title"
    assert row["year"] == 2021
    assert "cache" in str(row["metadata_source"])
    # unknown paper stays None — never guessed
    unk = out[out["doi"] == "10.2/unknown"].iloc[0]
    assert unk["title"] is None and unk["year"] is None


def test_enrich_papers_preserves_existing_metadata():
    papers = pd.DataFrame([
        {"paper_id": "10.1/x", "doi": "10.1/x",
         "title": "Already known", "journal": None, "year": 2020},
    ])
    caches = {"10.1/x": {"title": "Wrong title", "year": 1999, "journal": None}}
    out = P.enrich_papers(papers, caches=caches, pdf_dir=None)
    row = out.iloc[0]
    assert row["title"] == "Already known"
    assert row["year"] == 2020


def test_enrich_papers_adds_metadata_source_column():
    papers = _mk_papers()
    out = P.enrich_papers(papers, caches={}, pdf_dir=None)
    assert "metadata_source" in out.columns


def test_enrich_papers_missing_doi_skipped():
    papers = pd.DataFrame([{"paper_id": "x", "doi": None, "title": None}])
    out = P.enrich_papers(papers, caches={}, pdf_dir=None)
    assert out.iloc[0]["metadata_source"] is None


# --------------------------------------------------------------------------
# first-page PDF extraction + DOI-confirmation gate
# --------------------------------------------------------------------------

def test_escholarship_extractor():
    lines = [
        "Lawrence Berkeley National Laboratory",
        "LBL Publications",
        "Title",
        "A Great Solid Electrolyte Paper",
        "Permalink",
        "https://escholarship.org/uc/item/8cc5m7jh",
        "Journal",
        "ACS Applied Energy Materials, 7(5)",
        "Authors",
        "Ahmed, Faiz",
        "Chen, Anna",
        "Publication Date",
        "2024-03-11",
        "DOI",
        "10.1021/acsaem.3c02858",
    ]
    rec = P._extract_escholarship(lines)
    assert rec["title"] == "A Great Solid Electrolyte Paper"
    assert rec["journal"] == "ACS Applied Energy Materials, 7(5)"
    assert rec["year"] == 2024
    assert rec["authors"] == ["Ahmed, Faiz", "Chen, Anna"]


def test_nature_extractor_strips_article_prefix():
    lines = [
        "Article https://doi.org/10.1038/x",
        "A real title about garnets",
        "and it continues",
        "Received:22August2023",
    ]
    rec = P._extract_nature_style(lines, "10.1038/x")
    assert rec["title"] == "A real title about garnets and it continues"
    assert rec["year"] == 2023


def test_nature_extractor_in_press():
    lines = [
        "Nature Communications https://doi.org/10.1038/y",
        "Article in Press A title after the prefix",
        "Received:1January2025",
    ]
    rec = P._extract_nature_style(lines, "10.1038/y")
    assert rec["title"] == "A title after the prefix"
    assert rec["year"] == 2025


def test_doi_confirmation_gate_rejects_mismatched_pdf(tmp_path, monkeypatch):
    """The JACS lesson: a PDF whose filename says one DOI but whose page
    shows another paper must NOT mint a title for the wrong DOI."""
    import pdfplumber
    pdf = tmp_path / "10.1021_jacs.1c07481.pdf"
    pdf.write_text("not a real pdf")
    # A page that does NOT contain the DOI must yield None.
    class FakePDF:
        class page:
            @staticmethod
            def extract_text():
                return "Some other paper entirely"
    monkeypatch.setattr(pdfplumber, "open", lambda *a, **k: type(
        "ctx", (), {"__enter__": lambda s: type(
            "pdf", (), {"pages": [FakePDF.page]})(),
            "__exit__": lambda *a: None})())
    assert P.extract_first_page_metadata(pdf, doi="10.1021/jacs.1c07481") is None


def test_doi_confirmation_gate_passes_matching_page(tmp_path, monkeypatch):
    import pdfplumber
    pdf = tmp_path / "10.1038_x.pdf"
    pdf.write_text("not a real pdf")

    class FakePDF:
        class page:
            @staticmethod
            def extract_text():
                return ("Article https://doi.org/10.1038/x\n"
                        "A real title\nReceived:1Jan2023")

    monkeypatch.setattr(pdfplumber, "open", lambda *a, **k: type(
        "ctx", (), {"__enter__": lambda s: type(
            "pdf", (), {"pages": [FakePDF.page]})(),
            "__exit__": lambda *a: None})())
    rec = P.extract_first_page_metadata(pdf, doi="10.1038/x")
    assert rec and rec.get("title") == "A real title"


# --------------------------------------------------------------------------
# authors table
# --------------------------------------------------------------------------

def test_author_id_scheme():
    a1 = s.stable_id("author", "10.1/x", "Ahmed, Faiz", 1)
    a2 = s.stable_id("author", "10.1/x", "Ahmed, Faiz", 1)
    assert a1 == a2
    assert a1.startswith("aut-")


def test_build_authors_empty_when_no_pdfs(tmp_path, monkeypatch):
    papers = _mk_papers()
    monkeypatch.setattr(P, "ROOT", tmp_path)  # no pdfs dir
    out = P.build_authors(papers, pdf_dir=tmp_path / "nope")
    assert len(out) == 0


def test_build_authors_requires_clean_lists(tmp_path, monkeypatch):
    """Only structured author lists (eScholarship blocks) are emitted."""
    import pdfplumber
    papers = pd.DataFrame([{"paper_id": "10.1021/acsaem.3c02858",
                            "doi": "10.1021/acsaem.3c02858"}])

    class FakePDF:
        class page:
            @staticmethod
            def extract_text():
                return (
                    "Lawrence Berkeley National Laboratory\nLBL Publications\n"
                    "Title\nA Paper\nPermalink\nhttps://escholarship.org/x\n"
                    "Journal\nSome Journal\nAuthors\nAhmed, Faiz\nChen, Anna\n"
                    "Publication Date\n2024-03-11\nDOI\n10.1021/acsaem.3c02858")

    pdf = tmp_path / "10.1021_acsaem.3c02858.pdf"
    pdf.write_text("not a real pdf")
    monkeypatch.setattr(pdfplumber, "open", lambda *a, **k: type(
        "ctx", (), {"__enter__": lambda s: type(
            "pdf", (), {"pages": [FakePDF.page]})(),
            "__exit__": lambda *a: None})())
    out = P.build_authors(papers, pdf_dir=tmp_path)
    assert len(out) == 2
    assert out["author"].tolist() == ["Ahmed, Faiz", "Chen, Anna"]
    assert out["author_position"].tolist() == [1, 2]
    assert out["author_id"].str.startswith("aut-").all()


def test_build_authors_skips_nature_style(tmp_path, monkeypatch):
    """Free-text first-page name blocks (Nature-style, names fused with
    affiliation markers and no spaces) are NOT parsed heuristically."""
    import pdfplumber
    papers = pd.DataFrame([{"paper_id": "10.1038/x", "doi": "10.1038/x"}])

    class FakePDF:
        class page:
            @staticmethod
            def extract_text():
                return ("Article https://doi.org/10.1038/x\n"
                        "A title\nReceived:22August2023\n"
                        "Cheng-DongFang1,3,YingHuang1,3,KeLi1,")

    pdf = tmp_path / "10.1038_x.pdf"
    pdf.write_text("not a real pdf")
    monkeypatch.setattr(pdfplumber, "open", lambda *a, **k: type(
        "ctx", (), {"__enter__": lambda s: type(
            "pdf", (), {"pages": [FakePDF.page]})(),
            "__exit__": lambda *a: None})())
    out = P.build_authors(papers, pdf_dir=tmp_path)
    assert len(out) == 0


def test_build_authors_dedupes(tmp_path, monkeypatch):
    import pdfplumber
    papers = pd.DataFrame([
        {"paper_id": "10.1021/acsaem.3c02858", "doi": "10.1021/acsaem.3c02858"},
        {"paper_id": "10.1021/acsaem.3c02858", "doi": "10.1021/acsaem.3c02858"},
    ])

    class FakePDF:
        class page:
            @staticmethod
            def extract_text():
                return (
                    "Lawrence Berkeley National Laboratory\nLBL Publications\n"
                    "Title\nA Paper\nPermalink\nhttps://escholarship.org/x\n"
                    "Journal\nSome Journal\nAuthors\nAhmed, Faiz\n"
                    "Publication Date\n2024-03-11\nDOI\n10.1021/acsaem.3c02858")

    pdf = tmp_path / "10.1021_acsaem.3c02858.pdf"
    pdf.write_text("not a real pdf")
    monkeypatch.setattr(pdfplumber, "open", lambda *a, **k: type(
        "ctx", (), {"__enter__": lambda s: type(
            "pdf", (), {"pages": [FakePDF.page]})(),
            "__exit__": lambda *a: None})())
    out = P.build_authors(papers, pdf_dir=tmp_path)
    assert len(out) == 1
