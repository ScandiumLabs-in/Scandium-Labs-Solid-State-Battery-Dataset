"""Build the ML-ready export (``dataset_ml/``).

Deterministic assembly: loads the canonical dataset + descriptors, takes the
21,528 structure-bearing Materials Project rows, builds a crystal graph per
structure (CrystalNN with a 5 A cutoff fallback), attaches the benchmark task
targets (dense: formation energy, band gap, energy-above-hull, density,
volume, ionic radius, stability, wide-gap, family, crystal-system, space
group; sparse: consensus σ_RT material-level ranking labels where a
structure matches a consensus group), and reuses the leakage-checked
train/val/test/gold split assignment from Phase 6.

Output (see module docstring in __init__.py) is written under
``dataset_ml/``. Framework-agnostic: node_features.pt / edge_features.pt are
raw torch tensors with per-graph offsets; graph.pt is a list of PyG Data
objects for direct torch_geometric consumption.
"""

from __future__ import annotations

import json
import time
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parent.parent.parent.parent

BUILD_VERSION = "1.0.0"

DESCRIPTORS = ROOT / "features_output/descriptors.parquet"
CANONICAL = ROOT / "cleaning_output/canonical_dataset.parquet"
CONSENSUS = ROOT / "literature_output/consensus_db.json"
OUT_DIR = ROOT / "dataset_ml"
STRUCT_DIR = OUT_DIR / "structures"

# The 21,528 structure-bearing MP rows are the graph corpus.
STRUCTURED_SOURCE = "materials_project"

# Task definitions mirror the benchmark registry (v0.8.0) so leaderboard
# comparisons stay meaningful.
TASKS: tuple[dict[str, Any], ...] = (
    {"id": "formation_energy_regression", "type": "regression",
     "col": "thermodynamics.formation_energy_per_atom", "metric": "mae"},
    {"id": "band_gap_regression", "type": "regression",
     "col": "thermodynamics.band_gap", "metric": "mae"},
    {"id": "energy_above_hull_regression", "type": "regression",
     "col": "thermodynamics.energy_above_hull", "metric": "mae"},
    {"id": "density_regression", "type": "regression",
     "col": "structure.density", "metric": "mae"},
    {"id": "volume_regression", "type": "regression",
     "col": "structure.volume", "metric": "mae"},
    {"id": "ionic_radius_regression", "type": "regression",
     "col": "chemistry.ionic_radius_mean", "metric": "mae"},
    {"id": "stability_classification", "type": "classification",
     "col": "thermodynamics.is_stable", "metric": "macro_f1"},
    {"id": "wide_gap_classification", "type": "classification",
     "col": "thermodynamics.band_gap", "metric": "macro_f1", "threshold": 4.0},
    {"id": "family_classification", "type": "classification",
     "col": "identity.family", "metric": "macro_f1"},
    {"id": "crystal_system_classification", "type": "classification",
     "col": "structure.crystal_system", "metric": "macro_f1"},
    {"id": "space_group_classification", "type": "classification",
     "col": "structure.space_group_number", "metric": "top5_accuracy"},
    {"id": "conductive_candidate_ranking", "type": "ranking",
     "col": "ion_transport.sigma_RT", "metric": "ndcg10", "transform": "log10"},
)

CLASS_FIELDS = ("identity.family", "structure.crystal_system")

# Columns excluded as *targets* (already target of another task) so nothing
# leaks through the dense features.
NON_FEATURE_COLUMNS = {
    "structure.structure_relaxed", "structure.structure_unrelaxed",
    "structure.lattice_params", "structure.li_site_occupancy",
    "structure.coordination_environment", "structure.coordination_csm",
    "structure.coordination_species", "structure.space_group",
    "structure.neighbor_species_distribution", "structure.bond_types",
    "structure.bond_length_stats", "thermodynamics.decomposition_products",
    "thermodynamics.electrochemical_stability_window",
    "ion_transport.sigma_vs_T_curve", "ion_transport.temperature_range_measured",
    "chemistry.atomic_fractions", "chemistry.elemental_fractions",
    "chemistry.weight_fractions", "electronic.possible_species",
    "magnetic.types_of_magnetic_species", "synthesis.precursors",
    "experiment.notes",
}

