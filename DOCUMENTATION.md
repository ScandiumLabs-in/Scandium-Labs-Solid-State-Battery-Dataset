# Scandium Labs Solid-State Battery (SSB) Dataset — Technical Documentation

Welcome to the official technical documentation for the **Scandium Labs Solid-State Battery Materials Dataset**. This document provides an exhaustive reference to the dataset schema, multi-agent architecture, data ingestion & extraction pipelines, quality scoring system, and programmatic usage.

---

## Table of Contents
1. [Overview & Scientific Vision](#1-overview--scientific-vision)
2. [Dataset Architecture & Unified Schema](#2-dataset-architecture--unified-schema)
3. [Source Connectors & Data Sourcing](#3-source-connectors--data-sourcing)
4. [Literature Mining & Extraction Pipeline](#4-literature-mining--extraction-pipeline)
5. [Deterministic Cleaning & Canonicalization](#5-deterministic-cleaning--canonicalization)
6. [Quality Scoring & Tier Taxonomy](#6-quality-scoring--tier-taxonomy)
7. [Cross-Paper Consensus Engine](#7-cross-paper-consensus-engine)
8. [Multi-Agent Governance Architecture](#8-multi-agent-governance-architecture)
9. [Release Gates & Validation Framework](#9-release-gates--validation-framework)
10. [CLI & Script Usage Reference](#10-cli--script-usage-reference)
11. [Developer Guide & Testing](#11-developer-guide--testing)

---

## 1. Overview & Scientific Vision

Experimental ionic conductivity ($\sigma_{\text{RT}}$) and activation energy ($E_a$) labels for solid electrolytes are the single scarcest asset in solid-state lithium battery discovery. While density functional theory (DFT) structural calculations are abundant across computational databases, experimental transport measurements require labor-intensive pellet synthesis, electrochemical impedance spectroscopy (EIS), and Arrhenius temperature sweeps.

**Scandium Labs** solves this label-scarcity problem through a hybrid architecture:
- **30,071 Bulk DFT Structural Records:** Sourced across 8 structural databases (Materials Project, JARVIS, NOMAD, AFLOW, OQMD, COD, Materials Cloud).
- **116 Sentence-Verified Experimental Transport Records:** Extracted from peer-reviewed literature, verified to the verbatim sentence, page, table/figure, and DOI.
- **334 Benchmark Compounds:** Standardized reference inventory for solid electrolytes across 11 material families.
- **Cross-Paper Consensus Database:** Material-level aggregation tracking measurement agreement ($n \ge 3$ independent papers).

---

## 2. Dataset Architecture & Unified Schema

Every record in the dataset is modeled via a strict Pydantic schema (`src/ssb_dataset/schema.py`) composed of 11 functional blocks.

```
MaterialRecord
 ├── identity         : IdentityProvenance
 ├── structure        : StructureBlock
 ├── thermodynamics   : ThermodynamicsBlock
 ├── ion_transport    : IonTransportBlock
 ├── electronics      : ElectronicsBlock
 ├── magnetics        : MagneticsBlock
 ├── synthesis        : SynthesisBlock
 ├── characterization : CharacterizationBlock
 ├── experiment       : ExperimentBlock
 ├── consensus        : ConsensusBenchmarkBlock
 └── quality          : QualityScoreBlock
```

### 2.1 Family Taxonomy

The dataset categorizes solid electrolytes into 11 distinct chemical families:

| Family | Key Formula Patterns | Typical $\sigma_{\text{RT}}$ Range (S/cm) | Typical $E_a$ Range (eV) |
| :--- | :--- | :--- | :--- |
| **Garnet** | $\text{Li}_7\text{La}_3\text{Zr}_2\text{O}_{12}$ (LLZO), Ta/Al-doped | $10^{-5} - 2 \times 10^{-3}$ | $0.20 - 0.55$ |
| **NASICON** | $\text{Li}_{1+x}\text{Al}_x\text{Ti}_{2-x}(\text{PO}_4)_3$ (LATP), LAGP | $10^{-5} - 10^{-2}$ | $0.20 - 0.45$ |
| **Sulfide** | $\text{Li}_{10}\text{GeP}_2\text{S}_{12}$ (LGPS), $\text{Li}_7\text{P}_3\text{S}_{11}$, thio-LISICON | $10^{-5} - 10^{-1}$ | $0.10 - 0.50$ |
| **Argyrodite** | $\text{Li}_6\text{PS}_5\text{Cl}$, $\text{Li}_6\text{PS}_5\text{Br}$, halogen-rich | $10^{-4} - 10^{-1}$ | $0.15 - 0.50$ |
| **Perovskite** | $\text{Li}_{3x}\text{La}_{2/3-x}\text{TiO}_3$ (LLTO) | $10^{-6} - 10^{-3}$ | $0.25 - 0.50$ |
| **Oxide** | Bulk lithium metal oxides, perovskite-related | $10^{-10} - 10^{-2}$ | $0.20 - 0.90$ |
| **Halide** | $\text{Li}_3\text{YCl}_6$, $\text{Li}_3\text{InCl}_6$, $\text{Li}_3\text{ErCl}_6$ | $10^{-4} - 10^{-2}$ | $0.25 - 0.50$ |
| **Hydride** | $\text{LiBH}_4$, $\text{Li}_2\text{NH}$, transition metal hydrides | $10^{-8} - 10^{-3}$ | $0.30 - 0.80$ |
| **Borohydride** | $\text{LiCB}_{11}\text{H}_{12}$, $\text{Li}_2\text{B}_{12}\text{H}_{12}$ clusters | $10^{-8} - 10^{-3}$ | $0.20 - 1.70$ |
| **Antiperovskite** | $\text{Li}_3\text{OCl}$, $\text{Li}_3\text{OBr}$, $\text{Li}_{2.9}\text{Sr}_{0.05}\text{OCl}$ | $10^{-8} - 10^{-4}$ | $0.30 - 0.70$ |
| **Polymer Composite** | PEO-LiTFSI + LLZO/LATP ceramic fillers | $10^{-8} - 10^{-3}$ | $0.30 - 1.50$ |

---

## 3. Source Connectors & Data Sourcing

The dataset ingests computational structures from 8 primary databases:

1. **Materials Project Connector:** Keyed API client retrieving bulk Li-containing structural and thermodynamic entries.
2. **JARVIS-DFT Connector:** Keyless REST integration extracting structural parameters and band gaps.
3. **NOMAD API Connector:** OPTIMADE keyless query endpoint for raw DFT calculation entries.
4. **AFLOW / AFLUX Connector:** Keyless REST query wrapper over AFLOW repository. **Licensing note:** AFLOW data is restricted to scientific/academic/non-commercial purposes; the current release includes 150 AFLOW rows (`identity.source_db == "aflow"`), which must be removed or separately cleared before commercial redistribution. See the per-source license table in `LICENSE_BREAKDOWN.md`.
5. **OQMD Connector:** Open Quantum Materials Database REST interface. **Licensing note:** OQMD data is licensed CC BY 4.0 (per oqmd.org); the current release includes 50 OQMD-derived rows (`identity.source_db == "oqmd"`), which are redistributable with attribution. See the per-source license table in `LICENSE_BREAKDOWN.md`.
6. **Crystallography Open Database (COD):** Sourced experimental CIF structures tagged `dft_native`.
7. **Materials Cloud Connector:** Keyless OPTIMADE API client retrieving curated 2D/3D solid-state structures.
8. **Verified Literature Connector:** High-precision experimental transport parser consuming review-approved extractions.

---

## 4. Literature Mining & Extraction Pipeline

```
PDF Discovery ──► GROBID / PyMuPDF ──► Dual-Pass LLM ──► Deterministic Verifier ──► AI-Review Gate
 (OpenAlex /      (Table + Prose)     (Groq / Ollama)     (Arrhenius + Digit +    (Zero-FAIL Gate)
  Unpaywall)                                              Copy-Paste Checks)
```

### 4.1 Multi-Route Open Access Funnel (`scripts/harvest_multi_route.py`)
PDF acquisition operates strictly on legal open-access (OA) sources:
1. **Unpaywall API:** Direct per-DOI resolution for published OA PDFs.
2. **OpenAlex API:** Pre-filtered open-access repository lookup.
3. **Europe PMC (EPMC) Render:** XML/HTML rendering for deposited PMC papers.
4. **CORE / BASE / arXiv / ChemRxiv:** Author preprint and institutional repository fallbacks.

### 4.2 Vision-Capable Extraction (`verifier.py::vision_locate_evidence`)
When text-layer PDF extraction yields SCRIBED or scanned pages, the vision pipeline:
1. Renders PDF pages to high-resolution PNG images.
2. Transcribes tables and prose via vision-capable models (Groq Vision or Ollama VL).
3. Passes transcribed content to the deterministic snippet scanner.

---

## 5. Deterministic Cleaning & Canonicalization

Raw staging records pass through `src/ssb_dataset/pipeline/cleaning.py`:
- **Structure Deduplication:** Composition-grouped CIF matching using `pymatgen.analysis.structure_matcher.StructureMatcher`.
- **Unit Standardizer:** Converts mS/cm, $\mu\text{S/cm}$, S/m to standard $\text{S/cm}$, and kJ/mol, meV to $\text{eV}$.
- **Arrhenius Red-Flag Screen:** Verifies whether $\sigma_{\text{RT}}$ and $E_a$ produce a physical pre-factor $\sigma_0 \in [10^1, 10^5] \text{ S/cm}$. VTF kinetics families (polymers) are exempted.

---

## 6. Quality Scoring & Tier Taxonomy

Every record receives a deterministic 0–100 quality score and letter grade (A+, A, B, C, D).

$$\text{Quality Score} = \text{Human} (25) + \text{Evidence} (20) + \text{Metadata} (20) + \text{Consensus} (15) + \text{Depth} (10) - \text{Penalty} (10)$$

### Quality Tiers

- **Gold:** Human-reviewed + evidence page/sentence + agrees with consensus ($n \ge 2$) + complete temperature & method metadata + score $\ge 80$.
- **Silver:** Human-reviewed but single-paper or partial metadata.
- **Bronze:** AI-extracted high-confidence record, not yet human-verified.
- **Rejected:** Non-experimental (`dft_native`) or failed quality review.

---

## 7. Cross-Paper Consensus Engine

Material-level aggregation (`src/ssb_dataset/literature/consensus_db.py`) clusters measurements by canonical reduced composition:
- Tracks independent measurement count ($n$), median conductivity ($\sigma_{\text{med}}$), logarithmic standard deviation ($\sigma_{\text{logstd}}$), and activation energy spread ($E_{a, \text{med}}$).
- Flags statistical outliers deviating $> 1.5$ orders of magnitude from group medians.
- Generates material summary cards (`release/v0.2.0/material_cards.json`).

---

## 8. Multi-Agent Governance Architecture

The pipeline is orchestrated via the 11 agent roles defined in `AGENTS.md`:

```
Orchestrator Agent
├── 1. Source-Survey Agent (Phase 1)
├── 2. Ingestion Agent (Phase 2)
├── 3. Family-Classification Agent (Phase 2)
├── 4. Literature-Discovery Agent (Phase 3.1)
├── 5. Extraction Agent (Phase 3.3)
├── 6. Cleaning & Canonicalization Agent (Phase 4)
├── 7. DFT Compute Agent (Phase 5)
├── 8. Feature-Engineering Agent (Phase 6)
├── 9. Validation Agent (Phase 7)
├── 10. Documentation Agent (Phase 8)
└── 11. Release Agent (Phase 9–10)
```

---

## 9. Release Gates & Validation Framework

The dataset release pipeline (`scripts/release.py`) evaluates 10 strict release gates before publishing:

1. `tests_passing`: 100% test suite pass rate.
2. `validation_passed`: Phase 7 distributional sanity check.
3. `no_pending_review_flags`: Review queue cleared to 0 pending.
4. `evidence_coverage`: $\ge 85\%$ sentence-level evidence attribution.
5. `duplicate_rate`: $0.0\%$ unresolved duplicates.
6. `metadata_completeness`: $\ge 80\%$ temperature and measurement method metadata.
7. `doi_provenance`: $100\%$ DOI coverage for experimental records.
8. `min_verified_labels`: $\ge 100$ human-verified experimental transport records.
9. `min_total_records`: $\ge 25,000$ bulk structural records.
10. `health_report_generated`: Health report metadata check.

---

## 10. CLI & Script Usage Reference

### Primary Execution Entry Point (`run.py`)

```bash
# Execute full end-to-end pipeline
python run.py all

# Run individual pipeline stages
python run.py ingest all
python run.py clean
python run.py featurize
python run.py validate all
python run.py release
```

### Specialist Scripts (`scripts/`)

```bash
# Re-score quality metrics and tiers
python scripts/build_quality.py

# Re-build material consensus database
python scripts/build_consensus_db.py

# Re-build material cards
python scripts/build_material_cards.py

# Synchronize README status block with release report
python scripts/sync_readme_status.py

# Prioritize discovery queue for sulfide deficits
python scripts/prioritize_discovery.py

# Execute full release check chain and generate release bundle
python scripts/release.py --build
```

---

## 11. Developer Guide & Testing

### Installation

```bash
# Clone repository
git clone https://github.com/ScandiumLabs-in/Scandium-Labs-Solid-State-Battery-Dataset.git
cd Scandium-Labs-Solid-State-Battery-Dataset

# Create and activate environment
python -m venv .venv
source .venv/bin/activate

# Install package in editable mode
pip install -e .
```

### Running Test Suite

```bash
# Run pytest test suite (600 tests)
pytest
```

---
*Documentation maintained by Scandium Labs Agentic Systems.*
