"""Documentation generators for the SSB Dataset.

Produces the full Phase 8 documentation set:
  - Datasheet for Datasets (Gebru et al. format)
  - Per-family README
  - Confidence-tier documentation
  - CITATION.cff
  - CHANGELOG.md update
"""

from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

FAMILY_NAMES = {
    "sulfide": "Sulfide (Thio-LISICON)",
    "oxide": "Oxide",
    "garnet": "Garnet (LLZO-type)",
    "perovskite": "Perovskite (LLTO-type)",
    "nasicon": "NASICON (LATP/LAGP-type)",
    "halide": "Halide",
    "argyrodite": "Argyrodite (Li6PS5X)",
    "hydride": "Hydride",
    "borohydride": "Borohydride",
    "antiperovskite": "Antiperovskite",
    "polymer_composite": "Polymer / Composite",
}

FAMILY_DESCRIPTIONS = {
    "sulfide": "Li-ion conductors based on sulfide frameworks, including thio-LISICONs (Li10GeP2S12). Typically the highest room-temperature conductivities (1e-3 to 1e-1 S/cm).",
    "oxide": "Oxide-based Li-ion conductors not captured by more specific oxide families (garnet, perovskite, NASICON, antiperovskite). Broad class including simple oxides and complex oxide frameworks.",
    "garnet": "Garnet-structured Li-ion conductors, typified by Li7La3Zr2O12 (LLZO) and its doped variants. Good chemical stability against Li metal.",
    "perovskite": "Li-stuffed perovskite oxides based on Li3xLa2/3-xTiO3 (LLTO). High bulk conductivity but significant grain-boundary resistance.",
    "nasicon": "Sodium superionic conductor (NASICON)-type Li-ion conductors, primarily LATP and LAGP. Good air stability and moderate conductivity.",
    "halide": "Halide-based Li-ion conductors (Li3MX6, M = In, Y, Sc; X = Cl, Br). Emerging class with high oxidative stability for high-voltage cathodes.",
    "argyrodite": "Argyrodite-structure Li-ion conductors (Li6PS5X, X = Cl, Br, I). Cubic framework with superionic conductivity at room temperature.",
    "hydride": "Hydride Li-ion conductors (LiH, LiAlH4, complex hydrides). Typically require high-temperature phases for high conductivity.",
    "borohydride": "Borohydride Li-ion conductors (LiBH4, Li2B12H12). High-temperature phase transitions enable fast Li transport.",
    "antiperovskite": "Antiperovskite Li-ion conductors (Li3OX, X = Cl, Br). Theoretically promising but experimental synthesis has proven challenging.",
    "polymer_composite": "Polymer/ceramic composite electrolytes (e.g., PEO-LiTFSI with ceramic fillers). Standard crystal-graph featurization does not apply.",
}


def _get_column(df, *candidates: str) -> str | None:
    for c in candidates:
        if c in df.columns:
            return c
    return None


