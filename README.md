# Scandium Labs — Solid-State Battery (SSB) Materials Dataset

[![Release](https://img.shields.io/badge/dataset--release-1.9.0-blue.svg)](https://github.com/ScandiumLabs-in/Scandium-Labs-Solid-State-Battery-Dataset)
[![Release Gates](https://img.shields.io/badge/release--gates-22%2F22%20PASS-brightgreen.svg)](release_report.json)
[![Tests](https://img.shields.io/badge/tests-869%20PASSing-success.svg)](tests/)
[![License: CC BY 4.0](https://img.shields.io/badge/License-CC%20BY%204.0-lightgrey.svg)](LICENSE)
[![Python Version](https://img.shields.io/badge/python-3.10%2B-blue.svg)](pyproject.toml)

> **A Literature-Derived & DFT-Anchored Dataset for Solid-State Battery Electrolytes**  
> Unifying **30,071 bulk structural/thermodynamic DFT entries** with **sentence-verified experimental room-temperature ionic conductivity ($\sigma_{\text{RT}}$) and activation energy ($E_a$) transport labels**.

---

## Executive Summary

The critical bottleneck in machine-learning-driven solid electrolyte discovery is the extreme scarcity of reliable experimental room-temperature ionic conductivity labels. While computational structures are abundant, physical ionic conductivity measurements require complex pellet synthesis, sintering, and electrochemical impedance spectroscopy (EIS).

**Scandium Labs SSB Dataset** addresses this challenge through a multi-tier architecture:
1. **Sentence-Level Literature Evidence:** Experimental $\sigma_{\text{RT}}$ and $E_a$ values mined from peer-reviewed publications, hand-verified against verbatim sentences, pages, table/figure annotations, and DOIs.
2. **Deterministic Red-Flag Verification:** Every literature record passes Arrhenius consistency screens ($\sigma_0 \in [10^1, 10^5] \text{ S/cm}$), digit-matching verification against source text, unit standardization, and copy-paste anomaly detection.
3. **Bulk DFT Structural Backbone:** Over 30,000 Li-containing structures sourced across 8 database connectors (Materials Project, JARVIS, NOMAD, AFLOW, OQMD, COD, Materials Cloud).
4. **Cross-Paper Consensus Engine:** Material-level aggregation tracking independent measurement agreement ($n \ge 3$ papers) and statistical outlier bounds.

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

### 3. Querying Material Consensus ($n \ge 3$ Independent Papers)

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

| Family | Formula Pattern / Examples | $\sigma_{\text{RT}}$ Range (S/cm) | $E_a$ Range (eV) | Key Transport Feature |
| :--- | :--- | :--- | :--- | :--- |
| **Garnet** | $\text{Li}_7\text{La}_3\text{Zr}_2\text{O}_{12}$ (LLZO), Ta/Al-doped | $10^{-5} - 2 \times 10^{-3}$ | $0.20 - 0.55$ | Excellent Li-metal stability, bulk/GB impedance split |
| **NASICON** | $\text{Li}_{1+x}\text{Al}_x\text{Ti}_{2-x}(\text{PO}_4)_3$ (LATP) | $10^{-5} - 10^{-2}$ | $0.20 - 0.45$ | High air stability, moisture sensitive grain boundaries |
| **Sulfide** | $\text{Li}_{10}\text{GeP}_2\text{S}_{12}$ (LGPS), $\text{Li}_7\text{P}_3\text{S}_{11}$ | $10^{-5} - 10^{-1}$ | $0.10 - 0.50$ | Extremely high room-temperature ionic conductivity |
| **Argyrodite** | $\text{Li}_6\text{PS}_5\text{Cl}$, $\text{Li}_6\text{PS}_5\text{Br}$ | $10^{-4} - 10^{-1}$ | $0.15 - 0.50$ | Ductile, low grain boundary resistance |
| **Perovskite** | $\text{Li}_{3x}\text{La}_{2/3-x}\text{TiO}_3$ (LLTO) | $10^{-6} - 10^{-3}$ | $0.25 - 0.50$ | High bulk conductivity ($>10^{-3}$ S/cm), high GB resistance |
| **Halide** | $\text{Li}_3\text{YCl}_6$, $\text{Li}_3\text{InCl}_6$ | $10^{-4} - 10^{-2}$ | $0.25 - 0.50$ | High oxidative stability ($>4$V vs $\text{Li/Li}^+$) |
| **Oxide** | Lithium metal oxides, perovskite-related | $10^{-10} - 10^{-2}$ | $0.20 - 0.90$ | Structural foundation, cathode/electrolyte interfaces |
| **Hydride** | $\text{LiBH}_4$, $\text{Li}_2\text{NH}$ | $10^{-8} - 10^{-3}$ | $0.30 - 0.80$ | Thermally activated superionic transitions |
| **Borohydride** | $\text{LiCB}_{11}\text{H}_{12}$, $\text{Li}_2\text{B}_{12}\text{H}_{12}$ | $10^{-8} - 10^{-3}$ | $0.20 - 1.70$ | Rotational anion disorder, low lattice density |
| **Antiperovskite** | $\text{Li}_3\text{OCl}$, $\text{Li}_3\text{OBr}$ | $10^{-8} - 10^{-4}$ | $0.30 - 0.70$ | Low melting point, low activation energy potential |
| **Polymer Composite** | PEO-LiTFSI + LLZO/LATP ceramic | $10^{-8} - 10^{-3}$ | $0.30 - 1.50$ | Non-Arrhenius VTF kinetics, flexible mechanical interface |

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

This project and dataset are distributed under the [Creative Commons Attribution 4.0 International License (CC-BY-4.0)](LICENSE). You are free to share and adapt the material for any purpose, even commercially, provided you give appropriate credit, link to the license, and indicate if changes were made. Structural data sourced from third-party databases retain their respective open computational licenses (Creative Commons / Materials Project Terms).
