"""Evaluation engine for the Scandium Benchmark Suite.

Pure, deterministic functions:
  - feature selection (all numeric deterministic columns minus identity/
    provenance, minus per-task target + leaky columns)
  - metric computation (regression / classification / ranking)
  - sklearn baseline training (dummy + linear + random forest + MLP)
    evaluated on the leakage-checked test split (reused from Phase 6
    featurization).

No LLM calls. Deterministic (fixed random_state).
"""

from __future__ import annotations

import math

import numpy as np
import pandas as pd

from ssb_dataset.benchmarks.tasks import BenchmarkTask

# Minimum number of test rows (or train rows) below which a train/test split is
# degenerate for the deterministic baselines. Tasks whose labeled rows land in
# the gold split (the scarce literature-verified σ_RT / Ea subsets) or which
# reach the test split with only a handful of rows must fall back to grouped
# K-fold CV rather than reporting a meaningless 7-train/2-test split.
SCARCE_TEST_MIN = 30

# Dot-path columns that are never usable as ML features (identity/provenance,
# free text, list/dict columns). Everything else numeric gets considered.
# The validation.* and negative.* blocks are *derived annotations* (agreement
# scores, anti-survivorship labels computed from the same descriptors) — they
# are benchmark outputs, never model inputs.
NON_FEATURE_PREFIXES = ("identity.", "text_provenance.", "ml_features.",
                        "validation.", "negative.")
NON_FEATURE_COLUMNS = {
    "structure.structure_relaxed",
    "structure.structure_unrelaxed",
    "structure.lattice_params",
    "structure.li_site_occupancy",
    "structure.coordination_environment",
    "structure.coordination_csm",
    "structure.coordination_species",
    "structure.space_group",
    "structure.neighbor_species_distribution",
    "structure.bond_types",
    "structure.bond_length_stats",
    "thermodynamics.decomposition_products",
    "thermodynamics.electrochemical_stability_window",
    "ion_transport.sigma_vs_T_curve",
    "ion_transport.temperature_range_measured",
    "chemistry.atomic_fractions",
    "chemistry.elemental_fractions",
    "chemistry.weight_fractions",
    "electronic.possible_species",
    "magnetic.types_of_magnetic_species",
    "synthesis.precursors",
    "experiment.notes",
}

_ML_MODELS = None  # lazy import


def _numeric_frame(df: pd.DataFrame, cols: list[str]) -> pd.DataFrame:
    """Coerce the chosen columns to float (NaN preserved), dropping columns
    that fail numeric coercion or are mostly missing."""
    out: dict[str, np.ndarray] = {}
    for c in cols:
        s = df[c]
        if s.dtype == object:
            try:
                s = pd.to_numeric(s, errors="raise")
            except Exception:
                continue
        if s.dtype.kind not in ("f", "i", "b"):
            continue
        if s.notna().sum() < max(10, 0.3 * len(df)):
            continue
        arr = s.to_numpy(dtype=float)
        if np.isnan(arr).all():
            continue
        out[c] = arr
    if not out:
        return pd.DataFrame(index=df.index)
    return pd.DataFrame(out, index=df.index)


def select_features(df: pd.DataFrame, task: BenchmarkTask) -> list[str]:
    """Choose the numeric feature columns for a task: all usable deterministic
    numeric columns minus the target and its leaky columns."""
    excluded = set(NON_FEATURE_COLUMNS)
    for c in df.columns:
        if c.startswith(NON_FEATURE_PREFIXES) or c.startswith("_"):
            excluded.add(c)
    excluded.add(task.target)
    excluded.update(task.leaky_cols)
    candidates = [c for c in df.columns if c not in excluded]
    num = _numeric_frame(df, candidates)
    return list(num.columns)


def mae(y, p):
    return float(np.mean(np.abs(y - p)))


def rmse(y, p):
    return float(np.sqrt(np.mean((y - p) ** 2)))


