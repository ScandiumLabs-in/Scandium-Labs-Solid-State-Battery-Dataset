"""ScandiumBench v1.0 — split-regime determinism + OOD guarantees.

Covers the four split regimes (random / family_ood / composition_ood /
crystal_system_ood): deterministic output, no group straddling the
train/test boundary, and the runner's grouped-CV-vs-split-test routing.
"""

from __future__ import annotations

import numpy as np
import pandas as pd
import pytest

from ssb_dataset.benchmarks.splits import (
    FAMILY_OOD_HOLDOUT, REGIMES, build_split_map, _group_bucket,
)
from ssb_dataset.benchmarks.tasks import get_task


def _synthetic_frame(n: int = 200) -> pd.DataFrame:
    rng = np.random.RandomState(0)
    families = ("oxide", "unknown", "halide", "sulfide", "nasicon")
    crystals = ("cubic", "hexagonal", "tetragonal", "triclinic")
    rows = []
    for i in range(n):
        rows.append({
            "identity.material_id": f"m{i}",
            "identity.reduced_formula": f"F{i % 40}",
            "identity.family": families[i % len(families)],
            "structure.crystal_system": crystals[i % len(crystals)],
            "thermodynamics.is_stable": bool(rng.rand() > 0.5),
        })
    df = pd.DataFrame(rows)
    df["thermodynamics.is_metal"] = df["thermodynamics.is_stable"].map(
        lambda s: not s)
    df.loc[::3, "negative.is_negative_result"] = True
    df.loc[1::3, "negative.is_negative_result"] = False
    df["ion_transport.sigma_RT"] = np.nan
    df.loc[:19, "ion_transport.sigma_RT"] = 10.0 ** -np.linspace(2, 5, 20)
    return df


# ---------------------------------------------------------------------------
# regime definitions
# ---------------------------------------------------------------------------


def test_regimes_exist():
    assert set(REGIMES) == {"random", "family_ood", "composition_ood",
                            "crystal_system_ood", "paper_ood"}


def test_family_ood_holdout_nonempty_and_defined():
    assert len(FAMILY_OOD_HOLDOUT) >= 8
    assert "oxide" not in FAMILY_OOD_HOLDOUT
    assert "unknown" not in FAMILY_OOD_HOLDOUT


# ---------------------------------------------------------------------------
# determinism
# ---------------------------------------------------------------------------


def test_split_maps_deterministic():
    df = _synthetic_frame()
    for regime in REGIMES:
        m1 = build_split_map(regime, df)
        m2 = build_split_map(regime, df)
        assert m1 == m2


def test_group_bucket_is_stable_hash():
    a = _group_bucket("Li7La3Zr2O12")
    b = _group_bucket("Li7La3Zr2O12")
    assert a == b


# ---------------------------------------------------------------------------
# OOD guarantees: a group never straddles train/test
# ---------------------------------------------------------------------------


def _group_stride_check(df, group_col, split_map):
    df = df.copy()
    df["_grp"] = df[group_col].fillna("unknown").astype(str)
    df["_s"] = df["identity.material_id"].astype(str).map(split_map)
    straddlers = df.groupby("_grp")["_s"].nunique()
    return int((straddlers[straddlers == 2]).sum())


def test_composition_ood_no_group_straddle():
    df = _synthetic_frame()
    smap = build_split_map("composition_ood", df)
    # train/test boundary: no reduced formula in both
    df["_s"] = df["identity.material_id"].astype(str).map(smap)
    g = df.groupby("identity.reduced_formula")["_s"].nunique()
    assert int((g[g == 2]).sum()) == 0


def test_crystal_system_ood_no_group_straddle():
    df = _synthetic_frame()
    smap = build_split_map("crystal_system_ood", df)
    df["_s"] = df["identity.material_id"].astype(str).map(smap)
    g = df.groupby("structure.crystal_system")["_s"].nunique()
    assert int((g[g == 2]).sum()) == 0


def _paper_aware_frame():
    """Synthetic frame with paper+composition columns for paper_ood tests."""
    df = _synthetic_frame()
    df["text_provenance.source_doi"] = [f"doi{i % 5}" for i in range(len(df))]
    return df


def test_paper_ood_no_paper_or_composition_straddle():
    from ssb_dataset.benchmarks.splits import paper_ood_split_map
    df = _paper_aware_frame()
    smap = paper_ood_split_map(df)
    df["_s"] = df["identity.material_id"].astype(str).map(smap)
    # no source DOI appears in both train and test
    g = df.groupby("text_provenance.source_doi")["_s"].nunique()
    assert int((g[g == 2]).sum()) == 0
    # no reduced formula appears in both train and test
    g2 = df.groupby("identity.reduced_formula")["_s"].nunique()
    assert int((g2[g2 == 2]).sum()) == 0


def test_paper_ood_doping_series_stays_together():
    # One paper reporting N variants of one composition must not straddle —
    # the union-find grouping treats same-paper rows as one component.
    import pandas as pd
    from ssb_dataset.benchmarks.splits import paper_ood_split_map
    df = pd.DataFrame({
        "identity.material_id": [f"LATP{i}" for i in range(4)] + ["Li2O"],
        "text_provenance.source_doi": ["doiA"] * 4 + [None],
        "identity.reduced_formula": [f"LATP{i}" for i in range(4)] + ["Li2O"],
        "identity.family": ["nasicon"] * 4 + ["oxide"],
        "structure.crystal_system": ["hexagonal"] * 5,
        "thermodynamics.is_stable": [True] * 5,
        "thermodynamics.is_metal": [False] * 5,
    })
    smap = paper_ood_split_map(df)
    series_splits = {smap[f"LATP{i}"] for i in range(4)}
    assert len(series_splits) == 1
    assert smap["Li2O"] in {"train", "val", "test"}


