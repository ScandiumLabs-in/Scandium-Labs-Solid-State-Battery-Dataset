# Scandium Labs SSB Dataset — Expansion & Data-Quality Guide

**Companion to `scandium-ssb-dataset-guide.md` and `AGENTS.md`.** That guide covers Phases 0–9 (build the pipeline). This guide covers what happens *after* the pipeline works and passes its own gates — closing the gaps the pipeline itself has already surfaced, using only free resources. Read this after Phase 9, not instead of it.

**Baseline this plan works from (as of the last release, v0.3.2):**

| Metric | Current | Target (v1.0) |
|---|---|---|
| Verified experimental labels | 116 | 500 |
| Gold-tier records | 0 | ≥15% of verified set |
| Materials with real consensus (n≥3 papers) | 20 | 60+ |
| Sulfide-family verified labels | 7–9 | 40+ (proportional to real-world SSB research volume) |
| Blocked/paywalled DOIs | 135 of 594 probed | <60 |
| Vision-capable extraction | None wired in | Wired in, unblocks scanned PDFs |
| README accuracy | Contradicts CHANGELOG.md | Auto-synced, never drifts |
| Metadata completeness (temp+method) | ~94–99% | maintain; extend to pressure/density/electrode/atmosphere on 80%+ |

Every phase below ends with a **Definition of Done** tied to a release-gate number in `release_config.toml`, so progress is never a vibe — it's a number that either moved or didn't.

---

## Guiding principles for this phase

