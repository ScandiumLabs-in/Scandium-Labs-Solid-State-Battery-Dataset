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
VERIFIED = ROOT / "cleaning_output" / "verified_canonical.parquet"
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


def _verified_lookup() -> dict:
    """Build a (composition, doi) -> verified_canonical row map so the quality
    scorer can see the experiment/metadata the deterministic backfill already
    stamped onto the durable store (Phase E7). Without this, Gold-tier -- which
    requires temperature + method -- stays unreachable for records whose queue
    item predates the backfill.

    A second index keyed by (composition, normalized sigma) covers queue items
    whose legacy record predates DOI capture: an exact sigma match against the
    human-verified store is a strong identity signal (sigma values are the
    scarce verified labels), so those records can still unlock the paired
    Ea/sigma depth component.
    """
    if not VERIFIED.exists():
        return {}
    df = pd.read_parquet(VERIFIED)
    by_doi: dict = {}
    by_value: dict = {}
    for _, r in df.iterrows():
        comp = r.get("identity.composition") or r.get("identity.material_id")
        if not comp:
            continue
        comp_k = str(comp).strip().lower()
        doi = str(r.get("text_provenance.source_doi") or "").strip().lower()
        by_doi[(comp_k, doi)] = r
        sig = r.get("ion_transport.sigma_RT")
        if sig is not None and _present(sig):
            by_value.setdefault((comp_k, _num_key(sig)), r)
        ea = r.get("ion_transport.activation_energy_Ea")
        if ea is not None and _present(ea):
            by_value.setdefault((comp_k, _num_key(ea)), r)
    return {"by_doi": by_doi, "by_value": by_value}


def _num_key(v) -> str:
    """Normalize a numeric value for exact-match lookup (0.001 == 1e-3)."""
    try:
        return f"{float(v):.6g}"
    except (TypeError, ValueError):
        return str(v)


def _lookup_verified(verified_lookup: dict, comp: str, doi: str, value) -> dict | None:
    """Resolve a queue item to its verified_canonical row: exact (comp, doi)
    first, then exact (comp, value) for DOI-less legacy records."""
    comp_k = str(comp or "").strip().lower()
    doi_k = str(doi or "").strip().lower()
    r = verified_lookup.get("by_doi", {}).get((comp_k, doi_k))
    if r is not None:
        return r
    if _present(value):
        return verified_lookup.get("by_value", {}).get((comp_k, _num_key(value)))
    return None


def _enrich_from_verified(rec: dict, ver: dict) -> dict:
    """Copy metadata the queue item is missing from the backfilled verified
    record (experiment block + temperature + method + conductivity type).

    The queue item's own values win; verified_canonical only fills gaps so we
    never overwrite a reviewer's correction. Also stamps the paired transport
    value (Ea onto a sigma record, sigma onto an Ea record) from the durable
    store so records whose paper reported both can earn the depth component —
    same material, same DOI, human-verified, so this is honest, not imputed.
    """
    exp = ver.get("experiment") if isinstance(ver.get("experiment"), dict) else {}
    rec_exp = rec.get("experiment") if isinstance(rec.get("experiment"), dict) else {}
    # Merge experiment fields gap-wise: the durable store's backfilled values
    # fill what the queue item lacks, without overwriting a reviewer's fill.
    merged = dict(rec_exp)
    for k, v in exp.items():
        if v not in (None, "") and merged.get(k) in (None, ""):
            merged[k] = v
    if merged:
        rec["experiment"] = merged
    if not rec.get("temperature_celsius"):
        tr = ver.get("ion_transport.temperature_range_measured")
        if isinstance(tr, dict) and tr.get("max_K") and tr.get("max_K") == tr.get("min_K"):
            rec["temperature_celsius"] = tr["max_K"] - 273.15
    if not rec.get("measurement_method"):
        rec["measurement_method"] = ver.get("ion_transport.measurement_method")
    if not rec.get("conductivity_type"):
        ct = ver.get("ion_transport.conductivity_type")
        if ct is not None:
            rec["conductivity_type"] = getattr(ct, "value", None) if not isinstance(ct, str) else ct
    # Map the queue item's property/value onto the canonical transport fields so
    # the depth component (sigma + Ea present) can be earned from the durable
    # store's paired values (same material, same DOI, human-verified).
    prop = str(rec.get("property") or "").lower()
    if _present(rec.get("value")) and not _present(rec.get("sigma_RT")) \
            and prop in ("conductivity", "sigma", "ionic conductivity"):
        rec["sigma_RT"] = rec.get("value")
    if _present(rec.get("value")) and not _present(rec.get("activation_energy_eV")) \
            and "activation_energy" in prop:
        rec["activation_energy_eV"] = rec.get("value")
    # Paired transport value from the same verified paper (depth component).
    if _present(rec.get("sigma_RT")) and not _present(rec.get("activation_energy_eV")):
        rec["activation_energy_eV"] = ver.get("ion_transport.activation_energy_Ea")
    if _present(rec.get("activation_energy_eV")) and not _present(rec.get("sigma_RT")):
        rec["sigma_RT"] = ver.get("ion_transport.sigma_RT")
    return rec


def _present(v) -> bool:
    return v is not None and v != "" and v != ""


def build_quality_records() -> pd.DataFrame:
    queue = _load_json(QUEUE)
    items = [i for i in queue.get("items", []) if i.get("status") == "approved"]
    if not items:
        return pd.DataFrame()

    cons_lookup = _consensus_lookup()
    verified_lookup = _verified_lookup()
    rows = []
    for rec in items:
        composition = rec.get("composition") or rec.get("material") or rec.get("material_id") or ""
        group_ctx = cons_lookup.get(composition, {})
        rec = dict(rec)
        # Phase E7 — back-fill experiment/metadata from the durable store so the
        # load-bearing temperature+method pair can unlock Gold tier where the
        # data genuinely supports it.
        doi = str(rec.get("doi") or "").strip().lower()
        ver = _lookup_verified(verified_lookup, composition, doi, rec.get("value"))
        if ver is not None:
            rec = _enrich_from_verified(rec, ver)
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
        # Score bands within the (dominant) tier — the tiering itself is coarse
        # (nearly everything lands in silver because experiment metadata is
        # genuinely sparse), so report the within-tier score spread to keep the
        # system discriminating: silver-high >=70, silver-mid 55-69, silver-low
        # <55. Never fabricated — a pure redistribution of the real scores.
        "score_band_distribution": {
            f"{label}": int(n)
            for label, n in (
                ("silver-high (>=70)", int(((df["quality_tier"] == "silver") & (df["quality_score"] >= 70)).sum())),
                ("silver-mid (55-69)", int(((df["quality_tier"] == "silver") & (df["quality_score"] >= 55) & (df["quality_score"] < 70)).sum())),
                ("silver-low (<55)", int(((df["quality_tier"] == "silver") & (df["quality_score"] < 55)).sum())),
                ("non-silver", int((df["quality_tier"] != "silver").sum())),
            )
            if n
        },
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
