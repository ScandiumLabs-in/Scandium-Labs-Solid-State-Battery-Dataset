from __future__ import annotations

import math
from typing import Any

import re

FORMULA_PATTERN = re.compile(
    r"^(?:[A-Z][a-z]?\d*)+$"
)


def _source_group(source: str) -> str:
    if not source:
        return "unknown"
    if "table" in source.lower():
        return "table"
    if "figure" in source.lower() or "fig" in source.lower():
        return "figure"
    return "text"


def detect_cross_source_conflicts(extractions: list[dict[str, Any]]) -> list[dict[str, Any]]:
    conflicts: list[dict[str, Any]] = []
    grouped: dict[str, list[dict[str, Any]]] = {}
    for ex in extractions:
        prop = ex.get("_property_type", "unknown")
        comp = ex.get("composition", ex.get("_primary_composition", "unknown"))
        is_primary = ex.get("is_primary_measurement", True)
        if not is_primary:
            continue
        key = f"{prop}|{comp}"
        grouped.setdefault(key, []).append(ex)

    for key, group in grouped.items():
        prop, comp = key.split("|", 1)
        if len(group) < 2:
            continue

        by_source_type: dict[str, list[tuple[float, str, float]]] = {}
        for ex in group:
            v = ex.get("value_normalized") or ex.get("value")
            if v is None:
                continue
            src = ex.get("source", "unknown")
            stype = _source_group(src)
            by_source_type.setdefault(stype, []).append(
                (v, src, ex.get("_confidence", 0))
            )

        source_types = list(by_source_type.keys())
        for i in range(len(source_types)):
            for j in range(i + 1, len(source_types)):
                st1, st2 = source_types[i], source_types[j]
                vals1 = by_source_type[st1]
                vals2 = by_source_type[st2]
                for v1, s1, c1 in vals1:
                    for v2, s2, c2 in vals2:
                        if v1 == 0 or v2 == 0:
                            continue
                        ratio = max(v1, v2) / min(v1, v2)
                        if ratio > 1.5:
                            conflicts.append({
                                "property": prop,
                                "composition": comp,
                                "value_1": v1,
                                "source_1": s1,
                                "conf_1": c1,
                                "value_2": v2,
                                "source_2": s2,
                                "conf_2": c2,
                                "ratio": round(ratio, 2),
                                "severity": "high" if ratio > 5 else "medium",
                                "message": (
                                    f"{prop} conflict for {comp}: "
                                    f"{v1:.2e} ({s1}, {st1}) vs "
                                    f"{v2:.2e} ({s2}, {st2}) — "
                                    f"{ratio:.1f}x difference"
                                ),
                            })

    return conflicts


def validate_formula(formula: str) -> list[str]:
    issues: list[str] = []
    if not formula:
        issues.append("Empty formula")
        return issues
    cleaned = formula.replace("(", "").replace(")", "")
    cleaned = re.sub(r"x\d*", "", cleaned)
    cleaned = cleaned.replace(",", "").replace(" ", "")
    if len(cleaned) < 2:
        issues.append(f"Formula too short: {formula}")
    elements = re.findall(r"[A-Z][a-z]?", cleaned)
    if not elements:
        issues.append(f"No recognizable elements in: {formula}")
    valid_elements = {
        "Li", "Na", "K", "Mg", "Ca", "Sr", "Ba",
        "La", "Zr", "Ti", "Ta", "Nb", "Hf", "Sc", "Y",
        "Al", "Ga", "In", "Ge", "Sn", "Pb",
        "P", "As", "Sb", "Bi",
        "S", "Se", "Te",
        "O", "F", "Cl", "Br", "I",
        "C", "N", "B", "Si",
        "Fe", "Co", "Ni", "Cu", "Zn", "Mn",
        "Ru", "Rh", "Pd", "Ag", "Cd",
        "Pt", "Au", "Hg",
    }
    for elem in elements:
        if elem not in valid_elements:
            issues.append(f"Unrecognized element: {elem} in {formula}")
    return issues


def check_composition_charge_balance(formula: str) -> list[str]:
    issues: list[str] = []
    oxidation_states = {
        "Li": 1, "Na": 1, "K": 1,
        "Mg": 2, "Ca": 2, "Sr": 2, "Ba": 2,
        "La": 3,
        "Zr": 4, "Ti": 4, "Ta": 5, "Nb": 5,
        "Al": 3, "Ga": 3, "In": 3,
        "Ge": 4, "Sn": 4,
        "P": 5, "As": 5, "Sb": 5,
        "S": -2, "Se": -2, "Te": -2,
        "O": -2, "F": -1, "Cl": -1, "Br": -1, "I": -1,
        "N": -3,
    }
    try:
        elements = re.findall(r"([A-Z][a-z]?)(\d*\.?\d*)", formula)
        charge = 0.0
        for elem, count_str in elements:
            if elem in oxidation_states:
                count = float(count_str) if count_str else 1.0
                charge += oxidation_states[elem] * count
        if abs(charge) > 1.0:
            issues.append(f"Charge imbalance in {formula}: net charge = {charge:.1f}")
    except Exception:
        pass
    return issues


def full_verification_report(
    compositions: list[dict[str, Any]],
    conductivities: list[dict[str, Any]],
    activation_energies: list[dict[str, Any]],
    primary_composition: str = "",
) -> dict[str, Any]:
    report: dict[str, Any] = {
        "n_compositions": len(compositions),
        "n_conductivities": len(conductivities),
        "n_activation_energies": len(activation_energies),
        "composition_issues": [],
        "cross_source_conflicts": [],
        "arrhenius_flags": [],
        "summary": {},
    }

    for c in compositions:
        formula = c.get("formula", "")
        report["composition_issues"].extend(validate_formula(formula))
        report["composition_issues"].extend(check_composition_charge_balance(formula))

    all_extractions: list[dict[str, Any]] = []
    for c in conductivities:
        c["_property_type"] = "conductivity"
        all_extractions.append(c)
    for e in activation_energies:
        e["_property_type"] = "activation_energy"
        all_extractions.append(e)

    report["cross_source_conflicts"] = detect_cross_source_conflicts(all_extractions)

    n_high_conf = sum(1 for c in conductivities if c.get("_confidence", 0) >= 0.6)
    n_flagged = sum(1 for c in conductivities if c.get("_confidence", 0) < 0.6)
    n_ea_high = sum(1 for e in activation_energies if e.get("_confidence", 0) >= 0.6)
    n_ea_flagged = sum(1 for e in activation_energies if e.get("_confidence", 0) < 0.6)

    report["summary"] = {
        "primary_composition": primary_composition,
        "high_confidence_conductivities": n_high_conf,
        "flagged_conductivities": n_flagged,
        "high_confidence_activation_energies": n_ea_high,
        "flagged_activation_energies": n_ea_flagged,
        "total_conflicts": len(report["cross_source_conflicts"]),
        "composition_issues": len(report["composition_issues"]),
    }

    return report
