"""Persistence layer for the review dashboard.

Single source of truth for loading/saving the review queue, recording active
learning training pairs, and exporting approved records. Mirrors the write
semantics of scripts/review.py so a dashboard decision and a CLI decision land
in exactly the same on-disk state (queue.json + training_pairs.jsonl +
approved_records.parquet).

Paths are absolute from the repo root so the dashboard works regardless of CWD.
"""

from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parent.parent.parent.parent
REVIEW_DIR = ROOT / "review_output"
QUEUE_PATH = REVIEW_DIR / "queue.json"
APPROVED_PATH = REVIEW_DIR / "approved_records.parquet"
TRAINING_PAIRS = REVIEW_DIR / "training_pairs.jsonl"


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def load_queue() -> dict:
    if not QUEUE_PATH.exists():
        return {"version": 1, "updated_at": _now(), "items": []}
    return json.loads(QUEUE_PATH.read_text())


def save_queue(queue: dict) -> None:
    queue["updated_at"] = _now()
    REVIEW_DIR.mkdir(parents=True, exist_ok=True)
    QUEUE_PATH.write_text(json.dumps(queue, indent=2))


def record_training_pair(item: dict, action: str, human_note: str = "") -> None:
    """Active learning: store the AI prediction vs the human verdict as a
    training pair (one JSON line per correction event). Same schema as
    scripts/review.py::_record_training_pair."""
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
        "evidence_snippet": (item.get("verified_snippet") or item.get("evidence_sentence") or "")[:300],
        "reviewed_at": item.get("reviewed_at"),
        "reviewer": item.get("reviewer"),
    }
    REVIEW_DIR.mkdir(parents=True, exist_ok=True)
    with open(TRAINING_PAIRS, "a") as fh:
        fh.write(json.dumps(pair) + "\n")


def _to_int_or_none(v):
    if v is None or isinstance(v, bool):
        return None
    try:
        return int(float(v))
    except (TypeError, ValueError):
        return None


def export_approved(queue: dict) -> int:
    """Write approved records to approved_records.parquet (same schema as
    scripts/review.py::export). Returns the number of exported rows."""
    approved = [i for i in queue.get("items", []) if i.get("status") == "approved"]
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
    if not rows:
        return 0
    REVIEW_DIR.mkdir(parents=True, exist_ok=True)
    pd.DataFrame(rows).to_parquet(APPROVED_PATH, index=False)
    return len(rows)


def apply_decision(
    queue: dict,
    review_id: str,
    action: str,
    reviewer: str,
    *,
    edited_value: float | None = None,
    edited_unit: str | None = None,
    note: str = "",
) -> dict | None:
    """Mutate one queue item by a human decision and persist all artifacts.

    action in {"approve", "reject", "edit"}: edit implies approve with a
    corrected value/unit. Returns the updated item, or None if not found.
    """
    for item in queue.get("items", []):
        if item.get("review_id") != review_id:
            continue
        if action in ("approve", "edit"):
            item["status"] = "approved"
        elif action == "reject":
            item["status"] = "rejected"
        else:
            raise ValueError(f"unknown action {action!r}")
        if edited_value is not None:
            item["edited_value"] = edited_value
            if edited_unit:
                item["edited_unit"] = edited_unit
        elif action == "edit" and edited_value is None:
            item["edited_value"] = None
        item["reviewed_at"] = _now()
        item["reviewer"] = reviewer
        item["review_note"] = note or item.get("review_note") or None
        record_training_pair(item, action, note or "")
        save_queue(queue)
        export_approved(queue)
        if action in ("approve", "edit"):
            # Action 5 — continuous consensus flywheel: stamp the composition so
            # the next prioritize_consensus_growth.py sweep re-targets it
            # immediately (depth tracks breadth, not lagging behind it).
            comp = item.get("composition") or item.get("material_id")
            if comp:
                try:
                    try:
                        from scripts.prioritize_consensus_growth import stamp_feed
                    except ImportError:
                        from prioritize_consensus_growth import stamp_feed
                    stamp_feed(str(comp), source="review")
                except Exception:
                    pass
        return item
    return None
