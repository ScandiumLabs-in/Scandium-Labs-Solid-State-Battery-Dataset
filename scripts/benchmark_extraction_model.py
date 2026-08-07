#!/usr/bin/env python3
"""Phase E6 — benchmark an extraction model against human-verified ground truth.

The extraction model choice is the dataset's core quality lever. Swap it only on
a measured accuracy delta, not on faith. This script:

  1. Collects the human-approved queue records that have an on-disk PDF (the
     ground-truth labels).
  2. Runs ``extract_from_pdf(pdf, llm_model=MODEL, ensemble_size=N)`` over a
     sample of those PDFs.
  3. Scores each extracted sigma/Ea against the approved value (unit-aware,
     tolerance mirroring the review engine: 35% sigma, ±0.05 eV Ea).
  4. ``--determinism N`` repeats extraction N times on the same PDF and reports
     record-count + value-assignment stability (the AGENTS.md 5-run test).

The purpose is a before/after number: run with the current model
(``--model llama-3.1-8b-instant``), then with ``--model llama-3.3-70b-versatile``,
and only switch the default if the bigger model wins on accuracy.

Usage:
    python scripts/benchmark_extraction_model.py --model llama-3.3-70b-versatile
    python scripts/benchmark_extraction_model.py --model llama-3.3-70b-versatile --ensemble 2
    python scripts/benchmark_extraction_model.py --model X --determinism 5 --pdf literature_output/pdfs/10.1021_jacs.1c07481.pdf
"""

from __future__ import annotations

import argparse
import json
import sys
import time
from collections import Counter
from pathlib import Path

from dotenv import load_dotenv

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

QUEUE = ROOT / "review_output" / "queue.json"
OUT = ROOT / "literature_output" / "extraction_model_benchmark.json"
PDF_DIR = ROOT / "literature_output" / "pdfs"


def load_ground_truth() -> list[dict]:
    """Approved queue records that have an on-disk PDF → ground-truth labels.

    Approved queue items store ``paper_id`` (an underscored DOI matching the
    staging PDF's filename stem, e.g. ``10.1038_s41467-022-35287-1``), not an
    explicit ``pdf_path``. Resolve the stem to the on-disk PDF so the accuracy
    benchmark has real labels to score against.
    """
    if not QUEUE.exists():
        return []
    q = json.loads(QUEUE.read_text())
    out = []
    for it in q.get("items", []):
        if it.get("status") != "approved":
            continue
        pdf = it.get("pdf_path") or (it.get("evidence") or {}).get("pdf")
        if not pdf:
            stem = it.get("paper_id")
            if stem:
                candidate = PDF_DIR / f"{stem}.pdf"
                if candidate.exists():
                    pdf = str(candidate)
        if pdf and Path(pdf).exists():
            out.append({**it, "pdf_path": str(pdf)})
    return out


def sigma_match(extracted: float, expected: float, unit_mult: float = 1.0) -> bool:
    """True when an extracted conductivity is within 35% of the expected value
    after the reported unit multiplier (S/cm vs mS/cm vs uS/cm)."""
    return abs(extracted - expected * unit_mult) <= abs(expected * unit_mult) * 0.35


def score_extraction(records: list, gt: list[dict]) -> dict:
    """Compare extracted records against the per-PDF ground-truth label list.

    ``gt`` entries are queue items with ``composition``/``value``/``unit``
    fields; matching is by reduced composition so a record's label is counted
    once even if extraction produced multiple entries for the same material.
    """
    n_sigma_expect = sum(1 for g in gt if g.get("property") in ("sigma", "conductivity"))
    n_ea_expect = sum(1 for g in gt if g.get("property") == "activation_energy")
    sigma_hits = ea_hits = 0
    by_composition: dict[str, int] = {}
    for rec in records:
        # MaterialRecord (schema) or a plain dict — extract composition both ways
        if hasattr(rec, "identity"):
            comp = rec.identity.composition or rec.identity.material_id or ""
        else:
            comp = rec.get("composition") or rec.get("material") or rec.get("material_id", "")
        # pull the canonical values off the record
        sig = getattr(rec, "sigma", None)
        if sig is None and hasattr(rec, "ion_transport"):
            sig = rec.ion_transport.sigma_RT
        ea = getattr(rec, "ea_eV", None)
        if ea is None and hasattr(rec, "ion_transport"):
            ea = rec.ion_transport.activation_energy_Ea
        key = comp if isinstance(comp, str) else str(comp)
        by_composition[key] = by_composition.get(key, 0) + 1
        if sig is not None and any(
            sigma_match(sig, g.get("value"), float(g.get("unit_multiplier", 1)))
            for g in gt
            if g.get("property") in ("sigma", "conductivity")
            and _same_material(key, g.get("composition"))
        ):
            sigma_hits += 1
        if ea is not None and any(
            abs(ea - g.get("value")) <= 0.05
            for g in gt
            if g.get("property") == "activation_energy"
            and _same_material(key, g.get("composition"))
        ):
            ea_hits += 1
    return {
        "sigma_expected": n_sigma_expect,
        "sigma_hits": sigma_hits,
        "sigma_accuracy": round(sigma_hits / n_sigma_expect, 3) if n_sigma_expect else None,
        "ea_expected": n_ea_expect,
        "ea_hits": ea_hits,
        "ea_accuracy": round(ea_hits / n_ea_expect, 3) if n_ea_expect else None,
        "records": len(records),
        "distinct_compositions": len(by_composition),
    }


