#!/usr/bin/env python3
"""Phase 1 expansion — Materials Project full-catalog harvest.

Downloads EVERY Li-containing compound from the Materials Project summary
database (currently ~21k) and stores, per material:

  data/raw/materials_project/raw_json/<mp-id>.json   raw API doc (never lost)
  data/raw/materials_project/cif/<mp-id>.cif          relaxed structure CIF
  data/raw/materials_project/parsed/...parquet        canonical flat records

Filtering (default): contains Li, NOT radioactive, NOT a gas, structure
present, formation energy present. `--no-filter` keeps everything.

Resumable: raw_json is written incrementally; re-running skips mp-ids that
already have a JSON file. The cif/ and parsed/ outputs are derived from the
raw_json store, so a partial download can always be reprocessed.

Usage:
  python scripts/expand_mp.py                    # filtered full harvest
  python scripts/expand_mp.py --no-filter        # keep everything MP returns
  python scripts/expand_mp.py --limit 500        # small test pull
  python scripts/expand_mp.py --reprocess        # rebuild cif/parsed from raw_json only
"""

from __future__ import annotations

import argparse
import json
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

from dotenv import load_dotenv

load_dotenv()

from pymatgen.core import Composition, Element  # noqa: E402

from ssb_dataset.config.settings import settings  # noqa: E402
from ssb_dataset.schema import (  # noqa: E402
    ConfidenceTier,
    ElectronicBlock,
    Family,
    Functional,
    IdentityProvenance,
    LatticeParams,
    MagneticBlock,
    MaterialRecord,
    SourceDB,
    StructureBlock,
    StructureType,
    ThermodynamicsBlock,
)
from ssb_dataset.sources.classifier import classify_family  # noqa: E402
from ssb_dataset.sources.classifier import is_electrolyte_candidate  # noqa: E402

BASE = Path("data/raw/materials_project")
RAW_DIR = BASE / "raw_json"
CIF_DIR = BASE / "cif"
PARSED_DIR = BASE / "parsed"

FIELDS = [
    "material_id",
    "structure",
    "composition",
    "composition_reduced",
    "formula_pretty",
    "formula_anonymous",
    "chemsys",
    "elements",
    "nelements",
    "nsites",
    "formation_energy_per_atom",
    "energy_above_hull",
    "is_stable",
    "equilibrium_reaction_energy_per_atom",
    "decomposes_to",
    "band_gap",
    "cbm",
    "vbm",
    "efermi",
    "is_gap_direct",
    "is_metal",
    "is_magnetic",
    "ordering",
    "total_magnetization",
    "total_magnetization_normalized_vol",
    "total_magnetization_normalized_formula_units",
    "num_magnetic_sites",
    "num_unique_magnetic_sites",
    "types_of_magnetic_species",
    "symmetry",
    "volume",
    "density",
    "density_atomic",
    "deprecated",
    "deprecation_reasons",
    "origins",
    "warnings",
    "last_updated",
    "task_ids",
    "theoretical",
    "database_IDs",
    "possible_species",
]

# Elements that are radioactive (excluded by default: unstable / hazardous).
RADIOACTIVE = {
    "Po", "At", "Rn", "Fr", "Ra", "Ac", "Th", "Pa", "U", "Np", "Pu",
    "Am", "Cm", "Bk", "Cf", "Es", "Fm", "Md", "No", "Lr", "Rf", "Db",
    "Sg", "Bh", "Hs", "Mt", "Ds", "Rg", "Cn", "Nh", "Fl", "Mc", "Lv",
    "Ts", "Og", "Tc", "Pm",
}

# Elements whose elemental form is a gas at STP.
GAS_ELEMENTS = {"H", "He", "N", "O", "F", "Ne", "Cl", "Ar", "Kr", "Xe"}


def _mp_version() -> str:
    try:
        import mp_api

        return getattr(mp_api, "__version__", "unknown")
    except Exception:
        return "unknown"


def is_radioactive(doc: dict) -> bool:
    for el in doc.get("elements", []) or []:
        if el in RADIOACTIVE:
            return True
    return False


def is_gas(doc: dict) -> bool:
    """True only if EVERY element is a gas at STP (a compound containing O is
    a solid, e.g. Li2O — the whole-material check must be all-gases)."""
    els = doc.get("elements", []) or []
    if not els:
        return False
    return all(el in GAS_ELEMENTS for el in els)


def structure_from_doc(doc: dict):
    """Return the pymatgen Structure for a summary doc (or None)."""
    s = doc.get("structure")
    if s is None:
        return None
    try:
        return s if hasattr(s, "lattice") else None
    except Exception:
        return None


