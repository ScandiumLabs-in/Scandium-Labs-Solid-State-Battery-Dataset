# Structure-to-label attribution audit (guide §5 action 6)

Structure-to-label attribution audit: each verified label's composition is reduced-formula matched against the structure-bearing Materials Project backbone. 'structure_attached' means a DFT structure of the same reduced formula exists and is what featurization pairs with the label (this structure is from MP, NOT from the measurement paper — the documented systematic borrow our architecture makes). 'n_mp_structures_for_formula' counts distinct polymorph structures, exposing ambiguity about which polymorph the label was measured on.

- Verified/gold labeled rows: **183**
- With a structure-attached MP match: **35** (19%)
- Without any MP structure match: **148**

Labeled rows WITHOUT an MP structure match:

- `(Li0.45La0.78Ce0.05)ScO3`
- `(Li0.45La0.85)ScO3`
- `(Li0.4Ce0.15La0.67)ScO3`
- `(Li2OH)0.99K0.01Cl`
- `0-LATP/PVDF-HFP-LiTFSI CSE`
- `0.5Li2SO4-ZrCl4`
- `0.7Li(CB9H10)-0.3Li(CB11H12)`
- `1.4Li2O-0.75ZrCl4-0.25AlCl3`
- `40wt% Li2OHCl0.5Br0.5/NBR CPE`
- `80(3LiBH4LiCl)20P2S5`
- `C4N2H12ZnBr4`
- `Ca-CeO2/LiTFSI/PEO`
- `Co-LATP/PVDF-HFP-LiTFSI CSE`
- `CsSn0.9In0.067Cl3`
- `Cu-LATP/PVDF-HFP-LiTFSI CSE`
- `LATP-0.1LBSO`
- `La0.57Li0.29TiO3`
- `Li(BH4)1-xIx`
- `Li(CB9H10)`
- `Li0.27La0.58TiO3`
- `Li0.29La0.57TiO3`
- `Li0.33La0.56TiO3`
- `Li0.34La0.56TiO3 (G-LLTO)`
- `Li0.34La0.56TiO3 (M-LLTO)`
- `Li0.35La0.55TiO3`
- `Li0.35La0.55TiO3 (LLTO-F0)`
- `Li0.35La0.55TiO3-2wt%LiF`
- `Li0.35La0.55TiO3-4wt%LiF`
- `Li0.35La0.55TiO3-6wt%LiF`
- `Li0.35La0.55TiO3-F2`
- `Li0.375Sr0.4375Ta0.75Zr0.25O3`
- `Li0.4Sr0.3Ti1.5Zr0.5(PO4)3`
- `Li0.4Sr0.3Zr2(PO4)3`
- `Li1.3Al0.15Y0.15Ti1.7(PO4)3`
- `Li1.3Al0.25Y0.05Ti1.7(PO4)3`
- `Li1.3Al0.29Y0.01Ti1.7(PO4)3`
- `Li1.3Al0.2Y0.1Ti1.7(PO4)3`
- `Li1.3Al0.3BxTi1.7-x(PO4)3 (10% H3BO3)`
- `Li1.3Al0.3In0.1Ti1.7(PO4)3/PVDF`
- `Li1.3Al0.3Ti1.7(PO4)3`
- `Li1.3Al0.3Ti1.7(PO4)3-4wt%Li0.348La0.55TiO3`
- `Li1.3Al0.3Ti1.7(PO4)3-PVDF-HFP`
- `Li1.3Al0.3Ti1.7(PO4)3/PVDF-HFP CSE`
- `Li1.5Al0.5Ge1.5(PO4)3`
- `Li2.50In0.56Nb0.06Zr0.38Cl6`
- `Li2.51In0.63Nb0.12Zr0.25Cl6`
- `Li2.56In0.75Nb0.19Zr0.06Cl6`
- `Li2.61Y1.13Cl6 (MC)`
- `Li2.61Y1.13Cl6 (SS)`
- `Li2.96Ge0.72P0.32O4 (LGPO ITLP thin film)`
- `Li2O-TaCl5`
- `Li2SO4-ZrCl4`
- `Li2ZrCl5.5F0.5`
- `Li2ZrCl6`
- `Li3.08Ge0.52P0.47O4 (LGPO HTLP thin film)`
- `Li3.7Ge0.7As0.3S4`
- `Li3.7Ge0.7P0.3S4`
- `Li3.7Ge0.7Sb0.3S4`
- `Li3OCl (x=1)`
- `Li3OCl (x=1.5)`
- `Li3PS4-2LiBH4`
- `Li3YCl6`
- `Li3YCl6 (as-prepared)`
- `Li3Zr2Si2PO12`
- `Li3xZrCl4Nx`
- `Li4-xGe1-xPxO4`
- `Li4.8InCl7.8`
- `Li5.4Al0.1PS4.7Cl1.3`
- `Li5.5PS4.5Cl1.5`
- `Li6.1Ga0.3La3Zr2O12 (LGLZO_5)`
- `Li6.25Al0.25La3Zr2O12-in-PEGDA`
- `Li6.4Ga0.2La3Zr1.9Ce0.1O12`
- `Li6.4Ga0.2La3Zr2O12`
- `Li6.4Ga0.2La3Zr2O12 (x=0)`
- `Li6.55Ge0.05La3Zr1.75Ta0.25O12`
- `Li6.5Fe0.2La3Zr1.9Bi0.1O12`
- `Li6.5La3-xBaxZr1.5-xTa0.5+xO12`
- `Li6.5La3Zr1.5Ta0.5O12`
- `Li6.5P0.5Ge0.5S5I`
- `Li6.65Ge0.05La3Zr1.85Ta0.15O12`
- `Li6.6La3Zr1.6Nb0.4O12`
- `Li6.7Ge0.595Si0.105P0.3S5I`
- `Li6.8-0.25Ge0.05La3Zr1.75Ta0.25O12`
- `Li6.8Ge0.05La3Zr2O12`
- `Li6.98Ga0.072La3Zr1.982Ta0.018O12`
- `Li6PS4Cl0.75-OF0.25`
- `Li6PS5Cl/TEGDMA`
- `Li6PS5Cl0.5Br0.5`
- `Li7La2.75Ca0.25Zr1.75Nb0.25O12`
- `Li7La3Zr0.4Hf0.4Sn0.4Sc0.4Ta0.4O12`
- `Li7La3Zr0.5Hf0.5Sc0.5Nb0.5O12`
- `Li7La3Zr2O12-8wt.%Li3BO3`
- `Li9.54Si1.74P1.44S11.7Cl0.3`
- `Li9.54[Si0.6Ge0.4]1.74P1.44S11.1Br0.3O0.6`
- `LiBH4-LiI/Al2O3`
- `LiBH4-MgO`
- `LiBH4-MgO (CE26)`
- `LiBH4-MgO (CE74)`
- `LiCB9H10`
- `LiDFOB-TXE-FDMA-FEC`
- `LiTFSI-PC(quasi-solid)`
- `LiTFSI-SN`
- `LiTFSI-SN-FEC`
- `Mg(BH4)21.47NH3`
- `Mg(BH4)2·1.47NH3 nanoconfined in SBA-15`
- `Mg(en)1(BH4)2`
- `NBR SPE`
- `Na2.9H(Se0.9I0.1)`
- `Na3.2Hf0.8Sc0.2ZrSi2PO12`
- `Na3.4Hf0.6Sc0.4ZrSi2PO12`
- `Na3HSe`
- `Na3HfSc(SiO4)(PO4)2`
- `Na3HfZr(SiO4)2(PO4)`
- `Na3PS4`
- `NaCB9H10`
- `PAFP`
- `PEO`
- `PEO-5% COF-LZU1`
- `PEO-LiTFSI`
- `PEO-LiTFSI-AlOC`
- `PEO-LiTFSI-LLZTO-SN-ETPTA`
- `PEO-PAPI (crosslinked)`
- `PEO/LiFSI`
- `PEO/LiTFSI`
- `PEO/LiTFSI (electrospun)`
- `PEO/LiTFSI/in-situ SiO2 (10wt%)`
- `PVDF-HFP`
- `PVDF-HFP-LLZTO(10wt%)`
- `PVDF-HFP/10%LLZTO`
- `Sn-LATP/PVDF-HFP-LiTFSI CSE`
- `UiO-66/PEO`
- `V-LATP/PVDF-HFP-LiTFSI CSE`
- `Zr-LATP/PVDF-HFP-LiTFSI CSE`

Polymorph ambiguity: **11** attached labels match a formula with >1 distinct MP structure.

| composition | n MP structures |
|---|---|
| Li10GeP2S12 | 2 |
| Li10GeP2S12 | 2 |
| Li2B12H12 | 3 |
| Li3InCl6 | 2 |
| Li3InCl6 | 2 |
| Li3InCl6 | 2 |
| Li3InCl6 | 2 |
| Li3PS4 | 3 |
| Li4GeS4 | 3 |
| Li6PS5I | 2 |
| LiBH4 | 9 |

Structure borrowing is systematic and documented here: labeled rows carry an MP DFT structure of the same composition, not the paper's own structure. Labels with no MP structure match have no structure at all (honest gap). Labels matching a formula with multiple MP polymorphs are ambiguous about which polymorph was measured — model cards should caveat this.
