#!/usr/bin/env python3
"""File new LLM extraction records into the review queue for human verification.

Reads literature_output/extraction_results.json and appends pending items to
review_output/queue.json (dedup by pdf+composition+property+value).

Usage:
    python scripts/file_extraction_to_queue.py
"""

from __future__ import annotations

import json
import hashlib
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
RESULTS = ROOT / "literature_output/extraction_results.json"
QUEUE = ROOT / "review_output/queue.json"


def load_queue() -> dict:
    if QUEUE.exists():
        return json.loads(QUEUE.read_text())
    return {"version": 1, "updated_at": None, "items": []}


def save_queue(queue: dict) -> None:
    import datetime

    queue["updated_at"] = datetime.datetime.now(datetime.timezone.utc).isoformat()
    QUEUE.write_text(json.dumps(queue, indent=2))


def _existing_keys(queue: dict) -> set[str]:
    keys = set()
    for it in queue.get("items", []):
        key = (
            f"{it.get('paper_id')}|{it.get('composition')}|"
            f"{it.get('property')}|{it.get('value')}|{it.get('unit')}|"
            f"{it.get('temperature_celsius')}|{it.get('conductivity_type')}"
        )
        keys.add(key)
    return keys


def main() -> None:
    results = json.loads(RESULTS.read_text())
    queue = load_queue()
    existing = _existing_keys(queue)

    added = 0
    for pdf_name, recs in results.items():
        if not isinstance(recs, list):
            continue
        paper_id = Path(pdf_name).stem
        doi = None
        for r in recs:
            if r.get("doi"):
                doi = r["doi"]
                break
        for r in recs:
            composition = r.get("composition") or ""
            if not composition:
                continue
            family = r.get("family", "")
            has_sigma = r.get("sigma_RT") is not None
            has_ea = r.get("Ea") is not None
            if not has_sigma and not has_ea:
                continue

            if has_sigma:
                key = f"{paper_id}|{composition}|conductivity|{r['sigma_RT']}|S/cm|{r.get('temperature_celsius')}|{r.get('conductivity_type')}"
                if key not in existing:
                    queue["items"].append({
                        "review_id": f"review_{hashlib.md5(key.encode()).hexdigest()[:12]}",
                        "evidence_id": f"review_{hashlib.md5(key.encode()).hexdigest()[:12]}",
                        "paper_id": paper_id,
                        "doi": doi,
                        "composition": composition,
                        "family": family,
                        "property": "conductivity",
                        "value": r["sigma_RT"],
                        "unit": "S/cm",
                        "temperature_celsius": r.get("temperature_celsius"),
                        "conductivity_type": r.get("conductivity_type"),
                        "measurement_method": r.get("method") or r.get("measurement_method"),
                        "experiment": r.get("experiment") or {},
                        "evidence_sentence": f"LLM ensemble extraction from {pdf_name}",
                        "page": None,
                        "section": None,
                        "table_number": None,
                        "source": "llm_ensemble",
                        "is_primary": True,
                        "confidence": 0.7,
                        "issues": [],
                        "llm_model": "llama-3.1-8b-instant",
                        "prompt_version": "ensemble-v1",
                        "pipeline_version": "phase2-batch1",
                        "status": "pending",
                        "reviewed_at": None,
                        "reviewer": None,
                        "review_note": None,
                        "edited_value": None,
                        "edited_unit": None,
                    })
                    existing.add(key)
                    added += 1

            if has_ea:
                key = f"{paper_id}|{composition}|activation_energy|{r['Ea']}|eV|{r.get('temperature_celsius')}|{r.get('conductivity_type')}"
                if key not in existing:
                    queue["items"].append({
                        "review_id": f"review_{hashlib.md5(key.encode()).hexdigest()[:12]}",
                        "evidence_id": f"review_{hashlib.md5(key.encode()).hexdigest()[:12]}",
                        "paper_id": paper_id,
                        "doi": doi,
                        "composition": composition,
                        "family": family,
                        "property": "activation_energy",
                        "value": r["Ea"],
                        "unit": "eV",
                        "temperature_celsius": r.get("temperature_celsius"),
                        "conductivity_type": r.get("conductivity_type"),
                        "measurement_method": r.get("method") or r.get("measurement_method"),
                        "experiment": r.get("experiment") or {},
                        "evidence_sentence": f"LLM ensemble extraction from {pdf_name}",
                        "page": None,
                        "section": None,
                        "table_number": None,
                        "source": "llm_ensemble",
                        "is_primary": True,
                        "confidence": 0.7,
                        "issues": [],
                        "llm_model": "llama-3.1-8b-instant",
                        "prompt_version": "ensemble-v1",
                        "pipeline_version": "phase2-batch1",
                        "status": "pending",
                        "reviewed_at": None,
                        "reviewer": None,
                        "review_note": None,
                        "edited_value": None,
                        "edited_unit": None,
                    })
                    existing.add(key)
                    added += 1

    save_queue(queue)
    print(f"Added {added} new pending review items. Queue now has {len(queue['items'])} items.")


if __name__ == "__main__":
    main()
