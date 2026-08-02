"""Pydantic models matching the unified schema spec (Section 2 of the build guide)."""

from __future__ import annotations

from datetime import datetime, timezone
from enum import Enum
from typing import Any

from pydantic import BaseModel, Field


class SourceDB(str, Enum):
    materials_project = "materials_project"
    jarvis = "jarvis"
    oqmd = "oqmd"
    aflow = "aflow"
    icsd = "icsd"
    cod = "cod"
    nomad = "nomad"
    literature_mined = "literature_mined"
    scandium_computed = "scandium_computed"


class Family(str, Enum):
    sulfide = "sulfide"
    oxide = "oxide"
    garnet = "garnet"
    perovskite = "perovskite"
    nasicon = "nasicon"
    halide = "halide"
    argyrodite = "argyrodite"
    hydride = "hydride"
    borohydride = "borohydride"
    antiperovskite = "antiperovskite"
    polymer_composite = "polymer_composite"
    unknown = "unknown"


class ConfidenceTier(str, Enum):
    verified_human = "verified_human"
    high_confidence_extraction = "high_confidence_extraction"
    low_confidence_extraction = "low_confidence_extraction"
    dft_native = "dft_native"
    dft_computed_inhouse = "dft_computed_inhouse"


class StructureType(str, Enum):
    ordered = "ordered"
    disordered = "disordered"
    amorphous = "amorphous"
    semi_crystalline = "semi_crystalline"


class ConductivityType(str, Enum):
    bulk = "bulk"
    grain_boundary = "grain_boundary"
    total = "total"


class ConductivitySourceType(str, Enum):
    measured = "measured"
    aimd_computed = "aimd_computed"
    neb_computed = "neb_computed"
    predicted_empirical = "predicted_empirical"


class Functional(str, Enum):
    pbe = "PBE"
    pbe_plus_u = "PBE+U"
    scan = "SCAN"
    hse06 = "HSE06"
    r2scan = "r2SCAN"


class SynthesisRoute(str, Enum):
    solid_state = "solid_state"
    sol_gel = "sol_gel"
    mechanochemical = "mechanochemical"
    melt_quench = "melt_quench"
    co_precipitation = "co_precipitation"


class ExtractionMethod(str, Enum):
    manual = "manual"
    human_curated = "human_curated"
    grobid_table_parse = "grobid_table_parse"
    llm_extraction = "llm_extraction"


class SplitAssignment(str, Enum):
    train = "train"
    val = "val"
    test = "test"
    gold_benchmark = "gold_benchmark"


class LatticeParams(BaseModel):
    a: float
    b: float
    c: float
    alpha: float
    beta: float
    gamma: float


class ElectrochemicalStabilityWindow(BaseModel):
    lower_V: float | None = None
    upper_V: float | None = None


class ConductivityPoint(BaseModel):
    temperature_K: float
    conductivity_S_per_cm: float


class TemperatureRange(BaseModel):
    min_K: float
    max_K: float


class IdentityProvenance(BaseModel):
    material_id: str = ""
    source_db: SourceDB
    source_id: str
    composition: str = ""
    family: Family
    subfamily_tag: list[str] = Field(default_factory=list)
    ingestion_date: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    schema_version: str = "0.1.0"
    confidence_tier: ConfidenceTier


class StructureBlock(BaseModel):
    structure_relaxed: str | None = None
    structure_unrelaxed: str | None = None
    space_group: str | None = None
    space_group_number: int | None = None
    crystal_system: str | None = None
    point_group: str | None = None
    density: float | None = None
    density_atomic: float | None = None
    volume: float | None = None
    nsites: int | None = None
    lattice_params: LatticeParams | None = None
    li_site_occupancy: list[float] = Field(default_factory=list)
    coordination_environment: list[str] = Field(default_factory=list)
    structure_type: StructureType = StructureType.ordered
    is_experimental_structure: bool = False


class ThermodynamicsBlock(BaseModel):
    formation_energy_per_atom: float | None = None
    energy_above_hull: float | None = None
    is_stable: bool | None = None
    equilibrium_reaction_energy_per_atom: float | None = None
    band_gap: float | None = None
    cbm: float | None = None
    vbm: float | None = None
    efermi: float | None = None
    is_gap_direct: bool | None = None
    is_metal: bool | None = None
    decomposition_products: list[str] = Field(default_factory=list)
    electrochemical_stability_window: ElectrochemicalStabilityWindow | None = None
    functional_used: Functional | None = None


