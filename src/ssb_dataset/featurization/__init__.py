"""Featurization package — feature engineering for ML-ready dataset.

Modules:
  - graphs: PIGNet V2-compatible graph construction from CIF structures
  - features: Composition (Magpie-style) + symmetry descriptors
  - splits: Train/val/test splits with leakage prevention + gold benchmark
  - polymer: Family 8 polymer/composite parallel featurization path
"""

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

__all__ = [
    "compute_composition_descriptors",
    "compute_symmetry_descriptors",
    "PIGNetGraph",
    "build_graph_from_structure",
    "build_graph_batch",
    "featurize_polymer_records",
    "is_graph_compatible",
    "polymer_feature_columns",
    "create_splits",
    "write_splits",
    "check_split_leakage",
    "compute_split_key",
    "build_gold_benchmark",
]