def generate_datasheet(
    df,
    output_path: str | Path,
    report: dict[str, Any] | None = None,
) -> str:
    """Generate a Datasheet for Datasets (Gebru et al. format) as Markdown."""
    family_col = _get_column(df, "identity.family", "family")
    source_col = _get_column(df, "identity.source_db", "source_db")
    conf_col = _get_column(df, "identity.confidence_tier", "confidence_tier")
    sigma_col = _get_column(df, "ion_transport.sigma_RT", "sigma_RT")
    label_col = _get_column(df, "ion_transport.label_available", "label_available")

    n_records = len(df)
    families = df[family_col].value_counts().to_dict() if family_col else {}
    sources = df[source_col].value_counts().to_dict() if source_col else {}
    n_with_sigma = df[sigma_col].notna().sum() if sigma_col else 0
    if label_col is not None and df[label_col].dtype == bool:
        n_labels = int(df[label_col].sum())
    elif report and report.get("verified_records") is not None:
        n_labels = int(report["verified_records"])
    else:
        n_labels = n_with_sigma
    version = (report or {}).get("version", "") or ""
    version_line = f" ({version})" if version else ""

    datasheet = f"""# Datasheet: Scandium Labs Solid-State Battery Electrolyte Dataset{version_line}

## Motivation

**For what purpose was the dataset created?**
To provide the first unified, provenance-tracked, ML-ready dataset of Li-ion
conductivity and activation energy values for solid-state battery electrolyte
materials across all 11 major SSB families (sulfides, oxides, garnets,
perovskites, NASICONs, halides, argyrodites, hydrides, borohydrides,
antiperovskites, and polymer/composites).

**Who created the dataset and on behalf of which entity?**
Scandium Labs. The dataset was built using the automated pipeline in this
repository.

**Who funded the creation of the dataset?**
Scandium Labs (self-funded).

## Composition

**Total records:** {n_records}
**Records per family:** {json.dumps(families, indent=2)}
**Records per source:** {json.dumps(sources, indent=2)}
**Records with verified experimental transport label:** {n_labels}
**Records with raw σ_RT value:** {n_with_sigma}

**What are the instances?**
Each instance is a unique material record identified by composition and source,
with associated structural, thermodynamic, and ion-transport properties.

**Are there recommended data splits?**
Yes — see `features_output/splits_metadata.json`. Splits are grouped by
composition-family key to prevent leakage between polymorphs/doped variants
of the same base composition.

## Collection Process

**How was the data collected?**
Data was collected through three parallel channels:
1. Bulk API pull from Materials Project, JARVIS-DFT, AFLOW, OQMD, NOMAD,
   and ICSD (where accessible).
2. Literature mining via Semantic Scholar discovery + GROBID table extraction
   + LLM-based structured extraction.
3. In-house DFT computation (VASP/Quantum Espresso) for priority gap compounds.

**Who was involved in the data collection process?**
The automated pipeline in this repository.

## Preprocessing / Cleaning / Labeling

**Was any preprocessing or cleaning applied?**
Yes — the Phase 4 cleaning pipeline:
- Unit standardization (conductivity → S/cm, energy → eV, temperature → K)
- Arrhenius consistency filtering (flagging implausible sigma/Ea pairs)
- Cross-source structural deduplication using pymatgen StructureMatcher
- Missing-data audit (sentinel detection, label-presence verification)

**Was a benchmark subset created?**
Yes — a gold benchmark subset of highest-confidence records (verified_human or
dft_native with measured sigma_RT) was selected for leaderboard-style model
comparison. See `features_output/gold.parquet`.

## Known Limitations & Biases

**What are the known limitations?**
- Sulfides and garnets are overrepresented relative to antiperovskites and
  hydrides because they are more studied in the literature — this reflects
  the state of the field, not a sampling choice.
- AIMD-computed conductivities (where present) are not equivalent to measured
  values — check `conductivity_source_type` before blending.
- Polymer/composite records are not compatible with standard crystal-graph
  featurization — use the separate polymer feature set.

**What are the recommended uses?**
- Training ML models for ionic conductivity prediction
- Benchmarking new models against the gold subset
- Identifying under-explored composition spaces (especially halides and
  antiperovskites)

**What are the explicitly discouraged uses?**
- Treating literature-mined values as equivalent to experimentally verified
  values without checking `confidence_tier`
- Using AIMD-computed conductivities as direct substitutes for experimental
  measurements

## Licensing

**What license applies to this dataset?**
The Scandium-authored portions (processing, quality scoring, validation,
analysis, documentation) are released under CC-BY-4.0. Third-party records
retain their respective source-database licenses, identified per row via
`identity.source_db`. The current release includes **150 AFLOW rows restricted
to scientific/academic/non-commercial use**, plus rows from Materials Project,
JARVIS-DFT, COD, NOMAD, and OQMD under their permissive terms. See
`LICENSE` and `LICENSE_BREAKDOWN.md` for the authoritative per-source license
table, record counts, and the "AS IS" warranty disclaimer. Consult
`identity.source_db` before assuming redistribution rights for any record.

## Maintenance

**Who maintains the dataset?**
Scandium Labs. The dataset is versioned (see CHANGELOG.md) and will receive
quarterly re-ingestion passes as source databases update.

**How can the dataset be extended?**
Community contributions are welcome — see CONTRIBUTING.md for the structured
submission template.
"""
    path = Path(output_path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(datasheet)
    return datasheet


def generate_family_readme(
    family: str,
    n_records: int,
    n_with_sigma: int,
    output_path: str | Path,
    extra_notes: str | None = None,
) -> str:
    """Generate a per-family README markdown file."""
    name = FAMILY_NAMES.get(family, family)
    description = FAMILY_DESCRIPTIONS.get(family, "")

    notes = extra_notes or ""
    if family == "polymer_composite":
        notes = "**Note:** This family uses a parallel featurization path. Standard crystal-graph representation does not apply. See `polymer_feature_columns()` for available features."
    elif family in ("hydride", "antiperovskite", "borohydride", "argyrodite"):
        if n_records < 50:
            notes = "**Note:** This family has sparse coverage. Use with caution — conductivities may be dominated by a small number of sources."

    readme = f"""# {name}

**Family:** `{family}`

**Records:** {n_records}
**Records with conductivity label:** {n_with_sigma}

## Description

{description}

## Known Quirks

{notes}

## Schema Notes

- `ion_transport.sigma_RT`: Room-temperature conductivity in S/cm.
- `ion_transport.activation_energy_Ea`: Activation energy in eV.
- `ion_transport.temperature_range_measured`: Dict with `min_K` and `max_K`.
"""
    path = Path(output_path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(readme)
    return readme


def generate_confidence_tier_doc(output_path: str | Path) -> str:
    """Generate standalone confidence-tier documentation."""
    doc = """# Confidence Tier System

Every record in the SSB Dataset carries a `confidence_tier` field indicating
the trustworthiness of its data. This is the dataset's primary quality signal.

## Tiers (highest to lowest confidence)

### `verified_human`
- **Source:** Hand-curated by a domain expert
- **When used:** Benchmark compounds (Section 17) and gold subset
- **Trust:** Maximum — these records are the dataset's quality anchor

### `dft_native`
- **Source:** Pulled directly from Materials Project, JARVIS-DFT, AFLOW, OQMD,
  NOMAD, or ICSD via their APIs
- **Trust:** High — DFT data from established, peer-reviewed repositories

### `dft_computed_inhouse`
- **Source:** Computed in-house via VASP/Quantum Espresso (Phase 5)
- **Trust:** High — follows MP's calculation scheme for schema compatibility
- **Note:** These are structural/thermodynamic properties only; conductivity
  labels are not computed at this tier unless explicitly marked AIMD

### `high_confidence_extraction`
- **Source:** Extracted from literature via GROBID + LLM with confidence score >= 0.85
- **Trust:** Moderate-high — but ALWAYS check against seed set accuracy

### `low_confidence_extraction`
- **Source:** Extracted from literature with confidence score < 0.85
- **Trust:** Low — use primarily for exploratory analysis, not for publications

## Usage Guidelines

1. **For training:** Filter to `dft_native` + `high_confidence_extraction` for
   structural/thermodynamic targets; use `verified_human` for conductivity labels.
2. **For benchmarking:** Only use `verified_human` records from the gold subset.
3. **For publication:** Clearly state which confidence tiers your analysis uses.
   Never blend tiers silently in reported statistics.

## Field-Level vs Row-Level Confidence

Future versions will support field-level confidence (e.g., a row might have
dft_native structure but literature_mined conductivity). Currently, confidence
is at the row level and reflects the least-trusted source in that row.
"""
    path = Path(output_path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(doc)
    return doc


def generate_citation_cff(output_path: str | Path) -> str:
    """Generate or update CITATION.cff."""
    cff = """cff-version: 1.2.0
message: "If you use this dataset in your research, please cite it as follows."
title: "Scandium Labs Solid-State Battery Electrolyte Dataset"
version: v1.9.0
date-released: 2026-08-07
authors:
  - name: "Scandium Labs"
    affiliation: "Scandium Labs"
license: "CC-BY-4.0"
repository-code: "https://github.com/ScandiumLabs-in/Scandium-Labs-Solid-State-Battery-Dataset"
description: >
  A unified, provenance-tracked, ML-ready dataset of Li-ion conductivity and
  activation energy values for solid-state battery electrolyte materials across
  11 families (sulfides, oxides, garnets, perovskites, NASICONs, halides,
  argyrodites, hydrides, borohydrides, antiperovskites, and polymer/composites).

keywords:
  - solid-state battery
  - lithium-ion conductivity
  - electrolyte
  - materials science
  - machine learning
"""
    path = Path(output_path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(cff)
    return cff


def update_changelog(output_path: str | Path, version: str = "v0.1.0") -> str:
    """Update the changelog with a new version entry."""
    date = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    entry = f"""
## [{version}] — {date}

### Added
- Phase 0: Schema lock with 11 SSB families + unknown fallback
- Phase 1: Source survey across MP, JARVIS, AFLOW, OQMD, NOMAD, ICSD
- Phase 2: Ingestion pipeline — 6 source connectors, Parquet staging
- Phase 3: Literature mining — Semantic Scholar discovery, GROBID + LLM extraction, 15-record seed set
- Phase 4: Cleaning — Arrhenius consistency, unit standardization, cross-source dedup, missing-data audit
- Phase 5: DFT compute pipeline — priority queue, VASP/QE input generation, Custodian workflow, AIMD estimation
- Phase 6: Featurization — PIGNet V2 graphs, composition/symmetry descriptors, stratified splits, gold benchmark
- Phase 7: Validation — family distribution checks, Section 17 benchmark verification, cross-source consistency audit
- Phase 8: Documentation — datasheet, per-family READMEs, confidence-tier doc, CITATION.cff

### Known Limitations
- Antiperovskite and hydride families have sparse coverage (reflects field reality)
- Literature-mined values carry inherent extraction uncertainty
- Polymer/composite records require separate featurization path
"""
    path = Path(output_path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(entry)
    return entry
