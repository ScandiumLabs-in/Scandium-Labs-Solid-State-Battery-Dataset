#!/usr/bin/env python3
"""Re-enrich JARVIS staging rows with the fields needed for cross-database
validation (Phase A, v1.4.0).

The original JARVIS harvest (scripts/expand_sources.py) wrote a minimal column
set — only formation energy, band gap, lattice params and modulus — because
those were the only fields the pre-v1.4 staging schema carried. The bundled
JARVIS-DFT figshare cache has everything else (formula, density, atoms), all
on disk with no network. This script backfills, per staged record:

  identity.composition        full formula string
  identity.reduced_formula    pymatgen reduced formula (the cross-DB join key)
  structure.density           g/cm3 from the cache
  structure.volume            A^3 from the lattice matrix determinant
  structure.nsites            number of atoms in the cell

Deterministic, idempotent (backfills only columns that are currently null),
no LLM, no network beyond the already-cached figshare download.

Usage:
  python scripts/enrich_jarvis.py                  # backfill all staged rows
  python scripts/enrich_jarvis.py --dry-run        # report coverage, write nothing
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

import numpy as np
import pandas as pd
import pyarrow as pa
import pyarrow.parquet as pq

BASE = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(BASE))
sys.path.insert(0, str(BASE / "src"))

from pymatgen.core import Composition

STAGING_JARVIS = BASE / "staging" / "jarvis"

JARVIS_FIELDS = {
    "identity.composition": ("formula", None),
    "identity.reduced_formula": ("_reduced_formula", None),
    "structure.density": ("density", float),
    "structure.volume": ("_volume", float),
    "structure.nsites": ("_nsites", int),
}

# columns that must stay null on JARVIS rows — the cache cannot provide them
# and a wrong default would poison cross-DB comparison. Left as None.


def _load_cache() -> dict[str, dict]:
    from jarvis.db.figshare import data

    all_data = data("dft_3d")
    out: dict[str, dict] = {}
    for entry in all_data:
        jid = entry.get("jid", "")
        if jid:
            out[jid] = entry
    return out


def _formula_info(entry: dict) -> tuple[str | None, str | None, int | None, float | None]:
    formula = entry.get("formula") or None
    reduced: str | None = None
    nsites: int | None = None
    volume: float | None = None
    atoms = entry.get("atoms")
    if formula:
        try:
            reduced = Composition(formula).reduced_formula
        except Exception:
            reduced = None
    if isinstance(atoms, dict):
        elements = atoms.get("elements")
        if isinstance(elements, list):
            nsites = len(elements)
        lattice = atoms.get("lattice_mat")
        if lattice is not None:
            try:
                volume = abs(float(np.linalg.det(np.asarray(lattice, dtype=float))))
            except Exception:
                volume = None
    return formula, reduced, nsites, volume


def enrich_row(entry: dict) -> dict[str, object]:
    formula, reduced, nsites, volume = _formula_info(entry)
    return {
        "identity.composition": formula,
        "identity.reduced_formula": reduced,
        "structure.density": entry.get("density") or None,
        "structure.volume": volume,
        "structure.nsites": nsites,
    }


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--limit", type=int, default=0,
                        help="only process the first N staging files (dev)")
    args = parser.parse_args()

    print("Loading bundled JARVIS-DFT cache ...")
    cache = _load_cache()
    print(f"  cache entries: {len(cache)}")

    files = sorted(STAGING_JARVIS.rglob("part-*.parquet"))
    if args.limit:
        files = files[: args.limit]
    print(f"  staging part files: {len(files)}")

    total = 0
    backfilled = {k: 0 for k in JARVIS_FIELDS}
    not_in_cache = 0
    for f in files:
        df = pq.read_table(f).to_pandas()
        src_ids = df["identity.source_id"].astype(str).tolist()
        new_cols: dict[str, list] = {k: [] for k in JARVIS_FIELDS}
        for sid in src_ids:
            entry = cache.get(sid)
            if entry is None:
                not_in_cache += 1
                for k in new_cols:
                    new_cols[k].append(None)
                continue
            vals = enrich_row(entry)
            for k in new_cols:
                new_cols[k].append(vals[k])
        for col, values in new_cols.items():
            if col not in df.columns:
                df[col] = None
            mask = df[col].isna()
            if mask.any():
                df.loc[mask, col] = [v for v, m in zip(values, mask) if m]
                backfilled[col] += int(mask.sum())
        total += len(df)
        if not args.dry_run:
            pq.write_table(pa.Table.from_pandas(df), f)

    print(f"\n  rows scanned: {total}, not-in-cache: {not_in_cache}")
    for k, n in backfilled.items():
        print(f"  backfilled {k}: {n}")
    if args.dry_run:
        print("  dry-run — nothing written")


if __name__ == "__main__":
    main()
