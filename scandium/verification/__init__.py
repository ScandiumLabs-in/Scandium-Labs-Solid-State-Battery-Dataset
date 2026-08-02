from __future__ import annotations

from typing import Any

from .units import (
    normalize_conductivity,
    normalize_activation_energy,
    validate_conductivity_value,
    validate_activation_energy,
)
from .physics import (
    check_arrhenius_consistency,
    check_range_plausibility,
)
from .consistency import (
    detect_cross_source_conflicts,
    validate_formula,
    full_verification_report,
)


def verify_conductivity_entry(
    entry: dict[str, Any],
    family: str | None = None,
    temperature_celsius: float | None = None,
) -> dict[str, Any]:
    issues: list[str] = []
    warnings: list[str] = []

    value = entry.get("value")
    if value is not None:
        unit = entry.get("unit", "S/cm")
        normalized = normalize_conductivity(value, unit)
        entry["value_normalized"] = normalized
        issues.extend(validate_conductivity_value(normalized))
        issues.extend(
            check_range_plausibility(normalized, "conductivity", family)
        )
        ea = entry.get("activation_energy")
        if ea is not None and temperature_celsius is not None:
            issues.extend(
                check_arrhenius_consistency(normalized, ea, temperature_celsius)
            )

    result = {
        "entry": entry,
        "passed": len(issues) == 0,
        "issues": issues,
        "warnings": warnings,
    }
    return result


def verify_activation_energy_entry(
    entry: dict[str, Any],
    family: str | None = None,
) -> dict[str, Any]:
    issues: list[str] = []
    warnings: list[str] = []

    value = entry.get("value")
    if value is not None:
        unit = entry.get("unit", "eV")
        normalized = normalize_activation_energy(value, unit)
        entry["value_normalized"] = normalized
        issues.extend(validate_activation_energy(normalized))
        issues.extend(
            check_range_plausibility(normalized, "activation_energy", family)
        )

    return {
        "entry": entry,
        "passed": len(issues) == 0,
        "issues": issues,
        "warnings": warnings,
    }


__all__ = [
    "verify_conductivity_entry",
    "verify_activation_energy_entry",
    "normalize_conductivity",
    "normalize_activation_energy",
    "detect_cross_source_conflicts",
    "validate_formula",
    "full_verification_report",
]
