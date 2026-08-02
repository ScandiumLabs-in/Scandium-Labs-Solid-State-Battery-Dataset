# Confidence-score fix — design notes (2026-08-03, UPDATED)

## Problem
Every extraction record carried a **flat placeholder confidence (~0.7)** regardless
of model, paper quality, or ensemble agreement. It conveyed no signal and was
ignored by the trust score. (Phase A.4 of the roadmap.)

## Finding (why retrospective was impossible)
The ensemble runner was emitting only the **aggregated** final record — the
per-model vote counts, ensemble size, and spread were computed in-memory in
`_aggregate_ensemble()` and then dropped. No `confidence` / `votes` / `agreement`
keys were persisted on the 109 extracted records, so agreement→confidence could
not be calibrated on existing data without re-running extraction (429 rate ceiling,
3× call cost).

## ✓ What landed (2026-08-03)
The recording gap is closed **before** resuming extraction volume:
- `ExtractedConductivityRecord` gained `ensemble_votes`, `ensemble_size`,
  `sigma_spread_frac` fields (defaults None, backwards-compatible).
- `_aggregate_ensemble()` now fills them: `votes = len(records)`,
  `size = n` (ensemble runs), `spread = max relative sigma deviation from the
  running median across agreeing runs (0 = perfect agreement)`.
- `TextProvenanceBlock` gained the same three fields so the values ride through
  `extraction_record_to_material_record()`.
- `scripts/batch_extract.py::record_to_dict` persists `extraction_confidence`,
  `ensemble_votes`, `ensemble_size`, `sigma_spread_frac` alongside the record.

`confidence` itself is still the heuristic `min(0.85, 0.5 + 0.1*votes)` (cap 0.85).
The next step is to **calibrate** that against the verifier (`verification_report.json`
digit_match) now that votes+spread are captured: a value with
`votes == ensemble_size` and `spread ≈ 0` and `digit_match True` is high-confidence;
a `1-of-N` split is low. Use the already-verified records as the labeled set.

## Tests added (+2, suite 544)
- `test_extraction_record_ensemble_provenance` — votes/size/spread ride through to provenance.
- `test_aggregate_ensemble_carries_votes_and_spread` — 3 identical runs → votes 3, size 3, spread 0.0, conf 0.80.

## Guarantee
An `activation_energy` record never inherits a sigma-derived confident (mirror the
existing property-aware guard): `ensemble_*` fields are sigma-only provenance and
are null for Ea-only aggregations unless a sigma value exists.