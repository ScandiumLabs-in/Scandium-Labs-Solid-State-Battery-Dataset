"""Publish the Scandium SSB dataset to Hugging Face Hub.

Builds a multi-config dataset card + flat-parquet `data/` layout and uploads it
to `Scandium-Labs/solid-state-electrolyte-conductivity`, mirroring the v1.9.0
release. HF's dataset viewer auto-detects `data/{config}/train-*.parquet`.

Configs:
    default        full canonical dataset (30,838 records, 246 columns)
    verified       the 183 literature-verified transport-label records
    consensus      the 427-material cross-paper consensus database
    gold_benchmark the 165-record gold benchmark subset

Usage:
    python scripts/publish_hf_dataset.py --dry-run      # stage locally, no upload
    python scripts/publish_hf_dataset.py                 # stage + upload + tag
    HF_TOKEN=hf_... python scripts/publish_hf_dataset.py # token via env

Never commit the HF token. It is read from --hf-token or HF_TOKEN env var only.
"""

from __future__ import annotations

import argparse
import json
import os
import shutil
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
STAGE_DIR = ROOT / "hf_publish"
DEFAULT_REPO = "Scandium-Labs/solid-state-electrolyte-conductivity"
VERSION = "v1.9.0"

CONFIGS = ("default", "verified", "consensus", "gold_benchmark")


def build_card_text() -> str:
    report = json.loads((ROOT / "release_report.json").read_text())
    n_total = report.get("total_records", 30838)
    n_verified = report.get("verified_records", 183)
    n_consensus = report.get("consensus_materials", 427)
    n_gold = 165

    return f"""---
license: cc-by-4.0
task_categories:
  - tabular-regression
  - tabular-classification
language:
  - en
tags:
  - materials-science
  - chemistry
  - battery
  - solid-state-electrolyte
  - ionic-conductivity
  - lithium-ion
  - DFT
  - machine-learning
pretty_name: Solid-State Battery Electrolyte Dataset — Ionic Conductivity & Activation Energy, Literature-Verified
size_categories:
  - 10K<n<100K
configs:
  - config_name: default
    data_files: data/default/*.parquet
  - config_name: verified
    data_files: data/verified/*.parquet
  - config_name: consensus
    data_files: data/consensus/*.parquet
  - config_name: gold_benchmark
    data_files: data/gold_benchmark/*.parquet
---

# Solid-State Battery Electrolyte Dataset — Ionic Conductivity & Activation Energy

A unified, provenance-tracked, ML-ready dataset of **solid-state battery
electrolyte** materials with literature-verified **ionic conductivity** and
**activation energy** labels — not just another Materials Project / JARVIS
structural dump. Every one of the **{n_verified} verified transport labels**
traces back to its source paper, page, and evidence sentence.

> **Honest scope:** the release contains **{n_total} bulk structural /
> thermodynamic DFT records** (Materials Project, JARVIS-DFT, COD, AFLOW, NOMAD,
> OQMD) plus **{n_verified} human-verified experimental conductivity/Ea labels**
> across 11 solid-state-electrolyte families, **{n_consensus} materials with
> cross-paper consensus statistics**, and a **{n_gold}-record gold benchmark**.
> The scarce verified labels are the asset; the bulk DFT rows are the
> structure/composition backbone for featurization.

## Ionic Conductivity Data

The `verified` config holds the literature-verified σ_RT (S/cm) and activation
energy Ea (eV) labels for solid-state battery electrolytes. Each record carries
its source DOI, measurement temperature, measurement method, conductivity type,
and sentence-level provenance evidence.

## Solid-State Electrolyte Families

All 11 major families are covered: sulfides, oxides, garnets, perovskites,
NASICONs, halides, argyrodites, hydrides, borohydrides, antiperovskites, and
polymer/composites.

## How This Dataset Was Built

An automated multi-agent pipeline: source ingestion (8 connectors) → family
classification → literature mining & LLM-assisted extraction → deterministic
verification (Arrhenius consistency, unit normalization, cross-paper consensus)
→ human review → quality scoring → validation → release. The pipeline is fully
deterministic after ingestion; no LLM calls are required to reproduce any
artifact.

## Data Splits

Splits are grouped by composition-family key to prevent leakage between
polymorphs and doped variants of the same base composition. See
`splits_metadata.json` in the source repository for the exact assignment.

## Known Limitations

- 98% of quality-scored records sit in a single "silver" tier — honest, not a
  scoring bug: experimental metadata (density, pressure, atmosphere) is sparse.
- Antiperovskites, hydrides, and borohydrides are under-covered relative to
  sulfides/garnets — this reflects the field's publication volume, not a
  sampling choice.
- Bulk DFT rows are **not** screened for solid-electrolyte relevance; check
  `family` / `negative.*` flags before use.
- 150 AFLOW rows are restricted to non-commercial use (see Licensing below).

## Licensing

Scandium-authored content is CC-BY-4.0. Third-party records retain their source
licenses (Materials Project CC-BY-4.0, JARVIS-DFT CC0, OQMD CC-BY-4.0, COD CC0,
NOMAD CC-BY-4.0, **AFLOW non-commercial only**). Per-record source is in
`identity.source_db`. See `LICENSE` and `LICENSE_BREAKDOWN.md` for the full
per-source table and the "AS IS" warranty disclaimer.

## Citation

```bibtex
@dataset{{scandium_ssb_dataset_2026,
  author       = {{Scandium Labs Team}},
  title        = {{Solid-State Battery Electrolyte Dataset — Ionic Conductivity \\& Activation Energy}},
  year         = 2026,
  version      = {VERSION},
  publisher    = {{Hugging Face / GitHub / Zenodo}},
  url          = {{https://huggingface.co/datasets/{DEFAULT_REPO}}}
}}
```

## Contact & Feedback

Open an issue on the [source repository](https://github.com/ScandiumLabs-in/Scandium-Labs-Solid-State-Battery-Dataset) for corrections, community
submissions, or questions.
"""


