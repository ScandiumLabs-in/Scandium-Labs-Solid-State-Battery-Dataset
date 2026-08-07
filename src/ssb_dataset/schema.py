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
    materials_cloud = "materials_cloud"
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
    plot_digitized = "plot_digitized"


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
    is_electrolyte_candidate: bool = True
    ingestion_date: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    schema_version: str = "0.1.0"
    confidence_tier: ConfidenceTier
    # Layer 1 — Materials Project identity (MP summary API)
    formula_pretty: str | None = None
    formula_anonymous: str | None = None
    chemsys: str | None = None
    elements: list[str] = Field(default_factory=list)
    nelements: int | None = None
    database_ids: list[str] = Field(default_factory=list)   # ICSD etc.
    reduced_formula: str | None = None


class StructureBlock(BaseModel):
    structure_relaxed: str | None = None
    structure_unrelaxed: str | None = None
    space_group: str | None = None
    space_group_number: int | None = None
    crystal_system: str | None = None
    point_group: str | None = None
    symmetry_operations_count: int | None = None
    density: float | None = None
    density_atomic: float | None = None
    volume: float | None = None
    nsites: int | None = None
    lattice_params: LatticeParams | None = None
    li_site_occupancy: list[float] = Field(default_factory=list)
    coordination_environment: list[str] = Field(default_factory=list)
    coordination_csm: list[float] = Field(default_factory=list)
    coordination_species: list[str] = Field(default_factory=list)
    # Layer 8 — Robocrystallographer structural descriptors
    robocrys_description: str | None = None
    mineral_prototype: str | None = None
    packing_fraction: float | None = None
    # Layer 8 — MP bonds endpoint descriptors
    bond_length_stats: dict[str, float] | None = None    # {min,max,mean,variance}
    bond_types: dict[str, list[float]] = Field(default_factory=dict)
    coordination_number: float | None = None
    dimensionality: int | None = None
    # Section 5 — local environment geometry (CrystalNN-derived)
    polyhedron_volume: float | None = None
    polyhedron_distortion: float | None = None
    bond_angle_variance: float | None = None
    tetrahedrality: float | None = None
    octahedrality: float | None = None
    mean_neighbor_distance: float | None = None
    neighbor_species_distribution: dict[str, float] = Field(default_factory=dict)
    # Tier 1/2 — structure-derived transport proxies (CrystalNN / Li sublattice)
    nearest_neighbor_distance: float | None = None
    packing_fraction: float | None = None
    li_site_count: int | None = None
    li_vacancy_fraction: float | None = None
    li_hopping_distance: float | None = None
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
    # Layer 10 — battery-relevant surface properties (MP summary API)
    weighted_surface_energy: float | None = None
    surface_anisotropy: float | None = None
    weighted_work_function: float | None = None
    total_energy: float | None = None
    energy_per_atom: float | None = None


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
    # Layer 7 — chemistry descriptors (MP oxidation_states / summary endpoints)
    average_oxidation_states: dict[str, float] | None = None


class ChemistryBlock(BaseModel):
    """Layer 7 — composition-derived chemistry descriptors. Computed
    deterministically from the reduced composition (pymatgen), so coverage is
    full for every record that carries a formula (no MP endpoint needed)."""
    electronegativity_mean: float | None = None
    electronegativity_max: float | None = None
    electronegativity_min: float | None = None
    electronegativity_std: float | None = None
    valence_electron_count: float | None = None
    atomic_fractions: dict[str, float] = Field(default_factory=dict)
    elemental_fractions: dict[str, float] = Field(default_factory=dict)
    # Tier 1/5 — Magpie-style composition descriptors (weighted, deterministic)
    weight_fractions: dict[str, float] = Field(default_factory=dict)
    atomic_radius_mean: float | None = None
    atomic_radius_std: float | None = None
    ionic_radius_mean: float | None = None
    ionic_radius_std: float | None = None
    average_atomic_mass: float | None = None
    average_group: float | None = None
    average_period: float | None = None
    average_mendeleev_number: float | None = None


