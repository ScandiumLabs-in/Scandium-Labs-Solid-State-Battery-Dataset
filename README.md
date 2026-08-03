# Scandium Labs - Solid-State Battery Materials Dataset

A literature-derived dataset of solid-state battery (SSB) electrolyte materials:
ionic conductivity (σ) and activation energy (Ea) labels that are **evidence-verified
to the sentence level**, layered on a DFT structural backbone. The core scientific
value is the measured σ/Ea labels, which are scarce: they are hand-checked against
the source paper (verbatim evidence sentence + page + DOI) and pass a rigorous
deterministic check chain (`Arrhenius` sanity, σ-specific digit-match, copy-paste /
duplicate-value detection). This is an **eval / benchmark set and a self-supervised
pretraining target**, not yet a full supervised GNN-training set — measured σ_RT
values for solid electrolytes are genuinely rare in the literature, so the honest
use is as a clean benchmark, few-shot fine-tuning set, or pretraining target over
the ~30k unlabeled DFT structures.

## Project Files

| File | Purpose |
|---|---|
| `scandium-ssb-dataset-guide.md` | The complete phase-wise build guide — schema, sourcing, pipeline design, validation, release, and maintenance plan. Start here. |
| `AGENTS.md` | Defines the agent roles that execute the pipeline (or the human roles, if run manually) — input/output contracts and escalation rules per phase. |
| `SKILLS.md` | Skills/expertise required across the build, mapped to phases — use to spot gaps before a phase starts. |
| `TOOLS.md` | Consolidated tool, library, and API reference with a pre-Phase-1 access checklist. |
| `CONTRIBUTING.md` | How external labs/contributors can submit new measured values once the dataset is public. |
| `CHANGELOG.md` | Version history — starts at project setup, first real entry lands at v1.0 release. |

## Quick Start

1. Read `scandium-ssb-dataset-guide.md` Section 0–2 (design principles + schema) — nothing downstream makes sense without this.
2. Check `TOOLS.md`'s access checklist before starting Phase 1.
3. Use `AGENTS.md` to assign phase ownership (whether to a person or an automated agent).
4. Use `SKILLS.md` to flag any gap before it becomes a Phase 5 or Phase 3 bottleneck (the two hardest phases).

## Status

<!-- status-begin -->
**Status (auto-generated from `release_report.json` — do not edit by hand).** Version **v0.2.0**, generated 2026-08-03T12:48:47.209956+00:00. Release gates: **ALL PASS**.

| Bucket | Count | What it is |
|---|---|---|
| **Bulk structural records** | ~30071 | DFT-native pulls (Materials Project / JARVIS / NOMAD / COD / etc.), Li-containing catalog. **Not screened for SSE relevance** — the dump includes cathode chemistries that share the Li+O+metal formula pattern. |
| **Verified experimental labels** | 116 | Evidence-linked σ/Ea from literature mining, **human-reviewed**, provenance-tracked to the sentence level. The scarce valuable asset. |
| **Consensus (n≥3 papers)** | 24 | Cross-paper consensus: only 24 materials have ≥3 independent papers. |

> **Honest caveat.** Of the ~30071 records, only **116 carry human-verified conductivity/Ea labels**; the remainder are structural/thermodynamic DFT records *without* transport labels. Quality-tier distribution: silver 97.4%, rejected 2.6%. See `quality_output/quality_report.json` and `release_report.json` — stated up front so the rest of the dataset's claims are credible.

> *This block is generated. Run `python scripts/sync_readme_status.py` (or any `scripts/release.py` invocation) to regenerate; if it disagrees with the report, regenerate — never hand-edit.*
<!-- status-end -->
