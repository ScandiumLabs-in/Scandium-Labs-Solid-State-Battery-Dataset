# ScandiumBench v1.0 — split-regime leaderboard

Generated 2026-08-07T01:39:55 · 25 tasks × 4 split regimes · deterministic sklearn baselines (dummy / linear / random forest).

Split regimes: **random** (Phase-6 leakage-checked, reused), **family_ood** (test chemistries never seen in train), **composition_ood** (no composition in both train and test), **crystal_system_ood** (test crystal systems unseen in train).

### Formation energy regression (`formation_energy_regression`, metric=mae)

| Regime | n_train | n_test | Best model | Value | Eval |
|---|---|---:|---|---|---|
| random | 16394 | 3248 | rf | 0.0669 | split_test |
| family_ood | 20543 | 9312 | rf | 1.0058 | split_test |
| composition_ood | 20682 | 5540 | rf | 0.1626 | split_test |
| crystal_system_ood | 12830 | 15164 | ridge | 0.6435 | split_test |

### Band gap regression (`band_gap_regression`, metric=mae)

| Regime | n_train | n_test | Best model | Value | Eval |
|---|---|---:|---|---|---|
| random | 16394 | 3248 | rf | 0.4304 | split_test |
| family_ood | 20543 | 9312 | rf | 0.8830 | split_test |
| composition_ood | 20682 | 5540 | rf | 0.5249 | split_test |
| crystal_system_ood | 12830 | 15164 | rf | 0.6359 | split_test |

### Energy above hull regression (`energy_above_hull_regression`, metric=mae)

| Regime | n_train | n_test | Best model | Value | Eval |
|---|---|---:|---|---|---|
| random | 15064 | 3228 | rf | 0.0352 | split_test |
| family_ood | 16312 | 5216 | dummy | 0.1928 | split_test |
| composition_ood | 14734 | 3996 | rf | 0.0443 | split_test |
| crystal_system_ood | 12830 | 6837 | rf | 0.0997 | split_test |

### Bulk modulus regression (`bulk_modulus_regression`, metric=mae)

| Regime | n_train | n_test | Best model | Value | Eval |
|---|---|---:|---|---|---|
| random | 1126 | 143 | rf | 13.1247 | split_test |
| family_ood | 616 | 2492 | ridge | 29.7131 | split_test |
| composition_ood | 2253 | 568 | rf | 20.9401 | split_test |
| crystal_system_ood | 710 | 2242 | dummy | 33.7909 | split_test |

### Shear modulus regression (`shear_modulus_regression`, metric=mae)

| Regime | n_train | n_test | Best model | Value | Eval |
|---|---|---:|---|---|---|
| random | 1036 | 138 | rf | 12.4580 | split_test |
| family_ood | 601 | 2327 | rf | 18.1220 | split_test |
| composition_ood | 2120 | 540 | rf | 14.1652 | split_test |
| crystal_system_ood | 668 | 2107 | ridge | 19.0254 | split_test |

### Debye temperature regression (`debye_temperature_regression`, metric=mae)

| Regime | n_train | n_test | Best model | Value | Eval |
|---|---|---:|---|---|---|
| random | 581 | 130 | rf | 54.8391 | split_test |
| family_ood | 103 | 723 | rf | 93.2027 | split_test |
| composition_ood | 590 | 154 | rf | 55.4565 | split_test |
| crystal_system_ood | 826 | 826 | rf | 92.7500 | grouped_cv_k5 |

### Density regression (`density_regression`, metric=mae)

| Regime | n_train | n_test | Best model | Value | Eval |
|---|---|---:|---|---|---|
| random | 16394 | 3248 | rf | 0.1183 | split_test |
| family_ood | 20543 | 9312 | ridge | 1.7779 | split_test |
| composition_ood | 20682 | 5540 | rf | 0.4103 | split_test |
| crystal_system_ood | 12830 | 15164 | rf | 0.8586 | split_test |

### Volume regression (`volume_regression`, metric=mae)

| Regime | n_train | n_test | Best model | Value | Eval |
|---|---|---:|---|---|---|
| random | 16394 | 3248 | rf | 14.5481 | split_test |
| family_ood | 20543 | 9312 | rf | 75.4315 | split_test |
| composition_ood | 20682 | 5540 | rf | 17.1382 | split_test |
| crystal_system_ood | 12830 | 15164 | ridge | 43.6594 | split_test |

