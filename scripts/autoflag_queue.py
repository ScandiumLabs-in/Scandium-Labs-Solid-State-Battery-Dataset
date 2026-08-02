#!/usr/bin/env python3
"""Run red-flag auto-checks over all PENDING review queue items and stamp
auto_check_note + auto_check_severity on each. Pure triage layer — never
approves/rejects, only annotates so a human reviewer sees likely errors first.

Usage:
    python scripts/autoflag_queue.py
"""

from __future__ import annotations

import json
from pathlib import Path

from dotenv import load_dotenv

load_dotenv()

from ssb_dataset.pipeline.consensus import compute_consensus
from ssb_dataset.pipeline.normalization import normalize_record_units
from ssb_dataset.pipeline.redflags import (
    FAMILY_EA_RANGES,
    FAMILY_SIGMA_RANGES,
    check_arrhenius_consistency,
    check_ea_in_family_range,
    check_sigma_in_family_range,
)

ROOT = Path(__file__).resolve().parent.parent
QUEUE = ROOT / "review_output/queue.json"

# normalize family aliases used in the queue to redflags' family keys
FAMILY_ALIASES = {
    "garnet": "garnet",
    "perovskite": "perovskite",
    "perovskite/llto": "perovskite",
    "sulfide": "sulfide",
    "argyrodite": "sulfide",
    "halide": "halide",
    "nasicon": "nasicon",
    "antiperovskite": "antiperovskite",
    "hydride": "hydride",
    "borohydride": "borohydride",
    "polymer": "polymer_composite",
    "polymer_composite": "polymer_composite",
    "oxide": "oxide",
}


def main() -> None:
    q = json.loads(QUEUE.read_text())
    items = q["items"]
    # clear stale auto-check fields so re-runs are idempotent
    for it in items:
        it.pop("auto_check_note", None)
        it.pop("auto_check_severity", None)
    n_flagged = 0
    for it in items:
        if it.get("status") != "pending":
            continue
        family = FAMILY_ALIASES.get((it.get("family") or "").lower(), "")
        prop = (it.get("property") or "").lower()
        value = it.get("value")
        if not isinstance(value, (int, float)):
            continue
        notes: list[str] = []
        severity = "low"

        if "conductivity" in prop or it.get("unit") == "S/cm":
            sigma = float(value)
            is_flag, msg = check_sigma_in_family_range(sigma, family) if family else (False, "")
            if is_flag:
                notes.append(msg)
                severity = "high"
            ea = it.get("activation_energy_eV") or it.get("ea_eV")
            if family and ea:
                is_flagA, msgA = check_arrhenius_consistency(
                    sigma, float(ea), family=family,
                    temperature_k=(it.get("temperature_celsius") or 25) + 273.15,
                )
                if is_flagA:
                    notes.append(f"Arrhenius-inconsistent: sigma={sigma} Ea={ea} {msgA}")
                    severity = "high"
        elif "activation" in prop or prop == "ea" or it.get("unit") == "eV":
            ea = float(value)
            is_flag, msg = check_ea_in_family_range(ea, family) if family else (False, "")
            if is_flag:
                notes.append(msg)
                severity = "high"

        if notes:
            it["auto_check_note"] = "; ".join(notes)
            it["auto_check_severity"] = severity
            n_flagged += 1

    # literature consensus pass: cross-record outlier detection within each
    # material group. Uses normalized S/cm values so mS/cm-vs-S/cm mistakes
    # surface as genuine outliers instead of looking like a different material.
    pending = [it for it in items if it.get("status") == "pending"]
    for it in pending:
        normalize_record_units(it)
    consensus = compute_consensus(pending)
    for f in consensus.flagged:
        rid = f["review_id"]
        for it in items:
            if it.get("review_id") == rid:
                prev = it.get("auto_check_note") or ""
                it["auto_check_note"] = (prev + "; " if prev else "") + "consensus-outlier: " + f["note"]
                it["auto_check_severity"] = "high"
                n_flagged += 1
                break

    q["items"] = items
    q["updated_at"] = None
    QUEUE.write_text(json.dumps(q, indent=2))
    print(f"Flagged {n_flagged}/{sum(1 for i in items if i.get('status')=='pending')} pending items")


if __name__ == "__main__":
    main()
