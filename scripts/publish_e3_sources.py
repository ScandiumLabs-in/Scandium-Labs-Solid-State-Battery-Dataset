#!/usr/bin/env python3
"""Publish the Phase E3 structural connectors into partitioned staging.

The E3 connectors (AFLOW, OQMD, COD, Materials Cloud) were re-enabled in the
source layer but no script ever harvested them into `staging/`, so the release
dataset only contains materials_project / jarvis / nomad / literature_mined
records. This script closes that gap: it runs each connector and writes the
records to `staging/<source>/<family>/part-*.parquet` using the exact same
column scheme + family-partitioned layout as `publish_mp_to_staging.py` and
`expand_sources.py`, so the canonical merge (Phase 4) picks them up unchanged.

Usage:
  python scripts/publish_e3_sources.py                   # all four sources
  python scripts/publish_e3_sources.py --source cod      # single source
  python scripts/publish_e3_sources.py --limit 500       # cap per source
  python scripts/publish_e3_sources.py --dry-run         # report counts only
"""

from __future__ import annotations

import argparse
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

from ssb_dataset.sources.aflow_connector import AFLOWConnector
from ssb_dataset.sources.cod_connector import CODConnector
from ssb_dataset.sources.materials_cloud_connector import MaterialsCloudConnector
from ssb_dataset.sources.oqmd_connector import OQMDConnector

STAGING = BASE / "staging"

FULL_COLUMNS = [
    "identity.material_id",
    "identity.source_db",
    "identity.source_id",
    "identity.family",
    "identity.subfamily_tag",
    "identity.is_electrolyte_candidate",
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

LATTICE_KEYS = ("a", "b", "c", "alpha", "beta", "gamma")


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


def _family_value(family: object) -> str:
    return family.value if hasattr(family, "value") else str(family)


def _lattice_flat(lattice: dict) -> dict[str, float]:
    return {k: float(lattice.get(k, 90.0 if k in ("alpha", "beta", "gamma") else 0.0) or 0.0) for k in LATTICE_KEYS}


def _row_from_material(m: object, source_db: str, material_id: str, source_id: str) -> dict[str, object]:
    """Serialize a connector MaterialRecord into a staging row (mirrors the
    expand_sources.py serialization, reading from the dataclass fields)."""
    row = make_row()
    row["identity.material_id"] = material_id
    row["identity.source_db"] = source_db
    row["identity.source_id"] = source_id
    row["identity.family"] = _family_value(m.identity.family)
    row["identity.is_electrolyte_candidate"] = bool(m.identity.is_electrolyte_candidate)
    row["identity.ingestion_date"] = datetime.now(timezone.utc)
    row["identity.confidence_tier"] = "dft_native"
    struct = m.structure
    if struct:
        row["structure.structure_relaxed"] = struct.structure_relaxed or None
        row["structure.space_group"] = struct.space_group or None
        if struct.lattice_params:
            row.update({f"structure.lattice_params.{k}": v for k, v in _lattice_flat(
                {k: getattr(struct.lattice_params, k) for k in LATTICE_KEYS}).items()})
        if struct.is_experimental_structure is not None:
            row["structure.is_experimental_structure"] = bool(struct.is_experimental_structure)
    return row


def harvest(conn: object, limit: int) -> list[dict[str, object]]:
    rows: list[dict[str, object]] = []
    try:
        conn.connect()
    except Exception as exc:
        print(f"  {conn.source_db}: connect FAILED — {exc}")
        return rows
    source_db = conn.source_db
    for raw in conn.fetch_records(limit=limit):
        try:
            m = conn.to_material_record(raw)
        except Exception as exc:
            print(f"  {source_db}: to_material_record error — {exc}")
            continue
        rows.append(
            _row_from_material(
                m,
                source_db=source_db,
                material_id=m.identity.material_id,
                source_id=m.identity.source_id,
            )
        )
        if limit and len(rows) >= limit:
            break
    return rows


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
    parser.add_argument("--source", choices=["aflow", "oqmd", "cod", "materials_cloud", "all"], default="all")
    parser.add_argument("--limit", type=int, default=1000)
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()

    sources: list[tuple[str, object]] = []
    if args.source in ("all", "aflow"):
        sources.append(("aflow", AFLOWConnector()))
    if args.source in ("all", "oqmd"):
        sources.append(("oqmd", OQMDConnector()))
    if args.source in ("all", "cod"):
        sources.append(("cod", CODConnector()))
    if args.source in ("all", "materials_cloud"):
        sources.append(("materials_cloud", MaterialsCloudConnector()))

    for label, conn in sources:
        print(f"\n=== Harvesting {label} (limit {args.limit}) ===")
        rows = harvest(conn, args.limit)
        print(f"  {label}: {len(rows)} records harvested")
        if args.dry_run:
            continue
        write_staging(rows, STAGING / label, label)


if __name__ == "__main__":
    main()
