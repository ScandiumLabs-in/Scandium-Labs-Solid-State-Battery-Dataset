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

from pymatgen.core import Composition

from ssb_dataset.config.settings import settings
from ssb_dataset.schema import (
    ChemistryBlock,
    ConfidenceTier,
    DielectricBlock,
    DiscoveryLabelsBlock,
    ElectronicBlock,
    Family,
    Functional,
    GraphBlock,
    IdentityProvenance,
    IonTransportBlock,
    LatticeParams,
    MagneticBlock,
    MaterialRecord,
    MechanicalBlock,
    RedoxBlock,
    SourceDB,
    StructureBlock,
    StructureType,
    SynthesisBlock,
    SynthesisRoute,
    ThermodynamicsBlock,
)
from ssb_dataset.sources.classifier import classify_family, is_electrolyte_candidate

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


ENRICH_DIR = BASE / "enrichment"
STRUCT_DESC_DIR = BASE / "struct_desc"


def _load_struct_desc(d: dict) -> dict:
    """Merge the deterministic graph + local-environment descriptors
    (scripts/compute_structure_descriptors.py) into the raw doc dict."""
    mid = d.get("material_id", "")
    if not mid:
        return d
    sp = STRUCT_DESC_DIR / f"{mid}.json"
    if not sp.exists():
        return d
    try:
        data = json.loads(sp.read_text())
    except Exception:
        return d
    for k, v in (data.get("graph") or {}).items():
        d[f"graph_{k}"] = v
    for k, v in (data.get("local") or {}).items():
        d[f"local_{k}"] = v
    for k, v in (data.get("li") or {}).items():
        d[f"li_{k}"] = v
    return d


def _load_enrichment(d: dict) -> dict:
    """Merge the MP API enrichment blocks (elasticity/dielectric/robocrys/
    surface/chemenv) into the raw doc dict so build_record can consume them.
    Returns the same dict, mutated; missing enrichment is a silent no-op."""
    mid = d.get("material_id", "")
    if not mid:
        return d
    ep = ENRICH_DIR / f"{mid}.json"
    if not ep.exists():
        return d
    try:
        data = json.loads(ep.read_text())
    except Exception:
        return d
    blocks = data.get("blocks") or {}
    for name, fields in blocks.items():
        if name == "synthesis":
            recipes = fields if isinstance(fields, list) else []
            if recipes:
                d["synthesis_recipes"] = recipes
            continue
        if not isinstance(fields, dict):
            continue
        if name == "summary":
            d.update({k: v for k, v in fields.items()})
        elif name in ("elasticity", "dielectric"):
            d.update(fields)
        elif name == "robocrys":
            d["robocrys_description"] = fields.get("description")
            d["mineral_prototype"] = fields.get("mineral") or None
            d["dimensionality"] = fields.get("dimensionality")
        elif name == "oxidation_states":
            d["average_oxidation_states"] = fields.get("average_oxidation_states")
        elif name == "chemenv":
            d["coordination_environment"] = fields.get("coordination_environment") or []
            d["coordination_csm"] = fields.get("coordination_csm") or []
            d["coordination_species"] = fields.get("coordination_species") or []
        elif name == "bonds":
            d["bond_length_stats"] = fields.get("bond_length_stats")
            d["bond_types"] = fields.get("bond_types") or {}
            d["coordination_number"] = fields.get("coordination_number")
    return d


