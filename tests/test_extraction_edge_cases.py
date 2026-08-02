"""Tests for extraction edge cases: unit conversions, multi-composition tables, regex prepass, review detection, red-flag detector."""

from __future__ import annotations

import json
from unittest.mock import patch

import numpy as np
import pandas as pd
import pytest

from ssb_dataset.literature.extraction import (
    CONDUCTIVITY_RE,
    ExtractedConductivityRecord,
    _fix_units,
    _is_review,
    _regex_prepass,
    extraction_record_to_material_record,
    normalize_composition,
    run_llm_extraction,
)
from ssb_dataset.literature.seed import SEED_RECORDS
from ssb_dataset.pipeline.redflags import (
    TYPICAL_PREFACTOR_RANGE,
    check_arrhenius_consistency,
    check_conductivity_type_missing,
    check_duplicate_composition_values,
    check_ea_in_family_range,
    check_sigma_in_family_range,
    generate_report,
)
from ssb_dataset.schema import Family


# ── Unit Conversion Edge Cases ────────────────────────────────────────────────


class TestUnitConversion:
    def test_normalize_composition_preserves_stoichiometry(self) -> None:
        assert normalize_composition("Li1.3Al0.3Ti1.7(PO4)3") == "Li1.3Al0.3Ti1.7(PO4)3"

    def test_normalize_composition_handles_bullet(self) -> None:
        assert normalize_composition("Li6·PS5·Cl") == "Li6PS5Cl"

    def test_normalize_composition_handles_unicode_minus(self) -> None:
        assert normalize_composition("Li₀.₅La₀.₅TiO₃") == "Li₀.₅La₀.₅TiO₃"

    def test_fix_units_mS_to_S_per_cm(self) -> None:
        """If paper uses mS/cm but LLM didn't convert, _fix_units should catch it."""
        rec = ExtractedConductivityRecord(
            composition="Li6PS5Cl",
            sigma_S_per_cm=1.0,  # Should be 0.001 S/cm if paper meant 1 mS/cm
            confidence_score=0.9,
        )
        paper_text = "The ionic conductivity was 1 mS/cm at room temperature"
        fixed = _fix_units([rec], paper_text)
        assert fixed[0].sigma_S_per_cm == 0.001
        assert fixed[0].confidence_score == 0.7  # Downgraded due to uncertainty

    def test_fix_units_no_change_for_correct_values(self) -> None:
        """When paper uses S/cm, values should not be modified."""
        rec = ExtractedConductivityRecord(
            composition="Li6PS5Cl",
            sigma_S_per_cm=0.001,
            confidence_score=0.9,
        )
        paper_text = "The ionic conductivity was 0.001 S/cm"
        fixed = _fix_units([rec], paper_text)
        assert fixed[0].sigma_S_per_cm == 0.001
        assert fixed[0].confidence_score == 0.9

    def test_fix_units_no_mS_in_text_skips(self) -> None:
        """If paper text doesn't mention mS/cm, _fix_units is a no-op."""
        rec = ExtractedConductivityRecord(
            composition="Li6PS5Cl",
            sigma_S_per_cm=0.001,
            confidence_score=0.9,
        )
        paper_text = "The ionic conductivity was 0.001 S/cm"
        fixed = _fix_units([rec], paper_text)
        assert len(fixed) == 1
        assert fixed[0].sigma_S_per_cm == 0.001

    def test_fix_units_empty_records(self) -> None:
        assert _fix_units([], "conductivity 1 mS/cm") == []


# ── Regex Prepass Tests ──────────────────────────────────────────────────────


