"""v0.9 — full-canonical quality scoring.

The roadmap asks for a *reproducible* per-record quality score on every row of
the canonical dataset, not just the approved literature records. This module
scores both kinds of row honestly:

  - experimental rows (verified_human / extraction tiers) reuse the proven
    A3/A4 `score_record` ladder — human verification + evidence + metadata +
    consensus + depth.
  - dft_native / dft_computed rows get a **completeness score**: what fraction
    of the expected schema blocks are populated, plus internal consistency
    (density/volume/gap/electroneutrality). These are structural records, so
    the honest score is "how complete and self-consistent is this record", not
    a trust ladder that would label all of them "rejected".

Every scorer returns a dict with the roadmap's four keys:

    quality.score      0-100
    quality.flags      list[str] of what is missing / inconsistent
    quality.confidence high | medium | low
    quality.version    scorer version string (v0.9.0)

Pure functions; no LLM, no network.
"""

from __future__ import annotations

from typing import Any

import numpy as np

from ssb_dataset.literature.record_quality import (
    QualityTier,
    quality_grade,
    score_record,
)

SCORER_VERSION = "v0.9.0"

# ── DFT completeness: expected block weights (sums to 100) ────────────────────

# Weight per schema block for a structural record. Blocks that carry the bulk
# of a DFT record's value weigh most; transport/labels are usually absent by
# construction on computed records and must not tank the score.
BLOCK_WEIGHTS: dict[str, float] = {
    "structure": 30.0,
    "thermodynamics": 20.0,
    "chemistry": 15.0,
    "electronic": 10.0,
    "redox": 7.0,
    "magnetic": 6.0,
    "graph": 6.0,
    "dielectric": 3.0,
    "mechanical": 3.0,
}

# Columns that are genuinely optional per-block (not counted against coverage)
# e.g. work function (0.02% coverage) and piezo (3.1%) are honest-to-goodness
# sparse MP fields and must not make otherwise-complete records look bad.
_OPTIONAL_COLUMNS = {
    "thermodynamics.weighted_work_function",
    "dielectric.piezo_e_ij_max",
    "thermodynamics.decomposition_products",
    "thermodynamics.electrochemical_stability_window",
}

# Consistency checks applied to DFT rows (each violation -5).
# column -> (is_bad(value), message)
_CONSISTENCY_CHECKS: list[tuple[str, Any]] = []


def _value(row: dict[str, Any], key: str) -> Any:
    """Read a dot-path key from a flat canonical dict, or the nested form."""
    if key in row:
        return row[key]
    # nested: structure.density -> row["structure"]["density"]
    if "." in key:
        head, _, tail = key.partition(".")
        if isinstance(row.get(head), dict):
            return row[head].get(tail)
    return None


def _present(v: Any) -> bool:
    if v is None:
        return False
    s = str(v).strip()
    return s != "" and s.lower() not in ("nan", "none", "null", "unknown")


def _is_listy(v: Any) -> bool:
    return isinstance(v, (list, tuple, dict))


