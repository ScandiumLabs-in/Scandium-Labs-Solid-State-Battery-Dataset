"""Deterministic family classifier — composition rules for all 12 SSB families."""

from __future__ import annotations

import re

from pymatgen.core import Composition, Structure

from ssb_dataset.schema import Family

POLYMER_PATTERNS = re.compile(
    r"(PEO|PAN|PVDF|PMMA|PCL|PEG|PPO|PTMC|PVDF-HFP)\d*", re.IGNORECASE
)

HALOGENS = {"CL", "BR", "I", "F"}

# Elements that do NOT count as a "metal" for the oxide catch-all. A Li+O
# compound whose only non-Li/O elements come from this set is not an oxide
# (e.g. LiPON -> P+N, Li2CO3 -> C, Li3PO4 -> P) and stays unknown.
NON_METALS = {
    "H", "HE", "B", "C", "N", "O", "F", "NE",
    "P", "S", "CL", "AR", "BR", "KR", "I", "XE",
    "SE", "AS", "TE", "AT", "RN",
}


def _parse_formula_string(formula: str) -> set[str]:
    """Extract element symbols from a formula string, handling polymer/composite notation."""
    from pymatgen.core import Composition, Element

    elements: set[str] = set()

    chunks = re.split(r"[-_+/() ]+", formula)
    for chunk in chunks:
        if not chunk:
            continue
        try:
            comp = Composition(chunk)
            elements.update(el.symbol for el in comp.elements)
        except Exception:
            raw_els = re.findall(r"[A-Z][a-z]?", chunk)
            for el in raw_els:
                try:
                    Element(el)
                    elements.add(el)
                except Exception:
                    pass

    return elements


def classify_family(
    composition: dict[str, float] | str | Composition | None = None,
    elements: set[str] | None = None,
    struct: Structure | None = None,
) -> Family:
    if isinstance(composition, str) and POLYMER_PATTERNS.search(composition) and ("Li" in composition or "li" in composition):
        return Family.polymer_composite

    if elements is None and composition is not None:
        if isinstance(composition, str):
            try:
                comp = Composition(composition)
                elements = {el.symbol for el in comp.elements}
            except Exception:
                elements = _parse_formula_string(composition)
        elif isinstance(composition, dict):
            elements = set(composition.keys())
        elif isinstance(composition, Composition):
            elements = {el.symbol for el in composition.elements}
        else:
            elements = set()

    if elements is None:
        elements = set()

    if struct is not None:
        comp = struct.composition
        elements = {el.symbol for el in comp.elements}

    upper = {e.upper() for e in elements}

    has_li = "LI" in upper
    has_alkali = bool(upper & {"LI", "NA", "K", "RB", "CS", "MG"})
    poly_in_name = bool(
        POLYMER_PATTERNS.search(composition)
        if isinstance(composition, str)
        else False
    )

    # A bare polymer-host abbreviation (PEO, PVDF-HFP, PAN, PEG, ...) in the
    # composition string is a polymer-composite electrolyte host even when it
    # has no parseable alkali metal (pure host backbone, or name not split).
    if poly_in_name:
        return Family.polymer_composite

    if not (has_li or has_alkali):
        return Family.unknown

    halogens = upper & HALOGENS

    # 1. Polymer/composite — requires organic carbon (C + H), NOT any C.
    #    This excludes carbonates (Li2CO3), carbides (Li2C2), oxycarbonates.
    if "C" in upper and "H" in upper:
        return Family.polymer_composite

    # 2. Argyrodite — Li6PS5X (X = Cl/Br/I).
    if "P" in upper and "S" in upper and halogens:
        return Family.argyrodite

    # 3. Antiperovskite — Li3OX (X = Cl/Br/I) and hydroxy variants Li2OHX.
    #    Must be alkali + (H) + oxygen + halogen only: excludes oxyfluorides/
    #    oxyhalides of transition metals and main-group frameworks.
    if "O" in upper and halogens:
        allowed = {"LI", "NA", "K", "RB", "CS", "H", "O", "F", "CL", "BR", "I"}
        if upper <= allowed:
            return Family.antiperovskite

    # 4. Halide — Li + halogen, no O/S.
    if halogens and "O" not in upper and "S" not in upper:
        return Family.halide

    # 5. Borohydride — (Li|Na|Mg)BH4 / complex borohydrides / borohydride-amides.
    if "B" in upper and "H" in upper and ("MG" in upper or has_alkali):
        return Family.borohydride

    # 6. Garnet — Li7La3Zr2O12-type.
    if "LA" in upper and "O" in upper and (upper & {"ZR", "HF", "TA", "NB"}):
        return Family.garnet

    # 7. Perovskite — Li3xLa2/3-xTiO3-type.
    if "LA" in upper and "TI" in upper and "O" in upper:
        return Family.perovskite

    # 8. NASICON — LATP/LAGP-type (Li + P + O + framework metal).
    if "O" in upper and "P" in upper and (upper & {"TI", "ZR", "GE", "HF", "AL", "SN"}):
        return Family.nasicon

    # 9. Hydride — Li + H (no O, borohydrides already caught).
    if "H" in upper and "O" not in upper:
        return Family.hydride

    # 10. Sulfide — Li + S (no O, or a thio-phosphate framework).
    if "S" in upper and ("O" not in upper or (upper & {"P", "SI", "GE", "SN"})):
        return Family.sulfide

    # 11. Oxide catch-all — Li + O with a metal (or pure Li-O).
    if "O" in upper:
        other = upper - {"LI", "O"}
        if not other or not (other <= NON_METALS):
            return Family.oxide

    return Family.unknown
