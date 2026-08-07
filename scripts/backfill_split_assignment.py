#!/usr/bin/env python3
"""Populate `ml_features.split_assignment` + `ml_features.split_group_key`
in the canonical dataset (guide §5 action 1).

The schema has carried these fields since v0.6, but they were never populated —
every canonical row currently has `split_assignment=None` and an empty
`split_group_key`. A dataset whose split fields are null is "a CSV, not a
benchmark-ready dataset": downstream users cannot reproduce leakage-free
splits from the release artifacts alone.

This script backfills:

  ml_features.split_assignment   train | val | test | gold_benchmark — the
                                 OBELiX-style leakage-free split (grouped by
                                 paper of origin OR composition, so any two
                                 entries sharing either land in the same
                                 split; test ≈20%, the 20–30% band OBELiX
                                 targets). Gold rows keep their
                                 gold_benchmark tag.
  ml_features.split_group_key    the composition-family grouping key — the
                                 reduced formula when present, else the
                                 material id (verified rows carry their
                                 formula in `identity.material_id`). Two rows
                                 sharing this key are the same chemical
                                 species and must never straddle train/test.

Deterministic: paper_ood assignment uses a stable hash of the connected-
component key — no RNG state, no network.

Usage:
    python scripts/backfill_split_assignment.py                 # rewrite in place
    python scripts/backfill_split_assignment.py --dry-run       # report only
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from ssb_dataset.benchmarks.splits import (  # noqa: E402
    OUT, paper_ood_split_map,
)

CANONICAL = ROOT / "cleaning_output/canonical_dataset.parquet"


def _gold_ids() -> set[str]:
    """material_ids tagged gold_benchmark in the persisted random split map."""
    random_map = OUT / "random.parquet"
    if not random_map.exists():
        return set()
    df = pd.read_parquet(random_map)
    return {
        str(mid)
        for mid, split in zip(df["material_id"].astype(str),
                              df["split"].astype(str))
        if split == "gold_benchmark"
    }


def _group_key(df: pd.DataFrame) -> pd.Series:
    """Composition-family grouping key: reduced formula, else material id.

    Verified/literature rows carry their composition in
    `identity.material_id` (their `identity.reduced_formula` is None), so the
    fallback matters — otherwise every labeled row would land in the same
    'unknown' group and the leakage guard would be silently dead for the rows
    that matter most.
    """
    has_formula = "identity.reduced_formula" in df.columns
    formula = df["identity.reduced_formula"].fillna("") if has_formula else ""
    mid = df["identity.material_id"].fillna("")
    out = formula.astype(str).where(formula.astype(str).str.len() > 0, mid)
    return out


def backfill(canonical_path: Path, gold_ids: set[str]) -> pd.DataFrame:
    canon = pd.read_parquet(canonical_path)
    mid_col = "identity.material_id"
    if mid_col not in canon.columns:
        raise ValueError(f"{mid_col} missing from {canonical_path}")

    ids = canon[mid_col].astype(str)
    split_map = paper_ood_split_map(canon)
    assignment = ids.map(split_map)
    missing = int(assignment.isna().sum())
    if missing:
        raise ValueError(
            f"{missing} canonical rows have no paper_ood split assignment — "
            "the split map does not cover the full corpus. Build the splits "
            "first: `python scripts/run_scandium_bench.py`."
        )

    # preserve the gold tier: gold rows are always held out, never re-split
    assignment = assignment.where(~ids.isin(gold_ids), "gold_benchmark")

    canon["ml_features.split_assignment"] = assignment
    canon["ml_features.split_group_key"] = _group_key(canon)
    return canon


def summarize(canon: pd.DataFrame) -> dict:
    sa = canon["ml_features.split_assignment"]
    gk = canon["ml_features.split_group_key"]
    return {
        "n_records": int(len(canon)),
        "split_assignment_populated": int(sa.notna().sum()),
        "split_group_key_populated": int(gk.notna().sum()),
        "split_distribution": sa.value_counts(dropna=False).to_dict(),
        "distinct_group_keys": int(gk.nunique()),
        "max_group_size": int(gk.value_counts().max()),
    }


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--canonical", type=Path, default=CANONICAL)
    ap.add_argument("--dry-run", action="store_true",
                    help="report coverage without writing")
    args = ap.parse_args()

    gold_ids = _gold_ids()
    canon = backfill(args.canonical, gold_ids)
    stats = summarize(canon)
    print(f"split_assignment populated: {stats['split_assignment_populated']}"
          f" / {stats['n_records']}  (unmapped: 0)")
    print(f"split_group_key populated: {stats['split_group_key_populated']}"
          f" / {stats['n_records']}  ({stats['distinct_group_keys']} distinct"
          f" keys, max group {stats['max_group_size']})")
    print("assignment distribution:", stats["split_distribution"])

    if args.dry_run:
        print("[dry-run] no changes written")
        return
    canon.to_parquet(args.canonical, index=False)
    print(f"wrote {args.canonical}")


if __name__ == "__main__":
    main()
