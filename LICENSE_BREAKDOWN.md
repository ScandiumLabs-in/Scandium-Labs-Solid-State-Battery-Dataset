# License Breakdown — Scandium Labs SSB Dataset

This document is the authoritative per-source license reference for the
released dataset. The blanket CC-BY-4.0 grant in `LICENSE` covers only
Scandium-authored content (processing, quality scoring, validation, analysis,
documentation, and literature-mined records). Every third-party record is
subject to its source database's own terms, identified per row via
`identity.source_db`.

## Per-source license table (release v1.9.0, `materials.parquet`, 30,801 records)

| `identity.source_db` | Records | License | Commercial use |
|---|---|---|---|
| `materials_project` | 21,528 | CC BY 4.0 | Permitted (attribution) |
| `jarvis` | 8,327 | CC0 1.0 (Public Domain) | Permitted |
| `cod` | 500 | CC0 1.0 (Public Domain) | Permitted |
| `aflow` | 150 | **Non-commercial only** | **Prohibited** |
| `literature_mined` | 146 | CC BY 4.0 (Scandium-authored) | Permitted (attribution) |
| `nomad` | 100 | CC BY 4.0 | Permitted (attribution) |
| `oqmd` | 50 | CC BY 4.0 | Permitted (attribution) |
| **Total** | **30,801** | | |

## Source license details

### Materials Project (`materials_project`) — CC BY 4.0
Materials Project data is distributed under the Creative Commons Attribution
4.0 International License. Attribution is required; commercial use is
permitted. See https://materialsproject.org and https://creativecommons.org/licenses/by/4.0/.

### JARVIS-DFT (`jarvis`) — CC0 1.0 (Public Domain)
JARVIS-DFT data is hosted and distributed by NIST as a public resource.
JARVIS data and NIST-created content are in the public domain under CC0 1.0
Universal (CC0 1.0 Public Domain Dedication). See https://jarvis.nist.gov and
https://creativecommons.org/publicdomain/zero/1.0/.

### COD (`cod`) — CC0 1.0 (Public Domain)
The Crystallography Open Database is an open-access collection of crystal
structures, distributed under the CC0 1.0 Public Domain Dedication. See
https://www.crystallography.net/cod/.

### AFLOW (`aflow`) — Non-commercial only
AFLOW/aflowlib.org data is licensed for **scientific, academic, and
non-commercial purposes only; any other use is prohibited**. Per AFLOW's
REST-API terms: "The data included within the aflow.org repository is free for
scientific, academic and non-commercial purposes. Any other use is prohibited."
These 150 records are **excluded from the CC-BY-4.0 blanket grant**; a
commercial redistribution of the dataset requires these rows removed or
separately cleared. See http://www.aflowlib.org/.

### NOMAD (`nomad`) — CC BY 4.0
NOMAD repository data is available under the Creative Commons Attribution 4.0
International License. See https://nomad-lab.eu and
https://creativecommons.org/licenses/by/4.0/.

### OQMD (`oqmd`) — CC BY 4.0
OQMD data is licensed under CC BY 4.0 per OQMD's own terms of use ("The data in
OQMD is licensed under CC-BY 4.0", oqmd.org). Attribution to the OQMD and its
source publications is required; commercial use is permitted. See
https://oqmd.org and https://creativecommons.org/licenses/by/4.0/.

### Literature-mined records (`literature_mined`) — CC BY 4.0 (Scandium-authored)
Records extracted and curated by Scandium Labs from scientific literature are
original Scandium-authored content licensed under CC BY 4.0. The underlying
papers remain subject to their publishers' copyright; the extracted
conductivity/Ea data points and their provenance annotations are released here
under CC BY 4.0.

## Attribution

When redistributing this dataset, please:
1. Credit Scandium Labs and link to the repository and this license file.
2. Credit each source database used, and satisfy their citation requirements:
   Materials Project, JARVIS-DFT (NIST), COD, AFLOW, NOMAD, and OQMD each
   request citation of their respective reference publications.
3. Preserve `identity.source_db` so downstream users can honor the per-source
   terms above.

## How to determine a row's license

Every record in the released parquet files carries its source database in the
`identity.source_db` column. Look up that value in the table above. Rows with
`identity.source_db == "aflow"` are non-commercial; all other rows fall under
either a permissive source license or the Scandium-authored CC BY 4.0 grant.

## Warranty

THE DATASET IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR
IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY,
FITNESS FOR A PARTICULAR PURPOSE, AND NON-INFRINGEMENT. IN NO EVENT SHALL THE
AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES, OR OTHER
LIABILITY ARISING FROM, OUT OF, OR IN CONNECTION WITH THE DATASET OR ITS USE.
