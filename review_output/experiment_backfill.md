# Experiment-metadata backfill report (Phase 2.2)

Deterministic extraction from each verified record's source PDF. Review the values below; then run `--apply` to stamp the `experiment` block.

**116 records | 101 with on-disk PDF | 100 with ≥1 condition extracted | 32 with suspicious-flag**

**Field coverage (count of records):**

- sample_form: 99
- electrode_material: 99
- atmosphere: 99
- electrode_deposition: 94
- instrument: 57
- pelletizing_pressure_MPa: 51
- pellet_diameter_mm: 49
- sinter_temperature_C: 34
- thickness_mm: 17
- sinter_time_h: 15
- relative_density_pct: 13
- annealing_temperature_C: 12
- frequency_min_Hz: 6
- frequency_max_Hz: 6

## Coverage summary

| Metric | Value |
|---|---|
| verified records read | 116 |
| on-disk PDF matched | 101 |
| ≥1 condition extracted | 100 |
| suspicious-value flags | 32 |

## Li7La3Zr2O12
`10.1038/s41467-022-35287-1` — `10.1038_s41467-022-35287-1.pdf`
- **sample_form**: PELLET
- **pelletizing_pressure_MPa**: 250.0
- **electrode_material**: LI_METAL
- **electrode_deposition**: SPUTTERED
- **atmosphere**: AIR
- **sinter_temperature_C**: 1000.0
- **sinter_time_h**: 12.0

## Li7La3Zr0.5Hf0.5Sc0.5Nb0.5O12
`10.1038/s41467-022-35287-1` — `10.1038_s41467-022-35287-1.pdf`
- **sample_form**: PELLET
- **pelletizing_pressure_MPa**: 250.0
- **electrode_material**: LI_METAL
- **electrode_deposition**: SPUTTERED
- **atmosphere**: AIR
- **sinter_temperature_C**: 1000.0
- **sinter_time_h**: 12.0

## Li7La3Zr0.4Hf0.4Sn0.4Sc0.4Ta0.4O12
`10.1038/s41467-022-35287-1` — `10.1038_s41467-022-35287-1.pdf`
- **sample_form**: PELLET
- **pelletizing_pressure_MPa**: 250.0
- **electrode_material**: LI_METAL
- **electrode_deposition**: SPUTTERED
- **atmosphere**: AIR
- **sinter_temperature_C**: 1000.0
- **sinter_time_h**: 12.0

## Li2OHCl
`10.1038/s41467-023-42385-1` — `10.1038_s41467-023-42385-1.pdf`
- **sample_form**: COMPOSITE
- **pellet_diameter_mm**: 1.0
- **pelletizing_pressure_MPa**: 480.0
- **electrode_material**: LI_METAL
- **electrode_deposition**: PRESSED
- **atmosphere**: INERT
- **sinter_temperature_C**: 120.0
- **annealing_temperature_C**: 120.0
- **instrument**: Autolab

⚠️ *Suspicious (verify against paper):*
  - pellet_diameter_mm=1.0 outside 4–40 mm

## (Li2OH)0.99K0.01Cl
`10.1038/s41467-023-42385-1` — `10.1038_s41467-023-42385-1.pdf`
- **sample_form**: COMPOSITE
- **pellet_diameter_mm**: 1.0
- **pelletizing_pressure_MPa**: 480.0
- **electrode_material**: LI_METAL
- **electrode_deposition**: PRESSED
- **atmosphere**: INERT
- **sinter_temperature_C**: 120.0
- **annealing_temperature_C**: 120.0
- **instrument**: Autolab

⚠️ *Suspicious (verify against paper):*
  - pellet_diameter_mm=1.0 outside 4–40 mm

## PEO-LiTFSI-AlOC
`10.1038/s41467-024-51191-2` — `10.1038_s41467-024-51191-2.pdf`
- **sample_form**: MEMBRANE
- **pellet_diameter_mm**: 15.6
- **thickness_mm**: 1.0
- **electrode_material**: STAINLESS_STEEL
- **electrode_deposition**: PRESSED
- **atmosphere**: O2

## Li10GeP2S12
`10.1038/nmat3066` — `None`
_no conditions extracted_

## Li6PS5Cl
`10.1039/C5EE02930D` — `None`
_no conditions extracted_

## Li6PS5Br
`10.1039/C5EE02930D` — `None`
_no conditions extracted_

## Li3PS4
`10.1016/j.ssi.2015.09.010` — `None`
_no conditions extracted_

## Li7La3Zr2O12
`10.1002/anie.200701144` — `None`
_no conditions extracted_

## Li6.5La3Zr1.5Ta0.5O12
`10.1039/C6EE00556K` — `None`
_no conditions extracted_

## Li0.33La0.56TiO3
`10.1016/0167-2738(93)90241-4` — `None`
_no conditions extracted_

## Li1.3Al0.3Ti1.7(PO4)3
`10.1016/S0167-2738(03)00260-7` — `None`
_no conditions extracted_

## Li1.5Al0.5Ge1.5(PO4)3
`10.1016/j.electacta.2012.04.007` — `None`
_no conditions extracted_

## Li3InCl6
`10.1038/s41467-019-09619-5` — `None`
_no conditions extracted_

## Li3YCl6
`10.1016/j.matt.2019.06.004` — `None`
_no conditions extracted_

## Li2ZrCl6
`10.1021/jacs.1c07481` — `10.1021_jacs.1c07481.pdf`
- **sample_form**: WAFER
- **electrode_deposition**: PRESSED
- **atmosphere**: HE

## LiBH4
`10.1038/nmat1912` — `None`
_no conditions extracted_

## Li2B12H12
`10.1039/C6EE02745A` — `None`
_no conditions extracted_

## Li3OCl
`10.1021/ja305709z` — `None`
_no conditions extracted_

## PEO-LiTFSI
`10.1038/s41467-024-51191-2` — `10.1038_s41467-024-51191-2.pdf`
- **sample_form**: MEMBRANE
- **pellet_diameter_mm**: 15.6
- **thickness_mm**: 1.0
- **electrode_material**: STAINLESS_STEEL
- **electrode_deposition**: PRESSED
- **atmosphere**: O2

