"""Phase C — Dataset health report (coverage, drift, missing-data).

Computes the release-gate metrics for Scandium Dataset v1.0:

  - Coverage % per field (temperature, pressure, density, method, evidence,
    conductivity type, confidence tier) over the verified experimental set.
  - Distribution drift: family balance, publication years, measurement
    temperatures, methods, journals.
  - Missing-data report with per-field gaps.
  - Dataset-wide metrics (materials, sigma/Ea counts, consensus, agreement
    distribution, benchmark count, quality scores).

Writes `literature_output/health_report.md` (+ a machine-readable
`health_report.json`). Network-free and deterministic — no LLM calls.
"""

from __future__ import annotations

import json
from collections import Counter
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parent.parent
CANONICAL = ROOT / "cleaning_output" / "canonical_dataset.parquet"
CONSENSUS = ROOT / "literature_output" / "consensus_db.json"
CARDS = ROOT / "literature_output" / "material_cards.json"
QUEUE = ROOT / "review_output" / "queue.json"
QUALITY = ROOT / "quality_output" / "quality.parquet"
OUT_MD = ROOT / "literature_output" / "health_report.md"
OUT_JSON = ROOT / "literature_output" / "health_report.json"

EXPERIMENT_FIELDS = [
    ("temperature_celsius", "temperature_range_measured", "ion_transport"),
    ("measurement_method", "measurement_method", "ion_transport"),
    ("conductivity_type", "conductivity_type", "ion_transport"),
    ("pelletizing_pressure_MPa", "pelletizing_pressure_MPa", "experiment"),
    ("relative_density_pct", "relative_density_pct", "experiment"),
    ("theoretical_density_g_per_cm3", "theoretical_density_g_per_cm3", "experiment"),
    ("electrode_material", "electrode_material", "experiment"),
    ("atmosphere", "atmosphere", "experiment"),
    ("sample_form", "sample_form", "experiment"),
    ("frequency_max_Hz", "frequency_max_Hz", "experiment"),
    ("sinter_temperature_C", "sinter_temperature_C", "experiment"),
    ("sinter_time_h", "sinter_time_h", "experiment"),
    ("page", "text_provenance.evidence_page", "raw"),
    ("evidence_sentence", "text_provenance.evidence_sentence", "raw"),
]


def _row_field(row: pd.Series, field: str, scope: str) -> bool:
    if scope == "ion_transport":
        col = f"ion_transport.{field}"
    elif scope == "experiment":
        exp = row.get("experiment")
        if isinstance(exp, dict):
            return exp.get(field) is not None and exp.get(field) != ""
        return False
    else:
        col = field
    v = row.get(col)
    if v is None:
        return False
    s = str(v)
    return s != "" and s.lower() != "nan" and s.lower() != "none"


def coverage(df: pd.DataFrame) -> dict[str, float]:
    """Per-field coverage % over the verified labelled subset."""
    labelled = df[df.get("ion_transport.label_available", pd.Series(False, index=df.index)) == True]
    if len(labelled) == 0:
        return {}
    out = {}
    for label, field, scope in EXPERIMENT_FIELDS:
        present = sum(_row_field(r, field, scope) for _, r in labelled.iterrows())
        out[label] = round(present / len(labelled) * 100, 1)
    return out


def family_balance(df: pd.DataFrame) -> dict[str, int]:
    labelled = df[df.get("ion_transport.label_available", pd.Series(False, index=df.index)) == True]
    fam = labelled.get("identity.family")
    if fam is None:
        return {}
    return dict(Counter(fam.fillna("unknown").tolist()).most_common())


def _load_json(path: Path) -> dict:
    if path.exists():
        try:
            return json.loads(path.read_text())
        except Exception:
            return {}
    return {}


