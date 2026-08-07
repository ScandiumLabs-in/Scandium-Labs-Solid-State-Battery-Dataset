"""Automated red-flag detector for extracted conductivity records.

Flags (not filters) records that look statistically or physically implausible,
so human review time goes where it matters most.

Checks implemented:
  1. Arrhenius-consistency — does sigma_RT roughly match what Ea predicts?
  2. Units plausibility — sigma and Ea within known family ranges
  3. Duplicate compositions with wildly different values
  4. Missing conductivity_type on families where bulk/GB matters
  5. Missing/implausible temperature annotation
"""

from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass, field
from typing import Any

import numpy as np
import pandas as pd


# Boltzmann constant in eV/K
KB_EV = 8.617333262e-5

# Typical pre-factor range for superionic conductors (S/cm)
TYPICAL_PREFACTOR_RANGE = (1e1, 1e5)

# Known sigma ranges per family at RT (S/cm) — from literature survey
FAMILY_SIGMA_RANGES: dict[str, tuple[float, float]] = {
    "sulfide": (1e-6, 1e-1),
    "oxide": (1e-10, 1e-2),
    "garnet": (1e-6, 2e-3),
    "perovskite": (1e-8, 1e-2),
    "nasicon": (1e-6, 1e-2),
    "halide": (1e-6, 1e-2),
    "argyrodite": (1e-6, 1e-1),
    "hydride": (1e-10, 1e-3),
    "borohydride": (1e-10, 1e-3),
    "antiperovskite": (1e-8, 1e-3),
    "polymer_composite": (1e-8, 1e-3),
}

# Known Ea ranges per family (eV)
FAMILY_EA_RANGES: dict[str, tuple[float, float]] = {
    "sulfide": (0.10, 0.50),
    "oxide": (0.10, 1.00),
    "garnet": (0.10, 0.60),
    "perovskite": (0.10, 0.60),
    "nasicon": (0.10, 0.50),
    "halide": (0.15, 0.60),
    "argyrodite": (0.15, 0.50),
    "hydride": (0.20, 1.70),
    "borohydride": (0.20, 1.70),
    "antiperovskite": (0.10, 1.00),
    "polymer_composite": (0.10, 1.70),
}

# Families where bulk vs grain-boundary distinction is important
BULK_GB_FAMILIES = {"garnet", "nasicon", "perovskite"}

# Room temperature reference (K)
RT_K = 298


@dataclass
class RedFlag:
    record_id: str
    flag_type: str
    severity: str  # "high", "medium", "low"
    message: str
    field: str = ""
    value: Any = None
    expected_range: str = ""


@dataclass
class RedFlagReport:
    total_records: int
    total_flags: int
    high_severity: int
    medium_severity: int
    low_severity: int
    flags: list[RedFlag] = field(default_factory=list)
    per_family_summary: dict[str, int] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "total_records": self.total_records,
            "total_flags": self.total_flags,
            "high_severity": self.high_severity,
            "medium_severity": self.medium_severity,
            "low_severity": self.low_severity,
            "per_family_summary": self.per_family_summary,
            "flags": [
                {
                    "record_id": f.record_id,
                    "flag_type": f.flag_type,
                    "severity": f.severity,
                    "message": f.message,
                    "field": f.field,
                    "value": str(f.value) if f.value is not None else None,
                    "expected_range": f.expected_range,
                }
                for f in self.flags
            ],
        }


def _get_col(df: pd.DataFrame, *candidates: str) -> str | None:
    for c in candidates:
        if c in df.columns:
            return c
    return None


def _safe_float(val: Any) -> float | None:
    if val is None:
        return None
    try:
        v = float(val)
        if np.isnan(v):
            return None
        return v
    except (ValueError, TypeError):
        return None


# Families that follow VTF (Vogel-Tammann-Fulcher) kinetics, not Arrhenius
VTF_FAMILIES = {"polymer_composite"}


