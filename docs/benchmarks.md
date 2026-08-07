# Scandium Benchmark Suite (v0.8.0 → v1.9.0 ScandiumBench)

The dataset's evaluable core. Twenty-five declarative benchmark tasks turn the
30,838-record canonical dataset into a measurable, comparable testbed — the
first milestone of the ImageNet-of-SSBs pivot. Everything is deterministic and
LLM-free: any model can be dropped in and scored against the same
leakage-checked splits.

**v1.8.0 adds the split-regime dimension** (ScandiumBench v1.0): every task is
scored under four deterministic split regimes — the reused random split plus
three *out-of-distribution* regimes (`family_ood`, `composition_ood`,
`crystal_system_ood`) that force a model to generalize to chemistries,
compositions, and crystal systems never seen in training. The gap between
random and OOD scores is the dataset's honesty check: a model that only
memorized the training distribution collapses on the OOD regimes, and the
leaderboard makes that visible instead of hiding it behind one random split.

**v1.9.0 expands the registry 15 → 25 tasks** across the property blocks the
roadmap Phase 4 called for: scarce literature-verified transport (Ea, σ_RT
magnitude), mechanical (bulk modulus, shear modulus, Debye temperature),
magnetic, structural packing, Li-sublattice transport-proxy, redox charge
balance, and the electrolyte-candidate screening/synthesis-success proxy.
Every new task follows the same hand-audited leaky-column discipline, and the
scarce transport tasks inherit the grouped-CV routing (a degenerate 7-train /
2-test split is never reported as evidence).

## Design principles

1. **Declarative tasks.** A task is a `BenchmarkTask` dataclass
   (`src/ssb_dataset/benchmarks/tasks.py`): which column to predict, the task
   type, the primary metric, and the leaky columns. No bespoke training code
   per task.
2. **Leaky-column discipline.** Every task hand-audits which columns are
   *derived from* the target and excludes them from features. Violations here
   would silently inflate a model's score:

   - volume regression → density excluded (`density = mass/volume`)
   - band-gap targets → cbm/vbm/efermi/is_metal excluded
   - stability → energy-above-hull excluded (it defines the label)
   - crystal system ↔ space group → each other's fields excluded
   - conductive ranking → all measurement-condition fields excluded
   - v1.9.0 extends this to whole *derived blocks*: each mechanical task
     excludes the sibling elastic/vibrational columns (K, G, ν, Aᴵ, θ_D all
     come from the same elastic-tensor computation); the magnetic task
     excludes the other magnetic descriptors; electroneutral excludes the
     oxidation/redox descriptors that define charge balance; packing-fraction
     excludes density/volume; the Li-hop task excludes the sibling
     Li-sublattice analysis fields; the Ea task excludes the sibling σ_RT
     scarce label and vice versa.
   - v1.9.0 `label_bounds`: mechanical tasks gate their labels to a physical
     window (K/G ∈ [1, 1000] GPa, θ_D ∈ [50, 3000] K) — MP's unphysical
     extremes are excluded from the benchmark, never imputed.

3. **Leakage-checked splits.** Model features are never fit on test rows: the
   split assignment comes from Phase 6 featurization
   (`features_output/{train,val,test,gold}.parquet`, keyed by
   `identity.material_id`, composition-family-grouped, leakage check PASSED).
   Mean imputation uses training means only.
4. **Deterministic baselines.** Dummy + linear (StandardScaler + ridge /
   logistic) + random forest + MLP (2-layer, 64→32, early stopping,
   `random_state=0`), all with `random_state=0`. No hyperparameter search in
   the shipped run — these are floor-level numbers, not SOTA. The MLP closes
   the improvement guide's §5 action-2 requirement ("at minimum RF + MLP on
   composition/space-group/lattice features"): a nonlinear composition
   descriptor baseline that is cheap enough to run on every task × regime.
