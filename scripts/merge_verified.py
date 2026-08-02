#!/usr/bin/env python3
"""Merge verified extraction records with existing staging, flatten struct columns properly."""

from __future__ import annotations

from pathlib import Path

import pandas as pd
import pyarrow as pa
import pyarrow.parquet as pq


def _flatten_dict_col(df: pd.DataFrame, col: str, prefix: str) -> pd.DataFrame:
    """Expand a dict column into prefixed columns, preserving existing flat columns.

    No-op when the column is absent (already flattened) or not a dict column.
    """
    if col not in df.columns:
        return df
    first = df[col].dropna()
    if first.empty or not isinstance(first.iloc[0], dict):
        return df
    expanded = df[col].apply(lambda d: d if isinstance(d, dict) else {})
    expanded_df = expanded.apply(pd.Series)
    expanded_df.columns = [f"{prefix}.{c}" for c in expanded_df.columns]
    # Only fill NaN where flat column doesn't exist yet
    for c in expanded_df.columns:
        if c in df.columns:
            df[c] = df[c].fillna(expanded_df[c])
        else:
            df[c] = expanded_df[c]
    return df


def merge_datasets(verified_path: Path, staging_dir: Path, output_path: Path) -> pd.DataFrame:
    vdf = pq.read_table(verified_path).to_pandas()
    print(f"Verified records: {len(vdf)}")

    staging_dfs = []
    if staging_dir.exists():
        files = list(staging_dir.rglob("*.parquet"))
        for f in files:
            staging_dfs.append(pq.read_table(f).to_pandas())
        sdf = pd.concat(staging_dfs, ignore_index=True) if staging_dfs else pd.DataFrame()
        print(f"Staging records: {len(sdf)} from {len(files)} files")
    else:
        sdf = pd.DataFrame()
        print("No staging dir found")

    if sdf.empty:
        merged = vdf.copy()
    else:
        # Flatten verified dict columns into staging's flat column structure
        vdf = _flatten_dict_col(vdf, "identity", "identity")
        vdf = _flatten_dict_col(vdf, "ion_transport", "ion_transport")
        vdf = _flatten_dict_col(vdf, "structure", "structure")
        vdf = _flatten_dict_col(vdf, "text_provenance", "text_provenance")

        # Deduplicate: drop staging records whose material_id appears in verified
        mid_col = "identity.material_id"
        if mid_col in sdf.columns and mid_col in vdf.columns:
            verified_ids = set(vdf[mid_col].dropna().unique())
            before = len(sdf)
            sdf = sdf[~sdf[mid_col].isin(verified_ids)]
            print(f"  Deduplicated: removed {before - len(sdf)} staging records with matching verified IDs")

        all_cols = list(dict.fromkeys(list(sdf.columns) + list(vdf.columns)))
        for col in all_cols:
            if col not in sdf.columns:
                sdf[col] = None
            if col not in vdf.columns:
                vdf[col] = None
        merged = pd.concat([sdf[all_cols], vdf[all_cols]], ignore_index=True)

    print(f"Merged: {len(merged)} records")
    sigma_count = merged.get("ion_transport.sigma_RT", pd.Series([None])).notna().sum()
    ea_count = merged.get("ion_transport.activation_energy_Ea", pd.Series([None])).notna().sum()
    mid_nan = merged.get("identity.material_id", pd.Series([None])).isna().sum()
    print(f"  With sigma_RT: {sigma_count}")
    print(f"  With Ea: {ea_count}")
    print(f"  NaN material_id: {mid_nan}")

    output_path.parent.mkdir(parents=True, exist_ok=True)
    pq.write_table(pa.Table.from_pandas(merged), output_path)
    print(f"Saved to {output_path}")
    return merged


if __name__ == "__main__":
    merge_datasets(
        verified_path=Path("cleaning_output/verified_canonical.parquet"),
        staging_dir=Path("staging"),
        output_path=Path("cleaning_output/canonical_dataset.parquet"),
    )
