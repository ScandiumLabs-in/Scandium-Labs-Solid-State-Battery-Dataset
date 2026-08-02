"""Tests for Phase 10 — Maintenance Documentation."""

from __future__ import annotations

from pathlib import Path

import pytest

from ssb_dataset.maintenance import (
    generate_contributing,
    generate_deprecation_policy,
    generate_issue_templates,
    generate_maintenance_plan,
    generate_pr_template,
    generate_usage_guide,
)


# ── CONTRIBUTING.md ────────────────────────────────────────────────────────────


class TestGenerateContributing:
    def test_creates_file(self, tmp_path: Path) -> None:
        path = tmp_path / "CONTRIBUTING.md"
        result = generate_contributing(path)
        assert path.exists()
        assert "Contributing" in result

    def test_includes_submission_guide(self, tmp_path: Path) -> None:
        path = tmp_path / "CONTRIBUTING.md"
        result = generate_contributing(path)
        assert "conductivity" in result
        assert "PR" in result

    def test_includes_license_note(self, tmp_path: Path) -> None:
        path = tmp_path / "CONTRIBUTING.md"
        result = generate_contributing(path)
        assert "CC-BY-4.0" in result


# ── MAINTENANCE.md ─────────────────────────────────────────────────────────────


class TestGenerateMaintenancePlan:
    def test_creates_file(self, tmp_path: Path) -> None:
        path = tmp_path / "MAINTENANCE.md"
        result = generate_maintenance_plan(path)
        assert path.exists()
        assert "Maintenance Plan" in result

    def test_includes_cadence(self, tmp_path: Path) -> None:
        path = tmp_path / "MAINTENANCE.md"
        result = generate_maintenance_plan(path)
        assert "Quarterly" in result

    def test_includes_versioning(self, tmp_path: Path) -> None:
        path = tmp_path / "MAINTENANCE.md"
        result = generate_maintenance_plan(path)
        assert "Semantic Versioning" in result or "MAJOR" in result


# ── DEPRECATION.md ─────────────────────────────────────────────────────────────


class TestGenerateDeprecationPolicy:
    def test_creates_file(self, tmp_path: Path) -> None:
        path = tmp_path / "DEPRECATION.md"
        result = generate_deprecation_policy(path)
        assert path.exists()
        assert "Deprecation Policy" in result

    def test_includes_lifecycle(self, tmp_path: Path) -> None:
        path = tmp_path / "DEPRECATION.md"
        result = generate_deprecation_policy(path)
        assert "active" in result
        assert "deprecated" in result

    def test_no_current_deprecations(self, tmp_path: Path) -> None:
        path = tmp_path / "DEPRECATION.md"
        result = generate_deprecation_policy(path)
        assert "None" in result


# ── USAGE_GUIDE.md ─────────────────────────────────────────────────────────────


class TestGenerateUsageGuide:
    def test_creates_file(self, tmp_path: Path) -> None:
        path = tmp_path / "USAGE_GUIDE.md"
        result = generate_usage_guide(path)
        assert path.exists()
        assert "Usage Guide" in result or "Quick Start" in result

    def test_includes_hf_option(self, tmp_path: Path) -> None:
        path = tmp_path / "USAGE_GUIDE.md"
        result = generate_usage_guide(path)
        assert "datasets" in result.lower()

    def test_includes_citation(self, tmp_path: Path) -> None:
        path = tmp_path / "USAGE_GUIDE.md"
        result = generate_usage_guide(path)
        assert "bibtex" in result.lower() or "citation" in result.lower()


# ── Issue Templates ────────────────────────────────────────────────────────────


class TestGenerateIssueTemplates:
    def test_creates_all_templates(self, tmp_path: Path) -> None:
        paths = generate_issue_templates(tmp_path)
        assert len(paths) == 3

    def test_bug_report_created(self, tmp_path: Path) -> None:
        paths = generate_issue_templates(tmp_path)
        bug = [p for p in paths if p.endswith("bug_report.md")]
        assert len(bug) == 1
        content = Path(bug[0]).read_text()
        assert "Bug Report" in content

    def test_data_submission_created(self, tmp_path: Path) -> None:
        paths = generate_issue_templates(tmp_path)
        ds = [p for p in paths if p.endswith("data_submission.md")]
        assert len(ds) == 1
        content = Path(ds[0]).read_text()
        assert "Composition" in content
        assert "sigma_RT" in content

    def test_feature_request_created(self, tmp_path: Path) -> None:
        paths = generate_issue_templates(tmp_path)
        fr = [p for p in paths if p.endswith("feature_request.md")]
        assert len(fr) == 1
        content = Path(fr[0]).read_text()
        assert "Feature Request" in content


# ── PR Template ────────────────────────────────────────────────────────────────


class TestGeneratePRTemplate:
    def test_creates_file(self, tmp_path: Path) -> None:
        path = tmp_path / "PULL_REQUEST_TEMPLATE.md"
        result = generate_pr_template(path)
        assert path.exists()
        assert "Pull Request" in result

    def test_includes_checklist(self, tmp_path: Path) -> None:
        path = tmp_path / "PULL_REQUEST_TEMPLATE.md"
        result = generate_pr_template(path)
        assert "pytest" in result
        assert "CHANGELOG" in result

    def test_includes_type_options(self, tmp_path: Path) -> None:
        path = tmp_path / "PULL_REQUEST_TEMPLATE.md"
        result = generate_pr_template(path)
        assert "Bug fix" in result
        assert "New feature" in result
