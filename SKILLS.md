# SKILLS.md — Scandium Labs SSB Dataset Build

Skills required across the build, mapped to phases and to the agent roles in `AGENTS.md`. Use this to identify gaps before a phase starts, not during it.

---

## 1. Materials Science / Solid-State Chemistry
**Needed for:** Phase 0 (schema calibration), Phase 1 (family taxonomy), Phase 5 (DFT settings), Phase 7 (sanity checks)
- Understanding of the 8 SSB families' structural chemistry (garnets vs. NASICON vs. sulfides etc.)
- Knowledge of what "reasonable" formation energy / band gap / conductivity ranges look like per family — this is what makes the Validation Agent's sanity checks meaningful rather than arbitrary
- Familiarity with bulk-vs-grain-boundary conductivity distinction, order-disorder phase transitions (hydrides), and electrochemical stability window interpretation

## 2. Computational Materials / DFT
**Needed for:** Phase 5
- VASP or Quantum Espresso operation: INCAR/KPOINTS conventions matching Materials Project's scheme
- Convergence troubleshooting, functional selection (PBE vs SCAN vs HSE06 tradeoffs)
- AIMD workflow setup and interpretation for conductivity estimation — knowing when an AIMD run is statistically meaningful vs. too short to trust
- Custodian or equivalent job-management/error-handling experience

## 3. Data Engineering
**Needed for:** Phase 2, Phase 4, Phase 10
- API integration across heterogeneous sources (REST, bulk dumps, differing auth schemes)
- Schema design and enforcement (Pydantic/JSON Schema), Parquet partitioning
- Pipeline orchestration (Makefile/Prefect/Airflow-equivalent) built for reproducible re-runs, not one-off scripts
- Deduplication logic design, unit-consistency testing

## 4. NLP / LLM-Based Extraction
**Needed for:** Phase 3
- Prompt design for structured extraction from scientific text/tables
- GROBID or equivalent PDF-structure parsing
- Building and interpreting extraction-accuracy evaluation against a human-labeled seed set
- Composition-string normalization/fuzzy-matching (handling formula-writing variance)

## 5. ML / Graph Representation Engineering
**Needed for:** Phase 6
- Graph neural network input representation design (matching PIGNet V2's attention-gated message-passing + 3-body angular edge feature spec)
- matminer/Magpie composition-descriptor generation
- Leakage-safe dataset splitting (grouped by composition family, not naive random split)

## 6. Scientific Writing / Documentation
**Needed for:** Phase 8, Phase 9
- Datasheets-for-Datasets format fluency
- Writing limitation/bias sections that are genuinely honest rather than promotional — this is what earns trust from the academic GTM segment
- Optional: data-descriptor paper writing (ChemRxiv/arXiv) if pursuing that credibility path instead of/alongside the existing preprint

## 7. Domain Networking / Academic Outreach
**Needed for:** Phase 7 (external review), Phase 9 (GTM)
- Ability to get 1–2 electrochemistry academics to sanity-check a release candidate — leverage the existing VIT Bhopal / [[prakash-n-b]] network here
- Positioning the gold benchmark subset as a low-friction adoption hook for university labs

## 8. Project & Pipeline Governance
**Needed for:** all phases, especially Phase 0 and Phase 10
- Version control discipline (semantic versioning, changelog hygiene)
- Licensing decisions (CC-BY-4.0 rationale, per-source redistribution terms)
- Maintaining the confidence-tier system's integrity across quarterly re-ingestion cycles — this is a governance skill as much as a technical one

---

## Skill Gaps to Watch For

- **DFT + AIMD interpretation** is the most likely single-point-of-failure skill if not already in-house — flag early whether this needs an external collaborator (Phase 5 is the phase most likely to stall without it).
- **LLM extraction QC discipline** (Skill 4) is easy to underinvest in since it's tempting to trust automated extraction at face value — the 85% accuracy gate in `AGENTS.md` only works if someone actually does the spot-checking.
- **Honest documentation writing** (Skill 6) is a soft skill that's easy to skip under release-pressure — but it's precisely what differentiates this dataset from a promotional data dump in the eyes of academic adopters.
