"""AFLOW connector — Phase 2 ingestion source (AFLUX REST, no client package).

The ``aflow`` PyPI client is unmaintained and incompatible with the current
AFLUX API schema. This connector queries the AFLOW ``AFLUX`` REST endpoint
directly with ``httpx`` — the same API the client wraps — so the source is
re-enabled without any stale dependency.

AFLUX query grammar used (see https://aflow.org/API/aflux/):
    species(Li),paging(N,M),format(json)
Each result entry carries ``auid``, lattice constants, space group and
``compound`` (formula string); the CIF is fetched per-auid from the entry's
``aurl`` when reachable.

Notes from live testing (2026-08-05):
- The summon must be written into the URL path after ``?`` — passing it as an
  ``API=`` query parameter returns ``DB Fail!null``.
- ``catalog(CFAFLOW_LIB1)`` (the old default) returns ``[]`` — drop the catalog
  directive to query the full LIB catalog.
- ``paging(0,K)`` means "return ALL results" (146k for species(Li) — huge and
  slow). Pages are 1-indexed: ``paging(1,K)`` is the first page.
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
        """Fetch the relaxed structure file for an auid (best-effort).

        AFLOW exposes the relaxed VASP CONTCAR at
        ``https://aflowlib.duke.edu/AFLOWDATA/<aurl>/CONTCAR.relax``. The legacy
        ``material.urn.php?auid=...&cif`` endpoint 404s (2026-08-05).
        """
        if not auid and not aurl:
            return None
        candidates = []
        if aurl:
            # aurl looks like "aflowlib.duke.edu:AFLOWDATA/LIB3_WEB/AgAlLi_sv/TBCC014.BCA"
            aurl_path = aurl.split(":", 1)[-1].rstrip("/")
            if aurl_path.startswith("AFLOWDATA/"):
                aurl_path = aurl_path[len("AFLOWDATA/"):]
            candidates.append(f"https://aflowlib.duke.edu/AFLOWDATA/{aurl_path}/CONTCAR.relax")
        if auid:
            candidates.append(f"https://aflowlib.duke.edu/AFLOWDATA/{auid}/CONTCAR.relax")
        for url in candidates:
            try:
                r = httpx.get(url, follow_redirects=True, timeout=12)
                if r.status_code == 200 and r.text.strip() and not r.text.lstrip().startswith("<"):
                    return r.text
            except Exception:
                continue
        return None

    def fetch_records(self, **kwargs: Any) -> Generator[dict[str, Any], None, None]:
        species = kwargs.get("species", "Li")
        limit = kwargs.get("limit", 1000)
        page = 1  # paging(0, K) = "all results"; pages are 1-indexed
        PAGE_SIZE = 200
        fetched = 0
        while not limit or fetched < limit:
            query = (
                f"species({species}),paging({page},{PAGE_SIZE}),format(json)"
            )
            try:
                resp = self._client.get(f"?{query}")
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
            # AFLUX returns a dict {"1 of N": {...}, ...}
            if isinstance(entries, dict):
                entries = list(entries.values())
            if not isinstance(entries, list) or not entries:
                break
            for entry in entries:
                if limit and fetched >= limit:
                    break
                cif = self._fetch_cif(str(entry.get("auid", "")), entry.get("aurl"))
                entry["cif"] = cif or ""
                yield entry
                fetched += 1
            if len(entries) < PAGE_SIZE:
                break
            page += 1

    def to_material_record(self, raw: dict[str, Any]) -> MaterialRecord:
        cif = raw.get("cif", "")

        # Elements: prefer AFLUX's explicit species list (authoritative); the
        # CONTCAR header is not POSCAR-parseable, so pymatgen would guess
        # wrong names. Fall back to the compound formula when species is empty.
        elements: set[str] = set()
        species_raw = raw.get("species")
        if species_raw:
            for s in species_raw:
                sym = str(s).strip()
                if sym and not sym[0].isdigit():
                    elements.add(sym)
        if not elements and raw.get("compound"):
            try:
                from pymatgen.core import Composition
                elements = {el.symbol for el in Composition(raw["compound"]).elements}
            except Exception:
                pass

        # Lattice params: parse from the CONTCAR text we already fetched, since
        # AFLUX doesn't return lattice constants unless requested.
        lattice: dict[str, float] = {}
        if cif:
            try:
                from pymatgen.core import Structure
                if cif.lstrip().startswith("data_") or "_cell_length_a" in cif:
                    struct = Structure.from_str(cif, fmt="cif")
                else:
                    struct = Structure.from_str(cif, fmt="poscar")
                lp = struct.lattice
                lattice = {
                    "a": lp.a, "b": lp.b, "c": lp.c,
                    "alpha": lp.alpha, "beta": lp.beta, "gamma": lp.gamma,
                }
            except Exception:
                pass

        spg = raw.get("spacegroup", {}) or raw.get("spacegroup_relax", {})

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
                if lattice
                else None
            ),
        )

        return MaterialRecord(identity=identity, structure=structure)
