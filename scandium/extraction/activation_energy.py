from __future__ import annotations

import re
from typing import Any

from .base import call_llm, parse_json_response
from ..verification.units import normalize_activation_energy, validate_activation_energy
from ..verification.physics import check_range_plausibility

PROMPT_VERSION = "activation_energy_v3"
LLM_MODEL = "llama3.2:3b"

SYSTEM_PROMPT = """You extract activation energy (Ea) values from solid-state battery papers.

For every Ea value, classify the source:
- "primary" — the authors' own measurement from their Arrhenius plot (DEFAULT)
- "literature" — a value cited from another paper (ONLY if explicitly attributed)
- "comparison" — comparing to a known standard
- "background" — general knowledge

Return a JSON array of objects with:
- "value": float — activation energy in eV
- "unit": "eV" or "meV"
- "temperature_range": string or null — e.g., "-20 to 75 °C"
- "method": "Arrhenius" | "VTF" | null
- "pressure_MPa": float or null
- "is_primary": bool — DEFAULT true for the primary material's values
- "source_type": "primary" | "literature" | "comparison" | "background" | "unknown"
- "material_formula": string or null — the specific material for this value
- "source": string or null
- "notes": string

Critical:
- Default to "primary" unless the text explicitly says "reported by" or references another paper
- Typical Ea for sulfides: 0.1–0.5 eV. For oxides: 0.2–1.0 eV.
- Values > 1.0 eV should be double-checked (might be meV not eV)
- Any Ea > 3.0 eV is almost certainly wrong (decimal point error)
- Always include the 'unit' field with value — never omit it
- Return [] if no valid Ea values found"""


def validate_and_score(entry: dict[str, Any], primary_material: str = "") -> dict[str, Any]:
    score = 0.5
    issues: list[str] = []
    factors: list[dict[str, Any]] = [
        {"factor": "base", "delta": 0.5, "reason": "neutral starting point"},
    ]
    raw = entry.get("value")
    unit = entry.get("unit", "eV")
    if raw is not None:
        normalized = normalize_activation_energy(raw, unit)
        entry["value_normalized"] = normalized
        entry["unit_normalized"] = "eV"
        ve_issues = validate_activation_energy(normalized)
        issues.extend(ve_issues)
        if normalized > 1.0:
            issues.append(f"High Ea ({normalized} eV) — possible meV vs eV confusion")
            score -= 0.3
            entry["_flag_units"] = True
            factors.append({"factor": "unit_confusion", "delta": -0.3, "reason": f"Ea > 1.0 eV, possible meV/eV confusion"})
        if normalized > 0.8 and entry.get("_family") in ("sulfide", "argyrodite"):
            issues.append(f"Ea ({normalized} eV) unusually high for {entry.get('_family')} family")
            score -= 0.15
            factors.append({"factor": "family_range", "delta": -0.15, "reason": f"Ea high for {entry.get('_family')} family"})
        elif normalized < 0.01:
            issues.append(f"Very low Ea ({normalized} eV)")
            score -= 0.1
            factors.append({"factor": "value_in_range", "delta": -0.1, "reason": "Ea < 0.01 eV implausibly low"})
        else:
            score += 0.2
            factors.append({"factor": "value_in_range", "delta": 0.2, "reason": "Ea in plausible physical range"})
        if entry.get("temperature_range"):
            score += 0.15
            factors.append({"factor": "temperature_present", "delta": 0.15, "reason": "temperature range reported"})
        if entry.get("method") == "Arrhenius":
            score += 0.1
            factors.append({"factor": "method_arrhenius", "delta": 0.1, "reason": "Arrhenius fit method reported"})
        if entry.get("is_primary"):
            score += 0.15
            factors.append({"factor": "primary_measurement", "delta": 0.15, "reason": "marked as paper's own measurement"})
        source_type = entry.get("source_type", "unknown")
        if source_type == "primary":
            score += 0.2
            entry["is_primary"] = True
            factors.append({"factor": "source_primary", "delta": 0.2, "reason": "LLM classified as primary measurement"})
        elif source_type == "literature":
            score -= 0.3
            entry["is_primary"] = False
            factors.append({"factor": "source_literature", "delta": -0.3, "reason": "LLM classified as literature citation"})
        material = entry.get("material_formula", "")
        if primary_material and material:
            mat_norm = re.sub(r"[_₀₁₂₃₄₅₆₇₈₉]", "", material.lower())
            prim_norm = re.sub(r"[_₀₁₂₃₄₅₆₇₈₉]", "", primary_material.lower())
            if mat_norm != prim_norm:
                score -= 0.2
                entry["is_primary"] = False
                issues.append(f"Material mismatch: {material} != {primary_material}")
                factors.append({"factor": "material_mismatch", "delta": -0.2, "reason": f"{material} != primary material {primary_material}"})
    else:
        issues.append("Missing value")
        factors.append({"factor": "missing_value", "delta": 0.0, "reason": "no numeric value extracted"})
    entry["_confidence"] = round(min(score, 1.0), 3)
    entry["_issues"] = issues
    entry["_valid"] = len(issues) == 0
    entry["_confidence_breakdown"] = factors
    return entry


def extract_activation_energy(
    context: str,
    api_key: str = "",
    model: str = "llama3.2:3b",
    base_url: str = "http://localhost:11434/v1",
    family: str = "",
    primary_material: str = "",
    is_review: bool = False,
) -> list[dict[str, Any]]:
    if is_review:
        hint = (
            " This is a review paper. ALL values are literature citations. "
            "Set source_type=\"literature\" and is_primary=false for every entry."
        )
    elif primary_material:
        hint = f" The primary material is: {primary_material}. Focus on Ea values for {primary_material}."
    else:
        hint = ""

    user = f"Extract activation energy values from this paper content.{hint}\n\n{context}\n\nReturn only the JSON array."
    content = call_llm(SYSTEM_PROMPT, user, api_key, model, base_url)
    raw = parse_json_response(content) or []
    for e in raw:
        e["_family"] = family
    validated = [validate_and_score(e, primary_material) for e in raw]
    validated.sort(key=lambda x: -x.get("_confidence", 0))

    primary_only = [e for e in validated if e.get("source_type") == "primary" or e.get("is_primary")]
    other = [e for e in validated if e.get("source_type") != "primary" and not e.get("is_primary")]

    return primary_only + other