class TestRegexPrepass:
    def test_regex_catches_simple_sigma(self) -> None:
        text = "The ionic conductivity was 1.2e-3 S/cm at RT"
        candidates = _regex_prepass(text)
        assert len(candidates) >= 1
        found = [c for c in candidates if abs(c["sigma_S_per_cm"] - 0.0012) < 1e-5]
        assert len(found) >= 1

    def test_regex_catches_scientific_notation(self) -> None:
        text = "conductivity of 3.0 × 10^-4 S cm⁻¹"
        candidates = _regex_prepass(text)
        assert len(candidates) >= 1
        assert any(abs(c["sigma_S_per_cm"] - 3e-4) < 1e-6 for c in candidates)

    def test_regex_catches_exponential_notation(self) -> None:
        text = "σ = 5.2e-3 S/cm (25°C)"
        candidates = _regex_prepass(text)
        assert len(candidates) >= 1
        assert any(abs(c["sigma_S_per_cm"] - 0.0052) < 1e-5 for c in candidates)

    def test_regex_no_false_positive_on_non_conductivity(self) -> None:
        text = "The sample was 10 cm in length and weighed 5 g"
        assert _regex_prepass(text) == []

    def test_regex_empty_text(self) -> None:
        assert _regex_prepass("") == []

    def test_regex_composition_extraction(self) -> None:
        text = "Li6PS5Cl exhibited an ionic conductivity of 1.0e-3 S/cm"
        candidates = _regex_prepass(text)
        assert len(candidates) >= 1
        assert any("Li6PS5Cl" in c.get("composition", "") for c in candidates)


# ── Review Detection Tests ──────────────────────────────────────────────────


class TestReviewDetection:
    def test_detects_review_article(self) -> None:
        text = "This review article summarizes recent progress in solid-state electrolytes."
        assert _is_review(text) is True

    def test_passes_primary_research(self) -> None:
        text = "We synthesized Li6PS5Cl and measured its ionic conductivity."
        assert _is_review(text) is False

    def test_detects_mini_review(self) -> None:
        text = "A mini-review of lithium garnet electrolytes for SSBs."
        assert _is_review(text) is True

    def test_empty_text_not_review(self) -> None:
        assert _is_review("") is False


# ── Dual-Pass Extraction Logic Tests ─────────────────────────────────────────


class TestDualPassExtraction:
    def test_extraction_record_to_material_record_full(self) -> None:
        extracted = ExtractedConductivityRecord(
            composition="Li6PS5Cl",
            sigma_S_per_cm=1e-3,
            activation_energy_eV=0.30,
            temperature_K=298,
            measurement_method="EIS",
            conductivity_type="bulk",
            synthesis_route="mechanochemical",
            source_doi="10.1000/test",
            confidence_score=0.9,
        )
        rec = extraction_record_to_material_record(extracted, doi="10.1000/test", title="Test")
        assert rec.identity.family == Family.argyrodite
        assert rec.ion_transport.sigma_RT == 1e-3
        assert rec.ion_transport.activation_energy_Ea == 0.30
        assert rec.ion_transport.measurement_method == "EIS"
        assert rec.text_provenance.source_doi == "10.1000/test"

    def test_extraction_record_no_conductivity(self) -> None:
        extracted = ExtractedConductivityRecord(
            composition="Li3InCl6",
            sigma_S_per_cm=None,
            confidence_score=0.9,
        )
        rec = extraction_record_to_material_record(extracted)
        assert rec.ion_transport.label_available is False
        assert rec.ion_transport.sigma_RT is None

    def test_extraction_record_low_confidence(self) -> None:
        extracted = ExtractedConductivityRecord(
            composition="LiBH4",
            sigma_S_per_cm=1e-6,
            confidence_score=0.5,
        )
        rec = extraction_record_to_material_record(extracted)
        assert rec.identity.confidence_tier.name == "low_confidence_extraction"

    def test_extraction_record_with_temperature_range(self) -> None:
        extracted = ExtractedConductivityRecord(
            composition="Li7La3Zr2O12",
            sigma_S_per_cm=3e-4,
            temperature_range=(298, 373),
        )
        rec = extraction_record_to_material_record(extracted)
        assert rec.ion_transport.temperature_range_measured is not None
        assert rec.ion_transport.temperature_range_measured.min_K == 298
        assert rec.ion_transport.temperature_range_measured.max_K == 373

    def test_extraction_record_conductivity_type_mapping(self) -> None:
        for ct, expected in [("bulk", "bulk"), ("grain_boundary", "grain_boundary"), ("total", "total")]:
            extracted = ExtractedConductivityRecord(
                composition="Li6PS5Cl",
                sigma_S_per_cm=1e-3,
                conductivity_type=ct,
            )
            rec = extraction_record_to_material_record(extracted)
            assert rec.ion_transport.conductivity_type is not None
            assert rec.ion_transport.conductivity_type.value == expected


