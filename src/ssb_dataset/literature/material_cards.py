"""Material Cards — automatic per-material structured summaries.

Built from the consensus database (the Material -> Paper -> Experiment ->
Measurement -> Evidence hierarchy) plus Materials Project structural metadata.
Every card answers, at a glance: what family, how many papers/measurements,
over what temperature range, what is the cross-paper consensus σ and Ea, how
confident is that consensus, and which papers / pages / sentences carry it.

The consensus score (0-100) is deterministic and statistical only:

  - n>=3 independent-paper σ records that AGREE within one order of magnitude
    is the strongest signal a literature dataset can have -> +40
  - each additional paper beyond 2 with a usable σ measurement -> +15 each
  - Ea agreement (n>=2, within 0.2 eV) -> +10
  - temperature coverage (>=1 record carries a measured T) -> +5
  - each 1.5-order outlier in the group -> -10

Score is clamped to [0, 100]. The card never edits values; it only reports
statistics so a human can judge confidence at a glance.

Usage:
    python scripts/build_material_cards.py
        # reads literature_output/consensus_db.json (+ canonical dataset)
        # writes literature_output/material_cards.json
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from statistics import median
from typing import Any

from ssb_dataset.literature.consensus_db import _normalize_temp

# Order-of-magnitude spread threshold for "in agreement" (matches consensus_db).
_AGREE_ORDER_SPREAD = 1.0
_Ea_AGREE_SPREAD_EV = 0.2


@dataclass
class MaterialCard:
    """A structured, human-readable summary of one material's literature."""
    material: str
    family: str
    n_papers: int
    n_sigma: int
    n_ea: int
    n_measurements: int
    sigma_values: list[float]
    ea_values: list[float]
    median_sigma: float | None
    sigma_ci95: tuple[float, float] | None
    min_sigma: float | None
    max_sigma: float | None
    sigma_mad_log10: float | None
    sigma_std_log10: float | None
    sigma_iqr_log10: float | None
    agreement_grade: str
    sigma_by_temp: list[dict]
    median_ea: float | None
    temperature_range_c: tuple[float, float] | None
    temperature_counts: int
    sigma_by_temp: list[dict]
    consensus_score: int
    consensus_verdict: str
    quality_score: int
    quality_grade: str
    metadata_completeness: float
    outliers: list[dict]
    dois: list[str]
    papers: list[dict]
    structure: dict[str, Any] | None

    def to_dict(self) -> dict[str, Any]:
        return {
            "material": self.material,
            "family": self.family,
            "n_papers": self.n_papers,
            "n_sigma": self.n_sigma,
            "n_ea": self.n_ea,
            "n_measurements": self.n_measurements,
            "median_sigma": self.median_sigma,
            "sigma_ci95": self.sigma_ci95,
            "min_sigma": self.min_sigma,
            "max_sigma": self.max_sigma,
            "sigma_mad_log10": self.sigma_mad_log10,
            "sigma_std_log10": self.sigma_std_log10,
            "sigma_iqr_log10": self.sigma_iqr_log10,
            "agreement_grade": self.agreement_grade,
            "sigma_by_temp": self.sigma_by_temp,
            "median_ea": self.median_ea,
            "temperature_range_c": self.temperature_range_c,
            "temperature_counts": self.temperature_counts,
            "consensus_score": self.consensus_score,
            "consensus_verdict": self.consensus_verdict,
            "quality_score": self.quality_score,
            "quality_grade": self.quality_grade,
            "metadata_completeness": self.metadata_completeness,
            "outliers": self.outliers,
            "dois": self.dois,
            "papers": self.papers,
            "structure": self.structure,
        }


def _verdict(score: int) -> str:
    if score >= 75:
        return "strong consensus"
    if score >= 50:
        return "moderate consensus"
    if score >= 25:
        return "weak consensus"
    return "no consensus"


# Grade scale for the agreement letter + quality letter grades.
_GRADE_RANK = {"A+": 5, "A": 4, "B": 3, "C": 2, "D": 1, "": 0}


def _quality_grade(score: int) -> str:
    if score >= 85:
        return "A"
    if score >= 70:
        return "B"
    if score >= 50:
        return "C"
    return "D"


