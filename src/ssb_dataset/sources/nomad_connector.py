"""NOMAD connector — Phase 2 ingestion source (public API, no key required)."""

from __future__ import annotations

from collections.abc import Generator
from datetime import datetime, timezone
from typing import Any

from ssb_dataset.schema import (
    ConfidenceTier,
    IdentityProvenance,
    MaterialRecord,
    SourceDB,
    StructureBlock,
)
from ssb_dataset.sources.base import BaseSourceConnector
from ssb_dataset.sources.classifier import classify_family, is_electrolyte_candidate


class NOMADConnector(BaseSourceConnector):
    source_db = SourceDB.nomad.value

    BASE_URL = "https://nomad-lab.eu/prod/v1/api"

    def connect(self) -> None:
        import httpx
        self._client = httpx.Client(base_url=self.BASE_URL, timeout=120)
        try:
            resp = self._client.get("/v1/info", timeout=10)
            resp.raise_for_status()
            self._connected = True
        except Exception as exc:
            self._connected = False
            msg = f"NOMAD public API unreachable: {exc}"
            raise RuntimeError(msg) from exc

    def fetch_records(self, **kwargs: Any) -> Generator[dict[str, Any], None, None]:
        elements = kwargs.get("elements", ["Li"])
        limit = kwargs.get("limit", 500)
        page_after = kwargs.get("page_after", None)

        params: dict[str, Any] = {
            "query": {"results.material.elements": {"all": elements}},
            "pagination": {"page_size": min(limit, 100)},
        }
        if page_after:
            params["pagination"]["page_after_value"] = page_after

        fetched = 0
        while fetched < limit:
            try:
                resp = self._client.post("/v1/entries/query", json=params, timeout=60)
                resp.raise_for_status()
                data = resp.json()
                entries = data.get("data", [])
                for entry in entries:
                    yield entry
                    fetched += 1
                    if fetched >= limit:
                        return
                pagination = data.get("pagination", {})
                page_after = pagination.get("next_page_after_value")
                if not page_after:
                    break
                params["pagination"]["page_after_value"] = page_after
            except Exception as exc:
                msg = f"NOMAD query failed: {exc}"
                raise RuntimeError(msg) from exc

    def to_material_record(self, raw: dict[str, Any]) -> MaterialRecord:
        entry_id = raw.get("entry_id", "")
        results = raw.get("results", {})
        material = results.get("material", {})
        elements = material.get("elements", [])
        symmetry = material.get("symmetry", {})

        cif_str = raw.get("cif", "")

        identity = IdentityProvenance(
            material_id=f"nomad-{entry_id}",
            source_db=SourceDB.nomad,
            source_id=entry_id,
            family=classify_family(elements=set(elements)),
            is_electrolyte_candidate=is_electrolyte_candidate(elements=set(elements)),
            ingestion_date=datetime.now(timezone.utc),
            confidence_tier=ConfidenceTier.dft_native,
        )

        structure = StructureBlock(
            structure_relaxed=cif_str or None,
            space_group=symmetry.get("space_group_symbol", "") if isinstance(symmetry, dict) else str(symmetry or ""),
            lattice_params=None,
        )

        return MaterialRecord(identity=identity, structure=structure)