def r2(y, p):
    ss_res = np.sum((y - p) ** 2)
    ss_tot = max(np.sum((y - np.mean(y)) ** 2), 1e-12)
    return float(1.0 - ss_res / ss_tot)


def accuracy(y, p):
    return float(np.mean(y == p))


def macro_f1(y, p):
    from sklearn.metrics import f1_score
    return float(f1_score(y, p, average="macro", zero_division=0))


def roc_auc(y, p_prob):
    from sklearn.metrics import roc_auc_score
    try:
        return float(roc_auc_score(y, p_prob))
    except ValueError:
        return None


def top5_accuracy(y, p_proba):
    top5 = np.argsort(-np.asarray(p_proba), axis=1)[:, :5]
    hit = [y[i] in top5[i] for i in range(len(y))]
    return float(np.mean(hit))


def spearman(y, p):
    from scipy.stats import spearmanr
    with np.errstate(invalid="ignore"):
        if len(np.unique(p)) < 2 or len(np.unique(y)) < 2:
            return None
        try:
            return float(spearmanr(y, p).statistic)
        except Exception:
            return None


def ndcg_at_k(y_true: np.ndarray, y_pred: np.ndarray, k: int = 10,
              better: str = "higher") -> float | None:
    """Ranking quality: NDCG@k treating the true label as the gain. For
    `better='higher'` larger labels rank first (e.g. conductivity); for
    'lower' smaller labels rank first (e.g. energy above hull)."""
    if len(y_true) == 0 or len(y_pred) != len(y_true):
        return None
    sign = 1.0 if better == "higher" else -1.0
    order = np.argsort(-sign * np.asarray(y_pred))[:k]
    gains = np.asarray(y_true)[order]
    ideal_order = np.argsort(-sign * np.asarray(y_true))[:k]
    ideal_gains = np.asarray(y_true)[ideal_order]
    g_all = np.concatenate([gains, ideal_gains])
    offset = g_all.min()
    gains = 2.0 ** (gains - offset) - 1.0
    ideal_gains = 2.0 ** (ideal_gains - offset) - 1.0
    dcg = sum(gains[i] / math.log2(i + 2.0) for i in range(len(gains)))
    ideal = sum(ideal_gains[i] / math.log2(i + 2.0)
                for i in range(len(ideal_gains)))
    if ideal <= 0:
        return None
    return float(dcg / ideal)


def compute_metrics(task: BenchmarkTask, y_true, y_pred,
                    proba=None) -> dict:
    y_true = np.asarray(y_true, dtype=float)
    if task.task_type == "classification":
        y_pred = np.asarray(y_pred)
        m = {"accuracy": accuracy(y_true, y_pred),
             "macro_f1": macro_f1(y_true, y_pred)}
        n_classes = len(np.unique(y_true))
        if proba is not None and n_classes == 2:
            m["roc_auc"] = roc_auc(y_true, proba)
        if "top5_accuracy" in task.doc_metrics or task.metric == "top5_accuracy":
            if proba is not None:
                m["top5_accuracy"] = top5_accuracy(y_true, proba)
        return m
    if task.task_type == "ranking":
        m = {"mae": mae(y_true, y_pred), "rmse": rmse(y_true, y_pred),
             "spearman": spearman(y_true, y_pred),
             "ndcg10": ndcg_at_k(y_true, y_pred, k=10, better=task.better)}
        return m
    return {"mae": mae(y_true, y_pred), "rmse": rmse(y_true, y_pred),
            "r2": r2(y_true, y_pred)}


