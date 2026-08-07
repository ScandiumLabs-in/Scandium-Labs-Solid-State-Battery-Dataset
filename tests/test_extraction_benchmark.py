"""Phase E6 — extraction-model benchmark scoring tests (no LLM/network)."""

from __future__ import annotations

import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "scripts"))

from benchmark_extraction_model import sigma_match  # noqa: E402


class TestSigmaMatch:
    def test_exact_sigma(self) -> None:
        assert sigma_match(1.187e-3, 1.187e-3)

    def test_within_35_pct(self) -> None:
        assert sigma_match(1.3e-3, 1.187e-3)

    def test_unit_multiplier_applied(self) -> None:
        # expected mS/cm (unit_multiplier 1e-3 when stored in S/cm)
        assert sigma_match(1.187, 1.187e-3, unit_mult=1e3)

    def test_outside_tolerance_rejected(self) -> None:
        assert not sigma_match(2.0e-3, 1.187e-3, unit_mult=1.0)   # ~68% off
        assert not sigma_match(1.187e-4, 1.187e-3)                # 10x off


class TestScoreExtractionReadsSchemaFields:
    """Phase E6 — the benchmark must read the record's canonical schema fields
    (sigma_RT / activation_energy_Ea) so determinism + accuracy numbers are
    real, not empty tuples from a wrong field name."""

    def test_score_extraction_reads_sigma_and_ea(self) -> None:
        from benchmark_extraction_model import score_extraction
        from ssb_dataset.literature.extraction import extraction_record_to_material_record
        from ssb_dataset.literature.extraction import ExtractedConductivityRecord
        records = [
            extraction_record_to_material_record(
                ExtractedConductivityRecord(
                    composition="Li6PS5Cl",
                    sigma_S_per_cm=1.187e-3,
                    activation_energy_eV=0.32,
                )
            )
        ]
        gt = [
            {"composition": "Li6PS5Cl", "property": "sigma",
             "value": 1.187e-3, "unit_multiplier": 1.0},
            {"composition": "Li6PS5Cl", "property": "activation_energy",
             "value": 0.32, "unit_multiplier": 1.0},
        ]
        sc = score_extraction(records, gt)
        assert sc["sigma_accuracy"] == 1.0
        assert sc["ea_accuracy"] == 1.0
        assert sc["distinct_compositions"] == 1

    def test_mismatch_scores_zero(self) -> None:
        """A wrong extracted value must not be scored as a hit."""
        from benchmark_extraction_model import score_extraction
        from ssb_dataset.literature.extraction import extraction_record_to_material_record
        from ssb_dataset.literature.extraction import ExtractedConductivityRecord
        records = [
            extraction_record_to_material_record(
                ExtractedConductivityRecord(
                    composition="Li6PS5Cl",
                    sigma_S_per_cm=1.0e-2,  # 8x off the expected value
                    activation_energy_eV=0.32,
                )
            )
        ]
        gt = [
            {"composition": "Li6PS5Cl", "property": "sigma",
             "value": 1.187e-3, "unit_multiplier": 1.0},
        ]
        sc = score_extraction(records, gt)
        assert sc["sigma_accuracy"] == 0.0
        assert sc["sigma_expected"] == 1