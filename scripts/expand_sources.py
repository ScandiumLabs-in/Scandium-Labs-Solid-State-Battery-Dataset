#!/usr/bin/env python3
"""Expand the staging dataset toward the 25,000-record release target.

Fixes the JARVIS connector's stale schema key (struct -> atoms) and harvests
ALL Li-containing JARVIS-DFT entries plus a larger NOMAD Li batch into the
partitioned staging layout, then re-runs the canonical merge (Phase 4).

Usage:
  python scripts/expand_sources.py            # full run (jarvis + nomad)
  python scripts/expand_sources.py --source jarvis
  python scripts/expand_sources.py --source nomad --limit 3000
  python scripts/expand_sources.py --dry-run  # report counts, write nothing
"""

from __future__ import annotations

import argparse
import re
import sys
from datetime import datetime, timezone
from pathlib import Path

import numpy as np
import pandas as pd
import pyarrow as pa
import pyarrow.parquet as pq

BASE = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(BASE))
sys.path.insert(0, str(BASE / "src"))

from ssb_dataset.sources.classifier import classify_family

STAGING_JARVIS = BASE / "staging" / "jarvis"
STAGING_NOMAD = BASE / "staging" / "nomad"

LATTICE_KEYS = ("a", "b", "c", "alpha", "beta", "gamma")

FAMILIES = (
    "antiperovskite",
    "argyrodite",
    "borohydride",
    "garnet",
    "halide",
    "hydride",
    "nasicon",
    "oxide",
    "perovskite",
    "polymer",
    "sulfide",
    "unknown",
)

FULL_COLUMNS = [
    "identity.material_id",
    "identity.source_db",
    "identity.source_id",
    "identity.family",
    "identity.subfamily_tag",
    "identity.ingestion_date",
    "identity.schema_version",
    "identity.confidence_tier",
    "structure.structure_relaxed",
    "structure.structure_unrelaxed",
    "structure.space_group",
    "structure.lattice_params",
    "structure.li_site_occupancy",
    "structure.coordination_environment",
    "structure.structure_type",
    "structure.is_experimental_structure",
    "thermodynamics.formation_energy_per_atom",
    "thermodynamics.energy_above_hull",
    "thermodynamics.band_gap",
    "thermodynamics.decomposition_products",
    "thermodynamics.electrochemical_stability_window",
    "thermodynamics.functional_used",
    "ion_transport.sigma_RT",
    "ion_transport.sigma_vs_T_curve",
    "ion_transport.activation_energy_Ea",
    "ion_transport.conductivity_type",
    "ion_transport.conductivity_source_type",
    "ion_transport.measurement_method",
    "ion_transport.temperature_range_measured",
    "ion_transport.label_available",
    "mechanical.bulk_modulus",
    "mechanical.shear_modulus",
    "mechanical.elastic_tensor",
    "synthesis.precursors",
    "synthesis.synthesis_route",
    "synthesis.synthesis_atmosphere",
    "synthesis.requires_interlayer",
    "synthesis.processing_metadata",
    "ml_features.graph_representation",
    "ml_features.composition_descriptors",
    "ml_features.symmetry_descriptors",
    "ml_features.split_assignment",
    "ml_features.split_group_key",
    "text_provenance.source_doi",
    "text_provenance.source_paper_title",
    "text_provenance.extraction_method",
    "text_provenance.extraction_confidence_score",
    "text_provenance.extraction_reviewer",
]


def make_row(**kw: object) -> dict[str, object]:
    row = {c: None for c in FULL_COLUMNS}
    row.update(kw)
    return row


def clean_record_dict(df: pd.DataFrame) -> pd.DataFrame:
    for col in df.columns:
        s = df[col]
        if s.dtype == object:
            non_null = s.dropna()
            if non_null.map(lambda v: isinstance(v, (list, tuple, np.ndarray))).all():
                df[col] = s.map(lambda v: list(v) if isinstance(v, (np.ndarray, tuple)) else v)
            elif non_null.map(lambda v: isinstance(v, (int, float, np.integer, np.floating))).all():
                df[col] = pd.to_numeric(s, errors="coerce")
            elif s.isna().all():
                df[col] = pd.Series([None] * len(df), index=df.index, dtype=object)
    return df


