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
from ssb_dataset.sources.classifier import classify_family, is_electrolyte_candidate


class JARVISConnector(BaseSourceConnector):
    source_db = SourceDB.jarvis.value

    def connect(self) -> None:
        try:
            from jarvis.db.figshare import data

            self._all_data = data("dft_3d")
            self._connected = True
        except Exception as exc:
            msg = f"Failed to connect to JARVIS-DFT: {exc}"
            raise RuntimeError(msg) from exc

    def fetch_records(self, **kwargs: Any) -> Generator[dict[str, Any], None, None]:
        limit = kwargs.get("limit", 100)
        returned = 0
        for entry in self._all_data:
            if returned >= limit:
                break
            yield entry
            returned += 1

    def to_material_record(self, raw: dict[str, Any]) -> MaterialRecord:
        struct = raw.get("struct", {})
        lattice = struct.get("lattice", {}) if isinstance(struct, dict) else {}
        spg = raw.get("space_group", "")

        elements: set[str] = set()
        cif_str = ""
        if struct:
            try:
                from jarvis.core.atoms import Atoms
                atoms = Atoms.from_dict(struct)
                cif_str = atoms.to_cif()
                comp = atoms.composition
                elements = {el.symbol for el in comp.elements} if hasattr(comp, 'elements') else set()
            except Exception:
                cif_str = ""
                raw_elements = struct.get("elements", []) if isinstance(struct, dict) else []
                if raw_elements:
                    elements = set(raw_elements)

        identity = IdentityProvenance(
            material_id=f"jarvis-{raw.get('jid', '')}",
            source_db=SourceDB.jarvis,
            source_id=str(raw.get("jid", "")),
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
                    a=lattice.get("a", 0.0),
                    b=lattice.get("b", 0.0),
                    c=lattice.get("c", 0.0),
                    alpha=lattice.get("alpha", 90.0),
                    beta=lattice.get("beta", 90.0),
                    gamma=lattice.get("gamma", 90.0),
                )
                if lattice
                else None
            ),
        )

        return MaterialRecord(identity=identity, structure=structure)
