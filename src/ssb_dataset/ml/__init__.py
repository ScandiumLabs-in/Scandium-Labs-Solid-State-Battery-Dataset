"""ML-ready export (Phase 19): crystal graphs + targets + splits for GNN training.

The module turns the 21,528 structure-bearing Materials Project rows into a
framework-agnostic, deterministic graph dataset written to ``dataset_ml/``:

  dataset_ml/
    metadata.json          schema version, task table, feature dict, provenance
    graph.pt               list of torch_geometric.data.Data (one per material)
    node_features.pt       concat node feature tensor + per-graph offsets
    edge_features.pt       concat edge feature tensor + per-graph offsets
    targets.pt             dict: task_id -> {y, mask} aligned to material order
    splits/
      train.pt / val.pt / test.pt / gold.pt    index tensors into material order
      split_keys.json                          material_id -> split
    structures/            per-material CIF (for MatGL/MACE/ALIGNN native use)

Graph construction: CrystalNN structure graph (nodes = atoms, edges = bonds,
edge features = bond distance), with a deterministic 5 A cutoff fallback so a
structure that CrystalNN cannot resolve still yields a graph (honest, never
silently dropped). Node features are fixed per-element property vectors.

PyG, DGL, MatGL, ALIGNN and MACE all consume this layout:
  - PyG:   torch.load(graph.pt) -> list[Data]
  - DGL:   convert each Data via dgl.from_networkx / dgl.graph
  - MatGL: pymatgen Structure.from_file(CIF) + our Data (their PLEGNN needs x)
  - ALIGNN: bond/angle edges derivable from edge_index + pos
  - MACE:  pymatgen/ASE structures from dataset_ml/structures
"""

from __future__ import annotations

from .build import (
    BUILD_VERSION,
    CrystalGraphBuilder,
    build_dataset,
    build_targets,
    load_structures,
)
from .construct import construct_crystal_graph, element_feature_vector

__all__ = [
    "BUILD_VERSION",
    "CrystalGraphBuilder",
    "build_dataset",
    "build_targets",
    "construct_crystal_graph",
    "element_feature_vector",
    "load_structures",
]