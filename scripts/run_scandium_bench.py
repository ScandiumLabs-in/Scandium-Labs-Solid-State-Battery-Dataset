#!/usr/bin/env python3
"""ScandiumBench v1.0 — research-grade benchmark runner.

Evaluates every benchmark task in `ssb_dataset.benchmarks.tasks` (15 tasks)
across all four deterministic split regimes (random / family_ood /
composition_ood / crystal_system_ood) with the fixed sklearn baselines.

The random regime reuses the Phase-6 leakage-checked split; the three OOD
regimes are the value-add: they force the model to generalize to chemistries,
compositions, and crystal systems never seen during training.

Output:
  benchmark_output/splits/{random,family_ood,...}.parquet   split assignments
  benchmark_output/splits/manifest.json                      regime definitions
  benchmark_output/tasks/<task_id>.json                      per-task result
  benchmark_output/benchmark_report.{json,md}               leaderboard
  benchmark_output/scandium_bench_report.{json,md}          per-regime leaderboard

Usage:
  python scripts/run_scandium_bench.py --limit 3000   # smoke run
  python scripts/run_scandium_bench.py --regimes random,family_ood
"""

from __future__ import annotations

import argparse
import json
import sys
import time
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parent.parent
sys_path = str(ROOT)
if sys_path not in sys.path:
    sys.path.insert(0, sys_path)

from ssb_dataset.benchmarks.evaluate import (  # noqa: E402
    SCARCE_TEST_MIN, run_task,
)
from ssb_dataset.benchmarks.splits import (  # noqa: E402
    REGIMES, build_split_map, build_manifests, persist,
)
from ssb_dataset.benchmarks.tasks import BENCHMARK_TASKS  # noqa: E402

OUT = ROOT / "benchmark_output"
TASKS_DIR = OUT / "tasks"
# base frame = canonical + negative.* block (labels for the negative-result
# and metallic tasks live there), plus the featurized descriptors.
CANONICAL = ROOT / "negative_output/canonical_negative.parquet"
DESCRIPTORS = ROOT / "features_output/descriptors.parquet"


def build_frame(limit: int = 0) -> pd.DataFrame:
    df = pd.read_parquet(CANONICAL)
    desc = pd.read_parquet(DESCRIPTORS)
    desc = desc.drop_duplicates(subset=["identity.material_id"], keep="first")
    merge_cols = ["identity.material_id"] + [c for c in desc.columns
                                             if c not in df.columns]
    df = df.merge(desc[merge_cols], on="identity.material_id", how="left",
                  suffixes=("", "_f"))
    if limit:
        df = df.head(limit)
    return df


def best_model(models: dict, metric: str) -> tuple[str, dict]:
    best_name = None
    best_val = None
    lower_is_better = metric in ("mae", "rmse")
    for name, m in models.items():
        if not isinstance(m, dict) or "error" in m:
            continue
        if metric not in m and "top5_accuracy" not in m:
            continue
        key = metric if metric in m else "top5_accuracy"
        val = m.get(key)
        if val is None:
            continue
        if best_val is None:
            best_val = val
            best_name = name
            continue
        if lower_is_better:
            better = val < best_val
        else:
            better = val > best_val
        if better:
            best_val = val
            best_name = name
    if best_name is None:
        return "none", {}
    return best_name, models[best_name]


