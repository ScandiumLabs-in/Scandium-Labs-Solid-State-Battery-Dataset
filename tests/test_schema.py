"""Tests for schema, classifiers, and source connectors."""

from __future__ import annotations

import pytest
from pymatgen.core import Composition

from ssb_dataset.schema import (
    ConductivityPoint,
    ConfidenceTier,
    Family,
    IdentityProvenance,
    LatticeParams,
    MaterialRecord,
    SourceDB,
    StructureBlock,
    StructureType,
    SynthesisBlock,
)
from ssb_dataset.sources.classifier import classify_family


class TestFamilyClassifier:
    @pytest.mark.parametrize(
        ("elements", "expected"),
        [
            ({"Li", "S", "P", "Si"}, Family.sulfide),
            ({"Li", "La", "Zr", "O"}, Family.garnet),
            ({"Li", "La", "Ti", "O"}, Family.perovskite),
            ({"Li", "Zr", "P", "O"}, Family.nasicon),
            ({"Li", "In", "Cl"}, Family.halide),
            ({"Li", "Y", "Cl"}, Family.halide),
            ({"Li", "Sc", "Cl"}, Family.halide),
            ({"Li", "B", "H"}, Family.borohydride),
            ({"Li", "Cl", "O"}, Family.antiperovskite),
            ({"Li", "S", "P", "Cl"}, Family.argyrodite),
            ({"Li", "Fe", "P", "O"}, Family.oxide),
            ({"Li", "Al", "O"}, Family.oxide),
            ({"Li", "La", "O"}, Family.oxide),
            ({"C", "H", "Li"}, Family.polymer_composite),
            ({"Li", "C", "O"}, Family.unknown),
            ({"Li", "P", "O", "N"}, Family.unknown),
        ],
    )
    def test_classification(self, elements: set[str], expected: Family) -> None:
        result = classify_family(elements=elements)
        assert result == expected, f"{elements} -> {result}, expected {expected}"

    def test_classify_from_composition(self) -> None:
        comp = "Li6PS5Cl"
        result = classify_family(composition=comp)
        comp_obj = Composition(comp)
        result2 = classify_family(composition=comp_obj)
        result3 = classify_family(composition={"Li": 6, "P": 1, "S": 5, "Cl": 1})
        assert result == Family.argyrodite
        assert result2 == Family.argyrodite
        assert result3 == Family.argyrodite

    def test_classify_lipo4_oxide_not_polymer(self) -> None:
        assert classify_family(composition="LiCoO2") == Family.oxide
        assert classify_family(composition="Li2CO3") == Family.unknown
        assert classify_family(composition="Li3PO4") == Family.unknown


class TestMaterialRecord:
    def test_minimal_record(self) -> None:
        rec = MaterialRecord(
            identity=IdentityProvenance(
                source_db=SourceDB.literature_mined,
                source_id="test-000",
                family=Family.halide,
                confidence_tier=ConfidenceTier.verified_human,
            )
        )
        assert rec.identity.family == Family.halide
        assert rec.ion_transport.label_available is False

    def test_hydride_t_curve(self) -> None:
        rec = MaterialRecord(
            identity=IdentityProvenance(
                source_db=SourceDB.literature_mined,
                source_id="hydride-tcurve-001",
                family=Family.hydride,
                confidence_tier=ConfidenceTier.verified_human,
            )
        )
        rec.ion_transport.sigma_vs_T_curve = [
            ConductivityPoint(temperature_K=373.0, conductivity_S_per_cm=1e-4),
            ConductivityPoint(temperature_K=473.0, conductivity_S_per_cm=1e-3),
        ]
        rec.ion_transport.label_available = True
        assert len(rec.ion_transport.sigma_vs_T_curve) == 2
        assert rec.ion_transport.sigma_vs_T_curve[1].temperature_K == 473.0

    def test_polymer_amorphous(self) -> None:
        rec = MaterialRecord(
            identity=IdentityProvenance(
                source_db=SourceDB.literature_mined,
                source_id="polymer-amorph-001",
                family=Family.polymer_composite,
                confidence_tier=ConfidenceTier.high_confidence_extraction,
            ),
            structure=StructureBlock(
                structure_type=StructureType.amorphous,
                structure_relaxed=None,
            ),
            synthesis=SynthesisBlock(
                processing_metadata={
                    "crystallinity_pct": 15.0,
                    "plasticizer": "PEG",
                    "salt_concentration": "1M",
                }
            ),
        )
        assert rec.structure.structure_type == StructureType.amorphous
        assert rec.synthesis.processing_metadata["crystallinity_pct"] == 15.0

    def test_full_record(self) -> None:
        rec = MaterialRecord(
            identity=IdentityProvenance(
                material_id="mp-123456",
                source_db=SourceDB.materials_project,
                source_id="123456",
                family=Family.garnet,
                confidence_tier=ConfidenceTier.dft_native,
            ),
            structure=StructureBlock(
                structure_relaxed="data_cif\n_cell_length_a 12.0",
                space_group="Ia-3d",
                lattice_params=LatticeParams(
                    a=12.0, b=12.0, c=12.0, alpha=90.0, beta=90.0, gamma=90.0
                ),
            ),
        )
        data = rec.model_dump()
        assert data["identity"]["family"] == "garnet"
        assert data["structure"]["lattice_params"]["a"] == 12.0


class TestConnectorBase:
    def test_connector_imports(self) -> None:
        from ssb_dataset.sources import (
            AFLOWConnector,
            ICSDConnector,
            JARVISConnector,
            MPConnector,
            NOMADConnector,
            OQMDConnector,
        )

        connectors = [MPConnector, JARVISConnector, AFLOWConnector, OQMDConnector, NOMADConnector, ICSDConnector]
        assert len(connectors) == 6
        for c in connectors:
            instance = c()
            assert instance.source_db is not None