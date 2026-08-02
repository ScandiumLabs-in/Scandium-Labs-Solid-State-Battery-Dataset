"""Tests for Phase 9 — Release Pipeline."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from ssb_dataset.release import HuggingFacePublisher, ZenodoPublisher, GitHubReleaser, ReleaseManager, ReleaseChecklist


# ── Helpers ────────────────────────────────────────────────────────────────────


def _populate_artifacts(root: Path, include_all: bool = True) -> None:
    (root / "CITATION.cff").write_text("cff-version: 1.2.0")
    (root / "CHANGELOG.md").write_text("# Changelog\n\n## v0.1.0")
    (root / "docs_output").mkdir(parents=True, exist_ok=True)
    (root / "docs_output" / "datasheet.md").write_text("# Datasheet")
    (root / "docs_output" / "confidence_tiers.md").write_text("# Confidence")
    (root / "docs_output" / "families").mkdir(exist_ok=True)
    (root / "docs_output" / "families" / "sulfide.md").write_text("# Sulfide")
    (root / "features_output").mkdir(parents=True, exist_ok=True)
    (root / "features_output" / "descriptors.parquet").write_bytes(b"")
    (root / "features_output" / "splits_metadata.json").write_text('{"has_splits": true}')
    (root / "features_output" / "gold.parquet").write_bytes(b"")
    (root / "validation_output").mkdir(parents=True, exist_ok=True)
    (root / "validation_output" / "validation_report.json").write_text(
        json.dumps({"passed": include_all, "family_distribution_flags": 0 if include_all else 1})
    )
    (root / "cleaning_output").mkdir(parents=True, exist_ok=True)
    (root / "cleaning_output" / "canonical_dataset.parquet").write_bytes(b"")


# ── ReleaseChecklist ───────────────────────────────────────────────────────────


class TestReleaseChecklist:
    def test_default_not_ready(self) -> None:
        c = ReleaseChecklist()
        assert not c.ready

    def test_ready_when_all_set(self) -> None:
        c = ReleaseChecklist(
            artifacts_exist=True,
            changelog_updated=True,
            citation_cff_exists=True,
            datasheet_exists=True,
            validation_passed=True,
            gold_benchmark_exists=True,
            splits_exist=True,
            human_signoff=True,
        )
        assert c.ready

    def test_summary_includes_all_checks(self) -> None:
        c = ReleaseChecklist(artifacts_exist=True, human_signoff=True)
        s = c.summary()
        assert "All build artifacts present" in s
        assert "Human sign-off" in s
        assert "CHANGELOG.md" in s


# ── HuggingFacePublisher ───────────────────────────────────────────────────────


class TestHuggingFacePublisher:
    def test_validate_no_token(self) -> None:
        pub = HuggingFacePublisher(token="")
        errors = pub.validate()
        assert any("HF_TOKEN" in e for e in errors)

    def test_validate_missing_artifacts(self, tmp_path: Path) -> None:
        pub = HuggingFacePublisher(token="hf_test_token")
        errors = pub.validate(root=tmp_path)
        assert any("Missing" in e for e in errors)

    def test_validate_ok(self, tmp_path: Path) -> None:
        _populate_artifacts(tmp_path)
        pub = HuggingFacePublisher(token="hf_test_token")
        errors = pub.validate(root=tmp_path)
        assert errors == []

    def test_publish_dry_run(self, tmp_path: Path) -> None:
        _populate_artifacts(tmp_path)
        pub = HuggingFacePublisher(token="hf_test_token")
        result = pub.publish("v0.1.0", root=tmp_path, dry_run=True)
        assert result["dry_run"]
        assert result["repo_id"] == "scandium-labs/ssb-dataset"


# ── ZenodoPublisher ────────────────────────────────────────────────────────────


class TestZenodoPublisher:
    def test_validate_no_token(self) -> None:
        pub = ZenodoPublisher(token="")
        errors = pub.validate()
        assert any("ZENODO_TOKEN" in e for e in errors)

    def test_validate_missing_artifacts(self, tmp_path: Path) -> None:
        pub = ZenodoPublisher(token="zenodo_test_token")
        errors = pub.validate(root=tmp_path)
        assert any("Missing" in e for e in errors)

    def test_validate_ok(self, tmp_path: Path) -> None:
        _populate_artifacts(tmp_path)
        pub = ZenodoPublisher(token="zenodo_test_token")
        errors = pub.validate(root=tmp_path)
        assert errors == []

    def test_publish_dry_run(self, tmp_path: Path) -> None:
        _populate_artifacts(tmp_path)
        pub = ZenodoPublisher(token="zenodo_test_token", sandbox=True)
        result = pub.publish("v0.1.0", root=tmp_path, dry_run=True)
        assert result["dry_run"]
        assert "DRYRUN" in result["doi"]


# ── GitHubReleaser ─────────────────────────────────────────────────────────────


class TestGitHubReleaser:
    def test_validate_no_token(self) -> None:
        pub = GitHubReleaser(token="")
        errors = pub.validate()
        assert any("GITHUB_TOKEN" in e for e in errors)

    def test_publish_dry_run(self, tmp_path: Path) -> None:
        _populate_artifacts(tmp_path)
        pub = GitHubReleaser(token="gh_test_token")
        result = pub.publish("v0.1.0", root=tmp_path, dry_run=True)
        assert result["dry_run"]
        assert "v0.1.0" in result["tag"]


# ── ReleaseManager ─────────────────────────────────────────────────────────────


class TestReleaseManager:
    def test_build_checklist_all_pass(self, tmp_path: Path) -> None:
        _populate_artifacts(tmp_path, include_all=True)
        manager = ReleaseManager()
        checklist = manager.build_checklist(root=tmp_path)
        assert checklist.artifacts_exist
        assert checklist.citation_cff_exists
        assert checklist.datasheet_exists
        assert checklist.gold_benchmark_exists
        assert checklist.splits_exist
        assert checklist.validation_passed

    def test_build_checklist_validation_fails(self, tmp_path: Path) -> None:
        _populate_artifacts(tmp_path, include_all=False)
        manager = ReleaseManager()
        checklist = manager.build_checklist(root=tmp_path)
        assert not checklist.validation_passed

    def test_build_checklist_missing_artifacts(self, tmp_path: Path) -> None:
        manager = ReleaseManager()
        checklist = manager.build_checklist(root=tmp_path)
        assert not checklist.artifacts_exist

    def test_publish_all_dry_run(self, tmp_path: Path) -> None:
        _populate_artifacts(tmp_path)
        manager = ReleaseManager(
            hf_publisher=HuggingFacePublisher(token="hf_test"),
            zenodo_publisher=ZenodoPublisher(token="zenodo_test"),
            github_releaser=GitHubReleaser(token="gh_test"),
        )
        results = manager.publish_all("v0.1.0", root=tmp_path, dry_run=True)
        assert len(results) == 0  # dry_run doesn't accumulate results

    def test_print_summary_ready(self, capsys: pytest.CaptureFixture) -> None:
        c = ReleaseChecklist(
            artifacts_exist=True,
            changelog_updated=True,
            citation_cff_exists=True,
            datasheet_exists=True,
            validation_passed=True,
            gold_benchmark_exists=True,
            splits_exist=True,
            human_signoff=True,
        )
        manager = ReleaseManager()
        manager.print_summary(c)
        captured = capsys.readouterr()
        assert "All checks pass" in captured.out

    def test_print_summary_not_ready(self, capsys: pytest.CaptureFixture) -> None:
        c = ReleaseChecklist(artifacts_exist=False)
        manager = ReleaseManager()
        manager.print_summary(c)
        captured = capsys.readouterr()
        assert "Not all checks pass" in captured.out


# ── Edge Cases ─────────────────────────────────────────────────────────────────


class TestReleaseEdgeCases:
    def test_checklist_with_notes(self) -> None:
        c = ReleaseChecklist(notes=["Missing validation report", "HF token not set"])
        s = c.summary()
        assert "Missing validation report" in s
        assert "HF token not set" in s

    def test_hf_publisher_repo_id_custom(self) -> None:
        pub = HuggingFacePublisher(token="test", repo_id="custom/ssb")
        assert pub.repo_id == "custom/ssb"

    def test_zenodo_sandbox_default(self) -> None:
        pub = ZenodoPublisher(token="test")
        assert not pub.sandbox
        assert pub._base == "https://zenodo.org/api"

    def test_zenodo_sandbox_enabled(self) -> None:
        pub = ZenodoPublisher(token="test", sandbox=True)
        assert pub.sandbox
        assert pub._base == "https://sandbox.zenodo.org/api"

    def test_rollback_without_deposition(self) -> None:
        pub = ZenodoPublisher(token="test")
        pub.rollback()

    def test_release_manager_default_constructors(self) -> None:
        m = ReleaseManager()
        assert m.hf is not None
        assert m.zenodo is not None
        assert m.github is not None
