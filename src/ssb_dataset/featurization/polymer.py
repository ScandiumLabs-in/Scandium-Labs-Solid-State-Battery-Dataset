"""Family 8 (polymer/composite) parallel featurization path.

Standard crystal-graph representation does not apply to polymer electrolytes.
This module provides an alternative featurization using composition-weighted
descriptors plus processing metadata.
"""

from __future__ import annotations

import re
from typing import Any

import pandas as pd

from ssb_dataset.schema import Family


def _is_polymer_family(df: pd.DataFrame) -> pd.Series:
    """Identify rows belonging to polymer/composite family."""
    family_col = None
    for c in ["identity.family", "family"]:
        if c in df.columns:
            family_col = c
            break
    if family_col is None:
        return pd.Series([False] * len(df), index=df.index)

    return df[family_col].astype(str).str.lower().isin([
        Family.polymer_composite.value,
        "polymer",
        "polymer_composite",
        "composite",
        "polymer/ceramic",
    ])


def featurize_polymer_records(df: pd.DataFrame) -> pd.DataFrame:
    """Apply polymer-specific featurization.

    For polymer/composite records, standard crystal-graph featurization is not
    applicable. Instead, we use:
      - Composition-weighted elemental descriptors (from features.py)
      - Processing metadata (synthesis route, processing conditions)
      - Polymer-specific derived features (salt-to-polymer ratio if applicable)
    """
    polymer_mask = _is_polymer_family(df)

    df["is_polymer"] = polymer_mask.values

    if not polymer_mask.any():
        return df

    p_frac_col = "ion_transport.polymer_salt_ratio"
    for c in ["polymer_salt_ratio", p_frac_col]:
        if c in df.columns:
            df.loc[polymer_mask, "polymer_salt_ratio_extracted"] = df.loc[polymer_mask, c]

    synth_cols = [c for c in df.columns if "synthesis" in c.lower()]
    if synth_cols:
        df.loc[polymer_mask, "has_synthesis_info"] = df.loc[polymer_mask, synth_cols[0]].notna()

    return df


def is_graph_compatible(family_value: str) -> bool:
    """Check if a family is compatible with standard crystal-graph featurization."""
    return family_value.lower() != Family.polymer_composite.value


def polymer_feature_columns() -> list[str]:
    """Return the list of feature columns available for polymer records."""
    return [
        "is_polymer",
        "polymer_salt_ratio_extracted",
        "has_synthesis_info",
        "n_elements",
        "frac_s_block",
        "frac_p_block",
        "frac_d_block",
        "frac_f_block",
    ]
