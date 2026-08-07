"""Cross-database scientific validation (Phase A, v1.4.0).

Deterministic, LLM-free agreement scoring between independent DFT databases
for overlapping materials. The join key is the pymatgen *reduced formula* —
the only identity both Materials Project and JARVIS-DFT staging rows share
(JARVIS carries no MP material-id cross-reference in this snapshot).

For each reduced formula present in >= 2 sources, every property the record
shares with the other source(s) is compared and scored:

  agreement_score      0..1 — mean over comparable properties of
                              max(0, 1 - |dev| / tolerance)
  database_count       number of distinct source databases for the formula
  disagreement         per-property {abs_dev, rel_dev, source}
  rank                 record's agreement-score rank within its formula
                       (1 = best-agreeing record for that composition)

Properties compared (only when BOTH sides carry a value; NaN/missing never
counts as disagreement):
  - formation_energy_per_atom (eV/atom; tol 0.05)
  - band_gap (eV; tol 0.5 — wide because JARVIS reports OptB88vdW, MP PBE)
  - density (g/cm3; tol 5%)
  - volume_per_formula_unit (A3; tol 5% — volume is normalized by formula
    units so primitive/conventional cell choices do not create fake
    disagreement)
  - lattice a/b/c (A; tol 3%)

Sourcing: MP from staging/materials_project (already carries full columns);
JARVIS rows are read from staging/jarvis which scripts/enrich_jarvis.py has
backfilled with composition/density/volume/nsites. NOMAD and COD staging
rows are too small and/or lack comparable values and are reported as
excluded, not as agreement 0.

Outputs:
  validation_output/cross_db_validation.parquet   per-record validation block
  validation_output/cross_db_validation_report.json   summary + findings
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Iterable

import numpy as np
import pandas as pd
from pymatgen.core import Composition

ROOT = Path(__file__).resolve().parent.parent.parent.parent
MP_STAGING = ROOT / "staging" / "materials_project"
JARVIS_STAGING = ROOT / "staging" / "jarvis"
VALIDATION_OUT = ROOT / "validation_output"

# per-property comparison tolerances (absolute for energies, relative for
# structure). band_gap is deliberately wide because the two databases use
# different exchange-correlation functionals (PBE vs OptB88vdW).
PROPERTIES = {
    "formation_energy_per_atom": {"tol": 0.05, "mode": "abs", "unit": "eV/atom"},
    "band_gap": {"tol": 0.5, "mode": "abs", "unit": "eV"},
    "density": {"tol": 0.05, "mode": "rel", "unit": "g/cm3"},
    "volume_per_formula_unit": {"tol": 0.05, "mode": "rel", "unit": "A3/f.u."},
    "lattice_a": {"tol": 0.03, "mode": "rel", "unit": "A"},
    "lattice_b": {"tol": 0.03, "mode": "rel", "unit": "A"},
    "lattice_c": {"tol": 0.03, "mode": "rel", "unit": "A"},
}


# ---------------------------------------------------------------------------
# data loaders
# ---------------------------------------------------------------------------


def _read_staging(glob_pattern: str) -> pd.DataFrame:
    frames = []
    for f in sorted(Path(ROOT).glob(glob_pattern)):
        frames.append(pd.read_parquet(f))
    return pd.concat(frames, ignore_index=True) if frames else pd.DataFrame()


def load_mp() -> pd.DataFrame:
    df = _read_staging("staging/materials_project/*/part-*.parquet")
    cols = ["identity.material_id", "identity.reduced_formula",
            "thermodynamics.formation_energy_per_atom", "thermodynamics.band_gap",
            "structure.density", "structure.volume", "structure.nsites",
            "structure.lattice_params.a", "structure.lattice_params.b",
            "structure.lattice_params.c"]
    return _renamed(df, "materials_project", cols)


def load_jarvis() -> pd.DataFrame:
    df = _read_staging("staging/jarvis/*/part-*.parquet")
    cols = ["identity.material_id", "identity.reduced_formula",
            "thermodynamics.formation_energy_per_atom", "thermodynamics.band_gap",
            "structure.density", "structure.volume", "structure.nsites",
            "structure.lattice_params.a", "structure.lattice_params.b",
            "structure.lattice_params.c"]
    return _renamed(df, "jarvis", cols)


def _renamed(df: pd.DataFrame, source: str, cols: list[str]) -> pd.DataFrame:
    keep = {c: c.split(".")[-1] for c in cols}
    out = df[list(keep)].rename(columns=keep)
    out["source_db"] = source
    out["material_id"] = out["material_id"].astype(str)
    return out


# ---------------------------------------------------------------------------
# agreement math
# ---------------------------------------------------------------------------


def _per_property_agreement(mp_value: float, jv_value: float, spec: dict) -> float:
    if np.isnan(mp_value) or np.isnan(jv_value):
        return 0.0  # never call missing a disagreement; caller filters
    dev = abs(mp_value - jv_value)
    if spec["mode"] == "rel":
        denom = max(abs(mp_value), abs(jv_value), 1e-12)
        dev = dev / denom
    return max(0.0, 1.0 - dev / spec["tol"])


def _volume_per_fu(volume: float, nsites: float, formula: str) -> float | None:
    if np.isnan(volume) or np.isnan(nsites) or not formula:
        return None
    try:
        fu_atoms = float(Composition(formula).num_atoms)
    except Exception:
        return None
    if fu_atoms <= 0 or nsites <= 0:
        return None
    return volume * fu_atoms / nsites


def _record_features(row: pd.Series) -> dict:
    """Extract comparable properties for one record."""
    formula = row.get("reduced_formula") or ""
    feats: dict[str, float] = {}
    for prop in PROPERTIES:
        key = prop
        if prop == "volume_per_formula_unit":
            v = _volume_per_fu(row.get("volume"), row.get("nsites"), formula)
            if v is not None:
                feats[prop] = v
        else:
            col = {"lattice_a": "lattice_a", "lattice_b": "lattice_b",
                   "lattice_c": "lattice_c", "density": "density",
                   "band_gap": "band_gap",
                   "formation_energy_per_atom": "formation_energy_per_atom"
                   }[key]
            val = row.get(col)
            if val is not None and not (isinstance(val, float) and np.isnan(val)):
                feats[prop] = float(val)
    return feats


# ---------------------------------------------------------------------------
# main scoring
# ---------------------------------------------------------------------------


def compute_agreement(mp: pd.DataFrame, jarvis: pd.DataFrame) -> pd.DataFrame:
    """Score every overlapping-material record. Returns per-record rows with
    the validation block columns flattened."""
    mp = mp.dropna(subset=["reduced_formula"])
    jarvis = jarvis.dropna(subset=["reduced_formula"])
    mp_f = {f: g for f, g in mp.groupby("reduced_formula")}
    jv_f = {f: g for f, g in jarvis.groupby("reduced_formula")}

    records: list[dict] = []
    for formula in set(mp_f) & set(jv_f):
        mp_grp = mp_f[formula]
        jv_grp = jv_f[formula]
        for _, mrow in mp_grp.iterrows():
            for _, jrow in jv_grp.iterrows():
                records.extend(_score_pair(formula, mrow, jrow))
    if not records:
        return pd.DataFrame()

    df = pd.DataFrame(records)
    # per-record: average per-property agreement across all partners
    df["_pa"] = df["_properties"].map(
        lambda d: float(np.mean([v["agreement"] for v in d.values()]))
        if d else 0.0)
    agg = (df.groupby(["formula", "material_id", "source_db"])
           .agg(agreement_score=("_pa", "mean"),
                _partners=("_partner", list),
                _props=("_properties", list))
           .reset_index())
    # merge back partner property maps (dedup identical partner props)
    rows = []
    for _, r in agg.iterrows():
        props: dict[str, dict] = {}
        for p in r["_props"]:
            for k, v in p.items():
                props.setdefault(k, v)
        rows.append({
            "reduced_formula": r["formula"],
            "material_id": r["material_id"],
            "source_db": r["source_db"],
            "database_count": 2,
            "agreement_score": round(float(r["agreement_score"]), 4),
            "disagreement": json.dumps(props),
        })
    out = pd.DataFrame(rows)
    out = _rank_within_formula(out)
    return out


def _score_pair(formula: str, mrow: pd.Series, jrow: pd.Series) -> list[dict]:
    """Score one MP-JARVIS pair, emitting a validation row for BOTH sides so
    the JARVIS record also carries its cross-database agreement."""
    mf = _record_features(mrow)
    jf = _record_features(jrow)
    props: dict[str, dict] = {}
    for prop in PROPERTIES:
        if prop in mf and prop in jf:
            spec = PROPERTIES[prop]
            a = _per_property_agreement(mf[prop], jf[prop], spec)
            dev = abs(mf[prop] - jf[prop])
            if spec["mode"] == "rel":
                denom = max(abs(mf[prop]), abs(jf[prop]), 1e-12)
                dev = dev / denom
            props[prop] = {
                "agreement": round(a, 4),
                "abs_dev": round(dev, 4),
                "mp": round(mf[prop], 4),
                "jarvis": round(jf[prop], 4),
            }
    return [
        {
            "formula": formula,
            "material_id": str(mrow["material_id"]),
            "source_db": str(mrow["source_db"]),
            "_partner": str(jrow["material_id"]),
            "_properties": props,
        },
        {
            "formula": formula,
            "material_id": str(jrow["material_id"]),
            "source_db": str(jrow["source_db"]),
            "_partner": str(mrow["material_id"]),
            "_properties": props,
        },
    ]


def _rank_within_formula(df: pd.DataFrame) -> pd.DataFrame:
    """rank 1 = best-agreeing record for that composition (ties by name)."""
    df = df.sort_values(["reduced_formula", "agreement_score", "material_id"],
                        ascending=[True, False, True])
    df["rank"] = df.groupby("reduced_formula").cumcount() + 1
    return df


# ---------------------------------------------------------------------------
# report
# ---------------------------------------------------------------------------


def build_report(df: pd.DataFrame) -> dict:
    excluded = {
        "nomad": "staging rows carry no composition/density/volume and no "
                 "formation-energy/band-gap values to compare",
        "cod": "staging rows carry lattice params only (formation/gap null) "
               "and the CIFs have heavy occupancy defects; 66-row source "
               "too small for a meaningful agreement signal",
        "aflow": "connector stubbed — no data on disk",
        "oqmd": "connector stubbed — no data on disk",
    }
    if df.empty:
        return {"overlap_formulas": 0, "records_validated": 0,
                "excluded_sources": excluded,
                "note": "no overlapping materials"}
    overlap_formulas = df["reduced_formula"].nunique()
    n_mp = int((df["source_db"] == "materials_project").sum())
    n_jv = int((df["source_db"] == "jarvis").sum())
    scores = df["agreement_score"].dropna()
    by_prop: dict[str, dict] = {}
    for prop, spec in PROPERTIES.items():
        devs = []
        for d in df["disagreement"].dropna():
            try:
                v = json.loads(d).get(prop, {}).get("abs_dev")
            except Exception:
                v = None
            if v is not None:
                devs.append(v)
        if devs:
            by_prop[prop] = {
                "unit": spec["unit"],
                "n": len(devs),
                "mean_abs_dev": round(float(np.mean(devs)), 4),
                "median_abs_dev": round(float(np.median(devs)), 4),
                "p95_abs_dev": round(float(np.percentile(devs, 95)), 4),
            }
    report = {
        "overlap_formulas": overlap_formulas,
        "records_validated": len(df),
        "mp_records": n_mp,
        "jarvis_records": n_jv,
        "mean_agreement": round(float(scores.mean()), 4),
        "median_agreement": round(float(scores.median()), 4),
        "agreement_distribution": {
            "p25": round(float(np.percentile(scores, 25)), 4),
            "p50": round(float(np.percentile(scores, 50)), 4),
            "p75": round(float(np.percentile(scores, 75)), 4),
        },
        "per_property": by_prop,
        "excluded_sources": excluded,
        "band_gap_note": ("JARVIS reports OptB88vdW band gaps, MP PBE — a "
                          "known functional systematic. The 0.5 eV tolerance "
                          "absorbs it; the per-property mean_abs_dev is the "
                          "honest offset magnitude."),
    }
    return report


def main() -> None:
    VALIDATION_OUT.mkdir(parents=True, exist_ok=True)
    print("Loading MP staging ...")
    mp = load_mp()
    print(f"  {len(mp)} MP records")
    print("Loading JARVIS staging (enriched) ...")
    jv = load_jarvis()
    print(f"  {len(jv)} JARVIS records")
    df = compute_agreement(mp, jv)
    print(f"Validated {len(df)} records across {df['reduced_formula'].nunique()}"
          if not df.empty else "No overlap")
    df.to_parquet(VALIDATION_OUT / "cross_db_validation.parquet", index=False)
    report = build_report(df)
    (VALIDATION_OUT / "cross_db_validation_report.json").write_text(
        json.dumps(report, indent=2))
    print(json.dumps({k: v for k, v in report.items()
                      if k not in ("excluded_sources", "per_property")},
                     indent=2))


if __name__ == "__main__":
    main()
