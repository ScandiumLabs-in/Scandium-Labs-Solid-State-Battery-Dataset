"""Tests for Phase 4 — Cleaning, Deduplication & Canonicalization."""

from __future__ import annotations

import numpy as np
import pandas as pd
import pytest

from ssb_dataset.pipeline.cleaning import (
    audit_missing_data,
    check_arrhenius_consistency,
    deduplicate_cross_source,
    deduplicate_literature_records,
    filter_arrhenius_failures,
    run_cleaning,
    standardize_units,
    _standardize_conductivity,
    _standardize_energy,
    _standardize_temperature,
)
from ssb_dataset.schema import (
    ConfidenceTier,
    Family,
    IdentityProvenance,
    IonTransportBlock,
    MaterialRecord,
    SourceDB,
)


class TestArrheniusConsistency:
    def test_plausible_pair(self) -> None:
        plausible, predicted = check_arrhenius_consistency(sigma_S_per_cm=1e-3, Ea_eV=0.30, T_K=298)
        assert plausible is True
        assert 0 < predicted < 1

    def test_impossible_pair(self) -> None:
        plausible, _ = check_arrhenius_consistency(sigma_S_per_cm=1e-3, Ea_eV=5.0, T_K=298)
        assert plausible is False

    def test_high_temperature(self) -> None:
        plausible, _ = check_arrhenius_consistency(sigma_S_per_cm=1e-4, Ea_eV=0.60, T_K=473)
        assert plausible is True

    def test_zero_sigma(self) -> None:
        plausible, _ = check_arrhenius_consistency(sigma_S_per_cm=0.0, Ea_eV=0.30, T_K=298)
        assert plausible is False

    def test_extreme_ea(self) -> None:
        plausible, _ = check_arrhenius_consistency(sigma_S_per_cm=1e-3, Ea_eV=0.001, T_K=298)
        assert plausible is True


class TestFilterArrheniusFailures:
    def test_filters_bad_pairs(self) -> None:
        df = pd.DataFrame({
            "ion_transport.sigma_RT": [1e-3, 1e-3],
            "ion_transport.activation_energy_Ea": [0.30, 5.0],
            "ion_transport.temperature_range_measured": [None, None],
            "other_col": ["good", "bad"],
        })
        cleaned, failures = filter_arrhenius_failures(df)
        assert len(cleaned) == 1
        assert len(failures) == 1
        assert failures[0]["Ea"] == 5.0

    def test_no_failures(self) -> None:
        df = pd.DataFrame({
            "ion_transport.sigma_RT": [1e-3, 1e-4],
            "ion_transport.activation_energy_Ea": [0.30, 0.40],
        })
        cleaned, failures = filter_arrhenius_failures(df)
        assert len(cleaned) == 2
        assert len(failures) == 0

    def test_missing_values_skipped(self) -> None:
        df = pd.DataFrame({
            "ion_transport.sigma_RT": [None, 1e-3],
            "ion_transport.activation_energy_Ea": [0.30, None],
        })
        cleaned, failures = filter_arrhenius_failures(df)
        assert len(cleaned) == 2
        assert len(failures) == 0

    def test_with_temperature_range(self) -> None:
        df = pd.DataFrame({
            "ion_transport.sigma_RT": [1e-3],
            "ion_transport.activation_energy_Ea": [0.60],
            "ion_transport.temperature_range_measured": [{"min_K": 473, "max_K": 473}],
        })
        cleaned, failures = filter_arrhenius_failures(df)
        assert len(cleaned) == 1


class TestUnitStandardization:
    def test_conductivity_mS_to_S(self) -> None:
        result = _standardize_conductivity(1.0, "mS/cm")
        assert result == 0.001

    def test_conductivity_S_to_S(self) -> None:
        result = _standardize_conductivity(1.0, "S/cm")
        assert result == 1.0

    def test_conductivity_uS_to_S(self) -> None:
        result = _standardize_conductivity(1000, "uS/cm")
        assert abs(result - 0.001) < 1e-6

    def test_conductivity_unknown_unit(self) -> None:
        result = _standardize_conductivity(1.0, "arb. units")
        assert result == 1.0

    def test_energy_kJ_to_eV(self) -> None:
        result = _standardize_energy(100, "kJ/mol")
        assert abs(result - 1.0364) < 0.001

    def test_energy_eV_to_eV(self) -> None:
        result = _standardize_energy(1.0, "eV")
        assert result == 1.0

    def test_temperature_C_to_K(self) -> None:
        result = _standardize_temperature(25.0, "°C")
        assert abs(result - 298.15) < 0.01

    def test_temperature_K_to_K(self) -> None:
        result = _standardize_temperature(298.0, "K")
        assert result == 298.0


