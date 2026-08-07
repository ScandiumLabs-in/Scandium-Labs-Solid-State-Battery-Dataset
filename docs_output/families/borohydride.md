# Borohydride

**Family:** `borohydride`

**Records:** 114
**Records with conductivity label:** 6

## Description

Borohydride Li-ion conductors (LiBH4, Li2B12H12). High-temperature phase transitions enable fast Li transport.

## Known Quirks

- **Phase-transition conductivity jump:** LiBH4 undergoes an orthorhombic→hexagonal phase transition near 390 K; conductivity jumps ~3 orders of magnitude at that temperature. Records reporting σ at T < 390 K (low-phase) and T > 390 K (high-phase) are both valid but not comparable — always check `temperature_celsius` before comparing within this family.
- **Wide Ea range:** Reported activation energies range from ~0.2 eV (nanoconfined or composite LiBH4) to ~1.7 eV (bulk low-temperature phase). The lower bound is supported by nanoconfinement/composite literature (e.g. LiBH4 in SBA-15 scaffolds); the upper bound by bulk Arrhenius fits below the phase transition. The validation range was widened from (0.30–0.90) eV to (0.20–1.70) eV in v0.3.2 to accommodate both regimes — see `docs/calibration_history.md` for the citation.
- **Closo-borane derivatives (Li2B12H12, LiCB11H12):** These are polyanion materials with distinct transport mechanism (polyanion reorientation) and much higher RT conductivity (up to ~10⁻³ S/cm). They share the `borohydride` family tag by composition but behave very differently from simple LiBH4.

## Schema Notes

- `ion_transport.sigma_RT`: Room-temperature conductivity in S/cm.
- `ion_transport.activation_energy_Ea`: Activation energy in eV.
- `ion_transport.temperature_range_measured`: Dict with `min_K` and `max_K`.
