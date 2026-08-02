from __future__ import annotations

import re
from typing import Any

ELEMENT_ORDER = [
    "Li", "Na", "K", "Rb", "Cs",
    "Mg", "Ca", "Sr", "Ba",
    "Sc", "Y", "La", "Ce", "Pr", "Nd", "Sm", "Eu", "Gd", "Tb", "Dy", "Ho", "Er", "Tm", "Yb", "Lu",
    "Ti", "Zr", "Hf",
    "Nb", "Ta",
    "Cr", "Mo", "W",
    "Mn", "Fe", "Co", "Ni", "Cu", "Zn",
    "Al", "Ga", "In", "Ge", "Sn", "Pb",
    "P", "As", "Sb", "Bi",
    "O", "S", "Se", "Te",
    "F", "Cl", "Br", "I",
    "C", "N", "B", "Si",
]

FAMILY_PATTERNS: list[tuple[str, re.Pattern]] = [
    ("argyrodite", re.compile(r"Li6PS5", re.IGNORECASE)),
    ("lgps", re.compile(r"Li\d+GeP", re.IGNORECASE)),
    ("garnet", re.compile(r"Li[^A-Z]*La[^A-Z]*Zr", re.IGNORECASE)),
    ("llzo", re.compile(r"Li7La3Zr2O12", re.IGNORECASE)),
    ("llto", re.compile(r"Li[^A-Z]*La[^A-Z]*TiO", re.IGNORECASE)),
    ("perovskite", re.compile(r"Li[^A-Z]*La[^A-Z]*TiO", re.IGNORECASE)),
    ("nasicon", re.compile(r"(?:Li|Na)[^A-Z]*(?:Zr|Ti|Ge)[^Z]*P[^Z]*O", re.IGNORECASE)),
    ("lagp", re.compile(r"Li[^A-Z]*Al[^A-Z]*Ge[^Z]*P", re.IGNORECASE)),
    ("latp", re.compile(r"Li[^A-Z]*Al[^A-Z]*Ti[^Z]*P", re.IGNORECASE)),
    ("halide", re.compile(r"Li[^A-Z]*(?:Y|Sc|In|Er)[A-Za-z]*Cl", re.IGNORECASE)),
    ("sulfide", re.compile(r"Li[^A-Z]*[PS]", re.IGNORECASE)),
    ("polymer", re.compile(r"PEO|polyethylene|polypropylene|PVDF|PVDF-HFP|PMMA|PAN", re.IGNORECASE)),
    ("oxide", re.compile(r"Li[^A-Z]*O", re.IGNORECASE)),
]


def parse_formula(formula: str) -> dict[str, float]:
    cleaned = re.sub(r"[(){}]", "", formula)
    parts = cleaned.split()
    elements: dict[str, float] = {}
    pattern = re.compile(r"([A-Z][a-z]?)([\d.]*x?[\d]*)")
    for part in parts:
        for elem, count in pattern.findall(part):
            if not elem:
                continue
            cnt_str = count.replace("x", "")
            cnt = float(cnt_str) if cnt_str else 1.0
            elements[elem] = elements.get(elem, 0.0) + cnt
    return elements


def sort_formula(formula: str) -> str:
    elements = parse_formula(formula)
    ordered: list[str] = []
    for elem in ELEMENT_ORDER:
        if elem in elements:
            cnt = elements[elem]
            if cnt == int(cnt):
                ordered.append(f"{elem}{int(cnt)}" if cnt > 1 else elem)
            else:
                ordered.append(f"{elem}{cnt}")
    for elem in sorted(elements.keys()):
        if elem not in ELEMENT_ORDER:
            cnt = elements[elem]
            ordered.append(f"{elem}{int(cnt) if cnt == int(cnt) else cnt}")
    return "".join(ordered)


def classify_family(formula: str) -> str:
    for family, pattern in FAMILY_PATTERNS:
        if pattern.search(formula):
            return family
    return "unknown"


def canonical_key(formula: str) -> str:
    parts = re.findall(r"([A-Z][a-z]?)([\d.]*)", re.sub(r"[^A-Za-z0-9.]", "", formula))
    key_parts = []
    for elem, cnt in parts:
        cnt_val = float(cnt) if cnt else 1.0
        key_parts.append(f"{elem}{cnt_val:.4f}")
    return "".join(sorted(key_parts))


def resolve_material(formula: str, name: str = "") -> dict[str, Any]:
    result: dict[str, Any] = {
        "input_formula": formula,
        "canonical_formula": "",
        "family": "unknown",
        "elements": {},
        "name": name,
        "material_id": "",
        "mp_id": None,
    }

    elements = parse_formula(formula)
    result["elements"] = elements
    result["canonical_formula"] = sort_formula(formula)
    result["family"] = classify_family(formula)
    result["canonical_key"] = canonical_key(formula)

    name_lower = name.lower()
    if not result["family"] or result["family"] == "unknown":
        for family, pattern in FAMILY_PATTERNS:
            if family in name_lower or pattern.search(name_lower):
                result["family"] = family
                break

    return result
