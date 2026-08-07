"""OQMD connector — Phase 2 ingestion source (REST, no client package).

The ``oqmd`` PyPI client pins an old dependency stack and is often broken.
This connector queries the OQMD REST API (``oqmd.org/oqmdapi/``) directly with
``httpx`` — a free, keyless public interface — so the source is re-enabled
without the stale client.

Query used:
    /formationenergy?fields=...&filter=element_set=Li&limit=N&offset=O
``element_set`` is the OQMD filter keyword for "must contain these elements"
(the ``elements`` query param is not honored by the REST API — using it
returns 502 / unfiltered data). Each entry carries ``entry_id``, ``name``
(formula), ``composition``, ``spacegroup`` and ``unit_cell`` (lattice). No own
CIF is served for the elasticity endpoint, so ``to_material_record``
synthesizes structure info from lattice + symmetry only (consistent with a
DFT-native bulk record).
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

OQMD_BASE = "http://oqmd.org/oqmdapi/"


class OQMDConnector(BaseSourceConnector):
    source_db = SourceDB.oqmd.value

    def connect(self) -> None:
        self._client = httpx.Client(base_url=OQMD_BASE, timeout=120, follow_redirects=True)
        self._connected = True

    def fetch_records(self, **kwargs: Any) -> Generator[dict[str, Any], None, None]:
        elements = kwargs.get("elements", ["Li"])
        limit = kwargs.get("limit", 1000)
        offset = kwargs.get("offset", 0)
        el_str = "-".join(elements)
        page = 50  # OQMD 502s/timeouts on large page sizes
        fetched = 0
        while not limit or fetched < limit:
            resp = None
            for attempt in range(3):
                try:
                    resp = self._client.get(
                        "formationenergy",
                        params={
                            "filter": f"element_set={el_str}",
                            "limit": min(page, limit - fetched) if limit else page,
                            "offset": offset,
                            "fields": (
                                "name,entry_id,composition,spacegroup,unit_cell,"
                                "formationenergy_id,delta_e"
                            ),
                        },
                        timeout=120,
                    )
                    resp.raise_for_status()
                    break
                except Exception as exc:
                    if attempt < 2:
                        import time as _time
                        _time.sleep(5 * (attempt + 1))
                        continue
                    print(f"  [WARN] OQMD query failed at offset {offset}: {exc} — skipping OQMD")
                    return
            data = resp.json()
            entries = data.get("data") if isinstance(data, dict) else data
            if not isinstance(entries, list) or not entries:
                break
            for entry in entries:
                yield {
                    "id": entry.get("entry_id"),
                    "composition": entry.get("composition"),
                    "formula": entry.get("name"),
                    "lattice": _unit_cell_to_lattice(entry.get("unit_cell", {})),
                    "space_group": entry.get("spacegroup", {}),
                    "delta_e": entry.get("delta_e"),
                }
                fetched += 1
                offset += 1
            if len(entries) < page:
                break

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

        composition = raw.get("composition", {}) or {}
        if isinstance(composition, dict):
            comp_input = composition
        else:
            comp_input = raw.get("formula", raw.get("name", composition))

        identity = IdentityProvenance(
            material_id=f"oqmd-{raw.get('id', '')}",
            source_db=SourceDB.oqmd,
            source_id=str(raw.get("id", "")),
            family=classify_family(composition=comp_input),
            is_electrolyte_candidate=is_electrolyte_candidate(composition=comp_input),
            ingestion_date=datetime.now(timezone.utc),
            confidence_tier=ConfidenceTier.dft_native,
        )

        structure = StructureBlock(
            structure_relaxed=cif_str or None,
            space_group=spg.get("symbol", "") if isinstance(spg, dict) else str(spg or ""),
            lattice_params=(
                LatticeParams(
                    a=float(lattice.get("a", 0.0) or 0.0),
                    b=float(lattice.get("b", 0.0) or 0.0),
                    c=float(lattice.get("c", 0.0) or 0.0),
                    alpha=float(lattice.get("alpha", 90.0) or 90.0),
                    beta=float(lattice.get("beta", 90.0) or 90.0),
                    gamma=float(lattice.get("gamma", 90.0) or 90.0),
                )
                if isinstance(lattice, dict)
                else None
            ),
        )

        return MaterialRecord(identity=identity, structure=structure)


def _unit_cell_to_lattice(uc: dict[str, Any]) -> dict[str, float]:
    """OQMD ``unit_cell`` is a 3x3 matrix of lattice-vector rows (a, b, c)."""
    try:
        import numpy as np
        vecs = np.asarray(uc.get("lattice", uc), dtype=float)
        if vecs.shape != (3, 3):
            return {}
        a = float(np.linalg.norm(vecs[0]))
        b = float(np.linalg.norm(vecs[1]))
        c = float(np.linalg.norm(vecs[2]))
        alpha = float(np.degrees(
            np.arccos(np.clip(np.dot(vecs[1], vecs[2]) / (b * c), -1, 1))))
        beta = float(np.degrees(
            np.arccos(np.clip(np.dot(vecs[0], vecs[2]) / (a * c), -1, 1))))
        gamma = float(np.degrees(
            np.arccos(np.clip(np.dot(vecs[0], vecs[1]) / (a * b), -1, 1))))
        return {"a": a, "b": b, "c": c, "alpha": alpha, "beta": beta, "gamma": gamma}
    except Exception:
        return {}