def build_record(d: dict) -> MaterialRecord:
    """Convert a raw MP doc into the canonical MaterialRecord schema."""
    d = _load_enrichment(d)
    d = _load_struct_desc(d)
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

    # Number of symmetry operations from the space group type (Layer 2).
    symmetry_operations_count = _symmetry_ops_count(sym)

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
            formula_pretty=d.get("formula_pretty"),
            formula_anonymous=d.get("formula_anonymous"),
            chemsys=d.get("chemsys"),
            elements=list(elements),
            nelements=d.get("nelements"),
            database_ids=[str(x) for x in _flatten_database_ids(d.get("database_IDs"))],
            reduced_formula=_reduced_formula(d),
        ),
        structure=StructureBlock(
            structure_relaxed=d.get("structure_cif"),
            structure_unrelaxed=None,
            space_group=sym.get("symbol", "") if isinstance(sym, dict) else str(sym or ""),
            space_group_number=sym.get("number") if isinstance(sym, dict) else None,
            crystal_system=sym.get("crystal_system") if isinstance(sym, dict) else None,
            point_group=sym.get("point_group") if isinstance(sym, dict) else None,
            symmetry_operations_count=symmetry_operations_count,
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
            coordination_environment=d.get("coordination_environment") or [],
            coordination_csm=d.get("coordination_csm") or [],
            coordination_species=d.get("coordination_species") or [],
            robocrys_description=d.get("robocrys_description"),
            mineral_prototype=d.get("mineral_prototype"),
            bond_length_stats=d.get("bond_length_stats"),
            bond_types=d.get("bond_types") or {},
            coordination_number=d.get("coordination_number"),
            dimensionality=d.get("dimensionality"),
            polyhedron_volume=d.get("local_polyhedron_volume"),
            polyhedron_distortion=d.get("local_polyhedron_distortion"),
            bond_angle_variance=d.get("local_bond_angle_variance"),
            tetrahedrality=d.get("local_tetrahedrality"),
            octahedrality=d.get("local_octahedrality"),
            mean_neighbor_distance=d.get("local_mean_neighbor_distance"),
            neighbor_species_distribution=(
                d.get("local_neighbor_species_distribution") or {}),
            nearest_neighbor_distance=d.get("local_nearest_neighbor_distance"),
            packing_fraction=d.get("local_packing_fraction"),
            li_site_count=d.get("li_site_count"),
            li_vacancy_fraction=d.get("li_vacancy_fraction"),
            li_hopping_distance=d.get("li_hopping_distance"),
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
            weighted_surface_energy=d.get("weighted_surface_energy"),
            surface_anisotropy=d.get("surface_anisotropy"),
            weighted_work_function=d.get("weighted_work_function"),
            total_energy=d.get("total_energy"),
            energy_per_atom=d.get("energy_per_atom"),
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
            average_oxidation_states=d.get("average_oxidation_states"),
        ),
        chemistry=_chemistry_descriptors(d),
        redox=_redox_descriptors(d, oxidation_states),
        mechanical=_mechanical_from_doc(d),
        dielectric=_dielectric_from_doc(d),
        synthesis=_synthesis_from_recipes(d.get("synthesis_recipes") or []),
        ion_transport=IonTransportBlock(
            mobile_ion=_mobile_ion(d),
        ),
        graph=GraphBlock(
            num_nodes=d.get("graph_num_nodes"),
            num_edges=d.get("graph_num_edges"),
            average_degree=d.get("graph_average_degree"),
            graph_density=d.get("graph_graph_density"),
            edge_length_mean=d.get("graph_edge_length_mean"),
            edge_length_std=d.get("graph_edge_length_std"),
            clustering_coefficient=d.get("graph_clustering_coefficient"),
            graph_diameter=d.get("graph_graph_diameter"),
            connected=d.get("graph_connected"),
        ),
        discovery_labels=_discovery_labels(
            d, family,
            sigma_RT=None, Ea=None),
    )


def _reduced_formula(d: dict) -> str | None:
    """MP `composition_reduced` arrives as a Composition dict ({'Li': 1.0, ...})
    in newer API responses. Reduce it to a formula string deterministically."""
    v = d.get("composition_reduced")
    if not v:
        return None
    if isinstance(v, str):
        return v
    try:
        from pymatgen.core import Composition
        return Composition(v).reduced_formula
    except Exception:
        return None


def _mobile_ion(d: dict) -> str | None:
    """Tier 2 — the mobile-ion species, derived deterministically from the
    elements present (most electropositive alkali/alkaline-earth first)."""
    els = set(d.get("elements", []) or [])
    for ion in ("Li", "Na", "K", "Rb", "Cs", "Mg", "Ca", "Sr", "Ba"):
        if ion in els:
            return ion
    return None