## 0.7Li(CB9H10)-0.3Li(CB11H12)
`10.1038/s41467-019-09061-9` — `10.1038_s41467-019-09061-9.pdf`
- **sample_form**: COMPOSITE
- **pelletizing_pressure_MPa**: 153.6
- **electrode_material**: CARBON
- **electrode_deposition**: PRESSED
- **atmosphere**: VACUUM
- **instrument**: Solartron

## Ca-CeO2/LiTFSI/PEO
`10.1002/aenm.202000049` — `10.1002_aenm.202000049.pdf`
- **sample_form**: MEMBRANE
- **pellet_diameter_mm**: 11.0
- **electrode_material**: STAINLESS_STEEL
- **electrode_deposition**: PRESSED
- **atmosphere**: O2
- **sinter_temperature_C**: 600.0
- **sinter_time_h**: 6.0
- **instrument**: Biologic

## La0.57Li0.29TiO3
`10.3389/fchem.2022.966274` — `10.3389_fchem.2022.966274.pdf`
- **sample_form**: MEMBRANE
- **pelletizing_pressure_MPa**: 200.0
- **electrode_material**: LI_METAL
- **electrode_deposition**: SPUTTERED
- **atmosphere**: AR
- **sinter_temperature_C**: 960.0
- **sinter_time_h**: 12.0
- **instrument**: Solartron

## Li1.3Al0.3In0.1Ti1.7(PO4)3/PVDF
`10.35378/gujs.1589340` — `10.35378_gujs.1589340.pdf`
- **sample_form**: MEMBRANE
- **electrode_material**: LI_METAL
- **electrode_deposition**: PRESSED
- **atmosphere**: AIR
- **sinter_temperature_C**: 900.0
- **instrument**: Gamry

## Li1.3Al0.3Ti1.7(PO4)3
`10.3390/ma14164737` — `10.3390_ma14164737.pdf`
_no conditions extracted_

## Li2ZrCl6
`10.1038/s41467-021-24697-2` — `10.1038_s41467-021-24697-2.pdf`
- **sample_form**: COMPOSITE
- **pelletizing_pressure_MPa**: 380.0
- **electrode_material**: LI_METAL
- **electrode_deposition**: SPUTTERED
- **atmosphere**: AR
- **sinter_temperature_C**: 350.0
- **annealing_temperature_C**: 350.0

## Li3OCl
`10.3389/fchem.2020.562549` — `10.3389_fchem.2020.562549.pdf`
- **sample_form**: COMPOSITE
- **pellet_diameter_mm**: 0.3
- **electrode_material**: LI_METAL
- **electrode_deposition**: PRESSED
- **atmosphere**: INERT
- **instrument**: Biologic

⚠️ *Suspicious (verify against paper):*
  - pellet_diameter_mm=0.3 outside 4–40 mm

## Li3Zr2Si2PO12
`10.1126/sciadv.abj7698` — `10.1126_sciadv.abj7698.pdf`
- **sample_form**: THIN_FILM
- **pellet_diameter_mm**: 10.0
- **thickness_mm**: 2.4
- **relative_density_pct**: 83.0
- **pelletizing_pressure_MPa**: 70.0
- **electrode_material**: LI_METAL
- **electrode_deposition**: SPUTTERED
- **atmosphere**: AIR
- **sinter_temperature_C**: 700.0
- **annealing_temperature_C**: 700.0

## Li5.4Al0.1PS4.7Cl1.3
`10.3390/nano12244355` — `10.3390_nano12244355.pdf`
- **sample_form**: COMPOSITE
- **pellet_diameter_mm**: 10.0
- **pelletizing_pressure_MPa**: 15.0
- **electrode_material**: STAINLESS_STEEL
- **atmosphere**: N2
- **instrument**: Biologic

## Li5.5PS4.5Cl1.5
`10.3390/nano12244355` — `10.3390_nano12244355.pdf`
- **sample_form**: COMPOSITE
- **pellet_diameter_mm**: 10.0
- **pelletizing_pressure_MPa**: 15.0
- **electrode_material**: STAINLESS_STEEL
- **atmosphere**: N2
- **instrument**: Biologic

## Li6.25Al0.25La3Zr2O12-in-PEGDA
`10.1021/acsaem.5c01010` — `10.1021_acsaem.5c01010.pdf`
- **sample_form**: THIN_FILM
- **electrode_material**: LI_METAL
- **electrode_deposition**: COATED
- **frequency_min_Hz**: 1.0
- **frequency_max_Hz**: 2000000.0
- **atmosphere**: VACUUM
- **instrument**: Biologic

## Li6.5Fe0.2La3Zr1.9Bi0.1O12
`10.3390/molecules30092028` — `10.3390_molecules30092028.pdf`
- **sample_form**: MEMBRANE
- **relative_density_pct**: 95.0
- **electrode_material**: LI_METAL
- **electrode_deposition**: SPUTTERED
- **atmosphere**: O2

## Li6.5La3-xBaxZr1.5-xTa0.5+xO12
`10.3389/fenrg.2016.00028` — `10.3389_fenrg.2016.00028.pdf`
- **sample_form**: THIN_FILM
- **pelletizing_pressure_MPa**: 300.0
- **electrode_material**: LI_METAL
- **electrode_deposition**: SPUTTERED
- **atmosphere**: VACUUM
- **sinter_temperature_C**: 1100.0
- **sinter_time_h**: 15.0
- **annealing_temperature_C**: 1100.0

## Li6.5La3Zr1.5Ta0.5O12
`10.1038/s41467-025-58108-7` — `10.1038_s41467-025-58108-7.pdf`
- **sample_form**: MEMBRANE
- **pellet_diameter_mm**: 10.0
- **relative_density_pct**: 64.9
- **pelletizing_pressure_MPa**: 359.8
- **electrode_material**: LI_METAL
- **electrode_deposition**: SPUTTERED
- **atmosphere**: N2
- **sinter_temperature_C**: 1100.0

