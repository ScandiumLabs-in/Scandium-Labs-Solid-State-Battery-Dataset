"""Phase 2.2 — backfill rich experiment conditions onto verified records.

Reads the durable `verified_canonical.parquet`, maps each verified record's
source DOI to its on-disk PDF, runs the deterministic ``experiment_extract``
scanner, and stamps the resulting experiment conditions onto the record.

Deterministic and conservative: only clearly-labeled values are captured;
nothing is LLM-guessed. Supports ``--dry-run`` (report only) and ``--apply``
(write back to verified_canonical.parquet + re-run merge to refresh canonical).

Usage:
    python scripts/backfill_experiment_metadata.py            # dry-run report
    python scripts/backfill_experiment_metadata.py --apply    # stamp + merge
    python scripts/backfill_experiment_metadata.py --out rep.md
"""

from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parent.parent
VERIFIED = ROOT / "cleaning_output" / "verified_canonical.parquet"
PDF_DIR = ROOT / "literature_output" / "pdfs"
CANONICAL = ROOT / "cleaning_output" / "canonical_dataset.parquet"

sys.path.insert(0, str(ROOT))
from src.ssb_dataset.pipeline.experiment_extract import (  # noqa: E402
    ExtractResult, extract_conditions,
)

# fields the extractor produces → canonical experiment block keys
FIELD_MAP = {
    "sample_form": "sample_form",
    "pellet_diameter_mm": "pellet_diameter_mm",
    "thickness_mm": "thickness_mm",
    "relative_density_pct": "relative_density_pct",
    "pelletizing_pressure_MPa": "pelletizing_pressure_MPa",
    "electrode_material": "electrode_material",
    "electrode_deposition": "electrode_deposition",
    "frequency_min_Hz": "frequency_min_Hz",
    "frequency_max_Hz": "frequency_max_Hz",
    "atmosphere": "atmosphere",
    "sinter_temperature_C": "sinter_temperature_C",
    "sinter_time_h": "sinter_time_h",
    "annealing_temperature_C": "annealing_temperature_C",
    "annealing_time_h": "annealing_time_h",
    "instrument": "instrument",
    "dc_bias_V": "dc_bias_V",
    "equivalent_circuit": "equivalent_circuit",
    "humidity": "humidity",
}


def result_to_dict(r: ExtractResult) -> dict:
    d = {}
    for src_key, dst_key in FIELD_MAP.items():
        v = getattr(r, src_key)
        if v is not None:
            d[dst_key] = v
    return d


def find_pdf(doi: str | None) -> Path | None:
    if not doi:
        return None
    name = doi.replace("/", "_") + ".pdf"
    p = PDF_DIR / name
    return p if p.exists() else None