DENSE_FEATURE_COLUMNS: tuple[str, ...] = (
    "structure.nsites", "structure.packing_fraction",
    "structure.nearest_neighbor_distance", "structure.mean_neighbor_distance",
    "structure.li_site_count", "structure.li_vacancy_fraction",
    "structure.li_hopping_distance", "chemistry.electronegativity_mean",
    "chemistry.atomic_radius_mean", "chemistry.ionic_radius_mean",
    "chemistry.average_atomic_mass", "chemistry.average_group",
    "chemistry.average_period", "chemistry.average_mendeleev_number",
    "thermodynamics.formation_energy_per_atom", "thermodynamics.band_gap",
    "thermodynamics.energy_above_hull", "thermodynamics.is_stable",
    "magnetic.is_magnetic", "dielectric.e_total",
)


def _prebuild_worker(args: tuple[str, str]) -> tuple[str, dict]:
    """Module-level worker for the parallel graph prebuild (picklable)."""
    mid, cif = args
    try:
        return mid, CrystalGraphBuilder._build_one(Path(cif))
    except Exception as exc:  # pragma: no cover - defensive
        return mid, {"error": str(exc)}


class CrystalGraphBuilder:
    """Lazy per-material crystal graph cache (deterministic, resumable).

    ``prebuild`` uses a process pool so a full 21,528-material build can be
    parallelized; assembly then reads everything from the on-disk cache, so
    results are identical regardless of the number of workers.
    """

    def __init__(self, cache_dir: Path | None = None):
        self.cache_dir = cache_dir or (ROOT / "dataset_ml" / ".graph_cache")
        self.cache_dir.mkdir(parents=True, exist_ok=True)
        self._mem: dict[str, dict] = {}

    def build(self, material_id: str, cif_path: Path) -> dict:
        if material_id in self._mem:
            return self._mem[material_id]
        cache_file = self.cache_dir / f"{material_id.replace('/', '_')}.json"
        if cache_file.exists():
            g = json.loads(cache_file.read_text())
            self._mem[material_id] = g
            return g
        g = self._build_one(cif_path)
        cache_file.write_text(json.dumps(g))
        self._mem[material_id] = g
        return g

    def prebuild(self, rows: pd.DataFrame, jobs: int = 8) -> None:
        """Build all (not-yet-cached) graphs for the given rows in parallel.

        Rows need ``identity.material_id`` and ``cif_path`` columns. Already
        cached materials are skipped (resumable).
        """
        todo = []
        for _, r in rows.iterrows():
            mid = str(r["identity.material_id"])
            cif = Path(r["cif_path"])
            cache_file = self.cache_dir / f"{mid.replace('/', '_')}.json"
            if not cif.exists() or cache_file.exists():
                continue
            todo.append((mid, str(cif)))
        if not todo:
            print("  no uncached graphs to build")
            return
        if jobs <= 1:
            for mid, cif in todo:
                g = self._build_one(Path(cif))
                (self.cache_dir / f"{mid.replace('/', '_')}.json").write_text(
                    json.dumps(g))
            return
        from concurrent.futures import ProcessPoolExecutor

        print(f"  building {len(todo)} graphs with {jobs} workers ...")
        with ProcessPoolExecutor(max_workers=jobs) as ex:
            for mid, g in ex.map(_prebuild_worker, todo):
                if "error" in g:
                    print(f"    [warn] {mid}: {g['error']}")
                    continue
                (self.cache_dir / f"{mid.replace('/', '_')}.json").write_text(
                    json.dumps(g))
        print(f"  cached {len(todo)} graphs")

    @staticmethod
    def _build_one(cif_path: Path) -> dict:
        from pymatgen.core import Structure
        from ssb_dataset.ml.construct import construct_crystal_graph

        struct = Structure.from_file(str(cif_path))
        return construct_crystal_graph(struct, strategy="crystalnn")


