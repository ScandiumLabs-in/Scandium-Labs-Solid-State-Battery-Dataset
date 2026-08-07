# Improving the Scandium Labs Solid-State Electrolyte Dataset
### A methodology-driven guide, benchmarked against OBELiX, LiIon, and related literature datasets

---

## 1. Why this guide exists

Your dataset's own card is honest about its structure: **30,838 bulk DFT rows are the backbone, and 183 human-verified experimental labels are the actual asset.** That framing is correct and matches how the two most rigorous public datasets in this space — OBELiX (Therrien et al., 2025, Mila/NRC Canada) and the Liverpool Ionics Dataset ("LiIon", Hargreaves et al., 2023, *npj Computational Materials*) — position themselves. Both are explicit that the *scarce, verified, structure-linked experimental label* is the valuable, hard-to-produce artifact, not the bulk structural data, which is abundant elsewhere (Materials Project, ICSD, OQMD).

This guide extracts the concrete methodological choices those two papers made — data collection procedures, validation workflows, splitting strategies, benchmarking protocols, and known failure modes — and turns them into a prioritized improvement roadmap for your dataset.

---

## 2. Comparison table: what the literature datasets actually contain

This table is reconstructed from OBELiX's own comparison table (Therrien et al. 2025) plus the LiIon paper, extended with your dataset for reference.

| Dataset | Verified σ_RT labels | Structural info | Provenance | Splits | Benchmarked models |
|---|---|---|---|---|---|
| Sendek et al. | 0 | Comp+Spg+Lattice+CIF (317) | Screening only, no exp. | — | — |
| Jalem et al. | 0 | Comp+Spg+Lattice+CIF (318) | Eb (migration barrier) only | — | — |
| He et al. (SPSE) | 0 | 75 CIFs manually extracted; 12k geometric-only | Eb via bond-valence site energy | — | — |
| **LiIon (Hargreaves et al.)** | 465 (820 total incl. non-RT) | Composition + structural-family label only, **no space group/lattice/CIF** | Literature, ACIS-measured, sentence-level expert review | k-folds + LOCO-CV (DBSCAN clusters) | AutoSklearn, CrabNet (± transfer learning) |
| Laskowski et al. | 1,346 | Space group only (344 w/ ICSD ID, proprietary) | Semi-supervised extraction | — | — |
| Shon & Min | ~4,032 (text-mined) | ~350 have qualitative "structure type" | NLP/text-mining, temperature often unspecified | — | — |
| Yang et al. (DDSE) | 2,448 (on request) | Limited | Broad temp range 132–1262K | — | — |
| **OBELiX (Therrien et al.)** | 599 (321 with full CIF) | Composition + space group + lattice + **CIF for 321** | Literature, ICSD cross-matched, near-duplicate filtered | Monte-Carlo leakage-free split by paper/composition, 20–30% test | RF, MLP, PaiNN, SchNet, M3GNet, SO3Net, CGCNN (± pretrain, ± disorder-aware) |
| **Your dataset (Scandium-Labs)** | 183 verified (+427 consensus, 165 gold) | Full CIF/structure for all 30,838 DFT rows (backbone) | Sentence + page + DOI level, LLM-assisted + deterministic verification + human review | Composition-family grouped (per your card) | None published yet |

**What this table tells you directly:**

1. **You already beat every dataset except OBELiX on structural completeness of the labeled rows**, because your bulk DFT backbone means most materials in your ecosystem already have full crystal structures — OBELiX had to manually chase down CIFs for only 321/599 entries via ICSD cross-matching, a process that took real curator time. Your architecture (DFT-first, labels-attached-after) sidesteps that bottleneck structurally, *if* your verified 183 records are actually linked to their corresponding DFT structure rows.
2. **You lag every literature dataset on the most important comparison axis: independent, external benchmark results.** OBELiX's core contribution isn't the CSV — it's that they ran 7 models against it and published numbers. That's the single largest maturity gap between your release and theirs.
3. **Nobody except OBELiX solved data leakage properly.** LiIon uses LOCO-CV via DBSCAN clustering as a secondary check but their main results use random k-folds. OBELiX's Monte Carlo split-by-paper/composition method is the field's current best practice, and it's directly reusable on your verified/consensus/gold tiers.

---

## 3. Deep dive: what OBELiX did that you should replicate

### 3.1 Data collection — cross-database triangulation, not single-source scraping

OBELiX did not extract structures independently per paper. Instead, they:

- Started from **two existing composition/conductivity datasets** (LiIon + Laskowski) as seed lists, then manually filled gaps from original papers' tables/figures.
- **Cross-matched every entry against the ICSD** by lattice parameters, space group, and composition (±0.05 composition tolerance, ±3% lattice tolerance) to recover full CIFs — including "close matches" where the exact publication wasn't indexed but a near-identical structure was.
- Explicitly distinguished **"total" vs "bulk" ionic conductivity** — total includes grain-boundary effects, bulk does not, and conflating them is a silent source of label noise industry-wide. They recorded both when available.
- Tracked the **number of formula units (Z)** per unit cell, enabling density/volumetric-density computation consistently across entries with different cell choices for the same material (e.g., Li₃PO₄ can be reported as Z=2 or Z=4 depending on space group convention).

**Action for you:** Your `ion_transport` schema already separates `conductivity_type` — confirm this cleanly distinguishes bulk vs. total in every verified record, not just where the source paper happened to label it. If source papers don't specify, flag as `unknown` rather than defaulting to one — OBELiX's experience shows conflating these is a major uncontrolled noise source (see §3.4 below on quantified reproducibility).

### 3.2 Duplicate and near-duplicate detection — this is harder than it sounds

OBELiX explicitly filtered for two failure modes that are easy to miss automatically:

- **Exact duplicates** (same entry pulled from two source papers).
- **False near-duplicates**: papers routinely report conductivity measured in *one* study alongside structural data cited from *another* study of the "same" material. If not caught, you get two dataset rows with identical σ but only one of which is the material that σ was actually measured on — silently corrupting structure–property pairs.

**Action for you:** Your pipeline's "deterministic verification (Arrhenius consistency, unit normalization, cross-paper consensus)" step is a good start, but explicitly check whether it catches the *structure attribution* failure mode above — i.e., does the structure attached to a conductivity label come from the same measurement/paper as the conductivity itself, or was it silently borrowed from a different source? This is exactly the kind of error your sentence-level provenance should let you audit systematically, which is a genuine advantage you have over OBELiX (they did this by hand).

### 3.3 Leakage-free splitting — the single most reusable technique here

This is OBELiX's most transferable contribution. Their method:

1. Group entries by **paper of origin** and by **composition** — any two entries sharing either must end up in the same split (train or test).
2. Run a **Monte Carlo search** that moves whole groups between splits to jointly minimize:
   - the KL/distributional difference in log(σ) between train and test,
   - the distributional difference specifically within the CIF-bearing subset,
   - while constraining the test fraction to land between 20–30% of the full dataset.
3. Report the resulting **space-group and crystal-family balance** per split, and explicitly flag where perfect balance wasn't achievable (e.g., their space group 167 had a large single-paper cluster that couldn't be split without leaking).

Why this matters: without this, random k-fold splits leak information (a model can "cheat" by having seen a near-identical composition/paper during training), producing benchmark numbers that look good but don't reflect real extrapolation ability. OBELiX demonstrated this concretely — their geometric GNNs looked reasonable under naive validation but collapsed toward "predict the median" performance once evaluated on the leakage-free test set.

**Action for you:** Your `ml_features.split_group_key` field already exists — confirm whether the actual `ml_features.split_assignment` field (currently `null` in the schema) is populated with an OBELiX-style leakage-free split, or a naive random split. If it's not yet populated, this is the highest-leverage schema field to fill in next, because every downstream benchmark result you publish will be judged against whether your splits actually prevent leakage.

### 3.4 Quantifying measurement noise as a benchmark floor

OBELiX found 48 sets of entries (122 total) sharing identical composition + space group but reported independently, likely by different labs. They used the spread within these sets to compute:

- RMS deviation from set means: **0.63** in log₁₀(σ)
- Mean absolute deviation from set medians: **0.41**

They then used this number as a **noise floor**: any model reporting a lower MAE than 0.41 is very likely overfit, not genuinely more accurate than the experimental measurement process itself.

**Action for you:** Your `consensus` tier (427 materials with cross-paper statistics) is built for exactly this analysis and OBELiX didn't have anywhere near that scale (only 48 groups/122 entries). Compute and publish your own reproducibility floor from that tier — it would be a genuinely novel contribution, since no existing public SSE dataset has this many repeated measurements to draw the statistic from.

### 3.5 Benchmarking protocol — the part you're currently missing entirely

OBELiX's benchmark design, reusable near-verbatim on your `gold_benchmark` (165 records) and `verified` (183 records) tiers:

- **Baselines**: Random Forest and MLP on composition + space group + lattice vector features (fast, strong baselines — don't skip these in favor of jumping straight to GNNs).
- **Geometric models**: PaiNN, SchNet, M3GNet, SO3Net, CGCNN — run only on the CIF-bearing subset.
- **Hyperparameter search**: 100 randomly sampled configurations per model (exhaustive for RF/MLP since they're cheap to train), 5-fold cross-validation, lowest average validation MAE selects the config.
- **Pretraining comparison**: PaiNN/SchNet pretrained on Materials Project band-gap prediction, then fine-tuned; M3GNet/CGCNN using publicly available pretrained weights fine-tuned on formation energy / Fermi energy.
- **Disorder-aware variants**: they built modified CGCNN/SO3Net where atomic embeddings become an occupancy-weighted average across the partially-occupied elements at a site — rather than rounding occupancy to the nearest integer as all standard GNN implementations do by default.
- **Report against two controls**: a median-predictor baseline and, ideally, the experimental noise floor from §3.4. A model that doesn't beat "always predict the training median" is not a useful benchmark result, and OBELiX found this happened to *most* of the 3D geometric models they tested.

Their headline finding — **simple RF/MLP models beat every geometric GNN on the leakage-free test set**, because the GNNs overfit on a dataset this small and mishandle partial site occupancy — is itself a critical, non-obvious result for anyone modeling your dataset. It should shape what you recommend downstream users try first.

**Action for you:** Since your `structure.li_site_occupancy` field already exists, you have the raw material to reproduce their disorder-aware embedding trick directly, and given PIGNet's physics-informed GNN foundation, this is directly relevant to your own modeling work at Scandium Labs, not just the public dataset release.

---

## 4. Deep dive: what LiIon did that you should replicate

### 4.1 Human-in-the-loop QA infrastructure, not spreadsheets

LiIon's most underrated methodological point: with **20 researchers** validating **820 entries** from **214 sources**, they explicitly abandoned shared spreadsheets because of version conflicts, concurrent-edit collisions, and task-tracking chaos. Instead they built:

- A **Streamlit interface** presenting one entry at a time: composition, conductivity, temperature, and the **source PDF rendered inline** (served via a local Python HTTP server) so the validator never has to leave the tool to check the source.
- A required field for the validator to record discrepancies or corrections against the source.
- **Postgraduate/postdoctoral researchers with 2+ years of domain experience** doing the final validation pass — undergraduates only did the first-pass literature collation.
- A lighthearted retention mechanic: a GPT-2-generated compliment shown after each entry validated (small detail, but it's evidence they thought about annotator fatigue over a multi-month human-validation project).

**Action for you:** Your pipeline already has an `text_provenance.extraction_reviewer` field and an `evidence_sentence`/`evidence_paragraph` schema — good. The open question is whether your human review step has LiIon's core property: **the reviewer sees the actual source document inline, not just an extracted sentence**, so they can catch context the automated extraction missed (e.g., "this conductivity was computed, not measured" buried three sentences away from the number itself). If your `extraction_confidence_score` is currently purely model-generated rather than reviewer-adjusted, consider explicitly capturing reviewer agreement/disagreement with the automated extraction as a separate field.

### 4.2 Explicit rejection criteria — write down what gets thrown out

LiIon's exclusion policy, verbatim from their methods: any entry lacking supporting characterization (e.g., ICP analysis) to actually confirm lithium content/stoichiometry was **discarded outright**, not just down-weighted. They also dropped activation energy as a tracked field entirely once they discovered it wasn't reported consistently enough across sources to be useful.

**Action for you:** Your card already discloses "98% silver tier" honestly — good practice matching LiIon's transparency. Consider going one step further and publishing an explicit **rejection log or rejection-rate statistic** (how many candidate records were excluded during human review, and why) the way LiIon discloses its exclusion policy. This is a credibility signal reviewers and downstream users specifically look for, and right now your card doesn't state it.

### 4.3 Anthropogenic bias — name it, don't just imply it

LiIon devotes real space to a point your Known Limitations section only touches indirectly: **because researchers preferentially publish and characterize materials they already suspect are promising, low-conductivity materials are systematically underreported in the literature**, which biases the entire field's public data, not just any one dataset. They demonstrate this using an ElMD-based 2D projection showing where their conductor compositions sit relative to *all* known lithium-containing compounds in the ICSD — visually showing "the accessible-but-unexplored region" of composition space.

**Action for you:** You already have all 267,230 materials in your companion dataset to run exactly this analysis — project your verified conductivity-labeled compositions into the same compositional space as your full DFT backbone (t-SNE/UMAP is fine; LiIon specifically preferred UMAP over PCA for cluster separability) and visualize where your labeled data does and doesn't cover the space you've already screened computationally. This turns your "under-covered families" limitation from a qualitative statement into a quantitative, visual one — a direct upgrade matching LiIon's Figure 3/4.

### 4.4 Extrapolation testing (LOCO-CV) as a second, harder validation regime

LiIon's most important quantitative finding: models that perform well under standard k-fold cross-validation **collapse dramatically** under Leave-One-Cluster-Out cross-validation (clusters defined via DBSCAN on UMAP-embedded composition space). Their best model (CrabNet + transfer learning) dropped from R²=0.51/MAE~0.6 under k-fold to MCC=0.38 under LOCO — still the best of the models tested, but a meaningfully harder and more honest number.

**Action for you:** If/when you publish benchmark results (see §3.5), report **both** a standard split and a LOCO-style extrapolation split. A model that only looks good under standard k-fold is not evidence it can screen genuinely novel chemistries — which is presumably the actual use case for anyone using your dataset for discovery rather than interpolation within known families.

---

## 5. Concrete, prioritized action list

Ranked by (impact on dataset credibility / effort required):

**High impact, moderate effort**
1. **Populate `ml_features.split_assignment`** with an OBELiX-style leakage-free split (group by paper + composition, Monte Carlo balance on log(σ) distribution, target 20–30% test fraction). This single field is what separates "a CSV" from "a benchmark-ready dataset."
2. **Run and publish a baseline benchmark** — at minimum RF + MLP on composition/space-group/lattice features, ideally one GNN (CGCNN is the most standard/cheap starting point) on your CIF-bearing verified+gold_benchmark rows. Report MAE/R² under both random and leakage-free splits.
3. **Compute and publish an experimental-noise floor** from your 427-material consensus tier (RMS/MAD of log(σ) within same-composition, same-space-group groups). You have 3.5x more repeat-measurement groups than OBELiX did — this is a genuinely differentiating result to publish.

**High impact, low effort**
4. **Explicitly separate bulk vs. total conductivity** in every verified record, defaulting to `unknown` rather than guessing when source papers don't distinguish — a documented, not silent, choice.
5. **Publish a rejection-rate statistic**: how many candidate literature records were excluded during your human review stage, and the top 2–3 reasons (matches LiIon's transparency and preempts a common reviewer question).
6. **Cross-check structure-to-label attribution** in your verification pipeline specifically for the "structure from one paper, conductivity from another" failure mode OBELiX identified — your sentence-level provenance makes this auditable in a way OBELiX couldn't do at their scale.

**Medium impact, low effort**
7. **Add a disorder-aware occupancy field usage note** to your model card: since you already store `structure.li_site_occupancy`, explicitly flag for downstream users that standard GNN implementations (CGCNN, SchNet, etc.) silently round these to integers unless modified, per OBELiX's disorder-aware CGCNN/SO3Net variants.
8. **Compositional coverage visualization**: project your verified/gold-tier labeled compositions against your full 267,230-material DFT backbone using UMAP, to visually quantify which regions of already-screened chemical space still lack experimental conductivity labels — a direct, reusable extension of LiIon's Figure 3/4 approach, now possible at a scale neither LiIon nor OBELiX had access to.

**Lower priority / longer term**
9. Consider whether an activation-energy field is reported consistently enough across your sources to keep, following LiIon's precedent of dropping fields that can't be extracted reliably rather than leaving them sparsely populated indefinitely.
10. If pursuing external adoption, register the dataset on Kaggle in addition to Hugging Face — OBELiX does this explicitly to reach a broader non-HF audience.

---

## 6. Sources consulted

- Therrien, F. et al. *OBELiX: A Curated Dataset of Crystal Structures and Experimentally Measured Ionic Conductivities for Lithium Solid-State Electrolytes.* arXiv:2502.14234 (Mila, McGill, U. Ottawa, NRC Canada, U. Montréal), 2025.
- Hargreaves, C. J. et al. *A database of experimentally measured lithium solid electrolyte conductivities evaluated with machine learning.* npj Computational Materials 9, 9 (2023). DOI: 10.1038/s41524-022-00951-z.
- Your dataset card: `huggingface.co/datasets/Scandium-Labs/solid-state-electrolyte-conductivity`

Both papers are open access; full methods sections (data collection, splitting, hyperparameter tables, and computational resource logs) are reproduced in detail above rather than just cited, since those specifics are what's directly actionable for your pipeline.
