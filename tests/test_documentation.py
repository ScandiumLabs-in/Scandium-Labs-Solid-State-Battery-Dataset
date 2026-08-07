"""Tests for Phase 8 — Documentation."""

from __future__ import annotations

from pathlib import Path

import pandas as pd
import pytest

from ssb_dataset.documentation import (
    generate_citation_cff,
    generate_confidence_tier_doc,
    generate_datasheet,
    generate_family_readme,
    update_changelog,
)
from ssb_dataset.documentation.generator import FAMILY_DESCRIPTIONS, FAMILY_NAMES


def _make_test_df() -> pd.DataFrame:
    return pd.DataFrame({
        "identity.material_id": ["Li6PS5Cl", "Li7La3Zr2O12"],
        "identity.family": ["sulfide", "garnet"],
        "identity.source_db": ["materials_project", "jarvis"],
        "identity.confidence_tier": ["dft_native", "dft_native"],
        "ion_transport.sigma_RT": [1e-3, 3e-4],
        "ion_transport.activation_energy_Ea": [0.30, 0.40],
    })


# ── Datasheet ────────────────────────────────────────────────────────────────


class TestGenerateDatasheet:
    def test_creates_markdown(self, tmp_path: Path) -> None:
        df = _make_test_df()
        path = tmp_path / "datasheet.md"
        result = generate_datasheet(df, path)
        assert path.exists()
        assert "# Datasheet:" in result
        assert "Total records:" in result

    def test_includes_family_counts(self, tmp_path: Path) -> None:
        df = _make_test_df()
        path = tmp_path / "datasheet.md"
        result = generate_datasheet(df, path)
        assert "sulfide" in result
        assert "garnet" in result

    def test_label_count_handles_object_dtype_bool(self, tmp_path: Path) -> None:
        # label_available arrives as object dtype (True/False/None mix) from
        # the parquet pipeline; the datasheet must count True labels, not fall
        # back to the sigma_RT count (regression: 183 -> 166 on v1.9.0 docs).
        df = _make_test_df()
        df["ion_transport.label_available"] = pd.Series(
            [True, True], dtype=object)
        path = tmp_path / "datasheet.md"
        result = generate_datasheet(df, path)
        assert "**Records with verified experimental transport label:** 2" in result
        assert "**Records with raw σ_RT value:** 2" in result

    def test_label_count_with_none_is_still_true_count(self, tmp_path: Path) -> None:
        df = _make_test_df()
        df["ion_transport.label_available"] = pd.Series(
            [True, None], dtype=object)
        path = tmp_path / "datasheet.md"
        result = generate_datasheet(df, path)
        assert "**Records with verified experimental transport label:** 1" in result


# ── Per-Family README ────────────────────────────────────────────────────────


class TestGenerateFamilyReadme:
    def test_creates_readme(self, tmp_path: Path) -> None:
        path = tmp_path / "sulfide.md"
        result = generate_family_readme("sulfide", n_records=50, n_with_sigma=30, output_path=path)
        assert path.exists()
        assert "Sulfide" in result
        assert "50" in result

    def test_polymer_note(self, tmp_path: Path) -> None:
        path = tmp_path / "polymer.md"
        result = generate_family_readme("polymer_composite", n_records=10, n_with_sigma=5, output_path=path)
        assert "parallel featurization" in result

    def test_sparse_family_note(self, tmp_path: Path) -> None:
        path = tmp_path / "hydride.md"
        result = generate_family_readme("hydride", n_records=5, n_with_sigma=2, output_path=path)
        assert "sparse coverage" in result


# ── Confidence Tier Doc ──────────────────────────────────────────────────────


class TestGenerateConfidenceTierDoc:
    def test_creates_doc(self, tmp_path: Path) -> None:
        path = tmp_path / "confidence.md"
        result = generate_confidence_tier_doc(path)
        assert path.exists()
        assert "verified_human" in result
        assert "dft_native" in result
        assert "Confidence Tier System" in result


# ── CITATION.cff ─────────────────────────────────────────────────────────────


class TestGenerateCitationCff:
    def test_creates_cff(self, tmp_path: Path) -> None:
        path = tmp_path / "CITATION.cff"
        result = generate_citation_cff(path)
        assert path.exists()
        assert "cff-version:" in result
        assert "Scandium Labs" in result
        assert "CC-BY-4.0" in result


# ── CHANGELOG ────────────────────────────────────────────────────────────────


class TestUpdateChangelog:
    def test_creates_entry(self, tmp_path: Path) -> None:
        path = tmp_path / "CHANGELOG.md"
        result = update_changelog(path)
        assert path.exists()
        assert "v0.1.0" in result
        assert "Phase 0" in result
        assert "Phase 8" in result


# ── Module Constants ─────────────────────────────────────────────────────────


class TestFamilyConstants:
    def test_all_families_defined(self) -> None:
        assert len(FAMILY_NAMES) == 11
        assert all(f in FAMILY_NAMES for f in [
            "sulfide", "oxide", "garnet", "perovskite", "nasicon",
            "halide", "argyrodite", "hydride", "borohydride",
            "antiperovskite", "polymer_composite",
        ])

    def test_all_families_described(self) -> None:
        assert len(FAMILY_DESCRIPTIONS) == 11