def completeness_score(row: dict[str, Any]) -> dict[str, Any]:
    """Score a structural (DFT-native) record by block coverage + consistency.

    Coverage per block = fraction of non-optional scalar fields that are
    non-null. Score = Σ weight × coverage, minus consistency penalties.
    """
    flags: list[str] = []
    total = 0.0
    weight_sum = 0.0
    for block, weight in BLOCK_WEIGHTS.items():
        keys = [
            k for k, v in row.items()
            if k.startswith(f"{block}.") and not _is_listy(v)
        ]
        # If the record simply has no such block (e.g. magnetic absent on an
        # early pull), skip it entirely rather than scoring 0/weight.
        if not keys:
            continue
        weight_sum += weight
        denom_keys = [k for k in keys if k not in _OPTIONAL_COLUMNS]
        if not denom_keys:
            continue
        filled = sum(1 for k in denom_keys if _present(_value(row, k)))
        cov = filled / len(denom_keys)
        total += weight * cov

    # consistency penalties
    pen = 0.0
    density = _value(row, "structure.density")
    volume = _value(row, "structure.volume")
    gap = _value(row, "thermodynamics.band_gap")
    eabh = _value(row, "thermodynamics.energy_above_hull")
    electroneutral = _value(row, "redox.electroneutral")

    def _num(v):
        try:
            f = float(v)
            return None if np.isnan(f) else f
        except (TypeError, ValueError):
            return None

    d = _num(density)
    v = _num(volume)
    g = _num(gap)
    e = _num(eabh)
    if d is not None and d <= 0:
        flags.append(f"structure.density={d} non-positive")
        pen += 5
    if v is not None and v <= 0:
        flags.append(f"structure.volume={v} non-positive")
        pen += 5
    if g is not None and g < -0.05:
        flags.append(f"thermodynamics.band_gap={g} negative")
        pen += 5
    if e is not None and e < -0.05:
        flags.append(f"thermodynamics.energy_above_hull={e} negative")
        pen += 5
    if electroneutral is not None and str(electroneutral).lower() == "false":
        flags.append("redox.electroneutral=False (charge imbalance)")
        pen += 5

    score = total * (100.0 / weight_sum if weight_sum else 0.0) - pen
    score = int(round(max(0.0, min(100.0, score))))

    if score >= 80:
        confidence = "high"
    elif score >= 50:
        confidence = "medium"
    else:
        confidence = "low"

    return {
        "quality.score": score,
        "quality.grade": quality_grade(score),
        "quality.flags": flags,
        "quality.confidence": confidence,
        "quality.version": SCORER_VERSION,
        "quality.tier": QualityTier.rejected.value,  # not a gold-ladder record
        "quality.kind": "completeness",
    }


def _as_record_dict(row: dict[str, Any]) -> dict[str, Any]:
    """Map a canonical flat dict onto the field names `score_record` reads."""
    rec: dict[str, Any] = {}
    # human verification
    tier = str(_value(row, "identity.confidence_tier") or "")
    rec["confidence_tier"] = tier
    rec["human_verified"] = tier == "verified_human"
    rec["reviewer"] = _value(row, "text_provenance.extraction_reviewer")
    # evidence
    rec["evidence_page"] = _value(row, "text_provenance.evidence_page")
    rec["evidence_section"] = _value(row, "text_provenance.evidence_section")
    rec["evidence_sentence"] = _value(row, "text_provenance.evidence_sentence")
    rec["evidence_table_number"] = _value(row, "text_provenance.evidence_table_number")
    # values
    rec["sigma_RT"] = _value(row, "ion_transport.sigma_RT")
    rec["activation_energy_eV"] = _value(row, "ion_transport.activation_energy_Ea")
    rec["activation_energy"] = _value(row, "ion_transport.activation_energy_Ea")
    rec["temperature_celsius"] = _value(row, "experiment.temperature_celsius")
    rec["measurement_method"] = _value(row, "ion_transport.measurement_method")
    rec["conductivity_type"] = _value(row, "ion_transport.conductivity_type")
    # consensus context injected by the build script
    rec["agreement_grade"] = _value(row, "quality.agreement_grade")
    rec["n_papers"] = _value(row, "quality.n_papers")
    rec["is_outlier"] = _value(row, "quality.is_outlier")
    # experiment block (nested or flat)
    exp = _value(row, "experiment")
    rec["experiment"] = exp if isinstance(exp, dict) else {}
    return rec


def experimental_score(row: dict[str, Any]) -> dict[str, Any]:
    """Score an experimental record via the A3/A4 ladder (reused unchanged)."""
    rec = _as_record_dict(row)
    q = score_record(rec)
    score = q["quality_score"]
    confidence = "high" if score >= 80 else ("medium" if score >= 50 else "low")
    flags = [f"missing: {m}" for m in q.get("quality_notes", {}).get("missing", [])]
    if q.get("quality_notes", {}).get("evidence_missing"):
        flags.append("missing: evidence (no page/sentence)")
    return {
        "quality.score": score,
        "quality.grade": q["quality_grade"],
        "quality.flags": flags,
        "quality.confidence": confidence,
        "quality.version": SCORER_VERSION,
        "quality.tier": q["quality_tier"],
        "quality.kind": "experimental",
    }


def score_canonical_row(row: dict[str, Any]) -> dict[str, Any]:
    """Score any canonical row: completeness for structural records, the
    trust ladder for experimental ones."""
    tier = str(_value(row, "identity.confidence_tier") or "")
    if tier in ("dft_native", "dft_computed_inhouse") or not tier:
        return completeness_score(row)
    return experimental_score(row)
