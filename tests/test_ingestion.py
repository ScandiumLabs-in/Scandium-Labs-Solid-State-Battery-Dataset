"""Tests for ingestion pipeline — connectors, Parquet writer, and orchestrator."""

from __future__ import annotations

import tempfile
from pathlib import Path

import pytest
from pymatgen.core import Lattice, Structure

from ssb_dataset.pipeline.ingest import material_record_to_dict, run_ingestion, write_partition
from ssb_dataset.schema import (
    ConfidenceTier,
    Family,
    IdentityProvenance,
    MaterialRecord,
    SourceDB,
)
from ssb_dataset.sources.aflow_connector import AFLOWConnector
from ssb_dataset.sources.classifier import classify_family
from ssb_dataset.sources.icsd_connector import ICSDConnector
from ssb_dataset.sources.jarvis_connector import JARVISConnector
from ssb_dataset.sources.mp_connector import MPConnector
from ssb_dataset.sources.nomad_connector import NOMADConnector
from ssb_dataset.sources.oqmd_connector import OQMDConnector


def _make_id(source_db: SourceDB, source_id: str, family: Family, tier: ConfidenceTier) -> IdentityProvenance:
    return IdentityProvenance(
        material_id=f"{source_db.value}-{source_id}",
        source_db=source_db,
        source_id=source_id,
        family=family,
        confidence_tier=tier,
    )


class TestIngestionPipeline:
    def test_material_record_to_dict_roundtrip(self) -> None:
        rec = MaterialRecord(
            identity=_make_id(SourceDB.literature_mined, "test-001", Family.halide, ConfidenceTier.verified_human)
        )
        d = material_record_to_dict(rec)
        assert d["identity.source_db"] == "literature_mined"
        assert d["identity.family"] == "halide"
        assert d["ion_transport.label_available"] is False
        assert d.get("ml_features.composition_descriptors") is None

    def test_write_partition_creates_parquet(self) -> None:
        recs = [
            MaterialRecord(
                identity=_make_id(SourceDB.materials_project, str(i), Family.sulfide, ConfidenceTier.dft_native)
            )
            for i in range(10)
        ]
        with tempfile.TemporaryDirectory() as tmp:
            path = write_partition(recs, tmp, "materials_project", "sulfide", 0)
            assert path.exists()
            assert path.suffix == ".parquet"
            assert "materials_project" in str(path)
            assert "sulfide" in str(path)

    def test_run_ingestion_empty_connectors(self) -> None:
        counts = run_ingestion({}, staging_dir=tempfile.mkdtemp(), batch_size=10)
        assert counts == {}

    def test_run_ingestion_single_source(self) -> None:
        def gen_records():
            for i in range(5):
                yield MaterialRecord(
                    identity=_make_id(SourceDB.materials_project, str(i), Family.garnet, ConfidenceTier.dft_native)
                )

        with tempfile.TemporaryDirectory() as tmp:
            counts = run_ingestion(
                {"test_source": gen_records()},
                staging_dir=tmp,
                batch_size=3,
            )
            assert counts["test_source"] == 5
            parts = list(Path(tmp).rglob("*.parquet"))
            assert len(parts) == 2

    def test_run_ingestion_multiple_families(self) -> None:
        def gen_records():
            for i, family in enumerate([Family.sulfide, Family.garnet, Family.halide]):
                yield MaterialRecord(
                    identity=_make_id(SourceDB.materials_project, str(i), family, ConfidenceTier.dft_native)
                )

        with tempfile.TemporaryDirectory() as tmp:
            counts = run_ingestion(
                {"multi_family": gen_records()},
                staging_dir=tmp,
                batch_size=2,
            )
            assert counts["multi_family"] == 3