## Li6.6La3Zr1.6Nb0.4O12
`10.3390/ma13030560` — `10.3390_ma13030560.pdf`
- **sample_form**: MEMBRANE
- **pellet_diameter_mm**: 1.0
- **thickness_mm**: 4.0
- **relative_density_pct**: 87.3
- **pelletizing_pressure_MPa**: 200.0
- **electrode_material**: CARBON
- **electrode_deposition**: PRESSED
- **atmosphere**: AIR
- **instrument**: Gamry

⚠️ *Suspicious (verify against paper):*
  - pellet_diameter_mm=1.0 outside 4–40 mm

## Li6PS5Cl
`10.3390/nano12244355` — `10.3390_nano12244355.pdf`
- **sample_form**: COMPOSITE
- **pellet_diameter_mm**: 10.0
- **pelletizing_pressure_MPa**: 15.0
- **electrode_material**: STAINLESS_STEEL
- **atmosphere**: N2
- **instrument**: Biologic

## Li6PS5Cl0.5Br0.5
`10.3390/en16135100` — `None`
_no conditions extracted_

## Li7La3Zr2O12
`10.1021/acs.chemmater.3c01831` — `10.1021_acs.chemmater.3c01831.pdf`
- **sample_form**: SINGLE_CRYSTAL
- **electrode_material**: LI_METAL
- **electrode_deposition**: SPUTTERED
- **atmosphere**: GLOVEBOX
- **sinter_temperature_C**: 600.0
- **annealing_temperature_C**: 600.0
- **instrument**: Biologic

## LiBH4-LiI/Al2O3
`10.1021/acsami.0c10361` — `10.1021_acsami.0c10361.pdf`
- **sample_form**: COMPOSITE
- **pellet_diameter_mm**: 2.5
- **electrode_material**: LI_METAL
- **electrode_deposition**: SPUTTERED
- **atmosphere**: N2
- **instrument**: Novocontrol

⚠️ *Suspicious (verify against paper):*
  - pellet_diameter_mm=2.5 outside 4–40 mm

## LiBH4-MgO
`10.1021/acsaem.0c02525` — `10.1021_acsaem.0c02525.pdf`
- **sample_form**: COMPOSITE
- **pellet_diameter_mm**: 10.0
- **pelletizing_pressure_MPa**: 60.0
- **electrode_material**: LI_METAL
- **electrode_deposition**: PRESSED
- **atmosphere**: AR
- **instrument**: Biologic

## LiDFOB-TXE-FDMA-FEC
`10.1038/s41467-023-35857-x` — `10.1038_s41467-023-35857-x.pdf`
- **sample_form**: COMPOSITE
- **electrode_material**: STAINLESS_STEEL
- **electrode_deposition**: SPUTTERED
- **atmosphere**: GLOVEBOX
- **instrument**: Gamry

## Mg(BH4)21.47NH3
`10.1038/s43246-024-00601-5` — `10.1038_s43246-024-00601-5.pdf`
- **sample_form**: COMPOSITE
- **pellet_diameter_mm**: 10.3
- **electrode_material**: STAINLESS_STEEL
- **electrode_deposition**: PRESSED
- **atmosphere**: AR
- **instrument**: Biologic

## Na3HfZr(SiO4)2(PO4)
`10.1038/s41467-023-40669-0` — `10.1038_s41467-023-40669-0.pdf`
- **sample_form**: PELLET
- **pellet_diameter_mm**: 1.0
- **pelletizing_pressure_MPa**: 3.0
- **electrode_material**: STAINLESS_STEEL
- **electrode_deposition**: PRESSED
- **atmosphere**: GLOVEBOX

⚠️ *Suspicious (verify against paper):*
  - pelletizing_pressure_MPa=3.0 low (<15 MPa)
  - pellet_diameter_mm=1.0 outside 4–40 mm

## PEO-LiTFSI
`10.3390/polym12091889` — `10.3390_polym12091889.pdf`
- **sample_form**: MEMBRANE
- **thickness_mm**: 0.081
- **electrode_material**: STAINLESS_STEEL
- **electrode_deposition**: PRESSED
- **atmosphere**: N2

## (Li2OH)0.99K0.01Cl
`10.1038/s41467-023-42385-1` — `10.1038_s41467-023-42385-1.pdf`
- **sample_form**: COMPOSITE
- **pellet_diameter_mm**: 1.0
- **pelletizing_pressure_MPa**: 480.0
- **electrode_material**: LI_METAL
- **electrode_deposition**: PRESSED
- **atmosphere**: INERT
- **sinter_temperature_C**: 120.0
- **annealing_temperature_C**: 120.0
- **instrument**: Autolab

⚠️ *Suspicious (verify against paper):*
  - pellet_diameter_mm=1.0 outside 4–40 mm

## Li0.29La0.57TiO3
`10.1038/s43246-026-01164-3` — `10.1038_s43246-026-01164-3.pdf`
- **sample_form**: SINGLE_CRYSTAL
- **electrode_material**: AL
- **electrode_deposition**: PRESSED
- **atmosphere**: AIR

## Li2SO4-ZrCl4
`10.1038/s41467-026-69737-x` — `10.1038_s41467-026-69737-x.pdf`
- **sample_form**: COMPOSITE
- **pellet_diameter_mm**: 10.0
- **thickness_mm**: 0.1
- **pelletizing_pressure_MPa**: 2.0
- **electrode_material**: STAINLESS_STEEL
- **electrode_deposition**: PRESSED
- **atmosphere**: GLOVEBOX

⚠️ *Suspicious (verify against paper):*
  - pelletizing_pressure_MPa=2.0 low (<15 MPa)

## Li7La3Zr2O12
`10.1038/s41467-022-35287-1` — `10.1038_s41467-022-35287-1.pdf`
- **sample_form**: PELLET
- **pelletizing_pressure_MPa**: 250.0
- **electrode_material**: LI_METAL
- **electrode_deposition**: SPUTTERED
- **atmosphere**: AIR
- **sinter_temperature_C**: 1000.0
- **sinter_time_h**: 12.0

