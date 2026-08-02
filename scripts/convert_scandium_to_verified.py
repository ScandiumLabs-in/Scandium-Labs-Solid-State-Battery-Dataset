#!/usr/bin/env python3
"""Convert reviewed extraction records to verified_canonical.parquet format.

Preferred input: review-approved records from review_output/queue.json
Fallback:      raw scandium extraction results (no human review).
"""

from __future__ import annotations

import json
import re
from datetime import datetime, timezone
from pathlib import Path

import pandas as pd
import pyarrow as pa
import pyarrow.parquet as pq
import numpy as np

REVIEW_QUEUE_PATH = Path("review_output/queue.json")

# DOI mapping from filename stems
def _to_int_or_none(v):
    """Coerce a page/table number to int or None (avoids mixed-type Parquet col)."""
    if v is None:
        return None
    if isinstance(v, bool):
        return None
    try:
        return int(float(v))
    except (TypeError, ValueError):
        return None


DOI_MAP = {
    "10.1038_s41467-022-35287-1": "10.1038/s41467-022-35287-1",
    "10.1038_s41467-023-40669-0": "10.1038/s41467-023-40669-0",
    "10.1038_s41467-023-42385-1": "10.1038/s41467-023-42385-1",
    "10.1038_s41467-024-51191-2": "10.1038/s41467-024-51191-2",
    "nasicon_mdpi": "10.3390/nanomaterials13182602",
    "sulfide_argyrodite": None,
    "sulfide_preprint": None,
}

FAMILY_MAP = {
    "Li7La3Zr2O12": "garnet",
    "Li6PS5Cl": "argyrodite",
    "Li6PS5Cl0.5Br0.5": "argyrodite",
    "Li1.3Al0.3Ti1.7(PO4)3": "nasicon",
    "Li2OHCl": "antiperovskite",
    "(Li2OH)0.99K0.01Cl": "antiperovskite",
    "PEO-LiTFSI": "polymer_composite",
    "Na3HfZr(SiO4)2(PO4)": "nasicon",
}

# Canonicalize family strings seen in curated/queue records to the taxonomy.
FAMILY_ALIASES = {
    "llzo": "garnet",
    "llzto": "garnet",
    "peo-litfsi": "polymer_composite",
    "peo": "polymer_composite",
    "latp": "nasicon",
    "li3ocl": "antiperovskite",
    "anti-perovskite": "antiperovskite",
    "superionic": "sulfide",
}


def canon_family(family: str) -> str:
    if not family:
        return ""
    fam = str(family).lower().strip()
    return FAMILY_ALIASES.get(fam, fam)


def normalize_formula(formula: str) -> str:
    """Normalize chemical formula for consistent material_id generation."""
    if not formula:
        return ""
    return re.sub(r"[_₀₁₂₃₄₅₆₇₈₉]", lambda m: str("_0123456789"[ord(m.group(0)) - 0x2080] if 0x2080 <= ord(m.group(0)) <= 0x2089 else m.group(0)), formula)


def extract_doi(paper_id: str, result: dict) -> str:
    doi = DOI_MAP.get(paper_id)
    if doi:
        return doi
    return result.get("doi") or ""


def _paper_id_to_doi(paper_id: str) -> str:
    """Map a queue paper_id (DOI with / replaced by _, or a bare source tag)
    to a real DOI. Only returns something when the id actually looks like a DOI."""
    pid = (paper_id or "").strip()
    if not pid:
        return ""
    candidate = pid.replace("_", "/")
    if candidate.startswith("10.") and "/" in candidate:
        return candidate
    return DOI_MAP.get(pid, "")