class TestMPConnector:
    def test_connector_properties(self) -> None:
        conn = MPConnector()
        assert conn.source_db == "materials_project"
        assert conn._connected is False

    def test_to_material_record(self) -> None:
        conn = MPConnector()
        lattice = Lattice.cubic(10.0)
        struct = Structure(lattice, ["Li", "S"], [[0, 0, 0], [0.5, 0.5, 0.5]])
        raw = {
            "material_id": "mp-1234",
            "structure": struct,
            "initial_structure": {"cif": struct.to(fmt="cif")},
            "formation_energy_per_atom": -2.5,
            "energy_above_hull": 0.01,
            "band_gap": 3.0,
            "symmetry": {"is_disordered": False},
            "spacegroup": {"symbol": "Fm-3m"},
            "lattice_parameters": {"a": 10.0, "b": 10.0, "c": 10.0, "alpha": 90.0, "beta": 90.0, "gamma": 90.0},
        }
        rec = conn.to_material_record(raw)
        assert rec.identity.source_db == SourceDB.materials_project
        assert rec.identity.material_id == "mp-mp-1234"
        assert rec.thermodynamics.formation_energy_per_atom == -2.5
        assert rec.structure.lattice_params is not None
        assert rec.structure.lattice_params.a == 10.0

    def test_to_material_record_no_struct(self) -> None:
        conn = MPConnector()
        raw = {"material_id": "mp-9999", "structure": None, "initial_structure": None}
        rec = conn.to_material_record(raw)
        assert rec.structure.structure_relaxed is None
        assert rec.structure.lattice_params is not None

    def test_li_occupancy_extracted(self) -> None:
        lattice = Lattice.cubic(5.0)
        struct = Structure(lattice, ["Li", "Li", "S"], [[0, 0, 0], [0.5, 0.5, 0.5], [0.25, 0.25, 0.25]])
        occ = MPConnector._get_li_occupancy(struct)
        assert len(occ) == 2
        assert occ[0] == 1.0

    def test_li_occupancy_no_li(self) -> None:
        lattice = Lattice.cubic(5.0)
        struct = Structure(lattice, ["S", "P"], [[0, 0, 0], [0.5, 0.5, 0.5]])
        occ = MPConnector._get_li_occupancy(struct)
        assert occ == []

    def test_li_occupancy_none_struct(self) -> None:
        occ = MPConnector._get_li_occupancy(None)
        assert occ == []


class TestJARVISConnector:
    def test_to_material_record(self) -> None:
        conn = JARVISConnector()
        raw = {
            "jid": "JVASP-1001",
            "struct": {
                "lattice": {"a": 5.0, "b": 5.0, "c": 5.0, "alpha": 90.0, "beta": 90.0, "gamma": 90.0},
                "elements": ["Li", "Cl", "O"],
                "coords": [[0, 0, 0], [0.5, 0.5, 0.5], [0.25, 0.25, 0.25]],
                "lattice_mat": [[5.0, 0, 0], [0, 5.0, 0], [0, 0, 5.0]],
            },
            "space_group": "Pm-3m",
        }
        rec = conn.to_material_record(raw)
        assert rec.identity.source_db == SourceDB.jarvis
        assert rec.identity.family == Family.antiperovskite
        assert rec.structure.space_group == "Pm-3m"


class TestAFLOWConnector:
    def test_to_material_record(self) -> None:
        conn = AFLOWConnector()
        raw = {
            "auid": "aflow:abc123",
            "cif": "",
            "lattice": {"a": 7.5, "b": 7.5, "c": 7.5, "alpha": 90.0, "beta": 90.0, "gamma": 90.0},
            "spacegroup": {"symbol": "Ia-3d"},
        }
        rec = conn.to_material_record(raw)
        assert rec.identity.source_db == SourceDB.aflow


class TestOQMDConnector:
    def test_to_material_record(self) -> None:
        conn = OQMDConnector()
        raw = {
            "id": 5001,
            "composition": {"Li": 7, "La": 3, "Zr": 2, "O": 12},
            "lattice": {"a": 13.0, "b": 13.0, "c": 13.0, "alpha": 90.0, "beta": 90.0, "gamma": 90.0},
            "space_group": {"symbol": "Ia-3d"},
        }
        rec = conn.to_material_record(raw)
        assert rec.identity.source_db == SourceDB.oqmd
        assert rec.identity.family == Family.garnet


class TestNOMADConnector:
    def test_to_material_record(self) -> None:
        conn = NOMADConnector()
        raw = {
            "entry_id": "nomad-entry-001",
            "results": {
                "material": {
                    "elements": ["Li", "La", "Zr", "O"],
                    "symmetry": {"space_group_symbol": "Ia-3d"},
                },
            },
        }
        rec = conn.to_material_record(raw)
        assert rec.identity.source_db == SourceDB.nomad
        assert rec.identity.family == Family.garnet

    def test_to_material_record_no_lattice(self) -> None:
        conn = NOMADConnector()
        raw = {
            "entry_id": "nomad-entry-002",
            "results": {
                "material": {"elements": ["Li", "P", "S"]},
            },
        }
        rec = conn.to_material_record(raw)
        assert rec.identity.family == Family.sulfide
        assert rec.structure.lattice_params is None


class TestICSDConnector:
    def test_to_material_record(self) -> None:
        conn = ICSDConnector()
        raw = {
            "collectionId": "icsd-12345",
            "elements": ["Li", "La", "Zr", "O"],
            "cell": {
                "length_a": 13.0, "length_b": 13.0, "length_c": 13.0,
                "angle_alpha": 90.0, "angle_beta": 90.0, "angle_gamma": 90.0,
            },
            "space_group": "Ia-3d",
        }
        rec = conn.to_material_record(raw)
        assert rec.identity.source_db == SourceDB.icsd
        assert rec.identity.confidence_tier == ConfidenceTier.verified_human


