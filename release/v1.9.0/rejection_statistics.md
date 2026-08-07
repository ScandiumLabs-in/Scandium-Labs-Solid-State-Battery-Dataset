# Rejection-rate statistic (guide §5 action 5)

Rejection statistic computed from the human review queue (all_queue_records.json). Rejection rate = rejected / (approved + rejected). Reasons are categorized deterministically from the human review note text.

## Review funnel

| stage | count |
|---|---|
| submitted | 402 |
| approved | 215 |
| rejected | 178 |
| pending | 9 |

**Rejection rate: 45.3%** (178/393 decided records rejected).

## Top rejection reasons

| reason | n |
|---|---|
| duplicate / near-duplicate (incl. DUP_VALUE copy-paste across compositions) | 80 |
| hallucination / value not in paper | 25 |
| unit error (mS/cm→S/cm or similar 1000×/100× misread) | 18 |
| evidence missing / cannot verify | 17 |
| composition series out of range / hallucinated variants | 13 |
| wrong value / correct value is different | 8 |
| composition misattribution | 4 |
| other | 4 |
| computed/simulated value not a measurement (AIMD/DFT/MD barrier) | 3 |
| false positive (regex matched wrong context: vacancy/sampling/activation) | 2 |
