"""v1.0 — build the relational dataset from the canonical + verified tables.

Reads `cleaning_output/canonical_dataset.parquet` (the full 30,838-row catalog
with the experiment/synthesis/text_provenance blocks embedded) and derives six
first-class tables keyed by deterministic ids:

    materials / papers / experiments / measurements / synthesis / dopants

Experimental variability is preserved: every canonical row that carries a
measurement becomes its own experiment, and every σ/Ea/σ60C/σ80C value becomes
its own measurement row. Nothing is collapsed into material-level aggregates.
"""

from __future__ import annotations

import math
from pathlib import Path
from typing import Any

import pandas as pd

from ssb_dataset.db import schema as s

ROOT = Path(__file__).resolve().parent.parent.parent.parent


# Columns worth carrying into the materials table (the curated structural /
# thermodynamic / electronic core, NOT the whole 246-col flat table).
MATERIAL_CORE_COLS = (
    "identity.material_id", "identity.composition", "identity.formula_pretty",
    "identity.formula_anonymous", "identity.chemsys", "identity.elements",
    "identity.nelements", "identity.family", "identity.subfamily_tag",
    "identity.source_db", "identity.is_electrolyte_candidate",
    "identity.confidence_tier",
    "structure.space_group_number", "structure.crystal_system",
    "structure.point_group", "structure.density", "structure.volume",
    "structure.nsites", "structure.li_site_count", "structure.li_vacancy_fraction",
    "structure.li_hopping_distance", "thermodynamics.formation_energy_per_atom",
    "thermodynamics.energy_above_hull", "thermodynamics.band_gap",
    "thermodynamics.is_stable", "thermodynamics.is_metal",
    "thermodynamics.efermi", "thermodynamics.cbm", "thermodynamics.vbm",
    "magnetic.is_magnetic", "magnetic.ordering",
    "electronic.possible_species", "redox.electroneutral",
    "chemistry.electronegativity_mean", "chemistry.average_group",
    "chemistry.average_period", "mechanical.bulk_modulus",
    "mechanical.shear_modulus", "dielectric.e_total",
)


def load_canonical() -> pd.DataFrame:
    return pd.read_parquet(ROOT / "cleaning_output" / "canonical_dataset.parquet")


# --------------------------------------------------------------------------
# materials
# --------------------------------------------------------------------------

def build_materials(df: pd.DataFrame, quality_df: pd.DataFrame | None = None) -> pd.DataFrame:
    """One row per unique material_id. Multi-source materials (same formula
    harvested from MP + literature) keep the highest-quality source row and
    list all sources."""
    rows: dict[str, dict] = {}
    sources: dict[str, set] = {}
    for _, row in df.iterrows():
        mid = row.get("identity.material_id")
        if mid is None or not str(mid).strip():
            continue
        mid = str(mid)
        sources.setdefault(mid, set()).add(str(row.get("identity.source_db") or ""))
        existing = rows.get(mid)
        if existing is None:
            rows[mid] = row
            continue
        # prefer the row that carries an experiment / measurement, else the
        # one with more populated core columns
        if existing.get("identity.confidence_tier") != "dft_native" and row.get("identity.confidence_tier") == "dft_native":
            continue
        if row.get("identity.confidence_tier") != "dft_native" and existing.get("identity.confidence_tier") == "dft_native":
            rows[mid] = row
            continue
        if _populated_count(row) > _populated_count(existing):
            rows[mid] = row

    out = pd.DataFrame([rows[mid] for mid in rows])
    out["source_dbs"] = out["identity.material_id"].map(
        lambda m: sorted(src for src in sources[m] if src))
    # select the curated core columns that actually exist in the source
    present = [c for c in MATERIAL_CORE_COLS if c in out.columns]
    out = out[present + ["source_dbs"]]
    out = out.rename(columns={"identity.material_id": "material_id"})

    if quality_df is not None:
        qcols = {c for c in quality_df.columns if c.startswith("quality.")}
        if qcols:
            merge = quality_df[["identity.material_id", *sorted(qcols)]].copy()
            merge = merge.sort_values("quality.score", ascending=False)
            merge = merge.drop_duplicates(subset="identity.material_id", keep="first")
            merge = merge.rename(columns={"identity.material_id": "material_id"})
            out = out.merge(merge, on="material_id", how="left")

    return out