5. **Small-label honesty.** The scarce σ_RT subset (n=166) and Ea subset
   (n=91, all in the `gold` split) cannot use the train/test split files. In
   the sklearn path they fall back to GroupKFold cross-validation grouped by
   material family, so no family leaks between folds — the same guarantee the
   split files enforce elsewhere. v1.9.0's `SCARCE_TEST_MIN = 30` guard
   generalizes the rule to any task whose random-regime test split is too
   small to be meaningful. The **v1.3.0 GCN baseline does better**: the Phase
   19 crystal-graph corpus (`dataset_ml/`) carries the structure∩label
   intersection, so the ranking task trains on *real* held-out splits (train
   164 / val 38 / test 35) instead of CV.

## Tasks

| Task id | Type | Target | Primary metric | Labeled rows |
|---|---|---|---|---|
| `formation_energy_regression` | regression | `thermodynamics.formation_energy_per_atom` | MAE | 29,855 |
| `band_gap_regression` | regression | `thermodynamics.band_gap` | MAE | 29,855 |
| `energy_above_hull_regression` | regression | `thermodynamics.energy_above_hull` | MAE | 21,528 |
| `bulk_modulus_regression` | regression | `mechanical.bulk_modulus` (GPa, [1, 1000]) | MAE | 3,108 |
| `shear_modulus_regression` | regression | `mechanical.shear_modulus` (GPa, [1, 1000]) | MAE | 2,928 |
| `debye_temperature_regression` | regression | `mechanical.debye_temperature` (K, [50, 3000]) | MAE | 826 |
| `density_regression` | regression | `structure.density` | MAE | 21,528 |
| `volume_regression` | regression | `structure.volume` | MAE | 21,528 |
| `ionic_radius_regression` | regression | `chemistry.ionic_radius_mean` | MAE | 21,528 |
| `stability_classification` | classification | `thermodynamics.is_stable` | macro-F1 | 21,528 |
| `wide_gap_classification` | classification | band gap > 4 eV | macro-F1 | 18,571 |
| `family_classification` | classification | `identity.family` (12 classes) | macro-F1 | 30,838 |
| `crystal_system_classification` | classification | `structure.crystal_system` (7) | macro-F1 | 21,528 |
| `space_group_classification` | classification | `structure.space_group_number` (194) | top-5 acc | 21,528 |
| `conductive_candidate_ranking` | ranking | `ion_transport.sigma_RT` (log10) | NDCG@10 | 166 |
| `negative_result_classification` | classification | `negative.is_negative_result` | macro-F1 | 29,855 |
| `metallic_classification` | classification | `thermodynamics.is_metal` | macro-F1 | 21,520 |
| `high_conductivity_classification` | classification | σ_RT > 10⁻³ S/cm | macro-F1 | 166 |
| `activation_energy_regression` | regression | `ion_transport.activation_energy_Ea` (eV) | MAE | 91 |
| `sigma_RT_regression` | regression | `ion_transport.sigma_RT` (log10) | MAE | 166 |
| `is_magnetic_classification` | classification | `magnetic.is_magnetic` | macro-F1 | 21,528 |
| `packing_fraction_regression` | regression | `structure.packing_fraction` | MAE | 21,528 |
| `electroneutral_classification` | classification | `redox.electroneutral` | macro-F1 | 19,332 |
| `li_hopping_distance_regression` | regression | `structure.li_hopping_distance` (Å) | MAE | 20,534 |
| `electrolyte_candidate_classification` | classification | `identity.is_electrolyte_candidate` | macro-F1 | 22,228 |

Labeled-row counts are from the canonical 30,838-row catalog (label availability,
not the split-filtered train/test counts). The ranking, high-conductivity,
activation-energy, and σ_RT-magnitude tasks are the dataset's scarce-asset
benchmarks: only literature-verified σ_RT / Ea labels count (they sit in the
`gold` split and are evaluated by family-grouped CV on every regime). The
mechanical row counts are post-`label_bounds` (physical-window gated).

The v1.5 `negative.*` block and v1.4 `validation.*` block are never model
inputs — they carry the labels of `negative_result_classification` (whose
defining signals — energy-above-hull, is_metal, band gap, Li-hop distance — are
all excluded from features, so the model must learn the chemistry itself).

