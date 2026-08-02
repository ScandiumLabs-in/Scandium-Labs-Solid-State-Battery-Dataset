# Verification Summary

- Records swept: **53**
- Generated: from `/home/shamique/Scandium labs SSB dataset/literature_output/verification_results.json` and `/home/shamique/Scandium labs SSB dataset/review_output/queue.json`

## Auto-decision distribution

- **auto_approve** (auto-approve (no human needed)): 0
- **spot_check** (quick spot check): 1
- **needs_review** (full human review): 12
- **reject** (reject or re-extract): 40

## Highest-confidence records

| Score | Decision | Composition | Property | Value | Agreement | Literature | Flags |
|-------|----------|-------------|----------|-------|-----------|------------|-------|
| 96.2 | spot_check | Li2ZrCl6 | conductivity | 0.00081 | 2/2 | agree | literature agree |
| 92.5 | needs_review | Li2ZrCl6 | activation_energy | 0.35 | 2/2 | pending | — |
| 92.5 | needs_review | Li6PS5Cl | activation_energy | 0.22 | 2/2 | pending | — |
| 90.0 | needs_review | Li1.3+yAl0.3-xMxTi1.7(PO4)3(M=Mg) | conductivity | 0.0008 | 1/1 | no_ref | — |
| 89.5 | needs_review | Li6.4Fe0.2La3Zr2O12 | activation_energy | 0.25 | 1/1 | pending | — |
| 89.5 | needs_review | LiBH4-LiI/Al2O3 | activation_energy | 0.43 | 2/2 | pending | — |
| 87.0 | needs_review | Mg(BH4)21.47NH3 | conductivity | 0.00074 | 1/1 | no_ref | — |
| 87.0 | needs_review | Li5.4Al0.1PS4.7Cl1.3 | conductivity | 0.00729 | 1/1 | no_ref | — |
| 87.0 | needs_review | LiBH4-LiI/Al2O3 | conductivity | 0.001 | 2/2 | no_ref | — |
| 84.8 | needs_review | Li6.5La3Zr1.5Ta0.5O12 | conductivity | 0.00018 | 1/1 | conflict | literature conflict |
| 82.0 | needs_review | Li7La3Zr2O12 | conductivity | 0.0003 | 2/3 | agree | literature agree |
| 82.0 | needs_review | Li7La3Zr2O12 | activation_energy | 0.3 | 3/3 | pending | — |
| 80.0 | needs_review | Li2ZrCl6 | activation_energy | 0.5 | 1/2 | pending | — |
| 79.6 | reject | Li6PS5Cl | conductivity | 0.001 | 1/3 | agree | literature agree |
| 78.2 | reject | LiBH4-MgO | conductivity | 0.000286 | 1/2 | agree | literature agree |

## Human review queue (13 records)

### Li2ZrCl6 — conductivity = 0.00081  (score 96.2, spot_check)
- paper: `10.1038_s41467-021-24697-2`  page 1
- model agreement: 2/2  literature: agree
  Verdicts:
  - llama-3.1-8b-instant: sigma=None ea=None comp=None quote="0.81 mS cm–1"
  - llama-3.3-70b-versatile: sigma=None ea=None comp=None quote="0.81 mS cm–1"
  Evidence: s unlikely. Here, a cost-effective chloride solid elec- trolyte, Li2ZrCl6, is reported. Its raw materials are several orders of magnitude cheaper than those for the state-of-the-art chloride solid ele

### Li2ZrCl6 — activation_energy = 0.35  (score 92.5, needs_review)
- paper: `10.1038_s41467-021-24697-2`  page 3
- model agreement: 2/2  literature: pending
  Verdicts:
  - llama-3.1-8b-instant: sigma=None ea=None comp=None quote="0.35 eV"
  - llama-3.3-70b-versatile: sigma=None ea=None comp=None quote="the activation energy of the as- milled LZC (0.35 eV)"
  Evidence: teries. In addition to the room- temperature ionic conductivities, the activation energies were evaluated through the Arrhenius plot (Fig. 2d). Consistent with the measured ionic conductivities, the a