def test_paper_ood_empty_frame_returns_empty():
    import pandas as pd
    from ssb_dataset.benchmarks.splits import paper_ood_split_map
    df = pd.DataFrame({
        "identity.material_id": pd.Series(dtype=str),
        "text_provenance.source_doi": pd.Series(dtype=str),
        "identity.reduced_formula": pd.Series(dtype=str),
    })
    assert paper_ood_split_map(df) == {}


def test_family_ood_holdout_families_all_test():
    df = _synthetic_frame()
    smap = build_split_map("family_ood", df)
    for fam in FAMILY_OOD_HOLDOUT:
        fam_rows = df[df["identity.family"] == fam]
        if len(fam_rows):
            splits = {smap[mid] for mid in fam_rows["identity.material_id"].astype(str)}
            assert splits == {"test"}, f"family {fam} not fully held out"


def test_family_ood_train_excludes_holdout():
    df = _synthetic_frame()
    smap = build_split_map("family_ood", df)
    for mid, s in smap.items():
        fam = df.loc[df["identity.material_id"].astype(str) == mid,
                     "identity.family"].iloc[0]
        if fam in FAMILY_OOD_HOLDOUT:
            assert s == "test"


def test_random_regime_reuses_phase6_map():
    # The random regime must load the persisted split map (so results stay
    # comparable across releases) rather than re-hashing the frame: the
    # synthetic frame's m-ids must NOT appear as keys.
    from ssb_dataset.benchmarks.splits import OUT, SPLIT_FILES, build_split_map
    df = _synthetic_frame()
    smap = build_split_map("random", df)
    assert len(smap) > 0
    assert set(smap.values()) <= {"train", "val", "test", "gold_benchmark"}
    synthetic_mids = set(df["identity.material_id"].astype(str))
    assert not synthetic_mids & set(smap)
    # and the map must cover the full persisted Phase-6 corpus (unique ids),
    # sourced from whichever split map source random_split_map() used (the
    # committed benchmark split parquet, or the legacy Phase-6 files).
    persisted = OUT / "random.parquet"
    if persisted.exists():
        p = pd.read_parquet(persisted)
        seen = set(p["material_id"].astype(str))
    else:
        seen = set()
        for sp in SPLIT_FILES.values():
            if sp.exists():
                seen.update(pd.read_parquet(sp, columns=["identity.material_id"])
                            ["identity.material_id"].dropna().astype(str))
    assert len(smap) == len(seen)
    assert set(smap) == seen


# ---------------------------------------------------------------------------
# runner routing: scarce tasks -> grouped CV on every regime
# ---------------------------------------------------------------------------


def test_grouped_cv_routing_for_scarce_tasks():
    df = _synthetic_frame()
    # ranking labels are scarce (20 rows) and all unassigned by random map
    from ssb_dataset.benchmarks.evaluate import run_task
    smap = build_split_map("composition_ood", df)
    t = get_task("conductive_candidate_ranking")
    res = run_task(t, df, smap, prefer_grouped_cv=True)
    assert res["evaluation"].startswith("grouped_cv")


def test_grouped_cv_routing_when_split_test_degenerate():
    # If every labeled row lands in one split, must fall back to CV even
    # without the flag.
    from ssb_dataset.benchmarks.evaluate import run_task
    df = _synthetic_frame()
    smap = build_split_map("composition_ood", df)
    t = get_task("negative_result_classification")
    res = run_task(t, df, smap)
    assert res["n_train"] > 0 and res["n_test"] > 0


def test_mlp_baseline_present_in_split_and_cv():
    # Guide §5 action 2 requires RF + MLP as the published baselines; MLP must
    # appear on both the split-test path and the grouped-CV path.
    from ssb_dataset.benchmarks.evaluate import run_task
    df = _synthetic_frame()
    smap = {f"m{i}": ("train" if i % 2 == 0 else "test")
            for i in range(len(df))}
    t = get_task("stability_classification")
    res = run_task(t, df, smap)
    assert res["evaluation"].startswith("split_test")
    assert "mlp" in res["models"] and "macro_f1" in res["models"]["mlp"]
    t2 = get_task("conductive_candidate_ranking")
    res2 = run_task(t2, df, smap, prefer_grouped_cv=True)
    assert res2["evaluation"].startswith("grouped_cv")
    assert "mlp" in res2["models"] and "ndcg10" in res2["models"]["mlp"]


# ---------------------------------------------------------------------------
# boolean-target label handling
# ---------------------------------------------------------------------------


def test_boolean_target_label_mask_excludes_none_only():
    df = _synthetic_frame()
    t = get_task("negative_result_classification")
    mask = t.label_mask(df)
    assert mask.sum() > 0
    # rows with None (unassigned) must be excluded
    none_rows = df["negative.is_negative_result"].isna()
    assert not mask[none_rows].any()
    # rows with False MUST be included (not dropped by a !=0 test)
    false_rows = (df["negative.is_negative_result"] == False).to_numpy()  # noqa: E712
    assert mask[false_rows].all()


def test_boolean_classification_extract_y_gives_two_classes():
    df = _synthetic_frame()
    t = get_task("metallic_classification")
    y = t.extract_y(df)
    assert set(pd.Series(y).astype(str).unique()) <= {"True", "False"}


def test_high_conductivity_threshold_labels():
    df = _synthetic_frame()
    t = get_task("high_conductivity_classification")
    mask = t.label_mask(df)
    assert mask.sum() == 20
    y = t.extract_y(df).loc[mask]
    assert set(y.unique()) == {0, 1}
