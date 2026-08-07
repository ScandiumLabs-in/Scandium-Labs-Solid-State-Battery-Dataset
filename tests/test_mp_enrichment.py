"""Tests for the Layer 5/6/7/8/10 MP enrichment gap-closure (2026-08-05):
schema fields, enrich_mp_api.py helpers, and expand_mp.py consumption.
No network, no MP API — pure-function unit tests."""

from __future__ import annotations

import sys
from pathlib import Path

import pytest
from pymatgen.core import Element

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "scripts"))

from enrich_mp_api import (
    _coordination_number,
    _mineral_prototype,
    _tensor33,
    _tensor_matrix,
)

from ssb_dataset.schema import (
    ChemistryBlock,
    ConfidenceTier,
    DielectricBlock,
    ElectronicBlock,
    Family,
    IdentityProvenance,
    MaterialRecord,
    MechanicalBlock,
    SourceDB,
    StructureBlock,
)


@pytest.fixture(autouse=True)
def _protect_env():
    """expand_mp.py calls load_dotenv() at import time, which would pollute
    os.environ (HF_TOKEN etc.) for later tests in this file and others.
    Snapshot before any expand_mp import and restore after each test."""
    import os

    env_backup = dict(os.environ)
    yield
    os.environ.clear()
    os.environ.update(env_backup)


class TestMineralPrototype:
    def test_simple_prototype(self) -> None:
        assert _mineral_prototype(
            "Li is Copper structured and crystallizes in the cubic Fm-3m "
            "space group.") == "Copper"

    def test_multitoken_prototype(self) -> None:
        assert _mineral_prototype(
            "X is alpha La structured and crystallizes in the hexagonal "
            "P6_3/mmc space group.") == "alpha La"

    def test_no_structured_token_returns_none(self) -> None:
        assert _mineral_prototype(
            "BaLi4 crystallizes in the hexagonal P6_3/mmc space group.") is None

    def test_empty_and_none(self) -> None:
        assert _mineral_prototype(None) is None
        assert _mineral_prototype("") is None


class TestTensorConverters:
    def test_vortex_wrapper(self) -> None:
        raw = {"v1v1": 1.0, "v1v2": 2.0, "v1v3": 3.0, "v1v4": 4.0,
               "v1v5": 5.0, "v1v6": 6.0, "v2v1": 7.0, "v2v2": 8.0,
               "v2v3": 9.0, "v2v4": 10.0, "v2v5": 11.0, "v2v6": 12.0,
               "v3v1": 13.0, "v3v2": 14.0, "v3v3": 15.0, "v3v4": 16.0,
               "v3v5": 17.0, "v3v6": 18.0, "v4v1": 19.0, "v4v2": 20.0,
               "v4v3": 21.0, "v4v4": 22.0, "v4v5": 23.0, "v4v6": 24.0,
               "v5v1": 25.0, "v5v2": 26.0, "v5v3": 27.0, "v5v4": 28.0,
               "v5v5": 29.0, "v5v6": 30.0, "v6v1": 31.0, "v6v2": 32.0,
               "v6v3": 33.0, "v6v4": 34.0, "v6v5": 35.0, "v6v6": 36.0}
        m = _tensor_matrix(raw)
        assert m is not None
        assert m[0] == [1.0, 2.0, 3.0, 4.0, 5.0, 6.0]
        assert m[5][5] == 36.0

    def test_raw_ieee_wrapper(self) -> None:
        raw = {
            "raw": ((1.0, 2.0), (3.0, 4.0)),
            "ieee_format": ((1, 2), (3, 4)),
        }
        m = _tensor_matrix(raw)
        assert m == [[1.0, 2.0], [3.0, 4.0]]

    def test_plain_list(self) -> None:
        m = _tensor_matrix([[1.0, 2.0], [3.0, 4.0]])
        assert m == [[1.0, 2.0], [3.0, 4.0]]

    def test_none_and_junk(self) -> None:
        assert _tensor_matrix(None) is None
        assert _tensor_matrix({}) is None

    def test_tensor33(self) -> None:
        tri = ((1.0, 0.0, 0.0), (0.0, 2.0, 0.0), (0.0, 0.0, 3.0))
        assert _tensor33(tri) == [[1.0, 0.0, 0.0], [0.0, 2.0, 0.0],
                                  [0.0, 0.0, 3.0]]

    def test_tensor33_none(self) -> None:
        assert _tensor33(None) is None