### Ionic-radius regression (`ionic_radius_regression`, metric=mae)

| Regime | n_train | n_test | Best model | Value | Eval |
|---|---|---:|---|---|---|
| random | 15064 | 3228 | rf | 0.0081 | split_test |
| family_ood | 16312 | 5216 | rf | 0.1366 | split_test |
| composition_ood | 14734 | 3996 | rf | 0.0128 | split_test |
| crystal_system_ood | 12830 | 6837 | rf | 0.0067 | split_test |

### Stable vs unstable classification (`stability_classification`, metric=macro_f1)

| Regime | n_train | n_test | Best model | Value | Eval |
|---|---|---:|---|---|---|
| random | 15064 | 3228 | rf | 0.9260 | split_test |
| family_ood | 16312 | 5216 | rf | 0.6744 | split_test |
| composition_ood | 14734 | 3996 | rf | 0.9323 | split_test |
| crystal_system_ood | 12830 | 6837 | rf | 0.9580 | split_test |

### Wide-gap classification (E_g > 4 eV) (`wide_gap_classification`, metric=macro_f1)

| Regime | n_train | n_test | Best model | Value | Eval |
|---|---|---:|---|---|---|
| random | 11566 | 2298 | rf | 0.8254 | split_test |
| family_ood | 14360 | 4211 | logistic | 0.6538 | split_test |
| composition_ood | 12894 | 3391 | rf | 0.8257 | split_test |
| crystal_system_ood | 8878 | 8708 | rf | 0.6056 | split_test |

### Family classification (`family_classification`, metric=macro_f1)

| Regime | n_train | n_test | Best model | Value | Eval |
|---|---|---:|---|---|---|
| random | 17046 | 3370 | rf | 0.8217 | split_test |
| family_ood | 20753 | 10085 | dummy | 0.0652 | split_test |
| composition_ood | 20682 | 6523 | logistic | 0.5473 | split_test |
| crystal_system_ood | 12830 | 16147 | rf | 0.3223 | split_test |

### Crystal system prediction (`crystal_system_classification`, metric=macro_f1)

| Regime | n_train | n_test | Best model | Value | Eval |
|---|---|---:|---|---|---|
| random | 15064 | 3228 | rf | 0.8358 | split_test |
| family_ood | 16312 | 5216 | rf | 0.5295 | split_test |
| composition_ood | 14734 | 3996 | rf | 0.8393 | split_test |
| crystal_system_ood | 12830 | 6837 | rf | 0.0008 | split_test |

### Space group prediction (`space_group_classification`, metric=top5_accuracy)

| Regime | n_train | n_test | Best model | Value | Eval |
|---|---|---:|---|---|---|
| random | 15064 | 3228 | rf | 0.8885 | split_test |
| family_ood | 16312 | 5216 | rf | 0.2517 | split_test |
| composition_ood | 14734 | 3996 | rf | 0.8919 | split_test |
| crystal_system_ood | 12830 | 6837 | dummy | 0.6408 | split_test |

### Conductive-candidate ranking (`conductive_candidate_ranking`, metric=ndcg10)

| Regime | n_train | n_test | Best model | Value | Eval |
|---|---|---:|---|---|---|
| random | 166 | 166 | rf | 0.5726 | grouped_cv_k5 |
| family_ood | 166 | 166 | rf | 0.5726 | grouped_cv_k5 |
| composition_ood | 166 | 166 | rf | 0.5726 | grouped_cv_k5 |
| crystal_system_ood | 166 | 166 | rf | 0.5726 | grouped_cv_k5 |

### Negative-result (poor electrolyte) classification (`negative_result_classification`, metric=macro_f1)

| Regime | n_train | n_test | Best model | Value | Eval |
|---|---|---:|---|---|---|
| random | 16394 | 3248 | rf | 0.8351 | split_test |
| family_ood | 20543 | 9312 | rf | 0.7020 | split_test |
| composition_ood | 20682 | 5540 | rf | 0.7993 | split_test |
| crystal_system_ood | 12830 | 15164 | rf | 0.5083 | split_test |

### Metallic vs insulating classification (`metallic_classification`, metric=macro_f1)

| Regime | n_train | n_test | Best model | Value | Eval |
|---|---|---:|---|---|---|
| random | 15056 | 3228 | rf | 0.8385 | split_test |
| family_ood | 16306 | 5214 | rf | 0.8174 | split_test |
| composition_ood | 14731 | 3993 | rf | 0.8060 | split_test |
| crystal_system_ood | 12827 | 6834 | rf | 0.7121 | split_test |

