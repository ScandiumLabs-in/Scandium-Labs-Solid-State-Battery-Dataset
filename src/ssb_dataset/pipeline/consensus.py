"""Literature consensus engine — cross-paper aggregation of conductivity records.

Given a set of records (the review queue + approved records + benchmark
inventory), group them by material fingerprint and compute, per material:

  - n records, median sigma, geometric spread, outlier detection
  - n Ea records, median Ea
  - a per-material "consensus range" used to flag order-of-magnitude outliers

The engine is statistical only — it never edits values. An outlier flag means
"this record disagrees with the body of literature for this material by more
than the group allows" and is routed to human review (or to the benchmark
check), never auto-corrected.

Because conductivities span orders of magnitude, all aggregation is done in
log10 space and medians are reported as both linear and log values.
"""

from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass, field
from statistics import median

import numpy as np

from ssb_dataset.pipeline.fingerprint import group_key

# Order-of-magnitude outlier threshold (log10 units).
# If |log10(sigma) - median_log10| > MAX_ORDER_SPREAD, flag as outlier.
MAX_ORDER_SPREAD = 1.5  # ~30x from the group median
MIN_N_FOR_CONSENSUS = 3  # fewer records -> no consensus range, only spread check


@dataclass
class MaterialConsensus:
    group: str = ""
    n_sigma: int = 0
    sigma_values: list[float] = field(default_factory=list)
    median_sigma: float | None = None
    median_log10_sigma: float | None = None
    min_sigma: float | None = None
    max_sigma: float | None = None
    n_ea: int = 0
    ea_values: list[float] = field(default_factory=list)
    median_ea: float | None = None
    outlier_records: list[str] = field(default_factory=list)  # review_ids
    notes: list[str] = field(default_factory=list)

    def __post_init__(self):
        if self.sigma_values:
            logs = np.log10([v for v in self.sigma_values if v and v > 0])
            if len(logs) > 0:
                self.median_log10_sigma = float(median(logs))
                self.median_sigma = 10 ** self.median_log10_sigma
                self.min_sigma = float(10 ** logs.min())
                self.max_sigma = float(10 ** logs.max())
        if self.ea_values:
            self.median_ea = float(median(self.ea_values))

    @property
    def has_consensus(self) -> bool:
        return len(self.sigma_values) >= MIN_N_FOR_CONSENSUS


@dataclass
class ConsensusResult:
    materials: dict[str, MaterialConsensus] = field(default_factory=dict)
    flagged: list[dict] = field(default_factory=list)  # per-record outlier flags
    total_records: int = 0

    def summary(self) -> list[dict]:
        rows = []
        for grp, mc in sorted(self.materials.items()):
            rows.append({
                "group": grp,
                "n_sigma": mc.n_sigma,
                "n_ea": mc.n_ea,
                "median_sigma": mc.median_sigma,
                "median_log10_sigma": mc.median_log10_sigma,
                "range": [mc.min_sigma, mc.max_sigma] if mc.sigma_values else None,
                "median_ea": mc.median_ea,
                "has_consensus": mc.has_consensus,
            })
        return rows


def compute_consensus(records: list[dict],
                      *,
                      sigma_key: str = "normalized_sigma",
                      ea_key: str = "normalized_ea",
                      id_key: str = "review_id",
                      max_order_spread: float = MAX_ORDER_SPREAD) -> ConsensusResult:
    """Aggregate a list of record dicts into per-material consensus + outliers.

    Records without a resolvable sigma are counted for Ea consensus only.
    `sigma_key` selects the normalized sigma field (normalize_record_units
    should be run first); a `value`/`unit` fallback is attempted when the
    normalized field is absent.
    """
    from ssb_dataset.pipeline.normalization import normalize_sigma

    groups: dict[str, MaterialConsensus] = defaultdict(MaterialConsensus)
    flagged: list[dict] = []

    # pass 1: collect values per group
    for rec in records:
        grp = group_key(str(rec.get("composition", "")))
        mc = groups[grp]
        mc.group = grp

        sigma = rec.get(sigma_key)
        if sigma is None and rec.get("value") is not None and str(rec.get("property", "")).lower() == "conductivity":
            try:
                sigma = normalize_sigma(rec.get("value"), rec.get("unit")).value_s_per_cm
            except ValueError:
                sigma = None
        if sigma is not None and sigma > 0:
            mc.sigma_values.append(float(sigma))
            mc.n_sigma += 1

        ea = rec.get(ea_key)
        if ea is None and rec.get("Ea") is not None:
            ea = rec.get("Ea")
        if ea is not None:
            mc.ea_values.append(float(ea))
            mc.n_ea += 1

        # stash per-record sigma for pass 2 by id
        rec["_consensus_sigma"] = sigma
        rec["_consensus_group"] = grp

    # pass 2: re-init dataclasses so __post_init__ computes medians
    for grp in list(groups.keys()):
        prev = groups[grp]
        groups[grp] = MaterialConsensus(
            group=grp,
            sigma_values=prev.sigma_values,
            ea_values=prev.ea_values,
            n_sigma=prev.n_sigma,
            n_ea=prev.n_ea,
        )

    # pass 3: flag outliers — only when the group has a real consensus (n>=3).
    # With n=2 the two records are each other's only company: either can be
    # wrong and the "consensus" is meaningless, so don't flag (the family-range
    # and Arrhenius checks in autoflag_queue still cover that case).
    for rec in records:
        grp = rec.get("_consensus_group", "")
        mc = groups.get(grp)
        sigma = rec.get("_consensus_sigma")
        if not mc or not mc.has_consensus or sigma is None or sigma <= 0 or mc.median_log10_sigma is None:
            continue
        delta = abs(np.log10(sigma) - mc.median_log10_sigma)
        if delta > max_order_spread:
            rec_id = str(rec.get(id_key, "")) or f"{grp}/{sigma:.2e}"
            mc.outlier_records.append(rec_id)
            flagged.append({
                "review_id": rec_id,
                "group": grp,
                "composition": rec.get("composition", ""),
                "sigma": sigma,
                "median_sigma": mc.median_sigma,
                "delta_log10": round(float(delta), 2),
                "note": f"sigma {sigma:.2e} is {10**delta:.0f}x from {grp} median "
                        f"{mc.median_sigma:.2e} (n={mc.n_sigma})",
            })

    return ConsensusResult(materials=dict(groups), flagged=flagged, total_records=len(records))


def consensus_for(records: list[dict], composition: str,
                  sigma_key: str = "normalized_sigma",
                  ea_key: str = "normalized_ea") -> MaterialConsensus | None:
    """Convenience: consensus for a single material across the given records."""
    grp = group_key(composition)
    result = compute_consensus(records, sigma_key=sigma_key, ea_key=ea_key)
    return result.materials.get(grp)