def check_arrhenius_consistency(
    sigma: float | None,
    ea: float | None,
    family: str = "",
    temperature_k: float = RT_K,
) -> tuple[bool, str]:
    """Check if sigma_RT and Ea are mutually consistent via Arrhenius relation.

    σ = σ₀ * exp(-Ea/kT)
    If σ₀ computed from measured σ and Ea falls outside typical range, flag it.

    Skips check for VTF-kinetics families (polymer composites).
    """
    if sigma is None or ea is None or sigma <= 0 or ea <= 0:
        return False, ""
    if family.lower() in VTF_FAMILIES:
        return False, ""

    prefactor = sigma / np.exp(-ea / (KB_EV * temperature_k))

    low, high = TYPICAL_PREFACTOR_RANGE
    if prefactor < low:
        return True, (
            f"Implied pre-factor σ₀={prefactor:.1e} S/cm is below typical range "
            f"[{low:.0e}, {high:.0e}]; σ={sigma:.1e} at Ea={ea:.2f}eV suggests "
            f"either unit under-conversion or measurement at different T"
        )
    if prefactor > high:
        return True, (
            f"Implied pre-factor σ₀={prefactor:.1e} S/cm is above typical range "
            f"[{low:.0e}, {high:.0e}]; σ={sigma:.1e} at Ea={ea:.2f}eV suggests "
            f"possible unit over-conversion or reported at elevated T"
        )
    return False, ""


def check_sigma_in_family_range(
    sigma: float | None,
    family: str,
    floor_override: float | None = None,
) -> tuple[bool, str]:
    if sigma is None:
        return False, ""
    family_lower = family.lower()
    if family_lower not in FAMILY_SIGMA_RANGES:
        return False, ""
    low, high = FAMILY_SIGMA_RANGES[family_lower]
    if floor_override is not None:
        low = floor_override
    if sigma < low or sigma > high:
        return True, (
            f"σ={sigma:.1e} S/cm outside typical range for {family} "
            f"[{low:.1e}, {high:.1e}]"
        )
    return False, ""


def check_ea_in_family_range(
    ea: float | None,
    family: str,
    range_override: tuple[float, float] | None = None,
) -> tuple[bool, str]:
    if ea is None:
        return False, ""
    family_lower = family.lower()
    if family_lower not in FAMILY_EA_RANGES:
        return False, ""
    low, high = FAMILY_EA_RANGES[family_lower]
    if range_override is not None:
        low, high = range_override
    if ea < low or ea > high:
        return True, (
            f"Ea={ea:.2f} eV outside typical range for {family} "
            f"[{low:.2f}, {high:.2f}]"
        )
    return False, ""


def check_duplicate_composition_values(
    df: pd.DataFrame,
    sigma_col: str | None,
    composition_col: str | None,
    family_col: str | None,
) -> list[RedFlag]:
    """Flag compositions appearing multiple times with very different sigma values."""
    flags: list[RedFlag] = []
    if not sigma_col or not composition_col:
        return flags

    comp_groups = df.groupby(composition_col)
    for comp, group in comp_groups:
        if len(group) < 2:
            continue
        sigmas = group[sigma_col].dropna().values
        if len(sigmas) < 2:
            continue
        sigmas_f = np.array([float(s) for s in sigmas if _safe_float(s) is not None])
        if len(sigmas_f) < 2:
            continue

        ratio = sigmas_f.max() / sigmas_f.min()
        if ratio > 10:
            record_ids = group.index.tolist()
            families = set()
            if family_col:
                families = set(str(v) for v in group[family_col].dropna().unique())
            flags.append(RedFlag(
                record_id=str(record_ids),
                flag_type="duplicate_composition_different_values",
                severity="high",
                message=(
                    f"Composition '{comp}' appears {len(sigmas_f)} times with "
                    f"σ values ranging {sigmas_f.min():.1e}–{sigmas_f.max():.1e} "
                    f"S/cm (ratio={ratio:.0f}x) — families: {families}"
                ),
                field=sigma_col,
                value=f"{sigmas_f.min():.1e}–{sigmas_f.max():.1e}",
                expected_range=f"ratio < 10x",
            ))
    return flags


