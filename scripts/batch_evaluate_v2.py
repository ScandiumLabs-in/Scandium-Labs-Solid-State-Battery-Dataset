"""Full batch re-evaluation with new architecture."""

import json
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from scandium.pipeline import run_pipeline

PDF_DIR = Path("literature_output/pdfs")
OUTPUT_DIR = Path("scandium_output/batch_eval_v2")
OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

# Papers to evaluate (skip known non-PDFs)
PDFS = [
    "10.1038_s41467-022-35287-1.pdf",
    "10.1038_s41467-023-40669-0.pdf",
    "10.1038_s41467-023-42385-1.pdf",
    "10.1038_s41467-024-51191-2.pdf",
    "10.1038_s43246-024-00550-z.pdf",
    "antiperovskite_nature.pdf",
    "nasicon_mdpi.pdf",
    "sulfide_argyrodite.pdf",
    "sulfide_preprint.pdf",
    "garnet_electrochem.pdf",
]

results = []
for fname in PDFS:
    pdf_path = PDF_DIR / fname
    if not pdf_path.exists():
        print(f"\n*** SKIP (not found): {fname}")
        continue

    print(f"\n{'='*70}")
    print(f"PROCESSING: {fname}")
    print(f"{'='*70}")

    try:
        t0 = time.time()
        paper_out = run_pipeline(str(pdf_path))
        elapsed = round(time.time() - t0, 1)

        pm = paper_out.get("primary_material_detector", {})
        ev = paper_out.get("evidence", [])
        dr = paper_out.get("dataset_record", {})

        summary = {
            "pdf_id": pdf_path.stem,
            "status": "done",
            "primary_material": pm.get("primary_material", ""),
            "primary_confidence": pm.get("confidence", 0),
            "n_high_cond": len(paper_out["conductivities"]["high_confidence"]),
            "n_flagged_cond": len(paper_out["conductivities"]["flagged"]),
            "n_high_ea": len(paper_out["activation_energies"]["high_confidence"]),
            "n_flagged_ea": len(paper_out["activation_energies"]["flagged"]),
            "n_evidence": len(ev),
            "n_high_evidence": dr.get("n_high_confidence", 0),
            "n_flagged_evidence": dr.get("n_flagged", 0),
            "elapsed_s": elapsed,
        }
        results.append(summary)

        print(f"\n>>> DONE: {fname}")
        print(f"    Primary: {summary['primary_material']} (conf={summary['primary_confidence']:.2f})")
        print(f"    σ: {summary['n_high_cond']} high, {summary['n_flagged_cond']} flagged")
        print(f"    Ea: {summary['n_high_ea']} high, {summary['n_flagged_ea']} flagged")
        print(f"    Evidence: {summary['n_evidence']} ({summary['n_high_evidence']} high)")
        print(f"    Time: {elapsed}s")

    except Exception as e:
        import traceback
        traceback.print_exc()
        print(f"\n>>> ERROR: {fname}: {e}")
        results.append({"pdf_id": pdf_path.stem, "status": "error", "error": str(e)})

    with open(OUTPUT_DIR / "batch_results_v2.json", "w") as f:
        json.dump(results, f, indent=2)

# Final table
done = [r for r in results if r.get("status") == "done"]
errors = [r for r in results if r.get("status") == "error"]

print(f"\n{'='*70}")
print(f"BATCH EVALUATION V2 COMPLETE")
print(f"{'='*70}")
print(f"  Total: {len(PDFS)}")
print(f"  Done:  {len(done)}")
print(f"  Errors:{len(errors)}")
print(f"\n{'Paper':40s} {'Primary Material':25s} {'Conf':>4} {'σ_h':>4} {'σ_f':>4} {'Ea_h':>4} {'Ea_f':>4} {'Evid':>4}")
print(f"{'-'*95}")
total_high = total_flagged = 0
for r in done:
    total_high += r["n_high_evidence"]
    total_flagged += r["n_flagged_evidence"]
    pm = (r["primary_material"] or "?")[:24]
    print(f"{r['pdf_id'][:39]:40s} {pm:25s} {r['primary_confidence']:4.2f} {r['n_high_cond']:4d} {r['n_flagged_cond']:4d} {r['n_high_ea']:4d} {r['n_flagged_ea']:4d} {r['n_evidence']:4d}")
for r in errors:
    print(f"{r['pdf_id'][:39]:40s} {'ERROR':25s} {'':4s} {'':4s} {'':4s} {'':4s} {'':4s} {'':4s}")

print(f"\nTotals: {total_high} high-confidence evidence, {total_flagged} flagged")
print(f"Results: {OUTPUT_DIR}")
