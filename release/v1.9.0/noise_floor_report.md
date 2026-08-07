# Experimental noise floor (guide §5 action 3)

OBELiX-style reproducibility floor: within each (composition[, conductivity-type]) group with >=2 independent sigma measurements, deviation of every value from its group mean/median in log10(sigma_S_per_cm).

- Repeat-measurement groups: **76** (across 427 materials, 596 sigma measurements; 206 entries inside repeat groups).

- **RMS deviation from group means (log10 σ): 0.354**
- **MAD from group medians (log10 σ): 0.153**

OBELiX reference (48 groups / 122 entries): RMS 0.63, MAD 0.41.

Interpretation:
A model's test-set MAE in log10(sigma) below the noise-floor MAD is very likely overfit: it cannot be more accurate than the experimental measurement process itself.

Largest repeat groups (spread = max−min in log10 σ):

| group | n | log10 mean | spread |
|---|---|---|---|
| Li7La3Zr2O12::total | 19 | -3.714 | 2.240 |
| Li1.3Ti1.7Al0.3P3O12::total | 10 | -3.980 | 2.000 |
| Li6PS5Cl::total | 10 | -2.976 | 0.112 |
| Li3InCl6::total | 8 | -2.647 | 0.605 |
| Li2ZrCl6::total | 5 | -3.391 | 0.886 |
| Li6.5La3Zr1.5Ta0.5O12::total | 5 | -3.457 | 0.745 |
| Sr0.4375Li0.375Zr0.25Ta0.75O3::bulk | 4 | -3.188 | 0.535 |
| Li10Ge(PS6)2::total | 3 | -1.974 | 0.079 |
| Li2HClO::total | 3 | -6.190 | 1.009 |
| Li3ClO::total | 3 | -5.329 | 2.507 |
| Li3YCl6::total | 3 | -4.233 | 1.398 |
| Mg1B21.47H88.88N1::total | 3 | -3.277 | 0.438 |
| Na3PS4::bulk | 3 | -4.667 | 1.000 |
| PEO-LiTFSI::total | 3 | -5.163 | 2.255 |
| 0.7Li(CB9H10)-0.3Li(CB11H12)::total | 2 | -2.174 | 0.000 |
| 80(3LiBH4LiCl)20P2S5::total | 2 | -5.000 | 0.000 |
| Ca-CeO2/LiTFSI/PEO::total | 2 | -3.886 | 0.000 |
| Cs1In0.067Sn0.9Cl3::total | 2 | -3.479 | 0.033 |
| H4C2O::total | 2 | -4.094 | 1.277 |
| Li(BH4)1-xIx::total | 2 | -4.310 | 0.000 |