### High-conductivity classification (σ_RT > 10⁻³ S/cm) (`high_conductivity_classification`, metric=macro_f1)

| Regime | n_train | n_test | Best model | Value | Eval |
|---|---|---:|---|---|---|
| random | 166 | 166 | rf | 0.6523 | grouped_cv_k5 |
| family_ood | 166 | 166 | rf | 0.6523 | grouped_cv_k5 |
| composition_ood | 166 | 166 | rf | 0.6523 | grouped_cv_k5 |
| crystal_system_ood | 166 | 166 | rf | 0.6523 | grouped_cv_k5 |

### Activation energy regression (`activation_energy_regression`, metric=mae)

| Regime | n_train | n_test | Best model | Value | Eval |
|---|---|---:|---|---|---|
| random | 91 | 91 | dummy | 0.1480 | grouped_cv_k5 |
| family_ood | 91 | 91 | dummy | 0.1480 | grouped_cv_k5 |
| composition_ood | 91 | 91 | dummy | 0.1480 | grouped_cv_k5 |
| crystal_system_ood | 91 | 91 | dummy | 0.1480 | grouped_cv_k5 |

### Conductivity magnitude regression (`sigma_RT_regression`, metric=mae)

| Regime | n_train | n_test | Best model | Value | Eval |
|---|---|---:|---|---|---|
| random | 166 | 166 | dummy | 0.8183 | grouped_cv_k5 |
| family_ood | 166 | 166 | dummy | 0.8183 | grouped_cv_k5 |
| composition_ood | 166 | 166 | dummy | 0.8183 | grouped_cv_k5 |
| crystal_system_ood | 166 | 166 | dummy | 0.8183 | grouped_cv_k5 |

### Magnetic vs non-magnetic classification (`is_magnetic_classification`, metric=macro_f1)

| Regime | n_train | n_test | Best model | Value | Eval |
|---|---|---:|---|---|---|
| random | 15064 | 3228 | rf | 0.9208 | split_test |
| family_ood | 16312 | 5216 | rf | 0.7877 | split_test |
| composition_ood | 14734 | 3996 | rf | 0.9014 | split_test |
| crystal_system_ood | 12830 | 6837 | rf | 0.9051 | split_test |

### Packing-fraction regression (`packing_fraction_regression`, metric=mae)

| Regime | n_train | n_test | Best model | Value | Eval |
|---|---|---:|---|---|---|
| random | 15064 | 3228 | rf | 0.0149 | split_test |
| family_ood | 16312 | 5216 | rf | 0.1078 | split_test |
| composition_ood | 14734 | 3996 | rf | 0.0189 | split_test |
| crystal_system_ood | 12830 | 6837 | rf | 0.0143 | split_test |

### Electroneutrality classification (`electroneutral_classification`, metric=macro_f1)

| Regime | n_train | n_test | Best model | Value | Eval |
|---|---|---:|---|---|---|
| random | 13522 | 2917 | rf | 0.9097 | split_test |
| family_ood | 15748 | 3584 | rf | 0.6535 | split_test |
| composition_ood | 13192 | 3549 | rf | 0.8431 | split_test |
| crystal_system_ood | 11184 | 6608 | rf | 0.8637 | split_test |

### Li-sublattice hopping distance regression (`li_hopping_distance_regression`, metric=mae)

| Regime | n_train | n_test | Best model | Value | Eval |
|---|---|---:|---|---|---|
| random | 14365 | 3068 | rf | 0.1988 | split_test |
| family_ood | 15902 | 4632 | rf | 0.6987 | split_test |
| composition_ood | 14035 | 3800 | rf | 0.2324 | split_test |
| crystal_system_ood | 12128 | 6697 | rf | 0.3091 | split_test |

### Electrolyte-candidate classification (`electrolyte_candidate_classification`, metric=macro_f1)

| Regime | n_train | n_test | Best model | Value | Eval |
|---|---|---:|---|---|---|
| random | 15636 | 3334 | rf | 0.9685 | split_test |
| family_ood | 16513 | 5715 | logistic | 0.5021 | split_test |
| composition_ood | 14734 | 4696 | rf | 0.9304 | split_test |
| crystal_system_ood | 12830 | 7537 | rf | 0.9011 | split_test |

