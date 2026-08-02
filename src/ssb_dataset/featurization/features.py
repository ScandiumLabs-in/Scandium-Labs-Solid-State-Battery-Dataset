"""Composition and symmetry descriptors for SSB materials.

Provides composition-based featurization (Magpie-style fallback when matminer
is unavailable) and symmetry-based descriptors (space group, crystal system, Li
sublattice metrics).
"""

from __future__ import annotations

import math
import re
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd


# ── Elemental property lookup (Magpie-style fallback) ────────────────────────

_ELEMENTAL_PROPERTIES: dict[str, dict[str, float]] = {
    "Li": {"atomic_number": 3, "atomic_mass": 6.94, "atomic_radius": 1.82,
           "electronegativity": 0.98, "melting_point": 453.65, "group": 1, "period": 2,
           "block": "s", "mendeleev_number": 3},
    "Na": {"atomic_number": 11, "atomic_mass": 22.99, "atomic_radius": 2.27,
           "electronegativity": 0.93, "melting_point": 370.87, "group": 1, "period": 3,
           "block": "s", "mendeleev_number": 11},
    "K": {"atomic_number": 19, "atomic_mass": 39.10, "atomic_radius": 2.75,
          "electronegativity": 0.82, "melting_point": 336.53, "group": 1, "period": 4,
          "block": "s", "mendeleev_number": 19},
    "Mg": {"atomic_number": 12, "atomic_mass": 24.31, "atomic_radius": 1.73,
           "electronegativity": 1.31, "melting_point": 923.0, "group": 2, "period": 3,
           "block": "s", "mendeleev_number": 12},
    "Ca": {"atomic_number": 20, "atomic_mass": 40.08, "atomic_radius": 2.31,
           "electronegativity": 1.0, "melting_point": 1115.0, "group": 2, "period": 4,
           "block": "s", "mendeleev_number": 20},
    "B": {"atomic_number": 5, "atomic_mass": 10.81, "atomic_radius": 1.92,
          "electronegativity": 2.04, "melting_point": 2349.0, "group": 13, "period": 2,
          "block": "p", "mendeleev_number": 5},
    "C": {"atomic_number": 6, "atomic_mass": 12.01, "atomic_radius": 1.70,
          "electronegativity": 2.55, "melting_point": 3823.0, "group": 14, "period": 2,
          "block": "p", "mendeleev_number": 6},
    "N": {"atomic_number": 7, "atomic_mass": 14.01, "atomic_radius": 1.55,
          "electronegativity": 3.04, "melting_point": 63.15, "group": 15, "period": 2,
          "block": "p", "mendeleev_number": 7},
    "O": {"atomic_number": 8, "atomic_mass": 16.00, "atomic_radius": 1.52,
          "electronegativity": 3.44, "melting_point": 54.36, "group": 16, "period": 2,
          "block": "p", "mendeleev_number": 8},
    "F": {"atomic_number": 9, "atomic_mass": 19.00, "atomic_radius": 1.47,
          "electronegativity": 3.98, "melting_point": 53.53, "group": 17, "period": 2,
          "block": "p", "mendeleev_number": 9},
    "P": {"atomic_number": 15, "atomic_mass": 30.97, "atomic_radius": 1.80,
          "electronegativity": 2.19, "melting_point": 317.3, "group": 15, "period": 3,
          "block": "p", "mendeleev_number": 15},
    "S": {"atomic_number": 16, "atomic_mass": 32.06, "atomic_radius": 1.80,
          "electronegativity": 2.58, "melting_point": 388.36, "group": 16, "period": 3,
          "block": "p", "mendeleev_number": 16},
    "Cl": {"atomic_number": 17, "atomic_mass": 35.45, "atomic_radius": 1.75,
           "electronegativity": 3.16, "melting_point": 171.65, "group": 17, "period": 3,
           "block": "p", "mendeleev_number": 17},
    "Ti": {"atomic_number": 22, "atomic_mass": 47.87, "atomic_radius": 1.50,
           "electronegativity": 1.54, "melting_point": 1941.0, "group": 4, "period": 4,
           "block": "d", "mendeleev_number": 22},
    "Ge": {"atomic_number": 32, "atomic_mass": 72.63, "atomic_radius": 2.11,
           "electronegativity": 2.01, "melting_point": 1211.4, "group": 14, "period": 4,
           "block": "p", "mendeleev_number": 32},
    "As": {"atomic_number": 33, "atomic_mass": 74.92, "atomic_radius": 1.85,
           "electronegativity": 2.18, "melting_point": 1090.0, "group": 15, "period": 4,
           "block": "p", "mendeleev_number": 33},
    "Se": {"atomic_number": 34, "atomic_mass": 78.97, "atomic_radius": 1.90,
           "electronegativity": 2.55, "melting_point": 494.0, "group": 16, "period": 4,
           "block": "p", "mendeleev_number": 34},
    "Br": {"atomic_number": 35, "atomic_mass": 79.90, "atomic_radius": 1.85,
           "electronegativity": 2.96, "melting_point": 265.95, "group": 17, "period": 4,
           "block": "p", "mendeleev_number": 35},
    "Y": {"atomic_number": 39, "atomic_mass": 88.91, "atomic_radius": 2.00,
          "electronegativity": 1.22, "melting_point": 1799.0, "group": 3, "period": 5,
          "block": "d", "mendeleev_number": 39},
    "Zr": {"atomic_number": 40, "atomic_mass": 91.22, "atomic_radius": 1.50,
           "electronegativity": 1.33, "melting_point": 2128.0, "group": 4, "period": 5,
           "block": "d", "mendeleev_number": 40},
    "La": {"atomic_number": 57, "atomic_mass": 138.91, "atomic_radius": 2.50,
           "electronegativity": 1.10, "melting_point": 1193.0, "group": 3, "period": 6,
           "block": "f", "mendeleev_number": 57},
    "Ce": {"atomic_number": 58, "atomic_mass": 140.12, "atomic_radius": 2.50,
           "electronegativity": 1.12, "melting_point": 1071.0, "group": 3, "period": 6,
           "block": "f", "mendeleev_number": 58},
    "In": {"atomic_number": 49, "atomic_mass": 114.82, "atomic_radius": 1.93,
           "electronegativity": 1.78, "melting_point": 429.75, "group": 13, "period": 5,
           "block": "p", "mendeleev_number": 49},
    "Sn": {"atomic_number": 50, "atomic_mass": 118.71, "atomic_radius": 2.17,
           "electronegativity": 1.96, "melting_point": 505.08, "group": 14, "period": 5,
           "block": "p", "mendeleev_number": 50},
    "Sb": {"atomic_number": 51, "atomic_mass": 121.76, "atomic_radius": 2.06,
           "electronegativity": 2.05, "melting_point": 904.05, "group": 15, "period": 5,
           "block": "p", "mendeleev_number": 51},
    "Te": {"atomic_number": 52, "atomic_mass": 127.60, "atomic_radius": 2.06,
           "electronegativity": 2.10, "melting_point": 722.66, "group": 16, "period": 5,
           "block": "p", "mendeleev_number": 52},
    "I": {"atomic_number": 53, "atomic_mass": 126.90, "atomic_radius": 1.98,
          "electronegativity": 2.66, "melting_point": 386.85, "group": 17, "period": 5,
          "block": "p", "mendeleev_number": 53},
    "Ta": {"atomic_number": 73, "atomic_mass": 180.95, "atomic_radius": 1.50,
           "electronegativity": 1.50, "melting_point": 3290.0, "group": 5, "period": 6,
           "block": "d", "mendeleev_number": 73},
    "W": {"atomic_number": 74, "atomic_mass": 183.84, "atomic_radius": 1.50,
          "electronegativity": 2.36, "melting_point": 3695.0, "group": 6, "period": 6,
          "block": "d", "mendeleev_number": 74},
    "Bi": {"atomic_number": 83, "atomic_mass": 208.98, "atomic_radius": 2.07,
           "electronegativity": 2.02, "melting_point": 544.55, "group": 15, "period": 6,
           "block": "p", "mendeleev_number": 83},
}


