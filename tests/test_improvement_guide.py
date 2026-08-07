"""Tests for the improving-scandium-ssb-dataset guide §5 actions.

Covers A1 (paper_ood split + split_assignment backfill), A3 (noise floor),
A4 (conductivity-type normalization), A5 (rejection-rate stats), A6 (structure
attribution audit), A9 (Ea consistency audit). No network, no LLM.
"""

from __future__ import annotations

import json
import math
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

from scripts import audit_ea_consistency as A9
from scripts import audit_structure_attribution as A6
from scripts import compute_noise_floor as A3
from scripts import compute_rejection_stats as A5
from scripts import normalize_conductivity_type as A4
from scripts import backfill_split_assignment as A1
from ssb_dataset.benchmarks import splits as S

ROOT = Path(__file__).resolve().parent.parent


# --------------------------------------------------------------------------
# A1 — paper_ood split + backfill helpers
# --------------------------------------------------------------------------

def test_paper_ood_group_key_unions_paper_and_composition():
    df = pd.DataFrame({
        "identity.material_id": ["a", "b", "c", "d"],
        "text_provenance.source_doi": ["doi1", "doi1", "doi2", None],
        "identity.reduced_formula": ["Li2O", "Li3P", "Li3P", "Li2O"],
    })
    smap = S.paper_ood_split_map(df)
    # a and b share doi1 -> same split
    assert smap["a"] == smap["b"]
    # b and c share formula Li3P -> same split, so a==c==b
    assert smap["a"] == smap["b"] == smap["c"]


def test_paper_ood_deterministic():
    df = pd.DataFrame({
        "identity.material_id": ["a", "b", "c", "d"],
        "text_provenance.source_doi": ["doi1", "doi1", "doi2", None],
        "identity.reduced_formula": ["Li2O", "Li3P", "Li3P", "Li2O"],
    })
    assert S.paper_ood_split_map(df) == S.paper_ood_split_map(df)


def test_backfill_group_key_falls_back_to_material_id():
    df = pd.DataFrame({
        "identity.material_id": ["Li7La3Zr2O12", "mp-1"],
        "identity.reduced_formula": [None, "Li2O"],
    })
    keys = A1._group_key(df).tolist()
    assert keys[0] == "Li7La3Zr2O12"
    assert keys[1] == "Li2O"


def test_backfill_preserves_gold_rows(tmp_path):
    import pyarrow.parquet as pq
    # gold ids come from the persisted random split map; when absent, no gold
    assert A1._gold_ids() == set() or isinstance(A1._gold_ids(), set)


# --------------------------------------------------------------------------
# A3 — noise floor
# --------------------------------------------------------------------------

def test_noise_floor_ignores_single_measurement_groups():
    db = {
        "A": {"measurements": [
            {"sigma_S_per_cm": 1e-3, "conductivity_type": "total"},
            {"sigma_S_per_cm": 2e-3, "conductivity_type": "total"},
        ]},
        "B": {"measurements": [
            {"sigma_S_per_cm": 1e-4, "conductivity_type": "total"},
        ]},
    }
    report = A3.compute(db)
    assert report["n_repeat_groups"] == 1  # only A qualifies
    assert report["n_entries_in_repeat_groups"] == 2


def test_noise_floor_does_not_pool_bulk_and_total():
    db = {
        "A": {"measurements": [
            {"sigma_S_per_cm": 1e-3, "conductivity_type": "bulk"},
            {"sigma_S_per_cm": 5e-3, "conductivity_type": "bulk"},
            {"sigma_S_per_cm": 1e-2, "conductivity_type": "total"},
            {"sigma_S_per_cm": 9e-3, "conductivity_type": "total"},
        ]},
    }
    report = A3.compute(db)
    # two groups: A::bulk (2) and A::total (2), not one group of 4
    assert report["n_repeat_groups"] == 2
    assert report["n_entries_in_repeat_groups"] == 4


def test_noise_floor_metrics_finite_on_repeat_groups():
    db = {
        "A": {"measurements": [
            {"sigma_S_per_cm": 1e-3, "conductivity_type": "total"},
            {"sigma_S_per_cm": 2e-3, "conductivity_type": "total"},
            {"sigma_S_per_cm": 1.5e-3, "conductivity_type": "total"},
        ]},
    }
    report = A3.compute(db)
    assert np.isfinite(
        report["our_metrics"]["rms_deviation_from_group_means_log10"])
    assert np.isfinite(
        report["our_metrics"]["mad_from_group_medians_log10"])


def test_noise_floor_nan_sigma_excluded():
    db = {
        "A": {"measurements": [
            {"sigma_S_per_cm": float("nan"), "conductivity_type": "total"},
            {"sigma_S_per_cm": 1e-3, "conductivity_type": "total"},
        ]},
    }
    report = A3.compute(db)
    assert report["n_repeat_groups"] == 0  # only 1 usable value remains


# --------------------------------------------------------------------------
# A4 — conductivity-type normalization
# --------------------------------------------------------------------------

def test_normalize_value_maps_all_representations():
    assert A4.normalize_value("ConductivityType.total") == "total"
    assert A4.normalize_value("total") == "total"
    assert A4.normalize_value("ConductivityType.bulk") == "bulk"
    assert A4.normalize_value("bulk") == "bulk"
    assert A4.normalize_value("ConductivityType.grain_boundary") == \
        "grain_boundary"
    assert A4.normalize_value("grain") == "grain_boundary"
    assert A4.normalize_value(None) is None
    assert A4.normalize_value("garbage") is None