def build_health_report() -> dict:
    report: dict = {}

    # ---- Coverage + balance over the verified experimental set ----
    if CANONICAL.exists():
        df = pd.read_parquet(CANONICAL)
        labelled = df[df.get("ion_transport.label_available", pd.Series(False, index=df.index)) == True]
        report["total_records"] = int(len(df))
        report["verified_records"] = int(len(labelled))
        report["coverage"] = coverage(df)
        report["family_balance"] = family_balance(df)
        # Conductivity type split (bulk / GB / total / thin film / composite...)
        ct = labelled.get("ion_transport.conductivity_type")
        if ct is not None:
            report["conductivity_type_split"] = dict(Counter(ct.fillna("unknown").astype(str).tolist()).most_common())
    else:
        report["total_records"] = 0
        report["verified_records"] = 0
        report["coverage"] = {}

    # ---- Consensus DB health ----
    consensus = _load_json(CONSENSUS)
    report["materials_total"] = len(consensus)
    report["materials_with_consensus_n3"] = sum(1 for v in consensus.values() if v.get("n_sigma", 0) >= 3)
    # Action 5 — depth-vs-breadth ratio: n≥3 consensus materials per verified
    # label. A shrinking ratio as volume scales means breadth without depth.
    n3 = report["materials_with_consensus_n3"]
    verified = report.get("verified_records", 0)
    report["consensus_depth_ratio"] = round(n3 / verified, 4) if verified else 0.0
    report["materials_with_sigma"] = sum(1 for v in consensus.values() if v.get("n_sigma", 0) > 0)
    report["materials_with_ea"] = sum(1 for v in consensus.values() if v.get("n_ea", 0) > 0)
    report["materials_with_multipaper"] = sum(1 for v in consensus.values() if v.get("n_papers", 0) >= 2)
    report["total_sigma_records"] = sum(v.get("n_sigma", 0) for v in consensus.values())
    report["total_ea_records"] = sum(v.get("n_ea", 0) for v in consensus.values())
    report["outlier_records"] = sum(len(v.get("outliers", [])) for v in consensus.values())
    # Agreement grade distribution
    report["agreement_grade_distribution"] = dict(Counter(
        (v.get("agreement_grade") or "") for v in consensus.values()
    ).most_common())
    # Publication year coverage
    n_years = sum(1 for v in consensus.values() if v.get("publication_years"))
    report["materials_with_pub_years"] = n_years
    report["pub_years_coverage_pct"] = round(n_years / len(consensus) * 100, 1) if consensus else 0.0
    # Temperature-aware consensus coverage (sigma_by_temp non-empty)
    n_sbt = sum(1 for v in consensus.values() if v.get("sigma_by_temp"))
    report["materials_with_sigma_by_temp"] = n_sbt

    # ---- Quality-score distribution ----
    cards = _load_json(CARDS)
    qs = [c.get("quality_score") for c in cards.values() if c.get("quality_score") is not None]
    if qs:
        report["quality_score_avg"] = round(sum(qs) / len(qs), 1)
        report["quality_score_min"] = min(qs)
        report["quality_score_max"] = max(qs)
        report["quality_grade_distribution"] = dict(Counter(
            c.get("quality_grade", "") for c in cards.values() if c.get("quality_grade")
        ).most_common())

    # ---- Review queue health ----
    queue = _load_json(QUEUE)
    items = queue.get("items", [])
    report["queue_items"] = len(items)
    report["queue_pending"] = sum(1 for i in items if i.get("status") == "pending")
    report["queue_approved"] = sum(1 for i in items if i.get("status") == "approved")
    report["queue_rejected"] = sum(1 for i in items if i.get("status") == "rejected")
    # Records carrying the experiment block
    report["queue_with_experiment_block"] = sum(1 for i in items if i.get("experiment"))

    # ---- Record-level quality distribution (A3/A4) ----
    report["quality"] = _quality_summary()

    # ---- Missing-data recommendations (C4) ----
    report["missing_data_recommendations"] = _missing_recommendations(items)

    # ---- Drift vs previous health report (C2) ----
    report["drift"] = _drift_vs_previous(report)

    return report


def _quality_summary() -> dict:
    """A3/A4 record-level quality distribution from quality_output/quality.parquet."""
    if not QUALITY.exists():
        return {"records": 0}
    try:
        df = pd.read_parquet(QUALITY)
    except Exception:
        return {"records": 0}
    if df.empty:
        return {"records": 0}
    out: dict = {
        "records": int(len(df)),
        "avg_score": round(float(df["quality_score"].mean()), 1),
        "grade_distribution": dict(Counter(df["quality_grade"].tolist()).most_common()),
        "tier_distribution": dict(Counter(df["quality_tier"].tolist()).most_common()),
    }
    gold = int((df["quality_tier"] == "gold").sum())
    silver = int((df["quality_tier"] == "silver").sum())
    bronze = int((df["quality_tier"] == "bronze").sum())
    rejected = int((df["quality_tier"] == "rejected").sum())
    out["gold_records"] = gold
    out["silver_records"] = silver
    out["bronze_records"] = bronze
    out["rejected_records"] = rejected
    out["gold_pct"] = round(gold / len(df) * 100, 1) if len(df) else 0.0
    return out


_MISSING_FIELDS = [
    "pelletizing_pressure_MPa",
    "relative_density_pct",
    "theoretical_density_g_per_cm3",
    "pellet_diameter_mm",
    "thickness_mm",
    "electrode_material",
    "atmosphere",
    "humidity",
    "sample_form",
    "frequency_max_Hz",
    "sinter_temperature_C",
    "sinter_time_h",
    "annealing_temperature_C",
    "instrument",
    "equivalent_circuit",
    "dc_bias_V",
]


