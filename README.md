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

**Active.** v0.3.x development build. The dataset is real and growing; all release gates pass. This README and the companion files are living artifacts kept in lock-step with the data (see `CHANGELOG.md`).

The dataset is three things of differing maturity, stated honestly:

| Bucket | Count | What it is |
|---|---|---|
| **Bulk structural records** | ~30,071 | DFT-native pulls (Materials Project / JARVIS / NOMAD), Li-containing full catalog. **Not screened for SSE relevance** — e.g. `oxide` is ~68% of the dump and includes cathode chemistries (`LiCoO2`-type) that share the Li+O+metal formula pattern. Pending an electrolyte-candidate filter. |
| **Verified experimental labels** | 116 | Evidence-linked σ/Ea from literature mining, **human-reviewed**, provenance-tracked to the sentence level. The scarce valuable asset. |
| **Consensus database** | 387 materials / 942 measurements | Cross-paper consensus: only **20 materials** have n≥3 independent papers (real consensus); 28/387 are `verified` tier, 30 `high`, 276 `needs-verification`. |

> Framing: the current verified labels (116–150 across 8 families) are at the
> realistic ceiling for OA literature mining, and match the low-hundreds range of
> published conductivity compilations. They support a clean eval/benchmark set,
> few-shot fine-tuning, and self-supervised pretraining on the unlabeled structures —
> not yet large-scale supervised training. See `docs/calibration_history.md` and
> `docs/blocked_doi_segmentation.md` for the honest limits.
