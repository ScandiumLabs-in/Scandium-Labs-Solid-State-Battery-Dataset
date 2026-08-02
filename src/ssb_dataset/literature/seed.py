"""Phase 3.5 — Seed data bootstrap.

Hand-curated conductivity and activation energy values from well-known
SSB review papers. Used to validate the extraction pipeline (run the
pipeline on the same source papers and check it reproduces these values)
and as a high-confidence seed set for the dataset.
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from ssb_dataset.schema import (
    ConfidenceTier,
    ConductivitySourceType,
    ConductivityType,
    ExtractionMethod,
    Family,
    IdentityProvenance,
    IonTransportBlock,
    MaterialRecord,
    SourceDB,
    TemperatureRange,
    TextProvenanceBlock,
)


SEED_RECORDS: list[dict[str, Any]] = [
    # === Sulfides ===
    {
        "composition": "Li10GeP2S12",
        "sigma_S_per_cm": 1.2e-2,
        "activation_energy_eV": 0.22,
        "temperature_K": 298,
        "measurement_method": "AC impedance spectroscopy",
        "conductivity_type": "bulk",
        "synthesis_route": "solid state",
        "family": Family.sulfide,
        "subfamily_tag": ["LGPS"],
        "doi": "10.1038/nmat3066",
        "title": "Lithium superionic conductor Li10GeP2S12",
    },
    {
        "composition": "Li6PS5Cl",
        "sigma_S_per_cm": 1.0e-3,
        "activation_energy_eV": 0.30,
        "temperature_K": 298,
        "measurement_method": "AC impedance spectroscopy",
        "conductivity_type": "bulk",
        "synthesis_route": "mechanochemical",
        "family": Family.argyrodite,
        "subfamily_tag": ["argyrodite"],
        "doi": "10.1039/C5EE02930D",
        "title": "Argyrodite-type Li6PS5X solid electrolytes",
    },
    {
        "composition": "Li6PS5Br",
        "sigma_S_per_cm": 7.0e-3,
        "activation_energy_eV": 0.28,
        "temperature_K": 298,
        "measurement_method": "AC impedance spectroscopy",
        "conductivity_type": "bulk",
        "synthesis_route": "mechanochemical",
        "family": Family.argyrodite,
        "subfamily_tag": ["argyrodite"],
        "doi": "10.1039/C5EE02930D",
        "title": "Argyrodite-type Li6PS5X solid electrolytes",
    },
    {
        "composition": "Li3PS4",
        "sigma_S_per_cm": 3.0e-5,
        "activation_energy_eV": 0.40,
        "temperature_K": 298,
        "measurement_method": "AC impedance spectroscopy",
        "conductivity_type": "total",
        "synthesis_route": "mechanochemical",
        "family": Family.sulfide,
        "subfamily_tag": ["thio-LISICON"],
        "doi": "10.1016/j.ssi.2015.09.010",
        "title": "Lithium thiophosphate electrolytes",
    },
    # === Garnets ===
    {
        "composition": "Li7La3Zr2O12",
        "sigma_S_per_cm": 3.0e-4,
        "activation_energy_eV": 0.35,
        "temperature_K": 298,
        "measurement_method": "AC impedance spectroscopy",
        "conductivity_type": "bulk",
        "synthesis_route": "solid state",
        "family": Family.garnet,
        "subfamily_tag": ["garnet_cubic"],
        "doi": "10.1002/anie.200701144",
        "title": "Fast lithium ion conduction in garnet-type Li7La3Zr2O12",
    },
    {
        "composition": "Li6.5La3Zr1.5Ta0.5O12",
        "sigma_S_per_cm": 1.0e-3,
        "activation_energy_eV": 0.30,
        "temperature_K": 298,
        "measurement_method": "AC impedance spectroscopy",
        "conductivity_type": "total",
        "synthesis_route": "solid state",
        "family": Family.garnet,
        "subfamily_tag": ["garnet_cubic", "Ta-doped"],
        "doi": "10.1039/C6EE00556K",
        "title": "Ta-doped LLZO garnet electrolyte",
    },
    # === Perovskites ===
    {
        "composition": "Li0.33La0.56TiO3",
        "sigma_S_per_cm": 2.0e-5,
        "activation_energy_eV": 0.35,
        "temperature_K": 298,
        "measurement_method": "AC impedance spectroscopy",
        "conductivity_type": "bulk",
        "synthesis_route": "solid state",
        "family": Family.perovskite,
        "subfamily_tag": ["LLTO"],
        "doi": "10.1016/0167-2738(93)90241-4",
        "title": "Lithium ion conductivity in LLTO perovskite",
    },
    # === NASICON ===
    {
        "composition": "Li1.3Al0.3Ti1.7(PO4)3",
        "sigma_S_per_cm": 3.0e-4,
        "activation_energy_eV": 0.30,
        "temperature_K": 298,
        "measurement_method": "AC impedance spectroscopy",
        "conductivity_type": "total",
        "synthesis_route": "sol-gel",
        "family": Family.nasicon,
        "subfamily_tag": ["LATP"],
        "doi": "10.1016/S0167-2738(03)00260-7",
        "title": "LATP NASICON-type solid electrolyte",
    },
    {
        "composition": "Li1.5Al0.5Ge1.5(PO4)3",
        "sigma_S_per_cm": 4.0e-4,
        "activation_energy_eV": 0.32,
        "temperature_K": 298,
        "measurement_method": "AC impedance spectroscopy",
        "conductivity_type": "total",
        "synthesis_route": "melt-quench",
        "family": Family.nasicon,
        "subfamily_tag": ["LAGP"],
        "doi": "10.1016/j.electacta.2012.04.007",
        "title": "LAGP glass-ceramic electrolyte",
    },
    # === Halides ===
    {
        "composition": "Li3InCl6",
        "sigma_S_per_cm": 2.0e-3,
        "activation_energy_eV": 0.33,
        "temperature_K": 298,
        "measurement_method": "AC impedance spectroscopy",
        "conductivity_type": "bulk",
        "synthesis_route": "solid state",
        "family": Family.halide,
        "subfamily_tag": [],
        "doi": "10.1038/s41467-019-09619-5",
        "title": "Li3InCl6 halide superionic conductor",
    },
    {
        "composition": "Li3YCl6",
        "sigma_S_per_cm": 5.0e-4,
        "activation_energy_eV": 0.38,
        "temperature_K": 298,
        "measurement_method": "AC impedance spectroscopy",
        "conductivity_type": "bulk",
        "synthesis_route": "solid state",
        "family": Family.halide,
        "subfamily_tag": [],
        "doi": "10.1016/j.matt.2019.06.004",
        "title": "Li3YCl6 lithium halide solid electrolyte",
    },
    {
        "composition": "Li2ZrCl6",
        "sigma_S_per_cm": 1.0e-3,
        "activation_energy_eV": 0.35,
        "temperature_K": 298,
        "measurement_method": "AC impedance spectroscopy",
        "conductivity_type": "bulk",
        "synthesis_route": "solid state",
        "family": Family.halide,
        "subfamily_tag": [],
        "doi": "10.1021/jacs.1c07481",
        "title": "Li2ZrCl6 halide solid electrolyte",
    },
    # === Hydrides ===
    {
        "composition": "LiBH4",
        "sigma_S_per_cm": 1.0e-6,
        "activation_energy_eV": 0.60,
        "temperature_K": 298,
        "measurement_method": "AC impedance spectroscopy",
        "conductivity_type": "bulk",
        "synthesis_route": "solid state",
        "family": Family.borohydride,
        "subfamily_tag": ["high-T hexagonal"],
        "doi": "10.1038/nmat1912",
        "title": "LiBH4 high-temperature ionic conductor",
    },
    {
        "composition": "Li2B12H12",
        "sigma_S_per_cm": 8.9e-6,
        "activation_energy_eV": 0.59,
        "temperature_K": 298,
        "measurement_method": "AC impedance spectroscopy",
        "conductivity_type": "total",
        "synthesis_route": "solid state",
        "family": Family.borohydride,
        "subfamily_tag": ["closo-borate"],
        "doi": "10.1002/advs.202510193",
        "title": "Facile synthesis of inorganic Li2B12H12/LiI solid electrolytes (pristine Li2B12H12 baseline)",
    },
    # === Antiperovskites ===
    {
        "composition": "Li3OCl",
        "sigma_S_per_cm": 1.0e-7,
        "activation_energy_eV": 0.55,
        "temperature_K": 298,
        "measurement_method": "AC impedance spectroscopy",
        "conductivity_type": "total",
        "synthesis_route": "solid state",
        "family": Family.antiperovskite,
        "subfamily_tag": [],
        "doi": "10.1039/C3EE00512B",
        "title": "Li3OCl antiperovskite solid electrolyte",
    },
]


def get_seed_records() -> list[MaterialRecord]:
    """Return the seed set as MaterialRecord objects."""
    records: list[MaterialRecord] = []
    for item in SEED_RECORDS:
        rec = MaterialRecord(
            identity=IdentityProvenance(
                material_id=f"seed-{item['family'].value}-{len(records)}",
                source_db=SourceDB.literature_mined,
                source_id=item.get("doi", ""),
                composition=item.get("composition", ""),
                family=item["family"],
                subfamily_tag=item.get("subfamily_tag", []),
                ingestion_date=datetime.now(timezone.utc),
                confidence_tier=ConfidenceTier.verified_human,
            ),
            ion_transport=IonTransportBlock(
                sigma_RT=item["sigma_S_per_cm"],
                activation_energy_Ea=item.get("activation_energy_eV"),
                temperature_range_measured=(
                    TemperatureRange(min_K=item["temperature_K"], max_K=item["temperature_K"])
                    if item.get("temperature_K")
                    else None
                ),
                measurement_method=item.get("measurement_method", ""),
                label_available=True,
                conductivity_type=ConductivityType.bulk if item.get("conductivity_type") == "bulk" else ConductivityType.total,
                conductivity_source_type=ConductivitySourceType.measured,
            ),
            text_provenance=TextProvenanceBlock(
                source_doi=item.get("doi", ""),
                source_paper_title=item.get("title", ""),
                extraction_method=ExtractionMethod.human_curated,
                extraction_confidence_score=1.0,
                extraction_reviewer="seed-set-bootstrap",
            ),
        )
        records.append(rec)
    return records


def validate_extraction_against_seed(
    extracted: list[MaterialRecord],
    tolerance_factor: float = 2.0,
) -> dict[str, Any]:
    """Compare extracted records against the seed set to measure accuracy.

    Returns a validation report with per-field accuracy.
    """
    seed_map: dict[str, dict[str, Any]] = {}
    for i, item in enumerate(SEED_RECORDS):
        key = item.get("doi", f"seed-{i}")
        composition = item["composition"]
        seed_map[f"{key}::{composition}"] = item

    results: dict[str, Any] = {
        "total_seed": len(SEED_RECORDS),
        "matched": 0,
        "sigma_accuracy": 0,
        "ea_accuracy": 0,
        "per_composition": {},
        "failed_compositions": [],
    }

    for rec in extracted:
        doi = rec.identity.source_id or rec.text_provenance.source_doi or ""
        seed = None

        for item in SEED_RECORDS:
            item_doi = item.get("doi", "")
            if doi == item_doi:
                seed = item
                break

        if not seed:
            continue

        results["matched"] += 1
        transport = rec.ion_transport
        entry: dict[str, Any] = {"matched": True, "composition": seed["composition"]}

        if transport.sigma_RT is not None and seed.get("sigma_S_per_cm"):
            ratio = transport.sigma_RT / seed["sigma_S_per_cm"]
            sigma_ok = 1 / tolerance_factor <= ratio <= tolerance_factor
            entry["sigma_ok"] = sigma_ok
            entry["sigma_extracted"] = transport.sigma_RT
            entry["sigma_expected"] = seed["sigma_S_per_cm"]
            if sigma_ok:
                results["sigma_accuracy"] += 1
        else:
            entry["sigma_ok"] = None

        if transport.activation_energy_Ea is not None and seed.get("activation_energy_eV"):
            ea_ratio = transport.activation_energy_Ea / seed["activation_energy_eV"]
            ea_ok = 1 / tolerance_factor <= ea_ratio <= tolerance_factor
            entry["ea_ok"] = ea_ok
            entry["ea_extracted"] = transport.activation_energy_Ea
            entry["ea_expected"] = seed["activation_energy_eV"]
            if ea_ok:
                results["ea_accuracy"] += 1
        else:
            entry["ea_ok"] = None

        results["per_composition"][doi] = entry

    results["sigma_accuracy_pct"] = (results["sigma_accuracy"] / max(results["matched"], 1)) * 100
    results["ea_accuracy_pct"] = (results["ea_accuracy"] / max(results["matched"], 1)) * 100
    return results
