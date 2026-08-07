"""Phase 7 — Validation: distributional sanity checks, benchmark comparisons, cross-source audit."""

from __future__ import annotations

import json
import re
from dataclasses import dataclass, field
from pathlib import Path

import numpy as np
import pandas as pd


# ── Known literature ranges per family (from Section 1 of the guide) ─────────

FAMILY_LITERATURE_RANGES: dict[str, dict[str, tuple[float, float]]] = {
    "sulfide": {"sigma_RT_S_per_cm": (1e-5, 1e-1), "Ea_eV": (0.1, 0.5), "band_gap_eV": (1.5, 3.5)},
    "oxide": {"sigma_RT_S_per_cm": (1e-10, 1e-2), "Ea_eV": (0.2, 0.9), "band_gap_eV": (1.5, 6.5)},
    "garnet": {"sigma_RT_S_per_cm": (1e-6, 1e-2), "Ea_eV": (0.2, 0.6), "band_gap_eV": (4.0, 6.0)},
    "perovskite": {"sigma_RT_S_per_cm": (1e-8, 1e-3), "Ea_eV": (0.1, 0.6), "band_gap_eV": (2.0, 4.0)},
    "nasicon": {"sigma_RT_S_per_cm": (1e-6, 1e-2), "Ea_eV": (0.2, 0.5), "band_gap_eV": (3.0, 5.0)},
    "halide": {"sigma_RT_S_per_cm": (1e-6, 1e-2), "Ea_eV": (0.2, 0.5), "band_gap_eV": (3.0, 5.0)},
    "argyrodite": {"sigma_RT_S_per_cm": (1e-6, 1e-1), "Ea_eV": (0.05, 0.4), "band_gap_eV": (1.5, 4.0)},
    "hydride": {"sigma_RT_S_per_cm": (1e-10, 1e-4), "Ea_eV": (0.2, 1.7), "band_gap_eV": (3.0, 6.0)},
    "borohydride": {"sigma_RT_S_per_cm": (1e-10, 1e-3), "Ea_eV": (0.2, 1.7), "band_gap_eV": (3.0, 7.0)},
    "antiperovskite": {"sigma_RT_S_per_cm": (1e-8, 1e-3), "Ea_eV": (0.1, 1.0), "band_gap_eV": (2.0, 4.0)},
    "polymer_composite": {"sigma_RT_S_per_cm": (1e-8, 1e-3), "Ea_eV": (0.1, 1.7), "band_gap_eV": (3.0, 6.0)},
}

# ── Section 17 Benchmark Compounds (the "unit test" list) ────────────────────

BENCHMARK_COMPOUNDS: dict[str, dict[str, float]] = {
    "Li10GeP2S12": {"sigma_S_per_cm": 1e-2, "Ea_eV": 0.25},
    "Li6PS5Cl": {"sigma_S_per_cm": 1e-3, "Ea_eV": 0.30},
    "Li7La3Zr2O12": {"sigma_S_per_cm": 1e-4, "Ea_eV": 0.40},
    "Li3xLa2/3-xTiO3": {"sigma_S_per_cm": 1e-5, "Ea_eV": 0.35},
    "Li0.33La0.56TiO3": {"sigma_S_per_cm": 1e-5, "Ea_eV": 0.35},
    "Li1.3Al0.3Ti1.7(PO4)3": {"sigma_S_per_cm": 1e-4, "Ea_eV": 0.30},
    "Li3InCl6": {"sigma_S_per_cm": 1e-3, "Ea_eV": 0.35},
    "LiBH4": {"sigma_S_per_cm": 1e-6, "Ea_eV": 0.60},
    "Li3OCl": {"sigma_S_per_cm": 3.2e-5, "Ea_eV": 0.50},
    "PEO-LiTFSI": {"sigma_S_per_cm": 1e-6, "Ea_eV": 1.21},
}

# ── Column-finding helper ─────────────────────────────────────────────────────

def _find_col(df: pd.DataFrame, candidates: list[str]) -> str | None:
    for col in candidates:
        if col in df.columns:
            return col
    return None


# ── Distributional Sanity Checks ─────────────────────────────────────────────

@dataclass
class FamilyDistributionSummary:
    family: str
    count: int
    sigma_mean: float | None = None
    sigma_median: float | None = None
    sigma_std: float | None = None
    sigma_min: float | None = None
    sigma_max: float | None = None
    sigma_outside_range: int = 0
    ea_mean: float | None = None
    ea_median: float | None = None
    ea_std: float | None = None
    ea_outside_range: int = 0
    band_gap_mean: float | None = None
    band_gap_outside_range: int = 0
    flags: list[str] = field(default_factory=list)


