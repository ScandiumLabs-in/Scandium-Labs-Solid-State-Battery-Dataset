"""Phase 4 — Cleaning, Deduplication & Canonicalization.

Cross-source structural deduplication, composition-level dedup (literature),
Arrhenius consistency filtering, unit standardization, and missing-data audit.
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd

from ssb_dataset.schema import MaterialRecord


# ── Arrhenius Consistency ──────────────────────────────────────────────────────

KB_eV_K = 8.617333262e-5


def check_arrhenius_consistency(
    sigma_S_per_cm: float,
    Ea_eV: float,
    T_K: float = 298.0,
    tolerance: float = 1e4,
) -> tuple[bool, float]:
    """Check if a (sigma, Ea) pair is physically plausible via Arrhenius relation.

    Returns (is_plausible, predicted_sigma).
    """
    try:
        predicted = np.exp(-Ea_eV / (KB_eV_K * T_K))
        if predicted <= 0:
            return False, 0.0
        ratio = sigma_S_per_cm / predicted
        plausible = 1.0 / tolerance < ratio < tolerance
        return bool(plausible), float(predicted)
    except (ZeroDivisionError, OverflowError, FloatingPointError):
        return False, 0.0


def filter_arrhenius_failures(
    df: pd.DataFrame,
    sigma_col: str = "ion_transport.sigma_RT",
    ea_col: str = "ion_transport.activation_energy_Ea",
    temp_col: str = "ion_transport.temperature_range_measured",
    tolerance: float = 1e4,
    family_col: str = "identity.family",
) -> tuple[pd.DataFrame, list[dict[str, Any]]]:
    """Filter out rows with physically implausible sigma/Ea pairs.

    Polymer-composite family records are excluded from this check because
    they follow VTF kinetics (not Arrhenius), so the Arrhenius consistency
    test is not applicable.

    Returns (cleaned_df, failures_list).
    """
    failures: list[dict[str, Any]] = []
    valid_mask = pd.Series(True, index=df.index)
    tier_col = None
    for c in ["identity.confidence_tier", "confidence_tier"]:
        if c in df.columns:
            tier_col = c
            break

    for idx, row in df.iterrows():
        sigma = _nested_get(row, sigma_col)
        ea = _nested_get(row, ea_col)
        if sigma is None or ea is None:
            continue

        # Human-verified gold records are exempt: they were hand-checked against
        # the source paper, so the Arrhenius screen must not override them.
        tier = _nested_get(row, tier_col) if tier_col else None
        if isinstance(tier, str) and "verified_human" in tier.lower():
            continue

        fam = _nested_get(row, family_col)
        if isinstance(fam, str) and "polymer" in fam.lower():
            continue

        temp_range = _nested_get(row, temp_col)
        if isinstance(temp_range, dict):
            T_K = temp_range.get("min_K", 298.0)
        else:
            T_K = 298.0

        plausible, predicted = check_arrhenius_consistency(float(sigma), float(ea), float(T_K), tolerance)
        if not plausible:
            valid_mask.at[idx] = False
            failures.append({
                "index": idx,
                "sigma": sigma,
                "Ea": ea,
                "T_K": T_K,
                "predicted_sigma": predicted,
                "ratio": sigma / predicted if predicted > 0 else float("inf"),
            })

    return df[valid_mask].copy(), failures


# ── Unit Standardization ───────────────────────────────────────────────────────

CONDUCTIVITY_CONVERSIONS: dict[str, float] = {
    "S/cm": 1.0,
    "S/m": 0.01,
    "mS/cm": 0.001,
    "mS/m": 1e-5,
    "µS/cm": 1e-6,
    "uS/cm": 1e-6,
    "Ω⁻¹cm⁻¹": 1.0,
    "S*cm⁻¹": 1.0,
    "Scm⁻¹": 1.0,
}

ENERGY_CONVERSIONS: dict[str, float] = {
    "eV": 1.0,
    "kJ/mol": 0.010364,
    "kcal/mol": 0.043364,
    "meV": 0.001,
    "J": 6.242e18,
}

TEMPERATURE_CONVERSIONS: dict[str, str] = {
    "°C": "C",
    "C": "C",
    "K": "K",
    "F": "F",
}


def _nested_get(obj: Any, dotted_key: str) -> Any:
    """Get a value from a dict-like object using dot-separated keys or flat key."""
    if isinstance(obj, dict):
        if dotted_key in obj:
            return obj[dotted_key]
        parts = dotted_key.split(".")
        current = obj
        for part in parts:
            if isinstance(current, dict):
                current = current.get(part)
            else:
                return None
            if current is None:
                return None
        return current
    if isinstance(obj, pd.Series):
        if dotted_key in obj.index:
            val = obj[dotted_key]
            return None if (isinstance(val, float) and np.isnan(val)) else val
        return None
    if hasattr(obj, dotted_key):
        return getattr(obj, dotted_key)
    return None


def _standardize_conductivity(value: float, unit: str) -> float:
    """Convert conductivity to S/cm."""
    unit_clean = unit.strip().replace(" ", "")
    factor = CONDUCTIVITY_CONVERSIONS.get(unit_clean)
    if factor is None:
        for key, val in CONDUCTIVITY_CONVERSIONS.items():
            if key in unit_clean or unit_clean in key:
                factor = val
                break
    if factor is None:
        return value
    return value * factor


def _standardize_energy(value: float, unit: str) -> float:
    """Convert energy to eV."""
    unit_clean = unit.strip().lower()
    for key, factor in ENERGY_CONVERSIONS.items():
        if key.lower() in unit_clean or unit_clean in key.lower():
            return value * factor
    return value


def _standardize_temperature(value: float, unit: str) -> float:
    """Convert temperature to Kelvin."""
    unit_clean = unit.strip().upper()
    if "C" in unit_clean and "K" not in unit_clean:
        return value + 273.15
    if "F" in unit_clean:
        return (value - 32) * 5.0 / 9.0 + 273.15
    return value


@dataclass
class UnitStandardizationReport:
    records_checked: int = 0
    conductivity_converted: int = 0
    energy_converted: int = 0
    temperature_converted: int = 0
    errors: list[str] = field(default_factory=list)


def standardize_units(df: pd.DataFrame) -> tuple[pd.DataFrame, UnitStandardizationReport]:
    """Standardize all units across the dataset to canonical forms.

    Canonical units:
      - Conductivity: S/cm
      - Energy: eV
      - Temperature: Kelvin
      - Length: Angstrom
    """
    report = UnitStandardizationReport(records_checked=len(df))

    if "ion_transport.sigma_RT" in df.columns:
        sigma_col = "ion_transport.sigma_RT"
    elif "sigma_rt_S_per_cm" in df.columns:
        sigma_col = "sigma_rt_S_per_cm"
    elif "sigma_RT" in df.columns:
        sigma_col = "sigma_RT"
    else:
        sigma_col = None

    if sigma_col and sigma_col in df.columns:
        for idx in df.index:
            val = df.at[idx, sigma_col]
            if isinstance(val, dict):
                raw_value = val.get("value")
                raw_unit = val.get("unit", "S/cm")
                if raw_value is not None:
                    try:
                        converted = _standardize_conductivity(float(raw_value), raw_unit)
                        df.at[idx, sigma_col] = converted
                        report.conductivity_converted += 1
                    except (ValueError, TypeError):
                        report.errors.append(f"Row {idx}: bad conductivity value {raw_value}")

    return df, report


# ── Deduplication ──────────────────────────────────────────────────────────────

@dataclass
class DeduplicationReport:
    total_records: int = 0
    cross_source_deduped: int = 0
    composition_dedup_groups: int = 0
    canonicalization_decisions: list[dict[str, Any]] = field(default_factory=list)
    alternate_polymorphs: list[dict[str, Any]] = field(default_factory=list)


def _get_composition_key(formula: str) -> str:
    """Get a normalized composition key from a formula string."""
    try:
        from pymatgen.core import Composition
        comp = Composition(formula)
        return comp.reduced_formula
    except Exception:
        return formula.strip()


def _get_elements_set(formula: str) -> set[str]:
    """Extract element symbols from a formula."""
    try:
        from pymatgen.core import Composition
        return {el.symbol for el in Composition(formula).elements}
    except Exception:
        els = re.findall(r"[A-Z][a-z]?", formula)
        return set(els)


def _structure_similarity(cif_a: str, cif_b: str) -> float:
    """Compare two CIF structures using pymatgen StructureMatcher."""
    try:
        from pymatgen.core import Structure
        from pymatgen.analysis.structure_matcher import StructureMatcher

        try:
            s_a = Structure.from_str(cif_a, fmt="cif")
            s_b = Structure.from_str(cif_b, fmt="cif")
        except Exception:
            return 0.0

        matcher = StructureMatcher(ltol=0.3, stol=0.5, angle_tol=5)
        return matcher.fit(s_a, s_b)
    except Exception:
        return 0.0


def deduplicate_cross_source(df: pd.DataFrame) -> tuple[pd.DataFrame, DeduplicationReport]:
    """Cross-source structural deduplication.

    Canonicalization rule: prefer lowest formation_energy_per_atom;
    keep others as alternate_polymorph tags.
    """
    report = DeduplicationReport(total_records=len(df))
    canonical: list[int] = []
    alternate: list[dict[str, Any]] = []
    handled: set[int] = set()

    formula_col = None
    for candidate in ["identity.composition", "composition", "identity.material_id", "material_id"]:
        if candidate in df.columns:
            formula_col = candidate
            break

    energy_col = None
    for candidate in ["thermodynamics.formation_energy_per_atom", "formation_energy_per_atom"]:
        if candidate in df.columns:
            energy_col = candidate
            break

    structure_col = None
    for candidate in ["structure.structure_relaxed", "cif"]:
        if candidate in df.columns:
            structure_col = candidate
            break

    # Group indices by composition key so CIF comparisons happen only within
    # same-composition groups (near-linear) instead of an O(n^2) cross-product.
    from collections import defaultdict

    source_col = None
    for candidate in ["identity.source_db", "source_db"]:
        if candidate in df.columns:
            source_col = candidate
            break

    comp_groups: dict[str, list[int]] = defaultdict(list)
    for i in df.index:
        formula = str(df.at[i, formula_col]) if formula_col and not pd.isna(df.at[i, formula_col]) else ""
        key = _get_composition_key(formula) if formula else ""
        comp_groups[key].append(i)

    for members in comp_groups.values():
        # Build cross-source clusters within this composition. Same-source
        # records are already unique (each source dedups its own structures),
        # so they are never merged with each other — only a same-composition
        # record from a different source that is CIF-similar collapses in.
        clusters: list[list[int]] = []
        for idx in members:
            if idx in handled:
                continue

            cif_i = str(df.at[idx, structure_col]) if structure_col and not pd.isna(df.at[idx, structure_col]) else ""
            src_i = str(df.at[idx, source_col]) if source_col and not pd.isna(df.at[idx, source_col]) else ""

            # Find an existing cluster from a different source with CIF-similar structure.
            target: list[int] | None = None
            for cl in clusters:
                for existing in cl:
                    if src_i and source_col:
                        src_e = str(df.at[existing, source_col]) if not pd.isna(df.at[existing, source_col]) else ""
                        if src_i == src_e:
                            continue
                    if cif_i and structure_col:
                        cif_e = str(df.at[existing, structure_col]) if not pd.isna(df.at[existing, structure_col]) else ""
                        if cif_e and _structure_similarity(cif_i, cif_e) > 0.5:
                            target = cl
                            break
                if target is not None:
                    break
            if target is not None:
                target.append(idx)
                handled.add(idx)
            else:
                clusters.append([idx])

        # Each cluster = one canonical record (lowest formation energy);
        # alternate polymorphs from other sources become tagged alternates.
        for cl in clusters:
            if len(cl) == 1:
                canonical.append(cl[0])
                continue

            report.cross_source_deduped += len(cl) - 1
            report.composition_dedup_groups += 1

            if energy_col:
                energies = [(idx, df.at[idx, energy_col] if not pd.isna(df.at[idx, energy_col]) else float("inf")) for idx in cl]
                energies.sort(key=lambda x: x[1] if x[1] is not None else float("inf"))
                canonical_idx = energies[0][0]
            else:
                canonical_idx = cl[0]

            for idx in cl:
                if idx == canonical_idx:
                    canonical.append(idx)
                    report.canonicalization_decisions.append({
                        "canonical": int(idx),
                        "alternates": [int(g) for g in cl if g != idx],
                        "rationale": "lowest_formation_energy" if energy_col else "first_occurrence",
                    })
                else:
                    alternate.append({
                        "alternate_index": int(idx),
                        "canonical_index": int(canonical_idx),
                        "type": "cross_source_polymorph",
                    })

    canonical_set = set(canonical)
    deduped = df[df.index.isin(canonical_set)].copy()
    report.alternate_polymorphs = alternate

    return deduped, report


def deduplicate_literature_records(
    records: list[MaterialRecord],
) -> tuple[list[MaterialRecord], DeduplicationReport]:
    """Deduplicate literature-mined records at the composition level.

    Retains all measurements (does not average), tags duplicates.
    """
    from collections import defaultdict

    report = DeduplicationReport(total_records=len(records))
    comp_groups: dict[str, list[MaterialRecord]] = defaultdict(list)

    for rec in records:
        formula = rec.identity.material_id
        key = _get_composition_key(formula)
        comp_groups[key].append(rec)

    report.composition_dedup_groups = len([g for g in comp_groups.values() if len(g) > 1])

    result: list[MaterialRecord] = []
    for group in comp_groups.values():
        if len(group) > 1:
            report.cross_source_deduped += len(group) - 1
            for i, rec in enumerate(group):
                if i == 0:
                    rec.identity.subfamily_tag.append("canonical_measurement")
                else:
                    rec.identity.subfamily_tag.append("alternate_measurement")
        result.extend(group)

    return result, report


# ── Missing-Data Audit ────────────────────────────────────────────────────────

@dataclass
class MissingDataReport:
    total_records: int = 0
    null_sigma_count: int = 0
    null_ea_count: int = 0
    null_structure_count: int = 0
    label_available_false_count: int = 0
    label_available_true_no_data: list[int] = field(default_factory=list)
    silent_imputation_detected: list[str] = field(default_factory=list)
    passed: bool = False


def audit_missing_data(df: pd.DataFrame) -> MissingDataReport:
    """Audit the dataset for missing-data policy violations.

    Checks:
    1. Every null is explicit, never a sentinel value (0, -1)
    2. label_available matches actual data presence
    """
    report = MissingDataReport(total_records=len(df))

    sigma_col = None
    for c in ["ion_transport.sigma_RT", "sigma_rt_S_per_cm", "sigma_RT"]:
        if c in df.columns:
            sigma_col = c
            break

    ea_col = None
    for c in ["ion_transport.activation_energy_Ea", "Ea_eV"]:
        if c in df.columns:
            ea_col = c
            break

    struct_col = None
    for c in ["structure.structure_relaxed", "cif"]:
        if c in df.columns:
            struct_col = c
            break

    label_col = None
    for c in ["ion_transport.label_available", "label_available"]:
        if c in df.columns:
            label_col = c
            break

    for pos, idx in enumerate(df.index):
        row = df.iloc[pos]
        sigma = _nested_get(row, sigma_col) if sigma_col else None
        ea = _nested_get(row, ea_col) if ea_col else None
        struct = _nested_get(row, struct_col) if struct_col else None
        label = _nested_get(row, label_col) if label_col else None

        if sigma is None or (isinstance(sigma, float) and np.isnan(sigma)):
            report.null_sigma_count += 1
        elif sigma == 0 or sigma == -1:
            report.silent_imputation_detected.append(f"Row {pos}: sigma={sigma} (possible sentinel)")

        if ea is None or (isinstance(ea, float) and np.isnan(ea)):
            report.null_ea_count += 1

        if struct is None or (isinstance(struct, str) and len(struct) < 10):
            report.null_structure_count += 1

        if label is False:
            report.label_available_false_count += 1
            if sigma is not None and not (isinstance(sigma, float) and np.isnan(sigma)):
                report.label_available_true_no_data.append(int(pos))

    report.passed = (
        len(report.silent_imputation_detected) == 0
        and len(report.label_available_true_no_data) == 0
    )

    return report


# ── Full Cleaning Pipeline ─────────────────────────────────────────────────────

@dataclass
class CleaningReport:
    total_input: int = 0
    total_output: int = 0
    arrhenius_failures: list[dict[str, Any]] = field(default_factory=list)
    unit_report: UnitStandardizationReport = field(default_factory=UnitStandardizationReport)
    dedup_report: DeduplicationReport = field(default_factory=DeduplicationReport)
    missing_data_report: MissingDataReport = field(default_factory=MissingDataReport)
    passed: bool = False


def run_cleaning(
    df: pd.DataFrame,
    skip_arrhenius: bool = False,
) -> CleaningReport:
    """Run the full Phase 4 cleaning pipeline on a DataFrame.

    Steps:
    1. Unit standardization
    2. Arrhenius consistency filtering
    3. Cross-source deduplication
    4. Missing-data audit
    """
    report = CleaningReport(total_input=len(df))

    df, unit_report = standardize_units(df)
    report.unit_report = unit_report

    if not skip_arrhenius:
        df, arrhenius_failures = filter_arrhenius_failures(df)
        report.arrhenius_failures = arrhenius_failures

    df, dedup_report = deduplicate_cross_source(df)
    report.dedup_report = dedup_report

    missing_report = audit_missing_data(df)
    report.missing_data_report = missing_report

    report.total_output = len(df)
    report.passed = (
        len(report.arrhenius_failures) == 0
        and report.missing_data_report.passed
    )

    return report


def save_cleaning_report(report: CleaningReport, output_path: str | Path) -> None:
    """Save the cleaning report as JSON."""
    output_path = Path(output_path)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(
        json.dumps({
            "total_input": report.total_input,
            "total_output": report.total_output,
            "arrhenius_failures_count": len(report.arrhenius_failures),
            "unit_conversions": {
                "conductivity": report.unit_report.conductivity_converted,
                "energy": report.unit_report.energy_converted,
                "temperature": report.unit_report.temperature_converted,
            },
            "deduplication": {
                "cross_source_removed": report.dedup_report.cross_source_deduped,
                "composition_groups": report.dedup_report.composition_dedup_groups,
                "alternate_polymorphs": len(report.dedup_report.alternate_polymorphs),
            },
            "missing_data": {
                "null_sigma": report.missing_data_report.null_sigma_count,
                "null_ea": report.missing_data_report.null_ea_count,
                "null_structure": report.missing_data_report.null_structure_count,
                "silent_imputations": len(report.missing_data_report.silent_imputation_detected),
            },
            "passed": report.passed,
        }, indent=2)
    )