## Split regimes (v1.8.0)

Every task is scored under four regimes
(`benchmark_output/splits/{regime}.parquet` + `manifest.json`, all
deterministic — stable group hashes, no RNG, no network):

| Regime | Split rule | Question it answers |
|---|---|---|
| `random` | Phase-6 leakage-checked split, reused unchanged | in-distribution baseline (comparable to prior releases) |
| `family_ood` | test = held-out families (halide, sulfide, nasicon, hydride, polymer_composite, borohydride, antiperovskite, garnet, perovskite, argyrodite); train = oxides + unknown | does an oxide-trained model generalize to other chemistries? |
| `composition_ood` | whole reduced-formula groups in one split (stable md5 bucket) | does a model generalize to compositions never seen in training? |
| `crystal_system_ood` | whole crystal systems in one split | does a model generalize to unseen crystal systems? |

Scarce tasks (the 166-row σ_RT subset and the 91-row Ea subset) are evaluated
by family-grouped GroupKFold CV on *every* regime — they sit in the gold split
under `random`, and v1.9.0's `SCARCE_TEST_MIN = 30` guard extends the rule to
any task whose random-regime test split is too small to be meaningful (the Ea
task would otherwise report a degenerate 7-train/2-test split). OOD results
for those tasks are therefore CV-based and comparable across
regimes.

## Running

```bash
# full suite (all 25 tasks, ~2 min)
python scripts/run_benchmarks.py

# a subset
python scripts/run_benchmarks.py --tasks band_gap_regression,family_classification

# re-render the leaderboard from cached per-task results (no re-training)
python scripts/run_benchmarks.py --report-only

# smoke run on the first N canonical rows
python scripts/run_benchmarks.py --limit 3000

# train the dataset_ml GCN baseline and merge it into the leaderboard
# (~2-4 min/task on CPU; --gnn-only skips the sklearn baselines)
python scripts/run_benchmarks.py --gnn-only --gnn-hidden 64 --gnn-layers 3 --gnn-epochs 40 --gnn-batch 128

# sklearn baselines + GCN in one pass
python scripts/run_benchmarks.py --gnn
```

**ScandiumBench (v1.8.0 → v1.9.0)** — all 25 tasks × 4 split regimes:

```bash
# full ScandiumBench run (~25-40 min: 25 tasks × 4 regimes)
python scripts/run_scandium_bench.py

# a subset (regimes / tasks) for iteration
python scripts/run_scandium_bench.py --regimes random,family_ood \
    --tasks negative_result_classification,electroneutral_classification
```

Output:
- `benchmark_output/tasks/<task_id>.json` — per-task metrics + feature list
  (`models.gcn` holds the GCN result, `gcn` the n_train/n_test/architecture)
- `benchmark_output/benchmark_report.json` — leaderboard (best model per task)
- `benchmark_output/benchmark_report.md` — human-readable leaderboard
- `benchmark_output/scandium_bench_report.json` / `.md` — **per-regime
  leaderboard** (best model per task per regime)
- `benchmark_output/splits/{random,family_ood,composition_ood,
  crystal_system_ood}.parquet` + `manifest.json` — persisted split assignments
  + regime definitions (auditable, deterministic)

## Baseline leaderboard (2026-08-06/07, deterministic)

The classic single-split leaderboard below is the `random`-regime result from
the older `run_benchmarks.py` path (RF best per task). The ScandiumBench
split-regime report (`benchmark_output/scandium_bench_report.md`) supersedes
it with per-model results (dummy / ridge / rf / mlp) across all five regimes;
the MLP column there shows where the nonlinear descriptor baseline edges out
RF (e.g. density under `random`, formation energy under `crystal_system_ood`).

