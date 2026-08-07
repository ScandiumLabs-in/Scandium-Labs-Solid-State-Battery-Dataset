"""Phase 10 — Maintenance documentation generators.

Produces:
  - CONTRIBUTING.md       — community contribution guide
  - MAINTENANCE.md        — maintenance cadence & plan
  - DEPRECATION.md        — deprecation policy
  - USAGE_GUIDE.md        — quick start for university labs
  - Issue templates       — bug report, data submission, feature request
  - PR template           — structured pull request template
"""

from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path

REPO_URL = "https://github.com/ScandiumLabs-in/Scandium-Labs-Solid-State-Battery-Dataset"
HF_DATASET_URL = "https://huggingface.co/datasets/Scandium-Labs/solid-state-electrolyte-conductivity"


def generate_contributing(output_path: str | Path) -> str:
    content = """# Contributing to the SSB Dataset

Thank you for your interest in contributing to the Scandium Labs Solid-State
Battery Electrolyte Dataset. We welcome community contributions — especially
experimentally measured ionic conductivity values from academic labs.

## Ways to Contribute

### 1. Submit a New Conductivity Measurement

If your lab has measured ionic conductivity or activation energy for an SSB
electrolyte, we want it. Use the **Data Submission** issue template.

We ask for:
- Composition (exact formula)
- Room-temperature conductivity (sigma_RT) in S/cm
- Activation energy (Ea) in eV
- Measurement method (EIS, DC polarization, etc.)
- Temperature range
- DOI or citation for the source paper
- Crystal structure / space group if available

### 2. Report an Error

Found a wrong conductivity value, a misclassified compound, or a broken link?
Open a **Bug Report** issue with the specific record ID and the correction.

### 3. Suggest a New Feature

Ideas for additional data sources, featurization methods, or dataset extensions?
Open a **Feature Request** issue.

### 4. Code Contributions

PRs are welcome for:
- New source connectors (Phase 2)
- Extraction pipeline improvements (Phase 3)
- Cleaning/dedup rule improvements (Phase 4)
- Featurization descriptors (Phase 6)
- Validation checks (Phase 7)

## PR Process

1. Open an issue first to discuss the change.
2. Fork the repo and create a feature branch.
3. Run `pytest tests/` — all tests must pass.
4. Update relevant documentation.
5. Open a PR using the PR template.

## Code Standards

- Python 3.10+ with type annotations
- Follow existing patterns (pydantic models, dataclass config, pytest tests)
- No silent imputation of conductivity labels (the scarce label principle)
- Every new feature must have tests

## License

By contributing, you agree that your contributions will be licensed under
CC-BY-4.0, matching the dataset license.
"""
    _write(path := Path(output_path), content)
    return content


def generate_maintenance_plan(output_path: str | Path) -> str:
    content = f"""# Maintenance Plan — SSB Dataset

**Version:** 0.1.0
**Last updated:** {datetime.now(timezone.utc).strftime("%Y-%m-%d")}

## Cadence

| Activity | Frequency | Owner |
|----------|-----------|-------|
| Source re-ingestion (MP, JARVIS, AFLOW, OQMD, NOMAD) | Quarterly | Scandium Labs |
| Literature-mining pass (new papers since last pass) | Quarterly | Scandium Labs |
| Community submission review & integration | Rolling (as received) | Scandium Labs |
| Dependency updates (pymatgen, huggingface_hub, etc.) | Per release | Scandium Labs |
| Validation re-audit (gold benchmark verification) | Per release | Scandium Labs |
| Public release (vX.Y) | Semi-annual | Scandium Labs |

## Versioning Scheme

We follow [Semantic Versioning 2.0.0](https://semver.org/):

- **MAJOR** — breaking schema changes, removed fields, reorganized structure
- **MINOR** — new sources, new families, new featurization, new features
- **PATCH** — bug fixes, additional validation, documentation updates

Pre-release tags: `v1.0.0-alpha.1`, `v1.0.0-rc.1` for review candidates.

## Source Re-Ingestion Process

1. Re-run Phase 2 ingestion for each source (incremental if supported).
2. Classify new records into families (Phase 2 classifier).
3. Run Phase 4 cleaning & dedup against full dataset.
4. Run Phase 7 validation — all benchmarks must pass.
5. If new compositions lack conductivity labels, add to DFT priority queue (Phase 5).
6. Regenerate splits (Phase 6) and documentation (Phase 8).
7. Run release checklist (Phase 9) — human sign-off required.

## Community Submission Integration

1. Submitter opens an issue with measured data.
2. Reviewer validates against known ranges (Arrhenius plausibility, etc.).
3. Data is entered into a structured submission record (temp CSV).
4. Next maintenance release batch-integrates all accepted submissions.
5. Submitter is acknowledged in CHANGELOG.md.

## Backward Compatibility

- PATCH releases preserve full backward compatibility.
- MINOR releases deprecate fields but keep them for one release cycle.
- MAJOR releases document all breaking changes in upgrading guide.

## Communication Channels

- Issues: {REPO_URL}/issues
- Dataset page: {HF_DATASET_URL}
- Email: scandium.labs@example.com
"""
    _write(path := Path(output_path), content)
    return content