class RedoxBlock(BaseModel):
    """Section 7 — oxidation chemistry descriptors, derived deterministically
    from composition + oxidation states. Useful for battery chemistry."""
    redox_active_elements: list[str] = Field(default_factory=list)
    average_oxidation: float | None = None
    oxidation_range: float | None = None
    mixed_valence: bool = False
    anion_type: list[str] = Field(default_factory=list)
    cation_type: list[str] = Field(default_factory=list)
    electroneutral: bool | None = None


class GraphBlock(BaseModel):
    """Section 5/6 — precomputed structure-graph statistics (CrystalNN).
    Precomputed so downstream models don't rebuild the graph per record."""
    num_nodes: int | None = None
    num_edges: int | None = None
    average_degree: float | None = None
    graph_density: float | None = None
    edge_length_mean: float | None = None
    edge_length_std: float | None = None
    clustering_coefficient: float | None = None
    graph_diameter: int | None = None
    connected: bool | None = None


class DiscoveryLabelsBlock(BaseModel):
    """Section 10 — dataset-curated labels for ranking/retrieval/recommendation
    models. Deterministic heuristics over the record's own fields."""
    is_good_ssb: bool | None = None
    is_promising: bool | None = None
    is_fast_ion_conductor: bool | None = None
    is_high_conductivity: bool | None = None
    is_experimental: bool = False
    is_computational: bool = False
    is_verified: bool = False
    confidence_score: float | None = None
    novelty_score: float | None = None


class ValidationBlock(BaseModel):
    """Phase A (v1.4) — cross-database scientific validation.

    Per-record agreement between independent databases (Materials Project,
    JARVIS-DFT, NOMAD, COD, ...) for overlapping materials. Computed
    deterministically by ``scripts/run_cross_db_validation.py`` over the
    shared reduced-formula key: for each formula present in >= 2 sources, the
    record's properties are compared across sources and the agreement is
    summarized here. NaN/missing properties never count as disagreement.
    """
    database_count: int = 0
    agreement_score: float | None = None
    disagreement: dict[str, dict[str, float]] = Field(default_factory=dict)
    rank: int | None = None


class NegativeResultBlock(BaseModel):
    """Phase C (v1.5) — negative results database.

    Deterministic anti-survivorship-bias labels: records flagged here are
    materials the DFT evidence says are POOR solid-electrolyte candidates,
    not quiet omissions. Every flag carries its evidence so a downstream
    consumer can reason about *why* a material is negative. Flags are only
    ever set when the underlying signal is actually present — a record with
    no computable signal keeps is_negative_result=None (unknown), never a
    fabricated False.

    Signals (each deterministic over on-disk MP columns):
      - thermodynamically_unstable: energy_above_hull > 0.025 eV/atom
      - electronic_conductor: is_metal True or band_gap == 0 (a metal cannot
        be a pure electrolyte — it shorts the cell electronically)
      - poor_li_transport_proxy: li_hopping_distance > 4.5 Å (no connected
        Li sublattice path; medium confidence, it is a proxy)
    """
    is_negative_result: bool | None = None
    reasons: list[str] = Field(default_factory=list)
    evidence: dict[str, float] = Field(default_factory=dict)
    confidence: str | None = None  # high / medium
    # the three raw signals, kept so consumers can re-threshold
    energy_above_hull_eV_atom: float | None = None
    is_metal: bool | None = None
    band_gap_eV: float | None = None
    li_hopping_distance_A: float | None = None


class IonTransportBlock(BaseModel):
    sigma_RT: float | None = None
    sigma_vs_T_curve: list[ConductivityPoint] = Field(default_factory=list)
    activation_energy_Ea: float | None = None
    conductivity_type: ConductivityType | None = None
    conductivity_source_type: ConductivitySourceType | None = None
    measurement_method: str | None = None
    temperature_range_measured: TemperatureRange | None = None
    label_available: bool = False
    # Tier 2 — mobile-ion species (derived from composition; Li/Na/Mg/Al/etc.)
    mobile_ion: str | None = None