## PEO-LiTFSI
`10.1038/s41467-024-51191-2` — `10.1038_s41467-024-51191-2.pdf`
- **sample_form**: MEMBRANE
- **pellet_diameter_mm**: 15.6
- **thickness_mm**: 1.0
- **electrode_material**: STAINLESS_STEEL
- **electrode_deposition**: PRESSED
- **atmosphere**: O2

## Li0.375Sr0.4375Ta0.75Zr0.25O3
`10.1038/s41467-023-37115-6` — `10.1038_s41467-023-37115-6.pdf`
- **sample_form**: PELLET
- **thickness_mm**: 1.55
- **pelletizing_pressure_MPa**: 200.0
- **electrode_material**: AG
- **electrode_deposition**: PRESSED
- **atmosphere**: GLOVEBOX
- **sinter_temperature_C**: 1100.0
- **sinter_time_h**: 12.0
- **instrument**: PARSTAT

## Na2.9H(Se0.9I0.1)
`10.1038/s41467-020-20370-2` — `10.1038_s41467-020-20370-2.pdf`
- **sample_form**: PELLET
- **pellet_diameter_mm**: 55.0
- **electrode_material**: AG
- **electrode_deposition**: PRESSED
- **atmosphere**: GLOVEBOX

⚠️ *Suspicious (verify against paper):*
  - pellet_diameter_mm=55.0 outside 4–40 mm

## Na3HSe
`10.1038/s41467-020-20370-2` — `10.1038_s41467-020-20370-2.pdf`
- **sample_form**: PELLET
- **pellet_diameter_mm**: 55.0
- **electrode_material**: AG
- **electrode_deposition**: PRESSED
- **atmosphere**: GLOVEBOX

⚠️ *Suspicious (verify against paper):*
  - pellet_diameter_mm=55.0 outside 4–40 mm

## Na3HfSc(SiO4)(PO4)2
`10.1038/s41467-023-40669-0` — `10.1038_s41467-023-40669-0.pdf`
- **sample_form**: PELLET
- **pellet_diameter_mm**: 1.0
- **pelletizing_pressure_MPa**: 3.0
- **electrode_material**: STAINLESS_STEEL
- **electrode_deposition**: PRESSED
- **atmosphere**: GLOVEBOX

⚠️ *Suspicious (verify against paper):*
  - pelletizing_pressure_MPa=3.0 low (<15 MPa)
  - pellet_diameter_mm=1.0 outside 4–40 mm

## (Li0.45La0.85)ScO3
`10.3390/molecules26020299` — `10.3390_molecules26020299.pdf`
- **sample_form**: PELLET
- **pellet_diameter_mm**: 1.0
- **electrode_material**: LI_METAL
- **electrode_deposition**: PAINTED
- **atmosphere**: AR
- **sinter_temperature_C**: 623.0
- **instrument**: Solartron

⚠️ *Suspicious (verify against paper):*
  - pellet_diameter_mm=1.0 outside 4–40 mm

## (Li0.4Ce0.15La0.67)ScO3
`10.3390/molecules26020299` — `10.3390_molecules26020299.pdf`
- **sample_form**: PELLET
- **pellet_diameter_mm**: 1.0
- **electrode_material**: LI_METAL
- **electrode_deposition**: PAINTED
- **atmosphere**: AR
- **sinter_temperature_C**: 623.0
- **instrument**: Solartron

⚠️ *Suspicious (verify against paper):*
  - pellet_diameter_mm=1.0 outside 4–40 mm

## 40wt% Li2OHCl0.5Br0.5/NBR CPE
`10.3389/fchem.2021.744417` — `10.3389_fchem.2021.744417.pdf`
- **sample_form**: MEMBRANE
- **electrode_material**: LI_METAL
- **electrode_deposition**: PRESSED
- **atmosphere**: GLOVEBOX
- **instrument**: Solartron

## Li1.3Al0.3BxTi1.7-x(PO4)3 (10% H3BO3)
`10.3390/ma17153846` — `10.3390_ma17153846.pdf`
- **sample_form**: FILM
- **relative_density_pct**: 95.42
- **pelletizing_pressure_MPa**: 300.0
- **electrode_material**: STAINLESS_STEEL
- **electrode_deposition**: PRESSED
- **atmosphere**: O2
- **instrument**: Gamry

## Li6.98Ga0.072La3Zr1.982Ta0.018O12
`10.3390/nano12172946` — `10.3390_nano12172946.pdf`
- **sample_form**: PELLET
- **relative_density_pct**: 97.8
- **pelletizing_pressure_MPa**: 200.0
- **electrode_material**: LI_METAL
- **electrode_deposition**: PRESSED
- **frequency_min_Hz**: 1.0
- **frequency_max_Hz**: 10000000.0
- **atmosphere**: N2

## NBR SPE
`10.3389/fchem.2021.744417` — `10.3389_fchem.2021.744417.pdf`
- **sample_form**: MEMBRANE
- **electrode_material**: LI_METAL
- **electrode_deposition**: PRESSED
- **atmosphere**: GLOVEBOX
- **instrument**: Solartron

## PEO
`10.3390/molecules29081759` — `10.3390_molecules29081759.pdf`
- **sample_form**: THIN_FILM
- **pellet_diameter_mm**: 12.0
- **electrode_material**: CARBON
- **electrode_deposition**: EVAPORATED
- **atmosphere**: AR
- **instrument**: Metrohm

## PEO-5% COF-LZU1
`10.3390/molecules29081759` — `10.3390_molecules29081759.pdf`
- **sample_form**: THIN_FILM
- **pellet_diameter_mm**: 12.0
- **electrode_material**: CARBON
- **electrode_deposition**: EVAPORATED
- **atmosphere**: AR
- **instrument**: Metrohm

## PEO-PAPI (crosslinked)
`10.3389/fmats.2022.864478` — `10.3389_fmats.2022.864478.pdf`
- **sample_form**: MEMBRANE
- **electrode_material**: STAINLESS_STEEL
- **electrode_deposition**: PRESSED
- **atmosphere**: AR
- **instrument**: Zahner

