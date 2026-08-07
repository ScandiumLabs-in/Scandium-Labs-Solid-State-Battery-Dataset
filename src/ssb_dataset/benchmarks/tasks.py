"""Task registry for the Scandium Benchmark Suite (v0.8.0 → v1.9.0, 25 tasks).

Every task is a declarative definition: which column(s) to predict, the task
type (regression / classification / ranking), the primary metric(s), and which
columns are *leaky* (derived from the target and therefore excluded from the
model features). Task labels are real dataset columns — most tasks cover the
full MP-derived catalog; the scarce literature-verified ion-transport tasks
(σ_RT, Ea) use the dataset's most valuable rows.

Leaky-column discipline: for volume regression, density must be excluded
(density = mass/volume); for band-gap targets, cbm/vbm/is_metal are excluded;
for stability, energy_above_hull is excluded. Same rule applied to every task.
v1.9.0 extends the discipline to whole derived property blocks: each mechanical
task excludes the sibling elastic/vibrational columns (all come from the same
elastic-tensor computation), the magnetic task excludes the other magnetic
descriptors, electroneutral excludes the redox/oxidation descriptors that
define it, and the packing-fraction task excludes density/volume (packing is a
direct function of cell volume + atomic radii). `label_bounds` is a documented
label-plausibility gate (same spirit as the unit audit): mechanical values
outside physical windows are excluded rather than fed to the model as garbage.
"""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np
import pandas as pd


@dataclass(frozen=True)
class BenchmarkTask:
    id: str
    name: str
    description: str
    task_type: str                       # regression | classification | ranking
    target: str                          # canonical column to predict
    metric: str                          # primary metric (leaderboard sort)
    leaky_cols: tuple[str, ...] = ()     # columns excluded from features
    threshold: float | None = None       # binary split point for numeric targets
    better: str = "lower"                # ranking direction (lower/higher)
    transform: str = "none"              # none | log10 (pre-log of the target)
    label_bounds: tuple[float, float] | None = None  # plausibility window on
    # the target (label-quality gate — rows outside are excluded, never imputed)
    doc_metrics: tuple[str, ...] = ()    # secondary metrics (report only)

    def label_mask(self, df: pd.DataFrame) -> pd.Series:
        """Boolean mask of rows that carry a usable label for this task."""
        if self.task_type == "classification" and self.threshold is not None:
            m = df[self.target].notna() & (df[self.target] != 0)
        elif self.transform == "log10":
            m = df[self.target].notna() & (df[self.target] > 0)
        else:
            m = df[self.target].notna()
        if self.label_bounds is not None:
            s = pd.to_numeric(df[self.target], errors="coerce")
            lo, hi = self.label_bounds
            m = m & s.between(lo, hi)
        return m

    def extract_y(self, df: pd.DataFrame) -> pd.Series:
        """Return the numeric label series for a task (drops rows without one)."""
        m = self.label_mask(df)
        if self.task_type == "classification" and self.threshold is not None:
            return (df.loc[m, self.target] >= self.threshold).astype(int)
        y = df.loc[m, self.target]
        if self.transform == "log10":
            y = pd.to_numeric(y, errors="coerce")
            y = y.mask(y <= 0).map(lambda v: np.log10(v) if v is not None else None)
        return y


# The canonical-feature set is derived in the evaluator (all deterministic
# numeric columns minus identity/provenance, minus target + leaky columns). The
# leaky lists below are the hand-audited exceptions per task.