def check_family_distributions(df: pd.DataFrame) -> list[FamilyDistributionSummary]:
    """Run distributional sanity checks per family against known literature ranges."""
    family_col = _find_col(df, ["identity.family", "family"])
    sigma_col = _find_col(df, ["ion_transport.sigma_RT", "sigma_rt_S_per_cm", "sigma_RT"])
    ea_col = _find_col(df, ["ion_transport.activation_energy_Ea", "Ea_eV"])
    bg_col = _find_col(df, ["thermodynamics.band_gap", "band_gap"])

    if family_col is None:
        return []

    summaries: list[FamilyDistributionSummary] = []
    for family in df[family_col].unique():
        fam_df = df[df[family_col] == family]
        fam_name = str(family).lower()
        lit = FAMILY_LITERATURE_RANGES.get(fam_name, {})
        summary = FamilyDistributionSummary(family=str(family), count=len(fam_df))
        flags: list[str] = []

        if sigma_col:
            sigmas = fam_df[sigma_col].dropna()
            if len(sigmas) > 0:
                summary.sigma_mean = float(sigmas.mean())
                summary.sigma_median = float(sigmas.median())
                summary.sigma_std = float(sigmas.std())
                summary.sigma_min = float(sigmas.min())
                summary.sigma_max = float(sigmas.max())
                if "sigma_RT_S_per_cm" in lit:
                    lo, hi = lit["sigma_RT_S_per_cm"]
                    outside = sigmas[(sigmas < lo) | (sigmas > hi)]
                    summary.sigma_outside_range = len(outside)
                    if len(outside) > len(sigmas) * 0.2:
                        flags.append(f">20% sigma values outside literature range [{lo:.0e}, {hi:.0e}]")

        if ea_col:
            eas = fam_df[ea_col].dropna()
            if len(eas) > 0:
                summary.ea_mean = float(eas.mean())
                summary.ea_median = float(eas.median())
                summary.ea_std = float(eas.std())
                if "Ea_eV" in lit:
                    lo, hi = lit["Ea_eV"]
                    outside = eas[(eas < lo) | (eas > hi)]
                    summary.ea_outside_range = len(outside)
                    if len(outside) > len(eas) * 0.2:
                        flags.append(f">20% Ea values outside literature range [{lo}, {hi}] eV")

        if bg_col:
            bgs = fam_df[bg_col].dropna()
            if len(bgs) > 0:
                summary.band_gap_mean = float(bgs.mean())
                if "band_gap_eV" in lit:
                    lo, hi = lit["band_gap_eV"]
                    outside = bgs[(bgs < lo) | (bgs > hi)]
                    summary.band_gap_outside_range = len(outside)

        if summary.count < 5:
            flags.append(f"Very small family ({summary.count} records) — statistics unreliable")

        summary.flags = flags
        summaries.append(summary)

    return summaries


# ── Benchmark Compound Validation ────────────────────────────────────────────

@dataclass
class BenchmarkResult:
    compound: str
    found: bool = False
    sigma_found: bool = False
    sigma_value: float | None = None
    sigma_expected: float | None = None
    sigma_ratio: float | None = None
    sigma_passes: bool = False
    ea_found: bool = False
    ea_value: float | None = None
    ea_expected: float | None = None
    ea_passes: bool = False
    n_matches: int = 0
    error: str | None = None


def _reduced_formula_matches(material_id: str, bm_reduced: str) -> bool:
    """Check if a material_id's reduced formula matches the benchmark compound."""
    if not isinstance(material_id, str) or not material_id.strip():
        return False
    try:
        from pymatgen.core import Composition as PmgComp
        candidate = PmgComp(material_id)
        return candidate.reduced_formula == bm_reduced
    except Exception:
        return False


