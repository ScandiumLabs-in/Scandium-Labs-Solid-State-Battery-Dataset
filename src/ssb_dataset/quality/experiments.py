"""v0.9 — first-class experiments table.

The roadmap's v1.0 pivot: 1 material -> N papers -> N experiments -> N
measurements. The canonical dataset stores the experiment block embedded
per-record; this module promotes it into a standalone `experiments` entity
keyed by `experiment_id`, linked to `material_id` and the paper DOI, carrying
the full measurement block (σ, Ea, temperature, method, conditions, evidence).

An experiment is one measurement of one material under one set of reported
conditions — the finest grain the data supports. Records without any
experiment block (the bulk DFT catalog) are not promoted; the table is the
experimental core.

Deterministic: experiment_id is a stable hash of the material + paper +
measurement identity, so re-runs produce identical ids.
"""

from __future__ import annotations

import hashlib
from typing import Any

import pandas as pd

EXPERIMENT_FIELDS = (
    "sample_form", "pellet_diameter_mm", "thickness_mm", "relative_density_pct",
    "theoretical_density_g_per_cm3", "pellet_density_g_per_cm3",
    "pelletizing_pressure_MPa", "electrode_material", "electrode_deposition",
    "frequency_min_Hz", "frequency_max_Hz", "atmosphere", "humidity",
    "measurement_method", "conductivity_type", "heating_rate_C_per_min",
    "cooling_rate_C_per_min", "sinter_temperature_C", "sinter_time_h",
    "annealing_temperature_C", "annealing_time_h", "instrument",
    "equivalent_circuit", "dc_bias_V", "grain_size_um", "porosity_pct",
    "electrolyte_thickness_mm", "electrolyte_area_cm2",
    "current_density_mA_per_cm2", "cell_configuration",
    "electrochemical_window_V", "critical_current_density_mA_per_cm2",
    "cycling_stability", "sigma_60C_S_per_cm", "sigma_80C_S_per_cm", "notes",
)

MEASUREMENT_FIELDS = {
    "ion_transport.sigma_RT": "sigma_S_per_cm",
    "ion_transport.activation_energy_Ea": "activation_energy_eV",
    "ion_transport.measurement_method": "measurement_method",
    "ion_transport.conductivity_type": "conductivity_type",
    "ion_transport.conductivity_source_type": "conductivity_source_type",
}

EVIDENCE_FIELDS = {
    "text_provenance.source_doi": "paper_doi",
    "text_provenance.source_paper_title": "paper_title",
    "text_provenance.source_journal": "journal",
    "text_provenance.source_year": "year",
    "text_provenance.evidence_page": "evidence_page",
    "text_provenance.evidence_section": "evidence_section",
    "text_provenance.evidence_sentence": "evidence_sentence",
    "text_provenance.evidence_table_number": "evidence_table_number",
    "text_provenance.extraction_method": "extraction_method",
    "text_provenance.extraction_reviewer": "reviewer",
    "identity.confidence_tier": "confidence_tier",
}


def _stable_id(material_id: str, doi: str, sigma, ea, temperature) -> str:
    raw = "|".join(str(x) for x in (material_id, doi, sigma, ea, temperature))
    return "exp-" + hashlib.sha256(raw.encode()).hexdigest()[:16]


def build_experiments_table(df: pd.DataFrame) -> pd.DataFrame:
    """Promote canonical rows into a standalone experiments table.

    Every row that carries an experiment block OR a σ/Ea measurement becomes
    one experiment row. Bulk DFT rows without any experimental content are
    excluded (this is the experimental core, not the structural catalog).
    """
    exp_col = "experiment"
    has_exp = exp_col in df.columns
    has_measurement = any(c in df.columns for c in MEASUREMENT_FIELDS)

    def _carries_experiment(row) -> bool:
        if has_exp:
            e = row.get(exp_col)
            if isinstance(e, dict) and any(_present(v) for v in e.values()):
                return True
        if has_measurement:
            for c in MEASUREMENT_FIELDS:
                if c in df.columns and _present(row.get(c)):
                    return True
        return False

    rows = []
    for idx, row in df.iterrows():
        if not _carries_experiment(row):
            continue
        exp = row.get(exp_col) if has_exp and isinstance(row.get(exp_col), dict) else {}
        material_id = str(row.get("identity.material_id", "") or "")
        doi = str(row.get("text_provenance.source_doi", "") or "")
        sigma = row.get("ion_transport.sigma_RT")
        ea = row.get("ion_transport.activation_energy_Ea")
        temperature = _min_temp_c(row.get("ion_transport.temperature_range_measured"))

        rec: dict[str, Any] = {
            "experiment_id": _stable_id(material_id, doi, sigma, ea, temperature),
            "material_id": material_id,
            "family": row.get("identity.family"),
            "source_db": row.get("identity.source_db"),
            "canonical_row": idx,
        }
        for f in EXPERIMENT_FIELDS:
            rec[f] = exp.get(f)
        for col, out in MEASUREMENT_FIELDS.items():
            rec[out] = row.get(col)
        for col, out in EVIDENCE_FIELDS.items():
            rec[out] = row.get(col)
        rec["temperature_min_C"] = temperature
        rec["temperature_max_C"] = _max_temp_c(row.get("ion_transport.temperature_range_measured"))
        rows.append(rec)

    out = pd.DataFrame(rows)
    if not out.empty:
        out = out.drop_duplicates(subset=["experiment_id"]).reset_index(drop=True)
    return out


def _present(v) -> bool:
    if v is None:
        return False
    s = str(v).strip()
    return s != "" and s.lower() not in ("nan", "none", "null", "unknown")


def _min_temp_c(v) -> float | None:
    if isinstance(v, dict):
        for k in ("min_C", "min", "low"):
            if k in v:
                try:
                    return float(v[k])
                except (TypeError, ValueError):
                    return None
    return None


def _max_temp_c(v) -> float | None:
    if isinstance(v, dict):
        for k in ("max_C", "max", "high"):
            if k in v:
                try:
                    return float(v[k])
                except (TypeError, ValueError):
                    return None
    return None
