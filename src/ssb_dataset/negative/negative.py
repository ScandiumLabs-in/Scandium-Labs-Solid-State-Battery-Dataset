"""Phase C (v1.5) — negative results database.

Deterministic, LLM-free anti-survivorship-bias labeling of the canonical
dataset. Most materials datasets quietly drop the materials that don't work —
failed conductors, thermodynamically unstable hosts, electronically-conducting
phases. This module makes those negatives first-class: every record that the
DFT evidence marks as a poor solid-electrolyte candidate carries an explicit
flag + reasons + evidence, so ML pipelines can train on the full distribution
instead of the survivors.

The three signals (each deterministic over on-disk MP columns):

  thermodynamically_unstable  energy_above_hull > 0.025 eV/atom
                              (MP stability convention) — the host would
                              decompose toward its hull rather than serve
                              as a stable electrolyte.
  electronic_conductor        is_metal True or band_gap == 0 — a metal
                              cannot be a pure solid electrolyte; it shorts
                              the cell electronically.
  poor_li_transport_proxy     li_hopping_distance > 4.5 Å — no connected
                              Li-sublattice percolation path. MEDIUM
                              confidence: it is a proxy, not a measured
                              conductivity.

A record is flagged is_negative_result=True when ANY signal fires; reasons
lists the firing signals; evidence carries the raw values. When NO signal is
computable (e.g. a literature-mined row with no MP structure), the record is
is_negative_result=None (unknown) — never a fabricated False.
"""

from __future__ import annotations

from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parent.parent.parent.parent
CANONICAL = ROOT / "cleaning_output/canonical_dataset.parquet"
NEGATIVE_OUT = ROOT / "negative_output"

# MP thermodynamic stability convention: E_hull > 0.025 eV/atom = unstable.
E_HULL_THRESHOLD_EV_ATOM = 0.025
# Li–Li hop beyond which no percolating sublattice path is plausible.
LI_HOP_THRESHOLD_A = 4.5

SIGNAL_UNSTABLE = "thermodynamically_unstable"
SIGNAL_ELECTRONIC = "electronic_conductor"
SIGNAL_POOR_TRANSPORT = "poor_li_transport_proxy"


# ---------------------------------------------------------------------------
# per-record scoring
# ---------------------------------------------------------------------------


def evaluate_row(row: dict) -> dict:
    """Evaluate the negative-result signals for one canonical row dict.

    Returns the NegativeResultBlock flattened columns as dict keys
    (negative.is_negative_result, negative.reasons, ...).
    """
    e_hull = _num(row.get("thermodynamics.energy_above_hull"))
    is_metal = row.get("thermodynamics.is_metal")
    band_gap = _num(row.get("thermodynamics.band_gap"))
    li_hop = _num(row.get("structure.li_hopping_distance"))

    reasons: list[str] = []
    evidence: dict[str, float] = {}
    if e_hull is not None:
        evidence["energy_above_hull_eV_atom"] = e_hull
        if e_hull > E_HULL_THRESHOLD_EV_ATOM:
            reasons.append(SIGNAL_UNSTABLE)
    if is_metal is True or (band_gap is not None and band_gap == 0.0):
        reasons.append(SIGNAL_ELECTRONIC)
        if band_gap is not None:
            evidence["band_gap_eV"] = band_gap
        evidence["is_metal"] = float(is_metal is True)
    if li_hop is not None:
        evidence["li_hopping_distance_A"] = li_hop
        if li_hop > LI_HOP_THRESHOLD_A:
            reasons.append(SIGNAL_POOR_TRANSPORT)

    has_any_signal_data = (e_hull is not None or is_metal is not None
                           or band_gap is not None or li_hop is not None)
    if not has_any_signal_data:
        # unknown, not a fabricated negative
        return {
            "negative.is_negative_result": None,
            "negative.reasons": [],
            "negative.evidence": {},
            "negative.confidence": None,
            "negative.energy_above_hull_eV_atom": None,
            "negative.is_metal": None,
            "negative.band_gap_eV": None,
            "negative.li_hopping_distance_A": None,
        }

    is_negative = len(reasons) > 0
    # high confidence when a hard DFT fact fires; medium if only the proxy
    confidence = "high"
    if reasons and set(reasons) == {SIGNAL_POOR_TRANSPORT}:
        confidence = "medium"
    return {
        "negative.is_negative_result": is_negative,
        "negative.reasons": reasons,
        "negative.evidence": evidence,
        "negative.confidence": confidence,
        "negative.energy_above_hull_eV_atom": e_hull,
        "negative.is_metal": is_metal,
        "negative.band_gap_eV": band_gap,
        "negative.li_hopping_distance_A": li_hop,
    }


