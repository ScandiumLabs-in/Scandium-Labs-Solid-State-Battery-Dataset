# Oxide

**Family:** `oxide`

**Records:** 20548
**Records with conductivity label:** 5

## Description

Oxide-based Li-ion conductors not captured by more specific oxide families (garnet, perovskite, NASICON, antiperovskite). Broad class including simple oxides and complex oxide frameworks.

## Known Quirks

- **Cathode contamination (main issue):** The bulk MP/JARVIS oxide bucket is dominated by intercalation cathode materials (LiCoO2, LiMn2O4, LiNiO2, NMC). These carry the `oxide` family tag but have `is_electrolyte_candidate=False`. Always filter on `is_electrolyte_candidate` before computing oxide electrolyte statistics — without it the apparent oxide conductivity distribution is polluted by cathode non-conductors.
- **Broad catch-all:** Garnet, NASICON, perovskite, and antiperovskite are classified by their own rules and never reach the oxide bucket. The remaining oxides (LIPON precursors, LiAlO2, Li2ZrO3, etc.) are structurally diverse with no single σ/Ea centre; median values are less meaningful than for other families.
- **Doped garnets with Co/Mn/Ni:** Co-doped LLZO (Li7La3Zr1.5Co0.5O12, a real dopant) is correctly classified as `garnet` and kept as `is_electrolyte_candidate=True`. The cathode-exclusion logic was narrowed to the oxide/unknown buckets only (v0.3.2 fix).

## Schema Notes

- `ion_transport.sigma_RT`: Room-temperature conductivity in S/cm.
- `ion_transport.activation_energy_Ea`: Activation energy in eV.
- `ion_transport.temperature_range_measured`: Dict with `min_K` and `max_K`.
