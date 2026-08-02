#!/usr/bin/env python3
"""Merge verified extraction records with existing staging data, run Phases 4-8."""

from __future__ import annotations

import sys
from pathlib import Path

import pandas as pd
import pyarrow as pa
import pyarrow.parquet as pq

from ssb_dataset.schema import MaterialRecord

# 1. Load verified records
verified_path = Path("cleaning_output/verified_canonical.parquet")
verified_df = pq.read_table(verified_path).to_pandas()
print(f"Verified records: {len(verified_df)}")

# 2. Load existing staging data (if any)
staging = Path("staging")
staging_records = []
if staging.exists():
    files = list(staging.rglob("*.parquet"))
    for f in files:
        staging_records.append(pq.read_table(f).to_pandas())
    if staging_records:
        staging_df = pd.concat(staging_records, ignore_index=True)
        print(f"Staging records: {len(staging_df)} from {len(files)} files")
    else:
        staging_df = pd.DataFrame()
else:
    staging_df = pd.DataFrame()

# 3. Merge: staging first, then verified (so verified records are appended)
if not staging_df.empty:
    # Drop verified material_ids from staging to avoid duplicates
    verified_ids = set(verified_df.get("identity.material_id", verified_df.get("material_id", [])))
    staging_col = "identity.material_id" if "identity.material_id" in staging_df.columns else "material_id"
    if staging_col in staging_df.columns:
        staging_df = staging_df[~staging_df[staging_col].isin(verified_ids)]
        print(f"Staging after dedup against verified: {len(staging_df)}")

# Ensure compatible columns by taking union of all columns
all_cols = list(dict.fromkeys(list(staging_df.columns) + list(verified_df.columns)))
for col in all_cols:
    if col not in staging_df.columns:
        staging_df[col] = None
    if col not in verified_df.columns:
        verified_df[col] = None

merged_df = pd.concat([staging_df[all_cols], verified_df[all_cols]], ignore_index=True)
print(f"Merged dataset: {len(merged_df)} records")
print(f"  With conductivity: {merged_df.get('ion_transport.sigma_RT', merged_df.get('sigma_RT', pd.Series())).notna().sum()}")

# 4. Run cleaning
print("\n=== Phase 4: Cleaning ===")
from ssb_dataset.pipeline.cleaning import run_cleaning, save_cleaning_report

report = run_cleaning(merged_df)
output_dir = Path("cleaning_output")
save_cleaning_report(report, output_dir / "cleaning_report.json")

save_path = output_dir / "canonical_dataset.parquet"
pq.write_table(pa.Table.from_pandas(merged_df), save_path)
print(f"Cleaning: {report.total_input} → {report.total_output}")
print(f"Arrhenius failures: {len(report.arrhenius_failures)}")
print(f"Missed data violations: {len(report.missing_data_report.silent_imputation_detected)}")
print(f"Passed: {report.passed}")

print("\n=== Dataset saved. Run phases via: python run.py <phase> ===")
print("  python run.py featurize")
print("  python run.py validate")
print("  python run.py docs")
print("  python run.py release")

# 8. Release check
print("\n=== Phase 9: Release Check ===")
from ssb_dataset.release import ReleaseManager

release = ReleaseManager().build_checklist(Path("."))
print(f"Release check:")
print(f"  Artifacts exist: {release.artifacts_exist}")
print(f"  Citation/datasheet present: {release.citation_cff_exists} / {release.datasheet_exists}")
print(f"  Human sign-off present: {release.human_signoff}")
print(f"  Validation passed: {release.validation_passed}")
print(f"  Gold benchmark exists: {release.gold_benchmark_exists}")
print(f"  Splits exist: {release.splits_exist}")
print(f"  Ready to release: {release.ready}")
if release.notes:
    print("  Notes:")
    for note in release.notes:
        print(f"    - {note}")

print("\n=== Done ===")
