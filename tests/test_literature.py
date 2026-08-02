"""Tests for Phase 3 — Literature mining: discovery, extraction, linking, seed set."""

from __future__ import annotations

import json

import pytest

from ssb_dataset.literature.discovery import PaperCandidate, compute_relevance, triage_candidates
from ssb_dataset.literature.extraction import (
    ExtractedConductivityRecord,
    extraction_record_to_material_record,
    normalize_composition,
    run_llm_extraction,
)
from ssb_dataset.literature.linking import (
    MatchResult,
    StructureIndex,
    _formula_similarity,
    _normalize_formula,
    _parse_formula_dict,
    find_unmatched_compositions,
    match_composition,
)
from ssb_dataset.literature.seed import SEED_RECORDS, get_seed_records, validate_extraction_against_seed
from ssb_dataset.schema import ConfidenceTier, ExtractionMethod, Family, MaterialRecord, SourceDB


class TestNormalizeComposition:
    def test_whitespace_removed(self) -> None:
        assert normalize_composition("  Li6 PS5 Cl ") == "Li6PS5Cl"

    def test_dot_separator_removed(self) -> None:
        assert normalize_composition("Li7·La3·Zr2·O12") == "Li7La3Zr2O12"

    def test_dash_normalized(self) -> None:
        assert normalize_composition("Li1.3−Al0.3−Ti1.7(PO4)3") == "Li1.3-Al0.3-Ti1.7(PO4)3"


class TestComputeRelevance:
    def test_high_relevance(self) -> None:
        score = compute_relevance(
            "Lithium ionic conductivity in LLZO garnet",
            "We report the ionic conductivity and activation energy of Li7La3Zr2O12 "
            "measured by AC impedance spectroscopy at room temperature.",
        )
        assert score >= 0.3

    def test_low_relevance(self) -> None:
        score = compute_relevance(
            "Synthesis of metal-organic frameworks",
            "We synthesized a new MOF structure for gas storage applications.",
        )
        assert score < 0.2


class TestTriageCandidates:
    def test_empty_input(self) -> None:
        assert triage_candidates([]) == []

    def test_filters_missing_doi(self) -> None:
        raw = [{"title": "Test", "abstract": ""}]
        assert triage_candidates(raw) == []

    def test_filters_low_relevance(self) -> None:
        raw = [
            {
                "externalIds": {"DOI": "10.1000/test"},
                "title": "Unrelated chemistry paper",
                "abstract": "We studied organic synthesis methods.",
            }
        ]
        result = triage_candidates(raw)
        assert len(result) == 0

    def test_high_relevance_passes(self) -> None:
        raw = [
            {
                "externalIds": {"DOI": "10.1000/test"},
                "title": "Ionic conductivity of Li6PS5Cl solid electrolyte",
                "abstract": "AC impedance spectroscopy measurements of lithium ionic conductivity.",
            }
        ]
        result = triage_candidates(raw)
        assert len(result) == 1
        assert result[0].doi == "10.1000/test"

    def test_sorted_by_relevance(self) -> None:
        raw = [
            {
                "externalIds": {"DOI": "10.1000/low"},
                "title": "Battery materials low relevance",
                "abstract": "electrochemical impedance of lithium cells",
            },
            {
                "externalIds": {"DOI": "10.1000/high"},
                "title": "Ionic conductivity of solid electrolytes at high temperature",
                "abstract": "Li-ion conductivity and activation energy measured by impedance spectroscopy",
            },
        ]
        result = triage_candidates(raw)
        assert len(result) == 2
        assert result[0].doi == "10.1000/high"


class TestPaperCandidate:
    def test_dataclass(self) -> None:
        p = PaperCandidate(doi="10.1000/test", title="Test", abstract="Abstract text", relevance_score=0.8)
        assert p.doi == "10.1000/test"
        assert p.relevance_score == 0.8
        assert p.family_tags == []


