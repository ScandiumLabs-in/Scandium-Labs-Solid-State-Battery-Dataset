#!/usr/bin/env python3
"""Synchronize the README ``## Status`` block with the live release report.

Reads ``release_report.json`` (produced by ``scripts/release.py``) and rewrites
the marker-delimited status block in ``README.md`` so the repository's front
page can never silently drift out of step with the actual data. This is the Phase
E0 fix for the "README says pre-Phase-0 while the dataset is at v0.3" lie.

The generated block is honest *by construction*: it reports the verified-label
fraction against the total records and carries the explicit caveat that the huge
majority of records are DFT structural/thermodynamic rows *without* transport
labels. Burying that hides the dataset's real character; stating it up front is
what makes every other claim in the README credible.

Marker contract (idempotent — safe to re-run, byte-stable for identical input):

    <!-- status-begin -->
    ...generated...
    <!-- status-end -->

Usage:
    python scripts/sync_readme_status.py                 # sync README.md from release_report.json
    python scripts/sync_readme_status.py --readme X.md   # explicit README path
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parent.parent

BEGIN = "<!-- status-begin -->"
END = "<!-- status-end -->"


def _tier_breakdown(report: dict[str, Any]) -> str:
    """Render a one-line honest quality-tier distribution from the report."""
    qd = report.get("quality_distribution") or {}
    if not isinstance(qd, dict):
        return "quality tier distribution unavailable"
    # The quality report nests percentages under ``tier_pct``; fall back to flat
    # counts (``tier_distribution``) and then top-level ``{tier}_records``.
    pct = qd.get("tier_pct")
    if isinstance(pct, dict):
        parts = [f"{k} {round(float(v), 1)}%" for k, v in pct.items() if float(v) > 0]
        return ", ".join(parts) or "quality tier distribution unavailable"
    dist = qd.get("tier_distribution")
    if isinstance(dist, dict) and dist:
        total = sum(int(v) for v in dist.values())
        parts = [
            f"{k} {round(100.0 * int(v) / total, 1)}%"
            for k, v in dist.items()
            if int(v) > 0
        ]
        return ", ".join(parts) or "quality tier distribution unavailable"
    total = sum(int(qd[k]) for k in ("gold", "silver", "bronze", "rejected") if k in qd)
    if not total:
        return "quality tier distribution unavailable"
    pct = {
        k: round(100.0 * int(qd[k]) / total, 1)
        for k in ("gold", "silver", "bronze", "rejected")
        if int(qd.get(k, 0)) > 0
    }
    return ", ".join(f"{k} {v}%" for k, v in pct.items()) or "quality tier distribution unavailable"


def _render_status(report: dict[str, Any]) -> str:
    version = report.get("version", "unknown")
    generated = report.get("generated_at", "")
    verified = report.get("verified_records", 0)
    total = report.get("total_records", 0)
    n3 = report.get("consensus_n3", 0)
    failures = report.get("gate_failures", [])

    tier_note = _tier_breakdown(report)

    lines = [
        f"**Status (auto-generated from `release_report.json` — do not edit by hand).** "
        f"Version **{version}**, generated {generated}. Release gates: "
        f"**{'ALL PASS' if not failures else 'FAILING: ' + ', '.join(failures)}**.",
        "",
        "| Bucket | Count | What it is |",
        "|---|---|---|",
        f"| **Bulk structural records** | ~{total} | DFT-native pulls (Materials Project / JARVIS / NOMAD / COD / etc.), Li-containing catalog. **Not screened for SSE relevance** — the dump includes cathode chemistries that share the Li+O+metal formula pattern. |",
        f"| **Verified experimental labels** | {verified} | Evidence-linked σ/Ea from literature mining, **human-reviewed**, provenance-tracked to the sentence level. The scarce valuable asset. |",
        f"| **Consensus (n≥3 papers)** | {n3} | Cross-paper consensus: only {n3} materials have ≥3 independent papers. |",
        "",
        "> **Honest caveat.** Of the ~" + str(total) + " records, only **" + str(verified) + " carry "
        "human-verified conductivity/Ea labels**; the remainder are "
        "structural/thermodynamic DFT records *without* transport labels. "
        "Quality-tier distribution: " + str(tier_note) + ". See "
        "`quality_output/quality_report.json` and `release_report.json` — "
        "stated up front so the rest of the dataset's claims are credible.",
        "",
        "> *This block is generated. Run `python scripts/sync_readme_status.py` "
        "(or any `scripts/release.py` invocation) to regenerate; if it disagrees "
        "with the report, regenerate — never hand-edit.*",
    ]
    return "\n".join(lines)


def sync_readme_status(report: dict[str, Any], readme_path: str | Path) -> str:
    """Rewrite the marker-delimited status block in ``README.md``.

    Returns the new README text if changed, or "" if already in sync (so callers
    can gate on drift).
    """
    readme = Path(readme_path)
    if not readme.exists():
        raise FileNotFoundError(f"README not found: {readme}")
    text = readme.read_text()

    new_block = BEGIN + "\n" + _render_status(report) + "\n" + END

    if BEGIN in text:
        start = text.index(BEGIN)
        end = text.index(END, start) + len(END)
        new_text = text[:start] + new_block + text[end:]
    else:
        # Append so we never leave stale prose above the dynamic block.
        new_text = text + "\n" + new_block + "\n"

    if new_text == text:
        return ""
    readme.write_text(new_text)
    return new_text


def _load_report() -> dict[str, Any]:
    p = ROOT / "release_report.json"
    if not p.exists():
        return {}
    try:
        return json.loads(p.read_text())
    except json.JSONDecodeError:
        return {}


def main() -> int:
    ap = argparse.ArgumentParser(description="Sync README status from release report")
    ap.add_argument("--readme", default=str(ROOT / "README.md"), help="path to README.md")
    args = ap.parse_args()

    report = _load_report()
    if not report:
        print("release_report.json missing/empty — run scripts/release.py first.")
        return 1
    try:
        sync_readme_status(report, args.readme)
    except FileNotFoundError as e:
        print(e)
        return 1
    print(f"README {args.readme} status block synced to {report.get('version')}.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())