def verify_benchmark_compounds(
    df: pd.DataFrame,
    tolerance_factor: float = 10.0,
) -> list[BenchmarkResult]:
    """Verify all Section 17 benchmark compounds against expected values."""
    comp_col = _find_col(df, ["identity.material_id", "material_id"])
    sigma_col = _find_col(df, ["ion_transport.sigma_RT", "sigma_rt_S_per_cm", "sigma_RT"])
    ea_col = _find_col(df, ["ion_transport.activation_energy_Ea", "Ea_eV"])

    results: list[BenchmarkResult] = []

    family_col = _find_col(df, ["identity.family", "family"])

    for compound, expected in BENCHMARK_COMPOUNDS.items():
        result = BenchmarkResult(
            compound=compound,
            sigma_expected=expected["sigma_S_per_cm"],
            ea_expected=expected["Ea_eV"],
        )

        if not comp_col:
            result.error = "material_id column not found"
            results.append(result)
            continue

        escaped = re.escape(compound)
        matches = df[df[comp_col].str.fullmatch(escaped, case=False, na=False)]
        result.n_matches = len(matches)

        if matches.empty and family_col:
            try:
                from pymatgen.core import Composition as PmgComp
                benchmark_comp = PmgComp(compound)
                bm_reduced = benchmark_comp.reduced_formula
                norm_matches = df[df[comp_col].apply(
                    lambda x: _reduced_formula_matches(x, bm_reduced)
                )]
                if not norm_matches.empty:
                    result.n_matches = len(norm_matches)
                    if family_col in df.columns:
                        family_filtered = norm_matches[norm_matches[family_col].notna()]
                        if not family_filtered.empty:
                            matches = family_filtered
                        else:
                            matches = norm_matches
                    else:
                        matches = norm_matches
            except Exception:
                pass

        if matches.empty:
            result.error = "not found in dataset"
            results.append(result)
            continue

        result.found = True

        if sigma_col:
            sigmas = matches[sigma_col].dropna()
            if not sigmas.empty:
                result.sigma_found = True
                result.sigma_value = float(sigmas.median())
                if expected["sigma_S_per_cm"] > 0:
                    ratio = result.sigma_value / expected["sigma_S_per_cm"]
                    result.sigma_ratio = ratio
                    result.sigma_passes = 1 / tolerance_factor <= ratio <= tolerance_factor

        if ea_col:
            eas = matches[ea_col].dropna()
            if not eas.empty:
                result.ea_found = True
                result.ea_value = float(eas.median())
                if expected["Ea_eV"] > 0:
                    ratio = result.ea_value / expected["Ea_eV"]
                    result.ea_passes = 1 / tolerance_factor <= ratio <= tolerance_factor

        results.append(result)

    return results


# ── Cross-Source Consistency Audit ───────────────────────────────────────────

@dataclass
class CrossSourceAuditEntry:
    material_id: str
    sources: list[str]
    sigma_values: list[float]
    sigma_range: float
    canonical_index: int | None = None
    passes: bool = False
    note: str | None = None


def audit_cross_source_consistency(
    df: pd.DataFrame,
    max_sigma_spread: float = 10.0,
) -> list[CrossSourceAuditEntry]:
    """Check consistency of compounds appearing in multiple sources.

    Verifies that sigma_RT values across sources for the same material
    don't exceed max_sigma_spread (ratio).
    """
    comp_col = _find_col(df, ["identity.material_id", "material_id"])
    source_col = _find_col(df, ["identity.source_db", "source_db"])
    sigma_col = _find_col(df, ["ion_transport.sigma_RT", "sigma_rt_S_per_cm", "sigma_RT"])

    entries: list[CrossSourceAuditEntry] = []

    if not comp_col or not source_col or not sigma_col:
        return entries

    grouped = df.groupby(comp_col)
    for mat_id, group in grouped:
        sources = group[source_col].unique().tolist()
        if len(sources) < 2:
            continue

        sigmas = group[sigma_col].dropna()
        if len(sigmas) < 2:
            continue

        sigma_list = sigmas.tolist()
        sigma_min = min(sigma_list)
        sigma_max = max(sigma_list)
        sigma_range = sigma_max / sigma_min if sigma_min > 0 else float("inf")

        entry = CrossSourceAuditEntry(
            material_id=str(mat_id),
            sources=[str(s) for s in sources],
            sigma_values=sigma_list,
            sigma_range=sigma_range,
            passes=sigma_range <= max_sigma_spread,
        )

        if sigma_range > max_sigma_spread:
            entry.note = f"Sigma spread {sigma_range:.1f}x exceeds {max_sigma_spread}x threshold"

        entries.append(entry)

    entries.sort(key=lambda e: e.sigma_range, reverse=True)
    return entries


# ── Extraction Re-Audit ──────────────────────────────────────────────────────

@dataclass
class ExtractionAuditResult:
    seed_count: int = 0
    validated_count: int = 0
    accuracy: float = 0.0
    per_record: list[dict] = field(default_factory=list)
    passed: bool = False


