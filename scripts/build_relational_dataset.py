"""v1.2 — build the relational dataset.

Reads the canonical dataset + quality output and writes seven first-class
parquet tables to relational_output/:

    materials.parquet     one row per material (full catalog, curated core cols)
    papers.parquet        one row per paper DOI in the experimental core, with
                          title/journal/year backfilled from on-disk caches +
                          PDF first pages (deterministic, Phase 10)
    authors.parquet       recovered authors per paper (paper_id -> author)
    experiments.parquet   one material measured under one condition set in one
                          paper (deterministic experiment_id)
    measurements.parquet  every σ / Ea / σ60C / σ80C value as its own row with
                          per-field confidence (value/temperature/method/
                          evidence) + the full evidence chain
    synthesis.parquet     synthesis conditions per material+paper (sparse)
    dopants.parquet       explicit dopant annotations (e.g. Li7La3Zr2O12:Ta)

Also writes:
    validation_output/schema_report.json        per-table schema + row counts
    validation_output/provenance_report.json    measurement-level provenance
    validation_output/missing_value_report.json per-table per-column coverage

Deterministic: ids are stable hashes of identity fields; re-runs produce
identical tables. No network, no LLM.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

import pandas as pd

from ssb_dataset.db import build as rel

ROOT = Path(__file__).resolve().parent.parent
OUT = ROOT / "relational_output"
VAL = ROOT / "validation_output"


def _cols(df: pd.DataFrame) -> list[str]:
    return list(df.columns)


def write_schema_report(tables: dict[str, pd.DataFrame]) -> dict:
    report = {
        "tables": {},
        "relationships": {
            "material_has_experiments": "materials.material_id -> experiments.material_id",
            "paper_has_experiments": "papers.paper_id -> experiments.paper_id",
            "paper_has_authors": "papers.paper_id -> authors.paper_id",
            "experiment_has_measurements": "experiments.experiment_id -> measurements.experiment_id",
            "experiment_has_synthesis": "experiments.synthesis_id -> synthesis.synthesis_id",
            "material_has_dopants": "materials.material_id -> dopants.material_id",
        },
    }
    for name, df in tables.items():
        report["tables"][name] = {
            "rows": int(len(df)),
            "columns": _cols(df),
            "null_counts": {c: int(df[c].isna().sum()) for c in df.columns
                            if len(df) > 0 and c not in ("elements",)},
        }
    return report


def write_provenance_report(measurements: pd.DataFrame) -> dict:
    """Per-measurement provenance coverage: how many measurements carry the
    paper / page / sentence / reviewer / confidence chain."""
    n = len(measurements)
    if n == 0:
        return {"measurements": 0, "coverage": {}}
    coverage = {
        "paper_id": int(measurements["paper_id"].notna().sum()),
        "evidence_page": int(measurements["evidence_page"].notna().sum()),
        "evidence_sentence": int(measurements["evidence_sentence"].notna().sum()),
        "reviewer": int(measurements["reviewer"].notna().sum()),
        "confidence": int(measurements["confidence"].notna().sum()),
        "measurement_method": int(measurements["measurement_method"].notna().sum()),
        "temperature": int(measurements["temperature_c"].notna().sum()),
    }
    return {
        "measurements": n,
        "coverage": {k: round(100 * v / n, 1) for k, v in coverage.items()},
    }


def write_missing_value_report(tables: dict[str, pd.DataFrame]) -> dict:
    report = {}
    for name, df in tables.items():
        report[name] = {}
        for c in df.columns:
            if len(df) == 0:
                continue
            missing = int(df[c].isna().sum())
            if missing == 0:
                continue
            pct = round(100 * missing / len(df), 1)
            report[name][c] = {"missing": missing, "pct": pct}
    return report


def build() -> dict:
    tables = rel.build_relational()
    OUT.mkdir(exist_ok=True)
    VAL.mkdir(exist_ok=True)

    for name, df in tables.items():
        df.to_parquet(OUT / f"{name}.parquet", index=False)

    schema_report = write_schema_report(tables)
    (VAL / "schema_report.json").write_text(json.dumps(schema_report, indent=2, default=str))

    prov = write_provenance_report(tables["measurements"])
    (VAL / "provenance_report.json").write_text(json.dumps(prov, indent=2, default=str))

    missing = write_missing_value_report(tables)
    (VAL / "missing_value_report.json").write_text(json.dumps(missing, indent=2, default=str))

    summary = {
        "tables": {name: int(len(df)) for name, df in tables.items()},
        "provenance": prov,
    }
    (OUT / "relational_report.json").write_text(json.dumps(summary, indent=2, default=str))
    return summary


if __name__ == "__main__":
    summary = build()
    print(json.dumps(summary, indent=2, default=str))
    sys.exit(0)