class MagneticBlock(BaseModel):
    is_magnetic: bool | None = None
    ordering: str | None = None
    total_magnetization: float | None = None
    total_magnetization_normalized_vol: float | None = None
    total_magnetization_normalized_formula_units: float | None = None
    num_magnetic_sites: int | None = None
    num_unique_magnetic_sites: int | None = None
    types_of_magnetic_species: list[str] = Field(default_factory=list)


class ElectronicBlock(BaseModel):
    possible_species: list[str] = Field(default_factory=list)
    oxidation_states: list[int] = Field(default_factory=list)


class IonTransportBlock(BaseModel):
    sigma_RT: float | None = None
    sigma_vs_T_curve: list[ConductivityPoint] = Field(default_factory=list)
    activation_energy_Ea: float | None = None
    conductivity_type: ConductivityType | None = None
    conductivity_source_type: ConductivitySourceType | None = None
    measurement_method: str | None = None
    temperature_range_measured: TemperatureRange | None = None
    label_available: bool = False


class MechanicalBlock(BaseModel):
    bulk_modulus: float | None = None
    shear_modulus: float | None = None
    elastic_tensor: list[list[float]] | None = None


class SynthesisBlock(BaseModel):
    precursors: list[str] = Field(default_factory=list)
    synthesis_route: list[SynthesisRoute] = Field(default_factory=list)
    synthesis_atmosphere: str | None = None
    requires_interlayer: bool | None = None
    processing_metadata: dict[str, Any] | None = None


class ExperimentBlock(BaseModel):
    """Measurement-condition metadata (M6) — the conditions under which an
    ionic-conductivity value was measured. Two papers reporting different σ for
    the same material are usually measuring under different conditions; these
    fields capture why. Preserved per-record so consensus can be filtered
    temperature/condition-aware.
    """
    sample_form: str | None = None
    pellet_diameter_mm: float | None = None
    thickness_mm: float | None = None
    relative_density_pct: float | None = None
    theoretical_density_g_per_cm3: float | None = None
    pellet_density_g_per_cm3: float | None = None
    pelletizing_pressure_MPa: float | None = None
    electrode_material: str | None = None
    electrode_deposition: str | None = None
    frequency_min_Hz: float | None = None
    frequency_max_Hz: float | None = None
    atmosphere: str | None = None
    humidity: str | None = None
    measurement_method: str | None = None
    conductivity_type: str | None = None
    heating_rate_C_per_min: float | None = None
    cooling_rate_C_per_min: float | None = None
    sinter_temperature_C: float | None = None
    sinter_time_h: float | None = None
    annealing_temperature_C: float | None = None
    annealing_time_h: float | None = None
    instrument: str | None = None
    equivalent_circuit: str | None = None
    dc_bias_V: float | None = None
    notes: str | None = None


class MLFeaturesBlock(BaseModel):
    graph_representation: Any = None
    composition_descriptors: dict[str, float] | None = None
    symmetry_descriptors: dict[str, float] | None = None
    split_assignment: SplitAssignment | None = None
    split_group_key: str = ""


class TextProvenanceBlock(BaseModel):
    """A2 — full evidence/source chain. Every experimental value must link back
    to a specific, verifiable location in the source paper: DOI -> PDF -> page
    -> section/table/figure -> sentence. Fields mirror the roadmap's `source`
    block so any record is reproducible from its provenance alone.
    """
    source_doi: str | None = None
    source_paper_title: str | None = None
    source_journal: str | None = None
    source_year: int | None = None
    pdf_path: str | None = None
    extraction_method: ExtractionMethod | None = None
    extraction_confidence_score: float | None = None
    extraction_reviewer: str | None = None
    evidence_page: str | int | None = None
    evidence_section: str | None = None
    evidence_table_number: str | int | None = None
    evidence_figure_number: str | int | None = None
    evidence_paragraph: str | None = None
    evidence_sentence: str | None = None


class MaterialRecord(BaseModel):
    identity: IdentityProvenance
    structure: StructureBlock = Field(default_factory=StructureBlock)
    thermodynamics: ThermodynamicsBlock = Field(default_factory=ThermodynamicsBlock)
    magnetic: MagneticBlock = Field(default_factory=MagneticBlock)
    electronic: ElectronicBlock = Field(default_factory=ElectronicBlock)
    ion_transport: IonTransportBlock = Field(default_factory=IonTransportBlock)
    mechanical: MechanicalBlock = Field(default_factory=MechanicalBlock)
    synthesis: SynthesisBlock = Field(default_factory=SynthesisBlock)
    experiment: ExperimentBlock = Field(default_factory=ExperimentBlock)
    ml_features: MLFeaturesBlock = Field(default_factory=MLFeaturesBlock)
    text_provenance: TextProvenanceBlock = Field(default_factory=TextProvenanceBlock)
