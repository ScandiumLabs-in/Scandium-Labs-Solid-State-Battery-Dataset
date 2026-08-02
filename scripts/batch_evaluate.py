"""Week 7: Batch full pipeline evaluation across all PDFs."""

import json
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from scandium.pipeline import run_pipeline

PDF_DIR = Path("literature_output/pdfs")
OUTPUT_DIR = Path("scandium_output/batch_eval")
OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

BATCH_RESULTS = OUTPUT_DIR / "batch_results.json"


def main():
    all_pdfs = sorted(PDF_DIR.glob("*.pdf"))
    print(f"Pipeline batch evaluation: {len(all_pdfs)} PDFs\n")

    # Load existing progress if any
    results: list[dict] = []
    if BATCH_RESULTS.exists():
        with open(BATCH_RESULTS) as f:
            results = json.load(f)
        done_ids = {r["pdf_id"] for r in results}
    else:
        done_ids = set()

    for pdf in all_pdfs:
        pdf_id = pdf.stem
        if pdf_id in done_ids:
            print(f"  {pdf.stem}: already done, skipping")
            continue

        print(f"\n{'='*70}")
        print(f"PROCESSING: {pdf.name}")
        print(f"{'='*70}")

        try:
            t0 = time.time()
            paper_out = run_pipeline(str(pdf))
            elapsed = round(time.time() - t0, 1)

            v = paper_out.get("verification", {}).get("summary", {})
            ev = paper_out.get("evidence", [])
            dr = paper_out.get("dataset_record", {})

            summary = {
                "pdf_id": pdf_id,
                "status": "done",
                "doi": paper_out.get("doi"),
                "primary_composition": paper_out.get("primary_composition"),
                "n_high_conf_cond": v.get("high_confidence_conductivities", 0),
                "n_flagged_cond": v.get("flagged_conductivities", 0),
                "n_high_conf_ea": v.get("high_confidence_activation_energies", 0),
                "n_flagged_ea": v.get("flagged_activation_energies", 0),
                "n_conflicts": v.get("total_conflicts", 0),
                "n_evidence": len(ev),
                "n_high_confidence_evidence": dr.get("n_high_confidence", 0),
                "n_flagged_evidence": dr.get("n_flagged", 0),
                "n_chunks": paper_out.get("n_chunks", 0),
                "n_sections": paper_out.get("n_sections", 0),
                "elapsed_s": elapsed,
            }
            results.append(summary)

            # Print result summary
            print(f"\n>>> DONE: {pdf.stem}")
            print(f"    Composition: {summary['primary_composition']}")
            print(f"    σ: {summary['n_high_conf_cond']} high, {summary['n_flagged_cond']} flagged")
            print(f"    Ea: {summary['n_high_conf_ea']} high, {summary['n_flagged_ea']} flagged")
            print(f"    Conflicts: {summary['n_conflicts']}")
            print(f"    Evidence: {summary['n_evidence']} ({summary['n_high_confidence_evidence']} high)")
            print(f"    Time: {elapsed}s")

        except Exception as e:
            import traceback
            traceback.print_exc()
            print(f"\n>>> ERROR: {pdf.stem}: {e}")
            results.append({"pdf_id": pdf_id, "status": "error", "error": str(e)})

        # Save incremental progress
        with open(BATCH_RESULTS, "w") as f:
            json.dump(results, f, indent=2)

    # Final summary
    done = [r for r in results if r.get("status") == "done"]
    errors = [r for r in results if r.get("status") == "error"]

    print(f"\n{'='*70}")
    print(f"BATCH EVALUATION COMPLETE")
    print(f"{'='*70}")
    print(f"  Total: {len(all_pdfs)}")
    print(f"  Done:  {len(done)}")
    print(f"  Errors:{len(errors)}")
    print(f"\nPer-paper results:")
    print(f"  {'PDF':35s} {'Composition':20s} {'σ_high':>6} {'σ_flag':>6} {'Ea_high':>6} {'Ea_flag':>6} {'Conf':>5} {'Evid':>5} {'Time':>6}")
    print(f"  {'-'*35} {'-'*20} {'-'*6} {'-'*6} {'-'*6} {'-'*6} {'-'*5} {'-'*5} {'-'*6}")
    total_high = 0
    total_flagged = 0
    for r in done:
        total_high += r["n_high_confidence_evidence"]
        total_flagged += r["n_flagged_evidence"]
        print(f"  {r['pdf_id'][:34]:35s} {(r['primary_composition'] or '?')[:20]:20s} "
              f"{r['n_high_conf_cond']:6d} {r['n_flagged_cond']:6d} "
              f"{r['n_high_conf_ea']:6d} {r['n_flagged_ea']:6d} "
              f"{r['n_conflicts']:5d} {r['n_evidence']:5d} {r['elapsed_s']:5.1f}s")
    for r in errors:
        print(f"  {r['pdf_id'][:34]:35s} {'ERROR':20s} {r.get('error','')[:50]}")

    print(f"\nTotals: {total_high} high-confidence evidence, {total_flagged} flagged")
    print(f"Results: {BATCH_RESULTS}")


if __name__ == "__main__":
    main()