# ── LLM Extraction Output Parsing ───────────────────────────────────────────


class TestLLMOutputParsing:
    def test_parse_code_fenced_json(self) -> None:
        """LLM sometimes wraps JSON in ```json ... ``` fences."""
        mock_response_text = "```json\n[{\"composition\": \"Li6PS5Cl\", \"sigma_S_per_cm\": 0.001}]\n```"

        class MockResponse:
            status_code = 200
            def raise_for_status(self):
                pass
            def json(self):
                return {"choices": [{"message": {"content": mock_response_text}}]}

        import httpx
        orig = httpx.post
        try:
            httpx.post = lambda *a, **kw: MockResponse()
            results = run_llm_extraction("test", api_key="fake")
            assert len(results) == 1
            assert results[0].sigma_S_per_cm == 0.001
        finally:
            httpx.post = orig

    def test_parse_with_trailing_comma(self) -> None:
        """LLM sometimes produces trailing commas which break strict JSON."""
        mock = '[{"composition": "Li6PS5Cl", "sigma_S_per_cm": 0.001,}]'

        class MockResponse:
            status_code = 200
            def raise_for_status(self):
                pass
            def json(self):
                return {"choices": [{"message": {"content": mock}}]}

        import httpx
        orig = httpx.post
        try:
            httpx.post = lambda *a, **kw: MockResponse()
            results = run_llm_extraction("test", api_key="fake")
            assert len(results) == 1
            assert results[0].sigma_S_per_cm == 0.001
        finally:
            httpx.post = orig

    def test_parse_empty_array(self) -> None:
        class MockResponse:
            status_code = 200
            def raise_for_status(self):
                pass
            def json(self):
                return {"choices": [{"message": {"content": "[]"}}]}

        import httpx
        orig = httpx.post
        try:
            httpx.post = lambda *a, **kw: MockResponse()
            assert run_llm_extraction("test", api_key="fake") == []
        finally:
            httpx.post = orig

    def test_parse_multiple_records(self) -> None:
        mock = json.dumps([
            {"composition": "Li6PS5Cl", "sigma_S_per_cm": 0.001},
            {"composition": "Li7La3Zr2O12", "sigma_S_per_cm": 0.0003},
        ])

        class MockResponse:
            status_code = 200
            def raise_for_status(self):
                pass
            def json(self):
                return {"choices": [{"message": {"content": mock}}]}

        import httpx
        orig = httpx.post
        try:
            httpx.post = lambda *a, **kw: MockResponse()
            results = run_llm_extraction("test", api_key="fake")
            assert len(results) == 2
            assert results[0].composition == "Li6PS5Cl"
            assert results[1].composition == "Li7La3Zr2O12"
        finally:
            httpx.post = orig

    def test_parse_with_sigma_vs_T(self) -> None:
        mock = json.dumps([
            {
                "composition": "LiBH4",
                "sigma_S_per_cm": 1e-6,
                "sigma_vs_T": [[373, 1e-5], [473, 1e-4]],
                "activation_energy_eV": 0.60,
            }
        ])

        class MockResponse:
            status_code = 200
            def raise_for_status(self):
                pass
            def json(self):
                return {"choices": [{"message": {"content": mock}}]}

        import httpx
        orig = httpx.post
        try:
            httpx.post = lambda *a, **kw: MockResponse()
            results = run_llm_extraction("test", api_key="fake")
            assert len(results) == 1
            assert len(results[0].sigma_vs_T) == 2
            assert results[0].sigma_vs_T[0] == (373.0, 1e-5)
        finally:
            httpx.post = orig


# ── Red-Flag Detector Tests ──────────────────────────────────────────────────


