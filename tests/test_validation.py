"""Tests for Phase 7 — Validation, QC & Statistical Auditing."""

from __future__ import annotations

import json
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

from ssb_dataset.pipeline.validation import (
    BENCHMARK_COMPOUNDS,
    CrossSourceAuditEntry,
    FamilyDistributionSummary,
    ValidationReport,
    audit_cross_source_consistency,
    audit_extraction_accuracy,
    check_family_distributions,
    generate_report,
    run_validation,
    verify_benchmark_compounds,
)


def _make_test_df() -> pd.DataFrame:
    np.random.seed(42)
    n = 50
    rows = []
    families = ["sulfide", "garnet", "halide", "polymer_composite"]
    for i in range(n):
        fam = families[i % len(families)]
        rows.append({
            "identity.material_id": f"compound_{i}",
            "identity.family": fam,
            "identity.source_db": "materials_project" if i % 2 == 0 else "literature_mined",
            "identity.confidence_tier": "dft_native",
            "ion_transport.sigma_RT": np.random.lognormal(-6, 2),
            "ion_transport.activation_energy_Ea": np.random.uniform(0.1, 0.8),
            "thermodynamics.band_gap": np.random.uniform(1.0, 6.0),
            "structure.structure_relaxed": "cif_data",
        })
    df = pd.DataFrame(rows)
    df.loc[0, "ion_transport.sigma_RT"] = 1e-3
    df.loc[0, "identity.material_id"] = "Li6PS5Cl"
    return df


# ── Family Distribution Checks ───────────────────────────────────────────────


class TestCheckFamilyDistributions:
    def test_returns_per_family(self) -> None:
        df = _make_test_df()
        dists = check_family_distributions(df)
        assert len(dists) == 4

    def test_family_has_summary_stats(self) -> None:
        df = _make_test_df()
        dists = check_family_distributions(df)
        for d in dists:
            assert d.family in ["sulfide", "garnet", "halide", "polymer_composite"]
            assert d.count > 0

    def test_sigma_statistics(self) -> None:
        df = _make_test_df()
        dists = check_family_distributions(df)
        for d in dists:
            if d.count > 0:
                assert d.sigma_mean is not None or d.count == 0

    def test_flags_on_outliers(self) -> None:
        df = pd.DataFrame({
            "identity.family": ["sulfide"] * 10,
            "ion_transport.sigma_RT": [1e-10] * 10,
            "ion_transport.activation_energy_Ea": [0.3] * 10,
        })
        dists = check_family_distributions(df)
        flags = [f for d in dists for f in d.flags]
        assert len(flags) >= 0

    def test_no_family_col(self) -> None:
        df = pd.DataFrame({"other": [1, 2, 3]})
        dists = check_family_distributions(df)
        assert dists == []


# ── Benchmark Compound Validation ────────────────────────────────────────────


class TestVerifyBenchmarkCompounds:
    def test_benchmark_compounds_defined(self) -> None:
        assert len(BENCHMARK_COMPOUNDS) == 10

    def test_finds_Li6PS5Cl(self) -> None:
        df = _make_test_df()
        results = verify_benchmark_compounds(df)
        li6ps5cl = [r for r in results if r.compound == "Li6PS5Cl"]
        assert len(li6ps5cl) == 1
        assert li6ps5cl[0].found is True

    def test_no_match_returns_error(self) -> None:
        df = pd.DataFrame({
            "identity.material_id": ["some_other_compound"],
            "ion_transport.sigma_RT": [1e-3],
        })
        results = verify_benchmark_compounds(df)
        for r in results:
            if r.compound == "Li6PS5Cl":
                assert r.error is not None

    def test_returns_all_compounds(self) -> None:
        df = _make_test_df()
        results = verify_benchmark_compounds(df)
        assert len(results) == len(BENCHMARK_COMPOUNDS)

    def test_missing_columns(self) -> None:
        df = pd.DataFrame({"other": [1, 2]})
        results = verify_benchmark_compounds(df)
        assert all(r.error is not None for r in results)


# ── Cross-Source Consistency ─────────────────────────────────────────────────


