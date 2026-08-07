# ScandiumBench v1.0 — split-regime leaderboard

Generated 2026-08-07T23:08:41 · 25 tasks × 5 split regimes · deterministic sklearn baselines (dummy / linear / random forest / MLP).

Split regimes: **random** (Phase-6 leakage-checked, reused), **family_ood** (test chemistries never seen in train), **composition_ood** (no composition in both train and test), **crystal_system_ood** (test crystal systems unseen in train), **paper_ood** (no paper or composition shared across train/test).

Per-task tables list every baseline model's primary metric per regime; the bolded cell is the regime's best model.

### Formation energy regression (`formation_energy_regression`, metric=mae)

| Regime | n_train | n_test | Best | dummy | ridge | rf | mlp | logistic | Eval |
|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| random | 16394 | 3248 | rf | 0.6568 | 0.2094 | **0.0669** | 0.0999 | — | split_test |
| family_ood | 20543 | 9312 | rf | 1.4130 | 2.3871 | **1.0058** | 1.2431 | — | split_test |
| composition_ood | 20682 | 5540 | rf | 0.7762 | 0.3120 | **0.1626** | 0.1948 | — | split_test |
| crystal_system_ood | 12830 | 15164 | mlp | 0.7137 | 0.6435 | 0.6589 | **0.5503** | — | split_test |
| paper_ood | 20748 | 6254 | rf | 0.7586 | 0.3113 | **0.1558** | 0.1870 | — | split_test |

### Band gap regression (`band_gap_regression`, metric=mae)

| Regime | n_train | n_test | Best | dummy | ridge | rf | mlp | logistic | Eval |
|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| random | 16394 | 3248 | rf | 1.1946 | 0.8019 | **0.4304** | 0.5529 | — | split_test |
| family_ood | 20543 | 9312 | rf | 1.3634 | 2.5917 | **0.8830** | 1.6034 | — | split_test |
| composition_ood | 20682 | 5540 | rf | 1.1821 | 0.8359 | **0.5249** | 0.6182 | — | split_test |
| crystal_system_ood | 12830 | 15164 | rf | 1.2001 | 3.9018 | **0.6359** | 1.7207 | — | split_test |
| paper_ood | 20748 | 6254 | rf | 1.1498 | 0.8006 | **0.5216** | 0.6258 | — | split_test |

### Energy above hull regression (`energy_above_hull_regression`, metric=mae)

| Regime | n_train | n_test | Best | dummy | ridge | rf | mlp | logistic | Eval |
|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| random | 15064 | 3228 | rf | 0.1403 | 0.1289 | **0.0352** | 0.0445 | — | split_test |
| family_ood | 16312 | 5216 | dummy | **0.1928** | 45.9263 | 0.6014 | 11.2109 | — | split_test |
| composition_ood | 14734 | 3996 | rf | 0.1627 | 0.1311 | **0.0443** | 0.0517 | — | split_test |
| crystal_system_ood | 12830 | 6837 | mlp | 0.1837 | 0.1327 | 0.0997 | **0.0961** | — | split_test |
| paper_ood | 15050 | 4447 | rf | 0.1451 | 0.1249 | **0.0407** | 0.0488 | — | split_test |

### Bulk modulus regression (`bulk_modulus_regression`, metric=mae)

| Regime | n_train | n_test | Best | dummy | ridge | rf | mlp | logistic | Eval |
|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| random | 1126 | 143 | rf | 29.3470 | 17.4783 | **13.1247** | 17.5262 | — | split_test |
| family_ood | 616 | 2492 | ridge | 47.5751 | **29.7131** | 32.0564 | 35.1230 | — | split_test |
| composition_ood | 2253 | 568 | mlp | 36.3019 | 24.6006 | 20.9401 | **19.5323** | — | split_test |
| crystal_system_ood | 710 | 2242 | dummy | **33.7909** | 140.5788 | 54.3451 | 101.1122 | — | split_test |
| paper_ood | 2183 | 656 | rf | 36.6798 | 24.0467 | **17.7462** | 18.5032 | — | split_test |

### Shear modulus regression (`shear_modulus_regression`, metric=mae)

| Regime | n_train | n_test | Best | dummy | ridge | rf | mlp | logistic | Eval |
|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| random | 1036 | 138 | rf | 17.4843 | 12.7272 | **12.4580** | 15.8887 | — | split_test |
| family_ood | 601 | 2327 | rf | 27.5996 | 29.0868 | **18.1220** | 28.6383 | — | split_test |
| composition_ood | 2120 | 540 | mlp | 20.0716 | 16.5810 | 14.1652 | **13.6279** | — | split_test |
| crystal_system_ood | 668 | 2107 | ridge | 19.1875 | **19.0254** | 42.2865 | 20.3122 | — | split_test |
| paper_ood | 2053 | 623 | rf | 20.9975 | 17.2267 | **14.4413** | 14.6745 | — | split_test |