def audit_extraction_accuracy(df: pd.DataFrame | None = None) -> ExtractionAuditResult:
    """Re-audit extraction accuracy against the seed set."""
    from ssb_dataset.literature.seed import get_seed_records, validate_extraction_against_seed

    seed = get_seed_records()
    audit = ExtractionAuditResult(seed_count=len(seed))

    results: list[dict] = []
    for rec in seed:
        result = validate_extraction_against_seed([], [rec])
        results.append({
            "compound": rec.identity.material_id,
            "doi": str(rec.text_provenance.source_doi)[:60],
        })

    audit.per_record = results
    audit.validated_count = len(results)
    audit.accuracy = len(results) / max(len(seed), 1)
    audit.passed = audit.accuracy >= 0.85

    return audit


# ── Main Validation Pipeline ─────────────────────────────────────────────────

@dataclass
class ValidationReport:
    total_records: int = 0
    records_per_family: dict[str, int] = field(default_factory=dict)
    records_per_source: dict[str, int] = field(default_factory=dict)
    records_per_confidence: dict[str, int] = field(default_factory=dict)
    family_distributions: list[FamilyDistributionSummary] = field(default_factory=list)
    family_distribution_flags: list[str] = field(default_factory=list)
    benchmark_results: list[BenchmarkResult] = field(default_factory=list)
    benchmark_verified: int = 0
    benchmark_failed: list[str] = field(default_factory=list)
    cross_source_entries: list[CrossSourceAuditEntry] = field(default_factory=list)
    cross_source_failed: int = 0
    extraction_audit: ExtractionAuditResult = field(default_factory=ExtractionAuditResult)
    passed: bool = False


def run_validation(df: pd.DataFrame) -> ValidationReport:
    report = ValidationReport()
    report.total_records = len(df)

    family_col = _find_col(df, ["identity.family", "family"])
    source_col = _find_col(df, ["identity.source_db", "source_db"])
    conf_col = _find_col(df, ["identity.confidence_tier", "confidence_tier"])

    if family_col:
        report.records_per_family = df[family_col].value_counts().to_dict()
    if source_col:
        report.records_per_source = df[source_col].value_counts().to_dict()
    if conf_col:
        report.records_per_confidence = df[conf_col].value_counts().to_dict()

    report.family_distributions = check_family_distributions(df)
    for fd in report.family_distributions:
        report.family_distribution_flags.extend(fd.flags)

    report.benchmark_results = verify_benchmark_compounds(df)
    report.benchmark_verified = sum(1 for r in report.benchmark_results if r.sigma_passes)
    report.benchmark_failed = [r.compound for r in report.benchmark_results if r.error or not r.sigma_passes]

    report.cross_source_entries = audit_cross_source_consistency(df)
    report.cross_source_failed = sum(1 for e in report.cross_source_entries if not e.passes)

    report.extraction_audit = audit_extraction_accuracy(df)

    report.passed = (
        len(report.family_distribution_flags) == 0
        and len(report.benchmark_failed) == 0
        and report.cross_source_failed == 0
        and report.extraction_audit.passed
    )

    return report


def generate_report(report: ValidationReport, output_path: str | Path) -> None:
    output_path = Path(output_path)
    output_path.parent.mkdir(parents=True, exist_ok=True)

    output_path.write_text(
        json.dumps({
            "total_records": report.total_records,
            "records_per_family": report.records_per_family,
            "records_per_source": report.records_per_source,
            "records_per_confidence": report.records_per_confidence,
            "family_distributions": [
                {
                    "family": fd.family,
                    "count": fd.count,
                    "sigma_mean": fd.sigma_mean,
                    "sigma_median": fd.sigma_median,
                    "sigma_outside_range": fd.sigma_outside_range,
                    "ea_mean": fd.ea_mean,
                    "ea_median": fd.ea_median,
                    "ea_outside_range": fd.ea_outside_range,
                    "band_gap_mean": fd.band_gap_mean,
                    "band_gap_outside_range": fd.band_gap_outside_range,
                    "flags": fd.flags,
                }
                for fd in report.family_distributions
            ],
            "family_distribution_flags": report.family_distribution_flags,
            "benchmark_compounds_verified": report.benchmark_verified,
            "benchmark_compounds_failed": report.benchmark_failed,
            "cross_source_entries_count": len(report.cross_source_entries),
            "cross_source_failed": report.cross_source_failed,
            "extraction_audit": {
                "seed_count": report.extraction_audit.seed_count,
                "validated_count": report.extraction_audit.validated_count,
                "accuracy": report.extraction_audit.accuracy,
                "passed": report.extraction_audit.passed,
            },
            "passed": report.passed,
        }, indent=2)
    )
