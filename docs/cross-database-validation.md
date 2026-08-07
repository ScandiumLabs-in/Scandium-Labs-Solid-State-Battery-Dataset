# Cross-Database Validation (Phase A, v1.4.0)

First step of the post-Phase-19 scientific-credibility roadmap: every canonical
record whose reduced formula exists in ≥2 bundled DFT databases now carries a
deterministic **cross-database agreement block**. No LLM calls, no network —
the comparison runs entirely on the staged, on-disk source databases.

Built by `src/ssb_dataset/validation/cross_db.py` + `scripts/
build_canonical_validation.py`. Writes `validation_output/`.

## Outputs

```
validation_output/
├── cross_db_validation.parquet        # per-record agreement rows (both sides)
├── cross_db_validation_report.json    # summary + per-property offsets + exclusions
├── canonical_validation.parquet       # canonical + validation.* block columns
└── validation_report.json             # canonical-wide coverage summary
```

## Validation block (per canonical row)

| Column | Meaning |
|---|---|
| `validation.database_count` | # distinct bundled databases holding this reduced formula |
| `validation.agreement_score` | 0..1 mean over comparable properties of `max(0, 1 − |dev|/tol)` |
| `validation.disagreement` | JSON per-property `{agreement, abs_dev, mp, jarvis}` |
| `validation.rank` | agreement-score rank within the composition (1 = best-agreeing record) |

## Comparable properties & tolerances

| Property | Mode | Tolerance | Notes |
|---|---|---|---|
| `formation_energy_per_atom` | abs | 0.05 eV/atom | |
| `band_gap` | abs | 0.5 eV | JARVIS = OptB88vdW, MP = PBE — a known functional systematic |
| `density` | rel | 5% | |
| `volume_per_formula_unit` | rel | 5% | `cell_volume × fu_atoms / nsites` — cancels primitive-vs-conventional cell choice |
| `lattice_a/b/c` | rel | 3% | |

A property missing on either side is **absent**, never a zero score. A record
with no comparable counterpart in another database keeps `database_count = 0`
and `agreement_score = None` — missingness is never imputed as disagreement.

## Current scope (2026-08-06)

- **3,504 overlapping formulas → 17,802 validated records** (10,935 MP +
  6,867 JARVIS; 4,097 distinct compositions) of 30,838 canonical records.
- **Honest functional-systematic handling**: the per-property `mean_abs_dev` in
  the report is the documented offset (band gap ~0.4 eV, formation energy
  ~0.14 eV/atom median), not "disagreement". Structure agrees tightly
  (density/volume mean |Δ| ~0.08, lattice ~3%).
- **Excluded sources** (documented in the report, never zero-scored): NOMAD and
  COD staging rows lack composition/density/volume and formation-energy/band-gap
  values to compare; AFLOW/OQMD connectors are stubbed. See
  `validation_output/cross_db_validation_report.json` → `excluded_sources`.

## How to run

```bash
python scripts/enrich_jarvis.py                 # one-time: backfill JARVIS staging
python scripts/merge_verified.py                # rebuild canonical with enriched columns
python scripts/build_canonical_validation.py    # score + emit validation block
```