def _parse_formula_to_elements(formula: str) -> dict[str, float]:
    """Parse a chemical formula into element -> count mapping."""
    try:
        from pymatgen.core import Composition
        comp = Composition(formula)
        return {str(el): comp[el] for el in comp.elements}
    except Exception:
        pass

    elements: dict[str, float] = {}
    pattern = r"([A-Z][a-z]?)([0-9.]*)?"
    for match in re.finditer(pattern, formula):
        el = match.group(1)
        count_str = match.group(2)
        count = float(count_str) if count_str else 1.0
        elements[el] = elements.get(el, 0) + count
    return elements


def _element_property_stats(elements: dict[str, float], prop: str) -> dict[str, float]:
    """Compute aggregate statistics for a given elemental property."""
    values = []
    weights = []
    for el, count in elements.items():
        if el in _ELEMENTAL_PROPERTIES and prop in _ELEMENTAL_PROPERTIES[el]:
            values.append(_ELEMENTAL_PROPERTIES[el][prop])
            weights.append(count)
    if not values or sum(weights) == 0:
        return {"mean": 0.0, "std": 0.0, "min": 0.0, "max": 0.0, "range": 0.0}
    values = np.array(values)
    weights = np.array(weights)
    mean = np.average(values, weights=weights)
    variance = np.average((values - mean) ** 2, weights=weights)
    return {
        "mean": float(mean),
        "std": float(math.sqrt(variance)),
        "min": float(np.min(values)),
        "max": float(np.max(values)),
        "range": float(np.max(values) - np.min(values)),
    }


