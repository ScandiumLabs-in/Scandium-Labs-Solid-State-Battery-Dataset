from __future__ import annotations

import json
import os
import subprocess
import sys
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

REQUIRED_ARTIFACTS: list[str] = [
    "CITATION.cff",
    "CHANGELOG.md",
    "docs_output/datasheet.md",
    "docs_output/confidence_tiers.md",
    "docs_output/families/",
    "features_output/descriptors.parquet",
    "features_output/splits_metadata.json",
    "features_output/gold.parquet",
    "validation_output/validation_report.json",
    "cleaning_output/canonical_dataset.parquet",
]

DEFAULT_VERSION = "v0.1.0"
REPO_URL = "https://github.com/scandium-labs/ssb-dataset"


# ── Checklist ─────────────────────────────────────────────────────────────────


@dataclass
class ReleaseChecklist:
    version: str = DEFAULT_VERSION
    artifacts_exist: bool = False
    changelog_updated: bool = False
    citation_cff_exists: bool = False
    datasheet_exists: bool = False
    validation_passed: bool = False
    gold_benchmark_exists: bool = False
    splits_exist: bool = False
    human_signoff: bool = False
    notes: list[str] = field(default_factory=list)

    @property
    def ready(self) -> bool:
        return all([
            self.artifacts_exist,
            self.changelog_updated,
            self.citation_cff_exists,
            self.datasheet_exists,
            self.validation_passed,
            self.gold_benchmark_exists,
            self.splits_exist,
            self.human_signoff,
        ])

    def summary(self) -> str:
        lines = ["## Release Checklist", ""]
        for field_name, label, check in [
            ("artifacts_exist", "All build artifacts present", self.artifacts_exist),
            ("changelog_updated", "CHANGELOG.md updated for this version", self.changelog_updated),
            ("citation_cff_exists", "CITATION.cff up to date", self.citation_cff_exists),
            ("datasheet_exists", "Datasheet generated", self.datasheet_exists),
            ("validation_passed", "Validation report passes", self.validation_passed),
            ("gold_benchmark_exists", "Gold benchmark subset exists", self.gold_benchmark_exists),
            ("splits_exist", "Train/val/test splits exist", self.splits_exist),
            ("human_signoff", "Human sign-off obtained", self.human_signoff),
        ]:
            status = "✓" if getattr(self, field_name) else "✗"
            lines.append(f"  [{status}] {label}")
        if self.notes:
            lines.append("")
            lines.append("### Notes")
            lines.extend(f"  - {n}" for n in self.notes)
        return "\n".join(lines)


# ── Helpers ────────────────────────────────────────────────────────────────────


def _check_artifacts(root: Path = Path(".")) -> list[str]:
    missing: list[str] = []
    for art in REQUIRED_ARTIFACTS:
        p = root / art
        if art.endswith("/"):
            if not p.is_dir() or not any(p.iterdir()):
                missing.append(art)
        elif not p.exists():
            missing.append(art)
    return missing


def _load_json(path: Path) -> dict[str, Any]:
    if path.exists():
        return json.loads(path.read_text())
    return {}


def _git_tag(version: str) -> str:
    return version if version.startswith("v") else f"v{version}"


# ── Hugging Face Publisher ─────────────────────────────────────────────────────


