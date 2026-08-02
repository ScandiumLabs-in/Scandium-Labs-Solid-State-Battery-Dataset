"""ICSD connector — Phase 2 ingestion source (placeholder)."""

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


class ICSDConnector(BaseSourceConnector):
    source_db = SourceDB.icsd.value

    def connect(self) -> None:
        import os
        api_key = os.environ.get("ICSD_API_KEY")
        if not api_key:
            msg = "ICSD_API_KEY environment variable not set"
            raise RuntimeError(msg)
        self._api_key = api_key
        self._connected = True

    def fetch_records(self, **kwargs: Any) -> Generator[dict[str, Any], None, None]:
        elements = kwargs.get("elements", ["Li"])
        limit = kwargs.get("limit", 1000)

        import httpx
        headers = {"API-KEY": self._api_key}
        params = {
            "elements": ",".join(elements),
            "max_entries": min(limit, 1000),
            "format": "json",
        }

        resp = httpx.get(
            "https://icsd.fiz-karlsruhe.de/api/search/entries",
            headers=headers,
            params=params,
            timeout=120,
        )
        resp.raise_for_status()
        entries = resp.json().get("entries", [])
        for entry in entries[:limit]:
            yield entry

    def to_material_record(self, raw: dict[str, Any]) -> MaterialRecord:
        entry_id = str(raw.get("id", raw.get("collectionId", "")))
        elements = set(raw.get("elements", []))
        lattice = raw.get("cell", raw.get("lattice", {}))
        spg = raw.get("spaceGroup", raw.get("space_group", ""))
        cif_str = raw.get("cif", "")

        identity = IdentityProvenance(
            material_id=f"icsd-{entry_id}",
            source_db=SourceDB.icsd,
            source_id=entry_id,
            family=classify_family(elements=elements),
            is_electrolyte_candidate=is_electrolyte_candidate(elements=elements),
            ingestion_date=datetime.now(timezone.utc),
            confidence_tier=ConfidenceTier.verified_human,
        )

        structure = StructureBlock(
            structure_relaxed=cif_str or None,
            space_group=str(spg) if spg else None,
            lattice_params=(
                LatticeParams(
                    a=float(lattice.get("a", lattice.get("length_a", 0.0))),
                    b=float(lattice.get("b", lattice.get("length_b", 0.0))),
                    c=float(lattice.get("c", lattice.get("length_c", 0.0))),
                    alpha=float(lattice.get("alpha", lattice.get("angle_alpha", 90.0))),
                    beta=float(lattice.get("beta", lattice.get("angle_beta", 90.0))),
                    gamma=float(lattice.get("gamma", lattice.get("angle_gamma", 90.0))),
                )
                if lattice
                else None
            ),
        )

        return MaterialRecord(identity=identity, structure=structure)