def make_record(
    material_id: str,
    doi: str,
    family: str,
    sigma: float | None,
    sigma_type: str | None,
    sigma_method: str | None,
    sigma_conf: float,
    ea: float | None,
    ea_conf: float,
    extraction_method: str,
    title: str | None = None,
    human_reviewed: bool = False,
    reviewer: str | None = None,
    evidence_sentence: str = "",
    page: int | None = None,
    section: str = "",
    table_number: int | None = None,
    temperature_celsius: float | None = None,
) -> dict:
    now = datetime.now(timezone.utc)
    family_lower = canon_family(family) if family else "unknown"

    # Determine confidence tier
    if human_reviewed:
        confidence_tier = "verified_human"
    elif max(sigma_conf if sigma is not None else 0, ea_conf if ea is not None else 0) >= 0.85:
        confidence_tier = "high_confidence_extraction"
    else:
        confidence_tier = "low_confidence_extraction"

    sigma_vs_T = np.array([], dtype=object)

    temp_range = None
    if temperature_celsius is not None:
        temp_k = temperature_celsius + 273.15
        temp_range = {"min_K": round(temp_k, 2), "max_K": round(temp_k, 2)}
    elif sigma is not None:
        temp_range = {"min_K": 298.0, "max_K": 298.0}

    ion_transport = {
        "sigma_RT": sigma,
        "sigma_vs_T_curve": sigma_vs_T,
        "activation_energy_Ea": ea,
        "conductivity_type": sigma_type or None,
        "conductivity_source_type": "measured" if sigma is not None else None,
        "measurement_method": sigma_method or None,
        "temperature_range_measured": temp_range,
        "label_available": sigma is not None or ea is not None,
    }

    record = {
        "identity": {
            "material_id": material_id,
            "source_db": "literature_mined",
            "source_id": doi or material_id,
            "composition": material_id,
            "family": family_lower,
            "subfamily_tag": np.array([], dtype=object),
            "ingestion_date": now,
            "schema_version": "0.1.0",
            "confidence_tier": confidence_tier,
        },
        "structure": {
            "structure_relaxed": None,
            "structure_unrelaxed": None,
            "space_group": None,
            "lattice_params": None,
            "li_site_occupancy": np.array([], dtype=object),
            "coordination_environment": np.array([], dtype=object),
            "structure_type": "ordered",
            "is_experimental_structure": False,
        },
        "thermodynamics": {
            "formation_energy_per_atom": None,
            "energy_above_hull": None,
            "band_gap": None,
            "decomposition_products": np.array([], dtype=object),
            "electrochemical_stability_window": None,
            "functional_used": None,
        },
        "ion_transport": ion_transport,
        "mechanical": {
            "bulk_modulus": None,
            "shear_modulus": None,
            "elastic_tensor": None,
        },
        "synthesis": {
            "precursors": np.array([], dtype=object),
            "synthesis_route": np.array([], dtype=object),
            "synthesis_atmosphere": None,
            "requires_interlayer": None,
            "processing_metadata": None,
        },
        "ml_features": {
            "graph_representation": None,
            "composition_descriptors": None,
            "symmetry_descriptors": None,
            "split_assignment": None,
            "split_group_key": "",
        },
        "text_provenance": {
            "source_doi": doi or None,
            "source_paper_title": title or None,
            "extraction_method": extraction_method,
            "extraction_confidence_score": max(sigma_conf if sigma is not None else 0, ea_conf if ea is not None else 0),
            "extraction_reviewer": reviewer,
            "evidence_sentence": evidence_sentence or None,
            "evidence_page": page,
            "evidence_section": section or None,
            "evidence_table_number": table_number,
        },
    }
    return record


