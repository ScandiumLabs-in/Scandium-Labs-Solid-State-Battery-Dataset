"""A3/A4 — record-level quality score and Gold/Silver/Bronze confidence tiers.

Every verified experimental record receives a deterministic 0-100 quality score
and a letter grade (A+/A/B/C/D). The score answers the question *"why should
another researcher trust this measurement?"* — it combines:

    25  human verification (was a person able to confirm the value?)
    20  evidence quality (page + table + quoted sentence all present)
    20  metadata completeness (temperature + method + condition fields)
    15  cross-paper agreement (consensus grade of the material group)
    10  measurement depth (multi-point / multi-property records)
   -10  outlier penalty (record deviates >1.5 orders from group median)
   -15  missing evidence (no DOI/page/sentence → untrustworthy)

Grades: A+ >= 90, A >= 80, B >= 65, C >= 45, else D.

The tier assignment (Gold/Silver/Bronze/Rejected) maps the roadmap's
confidence ladder onto the existing schema:

    Gold     human-reviewed AND page + evidence sentence AND agrees with
             literature consensus (or n>=2 papers) AND metadata complete
    Silver   human-reviewed but single-paper / partial metadata
    Bronze   AI-verified only (high-confidence extraction, not human-checked)
    Rejected non-experimental (dft_native) or conflicting record

Pure functions; no LLM, no network, fully unit-testable.
"""

from __future__ import annotations

from enum import Enum
from typing import Any


class QualityTier(str, Enum):
    gold = "gold"
    silver = "silver"
    bronze = "bronze"
    rejected = "rejected"


# ── Grade scale ────────────────────────────────────────────────────────────────


def quality_grade(score: int) -> str:
    if score >= 90:
        return "A+"
    if score >= 80:
        return "A"
    if score >= 65:
        return "B"
    if score >= 45:
        return "C"
    return "D"


def _present(v: Any) -> bool:
    if v is None:
        return False
    s = str(v).strip()
    return s != "" and s.lower() not in ("nan", "none", "null", "unknown")


def _has_page_evidence(record: dict[str, Any]) -> bool:
    """Any of page / evidence_page / evidence_sentence / section present."""
    return any(
        _present(record.get(k))
        for k in ("page", "evidence_page", "evidence_sentence", "evidence_section", "section")
    )


def _evidence_quality(record: dict[str, Any]) -> tuple[int, list[str]]:
    """0-20 evidence sub-score. Requires page + table + sentence for full marks."""
    misses: list[str] = []
    has_page = _present(record.get("page")) or _present(record.get("evidence_page"))
    has_table = _present(record.get("table_number")) or _present(record.get("evidence_table_number"))
    has_sentence = _present(record.get("evidence_sentence"))
    if not has_page:
        misses.append("evidence_page")
    if not has_table:
        misses.append("evidence_table_number")
    if not has_sentence:
        misses.append("evidence_sentence")
    score = sum([has_page, has_table, has_sentence]) / 3 * 20
    return int(round(score)), misses


# ── Metadata completeness ──────────────────────────────────────────────────────


_EXPERIMENT_FIELDS = (
    "temperature_celsius",
    "measurement_method",
    "conductivity_type",
    "pelletizing_pressure_MPa",
    "relative_density_pct",
    "theoretical_density_g_per_cm3",
    "pellet_density_g_per_cm3",
    "electrode_material",
    "atmosphere",
    "sample_form",
    "frequency_max_Hz",
    "sinter_temperature_C",
    "sinter_time_h",
    "thickness_mm",
    "pellet_diameter_mm",
)


# Category weight per experiment field (sums to 20). Temperature + method are
# load-bearing; sample form / electrode / atmosphere / density are the next most
# informative; the rest complete the window.
_METADATA_CATEGORY_WEIGHTS: dict[str, float] = {
    "temperature_celsius": 6.0,
    "measurement_method": 6.0,
    "sample_form": 2.0,
    "electrode_material": 2.0,
    "atmosphere": 2.0,
    "density": 2.0,  # any of relative/theoretical/pellet density
}
_DENSITY_FIELDS = ("relative_density_pct", "theoretical_density_g_per_cm3", "pellet_density_g_per_cm3")


def _metadata_completeness(record: dict[str, Any]) -> tuple[int, list[str]]:
    """0-20 sub-score, category-weighted. Temperature + method (6+6) dominate;
    sample form, electrode, atmosphere, and any density (2 each) complete it."""
    exp = record.get("experiment", {}) if isinstance(record.get("experiment"), dict) else {}

    def has(field: str) -> bool:
        return _present(record.get(field)) or _present(exp.get(field))

    misses: list[str] = []
    score = 0.0
    for category, weight in _METADATA_CATEGORY_WEIGHTS.items():
        if category == "density":
            present = any(has(f) for f in _DENSITY_FIELDS)
        else:
            present = has(category)
        if present:
            score += weight
        else:
            misses.append(category)
    return int(round(score)), misses


