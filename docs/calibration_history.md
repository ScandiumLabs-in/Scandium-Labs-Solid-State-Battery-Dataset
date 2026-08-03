# Calibration history — AI review engine

Tracks auto-decision precision over time so a real regression is visible against a
trend line, not against memory. Add a row on **every** rules/scorer/decision change.

## Baseline

| Date | n ground-truth | auto-approve | auto-reject | auto-decided | false-reject | false-approve | notes |
|---|---|---|---|---|---|---|---|
| 2026-08-03 | 159 | 18/20 = 90% | 11/16 = 69% | 23% (36/159) | 5 | 2 | All 5 false-rejects are pre-existing evidence-FAIL records (SCRIBED/no-snippet); NOT caused by rule_digit_match/rule_dup_value (verified by running with those rules disabled). |

## Validation range changes

| Date | Family | Field | Old range | New range | Justification |
|---|---|---|---|---|---|
| 2026-08-03 | borohydride | Ea_eV | (0.30, 0.90) | (0.20, 1.70) | Lower bound: nanoconfined/composite LiBH4 in SBA-15 scaffolds reports ~0.2 eV (Takamura et al. 2009, J. Power Sources 187:337). Upper bound: bulk orthorhombic LiBH4 below the 390 K phase transition reports 1.4–1.7 eV Arrhenius barriers (Matsuo et al. 2007, Appl. Phys. Lett. 91:224103). Both extremes are physically legitimate; the old (0.30, 0.90) range was calibrated only on the high-phase data. |
| 2026-08-03 | sulfide | Ea_eV | (0.15, 0.45) | (0.10, 0.50) | Li5.4Al0.1PS4.7Cl1.3 argyrodite reports 0.09 eV (paper-verified). Widened lower bound by 0.05 eV to accommodate this verified extreme without blanket-widening. |
| 2026-08-03 | oxide | Ea_eV | (0.25, 0.85) | (0.20, 0.90) | Minor ±0.05 eV relaxation to avoid false flags on verified LATP/LLTO composites at the tails. |

---

## Action 6 — Human-review sampling & spot-audit policy (scale path)

100% human review is correct at ~116 records. It does not scale past ~500–1000.
This policy specifies **exactly when** full review applies vs. statistical
spot-audit, with a stated precision target the sampling rate is calibrated
against — never "let's sample less because there's more data now."

### Routing thresholds (based on the persisted ensemble-confidence signal)

| Record class | Route | Human effort |
|---|---|---|
| High confidence, model consensus (top-tier) | **Spot-audit** — sample at a fixed rate | 10–20% sampled |
| Medium confidence or model-disagreement | Full human review | 100% |
| Low confidence / evidence-FAIL / plot-digitized | Full human review | 100% |

**Sampling rate is NOT a free variable to shrink as volume grows.** It is
derived from a target spot-audit precision: the spot-audit pass runs the SAME
evidence chain (`verify_extraction_evidence.py`) on a uniform random sample; if
measured precision on the sampled sub-population falls below the target, the
sampling rate increases (never decreases). Target: **≥95% precision on the
lowest-confidence class that is spot-audited.**

**Sampling is never skipped for bulk sources.** Combinatorial-table (Action 3)
and plot-digitized (Action 4) records get full evidence verification regardless
of confidence — a systematic misread (bad axis calibration, wrong table column)
repeats across every row from one source, which is exactly the failure mode
uniform sampling under-detects. Bulk rows pass through the same
digit-match/duplicate detector that already caught a 250°C-misread and Ea-value
swaps.

### When the 100%→spot-audit switch is allowed

The switch is gated, not automatic:
1. **Calibration evidence exists** — at least one full-calibration pass at the
   current paper mix (below), so the ensemble's precision on that mix is known,
   not assumed.
2. **Mix-stability** — a new extraction source type (combinatorial table or
   plot digitization) entering production resets the affected class to 100%
   review until a new calibration row on *that specific class* is added.
3. **`min_gold_pct` gate** — see below.

### Rolling re-calibration (not one-off)

`scripts/calibrate_review_engine.py` must be re-run after every model/ensemble
or paper-mix change, and each run appends a row here so precision-vs-source-type
is tracked. A model calibrated on clean single-value text extraction will NOT
have the same precision on a 100-row combinatorial table or a digitized plot;
pretending it does is how quality erodes quietly.

### `min_gold_pct` blocking gate (once Gold moves off zero)

`min_verified_labels = 100` in `release_config.toml` is already trivially
cleared. Once Gold tier leaves zero, add a **blocking** `min_gold_pct` gate so
growth can't quietly ship all-Silver forever. This stays informational (0%
target) until Gold has a real denominator, per the plan.

### Audit log

(Append a row on every calibration run and every spot-audit result.)

| Date | Event | n | Auto-approve | Auto-reject | Spot-audit | Sampled | Sampled-precision | Notes |
|---|---|---|---|---|---|---|---|---|

