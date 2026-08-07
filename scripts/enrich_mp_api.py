#!/usr/bin/env python3
"""Enrich the Materials Project staging rows with the schema's Layer 5/6/7/8/10
blocks (mechanical, dielectric, coordination environments, robocrys structural
descriptors, oxidation states, surface energy) by querying the Materials
Project REST API per material_id.

Pipeline:
  data/raw/materials_project/raw_json/{mid}.json         (input; the summary doc)
  + data/raw/materials_project/enrichment/{mid}.json     (output; new blocks)
  -> scripts/expand_mp.py build_record consumes enrichment merged into raw doc

Resumable at BLOCK granularity: a mid is only re-fetched for the blocks its
enrichment file is missing. Use --force to re-fetch everything.

Endpoints queried (all free, same MPRester client as expand_mp.py):
  * summary        -> bulk_modulus, shear_modulus, universal_anisotropy,
                       homogeneous_poisson, weighted_surface_energy,
                       surface_anisotropy, piezo e_ij_max,
                       weighted_work_function                 (Layer 5/10)
  * elasticity     -> youngs_modulus, elastic_tensor,
                       compliance_tensor, debye_temperature,
                       sound_velocity, thermal_conductivity      (Layer 5)
  * dielectric     -> e_total, e_electronic, e_ionic,
                       dielectric_tensor (total), n              (Layer 6)
  * robocrys       -> description, mineral prototype, dimensionality (Layer 8)
                       [bulk search_docs, no per-id cap]
  * oxidation_states -> average oxidation states                 (Layer 7)
  * chemenv        -> coordination environments + csm            (Layer 8)
  * bonds          -> bond_length_stats, bond_types, coordination_envs,
                       coordination_number (CrystalNN)           (Layer 8)
  * synthesis      -> synthesis recipes (T/time/atmosphere, method flags,
                       precursors, reaction string) via target_formula query
                       (Section 2; sparse coverage — MP only synthesizes a
                       subset of compounds)

Sparse coverage is expected: MP only has elastic/dielectric calculations for a
fraction of the 21,528 Li-containing compounds, and chemenv only computes for
structures with distinct cation coordination (metals/intermetallics return
empty lists). Missing values stay None / empty — the schema field exists, and
the record honestly reports no data.

Usage:
  python scripts/enrich_mp_api.py --limit 100          # first 100 materials
  python scripts/enrich_mp_api.py --only-families sulfide,halide
  python scripts/enrich_mp_api.py --blocks chemenv,robocrys  # just missing blocks
  python scripts/enrich_mp_api.py --force              # re-fetch existing
"""

from __future__ import annotations

import argparse
import json
import os
import re
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path
from typing import Any

from mp_api.client import MPRester

ROOT = Path(__file__).resolve().parent.parent
RAW_DIR = ROOT / "data/raw/materials_project/raw_json"
ENRICH_DIR = ROOT / "data/raw/materials_project/enrichment"
STAGING_DIR = ROOT / "staging" / "materials_project"

CHUNK = 500  # MP API handles ~500 ids per search call comfortably

ALL_BLOCKS = ("summary", "elasticity", "dielectric", "oxidation_states",
              "robocrys", "chemenv", "bonds", "synthesis")

# summary fields we already fetched are excluded; these are the net-new ones.
SUMMARY_FIELDS = [
    "material_id",
    "bulk_modulus",
    "shear_modulus",
    "universal_anisotropy",
    "homogeneous_poisson",
    "weighted_surface_energy",
    "surface_anisotropy",
    "e_ij_max",
    "weighted_work_function",
]
ELASTICITY_FIELDS = [
    "material_id", "youngs_modulus", "elastic_tensor", "compliance_tensor",
    "debye_temperature", "sound_velocity", "thermal_conductivity",
]
DIELECTRIC_FIELDS = ["material_id", "e_total", "e_electronic", "e_ionic",
                     "total", "n"]
OXIDATION_FIELDS = ["material_id", "average_oxidation_states"]
CHEMENV_FIELDS = ["material_id", "species", "chemenv_name",
                  "chemenv_symbol", "csm"]