def _models(task: BenchmarkTask):
    from sklearn.dummy import DummyClassifier, DummyRegressor
    from sklearn.ensemble import RandomForestClassifier, RandomForestRegressor
    from sklearn.linear_model import LogisticRegression, Ridge
    from sklearn.neural_network import MLPClassifier, MLPRegressor
    from sklearn.pipeline import Pipeline
    from sklearn.preprocessing import StandardScaler

    if task.task_type == "regression" or task.task_type == "ranking":
        n_est = 100 if task.task_type == "ranking" else 200
        return {
            "dummy": DummyRegressor(strategy="mean"),
            "ridge": Pipeline([("s", StandardScaler()),
                               ("m", Ridge(alpha=1.0))]),
            "rf": RandomForestRegressor(n_estimators=n_est, random_state=0,
                                        n_jobs=-1),
            "mlp": Pipeline([("s", StandardScaler()),
                             ("m", MLPRegressor(
                                 hidden_layer_sizes=(64, 32),
                                 max_iter=2000, random_state=0,
                                 early_stopping=True, n_iter_no_change=20))]),
        }
    n_est = 100 if task.id == "space_group_classification" else 200
    return {
        "dummy": DummyClassifier(strategy="most_frequent"),
        "logistic": Pipeline([("s", StandardScaler()),
                              ("m", LogisticRegression(max_iter=3000,
                                                       random_state=0))]),
        "rf": RandomForestClassifier(n_estimators=n_est, random_state=0,
                                     n_jobs=-1),
        "mlp": Pipeline([("s", StandardScaler()),
                         ("m", MLPClassifier(
                             hidden_layer_sizes=(64, 32),
                             max_iter=2000, random_state=0,
                             early_stopping=True, n_iter_no_change=20))]),
    }


def _fit_eval(task: BenchmarkTask, labeled: pd.DataFrame,
              tr: pd.DataFrame, te: pd.DataFrame) -> dict:
    feats = select_features(labeled, task)
    Xnum = _numeric_frame(labeled, feats)
    Xtr = Xnum.loc[tr.index].to_numpy(dtype=float)
    Xte = Xnum.loc[te.index].to_numpy(dtype=float)
    means = np.where(np.all(np.isnan(Xtr), axis=0), 0.0, np.nanmean(Xtr, axis=0))
    Xtr = np.where(np.isnan(Xtr), means, Xtr)
    Xte = np.where(np.isnan(Xte), means, Xte)
    ytr = tr["_y"].to_numpy()
    yte = te["_y"].to_numpy()

    results = {"task": task.id, "name": task.name, "task_type": task.task_type,
               "metric": task.metric, "target": task.target,
               "n_train": int(len(tr)), "n_test": int(len(te)),
               "n_features": len(feats), "n_classes": int(len(np.unique(ytr))),
               "features_used": feats, "models": {},
               "evaluation": "split_test"}
    for name, model in _models(task).items():
        try:
            model.fit(Xtr, ytr)
            if task.task_type == "classification" and hasattr(model, "predict_proba"):
                proba = model.predict_proba(Xte)
                yp = np.argmax(proba, axis=1)
                two_col = proba[:, 1] if proba.shape[1] == 2 else proba
                m = compute_metrics(task, yte, yp, proba=two_col)
            else:
                m = compute_metrics(task, yte, model.predict(Xte))
        except Exception as e:  # a model may legitimately fail (e.g. 1-class fold)
            m = {"error": repr(e)}
        results["models"][name] = m
    return results


