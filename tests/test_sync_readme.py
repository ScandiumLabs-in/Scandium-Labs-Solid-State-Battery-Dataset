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

from sync_readme_status import (
    BEGIN, END, _render_status, sync_badges, sync_readme_status,
)

SAMPLE_REPORT = {
    "version": "v0.3.2",
    "generated_at": "2026-08-02T22:03:02+00:00",
    "total_records": 30071,
    "verified_records": 116,
    "consensus_n3": 24,
    "gate_failures": [],
    "gate_total": 10,
    "gate_passed": 10,
    "tests_passed": 600,
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


def _sample_readme_with_badges(tmp_path: Path) -> Path:
    p = tmp_path / "README.md"
    p.write_text(
        "# Heading\n\n"
        "[![Release](https://img.shields.io/badge/dataset--release-v0.2.0-blue.svg)](https://github.com/ScandiumLabs-in/Scandium-Labs-Solid-State-Battery-Dataset)\n"
        "[![Release Gates](https://img.shields.io/badge/release--gates-10%2F10%20PASS-brightgreen.svg)](release_report.json)\n"
        "[![Tests](https://img.shields.io/badge/tests-600%20PASSing-success.svg)](tests/)\n"
        "[![License: CC BY 4.0](https://img.shields.io/badge/License-CC%20BY%204.0-lightgrey.svg)](LICENSE)\n"
        "[![Python Version](https://img.shields.io/badge/python-3.10%2B-blue.svg)](pyproject.toml)\n\n"
        "## Status\n\n" + BEGIN + "\nstale\n" + END + "\n"
    )
    return p


class TestSyncBadges:
    def test_rewrites_stale_badges(self, tmp_path: Path) -> None:
        readme = _sample_readme_with_badges(tmp_path)
        report = {**SAMPLE_REPORT, "gate_total": 22, "gate_passed": 21,
                  "tests_passed": 865}
        changed = sync_badges(report, readme)
        assert changed
        body = readme.read_text()
        assert "dataset--release-0.3.2" in body
        assert "release--gates-21%2F22" in body
        assert "tests-865%20PASSing" in body
        assert "10%2F10%20PASS-brightgreen" not in body
        assert body.count("img.shields.io/badge/dataset--release") == 1

    def test_badges_idempotent(self, tmp_path: Path) -> None:
        readme = _sample_readme_with_badges(tmp_path)
        sync_badges(SAMPLE_REPORT, readme)
        assert sync_badges(SAMPLE_REPORT, readme) == ""

    def test_render_badges_live_counts(self) -> None:
        from sync_readme_status import _render_badges
        text = _render_badges(SAMPLE_REPORT)
        assert "0.3.2" in text and "10%2F10" in text and "600" in text

    def test_render_badges_unknown_tests(self) -> None:
        from sync_readme_status import _render_badges
        report = {**SAMPLE_REPORT, "tests_passed": None}
        text = _render_badges(report)
        assert "tests-?%20PASSing" in text
