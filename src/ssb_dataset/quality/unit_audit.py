"""v0.9 — unit-normalization audit across the whole canonical dataset.

Verifies that every conductivity / activation-energy / temperature value in the
canonical dataset is stored in canonical SI units (S/cm, eV, °C/K) and is
physically plausible, mirroring the roadmap's "everything in SI internally"
requirement.

What this checks per record:
  - σ_RT present → must be a positive float within [1e-12, 1e2] S/cm
  - Ea present  → must be a positive float within [0.01, 5.0] eV
  - temperature present → must be > 0 K
  - no canonical units column may still carry a raw unit string suffix
    (a sign the normalization step was skipped for that row)

Output: an audit dict + a per-row flag list. Pure functions.
"""

from __future__ import annotations

from typing import Any

import numpy as np
import pandas as pd

SIGMA_BOUNDS = (1e-12, 1e2)     # S/cm
EA_BOUNDS = (0.01, 5.0)         # eV


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


def audit_sigma(df: pd.DataFrame) -> dict[str, Any]:
    sig = _col(df, "ion_transport.sigma_RT", "sigma_RT")
    if sig is None:
        return {"n": 0, "invalid": 0, "sample_ids": [],
                "message": "no conductivity column"}
    bad = df[sig].apply(
        lambda v: (_num(v) is not None and not (SIGMA_BOUNDS[0] <= _num(v) <= SIGMA_BOUNDS[1])))
    return {"n": int(df[sig].notna().sum()), "invalid": int(bad.sum()),
            "sample_ids": df.loc[bad].index.tolist()[:50],
            "message": f"σ outside [{SIGMA_BOUNDS[0]:.0e}, {SIGMA_BOUNDS[1]:.0e}] S/cm"}


def audit_ea(df: pd.DataFrame) -> dict[str, Any]:
    ea = _col(df, "ion_transport.activation_energy_Ea", "activation_energy_Ea")
    if ea is None:
        return {"n": 0, "invalid": 0, "sample_ids": [],
                "message": "no activation-energy column"}
    bad = df[ea].apply(
        lambda v: (_num(v) is not None and not (EA_BOUNDS[0] <= _num(v) <= EA_BOUNDS[1])))
    return {"n": int(df[ea].notna().sum()), "invalid": int(bad.sum()),
            "sample_ids": df.loc[bad].index.tolist()[:50],
            "message": f"Ea outside [{EA_BOUNDS[0]}, {EA_BOUNDS[1]}] eV"}


def audit_temperature(df: pd.DataFrame) -> dict[str, Any]:
    tr = _col(df, "ion_transport.temperature_range_measured", "temperature_range_measured")
    if tr is None:
        return {"n": 0, "invalid": 0, "sample_ids": [],
                "message": "no temperature column"}

    def _min_k(v):
        if isinstance(v, dict):
            for k in ("min_K", "min", "low"):
                if k in v:
                    return _num(v[k])
        return None
    mins = df[tr].apply(_min_k)
    bad = mins.notna() & (mins < 0)
    return {"n": int(mins.notna().sum()), "invalid": int(bad.sum()),
            "sample_ids": df.loc[bad].index.tolist()[:50],
            "message": "temperature < 0 K"}


def audit_unit_string_leak(df: pd.DataFrame) -> dict[str, Any]:
    """Detect canonical numeric columns that still carry unit strings
    (e.g. '20 mS/cm' stored where the canonical float belongs)."""
    suspects = {
        "ion_transport.sigma_RT": ("S/cm", "mS", "µS", "uS", "nS"),
        "ion_transport.activation_energy_Ea": ("eV", "meV", "kJ", "kcal"),
    }
    issues = []
    for col, tokens in suspects.items():
        if col not in df.columns:
            continue
        s = df[col]
        for i in s.index:
            v = s.loc[i]
            if isinstance(v, str) and any(t in v for t in tokens):
                issues.append({"record": i, "column": col, "value": v})
    return {"n": len(issues), "issues": issues[:50],
            "message": "canonical numeric columns carrying unit strings"}


def audit_units(df: pd.DataFrame) -> dict[str, Any]:
    """Run all unit audits; returns coverage + validity summary."""
    checks = {
        "sigma": audit_sigma(df),
        "activation_energy": audit_ea(df),
        "temperature": audit_temperature(df),
        "unit_string_leak": audit_unit_string_leak(df),
    }
    total_invalid = sum(c["invalid"] for c in checks.values()
                        if "invalid" in c) + checks["unit_string_leak"]["n"]
    return {
        "scanned_records": int(len(df)),
        "total_invalid": int(total_invalid),
        "checks": checks,
        "passed": total_invalid == 0,
    }
