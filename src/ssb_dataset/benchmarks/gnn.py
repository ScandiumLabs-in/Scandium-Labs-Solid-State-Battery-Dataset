"""GNN baselines for the Scandium Benchmark Suite (v1.3.0).

Closes the v0.8 gap ("torch is not installed, so GNN/embedding models are the
explicit next step") with a deterministic, CPU-friendly graph baseline trained
on the Phase 19 crystal-graph export (``dataset_ml/``). Every task shares one
small GCN (hidden layers + global mean pool + task head) trained on the
leakage-checked train split and evaluated on the held-out test split with the
*exact same* metric functions as the sklearn baselines, so leaderboard
comparisons are apples-to-apples.

Design rules (mirror the rest of the pipeline):
  - deterministic: torch.manual_seed(0), fixed epochs, best-val checkpoint
  - labels are never imputed: only rows with mask=True enter the loss/eval
  - the conductive-ranking task trains directly on log10 σ_RT labels (the
    graph corpus gives it real train/val/test splits, unlike the sklearn
    path which had to fall back to GroupKFold because gold σ rows lack
    structures)
  - regression/ranking heads output 1 scalar; classification heads output
    n_classes logits
  - no LLM, no network
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any

import numpy as np
import torch
from torch import nn
from torch.nn import functional as F

from ssb_dataset.benchmarks.evaluate import compute_metrics
from ssb_dataset.benchmarks.tasks import get_task

ROOT = Path(__file__).resolve().parent.parent.parent.parent
DATASET_ML = ROOT / "dataset_ml"


@dataclass
class GNNConfig:
    hidden: int = 128
    layers: int = 3
    epochs: int = 60
    batch_size: int = 128
    lr: float = 1e-3
    weight_decay: float = 1e-5
    patience: int = 8
    seed: int = 0
    dropout: float = 0.0


class GCN(torch.nn.Module):
    """Stacked GCNConv layers + global mean pool + task head.

    Node features: per-element vectors (10-dim). Edge features are unused by
    this baseline (bond distance is folded into the adjacency via the graph).
    Regression/ranking heads output a single value; classification heads
    output ``n_classes`` logits.

    ``feature_mean`` / ``feature_std`` (optional) are per-dimension
    normalization statistics learned from the *train split only* and frozen at
    eval — this keeps the raw per-element features (atomic mass ~100 vs
    electronegativity ~1) on a common scale so gradients do not diverge.
    """

    def __init__(self, in_channels: int, hidden: int, n_out: int,
                 layers: int = 3, dropout: float = 0.0,
                 feature_mean: torch.Tensor | None = None,
                 feature_std: torch.Tensor | None = None):
        super().__init__()
        from torch_geometric.nn import GCNConv, global_mean_pool

        self.pool = global_mean_pool
        convs = [GCNConv(in_channels, hidden)]
        for _ in range(layers - 1):
            convs.append(GCNConv(hidden, hidden))
        self.convs = nn.ModuleList(convs)
        self.dropout = dropout
        self.head = nn.Sequential(
            nn.Linear(hidden, hidden),
            nn.ReLU(),
            nn.Linear(hidden, n_out),
        )
        if feature_mean is not None:
            self.register_buffer("feature_mean", feature_mean)
            self.register_buffer("feature_std", feature_std)

    def _norm(self, x: torch.Tensor) -> torch.Tensor:
        # guard against a NaN node feature (e.g. Xe valence is not in the
        # per-element table) — fill with the per-dimension train mean so a
        # single unknown element maps to 0 in normalized space and never
        # poisons an entire batch.
        if torch.isnan(x).any() or torch.isinf(x).any():
            if hasattr(self, "feature_mean"):
                fill = self.feature_mean.unsqueeze(0).to(x.device, x.dtype)
                x = torch.where(torch.isfinite(x), x, fill)
            else:
                x = torch.nan_to_num(x, nan=0.0, posinf=0.0, neginf=0.0)
        if not hasattr(self, "feature_mean"):
            return x
        eps = 1e-8
        return (x - self.feature_mean) / (self.feature_std + eps)

    def forward(self, data) -> torch.Tensor:
        x, edge_index, batch = data.x, data.edge_index, data.batch
        x = self._norm(x)
        for i, conv in enumerate(self.convs):
            x = conv(x, edge_index)
            if i < len(self.convs) - 1:
                x = F.relu(x)
                if self.dropout:
                    x = F.dropout(x, p=self.dropout, training=self.training)
        x = self.pool(x, batch)
        return self.head(x)


# ---------------------------------------------------------------------------
# helpers
# ---------------------------------------------------------------------------


def _task_metrics(task_id: str) -> dict:
    task = get_task(task_id)
    if task is None:
        return {"type": "regression", "metric": "mae"}
    return {"type": task.task_type, "metric": task.metric,
            "name": task.name, "target": task.target}


def _primary_value(task_id: str, m: dict) -> float:
    task = get_task(task_id)
    if task is None:
        return m.get("mae", float("inf"))
    key = task.metric
    if key not in m and "top5_accuracy" in m:
        key = "top5_accuracy"
    val = m.get(key)
    if val is None:
        return float("inf")
    return float(val)


def _primary_dir(task_id: str) -> str:
    task = get_task(task_id)
    if task is None or task.task_type == "regression":
        return "lower"
    return "higher"


def _load_graphs() -> list:
    return torch.load(DATASET_ML / "graph.pt", weights_only=False)


def _make_loader(graphs: list, idx: torch.Tensor, y_all: torch.Tensor | None,
                 batch_size: int, shuffle: bool):
    from torch_geometric.loader import DataLoader

    items = []
    for i in idx.tolist():
        g = graphs[i]
        if y_all is not None:
            g = g.clone() if hasattr(g, "clone") else g
            g.y = y_all[i].float()
            g.gidx = i
        items.append(g)
    return DataLoader(items, batch_size=batch_size, shuffle=shuffle)


def _classify_rows(targets: dict, splits: dict, task_id: str):
    mask = targets[task_id]["mask"]
    out = {}
    for s in ("train", "val", "test"):
        idx = splits[s][mask[splits[s]]]
        out[s] = idx
    return out


def _evaluate(model: GCN, task_id: str, loader, y_all: torch.Tensor,
              mask: torch.Tensor, idx_all: torch.Tensor, n_classes: int | None
              ) -> dict:
    """Collect predictions for masked rows and compute benchmark metrics.

    Each loader item carries ``gidx`` (global row index) and ``y`` attached
    at construction, so predictions align with labels even when the loader
    shuffles (labels never drift from their graphs).
    """
    task = get_task(task_id)
    model.eval()
    pred: dict[int, float] = {}
    proba_rows: dict[int, np.ndarray] = {}
    with torch.no_grad():
        for data in loader:
            out = model(data)  # (n, n_out)
            if task is not None and task.task_type == "classification":
                prob = torch.softmax(out, dim=1).cpu().numpy()
                for j in range(out.shape[0]):
                    gidx = int(data.gidx[j])
                    if bool(mask[gidx]):
                        proba_rows[gidx] = prob[j]
                        pred[gidx] = float(np.argmax(prob[j]))
            else:
                out = out.view(-1)
                for j in range(out.shape[0]):
                    gidx = int(data.gidx[j])
                    if bool(mask[gidx]):
                        pred[gidx] = float(out[j])
    if not pred:
        return {"error": "no masked rows in evaluation set"}
    ys = np.array([float(y_all[g]) for g in sorted(pred)])
    ps = np.array([pred[g] for g in sorted(pred)])

    if task is not None and task.task_type == "classification":
        y_pred = ps.astype(int)
        proba = None
        if proba_rows:
            sorted_g = sorted(proba_rows)
            if n_classes and n_classes == 2:
                proba = np.array([proba_rows[g][1] for g in sorted_g])
            elif (task.metric == "top5_accuracy"
                  or "top5_accuracy" in task.doc_metrics):
                proba = np.array([proba_rows[g] for g in sorted_g])
        return compute_metrics(task, ys, y_pred, proba=proba)
    return compute_metrics(task, ys, ps)


class _EarlyStop:
    def __init__(self, patience: int, mode: str):
        self.patience = patience
        self.mode = mode
        self.best: float | None = None
        self.wait = 0
        self.best_state = None

    def _better(self, metric: float) -> bool:
        if self.best is None:
            return True
        return metric < self.best if self.mode == "lower" else metric > self.best

    def update(self, metric: float, model: nn.Module) -> bool:
        if self._better(metric):
            self.best = metric
            self.wait = 0
            self.best_state = {k: v.detach().clone()
                               for k, v in model.state_dict().items()}
            return False
        self.wait += 1
        return self.wait >= self.patience


def train_task(task_id: str, cfg: GNNConfig | None = None,
               device: str | None = None, graphs: list | None = None
               ) -> dict[str, Any]:
    """Train + evaluate the GCN baseline for one task on dataset_ml.

    Returns a dict shaped like the sklearn task results (task, name,
    models={"gcn": metrics}, n_train, n_test, ...) so the leaderboard
    renderer can merge it unchanged.
    """
    cfg = cfg or GNNConfig()
    torch.manual_seed(cfg.seed)
    np.random.seed(cfg.seed)
    device = device or ("cuda" if torch.cuda.is_available() else "cpu")

    targets = torch.load(DATASET_ML / "targets.pt", weights_only=False)
    splits = {
        s: torch.load(DATASET_ML / "splits" / f"{s}.pt", weights_only=False)
        for s in ("train", "val", "test")
    }
    if task_id not in targets:
        return {"task": task_id, "error": f"task not in dataset_ml targets: {task_id}"}

    tinfo = _task_metrics(task_id)
    task = get_task(task_id)
    y_all = targets[task_id]["y"].float()
    mask = targets[task_id]["mask"]
    n_classes = targets[task_id]["n_classes"]

    idx = _classify_rows(targets, splits, task_id)
    if len(idx["train"]) == 0 or len(idx["test"]) == 0:
        return {"task": task_id, "n_train": int(len(idx["train"])),
                "n_test": int(len(idx["test"])),
                "error": "no labeled rows in train/test splits"}

    graphs = graphs if graphs is not None else _load_graphs()
    node_dim = graphs[0].x.shape[1]

    # Per-dimension normalization statistics from the TRAIN split only (frozen
    # at eval). Atomic mass ~100 vs electronegativity ~1 must share a scale.
    # NaN-safe: one element (Xe) has no valence in the feature table, so
    # statistics must skip non-finite entries rather than propagate them.
    x_tr = torch.cat([graphs[i].x for i in idx["train"].tolist()], dim=0)
    feature_mean = torch.nanmean(x_tr, dim=0)
    x_nan = torch.where(torch.isfinite(x_tr), x_tr, feature_mean.unsqueeze(0))
    feature_std = x_nan.std(dim=0).clamp_min(1e-6)

    # classification heads output n_classes logits
    if task is not None and task.task_type == "classification":
        if n_classes is None:
            n_classes = int(y_all[idx["train"]].max().item() + 1)
        n_out = int(n_classes)
    else:
        n_out = 1

    model = GCN(node_dim, cfg.hidden, n_out, layers=cfg.layers,
                dropout=cfg.dropout,
                feature_mean=feature_mean, feature_std=feature_std).to(device)
    optim = torch.optim.Adam(model.parameters(), lr=cfg.lr,
                             weight_decay=cfg.weight_decay)

    tr_loader = _make_loader(graphs, idx["train"], y_all, cfg.batch_size,
                             shuffle=True)
    va_loader = _make_loader(graphs, idx["val"], y_all, cfg.batch_size,
                             shuffle=False)
    te_loader = _make_loader(graphs, idx["test"], y_all, cfg.batch_size,
                             shuffle=False)

    es = _EarlyStop(cfg.patience, mode=_primary_dir(task_id))
    best_test: dict = {}

    # small labeled ranking task: the train loader may be a single batch
    for epoch in range(1, cfg.epochs + 1):
        model.train()
        for data in tr_loader:
            data = data.to(device)
            out = model(data)
            yb = data.y
            if task is not None and task.task_type == "classification":
                loss = F.cross_entropy(out, yb.long())
            else:
                loss = F.mse_loss(out.view(-1), yb)
            optim.zero_grad()
            loss.backward()
            optim.step()
        va_metrics = _evaluate(model, task_id, va_loader, y_all, mask,
                               idx["val"], n_classes)
        prim = _primary_value(task_id, va_metrics)
        if es.update(prim, model):
            best_test = _evaluate(model, task_id, te_loader, y_all, mask,
                                  idx["test"], n_classes)
        if es.wait >= cfg.patience:
            break

    if es.best_state is not None:
        model.load_state_dict(es.best_state)
        te_loader = _make_loader(graphs, idx["test"], y_all, cfg.batch_size,
                                 shuffle=False)
        best_test = _evaluate(model, task_id, te_loader, y_all, mask,
                              idx["test"], n_classes)

    return {
        "task": task_id,
        "name": tinfo["name"],
        "task_type": tinfo["type"],
        "metric": tinfo["metric"],
        "target": tinfo["target"],
        "n_train": int(len(idx["train"])),
        "n_val": int(len(idx["val"])),
        "n_test": int(len(idx["test"])),
        "n_classes": int(n_classes) if n_classes else None,
        "n_features": int(node_dim),
        "features_used": ["crystal_graph_node_features",
                          "crystal_graph_edges"],
        "models": {"gcn": best_test},
        "evaluation": "split_test (dataset_ml train/val/test)",
        "architecture": {
            "name": "GCN",
            "hidden": cfg.hidden,
            "layers": cfg.layers,
            "epochs_attempted": epoch,
            "patience": cfg.patience,
            "batch_size": cfg.batch_size,
            "lr": cfg.lr,
            "seed": cfg.seed,
        },
    }
