#!/usr/bin/env python3
"""Merge cross-database validation blocks into the canonical dataset.

Phase A of the v1.4 release: every MP/JARVIS canonical row whose reduced
formula exists in the other database receives:

  validation.database_count       # distinct sources for this composition
  validation.agreement_score      0..1 cross-database agreement
  validation.disagreement         per-property {agreement, abs_dev, mp, jarvis}
  validation.rank                 agreement rank within the composition
                                  (1 = best-agreeing record for that formula)

Sources without comparable data (NOMAD, COD, AFLOW, OQMD) stay database_count
= 0 / score None — never imputed. Rows in neither database (literature-verified
without an MP/JARVIS structure) also stay None.

Output: validation_output/canonical_validation.parquet (canonical + validation.*)
        validation_output/validation_report.json
"""

from __future__ import annotations

import json
from pathlib import Path

import pandas as pd

from ssb_dataset.validation import cross_db

ROOT = Path(__file__).resolve().parent.parent
CANONICAL = ROOT / "cleaning_output/canonical_dataset.parquet"
VALIDATION_OUT = ROOT / "validation_output"


def build_validation_frame() -> pd.DataFrame:
    canon = pd.read_parquet(CANONICAL)
    vdf = pd.read_parquet(VALIDATION_OUT / "cross_db_validation.parquet")
    for col in ("database_count", "agreement_score", "disagreement", "rank"):
        canon[f"validation.{col}"] = None
    if vdf.empty:
        canon["validation.database_count"] = 0
        return canon
    join = vdf[["material_id", "database_count", "agreement_score",
                "disagreement", "rank"]]
    merged = canon.merge(join, how="left",
                         left_on="identity.material_id", right_on="material_id",
                         suffixes=("", "_v"))
    # raise silently-present nulls to the explicit None convention
    merged["database_count"] = merged["database_count"].fillna(0).astype(int)
    merged["agreement_score"] = merged["agreement_score"].where(
        merged["database_count"] >= 2)
    merged["rank"] = merged["rank"].where(merged["database_count"] >= 2)
    for col in ("database_count", "agreement_score", "disagreement", "rank"):
        canon[f"validation.{col}"] = merged[col]
    return canon


def summarize(canon: pd.DataFrame) -> dict:
    vcount = canon["validation.database_count"].fillna(0)
    scored = canon["validation.agreement_score"].dropna()
    by_source = {}
    for src, g in canon.groupby("identity.source_db"):
        s = g["validation.agreement_score"].dropna()
        by_source[str(src)] = {
            "records": int(len(g)),
            "validated": int(g["validation.database_count"].fillna(0).ge(2).sum()),
            "avg_agreement": (round(float(s.mean()), 4) if len(s) else None),
        }
    return {
        "canonical_records": int(len(canon)),
        "records_validated": int(vcount.ge(2).sum()),
        "compositions_validated": int(
            canon.loc[scored.index, "identity.composition"].nunique()),
        "database_count_distribution": dict(
            vcount.astype(int).value_counts().sort_index().to_dict()),
        "mean_agreement_scored": (round(float(scored.mean()), 4)
                                  if len(scored) else None),
        "by_source": by_source,
        "convention": ("database_count=0 / agreement_score=None means the row "
                       "has no comparable counterpart in another bundled "
                       "database; never imputed."),
    }


def main() -> None:
    VALIDATION_OUT.mkdir(exist_ok=True)
    cross_db.main()
    canon = build_validation_frame()
    canon.to_parquet(VALIDATION_OUT / "canonical_validation.parquet", index=False)
    summary = summarize(canon)
    (VALIDATION_OUT / "validation_report.json").write_text(
        json.dumps(summary, indent=2, default=str))
    print(json.dumps(summary, indent=2))


if __name__ == "__main__":
    main()
