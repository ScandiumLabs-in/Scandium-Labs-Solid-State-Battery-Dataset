#!/usr/bin/env python3
"""Run the Scandium Benchmark Suite (v0.8.0).

Loads the canonical dataset + featurized descriptors, reuses the
leakage-checked train/val/test split assignment from Phase 6, and evaluates
every benchmark task in `ssb_dataset.benchmarks.tasks` with deterministic
sklearn baselines (dummy + linear + random forest).

Output:
  benchmark_output/tasks/<task_id>.json    per-task metrics + features
  benchmark_output/benchmark_report.json   leaderboard (best model per task)
  benchmark_output/benchmark_report.md     human-readable report

Usage:
  python scripts/run_benchmarks.py                      # all 12 tasks
  python scripts/run_benchmarks.py --tasks band_gap_regression,family_classification
  python scripts/run_benchmarks.py --limit 3000         # small smoke run
"""

from __future__ import annotations

import argparse
import json
import time
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parent.parent
sys_path = str(ROOT)
import sys  # noqa: E402
if sys_path not in sys.path:
    sys.path.insert(0, sys_path)

from ssb_dataset.benchmarks.tasks import BENCHMARK_TASKS, get_task  # noqa: E402
from ssb_dataset.benchmarks.evaluate import run_task  # noqa: E402

OUT = ROOT / "benchmark_output"
TASKS_DIR = OUT / "tasks"
CANONICAL = ROOT / "cleaning_output/canonical_dataset.parquet"
DESCRIPTORS = ROOT / "features_output/descriptors.parquet"
SPLIT_FILES = {
    "train": ROOT / "features_output/train.parquet",
    "val": ROOT / "features_output/val.parquet",
    "test": ROOT / "features_output/test.parquet",
    "gold_benchmark": ROOT / "features_output/gold.parquet",
}


def load_split_map() -> dict[str, str]:
    out: dict[str, str] = {}
    for split, path in SPLIT_FILES.items():
        if not path.exists():
            continue
        df = pd.read_parquet(path, columns=["identity.material_id"])
        for mid in df["identity.material_id"].dropna().astype(str):
            out[mid] = split
    return out


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
    """Pick the model with the best primary metric (None-metric counts worst)."""
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


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--tasks", type=str, default="",
                    help="comma-separated task ids (default: all)")
    ap.add_argument("--limit", type=int, default=0,
                    help="restrict to the first N canonical rows (smoke test)")
    ap.add_argument("--out", type=Path, default=OUT)
    ap.add_argument("--report-only", action="store_true",
                    help="re-render the leaderboard from cached task results "
                         "(no re-training)")
    ap.add_argument("--gnn", action="store_true",
                    help="train the dataset_ml GCN baseline and merge it into "
                         "the per-task results before rendering the leaderboard")
    ap.add_argument("--gnn-hidden", type=int, default=64,
                    help="GCN hidden width")
    ap.add_argument("--gnn-layers", type=int, default=3,
                    help="GCN layer count")
    ap.add_argument("--gnn-epochs", type=int, default=40,
                    help="GCN max epochs (early-stop on val)")
    ap.add_argument("--gnn-batch", type=int, default=128,
                    help="GCN batch size")
    ap.add_argument("--gnn-only", action="store_true",
                    help="train ONLY the GCN (skip sklearn baselines)")
    args = ap.parse_args()

    TASKS_DIR.mkdir(parents=True, exist_ok=True)

    task_ids = [t.strip() for t in args.tasks.split(",") if t.strip()]
    if task_ids:
        tasks = []
        for tid in task_ids:
            t = get_task(tid)
            if t is None:
                raise SystemExit(f"unknown task: {tid}")
            tasks.append(t)
    else:
        tasks = list(BENCHMARK_TASKS)

    if args.gnn and not args.report_only:
        if not args.gnn_only:
            run_sklearn(tasks, args)
        merge_gnn(tasks, args)
    elif args.gnn_only:
        merge_gnn(tasks, args)
    elif args.report_only:
        render_report(args)
        return
    else:
        run_sklearn(tasks, args)

    render_report(args)


def run_sklearn(tasks: list, args) -> None:
    print(f"Loading canonical + descriptors (limit={args.limit or 'all'}) ...")
    frame = build_frame(limit=args.limit)
    split_map = load_split_map()
    print(f"  frame rows: {len(frame)}, split map: {len(split_map)} "
          f"(test rows available: {sum(1 for v in split_map.values() if v == 'test')})")

    for task in tasks:
        t0 = time.time()
        print(f"[{task.id}] {task.name} ...", flush=True)
        res = run_task(task, frame, split_map)
        res["runtime_s"] = round(time.time() - t0, 1)
        (TASKS_DIR / f"{task.id}.json").write_text(json.dumps(res, indent=2))
        best, best_m = best_model(res.get("models", {}), task.metric)
        print(f"    n_train={res.get('n_train')} n_test={res.get('n_test')} "
              f"best={best} {best_m if best != 'none' else '(no valid model)'}")
    print(f"Wrote {len(tasks)} task results to {TASKS_DIR}")