def convert_paper_result(paper_id: str, result: dict) -> list[dict]:
    doi = extract_doi(paper_id, result)
    primary = result.get("primary_composition") or ""
    title = result.get("metadata", {}).get("title") if isinstance(result.get("metadata"), dict) else None

    conds = result.get("conductivities", {}).get("high_confidence", [])
    eas = result.get("activation_energies", {}).get("high_confidence", [])

    records: list[dict] = []
    seen_materials: set[str] = set()

    # Group sigma values by material, pick the one with highest confidence (or max sigma)
    by_material: dict[str, list[dict]] = {}
    for c in conds:
        mid = normalize_formula(c.get("material_formula") or primary)
        if not mid:
            continue
        by_material.setdefault(mid, []).append(c)
    best_cond_per_mat = {}
    for mid, clist in by_material.items():
        clist.sort(key=lambda x: -(x.get("_confidence", 0) or 0))
        best_cond_per_mat[mid] = clist[0]

    # Group Ea values by material
    ea_by_material: dict[str, list[dict]] = {}
    for e in eas:
        mid = normalize_formula(e.get("material_formula") or primary)
        if not mid:
            continue
        ea_by_material.setdefault(mid, []).append(e)
    best_ea_per_mat = {}
    for mid, elist in ea_by_material.items():
        elist.sort(key=lambda x: -(x.get("_confidence", 0) or 0))
        best_ea_per_mat[mid] = elist[0]

    all_materials = set(list(best_cond_per_mat.keys()) + list(best_ea_per_mat.keys()))

    for material_id in sorted(all_materials):
        family = canon_family(FAMILY_MAP.get(material_id, ""))
        if not family:
            for c in result.get("compositions", []):
                if normalize_formula(c.get("formula", "")) == material_id:
                    family = canon_family(c.get("family", ""))
                    break

        best_c = best_cond_per_mat.get(material_id)
        best_e = best_ea_per_mat.get(material_id)

        sigma = (best_c.get("value_normalized") or best_c.get("value")) if best_c else None
        sigma_type = best_c.get("conductivity_type") if best_c else None
        sigma_method = best_c.get("measurement_method") if best_c else None
        sigma_conf = best_c.get("_confidence", 0.5) if best_c else 0
        ea = (best_e.get("value_normalized") or best_e.get("value")) if best_e else None
        ea_conf = best_e.get("_confidence", 0) if best_e else 0

        if sigma is None and ea is None:
            continue

        rec = make_record(
            material_id=material_id,
            doi=doi,
            family=family,
            sigma=sigma,
            sigma_type=sigma_type,
            sigma_method=sigma_method,
            sigma_conf=sigma_conf,
            ea=ea,
            ea_conf=ea_conf,
            extraction_method="llm_extraction",
            title=title,
        )
        records.append(rec)

    return records


def convert_review_queue(queue: dict) -> list[dict]:
    """Convert review-approved items into verified records."""
    approved = [i for i in queue.get("items", []) if i.get("status") == "approved"]
    if not approved:
        print("  No approved review items.")
        return []

    # Group by (composition, doi) to pair sigma + Ea for the same material
    by_material: dict[tuple[str, str], dict] = {}
    for item in approved:
        doi = item.get("doi") or _paper_id_to_doi(item.get("paper_id") or "")
        key = (item.get("composition") or "", doi)
        by_material.setdefault(key, []).append(item)

    records: list[dict] = []
    for (material_id, doi), items in sorted(by_material.items()):
        if not material_id:
            continue
        family = canon_family(next((i.get("family") for i in items if i.get("family")), "")) or FAMILY_MAP.get(material_id, "")
        sigma = None
        sigma_type = None
        sigma_method = None
        sigma_conf = 0.0
        ea = None
        ea_conf = 0.0
        temperature_celsius = None
        reviewer = next((i.get("reviewer") for i in items if i.get("reviewer")), "reviewer")
        evidence_sentence = next((i.get("evidence_sentence") for i in items if i.get("evidence_sentence")), "")
        page = next((i.get("page") for i in items if i.get("page") is not None), None)
        section = next((i.get("section") for i in items if i.get("section")), "")
        table_number = next((i.get("table_number") for i in items if i.get("table_number") is not None), None)

        for item in items:
            value = item.get("edited_value") if item.get("edited_value") is not None else item.get("value")
            if value is None:
                continue
            if item.get("property") == "conductivity":
                sigma = float(value)
                sigma_type = item.get("conductivity_type")
                sigma_method = item.get("measurement_method")
                sigma_conf = item.get("confidence", 0)
                temperature_celsius = item.get("temperature_celsius")
            elif item.get("property") == "activation_energy":
                ea = float(value)
                ea_conf = item.get("confidence", 0)

        if sigma is None and ea is None:
            continue

        rec = make_record(
            material_id=material_id,
            doi=doi,
            family=family,
            sigma=sigma,
            sigma_type=sigma_type,
            sigma_method=sigma_method,
            sigma_conf=sigma_conf,
            ea=ea,
            ea_conf=ea_conf,
            extraction_method="manual",
            human_reviewed=True,
            reviewer=reviewer,
            evidence_sentence=evidence_sentence,
            page=page,
            section=section,
            table_number=table_number,
            temperature_celsius=temperature_celsius,
        )
        records.append(rec)
        print(f"  {material_id}: σ={sigma} Ea={ea} (reviewed by {reviewer})")
    return records


def flatten_record(record: dict) -> dict:
    """Convert a nested block dict into flat 'block.field' columns matching the
    format used by verified_literature.parquet and the rest of the pipeline."""
    flat: dict = {}
    for block_name, block in record.items():
        if isinstance(block, dict):
            for field, value in block.items():
                flat[f"{block_name}.{field}"] = value
        else:
            flat[block_name] = block
    return flat