def generate_deprecation_policy(output_path: str | Path) -> str:
    content = f"""# Deprecation Policy — SSB Dataset

## Principles

1. **No silent removal.** Every removed or renamed field goes through a
   documented deprecation cycle.
2. **One-release notice.** Fields slated for removal are marked deprecated
   in one MINOR release and removed in the next MAJOR release.
3. **Migration path.** Deprecated fields include a recommended replacement
   and codemod instructions.

## Deprecation Lifecycle

| Phase | Status | Action |
|-------|--------|--------|
| Active | `active` | Fully supported |
| Deprecated | `deprecated` | Still present but emits a warning; slated for removal |
| Removed | `removed` | Field no longer exists in schema |

## Current Deprecations (v0.1.0)

None. This is the initial release.

## How to Deprecate a Field

1. Open a GitHub issue with the deprecation proposal.
2. Add `_deprecated` suffix in the schema (or add `deprecated=True` metadata).
3. Update all documentation to reference the replacement.
4. Add a runtime warning when the field is accessed.
5. Remove in the next MAJOR release.

## Exceptions

- Fields that expose a security vulnerability may be removed immediately
  with a PATCH release.
- Fields that were never documented or populated may be removed without
  deprecation.

## Contact

For questions about this policy: {REPO_URL}/issues
"""
    _write(path := Path(output_path), content)
    return content


def generate_usage_guide(output_path: str | Path) -> str:
    content = f"""# SSB Dataset — Quick Start Usage Guide

**Target audience:** University electrochemistry labs and materials ML researchers.

## Getting the Data

### Option 1: Hugging Face Datasets (recommended)

```python
from datasets import load_dataset

ds = load_dataset("Scandium-Labs/solid-state-electrolyte-conductivity", name="default", split="train")
print(ds[0])
```

### Option 2: Zenodo DOI

Download the canonical dataset Parquet file from Zenodo:
10.5281/zenodo.XXXXX

### Option 3: GitHub Releases

Download release assets from: {REPO_URL}/releases

## Dataset Structure

```
cleaning_output/
  canonical_dataset.parquet   # Main dataset (all records)
features_output/
  descriptors.parquet         # With composition & symmetry descriptors
  splits_metadata.json        # Train/val/test split indices
  gold.parquet                # Gold benchmark subset
docs_output/
  datasheet.md                # Full Datasheet for Datasets
  confidence_tiers.md         # Confidence tier documentation
  families/                   # Per-family READMEs
validation_output/
  validation_report.json      # Validation report
```

## Quick Exploration (Pandas)

```python
import pandas as pd

df = pd.read_parquet("cleaning_output/canonical_dataset.parquet")
print(f"Records: {{len(df)}}")
print(df["identity.family"].value_counts())
print(df["ion_transport.sigma_RT"].describe())
```

## Recommended Workflow for Lab Use

1. **Browse** the data by family using `pandas`.
2. **Filter** by confidence tier (`verified_human` or `dft_native`).
3. **Train** your model on the provided splits (`train`/`val`/`test`).
4. **Benchmark** against the gold subset.
5. **Publish** and cite the dataset via Zenodo DOI.

## Confidence Tier Quick Reference

| Tier | Meaning | Use for |
|------|---------|---------|
| `verified_human` | Hand-curated | Gold standard, benchmarking |
| `dft_native` | From MP/JARVIS/AFLOW/OQMD/NOMAD/ICSD | Training |
| `dft_computed_inhouse` | In-house VASP/QE | Augmenting training |
| `high_confidence_extraction` | Literature-mined, score >= 0.85 | Training (with caution) |
| `low_confidence_extraction` | Literature-mined, score < 0.85 | Exploratory only |

## Submitting Your Own Measurements

See CONTRIBUTING.md or open a Data Submission issue at:
{REPO_URL}/issues/new?template=data_submission.md

## Citation

```bibtex
@software{{scandium_labs_ssb_dataset,
  title = {{Scandium Labs Solid-State Battery Electrolyte Dataset}},
  version = {{0.1.0}},
  doi = {{10.5281/zenodo.XXXXX}},
  publisher = {{Zenodo}},
  license = {{CC-BY-4.0}},
  year = 2026,
}}
```
"""
    _write(path := Path(output_path), content)
    return content


