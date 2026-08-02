"""COD (Crystallography Open Database) connector — Free alternative to ICSD."""

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


class CODConnector(BaseSourceConnector):
    """Free crystallographic database with 500k+ structures."""
    source_db = SourceDB.cod.value

    BASE_URL = "https://www.crystallography.net/cod"

    def connect(self) -> None:
        import httpx
        self._client = httpx.Client(base_url=self.BASE_URL, timeout=60)
        self._connected = True

    def fetch_records(self, **kwargs: Any) -> Generator[dict[str, Any], None, None]:
        elements = kwargs.get("elements", ["Li"])
        limit = kwargs.get("limit", 1000)

        import httpx
        client = httpx.Client(timeout=120)
        try:
            formula = "Li" + "".join([e for e in elements if e != "Li"])
            resp = client.get(
                "https://www.crystallography.net/cod/result.php",
                params={
                    "formula": formula,
                    "format": "json",
                },
                timeout=120,
            )
            resp.raise_for_status()
            data = resp.json()
            for entry in data.get("entries", [])[:limit]:
                yield entry
        except Exception as exc:
            msg = f"COD query failed: {exc}"
            raise RuntimeError(msg) from exc
        finally:
            client.close()

    def to_material_record(self, raw: dict[str, Any]) -> MaterialRecord:
        entry_id = str(raw.get("cod_id", raw.get("id", "")))
        elements = set(raw.get("elements", ["Li"]))
        lattice = raw.get("cell", {})
        spg = raw.get("space_group", "")
        cif_str = raw.get("cif", "")

        identity = IdentityProvenance(
            material_id=f"cod-{entry_id}",
            source_db=SourceDB.cod,
            source_id=entry_id,
            family=classify_family(elements=elements),
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