## PEO/LiTFSI (electrospun)
`10.3390/nano13071294` — `10.3390_nano13071294.pdf`
- **sample_form**: MEMBRANE
- **pellet_diameter_mm**: 19.0
- **electrode_material**: AL
- **electrode_deposition**: EVAPORATED
- **atmosphere**: VACUUM

## PEO/LiTFSI/in-situ SiO2 (10wt%)
`10.3390/nano13071294` — `10.3390_nano13071294.pdf`
- **sample_form**: MEMBRANE
- **pellet_diameter_mm**: 19.0
- **electrode_material**: AL
- **electrode_deposition**: EVAPORATED
- **atmosphere**: VACUUM

## Li1.3Al0.3Ti1.7(PO4)3
`10.37614/2949-1215.2025.16.2.020` — `10.37614_2949-1215.2025.16.2.020.pdf`
- **electrode_material**: AL

## Li6.4Ga0.2La3Zr1.9Ce0.1O12
`10.1007/s11664-026-12871-5` — `10.1007_s11664-026-12871-5.pdf`
- **sample_form**: SINGLE_CRYSTAL
- **pellet_diameter_mm**: 10.0
- **thickness_mm**: 1.5
- **relative_density_pct**: 94.0
- **pelletizing_pressure_MPa**: 4.0
- **electrode_material**: LI_METAL
- **electrode_deposition**: COATED
- **frequency_min_Hz**: 20.0
- **frequency_max_Hz**: 20000000.0
- **atmosphere**: HE
- **instrument**: Novocontrol

⚠️ *Suspicious (verify against paper):*
  - pelletizing_pressure_MPa=4.0 low (<15 MPa)

## CsSn0.9In0.067Cl3
`10.1002/aenm.202300982` — `10.1002_aenm.202300982.pdf`
- **sample_form**: THIN_FILM
- **thickness_mm**: 7.0
- **pelletizing_pressure_MPa**: 510.0
- **electrode_material**: STAINLESS_STEEL
- **electrode_deposition**: SPUTTERED
- **atmosphere**: INERT
- **instrument**: Biologic

## Li0.35La0.55TiO3-F2
`10.1007/s11664-021-09331-7` — `10.1007_s11664-021-09331-7.pdf`
- **sample_form**: COMPOSITE
- **pellet_diameter_mm**: 15.0
- **thickness_mm**: 1.0
- **relative_density_pct**: 95.4
- **pelletizing_pressure_MPa**: 10.0
- **electrode_material**: LI_METAL
- **electrode_deposition**: PRESSED
- **atmosphere**: AIR
- **sinter_temperature_C**: 800.0
- **sinter_time_h**: 2.0

⚠️ *Suspicious (verify against paper):*
  - pelletizing_pressure_MPa=10.0 low (<15 MPa)

## Li1.3Al0.2Y0.1Ti1.7(PO4)3
`10.3390/nano15010042` — `10.3390_nano15010042.pdf`
- **sample_form**: MEMBRANE
- **electrode_material**: LI_METAL
- **electrode_deposition**: SPUTTERED
- **atmosphere**: INERT
- **instrument**: Solartron

## Li1.3Al0.3Ti1.7(PO4)3
`10.3390/nano15010042` — `10.3390_nano15010042.pdf`
- **sample_form**: MEMBRANE
- **electrode_material**: LI_METAL
- **electrode_deposition**: SPUTTERED
- **atmosphere**: INERT
- **instrument**: Solartron

## Li6.55Ge0.05La3Zr1.75Ta0.25O12
`10.1016/j.ceramint.2023.09.330` — `10.1016_j.ceramint.2023.09.330.pdf`
- **sample_form**: THIN_FILM
- **thickness_mm**: 10.0
- **pelletizing_pressure_MPa**: 4.0
- **electrode_material**: BLOCKING
- **electrode_deposition**: COATED
- **atmosphere**: AIR
- **sinter_temperature_C**: 1050.0
- **instrument**: Novocontrol

⚠️ *Suspicious (verify against paper):*
  - pelletizing_pressure_MPa=4.0 low (<15 MPa)

## Sn-LATP/PVDF-HFP-LiTFSI CSE
`10.3390/polym16091251` — `10.3390_polym16091251.pdf`
- **sample_form**: COMPOSITE
- **electrode_material**: LI_METAL
- **electrode_deposition**: PRESSED
- **atmosphere**: AIR

## 0.5Li2SO4-ZrCl4
`10.1038/s41467-026-69737-x` — `10.1038_s41467-026-69737-x.pdf`
- **sample_form**: COMPOSITE
- **pellet_diameter_mm**: 10.0
- **thickness_mm**: 0.1
- **pelletizing_pressure_MPa**: 2.0
- **electrode_material**: STAINLESS_STEEL
- **electrode_deposition**: PRESSED
- **atmosphere**: GLOVEBOX

⚠️ *Suspicious (verify against paper):*
  - pelletizing_pressure_MPa=2.0 low (<15 MPa)

## Li1.3Al0.3Ti1.7(PO4)3/PVDF-HFP CSE
`10.3390/membranes13020201` — `10.3390_membranes13020201.pdf`
- **sample_form**: MEMBRANE
- **electrode_material**: LI_METAL
- **electrode_deposition**: PRESSED
- **atmosphere**: AIR

## Li3YCl6 (as-prepared)
`10.1021/jacs.1c11335` — `10.1021_jacs.1c11335.pdf`
- **sample_form**: COMPOSITE
- **electrode_material**: CARBON
- **electrode_deposition**: PRESSED
- **atmosphere**: INERT
- **sinter_temperature_C**: 823.0
- **annealing_temperature_C**: 823.0
- **instrument**: Solartron

## Li6.1Ga0.3La3Zr2O12 (LGLZO_5)
`10.1038/s41427-024-00563-7` — `10.1038_s41427-024-00563-7.pdf`
- **sample_form**: MEMBRANE
- **relative_density_pct**: 88.52
- **pelletizing_pressure_MPa**: 70.0
- **electrode_material**: LI_METAL
- **electrode_deposition**: SPUTTERED
- **atmosphere**: O2
- **sinter_temperature_C**: 1200.0

