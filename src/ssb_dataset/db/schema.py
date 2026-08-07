"""v1.0 — relational experimental dataset schema.

Turns the single flat canonical table into a set of first-class relational
entities following the roadmap:

    material -> experiment -> measurement
              -> paper
              -> synthesis
              -> dopant

Every entity gets a deterministic id so the tables can be joined and re-runs
produce identical ids. Measurements are never collapsed into material-level
aggregates — experimental variability is preserved row-for-row (never
overwrite). Field-level confidence (Phase F) is computed per measurement.

Tables (written by scripts/build_relational_dataset.py to relational_output/):

    materials.parquet      one row per unique material_id (full catalog)
    papers.parquet         one row per paper DOI in the experimental core
    experiments.parquet    one material measured under one condition set
                           in one paper (condition fingerprint)
    measurements.parquet   one (experiment, property, value) row with
                           per-field confidence + evidence chain
    synthesis.parquet      synthesis conditions per material+paper
    dopants.parquet        explicit dopant annotations (e.g. Li7La3Zr2O12:Ta)

All id schemes are stable hashes; build is deterministic and network-free.
"""

from __future__ import annotations

import hashlib
import math
from typing import Any

# ---- ID schemes -------------------------------------------------------------

_ID_HASHES = {
    "experiment": "exp-",
    "measurement": "meas-",
    "synthesis": "syn-",
    "sample": "smp-",
    "dopant": "dop-",
    "paper": "paper-",
    "author": "aut-",
}


def stable_id(kind: str, *parts: Any) -> str:
    """Deterministic id from a stable hash of the given parts."""
    raw = "|".join("" if p is None else str(p) for p in parts)
    return _ID_HASHES[kind] + hashlib.sha256(raw.encode()).hexdigest()[:16]


def paper_id(doi: str | None, fallback: str = "") -> str:
    """paper_id is the DOI itself (a natural unique key). Missing DOIs get a
    deterministic placeholder id derived from the material."""
    doi = (doi or "").strip()
    if doi:
        return doi
    return stable_id("paper", fallback)


# ---- Confidence tiers -------------------------------------------------------

# Base value-confidence per tier (Phase F). verified_human is the gold
# standard; anything auto-extracted sits strictly below it.
TIER_CONFIDENCE = {
    "verified_human": 1.0,
    "high_confidence_extraction": 0.85,
    "low_confidence_extraction": 0.5,
    "dft_computed_inhouse": 0.3,
    "dft_native": 0.2,
}


def tier_confidence(tier: str | None) -> float:
    return TIER_CONFIDENCE.get((tier or "").strip(), 0.5)


# ---- Measurement properties -------------------------------------------------

# Canonical column -> (property name, output unit). Extend as new measurement
# kinds (CCD, transference number, ...) are added to the experimental core.
MEASUREMENT_MAP = {
    "ion_transport.sigma_RT": ("conductivity", "S/cm"),
    "ion_transport.activation_energy_Ea": ("activation_energy", "eV"),
    "experiment.sigma_60C_S_per_cm": ("conductivity_60C", "S/cm"),
    "experiment.sigma_80C_S_per_cm": ("conductivity_80C", "S/cm"),
}


# ---- Experiment / synthesis condition fingerprints --------------------------

# Fields that distinguish one experiment (measurement event) from another for
# the same material+paper. Only the *populated* subset is used, so two rows
# that agree on every reported condition collapse to one experiment while a
# different atmosphere / sinter T / method yields a distinct experiment.
EXPERIMENT_FINGERPRINT_FIELDS = (
    "sample_form", "atmosphere", "pelletizing_pressure_MPa",
    "sinter_temperature_C", "sinter_time_h", "annealing_temperature_C",
    "annealing_time_h", "measurement_method", "conductivity_type",
    "instrument", "electrode_material", "frequency_min_Hz", "frequency_max_Hz",
    "pellet_diameter_mm", "thickness_mm", "relative_density_pct",
)

# Fields that define the synthesized specimen (sample). A sample is the
# material as made; experiments measure it.
SYNTHESIS_FINGERPRINT_FIELDS = (
    "precursors", "ball_milling", "solid_state", "sintering", "annealing",
    "calcination", "hot_pressing", "spark_plasma_sintering", "sol_gel",
    "mechanochemical", "sinter_temperature_C", "sinter_time_h",
    "annealing_temperature_C", "annealing_time_h", "pelletizing_pressure_MPa",
    "atmosphere", "heating_rate_C_per_min", "cooling_rate_C_per_min",
    "reaction_string",
)


def _populated(value: Any) -> bool:
    if value is None:
        return False
    if isinstance(value, bool):
        return value
    if isinstance(value, (list, dict, set, tuple)):
        return len(value) > 0
    # numpy arrays / other sized containers
    try:
        if not isinstance(value, str):
            return len(value) > 0
    except TypeError:
        pass
    s = str(value).strip()
    return s != "" and s.lower() not in ("nan", "none", "null", "unknown")


def fingerprint(record: dict[str, Any], fields: tuple[str, ...]) -> str:
    """Stable string of the populated fingerprint fields in fixed order."""
    return "|".join(
        f"{f}={record.get(f)}" for f in fields if _populated(record.get(f))
    )


def merge_fingerprints(*fps: str) -> str:
    """Combine several fingerprints (experiment + synthesis) into one id key."""
    return "|".join(fp for fp in fps if fp)


# ---- Field-level confidence (Phase F) ---------------------------------------

# Weights for the overall measurement confidence (sums to 1).
FIELD_WEIGHTS = {
    "value": 0.5,
    "temperature": 0.15,
    "method": 0.15,
    "evidence": 0.2,
}