def merge_gnn(tasks: list, args) -> None:
    """Train the dataset_ml GCN per task and merge into the cached task JSON."""
    from ssb_dataset.benchmarks.gnn import GNNConfig, train_task

    cfg = GNNConfig(hidden=args.gnn_hidden, layers=args.gnn_layers,
                    epochs=args.gnn_epochs, batch_size=args.gnn_batch)
    for task in tasks:
        tpath = TASKS_DIR / f"{task.id}.json"
        if not tpath.exists():
            res: dict = {"task": task.id, "name": task.name,
                         "task_type": task.task_type, "metric": task.metric,
                         "target": task.target, "models": {}}
        else:
            res = json.loads(tpath.read_text())
        res.setdefault("models", {})
        res.pop("gcn", None)
        t0 = time.time()
        print(f"[{task.id}] GCN baseline ...", flush=True)
        gr = train_task(task.id, cfg)
        if "error" in gr:
            res["models"]["gcn"] = {"error": gr["error"]}
            print(f"    error: {gr['error']}")
        else:
            gcn_metrics = gr["models"]["gcn"]
            res["models"]["gcn"] = gcn_metrics
            res["gcn"] = {"n_train": gr["n_train"], "n_test": gr["n_test"],
                          "evaluation": gr["evaluation"],
                          "architecture": gr["architecture"],
                          "runtime_s": round(time.time() - t0, 1)}
            best, best_m = best_model(res.get("models", {}), task.metric)
            print(f"    gcn n_train={gr['n_train']} n_test={gr['n_test']} "
                  f"best={best} {best_m if best != 'none' else '(no valid model)'}")
        (TASKS_DIR / f"{task.id}.json").write_text(json.dumps(res, indent=2))


def render_report(args) -> None:
    report = {"suite": "Scandium Benchmark Suite", "version": "v0.8.0",
              "generated_at": time.strftime("%Y-%m-%dT%H:%M:%S"),
              "frame_rows": None, "tasks": []}
    for tpath in sorted(TASKS_DIR.glob("*.json")):
        res = json.loads(tpath.read_text())
        best, best_m = best_model(res.get("models", {}),
                                  res.get("metric", "accuracy"))
        report["tasks"].append({
            "task": res.get("task"), "name": res.get("name"),
            "task_type": res.get("task_type"), "metric": res.get("metric"),
            "n_train": res.get("n_train"), "n_test": res.get("n_test"),
            "n_classes": res.get("n_classes"),
            "n_features": res.get("n_features"),
            "best_model": best, "best_metrics": best_m,
            "error": res.get("error"),
            "gcn": res.get("gcn"),
        })
    (args.out / "benchmark_report.json").write_text(
        json.dumps(report, indent=2))
    (args.out / "benchmark_report.md").write_text(render_md(report))
    print(f"Leaderboard -> {args.out / 'benchmark_report.md'}")


def render_md(report: dict) -> str:
    has_gnn = any(t.get("gcn") for t in report["tasks"])
    lines = [
        "# Scandium Benchmark Suite — v0.8.0 baseline results",
        "",
        f"Generated {report.get('generated_at')} · "
        f"{report.get('frame_rows')} canonical rows · deterministic sklearn "
        "baselines (dummy / linear / random forest) on the leakage-checked "
        "test split"
        + (" **+ dataset_ml GCN baseline (v1.3.0)**." if has_gnn else "."),
        "",
        "| Task | Type | n_train | n_test | Best model | Primary metric | Value |",
        "|---|---|---:|---:|---|---|---:|",
    ]
    for t in report["tasks"]:
        best = t.get("best_metrics") or {}
        metric = t.get("metric")
        val = best.get(metric)
        val_s = "—" if val is None else f"{val:.4f}"
        lines.append(
            f"| {t['name']} | {t['task_type']} | {t.get('n_train') or '—'} | "
            f"{t.get('n_test') or '—'} | {t.get('best_model') or '—'} | "
            f"{metric} | {val_s} |")
    if has_gnn:
        lines += [
            "",
            "## GCN baseline details (dataset_ml crystal graphs)",
            "",
            "| Task | GCN n_train | GCN n_test | Epochs | Architecture |",
            "|---|---|---:|---:|---|",
        ]
        for t in report["tasks"]:
            g = t.get("gcn")
            if not g:
                continue
            arch = g.get("architecture") or {}
            lines.append(
                f"| {t['name']} | {g.get('n_train') or '—'} | "
                f"{g.get('n_test') or '—'} | "
                f"{arch.get('epochs_attempted') or '—'} | "
                f"GCN hidden={arch.get('hidden')} layers={arch.get('layers')} |")
    return "\n".join(lines) + "\n"


if __name__ == "__main__":
    main()