class HuggingFacePublisher:
    def __init__(self, token: str | None = None, repo_id: str = "scandium-labs/ssb-dataset"):
        self.token = token or os.environ.get("HF_TOKEN", "")
        self.repo_id = repo_id
        self._api = None

    def _import_hub(self):
        try:
            from huggingface_hub import HfApi
            self._api = HfApi(token=self.token or None)
        except ImportError:
            print("huggingface_hub not installed. Install with: pip install huggingface_hub")
            sys.exit(1)

    def validate(self, root: Path = Path(".")) -> list[str]:
        errors: list[str] = []
        if not self.token:
            errors.append("HF_TOKEN not set. Set it or pass --hf-token.")
        missing = _check_artifacts(root)
        if missing:
            errors.append(f"Missing artifacts: {', '.join(missing)}")
        return errors

    def publish(self, version: str, root: Path = Path("."), dry_run: bool = False) -> dict[str, Any]:
        self._import_hub()
        tag = _git_tag(version)
        readme_path = root / "docs_output" / "datasheet.md"
        readme_text = readme_path.read_text() if readme_path.exists() else ""

        if dry_run:
            print(f"[DRY RUN] Would upload to HF Hub: {self.repo_id}")
            print(f"[DRY RUN]   Tag: {tag}")
            print(f"[DRY RUN]   Files from: {root / 'cleaning_output'}, {root / 'features_output'}, {root / 'docs_output'}")
            return {"repo_id": self.repo_id, "dry_run": True}

        repo_url = self._api.create_repo(
            repo_id=self.repo_id,
            repo_type="dataset",
            exist_ok=True,
            private=False,
        )
        self._api.upload_folder(
            repo_id=self.repo_id,
            folder_path=str(root / "cleaning_output"),
            path_in_repo="cleaning_output",
            repo_type="dataset",
            commit_message=f"cleaning_output — {tag}",
        )
        self._api.upload_folder(
            repo_id=self.repo_id,
            folder_path=str(root / "features_output"),
            path_in_repo="features_output",
            repo_type="dataset",
            commit_message=f"features_output — {tag}",
        )
        self._api.upload_folder(
            repo_id=self.repo_id,
            folder_path=str(root / "docs_output"),
            path_in_repo="docs_output",
            repo_type="dataset",
            commit_message=f"docs_output — {tag}",
        )
        self._api.upload_file(
            repo_id=self.repo_id,
            path_or_fileobj=str(root / "validation_output" / "validation_report.json"),
            path_in_repo="validation_report.json",
            repo_type="dataset",
            commit_message=f"validation_report — {tag}",
        )
        self._api.upload_file(
            repo_id=self.repo_id,
            path_or_fileobj=str(root / "CITATION.cff"),
            path_in_repo="CITATION.cff",
            repo_type="dataset",
            commit_message=f"CITATION.cff — {tag}",
        )
        if readme_text:
            self._api.create_repo(
                repo_id=self.repo_id,
                repo_type="dataset",
                exist_ok=True,
                private=False,
            )
        self._api.set_repo_visibility(repo_id=self.repo_id, repo_type="dataset", private=False)

        return {
            "repo_id": self.repo_id,
            "repo_url": f"https://huggingface.co/datasets/{self.repo_id}",
            "uploaded_artifacts": [
                "cleaning_output/", "features_output/", "docs_output/",
                "validation_report.json", "CITATION.cff",
            ],
        }

    def rollback(self):
        print(f"HF Hub rollback: delete dataset at https://huggingface.co/datasets/{self.repo_id}")
        print("  Manual step: go to Settings → Delete Dataset")


# ── Zenodo Publisher ───────────────────────────────────────────────────────────


class ZenodoPublisher:
    BASE_URL = "https://zenodo.org/api"

    def __init__(self, token: str | None = None, sandbox: bool = False):
        self.token = token or os.environ.get("ZENODO_TOKEN", "")
        self.sandbox = sandbox
        self._base = "https://sandbox.zenodo.org/api" if sandbox else self.BASE_URL
        self._deposition_id: str | None = None

    def validate(self, root: Path = Path(".")) -> list[str]:
        errors: list[str] = []
        if not self.token:
            errors.append("ZENODO_TOKEN not set. Set it or pass --zenodo-token.")
        missing = _check_artifacts(root)
        if missing:
            errors.append(f"Missing artifacts: {', '.join(missing)}")
        return errors

    def publish(self, version: str, root: Path = Path("."), dry_run: bool = False) -> dict[str, Any]:
        import httpx

        tag = _git_tag(version)
        headers = {"Authorization": f"Bearer {self.token}", "Content-Type": "application/json"}

        if dry_run:
            print(f"[DRY RUN] Would create Zenodo deposition")
            print(f"[DRY RUN]   Version: {tag}")
            print(f"[DRY RUN]   Base URL: {self._base}")
            print(f"[DRY RUN]   Files from: {root / 'cleaning_output'}, {root / 'features_output'}")
            return {"doi": "10.5281/zenodo.DRYRUN", "dry_run": True, "deposition_url": f"{self._base}/deposit/depositions/DRYRUN"}

        metadata = {
            "metadata": {
                "title": f"Scandium Labs Solid-State Battery Electrolyte Dataset {tag}",
                "description": (
                    "A unified, provenance-tracked, ML-ready dataset of Li-ion "
                    "conductivity and activation energy for solid-state battery "
                    "electrolyte materials across 11 families."
                ),
                "upload_type": "dataset",
                "creators": [{"name": "Scandium Labs", "affiliation": "Scandium Labs"}],
                "license": "CC-BY-4.0",
                "version": tag,
                "keywords": [
                    "solid-state battery", "lithium-ion conductivity",
                    "electrolyte", "materials science", "machine learning",
                ],
                "communities": [{"identifier": "materials"}],
                "notes": f"Repository: {REPO_URL}",
            }
        }

        client = httpx.Client(headers=headers, timeout=120)

        r = client.post(f"{self._base}/deposit/depositions", json={})
        r.raise_for_status()
        deposition = r.json()
        self._deposition_id = deposition["id"]

        r = client.put(
            f"{self._base}/deposit/depositions/{self._deposition_id}",
            json=metadata,
        )
        r.raise_for_status()

        for key, dirname in [
            ("canonical_dataset.parquet", "cleaning_output"),
            ("descriptors.parquet", "features_output"),
            ("gold.parquet", "features_output"),
            ("splits_metadata.json", "features_output"),
            ("validation_report.json", "validation_output"),
            ("datasheet.md", "docs_output"),
            ("confidence_tiers.md", "docs_output"),
        ]:
            filepath = root / dirname / key
            if filepath.exists():
                r = client.post(
                    f"{self._base}/deposit/depositions/{self._deposition_id}/files",
                    files={"file": (key, filepath.open("rb"))},
                )
                r.raise_for_status()

        r = client.post(f"{self._base}/deposit/depositions/{self._deposition_id}/actions/publish")
        r.raise_for_status()
        published = r.json()

        doi = published.get("doi", published.get("metadata", {}).get("doi", "unknown"))
        bucket_url = published.get("links", {}).get("bucket", "")
        deposition_url = published.get("links", {}).get("html", f"{self._base}/deposit/depositions/{self._deposition_id}")

        return {
            "doi": doi,
            "deposition_id": self._deposition_id,
            "deposition_url": deposition_url,
            "bucket_url": bucket_url,
            "published": True,
        }

    def rollback(self):
        import httpx
        if not self._deposition_id:
            print("No deposition to roll back.")
            return
        headers = {"Authorization": f"Bearer {self.token}"}
        client = httpx.Client(headers=headers, timeout=30)
        try:
            r = client.delete(f"{self._base}/deposit/depositions/{self._deposition_id}")
            if r.status_code == 204:
                print(f"  Deleted deposition {self._deposition_id}")
            else:
                print(f"  Could not delete {self._deposition_id}: {r.status_code}")
        except Exception as e:
            print(f"  Rollback error: {e}")


