# SSB Dataset — Quick Start Usage Guide

**Target audience:** University electrochemistry labs and materials ML researchers.

## Getting the Data

### Option 1: Hugging Face Datasets (recommended)

```python
from datasets import load_dataset

ds = load_dataset("scandium-labs/ssb-dataset", split="train")
print(ds[0])
```

### Option 2: Zenodo DOI

Download the canonical dataset Parquet file from Zenodo:
10.5281/zenodo.XXXXX

### Option 3: GitHub Releases

Download release assets from: https://github.com/scandium-labs/ssb-dataset/releases

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
print(f"Records: {len(df)}")
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
https://github.com/scandium-labs/ssb-dataset/issues/new?template=data_submission.md

## Citation

```bibtex
@software{scandium_labs_ssb_dataset,
  title = {Scandium Labs Solid-State Battery Electrolyte Dataset},
  version = {0.1.0},
  doi = {10.5281/zenodo.XXXXX},
  publisher = {Zenodo},
  license = {CC-BY-4.0},
  year = 2026,
}
```