def download_raw(limit: int | None = None, no_filter: bool = False) -> tuple[int, int]:
    """Fetch all Li-containing compounds, write raw_json incrementally.

    Uses the client's chunked search directly (much faster than per-id batch
    queries, which silently trip rate limits). Resumable: material_ids of
    already-written JSON files are excluded up front.

    Returns (downloaded_count, skipped_existing_count).
    """
    if not settings.mp.api_key:
        print("MP_API_KEY not set. Set it in .env or the environment.")
        sys.exit(1)

    from mp_api.client import MPRester

    RAW_DIR.mkdir(parents=True, exist_ok=True)
    CIF_DIR.mkdir(parents=True, exist_ok=True)
    PARSED_DIR.mkdir(parents=True, exist_ok=True)

    fetched = 0
    skipped = 0
    t0 = time.time()

    existing = {p.stem for p in RAW_DIR.glob("*.json")}
    print(f"Existing on disk: {len(existing)} (resume set)")

    with MPRester(api_key=settings.mp.api_key) as mpr:
        # Chunked full-field search across all Li compounds. The client handles
        # pagination; we stop early when reaching `limit` fresh materials.
        query = dict(
            elements=["Li"],
            fields=FIELDS,
            chunk_size=1000,
            num_chunks=None,
        )
        docs = mpr.materials.summary.search(**query)
        for doc in docs:
            d = doc.model_dump()
            mid = d.get("material_id")
            if not mid or mid in existing:
                skipped += 1
                continue
            if limit and fetched >= limit:
                break

            if not no_filter:
                if is_radioactive(d) or is_gas(d):
                    skipped += 1
                    continue
                if d.get("structure") is None:
                    skipped += 1
                    continue
                if d.get("formation_energy_per_atom") is None:
                    skipped += 1
                    continue

            # Serialize structure to a portable dict before storing raw JSON.
            struct = d.get("structure")
            if struct is not None:
                try:
                    if not hasattr(struct, "lattice"):
                        from pymatgen.core import Structure

                        struct = Structure.from_dict(struct)
                    d["structure_dict"] = struct.as_dict()
                    d["structure_cif"] = struct.to(fmt="cif")
                except Exception:
                    d["structure_dict"] = None
                    d["structure_cif"] = None
            d["_mp_api_version"] = _mp_version()
            d["_harvest_ts"] = datetime.now(timezone.utc).isoformat()

            (RAW_DIR / f"{mid}.json").write_text(json.dumps(d, default=str))
            fetched += 1
            existing.add(mid)

            if fetched and fetched % 1000 == 0:
                el = time.time() - t0
                print(f"  ...{fetched} new docs ({el/60:.1f} min)")

    dt = time.time() - t0
    print(f"Downloaded {fetched} docs in {dt/60:.1f} min ({fetched/max(dt,0.001):.1f} docs/s)")
    return fetched, skipped


def process_raw(no_filter: bool = False) -> int:
    """Derive CIF + canonical parquet records from the raw_json store."""
    files = sorted(RAW_DIR.glob("*.json"))
    if not files:
        print("No raw JSON files to process. Run a download first.")
        return 0

    rows: list[dict] = []
    n_cif = 0
    n_records = 0
    n_filtered = 0

    for p in files:
        with open(p) as f:
            d = json.load(f)
        mid = d.get("material_id", p.stem)

        if not no_filter:
            if is_radioactive(d) or is_gas(d):
                n_filtered += 1
                continue
            if d.get("structure_dict") is None:
                n_filtered += 1
                continue
            if d.get("formation_energy_per_atom") is None:
                n_filtered += 1
                continue

        cif = d.get("structure_cif")
        if cif:
            (CIF_DIR / f"{mid}.cif").write_text(cif)
            n_cif += 1

        rec = build_record(d)
        rows.append(flatten_record(rec))
        n_records += 1

    if rows:
        import pandas as pd
        import pyarrow as pa
        import pyarrow.parquet as pq

        df = pd.DataFrame(rows)
        pq.write_table(pa.Table.from_pandas(df), PARSED_DIR / "parsed.parquet")
        print(f"Parsed {n_records} records -> {PARSED_DIR}/parsed.parquet")
        print(f"  CIFs written: {n_cif}, filtered out: {n_filtered}")

    # Metadata manifest
    manifest = {
        "source": "Materials Project summary API",
        "mp_api_version": _mp_version(),
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "total_raw_json": len(files),
        "records_parsed": n_records,
        "cif_written": n_cif,
        "filtered_out": n_filtered,
        "filter": "none" if no_filter else "li,not_radioactive,not_gas,has_structure,has_formation_energy",
    }
    (BASE / "metadata.json").write_text(json.dumps(manifest, indent=2))
    return n_records