class TestBondsDescriptors:
    """Layer 8 — bonds endpoint helpers (bond_length_stats, coordination
    number)."""

    def test_coordination_number_max(self) -> None:
        assert _coordination_number(["Cu-Cu(6),Nd(3)", "Cu-Cu(8),Nd(4)"]) == 8.0

    def test_coordination_number_single(self) -> None:
        assert _coordination_number(["Nd-Cu(18)"]) == 18.0

    def test_coordination_number_none_and_empty(self) -> None:
        assert _coordination_number(None) is None
        assert _coordination_number([]) is None

    def test_coordination_number_malformed(self) -> None:
        assert _coordination_number(["Cu-Cu,Nd", "junk"]) is None

    def test_structure_block_bond_fields(self) -> None:
        s = StructureBlock(
            bond_length_stats={"min": 1.5, "max": 2.2, "mean": 1.9,
                               "variance": 0.06},
            bond_types={"Li-O": [1.9, 2.0, 2.1]},
            coordination_number=6.0,
            dimensionality=3,
        )
        assert s.bond_length_stats["mean"] == 1.9
        assert s.bond_types["Li-O"] == [1.9, 2.0, 2.1]
        assert s.coordination_number == 6.0
        assert s.dimensionality == 3


class TestChemistryBlock:
    """Layer 7 — composition-derived chemistry descriptors."""

    def test_chemistry_block_default(self) -> None:
        c = ChemistryBlock()
        assert c.electronegativity_mean is None
        assert c.atomic_fractions == {}
        assert c.elemental_fractions == {}

    def test_chemistry_block_populated(self) -> None:
        c = ChemistryBlock(
            electronegativity_mean=2.04,
            electronegativity_max=3.44,
            electronegativity_min=0.98,
            electronegativity_std=1.2,
            valence_electron_count=12.5,
            atomic_fractions={"Li": 0.5, "O": 0.5},
            elemental_fractions={"Li": 0.5, "O": 0.5},
        )
        assert c.electronegativity_max == 3.44
        assert c.valence_electron_count == 12.5

    def test_chemistry_descriptors_li2o(self) -> None:
        from expand_mp import _chemistry_descriptors

        d = _chemistry_descriptors({"composition_reduced": "Li2O"})
        assert d.atomic_fractions == {"Li": pytest.approx(2 / 3),
                                      "O": pytest.approx(1 / 3)}
        assert d.electronegativity_max == pytest.approx(
            max(Element("Li").X, Element("O").X))

    def test_chemistry_descriptors_absent_formula(self) -> None:
        from expand_mp import _chemistry_descriptors

        c = _chemistry_descriptors({"composition_reduced": None})
        assert c.electronegativity_mean is None
        assert c.atomic_fractions == {}


class TestSchemaEnrichmentFields:
    """The schema fields the enrichment populates must exist and be typeable."""

    def test_mechanical_block_extras(self) -> None:
        mech = MechanicalBlock(
            debye_temperature=385.3,
            sound_velocity={"transverse": 2861.7, "longitudinal": 5358.1},
            thermal_conductivity={"clarke": 0.9, "cahill": 1.0},
        )
        assert mech.debye_temperature == 385.3
        assert mech.sound_velocity["transverse"] == 2861.7

    def test_dielectric_block_tensor_and_n(self) -> None:
        die = DielectricBlock(
            e_total=15.6,
            dielectric_tensor=[[14.0, 0, 0], [0, 14.0, 0], [0, 0, 18.8]],
            refractive_index_n=2.1,
        )
        assert die.dielectric_tensor[2][2] == 18.8
        assert die.refractive_index_n == 2.1

    def test_structure_block_symmetry_ops_and_coordination(self) -> None:
        s = StructureBlock(
            symmetry_operations_count=192,
            coordination_environment=["Li+: Octahedron"],
            coordination_csm=[0.021],
            coordination_species=["Li+"],
            mineral_prototype="Copper",
        )
        assert s.symmetry_operations_count == 192
        assert s.coordination_csm == [0.021]
        assert s.mineral_prototype == "Copper"

    def test_electronic_average_oxidation_states(self) -> None:
        e = ElectronicBlock(average_oxidation_states={"Li": 1.0, "O": -2.0})
        assert e.average_oxidation_states["Li"] == 1.0

    def test_full_record_round_trip(self) -> None:
        rec = MaterialRecord(
            identity=IdentityProvenance(
                source_db=SourceDB.materials_project,
                source_id="mp-51",
                family=Family.oxide,
                confidence_tier=ConfidenceTier.dft_native,
            ),
            structure=StructureBlock(symmetry_operations_count=192),
            mechanical=MechanicalBlock(debye_temperature=400.0),
            dielectric=DielectricBlock(refractive_index_n=2.0),
        )
        data = rec.model_dump()
        assert data["structure"]["symmetry_operations_count"] == 192
        assert data["mechanical"]["debye_temperature"] == 400.0
        assert data["dielectric"]["refractive_index_n"] == 2.0