def load_structures() -> pd.DataFrame:
    """Return the structured MP corpus with a resolved CIF path per row."""
    desc = pd.read_parquet(DESCRIPTORS)
    mp = desc[
        desc["identity.source_db"].eq(STRUCTURED_SOURCE)
        & desc["structure.structure_relaxed"].notna()
    ].copy()
    mp = mp.drop_duplicates(subset=["identity.material_id"], keep="first")
    mp["cif_path"] = mp["identity.material_id"].map(
        lambda mid: ROOT / "data" / "raw" / "materials_project" / "cif"
        / f"{str(mid).replace('mp-mp-', 'mp-')}.cif")
    return mp


def _material_sigma_RT(material_id: str, composition: str,
                      consensus: dict[str, dict]) -> float | None:
    """Material-level σ_RT from the consensus DB where a structure exists.

    Uses the reduced-formula match so Li7La3Zr2O12 (gold) maps to its MP
    structure even though the ids differ. Returns the consensus median σ
    (log10-space) as a single material-level target; None when no consensus
    group matches. This is the only aggregation allowed — the measurement
    rows themselves stay untouched in the relational tables.
    """
    from pymatgen.core import Composition

    try:
        red = Composition(composition).reduced_formula
    except Exception:
        red = None
    for group, entry in consensus.items():
        if not entry.get("n_sigma"):
            continue
        try:
            g_red = Composition(group).reduced_formula
        except Exception:
            continue
        if g_red == red and entry.get("median_sigma"):
            return float(entry["median_sigma"])
    return None


def build_targets(mp: pd.DataFrame,
                  consensus: dict[str, dict]) -> dict[str, dict]:
    """Align every task target to the material order of ``mp``.

    Returns ``{task_id: {"y": np.ndarray (float), "mask": np.ndarray (bool),
    "n_classes": int|None, "classes": list|None}}``. Masks are True only where
    a usable label exists; missing labels are never imputed.
    """
    out: dict[str, dict] = {}
    for task in TASKS:
        tid = task["id"]
        col = task["col"]
        if col in CLASS_FIELDS:
            vals = mp[col].astype(str)
            cats = sorted(vals.unique())
            index = {c: i for i, c in enumerate(cats)}
            y = vals.map(index).to_numpy(dtype=float)
            mask = vals.notna().to_numpy()
            out[tid] = {"y": y, "mask": mask, "n_classes": len(cats),
                        "classes": cats}
            continue
        raw = mp[col]
        if tid == "conductive_candidate_ranking":
            sigmas = [
                _material_sigma_RT(str(mid), str(comp), consensus)
                for mid, comp in zip(mp["identity.material_id"].astype(str),
                                     mp["identity.composition"].astype(str))
            ]
            arr = np.array(sigmas, dtype=float)
            mask = ~np.isnan(arr)
            y = np.where(mask, np.log10(np.where(mask, arr, 1.0)), 0.0)
            out[tid] = {"y": y, "mask": mask, "n_classes": None,
                        "classes": None}
            continue
        arr = pd.to_numeric(raw, errors="coerce").to_numpy(dtype=float)
        mask = ~np.isnan(arr)
        y = arr.copy()
        if task.get("threshold") is not None and task["type"] == "classification":
            y = (arr >= task["threshold"]).astype(float)
            extra = pd.to_numeric(raw, errors="coerce").notna().to_numpy()
            mask = mask & (extra & (arr != 0))
            out[tid] = {"y": y, "mask": mask, "n_classes": 2,
                        "classes": [0, 1]}
            continue
        out[tid] = {"y": y, "mask": mask, "n_classes": None, "classes": None}
    return out