def compute_composition_descriptors(df: pd.DataFrame) -> pd.DataFrame:
    """Compute Magpie-style composition descriptors for each record.

    Adds columns for aggregate statistics of elemental properties,
    plus derived attributes like number of elements, fraction of each block type.
    """
    formula_col = None
    for c in ["composition", "identity.composition", "identity.material_id", "material_id"]:
        if c in df.columns:
            formula_col = c
            break
    if formula_col is None:
        return df

    descriptors: list[dict[str, float]] = []
    properties = ["atomic_number", "atomic_mass", "atomic_radius",
                  "electronegativity", "melting_point", "group", "period",
                  "mendeleev_number"]

    for formula in df[formula_col]:
        if formula is None or (isinstance(formula, float) and np.isnan(formula)):
            formula = ""
        elements = _parse_formula_to_elements(str(formula))
        row_desc: dict[str, float] = {}
        row_desc["n_elements"] = len(elements)

        s_block = block_count = p_block = d_block = f_block = 0
        for el in elements:
            props = _ELEMENTAL_PROPERTIES.get(el, {})
            block = props.get("block", "")
            if block == "s":
                s_block += 1
            elif block == "p":
                p_block += 1
            elif block == "d":
                d_block += 1
            elif block == "f":
                f_block += 1
        row_desc["frac_s_block"] = s_block / max(len(elements), 1)
        row_desc["frac_p_block"] = p_block / max(len(elements), 1)
        row_desc["frac_d_block"] = d_block / max(len(elements), 1)
        row_desc["frac_f_block"] = f_block / max(len(elements), 1)

        for prop in properties:
            stats = _element_property_stats(elements, prop)
            row_desc[f"{prop}_mean"] = stats["mean"]
            row_desc[f"{prop}_std"] = stats["std"]
            row_desc[f"{prop}_min"] = stats["min"]
            row_desc[f"{prop}_max"] = stats["max"]
            row_desc[f"{prop}_range"] = stats["range"]

        descriptors.append(row_desc)

    desc_df = pd.DataFrame(descriptors, index=df.index)
    for col in desc_df.columns:
        df[col] = desc_df[col]

    return df


# ── Symmetry Descriptors ─────────────────────────────────────────────────────


_SPACE_GROUP_RANGES: list[tuple[tuple[int, int], str]] = [
    ((1, 2), "Triclinic"),
    ((3, 15), "Monoclinic"),
    ((16, 74), "Orthorhombic"),
    ((75, 142), "Tetragonal"),
    ((143, 167), "Trigonal"),
    ((168, 194), "Hexagonal"),
    ((195, 230), "Cubic"),
]


def _get_space_group_info(spg: Any) -> tuple[int, str]:
    if spg is None or (isinstance(spg, float) and np.isnan(spg)):
        return 0, "Unknown"
    if isinstance(spg, (int, float, np.integer, np.floating)):
        num = int(spg)
    else:
        spg_str = str(spg).strip()
        if spg_str.isdigit():
            num = int(spg_str)
        else:
            return 0, "Unknown"

    for (low, high), system in _SPACE_GROUP_RANGES:
        if low <= num <= high:
            return num, system
    return num, "Unknown"


def _get_column(df: pd.DataFrame, *candidates: str) -> str | None:
    for c in candidates:
        if c in df.columns:
            return c
    return None


def compute_symmetry_descriptors(df: pd.DataFrame) -> pd.DataFrame:
    """Compute symmetry-based descriptors.

    Adds: space_group_number, crystal_system, li_fraction,
    has_li_sublattice, n_sites_in_unit_cell.
    """
    spg_cols = [c for c in df.columns if "space_group" in c.lower()]
    spg_col = spg_cols[0] if spg_cols else None

    struct_col = _get_column(df, "structure", "structure.structure_relaxed")
    if struct_col:
        n_sites = [len(s) if hasattr(s, "__len__") else 0 for s in df[struct_col]]
    else:
        n_sites = [0] * len(df)

    df["space_group_number"] = 0
    df["crystal_system"] = "Unknown"
    df["li_fraction"] = 0.0
    df["has_li_sublattice"] = False
    df["n_sites_unit_cell"] = n_sites

    if spg_col:
        for idx in df.index:
            spg = df.at[idx, spg_col]
            num, system = _get_space_group_info(spg)
            df.at[idx, "space_group_number"] = num
            df.at[idx, "crystal_system"] = system

    formula_col = None
    for c in ["composition", "identity.material_id", "material_id"]:
        if c in df.columns:
            formula_col = c
            break
    if formula_col:
        for idx in df.index:
            formula = str(df.at[idx, formula_col])
            elements = _parse_formula_to_elements(formula)
            total_atoms = sum(elements.values())
            li_count = elements.get("Li", 0)
            df.at[idx, "li_fraction"] = li_count / total_atoms if total_atoms > 0 else 0.0
            df.at[idx, "has_li_sublattice"] = li_count > 0

    return df
