"""Tests for Phase 6 — Feature Engineering."""

from __future__ import annotations

import json
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

from ssb_dataset.featurization.features import (
    compute_composition_descriptors,
    compute_symmetry_descriptors,
)
from ssb_dataset.featurization.graphs import (
    PIGNetGraph,
    build_graph_batch,
    build_graph_from_structure,
)
from ssb_dataset.featurization.polymer import (
    featurize_polymer_records,
    is_graph_compatible,
    polymer_feature_columns,
)
from ssb_dataset.featurization.splits import (
    build_gold_benchmark,
    check_split_leakage,
    compute_split_key,
    create_splits,
    write_splits,
)

SAMPLE_CIF = """data_test
_cell_length_a 5.0
_cell_length_b 5.0
_cell_length_c 5.0
_cell_angle_alpha 90.0
_cell_angle_beta 90.0
_cell_angle_gamma 90.0
_symmetry_space_group_name_H-M P1
loop_
_atom_site_label
_atom_site_fract_x
_atom_site_fract_y
_atom_site_fract_z
_atom_site_occupancy
Li1 0.0 0.0 0.0 1.0
Cl1 0.5 0.5 0.5 1.0
"""


def _make_test_df() -> pd.DataFrame:
    return pd.DataFrame({
        "identity.material_id": ["Li6PS5Cl", "Li7La3Zr2O12", "LiBH4", "PEO-LiTFSI"],
        "identity.family": ["sulfide", "garnet", "hydride", "polymer_composite"],
        "ion_transport.sigma_RT": [1e-3, 3e-4, 1e-5, 1e-6],
        "ion_transport.label_available": [True, True, True, False],
        "identity.confidence_tier": ["dft_native", "dft_native", "high_confidence_extraction", "low_confidence_extraction"],
        "structure": [SAMPLE_CIF, SAMPLE_CIF, SAMPLE_CIF, ""],
        "structure.space_group": [225, 230, 62, None],
    })


# ── Composition Descriptors ─────────────────────────────────────────────────


class TestCompositionDescriptors:
    def test_computes_n_elements(self) -> None:
        df = compute_composition_descriptors(_make_test_df())
        assert "n_elements" in df.columns
        assert df["n_elements"].iloc[0] > 0

    def test_block_fractions(self) -> None:
        df = compute_composition_descriptors(_make_test_df())
        assert "frac_s_block" in df.columns
        assert "frac_p_block" in df.columns
        assert "frac_d_block" in df.columns
        assert all(0.0 <= v <= 1.0 for v in df["frac_s_block"])

    def test_elemental_property_stats(self) -> None:
        df = compute_composition_descriptors(_make_test_df())
        assert "electronegativity_mean" in df.columns
        assert "atomic_mass_mean" in df.columns
        assert "atomic_number_mean" in df.columns

    def test_empty_formula(self) -> None:
        df = pd.DataFrame({"composition": [""]})
        result = compute_composition_descriptors(df)
        assert "n_elements" in result.columns

    def test_missing_formula_col(self) -> None:
        df = pd.DataFrame({"other": [1, 2, 3]})
        result = compute_composition_descriptors(df)
        assert result is df


# ── Symmetry Descriptors ─────────────────────────────────────────────────────


class TestSymmetryDescriptors:
    def test_crystal_system_assigned(self) -> None:
        df = compute_symmetry_descriptors(_make_test_df())
        assert "crystal_system" in df.columns
        assert df["crystal_system"].iloc[0] == "Cubic"

    def test_li_fraction(self) -> None:
        df = compute_symmetry_descriptors(_make_test_df())
        assert "li_fraction" in df.columns
        assert df["li_fraction"].iloc[3] > 0  # PEO-LiTFSI has Li

    def test_has_li_sublattice(self) -> None:
        df = compute_symmetry_descriptors(_make_test_df())
        assert "has_li_sublattice" in df.columns
        assert df["has_li_sublattice"].all()

    def test_no_space_group_col(self) -> None:
        df = pd.DataFrame({"other": [1, 2, 3]})
        result = compute_symmetry_descriptors(df)
        assert "crystal_system" in result.columns