def _run_grouped_cv(task: BenchmarkTask, labeled: pd.DataFrame,
                    n_splits: int = 5) -> dict:
    """Grouped K-fold CV on the labeled subset (groups = family, so a family is
    never split across train and test — the same guarantee the split files
    enforce for the other tasks)."""
    from sklearn.model_selection import GroupKFold

    families = labeled["identity.family"].fillna("unknown").astype(str)
    unique = families.unique()
    if len(unique) < n_splits:
        n_splits = max(2, len(unique))
    gkf = GroupKFold(n_splits=n_splits)
    feats = select_features(labeled, task)
    Xnum = _numeric_frame(labeled, feats)
    y = labeled["_y"].to_numpy()
    agg: dict[str, list[dict]] = {"dummy": [], "ridge": [], "rf": [],
                                  "logistic": [], "mlp": []}
    for tr_idx, te_idx in gkf.split(labeled, y, groups=families):
        Xtr = Xnum.iloc[tr_idx].to_numpy(dtype=float)
        Xte = Xnum.iloc[te_idx].to_numpy(dtype=float)
        means = np.where(np.all(np.isnan(Xtr), axis=0), 0.0,
                         np.nanmean(Xtr, axis=0))
        Xtr = np.where(np.isnan(Xtr), means, Xtr)
        Xte = np.where(np.isnan(Xte), means, Xte)
        ytr, yte = y[tr_idx], y[te_idx]
        for name, model in _models(task).items():
            try:
                model.fit(Xtr, ytr)
                if task.task_type == "classification" and hasattr(model, "predict_proba"):
                    proba = model.predict_proba(Xte)
                    yp = np.argmax(proba, axis=1)
                    two_col = proba[:, 1] if proba.shape[1] == 2 else proba
                    m = compute_metrics(task, yte, yp, proba=two_col)
                else:
                    m = compute_metrics(task, yte, model.predict(Xte))
                agg[name].append(m)
            except Exception:
                pass
    models: dict[str, dict] = {}
    for name, runs in agg.items():
        if not runs:
            continue
        merged: dict = {}
        for k in runs[0]:
            vals = [r[k] for r in runs if r.get(k) is not None]
            merged[k] = (sum(vals) / len(vals)) if vals else None
        models[name] = merged
    return {"task": task.id, "name": task.name, "task_type": task.task_type,
            "metric": task.metric, "target": task.target,
            "n_train": int(len(labeled)), "n_test": int(len(labeled)),
            "n_features": len(feats), "n_classes": int(len(set(y))),
            "features_used": feats, "models": models,
            "evaluation": f"grouped_cv_k{n_splits}"}


def run_task(task: BenchmarkTask, frame: pd.DataFrame,
             split_map: dict[str, str],
             prefer_grouped_cv: bool = False) -> dict:
    """Evaluate a task on the leakage-checked splits.

    frame: canonical + descriptors DataFrame (rows carry identity.material_id).
    split_map: material_id -> 'train' | 'val' | 'test' (test rows are the only
    held-out evaluation set; val is unused by the deterministic baselines).
    prefer_grouped_cv: force grouped K-fold CV even when a train/test pair
    exists. The scarce σ_RT-labeled tasks sit entirely in the gold split under
    the random regime, so they are always evaluated by grouped CV there; this
    flag makes OOD regimes comparable by using the same evaluation on every
    regime instead of producing degenerate near-empty train folds.
    """
    mask = task.label_mask(frame)
    labeled = frame.loc[mask].copy()
    if len(labeled) == 0:
        return {"task": task.id, "n_train": 0, "n_test": 0,
                "error": "no labeled rows in this frame"}
    y = task.extract_y(frame).loc[mask]

    labeled["_y"] = y.values
    if task.task_type == "classification" and task.threshold is None:
        codes, _uniques = pd.factorize(y.astype(str))
        labeled["_y"] = codes

    split = labeled["identity.material_id"].map(split_map)
    tr = labeled[split == "train"]
    te = labeled[split == "test"]
    if prefer_grouped_cv or len(te) < SCARCE_TEST_MIN or len(tr) < SCARCE_TEST_MIN:
        # Small-labeled tasks (e.g. the scarce σ_RT subset, all of which sits
        # in the gold split) cannot use the train/test split files, and under
        # an OOD regime a task whose every labeled row lands in one split has
        # no usable train/test pair. In both cases fall back to grouped K-fold
        # CV on the labeled subset (groups = material family, so no family
        # leaks between folds).
        return _run_grouped_cv(task, labeled)
    return _fit_eval(task, labeled, tr, te)
