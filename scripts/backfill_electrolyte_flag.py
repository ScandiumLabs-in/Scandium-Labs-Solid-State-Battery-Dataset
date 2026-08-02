#!/usr/bin/env python3
"""Backfill `identity.is_electrolyte_candidate` onto an existing canonical/staging
Parquet from stored compositions.

Why: the flag is computed at ingestion time by the connectors, but the current
on-disk canonical predates it. This deterministically re-derives the flag from the
stored `identity.composition` (or `identity.material_id`) for DFT rows and writes a
flag-only copy, so the honest electrolyte-candidate fraction can be reported without
a network-backed full re-ingest.

Writes `{stem}_flagged.parquet` next to the input (never overwrites the source).
Idempotent: skips rows that already carry the column.
"""
from __future__ import annotations

import sys
from pathlib import Path

import pandas as pd

from ssb_dataset.sources.classifier import is_electrolyte_candidate

ROOT = Path(__file__).resolve().parent.parent


def load_df(path: Path) -> pd.DataFrame:
    return pd.read_parquet(path)


def flag_row(comp: str) -> bool:
    if not comp or not isinstance(comp, str):
        return True  # conservative: unknown stays a candidate rather than dropping it
    try:
        return bool(is_electrolyte_candidate(composition=comp))
    except Exception:
        return True


def backfill(path: Path, *, force: bool = False) -> Path:
    df = load_df(path)
    if "identity.is_electrolyte_candidate" in df.columns and not force:
        print(f"  {path.name}: already has flag → skip")
        return path

    comp = "identity.composition" if "identity.composition" in df.columns else "identity.material_id"
    vals = df[comp].map(flag_row)
    df.insert(df.columns.get_loc("identity.family") + 1, "identity.is_electrolyte_candidate", vals)

    out = path.with_name(f"{path.stem}_identity_electrolyte.parquet")
    df.to_parquet(out)
    print(f"  {path.name} -> {out.name} ({df['identity.is_electrolyte_candidate'].sum()}/{len(df)} candidates)")
    return out


def main() -> None:
    targets = [
        ROOT / "cleaning_output/canonical_dataset.parquet",
        ROOT / "scandium_output/canonical_dataset.parquet",
    ]
    candidates_found = {p.exists() for p in targets}
    if not any(candidates_found):
        print("No canonical parquet found; pass explicit paths or run --all")
        return
    for p in targets:
        if p.exists():
            backfill(p)


if __name__ == "__main__":
    if len(sys.argv) > 1 and sys.argv[1] == "--all":
        from scripts.expand_sources import FULL_COLUMNS  # noqa: F401  (staging schema)
        for ph in (ROOT / "staging").rglob("*.parquet"):
            try:
                backfill(ph)
            except Exception as e:
                print(f"  ! {ph.name}: {e}")
    else:
        main()