| Task | Best model | Primary metric | Value |
|---|---|---|---|
| Formation energy | RF | MAE | 0.076 eV/atom |
| Band gap | RF | MAE | 0.439 eV |
| Energy above hull | RF | MAE | 0.035 eV/atom |
| Bulk modulus | RF | MAE | 13.1 GPa |
| Shear modulus | RF | MAE | 12.5 GPa |
| Debye temperature | RF | MAE | 54.8 K |
| Density | RF | MAE | 0.109 g/cm³ |
| Volume | RF | MAE | 14.97 Å³ |
| Ionic radius | RF | MAE | 0.008 Å |
| Stable vs unstable | RF | macro-F1 | 0.931 |
| Wide-gap (E_g > 4 eV) | RF | macro-F1 | 0.829 |
| Family (12 classes) | RF | macro-F1 | 0.848 |
| Crystal system (7 classes) | RF | macro-F1 | 0.838 |
| Space group (194 classes) | RF | top-5 acc | 0.887 |
| Conductive-candidate ranking | RF | NDCG@10 | 0.573 |
| Negative-result (poor electrolyte) | RF | macro-F1 | 0.835 |
| Metallic vs insulating | RF | macro-F1 | 0.838 |
| High-conductivity (σ_RT > 1e-3) | RF | macro-F1 | 0.652 |
| Activation energy | dummy | MAE | 0.148 eV |
| Conductivity magnitude (log10 σ_RT) | dummy | MAE | 0.818 |
| Magnetic vs non-magnetic | RF | macro-F1 | 0.921 |
| Packing fraction | RF | MAE | 0.015 |
| Electroneutrality | RF | macro-F1 | 0.910 |
| Li hopping distance | RF | MAE | 0.199 Å |
| Electrolyte candidate | RF | macro-F1 | 0.968 |

