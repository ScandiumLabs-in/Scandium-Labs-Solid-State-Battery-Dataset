"""Deterministic crystal-graph construction for the ML export.

Given a pymatgen Structure, produce:

  {
    "num_nodes": int,
    "node_features": list[list[float]],   # per-element property vectors
    "edge_index": list[[int, int], ...],  # undirected bond adjacency
    "edge_features": list[list[float]],   # [bond_distance]
    "pos": list[[x, y, z]],               # cartesian site coordinates
  }

Primary strategy: CrystalNN (the standard for MP-derived crystal graphs). For
structures where CrystalNN cannot produce a graph (e.g. single-site cells with
no chemically sensible coordination), fall back to a deterministic 5 A periodic
cutoff neighbor graph. Both strategies are pure functions of the structure.

Node features are fixed per-element property vectors (see
:func:`element_feature_vector`); they do NOT depend on the graph so the model
can use them as node attributes directly.
"""

from __future__ import annotations

from typing import Any

from pymatgen.core import Element, Structure
from pymatgen.analysis.graphs import StructureGraph
from pymatgen.analysis.local_env import CrystalNN

CUTOFF_ANGSTROM = 5.0

# Element symbols in pymatgen Element ordering (1..118). We only allocate
# vectors for symbols actually used; unknown/provisional symbols get the
# zero vector.
_ELEMENT_CACHE: dict[str, list[float]] = {}


def _prop(symbol: str) -> dict[str, Any]:
    el = Element(symbol)
    return {
        "atomic_number": float(el.Z),
        "group": float(el.group or 0.0),
        "row": float(el.row or 0.0),
        "electronegativity": float(el.X or 0.0),
        "mendeleev_no": float(el.mendeleev_no or 0.0),
        "atomic_mass": float(el.atomic_mass or 0.0),
        "electron_affinity": float(el.electron_affinity or 0.0),
        "ionization_energy": float((el.ionization_energies[0]
                                    if el.ionization_energies else 0.0)),
        "valence": float(max(el.valence) if el.valence else 0.0),
        "common_oxi": float((el.common_oxidation_states[0]
                             if el.common_oxidation_states else 0.0)),
    }


def element_feature_vector(symbol: str) -> list[float]:
    """Deterministic 10-dim property vector for one element symbol.

    Order: atomic_number, group, row, electronegativity, mendeleev_no,
    atomic_mass, electron_affinity, first ionization energy, valence, common
    oxidation state. Unknown symbols return the zero vector (never NaN).
    """
    if symbol in _ELEMENT_CACHE:
        return _ELEMENT_CACHE[symbol]
    try:
        p = _prop(symbol)
    except Exception:
        _ELEMENT_CACHE[symbol] = [0.0] * 10
        return _ELEMENT_CACHE[symbol]
    vec = [
        p["atomic_number"], p["group"], p["row"], p["electronegativity"],
        p["mendeleev_no"], p["atomic_mass"], p["electron_affinity"],
        p["ionization_energy"], p["valence"], p["common_oxi"],
    ]
    _ELEMENT_CACHE[symbol] = vec
    return vec


def _site_symbol(struct: Structure, i: int) -> str:
    try:
        return str(struct[i].species_string)
    except Exception:
        return str(struct.sites[i].species_string)


def _structgraph_to_graph(struct: Structure, sg: StructureGraph) -> dict:
    n = len(struct)
    node_features = [element_feature_vector(_site_symbol(struct, i))
                     for i in range(n)]
    edge_index: list[list[int]] = []
    edge_features: list[list[float]] = []
    pos = [list(struct[i].coords) for i in range(n)]
    for u, v, data in sg.graph.edges(data=True):
        d = float(data.get("weight", 0.0) or data.get("dist", 0.0))
        if d <= 0:
            d = float(struct.get_distance(u, v))
        edge_index.append([int(u), int(v)])
        edge_index.append([int(v), int(u)])
        edge_features.append([d])
        edge_features.append([d])
    return {
        "num_nodes": n,
        "node_features": node_features,
        "edge_index": edge_index,
        "edge_features": edge_features,
        "pos": pos,
    }


def _cutoff_graph(struct: Structure) -> dict:
    """Deterministic periodic 5 A cutoff neighbor graph (undirected)."""
    n = len(struct)
    node_features = [element_feature_vector(_site_symbol(struct, i))
                     for i in range(n)]
    pos = [list(struct[i].coords) for i in range(n)]
    edge_index: list[list[int]] = []
    edge_features: list[list[float]] = []
    seen: set[tuple[int, int]] = set()
    for i in range(n):
        neigh = struct.get_neighbors(struct[i], CUTOFF_ANGSTROM)
        for nn in sorted(neigh, key=lambda x: x.nn_distance):
            j = nn.index
            key = (min(i, j), max(i, j))
            if key in seen or j == i:
                continue
            seen.add(key)
            d = float(nn.nn_distance)
            edge_index.append([i, j])
            edge_index.append([j, i])
            edge_features.append([d])
            edge_features.append([d])
    return {
        "num_nodes": n,
        "node_features": node_features,
        "edge_index": edge_index,
        "edge_features": edge_features,
        "pos": pos,
    }


def construct_crystal_graph(
    struct: Structure,
    strategy: str = "crystalnn",
) -> dict:
    """Build a crystal graph for a structure.

    ``strategy``: "crystalnn" (primary, CrystalNN structure graph) or "cutoff"
    (deterministic 5 A periodic neighbor graph). CrystalNN falls back to
    cutoff internally when it cannot produce edges, so a structure is never
    silently dropped.
    """
    if strategy == "cutoff":
        return _cutoff_graph(struct)
    try:
        sg = StructureGraph.from_local_env_strategy(struct, CrystalNN())
        g = _structgraph_to_graph(struct, sg)
        if g["edge_index"]:
            return g
    except Exception:
        pass
    return _cutoff_graph(struct)
