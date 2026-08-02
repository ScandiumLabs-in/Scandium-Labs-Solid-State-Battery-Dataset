"""Phase 3.3 — Composition-to-structure linking.

Fuzzy-matches extracted compositions (from literature mining) against structures
already ingested in Phase 2. Where no match exists, flags the composition for
Phase 5 DFT computation.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Any

from pymatgen.core import Composition


@dataclass
class MatchResult:
    query_formula: str
    matched_formula: str | None = None
    matched_material_id: str | None = None
    match_score: float = 0.0
    is_exact: bool = False
    is_partial: bool = False
    substitution_variant: bool = False
    source_db: str = ""


@dataclass
class StructureIndex:
    """In-memory index of ingested structures for fast composition matching."""

    entries: list[dict[str, Any]] = field(default_factory=list)

    def add_entry(self, material_id: str, formula: str, source_db: str, elements: set[str] | None = None) -> None:
        try:
            comp = Composition(formula)
            formula_dict = comp.as_dict()
            redox_formula = comp.reduced_formula
        except Exception:
            formula_dict = {}
            redox_formula = formula
        self.entries.append({
            "material_id": material_id,
            "formula": formula,
            "reduced_formula": redox_formula,
            "formula_dict": formula_dict,
            "elements": elements or set(formula_dict.keys()),
            "source_db": source_db,
        })

    def add_from_material_record(self, material_id: str, composition: Any, source_db: str) -> None:
        elements: set[str] = set()
        formula = ""
        if isinstance(composition, dict):
            formula = " ".join(f"{k}{v}" for k, v in composition.items())
            elements = set(composition.keys())
        elif isinstance(composition, str):
            formula = composition
            try:
                elements = {el.symbol for el in Composition(composition).elements}
            except Exception:
                elements = set()
        elif hasattr(composition, "formula"):
            formula = composition.formula
            try:
                elements = {el.symbol for el in composition.elements}
            except Exception:
                elements = set()
        self.add_entry(material_id, formula, source_db, elements)


def _normalize_formula(f: str) -> str:
    """Normalize a formula string for comparison."""
    f = re.sub(r"[·∙•×\s]", "", f)
    f = f.replace("−", "-").replace("–", "-")
    f = re.sub(r"\{[^}]*\}", "", f)
    return f.strip()


def _parse_formula_dict(f: str) -> dict[str, float]:
    """Parse a formula string to an element-count dict, tolerant of edge cases."""
    try:
        comp = Composition(f)
        return comp.as_dict()
    except Exception:
        return {}


def _formula_similarity(d1: dict[str, float], d2: dict[str, float]) -> float:
    """Compute cosine similarity between two formula dicts (element proportions)."""
    all_els = set(d1.keys()) | set(d2.keys())
    v1: list[float] = []
    v2: list[float] = []
    for el in all_els:
        v1.append(d1.get(el, 0.0))
        v2.append(d2.get(el, 0.0))
    dot = sum(a * b for a, b in zip(v1, v2))
    n1 = sum(a * a for a in v1) ** 0.5
    n2 = sum(b * b for b in v2) ** 0.5
    if n1 == 0 or n2 == 0:
        return 0.0
    return dot / (n1 * n2)


def _has_doping_substitution(query: dict[str, float], target: dict[str, float]) -> bool:
    """Check if query is a doped/substituted variant of target (or vice versa)."""
    query_els = set(query.keys())
    target_els = set(target.keys())
    if query_els == target_els:
        return False
    common = query_els & target_els
    if len(common) < max(len(query_els), len(target_els)) - 2:
        return False
    return True


def match_composition(
    query_formula: str,
    index: StructureIndex,
    similarity_threshold: float = 0.95,
) -> MatchResult:
    """Match an extracted composition against the structure index.

    Returns the best match found, or a no-match result.
    """
    query_norm = _normalize_formula(query_formula)
    query_dict = _parse_formula_dict(query_norm)

    if not query_dict:
        return MatchResult(query_formula=query_formula)

    best: MatchResult = MatchResult(query_formula=query_formula)
    for entry in index.entries:
        target_dict = entry.get("formula_dict", {})
        if not target_dict:
            continue

        similarity = _formula_similarity(query_dict, target_dict)

        if similarity >= similarity_threshold:
            is_exact = abs(similarity - 1.0) < 1e-6
            is_sub = _has_doping_substitution(query_dict, target_dict)
            score = 1.0 if is_exact else similarity

            if score > best.match_score:
                best = MatchResult(
                    query_formula=query_formula,
                    matched_formula=entry["formula"],
                    matched_material_id=entry["material_id"],
                    match_score=score,
                    is_exact=is_exact,
                    substitution_variant=is_sub,
                    source_db=entry["source_db"],
                )

    return best


def find_unmatched_compositions(
    extracted_records: list[Any],
    index: StructureIndex,
    similarity_threshold: float = 0.95,
) -> list[tuple[str, list[Any]]]:
    """Find extracted compositions that don't match any structure.

    Returns list of (composition, unmatched_records) for DFT gap-filling.
    """
    matched: set[str] = set()
    for record in extracted_records:
        comp = getattr(record, "composition", "") or (record.get("composition", "") if isinstance(record, dict) else "")
        result = match_composition(comp, index, similarity_threshold)
        if result.matched_material_id:
            matched.add(comp)

    unmatched: dict[str, list[Any]] = {}
    for record in extracted_records:
        comp = getattr(record, "composition", "") or (record.get("composition", "") if isinstance(record, dict) else "")
        if comp not in matched:
            if comp not in unmatched:
                unmatched[comp] = []
            unmatched[comp].append(record)

    return list(unmatched.items())
