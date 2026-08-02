# Scandium Labs — Solid-State Battery Materials Dataset

The single best one-stop, ML-ready dataset of solid-state battery (SSB) electrolyte materials, spanning all 8 SSB electrolyte families, built for training physics-informed GNNs (PIGNet V2 and beyond) and for adoption by university electrochemistry labs.

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

Pre-Phase-0. No data ingested yet. This README and its companion files are the planning artifacts; the dataset itself does not exist until Phase 2 produces the first staging pull.
