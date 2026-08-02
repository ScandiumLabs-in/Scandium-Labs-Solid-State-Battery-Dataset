#!/usr/bin/env python3
"""Human review interface for LLM-extracted records.

Usage:
  python scripts/review.py build        # collect pending records from scandium_output
  python scripts/review.py list         # show queue summary
  python scripts/review.py review       # interactive review session
  python scripts/review.py export       # write approved records to Parquet
  python scripts/review.py stats        # status breakdown + accuracy preview

Workflow: LLM -> review queue -> approve/reject/edit -> verified dataset.
Every decision is persisted to review_output/queue.json for auditability.
"""

from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime, timezone
from pathlib import Path

import pandas as pd

REVIEW_DIR = Path("review_output")
QUEUE_PATH = REVIEW_DIR / "queue.json"
APPROVED_PATH = REVIEW_DIR / "approved_records.parquet"

# Benchmark compounds + family literature ranges for quick sanity context.
# Mirrors src/ssb_dataset/pipeline/validation.py.
BENCHMARK_COMPOUNDS: dict[str, dict[str, float]] = {
    "Li10GeP2S12": {"sigma_S_per_cm": 1e-2, "Ea_eV": 0.25},
    "Li6PS5Cl": {"sigma_S_per_cm": 1e-3, "Ea_eV": 0.30},
    "Li7La3Zr2O12": {"sigma_S_per_cm": 1e-4, "Ea_eV": 0.40},
    "Li3xLa2/3-xTiO3": {"sigma_S_per_cm": 1e-5, "Ea_eV": 0.35},
    "Li0.33La0.56TiO3": {"sigma_S_per_cm": 1e-5, "Ea_eV": 0.35},
    "Li1.3Al0.3Ti1.7(PO4)3": {"sigma_S_per_cm": 1e-4, "Ea_eV": 0.30},
    "Li3InCl6": {"sigma_S_per_cm": 1e-3, "Ea_eV": 0.35},
    "LiBH4": {"sigma_S_per_cm": 1e-6, "Ea_eV": 0.60},
    "Li3OCl": {"sigma_S_per_cm": 1e-7, "Ea_eV": 0.50},
    "PEO-LiTFSI": {"sigma_S_per_cm": 1e-6, "Ea_eV": 1.21},
}

FAMILY_SIGMA_RANGE: dict[str, tuple[float, float]] = {
    "sulfide": (1e-5, 1e-1),
    "oxide": (1e-10, 1e-2),
    "garnet": (1e-6, 1e-2),
    "perovskite": (1e-8, 1e-3),
    "nasicon": (1e-6, 1e-2),
    "halide": (1e-6, 1e-2),
    "hydride": (1e-10, 1e-4),
    "borohydride": (1e-10, 1e-3),
    "antiperovskite": (1e-8, 1e-4),
    "polymer_composite": (1e-8, 1e-3),
    "argyrodite": (1e-5, 1e-1),
}

FAMILY_EA_RANGE: dict[str, tuple[float, float]] = {
    "sulfide": (0.1, 0.5),
    "oxide": (0.2, 0.9),
    "garnet": (0.2, 0.6),
    "perovskite": (0.2, 0.6),
    "nasicon": (0.2, 0.5),
    "halide": (0.2, 0.5),
    "hydride": (0.3, 0.8),
    "borohydride": (0.2, 1.7),
    "antiperovskite": (0.2, 0.6),
    "polymer_composite": (0.3, 1.0),
    "argyrodite": (0.1, 0.4),
}

# Alias family strings seen in the wild to canonical families.
FAMILY_ALIASES: dict[str, str] = {
    "llzo": "garnet",
    "llzto": "garnet",
    "peo-litfsi": "polymer_composite",
    "peo": "polymer_composite",
    "latp": "nasicon",
    "argyrodite": "argyrodite",
    "li3ocl": "antiperovskite",
    "anti-perovskite": "antiperovskite",
    "superionic": "sulfide",
}


