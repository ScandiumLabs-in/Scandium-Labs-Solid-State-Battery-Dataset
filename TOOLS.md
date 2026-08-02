# TOOLS.md — Scandium Labs SSB Dataset Build

Consolidated tool, library, and API reference. Organized by pipeline function, cross-referenced to the phase(s) that use them.

---

## Structure & Materials Handling
| Tool | Purpose | Used in |
|---|---|---|
| `pymatgen` | Structure objects, CIF/POSCAR I/O, structure matching, symmetry analysis | Phases 2, 4, 6, 7 |
| ASE (Atomic Simulation Environment) | Structure manipulation, alternate I/O formats | Phase 2, 5 |
| BVSE / GULP | Bond-valence-based Li migration pathway analysis | Phase 6 (symmetry descriptors) |

## DFT Sources (Bulk/API)
| Tool | Purpose | Used in |
|---|---|---|
| `mp-api` / `pymatgen.ext.matproj` | Materials Project REST API client | Phase 1, 2 |
| `jarvis-tools` | JARVIS-DFT (NIST) Python package | Phase 1, 2 |
| OQMD REST API / bulk MySQL dump | OQMD data access | Phase 1, 2 |
| `aflow` Python wrapper / AFLOW REST API | AFLOW data access | Phase 1, 2 |
| NOMAD REST API | Raw calculation provenance archive | Phase 1, 2 |
| ICSD (institutional license) | Experimental structure database | Phase 1, 2 (if access available) |

## DFT Compute
| Tool | Purpose | Used in |
|---|---|---|
| VASP | Primary DFT engine (preferred for MP-schema compatibility) | Phase 5 |
| Quantum Espresso | Open-source alternative if compute-constrained | Phase 5 |
| Custodian | Automated job management, error handling, retry logic | Phase 5 |

## Literature Mining
| Tool | Purpose | Used in |
|---|---|---|
| Semantic Scholar API | Paper discovery, citation metadata | Phase 3.1 |
| Crossref API | DOI resolution, metadata | Phase 3.1 |
| GROBID | PDF structure/table extraction | Phase 3.3 |
| LLM (extraction pass) | Structured data extraction from parsed text/tables | Phase 3.3 |

## Feature Engineering / ML
| Tool | Purpose | Used in |
|---|---|---|
| matminer | Composition-based descriptor generation | Phase 6 |
| Magpie featurizer set | Composition descriptors (via matminer) | Phase 6 |
| PyTorch Geometric (or equivalent GNN framework) | Graph object construction matching PIGNet V2 input spec | Phase 6 |

## Storage, Orchestration & Versioning
| Tool | Purpose | Used in |
|---|---|---|
| Parquet (partitioned) | Staging dataset storage | Phase 2, 4 |
| Makefile / Prefect / Airflow (pick one, lightweight is fine) | Pipeline orchestration for reproducible re-runs | Phase 2, 10 |
| DVC (optional) | Large-artifact versioning | Phase 9, 10 |
| Git / GitHub | Pipeline code versioning, issue tracker, contribution intake | All phases |

## Hosting & Distribution
| Tool | Purpose | Used in |
|---|---|---|
| Hugging Face Datasets | Primary public distribution, ML-audience discovery | Phase 9 |
| Zenodo | DOI issuance, long-term academic archival | Phase 9 |

## Documentation
| Tool | Purpose | Used in |
|---|---|---|
| Datasheets for Datasets (Gebru et al. format) | Documentation standard | Phase 8 |
| `CITATION.cff` | Machine-readable citation metadata | Phase 8 |

---

## Access/Setup Checklist

Before Phase 1 kicks off, confirm:
- [ ] Materials Project API key obtained
- [ ] JARVIS-tools installed, no auth needed
- [ ] OQMD access method decided (REST vs. bulk dump)
- [ ] AFLOW API tested
- [ ] NOMAD API tested
- [ ] ICSD institutional access status resolved (yes/no — affects Phase 1 scope, see main guide Risk Register)
- [ ] Semantic Scholar API key obtained
- [ ] LLM API access provisioned with a cost-control plan (cheap model for triage, stronger model for extraction — see main guide Section 15)
- [ ] VASP or Quantum Espresso license/install confirmed, Custodian configured
- [ ] Hugging Face and Zenodo accounts created ahead of Phase 9, not scrambled together at release time
