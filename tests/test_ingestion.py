"""Tests for ingestion pipeline — connectors, Parquet writer, and orchestrator."""

from __future__ import annotations

import tempfile
from pathlib import Path

import httpx
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


def _fake_json_response(status: int, payload: object) -> httpx.Response:
    """Build an httpx.Response usable with raise_for_status() (sets request)."""
    request = httpx.Request("GET", "http://fake/")
    return httpx.Response(status, json=payload, request=request)


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

    def test_to_material_record_prefers_species_over_compound(self) -> None:
        """AFLUX 'species' is authoritative; a compound string that would
        misparse (intermetallic header) must not drive classification when
        species is present."""
        conn = AFLOWConnector()
        raw = {
            "auid": "aflow:xyz",
            "compound": "AgAlLi_sv/TBCC014.BCA",
            "species": ["Ag", "Al", "Li"],
            "cif": "",
            "spacegroup_relax": {"symbol": "C2/m"},
        }
        rec = conn.to_material_record(raw)
        assert rec.identity.family == Family.unknown

    def test_to_material_record_parses_contcar_lattice(self) -> None:
        """AFLOW CONTCAR.relax is VASP POSCAR format; lattice params must be
        parsed from it, not left as zero."""
        conn = AFLOWConnector()
        contcar = (
            "AgAlLi_sv/TBCC014.BCA - (TBCC014.BCA) - \n"
            "   1.0\n"
            "     5.0   0.0   0.0\n"
            "     0.0   5.0   0.0\n"
            "     0.0   0.0   5.0\n"
            "   Ag   Al   Li\n"
            "     1     1     1\n"
            "Direct\n"
            "  0.0  0.0  0.0\n"
            "  0.5  0.5  0.5\n"
            "  0.25 0.25 0.25\n"
        )
        raw = {
            "auid": "aflow:l",
            "compound": "AgAlLi",
            "species": ["Ag", "Al", "Li"],
            "cif": contcar,
            "spacegroup_relax": {"symbol": "Pm-3m"},
        }
        rec = conn.to_material_record(raw)
        assert rec.structure.lattice_params is not None
        assert abs(rec.structure.lattice_params.a - 5.0) < 1e-6

    def test_fetch_records_parses_aflux_dict_response(self) -> None:
        """AFLUX returns {"1 of N": {...}, ...} not a list; fetch_records must
        flatten it and honor paging starting at page 1 (page 0 = all results)."""
        import httpx

        conn = AFLOWConnector()
        conn._connected = True
        pages = iter([
            {"1 of 2": {"auid": "aflow:a", "aurl": "h:LD/A/B", "species": ["Li", "O"]},
             "2 of 2": {"auid": "aflow:b", "aurl": "h:LD/A/C", "species": ["Li", "Cl"]}},
        ])

        class FakeClient:
            def get(self, url: str) -> httpx.Response:
                assert url.startswith("?species(Li),paging(")
                return _fake_json_response(200, next(pages))

        conn._client = FakeClient()  # type: ignore[assignment]
        recs = list(conn.fetch_records(limit=3))
        assert len(recs) == 2
        assert recs[0]["auid"] == "aflow:a"

    def test_catalog_cfaflow_returns_empty_is_dropped(self) -> None:
        """catalog(CFAFLOW_LIB1) returns [] on the live API (2026-08-05); the
        query must not include it so records are actually returned."""
        import httpx

        conn = AFLOWConnector()
        conn._connected = True

        class FakeClient:
            def get(self, url: str) -> httpx.Response:
                assert "catalog(" not in url
                return _fake_json_response(200, {"1 of 1": {"auid": "aflow:a", "species": ["Li", "O"]}})

        conn._client = FakeClient()  # type: ignore[assignment]
        recs = list(conn.fetch_records(limit=1))
        assert len(recs) == 1


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

    def test_fetch_records_uses_element_set_filter(self) -> None:
        """OQMD only honors element filters via filter=element_set=...; the
        connector must send that, not a bare elements param (which 502s)."""
        import httpx

        conn = OQMDConnector()
        conn._connected = True

        class FakeClient:
            def get(self, path: str, params: dict, timeout: int) -> httpx.Response:
                assert path == "formationenergy"
                assert params["filter"].startswith("element_set=")
                return _fake_json_response(200, {
                    "data": [
                        {"entry_id": 1, "name": "LiCl", "composition": {"Li": 1, "Cl": 1}},
                        {"entry_id": 2, "name": "Li2O", "composition": {"Li": 2, "O": 1}},
                    ]
                })

        conn._client = FakeClient()  # type: ignore[assignment]
        recs = list(conn.fetch_records(limit=5))
        assert len(recs) == 2
        assert recs[0]["id"] == 1

    def test_fetch_records_paginates_in_small_pages(self) -> None:
        """OQMD 502s on large page sizes; fetch_records must page through in
        chunks of 50 rather than one big request."""
        import httpx

        conn = OQMDConnector()
        conn._connected = True
        calls = []

        class FakeClient:
            def get(self, path: str, params: dict, timeout: int) -> httpx.Response:
                calls.append(params["limit"])
                return _fake_json_response(200, {
                    "data": [
                        {"entry_id": i, "name": "LiX", "composition": {"Li": 1, "X": 1}}
                        for i in range(params["limit"])
                    ]
                })

        conn._client = FakeClient()  # type: ignore[assignment]
        recs = list(conn.fetch_records(limit=55))
        assert len(recs) == 55
        assert calls[0] == 50
        assert calls[-1] == 5  # remainder page