def _same_material(a: str, b: str | None) -> bool:
    """Loose composition match (case-insensitive substring both ways) so slight
    formula-syntax differences between extraction and the verified label don't
    zero the score."""
    if not a or not b:
        return False
    a = a.replace(" ", "").lower()
    b = b.replace(" ", "").lower()
    return a == b or a in b or b in a


def main() -> int:
    # Load .env inside main() so importing the module for tests never pollutes
    # the process environment (dotenv sets HF_TOKEN/API keys globally).
    load_dotenv()
    ap = argparse.ArgumentParser(description="Extraction model benchmark")
    ap.add_argument("--model", default="llama-3.3-70b-versatile")
    ap.add_argument("--ensemble", type=int, default=2)
    ap.add_argument("--limit", type=int, default=3, help="max PDFs to extract")
    ap.add_argument("--determinism", type=int, default=0,
                    help="repeat a single PDF N times to measure stability")
    ap.add_argument("--pdf", type=str, default="")
    ap.add_argument("--persist", action="store_true")
    args = ap.parse_args()

    from ssb_dataset.literature.extraction import extract_from_pdf

    if args.determinism:
        pdf = Path(args.pdf or "")
        if not pdf.exists():
            print(f"PDF not found: {pdf}. Pass --pdf for the determinism test.")
            return 1
        counts = []
        assignments: Counter = Counter()
        for run in range(args.determinism):
            records = extract_from_pdf(pdf, llm_model=args.model,
                                       ensemble_size=args.ensemble, skip_grobid=True)
            counts.append(len(records))
            for r in records:
                comp = getattr(r, "composition", "")
                if not comp and hasattr(r, "identity"):
                    comp = r.identity.composition
                sig = getattr(r, "sigma", None)
                if sig is None and hasattr(r, "ion_transport"):
                    sig = r.ion_transport.sigma_RT
                assignments[(str(comp), sig)] += 1
            time.sleep(1)
        stable = (max(counts) - min(counts) == 0)
        print(f"determinism({args.determinism} runs, model={args.model}):")
        print(f"  record counts: {counts} → {'STABLE' if stable else 'UNSTABLE'}")
        if assignments:
            max_assign = assignments.most_common(1)[0]
            print(f"  most frequent (composition, sigma): {max_assign[0]} ×{max_assign[1]}/{args.determinism}")
        else:
            print("  no records assigned across runs (extraction returned empty)")
        if args.persist:
            OUT.write_text(json.dumps({
                "kind": "determinism",
                "model": args.model,
                "runs": counts,
                "stable": stable,
            }, indent=2))
        return 0

    gt = load_ground_truth()
    if not gt:
        print("No approved ground-truth records with on-disk PDFs found.")
        return 1
    by_pdf: dict[str, list[dict]] = {}
    for it in gt:
        by_pdf.setdefault(it["pdf_path"], []).append(it)

    pdfs = sorted(by_pdf, key=lambda p: -len(by_pdf[p]))[:args.limit]
    print(f"Benchmarking model '{args.model}' on {len(pdfs)} PDFs "
          f"({len(gt)} ground-truth labels), ensemble={args.ensemble}...")

    all_records: list = []
    results: dict[str, dict] = {}
    for pdf in pdfs:
        try:
            recs = extract_from_pdf(pdf, llm_model=args.model,
                                    ensemble_size=args.ensemble, skip_grobid=True)
        except Exception as e:
            print(f"  ✗ {Path(pdf).name}: extraction failed ({e})")
            continue
        all_records.extend(recs)
        sc = score_extraction(recs, by_pdf[pdf])
        results[Path(pdf).name] = sc
        print(f"  · {Path(pdf).name}: {sc['sigma_accuracy']} σ-acc, "
              f"{sc['ea_accuracy']} Ea-acc, {sc['records']} records")

    overall = {
        "kind": "accuracy",
        "model": args.model,
        "ensemble": args.ensemble,
        "pdfs": len(results),
        "per_pdf": results,
    }
    print(f"\nOverall for '{args.model}': {json.dumps(overall, default=str, indent=2)[:400]}")
    if args.persist:
        OUT.write_text(json.dumps(overall, indent=2, default=str))
        print(f"\nPersisted → {OUT}")
    return 0


if __name__ == "__main__":
    sys.exit(main())