ROBOCRYS_FIELDS = ["material_id", "description", "condensed_structure"]
BONDS_FIELDS = ["material_id", "bond_length_stats", "bond_types",
                "coordination_envs", "method"]
SYNTHESIS_FIELDS = ["doi", "synthesis_type", "reaction_string",
                    "targets_formula", "precursors_formula", "precursors",
                    "operations"]

# Robocrys descriptions start like "Li is Copper structured and crystallizes
# in the cubic Fm-3m space group." — the prototype is the token(s) between
# "is " and " structured" at the START of the sentence.
_PROTOTYPE_RE = re.compile(r"\bis ([A-Za-z0-9α-ω]+(?:\s[A-Za-z0-9]+)?) structured")


def _num(v: Any) -> float | None:
    if v is None:
        return None
    try:
        return float(v)
    except (TypeError, ValueError):
        return None


def _vr(hashable: Any) -> float | None:
    """Extract the Voigt-Reuss-Hill average from an MP tensor wrapper."""
    if isinstance(hashable, dict):
        vrh = hashable.get("vrh")
        return _num(vrh)
    return _num(hashable)


def _tensor_matrix(raw: Any) -> list[list[float]] | None:
    """MP tensor fields arrive as a dict keyed by Voigt index labels
    ('v1v1'..'v6v6'), as a {'raw': (...), 'ieee_format': (...)} wrapper, or as
    a raw list. Rebuild the matrix when possible."""
    if not raw:
        return None
    if isinstance(raw, list) and raw and isinstance(raw[0], list):
        return [[_num(x) for x in row] for row in raw]
    if isinstance(raw, dict):
        if all(f"v{i}v{j}" in raw for i in range(1, 7) for j in range(1, 7)):
            return [[_num(raw[f"v{i}v{j}"]) for j in range(1, 7)]
                    for i in range(1, 7)]
        inner = raw.get("raw") or raw.get("ieee_format")
        if isinstance(inner, (list, tuple)):
            rows = [list(r) for r in inner]
            if rows and isinstance(rows[0], list):
                return [[_num(x) for x in row] for row in rows]
    return None


def _tensor33(triple: Any) -> list[list[float]] | None:
    """Convert a 3x3 nested tuple/list (MP dielectric `total` tensor) to a
    list-of-lists, or None."""
    if not triple:
        return None
    if isinstance(triple, (list, tuple)) and len(triple) == 3:
        try:
            return [[_num(x) for x in row] for row in triple]
        except Exception:
            return None
    return None


def _mineral_prototype(description: str | None) -> str | None:
    """Extract the mineral prototype from a robocrys description sentence.
    'Li is Copper structured ...' -> 'Copper'. Returns None when absent."""
    if not description:
        return None
    m = _PROTOTYPE_RE.search(description)
    if m:
        proto = m.group(1).strip()
        if proto and proto.lower() not in ("not", "a"):
            return proto
    return None


def _mid_from_doc(doc: Any) -> str | None:
    """The MPID serializer preserves the input id form (ULID alias when we
    queried by ULID) — model_dump()['material_id'] is the same string we
    passed in, which is what our files are keyed on."""
    md = doc.model_dump()
    return md.get("material_id")


def load_material_ids(*, limit: int, only_families: set[str] | None,
                      exclude_mids: set[str]) -> list[str]:
    """material_id list from raw JSON, optionally family-filtered via staging."""
    ids: list[str] = []
    if only_families:
        for fam in only_families:
            part = STAGING_DIR / fam
            if not part.exists():
                continue
            for p in part.glob("*.parquet"):
                import pyarrow.parquet as pq

                df = pq.read_table(p).to_pandas()
                if "identity.source_id" in df.columns:
                    ids.extend(df["identity.source_id"].astype(str).tolist())
    if not ids:
        for p in sorted(RAW_DIR.glob("*.json")):
            mid = p.stem
            if mid in exclude_mids:
                continue
            ids.append(mid)
            if limit and len(ids) >= limit:
                break
    else:
        ids = [i for i in ids if i not in exclude_mids][:limit] if limit else \
            [i for i in ids if i not in exclude_mids]
    return ids