BENCHMARK_TASKS: tuple[BenchmarkTask, ...] = (
    BenchmarkTask(
        id="formation_energy_regression",
        name="Formation energy regression",
        description="Predict formation energy per atom (eV/atom) from "
                    "composition + structure descriptors.",
        task_type="regression",
        target="thermodynamics.formation_energy_per_atom",
        metric="mae",
        doc_metrics=("rmse", "r2"),
        leaky_cols=("thermodynamics.total_energy",
                    "thermodynamics.energy_per_atom",
                    "thermodynamics.equilibrium_reaction_energy_per_atom",
                    "thermodynamics.decomposition_products"),
    ),
    BenchmarkTask(
        id="band_gap_regression",
        name="Band gap regression",
        description="Predict the PBE band gap (eV) from composition + "
                    "structure descriptors.",
        task_type="regression",
        target="thermodynamics.band_gap",
        metric="mae",
        doc_metrics=("rmse", "r2"),
        leaky_cols=("thermodynamics.cbm", "thermodynamics.vbm",
                    "thermodynamics.efermi", "thermodynamics.is_metal",
                    "thermodynamics.is_gap_direct"),
    ),
    BenchmarkTask(
        id="energy_above_hull_regression",
        name="Energy above hull regression",
        description="Predict the energy above hull (eV/atom) from "
                    "composition + structure descriptors.",
        task_type="regression",
        target="thermodynamics.energy_above_hull",
        metric="mae",
        doc_metrics=("rmse", "r2"),
        leaky_cols=("thermodynamics.is_stable",
                    "thermodynamics.equilibrium_reaction_energy_per_atom",
                    "thermodynamics.decomposition_products"),
    ),
    BenchmarkTask(
        id="bulk_modulus_regression",
        name="Bulk modulus regression",
        description="Predict the bulk modulus K (GPa) from composition + "
                    "structure descriptors. The sibling elastic/vibrational "
                    "columns (shear modulus, Poisson ratio, anisotropy, Debye "
                    "temperature) are excluded — they come from the same "
                    "elastic-tensor computation. Labels outside the physical "
                    "1–1000 GPa window are excluded (MP returns unphysical "
                    "extremes for a few entries), never imputed.",
        task_type="regression",
        target="mechanical.bulk_modulus",
        metric="mae",
        doc_metrics=("rmse", "r2"),
        label_bounds=(1.0, 1000.0),
        leaky_cols=("mechanical.shear_modulus",
                    "mechanical.homogeneous_poisson",
                    "mechanical.universal_anisotropy",
                    "mechanical.debye_temperature"),
    ),
    BenchmarkTask(
        id="shear_modulus_regression",
        name="Shear modulus regression",
        description="Predict the shear modulus G (GPa) from composition + "
                    "structure descriptors. Sibling elastic/vibrational "
                    "columns are excluded. Labels outside the physical "
                    "1–1000 GPa window are excluded, never imputed.",
        task_type="regression",
        target="mechanical.shear_modulus",
        metric="mae",
        doc_metrics=("rmse", "r2"),
        label_bounds=(1.0, 1000.0),
        leaky_cols=("mechanical.bulk_modulus",
                    "mechanical.homogeneous_poisson",
                    "mechanical.universal_anisotropy",
                    "mechanical.debye_temperature"),
    ),
    BenchmarkTask(
        id="debye_temperature_regression",
        name="Debye temperature regression",
        description="Predict the Debye temperature (K) from composition + "
                    "structure descriptors. Sibling elastic/vibrational "
                    "columns are excluded (θ_D is computed from the sound "
                    "velocities / elastic moduli). Labels outside the "
                    "physical 50–3000 K window are excluded, never imputed.",
        task_type="regression",
        target="mechanical.debye_temperature",
        metric="mae",
        doc_metrics=("rmse", "r2"),
        label_bounds=(50.0, 3000.0),
        leaky_cols=("mechanical.bulk_modulus",
                    "mechanical.shear_modulus",
                    "mechanical.homogeneous_poisson",
                    "mechanical.universal_anisotropy"),
    ),
    BenchmarkTask(
        id="density_regression",
        name="Density regression",
        description="Predict the mass density (g/cm³) from composition + "
                    "structure descriptors.",
        task_type="regression",
        target="structure.density",
        metric="mae",
        doc_metrics=("rmse", "r2"),
        leaky_cols=("structure.volume", "structure.density_atomic"),
    ),
    BenchmarkTask(
        id="volume_regression",
        name="Volume regression",
        description="Predict the unit-cell volume (Å³) from composition + "
                    "structure descriptors. Density is excluded (derived "
                    "from mass/volume — a direct leak).",
        task_type="regression",
        target="structure.volume",
        metric="mae",
        doc_metrics=("rmse", "r2"),
        leaky_cols=("structure.density", "structure.density_atomic",
                    "structure.lattice_params"),
    ),
    BenchmarkTask(
        id="ionic_radius_regression",
        name="Ionic-radius regression",
        description="Predict the composition-weighted mean Shannon ionic "
                    "radius (Å) from elemental composition descriptors.",
        task_type="regression",
        target="chemistry.ionic_radius_mean",
        metric="mae",
        doc_metrics=("rmse", "r2"),
    ),
    BenchmarkTask(
        id="stability_classification",
        name="Stable vs unstable classification",
        description="Classify MP is_stable from composition + structure "
                    "descriptors. Energy above hull is excluded (it defines "
                    "the label).",
        task_type="classification",
        target="thermodynamics.is_stable",
        metric="macro_f1",
        doc_metrics=("accuracy", "roc_auc"),
        leaky_cols=("thermodynamics.energy_above_hull",
                    "thermodynamics.equilibrium_reaction_energy_per_atom"),
    ),
    BenchmarkTask(
        id="wide_gap_classification",
        name="Wide-gap classification (E_g > 4 eV)",
        description="Classify materials as wide-gap (band gap > 4 eV) or not. "
                    "Electronic band-structure fields are excluded (they "
                    "define the label).",
        task_type="classification",
        target="thermodynamics.band_gap",
        metric="macro_f1",
        doc_metrics=("accuracy", "roc_auc"),
        threshold=4.0,
        leaky_cols=("thermodynamics.cbm", "thermodynamics.vbm",
                    "thermodynamics.efermi", "thermodynamics.is_metal",
                    "thermodynamics.is_gap_direct"),
    ),
    BenchmarkTask(
        id="family_classification",
        name="Family classification",
        description="Predict the electrolyte family (12 classes) from "
                    "composition + structure descriptors.",
        task_type="classification",
        target="identity.family",
        metric="macro_f1",
        doc_metrics=("accuracy",),
    ),
    BenchmarkTask(
        id="crystal_system_classification",
        name="Crystal system prediction",
        description="Predict the crystal system (7 classes) from composition "
                    "descriptors. Space-group fields are excluded (they "
                    "define the label).",
        task_type="classification",
        target="structure.crystal_system",
        metric="macro_f1",
        doc_metrics=("accuracy",),
        leaky_cols=("structure.space_group_number",
                    "structure.symmetry_operations_count"),
    ),
    BenchmarkTask(
        id="space_group_classification",
        name="Space group prediction",
        description="Predict the space group (194 classes in the catalog) "
                    "from composition descriptors. Crystal-system and "
                    "symmetry-count fields are excluded.",
        task_type="classification",
        target="structure.space_group_number",
        metric="top5_accuracy",
        doc_metrics=("accuracy", "macro_f1"),
        leaky_cols=("structure.crystal_system",
                    "structure.symmetry_operations_count"),
    ),
    BenchmarkTask(
        id="conductive_candidate_ranking",
        name="Conductive-candidate ranking",
        description="Rank materials by measured room-temperature ionic "
                    "conductivity (log10 σ_RT, S/cm) from composition + "
                    "structure descriptors only. Uses the scarce "
                    "literature-verified subset (σ_RT labeled rows); "
                    "measurement-condition fields are excluded.",
        task_type="ranking",
        target="ion_transport.sigma_RT",
        metric="ndcg10",
        doc_metrics=("spearman",),
        better="higher",
        transform="log10",
        leaky_cols=("ion_transport.activation_energy_Ea",
                    "ion_transport.conductivity_type",
                    "ion_transport.conductivity_source_type",
                    "ion_transport.measurement_method",
                    "ion_transport.temperature_range_measured"),
    ),
    BenchmarkTask(
        id="negative_result_classification",
        name="Negative-result (poor electrolyte) classification",
        description="Predict whether a material is a poor solid-electrolyte "
                    "candidate (negative.is_negative_result) from composition "
                    "+ structure descriptors only. The signals that DEFINE "
                    "the label are excluded (energy above hull, band gap, "
                    "is_metal, Li-hop distance) so the model must learn the "
                    "chemistry itself — the anti-survivorship-bias task.",
        task_type="classification",
        target="negative.is_negative_result",
        metric="macro_f1",
        doc_metrics=("accuracy", "roc_auc"),
        leaky_cols=("thermodynamics.energy_above_hull",
                    "thermodynamics.is_metal", "thermodynamics.band_gap",
                    "thermodynamics.cbm", "thermodynamics.vbm",
                    "thermodynamics.efermi", "thermodynamics.is_gap_direct",
                    "structure.li_hopping_distance"),
    ),
    BenchmarkTask(
        id="metallic_classification",
        name="Metallic vs insulating classification",
        description="Predict is_metal from composition + structure "
                    "descriptors. Band-structure fields are excluded (they "
                    "define the label).",
        task_type="classification",
        target="thermodynamics.is_metal",
        metric="macro_f1",
        doc_metrics=("accuracy", "roc_auc"),
        leaky_cols=("thermodynamics.band_gap", "thermodynamics.cbm",
                    "thermodynamics.vbm", "thermodynamics.efermi",
                    "thermodynamics.is_gap_direct"),
    ),
    BenchmarkTask(
        id="high_conductivity_classification",
        name="High-conductivity classification (σ_RT > 10⁻³ S/cm)",
        description="Classify materials as high-conductivity (measured σ_RT "
                    "> 10⁻³ S/cm) from composition + structure descriptors. "
                    "Uses the scarce literature-verified subset; "
                    "measurement-condition fields are excluded.",
        task_type="classification",
        target="ion_transport.sigma_RT",
        metric="macro_f1",
        doc_metrics=("accuracy", "roc_auc"),
        threshold=1e-3,
        leaky_cols=("ion_transport.activation_energy_Ea",
                    "ion_transport.conductivity_type",
                    "ion_transport.conductivity_source_type",
                    "ion_transport.measurement_method",
                    "ion_transport.temperature_range_measured"),
    ),
    BenchmarkTask(
        id="activation_energy_regression",
        name="Activation energy regression",
        description="Predict the measured activation energy Ea (eV) from "
                    "composition + structure descriptors. Uses the scarce "
                    "literature-verified subset (Ea-labeled rows); the "
                    "sibling σ_RT label and all measurement-condition fields "
                    "are excluded.",
        task_type="regression",
        target="ion_transport.activation_energy_Ea",
        metric="mae",
        doc_metrics=("rmse", "r2"),
        leaky_cols=("ion_transport.sigma_RT",
                    "ion_transport.conductivity_type",
                    "ion_transport.conductivity_source_type",
                    "ion_transport.measurement_method",
                    "ion_transport.temperature_range_measured"),
    ),
    BenchmarkTask(
        id="sigma_RT_regression",
        name="Conductivity magnitude regression",
        description="Predict the measured room-temperature ionic "
                    "conductivity (log10 σ_RT, S/cm) from composition + "
                    "structure descriptors. Complements the ranking task: "
                    "this measures how well a model estimates the *magnitude* "
                    "of conductivity, not just the ordering. Uses the scarce "
                    "literature-verified subset; sibling Ea and "
                    "measurement-condition fields are excluded.",
        task_type="regression",
        target="ion_transport.sigma_RT",
        metric="mae",
        doc_metrics=("rmse", "r2"),
        transform="log10",
        leaky_cols=("ion_transport.activation_energy_Ea",
                    "ion_transport.conductivity_type",
                    "ion_transport.conductivity_source_type",
                    "ion_transport.measurement_method",
                    "ion_transport.temperature_range_measured"),
    ),
    BenchmarkTask(
        id="is_magnetic_classification",
        name="Magnetic vs non-magnetic classification",
        description="Predict whether a material is magnetic (magnetic."
                    "is_magnetic) from composition + structure descriptors. "
                    "All other magnetic descriptors (ordering, magnetization, "
                    "magnetic-site counts) are excluded — they describe the "
                    "same computed result that defines the label.",
        task_type="classification",
        target="magnetic.is_magnetic",
        metric="macro_f1",
        doc_metrics=("accuracy", "roc_auc"),
        leaky_cols=("magnetic.ordering", "magnetic.total_magnetization",
                    "magnetic.total_magnetization_normalized_vol",
                    "magnetic.total_magnetization_normalized_formula_units",
                    "magnetic.num_magnetic_sites",
                    "magnetic.num_unique_magnetic_sites",
                    "magnetic.types_of_magnetic_species"),
    ),
    BenchmarkTask(
        id="packing_fraction_regression",
        name="Packing-fraction regression",
        description="Predict the atomic packing fraction from composition + "
                    "structure descriptors. Density and volume are excluded "
                    "(packing ≈ cell volume × atomic radii — density is a "
                    "near-direct inverse function of volume given the "
                    "composition).",
        task_type="regression",
        target="structure.packing_fraction",
        metric="mae",
        doc_metrics=("rmse", "r2"),
        leaky_cols=("structure.density", "structure.density_atomic",
                    "structure.volume"),
    ),
    BenchmarkTask(
        id="electroneutral_classification",
        name="Electroneutrality classification",
        description="Predict whether a compound is electroneutral (redox."
                    "electroneutral) from composition descriptors only. The "
                    "redox/oxidation descriptors that DEFINE charge balance "
                    "(average oxidation, oxidation range, mixed valence, "
                    "anion/cation type) are excluded so the model must learn "
                    "the charge chemistry itself.",
        task_type="classification",
        target="redox.electroneutral",
        metric="macro_f1",
        doc_metrics=("accuracy", "roc_auc"),
        leaky_cols=("redox.redox_active_elements",
                    "redox.average_oxidation", "redox.oxidation_range",
                    "redox.mixed_valence", "redox.anion_type",
                    "redox.cation_type"),
    ),
    BenchmarkTask(
        id="li_hopping_distance_regression",
        name="Li-sublattice hopping distance regression",
        description="Predict the shortest periodic Li–Li hopping distance "
                    "(Å, the structure-derived transport proxy) from "
                    "composition + structure descriptors. The sibling "
                    "Li-sublattice analysis fields (Li site count, vacancy "
                    "fraction, site occupancy) are excluded so the model "
                    "must infer the Li transport geometry from chemistry.",
        task_type="regression",
        target="structure.li_hopping_distance",
        metric="mae",
        doc_metrics=("rmse", "r2"),
        leaky_cols=("structure.li_site_count",
                    "structure.li_vacancy_fraction",
                    "structure.li_site_occupancy"),
    ),
    BenchmarkTask(
        id="electrolyte_candidate_classification",
        name="Electrolyte-candidate classification",
        description="Predict whether a composition is a plausible solid-"
                    "electrolyte candidate (identity.is_electrolyte_candidate, "
                    "the deterministic synthesis-relevance flag) from "
                    "composition + structure descriptors. This is the "
                    "screening/synthesis-success proxy: known intercalation "
                    "cathode chemistries (LiCoO2, NMC) must be rejected. "
                    "identity.* fields (family, subfamily) are never model "
                    "inputs.",
        task_type="classification",
        target="identity.is_electrolyte_candidate",
        metric="macro_f1",
        doc_metrics=("accuracy", "roc_auc"),
    ),
)

_BY_ID: dict[str, BenchmarkTask] = {t.id: t for t in BENCHMARK_TASKS}


def get_task(task_id: str) -> BenchmarkTask | None:
    return _BY_ID.get(task_id)