def _canon_family(family) -> str:
    if not family:
        return ""
    fam = str(family).lower().strip()
    return FAMILY_ALIASES.get(fam, fam)


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _to_int_or_none(v):
    """Coerce a page/table number to int or None (avoids mixed-type Parquet col)."""
    if v is None:
        return None
    if isinstance(v, bool):
        return None
    try:
        return int(float(v))
    except (TypeError, ValueError):
        return None


# ---------------------------------------------------------------------------
# Queue construction
# ---------------------------------------------------------------------------

def build_queue() -> dict:
    """Collect pending review items from all scandium extraction results."""
    items: list[dict] = []
    pipeline_dir = Path("scandium_output")

    for result_path in sorted(pipeline_dir.glob("*/extraction_result.json")):
        paper_id = result_path.parent.name
        try:
            with open(result_path) as f:
                result = json.load(f)
        except Exception:
            continue
        evidence = result.get("evidence", [])
        for ev in evidence:
            if not ev.get("valid", True):
                continue
            item = {
                "review_id": f"review_{ev.get('evidence_id', '')}",
                "evidence_id": ev.get("evidence_id"),
                "paper_id": paper_id,
                "doi": ev.get("doi") or result.get("doi"),
                "composition": ev.get("composition"),
                "family": ev.get("family"),
                "property": ev.get("property"),
                "value": ev.get("value"),
                "unit": ev.get("normalized_unit") or ev.get("unit"),
                "temperature_celsius": ev.get("temperature_celsius"),
                "conductivity_type": ev.get("conductivity_type"),
                "measurement_method": ev.get("measurement_method"),
                "evidence_sentence": ev.get("evidence_sentence", ""),
                "page": ev.get("page"),
                "section": ev.get("section"),
                "table_number": ev.get("table_number"),
                "source": ev.get("source", ""),
                "is_primary": ev.get("is_primary", True),
                "confidence": ev.get("confidence", 0),
                "issues": ev.get("issues", []),
                "llm_model": ev.get("llm_model", ""),
                "prompt_version": ev.get("prompt_version", ""),
                "pipeline_version": ev.get("pipeline_version", ""),
                "status": "pending",
                "reviewed_at": None,
                "reviewer": None,
                "review_note": None,
                "edited_value": None,
                "edited_unit": None,
            }
            items.append(item)

    queue = {"version": 1, "updated_at": _now(), "items": items}
    REVIEW_DIR.mkdir(parents=True, exist_ok=True)
    QUEUE_PATH.write_text(json.dumps(queue, indent=2))
    print(f"Built queue: {len(items)} items -> {QUEUE_PATH}")
    return queue


def load_queue() -> dict:
    if not QUEUE_PATH.exists():
        print(f"Queue not found. Run `python scripts/review.py build` first.")
        sys.exit(1)
    return json.loads(QUEUE_PATH.read_text())


def save_queue(queue: dict) -> None:
    queue["updated_at"] = _now()
    QUEUE_PATH.write_text(json.dumps(queue, indent=2))


# ---------------------------------------------------------------------------
# Summary + stats
# ---------------------------------------------------------------------------

def summarize(queue: dict) -> None:
    items = queue.get("items", [])
    from collections import Counter
    status_counts = Counter(i.get("status", "pending") for i in items)
    prop_counts = Counter(i.get("property") for i in items)
    pending = [i for i in items if i.get("status") == "pending"]

    print("=" * 60)
    print("REVIEW QUEUE SUMMARY")
    print("=" * 60)
    print(f"Total items:  {len(items)}")
    for status, n in sorted(status_counts.items()):
        print(f"  {status:12s}: {n}")
    print(f"\nBy property:")
    for prop, n in sorted(prop_counts.items()):
        print(f"  {prop:20s}: {n}")
    print(f"\nPending by confidence:")
    if pending:
        high = sum(1 for i in pending if i.get("confidence", 0) >= 0.85)
        med = sum(1 for i in pending if 0.6 <= i.get("confidence", 0) < 0.85)
        low = sum(1 for i in pending if i.get("confidence", 0) < 0.6)
        print(f"  high (>=0.85): {high}")
        print(f"  medium (0.6-0.85): {med}")
        print(f"  low (<0.6): {low}")
    print(f"\nRun `python scripts/review.py review` to start reviewing.")