def field_confidences(
    record: dict[str, Any],
    *,
    tier: str | None = None,
    extraction_confidence: float | None = None,
) -> dict[str, float]:
    """Per-field confidence scores for one measurement row (0..1 each).

    - value:        tier base, blended with extraction_confidence_score.
                    verified_human is the gold standard and is always 1.0 —
                    an extraction score can never dilute a human check.
    - temperature:  1.0 iff a measurement temperature is present
    - method:       1.0 iff a measurement method is present
    - evidence:     1.0 iff an evidence sentence is present
    """
    tier = (tier or "").strip()
    base = tier_confidence(tier)
    if tier == "verified_human":
        value = 1.0
    else:
        value = base
        if extraction_confidence is not None:
            try:
                xc = max(0.0, min(1.0, float(extraction_confidence)))
            except (TypeError, ValueError):
                xc = base
            value = 0.6 * base + 0.4 * xc

    temp = record.get("temperature_range_measured")
    if isinstance(temp, dict):
        temp_present = any(_populated(temp.get(k)) for k in ("min_C", "max_C", "min", "max", "min_K", "max_K"))
    else:
        temp_present = _populated(temp)
    method = record.get("ion_transport.measurement_method")
    evidence = record.get("text_provenance.evidence_sentence")

    return {
        "value": round(min(1.0, value), 3),
        "temperature": 1.0 if temp_present else 0.0,
        "method": 1.0 if _populated(method) else 0.0,
        "evidence": 1.0 if _populated(evidence) else 0.0,
    }


def overall_confidence(fields: dict[str, float]) -> float:
    """Weighted sum of the per-field confidences."""
    return round(
        sum(FIELD_WEIGHTS[k] * fields.get(k, 0.0) for k in FIELD_WEIGHTS), 3
    )


# ---- Temperature normalization ----------------------------------------------

def _min_temp_c(v: Any) -> float | None:
    if isinstance(v, dict):
        for k in ("min_C", "min", "low", "min_K"):
            if v.get(k) is not None:
                try:
                    val = float(v[k])
                    return val - 273.15 if k == "min_K" else val
                except (TypeError, ValueError):
                    return None
    return None


def _max_temp_c(v: Any) -> float | None:
    if isinstance(v, dict):
        for k in ("max_C", "max", "high", "max_K"):
            if v.get(k) is not None:
                try:
                    val = float(v[k])
                    return val - 273.15 if k == "max_K" else val
                except (TypeError, ValueError):
                    return None
    return None


# ---- Dopant parsing ---------------------------------------------------------

# Regex-free, deterministic annotation parser. A dopant is the token after ':'
# in an explicit annotation (Li7La3Zr2O12:Ta) or a '-doped'/'doped' qualifier.
# (70:30)-style mixture ratios are NOT dopants, and source-prefixed ids
# (aflow-aflow:hex) are not formula annotations.
_SOURCE_PREFIXES = (
    "aflow-", "mp-", "mcloud-", "materialscloud-", "cod-", "oqmd-",
    "jarvis-", "nomad-",
)
# element symbols used to anchor -doped qualifiers
_ELEMENTS = {
    "Al", "B", "Ba", "Ca", "Ce", "Cl", "Co", "Cr", "Cs", "Cu", "Fe", "Ga",
    "Ge", "Hf", "In", "K", "La", "Li", "Mg", "Mn", "Mo", "N", "Na", "Nb",
    "Ni", "O", "P", "Pb", "Rb", "S", "Sb", "Sc", "Se", "Si", "Sn", "Sr",
    "Ta", "Te", "Ti", "V", "W", "Y", "Zn", "Zr",
}


def _is_source_id(material_id: str) -> bool:
    low = material_id.strip().lower()
    return any(low.startswith(p) for p in _SOURCE_PREFIXES)


def _strip_ratio_annotations(material_id: str) -> str:
    """Remove (x:y) molar-ratio annotations so their ':' never looks like a
    dopant separator. Deterministic: keeps everything outside the parens."""
    out = []
    depth = 0
    for ch in material_id:
        if ch == "(":
            depth += 1
            continue
        if ch == ")":
            depth = max(0, depth - 1)
            continue
        if depth == 0:
            out.append(ch)
    return "".join(out)


def extract_dopants(material_id: str) -> list[str]:
    """Return explicit dopant annotations from a material id string."""
    if not material_id:
        return []
    if _is_source_id(material_id):
        return []
    out: list[str] = []
    # 1) colon annotations: Li7La3Zr2O12:Ta -> Ta
    cleaned = _strip_ratio_annotations(material_id)
    if ":" in cleaned:
        _, _, dopant = cleaned.partition(":")
        dopant = dopant.strip("() ").strip()
        if dopant and not dopant.replace(".", "").isdigit():
            out.append(dopant)
    # 2) -doped / doped qualifiers: "Al-doped" / "Al doped" -> Al
    lower = material_id.lower()
    if "-doped" in lower or "doped" in lower:
        toks = [t.strip(",; ") for t in material_id.replace("-", " ").split()]
        for i, tok in enumerate(toks):
            if "doped" in tok.lower():
                # candidate element is this token's stem or the previous token
                stem = tok.lower().replace("doped", "").strip(" -_")
                candidates = [stem]
                if i > 0:
                    candidates.append(toks[i - 1].lower())
                for cand in candidates:
                    for el in _ELEMENTS:
                        if cand == el.lower() or cand.startswith(el.lower()):
                            out.append(el)
    seen: set[str] = set()
    return [d for d in out if d and not (d in seen or seen.add(d))]
