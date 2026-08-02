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
from ssb_dataset.sources.classifier import classify_family, is_electrolyte_candidate


class TestElectrolyteCandidateFlag:
    """Relevance heuristics for the bulk DFT catalog: a composition stays in its
    formula family (LiCoO2 -> oxide) but is flagged as NON-electrolyte when it is a
    known intercalation cathode. Garnet/LLTO/NASICON are always candidates."""

    @pytest.mark.parametrize(
        ("composition", "expected"),
        [
            ("LiCoO2", False),
            ("LiMn2O4", False),
            ("LiNiO2", False),
            ("Li3NiMnO5", False),
            ("LiFePO4", False),
            ("Li7La3Zr2O12", True),   # LLZO garnet
            ("Li6.5La3Zr1.5Ta0.5O12", True),
            ("Li3xLa2/3-xTiO3", True),  # LLTO perovskite
            ("Li10GeP2S12", True),    # LGPS sulfide
            ("Li6PS5Cl", True),       # argyrodite
            ("LiO2", True),
            ("Li3PO4", True),
            ("Li2O", True),
        ],
    )
    def test_candidate_flag(self, composition: str, expected: bool) -> None:
        assert is_electrolyte_candidate(composition=composition) == expected

    def test_garnet_family_preserved_and_candidate(self) -> None:
        """relabeling a composition family: LLZO stays garnet AND candidate."""
        assert classify_family(composition="Li7La3Zr2O12") == Family.garnet
        assert is_electrolyte_candidate(composition="Li7La3Zr2O12") is True

    def test_cathode_stays_oxide_but_not_candidate(self) -> None:
        """LiCoO2 is an oxide by composition but not an electrolyte candidate."""
        assert classify_family(composition="LiCoO2") == Family.oxide
        assert is_electrolyte_candidate(composition="LiCoO2") is False


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