def _quality_score(card_vals: dict) -> tuple[int, float]:
    """Deterministic 0-100 data-quality score for a material card.

    Weighting (scientific-value oriented):
      30  agreement grade (A+ = 30 ... D = 5)
      20  publication breadth (min(n_papers,5)/5 * 20)
      15  measurement depth (min(n_sigma,6)/6 * 15)
      15  metadata completeness (fraction of measurements carrying a
          temperature AND a measurement method — the two most load-bearing
          experimental fields)
      10  Ea availability (has Ea -> 10)
      10  outlier penalty (each 1.5-order outlier -5, floor 0)
    """
    grade = card_vals.get("agreement_grade", "")
    rank = _GRADE_RANK.get(grade, 0)
    score = rank / 5 * 30
    n_papers = card_vals.get("n_papers", 0)
    n_sigma = card_vals.get("n_sigma", 0)
    score += min(n_papers, 5) / 5 * 20
    score += min(n_sigma, 6) / 6 * 15
    completeness = card_vals.get("metadata_completeness", 0.0)
    score += completeness * 15
    if card_vals.get("n_ea", 0) > 0:
        score += 10
    score -= 5 * len(card_vals.get("outliers", []))
    score = max(0, min(100, score))
    return int(round(score)), completeness


def _metadata_completeness(measurements: list[dict]) -> float:
    """Fraction of σ-bearing measurements that carry BOTH temperature + method."""
    sig = [m for m in measurements if m.get("sigma_S_per_cm") is not None]
    if not sig:
        return 0.0
    complete = 0
    for m in sig:
        has_t = _normalize_temp(m.get("temperature_celsius")) is not None
        has_m = bool(m.get("measurement_method"))
        if has_t and has_m:
            complete += 1
    return complete / len(sig)


def _papers_from_measurements(measurements: list[dict]) -> list[dict]:
    """Group preserved measurements under their DOI (Material -> Paper -> ...)."""
    by_doi: dict[str, dict] = {}
    for m in measurements:
        doi = m.get("doi") or "unknown"
        p = by_doi.setdefault(doi, {
            "doi": doi,
            "measurements": [],
            "n_sigma": 0,
            "n_ea": 0,
        })
        is_sigma = m.get("sigma_S_per_cm") is not None
        is_ea = m.get("activation_energy_eV") is not None
        if is_sigma:
            p["n_sigma"] += 1
        if is_ea:
            p["n_ea"] += 1
        p["measurements"].append({
            "property": m.get("property", ""),
            "value": m.get("value"),
            "unit": m.get("unit"),
            "sigma_S_per_cm": m.get("sigma_S_per_cm"),
            "activation_energy_eV": m.get("activation_energy_eV"),
            "temperature_celsius": m.get("temperature_celsius"),
            "reviewer": m.get("reviewer", ""),
            "page": m.get("page"),
            "section": m.get("section", ""),
            "table_number": m.get("table_number", ""),
            "evidence_sentence": m.get("evidence_sentence", ""),
            "measurement_method": m.get("measurement_method", ""),
            "conductivity_type": m.get("conductivity_type", ""),
        })
    papers = list(by_doi.values())
    papers.sort(key=lambda p: (p["n_sigma"] + p["n_ea"]), reverse=True)
    return papers


def _score_consensus(card_vals: dict) -> int:
    n_sigma = card_vals["n_sigma"]
    sigma_values = card_vals["sigma_values"]
    ea_values = card_vals["ea_values"]
    outliers = card_vals["outliers"]
    temp_counts = card_vals["temp_counts"]

    score = 0
    n_papers_agree = 0
    if n_sigma >= 1 and len(sigma_values) >= 1:
        logs = sorted(math.log10(v) for v in sigma_values if v and v > 0)
        if len(logs) >= 1:
            med = median(logs)
            n_papers_agree = sum(1 for l in logs if abs(l - med) <= _AGREE_ORDER_SPREAD)
    if n_sigma >= 3 and n_papers_agree >= 3:
        score += 40
    elif n_sigma >= 2 and n_papers_agree >= 2:
        score += 25
    elif n_sigma >= 1:
        score += 10
    score += 15 * max(0, n_papers_agree - 2)
    if len(ea_values) >= 2 and abs(max(ea_values) - min(ea_values)) <= _Ea_AGREE_SPREAD_EV:
        score += 10
    elif len(ea_values) == 1:
        score += 4
    if temp_counts >= 1:
        score += 5
    score -= 10 * len(outliers)
    return max(0, min(100, score))


