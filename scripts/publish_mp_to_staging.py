#!/usr/bin/env python3
"""Publish the full Materials Project harvest into partitioned staging.

Reads data/raw/materials_project/parsed/parsed.parquet (21,528 records) and
writes it to staging/materials_project/<family>/part-*.parquet using the same
partitioning + column scheme as the Phase 2 ingestion pipeline.

The parsed store uses a nested `structure.lattice_params` dict; staging needs
flat `structure.lattice_params.{a,b,c,alpha,beta,gamma}` columns. This script
flattens that field and drops the nested column, then partitions by family.

Usage:
  python scripts/publish_mp_to_staging.py                # write (replaces old MP staging)
  python scripts/publish_mp_to_staging.py --dry-run      # report counts only
  python scripts/publish_mp_to_staging.py --source-parsed <path>
"""

from __future__ import annotations

import argparse
import shutil
from pathlib import Path

import numpy as np
import pandas as pd
import pyarrow as pa
import pyarrow.parquet as pq

BASE = Path(__file__).resolve().parent.parent
PARSED = BASE / "data/raw/materials_project/parsed/parsed.parquet"
STAGING_MP = BASE / "staging" / "materials_project"

LATTICE_KEYS = ("a", "b", "c", "alpha", "beta", "gamma")


def load_parsed(path: Path) -> pd.DataFrame:
    df = pd.read_parquet(path)
    # The parsed store keeps a nested dict column; expand to flat columns.
    if "structure.lattice_params" in df.columns:
        lat = df["structure.lattice_params"]
        flat = pd.DataFrame([dict(x or {}) for x in lat], index=df.index)
        for k in LATTICE_KEYS:
            col = f"structure.lattice_params.{k}"
            if col not in df.columns:
                df[col] = flat.get(k, 0.0) if not flat.empty else 0.0
        df = df.drop(columns=["structure.lattice_params"])
    # Ensure all lattice columns exist (default to triclinic-agnostic 0/90).
    for k in LATTICE_KEYS:
        col = f"structure.lattice_params.{k}"
        if col not in df.columns:
            df[col] = 90.0 if k in ("alpha", "beta", "gamma") else 0.0
    return df


def clean_record_dict(df: pd.DataFrame) -> pd.DataFrame:
    """Coerce mixed/nullable object columns so pyarrow can serialize."""
    for col in df.columns:
        s = df[col]
        if s.dtype == object:
            # Empty lists -> keep as lists (matches ingestion output).
            if s.map(lambda v: isinstance(v, (list, tuple, np.ndarray))).all():
                df[col] = s.map(lambda v: list(v) if isinstance(v, (np.ndarray, tuple)) else v)
            elif s.isna().all():
                df[col] = pd.Series([None] * len(df), index=df.index, dtype=object)
    return df


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--source-parsed", type=Path, default=PARSED)
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--no-replace", action="store_true", help="keep existing MP staging partitions")
    args = parser.parse_args()

    if not args.source_parsed.exists():
        raise SystemExit(f"Parsed store not found: {args.source_parsed}")

    df = load_parsed(args.source_parsed)
    df = clean_record_dict(df)
    fam_col = "identity.family"
    if fam_col not in df.columns:
        raise SystemExit(f"Missing family column: {fam_col}")

    print(f"Loaded {len(df)} parsed records from {args.source_parsed}")
    counts = df[fam_col].value_counts()
    for fam, n in counts.items():
        print(f"  {str(fam):22s} {n}")

    if args.dry_run:
        print("\nDry run — no files written.")
        return

    if not args.no_replace and STAGING_MP.exists():
        backup = STAGING_MP.parent / "materials_project_bak_pre_full"
        if backup.exists():
            shutil.rmtree(backup)
        shutil.move(str(STAGING_MP), str(backup))
        print(f"Moved old MP staging -> {backup}")

    written = 0
    for fam in counts.index:
        fam_str = str(fam)
        part_dir = STAGING_MP / fam_str
        part_dir.mkdir(parents=True, exist_ok=True)
        fam_df = df[df[fam_col] == fam]
        # Sort for stable row order across reprocesses.
        fam_df = fam_df.sort_values("identity.material_id").reset_index(drop=True)
        # Split into ~500-row parts to match ingestion batch sizing.
        part_size = 500
        for i, start in enumerate(range(0, len(fam_df), part_size)):
            part = fam_df.iloc[start:start + part_size]
            path = part_dir / f"part-{i:04d}.parquet"
            pq.write_table(pa.Table.from_pandas(part), path)
            written += 1

    print(f"\nWrote {written} partition files across {len(counts)} families to {STAGING_MP}")
    total = int(df[df[fam_col].notna()].shape[0])
    print(f"Total staged records: {total}")


if __name__ == "__main__":
    main()
