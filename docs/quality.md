# Dataset Quality System (v0.9.0)

The first roadmap step toward the v1.0 experimental dataset. Every record in
the canonical dataset (30,838) now carries a deterministic quality score, is
scanned for anomalies, has its units audited, and — when it carries a
measurement — is promoted into a first-class experiments table.

Four new artifacts are produced by `scripts/build_canonical_quality.py` and
consumed by three new release gates.

## 1. Record-level quality scoring

### DFT rows (`completeness_score`)
Pure function in `src/ssb_dataset/quality/scoring.py`. Computes a weighted
block-coverage score, not a "how good is the physics" score. Weights match the
value of each schema block to the SSB use-case:

| Block | Weight |
|-------|--------|
| structure | 30 |
| thermodynamics | 20 |
| chemistry | 15 |
| electronic | 10 |
| redox | 7 |
| magnetic | 6 |
| graph | 6 |
| dielectric | 3 |
| mechanical | 3 |

Consistency penalties (−5 each): density ≤ 0, volume ≤ 0, band_gap < −0.05,
energy_above_hull < −0.05, charge imbalance (`redox.electroneutral = False`).

Optional columns (`weighted_work_function`, `piezo_e_ij_max`,
`decomposition_products`, `electrochemical_stability_window`) are excluded from
coverage so genuinely-sparse data never punishes a record.

### Literature rows (`experimental_score`)
Reuses the A3/A4 `score_record` ladder (`src/ssb_dataset/literature/
record_quality.py`): evidence quality, metadata completeness, cross-paper
consensus, Gold/Silver/Bronze tiers.

### Why JARVIS/COD/AFLOW/OQMD/NOMAD score low
The canonical staging for those sources holds structure + thermodynamics only;
the chemistry descriptor columns are computed later in the featurization stage
(`features_output/descriptors.parquet`). The low scores are honest — they
measure canonical-level completeness, and the fix is to materialize descriptors
into staging, not to relax the scorer.

## 2. Anomaly scan

`src/ssb_dataset/quality/anomalies.py` — `scan_anomalies(df)` runs 8 checks:
negative_activation_energy, negative_conductivity, density_exceeds_theoretical
(pellet density > 1.05×theoretical), temperature_below_zero_k,
duplicate_doi (one DOI → >1 material), duplicate_experiment (doi|material|
sigma duplicate), missing_composition, charge_imbalance.

`passed` = 0 high-severity failures. Writes `validation_output/anomaly_report.json`.

Known current findings (all non-blocking):
- `charge_imbalance` n=5,932 (medium) — MP `electroneutral=False` rows.
- `duplicate_experiment` n=2 (medium) — the known Li2OHCl same-DOI duplicate.
- `duplicate_doi` n=38 (low).

## 3. Unit-normalization audit

`src/ssb_dataset/quality/unit_audit.py` — `audit_units(df)`:
- σ_RT within [1e-12, 1e2] S/cm
- Ea within [0.01, 5.0] eV
- temperature_min_K ≥ 0
- unit-string leak: any canonical numeric column containing unit tokens
  (mS/cm, S/m, etc.) — the classic sign of a non-normalized value.

`passed` = 0 invalid values. Writes `validation_output/unit_audit.json`.

This is audit-only for now; a remediation pass (fixing the flagged rows into
canonical SI) is deferred.

## 4. First-class experiments table

`src/ssb_dataset/quality/experiments.py` — `build_experiments_table(df)`:

- Promotes every row carrying an `experiment` block or a σ/Ea measurement.
- `experiment_id` = `exp-` + sha256(material_id|doi|sigma|ea|min_temp)[:16] —
  deterministic, so re-runs are stable and identical measurements from the
  same paper collapse.
- 37 experiment/metadata fields + measurement fields (sigma_S_per_cm,
  activation_energy_eV, temperature_min_C/max_C) + evidence fields + family +
  source_db + canonical_row.
- Duplicate experiment_ids dropped.

This is the v1.0 hierarchy's foundation: **1 material → N papers → N
experiments → N measurements**. Experimental variability is preserved per-row
and never collapsed into a single material-level aggregate.

## Release gates

`release_config.toml` (config-driven):

| Gate | Threshold | Default |
|------|-----------|---------|
| `canonical_quality_scored` | ≥ N records scored AND avg ≥ min | 25,000 / 50.0 |
| `anomaly_report_passed` | 0 high-severity failures | — |
| `unit_normalization_passed` | 0 invalid unit values | — |

Current status (all 13 gates PASS):
- 30,838 scored, avg 60.3
- anomaly scan passed (0 high-severity)
- 0 invalid unit values

## Rebuild

```
python3 scripts/build_canonical_quality.py
python3 scripts/release.py            # --skip-tests to skip the suite
```

## Known limits
- Unit audit is audit-only (no auto-fix of flagged rows yet).
- DFT completeness scores cover canonical-level columns only; descriptor-level
  coverage is a featurization-stage concern.
- charge_imbalance (5,932) is medium-severity and intentionally non-blocking —
  MP marks some redox-imbalanced compositions as non-electroneutral by design.
