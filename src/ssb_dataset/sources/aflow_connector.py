"""AFLOW connector — Phase 2 ingestion source (AFLUX REST, no client package).

The ``aflow`` PyPI client is unmaintained and incompatible with the current
AFLUX API schema. This connector queries the AFLOW ``AFLUX`` REST endpoint
directly with ``httpx`` — the same API the client wraps — so the source is
re-enabled without any stale dependency.

AFLUX query grammar used (see https://aflow.org/API/aflux/):
    catalog(CFAFLOW_LIB1),species(Li),paging(N),format(json)
Each result entry carries ``auid``, lattice constants, space group and
``compound`` (formula string); the CIF is fetched per-auid from the entry's
``aurl`` when reachable.
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

AFLUX = "https://aflow.org/API/aflux/"


class AFLOWConnector(BaseSourceConnector):
    source_db = SourceDB.aflow.value

    def connect(self) -> None:
        self._client = httpx.Client(base_url=AFLUX, timeout=120)
        self._connected = True

    @staticmethod
    def _fetch_cif(auid: str, aurl: str | None) -> str | None:
        """Fetch the CIF for an auid when AFLOW exposes one (best-effort)."""
        if not auid:
            return None
        for url in (f"https://aflow.org/material.urn.php?auid={auid}&cif",
                    f"{aurl.rstrip('/')}/{auid}.cif" if aurl else ""):
            if not url:
                continue
            try:
                r = httpx.get(url, follow_redirects=True, timeout=45)
                if r.status_code == 200 and r.text.strip().startswith("data_"):
                    return r.text
            except Exception:
                continue
        return None

    def fetch_records(self, **kwargs: Any) -> Generator[dict[str, Any], None, None]:
        species = kwargs.get("species", "Li")
        limit = kwargs.get("limit", 1000)
        page = 0
        PAGE_SIZE = 200
        while page * PAGE_SIZE < limit:
            query = (
                f"catalog(CFAFLOW_LIB1),species({species}),"
                f"paging({page},{PAGE_SIZE}),format(json)"
            )
            try:
                resp = self._client.get("", params={"API": query})
            except Exception as exc:
                print(f"  [WARN] AFLOW query failed: {exc} — skipping AFLOW")
                return
            if resp.status_code != 200:
                print(f"  [WARN] AFLOW returned HTTP {resp.status_code} — skipping")
                return
            try:
                entries = resp.json()
            except Exception:
                entries = []
            if not isinstance(entries, list) or not entries:
                break
            for entry in entries:
                cif = self._fetch_cif(str(entry.get("auid", "")), entry.get("aurl"))
                entry["cif"] = cif or ""
                yield entry
            if len(entries) < PAGE_SIZE:
                break
            page += 1

    def to_material_record(self, raw: dict[str, Any]) -> MaterialRecord:
        lattice = raw.get("lattice", {})
        if not lattice:  # AFLUX names lattice constants ca/cb/cc, alpha/beta/gamma
            lattice = {
                "a": raw.get("ca") or raw.get("a") or 0.0,
                "b": raw.get("cb") or raw.get("b") or 0.0,
                "c": raw.get("cc") or raw.get("c") or 0.0,
                "alpha": raw.get("alpha", 90.0),
                "beta": raw.get("beta", 90.0),
                "gamma": raw.get("gamma", 90.0),
            }
        spg = raw.get("spacegroup", {}) or raw.get("spacegroup_relax", {})
        cif = raw.get("cif", "")

        elements: set[str] = set()
        if cif:
            try:
                from pymatgen.core import Structure
                struct = Structure.from_str(cif, fmt="cif")
                elements = {el.symbol for el in struct.composition.elements}
            except Exception:
                pass
        if not elements and raw.get("compound"):
            # AFLUX gives a formula string like "Li3ClO" / "Li O2"
            try:
                from pymatgen.core import Composition
                elements = {el.symbol for el in Composition(raw["compound"]).elements}
            except Exception:
                pass

        identity = IdentityProvenance(
            material_id=f"aflow-{raw.get('auid', '')}",
            source_db=SourceDB.aflow,
            source_id=str(raw.get("auid", "")),
            family=classify_family(elements=elements),
            is_electrolyte_candidate=is_electrolyte_candidate(elements=elements),
            ingestion_date=datetime.now(timezone.utc),
            confidence_tier=ConfidenceTier.dft_native,
        )

        structure = StructureBlock(
            structure_relaxed=raw.get("cif", None),
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