# ---------------------------------------------------------------------------
# JARVIS
# ---------------------------------------------------------------------------
def _num(v: object) -> object:
    """Coerce JARVIS 'na'/'' placeholders to None, pass floats through."""
    if v is None:
        return None
    if isinstance(v, str):
        v = v.strip()
        if v in ("", "na", "nan", "None"):
            return None
        try:
            return float(v)
        except ValueError:
            return None
    return v


def harvest_jarvis(limit: int | None = None) -> list[dict[str, object]]:
    from jarvis.db.figshare import data

    all_data = data("dft_3d")
    rows: list[dict[str, object]] = []
    seen: set[str] = set()
    for entry in all_data:
        formula = entry.get("formula", "") or ""
        if not (re.match(r"^Li\d", formula) or re.match(r"^Li[0-9A-Z]", formula) or formula == "Li"):
            continue
        jid = entry.get("jid", "")
        if jid in seen:
            continue
        seen.add(jid)
        elements = set()
        atoms = entry.get("atoms")
        try:
            if isinstance(atoms, dict):
                elements = {el for el in atoms.get("elements", []) if isinstance(el, str)}
        except Exception:
            elements = set()
        family = classify_family(elements=elements or None)
        family_value = family.value if hasattr(family, "value") else str(family)
        lattice = {}
        try:
            if isinstance(atoms, dict):
                abc = atoms.get("abc") or {}
                angles = atoms.get("angles") or {}
                lattice = {
                    "a": abc[0] if isinstance(abc, (list, tuple)) and len(abc) > 0 else 0.0,
                    "b": abc[1] if isinstance(abc, (list, tuple)) and len(abc) > 1 else 0.0,
                    "c": abc[2] if isinstance(abc, (list, tuple)) and len(abc) > 2 else 0.0,
                    "alpha": angles[0] if isinstance(angles, (list, tuple)) and len(angles) > 0 else 90.0,
                    "beta": angles[1] if isinstance(angles, (list, tuple)) and len(angles) > 1 else 90.0,
                    "gamma": angles[2] if isinstance(angles, (list, tuple)) and len(angles) > 2 else 90.0,
                }
        except Exception:
            lattice = {}
        rows.append(
            make_row(
                **{
                    "identity.material_id": f"jarvis-{jid}",
                    "identity.source_db": "jarvis",
                    "identity.source_id": jid,
                    "identity.family": family_value,
                    "identity.ingestion_date": datetime.now(timezone.utc),
                    "identity.confidence_tier": "dft_native",
                    "structure.space_group": entry.get("spg_symbol") or entry.get("spg", ""),
                    "structure.lattice_params.a": lattice.get("a", 0.0),
                    "structure.lattice_params.b": lattice.get("b", 0.0),
                    "structure.lattice_params.c": lattice.get("c", 0.0),
                    "structure.lattice_params.alpha": lattice.get("alpha", 90.0),
                    "structure.lattice_params.beta": lattice.get("beta", 90.0),
                    "structure.lattice_params.gamma": lattice.get("gamma", 90.0),
                    "thermodynamics.formation_energy_per_atom": _num(entry.get("formation_energy_peratom")),
                    "thermodynamics.band_gap": _num(entry.get("optb88vdw_bandgap")),
                    "mechanical.bulk_modulus": _num(entry.get("bulk_modulus_kv")),
                    "mechanical.shear_modulus": _num(entry.get("shear_modulus_gv")),
                }
            )
        )
        if limit and len(rows) >= limit:
            break
    return rows


