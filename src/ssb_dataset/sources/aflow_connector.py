"""AFLOW connector — Phase 2 ingestion source."""

from __future__ import annotations

from collections.abc import Generator
from datetime import datetime, timezone
from typing import Any

from ssb_dataset.schema import (
    ConfidenceTier,
    IdentityProvenance,
    LatticeParams,
    MaterialRecord,
    SourceDB,
    StructureBlock,
)
from ssb_dataset.sources.base import BaseSourceConnector
from ssb_dataset.sources.classifier import classify_family


class AFLOWConnector(BaseSourceConnector):
    source_db = SourceDB.aflow.value

    def connect(self) -> None:
        try:
            from aflow import search as aflow_search
            self._search = aflow_search
            self._connected = True
        except ImportError:
            msg = "aflow Python package not installed. Install with: pip install aflow"
            raise RuntimeError(msg)

    def fetch_records(self, **kwargs: Any) -> Generator[dict[str, Any], None, None]:
        species = kwargs.get("species", "Li")
        limit = kwargs.get("limit", 1000)
        try:
            query = self._search(catalog="lib1", batch_size=100)
            results = query.filter(f"species({species})")[:limit]
            for entry in results:
                yield entry
        except Exception as exc:
            msg = f"AFLOW search failed: {exc}"
            print(f"  [WARN] {msg} — skipping AFLOW")
            return

    def to_material_record(self, raw: dict[str, Any]) -> MaterialRecord:
        lattice = raw.get("lattice", {})
        spg = raw.get("spacegroup", {})
        cif = raw.get("cif", "")

        elements: set[str] = set()
        if cif:
            try:
                from pymatgen.core import Structure
                struct = Structure.from_str(cif, fmt="cif")
                elements = {el.symbol for el in struct.composition.elements}
            except Exception:
                pass

        identity = IdentityProvenance(
            material_id=f"aflow-{raw.get('auid', '')}",
            source_db=SourceDB.aflow,
            source_id=str(raw.get("auid", "")),
            family=classify_family(elements=elements),
            ingestion_date=datetime.now(timezone.utc),
            confidence_tier=ConfidenceTier.dft_native,
        )

        structure = StructureBlock(
            structure_relaxed=raw.get("cif", None),
            space_group=spg.get("symbol", "") if isinstance(spg, dict) else str(spg or ""),
            lattice_params=(
                LatticeParams(
                    a=lattice.get("a", 0.0),
                    b=lattice.get("b", 0.0),
                    c=lattice.get("c", 0.0),
                    alpha=lattice.get("alpha", 90.0),
                    beta=lattice.get("beta", 90.0),
                    gamma=lattice.get("gamma", 90.0),
                )
                if isinstance(lattice, dict)
                else None
            ),
        )

        return MaterialRecord(identity=identity, structure=structure)