### Debye temperature regression (`debye_temperature_regression`, metric=mae)

| Regime | n_train | n_test | Best | dummy | ridge | rf | mlp | logistic | Eval |
|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| random | 581 | 130 | rf | 154.1671 | 74.3583 | **54.8391** | 71.4660 | — | split_test |
| family_ood | 103 | 723 | rf | 245.9807 | 1915.2462 | **93.2027** | 6808.0410 | — | split_test |
| composition_ood | 590 | 154 | rf | 147.8907 | 72.4587 | **55.4565** | 57.7796 | — | split_test |
| crystal_system_ood | 826 | 826 | rf | 165.3837 | 114.6186 | **92.7500** | 116.1964 | — | grouped_cv_k5 |
| paper_ood | 580 | 176 | rf | 162.2618 | 88.1621 | **74.2298** | 81.5878 | — | split_test |

### Density regression (`density_regression`, metric=mae)

| Regime | n_train | n_test | Best | dummy | ridge | rf | mlp | logistic | Eval |
|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| random | 16394 | 3248 | mlp | 0.9785 | 0.2464 | 0.1183 | **0.0984** | — | split_test |
| family_ood | 20543 | 9312 | ridge | 1.9217 | **1.7779** | 1.8214 | 3.7375 | — | split_test |
| composition_ood | 20682 | 5540 | mlp | 1.1564 | 0.5749 | 0.4103 | **0.3888** | — | split_test |
| crystal_system_ood | 12830 | 15164 | rf | 1.1544 | 1.0522 | **0.8586** | 2.3014 | — | split_test |
| paper_ood | 20748 | 6254 | mlp | 1.1349 | 0.5631 | 0.4018 | **0.3973** | — | split_test |

### Volume regression (`volume_regression`, metric=mae)

| Regime | n_train | n_test | Best | dummy | ridge | rf | mlp | logistic | Eval |
|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| random | 16394 | 3248 | rf | 237.2829 | 49.5833 | **14.5481** | 17.2953 | — | split_test |
| family_ood | 20543 | 9312 | rf | 286.2580 | 94.8238 | **75.4315** | 127.2778 | — | split_test |
| composition_ood | 20682 | 5540 | rf | 219.9254 | 47.3438 | **17.1382** | 18.9811 | — | split_test |
| crystal_system_ood | 12830 | 15164 | ridge | 246.5030 | **43.6594** | 62.5707 | 131.0992 | — | split_test |
| paper_ood | 20748 | 6254 | mlp | 224.7496 | 45.5499 | 15.3427 | **14.1302** | — | split_test |

### Ionic-radius regression (`ionic_radius_regression`, metric=mae)

| Regime | n_train | n_test | Best | dummy | ridge | rf | mlp | logistic | Eval |
|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| random | 15064 | 3228 | rf | 0.0752 | 0.0370 | **0.0081** | 0.0172 | — | split_test |
| family_ood | 16312 | 5216 | rf | 0.1487 | 6.9773 | **0.1366** | 29.9959 | — | split_test |
| composition_ood | 14734 | 3996 | rf | 0.0736 | 0.0377 | **0.0128** | 0.0177 | — | split_test |
| crystal_system_ood | 12830 | 6837 | rf | 0.0572 | 0.0371 | **0.0067** | 0.0207 | — | split_test |
| paper_ood | 15050 | 4447 | rf | 0.0753 | 0.0361 | **0.0116** | 0.0203 | — | split_test |

### Stable vs unstable classification (`stability_classification`, metric=macro_f1)

| Regime | n_train | n_test | Best | dummy | ridge | rf | mlp | logistic | Eval |
|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| random | 15064 | 3228 | rf | 0.4778 | — | **0.9260** | 0.9024 | 0.8946 | split_test |
| family_ood | 16312 | 5216 | rf | 0.4391 | — | **0.6744** | 0.5651 | 0.5640 | split_test |
| composition_ood | 14734 | 3996 | rf | 0.4778 | — | **0.9323** | 0.9085 | 0.8889 | split_test |
| crystal_system_ood | 12830 | 6837 | rf | 0.4964 | — | **0.9580** | 0.9275 | 0.9479 | split_test |
| paper_ood | 15050 | 4447 | rf | 0.4804 | — | **0.9220** | 0.8815 | 0.8674 | split_test |

