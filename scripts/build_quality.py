"""A3/A4 — stamp record-level quality scores + Gold/Silver/Bronze tiers.

Reads the review-queue approved records and the consensus DB, computes a
deterministic 0-100 quality score + letter grade + tier for every verified
experimental record, and writes:

    quality_output/quality.parquet   — one row per approved record
    quality_output/quality_report.json — distribution summary + per-family stats

Network-free and deterministic — no LLM calls. Usage:

    python scripts/build_quality.py
"""

from __future__ import annotations

import json
from collections import Counter
from pathlib import Path

import pandas as pd

from ssb_dataset.literature.record_quality import QualityTier, score_record

ROOT = Path(__file__).resolve().parent.parent
QUEUE = ROOT / "review_output" / "queue.json"
CONSENSUS = ROOT / "literature_output" / "consensus_db.json"
OUT_DIR = ROOT / "quality_output"


def _load_json(path: Path) -> dict:
    if path.exists():
        try:
            return json.loads(path.read_text())
        except Exception:
            return {}
    return {}


def _consensus_lookup() -> dict[str, dict]:
    """Material-level consensus context (agreement grade, n_papers, outliers)."""
    cons = _load_json(CONSENSUS)
    out: dict[str, dict] = {}
    for group, c in cons.items():
        out[group] = {
            "agreement_grade": c.get("agreement_grade", ""),
            "n_papers": c.get("n_papers", 0),
            "n_sigma": c.get("n_sigma", 0),
        }
        # Outlier composition keys from the group's outlier records.
        out[group]["outlier_materials"] = {
            str(o.get("material") or o.get("composition") or "") for o in c.get("outliers", [])
        }
    return out


def build_quality_records() -> pd.DataFrame:
    queue = _load_json(QUEUE)
    items = [i for i in queue.get("items", []) if i.get("status") == "approved"]
    if not items:
        return pd.DataFrame()

    cons_lookup = _consensus_lookup()
    rows = []
    for rec in items:
        composition = rec.get("composition") or rec.get("material") or rec.get("material_id") or ""
        group_ctx = cons_lookup.get(composition, {})
        rec = dict(rec)
        # Inject material-level context so the record score can reward agreement.
        rec.setdefault("agreement_grade", group_ctx.get("agreement_grade", ""))
        rec.setdefault("n_papers", group_ctx.get("n_papers", 0))
        is_outlier = composition in group_ctx.get("outlier_materials", set())
        rec.setdefault("is_outlier", is_outlier)
        q = score_record(rec)
        row = {
            "review_id": rec.get("review_id", ""),
            "composition": composition,
            "family": rec.get("family", ""),
            "doi": rec.get("doi", ""),
            "property": rec.get("property", ""),
            "value": rec.get("value"),
            "unit": rec.get("unit", ""),
            "reviewer": rec.get("reviewer", ""),
            "quality_score": q["quality_score"],
            "quality_grade": q["quality_grade"],
            "quality_tier": q["quality_tier"].value,
            "quality_components": json.dumps(q["quality_components"]),
            "quality_notes": json.dumps(q["quality_notes"]),
            "human_verified": bool(rec.get("reviewer")),
        }
        rows.append(row)

    df = pd.DataFrame(rows)
    df = df.sort_values("quality_score", ascending=False).reset_index(drop=True)
    return df


def summarize(df: pd.DataFrame) -> dict:
    if df.empty:
        return {"records": 0}
    summary: dict = {
        "records": int(len(df)),
        "score_avg": round(float(df["quality_score"].mean()), 1),
        "score_min": int(df["quality_score"].min()),
        "score_max": int(df["quality_score"].max()),
        "grade_distribution": dict(Counter(df["quality_grade"].tolist()).most_common()),
        "tier_distribution": dict(Counter(df["quality_tier"].tolist()).most_common()),
        "tier_pct": {
            t.value: round(float((df["quality_tier"] == t.value).mean() * 100), 1)
            for t in QualityTier
        },
        "gold_records": int((df["quality_tier"] == "gold").sum()),
        "silver_records": int((df["quality_tier"] == "silver").sum()),
        "bronze_records": int((df["quality_tier"] == "bronze").sum()),
        "rejected_records": int((df["quality_tier"] == "rejected").sum()),
    }
    summary["family_scores"] = {
        str(k): {
            "n": int(len(g)),
            "avg_score": round(float(g["quality_score"].mean()), 1),
            "tiers": dict(Counter(g["quality_tier"].tolist()).most_common()),
        }
        for k, g in df.groupby("family")
    }
    return summary


def main() -> None:
    OUT_DIR.mkdir(exist_ok=True)
    df = build_quality_records()
    df.to_parquet(OUT_DIR / "quality.parquet", index=False)
    summary = summarize(df)
    (OUT_DIR / "quality_report.json").write_text(
        json.dumps(summary, indent=2, default=str)
    )
    print(f"wrote quality_output/quality.parquet ({len(df)} records)")
    print(f"  avg score: {summary.get('score_avg')}  tiers: {summary.get('tier_distribution')}")


if __name__ == "__main__":
    main()
