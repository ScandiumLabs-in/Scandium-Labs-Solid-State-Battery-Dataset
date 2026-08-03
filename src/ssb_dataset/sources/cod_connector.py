"""COD (Crystallography Open Database) connector — free alternative to ICSD.

COD is a fully open, keyless crystallography database. Unlike Materials Project
/ JARVIS (DFT-relaxed), COD holds experimentally-determined structures — an
"this actually exists" signal that is the free substitute for the paywalled
ICSD access a student setup cannot reach.

Fetch strategy:
    https://www.crystallography.net/cod/result.php?formula=Li&format=json
returns the search result set; the CIF for each ``cod_id`` is pulled from
    https://www.crystallography.net/cod/{cod_id}.cif
"""

from __future__ import annotations

from collections.abc import Generator
from datetime import datetime, timezone
from typing import Any

import httpx

from ssb_dataset.schema import (
    ConfidenceTier,
    IdentityProvenance,
    LatticeParams,
    MaterialRecord,
    SourceDB,
    StructureBlock,
)
from ssb_dataset.sources.base import BaseSourceConnector
from ssb_dataset.sources.classifier import classify_family, is_electrolyte_candidate


class CODConnector(BaseSourceConnector):
    """Free crystallographic database with 500k+ experimental structures."""
    source_db = SourceDB.cod.value

    BASE_URL = "https://www.crystallography.net/cod"

    def connect(self) -> None:
        import httpx
        self._client = httpx.Client(base_url=self.BASE_URL, timeout=60)
        self._connected = True

    @staticmethod
    def _fetch_cif(cod_id: str) -> str | None:
        try:
            r = httpx.get(f"https://www.crystallography.net/cod/{cod_id}.cif",
                          timeout=60)
            if r.status_code == 200 and r.text.strip().startswith("data_"):
                return r.text
        except Exception:
            pass
        return None

    def fetch_records(self, **kwargs: Any) -> Generator[dict[str, Any], None, None]:
        elements = kwargs.get("elements", ["Li"])
        limit = kwargs.get("limit", 1000)
        formula = "Li" + "".join(e for e in elements if e.upper() != "LI")

        import httpx
        client = httpx.Client(timeout=120)
        try:
            resp = client.get(
                "https://www.crystallography.net/cod/result.php",
                params={"formula": formula, "format": "json"},
                timeout=120,
            )
            resp.raise_for_status()
            data = resp.json()
        except Exception as exc:
            print(f"  [WARN] COD query failed: {exc} — skipping COD")
            return
        finally:
            client.close()

        # COD JSON returns a list of cells; tolerate dict wrapper variants.
        rows = data.get("results") if isinstance(data, dict) else None
        rows = rows if isinstance(rows, list) else (data if isinstance(data, list) else [])

        n = 0
        for entry in rows:
            if n >= limit:
                break
            cod_id = str(entry.get("cod_id", entry.get("id", "")))
            yield {
                "cod_id": cod_id,
                "elements": ["Li"] + [e for e in elements if e.upper() != "LI"],
                "lattice": {
                    "a": entry.get("cell_length_a", 0.0),
                    "b": entry.get("cell_length_b", 0.0),
                    "c": entry.get("cell_length_c", 0.0),
                    "alpha": entry.get("cell_angle_alpha", 90.0),
                    "beta": entry.get("cell_angle_beta", 90.0),
                    "gamma": entry.get("cell_angle_gamma", 90.0),
                },
                "space_group": entry.get("space_group", ""),
                "cif": self._fetch_cif(cod_id) or "",
            }
            n += 1

    def to_material_record(self, raw: dict[str, Any]) -> MaterialRecord:
        entry_id = str(raw.get("cod_id", raw.get("id", "")))
        elements = set(raw.get("elements", ["Li"]))
        lattice = raw.get("lattice", {})
        spg = raw.get("space_group", "")
        cif_str = raw.get("cif", "")

        if cif_str:
            try:
                from pymatgen.core import Structure
                elements = {el.symbol for el in Structure.from_str(cif_str, fmt="cif").composition.elements}
            except Exception:
                pass

        identity = IdentityProvenance(
            material_id=f"cod-{entry_id}",
            source_db=SourceDB.cod,
            source_id=entry_id,
            family=classify_family(elements=elements),
            is_electrolyte_candidate=is_electrolyte_candidate(elements=elements),
            ingestion_date=datetime.now(timezone.utc),
            confidence_tier=ConfidenceTier.dft_native,
        )

        structure = StructureBlock(
            structure_relaxed=cif_str or None,
            space_group=str(spg) if spg else None,
            lattice_params=(
                LatticeParams(
                    a=float(lattice.get("a", lattice.get("length_a", 0.0)) or 0.0),
                    b=float(lattice.get("b", lattice.get("length_b", 0.0)) or 0.0),
                    c=float(lattice.get("c", lattice.get("length_c", 0.0)) or 0.0),
                    alpha=float(lattice.get("alpha", lattice.get("angle_alpha", 90.0)) or 90.0),
                    beta=float(lattice.get("beta", lattice.get("angle_beta", 90.0)) or 90.0),
                    gamma=float(lattice.get("gamma", lattice.get("angle_gamma", 90.0)) or 90.0),
                )
                if lattice
                else None
            ),
        )

        return MaterialRecord(identity=identity, structure=structure)