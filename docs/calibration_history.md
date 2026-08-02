# Calibration history — AI review engine

Tracks auto-decision precision over time so a real regression is visible against a
trend line, not against memory. Add a row on **every** rules/scorer/decision change.

## Baseline

| Date | n ground-truth | auto-approve | auto-reject | auto-decided | false-reject | false-approve | notes |
|---|---|---|---|---|---|---|---|
| 2026-08-03 | 159 | 18/20 = 90% | 11/16 = 69% | 23% (36/159) | 5 | 2 | All 5 false-rejects are pre-existing evidence-FAIL records (SCRIBED/no-snippet); NOT caused by rule_digit_match/rule_dup_value (verified by running with those rules disabled). |