class TestExpandMpConsumption:
    """expand_mp.py must consume the enrichment blocks into the record.
    (Importing expand_mp triggers its module-level load_dotenv(); the autouse
    _protect_env fixture restores os.environ after each test.)"""

    def test_load_enrichment_merges_chemenv(self) -> None:
        import json

        from expand_mp import ENRICH_DIR, _load_enrichment

        if not ENRICH_DIR.exists():
            pytest.skip("enrichment dir not present in this checkout")

        p = next(ENRICH_DIR.glob("*.json"), None)
        if p is None:
            pytest.skip("no enrichment files present")
        data = json.loads(p.read_text())
        blocks = data.get("blocks") or {}
        d = {"material_id": data.get("material_id")}
        _load_enrichment(d)
        if "chemenv" in blocks:
            assert "coordination_environment" in d
            assert "coordination_species" in d
        if "dielectric" in blocks:
            assert "dielectric_tensor" in d
        if "elasticity" in blocks:
            assert "debye_temperature" in d
        if "oxidation_states" in blocks:
            assert "average_oxidation_states" in d
        if "robocrys" in blocks:
            assert "mineral_prototype" in d
            assert "dimensionality" in d
        if "bonds" in blocks:
            assert "bond_length_stats" in d
            assert "coordination_number" in d
            assert "bond_types" in d


class TestSynthesisBlock:
    """v0.6.0 — MP synthesis recipe collapse into SynthesisBlock."""

    def test_synthesis_block_fields(self) -> None:
        from ssb_dataset.schema import SynthesisBlock, SynthesisRoute

        s = SynthesisBlock(
            precursors=["Li2CO3", "ZrO2"],
            synthesis_route=[SynthesisRoute.solid_state],
            temperature_C=1253.0,
            time_h=5.0,
            ball_milling=True,
            reaction_string="Li2CO3 + ZrO2 -> LLZO",
            synthesis_doi="10.1016/j.jssc.2009.05.020",
            synthesis_type="solid-state",
        )
        assert s.temperature_C == 1253.0
        assert s.ball_milling is True
        assert s.synthesis_doi == "10.1016/j.jssc.2009.05.020"

    def test_synthesis_from_recipes(self) -> None:
        from expand_mp import _synthesis_from_recipes

        recipes = [
            {
                "temperature_C": 290.0,
                "time_h": 2.0,
                "reaction_string": "Li2S + P2S5 + LiCl",
                "synthesis_doi": "10.1021/acs.jpcc.5b06308",
                "ball_milling": True,
                "annealing": False,
                "synthesis_type": "solid-state",
            }
        ]
        s = _synthesis_from_recipes(recipes)
        assert s.temperature_C == 290.0
        assert s.time_h == 2.0
        assert s.ball_milling is True

    def test_synthesis_from_recipes_empty(self) -> None:
        from expand_mp import _synthesis_from_recipes

        s = _synthesis_from_recipes([])
        assert s.temperature_C is None
        assert s.precursors == []
        assert s.synthesis_route == []


class TestRedoxBlock:
    """v0.6.0 — redox chemistry from possible_species."""

    def test_redox_block_fields(self) -> None:
        from ssb_dataset.schema import RedoxBlock

        r = RedoxBlock(
            redox_active_elements=["Fe"],
            average_oxidation=2.5,
            oxidation_range=1.0,
            mixed_valence=True,
            anion_type=["O"],
            cation_type=["Li", "Fe"],
            electroneutral=True,
        )
        assert r.mixed_valence is True
        assert r.cation_type == ["Li", "Fe"]

    def test_redox_descriptors_no_states(self) -> None:
        from expand_mp import _redox_descriptors

        r = _redox_descriptors({"composition_reduced": "Li2O"}, [])
        assert r.average_oxidation is None
        assert r.mixed_valence is False
        assert r.electroneutral is None


