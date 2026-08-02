# Contributing to the SSB Dataset

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
