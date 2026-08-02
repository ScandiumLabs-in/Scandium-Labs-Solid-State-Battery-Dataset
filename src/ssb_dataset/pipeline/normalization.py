"""Unit and temperature normalization engine.

Every value in the review queue carries its own reported unit string (S/cm,
mS/cm, uS/cm, S/m, log(σ), Ω⁻¹cm⁻¹, ...). This module is the single source of
truth for converting those to canonical units:

  - conductivity  -> S/cm
  - activation Ea -> eV
  - temperature   -> °C (keeps K alongside when converting)

The purpose is to kill the single most common extraction error class — the
mS/cm -> S/cm 1000× mistake — at review time, deterministically, before any
human or LLM sees the record.

Every function is pure and total: given a (value, unit) pair it always returns
a canonical (value, unit) pair or raises ValueError with a human-readable
reason, never None, never a silent guess.
"""

from __future__ import annotations

import math
import re
from dataclasses import dataclass

# --------------------------------------------------------------------------
# Canonical units
# --------------------------------------------------------------------------

CANONICAL_SIGMA_UNIT = "S/cm"
CANONICAL_EA_UNIT = "eV"
CANONICAL_TEMP_UNIT = "C"  # report both; this is the display unit
RT_C = 25.0

# --------------------------------------------------------------------------
# Conductivity normalization
# --------------------------------------------------------------------------

# Order matters: longer/compound strings before their substrings (e.g. "mS/cm"
# before "S/cm" would be wrong, but "S m-1" before "S", "ohm-1 cm-1" first).
_SIGMA_UNIT_RE = re.compile(
    r"(?:"
    r"(?P<milli>milli|m)S\s*[/\\]?\s*cm"
    r"|(?P<micro>\s?u|µ|micro)S\s*[/\\]?\s*cm"
    r"|(?P<nano>n)S\s*[/\\]?\s*cm"
    r"|(?P<sim>S)\s*[/\\]?\s*m"
    r"|(?P<sohm>S)\s*[/\\]?\s*cm"
    r"|(?P<ohm>Ω|ohm|Ohm)\s*(?:\^?\s*[-\u2212\u207b]?\s*[1¹])?\s*[/\\]?\s*cm\s*(?:\^?\s*[-\u2212\u207b]?\s*[1¹])?"
    r"|(?P<ho>S)\s*[/\\]?\s*cm"
    r")",
    re.IGNORECASE,
)
_LOG_PREFIX_RE = re.compile(r"log\s*(?P<base>10|e|)\s*(?:[(\[])?\s*(?P<neg>-)?\s*σ|log\s*σ", re.IGNORECASE)

# multipliers to S/cm
_SIGMA_FACTORS: dict[str, float] = {
    "milli": 1e-3,
    "micro": 1e-6,
    "nano": 1e-9,
    "sim": 1e-2,    # S/m  -> S/cm
    "sohm": 1.0,    # S/cm -> S/cm
    "ohm": 1.0,     # ohm^-1 cm^-1 -> S/cm
    "ho": 1.0,      # bare S/cm
}


@dataclass
class NormalizedConductivity:
    """Conductivity fully reduced to canonical S/cm, with provenance."""
    value_s_per_cm: float
    reported_unit: str
    reported_value: float
    multiplier: float
    is_log: bool = False
    note: str = ""


def _strip_log(value_text: str, unit_text: str) -> tuple[str, str, bool]:
    """Detect 'log σ = -4.5' style reporting; return (value, unit, is_log)."""
    m = _LOG_PREFIX_RE.search(unit_text)
    if m:
        return value_text, "S/cm", True
    # some papers write log(σ/S cm-1) in the unit column and the value is the log
    if "log" in unit_text.lower():
        return value_text, "S/cm", True
    return value_text, unit_text, False