# ── Consensus agreement (15 pts) ───────────────────────────────────────────────


_GRADE_RANK = {"A+": 5, "A": 4, "B": 3, "C": 2, "D": 1, "": 0}


def _agreement_score(record: dict[str, Any]) -> int:
    """0-15 from the material's consensus agreement grade, when known."""
    grade = record.get("agreement_grade") or record.get("consensus_grade") or ""
    rank = _GRADE_RANK.get(str(grade), 0)
    if rank == 0:
        n_papers = record.get("n_papers")
        return 8 if (isinstance(n_papers, int) and n_papers >= 2) else 5
    return int(round(rank / 5 * 15))


# ── Measurement depth (10 pts) ─────────────────────────────────────────────────


def _depth_score(record: dict[str, Any]) -> int:
    """0-10: multi-point σ(T) curves and multiple properties add value."""
    curve = record.get("sigma_vs_T_curve") or record.get("sigma_vs_T")
    n_curve = len(curve) if isinstance(curve, list) else 0
    score = min(n_curve, 3) * 2  # up to 6 for curve points
    has_ea = _present(record.get("activation_energy_eV")) or _present(record.get("activation_energy"))
    has_sigma = _present(record.get("sigma_S_per_cm")) or _present(record.get("sigma_RT"))
    if has_sigma and has_ea:
        score += 4
    return min(score, 10)


# ── Outlier penalty (max -10) ──────────────────────────────────────────────────


def _outlier_penalty(record: dict[str, Any]) -> int:
    if record.get("is_outlier") or record.get("consensus_outlier"):
        return -10
    return 0


# ── Full scoring ───────────────────────────────────────────────────────────────


def score_record(record: dict[str, Any]) -> dict[str, Any]:
    """Score one experimental record.

    Accepts either a queue-item-like dict (review_id/composition/property/value/
    unit/...) or a consensus-measurement dict (sigma_S_per_cm/...). Returns a
    dict with `quality_score`, `quality_grade`, `tier`, and `quality_notes`
    (per-component breakdown) ready to merge into the record.
    """
    human = 25 if record.get("human_verified") or record.get("reviewer") else 0
    if not human and record.get("confidence_tier") in ("dft_native", "dft_computed_inhouse"):
        human = 0

    ev_score, ev_misses = _evidence_quality(record)
    md_score, md_misses = _metadata_completeness(record)
    agree = _agreement_score(record)
    depth = _depth_score(record)
    penalty = _outlier_penalty(record)

    score = human + ev_score + md_score + agree + depth + penalty
    score = max(0, min(100, score))

    # Missing evidence is a hard trust failure independent of the rest.
    if not _has_page_evidence(record) and not record.get("reviewer"):
        score = min(score, 30)

    return {
        "quality_score": score,
        "quality_grade": quality_grade(score),
        "quality_tier": assign_tier(record, score),
        "quality_components": {
            "human_verification": human,
            "evidence_quality": ev_score,
            "metadata_completeness": md_score,
            "agreement": agree,
            "depth": depth,
            "outlier_penalty": penalty,
        },
        "quality_notes": {
            "missing": sorted(set(ev_misses + md_misses)),
            "evidence_missing": not _has_page_evidence(record),
        },
    }


# ── Tier assignment (A4) ───────────────────────────────────────────────────────


def assign_tier(record: dict[str, Any], score: int | None = None) -> QualityTier:
    """Map a record to Gold / Silver / Bronze / Rejected.

    Decision order matters: a record that fails the hard trust checks is
    Rejected regardless of score; a human-verified record with page+sentence+
    consensus is Gold; a human-verified single-paper record is Silver; anything
    AI-only is Bronze.
    """
    if score is None:
        score = score_record(record)["quality_score"]

    # Hard reject: non-experimental sources never reach the gold ladder.
    if record.get("confidence_tier") in ("dft_native", "dft_computed_inhouse"):
        return QualityTier.rejected
    # Rejected status from the review queue is authoritative.
    if str(record.get("status", "")).lower() in ("rejected", "reject"):
        return QualityTier.rejected

    human = bool(record.get("human_verified") or record.get("reviewer"))
    has_evidence = _has_page_evidence(record)
    agrees = bool(record.get("agrees_with_consensus")) or _GRADE_RANK.get(
        str(record.get("agreement_grade") or ""), 0
    ) >= 4
    n_papers = record.get("n_papers")
    multi_paper = isinstance(n_papers, int) and n_papers >= 2

    if not human:
        return QualityTier.bronze if score >= 80 else QualityTier.rejected

    # Gold requires the load-bearing metadata pair (temperature + method), not
    # every optional condition field — Gold stays achievable for complete data.
    md_misses = _metadata_completeness(record)[1]
    metadata_ok = score >= 80 and "temperature_celsius" not in md_misses and "measurement_method" not in md_misses
    if human and has_evidence and (agrees or multi_paper) and metadata_ok:
        return QualityTier.gold
    if human and has_evidence:
        return QualityTier.silver
    return QualityTier.rejected