class TestRedFlagArrheniusConsistency:
    def test_typical_superionic_passes(self) -> None:
        """Li6PS5Cl: sigma=1e-3, Ea=0.30 -> sigma0 ~ 1.5e4 (in range 10^1-10^5)."""
        flagged, _ = check_arrhenius_consistency(1e-3, 0.30)
        assert flagged is False

    def test_too_low_prefactor_flags(self) -> None:
        """sigma=1e-7, Ea=0.60 -> sigma0 ~ 1.2e2 (OK).
        But sigma=1e-12, Ea=0.60 -> sigma0 ~ 1.2e-3 (too low)."""
        flagged, _ = check_arrhenius_consistency(1e-12, 0.60)
        assert flagged is True

    def test_too_high_prefactor_flags(self) -> None:
        """sigma=1e-3, Ea=0.05 -> sigma0 ~ 6.8 (actually fine at RT).
        sigma=10, Ea=0.80 -> sigma0 ~ 1e18 (too high)."""
        flagged, _ = check_arrhenius_consistency(10.0, 0.80)
        assert flagged is True

    def test_none_sigma_no_flag(self) -> None:
        flagged, _ = check_arrhenius_consistency(None, 0.30)
        assert flagged is False

    def test_none_ea_no_flag(self) -> None:
        flagged, _ = check_arrhenius_consistency(1e-3, None)
        assert flagged is False

    def test_zero_sigma_no_flag(self) -> None:
        flagged, _ = check_arrhenius_consistency(0.0, 0.30)
        assert flagged is False

    def test_polymer_composite_skipped(self) -> None:
        """Polymer composites follow VTF kinetics, not Arrhenius."""
        flagged, _ = check_arrhenius_consistency(1e-5, 0.80, family="polymer_composite")
        assert flagged is False


class TestRedFlagFamilyRanges:
    def test_sigma_in_range(self) -> None:
        flagged, _ = check_sigma_in_family_range(1e-3, "sulfide")
        assert flagged is False

    def test_sigma_out_of_range(self) -> None:
        flagged, _ = check_sigma_in_family_range(1.0, "sulfide")
        assert flagged is True

    def test_sigma_none_no_flag(self) -> None:
        flagged, _ = check_sigma_in_family_range(None, "sulfide")
        assert flagged is False

    def test_ea_in_range(self) -> None:
        flagged, _ = check_ea_in_family_range(0.30, "sulfide")
        assert flagged is False

    def test_ea_out_of_range(self) -> None:
        flagged, _ = check_ea_in_family_range(2.0, "sulfide")
        assert flagged is True

    def test_none_ea_no_flag(self) -> None:
        flagged, _ = check_ea_in_family_range(None, "sulfide")
        assert flagged is False

    def test_unknown_family_skipped(self) -> None:
        flagged, _ = check_sigma_in_family_range(1.0, "unknown")
        assert flagged is False


class TestRedFlagDuplicateCompositions:
    def test_duplicate_different_values(self) -> None:
        df = pd.DataFrame({
            "material_id": ["a", "b"],
            "sigma_RT": [1e-3, 1e-5],
            "composition": ["Li6PS5Cl", "Li6PS5Cl"],
        })
        flags = check_duplicate_composition_values(df, "sigma_RT", "composition", None)
        assert len(flags) == 1

    def test_duplicate_similar_values_no_flag(self) -> None:
        df = pd.DataFrame({
            "material_id": ["a", "b"],
            "sigma_RT": [1e-3, 2e-3],
            "composition": ["Li6PS5Cl", "Li6PS5Cl"],
        })
        flags = check_duplicate_composition_values(df, "sigma_RT", "composition", None)
        assert len(flags) == 0

    def test_no_duplicates(self) -> None:
        df = pd.DataFrame({
            "material_id": ["a", "b"],
            "sigma_RT": [1e-3, 1e-3],
            "composition": ["Li6PS5Cl", "Li7La3Zr2O12"],
        })
        flags = check_duplicate_composition_values(df, "sigma_RT", "composition", None)
        assert len(flags) == 0

    def test_empty_sigma_no_flag(self) -> None:
        df = pd.DataFrame({
            "material_id": ["a", "b"],
            "sigma_RT": [None, None],
            "composition": ["Li6PS5Cl", "Li6PS5Cl"],
        })
        flags = check_duplicate_composition_values(df, "sigma_RT", "composition", None)
        assert len(flags) == 0