class TestCODConnector:
    def test_to_material_record_reads_file_id_and_lattice(self) -> None:
        from ssb_dataset.sources.cod_connector import CODConnector
        conn = CODConnector()
        raw = {
            "cod_id": "1000067",
            "elements": ["Li"],
            "lattice": {"a": 5.0, "b": 5.0, "c": 5.0, "alpha": 90.0, "beta": 90.0, "gamma": 90.0},
            "space_group": "P 1",
            "cif": (
                "# comment header\n"
                "data_1\n"
                "_cell_length_a 5.0\n_cell_length_b 5.0\n_cell_length_c 5.0\n"
                "_cell_angle_alpha 90\n_cell_angle_beta 90\n_cell_angle_gamma 90\n"
                "_symmetry_space_group_name_H-M 'P 1'\n"
                "loop_\n_atom_site_label\n_atom_site_type_symbol\n"
                "_atom_site_fract_x\n_atom_site_fract_y\n_atom_site_fract_z\n"
                "Li1 Li 0 0 0\nO1 O 0.5 0.5 0.5\n"
            ),
        }
        rec = conn.to_material_record(raw)
        assert rec.identity.material_id == "cod-1000067"
        assert rec.identity.family == Family.oxide
        assert abs(rec.structure.lattice_params.a - 5.0) < 1e-6

    def test_fetch_records_uses_el1_element_search(self) -> None:
        """COD's formula= param is an exact-formula match (returns 21 for Li);
        el1= returns all Li-containing entries (8.8k+)."""
        import httpx

        from ssb_dataset.sources.cod_connector import CODConnector
        conn = CODConnector()
        conn._connected = True

        class FakeClient:
            def get(self, url: str, params: dict, timeout: int) -> httpx.Response:
                assert params["el1"] == "Li"
                return _fake_json_response(200, {
                    "results": [{"file": "1000067", "a": "5.0", "b": "5.0", "c": "5.0",
                                 "alpha": "90", "beta": "90", "gamma": "90", "sg": "P 1"}]
                })

        conn._client = FakeClient()  # type: ignore[assignment]
        import unittest.mock as mock
        with mock.patch.object(CODConnector, "_fetch_cif", return_value=""):
            recs = list(conn.fetch_records(limit=5))
        assert len(recs) == 1
        assert recs[0]["cod_id"] == "1000067"


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