def _populated_count(row: pd.Series) -> int:
    return int(row.notna().sum())


# --------------------------------------------------------------------------
# papers
# --------------------------------------------------------------------------

def build_papers(df: pd.DataFrame) -> pd.DataFrame:
    """One row per paper DOI in the experimental core (rows carrying an
    experiment block or a measurement)."""
    rows: dict[str, dict] = {}
    for _, row in df.iterrows():
        doi = row.get("text_provenance.source_doi")
        if not doi:
            continue
        doi = str(doi).strip()
        if not doi:
            continue
        rec = rows.setdefault(
            doi,
            {
                "paper_id": doi,
                "doi": doi,
                "title": row.get("text_provenance.source_paper_title"),
                "journal": row.get("text_provenance.source_journal"),
                "year": row.get("text_provenance.source_year"),
            },
        )
        for k in ("title", "journal"):
            if not rec.get(k):
                rec[k] = row.get(f"text_provenance.source_{k}")
        if not rec.get("year"):
            rec["year"] = row.get("text_provenance.source_year")
    out = pd.DataFrame(rows.values())
    return out


# --------------------------------------------------------------------------
# experiments + measurements
# --------------------------------------------------------------------------

def _experiment_condition_dict(row: pd.Series) -> dict[str, Any]:
    """Merge the experiment block fields into a flat dict for fingerprinting."""
    exp = row.get("experiment")
    base = {"temperature_range_measured": row.get("ion_transport.temperature_range_measured")}
    if isinstance(exp, dict):
        for k in s.EXPERIMENT_FINGERPRINT_FIELDS:
            base[k] = exp.get(k)
    return base


def _synthesis_condition_dict(row: pd.Series) -> dict[str, Any]:
    syn = row.get("synthesis")
    exp = row.get("experiment")
    out: dict[str, Any] = {}
    if isinstance(syn, dict):
        for k in s.SYNTHESIS_FINGERPRINT_FIELDS:
            out[k] = syn.get(k)
    if isinstance(exp, dict):
        # sinter/anneal/pelletizing live in the experiment block
        for k in ("sinter_temperature_C", "sinter_time_h", "annealing_temperature_C",
                  "annealing_time_h", "pelletizing_pressure_MPa", "atmosphere",
                  "heating_rate_C_per_min", "cooling_rate_C_per_min"):
            if out.get(k) is None:
                out[k] = exp.get(k)
    return out