def stats(queue: dict) -> None:
    items = queue.get("items", [])
    approved = [i for i in items if i.get("status") == "approved"]
    rejected = [i for i in items if i.get("status") == "rejected"]
    print("=" * 60)
    print("REVIEW STATS")
    print("=" * 60)
    print(f"Pending:  {sum(1 for i in items if i.get('status')=='pending')}")
    print(f"Approved: {len(approved)}")
    print(f"Rejected: {len(rejected)}")
    if approved:
        print("\nApproved labels:")
        for i in approved:
            v = i.get("edited_value") if i.get("edited_value") is not None else i.get("value")
            u = i.get("edited_unit") if i.get("edited_unit") is not None else i.get("unit")
            print(f"  {i.get('composition'):30s} {i.get('property'):18s} "
                  f"{v!s:>10} {u!s:8s} conf={i.get('confidence'):.2f} "
                  f"({i.get('doi')})")


# ---------------------------------------------------------------------------
# Interactive review
# ---------------------------------------------------------------------------

def _prompt(msg: str, valid: list[str]) -> str:
    while True:
        ans = input(msg).strip().lower()
        if ans in valid:
            return ans
        if ans in ("q", "quit"):
            return "q"
        print(f"  (valid: {', '.join(valid)})")


# ---------------------------------------------------------------------------
# Fast review card helpers
# ---------------------------------------------------------------------------

def _fmt_val(v, unit=""):
    if v is None:
        return "—"
    if isinstance(v, float):
        if abs(v) >= 1e4 or (abs(v) < 1e-3 and v != 0):
            return f"{v:.2e} {unit}".strip()
        return f"{v:.4g} {unit}".strip()
    return f"{v} {unit}".strip()


def _benchmark_hint(material: str, property: str, value) -> str:
    """Return a short sanity hint if the material is a known benchmark."""
    if not material:
        return ""
    key = material
    if key not in BENCHMARK_COMPOUNDS:
        return ""
    bm = BENCHMARK_COMPOUNDS[key]
    target = bm.get("sigma_S_per_cm") if property == "conductivity" else bm.get("Ea_eV")
    if target is None or value is None:
        return ""
    try:
        ratio = float(value) / target
    except (TypeError, ZeroDivisionError):
        return ""
    if ratio >= 10 or ratio <= 0.1:
        return f"⚠ benchmark {key} expects ~{_fmt_val(target)} — off by {ratio:.1f}x"
    return f"ok vs benchmark {key} ({_fmt_val(target)})"


def _range_hint(family: str, property: str, value) -> str:
    """Return a hint if the value is outside the family's literature range."""
    if not family or value is None:
        return ""
    fam = _canon_family(family)
    rng = FAMILY_SIGMA_RANGE if property == "conductivity" else FAMILY_EA_RANGE
    lo, hi = rng.get(fam, (None, None))
    if lo is None or hi is None:
        return ""
    try:
        v = float(value)
    except (TypeError, ValueError):
        return ""
    if v < lo or v > hi:
        return f"⚠ outside {fam} range [{_fmt_val(lo)}–{_fmt_val(hi)}]"
    return f"within {fam} range [{_fmt_val(lo)}–{_fmt_val(hi)}]"