def build_record(d: dict) -> MaterialRecord:
    """Convert a raw MP doc into the canonical MaterialRecord schema."""
    mid = d.get("material_id", "")
    struct = None
    if d.get("structure_dict"):
        try:
            from pymatgen.core import Structure

            struct = Structure.from_dict(d["structure_dict"])
        except Exception:
            struct = None

    sym = d.get("symmetry") or {}
    lattice = struct.lattice if struct else None

    # Family classification (deterministic composition + structure rules).
    elements = set(d.get("elements", []) or [])
    family = classify_family(elements=elements, struct=struct)

    comp = d.get("composition_reduced")
    if comp and not isinstance(comp, str):
        try:
            comp = Composition(comp).reduced_formula
        except Exception:
            comp = None
    composition_str = comp or d.get("formula_pretty") or mid

    # Oxidation states from MP possible_species (e.g. ["Li+", "O-", "Fe3+"]).
    oxidation_states: list[int] = []
    import re as _re

    for spec in d.get("possible_species") or []:
        m = _re.match(r"[A-Z][a-z]?(\d*)([+-])", spec or "")
        if not m:
            continue
        mag = 1 if m.group(2) == "+" else -1
        oxidation_states.append((int(m.group(1)) if m.group(1) else 1) * mag)

    return MaterialRecord(
        identity=IdentityProvenance(
            material_id=f"mp-{mid}",
            source_db=SourceDB.materials_project,
            source_id=mid,
            composition=composition_str,
            family=family,
            is_electrolyte_candidate=is_electrolyte_candidate(elements=elements, struct=struct),
            subfamily_tag=[d.get("chemsys", "")] if d.get("chemsys") else [],
            ingestion_date=datetime.now(timezone.utc),
            schema_version="0.1.0",
            confidence_tier=ConfidenceTier.dft_native,
        ),
        structure=StructureBlock(
            structure_relaxed=d.get("structure_cif"),
            structure_unrelaxed=None,
            space_group=sym.get("symbol", "") if isinstance(sym, dict) else str(sym or ""),
            space_group_number=sym.get("number") if isinstance(sym, dict) else None,
            crystal_system=sym.get("crystal_system") if isinstance(sym, dict) else None,
            point_group=sym.get("point_group") if isinstance(sym, dict) else None,
            density=d.get("density"),
            density_atomic=d.get("density_atomic"),
            volume=d.get("volume"),
            nsites=d.get("nsites"),
            lattice_params=LatticeParams(
                a=lattice.a if lattice else 0.0,
                b=lattice.b if lattice else 0.0,
                c=lattice.c if lattice else 0.0,
                alpha=lattice.alpha if lattice else 90.0,
                beta=lattice.beta if lattice else 90.0,
                gamma=lattice.gamma if lattice else 90.0,
            ),
            li_site_occupancy=_li_occupancy(struct),
            structure_type=(
                StructureType.disordered
                if (sym.get("is_disordered", False) if isinstance(sym, dict) else False)
                else StructureType.ordered
            ),
            is_experimental_structure=False,
        ),
        thermodynamics=ThermodynamicsBlock(
            formation_energy_per_atom=d.get("formation_energy_per_atom"),
            energy_above_hull=d.get("energy_above_hull"),
            is_stable=bool(d.get("is_stable")) if d.get("is_stable") is not None else None,
            equilibrium_reaction_energy_per_atom=d.get("equilibrium_reaction_energy_per_atom"),
            band_gap=d.get("band_gap"),
            cbm=d.get("cbm"),
            vbm=d.get("vbm"),
            efermi=d.get("efermi"),
            is_gap_direct=d.get("is_gap_direct"),
            is_metal=d.get("is_metal"),
            decomposition_products=[x.get("formula", "") for x in (d.get("decomposes_to") or [])],
            functional_used=Functional.pbe,
        ),
        magnetic=MagneticBlock(
            is_magnetic=d.get("is_magnetic"),
            ordering=d.get("ordering"),
            total_magnetization=d.get("total_magnetization"),
            total_magnetization_normalized_vol=d.get("total_magnetization_normalized_vol"),
            total_magnetization_normalized_formula_units=d.get("total_magnetization_normalized_formula_units"),
            num_magnetic_sites=d.get("num_magnetic_sites"),
            num_unique_magnetic_sites=d.get("num_unique_magnetic_sites"),
            types_of_magnetic_species=d.get("types_of_magnetic_species") or [],
        ),
        electronic=ElectronicBlock(
            possible_species=d.get("possible_species") or [],
            oxidation_states=oxidation_states,
        ),
    )


def _li_occupancy(struct) -> list[float]:
    if struct is None:
        return []
    occ = []
    for site in struct:
        if "Li" in site.species_string:
            occ.append(site.species.get("Li", 0))
    return occ


def flatten_record(rec: MaterialRecord) -> dict:
    """Flatten the nested record to 'block.field' columns (pipeline format)."""
    flat: dict = {}
    for block_name, block in rec.model_dump().items():
        if isinstance(block, dict):
            for field, value in block.items():
                flat[f"{block_name}.{field}"] = value
        else:
            flat[block_name] = block
    return flat


def main() -> None:
    parser = argparse.ArgumentParser(description="Materials Project full-catalog harvest")
    parser.add_argument("--limit", type=int, default=None, help="only fetch N materials (test)")
    parser.add_argument("--no-filter", action="store_true", help="keep everything MP returns")
    parser.add_argument("--reprocess", action="store_true", help="rebuild cif/parsed from raw_json only")
    args = parser.parse_args()

    if args.reprocess:
        n = process_raw(no_filter=args.no_filter)
        print(f"Reprocess done: {n} records.")
        return

    fetched, skipped = download_raw(limit=args.limit, no_filter=args.no_filter)
    n = process_raw(no_filter=args.no_filter)
    print(f"Done. Downloaded {fetched} (skipped {skipped} existing), parsed {n} records.")


if __name__ == "__main__":
    main()