def _chemistry_descriptors(d: dict) -> ChemistryBlock:
    """Layer 7 — composition-derived chemistry descriptors, computed
    deterministically from the reduced composition via pymatgen. Full coverage
    whenever the formula is available (no MP endpoint needed)."""
    comp = _reduced_formula(d)
    if not comp:
        return ChemistryBlock()
    try:
        c = Composition(comp)
    except Exception:
        return ChemistryBlock()
    try:
        fracs = {el.symbol: v for el, v in c.fractional_composition.items()}
    except Exception:
        fracs = {}
    enegs = []
    for el in c.elements:
        try:
            if el.X is not None:
                enegs.append(el.X)
        except Exception:
            continue
    if enegs:
        n = len(enegs)
        mean = sum(enegs) / n
        std = (sum((x - mean) ** 2 for x in enegs) / n) ** 0.5
        eneg_mean = mean
        eneg_max = max(enegs)
        eneg_min = min(enegs)
        eneg_std = std
    else:
        eneg_mean = eneg_max = eneg_min = eneg_std = None
    try:
        valence = sum(el.group * frac for el, frac in
                      c.fractional_composition.items())
    except Exception:
        valence = None

    # Tier 1/5 — Magpie-style composition descriptors (weighted by fraction).
    def _wmean(prop, default=None):
        vals = []
        for el, frac in c.fractional_composition.items():
            try:
                v = prop(el)
            except Exception:
                v = None
            if v is not None:
                vals.append((v, frac))
        if not vals:
            return default
        total_w = sum(w for _, w in vals)
        if not total_w:
            return default
        return sum(v * w for v, w in vals) / total_w

    def _wstd(prop, mean, default=None):
        vals = []
        for el, frac in c.fractional_composition.items():
            try:
                v = prop(el)
            except Exception:
                v = None
            if v is not None:
                vals.append((v, frac))
        if not vals:
            return default
        total_w = sum(w for _, w in vals)
        if not total_w:
            return default
        var = sum(((v - mean) ** 2) * w for v, w in vals) / total_w
        return var ** 0.5

    from pymatgen.core import Element as PElement

    def _atomic_radius(el):
        return el.atomic_radius
    def _ionic_radius(el):
        # Prefer the common oxidation-state radius; fall back to the element.
        try:
            ox = el.common_oxidation_states
            if ox:
                return el.ionic_radii.get(ox[0])
        except Exception:
            pass
        return None

    weight_fracs = {}
    try:
        for el, frac in c.fractional_composition.items():
            weight_fracs[el.symbol] = el.atomic_mass * frac
        tw = sum(weight_fracs.values())
        if tw:
            weight_fracs = {k: v / tw for k, v in weight_fracs.items()}
    except Exception:
        weight_fracs = {}

    a_rad_mean = _wmean(_atomic_radius)
    a_rad_std = _wstd(_atomic_radius, a_rad_mean) if a_rad_mean else None
    i_rad_mean = _wmean(_ionic_radius)
    i_rad_std = _wstd(_ionic_radius, i_rad_mean) if i_rad_mean else None
    mass_mean = _wmean(lambda el: el.atomic_mass)
    group_mean = _wmean(lambda el: getattr(el, "group", None))
    period_mean = _wmean(lambda el: getattr(el, "row", None))
    mendeleev_mean = _wmean(lambda el: getattr(el, "mendeleev_no", None))

    return ChemistryBlock(
        electronegativity_mean=eneg_mean,
        electronegativity_max=eneg_max,
        electronegativity_min=eneg_min,
        electronegativity_std=eneg_std,
        valence_electron_count=valence,
        atomic_fractions=fracs,
        elemental_fractions=fracs,
        weight_fractions=weight_fracs,
        atomic_radius_mean=round(a_rad_mean, 4) if a_rad_mean else None,
        atomic_radius_std=round(a_rad_std, 4) if a_rad_std else None,
        ionic_radius_mean=round(i_rad_mean, 4) if i_rad_mean else None,
        ionic_radius_std=round(i_rad_std, 4) if i_rad_std else None,
        average_atomic_mass=round(mass_mean, 4) if mass_mean else None,
        average_group=round(group_mean, 4) if group_mean else None,
        average_period=round(period_mean, 4) if period_mean else None,
        average_mendeleev_number=round(mendeleev_mean, 4)
        if mendeleev_mean else None,
    )