class TestCODConnector:
    def test_to_material_record_is_dft_native(self) -> None:
        """COD is experimental structural data WITHOUT conductivity — so the
        tier must be dft_native, not verified_human (which implies a reviewed
        σ/Ea label)."""
        from ssb_dataset.sources.cod_connector import CODConnector
        conn = CODConnector()
        rec = conn.to_material_record({
            "cod_id": "1234567",
            "elements": ["Li", "La", "Zr", "O"],
            "lattice": {"a": 13.0, "b": 13.0, "c": 13.0},
            "space_group": "Ia-3d",
            "cif": "",
        })
        assert rec.identity.source_db == SourceDB.cod
        assert rec.identity.confidence_tier == ConfidenceTier.dft_native
        assert rec.identity.family == Family.garnet

    def test_to_material_record_classifies_antiperovskite(self) -> None:
        from ssb_dataset.sources.cod_connector import CODConnector
        conn = CODConnector()
        rec = conn.to_material_record({
            "cod_id": "9",
            "elements": ["Li", "O", "Cl"],
            "lattice": {},
            "space_group": "Pm-3m",
            "cif": "",
        })
        assert rec.identity.family == Family.antiperovskite


class TestMaterialsCloudConnector:
    def test_to_material_record(self) -> None:
        from ssb_dataset.sources.materials_cloud_connector import (
            MaterialsCloudConnector,
        )
        conn = MaterialsCloudConnector()
        raw = {
            "mc_id": "mc-0001",
            "formula": "Li7La3Zr2O12",
            "elements": ["Li", "La", "Zr", "O"],
            "lattice": {"a": 13.0, "b": 13.0, "c": 13.0,
                        "alpha": 90.0, "beta": 90.0, "gamma": 90.0},
            "space_group": "Ia-3d",
        }
        rec = conn.to_material_record(raw)
        assert rec.identity.source_db == SourceDB.materials_cloud
        assert rec.identity.family == Family.garnet
        assert rec.identity.confidence_tier == ConfidenceTier.dft_native
        assert rec.structure.lattice_params.a == 13.0

    def test_source_db_registered(self) -> None:
        assert "materials_cloud" in SourceDB._value2member_map_


class TestAFLOWAFLUX:
    def test_to_material_record_from_compound(self) -> None:
        """AFLUX entries carry a formula string (compound) but no CIF; the
        connector must classify from the formula, not just raw elements."""
        conn = AFLOWConnector()
        raw = {
            "auid": "aflow:abc",
            "compound": "Li10GeP2S12",
            "cif": "",
            "ca": 12.0, "cb": 12.0, "cc": 12.0,
            "alpha": 90.0, "beta": 90.0, "gamma": 90.0,
            "spacegroup_relax": {"symbol": "P4_3 2_1 2"},
        }
        rec = conn.to_material_record(raw)
        assert rec.identity.source_db == SourceDB.aflow
        assert rec.identity.family == Family.sulfide
        assert rec.structure.space_group == "P4_3 2_1 2"


class TestOQMDUnitCell:
    def test_unit_cell_matrix_to_lattice(self) -> None:
        from ssb_dataset.sources.oqmd_connector import _unit_cell_to_lattice
        import math
        out = _unit_cell_to_lattice({"lattice": [
            [5.0, 0.0, 0.0],
            [0.0, 5.0, 0.0],
            [0.0, 0.0, 5.0],
        ]})
        assert math.isclose(out["a"], 5.0)
        assert math.isclose(out["alpha"], 90.0)
        assert math.isclose(out["gamma"], 90.0)


class TestClassifierExtended:
    @pytest.mark.parametrize(
        ("formula", "expected"),
        [
            ("Li10GeP2S12", Family.sulfide),
            ("Li6PS5Cl", Family.argyrodite),
            ("Li6PS5Br", Family.argyrodite),
            ("Li7La3Zr2O12", Family.garnet),
            ("Li3xLa2/3-xTiO3", Family.perovskite),
            ("Li1.3Al0.3Ti1.7(PO4)3", Family.nasicon),
            ("Li3InCl6", Family.halide),
            ("Li3YCl6", Family.halide),
            ("Li2ZrCl6", Family.halide),
            ("LiBH4", Family.borohydride),
            ("Li3OCl", Family.antiperovskite),
            ("LiCoO2", Family.oxide),
            ("Li2O", Family.oxide),
            ("PEO10-LiTFSI", Family.polymer_composite),
            ("LiPON", Family.unknown),
        ],
    )
    def test_real_formulas(self, formula: str, expected: Family) -> None:
        result = classify_family(composition=formula)
        assert result == expected, f"{formula} -> {result}, expected {expected}"
