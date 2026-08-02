#!/usr/bin/env python3
"""Rewrite verified literature parquet with flat columns matching MP/JARVIS staging format."""

from __future__ import annotations

from pathlib import Path

import pandas as pd
import pyarrow as pa
import pyarrow.parquet as pq


def flatten_struct(df: pd.DataFrame, col: str, prefix: str) -> pd.DataFrame:
    """Expand a struct/dict column into prefixed flat columns."""
    expanded = df[col].apply(lambda d: d if isinstance(d, dict) else {})
    expanded_df = expanded.apply(pd.Series)
    expanded_df.columns = [f"{prefix}.{c}" for c in expanded_df.columns]
    df = df.drop(columns=[col])
    for c in expanded_df.columns:
        df[c] = expanded_df[c].values
    return df


def main():
    path = Path("staging/verified_literature.parquet")
    if not path.exists():
        print(f"Not found: {path}")
        return

    df = pq.read_table(path).to_pandas()
    print(f"Original columns: {list(df.columns)}")

    # Flatten all struct columns
    for col in ["identity", "structure", "thermodynamics", "ion_transport",
                "mechanical", "synthesis", "ml_features", "text_provenance"]:
        if col in df.columns:
            df = flatten_struct(df, col, col)

    print(f"Flattened columns: {list(df.columns)}")

    # Ensure timestamp columns are tz-aware to match MP/JARVIS staging
    for col in df.columns:
        if df[col].dtype.kind == "M":  # datetime64
            if df[col].dt.tz is None:
                df[col] = df[col].dt.tz_localize("UTC")

    # Save back, replacing the original
    pq.write_table(pa.Table.from_pandas(df, preserve_index=False), path)
    print(f"Saved {len(df)} records to {path}")

    # Verify
    df2 = pq.read_table(path).to_pandas()
    nan_mid = df2.get("identity.material_id", pd.Series([None])).isna().sum()
    print(f"NaN material_id: {nan_mid}")
    print(f"Sample IDs: {list(df2['identity.material_id'].head(5))}")


if __name__ == "__main__":
    main()