Random forest wins 23 of 25 on the single-split leaderboard; the MLP baseline
(guide §5 action-2) is competitive on every task and wins density under the
random regime (0.098 vs RF 0.118). The chemistry/stability tasks are strongly
composition-learnable; the new-task spread shows where composition+descriptor
baselines saturate: magnetic, electroneutrality and electrolyte-candidate
classifications are near-solved (macro-F1 0.91–0.97), while **shear modulus
regression collapses to R² ≈ −0.66** (RF is worse than predicting the mean —
the honest signal that shear modulus needs structure-aware models, not
composition descriptors). The scarce transport tasks (Ea MAE 0.148 eV on 91
labels, log10 σ MAE 0.818 on 166) are CV-evaluated — and there **no model
beats predicting the median** (dummy wins both): with 91–166 labels spread
across a handful of families, the composition descriptors carry too little
signal, which is the honest floor for these two tasks. The `dummy` column
in each task JSON is the mean/most-frequent floor — any real model must beat
it. The `mlp` column is the improvement-guide nonlinear-descriptor baseline
(the guide's §5 action-2 "RF + MLP at minimum"); where a task's labels are
linearly learnable ridge and MLP land close, and RF retains the edge on
composition descriptors — the same story OBELiX reported for their RF/MLP
baselines.

## Split-regime leaderboard (v1.9.0 + paper_ood, 2026-08-07, deterministic)

The OOD gap is the dataset's honesty check — it shows how much of a task is
memorization versus chemistry that generalizes. Best-model results per task ×
regime from `benchmark_output/scandium_bench_report.md` (MAE for regression,
macro-F1 for classification; `M` = MLP is the regime winner, `D` = dummy).
The full per-model table (dummy / ridge / rf / mlp) is in the report — the
MLP column here captures where the nonlinear descriptor baseline beats RF:

| Task (metric) | random | family_ood | composition_ood | crystal_system_ood | paper_ood |
|---|---:|---:|---:|---:|---:|
| Formation energy (MAE) | 0.067 | 1.006 | 0.163 | 0.550 M | 0.156 |
| Band gap (MAE) | 0.430 | 0.883 | 0.525 | 0.636 | 0.522 |
| Energy above hull (MAE) | 0.035 | 0.193 D | 0.044 | 0.096 M | 0.041 |
| Bulk modulus (MAE, GPa) | 13.1 | 29.7 | 19.5 M | 33.8 D | 17.7 |
| Shear modulus (MAE, GPa) | 12.5 | 18.1 | 13.6 M | 19.0 | 14.4 |
| Debye temperature (MAE, K) | 54.8 | 93.2 | 55.5 | 92.8 | 74.2 |
| Density (MAE) | 0.098 M | 1.778 | 0.389 M | 0.859 | 0.397 M |
| Volume (MAE) | 14.5 | 75.4 | 17.1 | 43.7 | 14.1 M |
| Ionic radius (MAE) | 0.008 | 0.137 | 0.013 | 0.007 | 0.012 |
| Stable vs unstable | 0.926 | 0.674 | 0.932 | 0.958 | 0.922 |
| Wide-gap (E_g > 4 eV) | 0.825 | 0.654 | 0.826 | 0.606 | 0.775 |
| Family (12 classes) | 0.822 | 0.065 D | 0.550 M | 0.350 M | 0.803 |
| Crystal system (7 classes) | 0.836 | 0.529 | 0.839 | 0.001 M | 0.828 |
| Space group (top-5 acc) | 0.888 | 0.252 | 0.892 | 0.641 D | 0.823 |
| Negative-result | 0.835 | 0.702 | 0.799 | 0.508 | 0.800 |
| Metallic | 0.838 | 0.817 | 0.806 | 0.712 | 0.811 |
| Magnetic | 0.921 | 0.788 | 0.901 | 0.905 | 0.919 |
| Packing fraction (MAE) | 0.015 | 0.108 | 0.019 | 0.014 | 0.019 |
| Electroneutrality | 0.910 | 0.654 | 0.843 | 0.864 | 0.832 |
| Li hopping distance (MAE, Å) | 0.199 | 0.699 | 0.232 | 0.309 | 0.224 |
| Electrolyte candidate | 0.968 | 0.502 | 0.930 | 0.901 | 0.951 |

Reading the table: **formation-energy MAE degrades 15× (0.067 → 1.006)** when
the model must predict non-oxide chemistries it never trained on; density 15×;
Li-hop distance 3.5× (0.199 → 0.699 Å); packing fraction 7× (0.015 → 0.108);
bulk-modulus MAE 2.6×. **Crystal-system classification under
`crystal_system_ood` collapses to ~0.001 macro-F1** and family classification
under `family_ood` to 0.065 — the honest result that you cannot predict an
unseen class (the label *is* the group key). The electrolyte-candidate
screening task (0.968 random → 0.502 family_ood) exposes that a
family-derived label is only learnable in-distribution. The **MLP wins 11 of
the 125 task×regime slots** — most notably density under the random regime
(0.098 vs RF 0.118: the descriptor nonlinearity matters) and formation-energy
under `crystal_system_ood` (0.550 vs RF 0.659), where the MLP's smooth
interpolation across the unseen crystal systems generalizes better than RF's
axis-aligned trees. That is a concrete, non-obvious baseline result: the
nonlinear descriptor baseline is *not* always the fallback, it wins the
hardest structural-generalization regimes. These are the numbers a genuinely
generalizing model (e.g. a GNN trained on the phase-19 graphs) is expected to
beat — the floor baselines stay the same, the regime now measures
*generalization*, not just in-distribution fit.

The scarce literature-verified tasks (ranking, high-conductivity, activation
energy, σ_RT magnitude) are grouped-CV on every regime, so their per-regime
numbers are identical — see the ScandiumBench report for them.

## GCN baseline (v1.3.0)

`src/ssb_dataset/benchmarks/gnn.py` closes the v0.8 gap ("torch is not
installed, so GNN/embedding models are the explicit next step"). A single small
GCN (3× GCNConv hidden=64, global mean pool, task head) trains per task on the
Phase 19 crystal-graph corpus (`dataset_ml/`): 21,528 PyG graphs, 10-dim
per-element node features, 1-dim edge features (bond distance), 5 Å crystal
graph. Design rules:

- **Deterministic**: `torch.manual_seed(0)`, fixed epochs, best-val checkpoint
  restore (early stop patience 8). No hyperparameter search in the shipped run.
- **Labels never imputed**: only `mask=True` rows enter the loss/eval; the
  conductive-ranking task trains directly on log10 σ_RT with real train/val/test
  splits (164/38/35) — the sklearn path could only offer family-grouped CV.
- **Apples-to-apples metrics**: test predictions are scored with the exact same
  `compute_metrics` as the sklearn baselines, so `models.gcn` rows merge
  straight into the leaderboard.
- **Same leakage rules**: the split assignment is the Phase 6 leakage-checked
  one; per-dimension feature normalization uses *train-only* statistics (frozen
  at eval); a single NaN element feature (Xe has no valence in the table) is
  filled with the train mean rather than poisoning a batch.

GCN numbers are floor-level like the sklearn baselines — RF still leads on all
25 tasks. The GCN's value today is (a) a working, CPU-only graph-training path
for the `dataset_ml` export, and (b) real held-out ranking splits. It is the
reference point that future architectures (ALIGNN, MACE, PIGNet-style) must
beat on the ranking task.

## Adding a task

Append a `BenchmarkTask(...)` to `BENCHMARK_TASKS` in
`src/ssb_dataset/benchmarks/tasks.py`. Follow the discipline:

1. `target` must be a real canonical column.
2. List every feature column derived from the target in `leaky_cols` (verify
   with `test_leaky_col_discipline`-style assertions).
3. For numeric classification use `threshold=`; for log-scale regression /
   ranking use `transform="log10"`.
4. Re-run `python scripts/run_benchmarks.py --report-only` after the full run
   to refresh the leaderboard without retraining.

## Adding a model

Edit `_models()` in `src/ssb_dataset/benchmarks/evaluate.py` — it returns a
`{name: sklearn_estimator}` dict and is shared by the split and CV paths.
Keep `random_state=0`. sklearn's `Pipeline` is fine (the harness passes numpy
`X` arrays). Do not fit on test rows; the harness only ever feeds train rows
to `.fit()`.

For a graph model (torch/torch_geometric), implement a `train_task(task_id,
cfg)` in the style of `src/ssb_dataset/benchmarks/gnn.py` and merge its result
dict into the per-task JSON as `models["<name>"]`. The `merge_gnn` function in
`scripts/run_benchmarks.py` shows the wiring — the leaderboard's `best_model`
selector picks it up automatically.

## Known limits

- **OOD regime hardness is by design, not a bug.** `crystal_system_ood`
  collapses crystal-system classification because the label *is* the group key —
  the OOD regime reports the honest "cannot predict an unseen class" result.
  Treat OOD numbers as generalization floors: a model beating them has learned
  transferable chemistry; a model matching random-regime numbers under OOD is
  overfit to the training distribution.
- The GCN is a small CPU baseline; the ranking task's 164 train labels is still
  a small benchmark — treat its NDCG@10 with statistical caution.
- The ranking labels that sit in `gold` (verified σ with no MP structure) are
  honestly excluded from the graph corpus, so the GCN ranking metric is computed
  on the structure∩label intersection only. Growing it is a Phase 11 data
  problem, not a code gap.
- The scarce transport tasks (Ea n=91, σ_RT n=166) are CV-evaluated — their
  grouped-CV numbers are honest but carry wide error bars; treat the Ea MAE
  0.148 eV as a floor for a 91-label task.
- **Shear-modulus regression is hard by the numbers**: RF R² ≈ −0.66 (worse
  than the mean). That is a baseline result, not a bug — shear modulus is
  poorly predicted from composition descriptors, which is precisely why the
  mechanical tasks were added. The mechanical labels are MP elastic-tensor
  values gated to a physical window via `label_bounds`; the few extreme
  entries MP returns are excluded, never imputed.
- Regression targets are MP-derived (PBE band gaps, DFT energies). These are
  computed quantities — the tasks benchmark feature expressiveness, not
  experimental prediction.
