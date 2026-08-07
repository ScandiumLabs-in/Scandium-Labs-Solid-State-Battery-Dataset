"""Tests for the Scandium Benchmark Suite (v0.8.0) — task registry,
feature selection, metric functions, and the evaluation harness on synthetic
data (no network, no LLM)."""

from __future__ import annotations

import numpy as np
import pandas as pd
import pytest

from ssb_dataset.benchmarks.evaluate import (
    compute_metrics,
    ndcg_at_k,
    run_task,
    select_features,
)
from ssb_dataset.benchmarks.tasks import BENCHMARK_TASKS, get_task


# --------------------------------------------------------------------------
# Registry
# --------------------------------------------------------------------------

def test_registry_complete():
    ids = [t.id for t in BENCHMARK_TASKS]
    assert len(ids) == 25
    for required in ("formation_energy_regression", "band_gap_regression",
                     "energy_above_hull_regression", "density_regression",
                     "volume_regression", "ionic_radius_regression",
                     "stability_classification", "wide_gap_classification",
                     "family_classification", "crystal_system_classification",
                     "space_group_classification",
                     "conductive_candidate_ranking",
                     "negative_result_classification",
                     "metallic_classification",
                     "high_conductivity_classification",
                     "activation_energy_regression",
                     "sigma_RT_regression",
                     "bulk_modulus_regression",
                     "shear_modulus_regression",
                     "debye_temperature_regression",
                     "is_magnetic_classification",
                     "packing_fraction_regression",
                     "electroneutral_classification",
                     "li_hopping_distance_regression",
                     "electrolyte_candidate_classification"):
        assert required in ids


def test_registry_metadata_sane():
    for t in BENCHMARK_TASKS:
        assert t.id and t.name and t.target
        assert t.task_type in ("regression", "classification", "ranking")
        assert t.metric
        assert t.target not in t.leaky_cols  # a target must never leak itself
    for t in BENCHMARK_TASKS:
        if t.task_type == "classification":
            assert t.metric in ("accuracy", "macro_f1", "roc_auc",
                                "top5_accuracy")
        elif t.task_type == "ranking":
            assert t.metric == "ndcg10"


def test_get_task():
    assert get_task("band_gap_regression") is not None
    assert get_task("does_not_exist") is None
    assert get_task("band_gap_regression").metric == "mae"


def test_leaky_col_discipline():
    # volume regression must exclude density (density = mass / volume)
    vol = get_task("volume_regression")
    assert "structure.density" in vol.leaky_cols
    # band-gap targets must exclude band-derived electronic descriptors
    gap = get_task("band_gap_regression")
    assert "thermodynamics.cbm" in gap.leaky_cols
    assert "thermodynamics.vbm" in gap.leaky_cols
    # stability must exclude energy-above-hull (its direct definition)
    stab = get_task("stability_classification")
    assert "thermodynamics.energy_above_hull" in stab.leaky_cols
    # ranking must exclude measurement-condition fields
    rank = get_task("conductive_candidate_ranking")
    assert "ion_transport.measurement_method" in rank.leaky_cols


def test_threshold_classification():
    t = get_task("wide_gap_classification")
    df = pd.DataFrame({"thermodynamics.band_gap": [3.5, 5.5, None, 4.5]})
    mask = t.label_mask(df)
    assert list(mask) == [True, True, False, True]
    y = t.extract_y(df)
    assert list(y) == [0, 1, 1]
    assert y.dtype == int


def test_boolean_classification_labels():
    t = get_task("stability_classification")
    df = pd.DataFrame({"thermodynamics.is_stable": [True, False, None, True]})
    mask = t.label_mask(df)
    assert list(mask) == [True, True, False, True]  # False is a real label
    y = t.extract_y(df)
    assert list(y) == [True, False, True]


def test_ranking_transform_log10():
    t = get_task("conductive_candidate_ranking")
    df = pd.DataFrame({"ion_transport.sigma_RT": [0.001, 0.0, None, 0.01]})
    mask = t.label_mask(df)
    assert list(mask) == [True, False, False, True]
    y = t.extract_y(df)
    np.testing.assert_allclose(y, [-3.0, -2.0], atol=1e-9)


def test_label_mask_numeric_target():
    t = get_task("band_gap_regression")
    df = pd.DataFrame({"thermodynamics.band_gap": [1.5, None, 0.0, 4.5]})
    mask = t.label_mask(df)
    assert list(mask) == [True, False, True, True]