class MechanicalBlock(BaseModel):
    bulk_modulus: float | None = None
    shear_modulus: float | None = None
    youngs_modulus: float | None = None
    homogeneous_poisson: float | None = None
    universal_anisotropy: float | None = None
    elastic_tensor: list[list[float]] | None = None
    compliance_tensor: list[list[float]] | None = None
    debye_temperature: float | None = None
    sound_velocity: dict[str, float] | None = None
    thermal_conductivity: dict[str, float] | None = None


class DielectricBlock(BaseModel):
    """Layer 6 — dielectric response (MP dielectric endpoint) + piezoelectric
    modulus (MP summary e_ij_max)."""
    e_total: float | None = None
    e_electronic: float | None = None
    e_ionic: float | None = None
    dielectric_tensor: list[list[float]] | None = None
    refractive_index_n: float | None = None
    # Tier 1 — piezoelectric response (max piezoelectric modulus)
    piezo_e_ij_max: float | None = None


class SynthesisBlock(BaseModel):
    """Layer/section 2 — synthesis conditions. The MP `synthesis` endpoint
    (SynthesisRecipe) is the computational source; literature extraction
    populates the same fields from papers."""
    precursors: list[str] = Field(default_factory=list)
    synthesis_route: list[SynthesisRoute] = Field(default_factory=list)
    synthesis_atmosphere: str | None = None
    requires_interlayer: bool | None = None
    processing_metadata: dict[str, Any] | None = None
    # MP synthesis recipe / paper-derived conditions
    temperature_C: float | None = None
    time_h: float | None = None
    pressure_atm: float | None = None
    atmosphere: str | None = None
    cooling_rate_C_per_min: float | None = None
    heating_rate_C_per_min: float | None = None
    calcination: bool = False
    annealing: bool = False
    ball_milling: bool = False
    sintering: bool = False
    hot_pressing: bool = False
    spark_plasma_sintering: bool = False
    sol_gel: bool = False
    solid_state: bool = False
    mechanochemical: bool = False
    reaction_string: str | None = None
    synthesis_doi: str | None = None
    synthesis_type: str | None = None


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
    # Section 3 — expanded experimental / electrochemical metadata
    grain_size_um: float | None = None
    porosity_pct: float | None = None
    electrolyte_thickness_mm: float | None = None
    electrolyte_area_cm2: float | None = None
    current_density_mA_per_cm2: float | None = None
    cell_configuration: str | None = None
    electrochemical_window_V: str | None = None
    critical_current_density_mA_per_cm2: float | None = None
    cycling_stability: str | None = None
    sigma_60C_S_per_cm: float | None = None
    sigma_80C_S_per_cm: float | None = None


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
    ensemble_votes: int | None = None
    ensemble_size: int | None = None
    sigma_spread_frac: float | None = None
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
    chemistry: ChemistryBlock = Field(default_factory=ChemistryBlock)
    redox: RedoxBlock = Field(default_factory=RedoxBlock)
    ion_transport: IonTransportBlock = Field(default_factory=IonTransportBlock)
    mechanical: MechanicalBlock = Field(default_factory=MechanicalBlock)
    dielectric: DielectricBlock = Field(default_factory=DielectricBlock)
    synthesis: SynthesisBlock = Field(default_factory=SynthesisBlock)
    experiment: ExperimentBlock = Field(default_factory=ExperimentBlock)
    graph: GraphBlock = Field(default_factory=GraphBlock)
    discovery_labels: DiscoveryLabelsBlock = Field(default_factory=DiscoveryLabelsBlock)
    validation: ValidationBlock = Field(default_factory=ValidationBlock)
    negative_result: NegativeResultBlock = Field(default_factory=NegativeResultBlock)
    ml_features: MLFeaturesBlock = Field(default_factory=MLFeaturesBlock)
    text_provenance: TextProvenanceBlock = Field(default_factory=TextProvenanceBlock)
