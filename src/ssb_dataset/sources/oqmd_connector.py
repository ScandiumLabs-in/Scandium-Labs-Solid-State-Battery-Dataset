"""OQMD connector — Phase 2 ingestion source."""

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


class OQMDConnector(BaseSourceConnector):
    source_db = SourceDB.oqmd.value

    def connect(self) -> None:
        try:
            from oqmd import OQMD as OQMDClient
            self._client = OQMDClient()
            self._connected = True
        except ImportError:
            msg = "oqmd package not installed. Install with: pip install oqmd"
            raise RuntimeError(msg)

    def fetch_records(self, **kwargs: Any) -> Generator[dict[str, Any], None, None]:
        elements = kwargs.get("elements", ["Li"])
        limit = kwargs.get("limit", 1000)
        offset = kwargs.get("offset", 0)
        try:
            results = self._client.search(
                elements=elements,
                limit=limit,
                offset=offset,
            )
            for entry in results:
                yield entry
        except Exception as exc:
            msg = f"OQMD search failed: {exc}"
            raise RuntimeError(msg) from exc

    def to_material_record(self, raw: dict[str, Any]) -> MaterialRecord:
        lattice = raw.get("lattice", {})
        spg = raw.get("space_group", {})

        cif_str = raw.get("cif", "")
        if not cif_str and raw.get("structure"):
            try:
                from pymatgen.core import Structure
                struct = Structure.from_dict(raw["structure"])
                cif_str = struct.to(fmt="cif")
            except Exception:
                pass

        composition = raw.get("composition", {})
        identity = IdentityProvenance(
            material_id=f"oqmd-{raw.get('id', '')}",
            source_db=SourceDB.oqmd,
            source_id=str(raw.get("id", "")),
            family=classify_family(composition),
            ingestion_date=datetime.now(timezone.utc),
            confidence_tier=ConfidenceTier.dft_native,
        )

        structure = StructureBlock(
            structure_relaxed=cif_str or None,
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