def _missing_recommendations(items: list[dict]) -> dict[str, dict]:
    """C4 — for each experiment field, list which approved records lack it so the
    curation queue knows exactly what to backfill next."""
    approved = [i for i in items if i.get("status") == "approved"]
    if not approved:
        return {}
    recommendations: dict[str, dict] = {}
    for field in _MISSING_FIELDS:
        lacking = []
        for rec in approved:
            exp = rec.get("experiment")
            exp_v = exp.get(field) if isinstance(exp, dict) else None
            direct = rec.get(field)
            if (exp_v is None or exp_v == "") and (direct is None or direct == ""):
                lacking.append(rec.get("review_id") or rec.get("composition") or "?")
        recommendations[field] = {
            "missing_count": len(lacking),
            "missing_pct": round(len(lacking) / len(approved) * 100, 1),
            "top_records": lacking[:10],
        }
    return recommendations


def _drift_vs_previous(report: dict) -> dict:
    """C2 — compare this run against the previous health_report.json snapshot.

    Flags distribution drift in family balance, verified-record count, and
    coverage. No baseline stored yet -> records a `baseline` note so the next
    run can diff against this one."""
    prev = _load_json(OUT_JSON)
    if not prev or not prev.get("verified_records"):
        return {"baseline_established": True, "note": "no previous snapshot — this run becomes the baseline"}

    drift: dict = {}
    prev_cov = prev.get("coverage", {})
    cur_cov = report.get("coverage", {})
    cov_drift = {}
    for k in set(prev_cov) | set(cur_cov):
        d = cur_cov.get(k, 0.0) - prev_cov.get(k, 0.0)
        if abs(d) > 5.0:
            cov_drift[k] = round(d, 1)
    if cov_drift:
        drift["coverage_drift_gt_5pct"] = cov_drift

    prev_fam = prev.get("family_balance", {})
    cur_fam = report.get("family_balance", {})
    fam_drift = {
        k: (cur_fam.get(k, 0) - prev_fam.get(k, 0))
        for k in set(prev_fam) | set(cur_fam)
        if abs(cur_fam.get(k, 0) - prev_fam.get(k, 0)) > 2
    }
    if fam_drift:
        drift["family_drift_gt_2"] = fam_drift

    drift["record_count_change"] = report.get("verified_records", 0) - prev.get("verified_records", 0)
    drift["baseline_records"] = prev.get("verified_records", 0)
    return drift


def _pct_bar(pct: float, width: int = 20) -> str:
    filled = int(round(pct / 100 * width))
    return "█" * filled + "░" * (width - filled)