class TestDiscoveryLabels:
    """v0.6.0 — heuristic discovery labels from DFT + family."""

    def test_promising_stable_insulator_electrolyte(self) -> None:
        from expand_mp import _discovery_labels
        from ssb_dataset.sources.classifier import classify_family

        d = {"is_stable": True, "is_metal": False, "band_gap": 4.0}
        family = classify_family("Li7La3Zr2O12")
        lab = _discovery_labels(d, family, sigma_RT=1e-4, Ea=0.4)
        assert lab.is_promising is True
        assert lab.is_fast_ion_conductor is True
        assert lab.is_computational is True

    def test_not_promising_unstable_or_metal(self) -> None:
        from expand_mp import _discovery_labels
        from ssb_dataset.sources.classifier import Family

        d = {"is_stable": False, "is_metal": True, "band_gap": 0.0}
        lab = _discovery_labels(d, Family.unknown, sigma_RT=None, Ea=None)
        assert lab.is_promising is False
        assert lab.is_fast_ion_conductor is False


class TestGraphBlock:
    """v0.6.0 — structure-graph descriptors."""

    def test_graph_block_fields(self) -> None:
        from ssb_dataset.schema import GraphBlock

        g = GraphBlock(
            num_nodes=96,
            num_edges=272,
            average_degree=5.67,
            graph_density=0.06,
            edge_length_mean=2.28,
            edge_length_std=0.25,
            clustering_coefficient=0.0,
            graph_diameter=5,
            connected=True,
        )
        assert g.num_nodes == 96
        assert g.average_degree == 5.67
        assert g.connected is True


class TestTier1CompositionDescriptors:
    """v0.7.0 — Magpie-style composition descriptors (Tier 1/5 gap closure)."""

    def test_chemistry_block_new_fields_default(self) -> None:
        c = ChemistryBlock()
        assert c.weight_fractions == {}
        assert c.atomic_radius_mean is None
        assert c.ionic_radius_mean is None
        assert c.average_atomic_mass is None
        assert c.average_mendeleev_number is None

    def test_chemistry_descriptors_li2o_weighted(self) -> None:
        from expand_mp import _chemistry_descriptors

        d = _chemistry_descriptors({"composition_reduced": "Li2O"})
        assert d.weight_fractions["Li"] == pytest.approx(
            (2 * Element("Li").atomic_mass) /
            (2 * Element("Li").atomic_mass + Element("O").atomic_mass))
        assert sum(d.weight_fractions.values()) == pytest.approx(1.0)
        assert d.average_group == pytest.approx(
            (Element("Li").group * 2 + Element("O").group * 1) / 3)
        assert d.average_mendeleev_number is not None
        assert d.atomic_radius_mean == pytest.approx(
            (Element("Li").atomic_radius * 2 + Element("O").atomic_radius) / 3,
            rel=0.001)

    def test_chemistry_descriptors_absent_formula_still_empty(self) -> None:
        from expand_mp import _chemistry_descriptors

        c = _chemistry_descriptors({"composition_reduced": None})
        assert c.weight_fractions == {}
        assert c.average_atomic_mass is None


class TestTier12StructureTransportProxies:
    """v0.7.0 — packing fraction, nearest-neighbor distance, and Li-sublattice
    transport proxies (Tier 1/2 gap closure)."""

    def test_structure_block_new_fields(self) -> None:
        s = StructureBlock(
            nearest_neighbor_distance=2.42,
            packing_fraction=0.64,
            li_site_count=24,
            li_vacancy_fraction=0.25,
            li_hopping_distance=2.91,
        )
        assert s.li_site_count == 24
        assert s.li_vacancy_fraction == 0.25
        assert s.li_hopping_distance == 2.91
        assert s.nearest_neighbor_distance == 2.42
        assert s.packing_fraction == 0.64

    def test_load_struct_desc_merges_li(self, tmp_path) -> None:
        from expand_mp import _load_struct_desc

        sd = tmp_path / "struct_desc"
        sd.mkdir()
        (sd / "mp-99.json").write_text(
            '{"graph": {"num_nodes": 8}, "local": {"packing_fraction": 0.6},'
            ' "li": {"site_count": 4, "vacancy_fraction": 0.25,'
            ' "hopping_distance": 2.9}}')
        import expand_mp

        orig = expand_mp.STRUCT_DESC_DIR
        expand_mp.STRUCT_DESC_DIR = sd
        try:
            d = {"material_id": "mp-99"}
            _load_struct_desc(d)
            assert d["graph_num_nodes"] == 8
            assert d["local_packing_fraction"] == 0.6
            assert d["li_site_count"] == 4
            assert d["li_vacancy_fraction"] == 0.25
            assert d["li_hopping_distance"] == 2.9
        finally:
            expand_mp.STRUCT_DESC_DIR = orig

    def test_compute_one_li_metal(self, tmp_path) -> None:
        import json

        from pymatgen.core import Structure
        from pymatgen.core.lattice import Lattice

        struct = Structure(
            Lattice.cubic(3.51),
            ["Li", "Li"],
            [[0.0, 0.0, 0.0], [0.5, 0.5, 0.5]],
        )
        (tmp_path / "mp-1.json").write_text(
            '{"material_id": "mp-1", "structure_dict": %s}'
            % json.dumps(struct.as_dict()))
        from compute_structure_descriptors import _compute_one

        mid, out = _compute_one(tmp_path / "mp-1.json")
        assert mid == "mp-1"
        assert out["li"]["site_count"] == 2
        assert out["li"]["vacancy_fraction"] == 0.0
        assert out["li"]["hopping_distance"] == pytest.approx(3.51 * 0.866, rel=0.02)
        assert 0 < out["local"]["packing_fraction"] < 1