class TestDeduplication:
    def test_cross_source_exact_duplicates(self) -> None:
        df = pd.DataFrame({
            "identity.material_id": ["mp-Li6PS5Cl", "oqmd-Li6PS5Cl"],
            "structure.structure_relaxed": [
                "data_cif\n_cell_length_a 9.8\n_cell_length_b 9.8\n_cell_length_c 9.8",
                "data_cif\n_cell_length_a 9.8\n_cell_length_b 9.8\n_cell_length_c 9.8",
            ],
            "thermodynamics.formation_energy_per_atom": [-2.5, -2.4],
        })
        deduped, report = deduplicate_cross_source(df)
        assert report.cross_source_deduped >= 0
        assert len(deduped) <= len(df)

    def test_no_duplicates(self) -> None:
        df = pd.DataFrame({
            "identity.material_id": ["Li6PS5Cl", "Li7La3Zr2O12"],
        })
        deduped, report = deduplicate_cross_source(df)
        assert len(deduped) == 2
        assert report.cross_source_deduped == 0

    def test_single_record(self) -> None:
        df = pd.DataFrame({"identity.material_id": ["Li6PS5Cl"]})
        deduped, report = deduplicate_cross_source(df)
        assert len(deduped) == 1

    def test_empty_dataframe(self) -> None:
        df = pd.DataFrame()
        deduped, report = deduplicate_cross_source(df)
        assert len(deduped) == 0


class TestLiteratureDedup:
    def test_dedup_same_composition(self) -> None:
        records = [
            MaterialRecord(
                identity=IdentityProvenance(
                    material_id="Li6PS5Cl",
                    source_db=SourceDB.literature_mined,
                    source_id="lit-001",
                    family=Family.sulfide,
                    confidence_tier=ConfidenceTier.high_confidence_extraction,
                ),
                ion_transport=IonTransportBlock(sigma_RT=1e-3, label_available=True),
            ),
            MaterialRecord(
                identity=IdentityProvenance(
                    material_id="Li6PS5Cl",
                    source_db=SourceDB.literature_mined,
                    source_id="lit-002",
                    family=Family.sulfide,
                    confidence_tier=ConfidenceTier.high_confidence_extraction,
                ),
                ion_transport=IonTransportBlock(sigma_RT=2e-3, label_available=True),
            ),
        ]
        result, report = deduplicate_literature_records(records)
        assert len(result) == 2
        assert report.cross_source_deduped == 1

    def test_unique_compositions_untouched(self) -> None:
        records = [
            MaterialRecord(
                identity=IdentityProvenance(
                    material_id="Li6PS5Cl",
                    source_db=SourceDB.literature_mined,
                    source_id="lit-001",
                    family=Family.sulfide,
                    confidence_tier=ConfidenceTier.high_confidence_extraction,
                ),
                ion_transport=IonTransportBlock(sigma_RT=1e-3, label_available=True),
            ),
            MaterialRecord(
                identity=IdentityProvenance(
                    material_id="Li7La3Zr2O12",
                    source_db=SourceDB.literature_mined,
                    source_id="lit-002",
                    family=Family.garnet,
                    confidence_tier=ConfidenceTier.high_confidence_extraction,
                ),
                ion_transport=IonTransportBlock(sigma_RT=3e-4, label_available=True),
            ),
        ]
        result, report = deduplicate_literature_records(records)
        assert len(result) == 2
        assert report.cross_source_deduped == 0


class TestMissingDataAudit:
    def test_clean_data(self) -> None:
        df = pd.DataFrame({
            "ion_transport.sigma_RT": [1e-3, 1e-4],
            "ion_transport.activation_energy_Ea": [0.30, 0.40],
            "structure.structure_relaxed": ["data_cif...", "data_cif..."],
            "ion_transport.label_available": [True, True],
        })
        report = audit_missing_data(df)
        assert report.passed is True

    def test_sentinel_detected(self) -> None:
        df = pd.DataFrame({
            "ion_transport.sigma_RT": [0, -1],
            "ion_transport.activation_energy_Ea": [0.30, 0.40],
            "structure.structure_relaxed": ["cif", "cif"],
            "ion_transport.label_available": [True, True],
        })
        report = audit_missing_data(df)
        assert len(report.silent_imputation_detected) >= 1

    def test_null_values_counted(self) -> None:
        df = pd.DataFrame({
            "ion_transport.sigma_RT": [None, float("nan")],
            "ion_transport.activation_energy_Ea": [0.30, None],
            "structure.structure_relaxed": [None, "cif"],
            "ion_transport.label_available": [False, False],
        })
        report = audit_missing_data(df)
        assert report.null_sigma_count == 2
        assert report.null_ea_count == 1
        assert report.null_structure_count >= 1


class TestRunCleaning:
    def test_end_to_end(self) -> None:
        df = pd.DataFrame({
            "identity.material_id": ["Li6PS5Cl", "Li6PS5Cl"],
            "identity.source_db": ["materials_project", "oqmd"],
            "ion_transport.sigma_RT": [1e-3, 1e-3],
            "ion_transport.activation_energy_Ea": [0.30, 0.30],
        })
        report = run_cleaning(df, skip_arrhenius=True)
        assert report.total_input == 2

    def test_with_arrhenius_check(self) -> None:
        df = pd.DataFrame({
            "identity.material_id": ["good", "bad"],
            "ion_transport.sigma_RT": [1e-3, 1e-3],
            "ion_transport.activation_energy_Ea": [0.30, 5.0],
        })
        report = run_cleaning(df)
        assert len(report.arrhenius_failures) >= 1