def _redox_descriptors(d: dict, oxidation_states: list[int]) -> RedoxBlock:
    """Section 7 — oxidation chemistry derived from composition + oxidation
    states. Deterministic."""
    comp = _reduced_formula(d)
    fracs: dict[str, float] = {}
    if comp:
        try:
            fracs = {el.symbol: v for el, v in
                     Composition(comp).fractional_composition.items()}
        except Exception:
            fracs = {}
    os_by_element: dict[str, list[int]] = {}
    for spec in d.get("possible_species") or []:
        import re as _re

        m = _re.match(r"([A-Z][a-z]?)(\d*)([+-])", spec or "")
        if not m:
            continue
        el = m.group(1)
        mag = 1 if m.group(3) == "+" else -1
        val = (int(m.group(2)) if m.group(2) else 1) * mag
        os_by_element.setdefault(el, []).append(val)

    redox_active = [el for el in fracs if el in
                    ("Li", "Na", "Mg", "Al", "Fe", "Co", "Ni", "Mn", "V", "Ti",
                     "Zr", "Zn", "Sn", "Sb", "Cu", "Cr", "Mo", "W")
                    and any(v in (1, 2) for v in os_by_element.get(el, []))]

    all_os = [v for vals in os_by_element.values() for v in vals]
    avg = sum(all_os) / len(all_os) if all_os else None
    ox_range = float(max(all_os) - min(all_os)) if len(all_os) > 1 else None
    mixed = any(len({v for v in vals}) > 1
                for vals in os_by_element.values()) if all_os else False

    # Cation/anion classification: electronegativity-based.
    from pymatgen.core import Element as PElement
    cations = []
    anions = []
    for el in fracs:
        try:
            eneg = PElement(el).X
        except Exception:
            eneg = None
        if eneg is None:
            continue
        if eneg <= 1.9:
            cations.append(el)
        elif eneg >= 3.0:
            anions.append(el)
    # Electroneutrality: sum of composition-weighted oxidation states ~ 0.
    # Unknown (None) when we have no oxidation-state data to compute it from.
    neutral: bool | None = None
    if all_os and fracs:
        total = 0.0
        for el, f in fracs.items():
            el_os = os_by_element.get(el)
            if el_os:
                total += el_os[0] * f
        neutral = abs(total) < 0.01

    return RedoxBlock(
        redox_active_elements=redox_active,
        average_oxidation=avg,
        oxidation_range=ox_range,
        mixed_valence=mixed,
        anion_type=anions,
        cation_type=cations,
        electroneutral=neutral,
    )


def _discovery_labels(d: dict, family: Family,
                      sigma_RT: float | None, Ea: float | None) -> DiscoveryLabelsBlock:
    """Section 10 — dataset-curated labels from deterministic heuristics over
    the record's own fields (stability, band gap, family, transport)."""
    is_stable = d.get("is_stable") is True
    band_gap = d.get("band_gap")
    is_metal = d.get("is_metal") is True

    # A "fast ion conductor" heuristic: experimentally-measured σ_RT above the
    # 1e-4 S/cm threshold with a plausible activation energy (<0.6 eV).
    fast = sigma_RT is not None and sigma_RT >= 1e-4
    if Ea is not None:
        fast = fast and Ea < 0.6

    # Tier 8 — high-conductivity label. None (unknown) when no measured σ_RT —
    # never impute it from a computational record. A single reported measurement
    # above the SSE working threshold (1e-4 S/cm) earns the label.
    high_cond = None if sigma_RT is None else (sigma_RT >= 1e-4)

    # "Promising": computationally stable, insulating (band gap present, not
    # metallic), and in an electrolyte-relevant family.
    promising = bool(
        is_stable
        and not is_metal
        and (band_gap is None or band_gap > 0)
        and family in (Family.sulfide, Family.oxide, Family.garnet,
                       Family.perovskite, Family.nasicon, Family.halide,
                       Family.argyrodite, Family.hydride,
                       Family.borohydride, Family.antiperovskite)
    )
    if sigma_RT is not None:
        promising = promising or sigma_RT >= 1e-4

    return DiscoveryLabelsBlock(
        is_good_ssb=fast,
        is_promising=promising,
        is_fast_ion_conductor=fast,
        is_high_conductivity=high_cond,
        is_experimental=False,
        is_computational=True,
        is_verified=False,
        confidence_score=1.0 if is_stable else None,
        novelty_score=None,
    )


def _synthesis_from_recipes(recipes: list[dict]) -> SynthesisBlock:
    """Section 2 — collapse MP synthesis recipes into the SynthesisBlock."""
    if not recipes:
        return SynthesisBlock()
    temps = [r.get("temperature_C") for r in recipes
             if r.get("temperature_C") is not None]
    times = [r.get("time_h") for r in recipes if r.get("time_h") is not None]
    atms = [r.get("atmosphere") for r in recipes if r.get("atmosphere")]
    flags = {}
    for flag in ("calcination", "annealing", "ball_milling", "sintering",
                 "hot_pressing", "spark_plasma_sintering", "sol_gel",
                 "solid_state", "mechanochemical"):
        flags[flag] = any(r.get(flag) for r in recipes)
    return SynthesisBlock(
        precursors=sorted({p for r in recipes for p in (r.get("precursors") or [])}),
        synthesis_route=[
            route for route in [
                SynthesisRoute.solid_state if flags["solid_state"] else None,
                SynthesisRoute.sol_gel if flags["sol_gel"] else None,
                SynthesisRoute.mechanochemical if flags["ball_milling"] else None,
            ] if route is not None
        ],
        synthesis_atmosphere="; ".join(sorted(set(atms))) or None,
        requires_interlayer=None,
        temperature_C=max(temps) if temps else None,
        time_h=max(times) if times else None,
        atmosphere="; ".join(sorted(set(atms))) or None,
        calcination=flags["calcination"],
        annealing=flags["annealing"],
        ball_milling=flags["ball_milling"],
        sintering=flags["sintering"],
        hot_pressing=flags["hot_pressing"],
        spark_plasma_sintering=flags["spark_plasma_sintering"],
        sol_gel=flags["sol_gel"],
        solid_state=flags["solid_state"],
        mechanochemical=flags["mechanochemical"],
        reaction_string=recipes[0].get("reaction_string"),
        synthesis_doi=recipes[0].get("synthesis_doi"),
        synthesis_type=recipes[0].get("synthesis_type"),
    )


