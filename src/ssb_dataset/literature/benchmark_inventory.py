"""Scandium Benchmark inventory — canonical solid electrolytes (Phase 7 roadmap).

Thin backwards-compatible facade: BENCHMARK_INVENTORY is derived from the rich,
family-organized module ``benchmark_materials.py`` (the single source of truth).
New entries must be added there, not here.

Target: ~300 well-known solid electrolytes, each with a canonical DOI, that
form the gold benchmark set. Every value here is a *verification target* drawn
from canonical literature — it must be hand-checked against the cited paper
before it becomes a `verified_human` record.

Usage: the benchmark check in validation.py reads BENCHMARK_COMPOUNDS; this
inventory is the working list for growing that check to ~300 entries. Records
in this file that are not yet in the dataset are gaps the literature pipeline
should fill.

Convention:
  - sigma_S_per_cm: room-temperature (≈298 K) value from the cited paper.
  - Ea_eV: activation energy from the cited paper.
  - status: "verified" (already hand-checked, in dataset) | "target" (not yet).
"""

from __future__ import annotations

from ssb_dataset.literature.benchmark_materials import iter_benchmark_entries

# composition -> canonical values + DOI. Values are reference targets for
# manual verification; do NOT promote to verified_human without checking the
# cited paper. Derived from benchmark_materials.py — keep the source of truth
# there.
BENCHMARK_INVENTORY: dict[str, dict] = {
    entry["formula"]: {
        "formula": entry["formula"],
        "sigma_S_per_cm": entry.get("sigma_S_per_cm"),
        "Ea_eV": entry.get("Ea_eV"),
        "doi": entry.get("doi"),
        "family": entry.get("family"),
        "status": entry.get("status"),
        "confidence": entry.get("confidence"),
        "note": entry.get("note", ""),
    }
    for entry in iter_benchmark_entries()
    if entry.get("formula")
}