def normalize_sigma(value: float | str | None, unit: str | None) -> NormalizedConductivity:
    """Convert a conductivity value + reported unit to canonical S/cm.

    Raises ValueError for unparseable units so callers can surface the problem
    to a human instead of silently guessing.

    Handles: S/cm, mS/cm, uS/cm, µS/cm, nS/cm, S/m, ohm^-1 cm^-1, Ω⁻¹cm⁻¹,
    and log-form values (log σ = x or log10).
    """
    if value is None:
        raise ValueError("conductivity value is None")
    if unit is None:
        # no unit reported: keep value as-is but flag it (cannot confirm scale)
        return NormalizedConductivity(
            value_s_per_cm=float(value), reported_unit="", reported_value=float(value),
            multiplier=1.0, note="no unit reported — scale unverified",
        )
    unit_str = str(unit).strip().replace("\u2212", "-").replace("\u2013", "-")
    value_str = str(value).strip()

    # log-form: value is the exponent
    value_text, unit_text, is_log = _strip_log(value_str, unit_str)

    v = _parse_number(value_text)
    if v is None:
        raise ValueError(f"cannot parse conductivity value {value!r}")

    if is_log:
        base = 10.0
        mb = re.search(r"log\s*10", unit_str, re.IGNORECASE)
        if mb:
            base = 10.0
        return NormalizedConductivity(
            value_s_per_cm=base ** v, reported_unit=unit_str, reported_value=v,
            multiplier=base ** v, is_log=True,
            note=f"log-form: 10^{v} = {base ** v:.2e} S/cm",
        )

    m = _SIGMA_UNIT_RE.search(unit_text)
    if not m:
        # tolerate a bare number with a unitless context (e.g. column header
        # defined on a previous line); keep value but flag it
        return NormalizedConductivity(
            value_s_per_cm=v, reported_unit=unit_str, reported_value=v,
            multiplier=1.0, note=f"unit {unit!r} not recognized — assumed S/cm",
        )
    group = next(g for g in ("milli", "micro", "nano", "sim", "sohm", "ohm", "ho") if m.group(g))
    mult = _SIGMA_FACTORS[group]
    return NormalizedConductivity(
        value_s_per_cm=v * mult, reported_unit=unit_str, reported_value=v,
        multiplier=mult, note=f"{unit_str} -> S/cm (×{mult:g})",
    )


def _parse_number(text: str) -> float | None:
    t = text.strip()
    if not t:
        return None
    # scientific: 1.2e-4, 1.2×10⁻⁴, 1.2 x 10^-4
    m = re.fullmatch(r"([+-]?\d+\.?\d*)\s*[eEx×]\s*10\s*([+-]?\d+)", t.replace("−", "-"))
    if m:
        return float(m.group(1)) * 10 ** int(m.group(2))
    # superscript minus is Unicode; also '1,2' decimal comma
    t = t.replace(",", ".").replace("−", "-").replace("\u2013", "-")
    try:
        return float(t)
    except ValueError:
        return None


# --------------------------------------------------------------------------
# Activation energy normalization
# --------------------------------------------------------------------------

_EA_UNIT_RE = re.compile(
    r"(?:"
    r"(?P<kj>kJ\s*/?\s*mol\s*[\u2212-]?1?)"
    r"|(?P<kcal>kcal\s*/?\s*mol\s*[\u2212-]?1?)"
    r"|(?P<mev>meV)"
    r"|(?P<ev>eV)"
    r")",
    re.IGNORECASE,
)
_EA_FACTORS: dict[str, float] = {
    "kj": 1 / 96.485,    # kJ/mol -> eV
    "kcal": 1 / 23.061,  # kcal/mol -> eV
    "mev": 1e-3,         # meV -> eV
    "ev": 1.0,
}


def normalize_ea(value: float | str | None, unit: str | None) -> float:
    """Convert activation energy to eV. Raises ValueError on unparseable input."""
    if value is None:
        raise ValueError("Ea value is None")
    v = _parse_number(str(value).strip())
    if v is None:
        raise ValueError(f"cannot parse Ea value {value!r}")
    if unit is None:
        return v  # assume eV when no unit reported (the dominant convention)
    m = _EA_UNIT_RE.search(str(unit))
    if not m:
        raise ValueError(f"unrecognized Ea unit {unit!r}")
    group = next(g for g in ("kj", "kcal", "mev", "ev") if m.group(g))
    return v * _EA_FACTORS[group]


# --------------------------------------------------------------------------
# Temperature normalization
# --------------------------------------------------------------------------

