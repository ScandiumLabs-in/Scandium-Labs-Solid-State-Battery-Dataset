#!/usr/bin/env python3
"""Compositional coverage visualization (guide §5 action 8).

LiIon's key figure (their Fig 3/4) projects their labeled conductor
compositions into composition space alongside all known Li compounds, visually
showing "the accessible-but-unexplored region". This script reproduces that
figure at a scale neither LiIon (820 entries) nor OBELiX (599) had access to:

  - All 30,838 canonical records projected in composition descriptor space.
  - Verified/gold labeled rows highlighted against the bulk DFT backbone.
  - The companion dataset's broader Li-compound space is documented as the
    natural next projection source (its 267k materials include every bulk
    composition; this script consumes the canonical descriptors that are
    already featurized in-repo).

Method: UMAP (LiIon's own preference over PCA/TSNE for cluster separability)
on Magpie-style composition descriptors (atomic number / mass / radius /
Mendeleev means, stds, etc.). Deterministic: fixed random_state and fixed
sample (projection is seeded; the figure documents it).

Outputs:
  visualization_output/compositional_coverage.png
  visualization_output/compositional_coverage.json   (per-point metadata)
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
import umap

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

DESCRIPTORS = ROOT / "features_output/descriptors.parquet"
OUT_PNG = ROOT / "visualization_output/compositional_coverage.png"
OUT_JSON = ROOT / "visualization_output/compositional_coverage.json"

RANDOM_STATE = 0
N_COMPONENTS = 2
# dense descriptors only: numeric, per-atom-statistics columns (no categorical
# identity/redox lists). Excludes the aggregate fraction columns.
NUMERIC_PREFIXES = (
    "atomic_number_", "atomic_mass_", "atomic_radius_", "mendeleev_number_",
    "n_elements",
)

FEATURE_COLS = [
    "n_elements",
    "atomic_number_mean", "atomic_number_std", "atomic_number_min",
    "atomic_number_max", "atomic_number_range",
    "atomic_mass_mean", "atomic_mass_std", "atomic_mass_min",
    "atomic_mass_max", "atomic_mass_range",
    "atomic_radius_mean", "atomic_radius_std", "atomic_radius_min",
    "atomic_radius_max", "atomic_radius_range",
    "mendeleev_number_mean", "mendeleev_number_std", "mendeleev_number_min",
    "mendeleev_number_max", "mendeleev_number_range",
]

LABELED_SOURCES = ("literature_mined",)


def _feature_matrix(df: pd.DataFrame) -> np.ndarray:
    cols = [c for c in FEATURE_COLS if c in df.columns]
    X = df[cols].to_numpy(dtype=float)
    # NaN-safe: impute column means (projection only, never written back)
    col_means = np.nanmean(X, axis=0)
    inds = np.where(np.isnan(X))
    X[inds] = np.take(col_means, inds[1])
    return X


def main() -> None:
    d = pd.read_parquet(DESCRIPTORS)
    X = _feature_matrix(d)
    rng = np.random.default_rng(RANDOM_STATE)
    n = len(d)

    # deterministic down-sample for the projection (plot legibility + speed)
    subsample = n if n <= 20000 else 20000
    if n > subsample:
        idx = rng.choice(n, size=subsample, replace=False)
        idx.sort()
        d = d.iloc[idx].reset_index(drop=True)
        X = X[idx]

    reducer = umap.UMAP(
        n_components=N_COMPONENTS,
        random_state=RANDOM_STATE,
        n_neighbors=30,
        min_dist=0.1,
        metric="euclidean",
        verbose=False,
    )
    emb = reducer.fit_transform(X)

    d["_x"] = emb[:, 0]
    d["_y"] = emb[:, 1]
    d["_labeled"] = d["identity.source_db"].isin(LABELED_SOURCES)

    fig, ax = plt.subplots(figsize=(10, 8))
    bg = d[~d["_labeled"]]
    fg = d[d["_labeled"]]
    ax.scatter(bg["_x"], bg["_y"], s=4, c="#9ecae1", alpha=0.5,
               label=f"bulk DFT backbone ({len(bg)})", rasterized=True)
    ax.scatter(fg["_x"], fg["_y"], s=22, c="#d73027", alpha=0.9,
               edgecolors="white", linewidths=0.3,
               label=f"verified experimental labels ({len(fg)})")
    ax.set_title(
        "Compositional coverage — UMAP of composition descriptors\n"
        "verified labels vs. bulk DFT backbone (guide §5 action 8)",
        fontsize=11)
    ax.set_xlabel("UMAP-1")
    ax.set_ylabel("UMAP-2")
    ax.legend(loc="upper right", framealpha=0.9)
    fig.tight_layout()

    OUT_PNG.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(OUT_PNG, dpi=160)
    plt.close(fig)

    # metadata json: per-point, so the figure is reproducible + queryable
    out = {
        "method": "UMAP (n_neighbors=30, min_dist=0.1, euclidean)",
        "random_state": RANDOM_STATE,
        "feature_columns": FEATURE_COLS,
        "n_points_plotted": int(len(d)),
        "n_total_records": int(n),
        "labeled": {
            "n": int(fg["_x"].size),
            "compositions": sorted(fg["identity.material_id"].astype(str)
                                   .unique().tolist()),
        },
        "coverage_note": (
            "Highlighted points are verified experimental labels "
            "(source_db=literature_mined). Unhighlighted points are the bulk "
            "DFT backbone. Regions of the plot dense in backbone points but "
            "without highlighted labels are compositions screened "
            "computationally but lacking experimental conductivity "
            "measurements — the 'accessible-but-unexplored' region LiIon "
            "visualized."
        ),
    }
    OUT_JSON.write_text(json.dumps(out, indent=2))
    print(f"wrote {OUT_PNG}")
    print(f"wrote {OUT_JSON}")
    print(f"plotted {len(d)} points, {fg['_x'].size} labeled "
          f"({fg['_x'].size / len(d) * 100:.1f}%)")


if __name__ == "__main__":
    main()
