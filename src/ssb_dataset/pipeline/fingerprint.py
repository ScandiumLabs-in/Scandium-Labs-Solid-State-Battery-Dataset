"""Material fingerprinting — canonical identity for a composition string.

Two different strings may denote the same material (Li7La3Zr2O12 vs
Li7La3Zr2O12 vs Li7 La3 Zr2 O12; Li1.3Al0.3Ti1.7(PO4)3 vs LATP; nominal vs
exact stoichiometry). This module reduces any composition string to a canonical
reduced formula so records of the same material can be grouped, deduplicated,
and cross-paper-aggregated deterministically.

It is deliberately conservative: it never guesses element identities from
abbreviations (LATP -> Li1.3Al0.3Ti1.7(PO4)3 is NOT attempted — that mapping is
the benchmark inventory's job, not a fingerprint). The fingerprint only
canonicalizes what is already expressed as a chemical formula.

Fingerprint levels:
  - reduced_formula  : pymatgen reduced formula (Li6PS5Cl), the primary key
  - key_elements     : sorted tuple of element symbols present
  - formula_key      : reduced_formula if resolvable, else a normalized text key
"""

from __future__ import annotations

import re

from pymatgen.core import Composition

# Known composition aliases -> canonical composition (extend from benchmark
# inventory over time; these are authoritative, title-verified mappings only).
ALIASES: dict[str, str] = {
    "LATP": "Li1.3Al0.3Ti1.7(PO4)3",
    "LLZO": "Li7La3Zr2O12",
    "LLZTO": "Li6.5La3Zr1.5Ta0.5O12",
    "LGPS": "Li10GeP2S12",
    "LISICON": "Li14ZnGe4O16",
    "NASICON": "Na3Zr2Si2PO12",
    "LAGP": "Li1.5Al0.5Ge1.5(PO4)3",
    "LIPON": "Li2.9PO3.3N0.46",
    "PEO": "C2H4O",
    "LLTO": "Li0.33La0.56TiO3",
    "LTPS": "Li4PS4",
}

_FORBIDDEN_WORDS = re.compile(
    r"(?:\b(?:the|with|and|using|prepared|composite|doped|based|for|of|in|containing)\b)|[A-Za-z]{4,}"
)

# Descriptor suffixes that carry no stoichiometric meaning: "Li10GeP2S12-type
# (Li9.54...)" means a material "of the LGPS type with composition ...", so the
# parenthetical composition is the identity. Dopant annotations like
# "Li7La3Zr2O12:Ta" are intentionally NOT stripped — doped variants are distinct
# materials in the benchmark inventory and must keep their own group.
_DESCRIPTOR_SUFFIX = re.compile(r"(?:-type|-based|-like)\s*\(([^)]*)\)\s*$")


def _strip_descriptors(formula: str) -> str:
    """Remove descriptor suffixes so the real composition is what's fingerprinted.

    "Li10GeP2S12-type(Li9.54Si1.74P1.44S11.7Cl0.3)" -> "Li9.54Si1.74P1.44S11.7Cl0.3"
    "Li10GeP2S12-type (Li9.54Si1.74P1.44S11.7Cl0.3)" -> "Li9.54Si1.74P1.44S11.7Cl0.3"
    """
    f = str(formula or "").strip()
    m = _DESCRIPTOR_SUFFIX.search(f)
    if m:
        return m.group(1).strip()
    return f


def _strip_parenthetical_extras(formula: str) -> str:
    """Drop trailing descriptors like (cubic), (annealed), (PDF:...)."""
    # keep stoichiometric parentheses; drop parenthetical labels that contain no digits
    return re.sub(r"\([^)]*\d[^)]*\)", lambda m: m.group(0), formula)


def fingerprint(composition: str) -> dict[str, object]:
    """Canonical identity fields for a composition string.

    Returns {"reduced_formula", "key_elements", "formula_key", "alias_resolved"}.
    Never raises: unresolvable strings fall back to a normalized text key.
    """
    comp = str(composition or "").strip()
    comp = _strip_descriptors(comp)
    alias_resolved = ""
    lower = comp.lower()

    # direct alias hit — case-insensitive so "LiPON"/"LIPON" both resolve to the
    # same canonical formula (a case-only match previously returned None and
    # crashed downstream re.findall on the None value).
    if lower in {a.lower() for a in ALIASES} or comp in ALIASES:
        canonical = next((v for k, v in ALIASES.items() if k.lower() == lower), None)
        alias_resolved = comp
        if canonical is not None:
            comp = canonical

    # try pymatgen
    reduced = ""
    try:
        reduced = Composition(comp).reduced_formula
    except Exception:
        pass

    # key elements from either pymatgen or element-symbol scan
    key_elems: tuple[str, ...] = ()
    if reduced:
        try:
            key_elems = tuple(sorted({str(e) for e in Composition(reduced).elements}))
        except Exception:
            key_elems = tuple(sorted(set(re.findall(r"[A-Z][a-z]?", reduced))))
    else:
        key_elems = tuple(sorted(set(re.findall(r"[A-Z][a-z]?", comp))))

    if reduced:
        formula_key = reduced
    else:
        # normalized text key: strip spaces/punctuation, keep as-is
        formula_key = re.sub(r"\s+", "", comp)
        formula_key = formula_key.replace("·", "").replace("\u2212", "-")

    return {
        "reduced_formula": reduced,
        "key_elements": key_elems,
        "formula_key": formula_key,
        "alias_resolved": alias_resolved,
    }


def same_material(a: str, b: str, *, require_elements_match: bool = True) -> bool:
    """True if two composition strings denote the same material.

    Matches on reduced formula when both resolve; otherwise falls back to a
    key-element-set match (any order, ignoring ratios). Element-set match is
    only a grouping hint — it will group LiCoO2 and LiCoO1.5 as 'similar' by
    elements, so `require_elements_match` callers should not treat it as proof.
    """
    fa = fingerprint(a)
    fb = fingerprint(b)
    if fa["reduced_formula"] and fb["reduced_formula"]:
        return fa["reduced_formula"] == fb["reduced_formula"]
    if require_elements_match:
        ea, eb = fa["key_elements"], fb["key_elements"]
        return bool(ea) and ea == eb
    return fa["formula_key"] == fb["formula_key"]


def group_key(composition: str) -> str:
    """Best-effort grouping key: reduced formula if resolvable, else formula_key."""
    f = fingerprint(composition)
    return str(f["reduced_formula"] or f["formula_key"])