### Li6PS5Cl — activation_energy = 0.22  (score 92.5, needs_review)
- paper: `10.3390_nano12244355`  page 3
- model agreement: 2/2  literature: pending
  Verdicts:
  - llama-3.1-8b-instant: sigma=None ea=None comp=None quote="The Ea value of the Li6PS5Cl electrolyte was 0.22 eV"
  - llama-3.3-70b-versatile: sigma=None ea=None comp=None quote="The Ea value of the Li6PS5Cl electrolyte was 0.22 eV,"
  Evidence: ion, σ = A exp(−Ea/kT), where T is the absolute temperature, A is a pre-exponential factor, and k is the Boltzmann constant. The Ea value of the Li6PS5Cl electrolyte was 0.22 eV, and the Ea values of 

### Li1.3+yAl0.3-xMxTi1.7(PO4)3(M=Mg) — conductivity = 0.0008  (score 90.0, needs_review)
- paper: `10.1039_d2ra05782d`  page 2
- model agreement: 1/1  literature: no_ref
  Verdicts:
  - llama-3.1-8b-instant: sigma=None ea=None comp=None quote=""
  Evidence: d to the solution. The total mass of the dry components was about 20 g, and the water volume was 25 mL. The prepared solution was mixed using a magnetic stirrer at 70 °C for 12 h until dry. Then the r

### Li6.4Fe0.2La3Zr2O12 — activation_energy = 0.25  (score 89.5, needs_review)
- paper: `10.3390_molecules30092028`  page 2
- model agreement: 1/1  literature: pending
  Verdicts:
  - llama-3.1-8b-instant: sigma=None ea=None comp=None quote="0.25"
  Evidence: s it tends to have a more pronounced effect on improving both the ionic conductivity and sintering activity compared with single-element doping. Zhou et al. co-doped Sr2+ and Mo6+ into LLZO to obtain 

### LiBH4-LiI/Al2O3 — activation_energy = 0.43  (score 89.5, needs_review)
- paper: `10.1021_acsami.0c10361`  page 1
- model agreement: 2/2  literature: pending
  Verdicts:
  - llama-3.1-8b-instant: sigma=None ea=None comp=None quote="an activation energy of 0.43 eV"
  - llama-3.3-70b-versatile: sigma=None ea=None comp=None quote="an activation energy of 0.43 eV"
  Evidence: ic diﬀusion coeﬃcients from PFG NMR agree with those estimated from measurements of ionic conductivity and nuclear spin relaxation. The resulting 3D ionic transport in nanoconﬁned LiBH4-LiI/Al2O3 is c

### Mg(BH4)21.47NH3 — conductivity = 0.00074  (score 87.0, needs_review)
- paper: `10.1038_s43246-024-00601-5`  page 1
- model agreement: 1/1  literature: no_ref
  Verdicts:
  - llama-3.1-8b-instant: sigma=None ea=None comp=None quote=""
  Evidence: communications materials Article https://doi.org/10.1038/s43246-024-00601-5 Nanoconﬁnement of an ammine magnesium borohydride composite electrolyte in a mesoporous silica scaffold Check for updates Pa

### Li5.4Al0.1PS4.7Cl1.3 — conductivity = 0.00729  (score 87.0, needs_review)
- paper: `10.3390_nano12244355`  page 1
- model agreement: 1/1  literature: no_ref
  Verdicts:
  - llama-3.1-8b-instant: sigma=None ea=None comp=None quote=""
  Evidence: Citation: Choi, Y.J.; Kim, S.-I.; Son, M.; Lee, J.W.; Lee, D.H. Cl- and Al-Doped Argyrodite Solid Electrolyte Li6PS5Cl for All-Solid-State Lithium Batteries with Improved Ionic Conductivity. Nanomater

### LiBH4-LiI/Al2O3 — conductivity = 0.001  (score 87.0, needs_review)
- paper: `10.1021_acsami.0c10361`  page 1
- model agreement: 2/2  literature: no_ref
  Verdicts:
  - llama-3.1-8b-instant: sigma=None ea=None comp=None quote=""
  - llama-3.3-70b-versatile: sigma=None ea=None comp=None quote=""
  Evidence: tained that revealed promising properties as a solid electrolyte. The underlying principles of Li+ conduction in such a nanocomposite are, however, far from being understood completely. Here, we used 

