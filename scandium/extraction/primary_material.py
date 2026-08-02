from __future__ import annotations

import re
from typing import Any

from .base import call_llm, parse_json_response

PROMPT_VERSION = "primary_material_v4"
LLM_MODEL = "llama3.2:3b"

SYSTEM_PROMPT = """You are a primary material detector for solid-state battery papers.

Your task is to identify the MAIN electrolyte material that the authors synthesized and studied in this paper.

Rules:
- Return exactly ONE primary material — the paper's own synthesized/studied electrolyte
- Ignore precursors, reagents, or commercially purchased chemicals
- Ignore counter-electrodes (Li metal, In, Li-In, Au, etc.)
- Ignore standard electrode materials (LCO, NMC, LFP, etc.)
- If no clear electrolyte material is studied, return {"primary_material": null}

Return a JSON object with:
- "primary_material": string or null — chemical formula of the main studied electrolyte (e.g., "Li6PS5Cl", "Li7La3Zr2O12", "Li2OHCl", "PEO-LiTFSI")
- "name": string or null — common name if any (e.g., "argyrodite", "LLZO", "LATP", "NASICON")
- "aliases": list of strings — alternative formulas or names used in the paper
- "confidence": float between 0 and 1
- "evidence": string — exact sentence(s) that identify the primary material
- "synthesis_method": string or null — e.g., "solid-state", "ball milling", "solution casting"
"""


def extract_primary_material(
    experimental_context: str,
    api_key: str = "",
    model: str = "llama3.2:3b",
    base_url: str = "http://localhost:11434/v1",
) -> dict[str, Any]:
    user = f"Identify the primary solid electrolyte material studied in this paper:\n\n{experimental_context}\n\nReturn only the JSON object."
    content = call_llm(SYSTEM_PROMPT, user, api_key, model, base_url)
    raw = parse_json_response(content)
    if isinstance(raw, dict):
        result = raw
    elif isinstance(raw, list) and raw:
        result = raw[0]
    else:
        return {"primary_material": None, "confidence": 0, "evidence": ""}

    material = result.get("primary_material") or ""
    evidence = result.get("evidence") or ""
    if material and evidence:
        material_clean = re.sub(r"[_₀₁₂₃₄₅₆₇₈₉\-‒–—]", "", material.lower())
        evidence_lower = re.sub(r"[_₀₁₂₃₄₅₆₇₈₉\-‒–—]", "", evidence.lower())
        material_words = re.findall(r"[a-z]+\d*\.?\d*", material_clean)
        matches = sum(1 for w in material_words if w and w in evidence_lower)
        if matches == 0:
            result["confidence"] = max(0.1, result.get("confidence", 0) - 0.5)
            result["_issues"] = ["Material not found in evidence text"]
    # Polymer electrolyte heuristic: if evidence mentions PEO and only salt is detected,
    # promote to PEO-<salt> composite
    if material and evidence:
        common_salts = ["litfsi", "liclo4", "lipf6", "libf4", "lifsi", "lifap"]
        if material.lower().strip() in common_salts:
            evidence_lower = evidence.lower()
            if "peo" in evidence_lower or "polymer" in evidence_lower:
                composite = f"PEO-{material}"
                result["primary_material"] = composite
                result["name"] = f"PEO-{material} polymer electrolyte"
                result["_issues"] = result.get("_issues", [])
                result["_issues"].append(f"Upgraded from {material} to {composite} (PEO detected in evidence)")
    return result


EXPERIMENTAL_SECTION_NAMES = {
    "experimental", "methods", "materials and methods", "methodology",
    "synthesis", "sample preparation", "material synthesis",
    "preparation", "fabrication", "synthesis of",
    "characterization", "electrochemical measurements",
    "experimental section", "experimental methods",
    "experimental procedures",
}


def extract_experimental_text(
    sections: list[Any],
    paragraphs: list[dict[str, Any]],
    max_chars: int = 6000,
) -> str:
    section_map: dict[str, list[str]] = {}
    for p in paragraphs:
        sec = p.get("section", "Unknown")
        section_map.setdefault(sec, []).append(p["text"])

    experimental_paras: list[str] = []
    for sec_name, texts in section_map.items():
        sec_lower = sec_name.lower().strip()
        for known in EXPERIMENTAL_SECTION_NAMES:
            if known in sec_lower:
                experimental_paras.extend(texts)
                break

    if not experimental_paras:
        for p in paragraphs:
            text_lower = p["text"].lower()
            keywords = ["synthesized", "prepared", "fabricated", "pellet", "ball mill",
                        "solid state reaction", "we synthesized", "was prepared",
                        "sintered", "calcined", "pressed", "annealed"]
            if any(kw in text_lower for kw in keywords):
                experimental_paras.append(p["text"])

    text = "\n\n".join(experimental_paras)
    if len(text) > max_chars:
        text = text[:max_chars] + "\n...[truncated]"
    return text


def classify_material_role(
    formula: str,
    primary_material: str,
) -> str:
    if not formula or not primary_material:
        return "unknown"

    formula_norm = re.sub(r"[_₀₁₂₃₄₅₆₇₈₉]", "", formula.lower())
    primary_norm = re.sub(r"[_₀₁₂₃₄₅₆₇₈₉]", "", primary_material.lower())

    if formula_norm == primary_norm:
        return "primary"

    primary_elements = set(re.findall(r"[a-z]+", primary_norm))
    formula_elements = set(re.findall(r"[a-z]+", formula_norm))
    overlap = primary_elements & formula_elements
    if overlap and len(overlap) >= max(1, min(len(primary_elements), len(formula_elements)) - 1):
        return "primary_variant"

    return "other"