class TestExtractionRecord:
    def test_extraction_record_creation(self) -> None:
        rec = ExtractedConductivityRecord(
            composition="Li6PS5Cl",
            sigma_S_per_cm=1e-3,
            activation_energy_eV=0.30,
            temperature_K=298,
            measurement_method="EIS",
            source_doi="10.1000/test",
            confidence_score=0.9,
        )
        assert rec.composition == "Li6PS5Cl"
        assert rec.sigma_S_per_cm == 1e-3

    def test_to_material_record(self) -> None:
        extracted = ExtractedConductivityRecord(
            composition="Li7La3Zr2O12",
            sigma_S_per_cm=3e-4,
            activation_energy_eV=0.35,
            temperature_K=298,
            measurement_method="AC impedance spectroscopy",
        )
        rec = extraction_record_to_material_record(extracted, doi="10.1000/test", title="LLZO conductivity")
        assert rec.identity.source_db == SourceDB.literature_mined
        assert rec.identity.family == Family.garnet
        assert rec.ion_transport.sigma_RT == 3e-4
        assert rec.ion_transport.label_available is True
        assert rec.text_provenance.extraction_method == ExtractionMethod.llm_extraction

    def test_to_material_record_no_conductivity(self) -> None:
        extracted = ExtractedConductivityRecord(
            composition="Li3InCl6",
            sigma_S_per_cm=None,
            confidence_score=0.9,
        )
        rec = extraction_record_to_material_record(extracted)
        assert rec.ion_transport.label_available is False
        assert rec.ion_transport.sigma_RT is None
        assert rec.identity.confidence_tier == ConfidenceTier.high_confidence_extraction

    def test_to_material_record_with_T_curve(self) -> None:
        extracted = ExtractedConductivityRecord(
            composition="LiBH4",
            sigma_vs_T=[(373, 1e-4), (473, 1e-3)],
            activation_energy_eV=0.60,
        )
        rec = extraction_record_to_material_record(extracted)
        assert len(rec.ion_transport.sigma_vs_T_curve) == 2
        assert rec.ion_transport.sigma_vs_T_curve[0].temperature_K == 373.0


class TestLLMExtraction:
    def test_empty_text(self) -> None:
        results = run_llm_extraction("", api_key=None)
        assert results == []

    def test_no_llm_key_returns_empty(self) -> None:
        results = run_llm_extraction("Some paper text", api_key=None)
        assert results == []

    def test_llm_extraction_output(self) -> None:
        json_output = json.dumps([
            {"composition": "Li6PS5Cl", "sigma_S_per_cm": 0.001, "activation_energy_eV": 0.3, "temperature_K": 298},
        ])

        class MockResponse:
            status_code = 200

            def raise_for_status(self):
                pass

            def json(self):
                return {"choices": [{"message": {"content": json_output}}]}

        original_post = None
        import httpx
        original_post = httpx.post
        try:
            httpx.post = lambda *a, **kw: MockResponse()
            results = run_llm_extraction("test text", api_key="fake-key")
            assert len(results) == 1
            assert results[0].sigma_S_per_cm == 0.001
        finally:
            httpx.post = original_post

    def test_llm_extraction_empty_response(self) -> None:
        class MockResponse:
            status_code = 200

            def raise_for_status(self):
                pass

            def json(self):
                return {"choices": [{"message": {"content": "[]"}}]}

        import httpx
        original_post = httpx.post
        try:
            httpx.post = lambda *a, **kw: MockResponse()
            results = run_llm_extraction("test", api_key="fake-key")
            assert results == []
        finally:
            httpx.post = original_post


