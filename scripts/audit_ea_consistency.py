#!/usr/bin/env python3
"""Activation-energy field consistency audit (guide §5 action 9).

LiIon dropped activation energy as a tracked field once they found it wasn't
reported consistently enough across sources to be useful. Before making that
call for this dataset, quantify *how* consistent the Ea field actually is:

  - Coverage: how many labeled rows carry Ea vs sigma?
  - Cross-paper reproducibility: for materials with Ea in >1 paper, how tight
    is the spread (MAD in eV)? A wide spread with few pairs means the field is
    noisy; tight agreement means it is usable.
  - Unit provenance: any rows with implausible Ea (outside the physical window
    0.01–5.0 eV) that would indicate unit-conversion errors (kJ/mol misread as
    eV etc.)?
  - Companion sigma-Ea pairing: how often does a row carry BOTH sigma and Ea
    (needed for Arrhenius prediction)?

Outputs:
  validation_output/ea_consistency_audit.json
  validation_output/ea_consistency_audit.md

Deterministic. No LLM calls, no network.
"""

from __future__ import annotations

import json
import sys
from collections import defaultdict
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

CANONICAL = ROOT / "cleaning_output/canonical_dataset.parquet"
OUT_JSON = ROOT / "validation_output/ea_consistency_audit.json"
OUT_MD = ROOT / "validation_output/ea_consistency_audit.md"

EA = "ion_transport.activation_energy_Ea"
SIGMA = "ion_transport.sigma_RT"
LABEL = "ion_transport.label_available"
DOI = "text_provenance.source_doi"

# physical window for Ea (eV)
EA_MIN, EA_MAX = 0.01, 5.0


def _median_mad(values: list[float]) -> tuple[float, float]:
    if not values:
        return float("nan"), float("nan")
    arr = np.array(values)
    med = float(np.median(arr))
    mad = float(np.mean(np.abs(arr - med)))
    return med, mad


def audit(canon: pd.DataFrame) -> dict:
    lab = canon[canon[LABEL] == True].copy()  # noqa: E712
    n = len(lab)
    n_ea = int(lab[EA].notna().sum())
    n_sigma = int(lab[SIGMA].notna().sum())
    n_both = int((lab[EA].notna() & lab[SIGMA].notna()).sum())

    # physical-window / unit-suspicion check
    ea_vals = lab.loc[lab[EA].notna(), EA].astype(float)
    out_of_window = ea_vals[(ea_vals < EA_MIN) | (ea_vals > EA_MAX)]

    # cross-paper reproducibility: materials with Ea in >=2 distinct papers
    ea_by_paper: dict[str, list[tuple[str, float]]] = defaultdict(list)
    for _, r in lab.iterrows():
        if pd.notna(r[EA]):
            ea_by_paper[str(r["identity.material_id"])].append(
                (str(r[DOI] or ""), float(r[EA])))
    multi_paper: dict[str, dict] = {}
    for comp, pairs in ea_by_paper.items():
        dois = {d for d, _ in pairs}
        if len(dois) >= 2:
            vals = [v for _, v in pairs]
            med, mad = _median_mad(vals)
            multi_paper[comp] = {
                "n_papers": len(dois),
                "n_values": len(vals),
                "median_ea_eV": round(med, 4),
                "mad_eV": round(mad, 4),
                "min_eV": round(min(vals), 4),
                "max_eV": round(max(vals), 4),
                "dois": sorted(dois),
            }
    # materials where cross-paper Ea spread exceeds 0.2 eV (inconsistent)
    inconsistent = {
        k: v for k, v in multi_paper.items() if v["mad_eV"] > 0.2
    }

    return {
        "methodology": (
            "Ea consistency audit over the verified-labeled rows. Cross-paper "
            "reproducibility = MAD of Ea across distinct source papers for a "
            "material. A field whose cross-paper spread is wide (MAD > 0.2 eV) "
            "on many materials is not reliably comparable across sources — the "
            "signal LiIon used to justify dropping activation energy."
        ),
        "coverage": {
            "n_labeled_rows": n,
            "n_with_ea": n_ea,
            "ea_coverage_pct": round(100 * n_ea / n, 1) if n else None,
            "n_with_sigma": n_sigma,
            "n_with_both_sigma_and_ea": n_both,
            "both_pct": round(100 * n_both / n, 1) if n else None,
        },
        "unit_suspicion": {
            "n_out_of_physical_window": int(len(out_of_window)),
            "out_of_window_values": sorted(
                round(float(v), 3) for v in out_of_window),
            "window_eV": [EA_MIN, EA_MAX],
        },
        "cross_paper_reproducibility": {
            "n_materials_ea_from_ge2_papers": len(multi_paper),
            "n_materials_inconsistent_mad_gt_0.2eV": len(inconsistent),
            "inconsistent_examples": {
                k: {"mad_eV": v["mad_eV"], "n_papers": v["n_papers"]}
                for k, v in sorted(
                    inconsistent.items(), key=lambda kv: -kv[1]["mad_eV"]
                )[:15]
            },
            "per_material": multi_paper,
        },
        "verdict": (
            "Recommendation: keep the field with a documented confidence "
            "signal rather than dropping it, IF cross-paper MAD is small for "
            "the well-measured materials. If >50% of multi-paper materials "
            "have MAD > 0.2 eV, the field is LiIon-inconsistent and should "
            "be demoted to a secondary/caveated field."
        ),
    }