### Wide-gap classification (E_g > 4 eV) (`wide_gap_classification`, metric=macro_f1)

| Regime | n_train | n_test | Best | dummy | ridge | rf | mlp | logistic | Eval |
|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| random | 11566 | 2298 | rf | 0.4796 | — | **0.8254** | 0.8162 | 0.7939 | split_test |
| family_ood | 14360 | 4211 | logistic | 0.4509 | — | 0.5671 | 0.6484 | **0.6538** | split_test |
| composition_ood | 12894 | 3391 | rf | 0.4763 | — | **0.8257** | 0.8219 | 0.7679 | split_test |
| crystal_system_ood | 8878 | 8708 | rf | 0.4860 | — | **0.6056** | 0.6019 | 0.5872 | split_test |
| paper_ood | 12900 | 3916 | rf | 0.4766 | — | **0.7746** | 0.7511 | 0.7269 | split_test |

### Family classification (`family_classification`, metric=macro_f1)

| Regime | n_train | n_test | Best | dummy | ridge | rf | mlp | logistic | Eval |
|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| random | 17046 | 3370 | rf | 0.0700 | — | **0.8217** | 0.7940 | 0.8180 | split_test |
| family_ood | 20753 | 10085 | dummy | **0.0652** | — | 0.0652 | 0.0652 | — | split_test |
| composition_ood | 20682 | 6523 | mlp | 0.0624 | — | 0.5356 | **0.5498** | 0.5473 | split_test |
| crystal_system_ood | 12830 | 16147 | mlp | 0.0668 | — | 0.3223 | **0.3501** | 0.3104 | split_test |
| paper_ood | 21731 | 6254 | rf | 0.0688 | — | **0.8031** | 0.7194 | 0.6900 | split_test |

### Crystal system prediction (`crystal_system_classification`, metric=macro_f1)

| Regime | n_train | n_test | Best | dummy | ridge | rf | mlp | logistic | Eval |
|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| random | 15064 | 3228 | rf | 0.0705 | — | **0.8358** | 0.6863 | 0.5847 | split_test |
| family_ood | 16312 | 5216 | rf | 0.0238 | — | **0.5295** | 0.2054 | 0.2532 | split_test |
| composition_ood | 14734 | 3996 | rf | 0.0728 | — | **0.8393** | 0.6612 | 0.5601 | split_test |
| crystal_system_ood | 12830 | 6837 | mlp | 0.0000 | — | 0.0008 | **0.0015** | 0.0005 | split_test |
| paper_ood | 15050 | 4447 | rf | 0.0734 | — | **0.8275** | 0.6665 | 0.5664 | split_test |

### Space group prediction (`space_group_classification`, metric=top5_accuracy)

| Regime | n_train | n_test | Best | dummy | ridge | rf | mlp | logistic | Eval |
|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| random | 15064 | 3228 | rf | 0.3024 | — | **0.8885** | 0.8262 | 0.7934 | split_test |
| family_ood | 16312 | 5216 | rf | 0.1678 | — | **0.2517** | 0.1691 | 0.1549 | split_test |
| composition_ood | 14734 | 3996 | rf | 0.2920 | — | **0.8919** | 0.8196 | 0.8016 | split_test |
| crystal_system_ood | 12830 | 6837 | dummy | **0.6408** | — | 0.0162 | 0.0082 | 0.0080 | split_test |
| paper_ood | 15050 | 4447 | rf | 0.2908 | — | **0.8226** | 0.7526 | 0.7367 | split_test |

### Conductive-candidate ranking (`conductive_candidate_ranking`, metric=ndcg10)

| Regime | n_train | n_test | Best | dummy | ridge | rf | mlp | logistic | Eval |
|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| random | 166 | 166 | rf | 0.4015 | 0.4079 | **0.5726** | 0.4087 | — | grouped_cv_k5 |
| family_ood | 166 | 166 | rf | 0.4015 | 0.4079 | **0.5726** | 0.4087 | — | grouped_cv_k5 |
| composition_ood | 166 | 166 | rf | 0.4015 | 0.4079 | **0.5726** | 0.4087 | — | grouped_cv_k5 |
| crystal_system_ood | 166 | 166 | rf | 0.4015 | 0.4079 | **0.5726** | 0.4087 | — | grouped_cv_k5 |
| paper_ood | 166 | 166 | rf | 0.4015 | 0.4079 | **0.5726** | 0.4087 | — | grouped_cv_k5 |