def _render_report(out: list) -> str:
    """Render the extracted conditions as a human-readable markdown report."""
    n_pdf = sum(1 for r in out if r["pdf"])
    n_cond = sum(1 for r in out if r["conditions"])
    n_susp = sum(1 for r in out if r.get("suspicious"))
    fields = {}
    for r in out:
        for k, v in r["conditions"].items():
            fields[k] = fields.get(k, 0) + 1
    lines = [
        "# Experiment-metadata backfill report (Phase 2.2)",
        "",
        "Deterministic extraction from each verified record's source PDF. "
        "Review the values below; then run `--apply` to stamp the `experiment` block.",
        "",
        f"**{len(out)} records | {n_pdf} with on-disk PDF | "
        f"{n_cond} with ≥1 condition extracted | {n_susp} with suspicious-flag**",
        "",
        "**Field coverage (count of records):**",
        "",
    ]
    for k in sorted(fields, key=lambda k: -fields[k]):
        lines.append(f"- {k}: {fields[k]}")
    lines.append("")
    # skeleton summary table
    lines += [
        "## Coverage summary",
        "",
        "| Metric | Value |",
        "|---|---|",
        f"| verified records read | {len(out)} |",
        f"| on-disk PDF matched | {n_pdf} |",
        f"| ≥1 condition extracted | {n_cond} |",
        f"| suspicious-value flags | {n_susp} |",
        "",
    ]
    for rec in out:
        lines.append(f"## {rec['material']}")
        lines.append(f"`{rec['doi']}` — `{rec['pdf']}`")
        c = rec["conditions"]
        if not c:
            lines.append("_no conditions extracted_")
        else:
            for k, v in c.items():
                lines.append(f"- **{k}**: {v}")
        if rec.get("suspicious"):
            lines.append("")
            lines.append("⚠️ *Suspicious (verify against paper):*")
            for s in rec["suspicious"]:
                lines.append(f"  - {s}")
        lines.append("")
    return "\n".join(lines)


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--apply", action="store_true", help="write back into verified_canonical.parquet")
    ap.add_argument("--out", default=None)
    args = ap.parse_args()

    df = pd.read_parquet(VERIFIED)
    out = []
    n_pdf = 0
    n_found = 0
    conditions_by_doi: dict[str, dict] = {}

    dotted_doi = "text_provenance.source_doi" in df.columns
    dotted_comp = "identity.material_id" in df.columns

    def row_doi(row):
        if dotted_doi:
            v = row.get("text_provenance.source_doi")
            if v:
                return v
        tp = row.get("text_provenance")
        if isinstance(tp, dict):
            return tp.get("source_doi")
        return None

    def row_comp(row):
        if dotted_comp:
            v = row.get("identity.material_id")
            if v:
                return v
        ident = row.get("identity")
        if isinstance(ident, dict):
            return ident.get("composition") or ident.get("material_id")
        return row.get("identity.composition")

    for i, row in df.iterrows():
        doi = row_doi(row)
        comp = row_comp(row)
        pdf = find_pdf(doi)
        rec = {
            "material": comp,
            "doi": doi,
            "pdf": os.path.basename(pdf) if pdf else None,
            "conditions": {},
        }
        if not pdf:
            out.append(rec)
            continue
        n_pdf += 1
        r = extract_conditions(pdf)
        cond = result_to_dict(r)
        rec["conditions"] = cond
        rec["suspicious"] = list(r.suspicious)
        if cond:
            n_found += 1
        conditions_by_doi[doi] = cond
        out.append(rec)

    if args.out:
        Path(args.out).write_text(
            json.dumps({"records": out}, indent=2, default=str))
        report = _render_report(out)
        Path(args.out).with_suffix(".md").write_text(report)
    else:
        for rec in out:
            c = rec["conditions"]
            status = "OK " if c else "---"
            print(f"{status} {str(rec['material'])[:38]:<38} {str(rec['doi'] or '')[:32]:<32} {c or 'no conditions'}")
        print(f"\nrows={len(df)} with_pdf={n_pdf} with_conditions={n_found}")

    if args.apply:
        # dedupe per-conditions (overwrite the earlier non-FIELD_MAP version)
        return _apply(df, out, conditions_by_doi)

    return 0


def _drop_suspicious(rec: dict) -> dict:
    """Return conditions with any field flagged in ``rec['suspicious']`` removed.

    Suspicious messages encode the offending field as ``<field>=...``; we drop
    that field for this record rather than stamping an unverified value.
    """
    flagged = set()
    for s in rec.get("suspicious", []):
        field = s.split("=", 1)[0].strip()
        if field:
            flagged.add(field)
    if not flagged:
        return dict(rec["conditions"])
    return {k: v for k, v in rec["conditions"].items() if k not in flagged}


def _apply(df, out, conditions_by_doi) -> int:
    ROOT = Path(__file__).resolve().parent.parent
    dotted_doi = "text_provenance.source_doi" in df.columns
    exp_col = {}
    # map doi → experiment dict (merge non-suspicious fields across the DOI's
    # records; drop fields flagged suspicious on any one of them)
    for rec in out:
        doi = rec["doi"]
        if not doi or not rec["conditions"]:
            continue
        clean = _drop_suspicious(rec)
        merged = exp_col.get(doi, {})
        for k, v in clean.items():
            merged[k] = v  # same material+paper → consistent
        exp_col[doi] = merged
    def exp_for(row):
        if dotted_doi:
            doi = row.get("text_provenance.source_doi")
            if doi in exp_col:
                return exp_col[doi]
        tp = row.get("text_provenance")
        if isinstance(tp, dict):
            doi = tp.get("source_doi")
            if doi in exp_col:
                return exp_col[doi]
        return {}
    # build experiment column as JSON-encoded string column
    df["experiment"] = df.apply(exp_for, axis=1)
    df.to_parquet(VERIFIED, index=False)
    # re-run canonical merge
    subprocess.run([sys.executable, str(ROOT / "scripts" / "merge_verified.py")], check=True)
    print(f"\nWrote experiment block for {len(exp_col)} distinct DOIs; canonical re-merged.")
    return 0


if __name__ == "__main__":
    import os  # noqa: E402
    import os as _os
    sys.exit(main())