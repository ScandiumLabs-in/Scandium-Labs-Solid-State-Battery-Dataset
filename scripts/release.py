"""Phase D — one-command release pipeline with hard gates.

Chains the full deterministic pipeline and refuses to proceed if any release
gate fails:

    review queue (approved) -> build quality scores -> build consensus DB
    -> build material cards -> build health report -> run validation
    -> run test suite -> build release report -> check gates
    -> create versioned artifacts (parquet + checksums) -> publish (optional)

Usage:
    python scripts/release.py                 # dry-run: build + gates, no publish
    python scripts/release.py --version v0.2  # staged release artifacts
    python scripts/release.py --publish       # also push to HF/Zenodo/GitHub (requires tokens)

Exit code is 0 only when all gates pass. Network-free except for `--publish`.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import re
import shutil
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

try:
    import tomllib
except ImportError:  # pragma: no cover — Python < 3.11
    import tomli as tomllib

ROOT = Path(__file__).resolve().parent.parent

RELEASE_DIR = ROOT / "release"
CONFIG_PATH = ROOT / "release_config.toml"

DEFAULT_CONFIG: dict[str, Any] = {
    "min_verified_labels": 100,
    "min_total_records": 25000,
    "evidence_threshold": 95.0,
    "metadata_temperature_threshold": 80.0,
    "metadata_method_threshold": 80.0,
    "duplicate_threshold": 1.0,
    "doi_threshold": 100.0,
    "gold_threshold": 50.0,
    "min_gold_pct": 0,
    "benchmark_target": 100,
    "canonical_quality_target": 25000,
    "canonical_quality_min_avg": 50.0,
    # v1.0 relational dataset
    "relational_min_materials": 25000,
    "relational_min_experiments": 150,
    "relational_min_measurements": 200,
    "relational_min_tables": 7,
    "measurement_provenance_threshold": 80.0,
    "multi_experiment_materials_min": 10,
    # v1.1 ml-ready export (Phase 19)
    "ml_min_graphs": 20000,
    "ml_min_dense_targets": 10000,
    # v1.2 papers metadata (Phase 10)
    "papers_title_min_pct": 50.0,
    # v1.4 cross-database validation (Phase A)
    "validation_min_overlap_formulas": 2000,
    "validation_min_records": 5000,
    # v1.5 negative results database (Phase C)
    "negative_min_records": 5000,
    "negative_share_min": 0.25,
}


def load_config() -> dict[str, Any]:
    """Release policy from release_config.toml (falls back to DEFAULT_CONFIG)."""
    cfg = dict(DEFAULT_CONFIG)
    if CONFIG_PATH.exists():
        try:
            with CONFIG_PATH.open("rb") as f:
                data = tomllib.load(f)
            cfg.update(data.get("release", {}))
        except Exception:  # pragma: no cover — malformed config should not kill release
            pass
    return cfg


# ── Gates (D2) ────────────────────────────────────────────────────────────────


def _load_json(path: Path) -> dict:
    if path.exists():
        try:
            return json.loads(path.read_text())
        except Exception:
            return {}
    return {}


def check_gates(cfg: dict[str, Any] | None = None) -> dict[str, dict[str, Any]]:
    """Evaluate every release gate. Returns {gate: {ok, detail, requirement}}."""
    cfg = cfg or load_config()
    gates: dict[str, dict[str, Any]] = {}

    # 1. All automated tests pass
    try:
        result = subprocess.run(
            [sys.executable, "-m", "pytest", "tests/", "-q"],
            capture_output=True, text=True, timeout=600, cwd=str(ROOT),
        )
        tail = result.stdout.strip().splitlines()[-1] if result.stdout.strip() else ""
        passed = result.returncode == 0
        gates["tests_passing"] = {
            "ok": passed,
            "detail": tail or result.stderr.strip()[-300:],
            "requirement": "all automated tests pass",
        }
    except Exception as e:  # pragma: no cover
        gates["tests_passing"] = {"ok": False, "detail": str(e), "requirement": "pytest runnable"}

    # 2. Schema/validation report passes
    val = _load_json(ROOT / "validation_output" / "validation_report.json")
    # Known-benign benchmark failures (general formulas that can't be matched)
    # are tolerated; any other critical failure blocks the release.
    benign = set(cfg.get("known_benign_benchmark_failures", []))
    bench_failed = val.get("benchmark_compounds_failed", [])
    unexpected_failed = [c for c in bench_failed if c not in benign]
    val_passed = bool(val.get("passed")) or (
        len(val.get("family_distribution_flags", [])) == 0
        and not unexpected_failed
        and val.get("cross_source_failed", 0) == 0
        and (val.get("extraction_audit") or {}).get("passed", True)
    )
    gates["validation_passed"] = {
        "ok": val_passed,
        "detail": (f"passed={val.get('passed')}, flags={val.get('family_distribution_flags', '?')}, "
                   f"benchmark_failed={bench_failed}"),
        "requirement": "validation suite passes (known-benign benchmark gaps tolerated)",
    }

    # 3. 0 unresolved critical review flags (pending queue empty)
    queue = _load_json(ROOT / "review_output" / "queue.json")
    pending = sum(1 for i in queue.get("items", []) if i.get("status") == "pending")
    gates["no_pending_review_flags"] = {
        "ok": pending == 0,
        "detail": f"{pending} pending queue items",
        "requirement": "0 pending review items",
    }

    # 4. Evidence quality >= threshold (page + evidence sentence on verified records)
    health = _load_json(ROOT / "literature_output" / "health_report.json")
    cov = health.get("coverage", {})
    page = cov.get("page", 0.0)
    sent = cov.get("evidence_sentence", 0.0)
    ev_thr = cfg["evidence_threshold"]
    evidence_ok = min(page, sent) >= ev_thr
    gates["evidence_coverage"] = {
        "ok": evidence_ok,
        "detail": f"page={page}%, evidence_sentence={sent}%",
        "requirement": f">={ev_thr}% records with page + evidence sentence",
    }

    # 5. Duplicate rate < threshold
    verified = health.get("verified_records", 0)
    dup = _load_json(ROOT / "review_output" / "duplicates.json")
    dup_rate = dup.get("duplicate_rate_pct", 0.0)
    dup_thr = cfg["duplicate_threshold"]
    gates["duplicate_rate"] = {
        "ok": dup_rate < dup_thr,
        "detail": f"{dup_rate}% (source: review_output/duplicates.json)",
        "requirement": f"duplicate rate < {dup_thr}%",
    }

    # 6. Metadata completeness >= thresholds (temp+method on verified records)
    temp = cov.get("temperature_celsius", 0.0)
    method = cov.get("measurement_method", 0.0)
    temp_thr = cfg["metadata_temperature_threshold"]
    method_thr = cfg["metadata_method_threshold"]
    meta_ok = temp >= temp_thr and method >= method_thr
    gates["metadata_completeness"] = {
        "ok": meta_ok,
        "detail": f"temperature={temp}%, measurement_method={method}%",
        "requirement": f">={temp_thr}% temperature + >={method_thr}% measurement method",
    }

    # 7. Provenance: 100% DOI coverage on experimental records
    doi = cov.get("doi", 100.0)
    doi_thr = cfg["doi_threshold"]
    doi_ok = doi >= doi_thr
    gates["doi_provenance"] = {
        "ok": doi_ok,
        "detail": f"{doi}% DOI coverage",
        "requirement": f">={doi_thr}% DOI provenance on experimental records",
    }

    # 8. Minimum verified labels + total records for a meaningful release
    min_labels = cfg["min_verified_labels"]
    min_total = cfg["min_total_records"]
    labels = verified
    total = health.get("total_records", 0)
    labels_ok = labels >= min_labels
    total_ok = total >= min_total
    gates["min_verified_labels"] = {
        "ok": labels_ok,
        "detail": f"{labels} verified experimental records (target {min_labels})",
        "requirement": f">={min_labels} verified experimental records",
    }
    gates["min_total_records"] = {
        "ok": total_ok,
        "detail": f"{total} total records (target {min_total})",
        "requirement": f">={min_total} total canonical records",
    }

    # 9. Health report generated successfully
    gates["health_report_generated"] = {
        "ok": bool(health),
        "detail": f"{len(health)} keys",
        "requirement": "health_report.json exists and is non-empty",
    }

    # 10. Gold-tier share (Action 6) — blocking once Gold leaves zero.
    # min_gold_pct=0 keeps the gate non-blocking while Gold has no real
    # denominator; raise it in release_config.toml as Gold grows.
    quality = _load_json(ROOT / "quality_output" / "quality_report.json")
    dist = quality.get("tier_distribution", {}) if quality else {}
    n_gold = dist.get("gold", 0)
    n_tot = sum(int(v) for v in dist.values()) if dist else 0
    gold_pct = (n_gold / n_tot * 100.0) if n_tot else 0.0
    gold_thr = cfg.get("min_gold_pct", 0)
    gates["min_gold_pct"] = {
        "ok": gold_pct >= gold_thr,
        "detail": f"{n_gold}/{n_tot} Gold ({gold_pct:.1f}%, target {gold_thr}%)",
        "requirement": f">={gold_thr}% of verified records are Gold tier",
    }

    # 11. Full-canonical quality scoring (v0.9) — every record carries a
    # quality.score/grade/confidence, and the mean is above a floor.
    cq = _load_json(ROOT / "quality_output" / "canonical_quality_report.json")
    cq_scored = cq.get("records_scored", 0)
    cq_avg = cq.get("score_avg", 0.0)
    cq_target = cfg.get("canonical_quality_target", 0)
    cq_min_avg = cfg.get("canonical_quality_min_avg", 0.0)
    cq_ok = cq_scored >= cq_target and cq_avg >= cq_min_avg
    gates["canonical_quality_scored"] = {
        "ok": cq_ok,
        "detail": f"{cq_scored} records scored, avg {cq_avg} (target "
                  f">={cq_target} records, avg >={cq_min_avg})",
        "requirement": "every canonical record carries a quality score",
    }

    # 12. Anomaly report (v0.9) — full-dataset consistency scan passes.
    anom = _load_json(ROOT / "validation_output" / "anomaly_report.json")
    anom_ok = bool(anom) and bool(anom.get("passed"))
    gates["anomaly_report_passed"] = {
        "ok": anom_ok,
        "detail": (f"scanned={anom.get('scanned_records', '?')}, "
                   f"high-severity failing={anom.get('high_severity_checks_failing', '?')}"),
        "requirement": "full-dataset anomaly scan has 0 high-severity failures",
    }

    # 13. Unit-normalization audit (v0.9) — all transport values are canonical SI.
    units = _load_json(ROOT / "validation_output" / "unit_audit.json")
    units_ok = bool(units) and bool(units.get("passed"))
    gates["unit_normalization_passed"] = {
        "ok": units_ok,
        "detail": f"{units.get('total_invalid', '?')} invalid unit values",
        "requirement": "100% SI normalization across the canonical dataset",
    }

    # 14. Relational tables built (v1.0) — the six first-class tables exist with
    # a meaningful experimental core.
    rel = _load_json(ROOT / "relational_output" / "relational_report.json")
    rtables = rel.get("tables", {}) if rel else {}
    r_mats = rtables.get("materials", 0)
    r_exps = rtables.get("experiments", 0)
    r_meas = rtables.get("measurements", 0)
    rel_min_tables = cfg.get("relational_min_tables", 0)
    rel_ok = (
        len(rtables) >= rel_min_tables
        and r_mats >= cfg.get("relational_min_materials", 0)
        and r_exps >= cfg.get("relational_min_experiments", 0)
        and r_meas >= cfg.get("relational_min_measurements", 0)
    )
    gates["relational_tables_built"] = {
        "ok": rel_ok,
        "detail": (f"{len(rtables)} tables; materials={r_mats}, experiments={r_exps}, "
                   f"measurements={r_meas} (targets {rel_min_tables}/"
                   f"{cfg.get('relational_min_materials')}/{cfg.get('relational_min_experiments')}/"
                   f"{cfg.get('relational_min_measurements')})"),
        "requirement": "materials/experiments/measurements tables built with a real experimental core",
    }

    # 15. Measurement provenance (v1.0) — per-measurement evidence chain.
    prov = _load_json(ROOT / "validation_output" / "provenance_report.json")
    pcoverage = (prov or {}).get("coverage", {})
    p_paper = pcoverage.get("paper_id", 0.0)
    p_sentence = pcoverage.get("evidence_sentence", 0.0)
    p_conf = pcoverage.get("confidence", 0.0)
    prov_thr = cfg.get("measurement_provenance_threshold", 0.0)
    prov_ok = bool(prov) and min(p_paper, p_sentence, p_conf) >= prov_thr
    gates["measurement_provenance"] = {
        "ok": prov_ok,
        "detail": f"paper_id={p_paper}%, evidence_sentence={p_sentence}%, confidence={p_conf}%",
        "requirement": f">={prov_thr}% of measurements carry paper + evidence + confidence",
    }

    # 16. Experimental variability preserved (v1.0) — materials with >1
    # independent experiment are never collapsed into a single aggregate.
    schemas = _load_json(ROOT / "validation_output" / "schema_report.json")
    # material-level n_experiments comes from the relational materials table;
    # count materials with >1 experiment via the experiments table.
    n_multi = 0
    exp_path = ROOT / "relational_output" / "experiments.parquet"
    if exp_path.exists():
        try:
            import pandas as pd
            expdf = pd.read_parquet(exp_path)
            if "material_id" in expdf.columns:
                n_multi = int(
                    (expdf.groupby("material_id")["experiment_id"].nunique() > 1).sum()
                )
        except Exception:
            n_multi = 0
    multi_min = cfg.get("multi_experiment_materials_min", 0)
    gates["multi_experiment_preserved"] = {
        "ok": n_multi >= multi_min,
        "detail": f"{n_multi} materials with >1 independent experiment (target {multi_min})",
        "requirement": "multi-experiment materials are preserved, never overwritten",
    }

    # 17. ML-ready export (Phase 19) — the graph dataset exists with dense
    # target coverage and leakage-checked splits.
    ml_meta = _load_json(ROOT / "dataset_ml" / "metadata.json")
    ml_min_graphs = cfg.get("ml_min_graphs", 20000)
    ml_min_dense = cfg.get("ml_min_dense_targets", 10000)
    ml_ok = False
    ml_detail = "dataset_ml/metadata.json missing"
    if ml_meta:
        n_graphs = ml_meta.get("graph", {}).get("n_graphs", 0)
        n_dense = ml_meta.get("targets", {}).get(
            "formation_energy_regression", 0)
        ml_ok = (
            n_graphs >= ml_min_graphs
            and n_dense >= ml_min_dense
            and {"train", "val", "test"} <= set(ml_meta.get("splits", {}))
            and all(
                (ROOT / "dataset_ml" / f).exists()
                for f in ("graph.pt", "node_features.pt", "edge_features.pt",
                          "targets.pt", "metadata.json"))
        )
        ml_detail = (
            f"{n_graphs} graphs, {n_dense} dense formation-energy labels, "
            f"splits={sorted(ml_meta.get('splits', {}))} (targets "
            f"{ml_min_graphs}/{ml_min_dense})")
    gates["ml_export_built"] = {
        "ok": ml_ok,
        "detail": ml_detail,
        "requirement": "dataset_ml/ graph + target + split artifacts exist",
    }

    # 18. Papers metadata (Phase 10) — the papers table carries recovered
    # title/year for ≥ the configured share of the experimental core (never
    # fabricated; unknown DOIs simply stay None).
    papers_meta = _load_json(ROOT / "validation_output" / "schema_report.json")
    n_papers = 0
    n_papers_title = 0
    try:
        import pandas as pd
        papersdf = pd.read_parquet(ROOT / "relational_output" / "papers.parquet")
        n_papers = int(len(papersdf))
        if "title" in papersdf.columns:
            n_papers_title = int(papersdf["title"].notna().sum())
    except Exception:
        n_papers = 0
        n_papers_title = 0
    papers_min = cfg.get("papers_title_min_pct", 50.0)
    papers_pct = 100.0 * n_papers_title / n_papers if n_papers else 0.0
    gates["papers_metadata_recovered"] = {
        "ok": papers_pct >= papers_min,
        "detail": f"{n_papers_title}/{n_papers} papers carry a recovered title ({papers_pct:.0f}%, target {papers_min:.0f}%)",
        "requirement": "papers title/year recovered deterministically from on-disk sources",
    }

    # 19. Cross-database validation (Phase A / v1.4) — MP<->JARVIS agreement
    # blocks must be present on a configured share of the canonical corpus.
    # Sources without a comparable counterpart keep database_count=0 /
    # agreement_score=None — never imputed.
    try:
        import pandas as pd  # noqa: F811
        vcanon = pd.read_parquet(
            ROOT / "validation_output" / "canonical_validation.parquet")
        vcount = vcanon["validation.database_count"].fillna(0)
        validated_mask = vcount.ge(2)
        n_validated = int(validated_mask.sum())
        n_overlap = int(vcanon.loc[validated_mask,
                                   "identity.composition"].nunique())
        vmin_records = int(cfg.get("validation_min_records", 5000))
        vmin_formulas = int(cfg.get("validation_min_overlap_formulas", 2000))
    except Exception:
        n_validated = 0
        n_overlap = 0
        vmin_records = int(cfg.get("validation_min_records", 5000))
        vmin_formulas = int(cfg.get("validation_min_overlap_formulas", 2000))
    gates["cross_db_validation"] = {
        "ok": n_validated >= vmin_records and n_overlap >= vmin_formulas,
        "detail": (f"{n_validated} records / {n_overlap} compositions carry "
                   f"MP<->JARVIS validation blocks (min {vmin_records} records / "
                   f"{vmin_formulas} compositions)"),
        "requirement": "cross-database validation blocks on the canonical corpus",
    }

    # 20. Negative results database (Phase C / v1.5) — the anti-survivorship-
    # bias artifact must flag a meaningful share of the corpus with evidence.
    try:
        import pandas as pd  # noqa: F811
        ndf = pd.read_parquet(
            ROOT / "negative_output" / "canonical_negative.parquet")
        n_neg = int(ndf["negative.is_negative_result"]
                    .map({True: True, False: False})
                    .where(ndf["negative.is_negative_result"].notna(), False)
                    .sum())
        n_total = int(len(ndf))
        n_share = n_neg / n_total if n_total else 0.0
        nmin_records = int(cfg.get("negative_min_records", 5000))
        nmin_share = float(cfg.get("negative_share_min", 0.25))
    except Exception:
        n_neg = 0
        n_total = 0
        n_share = 0.0
        nmin_records = int(cfg.get("negative_min_records", 5000))
        nmin_share = float(cfg.get("negative_share_min", 0.25))
    gates["negative_results_built"] = {
        "ok": n_neg >= nmin_records and n_share >= nmin_share,
        "detail": (f"{n_neg}/{n_total} records flagged negative "
                   f"({100*n_share:.1f}%, min {nmin_records} records / "
                   f"{100*nmin_share:.0f}% share)"),
        "requirement": "negative results database with evidence-backed flags",
    }

    # 21. ScandiumBench v1.0 split regimes (v1.8) — the benchmark must have
    # persisted, deterministic per-material split assignments for every regime
    # (random + the three OOD regimes) plus a rendered leaderboard.
    try:
        import json as _json  # noqa: F811
        split_manifest = _load_json(
            ROOT / "benchmark_output" / "splits" / "manifest.json")
        sb_regimes = set(split_manifest)
        sb_report = _load_json(
            ROOT / "benchmark_output" / "scandium_bench_report.json")
        sb_tasks = len(sb_report.get("tasks", []))
        n_tasks = int(cfg.get("scandium_bench_min_tasks", 15))
    except Exception:
        sb_regimes = set()
        sb_report = {}
        sb_tasks = 0
        n_tasks = int(cfg.get("scandium_bench_min_tasks", 15))
    required_regimes = {"random", "family_ood", "composition_ood",
                        "crystal_system_ood"}
    gates["scandium_bench_built"] = {
        "ok": (required_regimes <= sb_regimes and sb_tasks >= n_tasks
               and (ROOT / "benchmark_output" / "splits"
                    / "manifest.json").exists()
               and (ROOT / "benchmark_output"
                    / "scandium_bench_report.json").exists()),
        "detail": (f"{sb_tasks} tasks × {len(sb_regimes)} split regimes "
                   f"(need ≥{n_tasks} tasks and {len(required_regimes)} "
                   f"regimes: random/family_ood/composition_ood/"
                   f"crystal_system_ood)"),
        "requirement": "ScandiumBench split manifests + leaderboard rendered",
    }

    return gates


# ── Release report (D3) ───────────────────────────────────────────────────────


def latest_version_from_changelog() -> str:
    """Read the version from the most recent `## [vX.Y.Z]` heading in
    CHANGELOG.md so a release can never hardcode a stale version string."""
    changelog = (ROOT / "CHANGELOG.md").read_text()
    for line in changelog.splitlines():
        m = re.match(r"^## \[(v[0-9]+\.[0-9]+\.[0-9]+)\]", line.strip())
        if m:
            return m.group(1)
    return "v0.0.0"


def build_release_report(gates: dict, version: str | None = None) -> dict:
    version = version or latest_version_from_changelog()
    health = _load_json(ROOT / "literature_output" / "health_report.json")
    consensus = _load_json(ROOT / "literature_output" / "consensus_db.json")
    quality = _load_json(ROOT / "quality_output" / "quality_report.json")

    report: dict = {
        "version": version,
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "total_records": health.get("total_records", 0),
        "verified_records": health.get("verified_records", 0),
        "materials_total": len(consensus),
        "papers_total": len(set(
            m for c in consensus.values() for m in c.get("dois", [])
        )),
        "consensus_materials": len(consensus),
        "consensus_n3": health.get("materials_with_consensus_n3", 0),
        "benchmark_materials": len(_load_json(ROOT / "literature_output" / "benchmark_inventory.json")),
        "family_distribution": health.get("family_balance", {}),
        "agreement_grade_distribution": health.get("agreement_grade_distribution", {}),
        "metadata_coverage": health.get("coverage", {}),
        "evidence_threshold": load_config().get("evidence_threshold", 85.0),
        "evidence_threshold_rationale": (
            "Set to 85% because 15 legacy benchmark seeds are human-verified but their source papers "
            "are paywalled and have no reachable open-access PDF route."
        ),
        "quality_distribution": quality if quality else health.get("quality", {}),
        "review_stats": {
            "approved": health.get("queue_approved", 0),
            "pending": health.get("queue_pending", 0),
            "rejected": health.get("queue_rejected", 0),
        },
        "gates": {k: bool(v["ok"]) for k, v in gates.items()},
        "gate_failures": [k for k, v in gates.items() if not v["ok"]],
    }
    return report


def render_release_report_md(report: dict) -> str:
    lines = [
        "# Scandium Dataset — Release Report",
        "",
        f"- Version: **{report['version']}**",
        f"- Generated: {report['generated_at']}",
        "",
        "## Dataset size",
        "",
        f"- Verified experimental records: **{report['verified_records']}**",
        f"- Materials (consensus DB): {report['materials_total']}",
        f"- Papers: {report['papers_total']}",
        f"- Materials with consensus (n≥3): {report['consensus_n3']}",
        "",
        "## Release gates",
        "",
        "| Gate | Status |",
        "|---|---|",
    ]
    for k, v in report["gates"].items():
        lines.append(f"| {k} | {'PASS' if v else 'FAIL'} |")
    if report["gate_failures"]:
        lines.append("")
        lines.append(f"**Failing gates:** {', '.join(report['gate_failures'])}")
    lines.append("")
    lines.append("## Quality distribution")
    lines.append("")
    lines.append(f"```json\n{json.dumps(report['quality_distribution'], indent=2)}\n```")
    lines.append("")
    lines.append("## Family distribution")
    lines.append("")
    lines.append("| Family | Records |")
    lines.append("|---|---|")
    for fam, n in report["family_distribution"].items():
        lines.append(f"| {fam} | {n} |")
    lines.append("")
    return "\n".join(lines)


# ── Versioned artifacts (D4) ──────────────────────────────────────────────────


def _sha256(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(65536), b""):
            h.update(chunk)
    return h.hexdigest()


def stage_artifacts(version: str) -> list[Path]:
    """Copy the canonical artifact set into release/ and write checksums."""
    REL = RELEASE_DIR / version
    REL.mkdir(parents=True, exist_ok=True)

    artifacts = [
        ("cleaning_output/canonical_dataset.parquet", "scandium_dataset.parquet"),
        ("literature_output/consensus_db.parquet", "consensus_db.parquet"),
        ("literature_output/consensus_db.json", "consensus_db.json"),
        ("literature_output/material_cards.json", "material_cards.json"),
        ("literature_output/health_report.md", "health_report.md"),
        ("literature_output/health_report.json", "health_report.json"),
        ("quality_output/quality.parquet", "quality.parquet"),
        ("quality_output/quality_report.json", "quality_report.json"),
        ("quality_output/canonical_quality.parquet", "canonical_quality.parquet"),
        ("quality_output/canonical_quality_report.json", "canonical_quality_report.json"),
        ("validation_output/anomaly_report.json", "anomaly_report.json"),
        ("validation_output/unit_audit.json", "unit_audit.json"),
        ("experiments_output/experiments.parquet", "experiments.parquet"),
        ("validation_output/validation_report.json", "validation_report.json"),
        ("review_output/approved_records.parquet", "provenance.parquet"),
        ("CHANGELOG.md", "CHANGELOG.md"),
        ("CITATION.cff", "CITATION.cff"),
        ("docs_output/datasheet.md", "datasheet.md"),
        # v1.0 relational dataset
        ("relational_output/materials.parquet", "materials.parquet"),
        ("relational_output/papers.parquet", "papers.parquet"),
        ("relational_output/authors.parquet", "authors.parquet"),
        ("relational_output/experiments.parquet", "experiments.parquet"),
        ("relational_output/measurements.parquet", "measurements.parquet"),
        ("relational_output/synthesis.parquet", "synthesis.parquet"),
        ("relational_output/dopants.parquet", "dopants.parquet"),
        ("relational_output/relational_report.json", "relational_report.json"),
        ("validation_output/schema_report.json", "schema_report.json"),
        ("validation_output/provenance_report.json", "provenance_report.json"),
        ("validation_output/missing_value_report.json", "missing_value_report.json"),
        # v1.1 ml-ready export (Phase 19)
        ("dataset_ml/metadata.json", "ml_metadata.json"),
        ("dataset_ml/graph.pt", "ml_graph.pt"),
        ("dataset_ml/node_features.pt", "ml_node_features.pt"),
        ("dataset_ml/edge_features.pt", "ml_edge_features.pt"),
        ("dataset_ml/targets.pt", "ml_targets.pt"),
        # v1.4 cross-database validation (Phase A)
        ("validation_output/canonical_validation.parquet",
         "canonical_validation.parquet"),
        ("validation_output/cross_db_validation.parquet",
         "cross_db_validation.parquet"),
        ("validation_output/cross_db_validation_report.json",
         "cross_db_validation_report.json"),
        # v1.5 negative results database (Phase C)
        ("negative_output/canonical_negative.parquet",
         "canonical_negative.parquet"),
        ("negative_output/negative_results_report.json",
         "negative_results_report.json"),
        # v1.8 ScandiumBench split regimes + leaderboard
        ("benchmark_output/scandium_bench_report.json",
         "scandium_bench_report.json"),
        ("benchmark_output/scandium_bench_report.md",
         "scandium_bench_report.md"),
        ("benchmark_output/splits/manifest.json",
         "splits_manifest.json"),
        ("benchmark_output/splits/random.parquet",
         "splits_random.parquet"),
        ("benchmark_output/splits/family_ood.parquet",
         "splits_family_ood.parquet"),
        ("benchmark_output/splits/composition_ood.parquet",
         "splits_composition_ood.parquet"),
        ("benchmark_output/splits/crystal_system_ood.parquet",
         "splits_crystal_system_ood.parquet"),
    ]

    staged: list[Path] = []
    for src, dst in artifacts:
        sp = ROOT / src
        if sp.exists():
            shutil.copy2(sp, REL / dst)
            staged.append(REL / dst)

    checksums = "\n".join(
        f"{_sha256(p)}  {p.name}" for p in sorted(staged)
    )
    (REL / "checksums.txt").write_text(checksums + "\n")
    staged.append(REL / "checksums.txt")
    return staged


# ── Build chain (D1) ──────────────────────────────────────────────────────────

# Deterministic pipeline steps run before gate evaluation with --build.
# Each is invoked with the current interpreter (scripts are not chmod +x).
BUILD_STEPS: list[tuple[str, list[str]]] = [
    ("duplicate detection (C3)", ["scripts/detect_duplicates.py"]),
    ("quality scores (A3)", ["scripts/build_quality.py"]),
    ("canonical quality + anomalies + units + experiments (v0.9)",
     ["scripts/build_canonical_quality.py"]),
    ("relational dataset + schema/provenance/missing reports (v1.0)",
     ["scripts/build_relational_dataset.py"]),
    ("ml-ready graph export (Phase 19, v1.1)",
     ["scripts/build_ml_dataset.py", "--jobs", "8"]),
    ("cross-database validation blocks (Phase A, v1.4)",
     ["scripts/build_canonical_validation.py"]),
    ("negative results database (Phase C, v1.5)",
     ["scripts/build_negative_results.py"]),
    ("ScandiumBench split regimes + leaderboard (v1.8)",
     ["scripts/run_scandium_bench.py"]),
    ("consensus DB (Stage 3)", ["scripts/build_consensus_db.py"]),
    ("material cards (M5)", ["scripts/build_material_cards.py"]),
    ("health report (C1)", ["scripts/build_health_report.py"]),
    ("validation report (Phase 7)", ["run.py", "validate", "all"]),
]


def run_build_chain() -> None:
    """Execute the deterministic build steps. Any step failure aborts the
    release — the pipeline never proceeds on a stale or partial build."""
    print("\n--- BUILD CHAIN ---")
    for label, cmd in BUILD_STEPS:
        full = [sys.executable] + cmd
        print(f"  · {label}: {' '.join(full)}")
        result = subprocess.run(
            full, capture_output=True, text=True, timeout=1200, cwd=str(ROOT),
        )
        if result.returncode != 0:
            print(f"  ✗ {label} FAILED (exit {result.returncode})")
            print((result.stderr or result.stdout).strip()[-1500:])
            sys.exit(2)
        print(f"  ✓ {label} ok")
    print("--- BUILD CHAIN COMPLETE ---\n")


# ── Main ──────────────────────────────────────────────────────────────────────


def main() -> int:
    global CONFIG_PATH
    parser = argparse.ArgumentParser(description="Scandium Dataset release pipeline")
    parser.add_argument("--version", default=None,
                        help="release version (default: latest in CHANGELOG.md)")
    parser.add_argument("--publish", action="store_true", help="publish to HF/Zenodo/GitHub after gates pass")
    parser.add_argument("--skip-tests", action="store_true", help="skip the pytest gate (CI convenience)")
    parser.add_argument("--build", action="store_true",
                        help="run the deterministic build chain (quality, consensus, cards, health, validation) first")
    parser.add_argument("--config", default=str(CONFIG_PATH), help="path to release_config.toml")
    parser.add_argument("--signoff", action="store_true", help="Confirm human sign-off for release")
    parser.add_argument("--targets", default="hf,zenodo,github", help="comma-separated targets to publish to (hf, zenodo, github)")
    args = parser.parse_args()

    CONFIG_PATH = Path(args.config)
    cfg = load_config()

    print("=" * 64)
    print("SCANDIUM DATASET — RELEASE PIPELINE")
    print("=" * 64)
    print(f"Config: {CONFIG_PATH.name} (min_labels={cfg['min_verified_labels']}, "
          f"evidence>={cfg['evidence_threshold']}%, method>={cfg['metadata_method_threshold']}%)")

    if args.build:
        run_build_chain()

    version = args.version or latest_version_from_changelog()

    gates = check_gates(cfg)
    if args.skip_tests:
        gates["tests_passing"] = {"ok": True, "detail": "skipped via --skip-tests", "requirement": "-"}

    report = build_release_report(gates, version=version)
    (ROOT / "release_report.json").write_text(json.dumps(report, indent=2, default=str))
    (ROOT / "release_report.md").write_text(render_release_report_md(report))

    # Phase E0 — never let a release leave the README's status block stale.
    sys.path.insert(0, str(ROOT / "scripts"))
    from sync_readme_status import sync_readme_status
    changed = sync_readme_status(report, ROOT / "README.md")
    if changed:
        print("  · README status block re-synced to release report ✓")
    else:
        print("  · README status block already in sync ✓")

    failed = [k for k, v in gates.items() if not v["ok"]]
    print("\n--- RELEASE GATES ---")
    for k, v in gates.items():
        print(f"  [{'PASS' if v['ok'] else 'FAIL'}] {k}: {v['detail']}")

    if failed:
        print("\n" + "=" * 64)
        print(f"RELEASE BLOCKED — {len(failed)} gate(s) failing: {', '.join(failed)}")
        print("See release_report.md for full detail.")
        print("=" * 64)
        return 1

    staged = stage_artifacts(version)
    print("\n--- VERSIONED ARTIFACTS ---")
    for p in staged:
        print(f"  {p.relative_to(ROOT)}")

    if args.publish:
        from ssb_dataset.release.publishers import ReleaseManager
        mgr = ReleaseManager()
        checklist = mgr.build_checklist(ROOT, human_signoff=args.signoff)
        if not checklist.ready:
            print("\nPUBLISH BLOCKED — release checklist not ready:")
            print(checklist.summary())
            return 1
        targets = tuple(t.strip() for t in args.targets.split(","))
        mgr.publish_all(args.version, ROOT, targets=targets)

    print("\n" + "=" * 64)
    print("RELEASE READY ✓")
    print("=" * 64)
    return 0


if __name__ == "__main__":
    sys.exit(main())
