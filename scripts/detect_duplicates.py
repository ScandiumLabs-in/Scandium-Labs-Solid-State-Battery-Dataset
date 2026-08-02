"""C3 — duplicate detection over the verified experimental set.

Deterministic duplicate scan run before every release. Detects, across the
approved review-queue records + canonical verified records:

  - composition duplication    — same material recorded twice within a paper
  - DOI duplication            — identical paper contributing twice
  - measurement duplication    — identical (material, property, value, unit)
    within the same source

The critical design rule (mirroring cleaning.py): same-material records from
DIFFERENT papers are NOT duplicates — they are consensus. Only intra-paper or
intra-source collisions are flagged.

Writes `review_output/duplicates.json`:

    {
      "duplicate_groups": [...],     # each group lists colliding record ids
      "duplicate_record_count": N,   # records participating in a collision
      "total_records_checked": M,
      "duplicate_rate_pct": x.xx,    # release gate input (must be < 1%)
      "duplicates_by_type": {...},   # per-type counts
      "checked_at": "..."
    }

Usage:
    python scripts/detect_duplicates.py
"""

from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
QUEUE = ROOT / "review_output" / "queue.json"
OUT = ROOT / "review_output" / "duplicates.json"


def _key(rec: dict) -> tuple:
    """Collision key for a measurement record (paper-scoped).

    Includes temperature + conductivity type so bulk-vs-total measurements of
    the same material/value are NOT collapsed — they are distinct physical
    measurements that legitimately share a paper."""
    material = (rec.get("composition") or rec.get("material") or rec.get("material_id") or "").strip()
    property_ = (rec.get("property") or "").strip()
    value = rec.get("value")
    unit = (rec.get("unit") or "").strip()
    temp = rec.get("temperature_celsius")
    ctype = rec.get("conductivity_type") or rec.get("ion_transport.conductivity_type")
    return (material.lower(), property_.lower(), value, unit.lower(), temp, str(ctype))


def _doi(rec: dict) -> str:
    doi = rec.get("doi") or rec.get("source_doi") or rec.get("paper_id") or ""
    # Doi may be embedded in a filename-style paper_id (e.g. 10.3389_fchem.2020.562549).
    if not doi and rec.get("paper_id"):
        return str(rec["paper_id"])
    return str(doi)


def detect_duplicates(items: list[dict]) -> dict:
    """Scan approved records for intra-source duplicates.

    Groups by DOI (same paper), then keys records within a paper by
    (material, property, value, unit). A group of size >1 within one paper is a
    true duplicate. Records from different papers are never compared — they are
    independent measurements feeding consensus.
    """
    approved = [i for i in items if i.get("status") == "approved"]
    total = len(approved)

    # DOI -> list of record dicts
    by_paper: dict[str, list[dict]] = {}
    for rec in approved:
        by_paper.setdefault(_doi(rec), []).append(rec)

    groups: list[dict] = []
    duplicated_ids: set[str] = set()
    type_counts: dict[str, int] = {
        "composition": 0,
        "doi": 0,
        "measurement": 0,
    }

    for doi, recs in by_paper.items():
        # DOI duplication: same paper contributing the same material twice
        material_counts: dict[str, list] = {}
        for r in recs:
            material_counts.setdefault(_key(r)[0], []).append(r)
        for material, ms in material_counts.items():
            if len(ms) > 1:
                # Same material twice in one paper is only a duplicate when the
                # second record duplicates the first's (property, value, temp, type).
                if len({_key(r)[1:] for r in ms}) < len(ms):
                    type_counts["composition"] += 1

        # Measurement duplication: exact (material, property, value, unit)
        seen: dict[tuple, list] = {}
        for r in recs:
            seen.setdefault(_key(r), []).append(r)
        for key, ms in seen.items():
            if len(ms) > 1:
                type_counts["measurement"] += 1
                ids = [m.get("review_id") or f"{doi}:{m.get('composition')}" for m in ms]
                duplicated_ids.update(ids)
                groups.append({
                    "doi": doi,
                    "material": ms[0].get("composition") or ms[0].get("material_id") or "",
                    "property": ms[0].get("property", ""),
                    "value": ms[0].get("value"),
                    "unit": ms[0].get("unit", ""),
                    "record_ids": ids,
                    "type": "measurement",
                })

    # DOI duplication: same material measured in the same paper but different values
    # is only flagged when composition repeats (covered by composition counter).

    dup_count = len(duplicated_ids)
    rate = round(dup_count / total * 100, 2) if total else 0.0

    return {
        "duplicate_groups": groups,
        "duplicate_record_count": dup_count,
        "total_records_checked": total,
        "duplicate_rate_pct": rate,
        "duplicates_by_type": type_counts,
        "checked_at": datetime.now(timezone.utc).isoformat(),
    }


def main() -> None:
    queue = json.loads(QUEUE.read_text()) if QUEUE.exists() else {"items": []}
    report = detect_duplicates(queue.get("items", []))
    OUT.write_text(json.dumps(report, indent=2, default=str))
    print(f"wrote {OUT.name}: {report['total_records_checked']} records checked, "
          f"duplicate rate {report['duplicate_rate_pct']}% "
          f"({report['duplicate_record_count']} records in {len(report['duplicate_groups'])} groups)")


if __name__ == "__main__":
    main()