def generate_issue_templates(output_dir: str | Path) -> list[str]:
    paths: list[str] = []
    templates = {
        "bug_report.md": {
            "name": "Bug Report",
            "about": "Report an error in the dataset or pipeline",
            "fields": [
                "**Describe the bug**",
                "**Record ID (if applicable)**",
                "**Expected value**",
                "**Actual value**",
                "**Steps to reproduce**",
                "**Environment (OS, Python version)**",
            ],
        },
        "data_submission.md": {
            "name": "Data Submission",
            "about": "Submit experimentally measured conductivity data",
            "fields": [
                "**Composition (exact formula)**",
                "**Room-temperature conductivity (sigma_RT, S/cm)**",
                "**Activation energy (Ea, eV)**",
                "**Measurement method**",
                "**Temperature range (K)**",
                "**DOI or citation**",
                "**Crystal structure / space group (if known)**",
                "**Notes**",
            ],
        },
        "feature_request.md": {
            "name": "Feature Request",
            "about": "Suggest an enhancement to the dataset or pipeline",
            "fields": [
                "**Is your feature request related to a problem?**",
                "**Describe the solution you'd like**",
                "**Describe alternatives you've considered**",
                "**Additional context**",
            ],
        },
    }

    base = Path(output_dir)
    base.mkdir(parents=True, exist_ok=True)

    for filename, tmpl in templates.items():
        lines = [
            "---",
            f"name: {tmpl['name']}",
            f"about: {tmpl['about']}",
            "title: \"\"",
            "labels: \"\"",
            "assignees: \"\"",
            "---",
            "",
        ]
        for f in tmpl["fields"]:
            lines.append(f"{f}")
            lines.append("")
        content = "\n".join(lines)
        path = base / filename
        path.write_text(content)
        paths.append(str(path))

    return paths


def generate_pr_template(output_path: str | Path) -> str:
    content = """---
name: Pull Request
about: Submit changes to the dataset pipeline
---

## Description

<!-- Describe the change and motivation. Link to related issue. -->

## Type of Change

- [ ] Bug fix
- [ ] New feature
- [ ] Documentation update
- [ ] Data update (new records / corrections)
- [ ] Dependency update

## Checklist

- [ ] All existing tests pass (`pytest tests/`)
- [ ] New tests added for new functionality
- [ ] Type annotations added
- [ ] Documentation updated (if applicable)
- [ ] CHANGELOG.md updated

## Testing

<!-- Describe how you tested the change -->

## Related Issue

Closes #

## Additional Notes
"""
    _write(path := Path(output_path), content)
    return content


def _write(path: Path, content: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content)
