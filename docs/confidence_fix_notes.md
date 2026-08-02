# Confidence-score fix — design notes (2026-08-03)

## Problem
Every extraction record carries a **flat placeholder confidence (~0.7)** regardless
of model, paper quality, or ensemble agreement. It conveys no signal and is ignored
by the trust score. (Phase A.4 of the roadmap.)

## Finding: the raw material for a real confidence score is NOT currently persisted

The ensemble runner (`scripts/batch_extract.py`) calls
`extract_from_pdf(..., ensemble_size=N)`, but `record_to_dict()` (line 42) emits
only the **aggregated** final record — `sigma_RT`/`Ea`/method/experiment. It does
not persist:

- per-model vote counts (`votes`),
- which model produced each value,
- the ensemble agreement ratio,
- the `confidence = 0.5 + 0.1 * votes` score that `extraction.py` computes in-memory.

The `literature_output/extraction_results.json` records confirm this: no
`confidence` / `votes` / `agreement` keys exist on any of the 109 extracted records.

## Why this matters for the recommended fix
Phase A.4's *cheapest* option ("derive confidence from ensemble agreement") cannot
be done retrospectively on the already-extracted 109 records — the vote data is gone.
Any model→value→vote mapping would have to re-run extraction, which hits the Groq
429 rate ceiling and triples call cost per paper.

## Recommended path (revised)
1. **Change recording first** (`scripts/batch_extract.py` + `extraction.py`):
   extend `record_to_dict` to persist `votes`, `ensemble_size`, `sigma_agreement`,
   and `confidence` per record *before* harvesting more volume. Then future
   batches accumulate the labeled signal cheaply.
2. **Re-run only a small sample** (existing on-disk PDFs, low count) to map
   agreement→confidence→verifier outcome, rather than re-fetching everything.
3. **Calibrate against the verifier** (`verification_report.json` digit_match):
   a value with `votes==ensemble && digit_match True` is high-confidence; a
   `1-of-N` split is low. Use the already-verified records as the labeled set.
4. **Wire the resulting confidence into the placeholder** only after it varies.
5. Unit-test that an `activation_energy` record never inherits a sigma-derived
   confidence (mirror the existing property-aware guard in normalization).

Requires a small schema addition then a targeted conffidence patch next batch run.