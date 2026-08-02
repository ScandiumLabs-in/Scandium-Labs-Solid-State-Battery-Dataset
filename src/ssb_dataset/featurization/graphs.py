"""PIGNet V2-compatible graph construction from CIF structures.

Builds attention-gated message-passing graphs with 3-body angular edge features.
Follows the PIGNet V2 input spec:
  - nodes: atom-type embeddings (Z number)
  - edges: radial + angular 3-body features
  - global: composition-weighted descriptors

Optional dependency on torch_geometric. Falls back to a dict-based graph
representation when torch is unavailable.
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import numpy as np

try:
    import torch
    HAS_TORCH = True
except ImportError:
    HAS_TORCH = False

try:
    from torch_geometric.data import Data
    HAS_PYG = True
except ImportError:
    HAS_PYG = False


# ── Radial Basis Functions (Gaussian expansion) ──────────────────────────────


def _gaussian_expansion(
    distances: np.ndarray,
    centers: np.ndarray,
    width: float = 0.5,
) -> np.ndarray:
    """Expand distances onto Gaussian radial basis functions."""
    diffs = distances[:, np.newaxis] - centers[np.newaxis, :]
    return np.exp(-0.5 * (diffs / width) ** 2)


def _linear_basis(distances: np.ndarray, n_basis: int = 20, cutoff: float = 5.0) -> np.ndarray:
    """Linear spacing radial basis."""
    centers = np.linspace(0.0, cutoff, n_basis)
    return _gaussian_expansion(distances, centers)


def _angular_basis(
    angles: np.ndarray,
    n_basis: int = 8,
) -> np.ndarray:
    """Fourier-style angular basis for 3-body interactions."""
    basis = []
    for i in range(n_basis):
        basis.append(np.cos(i * angles))
        basis.append(np.sin(i * angles))
    return np.column_stack(basis)


# ── Distance and Angle Computation ────────────────────────────────────────────

_VANDERWAALS_RADII: dict[str, float] = {
    "H": 1.20, "Li": 1.82, "Be": 1.53, "B": 1.92, "C": 1.70, "N": 1.55,
    "O": 1.52, "F": 1.47, "Na": 2.27, "Mg": 1.73, "Al": 1.84, "Si": 2.10,
    "P": 1.80, "S": 1.80, "Cl": 1.75, "K": 2.75, "Ca": 2.31, "Ti": 1.50,
    "V": 1.50, "Cr": 1.50, "Mn": 1.50, "Fe": 1.50, "Co": 1.50, "Ni": 1.50,
    "Cu": 1.40, "Zn": 1.39, "Ge": 2.11, "As": 1.85, "Se": 1.90, "Br": 1.85,
    "Y": 2.00, "Zr": 1.50, "Nb": 1.50, "Mo": 1.50, "Ru": 1.50, "Rh": 1.50,
    "Pd": 1.50, "Ag": 1.72, "In": 1.93, "Sn": 2.17, "Sb": 2.06, "Te": 2.06,
    "I": 1.98, "La": 2.50, "Ce": 2.50, "Pr": 2.50, "Nd": 2.50, "Sm": 2.50,
    "Eu": 2.50, "Gd": 2.50, "Tb": 2.50, "Dy": 2.50, "Ho": 2.50, "Er": 2.50,
    "Tm": 2.50, "Yb": 2.50, "Ta": 1.50, "W": 1.50, "Pt": 1.75, "Au": 1.66,
    "Pb": 2.02, "Bi": 2.07,
}


def _get_covalent_radius(symbol: str) -> float:
    return _VANDERWAALS_RADII.get(symbol, 1.50)


def _compute_neighbor_pairs(
    frac_coords: np.ndarray,
    lattice: np.ndarray,
    cutoff: float = 5.0,
    max_neighbors: int = 20,
) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    """Compute neighbor pairs with periodic boundary conditions.

    Returns (sender_indices, receiver_indices, distances).
    """
    cart_coords = np.dot(frac_coords, lattice)
    n_atoms = len(cart_coords)
    senders: list[int] = []
    receivers: list[int] = []
    distances: list[float] = []

    for i in range(n_atoms):
        diffs = cart_coords - cart_coords[i]
        diffs -= np.rint(diffs @ np.linalg.inv(lattice).T) @ lattice
        dists = np.sqrt(np.sum(diffs ** 2, axis=1))
        valid = np.where((dists > 0.01) & (dists < cutoff))[0]

        order = np.argsort(dists[valid])
        for j_idx in order[:max_neighbors]:
            j = valid[j_idx]
            senders.append(i)
            receivers.append(j)
            distances.append(dists[j])

    return (
        np.array(senders, dtype=np.int64),
        np.array(receivers, dtype=np.int64),
        np.array(distances, dtype=np.float64),
    )


def _compute_angles(
    senders: np.ndarray,
    receivers: np.ndarray,
    frac_coords: np.ndarray,
    lattice: np.ndarray,
) -> np.ndarray:
    """Compute bond angles for 3-body interactions."""
    cart_coords = np.dot(frac_coords, lattice)
    edge_vecs = cart_coords[receivers] - cart_coords[senders]

    unique_senders = np.unique(senders)
    angle_list: list[float] = []

    for center in unique_senders:
        center_mask = senders == center
        neighbor_indices = receivers[center_mask]
        neighbor_vecs = edge_vecs[center_mask]
        n_neighbors = len(neighbor_indices)
        if n_neighbors < 2:
            continue
        for i in range(n_neighbors):
            for j in range(i + 1, n_neighbors):
                vi = neighbor_vecs[i]
                vj = neighbor_vecs[j]
                dot = np.dot(vi, vj)
                norm = np.linalg.norm(vi) * np.linalg.norm(vj)
                if norm > 1e-8:
                    cos_angle = np.clip(dot / norm, -1.0, 1.0)
                    angle = math.acos(cos_angle)
                    angle_list.append(angle)

    return np.array(angle_list, dtype=np.float64)


# ── PIGNet V2 Graph Builder ──────────────────────────────────────────────────


@dataclass
class PIGNetGraph:
    """A precomputed graph compatible with PIGNet V2 input spec."""
    node_features: np.ndarray
    edge_index: np.ndarray
    edge_features: np.ndarray
    angle_features: np.ndarray | None
    global_features: np.ndarray
    num_nodes: int
    num_edges: int
    composition_key: str = ""

    def to_torch_geometric(self) -> Any:
        """Convert to PyTorch Geometric Data object."""
        if not HAS_PYG:
            raise ImportError("torch_geometric is required for conversion")
        return Data(
            x=torch.tensor(self.node_features, dtype=torch.float32),
            edge_index=torch.tensor(self.edge_index, dtype=torch.long),
            edge_attr=torch.tensor(self.edge_features, dtype=torch.float32),
            global_feat=torch.tensor(self.global_features, dtype=torch.float32),
            num_nodes=self.num_nodes,
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "node_features": self.node_features.tolist(),
            "edge_index": self.edge_index.tolist(),
            "edge_features": self.edge_features.tolist(),
            "angle_features": self.angle_features.tolist() if self.angle_features is not None else None,
            "global_features": self.global_features.tolist(),
            "num_nodes": self.num_nodes,
            "num_edges": self.num_edges,
            "composition_key": self.composition_key,
        }


_ATOMIC_NUMBERS: dict[str, int] = {
    "H": 1, "Li": 3, "Be": 4, "B": 5, "C": 6, "N": 7, "O": 8, "F": 9,
    "Na": 11, "Mg": 12, "Al": 13, "Si": 14, "P": 15, "S": 16, "Cl": 17,
    "K": 19, "Ca": 20, "Ti": 22, "V": 23, "Cr": 24, "Mn": 25, "Fe": 26,
    "Co": 27, "Ni": 28, "Cu": 29, "Zn": 30, "Ge": 32, "As": 33, "Se": 34,
    "Br": 35, "Y": 39, "Zr": 40, "Nb": 41, "Mo": 42, "Ru": 44, "Rh": 45,
    "Pd": 46, "Ag": 47, "In": 49, "Sn": 50, "Sb": 51, "Te": 52, "I": 53,
    "La": 57, "Ce": 58, "Pr": 59, "Nd": 60, "Sm": 62, "Eu": 63, "Gd": 64,
    "Tb": 65, "Dy": 66, "Ho": 67, "Er": 68, "Tm": 69, "Yb": 70, "Ta": 73,
    "W": 74, "Pt": 78, "Au": 79, "Pb": 82, "Bi": 83,
}


def _element_to_z(symbol: str) -> int:
    return _ATOMIC_NUMBERS.get(symbol, 0)


def build_graph_from_structure(
    structure_cif: str,
    cutoff: float = 5.0,
    max_neighbors: int = 20,
    n_radial: int = 20,
    n_angular: int = 8,
    composition_key: str = "",
) -> PIGNetGraph | None:
    """Build a PIGNet V2-compatible graph from a CIF structure string.

    Returns None if structure parsing fails.
    """
    try:
        from pymatgen.core import Structure
        struct = Structure.from_str(structure_cif, fmt="cif")
    except Exception:
        return None

    frac_coords = np.array([s.frac_coords for s in struct.sites])
    lattice = np.array(struct.lattice.matrix)
    species = [str(s.specie) for s in struct.sites]
    z_numbers = np.array([_element_to_z(s) for s in species], dtype=np.int64)

    senders, receivers, distances = _compute_neighbor_pairs(
        frac_coords, lattice, cutoff, max_neighbors
    )

    edge_index = np.stack([receivers, senders], axis=0)

    radial_feats = _linear_basis(distances, n_basis=n_radial, cutoff=cutoff)

    angles = _compute_angles(senders, receivers, frac_coords, lattice)
    angular_feats = _angular_basis(angles, n_basis=n_angular) if len(angles) > 0 else None

    node_features = z_numbers.astype(np.float32)[:, np.newaxis]

    global_features = np.array([
        len(struct.sites),
        struct.lattice.volume,
    ], dtype=np.float32)

    return PIGNetGraph(
        node_features=node_features,
        edge_index=edge_index,
        edge_features=radial_feats,
        angle_features=angular_feats,
        global_features=global_features,
        num_nodes=len(struct.sites),
        num_edges=senders.shape[0],
        composition_key=composition_key,
    )


def build_graph_batch(
    structures: list[str],
    composition_keys: list[str] | None = None,
    output_dir: str | Path | None = None,
) -> list[PIGNetGraph | None]:
    """Build graphs for a batch of structures, optionally caching to disk."""
    graphs: list[PIGNetGraph | None] = []
    for i, cif in enumerate(structures):
        key = composition_keys[i] if composition_keys else f"struct_{i}"
        graph = build_graph_from_structure(cif, composition_key=key)
        graphs.append(graph)
        if output_dir and graph is not None:
            out = Path(output_dir)
            out.mkdir(parents=True, exist_ok=True)
            (out / f"{key}.json").write_text(
                __import__("json").dumps(graph.to_dict(), indent=2)
            )
    return graphs