def _num(v) -> float | None:
    if v is None:
        return None
    try:
        f = float(v)
    except (TypeError, ValueError):
        return None
    if f != f:  # NaN
        return None
    return f


# ---------------------------------------------------------------------------
# whole-canonical build
# ---------------------------------------------------------------------------


def build_negative_frame() -> pd.DataFrame:
    df = pd.read_parquet(CANONICAL)
    cols = [
        "negative.is_negative_result",
        "negative.reasons",
        "negative.evidence",
        "negative.confidence",
        "negative.energy_above_hull_eV_atom",
        "negative.is_metal",
        "negative.band_gap_eV",
        "negative.li_hopping_distance_A",
    ]
    for c in cols:
        df[c] = None
    for idx in df.index:
        row = df.loc[idx].to_dict()
        out = evaluate_row(row)
        for k, v in out.items():
            df.at[idx, k] = v
    # serialize evidence/reasons to JSON for parquet friendliness
    df["negative.reasons"] = df["negative.reasons"].apply(lambda r: list(r))
    df["negative.evidence"] = df["negative.evidence"].apply(
        lambda d: dict(d) if isinstance(d, dict) else {})
    return df


def summarize(df: pd.DataFrame) -> dict:
    neg = df["negative.is_negative_result"]
    by_source = {}
    for src, g in df.groupby("identity.source_db"):
        s = g["negative.is_negative_result"]
        s_bool = s.map({True: True, False: False}).where(s.notna(), False)
        by_source[str(src)] = {
            "records": int(len(g)),
            "negative": int(s_bool.sum()),
            "unknown": int(s.isna().sum()),
            "negative_share": (round(float(s_bool.mean()), 4)
                               if len(g) else None),
        }
    reason_counts: dict[str, int] = {}
    for r in df["negative.reasons"].dropna():
        for reason in r:
            reason_counts[reason] = reason_counts.get(reason, 0) + 1
    neg_bool = neg.map({True: True, False: False}).where(neg.notna(), False)
    flagged = df[neg_bool.astype(bool)]
    return {
        "canonical_records": int(len(df)),
        "negative_records": int(neg_bool.sum()),
        "unknown_records": int(neg.isna().sum()),
        "signal_counts": dict(sorted(reason_counts.items(),
                                     key=lambda kv: -kv[1])),
        "confidence_distribution": dict(
            flagged["negative.confidence"].value_counts().to_dict()
            if len(flagged) else {}),
        "by_source": by_source,
        "signals": {
            SIGNAL_UNSTABLE: ("energy_above_hull > "
                              f"{E_HULL_THRESHOLD_EV_ATOM} eV/atom (MP "
                              "stability convention)"),
            SIGNAL_ELECTRONIC: "is_metal True or band_gap == 0 (electronic short)",
            SIGNAL_POOR_TRANSPORT: (f"li_hopping_distance > "
                                    f"{LI_HOP_THRESHOLD_A} A (no percolation "
                                    "path; medium confidence proxy)"),
        },
        "convention": ("is_negative_result=None means no signal was "
                       "computable for this row (e.g. no MP structure); "
                       "never a fabricated False. is_negative_result=True "
                       "means at least one DFT negative signal fired."),
    }


def main() -> None:
    NEGATIVE_OUT.mkdir(exist_ok=True)
    df = build_negative_frame()
    df.to_parquet(NEGATIVE_OUT / "canonical_negative.parquet", index=False)
    report = summarize(df)
    (NEGATIVE_OUT / "negative_results_report.json").write_text(
        __import__("json").dumps(report, indent=2, default=str))
    print(__import__("json").dumps(
        {k: v for k, v in report.items() if k != "by_source"},
        indent=2, default=str))


if __name__ == "__main__":
    main()
