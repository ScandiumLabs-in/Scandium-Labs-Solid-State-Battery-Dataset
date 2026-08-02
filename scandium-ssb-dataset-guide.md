# Scandium Labs — Solid-State Battery Materials Dataset
## Build Guide & Implementation Plan (Phase-Wise)

**Goal:** Build the single best one-stop, ML-ready dataset of solid-state battery (SSB) electrolyte materials — spanning all 8 SSB electrolyte families — designed specifically to train physics-informed GNNs like PIGNet V2, and to be licensable/usable by university electrochemistry labs and other model builders.

---

## 0. Design Principles

1. **Coverage over depth first, then depth on the winners.** Cast a wide net across all 8 families before deep-enriching any one.
2. **Unified schema.** Every material — regardless of source (DFT database, literature-mined, in-house computed) — lands in one consistent structure/property schema. This is the single biggest differentiator vs. Materials Project, JARVIS, AFLOW existing separately.
3. **Ionic conductivity is the scarce, valuable label.** Structural and thermodynamic data (formation energy, band gap, stability) is abundant across existing DFT repositories. Room-temperature ionic conductivity (σ_RT) and activation energy (Ea) are what's genuinely scarce and what makes this dataset valuable — prioritize sourcing and computing these.
4. **Provenance and confidence tracking on every row.** Tag each property with source (DFT-computed / experimental / literature-mined / model-predicted), method (functional used, mined-from-text confidence), and uncertainty where available. No dataset in this space does this well — it's a wedge.
5. **Reproducible, versioned, and citable.** Treat this like a scientific artifact (DOI via Zenodo, changelog, semantic versioning) not just a CSV dump.

---

## 1. Scope: The 8 SSB Electrolyte Families

| # | Family | Examples | Notes |
|---|--------|----------|-------|
| 1 | Sulfides | Li10GeP2S12 (LGPS), Li6PS5Cl (argyrodite), Li3PS4 | Highest conductivity class; air-sensitive |
| 2 | Oxides (garnet) | Li7La3Zr2O12 (LLZO) | Most studied; stable in air |
| 3 | Oxides (perovskite) | Li3xLa(2/3-x)TiO3 (LLTO) | Grain-boundary limited |
| 4 | Oxides (NASICON) | LiZr2(PO4)3, LAGP, LATP | Good stability, moderate conductivity |
| 5 | Halides | Li3InCl6, Li3YCl6, Li2ZrCl6 | High voltage stability, emerging class |
| 6 | Hydrides / Borohydrides | LiBH4, Li2B12H12 | High conductivity at elevated T |
| 7 | Antiperovskites | Li3OCl, Li3OBr | Promising, less mature |
| 8 | Polymer/composite & hybrid SSEs | PEO-LiTFSI composites, ceramic-polymer blends | Structurally distinct — needs separate featurization path |