1. **Free means free, not "free if you look the other way."** Every source below is either open-access by design, has a genuine no-cost API tier, or is access you *already legitimately have* (a university library subscription is not a paywall bypass — it's tuition you already paid). Nothing here routes around a paywall via scraping tools that violate a publisher's ToS.
2. **Every new record still goes through the existing gates.** This guide adds *sourcing and tooling*, not a shortcut around evidence-verification, red-flag detection, or human review. A record that skips `verify_extraction_evidence.py` doesn't count, no matter which phase produced it.
3. **Fix the lie before you fix the gap.** Phase 0 is documentation, not data. Ship it today — it costs an hour and it's the difference between the repo being credible on first look or not.
4. **Chase deficits, not volume.** 500 verified labels that are still 90% garnet/polymer isn't a better dataset than 300 that are family-balanced. Every literature phase below is deficit-weighted, not just "find more papers."

---

## Phase E0 — Fix the Documentation Debt (Day 0, ~1 hour)

**Why:** The README currently says "Pre-Phase-0, no data ingested" while the dataset is at v0.3.2 with 30,071 records and 10/10 release gates passing. This is the single highest-leverage fix available and it costs nothing.

**Tasks:**
- Replace the README `## Status` section with a live snapshot: version, verified-label count, gate status, last-release date.
- Write `scripts/sync_readme_status.py` that reads `release_report.json` and rewrites the README status block automatically. Wire it into `scripts/release.py` so a release can never again leave the README stale — this is a one-time fix that prevents the drift from ever recurring, not a one-time patch.
- Add a one-paragraph honest caveat directly under the status block: *"116 of 30,071 records carry human-verified conductivity/Ea labels; the remainder are structural/thermodynamic DFT records without transport labels. Quality tier distribution: 0% Gold, 96.5% Silver, 3.5% Rejected — see `quality_output/quality_report.json`."* Burying this helps no one; stating it up front is what makes the rest of the dataset's claims credible.

**Definition of Done:** README status section is generated, not hand-written, and matches `release_report.json` byte-for-byte on every CI run.

---

## Phase E1 — Widen the Free Discovery Funnel

**Why:** `AGENTS.md` shows discovery currently runs on Semantic Scholar + Crossref only, and 135 of 594 probed DOIs are blocked. Several free APIs index open-access full text that Semantic Scholar's metadata-only search misses, and some of the "blocked" DOIs likely have an OA copy these tools know about that your current harvester doesn't check.

**Free resources to add:**

| Source | What it gives you | Free tier |
|---|---|---|
| **Unpaywall API** | Given a DOI, returns the best legal OA location (repository, publisher OA, preprint) | Fully free, no key needed beyond an email param, no rate limit stated (be a good citizen — a few req/sec) |
| **OpenAlex API** | Richer discovery than Semantic Scholar for materials-science venues, includes `open_access.oa_url` per work | Fully free, 100k req/day with polite pool (email in User-Agent) |
| **CORE API** | Aggregates 250M+ OA full texts from repositories worldwide, has direct PDF download links | Free tier with API key, 10k req/day |
| **BASE (Bielefeld Academic Search Engine)** | One of the largest OA indexes, strong on institutional repositories that Semantic Scholar doesn't crawl | Free, no key for basic search |
| **DOAJ API** | Journal-level OA verification — confirms a venue is genuinely OA before you spend a harvest attempt on it | Fully free |
| **arXiv API** | Physics/cond-mat preprints — many DFT/computational SSB papers post here before or alongside journal publication | Fully free, full text |
| **ChemRxiv API** | Chemistry preprints — same logic as arXiv, chemistry-specific | Fully free |
| **Europe PMC** | Already in use for EPMC mirror harvesting — extend to their full-text search API, not just the render route | Fully free |

**Tasks:**
1. Build `scripts/harvest_unpaywall.py` — re-run **all 135 currently-blocked DOIs** through Unpaywall first. This is the cheapest possible win: it's a single API call per DOI and it's likely to immediately recover a meaningful slice without touching the "blocked" publisher routes at all.
2. Build `scripts/harvest_openalex.py` as a parallel discovery route to the existing Semantic Scholar discovery agent — merge results into `literature_output/discovery_candidates.json` with source tagging so you can compare yield per source later.
3. Add CORE and BASE as fallback download routes in `harvest_multi_route.py`'s existing route chain (Unpaywall → OpenAlex → direct publisher → EPMC render → CORE → BASE → Semantic Scholar).
4. Gate every new candidate through DOAJ before attempting a harvest, to avoid burning attempts on venues that only look OA.

**Definition of Done:** Blocked-DOI count drops from 135 to a documented, re-verified smaller number; every DOI still blocked after this phase gets a one-line reason logged (not just silently skipped).

---

## Phase E2 — Use Access You Already Have

**Why:** You're a student at VIT Bhopal. University libraries carry subscriptions to ACS, Elsevier, Wiley, RSC, and Springer that cover a meaningful fraction of the currently-blocked DOIs. Downloading a paper you have legitimate institutional access to and using it for extraction (with the same evidence-chain and citation discipline the pipeline already enforces) is not a paywall bypass — it's the access you're already paying for through tuition.

**Tasks:**
1. Cross-reference the 135 blocked DOIs against VIT Bhopal's library subscription list (check via the library portal or ask the library desk which publishers are covered).
2. For matches, download via the campus network or library EZproxy/VPN, drop the PDFs into `literature_output/pdfs/` exactly like any other harvested PDF, and let them flow through the existing extraction → evidence-verification → review pipeline unchanged. No special-casing needed — provenance is still `source_id` = DOI either way.
3. Reach out to **[[prakash-n-b]]** (or another VIT Bhopal electrochemistry-adjacent faculty contact) — a faculty member's institutional access sometimes covers journals a student portal doesn't, and this is the same network the original guide already earmarks for Phase 7 external review. Ask early, not just at release time.
4. Document which DOIs were sourced this way in the provenance chain (`source_journal`, existing fields) so the dataset's documentation is transparent about how access was obtained — this matters for anyone downstream deciding whether they can redistribute or must re-license.

**Definition of Done:** A tracked subset of the 135 blocked DOIs re-attempted via institutional access, with a clear log of which succeeded and which are genuinely unreachable from any legitimate route.

---

## Phase E3 — Fix and Extend the Structural-Data Connectors

**Why:** `AGENTS.md` notes AFLOW and OQMD "skip gracefully (missing/outdated client packages)" — that's dropped coverage on two free, legitimate structural databases for no good reason. There are also free structural sources not in the pipeline at all yet.

**Tasks:**
1. **Fix AFLOW/OQMD connectors.** Both have REST APIs that don't require the outdated client packages currently blocking them — AFLOW's `AFLUX` REST search and OQMD's REST API can both be queried directly with `requests`, bypassing the stale client dependency entirely. This is a connector rewrite, not a new integration.
2. **Add the Crystallography Open Database (COD).** Fully open, no key required, and — unlike Materials Project/JARVIS which are DFT-relaxed — COD contains real experimentally-determined structures, which is exactly the "this actually exists" signal the original guide flagged ICSD (paywalled) as providing. COD is the free substitute for the ICSD access you don't have.
3. **Add Materials Cloud.** Free, hosts several curated solid-electrolyte-adjacent datasets (e.g., ionic-conductor screening archives) directly relevant to the 8 SSB families, not just generic Li-containing compounds like MP/JARVIS.

**Definition of Done:** AFLOW and OQMD connectors produce non-zero staged records again; COD integrated as a new source with its own `source_db` tag; `min_total_records` gate headroom increases without touching MP/JARVIS.

---

## Phase E4 — Close the Sulfide Gap Specifically

**Why:** Sulfides (LGPS, argyrodites, thio-LISICON) are the highest-conductivity, most industrially referenced SSB family, and they're your worst-covered family in verified labels (7–9 records vs. 24–26 for polymer composites). This isn't a "mine more papers" problem — it's a targeting problem.

**Tasks:**
1. Build a **family-deficit-weighted discovery queue**: instead of running the same search terms across all 8–11 families equally, compute each family's (verified labels) ÷ (target share from the v2.0 benchmark distribution already defined in `benchmark_materials.py`) and rank discovery queries by which family is furthest below target. The changelog already describes doing this ad hoc for the last few pushes ("family-deficit-targeted") — formalize it into `scripts/prioritize_discovery.py` so it's repeatable, not manual triage each time.
2. Run targeted discovery specifically for: Li10GeP2S12-type sulfides, Li6PS5X argyrodites (X = Cl/Br/I), thio-LISICON (Li4-xGe1-xPxS4 series), Li7P3S11 glass-ceramics — these are the well-studied sulfide sub-families most likely to have multiple independent papers reporting the same or closely related compositions (which also feeds Phase E7's consensus goal).
3. Cross-check sulfide coverage against COD (Phase E3) for structures even where conductivity data isn't available — partial coverage (structure without label) is still worth having and flags candidates for future DFT gap-filling (Phase 5 of the original guide).

**Definition of Done:** Sulfide + argyrodite verified-label count moves from 7–9 toward the v2.0 target share (~17.7% of the labeled set); family-distribution flags in the validation report stay at 0.

---

## Phase E5 — Vision-Capable Extraction (Unlock Scanned PDFs, Fully Free)

**Why:** `AGENTS.md` explicitly names this as "Current gap: vision (Phase 5)" — text-layer search returns `None` for scanned pages, and 2+ known papers (halide_sciadv, antiperovskite_pmc) are stuck in `needs_review` purely because no vision model is wired in, not because the data is bad.

**Free options, in order of effort:**

1. **Groq vision models (same provider you already use for text extraction).** Groq has offered vision-capable Llama models on its free tier (check current model list — this changes; the point is the plumbing is already there since `verifier.py` and `extraction.py` already call the Groq API, so wiring in a vision model is a model-name swap plus an image-input code path, not a new integration).
2. **Local models via Ollama — fully free, no rate limits, deterministic.** This is worth prioritizing over another hosted API: running a vision-capable open-weight model (e.g., a Qwen-VL or Llama-vision variant) locally via Ollama costs nothing per call, has no rate limit to fight (the non-determinism section in `AGENTS.md` was partly a rate-limit artifact), and lets you pin a fixed seed for genuinely reproducible extraction — solving two gaps (vision + determinism) with one piece of infrastructure. Requires reasonable local/free-tier compute (a Kaggle/Colab free-tier GPU session is enough for inference, not training).
3. **Nougat (Meta, MIT-licensed, free).** Purpose-built for reconstructing structured text — including tables and equations — from scientific PDF page images. This is a better fit than generic OCR (`pytesseract`) for a table like "conductivity vs. temperature" because it's trained specifically on academic paper layouts. Use it as a pre-processing step that feeds cleaner input into the existing extraction prompt, rather than replacing the LLM extraction step entirely.

**Tasks:**
1. Add a `vision_locate_evidence()` path in `verifier.py` that activates specifically when text-layer search returns `None` (the current SCRIBED signal) — this is additive, it doesn't touch the working text-layer path.
2. Route the known SCRIBED papers through it first as a controlled test before opening it up to future scanned sources.
3. Feed Nougat's structured table output into the *existing* extraction prompt rather than building a parallel prompt — reuse the schema, reuse the review pipeline, reuse `verify_extraction_evidence.py`. The goal is one more input format into the pipeline you already trust, not a second pipeline.

**Definition of Done:** The 2 known SCRIBED records move out of permanent `needs_review` limbo (approved or cleanly rejected with evidence either way); vision path covered by tests the same way the text path is (`tests/test_review_engine.py` pattern).

---

## Phase E6 — Determinism & Extraction Model Upgrade

**Why:** `AGENTS.md`'s infrastructure findings section documents that Groq's `llama-3.1-8b-instant` is non-deterministic even at `temperature=0.0`, and the current fix (ensemble-of-3, majority vote) is a workaround, not a root-cause fix. It also costs 3x the API calls for the same paper.

**Free options:**
1. **Move primary extraction to `llama-3.3-70b-versatile`** (already used for verification, per the AI Verification Pipeline section, but not for primary extraction) — larger models are typically more stable under low-temperature sampling and the accuracy ceiling matters more here than the small model's speed advantage, since extraction accuracy is the dataset's core bottleneck.
2. **Local deterministic extraction via Ollama** for the highest-value papers (the ones already flagged for hand-verification anyway) — a locally-hosted model gives you a genuinely fixed seed and zero network-jitter variance, which is the actual root cause the changelog identifies ("rate-limit-driven retries routing to different LLM configs").
3. **Google Gemini free tier** as a third, independent extraction pass for cross-checking — Gemini's free tier (currently ~1500 requests/day on Flash-class models) is generous enough to run as a second-opinion pass on records the primary ensemble disagrees on, strengthening exactly the "models disagree" bucket that currently routes to `needs_review`.

**Tasks:**
1. Benchmark `llama-3.3-70b-versatile` against the existing 53-item ground-truth set (reuse `scripts/calibrate_review_engine.py`'s pattern) before switching the default — don't swap the extraction model on faith, swap it on a measured accuracy delta.
2. Keep the ensemble-of-3 approach but drop it to ensemble-of-2 with a larger, more stable model if benchmarking shows the variance problem is substantially reduced — this cuts API cost without cutting reliability.
3. Document the final model choice and its calibration numbers in `AGENTS.md`'s existing "Infrastructure findings" section, continuing the pattern already established there.

**Definition of Done:** Re-run of the 5-run determinism test (same procedure already documented in `AGENTS.md`) on the new model/setup shows record-count and value-assignment stability across runs; ensemble size can be reduced without accuracy regression on the calibration set.

---

## Phase E7 — Metadata Backfill to Unlock Gold Tier

**Why:** Every single verified record is currently capped at Silver tier because `record_quality.py`'s scoring explicitly requires *metadata completeness (temperature + method) + consensus (2+ papers)* for Gold, and — per the changelog's own honest note — experimental metadata (pressure, density, electrode, atmosphere) is populated on 0% of the original 41-record baseline and only partially since. The quality ceiling isn't a labeling problem, it's a metadata-extraction coverage problem.

**Tasks:**
1. Extend `experiment_extract.py`'s deterministic (no-LLM) backfill beyond its current field set — target **humidity**, **instrument**, and a cleaner re-attempt at **equivalent_circuit** (currently disabled because text-layer capture produced "prose garbage"). This last one is a good candidate for the vision pipeline from Phase E5: equivalent-circuit parameters usually live in a table or figure caption, which vision extraction can read far more reliably than a regex over reflowed PDF text.
2. Re-run the backfill against the growing PDF-on-disk set as Phases E1–E4 add more papers — the backfill script already scans "each verified record's source PDF," so it should be re-run after every harvest batch, not just once.
3. Use `build_health_report.py`'s existing "missing-data recommendations" section (per-field, which records lack it) as the literal to-do list — it's already generated, just needs to be acted on systematically rather than read once.

**Definition of Done:** `metadata_completeness` in the health report crosses 80% across the full experiment-block field set (not just temperature/method); Gold-tier record count moves off zero in the next `quality_report.json`.

---

## Phase E8 — Grow Cross-Paper Consensus (the Flywheel)

**Why:** Only 20 of 387 consensus-DB materials have real n≥3 consensus, and only 22 have even 2 papers. Consensus is what turns "the pipeline verified this number" into "independent labs measured the same number" — it's the strongest quality signal the dataset can offer, and it's currently the least-used lever.

**Tasks:**
1. Build `scripts/prioritize_consensus_growth.py`: for every material currently at n=1, search *specifically* for that composition (not a generic family search) across the Phase E1 discovery sources — you already know the exact formula, so this is a much higher-precision search than generic family-level literature mining.
2. Prioritize materials that are already well-known benchmarks (LGPS, LLZO, Li6PS5Cl, LATP) even past n=3, since deep consensus on the "unit tests" of the dataset (per the original guide's Phase 7 language) has outsized credibility value for external adopters.
3. Feed every new consensus-improving record through the existing `consensus_db` review rule unchanged — this phase is about sourcing, the scoring machinery already exists and works.

**Definition of Done:** Materials with n≥3 consensus grows from 20 toward 60+; agreement-grade distribution shifts visibly toward A/A+ in `material_cards.json`.

---

## Phase E9 — Free Community & Crowdsourcing Channels

**Why:** `CONTRIBUTING.md` already exists but there's no evidence it's being used — the community-contribution path the original guide's Phase 9 anticipates is currently theoretical. Free channels can generate real submissions at zero cost.

**Tasks:**
1. Post the **gold benchmark subset** (once Phase E7 produces one) to relevant free, no-cost channels: Hugging Face's dataset community discussion tab (free, and puts it directly in front of the ML audience the guide is targeting), r/MaterialsScience and r/batteries on Reddit, GitHub Discussions on this repo (already free, currently unused).
2. Add a lightweight issue template under the existing `.github/` folder specifically for "submit one verified conductivity value" — lower the bar from "understand the whole schema" to "fill in five fields," since that's the realistic unit of external contribution.
3. Reach out through the VIT Bhopal academic network — not just for the Phase 7 external-review sanity-check the original guide already plans, but as active graduate-student contributors: a grad student measuring one composition's conductivity as part of their own thesis work costs Scandium Labs nothing and gives them a citable dataset entry in return.

**Definition of Done:** At least one external contribution (even a single verified record) processed through the existing review pipeline via the community path, proving the channel works end-to-end before scaling outreach further.

---

## Phase E10 — Re-Validate, Re-Baseline, Ship v1.0

**Why:** Every phase above should be checkpointed against the existing release gates, not treated as done until the numbers move.

**Tasks:**
1. After each phase (not just at the end), run `scripts/release.py --build` and diff the new `release_report.json` against the previous one — the drift-detection already built into `build_health_report.py` (Phase 0 C2 feature) does this automatically; use it.
2. Re-run `scripts/calibrate_review_engine.py` after any model or ensemble change (Phase E6) to confirm the review engine's precision/recall on the ground-truth set hasn't regressed.
3. Once verified labels cross ~250 (a realistic first checkpoint, not the full 500), publish an intermediate versioned release to Hugging Face (free hosting, no minimum size requirement) rather than waiting for the full v1.0 target — earlier external feedback is worth more than a longer silent build cycle, and datasets can be updated in place.
4. Update the "Datasheet for Datasets" (original guide Phase 8) with the honest current-state numbers this plan targets: quality tier distribution, sulfide coverage relative to other families, and which structural sources (COD vs. MP vs. JARVIS) contributed which slice — this is the same honesty principle as Phase E0, applied to the final documentation artifact instead of the README.

**Definition of Done:** A published, versioned intermediate release on Hugging Face with a datasheet that accurately describes its own limitations — the same "release-ready" gate the pipeline already enforces internally, now applied to the public-facing artifact.

---

## Suggested sequencing

Not everything needs to happen in strict order, but dependencies matter:

```
E0 (docs)  ──────────────────────────────────────────────► do first, always
E1 (discovery) ──┬──► E4 (sulfide targeting) ──► E8 (consensus)
E2 (institutional)┘
E3 (connectors) ─────────────────────────────────────────► parallel, independent
E5 (vision) ──► E7 (metadata backfill, esp. equivalent_circuit)
E6 (determinism) ─────────────────────────────────────────► parallel, independent
E9 (community) ──────────────────────────────────────────► after E7 produces a gold subset
E10 (release checkpoints) ────────────────────────────────► after every phase, not just once
```

## What to deliberately not do in this phase

- Don't scrape paywalled publisher sites with tools designed to defeat access controls — Unpaywall/CORE/BASE/institutional access covers the legitimate ground; anything beyond that isn't a "free resource," it's a liability.
- Don't relax any existing release gate (evidence coverage, duplicate rate, etc.) to hit a bigger verified-label number faster — the whole value of this dataset relative to a generic scrape is that the gates are real. A larger dataset with a lowered bar is a worse dataset, not a better one.
- Don't build a second extraction pipeline in Phase E5/E6 — extend the existing `verifier.py`/`extraction.py` entry points. Every new input source should terminate in the same review queue, not a parallel one.

---

# Two-Layer Architecture + 13 Data Layers

**Companion schema expansion (2026-08-05).** This plan separates the dataset into
two layers so each record carries both a real-world performance profile and a
computational fingerprint:

1. **Experimental Layer** (from papers) → conductivity, activation energy, synthesis,
   EIS, experimental conditions — already the core of Phases E0–E10 above.
2. **Computational Layer** (from the Materials Project API) → crystal, thermodynamic,
   electronic, mechanical, structural descriptors — this section.

That combination (experiment + DFT + crystal structure for the same material) is
the dataset's differentiator. The schema (`src/ssb_dataset/schema.py`) implements
the fields below as pydantic blocks; the enrichment pipeline
(`scripts/enrich_mp_api.py` + `scripts/expand_mp.py`) populates them from the free
MP REST API (`mpr.materials.{summary,elasticity,dielectric,robocrys,chemenv,bonds,
oxidation_states}`). Coverage status per layer is tracked against the 21,528
Li-containing MP materials in the canonical dataset.

## Layer 1 — Material Identity (Highest Priority) — DONE

| Property | Schema field | Status |
|---|---|---|
| material_id (mp-xxxx) | `identity.material_id` | ✅ 21,528 |
| pretty_formula | `identity.formula_pretty` | ✅ |
| formula_anonymous | `identity.formula_anonymous` | ✅ |
| chemical_system | `identity.chemsys` | ✅ |
| elements | `identity.elements` | ✅ |
| n_elements | `identity.nelements` | ✅ |
| n_sites | `structure.nsites` | ✅ |
| reduced_formula | `identity.reduced_formula` | ✅ |
| database IDs (ICSD etc.) | `identity.database_ids` | ✅ |

## Layer 2 — Crystal Structure — DONE

`structure.structure_relaxed` (CIF), `space_group`, `space_group_number`,
`crystal_system`, `point_group`, `symmetry_operations_count` (computed from the
space-group type), `lattice_params`, `volume`, `density`, `nsites`.

## Layer 3 — Thermodynamic Properties — DONE

`thermodynamics.formation_energy_per_atom`, `energy_above_hull`, `is_stable`,
`equilibrium_reaction_energy_per_atom` (decomposition energy), `total_energy`,
`energy_per_atom`, `decomposition_products`, `functional_used` (provenance:
PBE for the full catalog), `electrochemical_stability_window`.

## Layer 4 — Electronic Properties — DONE (compact descriptors)

`thermodynamics.band_gap`, `efermi`, `cbm`, `vbm`, `is_gap_direct`, `is_metal`.
Full DOS curves are served by MP only via a per-task heavy endpoint; the compact
band descriptors above carry the ML-relevant signal, so full DOS is deliberately
not stored per-record (a band-center descriptor is a Phase 3 option if a consumer
needs it).

## Layer 5 — Mechanical Properties — DONE

`mechanical.bulk_modulus`, `shear_modulus`, `youngs_modulus`, `homogeneous_poisson`,
`universal_anisotropy`, `elastic_tensor`, `compliance_tensor` (+ free extras:
`debye_temperature`, `sound_velocity`, `thermal_conductivity`). Coverage 886/21,528
elasticity tensor (MP sparse — honest None elsewhere).

## Layer 6 — Dielectric Properties — DONE

`dielectric.e_total`, `e_electronic`, `e_ionic`, `dielectric_tensor`, `refractive_index_n`.
Coverage 1,102/21,528.

## Layer 7 — Chemistry — DONE

`electronic.possible_species`, `electronic.oxidation_states`,
`electronic.average_oxidation_states` (19,332/21,528). Electronegativity statistics,
valence-electron count, atomic fractions and elemental fractions are computed
deterministically from the composition at feature time (full coverage, no API).
**v0.6.0:** `redox` block adds oxidation chemistry from possible_species —
`redox_active_elements`, `average_oxidation`, `oxidation_range`, `mixed_valence`
(per-element: same element in ≥2 oxidation states), `anion_type`/`cation_type`
(electronegativity-split), `electroneutral` (None when uncomputable — never a
dishonest default).

## Layer 8 — Structural Descriptors — PARTIAL → DONE

`structure.coordination_environment` + `coordination_csm` + `coordination_species`
(chemenv, 160/21,528), `mineral_prototype` (robocrys, 765), `robocrys_description`,
`packing_fraction` (schema field, MP does not serve it), `density_atomic`. Bond
lengths, bond angles, coordination number and dimensionality were the remaining
gaps; closed via the MP `bonds` endpoint (`bond_length_stats`, `coordination_envs`)
and robocrys `condensed_structure.dimensionality`.
**v0.6.0:** `graph` block (CrystalNN structure graph → num_nodes/edges,
average_degree, graph_density, edge_length_mean/std via `ConnectedSite.dist`,
clustering_coefficient, graph_diameter, connected) + `structure` local-geometry
fields (polyhedron_volume via ConvexHull, polyhedron_distortion,
bond_angle_variance, tetra/octahedrality, mean_neighbor_distance,
neighbor_species_distribution) — computed offline by
`scripts/compute_structure_descriptors.py` (full coverage when the CIF parses).

## Layer 9 — Diffusion-Related Features — WHEN AVAILABLE

`ion_transport.activation_energy_Ea` (experimental). Li/Na diffusion coefficient and
migration barriers are stored only when a source provides them (DFT Phase 5 or
literature); MP exposes no per-material diffusion endpoint in the current client.
**v0.6.0:** `synthesis` block brings real MP recipe data (precursors, temperature,
time, atmosphere, method flags, reaction string, DOI) for compounds with
published synthesis recipes; `discovery_labels` block adds heuristic
fast-ion-conductor / promising-SSB labels from DFT stability, band gap, family,
and (when literature σ/Ea merge in) measured transport.

## Layer 10 — Battery-Relevant Properties — PARTIAL

`thermodynamics.electrochemical_stability_window`, `weighted_surface_energy`,
`surface_anisotropy`. Oxidation/reduction limits and interface stability are not
served by the free MP summary endpoint; schema fields exist where the data can
be obtained (stability window).

## Layer 11 — Experimental Layer — DONE

The full `experiment` block: ionic conductivity, temperature, activation energy,
sample form, pellet diameter/thickness/pressure, relative density, sinter/anneal
temperature+time, electrode material/deposition, atmosphere, instrument, frequency
range, DOI, journal, year.

## Layer 12 — SSB Family Classification — DONE

`identity.family` (11 families: sulfide, oxide, garnet, perovskite, nasicon,
halide, argyrodite, hydride, borohydride, antiperovskite, polymer_composite) +
`identity.subfamily_tag`. Deterministic composition rules classify the full MP
catalog; literature records carry the family the classifier derives from the formula.

## Layer 13 — Quality Metadata / Provenance — DONE

`identity.confidence_tier` (verified_human / high_confidence_extraction /
low_confidence_extraction / dft_native / dft_computed_inhouse) + the full
`text_provenance` block (DOI → PDF → page → section → table/figure → sentence,
extraction method, confidence score, ensemble votes). Per-property
`{value, unit, source, confidence}` wrappers are implemented as typed fields +
block-level provenance rather than nested dicts, so every value in the dataset
carries a traceable source.

## Priority Implementation Plan status (2026-08-05)

- **Phase 1 (Must Have)** — DONE: material ID, formula, structure, CIF, space
  group, crystal system, density, volume, formation energy, energy above hull,
  band gap, oxidation states.
- **Phase 2 (Strongly Recommended)** — DONE: elastic properties, dielectric
  properties, coordination environments, robocrys descriptions, provenance,
  thermodynamic functional.
- **Phase 3 (Advanced)** — PARTIAL: surface properties (weighted surface energy,
  anisotropy), similarity via existing descriptors. Phonons, grain boundaries and
  diffusion descriptors are NOT integrated — MP serves no phonon data for the
  electrolyte catalog (verified zero coverage) and diffusion is not served
  per-material by the current client; revisit only if a consumer needs them.
  **v0.6.0:** synthesis-endpoint data is now INTEGRATED (MP `synthesis` recipe
  search by target formula → `SynthesisBlock`), plus the `graph`/`local`
  structure descriptors and `redox`/`discovery_labels` blocks.

## Definition of Done for this section

Every Layer 1–8 property the free MP REST API serves for a Li-containing material
appears as a schema field and is populated in the canonical dataset (sparse =
MP lacks the calculation, honestly None). Verified by
`tests/test_mp_enrichment.py` + the release gates after each enrichment rerun.