def _load_existing_blocks(mids: list[str]) -> dict[str, dict]:
    """{mid: {block_name: fields}} for enrichment files already on disk."""
    out: dict[str, dict] = {}
    for mid in mids:
        p = ENRICH_DIR / f"{mid}.json"
        if not p.exists():
            continue
        try:
            data = json.loads(p.read_text())
            out[mid] = data.get("blocks") or {}
        except Exception:
            out[mid] = {}
    return out


def _fetch_summary(mpr, chunk: list[str]) -> dict[str, dict]:
    found: dict[str, dict] = {}
    docs = mpr.materials.summary.search(material_ids=chunk, fields=SUMMARY_FIELDS)
    for d in docs:
        md = d.model_dump()
        mid = md.get("material_id")
        if not mid:
            continue
        found[mid] = {
            "bulk_modulus": _vr(md.get("bulk_modulus")),
            "shear_modulus": _vr(md.get("shear_modulus")),
            "universal_anisotropy": _num(md.get("universal_anisotropy")),
            "homogeneous_poisson": _num(md.get("homogeneous_poisson")),
            "weighted_surface_energy": _num(md.get("weighted_surface_energy")),
            "surface_anisotropy": _num(md.get("surface_anisotropy")),
            "piezo_e_ij_max": _num(md.get("e_ij_max")),
            "weighted_work_function": _num(md.get("weighted_work_function")),
        }
    return found


def _fetch_elasticity(mpr, chunk: list[str]) -> dict[str, dict]:
    found: dict[str, dict] = {}
    docs = mpr.materials.elasticity.search(
        material_ids=chunk, fields=ELASTICITY_FIELDS)
    for d in docs:
        md = d.model_dump()
        mid = md.get("material_id")
        if not mid:
            continue
        found[mid] = {
            "youngs_modulus": _vr(md.get("youngs_modulus")),
            "elastic_tensor": _tensor_matrix(md.get("elastic_tensor")),
            "compliance_tensor": _tensor_matrix(md.get("compliance_tensor")),
            "debye_temperature": _num(md.get("debye_temperature")),
            "sound_velocity": {
                k: _num(v) for k, v in (md.get("sound_velocity") or {}).items()
            } or None,
            "thermal_conductivity": {
                k: _num(v) for k, v in (md.get("thermal_conductivity") or {}).items()
            } or None,
        }
    return found


def _fetch_dielectric(mpr, chunk: list[str]) -> dict[str, dict]:
    found: dict[str, dict] = {}
    docs = mpr.materials.dielectric.search(
        material_ids=chunk, fields=DIELECTRIC_FIELDS)
    for d in docs:
        md = d.model_dump()
        mid = md.get("material_id")
        if not mid:
            continue
        found[mid] = {
            "e_total": _num(md.get("e_total")),
            "e_electronic": _num(md.get("e_electronic")),
            "e_ionic": _num(md.get("e_ionic")),
            "dielectric_tensor": _tensor33(md.get("total")),
            "refractive_index_n": _num(md.get("n")),
        }
    return found


def _fetch_oxidation_states(mpr, chunk: list[str]) -> dict[str, dict]:
    found: dict[str, dict] = {}
    docs = mpr.materials.oxidation_states.search(
        material_ids=chunk, fields=OXIDATION_FIELDS)
    for d in docs:
        md = d.model_dump()
        mid = md.get("material_id")
        if not mid:
            continue
        found[mid] = {
            "average_oxidation_states": md.get("average_oxidation_states"),
        }
    return found