## Mg(BH4)2·1.47NH3 nanoconfined in SBA-15
`10.1038/s43246-024-00601-5` — `10.1038_s43246-024-00601-5.pdf`
- **sample_form**: COMPOSITE
- **pellet_diameter_mm**: 10.3
- **electrode_material**: STAINLESS_STEEL
- **electrode_deposition**: PRESSED
- **atmosphere**: AR
- **instrument**: Biologic

## Li2.61Y1.13Cl6 (MC)
`10.1021/acsenergylett.4c00317` — `10.1021_acsenergylett.4c00317.pdf`
- **sample_form**: COMPOSITE
- **pelletizing_pressure_MPa**: 8.0
- **electrode_material**: CARBON
- **electrode_deposition**: COATED
- **atmosphere**: HE

⚠️ *Suspicious (verify against paper):*
  - pelletizing_pressure_MPa=8.0 low (<15 MPa)

## Li3.08Ge0.52P0.47O4 (LGPO HTLP thin film)
`10.1039/d5ta07144e` — `10.1039_d5ta07144e.pdf`
- **sample_form**: PELLET
- **electrode_material**: BLOCKING
- **electrode_deposition**: SPUTTERED
- **atmosphere**: O2
- **sinter_temperature_C**: 900.0
- **sinter_time_h**: 12.0
- **instrument**: Biologic

## Li3PS4-2LiBH4
`10.1038/s41467-023-37564-z` — `10.1038_s41467-023-37564-z.pdf`
- **sample_form**: COMPOSITE
- **pellet_diameter_mm**: 0.127
- **relative_density_pct**: 86.0
- **pelletizing_pressure_MPa**: 55.0
- **electrode_material**: LI_METAL
- **electrode_deposition**: PRESSED
- **atmosphere**: AR
- **sinter_temperature_C**: 160.0
- **sinter_time_h**: 3.0
- **annealing_temperature_C**: 160.0
- **instrument**: Solartron

⚠️ *Suspicious (verify against paper):*
  - pellet_diameter_mm=0.127 outside 4–40 mm

## Mg(en)1(BH4)2
`10.1038/srep46189` — `10.1038_srep46189.pdf`
- **sample_form**: PELLET
- **pellet_diameter_mm**: 12.0
- **electrode_material**: STAINLESS_STEEL
- **electrode_deposition**: PRESSED
- **atmosphere**: AR
- **instrument**: Zahner

## Li2.61Y1.13Cl6 (SS)
`10.1021/acsenergylett.4c00317` — `10.1021_acsenergylett.4c00317.pdf`
- **sample_form**: COMPOSITE
- **pelletizing_pressure_MPa**: 8.0
- **electrode_material**: CARBON
- **electrode_deposition**: COATED
- **atmosphere**: HE

⚠️ *Suspicious (verify against paper):*
  - pelletizing_pressure_MPa=8.0 low (<15 MPa)

## Li2.96Ge0.72P0.32O4 (LGPO ITLP thin film)
`10.1039/d5ta07144e` — `10.1039_d5ta07144e.pdf`
- **sample_form**: PELLET
- **electrode_material**: BLOCKING
- **electrode_deposition**: SPUTTERED
- **atmosphere**: O2
- **sinter_temperature_C**: 900.0
- **sinter_time_h**: 12.0
- **instrument**: Biologic

## (Li0.45La0.78Ce0.05)ScO3
`10.3390/molecules26020299` — `10.3390_molecules26020299.pdf`
- **sample_form**: PELLET
- **pellet_diameter_mm**: 1.0
- **electrode_material**: LI_METAL
- **electrode_deposition**: PAINTED
- **atmosphere**: AR
- **sinter_temperature_C**: 623.0
- **instrument**: Solartron

⚠️ *Suspicious (verify against paper):*
  - pellet_diameter_mm=1.0 outside 4–40 mm

## Li6.65Ge0.05La3Zr1.85Ta0.15O12
`10.1016/j.ceramint.2023.09.330` — `10.1016_j.ceramint.2023.09.330.pdf`
- **sample_form**: THIN_FILM
- **thickness_mm**: 10.0
- **pelletizing_pressure_MPa**: 4.0
- **electrode_material**: BLOCKING
- **electrode_deposition**: COATED
- **atmosphere**: AIR
- **sinter_temperature_C**: 1050.0
- **instrument**: Novocontrol

⚠️ *Suspicious (verify against paper):*
  - pelletizing_pressure_MPa=4.0 low (<15 MPa)

## Li6.8Ge0.05La3Zr2O12
`10.1016/j.ceramint.2023.09.330` — `10.1016_j.ceramint.2023.09.330.pdf`
- **sample_form**: THIN_FILM
- **thickness_mm**: 10.0
- **pelletizing_pressure_MPa**: 4.0
- **electrode_material**: BLOCKING
- **electrode_deposition**: COATED
- **atmosphere**: AIR
- **sinter_temperature_C**: 1050.0
- **instrument**: Novocontrol

⚠️ *Suspicious (verify against paper):*
  - pelletizing_pressure_MPa=4.0 low (<15 MPa)

## Na3.2Hf0.8Sc0.2ZrSi2PO12
`10.1038/s41467-023-40669-0` — `10.1038_s41467-023-40669-0.pdf`
- **sample_form**: PELLET
- **pellet_diameter_mm**: 1.0
- **pelletizing_pressure_MPa**: 3.0
- **electrode_material**: STAINLESS_STEEL
- **electrode_deposition**: PRESSED
- **atmosphere**: GLOVEBOX

⚠️ *Suspicious (verify against paper):*
  - pelletizing_pressure_MPa=3.0 low (<15 MPa)
  - pellet_diameter_mm=1.0 outside 4–40 mm

