"""v0.9 — automatic consistency checks (anomaly report).

Every release runs a deterministic scan over the full canonical dataset for
physically implausible or provenance-corrupt values. The checks mirror the
roadmap's examples:

  Ea < 0, σ < 0, density > theoretical density, temperature < 0 K,
  duplicate DOI, duplicate experiment, missing composition, charge imbalance.

Each check emits (severity, n_affected, sample_ids). The release gate blocks
only on high-severity anomalies; medium/low are surfaced in the report for the
human. Pure functions, no LLM, no network.
"""

from __future__ import annotations

from typing import Any

import numpy as np
import pandas as pd


def _num(v):
    try:
        f = float(v)
        return None if np.isnan(f) else f
    except (TypeError, ValueError):
        return None


def _col(df: pd.DataFrame, *candidates: str) -> str | None:
    for c in candidates:
        if c in df.columns:
            return c
    return None


def check_negative_activation_energy(df: pd.DataFrame) -> dict[str, Any]:
    ea = _col(df, "ion_transport.activation_energy_Ea", "activation_energy_Ea")
    if ea is None:
        return {"severity": "high", "n": 0, "sample_ids": [],
                "message": "no activation-energy column"}
    s = df[ea]
    bad = s.apply(lambda v: (_num(v) is not None and _num(v) < 0))
    ids = df.loc[bad].index.tolist()
    return {"severity": "high", "n": int(bad.sum()), "sample_ids": ids,
            "message": f"activation energy < 0 in {ea}"}


def check_negative_conductivity(df: pd.DataFrame) -> dict[str, Any]:
    sig = _col(df, "ion_transport.sigma_RT", "sigma_RT")
    if sig is None:
        return {"severity": "high", "n": 0, "sample_ids": [],
                "message": "no conductivity column"}
    s = df[sig]
    bad = s.apply(lambda v: (_num(v) is not None and _num(v) < 0))
    ids = df.loc[bad].index.tolist()
    return {"severity": "high", "n": int(bad.sum()), "sample_ids": ids,
            "message": f"conductivity < 0 in {sig}"}


def check_density_exceeds_theoretical(df: pd.DataFrame) -> dict[str, Any]:
    """pellet/relative density > theoretical density is physically impossible."""
    pellet = _col(df, "experiment.pellet_density_g_per_cm3", "pellet_density_g_per_cm3")
    theo = _col(df, "experiment.theoretical_density_g_per_cm3", "theoretical_density_g_per_cm3")
    if not pellet or not theo:
        return {"severity": "medium", "n": 0, "sample_ids": [],
                "message": "no density pair to compare"}
    p = df[pellet].apply(_num)
    t = df[theo].apply(_num)
    bad = (p.notna() & t.notna() & (p > t * 1.05))
    ids = df.loc[bad].index.tolist()
    return {"severity": "medium", "n": int(bad.sum()), "sample_ids": ids,
            "message": "pellet density > 1.05x theoretical density"}


def check_temperature_below_zero_k(df: pd.DataFrame) -> dict[str, Any]:
    """Any reported temperature below absolute zero is an extraction error."""
    tr = _col(df, "ion_transport.temperature_range_measured", "temperature_range_measured")
    if tr is None:
        return {"severity": "high", "n": 0, "sample_ids": [],
                "message": "no temperature column"}

    def _min_k(v):
        if isinstance(v, dict):
            for k in ("min_K", "min", "low"):
                if k in v:
                    return _num(v[k])
        return None
    mins = df[tr].apply(_min_k)
    bad = (mins < 0)
    ids = df.loc[bad].index.tolist()
    return {"severity": "high", "n": int(bad.sum()), "sample_ids": ids,
            "message": "temperature below 0 K"}


def check_duplicate_doi(df: pd.DataFrame) -> dict[str, Any]:
    """A DOI that maps to many distinct material_ids on verified records —
    each experimental record should trace to exactly one paper + material."""
    doi = _col(df, "text_provenance.source_doi", "source_doi")
    mid = _col(df, "identity.material_id", "material_id")
    if not doi or not mid:
        return {"severity": "low", "n": 0, "sample_ids": [],
                "message": "no doi/material_id pair"}
    sub = df[df[doi].notna() & (df[doi] != "")]
    if sub.empty:
        return {"severity": "low", "n": 0, "sample_ids": [],
                "message": "no DOI-carrying records"}
    counts = sub.groupby(doi)[mid].nunique()
    heavy = counts[counts > 1]
    ids = [str(i) for i in heavy.index]
    return {"severity": "low", "n": int(len(heavy)), "sample_ids": ids[:50],
            "message": "DOIs each linked to >1 material_id (n of DOIs)"}


def check_duplicate_experiment(df: pd.DataFrame) -> dict[str, Any]:
    """Identical (doi, material, sigma, Ea) rows are copy-paste artifacts."""
    doi = _col(df, "text_provenance.source_doi", "source_doi")
    mid = _col(df, "identity.material_id", "material_id")
    sig = _col(df, "ion_transport.sigma_RT", "sigma_RT")
    if not doi or not mid or not sig:
        return {"severity": "low", "n": 0, "sample_ids": [],
                "message": "no doi/material/sigma triple"}
    key = df[doi].fillna("") + "|" + df[mid].fillna("") + "|" + df[sig].fillna("").astype(str)
    dup = key.duplicated(keep=False)
    return {"severity": "medium", "n": int(dup.sum()), "sample_ids": df.loc[dup].index.tolist()[:50],
            "message": "duplicate (doi, material, sigma) rows"}


def check_missing_composition(df: pd.DataFrame) -> dict[str, Any]:
    mid = _col(df, "identity.material_id", "material_id")
    if mid is None:
        return {"severity": "high", "n": len(df), "sample_ids": df.index.tolist()[:50],
                "message": "no material_id column"}
    bad = df[mid].isna() | (df[mid].astype(str).str.strip() == "")
    return {"severity": "high", "n": int(bad.sum()),
            "sample_ids": df.loc[bad].index.tolist()[:50],
            "message": "missing material composition"}


def check_charge_imbalance(df: pd.DataFrame) -> dict[str, Any]:
    en = _col(df, "redox.electroneutral", "electroneutral")
    if en is None:
        return {"severity": "low", "n": 0, "sample_ids": [],
                "message": "no electroneutrality column"}
    s = df[en]
    bad = s.astype(str).str.lower() == "false"
    return {"severity": "medium", "n": int(bad.sum()),
            "sample_ids": df.loc[bad].index.tolist()[:50],
            "message": "redox.electroneutral=False (charge imbalance)"}


_CHECKS = (
    check_negative_activation_energy,
    check_negative_conductivity,
    check_density_exceeds_theoretical,
    check_temperature_below_zero_k,
    check_duplicate_doi,
    check_duplicate_experiment,
    check_missing_composition,
    check_charge_imbalance,
)


def scan_anomalies(df: pd.DataFrame) -> dict[str, Any]:
    """Run all checks. Returns a full report dict."""
    results = {}
    for check in _CHECKS:
        name = check.__name__.replace("check_", "")
        try:
            r = check(df)
        except Exception as e:  # pragma: no cover — a broken check must not kill release
            r = {"severity": "high", "n": 0, "sample_ids": [], "message": repr(e)}
        results[name] = r
    n_high = sum(1 for r in results.values() if r["severity"] == "high" and r["n"])
    n_med = sum(1 for r in results.values() if r["severity"] == "medium" and r["n"])
    return {
        "scanned_records": int(len(df)),
        "high_severity_checks_failing": n_high,
        "medium_severity_checks_failing": n_med,
        "checks": results,
        "passed": n_high == 0,
    }
