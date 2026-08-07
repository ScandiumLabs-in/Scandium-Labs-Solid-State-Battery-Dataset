#!/usr/bin/env python3
"""Compute + publish the experimental noise floor (guide §5 action 3).

OBELiX (Therrien et al. 2025) found 48 repeat-measurement groups (122 entries)
of identical composition + space group and used the spread within those groups
as a *benchmark floor*: a model scoring better than the measurement process
itself is almost certainly overfit. Their numbers: RMS deviation from group
means 0.63, MAD from group medians 0.41 (in log10 sigma).

We have a materially larger repeat-measurement tier — the cross-paper consensus
DB (427 materials). This script computes the same statistics from the
per-measurement records (sigma_S_per_cm) grouped by composition, and — where a
measurement reports bulk vs total — groups by (composition, conductivity_type)
so bulk and total conductivities (which differ physically by the grain-boundary
contribution) are never pooled into one noise estimate.

Outputs:
  validation_output/noise_floor_report.json   machine-readable
  validation_output/noise_floor_report.md     human-readable

Deterministic. No LLM calls, no network.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

CONSENSUS = ROOT / "literature_output/consensus_db.json"
OUT_JSON = ROOT / "validation_output/noise_floor_report.json"
OUT_MD = ROOT / "validation_output/noise_floor_report.md"


def _norm_type(raw) -> str | None:
    """Normalize a conductivity_type to bulk/grain_boundary/total/unknown."""
    if raw is None:
        return None
    s = str(raw).strip().lower()
    if s in ("conductivitytype.bulk", "bulk"):
        return "bulk"
    if s in ("conductivitytype.grain_boundary", "grain_boundary", "grain"):
        return "grain_boundary"
    if s in ("conductivitytype.total", "total"):
        return "total"
    return "unknown"


def _log10_sigmas(db: dict) -> list[tuple[str, float]]:
    """(group_key, log10 sigma) over all sigma-bearing measurements."""
    out: list[tuple[str, float]] = []
    for group, m in db.items():
        ctype = _norm_type(m.get("type") or None)
        for meas in m.get("measurements", []):
            sig = meas.get("sigma_S_per_cm")
            if sig is None or not np.isfinite(sig) or sig <= 0:
                continue
            t = _norm_type(meas.get("conductivity_type"))
            gkey = group if t is None else f"{group}::{t}"
            out.append((gkey, float(np.log10(sig))))
    return out


def _rms_vs_means(values: list[list[float]]) -> float:
    """RMS deviation of each value from its group's mean (log10)."""
    devs: list[float] = []
    for grp in values:
        mean = float(np.mean(grp))
        devs.extend([(v - mean) ** 2 for v in grp])
    return float(np.sqrt(np.mean(devs))) if devs else float("nan")


def _mad_vs_medians(values: list[list[float]]) -> float:
    """Mean absolute deviation of each value from its group's median (log10)."""
    devs: list[float] = []
    for grp in values:
        med = float(np.median(grp))
        devs.extend([abs(v - med) for v in grp])
    return float(np.mean(devs)) if devs else float("nan")


def compute(db: dict) -> dict:
    rows = _log10_sigmas(db)
    # group rows by gkey
    grouped: dict[str, list[float]] = {}
    for gkey, lg in rows:
        grouped.setdefault(gkey, []).append(lg)
    # only groups with >=2 measurements are usable repeat groups (OBELiX rule)
    repeat = {k: v for k, v in grouped.items() if len(v) >= 2}
    values = list(repeat.values())
    all_sigmas = [lg for _, lg in rows]

    report = {
        "methodology": (
            "OBELiX-style reproducibility floor: within each "
            "(composition[, conductivity-type]) group with >=2 independent "
            "sigma measurements, deviation of every value from its group "
            "mean/median in log10(sigma_S_per_cm)."
        ),
        "n_materials": len(db),
        "n_sigma_measurements": len(rows),
        "n_repeat_groups": len(repeat),
        "n_entries_in_repeat_groups": sum(len(v) for v in repeat.values()),
        "obeliX_comparison": {
            "obeliX_repeat_groups": 48,
            "obeliX_entries": 122,
            "obeliX_rms_log10": 0.63,
            "obeliX_mad_log10": 0.41,
        },
        "our_metrics": {
            "rms_deviation_from_group_means_log10": _rms_vs_means(values),
            "mad_from_group_medians_log10": _mad_vs_medians(values),
        },
        "global_spread": {
            "log10_sigma_min": float(np.min(all_sigmas)) if all_sigmas else None,
            "log10_sigma_max": float(np.max(all_sigmas)) if all_sigmas else None,
            "log10_sigma_std": float(np.std(all_sigmas)) if all_sigmas else None,
        },
        "interpretation": (
            "A model's test-set MAE in log10(sigma) below the noise-floor MAD "
            "is very likely overfit: it cannot be more accurate than the "
            "experimental measurement process itself."
        ),
        "groups": sorted(
            ({"group": k, "n": len(v),
              "log10_mean": float(np.mean(v)),
              "log10_median": float(np.median(v)),
              "spread_log10": float(np.ptp(v))} for k, v in repeat.items()),
            key=lambda g: -g["n"],
        ),
    }
    return report


def main() -> None:
    db = json.loads(CONSENSUS.read_text())
    report = compute(db)
    OUT_JSON.parent.mkdir(parents=True, exist_ok=True)
    OUT_JSON.write_text(json.dumps(report, indent=2))
    lines = [
        "# Experimental noise floor (guide §5 action 3)",
        "",
        report["methodology"],
        "",
        f"- Repeat-measurement groups: **{report['n_repeat_groups']}** "
        f"(across {report['n_materials']} materials, "
        f"{report['n_sigma_measurements']} sigma measurements; "
        f"{report['n_entries_in_repeat_groups']} entries inside repeat "
        f"groups).",
        "",
        f"- **RMS deviation from group means (log10 σ): "
        f"{report['our_metrics']['rms_deviation_from_group_means_log10']:.3f}**",
        f"- **MAD from group medians (log10 σ): "
        f"{report['our_metrics']['mad_from_group_medians_log10']:.3f}**",
        "",
        "OBELiX reference (48 groups / 122 entries): RMS 0.63, MAD 0.41.",
        "",
        "Interpretation:",
        report["interpretation"],
        "",
        "Largest repeat groups (spread = max−min in log10 σ):",
        "",
        "| group | n | log10 mean | spread |",
        "|---|---|---|---|",
    ]
    for g in report["groups"][:20]:
        lines.append(f"| {g['group']} | {g['n']} | "
                     f"{g['log10_mean']:.3f} | {g['spread_log10']:.3f} |")
    OUT_MD.write_text("\n".join(lines) + "\n")
    print(f"wrote {OUT_JSON}")
    print(f"wrote {OUT_MD}")
    print(f"repeat groups: {report['n_repeat_groups']}, "
          f"rms={report['our_metrics']['rms_deviation_from_group_means_log10']:.3f}, "
          f"mad={report['our_metrics']['mad_from_group_medians_log10']:.3f}")


if __name__ == "__main__":
    main()
