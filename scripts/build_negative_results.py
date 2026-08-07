#!/usr/bin/env python3
"""Build the negative results database (Phase C, v1.5).

Deterministic, LLM-free anti-survivorship-bias labeling of the canonical
dataset: every record whose DFT evidence marks it a poor solid-electrolyte
candidate (thermodynamically unstable host, electronic conductor, no connected
Li-sublattice path) is flagged `negative.is_negative_result=True` with reasons
+ evidence. Records with no computable signal stay None (unknown) — never a
fabricated False.

Outputs:
  negative_output/canonical_negative.parquet  canonical + negative.* block
  negative_output/negative_results_report.json
"""

from __future__ import annotations

import json

from ssb_dataset.negative import negative


def main() -> None:
    negative.NEGATIVE_OUT.mkdir(exist_ok=True)
    df = negative.build_negative_frame()
    df.to_parquet(negative.NEGATIVE_OUT / "canonical_negative.parquet",
                  index=False)
    report = negative.summarize(df)
    (negative.NEGATIVE_OUT / "negative_results_report.json").write_text(
        json.dumps(report, indent=2, default=str))
    print(json.dumps(report, indent=2, default=str))


if __name__ == "__main__":
    main()
