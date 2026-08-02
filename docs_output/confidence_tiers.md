# Confidence Tier System

Every record in the SSB Dataset carries a `confidence_tier` field indicating
the trustworthiness of its data. This is the dataset's primary quality signal.

## Tiers (highest to lowest confidence)

### `verified_human`
- **Source:** Hand-curated by a domain expert
- **When used:** Benchmark compounds (Section 17) and gold subset
- **Trust:** Maximum — these records are the dataset's quality anchor

### `dft_native`
- **Source:** Pulled directly from Materials Project, JARVIS-DFT, AFLOW, OQMD,
  NOMAD, or ICSD via their APIs
- **Trust:** High — DFT data from established, peer-reviewed repositories

### `dft_computed_inhouse`
- **Source:** Computed in-house via VASP/Quantum Espresso (Phase 5)
- **Trust:** High — follows MP's calculation scheme for schema compatibility
- **Note:** These are structural/thermodynamic properties only; conductivity
  labels are not computed at this tier unless explicitly marked AIMD

### `high_confidence_extraction`
- **Source:** Extracted from literature via GROBID + LLM with confidence score >= 0.85
- **Trust:** Moderate-high — but ALWAYS check against seed set accuracy

### `low_confidence_extraction`
- **Source:** Extracted from literature with confidence score < 0.85
- **Trust:** Low — use primarily for exploratory analysis, not for publications

## Usage Guidelines

1. **For training:** Filter to `dft_native` + `high_confidence_extraction` for
   structural/thermodynamic targets; use `verified_human` for conductivity labels.
2. **For benchmarking:** Only use `verified_human` records from the gold subset.
3. **For publication:** Clearly state which confidence tiers your analysis uses.
   Never blend tiers silently in reported statistics.

## Field-Level vs Row-Level Confidence

Future versions will support field-level confidence (e.g., a row might have
dft_native structure but literature_mined conductivity). Currently, confidence
is at the row level and reflects the least-trusted source in that row.
