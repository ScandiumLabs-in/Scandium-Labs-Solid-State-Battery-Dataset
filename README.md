# Scandium Labs — Solid-State Battery (SSB) Materials Dataset

[![Release](https://img.shields.io/badge/dataset--release-1.9.0-blue.svg)](https://github.com/ScandiumLabs-in/Scandium-Labs-Solid-State-Battery-Dataset)
[![Release Gates](https://img.shields.io/badge/release--gates-22%2F22%20PASS-brightgreen.svg)](release_report.json)
[![Tests](https://img.shields.io/badge/tests-869%20PASSing-success.svg)](tests/)
[![License: CC BY 4.0](https://img.shields.io/badge/License-CC%20BY%204.0-lightgrey.svg)](LICENSE)
[![Python Version](https://img.shields.io/badge/python-3.10%2B-blue.svg)](pyproject.toml)

> **A Literature-Derived & DFT-Anchored Dataset for Solid-State Battery Electrolytes**  
> Unifying **30,071 bulk structural/thermodynamic DFT entries** with **sentence-verified experimental room-temperature ionic conductivity (σ<sub>RT</sub>) and activation energy (E<sub>a</sub>) transport labels**.

---

## About Scandium Labs

**Scandium Labs** is an AI-for-Science research company building open infrastructure for computational materials discovery — high-quality materials datasets, foundation models, and machine learning systems that let researchers explore millions of candidate materials before expensive laboratory or DFT validation. Our mission is to make materials discovery faster, reproducible, and accessible. This dataset is one of the core open-data pieces of that platform.

- 🌐 **Website:** [scandium-labs.com](https://scandium-labs.com/)
- 💼 **LinkedIn:** [linkedin.com/company/scandium-labs](https://www.linkedin.com/company/scandium-labs/)
- 🧪 **Research:** physics-informed crystal prediction, open materials datasets, solid-state battery discovery

---

## Executive Summary

The critical bottleneck in machine-learning-driven solid electrolyte discovery is the extreme scarcity of reliable experimental room-temperature ionic conductivity labels. While computational structures are abundant, physical ionic conductivity measurements require complex pellet synthesis, sintering, and electrochemical impedance spectroscopy (EIS).

**Scandium Labs SSB Dataset** addresses this challenge through a multi-tier architecture:
1. **Sentence-Level Literature Evidence:** Experimental σ<sub>RT</sub> and E<sub>a</sub> values mined from peer-reviewed publications, hand-verified against verbatim sentences, pages, table/figure annotations, and DOIs.
2. **Deterministic Red-Flag Verification:** Every literature record passes Arrhenius consistency screens (σ<sub>0</sub> ∈ [10¹, 10⁵] S/cm), digit-matching verification against source text, unit standardization, and copy-paste anomaly detection.
3. **Bulk DFT Structural Backbone:** Over 30,000 Li-containing structures sourced across 8 database connectors (Materials Project, JARVIS, NOMAD, AFLOW, OQMD, COD, Materials Cloud).
4. **Cross-Paper Consensus Engine:** Material-level aggregation tracking independent measurement agreement (n ≥ 3 papers) and statistical outlier bounds.

---

## Status

<!-- status-begin -->
**Status (auto-generated from `release_report.json` — do not edit by hand).** Version **v1.9.0**, generated 2026-08-07T03:14:47.865943+00:00. Release gates: **ALL PASS**.

| Bucket | Count | What it is |
|---|---|---|
| **Bulk structural records** | ~30838 | DFT-native pulls (Materials Project / JARVIS / NOMAD / COD / etc.), Li-containing catalog. **Not screened for SSE relevance** — the dump includes cathode chemistries that share the Li+O+metal formula pattern. |
| **Verified experimental labels** | 183 | Evidence-linked σ/Ea from literature mining, **human-reviewed**, provenance-tracked to the sentence level. The scarce valuable asset. |
| **Consensus (n≥3 papers)** | 20 | Cross-paper consensus: only 20 materials have ≥3 independent papers. |

> **Honest caveat.** Of the ~30838 records, only **183 carry human-verified conductivity/Ea labels**; the remainder are structural/thermodynamic DFT records *without* transport labels. Quality-tier distribution: silver 98.0%, rejected 2.0%. See `quality_output/quality_report.json` and `release_report.json` — stated up front so the rest of the dataset's claims are credible.

> *This block is generated. Run `python scripts/sync_readme_status.py` (or any `scripts/release.py` invocation) to regenerate; if it disagrees with the report, regenerate — never hand-edit.*
<!-- status-end -->

---

## Quick Start (Python API)

### 1. Installation

```bash
git clone https://github.com/ScandiumLabs-in/Scandium-Labs-Solid-State-Battery-Dataset.git
cd Scandium-Labs-Solid-State-Battery-Dataset
pip install -e .
```

Optional feature groups (`pip install -e ".[dev,literature,dashboard,sources,ml,dft]"`):

| Extra | Provides |
| :--- | :--- |
| `dev` | pytest, ruff, mypy, pre-commit — needed to run the test suite |
| `literature` | PDF text + OCR stack (pymupdf, pdfplumber, pdf2image, pytesseract, GROBID, OpenAI) |
| `dashboard` | Review dashboard web UI (FastAPI, uvicorn, jinja2) |
| `sources` | Source-database clients (JARVIS, mp-api) — OQMD/NOMAD/AFLOW/COD/Materials Cloud use keyless REST, no client needed |
| `ml` | PyTorch + PyTorch Geometric graph export and GNN baselines |
| `dft` | DFT workflow tooling (Custodian, ASE) |

Tests that need an optional extra (e.g. the dashboard, GNN, or PDF tests) auto-skip with a clear message when its dependency is not installed, and tests that exercise large gitignored build artifacts (e.g. `features_output/descriptors.parquet`) skip on a fresh clone until the build pipeline has been run.

### 2. Loading Verified Experimental Transport Records

```python
import pandas as pd

# Load verified experimental transport records
df = pd.read_parquet("quality_output/quality.parquet")

# Filter for top human-verified superionic conductors
verified = df[df["human_verified"] == True]
print(f"Loaded {len(verified)} human-verified experimental transport records.")

# Inspect composition, conductivity, activation energy, and DOI
print(verified[["composition", "family", "property", "value", "unit", "doi"]].head(10))
```

### 3. Querying Material Consensus (n ≥ 3 Independent Papers)

```python
import json

with open("literature_output/consensus_db.json") as f:
    consensus_db = json.load(f)

# Find high-consensus superionic conductors
for comp, data in consensus_db.items():
    if data.get("n_papers", 0) >= 3:
        print(f"Material: {comp:<25} | Papers: {data['n_papers']} | Agreement: {data.get('agreement_grade')}")
```

---

## Material Family Taxonomy

The dataset categorizes solid-state battery materials into 11 distinct chemical families:

| Family | Formula Pattern / Examples | σ<sub>RT</sub> Range (S/cm) | E<sub>a</sub> Range (eV) | Key Transport Feature |
| :--- | :--- | :--- | :--- | :--- |
| **Garnet** | Li<sub>7</sub>La<sub>3</sub>Zr<sub>2</sub>O<sub>12</sub> (LLZO), Ta/Al-doped | 10⁻⁵ – 2 × 10⁻³ | 0.20 – 0.55 | Excellent Li-metal stability, bulk/GB impedance split |
| **NASICON** | Li<sub>1+x</sub>Al<sub>x</sub>Ti<sub>2−x</sub>(PO<sub>4</sub>)<sub>3</sub> (LATP) | 10⁻⁵ – 10⁻² | 0.20 – 0.45 | High air stability, moisture sensitive grain boundaries |
| **Sulfide** | Li<sub>10</sub>GeP<sub>2</sub>S<sub>12</sub> (LGPS), Li<sub>7</sub>P<sub>3</sub>S<sub>11</sub> | 10⁻⁵ – 10⁻¹ | 0.10 – 0.50 | Extremely high room-temperature ionic conductivity |
| **Argyrodite** | Li<sub>6</sub>PS<sub>5</sub>Cl, Li<sub>6</sub>PS<sub>5</sub>Br | 10⁻⁴ – 10⁻¹ | 0.15 – 0.50 | Ductile, low grain boundary resistance |
| **Perovskite** | Li<sub>3x</sub>La<sub>2/3−x</sub>TiO<sub>3</sub> (LLTO) | 10⁻⁶ – 10⁻³ | 0.25 – 0.50 | High bulk conductivity (>10⁻³ S/cm), high GB resistance |
| **Halide** | Li<sub>3</sub>YCl<sub>6</sub>, Li<sub>3</sub>InCl<sub>6</sub> | 10⁻⁴ – 10⁻² | 0.25 – 0.50 | High oxidative stability (>4 V vs Li/Li⁺) |
| **Oxide** | Lithium metal oxides, perovskite-related | 10⁻¹⁰ – 10⁻² | 0.20 – 0.90 | Structural foundation, cathode/electrolyte interfaces |
| **Hydride** | LiBH<sub>4</sub>, Li<sub>2</sub>NH | 10⁻⁸ – 10⁻³ | 0.30 – 0.80 | Thermally activated superionic transitions |
| **Borohydride** | LiCB<sub>11</sub>H<sub>12</sub>, Li<sub>2</sub>B<sub>12</sub>H<sub>12</sub> | 10⁻⁸ – 10⁻³ | 0.20 – 1.70 | Rotational anion disorder, low lattice density |
| **Antiperovskite** | Li<sub>3</sub>OCl, Li<sub>3</sub>OBr | 10⁻⁸ – 10⁻⁴ | 0.30 – 0.70 | Low melting point, low activation energy potential |
| **Polymer Composite** | PEO-LiTFSI + LLZO/LATP ceramic | 10⁻⁸ – 10⁻³ | 0.30 – 1.50 | Non-Arrhenius VTF kinetics, flexible mechanical interface |

---

## Multi-Agent Governance Architecture (`AGENTS.md`)

Execution of the pipeline is governed by **11 specialist agents** coordinated by an Orchestrator:

```
                  ┌────────────────────────┐
                  │   Orchestrator Agent   │
                  └───────────┬────────────┘
                              │
  ┌───────────────────────────┼───────────────────────────┐
  │                           │                           │
  ▼                           ▼                           ▼
1. Source-Survey          2. Ingestion & Classifier   3. Literature Discovery
   (DB Survey)               (Staging Parquet)           (OpenAlex / Unpaywall)
  │                           │                           │
  ▼                           ▼                           ▼
4. Literature Extract     5. Cleaning & Canonical     6. DFT Compute Agent
   (Groq/Ollama Vision)      (Arrhenius / RedFlags)      (Priority Queue)
  │                           │                           │
  ▼                           ▼                           ▼
7. Feature Engineering    8. Validation Agent         9. Documentation & Release
   (Graph Descriptors)       (10 Release Gates)          (Automated Sync & HF)
```

---

## Project Documentation & File Navigation

| Documentation File | Description |
| :--- | :--- |
| [`DOCUMENTATION.md`](DOCUMENTATION.md) | **Complete Technical Manual:** Exhaustive guide to schema blocks, multi-agent pipeline, CLI reference, and consensus database. |
| [`scandium-ssb-dataset-guide.md`](scandium-ssb-dataset-guide.md) | **Build Guide:** Core design principles, 11 functional block schema specification, and phased execution roadmap. |
| [`guides/ssb-dataset-expansion-quality-guide.md`](guides/ssb-dataset-expansion-quality-guide.md) | **Expansion Guide:** Post-pipeline enhancement strategies (OpenAlex discovery, vision extraction, metadata backfill). |
| [`AGENTS.md`](AGENTS.md) | **Multi-Agent Governance:** Detailed agent roles, input/output contracts, confidence thresholds, and escalation rules. |
| [`SKILLS.md`](SKILLS.md) | **Competency Matrix:** Required domain skills (materials informatics, pymatgen, EIS parsing, PyTorch Geometric). |
| [`TOOLS.md`](TOOLS.md) | **API & Tool Reference:** REST endpoints, OPTIMADE syntax, GROBID setup, and access checklists. |
| [`CONTRIBUTING.md`](CONTRIBUTING.md) | **Community Guide:** Guidelines for submitting single-value experimental transport measurements. |
| [`CHANGELOG.md`](CHANGELOG.md) | **Version History:** Release changelog tracking dataset progression from v0.1 to v0.4.0. |

---

## Citation & License

### BibTeX Citation

```bibtex
@dataset{scandium_ssb_dataset_2026,
  author       = {Scandium Labs Team},
  title        = {Scandium Labs Solid-State Battery (SSB) Transport Dataset},
  year         = 2026,
  version      = {v0.2.0},
  publisher    = {GitHub / Zenodo},
  url          = {https://github.com/ScandiumLabs-in/Scandium-Labs-Solid-State-Battery-Dataset}
}
```

### License

This project and dataset are distributed under the [Creative Commons Attribution 4.0 International License (CC-BY-4.0)](LICENSE). You are free to share and adapt the material for any purpose, even commercially, provided you give appropriate credit, link to the license, and indicate if changes were made. Structural data sourced from third-party databases retain their respective source licenses.

> **Source-license carve-outs:** the blanket CC-BY-4.0 grant in [LICENSE](LICENSE) covers only Scandium-authored content. Per-record source terms are documented in [LICENSE_BREAKDOWN.md](LICENSE_BREAKDOWN.md) and are identified per row via `identity.source_db`. The current release (v1.9.0) includes **150 AFLOW rows that are restricted to scientific/academic/non-commercial use**, plus 50 OQMD rows (CC BY 4.0) and 21,528 Materials Project rows (CC BY 4.0). Consult `identity.source_db` before assuming redistribution rights.