## Na3.4Hf0.6Sc0.4ZrSi2PO12
`10.1038/s41467-023-40669-0` — `10.1038_s41467-023-40669-0.pdf`
- **sample_form**: PELLET
- **pellet_diameter_mm**: 1.0
- **pelletizing_pressure_MPa**: 3.0
- **electrode_material**: STAINLESS_STEEL
- **electrode_deposition**: PRESSED
- **atmosphere**: GLOVEBOX

⚠️ *Suspicious (verify against paper):*
  - pelletizing_pressure_MPa=3.0 low (<15 MPa)
  - pellet_diameter_mm=1.0 outside 4–40 mm

## Li0.35La0.55TiO3 (LLTO-F0)
`10.1007/s11664-021-09331-7` — `10.1007_s11664-021-09331-7.pdf`
- **sample_form**: COMPOSITE
- **pellet_diameter_mm**: 15.0
- **thickness_mm**: 1.0
- **relative_density_pct**: 95.4
- **pelletizing_pressure_MPa**: 10.0
- **electrode_material**: LI_METAL
- **electrode_deposition**: PRESSED
- **atmosphere**: AIR
- **sinter_temperature_C**: 800.0
- **sinter_time_h**: 2.0

⚠️ *Suspicious (verify against paper):*
  - pelletizing_pressure_MPa=10.0 low (<15 MPa)

## Li6.4Ga0.2La3Zr2O12 (x=0)
`10.1007/s11664-026-12871-5` — `10.1007_s11664-026-12871-5.pdf`
- **sample_form**: SINGLE_CRYSTAL
- **pellet_diameter_mm**: 10.0
- **thickness_mm**: 1.5
- **relative_density_pct**: 94.0
- **pelletizing_pressure_MPa**: 4.0
- **electrode_material**: LI_METAL
- **electrode_deposition**: COATED
- **frequency_min_Hz**: 20.0
- **frequency_max_Hz**: 20000000.0
- **atmosphere**: HE
- **instrument**: Novocontrol

⚠️ *Suspicious (verify against paper):*
  - pelletizing_pressure_MPa=4.0 low (<15 MPa)

## Li3OCl (x=1)
`10.3389/fchem.2020.562549` — `10.3389_fchem.2020.562549.pdf`
- **sample_form**: COMPOSITE
- **pellet_diameter_mm**: 0.3
- **electrode_material**: LI_METAL
- **electrode_deposition**: PRESSED
- **atmosphere**: INERT
- **instrument**: Biologic

⚠️ *Suspicious (verify against paper):*
  - pellet_diameter_mm=0.3 outside 4–40 mm

## Li3OCl (x=1.5)
`10.3389/fchem.2020.562549` — `10.3389_fchem.2020.562549.pdf`
- **sample_form**: COMPOSITE
- **pellet_diameter_mm**: 0.3
- **electrode_material**: LI_METAL
- **electrode_deposition**: PRESSED
- **atmosphere**: INERT
- **instrument**: Biologic

⚠️ *Suspicious (verify against paper):*
  - pellet_diameter_mm=0.3 outside 4–40 mm

## Li0.34La0.56TiO3 (G-LLTO)
`10.3389/fchem.2022.966274` — `10.3389_fchem.2022.966274.pdf`
- **sample_form**: MEMBRANE
- **pelletizing_pressure_MPa**: 200.0
- **electrode_material**: LI_METAL
- **electrode_deposition**: SPUTTERED
- **atmosphere**: AR
- **sinter_temperature_C**: 960.0
- **sinter_time_h**: 12.0
- **instrument**: Solartron

## Li0.34La0.56TiO3 (M-LLTO)
`10.3389/fchem.2022.966274` — `10.3389_fchem.2022.966274.pdf`
- **sample_form**: MEMBRANE
- **pelletizing_pressure_MPa**: 200.0
- **electrode_material**: LI_METAL
- **electrode_deposition**: SPUTTERED
- **atmosphere**: AR
- **sinter_temperature_C**: 960.0
- **sinter_time_h**: 12.0
- **instrument**: Solartron

## Li2OHCl
`10.1038/s41467-023-42385-1` — `10.1038_s41467-023-42385-1.pdf`
- **sample_form**: COMPOSITE
- **pellet_diameter_mm**: 1.0
- **pelletizing_pressure_MPa**: 480.0
- **electrode_material**: LI_METAL
- **electrode_deposition**: PRESSED
- **atmosphere**: INERT
- **sinter_temperature_C**: 120.0
- **annealing_temperature_C**: 120.0
- **instrument**: Autolab

⚠️ *Suspicious (verify against paper):*
  - pellet_diameter_mm=1.0 outside 4–40 mm

## Li(CB9H10)
`10.1038/s41467-019-09061-9` — `10.1038_s41467-019-09061-9.pdf`
- **sample_form**: COMPOSITE
- **pelletizing_pressure_MPa**: 153.6
- **electrode_material**: CARBON
- **electrode_deposition**: PRESSED
- **atmosphere**: VACUUM
- **instrument**: Solartron

## 0-LATP/PVDF-HFP-LiTFSI CSE
`10.3390/polym16091251` — `10.3390_polym16091251.pdf`
- **sample_form**: COMPOSITE
- **electrode_material**: LI_METAL
- **electrode_deposition**: PRESSED
- **atmosphere**: AIR

## Co-LATP/PVDF-HFP-LiTFSI CSE
`10.3390/polym16091251` — `10.3390_polym16091251.pdf`
- **sample_form**: COMPOSITE
- **electrode_material**: LI_METAL
- **electrode_deposition**: PRESSED
- **atmosphere**: AIR

## Cu-LATP/PVDF-HFP-LiTFSI CSE
`10.3390/polym16091251` — `10.3390_polym16091251.pdf`
- **sample_form**: COMPOSITE
- **electrode_material**: LI_METAL
- **electrode_deposition**: PRESSED
- **atmosphere**: AIR

## V-LATP/PVDF-HFP-LiTFSI CSE
`10.3390/polym16091251` — `10.3390_polym16091251.pdf`
- **sample_form**: COMPOSITE
- **electrode_material**: LI_METAL
- **electrode_deposition**: PRESSED
- **atmosphere**: AIR

