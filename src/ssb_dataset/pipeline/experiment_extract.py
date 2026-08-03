"""Deterministic experiment-condition extraction from PDF text (M6 / Phase 2.2).

Scans a solid-electrolyte paper's text layer for the measurement/processing
conditions that distinguish one conductivity value from another: sample form,
pellet geometry/density, pelletizing pressure, electrode material, EIS
frequency range, atmosphere, and sintering/annealing schedule. These fill the
``experiment`` block of every verified record so consensus is condition-aware.

Deterministic and unit-aware --- no LLM. Patterns are conservative: a field is
only set when a clearly-labeled value/unit pair is found. Ambiguities are
reported, not guessed.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from pathlib import Path

import fitz  # PyMuPDF


@dataclass
class ExtractResult:
    sample_form: str | None = None
    sample_form_detail: str | None = None
    pellet_diameter_mm: float | None = None
    thickness_mm: float | None = None
    relative_density_pct: float | None = None
    pelletizing_pressure_MPa: float | None = None
    electrode_material: str | None = None
    electrode_deposition: str | None = None
    frequency_min_Hz: float | None = None
    frequency_max_Hz: float | None = None
    atmosphere: str | None = None
    sinter_temperature_C: float | None = None
    sinter_time_h: float | None = None
    annealing_temperature_C: float | None = None
    annealing_time_h: float | None = None
    instrument: str | None = None
    equivalent_circuit: str | None = None
    dc_bias_V: float | None = None
    humidity: str | None = None
    suspicious: list[str] = field(default_factory=list)
    notes: list[str] = field(default_factory=list)


# ── controlled vocabulary (raw token → canonical value) ──────────────────────
# sample form: raw match order matters (longest/least-ambiguous first).
SAMPLE_FORM_VOCAB = [
    ("thin film", "THIN_FILM"),
    ("thick film", "THICK_FILM"),
    ("single crystal", "SINGLE_CRYSTAL"),
    ("sintered pellet", "PELLET"),
    ("pressed powder", "POWDER"),
    ("membrane", "MEMBRANE"),
    ("composite", "COMPOSITE"),
    ("film", "FILM"),
    ("pellet", "PELLET"),
    ("disk", "DISK"),
    ("wafer", "WAFER"),
]
# electrode material: fabrication methods are NOT materials.
ELECTRODE_MATERIAL_VOCAB = {
    "stainless steel": "STAINLESS_STEEL",
    "li metal": "LI_METAL",
    "blocking electrodes": "BLOCKING",
    "graphite": "GRAPHITE",
    "carbon": "CARBON",
    "gold": "AU",
    "au": "AU",
    "silver": "AG",
    "ag": "AG",
    "platinum": "PT",
    "pt": "PT",
    "nickel": "NI",
    "indium": "IN",
    "aluminium": "AL",
    "al": "AL",
    "copper": "CU",
    "cu": "CU",
}
ELECTRODE_DEPOSITION_VOCAB = {
    "sputter": "SPUTTERED",
    "sputtering": "SPUTTERED",
    "sputtered": "SPUTTERED",
    "pressed": "PRESSED",
    "cold-pressed": "COLD_PRESSED",
    "painted": "PAINTED",
    "screen-printed": "SCREEN_PRINTED",
    "screen printed": "SCREEN_PRINTED",
    "printed": "SCREEN_PRINTED",
    "evaporated": "EVAPORATED",
    "coated": "COATED",
    "welded": "WELDED",
}
# atmosphere raw → canonical
ATMOSPHERE_VOCAB = {
    "glovebox": "GLOVEBOX",
    "dry air": "AIR",
    "air": "AIR",
    "ambient": "AIR",
    "argon": "AR",
    "ar": "AR",
    "nitrogen": "N2",
    "n2": "N2",
    "n 2": "N2",
    "helium": "HE",
    "he": "HE",
    "o2": "O2",
    "oxygen": "O2",
    "vacuum": "VACUUM",
    "inert atmosphere": "INERT",
    "inert gas": "INERT",
    "argon atmosphere": "AR",
    "n2 atmosphere": "N2",
}
# regex-safe, longest-key-first lookup for atmosphere (wraps bare keys with \b).
# Shorter dative-element keys (He/Ar/N2/O2) are appended with a trailing space
# guard in the caller, distinct from argon/helium etc.
_ATMOS_KEYS = sorted(ATMOSPHERE_VOCAB.keys(), key=len, reverse=True)
# regex-safe atomusrdered lookup for atmosphere (longest key first)
_ATMOS_KEYS = sorted(ATMOSPHERE_VOCAB.keys(), key=len, reverse=True)


# ── vocabulary (ordered: first matching token wins) ───────────────────────────
_SAMPLE_FORMS = ("pellet", "thin film", "thick film", "single crystal",
                 "sintered pellet", "pressed powder", "membrane", "film",
                 "composite", "disk", "wafer")
_ELECTRODES = ("stainless steel", "Li metal", "blocking electrodes",
               "Au", "Ag", "Pt", "graphite", "carbon")
_ATMOSPHERES = ("Dry", "glovebox", "argon", "nitrogen", "vacuum",
                "inert", "Ar", "air", "He", "O2")
_INSTRUMENTS = ("Solartron", "Zahner", "Biologic", "PARSTAT", "Autolab",
                "Metrohm", "HP 4192", "Wayne Kerr", "Novocontrol", "Keysight",
                "Agilent", "IM6", "Gamry")

_FREQ_MULT = {"Hz": 1.0, "mHz": 1e-3, "kHz": 1e3, "MHz": 1e6, "GHz": 1e9, "hz": 1.0}
_SUPER = str.maketrans("⁰¹²³⁴⁵⁶⁷⁸⁹", "0123456789")

_PRESSURE = re.compile(
    r"(?:pellet(?:is|iz|ing)*|press(?:ing|ure|ed)*|cold[-\s]press|uniaxial)"
    r"[^0-9]{0,50}?(\d+(?:\.\d+)?)\s*(MPa|GPa|ton|bar)", re.I)
_DIAMETER = re.compile(r"(?:pellet|sample)?\s*diameter[^0-9]{0,15}?(\d+(?:\.\d+)?)\s*mm", re.I)
_THICKNESS = re.compile(r"(?:pellet|sample)?\s*thickness[^0-9]{0,15}?(\d+(?:\.\d+)?)\s*mm", re.I)
_DENSITY = re.compile(r"(?:relative|theoretical)\s+density[^0-9]{0,20}?(\d+(?:\.\d+)?)\s*%", re.I)
_FREQUENCY = re.compile(r"(\d+(?:\.\d+)?)\s*(Hz|kHz|MHz|GHz)(?:[^0-9]{0,8}(?:to|–|-)\s*(\d+(?:\.\d+)?)\s*(Hz|kHz|MHz|GHz))?", re.I)
_SINTER_T = re.compile(r"(?:sinter(?:ed|ing)?|fired?|calcined?|anneal(?:ed|ing)?)\s*(?:at|of|=)?\s*[^0-9]{0,20}?(\d+(?:\.\d+)?)\s*(?:°C|⁰C|℃| C|°\s*C|K)", re.I)
_TIME_H = re.compile(r"(\d+(?:\.\d+)?)\s*h\b")
_BIAS_V = re.compile(r"(?:dc|d\.c\.|d\.c)\s+bias[^0-9]{0,10}?(\d+(?:\.\d+)?)\s*V", re.I)
_EC = re.compile(
    r"(?:equivalent\s+circuit|equivalent\s+circuit\s+model|"
    r"fitted\s+to\s+(?:an?\s+)?equivalent\s+circuit)[^0-9A-Za-z]{0,12}?"
    r"([(A-Za-z][A-Za-z0-9()\[\]{}|+*/.,~-]*?)(?=\s+[A-Za-z]{2,}|\s*\.|\s*$)", re.I)
_HUMIDITY = re.compile(
    r"(?:relative\s+humidity\s+(?:of|was|=)?\s*(\d+(?:\.\d+)?)\s*%"
    r"|(\d+(?:\.\d+)?)\s*%\s*(?:relative\s+)?(?:RH|humidity)\b)", re.I)


def _freq_hz(num_s: str, unit_s: str | None) -> float | None:
    try:
        v = float(num_s)
    except (ValueError, TypeError):
        return None
    if not unit_s:
        return None
    m = _FREQ_MULT.get(unit_s)
    if m is None:
        m = _FREQ_MULT.get(unit_s.lower())
    return v * m if m is not None else None


def _unit_mult(unit: str | None) -> float | None:
    if not unit:
        return None
    m = _FREQ_MULT.get(unit)
    if m is None:
        m = _FREQ_MULT.get(unit.lower())
    return m


def _flatten_wordbreaks(text: str) -> str:
    """Reconstruct words split across a line break ("sint\\nered" → "sintered")."""
    return re.sub(r"(?<=[A-Za-z])\n(?=[A-Za-z])", "", text)


def _looks_like_circuit(s: str) -> bool:
    """True only for a compact equivalent-circuit expression (R, CPE, Q, W,
    parentheses, parallel ||). Never prose like "used for the fit"."""
    import re
    s = s.strip()
    # must contain only circuit elements and delimiters, not prose words
    return bool(re.fullmatch(
        r"[A-Za-z0-9_()\[\]{}|+*/.,~-]+", s)) and not re.search(
        r"model|figure|scheme|used|fitting|yield|shown|gives|was|the|of|"
        r"circuit|using|interface|electrode",
        s, re.I)


def _clean_circuit(s: str) -> str:
    s = s.strip()
    # trim trailing sentence fragment: cut at a sentence-end word
    s = re.sub(r"\s+(?:it yields|in which|where|described by).*", "", s, flags=re.I)
    return " ".join(s.split())[:32]

def _eis_frequency_range(win: str) -> tuple[float | None, float | None]:
    """Parse an EIS frequency sweep range from a window of paper text.

    Handles the two common typographic forms:
      * plain: "0.1 Hz to 1 MHz", "1 Hz - 7 MHz"
      * superscript-10^N (heavy papers render 10⁻²→10⁶ as "10-2 to 106 Hz"):
          ``10⁻² to 10⁶`` → (1e-2, 1e6)

    Returns ``(min_hz, max_hz)`` or ``(None, None)`` if nothing clean is
    found. Deterministic; never guesses.
    """
    win_n = (win.replace("\xad", "").replace("\xa0", " ")
             .replace("−", "-").replace("\u2013", "-").translate(_SUPER))

    # reject NMR / MAS / NMR-spinning-frequency artifacts outright
    if re.search(r"MHz\s*\(|\bMAS\b|\bspinning\s*speed|\bNMR\b", win_n):
        return (None, None)

    # Form 1: superscript-10 pair "10⁻² to 10⁶" / "10–2 to 106"
    m10 = re.search(
        r"10\s*(?:-)\s*([0-9])\s*(?:Hz|kHz|MHz|GHz)?\s*(?:to|-)\s*"
        r"10\s*(?:-)?\s*([0-9])\s*(Hz|kHz|MHz|GHz)", win_n, re.I)
    if m10 and m10.group(3):
        base = _unit_mult(m10.group(3))
        if base is None:
            return (None, None)
        lo = 10.0 ** (-int(m10.group(1))) * base
        hi = 10.0 ** int(m10.group(2)) * base
        return (lo, hi)

    # Form 2: numeric range with 10^N superscript upper band
    #   "0.01 to 10^6 Hz" (as "0.01 to 106 Hz")
    mz = re.search(
        r"(\d+(?:\.\d+)?)\s*(?:to|-|–|and|up to)\s*(10\s*([0-9]))\s*(Hz|kHz|MHz|GHz)", win_n, re.I)
    if mz and mz.group(4):
        base = _unit_mult(mz.group(4))
        if base is None:
            return (None, None)
        lo = float(mz.group(1)) * base
        hi = 10.0 ** int(mz.group(3)) * base
        return (min(lo, hi), max(lo, hi))

    # Form 3: plain numeric range "1 Hz - 7 MHz"
    mr = re.search(
        r"(\d+(?:\.\d+)?)\s*(Hz|kHz|MHz|GHz)\s*(?:to|-|–|and|up to)\s*"
        r"(\d+(?:\.\d+)?)\s*(Hz|kHz|MHz|GHz)", win_n, re.I)
    if mr:
        lo = _freq_hz(mr.group(1), mr.group(2))
        hi = _freq_hz(mr.group(3), mr.group(4))
        if lo is not None and hi is not None:
            return (min(lo, hi), max(lo, hi))
        return (lo, hi)

    # Form 4: plain single "from X Hz" / "X MHz"
    ms = re.search(r"(\d+(?:\.\d+)?)\s*(Hz|kHz|MHz|GHz)", win_n, re.I)
    if ms:
        v = _freq_hz(ms.group(1), ms.group(2))
        if v is not None:
            return (v, None)
    return (None, None)


def extract_conditions(pdf_path: str | Path) -> ExtractResult:
    res = ExtractResult()
    try:
        doc = fitz.open(str(pdf_path))
        pages = [p.get_text("text") for p in doc]
        doc.close()
    except Exception:
        return res
    text = "\n".join(pages)
    if not text or len(text.strip()) < 100:
        return res  # scanned / no text layer

    # Reconstruct words split across line breaks ("sint\nered" → "sintered").
    # Preserve sentence boundaries that matter for section scoping.
    text = _flatten_wordbreaks(text)

    low = text.lower()

    # sample form (controlled vocabulary)
    for raw, canon in SAMPLE_FORM_VOCAB:
        if re.search(rf"\b{re.escape(raw)}\b", low):
            res.sample_form = canon
            break

    # pelletizing pressure → MPa (reject hydrogen-storage/bar/torr contexts)
    pm = _PRESSURE.search(text)
    if pm:
        near = text[max(0, pm.start() - 60): pm.end() + 30]
        rejected = re.search(
            r"H2\s|hydrogen|bar?\s+H|\bTORR\b|\bstorage\s+press|desorbit|"
            r"\bbar\b|\bGPa\b for lattice|\bautoclave\b|\bkilobar\b", near, re.I)
        val = float(pm.group(1))
        u = pm.group(2).lower()
        if u == "gpa":
            val *= 1e3
        elif u == "bar":
            val = round(val * 0.1, 6)
        elif u == "pa":
            val = round(val * 1e-6, 9)
        # plausible pelletizing pressures for ceramic/composite SSEs: 1–600 MPa
        if not rejected and 1.0 <= val <= 600.0:
            res.pelletizing_pressure_MPa = val
            if val < 15.0:
                res.suspicious.append(f"pelletizing_pressure_MPa={val} low (<15 MPa)")

    # diameter / thickness (with plausibility checks → suspicious list)
    dm = _DIAMETER.search(text)
    if dm:
        v = float(dm.group(1))
        res.pellet_diameter_mm = v
        if not 4.0 <= v <= 40.0:
            res.suspicious.append(f"pellet_diameter_mm={v} outside 4–40 mm")
    tm = _THICKNESS.search(text)
    if tm:
        v = float(tm.group(1))
        res.thickness_mm = v
        if not 0.05 <= v <= 20.0:
            res.suspicious.append(f"thickness_mm={v} outside 0.05–20 mm")

    # relative density
    dn = _DENSITY.search(text)
    if dn:
        res.relative_density_pct = float(dn.group(1))

    # electrode: material vs deposition are distinct dimensions
    for raw, canon in ELECTRODE_MATERIAL_VOCAB.items():
        if re.search(rf"\b{re.escape(raw)}\b", low):
            res.electrode_material = canon
            break
    for raw, canon in ELECTRODE_DEPOSITION_VOCAB.items():
        if re.search(rf"{re.escape(raw)}", low):
            res.electrode_deposition = canon
            break

    # frequency (EIS sweep range) — must appear in an impedance/AC/EIS context,
    # NOT NMR MAS nuclei ("73.58 MHz (6Li)") or stray spectroscopy.
    _EIS_CTX = re.compile(
        r"(?:impedance|EIS|electrochemical impedance|AC\s*impedance|"
        r"conductivity measurements?|Nyquist|frequency range of|"
        r"frequency sweep)", re.I)
    eis_ctx = _EIS_CTX.search(text)
    if eis_ctx:
        # search frequency tokens only within a window around the EIS phrase
        win = text[max(0, eis_ctx.start() - 200): eis_ctx.end() + 200]
        # reject NMR/spinning artifacts in the window
        if re.search(r"MHz\s*\(|MAS|\bspinning\s*speed|\bNMR\b", win):
            win = ""
        if win:
            _fmin, _fmax = _eis_frequency_range(win)
            if _fmin is not None:
                res.frequency_min_Hz = _fmin
            if _fmax is not None:
                res.frequency_max_Hz = _fmax

    # atmosphere (canonical controlled vocabulary; longest key first to disambiguate
    # "Ar" inside "argon"/"argon atmosphere" and "N2" inside "nitrogen")
    for key in _ATMOS_KEYS:
        pat = r"\b" + key + r"\b" if re.fullmatch(r"[A-Za-z0-9]+", key) else key
        if re.search(pat, low, re.I):
            res.atmosphere = ATMOSPHERE_VOCAB[key]
            break

    # sinter / anneal temperature (guard superscript-degree artifacts like
    # ``10500`` from ``1050°C``; keep only physically plausible offsets)
    sm = _SINTER_T.search(text)
    if sm:
        tval = float(sm.group(1))
        # superscripted/unified degree symbol often coalesces a trailing 0
        if tval > 2000:  # unphysical for ceramic sintering → superscript artifact
            tval = tval / 10 if tval >= 10000 else tval
        res.sinter_temperature_C = tval
        seg = text[sm.start(): sm.end() + 150]
        th = _TIME_H.search(seg)
        if th:
            res.sinter_time_h = float(th.group(1))
    am = re.search(r"anneal(?:ed|ing)?\s*(?:at|of)?\s*[^0-9]{0,15}?(\d+(?:\.\d+)?)\s*(?:°C|℃| C|K)", text, re.I)
    if am:
        aval = float(am.group(1))
        if aval > 2000:
            aval = aval / 10.0 if aval >= 10000 else aval
        res.annealing_temperature_C = aval

    # instrument
    for ins in _INSTRUMENTS:
        if re.search(rf"\b{re.escape(ins)}\b", text, re.I):
            res.instrument = ins
            break

    # equivalent_circuit: enabled with the conservative parser only. A candidate
    # survives only if it is a compact circuit expression (R, CPE, Q, W,
    # parentheses, ||) and contains no prose words — so the classic failure mode
    # (capturing "model and scheme of int") is rejected by _looks_like_circuit.
    ec = _EC.search(text)
    if ec:
        cand = ec.group(1)
        if _looks_like_circuit(cand) and len(cand) >= 3:
            cleaned = _clean_circuit(cand)
            if cleaned:
                res.equivalent_circuit = cleaned

    # humidity (open-air / glovebox papers often report RH during storage or
    # measurement; store as a canonical string like "50%" or "DRIED")
    hm = _HUMIDITY.search(text)
    if hm:
        val = hm.group(1) or hm.group(2)
        pct = float(val)
        if 0.0 <= pct <= 100.0:
            res.humidity = f"{pct:g}%"

    # dc bias
    bi = _BIAS_V.search(text)
    if bi:
        res.dc_bias_V = float(bi.group(1))

    res.notes = [k for k, v in res.__dict__.items()
                 if k not in ("notes",) and v is not None]
    return res