# Scandium Labs — Solid-State Battery Materials Dataset
## Complete Build Guide & Implementation Plan — Start to End, Phase-Wise

**Mission:** Build the definitive, one-stop, ML-ready dataset of solid-state battery (SSB) electrolyte materials — spanning all 8 SSB electrolyte families — engineered specifically for training physics-informed GNNs (PIGNet V2 and beyond), and credible enough for university electrochemistry labs to adopt as ground truth.

This is written as an execution document. Every phase has: objectives, detailed sub-steps, concrete tools/commands, deliverables, exit criteria, and common failure modes to watch for.

---

## Table of Contents

0. Design Principles & Strategic Positioning
1. Scope Definition — The 8 SSB Families in Depth
2. Full Data Schema Specification
3. Phase 0 — Scoping & Governance
4. Phase 1 — Source Landscape & Access
5. Phase 2 — Ingestion Pipeline Engineering
6. Phase 3 — Literature Mining Pipeline (Conductivity Extraction)
7. Phase 4 — Cleaning, Deduplication, Canonicalization
8. Phase 5 — DFT Gap-Filling Compute Pipeline
9. Phase 6 — Feature Engineering & Graph Construction
10. Phase 7 — Validation, QC & Statistical Auditing
11. Phase 8 — Documentation, Datasheet & Governance Artifacts
12. Phase 9 — Release, Distribution & GTM
13. Phase 10 — Maintenance, Versioning & Community Loop
14. Team, Roles & Time Allocation
15. Compute & Cost Budget
16. Risk Register & Mitigations
17. Benchmark Compound List ("Unit Tests" for the Dataset)
18. Competitive Landscape — Why This Wins
19. Success Metrics & KPIs
20. Appendix: Reference Tools, APIs, and Reading List

---

## 0. Design Principles & Strategic Positioning

1. **Coverage first, depth on winners second.** Ingest broadly across all 8 families before deep-enriching any single one — premature depth on one family (e.g., sulfides, which are already well-covered by Materials Project) wastes the differentiation window.
2. **The scarce asset is ionic conductivity (σ_RT) and activation energy (Ea), not structure.** Structural/thermodynamic data is a commodity — Materials Project, JARVIS-DFT, OQMD, and AFLOW already give this away for free. What nobody has assembled at scale, cleanly, is transport-property labels tied to structure with provenance. This is the wedge. Every design decision downstream should protect this asset's quality.
3. **One unified schema across heterogeneous sources.** A record pulled from Materials Project, one mined from a 2019 Chemistry of Materials paper, and one computed in-house via VASP must all resolve to the same schema. This is what makes the dataset "one-stop" instead of "yet another aggregator link list."
4. **Provenance and confidence on every single field, not just every row.** Field-level tagging (not just row-level) is what lets a downstream user say "give me only DFT-native formation energies but literature-mined conductivities" — this granularity is a genuine differentiator versus every public materials database, which is provenance-blind at the field level.
5. **Never silently impute the scarce label.** Null + `label_available: false` beats a guessed conductivity value. Imputed transport properties would poison exactly the signal PIGNet V2 needs to learn from.
6. **Treat the dataset as a citable scientific artifact, not a CSV dump.** DOI, versioning, datasheet, changelog, benchmark subset — this is what earns adoption from academic labs (your GTM segment) versus a GitHub repo nobody trusts enough to build a thesis on.
7. **Build the pipeline, not just the dataset.** The ingestion + literature-mining + DFT-augmentation pipeline is a reusable asset in itself — every future release (v1.1, v2.0) should be a re-run, not a rebuild. Invest accordingly in pipeline code quality even though the "deliverable" the world sees is the dataset.

---

## 1. Scope Definition — The 8 SSB Families in Depth

For each family: representative compounds, why it matters, known conductivity range, known data gaps, and family-specific ingestion notes.

### 1.1 Sulfides
- **Representatives:** Li10GeP2S12 (LGPS), Li6PS5Cl / Li6PS5Br (argyrodites), Li3PS4 (β and γ phases), Li7P3S11.
- **Why it matters:** Highest bulk ionic conductivities known for inorganic SSEs (10⁻²–10⁻³ S/cm range), closest to commercial deployment (Toyota, Samsung SDI programs use sulfide-class electrolytes).
- **Conductivity range:** ~10⁻⁵ to 10⁻² S/cm at room temp depending on composition/doping.
- **Data gaps:** Doped/substituted variants (halogen-doped argyrodites) are under-represented in bulk DFT databases — these are exactly what recent high-conductivity records come from, so prioritize literature mining here.
- **Ingestion notes:** Air/moisture sensitivity means many reported values come with synthesis-condition caveats — capture synthesis atmosphere as a field, it correlates with reported conductivity variance.

### 1.2 Oxide — Garnets
- **Representatives:** Li7La3Zr2O12 (LLZO, both cubic and tetragonal phases), Al- or Ta-doped LLZO variants.
- **Why it matters:** Most heavily studied SSE family; air-stable, good electrochemical stability window against Li metal.
- **Conductivity range:** ~10⁻³–10⁻⁴ S/cm (cubic phase; tetragonal is 2 orders lower — phase matters enormously here).
- **Data gaps:** Grain-boundary conductivity vs. bulk conductivity are frequently conflated in reported literature — schema must distinguish these explicitly (`conductivity_type: bulk | grain_boundary | total`).