def _fetch_robocrys(mpr, chunk: list[str]) -> dict[str, dict]:
    """Bulk robocrys lookup (Layer 8). search_docs accepts material_id lists,
    so no per-id cap is needed. condensed_structure carries the structural
    dimensionality (0D/1D/2D/3D)."""
    found: dict[str, dict] = {}
    docs = mpr.materials.robocrys.search_docs(
        material_ids=chunk, fields=ROBOCRYS_FIELDS)
    for d in docs:
        mid = _mid_from_doc(d)
        if not mid:
            continue
        desc = getattr(d, "description", None)
        cs = getattr(d, "condensed_structure", None)
        dim = None
        if cs is not None:
            try:
                dim = int(cs.dimensionality) if cs.dimensionality is not None else None
            except (TypeError, ValueError):
                dim = None
        found[mid] = {
            "description": desc,
            "mineral": _mineral_prototype(desc),
            "dimensionality": dim,
        }
    return found


def _coordination_number(coordination_envs: list[str] | None) -> float | None:
    """Extract a scalar coordination number from bonds coordination_envs
    strings like 'Cu-Cu(6),Nd(3)'. Uses the max coordination count across the
    reported environments as a rough per-material scalar."""
    counts: list[int] = []
    for env in coordination_envs or []:
        for m in re.finditer(r"\((\d+)\)", env or ""):
            try:
                counts.append(int(m.group(1)))
            except ValueError:
                continue
    if not counts:
        return None
    return float(max(counts))


def _fetch_bonds(mpr, chunk: list[str]) -> dict[str, dict]:
    """Layer 8 — bond lengths + coordination environments via the bonds
    endpoint (CrystalNN structure graphs)."""
    found: dict[str, dict] = {}
    docs = mpr.materials.bonds.search(material_ids=chunk, fields=BONDS_FIELDS)
    for d in docs:
        md = d.model_dump()
        mid = md.get("material_id")
        if not mid:
            continue
        bls = md.get("bond_length_stats") or {}
        found[mid] = {
            "bond_length_stats": {
                k: _num(v) for k, v in bls.items() if k != "all_weights"
            } or None,
            "bond_types": md.get("bond_types"),
            "coordination_envs": md.get("coordination_envs") or [],
            "coordination_number": _coordination_number(md.get("coordination_envs")),
            "method": md.get("method"),
        }
    return found


def _fetch_chemenv(mpr, chunk: list[str]) -> dict[str, dict]:
    """Coordination environments (Layer 8) via the chemenv endpoint."""
    found: dict[str, dict] = {}
    docs = mpr.materials.chemenv.search(
        material_ids=chunk, fields=CHEMENV_FIELDS)
    for d in docs:
        md = d.model_dump()
        mid = md.get("material_id")
        if not mid:
            continue
        species = md.get("species") or []
        names = md.get("chemenv_name") or []
        csm = [None if v is None else float(v) for v in (md.get("csm") or [])]
        found[mid] = {
            "coordination_environment": [
                f"{sp}: {nm}" for sp, nm in zip(species, names)
            ],
            "coordination_csm": csm,
            "coordination_species": list(species),
        }
    return found


def _value_stats(vals: list) -> dict | None:
    """Extract min/max from an MP Value list like
    [{'values': [300.0], 'min_value': 300.0, 'max_value': 300.0, 'units': '°C'}]"""
    if not vals:
        return None
    first = vals[0]
    if not isinstance(first, dict):
        return None
    try:
        return {
            "min": _num(first.get("min_value")),
            "max": _num(first.get("max_value")),
            "units": first.get("units"),
        }
    except Exception:
        return None