def build_material_card(group: str, consensus: dict[str, Any],
                        structure_lookup: dict[str, dict] | None = None) -> MaterialCard:
    """Build a MaterialCard from one entry of the consensus DB (dict form)."""
    measurements = consensus.get("measurements", [])
    outliers = consensus.get("outliers", [])
    # Recover the raw per-record values from the preserved measurement detail
    # (consensus_db.json stores aggregates; measurements carry the full chain).
    sigma_values = []
    ea_values = []
    for m in measurements:
        s = m.get("sigma_S_per_cm")
        e = m.get("activation_energy_eV")
        if s is not None:
            try:
                sigma_values.append(float(s))
            except (TypeError, ValueError):
                pass
        if e is not None:
            try:
                ea_values.append(float(e))
            except (TypeError, ValueError):
                pass
    if not sigma_values and consensus.get("sigma_values"):
        sigma_values = [float(v) for v in consensus["sigma_values"]]
    if not sigma_values and consensus.get("median_sigma") is not None:
        sigma_values = [consensus["median_sigma"]]
    if not ea_values and consensus.get("ea_values"):
        ea_values = [float(v) for v in consensus["ea_values"]]

    temps = []
    for m in measurements:
        t = m.get("temperature_celsius")
        if isinstance(t, (int, float)):
            temps.append(float(t))
        elif isinstance(t, dict):
            lo = t.get("min_K") or t.get("min_C") or t.get("min")
            hi = t.get("max_K") or t.get("max_C") or t.get("max")
            if lo is not None and hi is not None:
                try:
                    temps.append((float(lo) + float(hi)) / 2)
                except (TypeError, ValueError):
                    pass
    temp_range = (min(temps), max(temps)) if len(temps) >= 2 else None
    if len(temps) == 1:
        temp_range = (temps[0], temps[0])

    families = consensus.get("families") or []
    vals = {
        "n_sigma": consensus.get("n_sigma", 0),
        "sigma_values": sigma_values,
        "ea_values": ea_values,
        "outliers": outliers,
        "temp_counts": len(temps),
    }
    score = _score_consensus(vals)
    structure = (structure_lookup or {}).get(group)
    completeness = _metadata_completeness(measurements)
    quality, _ = _quality_score({
        "agreement_grade": consensus.get("agreement_grade", ""),
        "n_papers": consensus.get("n_papers", 0),
        "n_sigma": consensus.get("n_sigma", 0),
        "n_ea": consensus.get("n_ea", 0),
        "metadata_completeness": completeness,
        "outliers": outliers,
    })

    return MaterialCard(
        material=group,
        family=families[0] if families else "unknown",
        n_papers=consensus.get("n_papers", 0),
        n_sigma=consensus.get("n_sigma", 0),
        n_ea=consensus.get("n_ea", 0),
        n_measurements=len(measurements),
        sigma_values=sigma_values,
        ea_values=ea_values,
        median_sigma=consensus.get("median_sigma"),
        sigma_ci95=consensus.get("sigma_ci95"),
        min_sigma=consensus.get("min_sigma"),
        max_sigma=consensus.get("max_sigma"),
        sigma_mad_log10=consensus.get("sigma_mad_log10"),
        sigma_std_log10=consensus.get("sigma_std_log10"),
        sigma_iqr_log10=consensus.get("sigma_iqr_log10"),
        agreement_grade=consensus.get("agreement_grade", ""),
        median_ea=consensus.get("median_ea"),
        temperature_range_c=temp_range,
        temperature_counts=len(temps),
        sigma_by_temp=consensus.get("sigma_by_temp", []),
        consensus_score=score,
        consensus_verdict=_verdict(score),
        quality_score=quality,
        quality_grade=_quality_grade(quality),
        metadata_completeness=round(completeness, 3),
        outliers=outliers,
        dois=sorted(set(consensus.get("dois", []))),
        papers=_papers_from_measurements(measurements),
        structure=structure,
    )


def build_all_cards(consensus_db: dict[str, dict[str, Any]],
                    structure_lookup: dict[str, dict] | None = None) -> dict[str, MaterialCard]:
    cards = {}
    for group, cons in consensus_db.items():
        cards[group] = build_material_card(group, cons, structure_lookup)
    return cards