### Li6.5La3Zr1.5Ta0.5O12 — conductivity = 0.00018  (score 84.8, needs_review)
- paper: `10.1038_s41467-025-58108-7`  page 5
- model agreement: 1/1  literature: conflict
  Verdicts:
  - llama-3.1-8b-instant: sigma=None ea=None comp=None quote=""
  Evidence: within the temperature range of 25–1000 °C. As depicted in Fig. 2c, the cubic-phase formation starts at 400 °C, indicated by the emergence of the two distinctive diffraction peaks at ~16° and ~19°, co

### Li7La3Zr2O12 — conductivity = 0.0003  (score 82.0, needs_review)
- paper: `10.1021_acs.chemmater.3c01831`  page 3
- model agreement: 2/3  literature: agree
  Verdicts:
  - llama-3.1-8b-instant: sigma=None ea=None comp=None quote="~ 3´10-4 Scm-1"
  - llama-3.3-70b-versatile: sigma=None ea=None comp=None quote="~ 3´10-4 Scm-1"
  - openai/gpt-oss-20b: sigma=None ea=None comp=None quote=""
  Evidence: s, sulphides and  nitrides have been explored as solid electrolytes. Li-rich garnets (Li7La3Zr2O12, LLZO) possess  high room temperature (RT) ionic conductivity and relatively wide electrochemical sta

### Li7La3Zr2O12 — activation_energy = 0.3  (score 82.0, needs_review)
- paper: `10.1021_acs.chemmater.3c01831`  page 3
- model agreement: 3/3  literature: pending
  Verdicts:
  - llama-3.1-8b-instant: sigma=None ea=None comp=None quote="a low activation energy of 0.3 eV"
  - llama-3.3-70b-versatile: sigma=None ea=None comp=None quote="~ 3´10-4 Scm-1"
  - openai/gpt-oss-20b: sigma=None ea=None comp=None quote=""
  Evidence: s, sulphides and  nitrides have been explored as solid electrolytes. Li-rich garnets (Li7La3Zr2O12, LLZO) possess  high room temperature (RT) ionic conductivity and relatively wide electrochemical sta

### Li2ZrCl6 — activation_energy = 0.5  (score 80.0, needs_review)
- paper: `10.1038_s41467-021-24697-2`  page 3
- model agreement: 1/2  literature: pending
  Verdicts:
  - llama-3.1-8b-instant: sigma=None ea=None comp=None quote="0.50 eV"
  - llama-3.3-70b-versatile: sigma=None ea=None comp=None quote="the activation energy of the as- milled LZC (0.35 eV) is much lower than that of the 350 °C- annealed one (0.50 eV)"
  Evidence: ies, the activation energies were evaluated through the Arrhenius plot (Fig. 2d). Consistent with the measured ionic conductivities, the activation energy of the as- milled LZC (0.35 eV) is much lower

## Rejected records by cause