def normalize_temperature(value: float | str | None, unit: str | None = None) -> float:
    """Convert a temperature to °C. Accepts K or °C explicitly; a bare number
    with no unit is assumed °C (the common SSB reporting convention).
    Raises ValueError on unparseable input.
    """
    if value is None:
        raise ValueError("temperature value is None")
    v = _parse_number(str(value).strip())
    if v is None:
        raise ValueError(f"cannot parse temperature {value!r}")
    if unit is None:
        return v  # assume °C
    u = str(unit).strip().lower()
    if u in ("k", "kelvin", "°k", "\u00b0k"):
        return v - 273.15
    if u in ("c", "celsius", "°c", "\u00b0c", "°"):
        return v
    raise ValueError(f"unrecognized temperature unit {unit!r}")


def c_to_k(value_c: float) -> float:
    return value_c + 273.15


def _looks_like_conductivity_unit(unit: str) -> bool:
    """Heuristic: is a unit string a conductivity unit (vs eV/J/temperature)?"""
    u = unit.lower()
    if not u or u in ("ev", "mev", "kj/mol", "kcal/mol"):
        return False
    if "s/cm" in u or "s/m" in u or "s cm" in u or "ohm" in u or "log" in u:
        return True
    if "cm" in u and ("s" in u or "m" in u or "Ω" in u or "ohm" in u):
        return True
    return False


# --------------------------------------------------------------------------
# Friendly public API
# --------------------------------------------------------------------------

def normalize_record_units(record: dict) -> dict:
    """Add normalized_* fields to a review-queue record dict in place.

    The queue record carries `unit`/`value` (conductivity) and optionally
    `ea_unit`/`ea_value` or a single `Ea`. Adds:
      - normalized_sigma (S/cm) + sigma_multiplier + sigma_note
      - normalized_ea (eV) + ea_note
      - normalized_temperature_c + temperature_K
      - normalization_issues: list[str] of anything that had to be assumed
    """
    issues: list[str] = []
    # idempotent: clear stale normalized fields so re-runs never inherit
    # a wrong classification (e.g. an Ea record previously misread as sigma)
    for k in ("normalized_sigma", "sigma_multiplier", "sigma_note",
              "normalized_ea", "ea_note", "normalized_temperature_c"):
        record.pop(k, None)
    prop = str(record.get("property", "")).lower()
    unit = str(record.get("unit", "") or "").lower()

    is_sigma_prop = "conduct" in prop or "sigma" in prop
    is_ea_prop = "activation" in prop or prop in ("ea", "energy")

    # A value+unit pair may be a sigma OR an Ea depending on the property.
    # property=activation_energy with unit=eV must NOT go through normalize_sigma
    # (it would be misread as a conductivity and poison the consensus groups).
    if record.get("value") is not None:
        value_for_sigma = bool(is_sigma_prop or (not is_ea_prop and _looks_like_conductivity_unit(unit)))
        if value_for_sigma:
            try:
                nc = normalize_sigma(record.get("value"), record.get("unit"))
                record["normalized_sigma"] = nc.value_s_per_cm
                record["sigma_multiplier"] = nc.multiplier
                record["sigma_note"] = nc.note
                if nc.multiplier != 1.0:
                    issues.append(nc.note)
            except ValueError as e:
                issues.append(str(e))

    ea_val = (record.get("value") if is_ea_prop else None) or record.get("Ea") or record.get("ea_value") or record.get("activation_energy_Ea")
    ea_unit = record.get("unit") if is_ea_prop else None
    ea_unit = ea_unit or record.get("ea_unit") or record.get("Ea_unit")
    if ea_val is not None:
        try:
            record["normalized_ea"] = normalize_ea(ea_val, ea_unit)
            record["ea_note"] = f"reported {ea_val} {ea_unit or 'eV'}"
        except ValueError as e:
            issues.append(str(e))

    tval = record.get("temperature_celsius") or record.get("temperature_C") or record.get("temperature_K")
    if tval is not None:
        tval = float(tval)
        if "temperature_K" in record and record.get("temperature_K") is not None:
            tc = normalize_temperature(tval, "K")
            tunit = "K"
        else:
            tc = normalize_temperature(tval, "C")
            tunit = "C"
        record["normalized_temperature_c"] = tc
        record["temperature_K"] = c_to_k(tc)

    record["normalization_issues"] = issues
    return record
