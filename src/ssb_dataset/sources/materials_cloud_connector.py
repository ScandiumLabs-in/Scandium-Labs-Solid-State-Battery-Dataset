"""Materials Cloud connector — free structural source via OPTIMADE.

Materials Cloud (EPFL) hosts curated computational materials datasets,
including solid-electrolyte-adjacent archives, behind a free, keyless
OPTIMADE API:

    https://www.materialscloud.org/api/optimade/v1/structures
    ?filter=elements HAS ALL "Li"&page_limit=N

OPTIMADE is a standards-track REST schema, so this connector needs no client
package. ``page_limit`` (the OPTIMADE name for per-page size) is honored via
``page_offset`` for pagination.
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

OPTIMADE_BASE = "https://www.materialscloud.org/api/optimade/v1/structures"


class MaterialsCloudConnector(BaseSourceConnector):
    source_db = SourceDB.materials_cloud.value

    def connect(self) -> None:
        self._client = httpx.Client(base_url=OPTIMADE_BASE, timeout=120)
        self._connected = True

    def fetch_records(self, **kwargs: Any) -> Generator[dict[str, Any], None, None]:
        elements = kwargs.get("elements", ["Li"])
        limit = kwargs.get("limit", 1000)
        el_list = ", ".join(f'"{e}"' for e in elements)
        cursor = None
        fetched = 0
        while fetched < limit:
            params: dict[str, Any] = {
                "filter": f'elements HAS ALL ({el_list})',
                "response_fields": (
                    "id,formula_reduced,species_at_sites,"
                    "lattice_vectors,space_group,attributes"
                ),
                "page_limit": min(100, limit - fetched),
            }
            if cursor:
                params["page_cursor"] = cursor
            try:
                resp = self._client.get("", params=params, timeout=120)
                resp.raise_for_status()
                data = resp.json()
            except Exception as exc:
                print(f"  [WARN] Materials Cloud query failed: {exc} — skipping")
                return

            meta = data.get("meta", {})
            cursor = (meta.get("more_data_available") or meta.get("next_cursor")
                      or (meta.get("pagination") or {}).get("next_cursor"))
            results = data.get("data", [])
            if not results:
                break
            for item in results:
                if fetched >= limit:
                    break
                yield self._to_raw(item)
                fetched += 1
            if not cursor:
                break

    @staticmethod
    def _to_raw(item: dict[str, Any]) -> dict[str, Any]:
        attrs = item.get("attributes", {}) or {}
        spg = attrs.get("space_group", {}) or {}
        lat = attrs.get("lattice_vectors") or []
        if len(lat) == 3 and all(len(row) == 3 for row in lat):
            try:
                import numpy as np
                vecs = np.asarray(lat, dtype=float)
                a = float(np.linalg.norm(vecs[0]))
                b = float(np.linalg.norm(vecs[1]))
                c = float(np.linalg.norm(vecs[2]))
                alpha = float(np.degrees(np.arccos(np.clip(np.dot(vecs[1], vecs[2]) / (b * c), -1, 1))))
                beta = float(np.degrees(np.arccos(np.clip(np.dot(vecs[0], vecs[2]) / (a * c), -1, 1))))
                gamma = float(np.degrees(np.arccos(np.clip(np.dot(vecs[0], vecs[1]) / (a * b), -1, 1))))
                lattice = {"a": a, "b": b, "c": c, "alpha": alpha, "beta": beta, "gamma": gamma}
            except Exception:
                lattice = {}
        else:
            lattice = {}
        return {
            "mc_id": item.get("id", ""),
            "formula": attrs.get("formula_reduced", ""),
            "elements": [str(s) for s in (attrs.get("species_at_sites") or [])
                         if s not in ("X", "")],
            "lattice": lattice,
            "space_group": spg.get("space_group_symbol", "") or spg.get("symbol", ""),
            "is_stable": attrs.get("is_stable"),
        }

    def to_material_record(self, raw: dict[str, Any]) -> MaterialRecord:
        elements: set[str] = set(raw.get("elements", []))
        formula = raw.get("formula", "")
        lattice = raw.get("lattice", {})
        spg = raw.get("space_group", "")
        if not elements and formula:
            try:
                from pymatgen.core import Composition
                elements = {el.symbol for el in Composition(formula).elements}
            except Exception:
                pass

        identity = IdentityProvenance(
            material_id=f"materials_cloud-{raw.get('mc_id', '')}",
            source_db=SourceDB.materials_cloud,
            source_id=str(raw.get("mc_id", "")),
            family=classify_family(elements=elements),
            is_electrolyte_candidate=is_electrolyte_candidate(elements=elements),
            ingestion_date=datetime.now(timezone.utc),
            confidence_tier=ConfidenceTier.dft_native,
        )

        structure = StructureBlock(
            structure_relaxed=None,
            space_group=str(spg) if spg else None,
            lattice_params=(
                LatticeParams(
                    a=float(lattice.get("a", 0.0) or 0.0),
                    b=float(lattice.get("b", 0.0) or 0.0),
                    c=float(lattice.get("c", 0.0) or 0.0),
                    alpha=float(lattice.get("alpha", 90.0) or 90.0),
                    beta=float(lattice.get("beta", 90.0) or 90.0),
                    gamma=float(lattice.get("gamma", 90.0) or 90.0),
                )
                if lattice
                else None
            ),
        )

        return MaterialRecord(identity=identity, structure=structure)