def build_experiments_and_measurements(
    df: pd.DataFrame,
) -> tuple[pd.DataFrame, pd.DataFrame]:
    """Promote measurement-carrying canonical rows into experiment + measurement
    tables. One canonical row = one experiment (one material + one paper +
    one condition fingerprint). Each σ / Ea / σ60C / σ80C value in that row is
    a separate measurement."""
    experiments: list[dict[str, Any]] = []
    measurements: list[dict[str, Any]] = []

    for _, row in df.iterrows():
        material_id = str(row.get("identity.material_id") or "").strip()
        if not material_id:
            continue
        has_measurement = any(
            row.get(col) is not None and not pd.isna(row.get(col))
            for col in s.MEASUREMENT_MAP
        )
        exp_block = row.get("experiment")
        carries = has_measurement or (isinstance(exp_block, dict) and any(
            v not in (None, "") and not pd.isna(v) if not isinstance(v, list) else bool(v)
            for v in exp_block.values()
        ))
        if not carries:
            continue

        doi = str(row.get("text_provenance.source_doi") or "").strip() or None
        pid = s.paper_id(doi, material_id)

        cond = _experiment_condition_dict(row)
        syn_cond = _synthesis_condition_dict(row)
        exp_fp = s.fingerprint(cond, s.EXPERIMENT_FINGERPRINT_FIELDS)
        syn_fp = s.fingerprint(syn_cond, s.SYNTHESIS_FINGERPRINT_FIELDS)
        eid = s.stable_id("experiment", material_id, pid, s.merge_fingerprints(exp_fp, syn_fp))
        sid = s.stable_id("synthesis", material_id, pid, syn_fp) if syn_fp else None

        tier = row.get("identity.confidence_tier")
        xconf = row.get("text_provenance.extraction_confidence_score")
        xconf = None if xconf is None or (isinstance(xconf, float) and math.isnan(xconf)) else xconf

        exp_rec: dict[str, Any] = {
            "experiment_id": eid,
            "material_id": material_id,
            "paper_id": pid,
            "sample_id": s.stable_id("sample", material_id, pid, syn_fp) if syn_fp else None,
            "synthesis_id": sid,
            "family": row.get("identity.family"),
            "confidence_tier": tier,
        }
        # condition fields (flat)
        for k in s.EXPERIMENT_FINGERPRINT_FIELDS:
            exp_rec[k] = cond.get(k)
        exp_rec["temperature_min_C"] = _min_temp_c(row.get("ion_transport.temperature_range_measured"))
        exp_rec["temperature_max_C"] = _max_temp_c(row.get("ion_transport.temperature_range_measured"))
        # evidence block
        exp_rec.update({
            "evidence_page": row.get("text_provenance.evidence_page"),
            "evidence_section": row.get("text_provenance.evidence_section"),
            "evidence_table_number": row.get("text_provenance.evidence_table_number"),
            "evidence_sentence": row.get("text_provenance.evidence_sentence"),
            "reviewer": row.get("text_provenance.extraction_reviewer"),
            "extraction_method": row.get("text_provenance.extraction_method"),
            "canonical_row": int(row.name) if hasattr(row, "name") else None,
        })
        experiments.append(exp_rec)

        # one measurement per populated property
        for col, (prop, unit) in s.MEASUREMENT_MAP.items():
            val = row.get(col)
            if val is None or (isinstance(val, float) and math.isnan(val)):
                continue
            try:
                val = float(val)
            except (TypeError, ValueError):
                continue
            temp_min = _min_temp_c(row.get("ion_transport.temperature_range_measured"))
            fields = s.field_confidences(
                {"temperature_range_measured": row.get("ion_transport.temperature_range_measured"),
                 "ion_transport.measurement_method": row.get("ion_transport.measurement_method"),
                 "text_provenance.evidence_sentence": row.get("text_provenance.evidence_sentence")},
                tier=tier, extraction_confidence=xconf,
            )
            measurements.append({
                "measurement_id": s.stable_id(
                    "measurement", eid, prop, val, unit, temp_min),
                "experiment_id": eid,
                "material_id": material_id,
                "paper_id": pid,
                "property": prop,
                "value": val,
                "unit": unit,
                "temperature_c": temp_min,
                "temperature_min_C": temp_min,
                "temperature_max_C": _max_temp_c(row.get("ion_transport.temperature_range_measured")),
                "measurement_method": row.get("ion_transport.measurement_method"),
                "conductivity_type": row.get("ion_transport.conductivity_type"),
                "confidence_value": fields["value"],
                "confidence_temperature": fields["temperature"],
                "confidence_method": fields["method"],
                "confidence_evidence": fields["evidence"],
                "confidence": s.overall_confidence(fields),
                "confidence_tier": tier,
                "evidence_page": row.get("text_provenance.evidence_page"),
                "evidence_section": row.get("text_provenance.evidence_section"),
                "evidence_table_number": row.get("text_provenance.evidence_table_number"),
                "evidence_sentence": row.get("text_provenance.evidence_sentence"),
                "reviewer": row.get("text_provenance.extraction_reviewer"),
                "extraction_method": row.get("text_provenance.extraction_method"),
                "extraction_confidence_score": xconf,
            })

    exp_df = pd.DataFrame(experiments)
    meas_df = pd.DataFrame(measurements)

    # The relational model emits one entity per unique id: identical
    # experiments (same material+paper+conditions recorded twice in the
    # canonical) collapse to one experiment row; identical measurement values
    # within an experiment collapse to one measurement row. Distinct values
    # are NEVER collapsed — experimental variability is preserved.
    if not exp_df.empty:
        exp_df = exp_df.drop_duplicates(subset=["experiment_id"], keep="first")
    if not meas_df.empty:
        meas_df = meas_df.drop_duplicates(
            subset=["experiment_id", "property", "value", "unit"], keep="first")
    return exp_df, meas_df