def _flatten_database_ids(v: Any) -> list[str]:
    """MP `database_IDs` arrives as {'icsd': ['icsd-44763', ...]} (or a plain
    list). Flatten to a single list of identifier strings."""
    if not v:
        return []
    if isinstance(v, dict):
        out: list[str] = []
        for vals in v.values():
            out.extend(str(x) for x in (vals or []))
        return out
    if isinstance(v, (list, tuple)):
        return [str(x) for x in v]
    return [str(v)]


def _voigt_vrh(v: Any) -> float | None:
    """Extract the VRH (Voigt-Reuss-Hill average) scalar from an MP tensor
    field, which arrives as {'voigt': .., 'reuss': .., 'vrh': ..}."""
    if v is None:
        return None
    if isinstance(v, dict):
        vrh = v.get("vrh")
        return float(vrh) if vrh is not None else None
    return float(v)


def _elastic_tensor_matrix(d: dict, key: str) -> list[list[float]] | None:
    """MP elasticity fields (elastic_tensor / compliance_tensor) arrive as a
    dict keyed by Voigt index ('v1v1', 'v1v2', ...), a {'raw': ..} wrapper, or
    a raw list. Rebuild the 6x6 matrix."""
    raw = d.get(key)
    if not raw:
        return None
    if isinstance(raw, list) and raw and isinstance(raw[0], list):
        return [[float(x) for x in row] for row in raw]
    if isinstance(raw, dict):
        labels = [f"v{i}v{j}" for i in range(1, 7) for j in range(1, 7)]
        if all(k in raw for k in labels):
            return [[float(raw[f"v{i}v{j}"]) for j in range(1, 7)] for i in range(1, 7)]
        if all(k in raw for k in ("voigt", "reuss", "vrh")):
            return raw  # tensor-as-array not available; keep the wrapper
        for inner_key in ("raw", "ieee_format"):
            inner = raw.get(inner_key)
            if isinstance(inner, (list, tuple)) and inner:
                rows = [list(r) for r in inner]
                if rows and isinstance(rows[0], list):
                    return [[float(x) for x in row] for row in rows]
    return None


def _symmetry_ops_count(sym: Any) -> int | None:
    """Number of symmetry operations for a space group type (Layer 2). The MP
    `symmetry` dict carries number/symbol/point_group but not the op count;
    the count is a fixed property of the space group type, computable from the
    international number via pymatgen."""
    if not isinstance(sym, dict):
        return None
    num = sym.get("number")
    if not num:
        return None
    try:
        from pymatgen.symmetry.groups import SpaceGroup

        return len(SpaceGroup.from_int_number(int(num)).symmetry_ops)
    except Exception:
        return None


def _mechanical_from_doc(d: dict) -> MechanicalBlock:
    return MechanicalBlock(
        bulk_modulus=_voigt_vrh(d.get("bulk_modulus")),
        shear_modulus=_voigt_vrh(d.get("shear_modulus")),
        youngs_modulus=_voigt_vrh(d.get("youngs_modulus")),
        homogeneous_poisson=d.get("homogeneous_poisson"),
        universal_anisotropy=d.get("universal_anisotropy"),
        elastic_tensor=_elastic_tensor_matrix(d, "elastic_tensor"),
        compliance_tensor=_elastic_tensor_matrix(d, "compliance_tensor"),
        debye_temperature=d.get("debye_temperature"),
        sound_velocity=d.get("sound_velocity"),
        thermal_conductivity=d.get("thermal_conductivity"),
    )


def _dielectric_from_doc(d: dict) -> DielectricBlock:
    return DielectricBlock(
        e_total=d.get("e_total"),
        e_electronic=d.get("e_electronic"),
        e_ionic=d.get("e_ionic"),
        dielectric_tensor=d.get("dielectric_tensor"),
        refractive_index_n=d.get("refractive_index_n"),
        piezo_e_ij_max=d.get("piezo_e_ij_max"),
        piezo_max_direction=d.get("piezo_max_direction"),
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