### 1.3 Oxide — Perovskite
- **Representatives:** Li3xLa(2/3-x)TiO3 (LLTO).
- **Why it matters:** High bulk conductivity but grain-boundary-limited overall performance — a good case study for the bulk-vs-total distinction above.
- **Data gaps:** Ti⁴⁺ reduction to Ti³⁺ against Li metal is a known instability — this affects electrochemical stability window data, capture as a stability flag.

### 1.4 Oxide — NASICON
- **Representatives:** LiZr2(PO4)3, Li1+xAlxGe2-x(PO4)3 (LAGP), Li1+xAlxTi2-x(PO4)3 (LATP).
- **Why it matters:** Good chemical/air stability, moderate conductivity, cheaper than garnets.
- **Data gaps:** Ge/Ti reduction against Li metal (similar issue to LLTO) — many NASICON compounds need a protective interlayer in practice; capture "requires_interlayer" as a derived/literature-mined flag where reported.

### 1.5 Halides
- **Representatives:** Li3InCl6, Li3YCl6, Li2ZrCl6, Li3ScCl6.
- **Why it matters:** Emerging class (post-2018 surge in publications), high oxidative stability enabling high-voltage cathodes — likely the fastest-growing family in the literature right now, so literature-mining coverage matters more here than DFT-database coverage.
- **Data gaps:** Youngest family — expect the sparsest DFT-database coverage and the highest ratio of literature-mined to database-native records. Budget mining effort accordingly (weight sampling toward this family in Phase 3).

### 1.6 Hydrides / Borohydrides
- **Representatives:** LiBH4 (high-T hexagonal phase has high conductivity), Li2B12H12, LiBH4-LiI solid solutions.
- **Why it matters:** Very high conductivity at elevated temperature via order-disorder phase transitions; lightweight.
- **Data gaps:** Conductivity is highly temperature-and-phase dependent (order-disorder transition around 110°C for LiBH4) — schema must capture the full conductivity-vs-T curve, not just a single σ_RT point, or this family's data is nearly meaningless.

### 1.7 Antiperovskites
- **Representatives:** Li3OCl, Li3OBr, mixed Li3OCl(1-x)Br(x).
- **Why it matters:** Theoretically promising (early DFT predictions suggested very high conductivity), but experimental synthesis has proven difficult — expect a gap between predicted and measured values; tag both explicitly (`conductivity_source_type: predicted | measured`).
- **Data gaps:** Least mature family experimentally; DFT-predicted values dominate. Flag this imbalance clearly in documentation so downstream users don't over-trust this family's numbers.

### 1.8 Polymer / Composite / Hybrid SSEs
- **Representatives:** PEO-LiTFSI, PVDF-based composites, ceramic-in-polymer blends (e.g., LLZO-PEO composites).
- **Why it matters:** Most manufacturable at scale today, flexible form factor.
- **Structural note:** These are frequently amorphous or semi-crystalline — the standard "crystal graph" input PIGNet V2 expects does not cleanly apply. This family needs a **parallel schema branch**: composition-weighted descriptors, polymer-chain topology features (if modeled), or a coarse-grained representative structure rather than a single relaxed crystal structure.
- **Data gaps:** Conductivity is strongly processing-dependent (crystallinity %, plasticizer content, salt concentration) — capture processing metadata as first-class fields, not free text, or this family's data will be unusable for regression.

---

## 2. Full Data Schema Specification

Design as a versioned JSON Schema / Pydantic model. Below is the field-level spec.

### 2.1 Identity & Provenance Block
```
material_id: str            # Scandium-Labs-internal canonical ID
source_db: enum             # materials_project | jarvis | oqmd | aflow | icsd | nomad | literature_mined | scandium_computed
source_id: str               # original ID in source system
family: enum                 # one of the 8 families above
subfamily_tag: str[]          # e.g., "argyrodite", "garnet_cubic", "garnet_tetragonal"
ingestion_date: datetime
schema_version: str
confidence_tier: enum        # verified_human | high_confidence_extraction | low_confidence_extraction | dft_native | dft_computed_inhouse
```

### 2.2 Structure Block
```
structure_relaxed: CIF/POSCAR (nullable)
structure_unrelaxed: CIF/POSCAR (nullable)   # PIGNet V2 needs unrelaxed input — do not skip this
space_group: str
lattice_params: {a, b, c, alpha, beta, gamma}
li_site_occupancy: float[]        # per symmetry-distinct Li site
coordination_environment: str[]   # per-site, from pymatgen CrystalNN or similar
structure_type: enum              # ordered | disordered | amorphous | semi_crystalline
is_experimental_structure: bool   # true if from ICSD or literature refinement, false if theoretical/relaxed-only
```

### 2.3 Thermodynamics & Electronics Block
```
formation_energy_per_atom: float (eV)
energy_above_hull: float (eV)
band_gap: float (eV)
decomposition_products: str[]
electrochemical_stability_window: {lower_V, upper_V}  # vs Li/Li+
functional_used: enum            # PBE | PBE+U | SCAN | HSE06 | r2SCAN etc.
```