# --------------------------------------------------------------------------
# synthesis
# --------------------------------------------------------------------------

def build_synthesis(df: pd.DataFrame) -> pd.DataFrame:
    """One synthesis row per material+paper+synthesis-fingerprint. Only rows
    with at least one populated synthesis field are emitted."""
    rows: list[dict[str, Any]] = []
    seen: set[str] = set()
    for _, row in df.iterrows():
        material_id = str(row.get("identity.material_id") or "").strip()
        if not material_id:
            continue
        syn = row.get("synthesis")
        exp = row.get("experiment")
        if not isinstance(syn, dict):
            syn = {}
        if not isinstance(exp, dict):
            exp = {}
        merged = dict(syn)
        for k in ("sinter_temperature_C", "sinter_time_h", "annealing_temperature_C",
                  "annealing_time_h", "pelletizing_pressure_MPa", "atmosphere",
                  "heating_rate_C_per_min", "cooling_rate_C_per_min"):
            if merged.get(k) is None:
                merged[k] = exp.get(k)
        if not any(_populated(v) for v in merged.values()):
            continue
        doi = str(row.get("text_provenance.source_doi") or "").strip() or None
        pid = s.paper_id(doi, material_id)
        fp = s.fingerprint(merged, s.SYNTHESIS_FINGERPRINT_FIELDS)
        syn_id = s.stable_id("synthesis", material_id, pid, fp)
        if syn_id in seen:
            continue
        seen.add(syn_id)
        rec: dict[str, Any] = {
            "synthesis_id": syn_id,
            "material_id": material_id,
            "paper_id": pid,
            "doi": doi,
        }
        for k in s.SYNTHESIS_FINGERPRINT_FIELDS:
            rec[k] = merged.get(k)
        rows.append(rec)
    return pd.DataFrame(rows)


# --------------------------------------------------------------------------
# dopants
# --------------------------------------------------------------------------

def build_dopants(df: pd.DataFrame) -> pd.DataFrame:
    """Explicit dopant annotations across the catalog (e.g. Li7La3Zr2O12:Ta).
    One row per (material_id, dopant). Sources: canonical material_ids plus
    the benchmark inventory's annotated names (which carry explicit dopant
    annotations like `:Ta` that the canonical formula strings do not)."""
    rows: list[dict[str, Any]] = []
    seen: set[tuple] = set()

    def _emit(mid: str, doi: str | None) -> None:
        for dop in s.extract_dopants(mid):
            key = (mid, dop)
            if key in seen:
                continue
            seen.add(key)
            rows.append({
                "dopant_id": s.stable_id("dopant", mid, dop),
                "material_id": mid,
                "paper_id": s.paper_id(doi, mid),
                "dopant": dop,
                "dopant_source": "material_id_annotation",
            })

    for _, row in df.iterrows():
        mid = str(row.get("identity.material_id") or "").strip()
        if not mid:
            continue
        doi = row.get("text_provenance.source_doi")
        _emit(mid, str(doi).strip() if doi else None)

    # benchmark inventory: formula + annotated names
    try:
        from ssb_dataset.literature.benchmark_inventory import BENCHMARK_INVENTORY
    except ImportError:
        BENCHMARK_INVENTORY = {}
    for name, entry in BENCHMARK_INVENTORY.items():
        formula = (entry.get("formula") or name or "").strip()
        for mid in {formula, name}:
            if mid and s.extract_dopants(mid):
                _emit(mid, entry.get("doi"))

    return pd.DataFrame(rows)


def _populated(v) -> bool:
    if v is None:
        return False
    if isinstance(v, (list, dict, set, tuple)):
        return len(v) > 0
    if hasattr(v, "size") and not hasattr(v, "strip"):
        try:
            return int(v.size) > 0
        except Exception:
            pass
    s2 = str(v).strip()
    return s2 != "" and s2.lower() not in ("nan", "none", "null", "unknown")