def render_markdown(report: dict) -> str:
    lines: list[str] = []
    lines.append("# Scandium Dataset — Health Report")
    lines.append("")
    lines.append("Auto-generated; deterministic (no LLM). Coverage is measured over the")
    lines.append("**verified experimental subset** (`ion_transport.label_available`).")
    lines.append("")
    lines.append(f"- Verified experimental records: **{report.get('verified_records', 0)}**")
    lines.append(f"- Queue: {report.get('queue_items', 0)} items "
                 f"({report.get('queue_pending', 0)} pending / "
                 f"{report.get('queue_approved', 0)} approved / "
                 f"{report.get('queue_rejected', 0)} rejected)")
    lines.append(f"- Queue items carrying experiment block: **{report.get('queue_with_experiment_block', 0)}**")
    lines.append("")

    # Coverage
    lines.append("## Field coverage (verified records)")
    lines.append("")
    lines.append("| Field | Coverage |")
    lines.append("|---|---|")
    for field, pct in report.get("coverage", {}).items():
        lines.append(f"| {field} | {pct:5.1f}% {_pct_bar(pct)} |")
    lines.append("")

    # Missing-data report
    cov = report.get("coverage", {})
    missing = {k: round(100 - v, 1) for k, v in cov.items() if v < 100}
    lines.append("## Missing-data report")
    lines.append("")
    if missing:
        lines.append("| Field | Missing |")
        lines.append("|---|---|")
        for field, pct in sorted(missing.items(), key=lambda kv: -kv[1]):
            lines.append(f"| {field} | {pct:5.1f}% |")
    else:
        lines.append("No missing fields — full coverage.")
    lines.append("")

    # Family balance
    lines.append("## Family balance (verified records)")
    lines.append("")
    lines.append("| Family | Records |")
    lines.append("|---|---|")
    for fam, n in report.get("family_balance", {}).items():
        lines.append(f"| {fam} | {n} |")
    lines.append("")

    # Conductivity type split
    if report.get("conductivity_type_split"):
        lines.append("## Conductivity type split")
        lines.append("")
        lines.append("| Type | Records |")
        lines.append("|---|---|")
        for t, n in report["conductivity_type_split"].items():
            lines.append(f"| {t} | {n} |")
        lines.append("")

    # Consensus health
    lines.append("## Consensus health")
    lines.append("")
    lines.append(f"- Materials: **{report.get('materials_total', 0)}** "
                 f"({report.get('materials_with_sigma', 0)} with σ, "
                 f"{report.get('materials_with_ea', 0)} with Ea)")
    lines.append(f"- Materials with real consensus (n≥3): **{report.get('materials_with_consensus_n3', 0)}**")
    lines.append(f"- Materials from ≥2 papers: {report.get('materials_with_multipaper', 0)}")
    lines.append(f"- σ records: {report.get('total_sigma_records', 0)}; Ea records: {report.get('total_ea_records', 0)}")
    lines.append(f"- Outlier records: {report.get('outlier_records', 0)}")
    lines.append(f"- Materials with σ-by-temperature bins: {report.get('materials_with_sigma_by_temp', 0)}")
    lines.append(f"- Publication-year coverage: {report.get('pub_years_coverage_pct', 0)}% "
                 f"({report.get('materials_with_pub_years', 0)}/{report.get('materials_total', 0)})")
    ag = report.get("agreement_grade_distribution", {})
    if ag:
        lines.append(f"- Agreement grade distribution: {dict(ag)}")
    lines.append("")

    # Quality scores
    if report.get("quality_score_avg") is not None:
        lines.append("## Quality scores")
        lines.append("")
        lines.append(f"- Average: **{report['quality_score_avg']}/100** "
                     f"(min {report.get('quality_score_min')}, max {report.get('quality_score_max')})")
        qg = report.get("quality_grade_distribution", {})
        if qg:
            lines.append(f"- Grade distribution: {dict(qg)}")
        lines.append("")

    # A3/A4 record-level quality
    q = report.get("quality", {})
    if q.get("records"):
        lines.append("## Record quality (A3/A4)")
        lines.append("")
        lines.append(f"- Scored records: **{q.get('records')}** (avg score {q.get('avg_score')}/100)")
        lines.append(f"- Tiers: Gold **{q.get('gold_records')}** ({q.get('gold_pct')}%), "
                     f"Silver {q.get('silver_records')}, Bronze {q.get('bronze_records')}, "
                     f"Rejected {q.get('rejected_records')}")
        if q.get("grade_distribution"):
            lines.append(f"- Grade distribution: {dict(q['grade_distribution'])}")
        lines.append("")

    # C4 missing-data recommendations
    recs = report.get("missing_data_recommendations", {})
    if recs:
        lines.append("## Missing-data recommendations (curation queue)")
        lines.append("")
        lines.append("| Field | Missing count | Missing % |")
        lines.append("|---|---|---|")
        for field, info in sorted(recs.items(), key=lambda kv: -kv[1]["missing_count"]):
            lines.append(f"| {field} | {info['missing_count']} | {info['missing_pct']}% |")
        lines.append("")
        top = sorted(recs.items(), key=lambda kv: -kv[1]["missing_count"])[0]
        if top[1]["missing_count"]:
            lines.append(f"Highest priority: `{top[0]}` missing on {top[1]['missing_count']} records — ")
            lines.append(f"backfill from {', '.join(top[1]['top_records'][:5])}…")
            lines.append("")

    # C2 drift vs previous snapshot
    drift = report.get("drift", {})
    if drift:
        lines.append("## Drift vs previous health snapshot (C2)")
        lines.append("")
        lines.append(f"- Record count change: {drift.get('record_count_change')} "
                     f"(baseline {drift.get('baseline_records')})")
        if drift.get("coverage_drift_gt_5pct"):
            lines.append(f"- Coverage drift >5%: {dict(drift['coverage_drift_gt_5pct'])}")
        if drift.get("family_drift_gt_2"):
            lines.append(f"- Family drift >2: {dict(drift['family_drift_gt_2'])}")
        if drift.get("baseline_established"):
            lines.append("- This run establishes the baseline; no prior snapshot to diff.")
        lines.append("")

    lines.append("---")
    lines.append("*Generated by `scripts/build_health_report.py`. Release gates are")
    lines.append("tracked in `AGENTS.md` under the v1.0 targets.*")
    return "\n".join(lines)


def main() -> None:
    report = build_health_report()
    OUT_MD.write_text(render_markdown(report))
    OUT_JSON.write_text(json.dumps(report, indent=2, default=str))
    print(f"wrote {OUT_MD.name} (+ {OUT_JSON.name})")
    cov = report.get("coverage", {})
    for k in ("temperature_celsius", "measurement_method", "relative_density_pct",
              "pelletizing_pressure_MPa", "evidence"):
        if k in cov:
            print(f"  {k}: {cov[k]}%")


if __name__ == "__main__":
    main()