# ── Graph Building ───────────────────────────────────────────────────────────


class TestBuildGraphFromStructure:
    def test_build_from_cif(self) -> None:
        graph = build_graph_from_structure(SAMPLE_CIF)
        assert graph is not None
        assert graph.num_nodes == 2
        assert graph.num_edges > 0

    def test_node_features(self) -> None:
        graph = build_graph_from_structure(SAMPLE_CIF)
        assert graph is not None
        assert graph.node_features.shape[0] == 2

    def test_edge_features(self) -> None:
        graph = build_graph_from_structure(SAMPLE_CIF)
        assert graph is not None
        assert graph.edge_features.shape[1] > 0

    def test_global_features(self) -> None:
        graph = build_graph_from_structure(SAMPLE_CIF)
        assert graph is not None
        assert graph.global_features.shape[0] > 0

    def test_invalid_cif(self) -> None:
        graph = build_graph_from_structure("not a CIF")
        assert graph is None

    def test_to_dict(self) -> None:
        graph = build_graph_from_structure(SAMPLE_CIF)
        assert graph is not None
        d = graph.to_dict()
        assert "node_features" in d
        assert "edge_index" in d


class TestPIGNetGraph:
    def test_create(self) -> None:
        g = PIGNetGraph(
            node_features=np.array([[3], [17]], dtype=np.float32),
            edge_index=np.array([[0, 1], [1, 0]], dtype=np.int64),
            edge_features=np.array([[0.5, 0.3], [0.5, 0.3]], dtype=np.float32),
            angle_features=np.array([[0.1]], dtype=np.float32),
            global_features=np.array([2, 1000], dtype=np.float32),
            num_nodes=2,
            num_edges=2,
        )
        assert g.num_nodes == 2
        assert g.num_edges == 2

    def test_to_dict_roundtrip(self) -> None:
        g = PIGNetGraph(
            node_features=np.array([[3]], dtype=np.float32),
            edge_index=np.array([[0], [0]], dtype=np.int64),
            edge_features=np.array([[0.5]], dtype=np.float32),
            angle_features=None,
            global_features=np.array([1, 100], dtype=np.float32),
            num_nodes=1,
            num_edges=1,
            composition_key="LiCl",
        )
        d = g.to_dict()
        assert d["composition_key"] == "LiCl"
        assert d["angle_features"] is None


class TestBuildGraphBatch:
    def test_batch(self, tmp_path: Path) -> None:
        graphs = build_graph_batch(
            [SAMPLE_CIF, SAMPLE_CIF],
            composition_keys=["LiCl_1", "LiCl_2"],
            output_dir=tmp_path / "graphs",
        )
        assert len(graphs) == 2
        assert graphs[0] is not None
        assert (tmp_path / "graphs" / "LiCl_1.json").exists()

    def test_batch_with_invalid(self) -> None:
        graphs = build_graph_batch([SAMPLE_CIF, "bad_cif"])
        assert graphs[0] is not None
        assert graphs[1] is None


# ── Splits ───────────────────────────────────────────────────────────────────


class TestComputeSplitKey:
    def test_creates_group_key(self) -> None:
        df = _make_test_df()
        keys = compute_split_key(df)
        assert len(keys) == len(df)
        assert "sulfide::Li6PS5Cl" in keys.values

    def test_key_uniqueness(self) -> None:
        df = _make_test_df()
        keys = compute_split_key(df)
        assert keys.nunique() == len(df)


