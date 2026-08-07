# Negative Results Database (Phase C, v1.5.0)

The artifact "almost nobody builds". Most materials datasets are
survivorship-biased: materials that don't work — thermodynamically unstable
hosts, electronically-conducting phases, poor-transport lattices — are quietly
dropped, and ML models train only on the ones that survived. This release makes
the negatives **first-class** so pipelines can train on the full distribution.

Built by `src/ssb_dataset/negative/negative.py` + `scripts/
build_negative_results.py` (no LLM calls, no network, deterministic). Writes
`negative_output/`.

## Outputs

```
negative_output/
├── canonical_negative.parquet        # canonical + negative.* block columns
└── negative_results_report.json      # scope, signal counts, per-source share
```

## Negative block (per canonical row)

| Column | Meaning |
|---|---|
| `negative.is_negative_result` | True / False / **None** |
| `negative.reasons` | firing signals (list) |
| `negative.evidence` | raw values behind the flags |
| `negative.confidence` | high (DFT fact) / medium (proxy) |
| `negative.energy_above_hull_eV_atom` / `is_metal` / `band_gap_eV` / `li_hopping_distance_A` | raw signals kept for re-thresholding |

## Signals (deterministic, MP columns)

1. **`thermodynamically_unstable`** — `energy_above_hull > 0.025 eV/atom`
   (MP stability convention). The host would decompose toward its hull rather
   than serve as a stable electrolyte.
2. **`electronic_conductor`** — `is_metal` True or `band_gap == 0`. A metal
   cannot be a pure solid electrolyte; it shorts the cell electronically.
3. **`poor_li_transport_proxy`** — `li_hopping_distance > 4.5 Å`. No connected
   Li-sublattice percolation path. **Medium confidence**: it is a proxy, not a
   measured conductivity.

## Honesty conventions

- **Unknown is never fabricated**: a record with no computable signal (e.g. a
  literature-mined row with no MP structure) stays `is_negative_result=None`,
  not False. 983 records are honestly unknown.
- A property missing on a row simply does not fire its signal — absence is not
  a negative.
- Known-good electrolytes (LLZO, Li3PS4, Li6PS5Cl, Li2O, LiF) are verified **not**
  flagged.

## Current scope (2026-08-06)

- **23,400/30,838 records flagged negative (75.9%)**: 16,326 unstable, 11,295
  electronic conductors, 3,214 poor-transport.
- By source: MP 85.3% (the bulk catalog is unstable-rich Li
  intermetallics/metals — exactly the bias this fixes), JARVIS 60.6%
  (electronic signal), lit/NOMAD/COD/OQMD/AFLOW unknown.

## How to run

```bash
python scripts/build_negative_results.py
```