Each family gets its own ingestion sub-pipeline (family 8 in particular needs different descriptors since "crystal structure" doesn't cleanly apply to amorphous polymer phases — plan for a parallel schema branch here).

---

## 2. Target Schema (per material record)

**Identity & provenance**
- `material_id`, `source_db`, `source_id`, `family`, `ingestion_date`, `confidence_tier`

**Structure**
- CIF / POSCAR structure file, space group, lattice parameters, Li-site occupancy, coordination environment, structure type (ordered/disordered), unrelaxed + relaxed structures (both — PIGNet V2 predicts from unrelaxed)

**Thermodynamics & electronics**
- Formation energy, energy above hull, band gap, decomposition products, electrochemical stability window (vs Li/Li+)

**Ion transport (the scarce label)**
- Room-temp ionic conductivity σ_RT, activation energy Ea, conductivity vs. T curve (if available), computation/measurement method (AIMD, NEB, impedance spectroscopy, etc.), temperature range measured

**Mechanical**
- Elastic moduli, shear modulus (relevant to dendrite suppression), where available

**Synthesis-accessibility (secondary but valuable)**
- Precursors, synthesis route tags (solid-state, sol-gel, mechanochemical), reported by literature-mining — flags "is this actually makeable"

**ML-ready features**
- Graph representation (nodes/edges pre-built for GNN ingestion), 3-body angular features, composition-based descriptors (Magpie/matminer), symmetry-based descriptors

---

## Phase 0 — Scoping & Requirements (Week 1–2)

- Finalize the 8-family taxonomy and the unified schema above (get sign-off, since retrofitting schema later is expensive).
- Define the minimum viable record: what fields are *required* vs. optional per family.
- Decide dataset hosting/versioning strategy up front: Hugging Face Datasets (best discoverability for ML crowd) + Zenodo (DOI, citability) + GitHub for pipeline code.
- Define success metrics: target row count per family, target % with real (not imputed) ionic conductivity labels, target license (CC-BY-4.0 recommended for academic adoption).

**Deliverable:** schema spec doc (JSON schema / Pydantic model), hosting decision, success metrics doc.

---

## Phase 1 — Source Identification & Access (Week 2–4)

**Primary structural/DFT sources (bulk API pull):**
- Materials Project (API, pymatgen-native) — broadest coverage, includes Li-containing compounds
- JARVIS-DFT (NIST) — strong on 2D + defect data, good complement to MP
- OQMD — large formation-energy coverage
- AFLOW — good for high-throughput screened low-T phases
- ICSD (if institutional access via VIT Bhopal or a lab partner) — experimental structures, gold-standard for "this actually exists"
- NOMAD — raw DFT calculation repository, useful for provenance-rich re-mining

**Ionic conductivity — the hard part (needs literature mining):**
- No clean bulk API exists for σ_RT/Ea across SSB literature. Plan for:
  - Semantic Scholar / Crossref API to pull candidate papers (search terms per family)
  - LLM-assisted extraction pipeline (table/text parsing) to pull conductivity values, temperatures, and composition from PDFs — this is a build-it-yourself component and the highest-leverage phase
  - Known curated seed sets to bootstrap from: existing published SSE conductivity compilations (there are a handful of review-paper appendix tables — good seed data, small but high-quality)

**Deliverable:** access credentials/API keys secured, source inventory spreadsheet with expected row counts and licensing terms per source.

---

## Phase 2 — Ingestion Pipeline (Week 4–8)

- Build per-source connector scripts (pymatgen `MPRester`, JARVIS-tools, AFLOW REST API, OQMD REST) that pull raw records into a staging store (start simple: partitioned Parquet on disk/S3, not a database yet).
- Normalize every source's structure representation to a common CIF + pymatgen `Structure` object.
- Tag every ingested record immediately with `source_db`, `source_id`, `ingestion_date` — never lose provenance at ingestion time, it's expensive to reconstruct later.
- Family-classification step: a rules-based classifier (composition + structure-type matching) to auto-tag each ingested structure into one of the 8 families, with manual spot-checking on a sample.

**Deliverable:** raw staging dataset, one partition per source, ~first full pull complete.

---

## Phase 3 — Literature-Mining Pipeline for Conductivity Labels (Week 6–12, runs parallel to Phase 2)

This is the differentiator phase — treat it as its own mini-project.

1. Paper retrieval: query Semantic Scholar API per family + "ionic conductivity" + "solid electrolyte."
2. PDF/table parsing: use a PDF-to-structured-data pipeline (start with tools like GROBID for structure extraction, then an LLM extraction pass over tables/figures/captions to pull σ, Ea, T, composition).
3. Composition-to-structure linking: match extracted compositions back to structures already ingested in Phase 2 (fuzzy match on formula + space group where reported).
4. Human-in-the-loop QC: spot-check a statistically meaningful sample (e.g., 10–15%) of extracted values against source PDFs before trusting the pipeline at scale.
5. Confidence tagging: every mined value gets a confidence tier (verified-by-human / high-confidence-LLM-extraction / low-confidence) — never mix silently with DFT-native data.

**Deliverable:** conductivity-labeled subset, with confidence tiers, linked back to structural records where possible.

---

## Phase 4 — Cleaning, Deduplication & Standardization (Week 10–14)

- Cross-source deduplication: same compound often appears in MP, OQMD, and AFLOW with slightly different relaxed geometries — decide a canonicalization rule (e.g., prefer lowest-energy relaxed structure, keep others as alternate polymorphs, not duplicates).
- Outlier/sanity filtering: flag physically implausible values (e.g., conductivity values inconsistent with reported Ea via Arrhenius check) for manual review rather than silent inclusion.
- Missing-data strategy: explicitly do NOT impute ionic conductivity — leave null and flag `label_available: false`. Imputing the scarce label defeats the dataset's purpose.
- Unit standardization pass across all sources (eV vs kJ/mol, S/cm vs mS/cm, etc.) — a notoriously easy place for silent bugs.

**Deliverable:** cleaned, deduplicated, canonical dataset version (v0.1 internal).

---

## Phase 5 — DFT Augmentation for Gaps (Week 12–20, ongoing)

For high-priority compositions/families with structural data but missing thermodynamic/electronic labels (or where you want higher-quality data than what was scraped):

- Set up a Custodian + VASP (or Quantum Espresso if compute-constrained) automated workflow, mirroring Materials Project's calculation scheme, so outputs are schema-compatible.
- Prioritize compute budget on: (a) family gaps (e.g., halides and antiperovskites are undersampled in MP/OQMD relative to sulfides/garnets), (b) compositions flagged as synthesis-accessible from Phase 3 but structurally under-characterized.
- For AIMD-based conductivity estimation (a proxy where experimental values are unavailable): budget this carefully — AIMD runs are expensive; use only for a curated priority list, not the full dataset.
- Use Kaggle/university HPC credits where possible before committing to paid cloud compute.

**Deliverable:** augmented dataset (v0.2), with new DFT-computed rows clearly tagged `source_db: scandium-labs-computed`.

---

## Phase 6 — Feature Engineering for ML-Readiness (Week 16–22, overlaps Phase 5)

- Build graph representations per structure (matching PIGNet V2's input format: attention-gated message-passing graphs with 3-body angular edge features) — precompute and cache these, don't make every training run recompute graphs from CIFs.
- Generate composition-based descriptor sets via matminer/Magpie for baseline/non-GNN model compatibility (so the dataset is usable by groups not running GNNs).
- Precompute standard train/val/test splits — critically, split by *composition family* and by *unique composition* (not just by structure) to prevent data leakage between polymorphs of the same compound landing in train and test.
- Provide a small, hand-curated "gold" benchmark subset (highest-confidence conductivity labels only) for leaderboard-style model comparison — this becomes a citable contribution in its own right.

**Deliverable:** ML-ready release candidate (v0.9) — graphs, descriptors, splits, benchmark subset.

---

## Phase 7 — Validation & Quality Control (Week 20–24)

- Statistical sanity checks per family: distribution of formation energies, band gaps, conductivities — compare against known literature ranges per family as a smell test.
- Cross-validation against a small set of well-known, high-confidence compounds (LGPS, LLZO, Li6PS5Cl) — these are the "unit tests" of the dataset; if their values look wrong, something upstream broke.
- External review: if possible, get 1–2 electrochemistry academics (potentially via your VIT Bhopal network or [[prakash-n-b]]) to sanity-check a sample before public release — this also seeds early credibility/adoption in the target customer segment.

**Deliverable:** validation report, v1.0 release candidate.

---

## Phase 8 — Documentation & Datasheet (Week 22–25, parallel)

- Write a "Datasheet for Datasets" (Gebru et al. format is the accepted academic standard) — motivation, composition, collection process, known limitations/biases (e.g., sulfides likely overrepresented since they're most-studied), recommended uses and misuses.
- Per-family README explaining schema quirks (especially family 8, polymer/composite, which breaks the standard crystal-graph assumption).
- Confidence-tier documentation: make very explicit which rows are DFT-verified vs. literature-mined vs. computed in-house, so downstream users can filter by trust level.
- Citation file (CITATION.cff) and versioned changelog from day one.

**Deliverable:** full documentation set, ready for public release.

---

## Phase 9 — Release, Distribution & Maintenance (Week 24+)

- Publish v1.0 on Hugging Face Datasets (primary discovery channel for ML practitioners) and Zenodo (DOI for academic citation).
- Distribute to the target GTM segment: university electrochemistry labs — pair the release with a short usage guide and the gold benchmark subset as a hook.
- Set a maintenance cadence: quarterly ingestion of new Materials Project/JARVIS/OQMD entries, rolling literature-mining passes as new papers publish, versioned releases (v1.1, v1.2...) rather than silent updates.
- Consider a community contribution path (structured PR/issue template) once the dataset has traction, so labs can submit their own measured conductivity values with provenance.

**Deliverable:** public v1.0 release, maintenance plan documented.

---

## Suggested Tech Stack Summary

| Layer | Tool |
|-------|------|
| Structure handling | pymatgen, ASE |
| DFT sources | Materials Project API, JARVIS-tools, AFLOW REST, OQMD REST |
| DFT compute (gap-filling) | VASP or Quantum Espresso + Custodian for automation |
| Literature mining | Semantic Scholar API, GROBID, LLM-based table/text extraction |
| Descriptors | matminer, Magpie |
| Storage (staging) | Partitioned Parquet |
| Storage (release) | Hugging Face Datasets + Zenodo (DOI) |
| Versioning | DVC or plain semantic-versioned releases + changelog |
| Compute budget | University HPC / Kaggle credits before paid cloud |

---

## Rough Timeline (Compressed View)

- **Weeks 1–2:** Scoping, schema lock
- **Weeks 2–8:** Bulk DFT-source ingestion
- **Weeks 6–12:** Literature-mining pipeline (parallel)
- **Weeks 10–14:** Cleaning, dedup, canonicalization
- **Weeks 12–20:** DFT gap-filling compute
- **Weeks 16–22:** Feature engineering, graph precompute, splits
- **Weeks 20–24:** Validation, external review
- **Weeks 22–25:** Documentation
- **Week 24+:** Public release + ongoing maintenance

~6 months to a credible v1.0, assuming this runs alongside PIGNet V2 work rather than fully blocking it — the two feed each other (dataset improves model, model's data needs sharpen dataset priorities).

---

## What Makes This "The Best One-Stop Dataset" (Positioning)

1. Only dataset unifying all 8 SSB families under one schema — existing sources are general-materials databases (MP, OQMD) with no SSB-specific curation, or narrow single-family compilations buried in paper appendices.
2. Only dataset treating ionic conductivity as a first-class, provenance-tagged label rather than an afterthought.
3. Ships pre-built as GNN-ready graphs, not just raw CIFs — removes the single biggest friction point for ML researchers in this space.
4. Confidence-tiered by design — usable by both academics who need experimental-only subsets and ML researchers who want maximum row count.
