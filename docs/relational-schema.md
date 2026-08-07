# Relational Schema (v1.2.0)

The v1.0.0+ releases convert the flat canonical dataset (30,838 rows in
`cleaning_output/canonical_dataset.parquet`) into seven linked, id-keyed parquet
tables implementing the roadmap's **material → paper → experiment →
measurement** hierarchy. Built by `scripts/build_relational_dataset.py` (no LLM
calls, fully deterministic), written to `relational_output/`.

The core design principle is the roadmap's "never overwrite experimental
variability": every reported σ/Ea/σ60C/σ80C value is its own measurement row.
Dedup collapses only identical (material, paper, condition-fingerprint) rows —
two experiments reporting different σ for the same material are both preserved.

## Table inventory

| Table | Rows | Key | Description |
|-------|------|-----|-------------|
| `materials` | 30,801 | `material_id` | One row per unique material formula; identity/family/space-group structure + thermodynamics + magnetic/electronic + chemistry descriptors + `source_dbs` + `n_experiments`/`n_papers`/`n_measurements` |
| `papers` | 111 | `paper_id` | DOI, title/journal/year (Phase 10 backfilled), `metadata_source`, `n_experiments`/`n_measurements` aggregates |
| `authors` | 9 | `author_id` | `paper_id` → ordered author list (recovered from clean structured first-page blocks only) |
| `experiments` | 179 | `experiment_id` | One row per unique (material, paper, experiment-condition, synthesis) fingerprint |
| `measurements` | 254 | `measurement_id` | One row per reported value: property, value, unit, temperature_C, method, field-level confidence |
| `synthesis` | 162 | `synthesis_id` | Precursors + method flags + conditions per material/paper |
| `dopants` | 1 | `dopant_id` | Explicit dopant annotations (`Li7La3Zr2O12:Ta`) |

## Papers metadata + authors (Phase 10, v1.2.0)

The v1.0 papers table was DOI-keyed only — every title/journal/year was None.
`src/ssb_dataset/db/papers.py` backfills it **deterministically from data
already on disk** (no network, no LLM, nothing fabricated):

1. `literature_output/gold_scored.json` — 762 DOI→{title, year} entries from
   the discovery/mining pipeline.
2. `literature_output/doi_years_cache.json` — 772 DOI→year entries.
3. `literature_output/crossref_metadata.json` — opt-in Crossref cache (populated
   by `scripts/enrich_papers_crossref.py` when a network is available).
4. On-disk PDF first pages — format-aware parsing (eScholarship/LBL structured
   block, Nature-style DOI-anchored block, arXiv/Science-Advances/KCerS
   headers).

**DOI-confirmation gate:** a PDF-recovered block is only trusted when the DOI
actually appears on the first page. This caught a real mislabeled file
(`10.1021_jacs.1c07481.pdf` on disk is a magneto-optic paper, not the Li2ZrCl6
electrolyte paper) and rejected it. Unknown DOIs stay None — never guessed.
Every filled field is traceable via the `metadata_source` column
(`cache`, `pdf_first_page_*`, or a combination).

The `authors` table only emits **clean structured author lists** (eScholarship/
LBL blocks). Free-text first-page name blocks (Nature-style names fused with
affiliation markers and no spaces) are deliberately not parsed heuristically —
a sparse-but-honest table beats invented names.

## Stable ids

All ids are deterministic sha256 fingerprints of the row's semantics:

```
stable_id(kind, *parts) -> "<prefix>-<16 hex>"
```

- Prefixes: `exp-`, `meas-`, `syn-`, `dop-`, `smp-`, `paper-`, `aut-`.
- `paper_id` = DOI when the source record has one, else `paper-<hash>`.
- `experiment_id` = hash(material_id | paper_id | experiment-fingerprint |
  synthesis-fingerprint).
- `measurement_id` = hash(material_id | paper_id | experiment_id | property |
  value | unit | temperature_C | method | ...).
- Fingerprints include only **populated** fields: `False` bools and empty
  containers are excluded (`_populated`), so a record that never measured
  something and a record that measured `False` produce the same fingerprint
  only when they are semantically identical.

## Field-level confidence (Phase F)

Every `measurements` row carries five confidence columns (0..1):

| Column | Rule |
|--------|------|
| `value_confidence` | tier base blended with `extraction_confidence_score` (0.6·base + 0.4·xc). `verified_human` is **always 1.0** — an extraction score can never dilute a human check |
| `temperature_confidence` | 1.0 iff a measurement temperature is present |
| `method_confidence` | 1.0 iff a measurement method is present |
| `evidence_confidence` | 1.0 iff an evidence sentence is present |
| `overall_confidence` | 0.5·value + 0.15·temperature + 0.15·method + 0.2·evidence |

Tier bases: `verified_human` 1.0, `high_confidence_extraction` 0.85,
`low_confidence_extraction` 0.5, `dft_native` 0.2–0.3 (by variant).

## Dopant extraction

`extract_dopants(material_id)` is intentionally conservative — a dopant is only
an **explicit annotation**:

- `Li7La3Zr2O12:Ta` → `["Ta"]`
- `Li6.25Al0.25La3Zr2O12 Al-doped` → `["Al"]`

Never treated as dopants:

- Molar-ratio annotations: `Li2S-P2S5 (70:30) glass` → `[]`
  (the `(70:30)` is a mixture ratio, not a dopant).
- Source-prefixed ids: `aflow-aflow:019c9366d67e6cca`, `mp-*` → `[]`.

The benchmark inventory's annotated names feed the `dopants` table as a
secondary source (`dopant_source = material_id_annotation`).

## Provenance chain

Every measurement links back through its full chain to the source paper:

```
measurements.measurement_id → experiments.experiment_id → materials.material_id
                          → papers.paper_id (DOI)
```

`measurement_provenance` coverage (from `validation_output/provenance_report.
json`, 254 measurements): paper_id **100%**, evidence_sentence **88.2%**,
confidence **100%**, temperature **94.5%**, measurement_method **53.5%**,
reviewer **84.3%**.

## Release gates

Three new config-driven gates in `release_config.toml`:

| Gate | Threshold |
|------|-----------|
| `relational_tables_built` | 6 tables; ≥25,000 materials; ≥150 experiments; ≥200 measurements |
| `measurement_provenance` | ≥80% paper/sentence/confidence coverage |
| `multi_experiment_preserved` | ≥10 materials with >1 independent experiment |

`scripts/release.py` stages the six relational tables plus
`relational_report.json` and the three `validation_output/*_report.json` files.

## Building

```bash
python3 scripts/build_relational_dataset.py   # → relational_output/ + validation_output reports
python3 scripts/release.py                    # → 17 gates (16 prior + relational gate count)
```

## Known limits

- `papers` is network-free: only DOI/title/journal/year already present in the
  canonical dataset (no Crossref enrichment).
- `dopants` = 1 is the honest count — after the ratio/source-id fix, only
  `Li7La3Zr2O12:Ta` is a genuine annotation in the catalog.
- `synthesis` (162) is sparse: only MP `synthesis`-endpoint recipes + the
  experiment block's synthesis fingerprints.