def build_configs() -> None:
    import pandas as pd

    data_dir = STAGE_DIR / "data"
    if data_dir.exists():
        shutil.rmtree(data_dir)
    data_dir.mkdir(parents=True)

    canonical = pd.read_parquet(ROOT / "cleaning_output" / "canonical_dataset.parquet")

    default = canonical
    verified = canonical[canonical["ion_transport.label_available"] == True]  # noqa: E712
    consensus = pd.read_parquet(ROOT / "literature_output" / "consensus_db.parquet")
    gold = pd.read_parquet(ROOT / "features_output" / "gold.parquet")

    for name, df in [("default", default), ("verified", verified), ("consensus", consensus), ("gold_benchmark", gold)]:
        out = data_dir / name
        out.mkdir(parents=True)
        df.to_parquet(out / "train-00000-of-00001.parquet", index=False)
        print(f"  staged {name}: {len(df)} rows")

    # supporting files
    for src in ["CITATION.cff", "CHANGELOG.md", "LICENSE", "LICENSE_BREAKDOWN.md"]:
        shutil.copy2(ROOT / src, STAGE_DIR / src)

    (STAGE_DIR / "README.md").write_text(build_card_text())
    print(f"  staged README.md (dataset card) in {STAGE_DIR / 'README.md'}")


def publish(hf_token: str, repo_id: str, dry_run: bool = False) -> None:
    if dry_run:
        print(f"[DRY RUN] would upload {STAGE_DIR}/ to {repo_id} (public), tag {VERSION}")
        return

    from huggingface_hub import HfApi

    api = HfApi(token=hf_token)
    api.create_repo(repo_id=repo_id, repo_type="dataset", exist_ok=True, private=False)
    api.upload_folder(
        repo_id=repo_id,
        folder_path=str(STAGE_DIR),
        path_in_repo="",
        repo_type="dataset",
        commit_message=f"Release {VERSION}: dataset card + multi-config data",
        ignore_patterns=[".git", ".gitattributes"],
    )
    api.create_tag(
        repo_id=repo_id,
        tag=VERSION,
        tag_message=f"Scandium SSB dataset {VERSION}",
        repo_type="dataset",
    )
    print(f"Published: https://huggingface.co/datasets/{repo_id} (tag {VERSION})")


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--hf-token", default=os.environ.get("HF_TOKEN", ""), help="HF token (or HF_TOKEN env). Never committed.")
    ap.add_argument("--repo-id", default=DEFAULT_REPO)
    ap.add_argument("--dry-run", action="store_true", help="stage only, no upload")
    args = ap.parse_args()

    print("Building HF staging layout...")
    build_configs()

    if args.dry_run:
        print("\nStaged at:", STAGE_DIR)
        print("Run without --dry-run to upload. Token required (--hf-token or HF_TOKEN).")
        return

    if not args.hf_token:
        print("HF_TOKEN not set. Refusing to publish without a token.", file=sys.stderr)
        sys.exit(1)

    publish(args.hf_token, args.repo_id)


if __name__ == "__main__":
    main()