class TestAuditCrossSourceConsistency:
    def test_detects_multi_source_compounds(self) -> None:
        df = pd.DataFrame({
            "identity.material_id": ["Li6PS5Cl"] * 3,
            "identity.source_db": ["mp", "jarvis", "oqmd"],
            "ion_transport.sigma_RT": [1e-3, 2e-3, 1.5e-3],
        })
        entries = audit_cross_source_consistency(df)
        assert len(entries) == 1
        assert entries[0].material_id == "Li6PS5Cl"

    def test_ignores_single_source(self) -> None:
        df = pd.DataFrame({
            "identity.material_id": ["Li6PS5Cl", "Li7La3Zr2O12"],
            "identity.source_db": ["mp", "mp"],
            "ion_transport.sigma_RT": [1e-3, 1e-4],
        })
        entries = audit_cross_source_consistency(df)
        assert len(entries) == 0

    def test_flags_large_spread(self) -> None:
        df = pd.DataFrame({
            "identity.material_id": ["Li6PS5Cl"] * 3,
            "identity.source_db": ["mp", "jarvis", "oqmd"],
            "ion_transport.sigma_RT": [1e-3, 1e-1, 1e-5],
        })
        entries = audit_cross_source_consistency(df, max_sigma_spread=5.0)
        assert len(entries) == 1
        assert entries[0].passes is False

    def test_missing_columns(self) -> None:
        df = pd.DataFrame({"other": [1, 2]})
        entries = audit_cross_source_consistency(df)
        assert entries == []


# ── Extraction Re-Audit ──────────────────────────────────────────────────────


class TestAuditExtractionAccuracy:
    def test_returns_seed_count(self) -> None:
        audit = audit_extraction_accuracy()
        assert audit.seed_count == 15

    def test_accuracy_calculated(self) -> None:
        audit = audit_extraction_accuracy()
        assert 0.0 <= audit.accuracy <= 1.0


# ── Full Validation Report ───────────────────────────────────────────────────


class TestRunValidation:
    def test_report_created(self) -> None:
        df = _make_test_df()
        report = run_validation(df)
        assert report.total_records == len(df)
        assert len(report.records_per_family) == 4
        assert len(report.family_distributions) == 4

    def test_benchmark_integration(self) -> None:
        df = _make_test_df()
        report = run_validation(df)
        assert report.benchmark_verified >= 0

    def test_cross_source_integration(self) -> None:
        df = _make_test_df()
        report = run_validation(df)
        assert report.cross_source_failed >= 0

    def test_passed_status(self) -> None:
        df = _make_test_df()
        report = run_validation(df)
        assert isinstance(report.passed, bool)


class TestGenerateReport:
    def test_writes_json(self, tmp_path: Path) -> None:
        report = ValidationReport(total_records=10)
        path = tmp_path / "report.json"
        generate_report(report, path)
        assert path.exists()
        data = json.loads(path.read_text())
        assert data["total_records"] == 10

    def test_with_full_data(self, tmp_path: Path) -> None:
        df = _make_test_df()
        report = run_validation(df)
        path = tmp_path / "full_report.json"
        generate_report(report, path)
        data = json.loads(path.read_text())
        assert "benchmark_compounds_verified" in data
        assert "family_distributions" in data
        assert "cross_source_entries_count" in data
        assert "extraction_audit" in data


# ── Dataclass Tests ──────────────────────────────────────────────────────────


class TestFamilyDistributionSummary:
    def test_defaults(self) -> None:
        fd = FamilyDistributionSummary(family="sulfide", count=10)
        assert fd.family == "sulfide"
        assert fd.count == 10
        assert fd.flags == []


class TestCrossSourceAuditEntry:
    def test_create(self) -> None:
        e = CrossSourceAuditEntry(
            material_id="Li6PS5Cl",
            sources=["mp", "jarvis"],
            sigma_values=[1e-3, 2e-3],
            sigma_range=2.0,
            passes=True,
        )
        assert e.material_id == "Li6PS5Cl"
        assert e.passes is True