### 2.4 Ion Transport Block (the core scarce asset)
```
sigma_RT: float (S/cm), nullable
sigma_vs_T_curve: [(T_K, sigma)][], nullable   # full curve where available — critical for hydrides/borohydrides
activation_energy_Ea: float (eV), nullable
conductivity_type: enum          # bulk | grain_boundary | total
conductivity_source_type: enum   # measured | AIMD_computed | NEB_computed | predicted_empirical
measurement_method: str          # e.g., "AC impedance spectroscopy", nullable if computed
temperature_range_measured: {min_K, max_K}, nullable
label_available: bool            # explicit flag — never silently null without this being true
```

### 2.5 Mechanical Block
```
bulk_modulus: float (GPa), nullable
shear_modulus: float (GPa), nullable   # relevant to dendrite-suppression screening
elastic_tensor: matrix, nullable
```

### 2.6 Synthesis-Accessibility Block (secondary but high value for GTM)
```
precursors: str[]
synthesis_route: enum[]           # solid_state | sol_gel | mechanochemical | melt_quench | co_precipitation
synthesis_atmosphere: str, nullable   # relevant esp. for sulfides
requires_interlayer: bool, nullable   # relevant for NASICON/perovskite vs Li metal
processing_metadata: dict, nullable   # crystallinity %, plasticizer content, etc. — required for family 8
```

### 2.7 ML-Ready Features Block
```
graph_representation: precomputed object (node/edge features matching PIGNet V2 input spec)
composition_descriptors: dict     # Magpie/matminer feature vector
symmetry_descriptors: dict
split_assignment: enum            # train | val | test | gold_benchmark
split_group_key: str              # composition-family key used to prevent leakage across splits
```

### 2.8 Text Provenance Block (for literature-mined records)
```
source_doi: str, nullable
source_paper_title: str, nullable
extraction_method: enum           # human_curated | grobid_table_parse | llm_extraction
extraction_confidence_score: float, nullable
extraction_reviewer: str, nullable  # who spot-checked it, if applicable
```

---

## Phase 0 — Scoping & Governance (Week 1–2)

**Objectives:** Lock the schema, decide hosting/licensing, define what "done" looks like.

**Sub-steps:**
1. Circulate the schema draft (Section 2) internally; run it against 5–10 sample compounds by hand from each family to check it doesn't break on edge cases (especially family 8's amorphous structures and family 6's temperature-dependent conductivity curves).
2. Decide licensing: CC-BY-4.0 recommended — permissive enough for academic adoption (your GTM target) while requiring attribution back to Scandium Labs.
3. Decide hosting stack: Hugging Face Datasets (primary discovery surface for the ML crowd) + Zenodo (DOI + long-term archival, required for academic citability) + GitHub (pipeline code, issue tracker for community corrections).
4. Define row-count and quality targets per family — don't leave this vague. Example targets:
   - Sulfides: 3,000+ structural records, 300+ conductivity-labeled
   - Garnets: 1,500+ structural, 200+ conductivity-labeled
   - Halides: 800+ structural, 150+ conductivity-labeled (youngest family, weight mining effort here)
   - Antiperovskites: 200+ structural, 50+ conductivity-labeled (smallest mature literature)
   - (Set your own numbers per family based on Phase 1 source survey — the above are illustrative starting targets, revise after the source inventory.)
5. Decide the "gold benchmark subset" criteria up front (Section 17) so Phase 6/7 has a clear target to build toward.

**Deliverables:** locked schema (v1 JSON Schema file), licensing decision doc, hosting decision doc, per-family target sheet.

**Exit criteria:** schema survives the 5–10 hand-tested compounds without structural changes needed.

---

## Phase 1 — Source Landscape & Access (Week 2–4)

**Objectives:** Inventory every usable source, secure access, estimate expected yield per source per family.

### 1.1 Structural/DFT bulk sources
| Source | Access method | Expected strength | Notes |
|---|---|---|---|
| Materials Project | REST API via `mp-api` / `pymatgen.ext.matproj` | Broadest Li-compound coverage | Free API key, rate-limited |
| JARVIS-DFT (NIST) | `jarvis-tools` Python package | Strong defect/2D data, good complement | Free, bulk-downloadable |
| OQMD | REST API or bulk MySQL dump | Large formation-energy coverage | Free |
| AFLOW | AFLOW REST API (`aflow` Python wrapper) | High-throughput screened phases | Free |
| ICSD | Institutional license required | Experimental (gold-standard) structures | Check if VIT Bhopal or a partner lab has institutional access — this is the single highest-value source to unlock if available, since it's the only one giving "this compound has actually been synthesized" confidence |
| NOMAD | REST API, bulk archive download | Raw calculation provenance, good for re-mining metadata | Free |

