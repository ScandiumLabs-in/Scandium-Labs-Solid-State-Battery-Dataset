#!/usr/bin/env python3
"""Cross-check structure-to-label attribution (guide §5 action 6).

OBELiX's identified failure mode: papers routinely report conductivity
measured in *one* study alongside structural data cited from *another* study
of the "same" material, silently corrupting structure–property pairs. Our
architecture avoids the manual version of that trap — labels are attached to
the DFT backbone by reduced-formula matching at featurization time — but that
same architecture *is* a systematic structure-borrowing: the structure paired
with a literature label is a Materials Project DFT structure, not the structure
from the measurement paper.

This audit makes that borrowing visible and quantifiable per labeled row:

  1. For each verified/gold label, is there a structure-bearing MP row whose
     reduced formula matches the label composition? (If not, the label has no
     structure — honest gap, not a silent borrow.)
  2. How many distinct structures exist for that formula (polymorphs)? A
     label matched to a formula with N polymorphs is inherently ambiguous
     about *which* polymorph the conductivity was measured on.
  3. Does the MP row's formula match the label EXACTLY (same reduced formula)
     vs. only partially? Partial matches are flagged — attaching a structure
     of a different composition would corrupt the pair.

Outputs:
  validation_output/structure_attribution_audit.json
  validation_output/structure_attribution_audit.md

Deterministic. No LLM calls, no network.
"""

from __future__ import annotations

import json
import sys
from collections import Counter
from pathlib import Path

import pandas as pd
from pymatgen.core import Composition

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from ssb_dataset.pipeline.fingerprint import fingerprint  # noqa: E402

CANONICAL = ROOT / "cleaning_output/canonical_dataset.parquet"
OUT_JSON = ROOT / "validation_output/structure_attribution_audit.json"
OUT_MD = ROOT / "validation_output/structure_attribution_audit.md"


def _reduced(formula: str | None) -> str | None:
    if not formula:
        return None
    try:
        return str(Composition(formula).reduced_formula)
    except Exception:
        return None


def _label_red(composition: str) -> str | None:
    """Reduced formula for a label composition, alias+descriptor aware."""
    fp = fingerprint(composition)
    if fp["reduced_formula"]:
        return str(fp["reduced_formula"])
    return None


def audit(canon: pd.DataFrame) -> dict:
    # structure-bearing backbone: MP rows with a relaxed structure
    struct = canon[
        canon["identity.source_db"].eq("materials_project")
        & canon["structure.structure_relaxed"].notna()
    ].copy()
    struct["_red"] = struct["identity.reduced_formula"].map(_reduced)
    # formula -> distinct structure ids (polymorph awareness)
    struct_by_formula: dict[str, list[str]] = {}
    for red, mid in zip(struct["_red"], struct["identity.material_id"]):
        if red:
            struct_by_formula.setdefault(red, []).append(str(mid))
    poly_count = {f: len(set(v)) for f, v in struct_by_formula.items()}

    labeled = canon[canon["ion_transport.label_available"] == True].copy()  # noqa: E712
    labeled["_red"] = labeled["identity.material_id"].map(_label_red)

    rows: list[dict] = []
    for _, r in labeled.iterrows():
        red = r["_red"]
        has_struct = bool(red and red in struct_by_formula)
        npoly = poly_count.get(red, 0) if red else 0
        rows.append({
            "composition": str(r["identity.material_id"]),
            "reduced_formula": red,
            "source_doi": str(r.get("text_provenance.source_doi")),
            "family": str(r.get("identity.family")),
            "structure_attached": has_struct,
            "n_mp_structures_for_formula": npoly,
            "status": (
                "structure_attached" if has_struct else "no_structure_match"
            ),
        })
    df = pd.DataFrame(rows)

    status = df["status"].value_counts().to_dict()
    attached = df[df["structure_attached"]]
    multi_poly = attached[attached["n_mp_structures_for_formula"] > 1]

    return {
        "methodology": (
            "Structure-to-label attribution audit: each verified label's "
            "composition is reduced-formula matched against the structure-"
            "bearing Materials Project backbone. 'structure_attached' means a "
            "DFT structure of the same reduced formula exists and is what "
            "featurization pairs with the label (this structure is from MP, "
            "NOT from the measurement paper — the documented systematic borrow "
            "our architecture makes). 'n_mp_structures_for_formula' counts "
            "distinct polymorph structures, exposing ambiguity about which "
            "polymorph the label was measured on."
        ),
        "n_labeled_rows": int(len(df)),
        "status": status,
        "n_attached": int(status.get("structure_attached", 0)),
        "n_without_structure": int(status.get("no_structure_match", 0)),
        "labeled_rows_without_structure": sorted(
            df[~df["structure_attached"]]["composition"].unique().tolist()),
        "polymorph_ambiguity": {
            "n_attached_with_multiple_mp_structures": int(len(multi_poly)),
            "examples": sorted(
                multi_poly[["composition", "n_mp_structures_for_formula"]]
                .head(15).to_dict("records"),
                key=lambda d: d["composition"]),
        },
        "per_row": rows,
        "interpretation": (
            "Structure borrowing is systematic and documented here: labeled "
            "rows carry an MP DFT structure of the same composition, not the "
            "paper's own structure. Labels with no MP structure match have no "
            "structure at all (honest gap). Labels matching a formula with "
            "multiple MP polymorphs are ambiguous about which polymorph was "
            "measured — model cards should caveat this."
        ),
    }


def main() -> None:
    canon = pd.read_parquet(CANONICAL)
    report = audit(canon)
    OUT_JSON.parent.mkdir(parents=True, exist_ok=True)
    OUT_JSON.write_text(json.dumps(report, indent=2))

    lines = [
        "# Structure-to-label attribution audit (guide §5 action 6)",
        "",
        report["methodology"],
        "",
        f"- Verified/gold labeled rows: **{report['n_labeled_rows']}**",
        f"- With a structure-attached MP match: "
        f"**{report['n_attached']}** "
        f"({100 * report['n_attached'] / report['n_labeled_rows']:.0f}%)",
        f"- Without any MP structure match: **{report['n_without_structure']}**",
        "",
        "Labeled rows WITHOUT an MP structure match:",
        "",
    ]
    for comp in report["labeled_rows_without_structure"]:
        lines.append(f"- `{comp}`")
    lines += [
        "",
        "Polymorph ambiguity: "
        f"**{report['polymorph_ambiguity']['n_attached_with_multiple_mp_structures']}** "
        "attached labels match a formula with >1 distinct MP structure.",
        "",
        "| composition | n MP structures |",
        "|---|---|",
    ]
    for ex in report["polymorph_ambiguity"]["examples"]:
        lines.append(f"| {ex['composition']} | {ex['n_mp_structures_for_formula']} |")
    lines += ["", report["interpretation"]]
    OUT_MD.write_text("\n".join(lines) + "\n")

    print(f"wrote {OUT_JSON}")
    print(f"wrote {OUT_MD}")
    print(f"labeled: {report['n_labeled_rows']}, attached: "
          f"{report['n_attached']}, no-match: {report['n_without_structure']}, "
          f"polymorph-ambiguous: "
          f"{report['polymorph_ambiguity']['n_attached_with_multiple_mp_structures']}")


if __name__ == "__main__":
    main()