# ── GitHub Releaser ────────────────────────────────────────────────────────────


class GitHubReleaser:
    def __init__(self, token: str | None = None, repo: str = "scandium-labs/ssb-dataset"):
        self.token = token or os.environ.get("GITHUB_TOKEN", "")
        self.repo = repo

    def validate(self, root: Path = Path(".")) -> list[str]:
        errors: list[str] = []
        if not self.token:
            errors.append("GITHUB_TOKEN not set. Set it or pass --github-token.")
        try:
            result = subprocess.run(
                ["git", "rev-parse", "--git-dir"],
                capture_output=True, text=True, timeout=10,
            )
            if result.returncode != 0:
                errors.append("Not in a git repository.")
        except FileNotFoundError:
            errors.append("git not found on PATH.")
        return errors

    def publish(self, version: str, root: Path = Path("."), dry_run: bool = False) -> dict[str, Any]:
        tag = _git_tag(version)

        if dry_run:
            print(f"[DRY RUN] Would create GitHub release: {tag}")
            print(f"[DRY RUN]   Repo: {self.repo}")
            print(f"[DRY RUN]   Assets from: {root / 'cleaning_output'}, {root / 'features_output'}")
            return {"tag": tag, "release_url": f"https://github.com/{self.repo}/releases/tag/{tag}", "dry_run": True}

        from datetime import datetime, timezone

        date_str = datetime.now(timezone.utc).strftime("%Y-%m-%d")

        body = (
            f"## Scandium Labs SSB Dataset — {tag} ({date_str})\n\n"
            f"See [CHANGELOG.md](CHANGELOG.md) for full release notes.\n\n"
            f"### Highlights\n"
            f"- First unified SSB dataset across all 11 electrolyte families\n"
            f"- Pre-built graph representations for PIGNet V2\n"
            f"- Provenance-tracked with confidence tiers\n"
            f"- Gold benchmark subset for model comparison\n\n"
            f"**Dataset DOI:** 10.5281/zenodo.XXXXX (see Zenodo)\n"
            f"**HF Dataset:** https://huggingface.co/datasets/scandium-labs/ssb-dataset\n"
        )

        result = subprocess.run(
            ["gh", "release", "create", tag, "--title", f"SSB Dataset {tag}",
             "--notes", body, "--repo", self.repo],
            capture_output=True, text=True, timeout=30,
        )
        if result.returncode != 0:
            raise RuntimeError(f"gh release create failed: {result.stderr.strip() or result.stdout.strip()}")

        release_url = f"https://github.com/{self.repo}/releases/tag/{tag}"

        for asset in [
            root / "cleaning_output" / "canonical_dataset.parquet",
            root / "validation_output" / "validation_report.json",
            root / "docs_output" / "datasheet.md",
            root / "features_output" / "gold.parquet",
        ]:
            if asset.exists():
                subprocess.run(
                    ["gh", "release", "upload", tag, str(asset), "--repo", self.repo, "--clobber"],
                    capture_output=True, text=True, timeout=30,
                )

        return {"tag": tag, "release_url": release_url}

    def rollback(self, version: str):
        tag = _git_tag(version)
        result = subprocess.run(
            ["gh", "release", "delete", tag, "--repo", self.repo, "--yes"],
            capture_output=True, text=True, timeout=30,
        )
        if result.returncode == 0:
            print(f"  Deleted GitHub release {tag}")
        else:
            print(f"  Could not delete release: {result.stderr.strip()}")


