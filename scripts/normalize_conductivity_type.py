#!/usr/bin/env python3
"""Normalize `ion_transport.conductivity_type` (guide §5 action 4).

Problem: the column is typed `ConductivityType | None` (a str-Enum) in the
schema, but different writers pushed different representations into the
canonical parquet — `"ConductivityType.total"`, `"total"`,
`"ConductivityType.bulk"`, `"bulk"`, and `None`. Any downstream filter like
`df[df.conductivity_type == "total"]` silently misses the 71 rows stored as
`"ConductivityType.total"` — a classic enum-leak data-quality bug, and one
that matters scientifically: OBELiX's single biggest noise control is the
bulk-vs-total distinction (total includes grain-boundary resistance).

Fix (deterministic, documented):
  - `"ConductivityType.total"` / `"total"`        -> `"total"`
  - `"ConductivityType.bulk"` / `"bulk"`          -> `"bulk"`
  - `"ConductivityType.grain_boundary"`/`"grain"` -> `"grain_boundary"`
  - label_available rows with None type           -> `"unknown"`
    (per guide: default to unknown, never guess bulk vs total from context)
  - everything else stays None.

Also emits an audit report (before/after distribution + per-DOI breakdown) so
the normalization is reviewable, not silent.

Usage:
    python scripts/normalize_conductivity_type.py             # rewrite in place
    python scripts/normalize_conductivity_type.py --dry-run   # audit only
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

CANONICAL = ROOT / "cleaning_output/canonical_dataset.parquet"
OUT = ROOT / "validation_output/conductivity_type_audit.json"

COL = "ion_transport.conductivity_type"
LABEL = "ion_transport.label_available"


def normalize_value(raw) -> str | None:
    if raw is None:
        return None
    s = str(raw).strip().lower()
    if s in ("conductivitytype.total", "total"):
        return "total"
    if s in ("conductivitytype.bulk", "bulk"):
        return "bulk"
    if s in ("conductivitytype.grain_boundary", "grain_boundary", "grain"):
        return "grain_boundary"
    return None


def audit(canon: pd.DataFrame) -> dict:
    labeled = canon[canon[LABEL] == True]  # noqa: E712
    before = canon[COL].value_counts(dropna=False).to_dict()
    before = {str(k): int(v) for k, v in before.items()}
    labeled_before = labeled[COL].value_counts(dropna=False).to_dict()
    labeled_before = {str(k): int(v) for k, v in labeled_before.items()}
    # per-DOI type breakdown (labeled rows only)
    doi_type = {}
    for doi, grp in labeled.groupby("text_provenance.source_doi"):
        doi_type[str(doi)] = grp[COL].fillna("None").astype(str).value_counts().to_dict()
    return {
        "before_total": before,
        "before_labeled": labeled_before,
        "n_labeled_rows": int(len(labeled)),
        "doi_type_breakdown": doi_type,
        "n_labeled_unknown_will_be_stamped": int(
            (labeled[COL].isna()).sum()),
    }


def apply(canon: pd.DataFrame) -> pd.DataFrame:
    canon = canon.copy()
    raw = canon[COL]
    norm = raw.map(normalize_value)
    # labeled rows with None -> "unknown" (documented, not guessed)
    labeled_mask = canon[LABEL] == True  # noqa: E712
    norm = norm.where(~(labeled_mask & norm.isna()), "unknown")
    canon[COL] = norm
    return canon


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--canonical", type=Path, default=CANONICAL)
    ap.add_argument("--dry-run", action="store_true",
                    help="write audit report only, do not rewrite canonical")
    args = ap.parse_args()

    canon = pd.read_parquet(args.canonical)
    if COL not in canon.columns:
        raise ValueError(f"{COL} missing from {args.canonical}")
    audit_report = audit(canon)

    canon2 = apply(canon)
    after = canon2[COL].value_counts(dropna=False).to_dict()
    audit_report["after_labeled"] = {
        str(k): int(v) for k, v in
        canon2[canon2[LABEL] == True][COL].value_counts(dropna=False).to_dict().items()  # noqa: E712
    }
    audit_report["after_all"] = {str(k): int(v) for k, v in after.items()}
    audit_report["n_rows_changed"] = int((
        canon[COL].fillna("__NA__") != canon2[COL].fillna("__NA__")).sum())

    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps(audit_report, indent=2))
    print(f"wrote audit report {OUT}")

    if args.dry_run:
        print("[dry-run] canonical not modified")
        return
    canon2.to_parquet(args.canonical, index=False)
    print(f"normalized {audit_report['n_rows_changed']} rows; "
          f"wrote {args.canonical}")


if __name__ == "__main__":
    main()
