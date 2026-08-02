from __future__ import annotations

import math
from typing import Any

KB_EV = 8.617333262e-5


def check_arrhenius_consistency(
    sigma_S_per_cm: float,
    ea_eV: float,
    temperature_celsius: float | None,
) -> list[str]:
    issues: list[str] = []
    if temperature_celsius is None:
        return issues

    T = temperature_celsius + 273.15
    if T <= 0:
        return issues

    expected_prefactor = sigma_S_per_cm / math.exp(-ea_eV / (KB_EV * T))

    if expected_prefactor < 0:
        issues.append(
            f"Arrhenius inconsistency: negative prefactor ({expected_prefactor:.2e}) "
            f"from σ={sigma_S_per_cm:.2e}, Ea={ea_eV:.3f}, T={T:.1f}K"
        )
    elif expected_prefactor > 1e10:
        issues.append(
            f"Unphysical prefactor ({expected_prefactor:.2e} S/cm): "
            f"σ={sigma_S_per_cm:.2e}, Ea={ea_eV:.3f}, T={T:.1f}K "
            f"(suggests units error — Ea may be in meV, or σ in mS/cm)"
        )
    elif expected_prefactor < 1e-10:
        issues.append(
            f"Suspiciously low prefactor ({expected_prefactor:.2e} S/cm): "
            f"σ={sigma_S_per_cm:.2e}, Ea={ea_eV:.3f}, T={T:.1f}K"
        )

    return issues


def check_cross_source_consistency(
    conductivity_entry: dict[str, Any],
    conductivity_type: str | None,
) -> list[str]:
    issues: list[str] = []
    if not conductivity_type:
        return issues
    if conductivity_type == "total" and conductivity_entry.get("conductivity_type") not in (
        None,
        "total",
    ):
        issues.append(f"Conductivity type mismatch: expected total, got {conductivity_entry.get('conductivity_type')}")
    return issues


def check_range_plausibility(
    value: float,
    property_type: str,
    family: str | None = None,
) -> list[str]:
    issues: list[str] = []
    ranges = {
        "conductivity": {
            "sulfide": (1e-8, 1e-1),
            "oxide": (1e-10, 1e-2),
            "polymer": (1e-10, 1e-3),
            "default": (1e-15, 1e2),
        },
        "activation_energy": {
            "sulfide": (0.1, 0.8),
            "oxide": (0.2, 1.5),
            "polymer": (0.3, 2.0),
            "default": (0.01, 5.0),
        },
    }
    if property_type not in ranges:
        return issues
    family_ranges = ranges[property_type]
    lo, hi = family_ranges.get(family or "", family_ranges["default"])
    if value < lo or value > hi:
        issues.append(
            f"{property_type} {value:.2e} outside typical range for "
            f"{family or 'unknown'} family [{lo:.2e}, {hi:.2e}]"
        )
    return issues
