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

