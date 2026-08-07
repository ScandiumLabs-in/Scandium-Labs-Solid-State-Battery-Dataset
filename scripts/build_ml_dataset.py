#!/usr/bin/env python3
"""Build the Phase 19 ML-ready export (``dataset_ml/``).

Crystal graphs (CrystalNN + 5 A cutoff fallback) for all 21,528
structure-bearing Materials Project rows, benchmark targets (dense
regression/classification + sparse consensus σ_RT ranking), and the
leakage-checked train/val/test/gold splits, in a PyG/DGL/MatGL/ALIGNN/MACE-
compatible layout.

Usage:
  python scripts/build_ml_dataset.py              # full build
  python scripts/build_ml_dataset.py --limit 100  # smoke test
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from ssb_dataset.ml.build import build_dataset  # noqa: E402


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--limit", type=int, default=0,
                    help="restrict to first N structured materials (smoke test)")
    ap.add_argument("--jobs", type=int, default=8,
                    help="parallel workers for graph prebuild")
    ap.add_argument("--out", type=Path, default=ROOT / "dataset_ml")
    args = ap.parse_args()

    meta = build_dataset(limit=args.limit, out_dir=args.out, jobs=args.jobs)
    print(json.dumps(meta, indent=2))


if __name__ == "__main__":
    main()