def main():
    pipeline_dir = Path("scandium_output")
    records: list[dict] = []

    if REVIEW_QUEUE_PATH.exists():
        with open(REVIEW_QUEUE_PATH) as f:
            queue = json.load(f)
        n_approved = sum(1 for i in queue.get("items", []) if i.get("status") == "approved")
        if n_approved:
            print(f"Using review-approved records ({n_approved} approved items):")
            records.extend(convert_review_queue(queue))

    if not records:
        print("No review-approved records found. Falling back to raw extraction results.")
        for result_path in pipeline_dir.glob("*/extraction_result.json"):
            paper_id = result_path.parent.name
            try:
                with open(result_path) as f:
                    result = json.load(f)
            except Exception as e:
                print(f"  Skip {paper_id}: {e}")
                continue
            paper_records = convert_paper_result(paper_id, result)
            if paper_records:
                print(f"  {paper_id}: {len(paper_records)} records ({result.get('primary_composition','?')})")
                records.extend(paper_records)

    if not records:
        print("No records to convert")
        return

    # Flatten to the pipeline's flat 'block.field' column format.
    records = [flatten_record(r) for r in records]

    def _nested(row: dict, block: str, field: str):
        flat_key = f"{block}.{field}"
        if flat_key in row:
            return row.get(flat_key)
        val = row.get(block)
        if isinstance(val, dict):
            return val.get(field)
        return None

    # Accumulate: merge new records into any existing verified set.
    # Policy: never overwrite an existing value (it was hand-checked). If a new
    # approval for a material+paper already exists, FILL IN the fields the
    # existing record is missing (e.g. existing has sigma_RT, new approval adds
    # activation_energy_Ea) instead of dropping the new information outright.
    save_path = Path("cleaning_output/verified_canonical.parquet")
    if save_path.exists():
        existing = pq.read_table(save_path).to_pandas()
        print(f"Existing verified records: {len(existing)}")
        new_df = pd.DataFrame(records)
        if not new_df.empty:
            # Index existing rows by (material_id, source_id).
            existing_rows = existing.to_dict("records")
            existing_by_key: dict[tuple, int] = {}
            for i, r in enumerate(existing_rows):
                existing_by_key.setdefault(
                    (_nested(r, "identity", "material_id"), _nested(r, "identity", "source_id")),
                    i,
                )
            kept = []
            merged = 0
            for row in new_df.to_dict("records"):
                key = (_nested(row, "identity", "material_id"), _nested(row, "identity", "source_id"))
                idx = existing_by_key.get(key)
                if idx is None:
                    kept.append(row)
                    existing_by_key[key] = len(existing_rows) + len(kept) - 1
                    continue
                # Merge: fill missing fields on the existing record only.
                target = existing_rows[idx]
                for col in row:
                    new = row[col]
                    if col in target:
                        old = target[col]
                        is_empty = old is None or (hasattr(old, "isna") and bool(old.isna())) or (
                            isinstance(old, float) and pd.isna(old)
                        )
                        if is_empty and new is not None and not (isinstance(new, float) and pd.isna(new)):
                            target[col] = new
                            merged += 1
                    else:
                        target[col] = new
                existing_rows[idx] = target
            if merged:
                print(f"  Merged {merged} missing field(s) into {len(new_df)} "
                      f"matching (material, doi) records (existing values kept)")
            if kept:
                combined = pd.concat([existing, pd.DataFrame(kept)], ignore_index=True)
            else:
                combined = pd.DataFrame(existing_rows)
        else:
            combined = existing
        combined = combined.reset_index(drop=True)
    else:
        combined = pd.DataFrame(records)

    # Coerce mixed-type provenance numeric columns to a single safe type before
    # writing (merge can mix int pages from new records with float NaN in old ones).
    for col in ("text_provenance.evidence_page", "text_provenance.evidence_table_number"):
        if col in combined.columns:
            combined[col] = combined[col].apply(_to_int_or_none)

    table = pa.Table.from_pandas(combined)
    pq.write_table(table, save_path)
    print(f"\nSaved {len(combined)} records (incl. {len(records)} new) to {save_path}")


if __name__ == "__main__":
    main()