def _print_card(item: dict, idx: int, total: int) -> None:
    value = item.get("edited_value") if item.get("edited_value") is not None else item.get("value")
    unit = item.get("edited_unit") if item.get("edited_unit") is not None else item.get("unit")
    prop = item.get("property", "")

    print("─" * 62)
    print(f"[{idx}/{total}]  {prop.upper():20s}  {item.get('composition')}")
    print("─" * 62)
    print(f"  Value        : {_fmt_val(value, unit)}   (conf {item.get('confidence', 0):.2f})")
    print(f"  Family       : {item.get('family') or '—'}")
    print(f"  T            : {_fmt_val(item.get('temperature_celsius'))} °C")
    print(f"  Type/Method  : {item.get('conductivity_type') or '—'} / {item.get('measurement_method') or '—'}")
    if item.get("is_primary") is not None:
        print(f"  Primary      : {item.get('is_primary')}")

    bm = _benchmark_hint(item.get("composition"), prop, value)
    rng = _range_hint(item.get("family"), prop, value)
    if bm:
        print(f"  Benchmark    : {bm}")
    if rng:
        print(f"  Range        : {rng}")

    print(f"  Source       : {item.get('doi') or '—'}  ({item.get('paper_id')})")
    if item.get("page") or item.get("section") or item.get("table_number"):
        loc = f"p.{item.get('page')} §{item.get('section')} tbl.{item.get('table_number')}"
        print(f"  Location     : {loc}")
    pdf = Path("literature_output/pdfs") / f"{item.get('paper_id')}.pdf"
    if pdf.exists():
        print(f"  PDF          : {pdf}" + (f"  (open page {item.get('page')})" if item.get("page") else ""))

    sentence = item.get("evidence_sentence") or ""
    if sentence:
        print(f"  Evidence     : {sentence.strip()[:260]}")
    else:
        print(f"  Evidence     : ⚠ NO SENTENCE RESOLVED — check PDF manually")

    vs = item.get("verified_snippet")
    vv = item.get("verified_values")
    if vs or vv:
        print(f"  Verified     : {'; '.join(vv) if vv else ''}  (p.{item.get('verified_page')})")
        print(f"  Src snippet  : {vs.strip()[:180]}")

    note = item.get("auto_check_note")
    if note:
        print(f"  ⚠ Auto-check : {note}")

    score = item.get("auto_review_score")
    adec = item.get("auto_decision")
    if score is not None:
        print(f"  🤖 AI review : {score}/100 ({adec})"
              + (f" — {item.get('verifier_note')}" if item.get("verifier_note") else ""))

    if item.get("issues"):
        print(f"  Flags        : {', '.join(item['issues'])}")
    if item.get("llm_model"):
        print(f"  Model        : {item.get('llm_model')} / {item.get('prompt_version')} / {item.get('pipeline_version')}")


TRAINING_PAIRS = REVIEW_DIR / "training_pairs.jsonl"


def _record_training_pair(item: dict, action: str, human_note: str = "") -> None:
    """Active learning: store the AI prediction vs the human verdict as a
    training pair (one JSON line per correction event)."""
    import json as _json

    pair = {
        "review_id": item.get("review_id"),
        "composition": item.get("composition"),
        "family": item.get("family"),
        "property": item.get("property"),
        "ai_value": item.get("value"),
        "ai_score": item.get("auto_review_score"),
        "ai_decision": item.get("auto_decision"),
        "ai_verifier_note": item.get("verifier_note"),
        "human_action": action,
        "human_value": item.get("edited_value") if item.get("edited_value") is not None else item.get("value"),
        "human_unit": item.get("edited_unit") or item.get("unit"),
        "human_note": human_note or item.get("review_note"),
        "evidence_page": item.get("verified_page") or item.get("page"),
        "evidence_snippet": (item.get("verified_snippet") or "")[:300],
        "reviewed_at": item.get("reviewed_at"),
        "reviewer": item.get("reviewer"),
    }
    with open(TRAINING_PAIRS, "a") as fh:
        fh.write(_json.dumps(pair) + "\n")


def review(queue: dict, reviewer: str = "reviewer") -> None:
    items = queue["items"]
    # Group by paper so the reviewer cross-checks one paper's values together.
    pending_idx = [i for i, it in enumerate(items) if it.get("status") == "pending"]
    pending_idx.sort(key=lambda i: (items[i].get("paper_id") or "", items[i].get("page") or 0))

    if not pending_idx:
        print("No pending items. Run `build` or `export`.")
        return

    print(f"\n{len(pending_idx)} items to review. Commands: [a]pprove [r]eject "
          f"[e]dit [s]kip [q]uit\n")

    for pos, idx in enumerate(pending_idx, start=1):
        item = items[idx]
        _print_card(item, pos, len(pending_idx))

        cmd = _prompt("\n  [a]pprove [r]eject [e]dit [s]kip [q]uit > ", ["a", "r", "e", "s"])
        if cmd == "q":
            print("Review session ended.")
            break
        if cmd == "s":
            continue
        if cmd == "a":
            item["status"] = "approved"
        elif cmd == "r":
            note = input("  rejection reason (optional): ").strip()
            item["status"] = "rejected"
            item["review_note"] = note or "rejected by reviewer"
        elif cmd == "e":
            item["status"] = "approved"
            new_val = input(f"  new value (current {item['value']}): ").strip()
            if new_val:
                try:
                    item["edited_value"] = float(new_val)
                except ValueError:
                    print(f"  invalid number '{new_val}' — keeping original")
                    item["edited_value"] = None
            new_unit = input(f"  new unit (current {item['unit']}): ").strip()
            if new_unit:
                item["edited_unit"] = new_unit
            note = input("  review note: ").strip()
            item["review_note"] = note or None
        item["reviewed_at"] = _now()
        item["reviewer"] = reviewer
        _record_training_pair(item, cmd, item.get("review_note") or "")
        save_queue(queue)
        print("  saved.\n")

    save_queue(queue)
    print("Session complete. Decisions saved to queue.json.")


