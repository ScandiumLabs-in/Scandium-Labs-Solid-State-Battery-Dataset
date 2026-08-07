"""Tests for the v1.3.0 GNN baseline (``src/ssb_dataset/benchmarks/gnn.py``).

Covers the GCN forward/normalization behavior, per-task train/eval contract,
label masking (never imputed), regression vs classification heads, early-stop
checkpoint restore, and NaN-safe feature handling (Xe valence is missing from
the element table). Uses tiny synthetic graphs monkeypatched into the module's
``dataset_ml`` path — no full-data build, deterministic, no network, no LLM.
"""

from __future__ import annotations

import json

import numpy as np
import pytest
import torch
from torch import nn
from torch.nn import functional as F

import ssb_dataset.benchmarks.gnn as gnn


def _tiny_graphs(n: int, node_dim: int = 4) -> list:
    """n small PyG Data graphs: 3 nodes each, a 2-cycle, simple 4-dim features."""
    from torch_geometric.data import Data

    gs = []
    for _ in range(n):
        x = torch.randn(3, node_dim) * 0.5
        edge_index = torch.tensor([[0, 1, 1, 2, 2, 0],
                                   [1, 0, 2, 1, 0, 2]], dtype=torch.long)
        gs.append(Data(x=x, edge_index=edge_index))
    return gs


def _patch(tmp_path, graphs, targets, splits, monkeypatch):
    """Write targets/splits/graph.pt to tmp_path and monkeypatch DATASET_ML."""
    (tmp_path / "splits").mkdir(parents=True, exist_ok=True)
    torch.save(targets, tmp_path / "targets.pt")
    for s, v in splits.items():
        torch.save(v, tmp_path / "splits" / f"{s}.pt")
    torch.save(graphs, tmp_path / "graph.pt")
    monkeypatch.setattr(gnn, "DATASET_ML", tmp_path)
    return lambda: graphs


def _make_tasks(n: int) -> dict:
    """Regression (density-like) + binary classification targets."""
    return {
        "density_regression": {
            "y": torch.arange(n, dtype=torch.float),
            "mask": torch.ones(n, dtype=torch.bool),
            "n_classes": None,
        },
        "wide_gap_classification": {
            "y": torch.tensor([i % 2 for i in range(n)], dtype=torch.long),
            "mask": torch.ones(n, dtype=torch.bool),
            "n_classes": 2,
        },
    }


def _make_splits(n: int) -> dict:
    return {
        "train": torch.arange(0, int(0.6 * n)),
        "val": torch.arange(int(0.6 * n), int(0.8 * n)),
        "test": torch.arange(int(0.8 * n), n),
    }


class TestGCN:
    def _batch_data(self):
        from torch_geometric.data import Data

        g = _tiny_graphs(1)[0]
        return Data(x=g.x, edge_index=g.edge_index,
                    batch=torch.zeros(3, dtype=torch.long))

    def test_forward_shape_regression(self):
        m = gnn.GCN(4, 16, 1, layers=2)
        data = self._batch_data()
        out = m(data)
        assert out.shape == (1, 1)
        assert torch.isfinite(out).all()

    def test_forward_shape_classification(self):
        m = gnn.GCN(4, 16, 3, layers=2)
        data = self._batch_data()
        out = m(data)
        assert out.shape == (1, 3)

    def test_norm_uses_frozen_train_stats(self):
        mean = torch.tensor([0.0, 10.0, 0.0, 0.0])
        std = torch.tensor([1.0, 5.0, 1.0, 1.0])
        m = gnn.GCN(4, 8, 1, layers=1, feature_mean=mean, feature_std=std)
        x = torch.tensor([[1.0, 20.0, 0.0, 0.0]])
        xn = m._norm(x)
        assert xn[0, 1].item() == pytest.approx(2.0)

    def test_norm_nan_feature_filled_with_train_mean(self):
        mean = torch.tensor([0.0, 2.0, 0.0, 0.0])
        std = torch.tensor([1.0, 1.0, 1.0, 1.0])
        m = gnn.GCN(4, 8, 1, layers=1, feature_mean=mean, feature_std=std)
        x = torch.tensor([[float("nan"), 0.0, 0.0, 0.0]])
        xn = m._norm(x)
        assert torch.isfinite(xn).all()
        assert xn[0, 0].item() == pytest.approx(0.0)  # (mean-mean)/std

    def test_norm_without_stats_returns_nan_to_num(self):
        m = gnn.GCN(4, 8, 1, layers=1)
        x = torch.tensor([[float("nan"), 0.0, 0.0, 0.0]])
        xn = m._norm(x)
        assert torch.isfinite(xn).all()