def test_label_bounds_excludes_unphysical_targets():
    # v1.9.0: mechanical tasks gate their labels to a physical window —
    # unphysical MP extremes are excluded, never imputed. Bounds inclusive.
    t = get_task("bulk_modulus_regression")
    df = pd.DataFrame({"mechanical.bulk_modulus": [1.0, 50.0, 999.0,
                                                   1000.0, 1e7, -5.0, None]})
    mask = t.label_mask(df)
    assert list(mask) == [True, True, True, True, False, False, False]
    y = t.extract_y(df)
    assert list(y) == [1.0, 50.0, 999.0, 1000.0]


def test_debye_label_bounds_window():
    t = get_task("debye_temperature_regression")
    df = pd.DataFrame({"mechanical.debye_temperature": [50.0, 3000.0, 37.0,
                                                       9.3e6, None]})
    mask = t.label_mask(df)
    assert list(mask) == [True, True, False, False, False]


def test_mechanical_leaky_discipline():
    # the sibling elastic/vibrational block must never be a feature of a
    # mechanical task (all come from the same elastic-tensor computation)
    bulk = get_task("bulk_modulus_regression")
    assert "mechanical.shear_modulus" in bulk.leaky_cols
    assert "mechanical.debye_temperature" in bulk.leaky_cols
    shear = get_task("shear_modulus_regression")
    assert "mechanical.bulk_modulus" in shear.leaky_cols
    # packing fraction must not see density/volume (packing ~ cell volume)
    pack = get_task("packing_fraction_regression")
    assert "structure.density" in pack.leaky_cols
    assert "structure.volume" in pack.leaky_cols


def test_derived_block_leaky_discipline():
    # the defining descriptors of the new labels are excluded from features
    mag = get_task("is_magnetic_classification")
    assert "magnetic.total_magnetization" in mag.leaky_cols
    assert "magnetic.ordering" in mag.leaky_cols
    neut = get_task("electroneutral_classification")
    assert "redox.average_oxidation" in neut.leaky_cols
    assert "redox.mixed_valence" in neut.leaky_cols
    hop = get_task("li_hopping_distance_regression")
    assert "structure.li_site_count" in hop.leaky_cols
    # the sibling scarce σ_RT label is excluded from the Ea task
    ea = get_task("activation_energy_regression")
    assert "ion_transport.sigma_RT" in ea.leaky_cols


# --------------------------------------------------------------------------
# Feature selection
# --------------------------------------------------------------------------

def _synthetic_df():
    df = pd.DataFrame({
        "identity.material_id": [f"mid{i}" for i in range(20)],
        "identity.family": ["oxide"] * 20,
        "text_provenance.source_doi": ["10.1/x"] * 20,
        "structure.structure_relaxed": [None] * 20,
        "chemistry.atomic_radius_mean": np.random.RandomState(0).rand(20),
        "n_elements": np.random.RandomState(1).randint(1, 6, 20),
        "li_fraction": np.random.RandomState(2).rand(20),
        "space_group_number": np.random.RandomState(3).randint(1, 230, 20),
        "structure.density": np.random.RandomState(4).rand(20),
        "structure.volume": np.random.RandomState(5).rand(20) * 100,
        "thermodynamics.formation_energy_per_atom": (
            np.random.RandomState(6).randn(20)),
        "thermodynamics.band_gap": np.random.RandomState(7).rand(20) * 5,
    })
    return df


def test_select_features_excludes_identity_text_and_target():
    df = _synthetic_df()
    t = get_task("band_gap_regression")
    feats = select_features(df, t)
    assert "identity.material_id" not in feats
    assert "identity.family" not in feats
    assert "text_provenance.source_doi" not in feats
    assert "structure.structure_relaxed" not in feats
    assert "thermodynamics.band_gap" not in feats  # target excluded
    assert "chemistry.atomic_radius_mean" in feats


def test_select_features_respects_leaky_cols():
    df = _synthetic_df()
    t = get_task("volume_regression")
    feats = select_features(df, t)
    assert "structure.density" not in feats
    assert "structure.volume" not in feats


def test_select_features_drops_non_numeric():
    df = _synthetic_df()
    df["family_str"] = ["garnet", "sulfide"] * 10
    t = get_task("band_gap_regression")
    feats = select_features(df, t)
    assert "family_str" not in feats


# --------------------------------------------------------------------------
# Metrics
# --------------------------------------------------------------------------

def test_regression_metrics():
    y = np.array([1.0, 2.0, 3.0, 4.0])
    p = np.array([1.1, 1.9, 3.2, 3.8])
    m = compute_metrics(get_task("band_gap_regression"), y, p)
    assert m["mae"] == pytest.approx(0.15, abs=1e-9)
    assert m["r2"] > 0.9
    assert m["rmse"] > 0


