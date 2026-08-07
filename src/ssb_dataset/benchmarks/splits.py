"""ScandiumBench v1.0 — deterministic split regimes.

A research-grade benchmark needs reproducible, chemically-meaningful splits —
not just one random split. This module produces per-material split assignments
for four regimes, all deterministic (no RNG state, no network):

  random            existing Phase-6 leakage-checked train/val/test split
                    (reused unchanged so results stay comparable to prior
                    releases)
  family_ood        test = whole hold-out families (chemistries never seen in
                    train). Default hold-out: the non-oxide electrolyte
                    families — training on oxides + unknown and testing on
                    halides/sulfides/etc. answers the question that actually
                    matters for SSB discovery: does an oxide-trained model
                    generalize to other chemistries?
  composition_ood   whole reduced-formula groups are assigned to one split, so
                    no composition appears in both train and test. Generalizes
                    to compositions never seen during training.
  crystal_system_ood  whole crystal systems are assigned to one split, so the
                    model never trains on a test-time crystal system.

Group assignment uses a stable hash of the group key, so a split never changes
run-to-run and no group straddles the train/test boundary.

Every regime emits {material_id: split} plus a manifest of hold-out groups and
sizes so the benchmark is auditable.
"""

from __future__ import annotations

import hashlib
import json
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parent.parent.parent.parent
OUT = ROOT / "benchmark_output" / "splits"

REGIMES = ("random", "family_ood", "composition_ood", "crystal_system_ood")

# Family OOD hold-out: the non-oxide electrolyte chemistries. Training set is
# then oxides + unknown (Li intermetallics/nitrides); test is the families the
# model has never seen — the SSB-relevant generalization question.
FAMILY_OOD_HOLDOUT = (
    "halide", "sulfide", "nasicon", "hydride", "polymer_composite",
    "borohydride", "antiperovskite", "garnet", "perovskite", "argyrodite",
)

VAL_FRAC = 0.10
TEST_FRAC = 0.20

SPLIT_FILES = {
    "train": ROOT / "features_output/train.parquet",
    "val": ROOT / "features_output/val.parquet",
    "test": ROOT / "features_output/test.parquet",
    "gold_benchmark": ROOT / "features_output/gold.parquet",
}


# ---------------------------------------------------------------------------
# hash helpers
# ---------------------------------------------------------------------------


def _group_bucket(key: str, val_frac: float = VAL_FRAC,
                  test_frac: float = TEST_FRAC) -> str:
    """Deterministic split bucket for a group key."""
    h = int(hashlib.md5(key.encode("utf-8")).hexdigest(), 16)
    bucket = h % 1000
    val_end = int(val_frac * 1000)
    test_end = val_end + int(test_frac * 1000)
    if bucket < val_end:
        return "val"
    if bucket < test_end:
        return "test"
    return "train"


# ---------------------------------------------------------------------------
# regime builders
# ---------------------------------------------------------------------------


def random_split_map() -> dict[str, str]:
    """Reuse the Phase-6 leakage-checked split assignment unchanged."""
    out: dict[str, str] = {}
    for split, path in SPLIT_FILES.items():
        if not path.exists():
            continue
        df = pd.read_parquet(path, columns=["identity.material_id"])
        for mid in df["identity.material_id"].dropna().astype(str):
            out[mid] = "train" if split == "train" else (
                "test" if split == "test" else split)
    return out


def _grouped_split_map(df: pd.DataFrame, group_col: str,
                       holdout: tuple[str, ...] = ()) -> dict[str, str]:
    """Assign whole groups to one split; holdout groups become test."""
    df = df.copy()
    df["_grp"] = df[group_col].fillna("unknown").astype(str)
    out: dict[str, str] = {}
    holdout_set = set(holdout)
    for mid, grp in zip(df["identity.material_id"].astype(str), df["_grp"]):
        if grp in holdout_set:
            out[mid] = "test"
        else:
            out[mid] = _group_bucket(grp)
    return out


def family_ood_split_map(df: pd.DataFrame,
                         holdout: tuple[str, ...] = FAMILY_OOD_HOLDOUT,
                         ) -> dict[str, str]:
    return _grouped_split_map(df, "identity.family", holdout)


def composition_ood_split_map(df: pd.DataFrame) -> dict[str, str]:
    return _grouped_split_map(df, "identity.reduced_formula")


def crystal_system_ood_split_map(df: pd.DataFrame) -> dict[str, str]:
    return _grouped_split_map(df, "structure.crystal_system")


def build_split_map(regime: str, df: pd.DataFrame) -> dict[str, str]:
    if regime == "random":
        return random_split_map()
    if regime == "family_ood":
        return family_ood_split_map(df)
    if regime == "composition_ood":
        return composition_ood_split_map(df)
    if regime == "crystal_system_ood":
        return crystal_system_ood_split_map(df)
    raise ValueError(f"unknown regime: {regime}")


# ---------------------------------------------------------------------------
# manifests + persistence
# ---------------------------------------------------------------------------


def _split_sizes(df: pd.DataFrame, split_map: dict[str, str]) -> dict:
    s = df["identity.material_id"].astype(str).map(split_map)
    return {k: int((s == k).sum()) for k in ("train", "val", "test")}


def _holdout_groups(df: pd.DataFrame, group_col: str,
                    holdout: tuple[str, ...]) -> dict:
    sizes = {}
    for grp in holdout:
        n = int((df[group_col].fillna("unknown").astype(str) == grp).sum())
        if n:
            sizes[grp] = n
    return sizes


def build_manifests(df: pd.DataFrame) -> dict:
    out = {}
    for regime in REGIMES:
        smap = build_split_map(regime, df)
        man = {
            "regime": regime,
            "description": REGIME_DESCRIPTIONS[regime],
            "split_sizes": _split_sizes(df, smap),
        }
        if regime == "family_ood":
            man["holdout_families"] = _holdout_groups(
                df, "identity.family", FAMILY_OOD_HOLDOUT)
        out[regime] = man
    return out


def persist(df: pd.DataFrame, out_dir: Path = OUT) -> dict:
    """Write per-regime material_id->split parquet + manifest.json."""
    out_dir.mkdir(parents=True, exist_ok=True)
    for regime in REGIMES:
        smap = build_split_map(regime, df)
        rows = pd.DataFrame(
            {"material_id": list(smap.keys()),
             "split": list(smap.values())})
        rows.to_parquet(out_dir / f"{regime}.parquet", index=False)
    manifests = build_manifests(df)
    (out_dir / "manifest.json").write_text(json.dumps(manifests, indent=2))
    return manifests


REGIME_DESCRIPTIONS = {
    "random": "Phase-6 leakage-checked random split (reused unchanged).",
    "family_ood": ("Held-out-family split: test families (halide, sulfide, "
                   "nasicon, hydride, polymer_composite, borohydride, "
                   "antiperovskite, garnet, perovskite, argyrodite) never "
                   "appear in train. Tests oxide-trained generalization to "
                   "unseen chemistries."),
    "composition_ood": ("Held-out-composition split: no reduced formula "
                        "appears in both train and test (stable group hash "
                        "assignment)."),
    "crystal_system_ood": ("Held-out-crystal-system split: whole crystal "
                           "systems assigned to one split by stable group "
                           "hash."),
}
