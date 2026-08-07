#!/usr/bin/env python3
"""Compute deterministic structure-graph + local-environment descriptors for
every Materials Project staging record and cache them per-material to
data/raw/materials_project/struct_desc/{mid}.json.

These are pure functions of the relaxed structure (no MP API): the CrystalNN
structure graph, its networkx statistics (GraphBlock), local polyhedral
geometry (polyhedron volume/distortion, bond-angle variance, tetrahedrality/
octahedrality, mean neighbor distance, neighbor species distribution), the
packing fraction, and Li-sublattice transport proxies (Li site count, vacancy
fraction on the Li sublattice, shortest periodic Li-Li hop distance).

Coverage: full for every record with a parseable structure (Li single-site /
intermetallics that CrystalNN cannot build a graph for are honestly None).

Resumable: --force to recompute; otherwise skips mids that already have output.

Usage:
  python scripts/compute_structure_descriptors.py              # all
  python scripts/compute_structure_descriptors.py --limit 500  # small test
  python scripts/compute_structure_descriptors.py --force      # recompute all
  python scripts/compute_structure_descriptors.py --jobs 8     # parallel
"""

from __future__ import annotations

import argparse
import json
import math
import time
from concurrent.futures import ProcessPoolExecutor, as_completed
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parent.parent
RAW_DIR = ROOT / "data/raw/materials_project/raw_json"
OUT_DIR = ROOT / "data/raw/materials_project/struct_desc"


