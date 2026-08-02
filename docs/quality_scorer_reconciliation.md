# Scorer reconciliation: `build_quality.py` vs `build_material_cards.py`

The dataset computes **two different numeric scores** that both use the word
"quality". They answer different questions and are produced by different
modules. This doc pins down exactly what each means so downstream consumers
never conflate them.

## 1. Record-level quality score — `quality_output/quality_report.json`

Produces `quality_output/quality.parquet` and `quality_report.json`.

- **Module:** `src/ssb_dataset/literature/record_quality.py::score_record`
- **Unit of analysis:** a single review-queue **record** (one composition ×
  σ/Ea × experiment measurement).
- **Builder:** `scripts/build_quality.py`
- **Fields:** `score` (0–100), `grade` (A+–D), `tier`
  (Gold / Silver / Bronze / Rejected).
- **Weights:** human verification 25, evidence quality 20, metadata
  completeness 20, cross-paper agreement 15, measurement depth 10, outlier
  penalty −10. Missing evidence caps the score at 30.
- **Tier rule:** **Gold** = human + evidence + (≥2 papers or consensus) +
  metadata pair; **Silver** = human + evidence; **Bronze** = AI-only with
  score ≥ 80.

### Current distribution (2026-08, resync)
- 143 records; score avg **47.7** (min 35, max 66).
- **Gold 0**, Silver 138, Bronze 0, Rejected 5.
- Gold is 0 because the metadata pair is genuinely unpopulated
  (temperature + method + sample form are sparse on most verified records),
  not because of a gate bug.

## 2. Material consensus/quality score — `literature_output/...`

Produced by `scripts/build_material_cards.py` → `material_cards.json`.

- **Module:** `src/ssb_dataset/literature/material_cards.py`
- **Unit of analysis:** a **material** (grouped across papers), not a record.
- **Two fields:**
  - `consensus_score` (0–100) — statistical agreement only: σ agreement
    within 1 order, paper breadth, Ea agreement, temperature coverage, minus
    outlier penalty.
  - `quality_score` (0–100) — M11 enriched score: agreement grade 30, paper
    breadth 20, measurement depth 15, **metadata completeness 15**, Ea
    coverage 10, outlier penalty −5 each.
- **Grades:** A+–D.

### Current distribution (387 materials)
- `consensus_score` avg **23.2** (0/range 19–100).
- `quality_score` avg **30.4** (16–84).

## Why they differ

| | `quality.py` score | `material_cards.py` quality_score |
|---|---|---|
| Scope | one record | one material (aggregated) |
| Weights | human-verify-heavy | agreement/breadth-heavy |
| Counts | 143 records | 387 materials |
| Gold | 0 (metadata pair) | n/a (material level) |

They are **not** redundant: the record score answers "is this single extraction
trustworthy?", while the material score answers "how well-agreed is this
material across the literature?". Both are deterministic and unit-tested.

## Forward note
A single named "quality score" would be simpler, but the two granularities
(record vs material) genuinely need separate scores. Keep the two names
distinct in any downstream report (release_report, dashboard) so a reader does
not compare `quality_report.json::score_avg` (47.7) to
`material_cards::quality_score` (30.4).