"""Stratified train/val/test splits with leakage prevention and gold benchmark subset.

Splits are grouped by composition-family key to prevent polymorphs and doped
variants of the same base composition from landing in different splits.
"""

from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd

from ssb_dataset.schema import ConfidenceTier, Family


def _composition_group_key(formula: str | None) -> str:
    if not formula or not isinstance(formula, str):
        return "unknown"
    try:
        from pymatgen.core import Composition
        comp = Composition(formula)
        reduced = comp.reduced_formula
        return reduced
    except Exception:
        return re.sub(r"[0-9.]+", "", formula).strip()


def _get_column(df: pd.DataFrame, *candidates: str) -> str | None:
    for c in candidates:
        if c in df.columns:
            return c
    return None


def compute_split_key(
    df: pd.DataFrame,
    formula_col: str = "identity.material_id",
    family_col: str = "identity.family",
) -> pd.Series:
    """Compute the split group key: composition_group + family to prevent leakage."""
    formula_col = _get_column(df, formula_col, "material_id", "composition") or formula_col
    family_col = _get_column(df, family_col, "family") or family_col

    if formula_col not in df.columns:
        return pd.Series(["unknown"] * len(df), index=df.index)

    if family_col in df.columns:
        families = df[family_col].astype(str)
    else:
        families = pd.Series(["unknown"] * len(df), index=df.index)

    group_keys = df[formula_col].apply(_composition_group_key)
    return families + "::" + group_keys


def create_splits(
    df: pd.DataFrame,
    train_frac: float = 0.7,
    val_frac: float = 0.15,
    test_frac: float = 0.15,
    seed: int = 42,
    split_by_group: bool = True,
) -> dict[str, pd.DataFrame]:
    """Create train/val/test splits with leakage prevention.

    When split_by_group=True, entire composition-family groups are assigned to
    a single split, preventing leakage between polymorphs/doped variants.
    """
    rng = np.random.default_rng(seed)

    if split_by_group:
        group_key = compute_split_key(df)
        unique_groups = list(group_key.unique())
        rng.shuffle(unique_groups)

        n = len(unique_groups)
        n_train = max(1, int(n * train_frac))
        n_val = max(1, int(n * val_frac))

        train_groups = set(unique_groups[:n_train])
        val_groups = set(unique_groups[n_train:n_train + n_val])
        test_groups = set(unique_groups[n_train + n_val:])

        train_idx = df.index[group_key.isin(train_groups)]
        val_idx = df.index[group_key.isin(val_groups)]
        test_idx = df.index[group_key.isin(test_groups)]
    else:
        families_col = _get_column(df, "identity.family", "family")
        if families_col:
            families = df[families_col]
        else:
            families = pd.Series(["unknown"] * len(df), index=df.index)

        train_idx = []
        val_idx = []
        test_idx = []
        for fam in families.unique():
            fam_mask = families == fam
            fam_indices = np.where(fam_mask)[0]
            rng.shuffle(fam_indices)
            n = len(fam_indices)
            n_train = max(1, int(n * train_frac))
            n_val = max(1, int(n * val_frac))
            train_idx.extend(fam_indices[:n_train])
            val_idx.extend(fam_indices[n_train:n_train + n_val])
            test_idx.extend(fam_indices[n_train + n_val:])

    df = df.reset_index(drop=True)

    result = {
        "train": df.iloc[train_idx].reset_index(drop=True) if len(train_idx) else pd.DataFrame(),
        "val": df.iloc[val_idx].reset_index(drop=True) if len(val_idx) else pd.DataFrame(),
        "test": df.iloc[test_idx].reset_index(drop=True) if len(test_idx) else pd.DataFrame(),
    }
    return result


def check_split_leakage(
    splits: dict[str, pd.DataFrame],
    formula_col: str = "identity.material_id",
    family_col: str = "identity.family",
) -> dict[str, Any]:
    """Check if any composition-family group appears in more than one split.

    The 'gold' split is excluded from leakage checking since it is a holdout
    verification set intentionally allowed to overlap with training splits.

    Returns a dict with pass/fail status and details.
    """
    training_splits = {name: df for name, df in splits.items() if name != "gold"}
    group_splits: dict[str, list[str]] = {}

    for name, split_df in training_splits.items():
        if split_df.empty:
            continue
        keys = compute_split_key(split_df, formula_col, family_col)
        for key in keys.unique():
            group_splits.setdefault(key, []).append(name)

    leaked = {k: v for k, v in group_splits.items() if len(v) > 1}
    return {
        "passed": len(leaked) == 0,
        "n_leaked_groups": len(leaked),
        "leaked_groups": leaked,
        "total_groups": len(group_splits),
    }


def build_gold_benchmark(
    df: pd.DataFrame,
    target_size: int = 300,
    seed: int = 42,
) -> pd.DataFrame:
    """Build a gold-standard benchmark subset of highest-confidence records.

    Selection priority:
      1. verified_human or dft_native confidence
      2. Has measured sigma_RT (not None, not 0)
      3. Balanced across families
    """
    rng = np.random.default_rng(seed)

    label_col = _get_column(df, "ion_transport.label_available", "label_available")
    sigma_col = _get_column(df, "ion_transport.sigma_RT", "sigma_RT")
    family_col = _get_column(df, "identity.family", "family")
    confidence_col = _get_column(df, "identity.confidence_tier", "confidence_tier")

    eligible = df.copy()

    if confidence_col in df.columns:
        high_confidence = eligible[confidence_col].isin([
            ConfidenceTier.verified_human.value,
            ConfidenceTier.dft_native.value,
            ConfidenceTier.high_confidence_extraction.value,
        ])
        eligible = eligible[high_confidence]

    if label_col in eligible.columns:
        eligible = eligible[eligible[label_col] == True]

    if sigma_col in eligible.columns:
        eligible = eligible[
            eligible[sigma_col].notna() & (eligible[sigma_col] > 0)
        ]

    if eligible.empty:
        return pd.DataFrame()

    if family_col in eligible.columns:
        families = eligible[family_col].unique()
    else:
        families = ["unknown"]

    per_family = max(1, target_size // max(len(families), 1))
    selected: list[int] = []

    for fam in families:
        if family_col in eligible.columns:
            fam_df = eligible[eligible[family_col] == fam]
        else:
            fam_df = eligible
        fam_indices = fam_df.index.tolist()
        rng.shuffle(fam_indices)
        selected.extend(fam_indices[:per_family])

    if len(selected) < target_size:
        remaining = [i for i in eligible.index if i not in set(selected)]
        rng.shuffle(remaining)
        selected.extend(remaining[:target_size - len(selected)])

    gold = df.loc[selected].reset_index(drop=True)
    return gold


def write_splits(
    splits: dict[str, pd.DataFrame],
    output_dir: str | Path,
    gold_df: pd.DataFrame | None = None,
) -> None:
    """Write splits to Parquet files with metadata."""
    output_dir = Path(output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)

    import pyarrow as pa
    import pyarrow.parquet as pq

    if gold_df is not None and not gold_df.empty:
        splits["gold"] = gold_df

    for name, split_df in splits.items():
        if split_df.empty:
            continue
        table = pa.Table.from_pandas(split_df)
        pq.write_table(table, output_dir / f"{name}.parquet")

    meta = {name: len(df) for name, df in splits.items() if not df.empty}
    (output_dir / "splits_metadata.json").write_text(json.dumps(meta, indent=2))

    leakage = check_split_leakage(splits)
    (output_dir / "leakage_check.json").write_text(json.dumps(leakage, indent=2))