class TestCreateSplits:
    def test_splits_cover_all(self) -> None:
        df = _make_test_df()
        splits = create_splits(df)
        total = sum(len(s) for s in splits.values())
        assert total == len(df)

    def test_no_leakage(self) -> None:
        df = pd.DataFrame({
            "identity.material_id": ["Li6PS5Cl"] * 10 + ["Li7La3Zr2O12"] * 10,
            "identity.family": ["sulfide"] * 10 + ["garnet"] * 10,
        })
        splits = create_splits(df, split_by_group=True)
        leakage = check_split_leakage(splits)
        assert leakage["passed"]

    def test_stratified_by_family(self) -> None:
        df = pd.DataFrame({
            "identity.material_id": ["Li6PS5Cl"] * 20 + ["Li7La3Zr2O12"] * 20,
            "identity.family": ["sulfide"] * 20 + ["garnet"] * 20,
        })
        splits = create_splits(df, split_by_group=False)
        for name in ("train", "val", "test"):
            if not splits[name].empty:
                families = splits[name].get("identity.family", pd.Series())
                assert "sulfide" in families.values or "garnet" in families.values


class TestCheckSplitLeakage:
    def test_no_leakage(self) -> None:
        df = _make_test_df()
        splits = create_splits(df)
        result = check_split_leakage(splits)
        assert "passed" in result

    def test_empty_splits(self) -> None:
        result = check_split_leakage({"train": pd.DataFrame(), "val": pd.DataFrame()})
        assert result["passed"]


class TestBuildGoldBenchmark:
    def test_selects_high_confidence(self) -> None:
        df = _make_test_df()
        gold = build_gold_benchmark(df, target_size=2)
        assert len(gold) > 0

    def test_empty_when_no_eligible(self) -> None:
        df = pd.DataFrame({
            "identity.confidence_tier": ["low_confidence_extraction"],
            "ion_transport.label_available": [False],
            "ion_transport.sigma_RT": [None],
        })
        gold = build_gold_benchmark(df)
        assert gold.empty

    def test_family_balance(self) -> None:
        df = _make_test_df()
        gold = build_gold_benchmark(df, target_size=10)
        if not gold.empty and "identity.family" in gold.columns:
            assert gold["identity.family"].nunique() > 1


class TestWriteSplits:
    def test_writes_parquet(self, tmp_path: Path) -> None:
        df = _make_test_df()
        splits = create_splits(df)
        write_splits(splits, tmp_path / "splits")
        assert (tmp_path / "splits" / "train.parquet").exists()
        assert (tmp_path / "splits" / "splits_metadata.json").exists()

    def test_with_gold(self, tmp_path: Path) -> None:
        df = _make_test_df()
        gold = build_gold_benchmark(df)
        splits = create_splits(df)
        write_splits(splits, tmp_path / "gold_splits", gold_df=gold)
        assert (tmp_path / "gold_splits" / "gold.parquet").exists() or gold.empty

    def test_leakage_check_written(self, tmp_path: Path) -> None:
        df = _make_test_df()
        splits = create_splits(df)
        write_splits(splits, tmp_path / "leakage_check")
        assert (tmp_path / "leakage_check" / "leakage_check.json").exists()


# ── Polymer ──────────────────────────────────────────────────────────────────


class TestPolymerFeaturization:
    def test_marks_polymer_records(self) -> None:
        df = featurize_polymer_records(_make_test_df())
        assert "is_polymer" in df.columns
        assert bool(df["is_polymer"].iloc[3]) is True
        assert bool(df["is_polymer"].iloc[0]) is False

    def test_non_polymer_df_unmodified(self) -> None:
        df = pd.DataFrame({"identity.family": ["sulfide", "garnet", "halide"]})
        result = featurize_polymer_records(df)
        assert "is_polymer" in result.columns
        assert not result["is_polymer"].any()


class TestIsGraphCompatible:
    def test_polymer_not_compatible(self) -> None:
        assert is_graph_compatible("polymer_composite") is False

    def test_crystal_compatible(self) -> None:
        assert is_graph_compatible("sulfide") is True
        assert is_graph_compatible("garnet") is True


class TestPolymerFeatureColumns:
    def test_returns_list(self) -> None:
        cols = polymer_feature_columns()
        assert isinstance(cols, list)
        assert "is_polymer" in cols