def test_classification_metrics_binary():
    y = np.array([0, 1, 1, 0, 1, 0, 1, 1])
    p = np.array([0, 1, 1, 0, 1, 0, 0, 1])
    proba = np.array([0.1, 0.9, 0.8, 0.2, 0.9, 0.3, 0.4, 0.7])
    m = compute_metrics(get_task("stability_classification"), y, p,
                        proba=proba)
    assert m["accuracy"] == pytest.approx(0.875, abs=1e-9)
    assert m["macro_f1"] > 0.8
    assert m["roc_auc"] > 0.8


def test_top5_accuracy():
    # true class ranked 4th among 6 -> top-5 hit
    y2 = np.array([3])
    p2 = np.array([[0.5, 0.4, 0.05, 0.02, 0.02, 0.01]])
    m = compute_metrics(get_task("space_group_classification"), y2, np.array([0]),
                        proba=p2)
    assert m["top5_accuracy"] == pytest.approx(1.0, abs=1e-9)


def test_ndcg_at_k_perfect_and_reversed():
    y = np.array([-2.0, -4.0, -3.0])
    # perfect ranking (higher true label first)
    perfect = ndcg_at_k(y, np.array([-2.0, -4.0, -3.0]), k=3, better="higher")
    assert perfect is not None and perfect > 0.99
    # reversed ranking should be much worse
    reversed_ = ndcg_at_k(y, np.array([-3.0, -4.0, -2.0]), k=3, better="higher")
    assert reversed_ < perfect


def test_ndcg_constant_label_returns_none():
    y = np.array([-3.0, -3.0, -3.0])
    assert ndcg_at_k(y, np.array([-3.0, -3.0, -3.0]), k=3, better="higher") is None


# --------------------------------------------------------------------------
# Harness on synthetic data
# --------------------------------------------------------------------------

