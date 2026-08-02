# Polymer / Composite

**Family:** `polymer_composite`

**Records:** 11
**Records with conductivity label:** 2

## Description

Polymer/ceramic composite electrolytes (e.g., PEO-LiTFSI with ceramic fillers). Standard crystal-graph featurization does not apply.

## Known Quirks

**Note:** This family uses a parallel featurization path. Standard crystal-graph representation does not apply. See `polymer_feature_columns()` for available features.

## Schema Notes

- `ion_transport.sigma_RT`: Room-temperature conductivity in S/cm.
- `ion_transport.activation_energy_Ea`: Activation energy in eV.
- `ion_transport.temperature_range_measured`: Dict with `min_K` and `max_K`.
