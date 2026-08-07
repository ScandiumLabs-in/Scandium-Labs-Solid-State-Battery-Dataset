# ML-Ready Export (Phase 19, v1.1.0)

The dataset's first framework-ready GNN artifact: 21,528 crystal graphs built
from the Materials Project structures in the canonical dataset, with benchmark
targets and leakage-checked splits, in a layout consumable by PyTorch
Geometric, DGL, MatGL, ALIGNN and MACE.

Built by `scripts/build_ml_dataset.py` (no LLM calls, deterministic, resumable
via an on-disk per-material graph cache). Writes `dataset_ml/`.

## Layout

```
dataset_ml/
├── metadata.json          # schema version, task table, feature dict, provenance
├── graph.pt               # list[torch_geometric.data.Data] — one per material
├── node_features.pt       # dict: values (N×10) + per-graph offsets (N×1)
├── edge_features.pt       # dict: values (E×1) + per-graph offsets (N×1)
├── targets.pt             # dict: task_id -> {y, mask, n_classes, classes}
├── splits/
│   ├── train.pt           # index tensors into the graph.pt material order
│   ├── val.pt
│   ├── test.pt
│   └── gold.pt            # empty today (gold rows carry no MP structure)
└── structures/            # 21,528 CIFs for MatGL/MACE/ALIGNN native ingestion
```

## Graph construction

- **Primary**: CrystalNN structure graph (nodes = atoms, edges = bonds).
- **Fallback**: deterministic 5 Å periodic cutoff neighbor graph when CrystalNN
  cannot resolve a structure. A material is never silently dropped.
- **Node features** (10-dim, fixed per element): atomic number, group, row,
  electronegativity, Mendeleev number, atomic mass, electron affinity, first
  ionization energy, valence, common oxidation state.
- **Edge features** (1-dim): bond distance in Å. Edges are undirected (both
  directions emitted). `pos` (cartesian site coordinates) is stored on each
  Data so ALIGNN's angle edges can be derived.

## Targets

Twelve tasks mirroring the v0.8.0 benchmark registry (`src/ssb_dataset/
benchmarks/tasks.py`). Each is a `{y, mask}` pair aligned to the `graph.pt`
material order — **missing labels are masked, never imputed**:

| Task | Type | n labeled (of 21,528) |
|------|------|------------------------|
| formation_energy_regression | regression | 21,528 |
| band_gap_regression | regression | 21,528 |
| energy_above_hull_regression | regression | 21,528 |
| density_regression | regression | 21,528 |
| volume_regression | regression | 21,528 |
| ionic_radius_regression | regression | 21,528 |
| stability_classification | classification | 21,528 |
| wide_gap_classification | classification | 15,286 (non-zero band gap) |
| family_classification | classification | 21,528 |
| crystal_system_classification | classification | 21,528 |
| space_group_classification | classification | 21,528 |
| **conductive_candidate_ranking** | **ranking (log10 σ)** | **237** |

### The ranking label: honest and sparse

σ_RT labels live on the 183 literature-verified rows, which carry no MP
structure. For the graph export, the ranking target is populated only where a
**structure** exists AND the material's reduced formula matches a consensus-DB
group with a median σ (`src/ssb_dataset/ml/build.py::_material_sigma_RT`).
Result: **237 materials** with a consensus material-level σ (e.g. Li7La3Zr2O12,
Li6PS5Cl). This is the honest intersection of "has a crystal graph" and "has a
measured label" — growing it is a Phase 11 (data expansion) task, not a code
task.

## Splits

Reuses the Phase 6 leakage-checked assignment (composition-family-grouped, so
polymorphs/doped variants never straddle splits). Verified disjoint and
covering the full corpus:

- train **15,064** · val **3,236** · test **3,228** · gold 0 (disjoint, union = 21,528)

`gold.pt` is empty because gold rows (literature materials) have no MP
structures; the gold conductivity subset remains served by the composition-
descriptor path (`features_output/gold.parquet`, n=165).

## Framework usage

```python
import torch

# PyG (native)
from torch_geometric.data import Batch
graphs = torch.load("dataset_ml/graph.pt", weights_only=False)
targets = torch.load("dataset_ml/targets.pt", weights_only=False)
train_idx = torch.load("dataset_ml/splits/train.pt", weights_only=False)
batch = Batch.from_data_list([graphs[i] for i in train_idx[:64]])
y = targets["formation_energy_regression"]["y"][train_idx[:64]]
```

- **DGL**: build from `node_features.pt` + each `Data.edge_index` via
  `dgl.graph()`.
- **MatGL**: load the CIF from `dataset_ml/structures/` with pymatgen, then use
  `Data.x` for the PLEGNN input.
- **ALIGNN**: bond edges from `edge_index`; derive angle edges from `pos`.
- **MACE**: `ase.io.read("dataset_ml/structures/<cif>")` — MACE consumes
  structures directly.

## Determinism & reproducibility

- Graph construction is a pure function of the CIF; `--jobs N` only affects
  wall-clock, never results (assembly reads the same on-disk cache).
- `metadata.json` records the source snapshot paths, build version, and counts.
- `scripts/release.py` gate **`ml_export_built`** (config: `ml_min_graphs`,
  `ml_min_dense_targets`) blocks release if the export is missing or shallow.

## Known limits

- Node/edge features are raw element/distance values, not learned embeddings —
  models are expected to apply their own normalization (standard GNN practice).
- `wide_gap_classification` excludes zero-band-gap rows (they are metals, not
  wide-gap), per the benchmark registry.
- The ranking task has 237 labels today; a trainable graph-based conductivity
  model needs the Phase 11 experimental corpus.