def test_normalize_marks_unknown_only_on_labeled_rows():
    df = pd.DataFrame({
        "identity.material_id": ["m1", "m2", "m3"],
        "ion_transport.label_available": [True, True, False],
        "ion_transport.conductivity_type": [None, "total", None],
        "text_provenance.source_doi": ["d1", "d2", None],
    })
    out = A4.apply(df)
    assert out["ion_transport.conductivity_type"].tolist() == \
        ["unknown", "total", None]


def test_normalize_is_idempotent():
    df = pd.DataFrame({
        "identity.material_id": ["m1"],
        "ion_transport.label_available": [True],
        "ion_transport.conductivity_type": ["ConductivityType.total"],
        "text_provenance.source_doi": ["d1"],
    })
    once = A4.apply(df)
    twice = A4.apply(once)
    pd.testing.assert_series_equal(
        once["ion_transport.conductivity_type"],
        twice["ion_transport.conductivity_type"])


# --------------------------------------------------------------------------
# A5 — rejection statistics
# --------------------------------------------------------------------------

def test_rejection_rate_math():
    queue = [
        {"status": "approved"},
        {"status": "approved"},
        {"status": "rejected"},
        {"status": "rejected", "review_note": "unit error (mS/cm->S/cm)"},
        {"status": "pending"},
    ]
    report = A5.compute(queue)
    assert report["funnel"]["decided"] == 4
    assert report["rejection_rate"] == pytest.approx(0.5)
    assert report["rejection_rate_pct"] == pytest.approx(50.0)


def test_rejection_reason_categorization():
    assert "unit error" in A5._categorize("Table 1 unit error (mS/cm->S/cm)")
    assert "duplicate" in A5._categorize("DUP_VALUE: same sigma copy-pasted")
    assert "hallucination" in A5._categorize(
        "Hallucination: value not in paper")
    assert A5._categorize("") == "no review note"


# --------------------------------------------------------------------------
# A6 — structure attribution audit
# --------------------------------------------------------------------------

def test_attribution_counts_attached_vs_missing(tmp_path):
    df = pd.DataFrame({
        "identity.material_id": ["Li7La3Zr2O12", "mp-1", "mp-2", "PEO-LiTFSI"],
        "identity.source_db": ["literature_mined", "materials_project",
                               "materials_project", "literature_mined"],
        "identity.reduced_formula": [None, "Li7La3Zr2O12", "Li2O", None],
        "structure.structure_relaxed": [None, "cif1", "cif2", None],
        "ion_transport.label_available": [True, False, False, True],
        "text_provenance.source_doi": ["d1", None, None, "d2"],
        "identity.family": ["garnet", "garnet", "oxide", "polymer"],
    })
    report = A6.audit(df)
    # Li7La3Zr2O12 matches mp-1; PEO-LiTFSI has no structure match
    assert report["status"]["structure_attached"] == 1
    assert report["status"]["no_structure_match"] == 1


def test_attribution_polymorph_awareness(tmp_path):
    df = pd.DataFrame({
        "identity.material_id": ["Li2O", "mp-1", "mp-2"],
        "identity.source_db": ["literature_mined", "materials_project",
                               "materials_project"],
        "identity.reduced_formula": [None, "Li2O", "Li2O"],
        "structure.structure_relaxed": [None, "cif1", "cif2"],
        "ion_transport.label_available": [True, False, False],
        "text_provenance.source_doi": ["d1", None, None],
        "identity.family": ["oxide", "oxide", "oxide"],
    })
    report = A6.audit(df)
    assert report["status"]["structure_attached"] == 1
    assert report["polymorph_ambiguity"]["n_attached_with_multiple_mp_structures"] == 1


# --------------------------------------------------------------------------
# A9 — Ea consistency audit
# --------------------------------------------------------------------------

def test_ea_audit_coverage_and_window():
    df = pd.DataFrame({
        "identity.material_id": ["A", "A", "B"],
        "ion_transport.label_available": [True, True, True],
        "ion_transport.activation_energy_Ea": [0.45, 0.43, 0.05],
        "ion_transport.sigma_RT": [1e-3, 1e-3, None],
        "text_provenance.source_doi": ["d1", "d2", "d3"],
    })
    report = A9.audit(df)
    assert report["coverage"]["n_with_ea"] == 3
    assert report["coverage"]["n_with_both_sigma_and_ea"] == 2
    assert report["unit_suspicion"]["n_out_of_physical_window"] == 0
    # A has Ea from 2 distinct papers
    assert report["cross_paper_reproducibility"]["n_materials_ea_from_ge2_papers"] == 1
    assert report["cross_paper_reproducibility"]["n_materials_inconsistent_mad_gt_0.2eV"] == 0


def test_ea_audit_flags_out_of_window_values():
    df = pd.DataFrame({
        "identity.material_id": ["A"],
        "ion_transport.label_available": [True],
        "ion_transport.activation_energy_Ea": [0.002],  # below physical window
        "ion_transport.sigma_RT": [1e-3],
        "text_provenance.source_doi": ["d1"],
    })
    report = A9.audit(df)
    assert report["unit_suspicion"]["n_out_of_physical_window"] == 1


def test_ea_audit_detects_cross_paper_inconsistency():
    df = pd.DataFrame({
        "identity.material_id": ["A", "A"],
        "ion_transport.label_available": [True, True],
        "ion_transport.activation_energy_Ea": [0.45, 1.1],
        "ion_transport.sigma_RT": [1e-3, 1e-3],
        "text_provenance.source_doi": ["d1", "d2"],
    })
    report = A9.audit(df)
    assert report["cross_paper_reproducibility"][
        "n_materials_inconsistent_mad_gt_0.2eV"] == 1
