from __future__ import annotations

import re
from typing import Any

from .base import call_llm, parse_json_response

PROMPT_VERSION = "composition_v3"
LLM_MODEL = "llama3.2:3b"

SYSTEM_PROMPT = """You extract chemical compositions of solid-state electrolyte materials.
Focus only on the material(s) that the authors themselves synthesized and studied.

Return a JSON array of objects with:
- "formula": string — chemical formula (e.g., "Li6PS5Cl", "Li7La3Zr2O12")
- "name": string or null — common name (e.g., "argyrodite", "LLZO", "LGPS")
- "dopant": string or null — dopant if any (e.g., "Al", "Ta")
- "is_primary": bool — true if this is the main material studied by the authors
- "source_type": "primary" | "literature" | "comparison" | "background" | "unknown"
- "evidence": string — the sentence(s) that identify this composition
- "notes": string

Return [] if no valid compositions found."""


KNOWN_FAMILIES = {
    "argyrodite": r"Li6PS5",
    "LGPS": r"Li\d+GeP",
    "LLZO": r"Li7La3Zr2O12",
    "LLTO": r"Li\d*La\d*TiO",
    "LAGP": r"Li\d*Al\d*Ge\d*P\d*O",
    "LATP": r"Li\d*Al\d*Ti\d*P\d*O",
    "NASICON": r"Na",
    "perovskite": r"Li\d*La\d*TiO",
    "garnet": r"Li\d*La\d*Zr\d*O",
    "sulfide": r"Li\d*[PS]",
    "halide": r"Li\d*[YScIn]Cl",
    "polymer": r"PEO|polyethylene",
}


def classify_family(formula: str) -> str:
    for family, pattern in KNOWN_FAMILIES.items():
        if re.search(pattern, formula, re.IGNORECASE):
            return family
    return "unknown"


def validate_composition(entry: dict[str, Any]) -> dict[str, Any]:
    score = 0.5
    issues: list[str] = []
    formula = entry.get("formula", "")
    if formula:
        if len(formula) >= 3:
            score += 0.3
        family = classify_family(formula)
        entry["family"] = family
        if family != "unknown":
            score += 0.2
        if entry.get("is_primary"):
            score += 0.2
        source_type = entry.get("source_type", "unknown")
        if source_type == "primary":
            score += 0.2
        elif source_type == "literature":
            score -= 0.2
    else:
        issues.append("Missing formula")
    entry["_confidence"] = round(min(score, 1.0), 3)
    entry["_issues"] = issues
    entry["_valid"] = len(issues) == 0
    return entry


def extract_composition(
    context: str,
    api_key: str = "",
    model: str = "llama3.2:3b",
    base_url: str = "http://localhost:11434/v1",
    primary_hint: str = "",
) -> list[dict[str, Any]]:
    if primary_hint:
        user = f"Extract compositions from this paper. The primary material is believed to be related to: {primary_hint}\n\n{context}\n\nReturn only the JSON array."
    else:
        user = f"Extract the solid electrolyte compositions from this paper:\n\n{context}\n\nReturn only the JSON array."
    content = call_llm(SYSTEM_PROMPT, user, api_key, model, base_url)
    raw = parse_json_response(content) or []
    validated = [validate_composition(e) for e in raw]
    validated.sort(key=lambda x: -x.get("_confidence", 0))
    return validated