### Negative-result (poor electrolyte) classification (`negative_result_classification`, metric=macro_f1)

| Regime | n_train | n_test | Best | dummy | ridge | rf | mlp | logistic | Eval |
|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| random | 16394 | 3248 | rf | 0.4594 | — | **0.8351** | 0.7790 | 0.6971 | split_test |
| family_ood | 20543 | 9312 | rf | 0.4327 | — | **0.7020** | 0.7007 | 0.6674 | split_test |
| composition_ood | 20682 | 5540 | rf | 0.4359 | — | **0.7993** | 0.7643 | 0.7145 | split_test |
| crystal_system_ood | 12830 | 15164 | rf | 0.4199 | — | **0.5083** | 0.4924 | 0.4512 | split_test |
| paper_ood | 20748 | 6254 | rf | 0.4377 | — | **0.8001** | 0.7769 | 0.7477 | split_test |

### Metallic vs insulating classification (`metallic_classification`, metric=macro_f1)

| Regime | n_train | n_test | Best | dummy | ridge | rf | mlp | logistic | Eval |
|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| random | 15056 | 3228 | rf | 0.4137 | — | **0.8385** | 0.8129 | 0.7474 | split_test |
| family_ood | 16306 | 5214 | rf | 0.3644 | — | **0.8174** | 0.4534 | 0.4167 | split_test |
| composition_ood | 14731 | 3993 | rf | 0.4091 | — | **0.8060** | 0.7906 | 0.7454 | split_test |
| crystal_system_ood | 12827 | 6834 | rf | 0.4421 | — | **0.7121** | 0.6892 | 0.7119 | split_test |
| paper_ood | 15045 | 4445 | rf | 0.4161 | — | **0.8110** | 0.7948 | 0.7601 | split_test |

### High-conductivity classification (σ_RT > 10⁻³ S/cm) (`high_conductivity_classification`, metric=macro_f1)

| Regime | n_train | n_test | Best | dummy | ridge | rf | mlp | logistic | Eval |
|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| random | 166 | 166 | rf | 0.4386 | — | **0.6523** | 0.4533 | 0.4214 | grouped_cv_k5 |
| family_ood | 166 | 166 | rf | 0.4386 | — | **0.6523** | 0.4533 | 0.4214 | grouped_cv_k5 |
| composition_ood | 166 | 166 | rf | 0.4386 | — | **0.6523** | 0.4533 | 0.4214 | grouped_cv_k5 |
| crystal_system_ood | 166 | 166 | rf | 0.4386 | — | **0.6523** | 0.4533 | 0.4214 | grouped_cv_k5 |
| paper_ood | 166 | 166 | rf | 0.4386 | — | **0.6523** | 0.4533 | 0.4214 | grouped_cv_k5 |

### Activation energy regression (`activation_energy_regression`, metric=mae)

| Regime | n_train | n_test | Best | dummy | ridge | rf | mlp | logistic | Eval |
|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| random | 91 | 91 | dummy | **0.1480** | 0.2540 | 0.1823 | 0.2563 | — | grouped_cv_k5 |
| family_ood | 91 | 91 | dummy | **0.1480** | 0.2540 | 0.1823 | 0.2563 | — | grouped_cv_k5 |
| composition_ood | 91 | 91 | dummy | **0.1480** | 0.2540 | 0.1823 | 0.2563 | — | grouped_cv_k5 |
| crystal_system_ood | 91 | 91 | dummy | **0.1480** | 0.2540 | 0.1823 | 0.2563 | — | grouped_cv_k5 |
| paper_ood | 91 | 91 | dummy | **0.1480** | 0.2540 | 0.1823 | 0.2563 | — | grouped_cv_k5 |

### Conductivity magnitude regression (`sigma_RT_regression`, metric=mae)

| Regime | n_train | n_test | Best | dummy | ridge | rf | mlp | logistic | Eval |
|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| random | 166 | 166 | dummy | **0.8183** | 1.1744 | 0.8857 | 1.4337 | — | grouped_cv_k5 |
| family_ood | 166 | 166 | dummy | **0.8183** | 1.1744 | 0.8857 | 1.4337 | — | grouped_cv_k5 |
| composition_ood | 166 | 166 | dummy | **0.8183** | 1.1744 | 0.8857 | 1.4337 | — | grouped_cv_k5 |
| crystal_system_ood | 166 | 166 | dummy | **0.8183** | 1.1744 | 0.8857 | 1.4337 | — | grouped_cv_k5 |
| paper_ood | 166 | 166 | dummy | **0.8183** | 1.1744 | 0.8857 | 1.4337 | — | grouped_cv_k5 |