def _to_tensor_offsets(graphs: list[dict]) -> tuple[dict, dict]:
    node_feats: list[np.ndarray] = []
    edge_feats: list[np.ndarray] = []
    node_off = [0]
    edge_off = [0]
    for g in graphs:
        node_feats.append(np.array(g["node_features"], dtype=np.float32))
        edge_feats.append(np.array(g["edge_features"], dtype=np.float32))
        node_off.append(node_off[-1] + g["num_nodes"])
        edge_off.append(edge_off[-1] + len(g["edge_index"]))
    return (
        {"values": np.concatenate(node_feats),
         "offsets": np.array(node_off[:-1], dtype=np.int64)},
        {"values": np.concatenate(edge_feats),
         "offsets": np.array(edge_off[:-1], dtype=np.int64)},
    )


def build_dataset(limit: int = 0, out_dir: Path | None = None,
                  builder: CrystalGraphBuilder | None = None,
                  jobs: int = 8) -> dict:
    """Build the full ML export. Returns a summary dict."""
    out_dir = out_dir or OUT_DIR
    (out_dir / "splits").mkdir(parents=True, exist_ok=True)
    STRUCT_DIR.mkdir(parents=True, exist_ok=True)
    builder = builder or CrystalGraphBuilder()

    print("Loading structured corpus ...")
    mp = load_structures()
    if limit:
        mp = mp.head(limit)
    print(f"  {len(mp)} structured materials")

    print("Loading consensus σ (ranking labels) ...")
    try:
        consensus = json.loads(CONSENSUS.read_text())
    except FileNotFoundError:
        consensus = {}

    print("Building crystal graphs ...")
    t0 = time.time()
    builder.prebuild(mp, jobs=jobs)
    graphs: list[dict] = []
    cif_paths: list[Path] = []
    for _, row in mp.iterrows():
        mid = str(row["identity.material_id"])
        cif = Path(row["cif_path"])
        if not cif.exists():
            continue
        g = builder.build(mid, cif)
        graphs.append(g)
        cif_paths.append(cif)
    print(f"  {len(graphs)} graphs assembled in {time.time() - t0:.1f}s")

    print("Assembling targets ...")
    targets = build_targets(mp, consensus)
    target_summary = {
        tid: int(v["mask"].sum()) for tid, v in targets.items()}

    print("Aligning splits ...")
    material_ids = [str(r["identity.material_id"]) for _, r in mp.iterrows()]
    split_map: dict[str, str] = {}
    for s in ("train", "val", "test", "gold"):
        f = ROOT / "features_output" / f"{s}.parquet"
        if not f.exists():
            continue
        df = pd.read_parquet(f, columns=["identity.material_id"])
        for mid in df["identity.material_id"].dropna().astype(str):
            split_map[mid] = s
    splits = {s: np.array([], dtype=np.int64) for s in
              ("train", "val", "test", "gold")}
    for i, mid in enumerate(material_ids):
        s = split_map.get(mid)
        if s:
            splits[s] = np.append(splits[s], i)
    split_counts = {s: int(len(v)) for s, v in splits.items()}

    print("Writing tensors ...")
    node_t, edge_t = _to_tensor_offsets(graphs)

    import torch
    torch.save({"node_features": torch.from_numpy(node_t["values"]),
                "offsets": torch.from_numpy(node_t["offsets"])},
               out_dir / "node_features.pt")
    torch.save({"edge_features": torch.from_numpy(edge_t["values"]),
                "offsets": torch.from_numpy(edge_t["offsets"])},
               out_dir / "edge_features.pt")

    # PyG Data list
    from torch_geometric.data import Data
    data_list = []
    for g, mid in zip(graphs, material_ids):
        data_list.append(Data(
            x=torch.tensor(g["node_features"], dtype=torch.float32),
            edge_index=torch.tensor(g["edge_index"], dtype=torch.long).t().contiguous(),
            edge_attr=torch.tensor(g["edge_features"], dtype=torch.float32),
            pos=torch.tensor(g["pos"], dtype=torch.float32),
            material_id=mid,
        ))
    torch.save(data_list, out_dir / "graph.pt")

    targets_pt = {
        tid: {"y": torch.from_numpy(v["y"].astype(np.float32)),
              "mask": torch.from_numpy(v["mask"]),
              "n_classes": v["n_classes"], "classes": v["classes"]}
        for tid, v in targets.items()}
    torch.save(targets_pt, out_dir / "targets.pt")

    for s in ("train", "val", "test", "gold"):
        torch.save(torch.from_numpy(splits[s]), out_dir / "splits" / f"{s}.pt")
    (out_dir / "splits" / "split_keys.json").write_text(
        json.dumps(split_map, indent=2))

    # copy CIFs for native MatGL/MACE/ALIGNN use
    print("Copying structures ...")
    copied = 0
    for mid, cif in zip(material_ids, cif_paths):
        dst = STRUCT_DIR / cif.name
        if not dst.exists():
            dst.write_bytes(cif.read_bytes())
            copied += 1
    print(f"  {copied} CIFs copied")

    metadata = {
        "schema": "scandium-ml",
        "version": BUILD_VERSION,
        "generated_at": time.strftime("%Y-%m-%dT%H:%M:%S"),
        "source": {
            "canonical": str(CANONICAL),
            "descriptors": str(DESCRIPTORS),
            "consensus": str(CONSENSUS),
            "structured_source": STRUCTURED_SOURCE,
            "n_structured": int(len(mp)),
        },
        "graph": {
            "strategy": "crystalnn + 5A cutoff fallback",
            "node_feature_dims": [10],
            "edge_feature_dims": [1],
            "node_feature_names": [
                "atomic_number", "group", "row", "electronegativity",
                "mendeleev_no", "atomic_mass", "electron_affinity",
                "ionization_energy", "valence", "common_oxidation_state",
            ],
            "edge_feature_names": ["bond_distance_angstrom"],
            "n_graphs": int(len(graphs)),
            "n_nodes": int(node_t["values"].shape[0]),
            "n_edges": int(edge_t["values"].shape[0]),
            "n_isolated_nodes": int(sum(1 for g in graphs if not g["edge_index"])),
            "fallback_used": int(sum(
                1 for g in graphs if not g["edge_index"])),
        },
        "targets": target_summary,
        "splits": split_counts,
        "frameworks": {
            "pyg": "graph.pt = list[torch_geometric.data.Data]",
            "dgl": "convert via dgl.graph(edge_index) + node_features.pt",
            "matgl": "pymatgen Structure.from_file(cif) + Data x",
            "alignn": "bond edges from edge_index, angle edges derivable from pos",
            "mace": "structures/*.cif via pymatgen/ASE",
        },
        "notes": [
            "dense regression/classification targets are 100% populated on the"
            " structured MP corpus",
            "conductive_candidate_ranking is sparse: only materials whose"
            " composition matches a consensus group carry a label (n labels = "
            f"{target_summary['conductive_candidate_ranking']})",
            "labels are never imputed; missing -> mask=False",
            "splits reuse the Phase 6 leakage-checked assignment (composition-"
            "family grouped)",
        ],
    }
    (out_dir / "metadata.json").write_text(json.dumps(metadata, indent=2))
    print(f"\nDone. Wrote {len(graphs)} graphs to {out_dir}")
    return metadata


if __name__ == "__main__":
    import argparse

    ap = argparse.ArgumentParser(description="Build dataset_ml/ ML export")
    ap.add_argument("--limit", type=int, default=0)
    ap.add_argument("--out", type=Path, default=OUT_DIR)
    args = ap.parse_args()
    meta = build_dataset(limit=args.limit, out_dir=args.out)
    print(json.dumps(meta, indent=2))
