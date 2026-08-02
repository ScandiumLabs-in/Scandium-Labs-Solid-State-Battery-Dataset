from __future__ import annotations

import re
from typing import Any

UNIT_PATTERNS = {
    "S/cm": re.compile(r"S\s*/\s*cm", re.IGNORECASE),
    "mS/cm": re.compile(r"mS\s*/\s*cm", re.IGNORECASE),
    "S/m": re.compile(r"S\s*/\s*m", re.IGNORECASE),
    "eV": re.compile(r"\beV\b"),
    "meV": re.compile(r"\bmeV\b"),
    "kJ/mol": re.compile(r"kJ\s*/\s*mol", re.IGNORECASE),
    "K": re.compile(r"\bK\b"),
    "°C": re.compile(r"°C|\bC\b"),
    "MPa": re.compile(r"\bMPa\b"),
}


def normalize_conductivity(value: float, unit: str | None) -> float:
    if not unit:
        return value
    unit_lower = unit.lower().replace(" ", "").replace("−", "-").replace("–", "-")
    if "ms/cm" in unit_lower or "ms·cm" in unit_lower:
        return value * 0.001
    if "s/m" in unit_lower:
        return value * 0.01
    return value


def normalize_activation_energy(value: float, unit: str | None) -> float:
    if not unit:
        return value
    unit_lower = unit.lower().replace(" ", "")
    if "mev" in unit_lower:
        return value * 0.001
    if "kj/mol" in unit_lower:
        return value * 0.01036
    return value


def validate_conductivity_value(value: float) -> list[str]:
    issues: list[str] = []
    if value <= 0:
        issues.append(f"Negative or zero conductivity: {value}")
    if value > 100:
        issues.append(f"Implausibly high conductivity (>100 S/cm): {value}")
    if value < 1e-15:
        issues.append(f"Implausibly low conductivity (<1e-15 S/cm): {value}")
    return issues


def validate_activation_energy(value: float) -> list[str]:
    issues: list[str] = []
    if value <= 0:
        issues.append(f"Negative or zero activation energy: {value}")
    if value > 5:
        issues.append(f"Implausibly high Ea (>5 eV): {value}")
    if value < 0.01:
        issues.append(f"Implausibly low Ea (<0.01 eV): {value}")
    return issues