def _parse_synthesis_recipe(recipe: Any) -> dict:
    """Collapse a SynthesisRecipe into a compact conditions dict for the
    SynthesisBlock: heating temperature/time/atmosphere, method flags, and the
    reaction string + precursors."""
    try:
        rd = recipe.model_dump() if hasattr(recipe, "model_dump") else \
            (dict(recipe) if isinstance(recipe, dict) else {})
    except Exception:
        return {}
    temps: list[float] = []
    times: list[float] = []
    atmospheres: list[str] = []
    flags: dict[str, bool] = {}
    for op in rd.get("operations") or []:
        if not isinstance(op, dict):
            continue
        cond = op.get("conditions") or {}
        for v in cond.get("heating_temperature") or []:
            st = _value_stats([v]) if isinstance(v, dict) else None
            if st and st.get("min") is not None:
                temps.append(float(st["min"]))
        for v in cond.get("heating_time") or []:
            st = _value_stats([v]) if isinstance(v, dict) else None
            if st and st.get("min") is not None:
                times.append(float(st["min"]))
        for atm in cond.get("heating_atmosphere") or []:
            if isinstance(atm, str) and atm:
                atmospheres.append(atm)
        tok = str(op.get("token", "")).lower()
        op_type = str(op.get("type", "")).lower()
        if "mill" in tok or "mixing" in tok:
            flags["ball_milling"] = True
        if "anneal" in tok:
            flags["annealing"] = True
        if "calc" in tok:
            flags["calcination"] = True
        if "sinter" in tok:
            flags["sintering"] = True
        if "press" in tok:
            flags["hot_pressing"] = True
        if "quench" in tok or "cool" in tok:
            flags["quenched"] = True
        if "sol-gel" in tok or "gel" in tok:
            flags["sol_gel"] = True
        if "solid" in tok or op_type == "starting_synthesis":
            flags["solid_state"] = True
    method = str(rd.get("synthesis_type") or "").lower()
    if "sol-gel" in method:
        flags["sol_gel"] = True
    if "solid" in method:
        flags["solid_state"] = True
    return {
        "temperature_C": max(temps) if temps else None,
        "time_h": max(times) if times else None,
        "atmosphere": "; ".join(sorted(set(atmospheres))) or None,
        "reaction_string": rd.get("reaction_string"),
        "synthesis_doi": rd.get("doi"),
        "synthesis_type": rd.get("synthesis_type"),
        "precursors": [str(x) for x in (rd.get("precursors_formula") or [])],
        **{k: v for k, v in flags.items()},
    }


def _synthesis_for_mid(mid: str) -> tuple[str, list]:
    """Query synthesis recipes for a single material id (per-worker call).
    Returns (mid, recipes) — recipes empty when MP has none / formula absent."""
    rp = RAW_DIR / f"{mid}.json"
    if not rp.exists():
        return mid, []
    try:
        formula = json.loads(rp.read_text()).get("formula_pretty", "")
    except Exception:
        formula = ""
    if not formula:
        return mid, []
    kept = []
    try:
        with MPRester(api_key=_api_key()) as mpr:
            docs = list(mpr.materials.synthesis.search(
                target_formula=formula, num_chunks=1, chunk_size=25))
            for recipe in docs:
                try:
                    rd = recipe.model_dump() if hasattr(recipe, "model_dump") else {}
                except Exception:
                    rd = {}
                targets = {str(x) for x in (rd.get("targets_formula_s") or [])} | \
                    {str(x) for x in (rd.get("targets_formula") or [])}
                if formula not in targets:
                    continue
                parsed = _parse_synthesis_recipe(recipe)
                if parsed:
                    kept.append(parsed)
                if len(kept) >= 5:
                    break
    except Exception:
        return mid, []
    return mid, kept


def _api_key() -> str:
    """MP API key from environment (already loaded via load_dotenv in main)."""
    return os.environ.get("MP_API_KEY", "")


def _fetch_synthesis(mpr, chunk: list[str], jobs: int = 8) -> dict[str, dict]:
    """Layer/section 2 — synthesis recipes. The synthesis endpoint is queried
    by target_formula (not material_id), so this fetcher reads each material's
    formula from its raw_json doc and keeps only recipes whose target matches.
    Coverage is sparse (MP synthesis covers a subset of compounds).

    Parallelized: each worker opens its own MPRester session (rate limit is
    generous, ~25 req/s), so the whole catalog runs in minutes instead of hours
    when the shared session drifts into throttled/backoff territory."""
    found: dict[str, dict] = {}
    done = 0
    with ThreadPoolExecutor(max_workers=jobs) as pool:
        futures = [pool.submit(_synthesis_for_mid, mid) for mid in chunk]
        for fut in as_completed(futures):
            mid, kept = fut.result()
            if kept:
                found[mid] = kept
            done += 1
            if done % 200 == 0:
                print(f"    synthesis: {done}/{len(chunk)} mid, "
                      f"{len(found)} with recipes", flush=True)
    return found


