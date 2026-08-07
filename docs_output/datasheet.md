# Datasheet: Scandium Labs Solid-State Battery Electrolyte Dataset

## Motivation

**For what purpose was the dataset created?**
To provide the first unified, provenance-tracked, ML-ready dataset of Li-ion
conductivity and activation energy values for solid-state battery electrolyte
materials across all 11 major SSB families (sulfides, oxides, garnets,
perovskites, NASICONs, halides, argyrodites, hydrides, borohydrides,
antiperovskites, and polymer/composites).

**Who created the dataset and on behalf of which entity?**
Scandium Labs. The dataset was built using the automated pipeline in this
repository.

**Who funded the creation of the dataset?**
Scandium Labs (self-funded).

## Composition

**Total records:** 30838
**Records per family:** {
  "oxide": 20753,
  "unknown": 5635,
  "halide": 2434,
  "sulfide": 804,
  "nasicon": 441,
  "hydride": 244,
  "polymer_composite": 187,
  "borohydride": 114,
  "antiperovskite": 84,
  "garnet": 68,
  "perovskite": 47,
  "argyrodite": 27
}
**Records per source:** {
  "materials_project": 21528,
  "jarvis": 8327,
  "cod": 500,
  "literature_mined": 183,
  "aflow": 150,
  "nomad": 100,
  "oqmd": 50
}
**Records with verified experimental transport label:** 183
**Records with raw σ_RT value:** 166

**What are the instances?**
Each instance is a unique material record identified by composition and source,
with associated structural, thermodynamic, and ion-transport properties.

**Are there recommended data splits?**
Yes — see `features_output/splits_metadata.json`. Splits are grouped by
composition-family key to prevent leakage between polymorphs/doped variants
of the same base composition.

## Collection Process

**How was the data collected?**
Data was collected through three parallel channels:
1. Bulk API pull from Materials Project, JARVIS-DFT, AFLOW, OQMD, NOMAD,
   and ICSD (where accessible).
2. Literature mining via Semantic Scholar discovery + GROBID table extraction
   + LLM-based structured extraction.
3. In-house DFT computation (VASP/Quantum Espresso) for priority gap compounds.

**Who was involved in the data collection process?**
The automated pipeline in this repository.

## Preprocessing / Cleaning / Labeling

**Was any preprocessing or cleaning applied?**
Yes — the Phase 4 cleaning pipeline:
- Unit standardization (conductivity → S/cm, energy → eV, temperature → K)
- Arrhenius consistency filtering (flagging implausible sigma/Ea pairs)
- Cross-source structural deduplication using pymatgen StructureMatcher
- Missing-data audit (sentinel detection, label-presence verification)

**Was a benchmark subset created?**
Yes — a gold benchmark subset of highest-confidence records (verified_human or
dft_native with measured sigma_RT) was selected for leaderboard-style model
comparison. See `features_output/gold.parquet`.

## Known Limitations & Biases

**What are the known limitations?**
- Sulfides and garnets are overrepresented relative to antiperovskites and
  hydrides because they are more studied in the literature — this reflects
  the state of the field, not a sampling choice.
- AIMD-computed conductivities (where present) are not equivalent to measured
  values — check `conductivity_source_type` before blending.
- Polymer/composite records are not compatible with standard crystal-graph
  featurization — use the separate polymer feature set.
- Disorder-aware occupancy: the schema carries `structure.li_site_occupancy`
  and `structure.structure_type` specifically so occupancy-weighted models
  (OBELiX-style disorder-aware CGCNN/SO3Net) can be built. Be aware that the
  current harvest captures fully-occupied Li sites only — every stored
  occupancy is 1.0 and every MP row is `structure_type=ordered`. Standard GNN
  implementations (CGCNN, SchNet, PaiNN, etc.) silently round partial
  occupancy to integers anyway, so this does not change their default
  behavior — but if you ingest partial-occupancy structures yourself, round
  them only if you intend the integer-site approximation. Do not treat the
  stored `li_site_occupancy` as evidence of partial site occupancy; it is the
  harvested (fully-occupied) structure's Li-site list.

**What are the recommended uses?**
- Training ML models for ionic conductivity prediction
- Benchmarking new models against the gold subset
- Identifying under-explored composition spaces (especially halides and
  antiperovskites)

**What are the explicitly discouraged uses?**
- Treating literature-mined values as equivalent to experimentally verified
  values without checking `confidence_tier`
- Using AIMD-computed conductivities as direct substitutes for experimental
  measurements

## Licensing

**What license applies to this dataset?**
The Scandium-authored portions (processing, quality scoring, validation,
analysis, documentation) are released under CC-BY-4.0. Third-party records
retain their respective source-database licenses, identified per row via
`identity.source_db`. The current release includes **150 AFLOW rows restricted
to scientific/academic/non-commercial use**, plus rows from Materials Project,
JARVIS-DFT, COD, NOMAD, and OQMD under their permissive terms. See
`LICENSE` and `LICENSE_BREAKDOWN.md` for the authoritative per-source license
table, record counts, and the "AS IS" warranty disclaimer. Consult
`identity.source_db` before assuming redistribution rights for any record.

## Maintenance

**Who maintains the dataset?**
Scandium Labs. The dataset is versioned (see CHANGELOG.md) and will receive
quarterly re-ingestion passes as source databases update.

**How can the dataset be extended?**
Community contributions are welcome — see CONTRIBUTING.md for the structured
submission template.
