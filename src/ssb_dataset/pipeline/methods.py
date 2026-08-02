"""Deterministic measurement-method parser.

Papers describe how a conductivity value was measured with well-known phrases:
electrochemical impedance spectroscopy (EIS), DC polarization, four-point
probe, Nyquist/Arrhenius fitting, galvanostatic/potentiostatic, AIMD/DFT for
computational values, plus the phase/structural characterisation methods
(XRD/SEM/TEM/Rietveld). Rather than relying on a human or an LLM to type the
method, we scan the PDF text layer with priority-ordered keyword patterns and
return the single best (most specific) method match.

Every function here is pure and deterministic: given the same PDF text it always
returns the same method string. No LLM, no network.

The returned method strings are the canonical vocabulary used across the
dataset (`measurement_method`): "EIS", "DC polarization", "four-point probe",
"galvanostatic", "potentiostatic", "GITT", "van der Pauw", "AC conductivity",
"DFT", "AIMD", "MD", "NMR", "Arrhenius fit". Characterisation-only methods
(XRD/SEM/TEM/Raman) are never returned as the conductivity method — they are
detected but flagged in a secondary set.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Iterable

# --------------------------------------------------------------------------
# Method pattern tables
# --------------------------------------------------------------------------

# Canonical method -> ordered list of (regex) patterns. Longer/more specific
# phrases come first so "electrochemical impedance spectroscopy" wins over a
# bare "impedance". Matching is case-insensitive over the full text layer.
_METHOD_PATTERNS: dict[str, list[str]] = {
    "EIS": [
        r"electrochemical\s+impedance\s+spectroscop(?:y|ies)",
        r"\bimpedance\s+spectroscop(?:y|ies)\b",
        r"\bEIS\b",
        r"Nyquist",
        r"impedance\s+measurements?\b",
        r"ac\s+impedance",
    ],
    "DC polarization": [
        r"dc\s+polarization",
        r"DC\s+(?:polarization|polarisation)",
        r"direct\s+current\s+polarization",
        r"electronic\s+conductivity\s+measurement",
    ],
    "four-point probe": [
        r"four[-\s]point\s+probe",
        r"4[-\s]point\s+probe",
        r"four[-\s]electrode\s+method",
    ],
    "van der Pauw": [
        r"van\s+der\s+pauw",
    ],
    "galvanostatic": [
        r"galvanostatic",
        r"galvanostat",
    ],
    "potentiostatic": [
        r"potentiostatic",
        r"potentiostat",
    ],
    "GITT": [
        r"\bGITT\b",
        r"galvanostatic\s+intermittent\s+titration",
    ],
    "AC conductivity": [
        r"ac\s+conductivity",
        r"frequency[-\s]dependent\s+conductivity",
    ],
    "NMR": [
        r"\bNMR\b",
        r"nuclear\s+magnetic\s+resonance",
    ],
    "DFT": [
        r"\bdensity\s+functional\s+theory\b",
        r"\bDFT\b",
        r"VASP",
        r"quantum\s+espresso",
    ],
    "AIMD": [
        r"\bAIMD\b",
        r"ab[-\s]initio\s+molecular\s+dynamics",
        r"first[-\s]principles\s+molecular\s+dynamics",
    ],
    "MD": [
        r"\bmolecular\s+dynamics\b",
        r"\bMD\s+simulations?\b",
    ],
}

# Characterisation / auxiliary methods: detected but NOT the conductivity
# measurement method. Reported separately so reviewers can cross-check.
_CHARACTERISATION_PATTERNS: dict[str, list[str]] = {
    "XRD": [r"x[-\s]?ray\s+diffraction", r"\bXRD\b", r"Rietveld"],
    "SEM": [r"scanning\s+electron", r"\bSEM\b"],
    "TEM": [r"transmission\s+electron", r"\bTEM\b"],
    "Raman": [r"\bRaman\b"],
    "TGA": [r"thermogravimetric", r"\bTGA\b"],
    "DSC": [r"differential\s+scanning\s+calorimetry", r"\bDSC\b"],
    "XPS": [r"x[-\s]?ray\s+photoelectron", r"\bXPS\b"],
    "EDX": [r"energy[-\s]dispersive", r"\bEDX\b", r"\bEDS\b"],
}

# Stop-words: tokens that, when alone, must not be treated as a method.
_METHOD_ORDER = (
    "AIMD",
    "DFT",
    "MD",
    "EIS",
    "GITT",
    "DC polarization",
    "galvanostatic",
    "potentiostatic",
    "four-point probe",
    "van der Pauw",
    "AC conductivity",
    "NMR",
)

_COMPILED: dict[str, list[re.Pattern]] = {
    method: [re.compile(p, re.IGNORECASE) for p in pats]
    for method, pats in _METHOD_PATTERNS.items()
}
_CHAR_COMPILED: dict[str, list[re.Pattern]] = {
    method: [re.compile(p, re.IGNORECASE) for p in pats]
    for method, pats in _CHARACTERISATION_PATTERNS.items()
}


@dataclass
class MethodMatch:
    """Result of scanning a document for measurement methods."""
    measurement_method: str | None
    characterisation_methods: list[str] = field(default_factory=list)
    matched_patterns: list[str] = field(default_factory=list)
    confidence: float = 0.0


def extract_measurement_method(text: str) -> MethodMatch:
    """Scan document text and return the most specific conductivity-measurement
    method plus any detected characterisation methods.

    Priority: explicit electrochemistry phrases (EIS/GITT/DC polarization) beat
    generic computation flags (DFT/AIMD/MD) when both appear — but a value that
    is purely computational carries its own method (DFT/AIMD), never "EIS".
    """
    if not text or not text.strip():
        return MethodMatch(measurement_method=None)

    found: dict[str, list[str]] = {}
    for method, pats in _COMPILED.items():
        hits = [p for p in pats if p.search(text)]
        if hits:
            found[method] = [p.pattern for p in hits]

    char_found: list[str] = []
    for method, pats in _CHAR_COMPILED.items():
        if any(p.search(text) for p in pats):
            char_found.append(method)

    if not found:
        return MethodMatch(measurement_method=None, characterisation_methods=char_found)

    # Rank: explicit electrochemistry measurement methods first, then
    # computational, then the rest — stable within the same tier by the
    # canonical order above.
    def _rank(m: str) -> int:
        if m in ("EIS", "GITT", "DC polarization", "galvanostatic",
                 "potentiostatic", "four-point probe", "van der Pauw",
                 "AC conductivity", "NMR"):
            return 0
        if m in ("AIMD", "DFT", "MD"):
            return 1
        return 2

    best = min(found, key=lambda m: (_rank(m), _METHOD_ORDER.index(m) if m in _METHOD_ORDER else 99))
    matched = found[best]
    conf = 0.6 + 0.1 * min(len(matched), 3) - (0.05 if _rank(best) == 1 else 0.0)
    return MethodMatch(
        measurement_method=best,
        characterisation_methods=char_found,
        matched_patterns=matched,
        confidence=min(conf, 1.0),
    )


def extract_measurement_method_from_pdf(pdf_path: str | Path) -> MethodMatch:
    """Open a PDF, extract its text layer, and run the method scan."""
    pdf_path = Path(pdf_path)
    if not pdf_path.exists():
        return MethodMatch(measurement_method=None)
    try:
        import fitz  # PyMuPDF

        doc = fitz.open(str(pdf_path))
        text = "\n".join(p.get_text("text") for p in doc)
        doc.close()
    except Exception:
        return MethodMatch(measurement_method=None)
    if not text or len(text) < 100:
        return MethodMatch(measurement_method=None)
    return extract_measurement_method(text)


def extract_methods_from_texts(texts: Iterable[str]) -> MethodMatch:
    """Aggregate the method scan over many text chunks (e.g. PDF pages)."""
    all_text = "\n".join(texts)
    return extract_measurement_method(all_text)