def run_one(task, frame, split_map) -> dict:
    t0 = time.time()
    res = run_task(task, frame, split_map)
    res["runtime_s"] = round(time.time() - t0, 1)
    return res


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--limit", type=int, default=0)
    ap.add_argument("--regimes", type=str, default=",".join(REGIMES),
                    help="comma-separated regimes (default: all four)")
    ap.add_argument("--tasks", type=str, default="",
                    help="comma-separated task ids (default: all)")
    ap.add_argument("--out", type=Path, default=OUT)
    args = ap.parse_args()

    regimes = [r.strip() for r in args.regimes.split(",") if r.strip()]
    for r in regimes:
        if r not in REGIMES:
            raise SystemExit(f"unknown regime: {r} (choose from {REGIMES})")

    task_ids = [t.strip() for t in args.tasks.split(",") if t.strip()]
    tasks = [t for t in BENCHMARK_TASKS if not task_ids or t.id in task_ids]
    if task_ids:
        found = {t.id for t in tasks}
        missing = [tid for tid in task_ids if tid not in found]
        if missing:
            raise SystemExit(f"unknown task ids: {missing}")

    print(f"Loading canonical (with negative block) + descriptors ...")
    full = build_frame(limit=0)
    # Split maps + persisted manifests are always built from the FULL corpus so
    # OOD assignments are complete and reproducible; --limit only trims the
    # frame actually evaluated (a smoke-test knob).
    frame = full.head(args.limit) if args.limit else full
    print(f"  full rows: {len(full)}  eval rows: {len(frame)}")
    for r in regimes:
        smap = build_split_map(r, full)
        n_tr = sum(1 for v in smap.values() if v == "train")
        n_te = sum(1 for v in smap.values() if v == "test")
        print(f"[{r}] split map: {len(smap)} rows (train {n_tr} / test {n_te})")

    TASKS_DIR.mkdir(parents=True, exist_ok=True)
    # Tasks whose labeled rows never reach the random regime's test split, or
    # reach it with a degenerate handful of rows (the gold-split-bound scarce
    # σ_RT/Ea subsets), are evaluated by grouped CV on every regime for
    # comparability — a 7-train/2-test split is never reported as evidence.
    random_map = build_split_map("random", full)
    grouped_cv_tasks = set()
    for task in tasks:
        mask = task.label_mask(full)
        split = full.loc[mask, "identity.material_id"].astype(str).map(random_map)
        if (split == "test").sum() < SCARCE_TEST_MIN:
            grouped_cv_tasks.add(task.id)
    if grouped_cv_tasks:
        print(f"Grouped-CV-everywhere tasks (no random-regime test rows): "
              f"{sorted(grouped_cv_tasks)}")

    results = {}
    for r in regimes:
        smap = build_split_map(r, full)
        results[r] = {}
        for task in tasks:
            t0 = time.time()
            print(f"[{r}] {task.id} ...", flush=True)
            res = run_task(task, frame, smap,
                           prefer_grouped_cv=task.id in grouped_cv_tasks)
            res["runtime_s"] = round(time.time() - t0, 1)
            results[r][task.id] = res
            best, best_m = best_model(res.get("models", {}), task.metric)
            print(f"    n_train={res.get('n_train')} n_test={res.get('n_test')} "
                  f"best={best} "
                  f"{best_m if best != 'none' else '(no valid model)'}")

    manifests = persist(full, args.out / "splits")
    render(args, results, tasks, manifests)


def render(args, results: dict, tasks, manifests: dict) -> None:
    report = {"suite": "ScandiumBench", "version": "v1.0.0",
              "generated_at": time.strftime("%Y-%m-%dT%H:%M:%S"),
              "regimes": list(results), "tasks": []}
    for task in tasks:
        tr = {"task": task.id, "name": task.name, "task_type": task.task_type,
              "metric": task.metric, "per_regime": {}}
        for r, rres in results.items():
            res = rres.get(task.id)
            if res is None:
                tr["per_regime"][r] = {"error": "not run"}
                continue
            best, best_m = best_model(res.get("models", {}), task.metric)
            tr["per_regime"][r] = {
                "n_train": res.get("n_train"), "n_test": res.get("n_test"),
                "n_features": res.get("n_features"),
                "best_model": best, "best_metrics": best_m,
                "evaluation": res.get("evaluation"),
                "error": res.get("error"),
            }
        report["tasks"].append(tr)
    report["split_manifests"] = manifests
    (args.out / "scandium_bench_report.json").write_text(
        json.dumps(report, indent=2))
    (args.out / "scandium_bench_report.md").write_text(render_md(report))
    print(f"ScandiumBench leaderboard -> {args.out / 'scandium_bench_report.md'}")


def _fmt_metric(best_m: dict, metric: str) -> str:
    if not best_m:
        return "—"
    v = best_m.get(metric)
    if v is None:
        return "—"
    return f"{v:.4f}"


def render_md(report: dict) -> str:
    lines = [
        "# ScandiumBench v1.0 — split-regime leaderboard",
        "",
        f"Generated {report.get('generated_at')} · "
        f"{len(report.get('tasks', []))} tasks × "
        f"{len(report.get('regimes', []))} split regimes · deterministic "
        "sklearn baselines (dummy / linear / random forest).",
        "",
        "Split regimes: **random** (Phase-6 leakage-checked, reused), "
        "**family_ood** (test chemistries never seen in train), "
        "**composition_ood** (no composition in both train and test), "
        "**crystal_system_ood** (test crystal systems unseen in train).",
        "",
    ]
    for t in report.get("tasks", []):
        metric = t["metric"]
        lines.append(f"### {t['name']} (`{t['task']}`, metric={metric})")
        lines.append("")
        lines.append("| Regime | n_train | n_test | Best model | Value | Eval |")
        lines.append("|---|---|---:|---|---|---|")
        for r, d in t["per_regime"].items():
            if "error" in d and d["error"]:
                lines.append(f"| {r} | — | — | error | — | {d['error']} |")
                continue
            lines.append(
                f"| {r} | {d.get('n_train') or '—'} | {d.get('n_test') or '—'} "
                f"| {d.get('best_model') or '—'} | "
                f"{_fmt_metric(d.get('best_metrics') or {}, metric)} | "
                f"{d.get('evaluation') or '—'} |")
        lines.append("")
    return "\n".join(lines) + "\n"


if __name__ == "__main__":
    main()