def _synthetic_frame_with_splits():
    rng = np.random.RandomState(0)
    n = 80
    families = ["oxide", "sulfide", "halide", "garnet"] * (n // 4)
    df = pd.DataFrame({
        "identity.material_id": [f"m{i}" for i in range(n)],
        "identity.family": families,
        "chemistry.atomic_radius_mean": rng.rand(n),
        "n_elements": rng.randint(1, 6, n),
        "li_fraction": rng.rand(n),
        "thermodynamics.band_gap": rng.rand(n) * 6.0,
        "thermodynamics.energy_above_hull": rng.rand(n) * 1.5,
        "thermodynamics.is_stable": rng.rand(n) > 0.5,
    })
    split_map = {f"m{i}": ("train" if i % 2 == 0 else "test")
                 for i in range(n)}
    return df, split_map


def test_run_task_regression_synthetic():
    df, split_map = _synthetic_frame_with_splits()
    t = get_task("band_gap_regression")
    res = run_task(t, df, split_map)
    assert res["n_train"] == 40 and res["n_test"] == 40
    assert set(res["models"]) >= {"dummy", "ridge", "rf", "mlp"}
    for m in res["models"].values():
        assert "mae" in m and "r2" in m
    # the real models should at least match or beat the dummy
    assert res["models"]["rf"]["r2"] >= res["models"]["dummy"]["r2"] - 0.3


def test_run_task_classification_synthetic():
    df, split_map = _synthetic_frame_with_splits()
    t = get_task("stability_classification")
    res = run_task(t, df, split_map)
    assert res["n_test"] == 40
    assert "accuracy" in res["models"]["rf"]


def test_run_task_grouped_cv_for_small_labels():
    # Only train rows carry labels (gold-like subset): must fall back to CV.
    df, split_map = _synthetic_frame_with_splits()
    t = get_task("conductive_candidate_ranking")
    df["ion_transport.sigma_RT"] = np.nan
    lab_idx = list(range(10))  # spans all 4 families (0,1:oxide 2,3:sulfide ...)
    df.loc[lab_idx, "ion_transport.sigma_RT"] = 10.0 ** (
        -np.linspace(2, 5, len(lab_idx)))
    # the labeled subset lives in the gold split, not train/test -> CV fallback
    for i in lab_idx:
        split_map[f"m{i}"] = "gold"
    res = run_task(t, df, split_map)
    assert res["n_test"] == len(lab_idx)  # CV reports full labeled size
    assert res["evaluation"].startswith("grouped_cv")
    assert "ndcg10" in res["models"]["rf"]


def test_run_task_empty_labeled_returns_error():
    df, split_map = _synthetic_frame_with_splits()
    t = get_task("band_gap_regression")
    df["thermodynamics.band_gap"] = np.nan
    res = run_task(t, df, split_map)
    assert "error" in res


# --------------------------------------------------------------------------
# v1.9.0 new-task harness checks (synthetic, no network/LLM)
# --------------------------------------------------------------------------

def _synthetic_frame_with_object_targets():
    rng = np.random.RandomState(0)
    n = 40
    families = ["oxide", "sulfide", "halide", "garnet"] * (n // 4)
    df = pd.DataFrame({
        "identity.material_id": [f"m{i}" for i in range(n)],
        "identity.family": families,
        "chemistry.atomic_radius_mean": rng.rand(n),
        "n_elements": rng.randint(1, 6, n),
        "li_fraction": rng.rand(n),
        "structure.volume": rng.rand(n) * 100,
        "structure.density": rng.rand(n),
        "structure.li_hopping_distance": rng.rand(n) * 4,
        "structure.li_site_count": rng.randint(1, 8, n),
        "mechanical.shear_modulus": rng.rand(n) * 300,
        "mechanical.debye_temperature": rng.rand(n) * 2000,
    })
    df["magnetic.is_magnetic"] = [bool(i % 2) for i in range(n)]
    df.loc[::7, "magnetic.is_magnetic"] = None
    df["redox.electroneutral"] = [bool(i % 3 != 1) for i in range(n)]
    df.loc[::9, "redox.electroneutral"] = None
    df["identity.is_electrolyte_candidate"] = [bool(i % 4 != 2)
                                               for i in range(n)]
    df["mechanical.bulk_modulus"] = rng.rand(n) * 300 + 1
    df.loc[:2, "mechanical.bulk_modulus"] = [1e7, -3.0, None]
    df["ion_transport.sigma_RT"] = np.nan
    df["ion_transport.activation_energy_Ea"] = np.nan
    lab_idx = list(range(12))
    df.loc[lab_idx, "ion_transport.sigma_RT"] = 10.0 ** (
        -np.linspace(2, 5, len(lab_idx)))
    df.loc[lab_idx, "ion_transport.activation_energy_Ea"] = np.linspace(
        0.1, 1.2, len(lab_idx))
    split_map = {f"m{i}": ("train" if i % 2 == 0 else "test")
                 for i in range(n)}
    for i in lab_idx:
        split_map[f"m{i}"] = "gold"
    return df, split_map


def test_run_task_object_boolean_classification():
    # new classification targets are object bool columns — must run through
    # the same factorize path as the existing boolean tasks
    df, split_map = _synthetic_frame_with_object_targets()
    for tid in ("is_magnetic_classification",
                "electroneutral_classification",
                "electrolyte_candidate_classification"):
        t = get_task(tid)
        res = run_task(t, df, split_map)
        assert "error" not in res
        assert res["n_test"] > 0
        assert set(res["models"]) >= {"dummy", "logistic", "rf", "mlp"}
        assert "macro_f1" in res["models"]["rf"]


def test_run_task_mechanical_label_bounds():
    # rows with unphysical bulk modulus must never enter training/eval
    df, split_map = _synthetic_frame_with_object_targets()
    t = get_task("bulk_modulus_regression")
    res = run_task(t, df, split_map)
    labeled = t.label_mask(df)
    assert int(labeled.sum()) == 37  # 40 rows minus 2 unphysical + 1 NaN
    assert "error" not in res
    assert res["n_test"] > 0
    assert res["n_features"] >= 3
    assert "mechanical.shear_modulus" not in res["features_used"]


def test_run_task_scarce_transport_grouped_cv():
    # the σ_RT and Ea regression tasks sit in gold -> grouped CV fallback
    df, split_map = _synthetic_frame_with_object_targets()
    for tid in ("sigma_RT_regression", "activation_energy_regression"):
        t = get_task(tid)
        res = run_task(t, df, split_map)
        assert res["evaluation"].startswith("grouped_cv")
        assert res["n_test"] == 12  # all labeled rows, CV-reported
        assert "mae" in res["models"]["rf"]


def test_run_task_tiny_test_split_falls_back_to_cv():
    # a task whose labeled rows reach the test split with only a handful of
    # rows (the v1.9 Ea case: 7 train / 2 test) must NOT report that split —
    # grouped CV is the honest evaluation.
    df, split_map = _synthetic_frame_with_splits()
    t = get_task("band_gap_regression")
    # collapse nearly all test rows into gold, leaving 2 test rows
    for i, s in list(split_map.items()):
        if s == "test" and int(i[1:]) >= 2:
            split_map[i] = "gold"
    res = run_task(t, df, split_map)
    assert res["evaluation"].startswith("grouped_cv")
    assert res["n_test"] == len(df)  # CV reports the full labeled set


def test_sigma_rt_regression_log10():
    t = get_task("sigma_RT_regression")
    assert t.transform == "log10"
    df = pd.DataFrame({"ion_transport.sigma_RT": [0.001, 0.0, None, 0.01]})
    y = t.extract_y(df)
    np.testing.assert_allclose(y, [-3.0, -2.0], atol=1e-9)