_FETCHERS = {
    "summary": _fetch_summary,
    "elasticity": _fetch_elasticity,
    "dielectric": _fetch_dielectric,
    "oxidation_states": _fetch_oxidation_states,
    "robocrys": _fetch_robocrys,
    "chemenv": _fetch_chemenv,
    "bonds": _fetch_bonds,
    "synthesis": _fetch_synthesis,
}


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--limit", type=int, default=0,
                    help="max materials to process (default: all)")
    ap.add_argument("--only-families", type=str, default="",
                    help="comma-separated family names to restrict to")
    ap.add_argument("--blocks", type=str, default="",
                    help="comma-separated blocks to fetch (default: all "
                         f"{','.join(ALL_BLOCKS)})")
    ap.add_argument("--force", action="store_true",
                    help="re-fetch blocks even if already on disk")
    ap.add_argument("--dry-run", action="store_true",
                    help="report how many materials would be fetched")
    ap.add_argument("--jobs", type=int, default=8,
                    help="parallel workers for the synthesis block (default 8)")
    args = ap.parse_args()

    ENRICH_DIR.mkdir(parents=True, exist_ok=True)
    blocks = tuple(b.strip() for b in args.blocks.split(",") if b.strip()) \
        or ALL_BLOCKS
    invalid = [b for b in blocks if b not in _FETCHERS]
    if invalid:
        raise SystemExit(f"unknown blocks: {invalid}. Valid: {ALL_BLOCKS}")

    families = {f.strip() for f in args.only_families.split(",") if f.strip()} \
        or None
    all_mids = load_material_ids(limit=args.limit, only_families=families,
                                 exclude_mids=set())
    if not all_mids:
        print("No materials found.")
        return

    existing = _load_existing_blocks(all_mids)

    # Decide which mids still need each block (unless --force).
    per_block_needs: dict[str, list[str]] = {}
    for block in blocks:
        needs = []
        for mid in all_mids:
            have = existing.get(mid, {})
            if args.force or block not in have or not have.get(block):
                needs.append(mid)
        per_block_needs[block] = needs
        print(f"{block}: {len(needs)}/{len(all_mids)} to fetch")

    total_to_fetch = sum(len(v) for v in per_block_needs.values())
    print(f"{total_to_fetch} block-fetch operations queued")
    if args.dry_run or total_to_fetch == 0:
        return

    from dotenv import load_dotenv
    load_dotenv()

    api_key = os.environ.get("MP_API_KEY")
    if not api_key:
        raise SystemExit("MP_API_KEY not set. Set it in .env or the environment.")

    with MPRester(api_key=api_key) as mpr:
        for block in blocks:
            needs = per_block_needs[block]
            if not needs:
                continue
            fetcher = _FETCHERS[block]
            print(f"  -- {block} ({len(needs)} mids)")
            t0 = time.time()
            for i in range(0, len(needs), CHUNK):
                chunk = needs[i:i + CHUNK]
                try:
                    if block == "synthesis":
                        found = fetcher(mpr, chunk, jobs=args.jobs)
                    else:
                        found = fetcher(mpr, chunk)
                except Exception as e:
                    print(f"    {block} error for chunk {i}: {e!r}")
                    continue
                for mid, fields in found.items():
                    existing.setdefault(mid, {})[block] = fields
            print(f"    ...{block} done ({time.time() - t0:.1f}s)")

    n_written = 0
    n_with_data = 0
    for mid, blocks_map in existing.items():
        if not blocks_map:
            continue
        (ENRICH_DIR / f"{mid}.json").write_text(
            json.dumps({"material_id": mid, "blocks": blocks_map}, indent=2))
        n_written += 1
        if any(bool(v) for v in blocks_map.values()):
            n_with_data += 1
    print(f"Wrote {n_written} enrichment files to {ENRICH_DIR} "
          f"({n_with_data} with at least one non-null value)")


if __name__ == "__main__":
    main()