# ---------------------------------------------------------------------------
# Export approved records to verified Parquet
# ---------------------------------------------------------------------------

def export(queue: dict) -> None:
    approved = [i for i in queue["items"] if i.get("status") == "approved"]
    if not approved:
        print("No approved records to export.")
        return

    rows = []
    for i in approved:
        value = i.get("edited_value") if i.get("edited_value") is not None else i.get("value")
        unit = i.get("edited_unit") if i.get("edited_unit") is not None else i.get("unit")
        rows.append({
            "material_id": i.get("composition"),
            "family": i.get("family"),
            "doi": i.get("doi"),
            "paper_id": i.get("paper_id"),
            "property": i.get("property"),
            "value": value,
            "unit": unit,
            "temperature_celsius": i.get("temperature_celsius"),
            "conductivity_type": i.get("conductivity_type"),
            "measurement_method": i.get("measurement_method"),
            "confidence": i.get("confidence"),
            "page": _to_int_or_none(i.get("page")),
            "section": i.get("section"),
            "table_number": i.get("table_number"),
            "evidence_sentence": i.get("evidence_sentence"),
            "reviewed_at": i.get("reviewed_at"),
            "reviewer": i.get("reviewer"),
            "review_note": i.get("review_note"),
            "llm_model": i.get("llm_model"),
            "prompt_version": i.get("prompt_version"),
            "pipeline_version": i.get("pipeline_version"),
        })
    df = pd.DataFrame(rows)
    REVIEW_DIR.mkdir(parents=True, exist_ok=True)
    df.to_parquet(APPROVED_PATH, index=False)
    print(f"Exported {len(rows)} approved records -> {APPROVED_PATH}")
    print(f"\nNext: convert to verified dataset via scripts/merge_and_run.py")


# ---------------------------------------------------------------------------

def preview(queue: dict, limit: int | None = None) -> None:
    """Non-interactive card dump — useful to eyeball items before deciding."""
    items = queue.get("items", [])
    pending = [i for i in items if i.get("status") == "pending"]
    if limit:
        pending = pending[:limit]
    if not pending:
        print("No pending items.")
        return
    for pos, item in enumerate(pending, start=1):
        _print_card(item, pos, len(pending))
    print()


def main() -> None:
    parser = argparse.ArgumentParser(description="Human review interface")
    parser.add_argument("command", choices=["build", "list", "review", "export", "stats", "preview", "resolve"])
    parser.add_argument("--reviewer", default="reviewer")
    parser.add_argument("--limit", type=int, default=None, help="only show N items (preview)")
    args = parser.parse_args()

    if args.command == "build":
        build_queue()
    elif args.command == "list":
        summarize(load_queue())
    elif args.command == "review":
        review(load_queue(), reviewer=args.reviewer)
    elif args.command == "export":
        export(load_queue())
    elif args.command == "stats":
        stats(load_queue())
    elif args.command == "preview":
        preview(load_queue(), limit=args.limit)
    elif args.command == "resolve":
        import runpy
        sys.argv = ["resolve_evidence.py"] + sys.argv[sys.argv.index("resolve") + 1:]
        runpy.run_path(str(Path(__file__).parent / "resolve_evidence.py"), run_name="__main__")


if __name__ == "__main__":
    main()
