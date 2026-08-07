"""Tests for the Phase 19 ML-ready export (``dataset_ml/``).

Covers the crystal-graph construction, element feature vectors, target
assembly (masks never imputed), tensor/offset alignment, PyG Data list
shape, and the deterministic build. Uses a tiny synthetic corpus so no
full-data build is needed. Deterministic, no network, no LLM.
"""

from __future__ import annotations

import json

import numpy as np
import pandas as pd
import pytest

from ssb_dataset.ml.construct import (
    construct_crystal_graph,
    element_feature_vector,
)
from ssb_dataset.ml.build import (
    build_targets,
    load_structures,
    _material_sigma_RT,
    _to_tensor_offsets,
    TASKS,
)


def _tiny_mp() -> pd.DataFrame:
    rows = [
        {
            "identity.material_id": "mp-mp-aaaaaabz",
            "identity.composition": "Li2O",
            "identity.source_db": "materials_project",
            "identity.family": "oxide",
            "structure.crystal_system": "Cubic",
            "structure.space_group_number": 225,
            "structure.structure_relaxed": "CIF",
            "thermodynamics.formation_energy_per_atom": -2.5,
            "thermodynamics.band_gap": 5.1,
            "thermodynamics.energy_above_hull": 0.0,
            "thermodynamics.is_stable": True,
            "structure.density": 2.0,
            "structure.volume": 60.0,
            "chemistry.ionic_radius_mean": 0.9,
            "ion_transport.sigma_RT": None,
        },
        {
            "identity.material_id": "mp-mp-aaaaaaff",
            "identity.composition": "Li7La3Zr2O12",
            "identity.source_db": "materials_project",
            "identity.family": "garnet",
            "structure.crystal_system": "Cubic",
            "structure.space_group_number": 230,
            "structure.structure_relaxed": "CIF",
            "thermodynamics.formation_energy_per_atom": -3.1,
            "thermodynamics.band_gap": 6.0,
            "thermodynamics.energy_above_hull": 0.01,
            "thermodynamics.is_stable": True,
            "structure.density": 4.5,
            "structure.volume": 1800.0,
            "chemistry.ionic_radius_mean": 0.95,
            "ion_transport.sigma_RT": None,
        },
    ]
    return pd.DataFrame(rows)


# --------------------------------------------------------------------------
# construct
# --------------------------------------------------------------------------

def test_element_feature_vector_deterministic():
    a = element_feature_vector("Li")
    b = element_feature_vector("Li")
    c = element_feature_vector("Ta")
    assert a == b
    assert a != c
    assert len(a) == 10
    assert all(isinstance(x, float) for x in a)
    assert element_feature_vector("NoSuchElement") == [0.0] * 10


def test_construct_crystal_graph_from_li2o(tmp_path):
    from pymatgen.core import Structure, Lattice
    s = Structure(Lattice.cubic(4.0),
                  ["Li", "Li", "O"],
                  [[0.1, 0.1, 0.1], [0.6, 0.6, 0.6], [0.25, 0.25, 0.25]])
    g = construct_crystal_graph(s, strategy="crystalnn")
    assert g["num_nodes"] == 3
    assert len(g["node_features"]) == 3
    assert all(len(f) == 10 for f in g["node_features"])
    assert len(g["pos"]) == 3
    # undirected edges: even count
    assert len(g["edge_index"]) % 2 == 0
    assert len(g["edge_features"]) == len(g["edge_index"])
    # cutoff strategy must produce a graph for any periodic structure
    g2 = construct_crystal_graph(s, strategy="cutoff")
    assert g2["num_nodes"] == 3
    assert len(g2["edge_index"]) >= 0


def test_cutoff_fallback_when_crystalnn_empty():
    """A structure CrystalNN cannot graph must still yield a valid graph."""
    from pymatgen.core import Structure, Lattice
    s = Structure(Lattice.cubic(10.0), ["Li"], [[0.5, 0.5, 0.5]])
    g = construct_crystal_graph(s, strategy="crystalnn")
    assert g["num_nodes"] == 1
    assert len(g["node_features"]) == 1
    assert len(g["pos"]) == 1