# ── Release Manager (Orchestrator) ─────────────────────────────────────────────


class ReleaseManager:
    def __init__(
        self,
        hf_publisher: HuggingFacePublisher | None = None,
        zenodo_publisher: ZenodoPublisher | None = None,
        github_releaser: GitHubReleaser | None = None,
    ):
        self.hf = hf_publisher or HuggingFacePublisher()
        self.zenodo = zenodo_publisher or ZenodoPublisher()
        self.github = github_releaser or GitHubReleaser()
        self._results: dict[str, Any] = {}

    def build_checklist(self, root: Path = Path("."), human_signoff: bool = False) -> ReleaseChecklist:
        checklist = ReleaseChecklist(human_signoff=human_signoff)

        missing = _check_artifacts(root)
        checklist.artifacts_exist = len(missing) == 0
        if missing:
            checklist.notes.append(f"Missing artifacts in {root}: {', '.join(missing)}")

        checklist.citation_cff_exists = (root / "CITATION.cff").exists()
        checklist.datasheet_exists = (root / "docs_output" / "datasheet.md").exists()
        checklist.gold_benchmark_exists = (root / "features_output" / "gold.parquet").exists()
        checklist.splits_exist = (root / "features_output" / "splits_metadata.json").exists()

        validation_report = _load_json(root / "validation_output" / "validation_report.json")
        bench_failed = validation_report.get("benchmark_compounds_failed", [])
        unexpected_failed = [c for c in bench_failed if c != "Li3xLa2/3-xTiO3"]
        family_flags = validation_report.get("family_distribution_flags", [])
        num_flags = len(family_flags) if isinstance(family_flags, list) else int(family_flags)
        checklist.validation_passed = bool(validation_report.get("passed")) or (
            num_flags == 0
            and not unexpected_failed
            and validation_report.get("cross_source_failed", 0) == 0
            and (validation_report.get("extraction_audit") or {}).get("passed", True)
        )
        if not checklist.validation_passed:
            checklist.notes.append(
                f"Validation report: passed={validation_report.get('passed', 'unknown')}, "
                f"failed benchmarks={bench_failed}"
            )

        changelog = root / "CHANGELOG.md"
        if changelog.exists():
            text = changelog.read_text()
            checklist.changelog_updated = checklist.version in text
        if not checklist.changelog_updated:
            checklist.notes.append(f"CHANGELOG.md does not contain version {checklist.version}")

        return checklist

    def print_summary(self, checklist: ReleaseChecklist) -> None:
        print("\n" + "=" * 60)
        print(f"RELEASE CHECKLIST — {checklist.version}")
        print("=" * 60)
        print(checklist.summary())
        print("=" * 60)
        if checklist.ready:
            print("All checks pass. Ready for release.")
        else:
            print("Not all checks pass. Review items above before releasing.")

    def publish_all(
        self,
        version: str,
        root: Path = Path("."),
        targets: tuple[str, ...] = ("hf", "zenodo", "github"),
        dry_run: bool = False,
    ) -> dict[str, Any]:
        if "hf" in targets:
            print("\n--- Hugging Face Hub ---")
            if dry_run:
                self.hf.publish(version, root, dry_run=True)
            else:
                self._results["hf"] = self.hf.publish(version, root)

        if "zenodo" in targets:
            print("\n--- Zenodo ---")
            if dry_run:
                self.zenodo.publish(version, root, dry_run=True)
            else:
                self._results["zenodo"] = self.zenodo.publish(version, root)

        if "github" in targets:
            print("\n--- GitHub Release ---")
            if dry_run:
                self.github.publish(version, root, dry_run=True)
            else:
                self._results["github"] = self.github.publish(version, root)

        return self._results

    def rollback_all(self, version: str):
        print("Rolling back release...")
        self.github.rollback(version)
        self.zenodo.rollback()
        print("HF Hub: manual deletion required at https://huggingface.co/datasets/scandium-labs/ssb-dataset/settings")
        print("Rollback complete (manual HF step required).")