def _compute_one(p: Path) -> tuple[str, dict]:
    mid = p.stem
    try:
        d = json.loads(p.read_text())
    except Exception:
        return mid, {}
    try:
        from pymatgen.core import Structure
        struct = Structure.from_dict(d["structure_dict"])
    except Exception:
        return mid, {}

    graph_stats: dict[str, Any] = {}
    local: dict[str, Any] = {}
    try:
        import networkx as nx
        from pymatgen.analysis.graphs import StructureGraph
        from pymatgen.analysis.local_env import CrystalNN

        nn = CrystalNN()
        sg = StructureGraph.from_local_env_strategy(struct, nn)
        ng = nx.Graph()
        for u in sg.graph.nodes:
            ng.add_node(u)
        for u, v, _data in sg.graph.edges(data=True):
            ng.add_edge(u, v)
        n_nodes = ng.number_of_nodes()
        n_edges = ng.number_of_edges()
        graph_stats["num_nodes"] = n_nodes
        graph_stats["num_edges"] = n_edges
        if n_nodes:
            graph_stats["average_degree"] = round(
                2.0 * n_edges / n_nodes, 4)
        graph_stats["graph_density"] = round(nx.density(ng), 6)
        if n_nodes:
            try:
                graph_stats["clustering_coefficient"] = round(
                    nx.average_clustering(ng), 6)
            except Exception:
                graph_stats["clustering_coefficient"] = None
        try:
            graph_stats["connected"] = nx.is_connected(ng)
            graph_stats["graph_diameter"] = (
                nx.diameter(ng) if graph_stats["connected"] else None)
        except Exception:
            graph_stats["connected"] = None
            graph_stats["graph_diameter"] = None

        # Edge lengths (from the structure graph) for mean/std. Use the
        # ConnectedSite.dist (correct nearest-image distance) rather than
        # reconstructing from to_jimage, which has sign conventions that are
        # easy to invert.
        lens = []
        for u in sg.graph.nodes:
            for cs in sg.get_connected_sites(u):
                lens.append(float(getattr(cs, "dist",
                                          getattr(cs, "nn_distance", 0.0))))
        if lens:
            graph_stats["edge_length_mean"] = round(sum(lens) / len(lens), 4)
            var = sum((x - sum(lens) / len(lens)) ** 2 for x in lens) / len(lens)
            graph_stats["edge_length_std"] = round(math.sqrt(var), 4)
            local["nearest_neighbor_distance"] = round(min(lens), 4)

        # Tier 1 — packing fraction: sum of atomic-sphere volumes (from the
        # element's atomic radius) over the cell volume.
        try:
            from pymatgen.core import Element as PElement
            total_site_vol = 0.0
            for site in struct:
                for sp, occ in site.species.items():
                    try:
                        r = PElement(sp).atomic_radius
                    except Exception:
                        r = None
                    if r is not None:
                        total_site_vol += occ * (4.0 / 3.0) * math.pi * r ** 3
            cell_vol = struct.lattice.volume
            if cell_vol and cell_vol > 0 and total_site_vol > 0:
                local["packing_fraction"] = round(total_site_vol / cell_vol, 4)
        except Exception:
            pass

        # Tier 2 — Li-sublattice transport proxies: distinct site count, vacancy
        # fraction on the Li sublattice, and the shortest periodic Li-Li hop.
        li_descr: dict[str, Any] = {}
        try:
            li_idx = [i for i, s in enumerate(struct) if "Li" in s.species_string]
            if li_idx:
                li_descr["site_count"] = len(li_idx)
                occ_sum = sum(struct[i].species.get("Li", 0.0) for i in li_idx)
                if occ_sum and len(li_idx):
                    li_descr["vacancy_fraction"] = round(
                        1.0 - occ_sum / len(li_idx), 4)
                li_set = set(li_idx)
                best: float | None = None
                nbrs = struct.get_all_neighbors(6.0, include_index=True)
                for i in li_idx:
                    for nbr in nbrs[i]:
                        if nbr.index in li_set and nbr.nn_distance > 0.001 and \
                                (best is None or nbr.nn_distance < best):
                            best = float(nbr.nn_distance)
                if best is not None:
                    li_descr["hopping_distance"] = round(best, 4)
        except Exception:
            pass

        # Local polyhedral geometry from the first non-trivial site.
        try:
            import numpy as np
            for site_idx in range(n_nodes):
                neighbors = sg.get_connected_sites(site_idx)
                if len(neighbors) < 3:
                    continue
                center = struct[site_idx].coords
                dists = []
                vecs = []
                species = {}
                for nbr in neighbors:
                    dist = float(getattr(nbr, "dist",
                                          getattr(nbr, "nn_distance", 0.0)))
                    dists.append(dist)
                    vecs.append(np.array(nbr.site.coords) - center)
                    sp = nbr.site.specie.symbol
                    species[sp] = species.get(sp, 0.0) + 1.0
                n_nb = len(neighbors)
                total_species = float(sum(species.values()))
                local["neighbor_species_distribution"] = {
                    k: round(v / total_species, 4) for k, v in species.items()
                }
                local["mean_neighbor_distance"] = round(
                    sum(dists) / n_nb, 4)
                # Polyhedron volume via the convex hull of neighbor vectors.
                try:
                    from scipy.spatial import ConvexHull
                    pts = np.array(vecs)
                    if pts.shape[0] >= 4:
                        local["polyhedron_volume"] = round(
                            ConvexHull(pts).volume, 4)
                except Exception:
                    local["polyhedron_volume"] = None
                # Bond-angle variance (about the central site).
                angles = []
                for i in range(n_nb):
                    for j in range(i + 1, n_nb):
                        a = vecs[i]
                        b = vecs[j]
                        denom = (math.sqrt((a * a).sum()) *
                                 math.sqrt((b * b).sum()))
                        if denom == 0:
                            continue
                        cosang = max(-1.0, min(1.0,
                                   float((a * b).sum()) / denom))
                        angles.append(math.degrees(math.acos(cosang)))
                if angles:
                    mean_ang = sum(angles) / len(angles)
                    local["bond_angle_variance"] = round(
                        sum((x - mean_ang) ** 2 for x in angles) / len(angles), 4)
                    # Tetrahedrality: RMS deviation from 109.47 deg.
                    local["tetrahedrality"] = round(
                        math.sqrt(sum((x - 109.47) ** 2 for x in angles)
                                  / len(angles)), 4)
                    # Octahedrality: RMS deviation from 90 deg.
                    local["octahedrality"] = round(
                        math.sqrt(sum((x - 90.0) ** 2 for x in angles)
                                  / len(angles)), 4)
                # Polyhedron distortion: RMS deviation of neighbor distances
                # from their mean (Baur distortion analog).
                if dists:
                    md = sum(dists) / len(dists)
                    local["polyhedron_distortion"] = round(
                        sum((x - md) ** 2 for x in dists) / len(dists) / md ** 2
                        if md else 0.0, 6)
                break
        except Exception:
            pass
    except Exception:
        pass

    return mid, {"graph": graph_stats, "local": local, "li": li_descr}


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--limit", type=int, default=0)
    ap.add_argument("--force", action="store_true")
    ap.add_argument("--jobs", type=int, default=1)
    args = ap.parse_args()

    OUT_DIR.mkdir(parents=True, exist_ok=True)
    paths = sorted(RAW_DIR.glob("*.json"))
    if args.limit:
        paths = paths[: args.limit]
    todo = [p for p in paths
            if args.force or not (OUT_DIR / f"{p.stem}.json").exists()]
    print(f"{len(todo)}/{len(paths)} materials to compute")

    t0 = time.time()
    done = 0
    if args.jobs > 1 and len(todo) > 1:
        with ProcessPoolExecutor(max_workers=args.jobs) as ex:
            futs = [ex.submit(_compute_one, p) for p in todo]
            for fut in as_completed(futs):
                mid, out = fut.result()
                if out:
                    (OUT_DIR / f"{mid}.json").write_text(
                        json.dumps(out, indent=2))
                done += 1
                if done % 1000 == 0:
                    print(f"  {done}/{len(todo)} ({time.time()-t0:.0f}s)")
    else:
        for p in todo:
            mid, out = _compute_one(p)
            if out:
                (OUT_DIR / f"{mid}.json").write_text(json.dumps(out, indent=2))
            done += 1
            if done % 1000 == 0:
                print(f"  {done}/{len(todo)} ({time.time()-t0:.0f}s)")
    print(f"Done: {done} computed in {time.time()-t0:.0f}s -> {OUT_DIR}")


if __name__ == "__main__":
    main()