class TestRedFlagMissingConductivityType:
    def test_missing_on_garnet_flags(self) -> None:
        row = pd.Series({"family": "garnet", "conductivity_type": None, "sigma_RT": 1e-3})
        flags = check_conductivity_type_missing(row, "test-1", "family", "conductivity_type", "sigma_RT")
        assert len(flags) == 1
        assert flags[0].flag_type == "missing_conductivity_type"

    def test_present_on_garnet_no_flag(self) -> None:
        row = pd.Series({"family": "garnet", "conductivity_type": "bulk", "sigma_RT": 1e-3})
        flags = check_conductivity_type_missing(row, "test-1", "family", "conductivity_type", "sigma_RT")
        assert len(flags) == 0

    def test_non_bulk_gb_family_skipped(self) -> None:
        row = pd.Series({"family": "sulfide", "conductivity_type": None, "sigma_RT": 1e-3})
        flags = check_conductivity_type_missing(row, "test-1", "family", "conductivity_type", "sigma_RT")
        assert len(flags) == 0


class TestRedFlagFullReport:
    def test_report_on_clean_data(self) -> None:
        df = pd.DataFrame({
            "material_id": ["mp-1", "mp-2"],
            "family": ["sulfide", "garnet"],
            "sigma_RT": [1e-3, 3e-4],
            "activation_energy_Ea": [0.30, 0.35],
            "composition": ["Li6PS5Cl", "Li7La3Zr2O12"],
            "conductivity_type": ["bulk", "bulk"],
        })
        report = generate_report(df)
        assert report.total_records == 2
        assert report.total_flags == 0

    def test_report_on_flagged_data(self) -> None:
        df = pd.DataFrame({
            "material_id": ["mp-1", "mp-2"],
            "family": ["sulfide", "sulfide"],
            "sigma_RT": [1e-3, 1e-12],
            "activation_energy_Ea": [0.30, 0.60],
            "composition": ["Li6PS5Cl", "Li6PS5Cl"],
            "conductivity_type": ["bulk", None],
        })
        report = generate_report(df)
        assert report.total_flags >= 1

    def test_report_empty_dataframe(self) -> None:
        df = pd.DataFrame()
        report = generate_report(df)
        assert report.total_records == 0
        assert report.total_flags == 0


# ── Seed Set Verification Tests ──────────────────────────────────────────────


class TestSeedSetEdgeCases:
    def test_all_seed_compositions_classify_correctly(self) -> None:
        from ssb_dataset.sources.classifier import classify_family
        for r in SEED_RECORDS:
            family = classify_family(composition=r["composition"])
            assert family == r["family"], (
                f"{r['composition']}: classified as {family}, expected {r['family']}"
            )

    def test_seed_sigma_values_consistent_with_arrhenius(self) -> None:
        for r in SEED_RECORDS:
            sigma = r["sigma_S_per_cm"]
            ea = r.get("activation_energy_eV")
            family = r["family"].value if hasattr(r["family"], "value") else str(r["family"])
            if sigma is not None and ea is not None:
                flagged, _ = check_arrhenius_consistency(sigma, ea, family=family)
                assert flagged is False, (
                    f"{r['composition']}: σ={sigma}, Ea={ea} fails Arrhenius check"
                )

    def test_seed_family_ranges(self) -> None:
        for r in SEED_RECORDS:
            family = r["family"].value if hasattr(r["family"], "value") else str(r["family"])
            sigma = r["sigma_S_per_cm"]
            if sigma is not None:
                flagged, _ = check_sigma_in_family_range(sigma, family)
                assert flagged is False, (
                    f"{r['composition']}: σ={sigma} out of range for {family}"
                )