class TestLinking:
    def test_normalize_formula(self) -> None:
        assert "Li6PS5Cl" in _normalize_formula("Li6·PS5·Cl")
        assert "Li7La3Zr2O12" in _normalize_formula("Li7La3Zr2O12")

    def test_parse_formula_dict(self) -> None:
        d = _parse_formula_dict("Li6PS5Cl")
        assert "Li" in d
        assert "P" in d
        assert "S" in d
        assert d["Li"] > 0

    def test_parse_formula_dict_invalid(self) -> None:
        d = _parse_formula_dict("not-a-formula")
        assert d == {}

    def test_formula_similarity_identical(self) -> None:
        d1 = {"Li": 6, "P": 1, "S": 5, "Cl": 1}
        d2 = {"Li": 6, "P": 1, "S": 5, "Cl": 1}
        assert abs(_formula_similarity(d1, d2) - 1.0) < 1e-6

    def test_formula_similarity_different(self) -> None:
        d1 = {"Li": 6, "P": 1, "S": 5, "Cl": 1}
        d2 = {"C": 1, "O": 1}
        assert _formula_similarity(d1, d2) < 0.5

    def test_structure_index(self) -> None:
        idx = StructureIndex()
        idx.add_entry("mp-1234", "Li6PS5Cl", "materials_project")
        idx.add_entry("mp-5678", "Li7La3Zr2O12", "materials_project")
        assert len(idx.entries) == 2
        assert idx.entries[0]["material_id"] == "mp-1234"

    def test_match_composition_exact(self) -> None:
        idx = StructureIndex()
        idx.add_entry("mp-1234", "Li6PS5Cl", "materials_project")
        result = match_composition("Li6PS5Cl", idx)
        assert result.is_exact is True
        assert result.matched_material_id == "mp-1234"

    def test_match_composition_no_match(self) -> None:
        idx = StructureIndex()
        idx.add_entry("mp-1234", "Li7La3Zr2O12", "materials_project")
        result = match_composition("LiBH4", idx)
        assert result.matched_material_id is None

    def test_match_composition_partial(self) -> None:
        idx = StructureIndex()
        idx.add_entry("mp-1234", "Li6PS5Cl", "materials_project")
        result = match_composition("Li6PS5Cl0.9Br0.1", idx)
        assert result.match_score > 0.9

    def test_find_unmatched_compositions(self) -> None:
        idx = StructureIndex()
        idx.add_entry("mp-1234", "Li6PS5Cl", "materials_project")

        class MockRecord:
            def __init__(self, comp: str):
                self.composition = comp

        records = [MockRecord("Li6PS5Cl"), MockRecord("LiBH4"), MockRecord("Li3InCl6")]
        unmatched = find_unmatched_compositions(records, idx)
        comps = [u[0] for u in unmatched]
        assert "Li6PS5Cl" not in comps
        assert "LiBH4" in comps
        assert "Li3InCl6" in comps


class TestSeedSet:
    def test_seed_records_count(self) -> None:
        assert len(SEED_RECORDS) >= 10

    def test_seed_covers_all_families(self) -> None:
        families = {r["family"] for r in SEED_RECORDS}
        assert Family.sulfide in families
        assert Family.garnet in families
        assert Family.halide in families

    def test_all_seed_have_doi(self) -> None:
        for r in SEED_RECORDS:
            assert r["doi"], f"Missing DOI for {r['composition']}"

    def test_all_seed_have_conductivity(self) -> None:
        for r in SEED_RECORDS:
            assert r["sigma_S_per_cm"] is not None, f"Missing conductivity for {r['composition']}"

    def test_get_seed_records(self) -> None:
        records = get_seed_records()
        assert len(records) == len(SEED_RECORDS)
        for r in records:
            assert isinstance(r, MaterialRecord)
            assert r.identity.confidence_tier == ConfidenceTier.verified_human
            assert r.ion_transport.label_available is True

    def test_seed_sigma_range_plausible(self) -> None:
        for r in SEED_RECORDS:
            sigma = r["sigma_S_per_cm"]
            assert 1e-8 <= sigma <= 1e-1, f"Implausible sigma for {r['composition']}: {sigma}"

    def test_seed_ea_range_plausible(self) -> None:
        for r in SEED_RECORDS:
            ea = r.get("activation_energy_eV")
            if ea is not None:
                assert 0.1 <= ea <= 1.0, f"Implausible Ea for {r['composition']}: {ea}"

    def test_validate_extraction_against_seed_empty(self) -> None:
        result = validate_extraction_against_seed([])
        assert result["total_seed"] == len(SEED_RECORDS)
        assert result["matched"] == 0

    def test_validate_extraction_against_seed_perfect(self) -> None:
        seed_records = get_seed_records()
        result = validate_extraction_against_seed(seed_records, tolerance_factor=2.0)
        assert result["matched"] > 0
        assert result["sigma_accuracy"] > 0


class TestSeedRecordFamilies:
    @pytest.mark.parametrize("record", SEED_RECORDS, ids=lambda r: r["composition"])
    def test_seed_record_classification(self, record: dict) -> None:
        from ssb_dataset.sources.classifier import classify_family
        result = classify_family(composition=record["composition"])
        assert result == record["family"], (
            f"Classifier: {record['composition']} -> {result}, expected {record['family']}"
        )