### 1.2 Literature/transport-property sources
| Source | Access method | Purpose |
|---|---|---|
| Semantic Scholar API | REST API, free tier with key | Paper discovery per family search terms |
| Crossref API | REST API | DOI resolution, metadata |
| Google Scholar (manual/scripted with care) | No official API — use sparingly, respect ToS | Supplementary discovery only |
| Known review-paper appendices | Manual curation | High-quality seed data — a handful of well-cited SSE review papers contain hand-curated conductivity tables; these are small but nearly ground-truth and should seed the confidence-tier system |

### 1.3 Source survey deliverable
For each source × family combination, run a quick count query (e.g., MP query filtered by Li-containing + relevant anion chemistry) and log expected record counts into a spreadsheet. This becomes the basis for revising Phase 0's per-family targets and for prioritizing Phase 3 literature-mining effort toward under-covered families (expect halides and antiperovskites to be the thinnest in bulk DFT sources).

**Deliverables:** API keys/credentials secured and stored securely (not in the repo), source inventory spreadsheet with per-source-per-family expected counts, licensing terms logged per source (some sources restrict redistribution — check before Phase 9 release planning).

**Exit criteria:** every source in section 1.1 has been test-queried successfully at least once; ICSD access status resolved (yes/no) since it affects Phase 1 scope.

---

## Phase 2 — Ingestion Pipeline Engineering (Week 4–8)

**Objectives:** Reliable, re-runnable connectors from every structural source into a common staging format.

**Sub-steps:**
1. Build one connector script per source (`ingest_mp.py`, `ingest_jarvis.py`, `ingest_oqmd.py`, `ingest_aflow.py`, `ingest_icsd.py` if available, `ingest_nomad.py`). Each script:
   - Queries by composition/chemistry filters relevant to the 8 families (e.g., Li + {S,P} for sulfides; Li + {La,Zr,O} for garnets, etc.)
   - Converts native structure format to a common `pymatgen.Structure` object
   - Writes out to partitioned Parquet: `staging/{source_db}/{family}/part-*.parquet`
   - Logs provenance fields (Section 2.1) at write time — never a separate reconciliation step later
