# Maintenance Plan — SSB Dataset

**Version:** 0.1.0
**Last updated:** 2026-07-29

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

- Issues: https://github.com/scandium-labs/ssb-dataset/issues
- Dataset page: https://huggingface.co/datasets/scandium-labs/ssb-dataset
- Email: scandium.labs@example.com
