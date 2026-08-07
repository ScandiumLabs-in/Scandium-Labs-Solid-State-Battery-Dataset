#!/usr/bin/env python3
"""v0.9 — full-canonical quality scoring + anomalies + unit audit + experiments.

Scores every row of the canonical dataset (not just the approved literature
records) with the four-part quality block (`quality.score`, `.flags`,
`.confidence`, `.version`), runs the full-dataset anomaly scan and the
unit-normalization audit, and promotes the experimental rows into the
first-class experiments table.

Writes:
    quality_output/canonical_quality.parquet  — canonical + quality.* columns
    quality_output/canonical_quality_report.json — distribution summary
    validation_output/anomaly_report.json     — full-dataset consistency scan
    validation_output/unit_audit.json         — SI-normalization audit
    experiments_output/experiments.parquet    — first-class experiments table

Deterministic, network-free, no LLM calls.

    python scripts/build_canonical_quality.py
"""

from __future__ import annotations

import json
import sys
from collections import Counter
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from ssb_dataset.quality.anomalies import scan_anomalies  # noqa: E402
from ssb_dataset.quality.experiments import build_experiments_table  # noqa: E402
from ssb_dataset.quality.scoring import score_canonical_row  # noqa: E402
from ssb_dataset.quality.unit_audit import audit_units  # noqa: E402

CANONICAL = ROOT / "cleaning_output/canonical_dataset.parquet"
CONSENSUS = ROOT / "literature_output/consensus_db.json"
QUALITY_OUT = ROOT / "quality_output"
VALIDATION_OUT = ROOT / "validation_output"
EXPERIMENTS_OUT = ROOT / "experiments_output"


def _load_consensus() -> dict:
    if not CONSENSUS.exists():
        return {}
    try:
        return json.loads(CONSENSUS.read_text())
    except Exception:
        return {}


def _consensus_context(cons: dict, composition: str) -> dict:
    """Material-level consensus context injected for the experimental scorer
    (agreement grade, n_papers, outlier flag)."""
    c = cons.get(composition or "", {})
    ctx = {
        "quality.agreement_grade": c.get("agreement_grade", ""),
        "quality.n_papers": c.get("n_papers", 0),
    }
    outliers = {str(o.get("material") or o.get("composition") or "")
                for o in c.get("outliers", [])}
    ctx["quality.is_outlier"] = composition in outliers
    return ctx


def build_quality_frame() -> pd.DataFrame:
    df = pd.read_parquet(CANONICAL)
    cons = _load_consensus()
    score_cols = ["quality.score", "quality.grade", "quality.confidence",
                  "quality.version", "quality.tier", "quality.kind"]
    flags_col = "quality.flags"
    df[score_cols] = None
    df[flags_col] = None
    for idx in df.index:
        row = df.loc[idx].to_dict()
        ctx = _consensus_context(cons, str(row.get("identity.material_id", "") or ""))
        row.update(ctx)
        q = score_canonical_row(row)
        for k in score_cols:
            df.at[idx, k] = q[k]
        df.at[idx, flags_col] = json.dumps(q["quality.flags"])
    return df


def summarize(df: pd.DataFrame) -> dict:
    score = df["quality.score"].astype(float)
    return {
        "records_scored": int(len(df)),
        "score_avg": round(float(score.mean()), 1),
        "score_min": int(score.min()),
        "score_max": int(score.max()),
        "grade_distribution": dict(Counter(df["quality.grade"].tolist()).most_common()),
        "confidence_distribution": dict(
            Counter(df["quality.confidence"].tolist()).most_common()),
        "kind_distribution": dict(Counter(df["quality.kind"].tolist()).most_common()),
        "flagged_records": int(df["quality.flags"].apply(lambda f: bool(json.loads(f))).sum()),
        "by_source": {
            str(k): {
                "n": int(len(g)),
                "avg_score": round(float(g["quality.score"].astype(float).mean()), 1),
            }
            for k, g in df.groupby("identity.source_db")
        },
    }


def main() -> None:
    QUALITY_OUT.mkdir(exist_ok=True)
    VALIDATION_OUT.mkdir(exist_ok=True)
    EXPERIMENTS_OUT.mkdir(exist_ok=True)

    df = build_quality_frame()
    df.to_parquet(QUALITY_OUT / "canonical_quality.parquet", index=False)
    summary = summarize(df)
    (QUALITY_OUT / "canonical_quality_report.json").write_text(
        json.dumps(summary, indent=2, default=str))
    print(f"quality: {summary['records_scored']} records scored, "
          f"avg {summary['score_avg']}, flags on {summary['flagged_records']}")

    base = pd.read_parquet(CANONICAL)
    anomalies = scan_anomalies(base)
    (VALIDATION_OUT / "anomaly_report.json").write_text(
        json.dumps(anomalies, indent=2, default=str))
    print(f"anomalies: {anomalies['high_severity_checks_failing']} high-severity "
          f"checks failing ({'PASS' if anomalies['passed'] else 'FAIL'})")

    units = audit_units(base)
    (VALIDATION_OUT / "unit_audit.json").write_text(
        json.dumps(units, indent=2, default=str))
    print(f"units: {units['total_invalid']} invalid values "
          f"({'PASS' if units['passed'] else 'FAIL'})")

    exp = build_experiments_table(base)
    exp.to_parquet(EXPERIMENTS_OUT / "experiments.parquet", index=False)
    print(f"experiments: {len(exp)} experiment rows promoted")


if __name__ == "__main__":
    main()