2. Build the family-classifier: a rules-based first pass (composition pattern matching + structure-type heuristics from pymatgen's structure matcher against known family archetypes), producing `family` and `subfamily_tag`. Manually spot-check ~50 compounds per family against the auto-classifier output before trusting it at scale.
3. Build the unrelaxed-structure capture path specifically — many source APIs return only the relaxed/final structure by default; you likely need the calculation's initial structure from the same entry (MP exposes this via `structure` vs `initial_structure` fields; JARVIS/OQMD equivalents vary) — do not skip this, since PIGNet V2's whole value proposition is predicting from unrelaxed input.
4. Set up basic pipeline orchestration (even a simple Makefile or Prefect/Airflow DAG is fine at this scale) so the full ingestion is a single reproducible command, not a manual notebook run — this matters enormously for Phase 10 maintenance.
5. Write ingestion-level tests: row-count sanity checks per source, schema-conformance checks (every required field present), duplicate-ID checks within a single source.

**Deliverables:** working per-source connectors, raw staging dataset (first full pull), pipeline orchestration script, ingestion test suite.

**Exit criteria:** full pipeline runs end-to-end from a clean environment without manual intervention; staging dataset row counts are within expected range of Phase 1's source survey.

---

## Phase 3 — Literature Mining Pipeline for Conductivity Labels (Week 6–12, parallel to Phase 2)

This is the highest-leverage, highest-difficulty phase — treat it as its own sub-project with its own mini-milestones.

### 3.1 Paper discovery
- Query Semantic Scholar API per family using term combinations: `{family representative terms} AND ("ionic conductivity" OR "Li-ion conductivity") AND ("solid electrolyte" OR "solid-state electrolyte")`.
- Deduplicate against DOI, rank by citation count and recency (weight toward 2015+ for halides/antiperovskites given they're younger fields; broader date range acceptable for sulfides/garnets).
- Target: 200–500 candidate papers per family for initial triage.

### 3.2 Triage & filtering
- Abstract-level LLM classification pass: does this paper report a measured or computed σ_RT/Ea value for a specific composition? (binary classify to avoid wasting extraction effort on papers that only cite others' values)
- Expect roughly 20–40% of candidate papers to survive triage with an actual reported value.

### 3.3 Extraction pipeline
1. PDF acquisition (respect publisher access rights — use institutional access, open-access repositories, or author-shared preprints only; do not scrape paywalled content).
2. Structural parsing with GROBID to extract clean text + table structure from the PDF.
3. LLM-based extraction pass over the parsed tables/figures/captions/body text, prompted to extract: composition, σ value + units, T at which measured, Ea if reported, measurement method, synthesis route if stated. Extraction should output structured JSON matching the schema in Section 2.4/2.6 directly.
4. Composition-to-structure linking: fuzzy-match extracted composition (accounting for common formula-writing variance, e.g., "Li6PS5Cl" vs "Li6PS5Cl0.9Br0.1") against structures already ingested in Phase 2; where no structural match exists, flag for a Phase 5 DFT computation candidate.

### 3.4 Human-in-the-loop QC
- Spot-check a statistically meaningful sample (10–15% minimum, weighted toward papers with unusual/outlier extracted values) against the source PDF.
- Track extraction accuracy rate per family — if accuracy on a family falls below ~85%, revisit the extraction prompt/method for that family before trusting further automated runs.
- Every extracted record gets `extraction_confidence_score` and, for human-reviewed ones, `extraction_reviewer` populated (Section 2.8) — never silently mix reviewed and unreviewed records without this tag.

### 3.5 Seed data bootstrap
- Before running the full pipeline at scale, hand-enter data from 2–3 well-known SSE review-paper appendix tables. This gives an immediate high-confidence seed set to validate the extraction pipeline against (i.e., run the pipeline on the same source papers and check if it reproduces the hand-curated values).

**Deliverables:** conductivity-labeled subset with full provenance and confidence tiers, extraction-accuracy report per family, seed validation report.

**Exit criteria:** extraction pipeline validated against hand-curated seed set at ≥85% field-level accuracy; per-family conductivity-labeled row counts meet or approach Phase 0 targets (revise targets if a family is structurally thin in the literature — e.g., antiperovskites may cap out lower than hoped, and that's a real finding to document, not a pipeline failure).

---

## Phase 4 — Cleaning, Deduplication & Canonicalization (Week 10–14)

**Sub-steps:**
1. **Cross-source structural deduplication:** the same compound frequently appears in MP, OQMD, and AFLOW with slightly different relaxed geometries (different functional, different convergence settings). Canonicalization rule: prefer the lowest-energy relaxed structure as canonical; retain others as `alternate_polymorph` links rather than discarding — polymorph energy differences are scientifically meaningful, not noise.
2. **Composition-level dedup for literature-mined records:** multiple papers often report conductivity for "the same" nominal composition with real experimental variance (synthesis-route dependent). Do not average these silently — retain all measurements linked to one composition, each with its own provenance, and let downstream users choose an aggregation strategy. Optionally provide a pre-computed `sigma_RT_median` and `sigma_RT_std` per composition as a convenience field, clearly labeled as derived.
3. **Outlier/sanity filtering:** cross-check reported (σ, Ea) pairs against the Arrhenius relationship at the reported temperature; flag pairs that are wildly inconsistent for manual review rather than silent inclusion or silent exclusion.
4. **Unit standardization:** enforce eV (not kJ/mol) for energies, S/cm (not mS/cm or Ω⁻¹cm⁻¹ inconsistently) for conductivity, Kelvin (not Celsius) for temperature — write unit tests that catch any pipeline stage introducing unit drift, this is the single easiest place for a silent, hard-to-detect bug in a materials dataset.
5. **Missing-data policy enforcement:** run a pipeline-wide audit confirming no field was silently imputed — every null should be an explicit null with `label_available: false` where relevant, never a placeholder value like 0 or -1.

**Deliverables:** cleaned, deduplicated, canonical dataset (internal v0.1), dedup/canonicalization decision log, unit-consistency test suite.

**Exit criteria:** zero unit-inconsistency test failures; dedup logic validated on a manually-checked sample of ~30 known-duplicate compound pairs.

---

## Phase 5 — DFT Gap-Filling Compute Pipeline (Week 12–20, ongoing)

**Objectives:** Fill structural/thermodynamic gaps for high-priority compositions, and (selectively) compute AIMD-based conductivity estimates where no experimental value exists.

**Sub-steps:**
1. Set up an automated VASP (preferred, matches Materials Project's calculation scheme for schema compatibility) or Quantum Espresso (if compute-constrained/open-source requirement) workflow using Custodian for job management and error handling, mirroring MP's INCAR/KPOINTS conventions so outputs are directly schema-compatible (same functional choices: PBE for standard relaxations, consider SCAN or r2SCAN for higher-accuracy formation energies on priority compounds).
2. Prioritization queue for compute budget, in order:
   - (a) Compositions flagged in Phase 3 as literature-reported-but-unmatched-to-structure (highest value — these already have a real conductivity label waiting for a structure)
   - (b) Family gaps identified in Phase 1's source survey (expect halides, antiperovskites, and doped/substituted sulfide variants to need the most fill-in)
   - (c) Compositions flagged as synthesis-accessible (Section 2.6) but structurally uncharacterized
3. **AIMD-based conductivity estimation** (proxy for experimental measurement, use sparingly): run only on a curated priority list (not the full dataset — these are expensive, typically tens of thousands of core-hours per compound for statistically meaningful diffusion statistics). Tag all AIMD-derived conductivities with `conductivity_source_type: AIMD_computed` and never blend silently with measured values in any headline dataset statistic.
4. Batch job submission and monitoring — build simple dashboards/logs (even a status spreadsheet is fine at this scale) tracking job success/failure/convergence-issues rate, since DFT job failure rates of 10-20% are normal and need a retry/triage loop rather than being treated as pipeline bugs.
5. Use university HPC allocations (VIT Bhopal compute resources if accessible) and Kaggle/free-tier compute credits before committing to paid cloud compute — budget paid compute (Section 15) only for the highest-priority compound list if free/institutional resources are insufficient.

**Deliverables:** augmented dataset (v0.2) with new DFT-computed rows tagged `source_db: scandium_computed`, compute job log/dashboard, AIMD priority-list results.

**Exit criteria:** priority queue (a) and (b) above show measurable reduction in gap count versus Phase 1's source survey; job failure/retry loop is stable (failure rate understood and triaged, not silently dropped).

---

## Phase 6 — Feature Engineering & Graph Construction (Week 16–22, overlaps Phase 5)

**Sub-steps:**
1. **Graph representation matching PIGNet V2's input spec:** build the attention-gated message-passing graph structure with 3-body angular edge features directly from `structure_unrelaxed`, precomputed and cached (e.g., as serialized `torch_geometric.Data` objects or equivalent) — never require a training run to recompute graphs from CIF on the fly, this is a major reproducibility and speed win.
2. **Composition-based descriptors** via matminer/Magpie featurizers, computed for every record regardless of whether structural data exists — this makes the dataset usable by groups running composition-only baseline models, not just GNN users, widening the addressable downstream audience.
3. **Symmetry-based descriptors:** space-group-derived features, Li-sublattice connectivity metrics (e.g., bond-valence-based Li migration pathway analysis via tools like BVSE or GULP) — these correlate meaningfully with ionic conductivity and are valuable both as ML features and as interpretability aids.
4. **Family 8 (polymer/composite) parallel path:** since standard crystal-graph representation doesn't apply, build a separate featurization branch using composition-weighted descriptors plus processing metadata (Section 2.6) as the primary feature set for this family — document clearly that family 8 records are not graph-compatible with the standard PIGNet V2 input pipeline without this adaptation.
5. **Split construction:** generate train/val/test splits grouped by composition-family key (`split_group_key`) — critically, ensure polymorphs and doped variants of the same base composition land in the same split, never spread across train and test, or reported model performance will be optimistically biased from leakage.
6. **Gold benchmark subset construction:** select the highest-confidence-tier records (verified_human or dft_native + measured conductivity) across all 8 families, balanced where possible, sized for a clean leaderboard-style comparison set (target: 200–500 compounds is a reasonable size for a first gold set — enough for statistical meaningfulness, small enough to keep fully human-auditable).

**Deliverables:** precomputed graph cache, composition/symmetry descriptor tables, finalized train/val/test/gold splits, ML-ready release candidate (v0.9).

**Exit criteria:** graph objects load and run through a PIGNet V2 forward pass without errors on a test batch; split leakage check passes (no composition-family key appears in more than one split); gold benchmark subset meets target size and family-balance goals.

---

## Phase 7 — Validation, QC & Statistical Auditing (Week 20–24)

**Sub-steps:**
1. **Distributional sanity checks per family:** plot/inspect formation energy, band gap, and conductivity distributions per family; compare against known literature ranges (Section 1) as a smell test — flag any family whose distribution looks implausible (e.g., a cluster of "sulfide" records with band gaps typical of metals) for re-classification review.
2. **Benchmark-compound validation:** run the full pipeline's output for the compounds in Section 17 (the "unit test" list) and manually verify every field against known literature values — this is the single most important QC gate, since these are the compounds every downstream user will sanity-check first.
3. **Cross-source consistency check:** for compounds present in multiple raw sources (Phase 4's dedup candidates), verify canonicalization chose sensibly (e.g., check a sample of 20-30 by hand).
4. **External academic review:** where possible, get 1–2 electrochemistry-focused academics to review a sample release candidate — this both catches errors an internal team might miss and seeds early credibility in the target GTM segment (university electrochemistry labs). [[prakash-n-b]] or others in the VIT Bhopal network may be a useful starting point for this review given existing familiarity with the user's research.
5. **Extraction-pipeline accuracy re-audit:** re-run the Phase 3.4 spot-check process on the final dataset state (not just mid-pipeline) since cleaning/dedup steps in Phase 4 could have introduced new errors.

**Deliverables:** validation report (per-family distributional summary, benchmark-compound comparison table, cross-source consistency audit, external review notes), v1.0 release candidate.

**Exit criteria:** all Section 17 benchmark compounds pass manual verification; no critical/blocking issues from external review; extraction accuracy re-audit still ≥85%.

---

## Phase 8 — Documentation, Datasheet & Governance Artifacts (Week 22–25, parallel)

**Sub-steps:**
1. Write a full **Datasheet for Datasets** (Gebru et al. format — the accepted academic standard for dataset documentation): motivation, composition, collection process, preprocessing/cleaning, known limitations and biases (e.g., sulfides and garnets likely overrepresented relative to antiperovskites simply because they're more studied — state this explicitly rather than letting users discover it themselves), recommended uses and explicit misuse warnings (e.g., "do not treat AIMD-computed conductivities as equivalent to measured values without checking `conductivity_source_type`").
2. Per-family README covering schema quirks — especially flagging family 8's parallel non-graph schema branch and family 6's temperature-curve requirement.
3. Confidence-tier documentation as a standalone, prominent doc — this is the trust mechanism for the whole dataset; make it impossible for a user to miss.
4. `CITATION.cff` file and a versioned `CHANGELOG.md` from the very first release, not retrofitted later.
5. Contribution guidelines for Phase 10's community-submission loop (issue template for submitting new measured values with required provenance fields).

**Deliverables:** full documentation set (datasheet, per-family READMEs, confidence-tier doc, CITATION.cff, CHANGELOG.md, CONTRIBUTING.md).

**Exit criteria:** documentation set reviewed by at least one person outside the immediate build team for clarity (a documentation-only "does this make sense to a stranger" pass).

---

## Phase 9 — Release, Distribution & GTM (Week 24+)

**Sub-steps:**
1. Publish v1.0 on **Hugging Face Datasets** (primary discovery channel for the ML practitioner audience) with a clear dataset card summarizing Section 0–2 content.
2. Publish simultaneously to **Zenodo** for a DOI — required for the academic citability that matters to the university electrochemistry lab GTM segment.
3. Push pipeline code to a public GitHub repo with the documentation set from Phase 8 and clear "how to reproduce/extend this dataset" instructions.
4. Direct outreach to the target GTM segment (university electrochemistry labs) — pair the release announcement with the gold benchmark subset as a concrete, low-friction hook ("here's a clean 300-compound benchmark you can drop into your next paper's comparison table").
5. Consider a short companion write-up (LinkedIn post per [[linkedin-content]] patterns, or a ChemRxiv/arXiv data-descriptor paper) — a proper data-descriptor paper is a stronger academic credibility asset than the existing PIGNet V2 preprint, given the noted concerns about that preprint's quality.

**Deliverables:** public v1.0 release on Hugging Face + Zenodo, public pipeline repo, outreach materials, optional data-descriptor writeup.

**Exit criteria:** dataset is publicly accessible and downloadable end-to-end by someone outside the team with no special access; DOI is live and resolves correctly.

---

## Phase 10 — Maintenance, Versioning & Community Loop (Ongoing)

**Sub-steps:**
1. Quarterly re-ingestion pass: pull new entries from Materials Project/JARVIS/OQMD/AFLOW (all actively updated sources) via the same Phase 2 pipeline — this should be a re-run, not a rebuild, if pipeline engineering in Phase 2 was done properly.
2. Rolling literature-mining passes as new papers publish, focused especially on halides (fastest-growing family) each quarter.
3. Versioned releases (v1.1, v1.2, ...) with a changelog entry per release — never silently mutate a published version, since academic citations will reference specific version numbers.
4. Community contribution path: structured PR/issue template for labs submitting their own measured conductivity values with required provenance fields (ties back to Phase 8's CONTRIBUTING.md) — this is how the dataset compounds in value over time rather than going stale.
5. Periodic re-validation of the gold benchmark subset as new, higher-confidence data arrives (a compound might move from literature_mined to verified_human confidence tier if independently re-measured and confirmed).

**Deliverables:** maintenance runbook, quarterly release cadence established, live community contribution channel.

---

## 14. Team, Roles & Time Allocation

| Role | Responsibility | Approx. time commitment |
|---|---|---|
| Pipeline/data engineer (likely you) | Phases 2, 4, 6, 10 — ingestion, cleaning, feature engineering, orchestration | Primary, ongoing |
| DFT/computational chemistry support | Phase 5 — compute workflow setup, job triage, functional/convergence decisions | Part-time, weeks 12–20 concentrated |
| Literature-mining/NLP support | Phase 3 — extraction pipeline build and QC | Part-time to significant, weeks 6–12 concentrated |
| Domain reviewer (academic collaborator) | Phase 7 external review, Phase 3 spot-check sampling | Light touch, a few focused sessions |
| Documentation owner | Phase 8 | Short, concentrated burst |

Given Scandium Labs' current team size, expect most roles to be worn by one or two people with the domain-reviewer role filled by an external academic contact — this is a reasonable place to lean on the existing VIT Bhopal academic network.

---

## 15. Compute & Cost Budget

- **Free/low-cost tier (default, prioritize this):** Materials Project, JARVIS, OQMD, AFLOW, NOMAD APIs are free. Semantic Scholar API free tier is sufficient for Phase 3 discovery volume. Kaggle notebooks (free GPU quota) suffice for Phase 6 graph construction and featurization at this dataset scale.
- **University/institutional compute:** Route Phase 5 DFT jobs through VIT Bhopal HPC allocation if available — this is the highest-cost phase if paid cloud compute is used instead, since VASP relaxation + AIMD runs are genuinely expensive at scale.
- **Paid cloud compute (only if free/institutional is insufficient):** Budget conservatively and only for the Section 5 priority queue item (a) — literature-matched-but-unstructured compositions — since that's the highest-value-per-compute-dollar target.
- **LLM API costs (Phase 3 extraction):** Budget for the paper-triage pass (cheap, high volume) and the extraction pass (more expensive, lower volume after triage filtering) — using a cheaper/faster model for triage and a stronger model for the actual structured extraction is a reasonable cost-control split.

---

## 16. Risk Register & Mitigations

| Risk | Impact | Mitigation |
|---|---|---|
| ICSD access unavailable | Lose the only "confirmed synthesized" structural source | Fall back to synthesis-accessibility flags from literature mining (Section 2.6) as a partial substitute |
| Literature-mining extraction accuracy too low | Whole dataset's core value prop (conductivity labels) is untrustworthy | Hard QC gate at 85% accuracy (Phase 3.4) before scaling; do not skip the seed-validation step |
| DFT compute budget insufficient to fill priority gaps | v1.0 ships with more gaps than planned | Prioritization queue (Phase 5.2) ensures highest-value gaps are filled first even under budget constraints; document remaining gaps transparently rather than hiding them |
| Family imbalance (e.g., antiperovskites structurally too sparse) | Dataset looks unbalanced/incomplete | Document imbalance explicitly in the datasheet (Phase 8) rather than treating it as a failure — it's a real, citable finding about the state of the field |
| Publisher/copyright issues with literature mining | Legal/distribution risk | Only extract structured data (numbers, not verbatim text) from papers accessed through legitimate means; never redistribute full paper text, only the extracted structured facts with DOI citation |
| Schema turns out to need retrofitting after Phase 2 is underway | Expensive rework | Phase 0's hand-testing against 5–10 compounds per family before locking schema is the mitigation — do not skip this step even under time pressure |
| Data leakage between train/test via unrecognized polymorphs | Inflated, non-reproducible model benchmark results | Composition-family-key grouped splits (Phase 6.5) with an explicit leakage-check test |

---

## 17. Benchmark Compound List — "Unit Tests" for the Dataset

Use these to sanity-check every pipeline stage, from ingestion through final release. If any of these look wrong at any stage, something upstream broke.

- Li10GeP2S12 (LGPS) — sulfide
- Li6PS5Cl (argyrodite) — sulfide
- Li7La3Zr2O12, cubic phase (LLZO) — garnet
- Li3xLa(2/3-x)TiO3 (LLTO) — perovskite
- Li1.3Al0.3Ti1.7(PO4)3 (LATP) — NASICON
- Li3InCl6 — halide
- LiBH4, high-T hexagonal phase — hydride/borohydride
- Li3OCl — antiperovskite
- PEO10:LiTFSI — polymer/composite

---

## 18. Competitive Landscape — Why This Wins

| Existing resource | What it has | What it's missing |
|---|---|---|
| Materials Project | Broad structural/thermodynamic DFT coverage | No SSB-specific curation, no transport-property labels, no literature-mined data |
| JARVIS-DFT | Strong defect/2D coverage | Same gap — general-purpose, not SSB-transport-focused |
| Individual review-paper appendix tables | High-quality, human-curated conductivity values | Small, static, not machine-readable, not linked to structural data, no versioning |
| Ad hoc lab-internal spreadsheets (common in the field) | Whatever a given lab happens to need | Not shared, not standardized, not citable, dies when the grad student graduates |

Scandium Labs' dataset differentiates by being the only resource that (a) unifies all 8 families under one schema, (b) treats conductivity as a first-class provenance-tagged label rather than an afterthought, (c) ships pre-built as GNN-ready graphs, and (d) is versioned, documented, and citable as an ongoing academic-grade artifact rather than a one-time dump.

---

## 19. Success Metrics & KPIs

- **Coverage:** row counts per family meeting or exceeding Phase 0 targets (revised post Phase 1 survey).
- **Label density:** % of records with `label_available: true` for conductivity, tracked per family.
- **Confidence-tier distribution:** healthy mix, not dominated by low-confidence extractions — track and report this transparently.
- **Adoption:** downloads on Hugging Face, citations of the Zenodo DOI, and direct adoption signals from the target university-lab GTM segment.
- **Benchmark utility:** whether the gold benchmark subset gets used in a published paper's model comparison table — this is the clearest external validation signal of GTM success.
- **Pipeline reproducibility:** whether v1.1 can be produced as a clean re-run of the Phase 2/3/5 pipeline without manual patching — this validates that Phase 10's maintenance loop actually works.

---

## 20. Appendix — Reference Tools, APIs & Reading List

**Structure/materials tooling:** pymatgen, ASE, matminer, Magpie featurizer set, BVSE/GULP for bond-valence pathway analysis.

**DFT sources:** Materials Project (`mp-api`), JARVIS-tools, OQMD REST/bulk dump, AFLOW REST API, NOMAD archive API, ICSD (institutional).

**DFT compute:** VASP (preferred for MP-schema compatibility) or Quantum Espresso; Custodian for automated job management/error handling.

**Literature mining:** Semantic Scholar API, Crossref API, GROBID for PDF structure extraction, an LLM for structured table/text extraction.

**ML/graph tooling:** PyTorch Geometric (or equivalent) for graph objects matching PIGNet V2's input spec, matminer for composition descriptors.

**Hosting/versioning:** Hugging Face Datasets, Zenodo (DOI), GitHub, DVC (optional, for large-artifact versioning).

**Documentation standard:** "Datasheets for Datasets" (Gebru et al.) as the format reference for Phase 8.

**Domain reading (for schema/QC calibration, not for direct data extraction):** recent SSE review articles covering each of the 8 families are the best source of the "known conductivity ranges" used throughout Section 1 and the sanity checks in Phase 7 — pull 1–2 recent (2022+) comprehensive reviews per family as calibration references during Phase 0 and Phase 7.