class TestPiezoWorkFunction:
    """v0.7.0 — piezoelectric modulus + weighted work function from MP summary."""

    def test_dielectric_block_piezo_fields(self) -> None:
        die = DielectricBlock(
            e_total=12.0,
            piezo_e_ij_max=0.18,
        )
        assert die.piezo_e_ij_max == 0.18

    def test_thermodynamics_weighted_work_function(self) -> None:
        from ssb_dataset.schema import ThermodynamicsBlock

        t = ThermodynamicsBlock(weighted_work_function=4.9)
        assert t.weighted_work_function == 4.9

    def test_fetch_summary_populates_piezo(self) -> None:
        from enrich_mp_api import SUMMARY_FIELDS, _fetch_summary

        assert "e_ij_max" in SUMMARY_FIELDS
        assert "weighted_work_function" in SUMMARY_FIELDS

        class _Doc:
            def model_dump(self):
                return {
                    "material_id": "mp-123",
                    "bulk_modulus": {"vrh": 50.0},
                    "shear_modulus": None,
                    "universal_anisotropy": 1.2,
                    "homogeneous_poisson": 0.3,
                    "weighted_surface_energy": 0.05,
                    "surface_anisotropy": 0.1,
                    "e_ij_max": 0.22,
                    "weighted_work_function": 4.7,
                }

        class _Mpr:
            class materials:
                class summary:
                    @staticmethod
                    def search(material_ids, fields):
                        return [_Doc()]

        out = _fetch_summary(_Mpr(), ["mp-123"])
        assert out["mp-123"]["piezo_e_ij_max"] == 0.22
        assert out["mp-123"]["weighted_work_function"] == 4.7


class TestMobileIonAndHighConductivity:
    """v0.7.0 — Tier 2 mobile_ion + Tier 8 is_high_conductivity label."""

    def test_mobile_ion_li(self) -> None:
        from expand_mp import _mobile_ion

        assert _mobile_ion({"elements": ["Li", "O"]}) == "Li"

    def test_mobile_ion_prefers_alkali_order(self) -> None:
        from expand_mp import _mobile_ion

        assert _mobile_ion({"elements": ["Na", "Li"]}) == "Li"
        assert _mobile_ion({"elements": ["K", "Na"]}) == "Na"
        assert _mobile_ion({"elements": ["Fe", "O"]}) is None

    def test_is_high_conductivity_none_when_unmeasured(self) -> None:
        from expand_mp import _discovery_labels
        from ssb_dataset.sources.classifier import Family

        lab = _discovery_labels({"is_stable": True}, Family.oxide,
                                sigma_RT=None, Ea=None)
        assert lab.is_high_conductivity is None

    def test_is_high_conductivity_true_above_threshold(self) -> None:
        from expand_mp import _discovery_labels
        from ssb_dataset.sources.classifier import Family

        lab = _discovery_labels({"is_stable": True}, Family.oxide,
                                sigma_RT=1e-3, Ea=0.3)
        assert lab.is_high_conductivity is True

    def test_is_high_conductivity_false_below_threshold(self) -> None:
        from expand_mp import _discovery_labels
        from ssb_dataset.sources.classifier import Family

        lab = _discovery_labels({"is_stable": True}, Family.oxide,
                                sigma_RT=1e-6, Ea=0.7)
        assert lab.is_high_conductivity is False

    def test_ion_transport_mobile_ion_schema(self) -> None:
        from ssb_dataset.schema import IonTransportBlock

        t = IonTransportBlock(mobile_ion="Li")
        assert t.mobile_ion == "Li"

