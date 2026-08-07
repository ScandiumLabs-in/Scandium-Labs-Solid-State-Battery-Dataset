"""ScandiumBench — deterministic split regimes.

A research-grade benchmark needs reproducible, chemically-meaningful splits —
not just one random split. This module produces per-material split assignments
for five regimes, all deterministic (no RNG state, no network):

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
  paper_ood         OBELiX-style leakage-free split: entries are grouped by
                    (paper of origin, composition), so any two entries sharing
                    a source paper OR a composition must land in the same
                    split. This is the field's current best practice for
                    experimental labels — without it, near-identical
                    measurements reported in one paper can straddle train and
                    test and inflate benchmark numbers. Bulk DFT rows (no
                    paper) fall back to composition-only grouping.

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

REGIMES = ("random", "family_ood", "composition_ood",
           "crystal_system_ood", "paper_ood")

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
    """Reuse the Phase-6 leakage-checked split assignment unchanged.

    Loads the persisted split map (`benchmark_output/splits/random.parquet`,
    committed to the repo) when present, falling back to the Phase-6 feature
    split files for backwards compatibility. Raises a descriptive error when
    neither source exists instead of silently returning an empty map — an
    empty split map looks like "no rows assigned" and quietly corrupts every
    downstream benchmark metric.
    """
    persisted = OUT / "random.parquet"
    if persisted.exists():
        df = pd.read_parquet(persisted)
        return {
            str(mid): split
            for mid, split in zip(df["material_id"].astype(str),
                                  df["split"].astype(str))
        }

    missing = [str(p) for p in SPLIT_FILES.values() if not p.exists()]
    if missing:
        raise FileNotFoundError(
            "random regime split map unavailable: "
            f"persisted map {persisted} is missing and Phase-6 split files "
            f"are absent ({', '.join(missing)}). Build the splits with "
            "`python scripts/run_scandium_bench.py` (or run the Phase-6 "
            "featurization pipeline) before evaluating the random regime."
        )
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


def paper_ood_split_map(df: pd.DataFrame) -> dict[str, str]:
    """Leakage-free split grouped by (paper of origin OR composition).

    OBELiX's rule, verbatim: any two entries sharing a paper *or* a
    composition must land in the same split. That is a union constraint, so we
    build connected components (union-find) over two edge types — same source
    DOI, and same reduced formula — and assign each whole component to one
    split. A paper reporting a doping series (N LATP variants from one study)
    forms one component and can never straddle train/test.

    Bulk DFT rows have no paper (source_doi null); their components are
    single compositions, so the regime degrades cleanly to composition-only
    grouping on the full corpus.
    """
    df = df.reset_index(drop=True)
    n = len(df)
    if n == 0:
        return {}
    parent = list(range(n))

    def find(i: int) -> int:
        while parent[i] != i:
            parent[i] = parent[parent[i]]
            i = parent[i]
        return i

    def union(a: int, b: int) -> None:
        ra, rb = find(a), find(b)
        if ra != rb:
            parent[rb] = ra

    def _vals(col: str) -> pd.Series:
        if col not in df.columns:
            return pd.Series([""] * n, index=df.index)
        s = df[col].fillna("").astype(str)
        return s

    paper = _vals("text_provenance.source_doi")
    formula = _vals("identity.reduced_formula")

    # edges: same paper (only for non-empty DOIs) and same composition
    paper_groups: dict[str, list[int]] = {}
    formula_groups: dict[str, list[int]] = {}
    for i in range(n):
        p = paper.iloc[i]
        f = formula.iloc[i]
        if p:
            paper_groups.setdefault(p, []).append(i)
        formula_groups.setdefault(f, []).append(i)
    for group in paper_groups.values():
        for i in range(1, len(group)):
            union(group[0], group[i])
    for group in formula_groups.values():
        for i in range(1, len(group)):
            union(group[0], group[i])

    # assign whole components by stable hash of the component's min row
    out: dict[str, str] = {}
    comp_key: dict[int, str] = {}
    for i in range(n):
        root = find(i)
        if root not in comp_key:
            # representative key: paper first, else formula (deterministic)
            p, f = paper.iloc[root], formula.iloc[root]
            comp_key[root] = (p + "::" + f) if p else ("::" + f)
        mid = str(df["identity.material_id"].iloc[i])
        out[mid] = _group_bucket(comp_key[root])
    return out


def build_split_map(regime: str, df: pd.DataFrame) -> dict[str, str]:
    if regime == "random":
        return random_split_map()
    if regime == "family_ood":
        return family_ood_split_map(df)
    if regime == "composition_ood":
        return composition_ood_split_map(df)
    if regime == "crystal_system_ood":
        return crystal_system_ood_split_map(df)
    if regime == "paper_ood":
        return paper_ood_split_map(df)
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
    "paper_ood": ("OBELiX-style leakage-free split: entries grouped by "
                  "(paper of origin, composition); any two entries sharing "
                  "either must land in the same split. Bulk DFT rows (no "
                  "paper) fall back to composition-only grouping."),
}