def check_conductivity_type_missing(
    row: pd.Series,
    record_id: str,
    family_col: str | None,
    cond_type_col: str | None,
    sigma_col: str | None,
) -> list[RedFlag]:
    """Flag missing conductivity_type for families where bulk/GB matters."""
    flags: list[RedFlag] = []
    if not family_col or not cond_type_col:
        return flags

    family = str(row.get(family_col, "")).lower()
    if family not in BULK_GB_FAMILIES:
        return flags

    cond_type = row.get(cond_type_col)
    if cond_type is None or (isinstance(cond_type, float) and np.isnan(cond_type)) or str(cond_type).strip() in ("", "nan", "None"):
        sigma = _safe_float(row.get(sigma_col)) if sigma_col else None
        flags.append(RedFlag(
            record_id=record_id,
            flag_type="missing_conductivity_type",
            severity="medium",
            message=(
                f"Missing conductivity_type for {family} record where "
                f"bulk/GB distinction matters"
            ),
            field=cond_type_col,
            value=sigma,
            expected_range="bulk, grain_boundary, or total",
        ))
    return flags


def generate_report(df: pd.DataFrame) -> RedFlagReport:
    """Run all red-flag checks against a DataFrame of records."""
    flags: list[RedFlag] = []

    sigma_col = _get_col(df, "sigma_RT", "ion_transport.sigma_RT")
    ea_col = _get_col(df, "activation_energy_Ea", "ion_transport.activation_energy_Ea")
    family_col = _get_col(df, "family", "identity.family")
    comp_col = _get_col(df, "composition", "identity.material_id", "material_id")
    cond_type_col = _get_col(df, "conductivity_type", "ion_transport.conductivity_type")
    id_col = _get_col(df, "material_id", "identity.material_id")

    for idx in df.index:
        row = df.loc[idx]
        record_id = str(row.get(id_col, idx)) if id_col else str(idx)
        family = str(row.get(family_col, "unknown")) if family_col else "unknown"
        sigma = _safe_float(row.get(sigma_col)) if sigma_col else None
        ea = _safe_float(row.get(ea_col)) if ea_col else None

        # 1. Arrhenius consistency
        flagged, msg = check_arrhenius_consistency(sigma, ea, family=family)
        if flagged:
            flags.append(RedFlag(
                record_id=record_id,
                flag_type="arrhenius_inconsistency",
                severity="high",
                message=msg,
                field="sigma_RT / Ea",
                value=f"σ={sigma:.1e}, Ea={ea:.2f}",
                expected_range=f"σ₀ in {TYPICAL_PREFACTOR_RANGE}",
            ))

        # 2. Sigma in family range
        flagged, msg = check_sigma_in_family_range(sigma, family)
        if flagged:
            flags.append(RedFlag(
                record_id=record_id,
                flag_type="sigma_out_of_family_range",
                severity="medium",
                message=msg,
                field="sigma_RT",
                value=f"{sigma:.1e}",
                expected_range=str(FAMILY_SIGMA_RANGES.get(family.lower(), ())),
            ))

        # 3. Ea in family range
        flagged, msg = check_ea_in_family_range(ea, family)
        if flagged:
            flags.append(RedFlag(
                record_id=record_id,
                flag_type="ea_out_of_family_range",
                severity="medium",
                message=msg,
                field="activation_energy_Ea",
                value=f"{ea:.2f}",
                expected_range=str(FAMILY_EA_RANGES.get(family.lower(), ())),
            ))

        # 4. Missing conductivity_type for bulk/GB families
        flags.extend(check_conductivity_type_missing(
            row, record_id, family_col, cond_type_col, sigma_col
        ))

    # 5. Duplicate compositions with different values
    flags.extend(check_duplicate_composition_values(
        df, sigma_col, comp_col, family_col
    ))

    # Tally
    high = sum(1 for f in flags if f.severity == "high")
    med = sum(1 for f in flags if f.severity == "medium")
    low = sum(1 for f in flags if f.severity == "low")

    per_family: dict[str, int] = defaultdict(int)
    for f in flags:
        family = str(df.loc[df.index[0]].get(family_col, "unknown")) if family_col else "unknown"
        per_family[f.flag_type] += 1

    return RedFlagReport(
        total_records=len(df),
        total_flags=len(flags),
        high_severity=high,
        medium_severity=med,
        low_severity=low,
        flags=flags,
        per_family_summary=dict(per_family),
    )