### weak evidence / low agreement: 21
- `Li1.3+yAl0.3MxTi1.7-x(PO4)3(M=Hf)` conductivity=0.0011 (score 62.0, agree 0/0)
- `Li6.4Fe0.2La3Zr2O12` conductivity=0.0001 (score 62.0, agree 0/0)
- `Mg(BH4)21.47NH3` conductivity=0.00027 (score 62.0, agree 0/0)
- `Li6.6La3Zr1.6Nb0.4O12` activation_energy=0.311 (score 62.0, agree 0/0)
- `Li1.3Al0.3Ti1.7(PO4)3` activation_energy=0.25 (score 72.8, agree 1/3)
- `Li6PS5Cl` conductivity=0.001 (score 79.6, agree 1/3)
- `Li3Zr2Si2PO12` activation_energy=0.21 (score 62.0, agree 0/0)
- `Mg(BH4)21.47NH3` conductivity=6.3e-06 (score 62.0, agree 0/0)
- `La0.57Li0.29TiO3` conductivity=0.00021 (score 62.0, agree 0/0)
- `LiBH4-MgO` conductivity=0.000286 (score 78.2, agree 1/2)
- `Li5.5PS4.5Cl1.5` activation_energy=0.17 (score 62.0, agree 0/0)
- `Li3OCl` conductivity=3.21e-05 (score 65.8, agree 0/0)
- `Li1.3+yAl0.3MxTi1.7-x(PO4)3(M=Zr)` conductivity=0.0012 (score 62.0, agree 0/0)
- `Li6.5Fe0.2La3Zr1.9Bi0.1O12` activation_energy=0.22 (score 62.0, agree 0/0)
- `Li6.5Fe0.2La3Zr1.9Bi0.1O12` conductivity=0.000757 (score 62.0, agree 0/0)
- `Li6.4La3Zr1.4Ta0.6O12` conductivity=0.0005 (score 78.2, agree 1/2)
- `Li6.6La3Zr1.6Nb0.4O12` conductivity=0.000509 (score 62.0, agree 0/0)
- `Li1.3Al0.3In0.1Ti1.7(PO4)3/PVDF` conductivity=1.7e-05 (score 62.0, agree 0/0)
- `Mg(BH4)21.47NH3` activation_energy=0.69 (score 62.0, agree 0/0)
- `Li1.3+yAl0.3-xMxTi1.7(PO4)3(M=Sr)` conductivity=0.0006 (score 62.0, agree 0/0)
- `Li1.3+yAl0.3-xMxTi1.7(PO4)3(M=Ca)` conductivity=0.0007 (score 62.0, agree 0/0)

### physics/range fail: 8
- `0.7Li(CB9H10)-0.3Li(CB11H12)` conductivity=0.0067 (score 47.0, agree 0/2)
- `Li2ZrCl6` conductivity=5.81e-07 (score 66.8, agree 2/2)
- `Li6.25Al0.25La3Zr2O12-in-PEGDA` activation_energy=0.25 (score 28.2, agree 0/0)
- `Li1.3Al0.3In0.1Ti1.7(PO4)3/PVDF` activation_energy=0.23 (score 28.2, agree 0/0)
- `Li5.4Al0.1PS4.7Cl1.3` activation_energy=0.09 (score 47.0, agree 0/0)
- `Li3Zr2Si2PO12` conductivity=3.59e-06 (score 59.5, agree 1/2)
- `PEO-LiTFSI` activation_energy=0.15 (score 28.2, agree 0/0)
- `0.7Li(CB9H10)-0.3Li(CB11H12)` activation_energy=0.0289 (score 47.0, agree 0/0)

### no evidence located: 5
- `Li1.3+yAl0.3-xMxTi1.7(PO4)3(M=Mg)` activation_energy=0.28 (score 43.2, agree 0/0)
- `Li1.3+yAl0.3MxTi1.7-x(PO4)3(M=Hf)` activation_energy=0.23 (score 43.2, agree 0/0)
- `Li1.3+yAl0.3MxTi1.7-x(PO4)3(M=Zr)` activation_energy=0.22 (score 43.2, agree 0/0)
- `Li1.3+yAl0.3-xMxTi1.7(PO4)3(M=Ca)` activation_energy=0.29 (score 43.2, agree 0/0)
- `Li1.3+yAl0.3-xMxTi1.7(PO4)3(M=Sr)` activation_energy=0.3 (score 43.2, agree 0/0)

### models disagree / value not confirmed: 4
- `Ca-CeO2/LiTFSI/PEO` conductivity=0.00013 (score 67.5, agree 0/3)
- `Li5.5PS4.5Cl1.5` conductivity=0.00505 (score 62.0, agree 0/2)
- `Li6.5La3-xBaxZr1.5-xTa0.5+xO12` conductivity=0.000834 (score 68.8, agree 0/2)
- `Li6.25Al0.25La3Zr2O12-in-PEGDA` conductivity=0.00051 (score 62.0, agree 0/2)

### conflicts benchmark: 2
- `PEO-LiTFSI` conductivity=0.00018 (score 56.8, agree 0/0)
- `Li1.3Al0.3Ti1.7(PO4)3` conductivity=0.001 (score 69.2, agree 1/2)