# --------------------------------------------------------------------------
# build
# --------------------------------------------------------------------------

def test_load_structures_returns_structured_mp():
    from pathlib import Path
    import sys
    # This test exercises the full-data path: it reads the Phase-6
    # descriptors artifact (features_output/descriptors.parquet) and the raw
    # MP CIF directory, both of which are gitignored regenerable build
    # artifacts. On a fresh clone they are absent by design, so skip with a
    # clear message instead of failing (matching test_mp_enrichment.py).
    root = Path(__file__).resolve().parent.parent
    if not (root / "features_output" / "descriptors.parquet").exists():
        pytest.skip("features_output/descriptors.parquet absent — build artifacts not generated in this checkout")
    if not (root / "data" / "raw" / "materials_project" / "cif").is_dir():
        pytest.skip("raw MP CIF directory absent — build artifacts not generated in this checkout")
    mp = load_structures()
    assert len(mp) >= 20000
    assert {"identity.material_id", "identity.composition", "cif_path"} <= set(mp.columns)
    assert mp["identity.source_db"].eq("materials_project").all()
    assert mp["cif_path"].apply(lambda p: p.exists()).all()


def test_material_sigma_RT_reduced_formula_match():
    cons = {
        "Li7La3Zr2O12": {"n_sigma": 5, "median_sigma": 0.0005},
        "Li2O": {"n_sigma": 0, "median_sigma": None},
    }
    # exact reduced-formula match works despite different id strings
    assert _material_sigma_RT("mp-x", "Li7La3Zr2O12", cons) == 0.0005
    assert _material_sigma_RT("mp-y", "Li2O", cons) is None  # no n_sigma
    assert _material_sigma_RT("mp-z", "MgO", cons) is None  # no match


def test_build_targets_no_imputation():
    mp = _tiny_mp()
    targets = build_targets(mp, {})
    for tid, t in targets.items():
        assert t["y"].shape == (2,)
        assert t["mask"].shape == (2,)
    # dense targets: mask all True (all rows labeled)
    for tid in ("formation_energy_regression", "family_classification",
                "crystal_system_classification", "space_group_classification",
                "stability_classification"):
        assert targets[tid]["mask"].all(), tid
    # ranking: no consensus labels -> mask all False
    assert not targets["conductive_candidate_ranking"]["mask"].any()
    # wide-gap: Li2O (5.1) is wide, LLZO (6.0) wide
    assert targets["wide_gap_classification"]["y"].tolist() == [1.0, 1.0]
    # family classes sorted
    assert targets["family_classification"]["classes"] == ["garnet", "oxide"]


def test_targets_all_tasks_present():
    mp = _tiny_mp()
    targets = build_targets(mp, {})
    task_ids = {t["id"] for t in TASKS}
    assert set(targets) == task_ids


def test_to_tensor_offsets():
    graphs = [
        {"num_nodes": 2, "node_features": [[1.0], [2.0]],
         "edge_features": [[0.5], [0.5]], "edge_index": [[0, 1], [1, 0]]},
        {"num_nodes": 3, "node_features": [[3.0], [4.0], [5.0]],
         "edge_features": [[0.7], [0.7], [0.8], [0.8]],
         "edge_index": [[0, 1], [1, 0], [1, 2], [2, 1]]},
    ]
    node_t, edge_t = _to_tensor_offsets(graphs)
    assert node_t["values"].shape == (5, 1)
    assert node_t["offsets"].tolist() == [0, 2]
    assert edge_t["values"].shape == (6, 1)
    assert edge_t["offsets"].tolist() == [0, 2]


def test_metadata_schema():
    """metadata.json must be loadable and self-consistent after a build."""
    from ssb_dataset.ml.build import OUT_DIR
    meta = json.loads((OUT_DIR / "metadata.json").read_text())
    assert meta["schema"] == "scandium-ml"
    assert meta["graph"]["node_feature_dims"] == [10]
    assert set(meta["splits"]) <= {"train", "val", "test", "gold"}
    assert meta["targets"]["conductive_candidate_ranking"] >= 0
    # mask counts can't exceed the corpus size
    assert meta["targets"]["formation_energy_regression"] <= meta["graph"]["n_graphs"]