def main() -> None:
    canon = pd.read_parquet(CANONICAL)
    report = audit(canon)
    OUT_JSON.parent.mkdir(parents=True, exist_ok=True)
    OUT_JSON.write_text(json.dumps(report, indent=2))

    cov = report["coverage"]
    xp = report["cross_paper_reproducibility"]
    lines = [
        "# Activation-energy field consistency audit (guide §5 action 9)",
        "",
        report["methodology"],
        "",
        "## Coverage",
        "",
        f"- Labeled rows: **{cov['n_labeled_rows']}**",
        f"- With Ea: **{cov['n_with_ea']}** ({cov['ea_coverage_pct']}%)",
        f"- With sigma: **{cov['n_with_sigma']}**",
        f"- With BOTH sigma and Ea (Arrhenius-predictable): "
        f"**{cov['n_with_both_sigma_and_ea']}** ({cov['both_pct']}%)",
        "",
        "## Unit-suspicion check (physical window "
        f"{report['unit_suspicion']['window_eV'][0]}–"
        f"{report['unit_suspicion']['window_eV'][1]} eV)",
        "",
        f"- Out-of-window values: "
        f"**{report['unit_suspicion']['n_out_of_physical_window']}** "
        f"{report['unit_suspicion']['out_of_window_values']}",
        "",
        "## Cross-paper reproducibility",
        "",
        f"- Materials with Ea from ≥2 papers: "
        f"**{xp['n_materials_ea_from_ge2_papers']}**",
        f"- Materials with inconsistent cross-paper Ea (MAD > 0.2 eV): "
        f"**{xp['n_materials_inconsistent_mad_gt_0.2eV']}**",
        "",
    ]
    if xp["inconsistent_examples"]:
        lines += ["Most-inconsistent materials:", "", "| material | MAD (eV) | n papers |", "|---|---|---|"]
        for k, v in xp["inconsistent_examples"].items():
            lines.append(f"| {k} | {v['mad_eV']} | {v['n_papers']} |")
        lines.append("")
    lines += ["", report["verdict"]]
    OUT_MD.write_text("\n".join(lines) + "\n")

    print(f"wrote {OUT_JSON}")
    print(f"wrote {OUT_MD}")
    print(f"Ea coverage: {cov['n_with_ea']}/{cov['n_labeled_rows']} "
          f"({cov['ea_coverage_pct']}%), both σ+Ea: {cov['n_with_both_sigma_and_ea']}, "
          f"multi-paper Ea materials: {xp['n_materials_ea_from_ge2_papers']}, "
          f"inconsistent: {xp['n_materials_inconsistent_mad_gt_0.2eV']}")


if __name__ == "__main__":
    main()