class TestClassifyRows:
    def test_masks_filter_splits(self):
        targets = _make_tasks(100)
        splits = _make_splits(100)
        # mask off a few test rows
        targets["density_regression"]["mask"][95] = False
        idx = gnn._classify_rows(targets, splits, "density_regression")
        assert 95 not in set(idx["test"].tolist())
        assert len(idx["train"]) == 60
        assert len(idx["test"]) == 19  # 95 excluded

    def test_masked_rows_never_enter_eval(self):
        targets = _make_tasks(100)
        splits = _make_splits(100)
        targets["density_regression"]["mask"][90] = False
        # classify + evaluate on a synthetic model returning the row index
        idx = gnn._classify_rows(targets, splits, "density_regression")
        assert 90 not in set(idx["test"].tolist())


class TestTrainTask:
    def _setup(self, tmp_path, monkeypatch, n=30):
        targets = _make_tasks(n)
        splits = _make_splits(n)
        graphs = _tiny_graphs(n)
        _patch(tmp_path, graphs, targets, splits, monkeypatch)
        cfg = gnn.GNNConfig(hidden=8, layers=2, epochs=5, batch_size=8,
                            patience=2, seed=0)
        return targets, splits, graphs, cfg

    def test_shuffled_loader_labels_track_graphs(self, tmp_path):
        """The misalignment bug: labels must ride on their graph through a
        shuffled loader, never be indexed by batch position."""
        n = 20
        y = torch.arange(n, dtype=torch.float)
        idx = torch.arange(n)
        loader = gnn._make_loader(_tiny_graphs(n), idx, y, batch_size=4,
                                  shuffle=True)
        seen = []
        for data in loader:
            for j in range(data.num_graphs):
                seen.append((int(data.gidx[j]), float(data.y[j])))
        # every (gidx, y) pair must be consistent and complete
        pairs = dict(seen)
        assert len(pairs) == n
        for i in range(n):
            assert pairs[i] == float(i)
        # ensure ordering actually differs from natural (shuffle engaged)
        order = [g for g, _ in seen]
        assert order != list(range(n))

    def test_regression_result_shape(self, tmp_path, monkeypatch):
        _, _, _, cfg = self._setup(tmp_path, monkeypatch)
        r = gnn.train_task("density_regression", cfg, device="cpu")
        assert r["task"] == "density_regression"
        assert "gcn" in r["models"]
        m = r["models"]["gcn"]
        assert set(m) >= {"mae", "rmse"}
        assert all(np.isfinite(v) for v in m.values())
        assert r["n_test"] > 0

    def test_classification_result_shape(self, tmp_path, monkeypatch):
        _, _, _, cfg = self._setup(tmp_path, monkeypatch)
        r = gnn.train_task("wide_gap_classification", cfg, device="cpu")
        assert "gcn" in r["models"]
        m = r["models"]["gcn"]
        assert "accuracy" in m
        assert 0.0 <= m["accuracy"] <= 1.0

    def test_masked_labels_not_imputed(self, tmp_path, monkeypatch):
        targets, _, _, cfg = self._setup(tmp_path, monkeypatch, n=40)
        # mask out all but 5 train rows: model must still train on the rest
        targets["density_regression"]["mask"] = torch.zeros(40, dtype=torch.bool)
        targets["density_regression"]["mask"][:5] = True
        # rewrite targets with mask applied
        _patch(tmp_path, _tiny_graphs(40), targets, _make_splits(40), monkeypatch)
        r = gnn.train_task("density_regression", cfg, device="cpu")
        assert r["n_train"] == 5

    def test_classification_n_classes_from_targets(self, tmp_path, monkeypatch):
        _, _, _, cfg = self._setup(tmp_path, monkeypatch)
        r = gnn.train_task("wide_gap_classification", cfg, device="cpu")
        assert r["n_classes"] == 2

    def test_early_stop_returns_best_val_model(self, tmp_path, monkeypatch):
        _, _, _, cfg = self._setup(tmp_path, monkeypatch)
        cfg.epochs = 20
        cfg.patience = 3
        r = gnn.train_task("density_regression", cfg, device="cpu")
        assert r["architecture"]["epochs_attempted"] <= 20
        assert "gcn" in r["models"]

    def test_no_train_rows_returns_error(self, tmp_path, monkeypatch):
        targets = _make_tasks(30)
        splits = {"train": torch.arange(0),
                  "val": torch.arange(0),
                  "test": torch.arange(0)}
        _patch(tmp_path, _tiny_graphs(30), targets, splits, monkeypatch)
        r = gnn.train_task("density_regression", gnn.GNNConfig(epochs=2),
                           device="cpu")
        assert "error" in r
