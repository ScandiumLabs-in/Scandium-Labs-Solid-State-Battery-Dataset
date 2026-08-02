"""Materials Project connector — Phase 2 ingestion source.

Uses mp-api (pymatgen MPRester) to pull structures and thermodynamic data
for Li-containing compounds across the 11 SSB families.
"""

from __future__ import annotations

from collections.abc import Generator
from datetime import datetime, timezone
from typing import Any

from pymatgen.core import Structure

from ssb_dataset.config.settings import settings
from ssb_dataset.schema import (
    ConfidenceTier,
    Functional,
    IdentityProvenance,
    LatticeParams,
    MaterialRecord,
    SourceDB,
    StructureBlock,
    StructureType,
    ThermodynamicsBlock,
)
from ssb_dataset.sources.base import BaseSourceConnector
from ssb_dataset.sources.classifier import classify_family, is_electrolyte_candidate


class MPConnector(BaseSourceConnector):
    source_db = SourceDB.materials_project.value

    def __init__(self) -> None:
        super().__init__()
        self._api_key = settings.mp.api_key
        self._client = None

    def connect(self) -> None:
        if not self._api_key:
            msg = "MP_API_KEY not set. Set it in your environment or .env file."
            raise RuntimeError(msg)
        from mp_api.client import MPRester

        self._client = MPRester(api_key=self._api_key)
        self._connected = True

    def fetch_records(self, **kwargs: Any) -> Generator[dict[str, Any], None, None]:
        chemsys = kwargs.get("chemsys", "Li-*")
        fields = kwargs.get(
            "fields",
            [
                "material_id",
                "structure",
                "formation_energy_per_atom",
                "energy_above_hull",
                "band_gap",
                "symmetry",
                "volume",
                "density",
            ],
        )

        with self._client as mpr:
            results = mpr.materials.summary.search(
                chemsys=chemsys,
                fields=fields,
                num_chunks=kwargs.get("num_chunks", None),
                chunk_size=kwargs.get("chunk_size", 500),
            )
            for doc in results:
                yield doc.model_dump()

    def to_material_record(self, raw: dict[str, Any]) -> MaterialRecord:
        struct = raw.get("structure")
        if struct and not isinstance(struct, Structure):
            struct = Structure.from_dict(struct) if isinstance(struct, dict) else None

        sym = raw.get("symmetry", {}) or {}

        lattice = struct.lattice if struct else None

        return MaterialRecord(
            identity=IdentityProvenance(
                material_id=f"mp-{raw.get('material_id', '')}",
                source_db=SourceDB.materials_project,
                source_id=str(raw.get("material_id", "")),
                family=classify_family(struct=struct),
                is_electrolyte_candidate=is_electrolyte_candidate(struct=struct),
                ingestion_date=datetime.now(timezone.utc),
                confidence_tier=ConfidenceTier.dft_native,
            ),
            structure=StructureBlock(
                structure_relaxed=struct.to(fmt="cif") if struct else None,
                space_group=sym.get("symbol", "") if isinstance(sym, dict) else str(sym or ""),
                lattice_params=LatticeParams(
                    a=lattice.a if lattice else 0.0,
                    b=lattice.b if lattice else 0.0,
                    c=lattice.c if lattice else 0.0,
                    alpha=lattice.alpha if lattice else 90.0,
                    beta=lattice.beta if lattice else 90.0,
                    gamma=lattice.gamma if lattice else 90.0,
                ),
                li_site_occupancy=self._get_li_occupancy(struct),
                structure_type=(
                    StructureType.disordered
                    if (sym.get("is_disordered", False) if isinstance(sym, dict) else False)
                    else StructureType.ordered
                ),
                is_experimental_structure=False,
            ),
            thermodynamics=ThermodynamicsBlock(
                formation_energy_per_atom=raw.get("formation_energy_per_atom"),
                energy_above_hull=raw.get("energy_above_hull"),
                band_gap=raw.get("band_gap"),
                functional_used=Functional.pbe,
            ),
        )

    @staticmethod
    def _get_li_occupancy(struct: Structure | None) -> list[float]:
        if struct is None:
            return []
        occupancies = []
        for site in struct:
            if "Li" in site.species_string:
                occupancies.append(site.species.get("Li", 0))
        return occupancies
