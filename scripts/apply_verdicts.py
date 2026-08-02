#!/usr/bin/env python3
"""Apply AI-assisted verification verdicts to the review queue.

Each verdict was reached by checking the extracted value against the source
paper text (full_text.txt + PDF pages). The reviewer is recorded as
"ai-verification" so a human can sweep the queue and confirm/flip any
decision in seconds. Every decision carries a review_note with the source
evidence and the correct value where applicable.

Usage:
  python scripts/apply_verdicts.py [--dry-run]
"""

from __future__ import annotations

import argparse
import json
import re
from datetime import datetime, timezone
from pathlib import Path

QUEUE_PATH = Path("review_output/queue.json")

# Verdicts keyed by (paper_id, property, value) — resolved from source reading.
VERDICTS: dict[tuple[str, str, str], dict] = {
    # ── garnet paper 022-35287-1 ────────────────────────────────────────────
    ("10.1038_s41467-022-35287-1", "conductivity", "9.18e-06"): {
        "status": "rejected",
        "review_note": "Hallucination: value not in paper. Paper reports ~1e-3 S/cm LLZO baseline, "
                       "2.7e-4/1.7e-4 S/cm (Li=7.0 bulk), 3.2e-4 S/cm (Li=6.6 bulk) at 25C.",
    },
    ("10.1038_s41467-022-35287-1", "conductivity", "7.69e-06"): {
        "status": "rejected",
        "review_note": "Hallucination: value not in paper (see above verdict).",
    },
    ("10.1038_s41467-022-35287-1", "activation_energy", "0.3"): {
        "status": "rejected",
        "review_note": "Paper reports 406.8/403.5 meV (0.407/0.404 eV) for Li=7.0/Li=6.6 garnets, "
                       "not 0.3 eV.",
    },
    ("10.1038_s41467-022-35287-1", "activation_energy", "0.4"): {
        "status": "approved",
        "review_note": "Matches paper 'similar activation energy for both two different garnets "
                       "(406.8 meV and 403.5 meV)' for Li=7.0 garnet (0.407 eV).",
    },
    ("10.1038_s41467-022-35287-1", "activation_energy", "0.5"): {
        "status": "rejected",
        "review_note": "False positive: 0.5 matches vacancy concentration 'nc,vac = 0.4-0.5', "
                       "not activation energy.",
    },

    # ── Na3HfZr NASICON paper 023-40669-0 ───────────────────────────────────
    ("10.1038_s41467-023-40669-0", "conductivity", "6.48e-05"): {
        "status": "rejected",
        "review_note": "Composition mismatch: 6.48e-5 S/cm is for a different composition "
                       "transition (Na3HfMg(PO4)3 -> Na3ScIn(PO4)3), not Na3HfZr(SiO4)2(PO4).",
    },
    ("10.1038_s41467-023-40669-0", "conductivity", "0.00044"): {
        "status": "approved",
        "review_note": "Correct: 'highest ionic conductivity of 4.4 x 10-4 S cm-1 is achieved in "
                       "Na3HfZr(SiO4)2(PO4)'.",
    },
    ("10.1038_s41467-023-40669-0", "activation_energy", "0.1"): {
        "status": "rejected",
        "review_note": "Wrong: paper reports lowest bulk activation energy of 0.302 eV for "
                       "Na3HfZr(SiO4)2(PO4), not 0.1 eV.",
    },
    ("10.1038_s41467-023-40669-0", "activation_energy", "0.5"): {
        "status": "rejected",
        "review_note": "False positive: 0.5 matches composition sampling intervals "
                       "(z can take values 0-3.0 using intervals of 0.5), not Ea.",
    },

    # ── antiperovskite paper 023-42385-1 ────────────────────────────────────
    ("10.1038_s41467-023-42385-1", "activation_energy", "0.326"): {
        "status": "rejected",
        "review_note": "0.326 eV is the AIMD-computed migration barrier, not the measured Ea. "
                       "Measured Ea = 0.56 eV (already in verified set); sigma = 4.5e-6 S/cm at 25C.",
    },

    # ── PEO-LiTFSI paper 024-51191-2 ────────────────────────────────────────
    ("10.1038_s41467-024-51191-2", "conductivity", "0.000121"): {
        "status": "rejected",
        "review_note": "Not in paper. Paper reports PEO-LiTFSI ~1e-6 S/cm RT; AlOC-doped version "
                       "1.87e-4 S/cm at 35C.",
    },
    ("10.1038_s41467-024-51191-2", "conductivity", "4.2e-05"): {
        "status": "rejected",
        "review_note": "Not in paper (see above).",
    },
    ("10.1038_s41467-024-51191-2", "activation_energy", "0.42"): {
        "status": "rejected",
        "review_note": "0.42 eV is the AlOC-doped version's Ea above Tm (Fig 3), wrong attribution "
                       "to PEO-LiTFSI. PEO-LiTFSI Ea = 1.21 eV (already in verified set).",
    },

    # ── nasicon LATP paper ──────────────────────────────────────────────────
    ("nasicon_mdpi", "conductivity", "3e-06"): {
        "status": "approved",
        "review_note": "Correct: 'total conductivity ... improved from 3.0 x 10-6 S/cm to "
                       "3.0 x 10-4 S/cm' (25C).",
    },
    ("nasicon_mdpi", "conductivity", "0.0003"): {
        "status": "approved",
        "review_note": "Correct: 3.0 x 10-4 S/cm at 25C (total conductivity).",
    },
    ("nasicon_mdpi", "activation_energy", "0.2"): {
        "status": "rejected",
        "review_note": "Hallucination: paper reports NO activation energy; 'activation' regex "
                       "matched 'CC BY license' text.",
    },

    # ── sulfide_argyrodite (Energies 2023 published version) ────────────────
    ("sulfide_argyrodite", "conductivity", "1.53"): {
        "status": "rejected",
        "review_note": "Table 1 literature value (1.53 mS/cm, Li6PS5Cl, Ohno[28]) in mS/cm stored "
                       "as S/cm = 1000x error; also wrong composition attribution. Paper's own "
                       "measurement: 12 mS/cm at 75C (540 MPa pelletizing, 250 MPa operating).",
    },
    ("sulfide_argyrodite", "activation_energy", "0.275"): {
        "status": "approved",
        "review_note": "Correct: 'activation energy was found to be 0.275 eV' at 250 MPa operating, "
                       "540 MPa pelletizing, -20 to 75C.",
    },

    # ── sulfide_preprint (same study, preprint version) ─────────────────────
    # All Table 1 literature values: wrong unit (mS/cm stored as S/cm) + wrong
    # composition attribution (Li6PS5Cl literature, not Li6PS5Cl0.5Br0.5).
    ("sulfide_preprint", "conductivity", "1.53"): {
        "status": "rejected",
        "review_note": "Table 1 literature value for Li6PS5Cl in mS/cm stored as S/cm (1000x error); "
                       "own measurement is 12 mS/cm at 75C.",
    },
    ("sulfide_preprint", "conductivity", "2.6"): {
        "status": "rejected", "review_note": "Table 1 literature value (Li6PS5Cl) unit error (mS/cm->S/cm).",
    },
    ("sulfide_preprint", "conductivity", "1.9"): {
        "status": "rejected", "review_note": "Table 1 literature value (Li6PS5Cl) unit error (mS/cm->S/cm).",
    },
    ("sulfide_preprint", "conductivity", "2.14"): {
        "status": "rejected", "review_note": "Table 1 literature value (Li6PS5Cl) unit error (mS/cm->S/cm).",
    },
    ("sulfide_preprint", "conductivity", "0.443"): {
        "status": "rejected", "review_note": "Table 1 literature value (Li6PS5Cl) unit error (mS/cm->S/cm).",
    },
    ("sulfide_preprint", "conductivity", "2.98"): {
        "status": "rejected", "review_note": "Table 1 literature value (Li6PS5Cl) unit error (mS/cm->S/cm).",
    },
    ("sulfide_preprint", "conductivity", "0.79"): {
        "status": "rejected", "review_note": "Table 1 literature value (Li6PS5Cl) unit error (mS/cm->S/cm).",
    },
    ("sulfide_preprint", "conductivity", "0.63"): {
        "status": "rejected", "review_note": "Table 1 literature value (Li6PS5Cl) unit error (mS/cm->S/cm).",
    },
    ("sulfide_preprint", "conductivity", "1.0"): {
        "status": "rejected", "review_note": "Table 1 literature value (Li6PS5Cl) unit error (mS/cm->S/cm).",
    },
    ("sulfide_preprint", "conductivity", "1.8"): {
        "status": "rejected", "review_note": "Table 1 literature value (Li6PS5Cl) unit error (mS/cm->S/cm).",
    },
    ("sulfide_preprint", "conductivity", "1.3"): {
        "status": "rejected", "review_note": "Table 1 literature value (Li6PS5Cl) unit error (mS/cm->S/cm).",
    },
    ("sulfide_preprint", "conductivity", "0.5"): {
        "status": "rejected", "review_note": "Table 1 literature value (Li6PS5Cl) unit error (mS/cm->S/cm).",
    },
    ("sulfide_preprint", "conductivity", "1.29"): {
        "status": "rejected", "review_note": "Table 1 literature value (Li6PS5Cl) unit error (mS/cm->S/cm).",
    },
    ("sulfide_preprint", "conductivity", "0.375"): {
        "status": "rejected", "review_note": "Not in paper table or text at all (hallucination).",
    },
    ("sulfide_preprint", "conductivity", "0.72"): {
        "status": "rejected", "review_note": "Not in paper table or text at all (hallucination).",
    },
    ("sulfide_preprint", "conductivity", "0.325"): {
        "status": "rejected", "review_note": "Not in paper table or text at all (hallucination).",
    },
    ("sulfide_preprint", "conductivity", "0.441"): {
        "status": "rejected", "review_note": "Not in paper (closest table value 0.443) - hallucination/typo.",
    },
    ("sulfide_preprint", "conductivity", "0.275"): {
        "status": "rejected", "review_note": "0.275 is the activation energy (eV), mislabeled as conductivity S/cm.",
    },
    ("sulfide_preprint", "conductivity", "0.3"): {
        "status": "rejected", "review_note": "Not a standalone conductivity in paper (matches pelletizing "
                        "pressure '300' or range) - hallucination.",
    },
    ("sulfide_preprint", "conductivity", "0.01"): {
        "status": "rejected", "review_note": "Not in paper (hallucination).",
    },
}


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()

    queue = json.loads(QUEUE_PATH.read_text())
    items = queue["items"]

    applied = 0
    unmatched = []

    for item in items:
        key = (item.get("paper_id", ""), item.get("property", ""), str(item.get("value")))
        verdict = VERDICTS.get(key)
        if verdict is None:
            unmatched.append(key)
            continue
        item["status"] = verdict["status"]
        item["reviewer"] = "ai-verification"
        item["reviewed_at"] = _now()
        item["review_note"] = verdict["review_note"]
        applied += 1

    if args.dry_run:
        print(f"[dry-run] would apply {applied} verdicts")
        if unmatched:
            print(f"[dry-run] {len(unmatched)} items WITHOUT a verdict (left pending):")
            for u in unmatched:
                print(f"    {u}")
        return

    QUEUE_PATH.write_text(json.dumps(queue, indent=2))
    print(f"Applied {applied} verdicts to review_output/queue.json")
    if unmatched:
        print(f"{len(unmatched)} items left pending (no verdict defined):")
        for u in unmatched:
            print(f"    {u}")

    # summary
    from collections import Counter
    counts = Counter(i.get("status") for i in items)
    print("\nQueue status now:")
    for k, v in counts.items():
        print(f"  {k:12s}: {v}")


if __name__ == "__main__":
    main()