# ---------------------------------------------------------------------------
# NOMAD
# ---------------------------------------------------------------------------
def harvest_nomad(limit: int = 3000) -> list[dict[str, object]]:
    import httpx

    rows: list[dict[str, object]] = []
    params: dict = {
        "query": {"results.material.elements": {"all": ["Li"]}},
        "pagination": {"page_size": min(limit, 100)},
    }
    page_after = None
    client = httpx.Client(base_url="https://nomad-lab.eu/prod/v1/api", timeout=120)
    try:
        while len(rows) < limit:
            if page_after:
                params["pagination"]["page_after_value"] = page_after
            resp = client.post("/v1/entries/query", json=params, timeout=60)
            resp.raise_for_status()
            data = resp.json()
            for entry in data.get("data", []):
                results = entry.get("results", {})
                material = results.get("material", {})
                elements = set(material.get("elements", []))
                if "Li" not in elements:
                    continue
                entry_id = entry.get("entry_id", "")
                family = classify_family(elements=elements)
                family_value = family.value if hasattr(family, "value") else str(family)
                rows.append(
                    make_row(
                        **{
                            "identity.material_id": f"nomad-{entry_id}",
                            "identity.source_db": "nomad",
                            "identity.source_id": entry_id,
                            "identity.family": family_value,
                            "identity.ingestion_date": datetime.now(timezone.utc),
                            "identity.confidence_tier": "dft_native",
                            "structure.structure_relaxed": entry.get("cif") or None,
                            "structure.space_group": material.get("symmetry", {}).get("space_group_symbol", ""),
                        }
                    )
                )
                if len(rows) >= limit:
                    break
            pagination = data.get("pagination", {})
            page_after = pagination.get("next_page_after_value")
            if not page_after:
                break
    finally:
        client.close()
    return rows


# ---------------------------------------------------------------------------
# Staging writer (family-partitioned, same scheme as publish_mp_to_staging)
# ---------------------------------------------------------------------------
def write_staging(rows: list[dict[str, object]], source_dir: Path, source_label: str) -> None:
    if not rows:
        print(f"  {source_label}: no records — nothing written")
        return
    df = clean_record_dict(pd.DataFrame(rows))
    fam_col = "identity.family"
    if source_dir.exists():
        for old in source_dir.rglob("*.parquet"):
            old.unlink()
    for fam in df[fam_col].fillna("unknown").unique():
        sub = df[df[fam_col].fillna("unknown") == fam]
        fam_dir = source_dir / str(fam)
        fam_dir.mkdir(parents=True, exist_ok=True)
        for old in fam_dir.glob("part-*.parquet"):
            old.unlink()
        for i, start in enumerate(range(0, len(sub), 500)):
            chunk = sub.iloc[start : start + 500]
            pq.write_table(pa.Table.from_pandas(chunk), fam_dir / f"part-{i:04d}.parquet")
    print(f"  {source_label}: wrote {len(df)} records across {df[fam_col].nunique()} families")


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--source", choices=["jarvis", "nomad", "both"], default="both")
    parser.add_argument("--jarvis-limit", type=int, default=None)
    parser.add_argument("--nomad-limit", type=int, default=3000)
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()

    runs = []
    if args.source in ("jarvis", "both"):
        runs.append(("jarvis", lambda: harvest_jarvis(args.jarvis_limit)))
    if args.source in ("nomad", "both"):
        runs.append(("nomad", lambda: harvest_nomad(args.nomad_limit)))

    for label, fn in runs:
        print(f"\n=== Harvesting {label} ===")
        try:
            rows = fn()
            print(f"  {label}: {len(rows)} records harvested")
        except Exception as exc:
            print(f"  {label}: FAILED — {exc}")
            continue
        if args.dry_run:
            print(f"  {label}: dry-run, not writing")
            continue
        source_dir = STAGING_JARVIS if label == "jarvis" else STAGING_NOMAD
        write_staging(rows, source_dir, label)


if __name__ == "__main__":
    main()