## Zr-LATP/PVDF-HFP-LiTFSI CSE
`10.3390/polym16091251` — `10.3390_polym16091251.pdf`
- **sample_form**: COMPOSITE
- **electrode_material**: LI_METAL
- **electrode_deposition**: PRESSED
- **atmosphere**: AIR

## Li6PS5Cl
`10.3390/ma16072751` — `10.3390_ma16072751.pdf`
- **sample_form**: COMPOSITE
- **pellet_diameter_mm**: 8.0
- **pelletizing_pressure_MPa**: 25.0
- **electrode_material**: LI_METAL
- **atmosphere**: VACUUM

## LiBH4-MgO (CE26)
`10.1021/acsaem.0c02525` — `10.1021_acsaem.0c02525.pdf`
- **sample_form**: COMPOSITE
- **pellet_diameter_mm**: 10.0
- **pelletizing_pressure_MPa**: 60.0
- **electrode_material**: LI_METAL
- **electrode_deposition**: PRESSED
- **atmosphere**: AR
- **instrument**: Biologic

## LiBH4-MgO (CE74)
`10.1021/acsaem.0c02525` — `10.1021_acsaem.0c02525.pdf`
- **sample_form**: COMPOSITE
- **pellet_diameter_mm**: 10.0
- **pelletizing_pressure_MPa**: 60.0
- **electrode_material**: LI_METAL
- **electrode_deposition**: PRESSED
- **atmosphere**: AR
- **instrument**: Biologic

## Li6PS5Cl
`10.1021/acsaem.3c02858` — `10.1021_acsaem.3c02858.pdf`
- **sample_form**: COMPOSITE
- **pellet_diameter_mm**: 12.0
- **pelletizing_pressure_MPa**: 348.0
- **electrode_material**: STAINLESS_STEEL
- **electrode_deposition**: PRESSED
- **frequency_min_Hz**: 0.1
- **frequency_max_Hz**: 1000000.0
- **atmosphere**: GLOVEBOX
- **instrument**: Biologic

## Li6PS5Cl/TEGDMA
`10.1021/acsaem.3c02858` — `10.1021_acsaem.3c02858.pdf`
- **sample_form**: COMPOSITE
- **pellet_diameter_mm**: 12.0
- **pelletizing_pressure_MPa**: 348.0
- **electrode_material**: STAINLESS_STEEL
- **electrode_deposition**: PRESSED
- **frequency_min_Hz**: 0.1
- **frequency_max_Hz**: 1000000.0
- **atmosphere**: GLOVEBOX
- **instrument**: Biologic

## LATP-0.1LBSO
`10.1016/j.jallcom.2019.153072` — `10.1016_j.jallcom.2019.153072.pdf`
- **sample_form**: COMPOSITE
- **pellet_diameter_mm**: 2.0
- **pelletizing_pressure_MPa**: 10.0
- **electrode_material**: STAINLESS_STEEL
- **electrode_deposition**: PRESSED
- **atmosphere**: O2
- **sinter_temperature_C**: 800.0
- **annealing_temperature_C**: 1100.0

⚠️ *Suspicious (verify against paper):*
  - pelletizing_pressure_MPa=10.0 low (<15 MPa)
  - pellet_diameter_mm=2.0 outside 4–40 mm

## Li0.27La0.58TiO3
`10.15625/0868-3166/17946` — `10.15625_0868-3166_17946.pdf`
- **sample_form**: COMPOSITE
- **relative_density_pct**: 76.0
- **pelletizing_pressure_MPa**: 60.0
- **electrode_material**: BLOCKING
- **atmosphere**: AIR
- **instrument**: Autolab

## Li1.3Al0.3Ti1.7(PO4)3
`10.1016/j.jallcom.2019.153072` — `10.1016_j.jallcom.2019.153072.pdf`
- **sample_form**: COMPOSITE
- **pellet_diameter_mm**: 2.0
- **pelletizing_pressure_MPa**: 10.0
- **electrode_material**: STAINLESS_STEEL
- **electrode_deposition**: PRESSED
- **atmosphere**: O2
- **sinter_temperature_C**: 800.0
- **annealing_temperature_C**: 1100.0

⚠️ *Suspicious (verify against paper):*
  - pelletizing_pressure_MPa=10.0 low (<15 MPa)
  - pellet_diameter_mm=2.0 outside 4–40 mm

## Li3.7Ge0.7As0.3S4
`10.1021/acsami.4c22390` — `10.1021_acsami.4c22390.pdf`
- **sample_form**: FILM
- **electrode_material**: STAINLESS_STEEL
- **electrode_deposition**: PRESSED
- **atmosphere**: GLOVEBOX
- **instrument**: Gamry

## Li3.7Ge0.7P0.3S4
`10.1021/acsami.4c22390` — `10.1021_acsami.4c22390.pdf`
- **sample_form**: FILM
- **electrode_material**: STAINLESS_STEEL
- **electrode_deposition**: PRESSED
- **atmosphere**: GLOVEBOX
- **instrument**: Gamry

## Li3.7Ge0.7Sb0.3S4
`10.1021/acsami.4c22390` — `10.1021_acsami.4c22390.pdf`
- **sample_form**: FILM
- **electrode_material**: STAINLESS_STEEL
- **electrode_deposition**: PRESSED
- **atmosphere**: GLOVEBOX
- **instrument**: Gamry

## Li4GeS4
`10.1021/acsami.4c22390` — `10.1021_acsami.4c22390.pdf`
- **sample_form**: FILM
- **electrode_material**: STAINLESS_STEEL
- **electrode_deposition**: PRESSED
- **atmosphere**: GLOVEBOX
- **instrument**: Gamry

## PVDF-HFP/10%LLZTO
`10.3390/gels12060534` — `10.3390_gels12060534.pdf`
- **sample_form**: MEMBRANE
- **electrode_material**: CARBON
- **electrode_deposition**: SPUTTERED
- **atmosphere**: GLOVEBOX
