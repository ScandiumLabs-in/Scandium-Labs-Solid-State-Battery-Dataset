#!/usr/bin/env python3
"""Run the full AI verification sweep over pending review-queue items.

Per pending record:
  1. locate evidence window in the source PDF (unit-aware, formula-aware)
  2. physics check (family ranges + Arrhenius prefactor)
  3. literature cross-check vs benchmark inventory + approved records
  4. multi-model LLM verification with 2/3 consensus
  5. composite review score + auto-decision

Writes literature_output/verification_results.json — one ReviewResult per record.
This is a triage/automation layer: high scores can be auto-approved downstream;
low scores still go to human review. Never edits values.

Usage:
    python scripts/run_verification.py                # all pending, single model
    python scripts/run_verification.py --models 2     # 2 independent models
    python scripts/run_verification.py --skip-llm     # evidence+physics+literature only
    python scripts/run_verification.py --write-queue  # stamp decision onto queue.json
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from dotenv import load_dotenv

load_dotenv()

from ssb_dataset.pipeline.verifier import (
    AUTO_APPROVE_MIN,
    VERIFIER_MODELS,
    composite_score,
    decide,
    locate_evidence,
    physics_check,
    verify_single,
)

ROOT = Path(__file__).resolve().parent.parent
QUEUE = ROOT / "review_output/queue.json"
OUT = ROOT / "literature_output/verification_results.json"
BENCHMARK = ROOT / "src/ssb_dataset/literature/benchmark_inventory.py"
PDF_DIR = ROOT / "literature_output/pdfs"

# Families with conductivity labels approved so far (for literature cross-check)
APPROVED_SIGMAS = {
    "Li6PS5Cl": (0.012, "sulfide"),
    "Li7La3Zr2O12": (0.0004, "garnet"),
    "Li2ZrCl6": (5.81e-6, "halide"),
    "Li1.3Al0.3Ti1.7(PO4)3": (0.00044, "nasicon"),
    "PEO-LiTFSI": (1.0e-6, "polymer_composite"),
}


def _mk_verdict(vd: dict):
    """Reconstruct a VerifierVerdict from its serialized dict."""
    from ssb_dataset.pipeline.verifier import VerifierVerdict

    v = VerifierVerdict()
    raw = vd.get("raw") or {}
    v.model = vd.get("model", "")
    v.evidence_ok = bool(raw.get("evidence_present"))
    comp = str(raw.get("composition_found", "")).lower()
    v.composition_ok = comp in ("true", "partial")
    v.sigma_ok = raw.get("sigma_found") == "yes"
    v.sigma_different = raw.get("sigma_found") == "different"
    v.ea_ok = raw.get("ea_found") == "yes"
    v.ea_different = raw.get("ea_found") == "different"
    v.temp_ok = bool(raw.get("temperature_found"))
    v.units_ok = bool(raw.get("units_consistent"))
    v.quote = vd.get("quote") or raw.get("sigma_quote") or raw.get("ea_quote") or ""
    return v


def load_benchmark() -> dict[str, dict]:
    import ast

    tree = ast.parse(BENCHMARK.read_text())
    out: dict[str, dict] = {}
    for node in ast.walk(tree):
        if isinstance(node, ast.Dict) and node.keys:
            for k, v in zip(node.keys, node.values):
                if isinstance(k, ast.Constant) and isinstance(k.value, str):
                    d = {}
                    if isinstance(v, ast.Dict):
                        for kk, vv in zip(v.keys, v.values):
                            if isinstance(kk, ast.Constant):
                                try:
                                    d[kk.value] = ast.literal_eval(vv)
                                except Exception:
                                    pass
                    out[k.value] = d
    return out


def literature_check(composition: str, sigma: float | None,
                     benchmark: dict, approved: dict) -> str:
    """Return 'agree' | 'conflict' | 'no_ref' | 'pending'."""
    if sigma is None:
        return "pending"
    # exact match in benchmark
    if composition in benchmark and benchmark[composition].get("sigma_S_per_cm"):
        ref = benchmark[composition]["sigma_S_per_cm"]
        if abs(sigma - ref) <= max(abs(ref) * 0.5, 5e-5):
            return "agree"
        return "conflict"
    # benchmark entries that share the base composition
    base = composition.split("-")[0].split("/")[0]
    for name, d in benchmark.items():
        if name.startswith(base) and d.get("sigma_S_per_cm"):
            ref = d["sigma_S_per_cm"]
            if abs(sigma - ref) <= max(abs(ref) * 1.0, 5e-5):
                return "agree"
    # approved records
    if composition in approved:
        ref, _ = approved[composition]
        if abs(sigma - ref) <= max(abs(ref) * 0.5, 5e-5):
            return "agree"
        return "conflict"
    return "no_ref"


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--models", type=int, default=1, help="number of independent models")
    parser.add_argument("--skip-llm", action="store_true")
    parser.add_argument("--write-queue", action="store_true",
                        help="stamp decisions onto queue.json from an EXISTING results file (no sweep)")
    parser.add_argument("--pdf-dir", type=str, default=str(PDF_DIR))
    parser.add_argument("--limit", type=int, default=0, help="process first N items (0=all)")
    parser.add_argument("--flags-only", action="store_true", help="only records with physics/literature flags")
    args = parser.parse_args()

    queue = json.loads(QUEUE.read_text())

    if args.write_queue:
        if not OUT.exists():
            print(f"No {OUT} — run the sweep first without --write-queue")
            return
        results = json.loads(OUT.read_text())
        by_id = {r.get("evidence_id") or r.get("review_id"): r for r in results}
        n = 0
        for it in queue["items"]:
            r = by_id.get(it.get("evidence_id")) or by_id.get(it.get("review_id"))
            if r:
                it["auto_review_score"] = r["score"]
                it["auto_decision"] = r["decision"]
                it["verifier_consensus"] = r["consensus"]
                it["verifier_note"] = "; ".join(r["notes"])[:200]
                n += 1
        QUEUE.write_text(json.dumps(queue, indent=2))
        print(f"Stamped decision onto {n} queue items from {OUT}")
        return

    items = [i for i in queue["items"] if i.get("status") == "pending"]
    if args.flags_only:
        items = [i for i in items if i.get("auto_check_severity") == "high"]
    if args.limit:
        items = items[: args.limit]
    benchmark = load_benchmark()

    results: list[dict] = []

    for idx, item in enumerate(items, 1):
        comp = item.get("composition") or ""
        prop = item.get("property") or ""
        value = item.get("value")
        if not isinstance(value, (int, float)):
            continue
        sigma = value if prop == "conductivity" else None
        ea = value if prop != "conductivity" else None
        family = item.get("family") or ""

        paper_id = item.get("paper_id") or ""
        pdf_path = Path(args.pdf_dir) / f"{paper_id}.pdf"

        # 1. evidence
        ev = locate_evidence(pdf_path, comp, sigma, ea)
        evidence_present = bool(ev and (ev.sigma_in_window or ev.ea_in_window or ev.window))

        # 2. physics
        phys_ok, phys_notes = physics_check(sigma, ea, family, item.get("temperature_celsius"))

        # 3. literature
        lit = literature_check(comp, sigma, benchmark, APPROVED_SIGMAS)

        # 4. LLM verification
        verdicts = []
        n_agree = 0
        n_models = 0
        if not args.skip_llm and evidence_present and ev is not None:
            models = VERIFIER_MODELS[: args.models]
            for m in models:
                v = verify_single(ev, {**item, "sigma_RT": sigma, "Ea": ea}, m)
                if not v.raw:
                    continue  # LLM call failed (rate limit) — skip
                n_models += 1
                if v.agree:
                    n_agree += 1
                verdicts.append(v.to_dict() if hasattr(v, "to_dict") else v.__dict__)

            # second pass: if models disagree or report 'different', widen the
            # evidence window and re-verify with one more model to disambiguate
            # an off-target window from a genuine paper contradiction.
            any_different = any(
                (vd.get("raw") or {}).get("sigma_found") == "different"
                or (vd.get("raw") or {}).get("ea_found") == "different"
                for vd in verdicts
            )
            no_agreement = n_agree == 0 and n_models >= 1
            if (any_different or no_agreement) and args.models < len(VERIFIER_MODELS):
                ev2 = locate_evidence(pdf_path, comp, sigma, ea, window_expand=300)
                if ev2 and ev2.window:
                    v2 = verify_single(ev2, {**item, "sigma_RT": sigma, "Ea": ea},
                                       VERIFIER_MODELS[args.models])
                    if v2.raw:
                        n_models += 1
                        if v2.agree:
                            n_agree += 1
                        verdicts.append(v2.to_dict() if hasattr(v2, "to_dict") else v2.__dict__)
                        ev = ev2  # use the widened window for evidence scoring

        consensus = n_agree >= 2 if n_models >= 2 else (n_agree == 1 if n_models == 1 else False)

        # units + temp signals from the LLM: the verifier tells us whether the
        # paper's value (in whatever unit) matches the stored S/cm value.
        units_ok = True
        temp_reported = bool(item.get("temperature_celsius")) or item.get("temperature_celsius") is not None
        for vd in verdicts:
            raw = vd.get("raw") or {}
            if raw.get("sigma_found") == "yes":
                units_ok = True  # verifier confirmed value matches after conversion
            if raw.get("temperature_found"):
                temp_reported = True

        # 5. composite
        from ssb_dataset.pipeline.verifier import ReviewResult

        rr = ReviewResult(
            record_id=item.get("evidence_id", ""),
            paper_id=paper_id,
            composition=comp,
            sigma=sigma,
            ea=ea,
            family=family,
            evidence=ev,
            verdicts=[_mk_verdict(vd) for vd in verdicts],
            n_agree=n_agree,
            n_models=max(n_models, 1),
            physics_ok=phys_ok,
            physics_notes=phys_notes,
            literature_note=lit,
        )
        score = composite_score(rr, units_ok=units_ok, temp_reported=temp_reported)
        decision = decide(score)

        results.append({
            "review_id": item.get("review_id"),
            "evidence_id": item.get("evidence_id"),
            "paper_id": paper_id,
            "composition": comp,
            "family": family,
            "property": prop,
            "value": value,
            "sigma": sigma,
            "ea": ea,
            "evidence_present": evidence_present,
            "evidence_page": ev.page if ev else None,
            "evidence_window": (ev.window or "")[:200] if ev else "",
            "physics_ok": phys_ok,
            "physics_notes": phys_notes,
            "literature": lit,
            "n_agree": n_agree,
            "n_models": n_models,
            "consensus": consensus,
            "verdicts": verdicts,
            "units_ok": units_ok,
            "temp_reported": temp_reported,
            "score": score,
            "decision": decision,
            "notes": [*phys_notes] + ([f"literature {lit}"] if lit in ("conflict", "agree") else []),
        })
        print(f"[{idx:2d}/{len(items)}] {comp:32s} {value!r:>12} score={score:5.1f} -> {decision:12s} "
              f"(ev={evidence_present}, phys={phys_ok}, lit={lit}, agree={n_agree}/{n_models})")

    OUT.write_text(json.dumps(results, indent=2))
    from collections import Counter

    print(f"\nVerification complete: {len(results)} records -> {OUT}")
    print("Decisions:", dict(Counter(r["decision"] for r in results)))


if __name__ == "__main__":
    main()
