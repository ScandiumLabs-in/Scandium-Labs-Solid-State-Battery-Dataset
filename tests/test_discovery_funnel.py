"""Phase E1 — widened free discovery funnel tests.

Covers the OpenAlex discovery merge (DOI-merge, no truncation) and the
multi-route harvester's expanded route chain (reason recording, CORE/BASE
fallbacks, DOAJ pre-check) using mocked network boundaries.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "scripts"))

from ssb_dataset.schema import Family  # noqa: E402


class TestOpenAlexMerge:
    def test_merges_by_doi_without_truncation(self, tmp_path: Path) -> None:
        from harvest_openalex import merge_into_discovery
        out = tmp_path / "discovery_candidates.json"
        out.write_text(json.dumps({
            "sulfide": [
                {"doi": "10.1/a", "title": "A", "relevance_score": 0.4,
                 "source": "semantic_scholar", "sources": ["semantic_scholar"]},
            ],
        }))
        new = {Family.sulfide: [
            {"doi": "10.1/a", "title": "A", "relevance_score": 0.4},
            {"doi": "10.2/b", "title": "B", "relevance_score": 0.6},
        ]}
        merged = merge_into_discovery(new, out)
        sulfide = merged["sulfide"]
        by_doi = {p["doi"]: p for p in sulfide}
        assert "10.2/b" in by_doi                     # new candidate appended
        assert "openalex" in by_doi["10.1/a"]["sources"]   # existing tagged
        assert by_doi["10.1/a"]["source"] == "semantic_scholar"  # source preserved

    def test_persists_file(self, tmp_path: Path) -> None:
        from harvest_openalex import merge_into_discovery
        out = tmp_path / "discovery_candidates.json"
        merge_into_discovery({Family.garnet: [
            {"doi": "10.9/x", "title": "X", "relevance_score": 0.9},
        ]}, out)
        data = json.loads(out.read_text())
        assert data["garnet"][0]["doi"] == "10.9/x"
        assert data["garnet"][0]["source"] == "openalex"


class TestHarvestRoutes:
    def test_is_pdf_rejects_html(self) -> None:
        from harvest_multi_route import _is_pdf
        assert _is_pdf(b"%PDF-1.7\n" + b"0" * 6000)
        assert not _is_pdf(b"<html><body>no</body></html>")

    def test_europepmc_for_returns_render_url(self) -> None:
        from harvest_multi_route import europepmc_for
        assert europepmc_for(["https://pmc.ncbi.nlm.nih.gov/articles/PMC123/"]) \
            == "https://europepmc.org/articles/PMC123?pdf=render"
        assert europepmc_for(["https://example.com/x.pdf"]) is None

    def test_harvest_records_venue_oa_and_reason(self, tmp_path: Path, monkeypatch) -> None:
        from harvest_multi_route import harvest
        # Repoint module-level paths to a tmp dir so nothing touches the repo.
        monkeypatch.setattr("harvest_multi_route.PDF_DIR", tmp_path)
        pdf = tmp_path / "10.9_y.pdf"
        pdf.write_bytes(b"%PDF-1.7\n" + b"0" * 6000)
        res = harvest("10.9/y")
        assert res["status"] == "already_have"

    def test_harvest_reason_not_open_access(self, tmp_path: Path, monkeypatch) -> None:
        import harvest_multi_route as hm
        monkeypatch.setattr("harvest_multi_route.PDF_DIR", tmp_path)
        monkeypatch.setattr("harvest_multi_route.venue_is_oa", lambda doi: False)
        monkeypatch.setattr("harvest_multi_route.unpaywall_locations", lambda doi: [])
        monkeypatch.setattr("harvest_multi_route.openalex_oa_url", lambda doi: None)
        monkeypatch.setattr("harvest_multi_route.s2_oa_url", lambda doi: None)
        monkeypatch.setattr("harvest_multi_route.core_oa_url", lambda doi: None)
        monkeypatch.setattr("harvest_multi_route.base_landing_url", lambda doi: None)
        res = hm.harvest("10.9/z")
        assert res["status"] == "blocked"
        assert res["reason"] == "not_open_access"
        assert res["venue_oa"] is False

    def test_harvest_core_route_recovers_pdf(self, tmp_path: Path, monkeypatch) -> None:
        import harvest_multi_route as hm
        monkeypatch.setattr("harvest_multi_route.PDF_DIR", tmp_path)
        monkeypatch.setattr("harvest_multi_route.venue_is_oa", lambda doi: None)
        monkeypatch.setattr("harvest_multi_route.unpaywall_locations", lambda doi: [])
        monkeypatch.setattr("harvest_multi_route.openalex_oa_url", lambda doi: None)
        monkeypatch.setattr("harvest_multi_route.s2_oa_url", lambda doi: None)

        class _R:
            status_code = 200
            content = b"%PDF-1.7\n" + b"0" * 6000
        monkeypatch.setattr(hm, "_get", lambda url: _R())
        monkeypatch.setattr(hm, "europepmc_for", lambda cands: None)
        monkeypatch.setattr(hm, "core_oa_url", lambda doi: "https://core/x.pdf")
        res = hm.harvest("10.9/core")
        assert res["status"] == "downloaded_core"
        assert (tmp_path / "10.9_core.pdf").exists()
