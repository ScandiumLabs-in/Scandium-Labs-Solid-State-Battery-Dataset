from __future__ import annotations

import re
from typing import Any

from .base import call_llm, parse_json_response
from ..verification.units import normalize_conductivity, validate_conductivity_value
from ..verification.physics import check_range_plausibility

PROMPT_VERSION = "conductivity_v3"
LLM_MODEL = "llama3.2:3b"

SYSTEM_PROMPT = """You extract ionic conductivity data from solid-state battery papers.

For every conductivity value, classify the source:
- "primary" — the authors' own measurement of their synthesized material (DEFAULT)
- "literature" — a value cited from another paper (ONLY if explicitly attributed)
- "comparison" — comparing the authors' material to a known standard
- "background" — general knowledge

Return a JSON array of objects with these fields:
- "value": float — conductivity VALUE only (e.g., 1.2, 0.005, 3.5e-4)
- "unit": "S/cm" or "mS/cm" — leave as reported
- "temperature_celsius": float or null
- "conductivity_type": "total" | "bulk" | "grain_boundary" | null
- "measurement_method": "EIS" | "DC" | null
- "pressure_MPa": float or null
- "is_primary_measurement": bool — DEFAULT true for the primary material's values
- "source_type": "primary" | "literature" | "comparison" | "background" | "unknown"
- "material_formula": string or null — the specific material for this measurement
- "source": string — what table/figure/section this came from
- "notes": string

Rules:
- Default to "primary" unless the text explicitly says "reported by" or references another paper
- Extract specific single values, not ranges
- Include temperature when available
- Always include the 'unit' field with value — never omit it
- Return [] if no valid conductivity values found"""


def validate_and_score(entry: dict[str, Any], primary_material: str = "") -> dict[str, Any]:
    score = 0.5
    issues: list[str] = []
    factors: list[dict[str, Any]] = [
        {"factor": "base", "delta": 0.5, "reason": "neutral starting point"},
    ]

    raw = entry.get("value")
    unit = entry.get("unit", "S/cm")
    if raw is not None:
        normalized = normalize_conductivity(raw, unit)
        entry["value_normalized"] = normalized
        entry["unit_normalized"] = "S/cm"
        ve_issues = validate_conductivity_value(normalized)
        issues.extend(ve_issues)
        if not ve_issues:
            score += 0.2
            factors.append({"factor": "value_in_range", "delta": 0.2, "reason": "conductivity in physically plausible range"})
        range_issues = check_range_plausibility(normalized, "conductivity")
        if range_issues:
            issues.extend(range_issues)
            score -= 0.1
            factors.append({"factor": "range_plausibility", "delta": -0.1, "reason": "; ".join(range_issues)})
        if entry.get("temperature_celsius") is not None:
            score += 0.15
            factors.append({"factor": "temperature_present", "delta": 0.15, "reason": "measurement temperature reported"})
        if entry.get("conductivity_type") in ("total", "bulk", "grain_boundary"):
            score += 0.1
            factors.append({"factor": "conductivity_type", "delta": 0.1, "reason": f"conductivity type = {entry.get('conductivity_type')}"})
        if entry.get("is_primary_measurement"):
            score += 0.15
            factors.append({"factor": "primary_measurement", "delta": 0.15, "reason": "marked as paper's own measurement"})
        source_type = entry.get("source_type", "unknown")
        if source_type == "primary":
            score += 0.2
            entry["is_primary_measurement"] = True
            factors.append({"factor": "source_primary", "delta": 0.2, "reason": "LLM classified as primary measurement"})
        elif source_type == "literature":
            entry["is_primary_measurement"] = False
            score -= 0.3
            factors.append({"factor": "source_literature", "delta": -0.3, "reason": "LLM classified as literature citation"})
        material = entry.get("material_formula", "")
        if primary_material and material:
            mat_norm = re.sub(r"[_₀₁₂₃₄₅₆₇₈₉]", "", material.lower())
            prim_norm = re.sub(r"[_₀₁₂₃₄₅₆₇₈₉]", "", primary_material.lower())
            if mat_norm != prim_norm:
                score -= 0.2
                entry["is_primary_measurement"] = False
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


def extract_conductivity(
    context: str,
    api_key: str = "",
    model: str = "llama3.2:3b",
    base_url: str = "http://localhost:11434/v1",
    primary_material: str = "",
    is_review: bool = False,
) -> list[dict[str, Any]]:
    if is_review:
        user = (
            f"Extract ionic conductivity values from this review paper.\n"
            f"ALL values are literature citations. Set source_type=\"literature\" and is_primary_measurement=false for every entry.\n\n"
            f"{context}\n\nReturn only the JSON array."
        )
    elif primary_material:
        user = (
            f"Extract ionic conductivity values from this paper content.\n"
            f"The primary material is: {primary_material}\n"
            f"FOCUS on measurements of {primary_material}. "
            f"Classify literature citations correctly.\n\n"
            f"{context}\n\nReturn only the JSON array."
        )
    else:
        user = f"Extract ionic conductivity values from this paper content:\n\n{context}\n\nReturn only the JSON array."

    content = call_llm(SYSTEM_PROMPT, user, api_key, model, base_url)
    raw = parse_json_response(content) or []
    validated = [validate_and_score(e, primary_material) for e in raw]
    validated.sort(key=lambda x: -x.get("_confidence", 0))

    primary_only = [e for e in validated if e.get("source_type") == "primary" or e.get("is_primary_measurement")]
    other = [e for e in validated if e.get("source_type") != "primary" and not e.get("is_primary_measurement")]

    return primary_only + other
