"""Phase E0 — README status-block synchronization.

Verifies that the README's ``## Status`` section is machine-generated from
``release_report.json`` (marker-delimited, idempotent, honest by construction)
so the repo's front page can never drift from the live data again.
"""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))

from sync_readme_status import BEGIN, END, _render_status, sync_readme_status

SAMPLE_REPORT = {
    "version": "v0.3.2",
    "generated_at": "2026-08-02T22:03:02+00:00",
    "total_records": 30071,
    "verified_records": 116,
    "consensus_n3": 24,
    "gate_failures": [],
    "quality_distribution": {"gold": 0, "silver": 40, "rejected": 1},
}


def _sample_readme(tmp_path: Path) -> Path:
    p = tmp_path / "README.md"
    p.write_text(
        "# Heading\n\n## Status\n\n"
        + BEGIN + "\nstale hand-written status\n" + END +
        "\n\n## Next\n"
    )
    return p


class TestRenderStatus:
    def test_reports_verified_fraction_honestly(self) -> None:
        text = _render_status(SAMPLE_REPORT)
        assert "only **116 carry" in text or "only **116 " in text
        assert "structural/thermodynamic DFT records" in text
        assert "**ALL PASS**" in text

    def test_reports_failing_gates(self) -> None:
        report = {**SAMPLE_REPORT, "gate_failures": ["min_verified_labels"]}
        text = _render_status(report)
        assert "FAILING: min_verified_labels" in text

    def test_tier_breakdown_renders(self) -> None:
        text = _render_status(SAMPLE_REPORT)
        assert "silver 97.6%" in text
        assert "rejected 2.4%" in text

    def test_tier_breakdown_from_nested_report(self) -> None:
        report = {**SAMPLE_REPORT, "quality_distribution": {
            "tier_pct": {"gold": 0.0, "silver": 97.4, "bronze": 0.0, "rejected": 2.6},
        }}
        text = _render_status(report)
        assert "silver 97.4%" in text
        assert "rejected 2.6%" in text


class TestSyncReadmeStatus:
    def test_replaces_stale_section(self, tmp_path: Path) -> None:
        readme = _sample_readme(tmp_path)
        new_text = sync_readme_status(SAMPLE_REPORT, readme)
        assert new_text
        body = readme.read_text()
        assert "stale hand-written status" not in body
        assert BEGIN in body and END in body

    def test_idempotent_when_in_sync(self, tmp_path: Path) -> None:
        readme = _sample_readme(tmp_path)
        sync_readme_status(SAMPLE_REPORT, readme)
        second = sync_readme_status(SAMPLE_REPORT, readme)
        assert second == ""

    def test_missing_readme_raises(self, tmp_path: Path) -> None:
        with pytest.raises(FileNotFoundError):
            sync_readme_status(SAMPLE_REPORT, tmp_path / "nope.md")