def _min_temp_c(v) -> float | None:
    if isinstance(v, dict):
        for k in ("min_C", "min", "low", "min_K"):
            if v.get(k) is not None:
                try:
                    val = float(v[k])
                    return val - 273.15 if k == "min_K" else val
                except (TypeError, ValueError):
                    return None
    return None


def _max_temp_c(v) -> float | None:
    if isinstance(v, dict):
        for k in ("max_C", "max", "high", "max_K"):
            if v.get(k) is not None:
                try:
                    val = float(v[k])
                    return val - 273.15 if k == "max_K" else val
                except (TypeError, ValueError):
                    return None
    return None


def build_relational(
    canonical_path: str | None = None,
    quality_path: str | None = None,
    *,
    pdf_dir: str | Path | None = None,
    enrich_papers_metadata: bool = True,
) -> dict[str, pd.DataFrame]:
    """Build all six tables from the canonical dataset (+ optional quality).

    Returns {"materials": df, "papers": df, "experiments": df,
             "measurements": df, "synthesis": df, "dopants": df,
             "authors": df}.

    `enrich_papers_metadata` backfills papers title/journal/year and the
    authors table from on-disk caches + PDF first pages (deterministic, no
    network). See ssb_dataset.db.papers.
    """
    df = load_canonical() if canonical_path is None else pd.read_parquet(canonical_path)

    quality_df = None
    if quality_path:
        quality_df = pd.read_parquet(quality_path)
    elif (ROOT / "quality_output" / "canonical_quality.parquet").exists():
        quality_df = pd.read_parquet(ROOT / "quality_output" / "canonical_quality.parquet")

    materials = build_materials(df, quality_df)
    papers = build_papers(df)
    experiments, measurements = build_experiments_and_measurements(df)
    synthesis = build_synthesis(df)
    dopants = build_dopants(df)

    # --- Phase 10 enrichment: papers metadata + authors (deterministic) -----
    authors: pd.DataFrame = pd.DataFrame()
    if enrich_papers_metadata and not papers.empty:
        from ssb_dataset.db import papers as papermeta

        papers = papermeta.enrich_papers(
            papers, pdf_dir=pdf_dir or ROOT / "literature_output" / "pdfs")
        authors = papermeta.build_authors(
            papers, pdf_dir=pdf_dir or ROOT / "literature_output" / "pdfs")

    # --- populate aggregate counts on materials / papers -------------------
    if not experiments.empty:
        agg = experiments.groupby("material_id").agg(
            n_experiments=("experiment_id", "nunique"),
            n_papers=("paper_id", "nunique"),
        ).reset_index()
        materials = materials.merge(agg, on="material_id", how="left")
        materials["n_experiments"] = materials["n_experiments"].fillna(0).astype(int)
        materials["n_papers"] = materials["n_papers"].fillna(0).astype(int)
    if not measurements.empty:
        m_agg = measurements.groupby("material_id")["measurement_id"].nunique().rename("n_measurements")
        materials = materials.merge(m_agg, on="material_id", how="left")
        materials["n_measurements"] = materials["n_measurements"].fillna(0).astype(int)

    if not papers.empty and not experiments.empty:
        p_exp = experiments.groupby("paper_id")["experiment_id"].nunique().rename("n_experiments")
        papers = papers.merge(p_exp, on="paper_id", how="left")
        papers["n_experiments"] = papers["n_experiments"].fillna(0).astype(int)
    if not papers.empty and not measurements.empty:
        p_meas = measurements.groupby("paper_id")["measurement_id"].nunique().rename("n_measurements")
        p_mat = measurements.drop_duplicates("paper_id").groupby("paper_id")["material_id"].count().rename("n_materials")
        papers = papers.merge(p_meas, on="paper_id", how="left")
        papers = papers.merge(p_mat, on="paper_id", how="left")
        papers["n_measurements"] = papers["n_measurements"].fillna(0).astype(int)
        papers["n_materials"] = papers["n_materials"].fillna(0).astype(int)

    return {
        "materials": materials,
        "papers": papers,
        "experiments": experiments,
        "measurements": measurements,
        "synthesis": synthesis,
        "dopants": dopants,
        "authors": authors,
    }