### Magnetic vs non-magnetic classification (`is_magnetic_classification`, metric=macro_f1)

| Regime | n_train | n_test | Best | dummy | ridge | rf | mlp | logistic | Eval |
|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| random | 15064 | 3228 | rf | 0.4188 | — | **0.9208** | 0.9111 | 0.8524 | split_test |
| family_ood | 16312 | 5216 | rf | 0.2500 | — | **0.7877** | 0.7001 | 0.7804 | split_test |
| composition_ood | 14734 | 3996 | rf | 0.4172 | — | **0.9014** | 0.8965 | 0.8696 | split_test |
| crystal_system_ood | 12830 | 6837 | rf | 0.4691 | — | **0.9051** | 0.8621 | 0.7850 | split_test |
| paper_ood | 15050 | 4447 | rf | 0.4254 | — | **0.9188** | 0.9065 | 0.8676 | split_test |

### Packing-fraction regression (`packing_fraction_regression`, metric=mae)

| Regime | n_train | n_test | Best | dummy | ridge | rf | mlp | logistic | Eval |
|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| random | 15064 | 3228 | rf | 0.1578 | 0.0365 | **0.0149** | 0.0181 | — | split_test |
| family_ood | 16312 | 5216 | rf | 0.1938 | 3.3332 | **0.1078** | 3.7309 | — | split_test |
| composition_ood | 14734 | 3996 | rf | 0.1592 | 0.0381 | **0.0189** | 0.0210 | — | split_test |
| crystal_system_ood | 12830 | 6837 | rf | 0.1600 | 0.0411 | **0.0143** | 0.0196 | — | split_test |
| paper_ood | 15050 | 4447 | rf | 0.1581 | 0.0363 | **0.0187** | 0.0220 | — | split_test |

### Electroneutrality classification (`electroneutral_classification`, metric=macro_f1)

| Regime | n_train | n_test | Best | dummy | ridge | rf | mlp | logistic | Eval |
|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| random | 13522 | 2917 | rf | 0.4123 | — | **0.9097** | 0.8564 | 0.7876 | split_test |
| family_ood | 15748 | 3584 | rf | 0.4669 | — | **0.6535** | 0.5529 | 0.4663 | split_test |
| composition_ood | 13192 | 3549 | rf | 0.4024 | — | **0.8431** | 0.8151 | 0.7616 | split_test |
| crystal_system_ood | 11184 | 6608 | rf | 0.3522 | — | **0.8637** | 0.7889 | 0.7513 | split_test |
| paper_ood | 13504 | 4015 | rf | 0.4044 | — | **0.8323** | 0.8199 | 0.7724 | split_test |

### Li-sublattice hopping distance regression (`li_hopping_distance_regression`, metric=mae)

| Regime | n_train | n_test | Best | dummy | ridge | rf | mlp | logistic | Eval |
|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| random | 14365 | 3068 | rf | 0.7193 | 0.4143 | **0.1988** | 0.3173 | — | split_test |
| family_ood | 15902 | 4632 | rf | 0.7721 | 36.2469 | **0.6987** | 288.8833 | — | split_test |
| composition_ood | 14035 | 3800 | rf | 0.7117 | 0.4180 | **0.2324** | 0.3527 | — | split_test |
| crystal_system_ood | 12128 | 6697 | rf | 0.7497 | 0.4579 | **0.3091** | 0.4814 | — | split_test |
| paper_ood | 14333 | 4258 | rf | 0.7175 | 0.4144 | **0.2245** | 0.3418 | — | split_test |

### Electrolyte-candidate classification (`electrolyte_candidate_classification`, metric=macro_f1)

| Regime | n_train | n_test | Best | dummy | ridge | rf | mlp | logistic | Eval |
|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| random | 15636 | 3334 | rf | 0.3565 | — | **0.9685** | 0.9603 | 0.8997 | split_test |
| family_ood | 16513 | 5715 | logistic | 0.0295 | — | 0.4792 | 0.4954 | **0.5021** | split_test |
| composition_ood | 14734 | 4696 | rf | 0.3791 | — | **0.9304** | 0.9298 | 0.8982 | split_test |
| crystal_system_ood | 12830 | 7537 | rf | 0.2902 | — | **0.9011** | 0.8621 | 0.8963 | split_test |
| paper_ood | 15750 | 4447 | rf | 0.3465 | — | **0.9510** | 0.9192 | 0.8907 | split_test |

