"""Build Material Cards for every material in the consensus database.

Reads:
  - literature_output/consensus_db.json   (consensus aggregates + measurements)
  - cleaning_output/canonical_dataset.parquet (Materials Project structure data)

Writes:
  - literature_output/material_cards.json        (all cards, machine-readable)
  - literature_output/material_cards.md          (index + all cards, readable)

Usage:
    python scripts/build_material_cards.py
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent


def load_structure_lookup() -> dict[str, dict]:
    """Composition group -> best Materials Project structure metadata."""
    import pandas as pd

    cp = ROOT / "cleaning_output/canonical_dataset.parquet"
    if not cp.exists():
        return {}
    df = pd.read_parquet(cp)
    comp_col = "identity.composition"
    if comp_col not in df.columns:
        return {}
    from ssb_dataset.pipeline.fingerprint import group_key

    best: dict[str, dict] = {}
    for _, row in df.iterrows():
        comp = row.get(comp_col) or ""
        if not comp:
            continue
        g = group_key(str(comp))
        if not g:
            continue
        entry = {
            "space_group": row.get("structure.space_group"),
            "space_group_number": row.get("structure.space_group_number"),
            "crystal_system": row.get("structure.crystal_system"),
            "band_gap": row.get("thermodynamics.band_gap"),
            "formation_energy_per_atom": row.get("thermodynamics.formation_energy_per_atom"),
            "is_stable": row.get("thermodynamics.is_stable"),
        }
        # keep the first (and most complete) structure seen for each group
        if g not in best:
            best[g] = entry
    return best


def _temp_str(m: dict) -> str:
    t = m.get("temperature_celsius")
    if isinstance(t, (int, float)):
        return f", {t:.0f} °C"
    if isinstance(t, dict):
        lo = t.get("min_K") or t.get("min_C") or t.get("min")
        hi = t.get("max_K") or t.get("max_C") or t.get("max")
        if lo is not None and hi is not None:
            try:
                return f", {float(lo):.0f}–{float(hi):.0f} K"
            except (TypeError, ValueError):
                pass
    return ""


def card_to_markdown(card: dict, score: int, verdict: str) -> str:
    lines = []
    lines.append(f"## {card['material']}")
    lines.append("")
    lines.append(f"- **Family:** {card['family']}")
    lines.append(f"- **Papers:** {card['n_papers']} | **Measurements:** {card['n_measurements']} "
                 f"({card['n_sigma']} σ, {card['n_ea']} Ea)")
    if card["median_sigma"] is not None:
        ci = ""
        if card["sigma_ci95"]:
            lo, hi = card["sigma_ci95"]
            ci = f" (95% CI {lo:.2e}–{hi:.2e})"
        lines.append(f"- **Median σ:** {card['median_sigma']:.2e} S/cm{ci} "
                     f"[{card['min_sigma']:.2e}–{card['max_sigma']:.2e}]")
        unc = []
        if card.get("sigma_mad_log10") is not None:
            unc.append(f"MAD {card['sigma_mad_log10']:.2f} log10")
        if card.get("sigma_std_log10") is not None:
            unc.append(f"std {card['sigma_std_log10']:.2f} log10")
        if card.get("sigma_iqr_log10") is not None:
            unc.append(f"IQR {card['sigma_iqr_log10']:.2f} log10")
        grade = f" — agreement **{card['agreement_grade']}**" if card.get("agreement_grade") else ""
        if unc:
            lines.append(f"- **Uncertainty:** {', '.join(unc)}{grade}")
        elif grade:
            lines.append(f"- **Agreement grade:** {card['agreement_grade']}")
    if card["median_ea"] is not None:
        lines.append(f"- **Median Ea:** {card['median_ea']:.3f} eV")
    if card["temperature_range_c"]:
        lo, hi = card["temperature_range_c"]
        lines.append(f"- **Temperature range:** {lo:.0f}–{hi:.0f} °C "
                     f"({card['temperature_counts']} measurements)")
    if card.get("sigma_by_temp"):
        tlines = "; ".join(
            f"{b['temp_c']}°C: n={b['n']}, median {b['median_sigma']:.1e} S/cm"
            f" [{b['min_sigma']:.1e}–{b['max_sigma']:.1e}]"
            for b in card["sigma_by_temp"]
        )
        lines.append(f"- **σ vs temperature:** {tlines}")
    lines.append(f"- **Consensus score:** {score}/100 — **{verdict}**")
    lines.append(f"- **Quality score:** {card.get('quality_score', '—')}/100 "
                 f"({card.get('quality_grade', '—')}) — metadata completeness "
                 f"{card.get('metadata_completeness', 0)*100:.0f}% (temp+method)")
    if card["outliers"]:
        lines.append(f"- **Outliers ({len(card['outliers'])}):**")
        for o in card["outliers"]:
            lines.append(f"    - σ={o.get('sigma')} ({o.get('note', '')})")
    if card["structure"]:
        s = card["structure"]
        lines.append("- **Structure (MP):**")
        if s.get("space_group"):
            lines.append(f"    - Space group: {s['space_group']} "
                         f"(#{s.get('space_group_number')}, {s.get('crystal_system')})")
        if s.get("band_gap") is not None:
            lines.append(f"    - Band gap: {s['band_gap']:.3f} eV")
        if s.get("formation_energy_per_atom") is not None:
            lines.append(f"    - Formation energy: {s['formation_energy_per_atom']:.3f} eV/atom")
        if s.get("is_stable") is not None:
            lines.append(f"    - Stable: {s['is_stable']}")
    if card["dois"]:
        lines.append("- **DOIs:** " + ", ".join(card["dois"]))
    lines.append("")
    lines.append("### Papers")
    lines.append("")
    if not card["papers"]:
        lines.append("_No measurement-level detail preserved._")
        lines.append("")
        return "\n".join(lines)
    for p in card["papers"]:
        lines.append(f"- **{p['doi']}** ({p['n_sigma']} σ, {p['n_ea']} Ea)")
        for m in p["measurements"]:
            t = _temp_str(m)
            meth = f", {m['measurement_method']}" if m.get("measurement_method") else ""
            page = f" p.{m['page']}" if m.get("page") else ""
            lines.append(f"    - {m['property']}: {m['value']} {m['unit']}{t}{meth}{page}")
            if m.get("evidence_sentence"):
                lines.append(f"      > {m['evidence_sentence']}")
    lines.append("")
    return "\n".join(lines)


def main() -> int:
    cons_path = ROOT / "literature_output/consensus_db.json"
    if not cons_path.exists():
        print(f"consensus db not found: {cons_path}. Run scripts/build_consensus_db.py first.")
        return 1

    consensus_db = json.loads(cons_path.read_text())
    structure_lookup = load_structure_lookup()

    from ssb_dataset.literature.material_cards import build_all_cards

    cards = build_all_cards(consensus_db, structure_lookup)

    out_dict = {g: c.to_dict() for g, c in cards.items()}
    out_path = ROOT / "literature_output/material_cards.json"
    out_path.write_text(json.dumps(out_dict, indent=2, default=str))

    # Markdown: index + one section per card, strongest consensus first.
    ordered = sorted(cards.values(), key=lambda c: c.consensus_score, reverse=True)
    md = ["# Scandium Material Cards", ""]
    md.append(f"Generated from `literature_output/consensus_db.json`. "
              f"**{len(cards)} materials**, "
              f"**{sum(c.n_measurements for c in cards.values())} measurements** "
              f"({sum(c.n_sigma for c in cards.values())} σ, "
              f"{sum(c.n_ea for c in cards.values())} Ea).")
    md.append("")
    md.append("## Index (by consensus score)")
    md.append("")
    md.append("| Material | Family | Papers | Measurements | Median σ (S/cm) | Median Ea (eV) | Agreement | Score | Quality |")
    md.append("|---|---|---|---|---|---|---|---|---|")
    for c in ordered:
        sig = f"{c.median_sigma:.1e}" if c.median_sigma is not None else "—"
        ea = f"{c.median_ea:.2f}" if c.median_ea is not None else "—"
        grade = c.agreement_grade or "—"
        q = f"{c.quality_score} ({c.quality_grade})" if getattr(c, "quality_score", 0) else "—"
        md.append(f"| {c.material} | {c.family} | {c.n_papers} | {c.n_measurements} | {sig} | {ea} | "
                  f"{grade} | **{c.consensus_score}** ({c.consensus_verdict}) | {q} |")
    md.append("")
    for c in ordered:
        md.append(card_to_markdown(c.to_dict(), c.consensus_score, c.consensus_verdict))

    md_path = ROOT / "literature_output/material_cards.md"
    md_path.write_text("\n".join(md))

    n_with_detail = sum(1 for c in cards.values() if c.papers)
    print(f"wrote {out_path}")
    print(f"wrote {md_path}")
    print(f"{len(cards)} materials, {sum(c.n_measurements for c in cards.values())} measurements "
          f"({sum(c.n_sigma for c in cards.values())} σ, {sum(c.n_ea for c in cards.values())} Ea); "
          f"{n_with_detail} materials with measurement-level detail")
    print(f"top consensus: {ordered[0].material} ({ordered[0].consensus_score}/100) "
          f"… {ordered[-1].material} ({ordered[-1].consensus_score}/100)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
