"""Tests for Phase 5 — DFT Compute Pipeline."""

from __future__ import annotations

import json
import tempfile
from pathlib import Path

import pytest

from ssb_dataset.dft.aimd import AIMDWorkflow
from ssb_dataset.dft.inputs import generate_qe_inputs, generate_vasp_inputs, write_inputs
from ssb_dataset.dft.monitor import JobMonitor, JobStatus
from ssb_dataset.dft.parse import parse_to_material_record, parse_vasp_output
from ssb_dataset.dft.priority import GapType, JobPriority, compute_queue
from ssb_dataset.dft.workflow import DFTWorkflow, VaspJob

SAMPLE_CIF = """data_test
_cell_length_a 10.0
_cell_length_b 10.0
_cell_length_c 10.0
_cell_angle_alpha 90.0
_cell_angle_beta 90.0
_cell_angle_gamma 90.0
_symmetry_space_group_name_H-M P1
loop_
_atom_site_label
_atom_site_fract_x
_atom_site_fract_y
_atom_site_fract_z
_atom_site_occupancy
Li1 0.0 0.0 0.0 1.0
Cl1 0.5 0.5 0.5 1.0
"""


# ── Priority Queue ─────────────────────────────────────────────────────────────


class TestBuildPriorityQueue:
    def test_empty_queue(self) -> None:
        from ssb_dataset.dft.priority import BuildPriorityQueue
        q = BuildPriorityQueue()
        assert len(q) == 0

    def test_add_composition(self) -> None:
        from ssb_dataset.dft.priority import BuildPriorityQueue
        q = BuildPriorityQueue()
        q.add("Li6PS5Cl", gap_type=GapType.unmatched_structure, priority=JobPriority.critical)
        assert len(q) == 1
        assert q.compositions[0]["composition"] == "Li6PS5Cl"
        assert q.compositions[0]["priority"] == 1

    def test_sort_by_priority(self) -> None:
        from ssb_dataset.dft.priority import BuildPriorityQueue
        q = BuildPriorityQueue()
        q.add("low_priority", gap_type=GapType.family_undersampled, priority=JobPriority.low)
        q.add("high_priority", gap_type=GapType.unmatched_structure, priority=JobPriority.critical)
        sorted_items = q.sort()
        assert sorted_items[0]["priority"] == 1
        assert sorted_items[1]["priority"] == 4


class TestComputeQueue:
    def test_without_files(self, tmp_path: Path) -> None:
        queue = compute_queue(
            survey_path=str(tmp_path / "nonexistent.json"),
            literature_unmatched_path=str(tmp_path / "nonexistent.json"),
        )
        assert len(queue) == 0

    def test_with_literature_unmatched(self, tmp_path: Path) -> None:
        unmatched = [
            {"composition": "Li6PS5Cl", "doi": "10.1234/test", "sigma_RT": 1e-3},
        ]
        f = tmp_path / "unmatched.json"
        f.write_text(json.dumps(unmatched))
        queue = compute_queue(
            survey_path=str(tmp_path / "empty.json"),
            literature_unmatched_path=str(f),
        )
        assert len(queue) == 1
        assert queue.compositions[0]["gap_type"] == "unmatched_structure"
        assert queue.compositions[0]["priority"] == 1

    def test_with_family_targets(self, tmp_path: Path) -> None:
        survey = {"materials_project": {"sulfide": 100, "halide": 5}}
        f = tmp_path / "survey.json"
        f.write_text(json.dumps(survey))
        queue = compute_queue(
            survey_path=str(f),
            literature_unmatched_path=str(tmp_path / "empty.json"),
            family_targets={"halide": 50, "sulfide": 50},
        )
        assert len(queue) == 1
        assert queue.compositions[0]["gap_type"] == "family_undersampled"


# ── Input Generation ──────────────────────────────────────────────────────────


class TestGenerateVASPInputs:
    def test_creates_input_files(self, tmp_path: Path) -> None:
        result = generate_vasp_inputs(SAMPLE_CIF, tmp_path)
        assert (tmp_path / "INCAR").exists()
        assert (tmp_path / "POSCAR").exists()
        assert (tmp_path / "KPOINTS").exists()
        assert result["poscar"]
        assert result["incar"]
        assert result["kpoints"]

    def test_incar_defaults(self, tmp_path: Path) -> None:
        generate_vasp_inputs(SAMPLE_CIF, tmp_path)
        incar_text = (tmp_path / "INCAR").read_text()
        assert "PREC = Accurate" in incar_text
        assert "ENCUT = 520" in incar_text
        assert "ISIF = 3" in incar_text

    def test_incar_overrides(self, tmp_path: Path) -> None:
        generate_vasp_inputs(SAMPLE_CIF, tmp_path, incar_overrides={"ENCUT": 400})
        incar_text = (tmp_path / "INCAR").read_text()
        assert "ENCUT = 400" in incar_text

    def test_kpoints_generated(self, tmp_path: Path) -> None:
        generate_vasp_inputs(SAMPLE_CIF, tmp_path, kppa=2000)
        kpoints = (tmp_path / "KPOINTS").read_text()
        assert "Gamma-centered" in kpoints


class TestGenerateQEInputs:
    def test_creates_input(self, tmp_path: Path) -> None:
        result = generate_qe_inputs(SAMPLE_CIF, tmp_path)
        assert "input" in result
        assert (tmp_path / "ssb.in").exists()

    def test_qe_input_content(self, tmp_path: Path) -> None:
        generate_qe_inputs(SAMPLE_CIF, tmp_path)
        text = (tmp_path / "ssb.in").read_text()
        assert "&CONTROL" in text
        assert "&SYSTEM" in text
        assert "ATOMIC_SPECIES" in text
        assert "K_POINTS" in text
        assert "Li" in text
        assert "Cl" in text


class TestWriteInputs:
    def test_vasp_selection(self, tmp_path: Path) -> None:
        result = write_inputs(SAMPLE_CIF, tmp_path, code="vasp")
        assert (tmp_path / "INCAR").exists()
        assert result["incar"]

    def test_qe_selection(self, tmp_path: Path) -> None:
        result = write_inputs(SAMPLE_CIF, tmp_path, code="qe")
        assert (tmp_path / "ssb.in").exists()
        assert result["input"]

    def test_invalid_code(self, tmp_path: Path) -> None:
        with pytest.raises(ValueError):
            write_inputs(SAMPLE_CIF, tmp_path, code="unknown")


# ── Job Monitor ───────────────────────────────────────────────────────────────


class TestJobMonitor:
    def test_register_and_update(self) -> None:
        m = JobMonitor()
        m.register_job("test_job", composition="Li6PS5Cl")
        assert m.jobs["test_job"]["status"] == "pending"
        m.update_job("test_job", JobStatus.RUNNING)
        assert m.jobs["test_job"]["status"] == "running"

    def test_summary(self) -> None:
        m = JobMonitor()
        m.register_job("a")
        m.register_job("b")
        m.update_job("a", JobStatus.COMPLETED)
        m.update_job("b", JobStatus.FAILED)
        summary = m.summary()
        assert summary.get("completed") == 1
        assert summary.get("failed") == 1

    def test_success_rate(self) -> None:
        m = JobMonitor()
        m.register_job("a")
        m.update_job("a", JobStatus.COMPLETED)
        assert m.success_rate == 1.0

        m.register_job("b")
        m.update_job("b", JobStatus.FAILED)
        assert m.success_rate == 0.5

    def test_failures(self) -> None:
        m = JobMonitor()
        m.register_job("a")
        m.update_job("a", JobStatus.FAILED, error="convergence error")
        assert len(m.failures()) == 1
        assert m.failures()[0]["error"] == "convergence error"

    def test_completed(self) -> None:
        m = JobMonitor()
        m.register_job("a")
        m.update_job("a", JobStatus.COMPLETED)
        assert len(m.completed()) == 1

    def test_logging(self, tmp_path: Path) -> None:
        log = tmp_path / "monitor.json"
        m = JobMonitor(log_path=log)
        m.register_job("a")
        m.update_job("a", JobStatus.COMPLETED)
        assert log.exists()
        data = json.loads(log.read_text())
        assert "summary" in data

    def test_empty_success_rate(self) -> None:
        m = JobMonitor()
        assert m.success_rate == 0.0


# ── Workflow (no VASP binary — tests metadata only) ──────────────────────────


class TestVaspJob:
    def test_job_metadata(self, tmp_path: Path) -> None:
        job = VaspJob(
            name="test_job",
            structure_cif=SAMPLE_CIF,
            work_dir=str(tmp_path / "test_job"),
        )
        assert job.name == "test_job"

    def test_run_without_vasp(self, tmp_path: Path) -> None:
        job = VaspJob(
            name="no_vasp",
            structure_cif=SAMPLE_CIF,
            work_dir=str(tmp_path / "no_vasp"),
        )
        result = job.run()
        assert result["success"] is False
        assert "vasp not found" in result.get("error", "")


class TestDFTWorkflow:
    def test_empty_workflow(self) -> None:
        wf = DFTWorkflow()
        assert len(wf.results) == 0

    def test_add_job(self, tmp_path: Path) -> None:
        wf = DFTWorkflow()
        job = VaspJob(name="test", structure_cif=SAMPLE_CIF, work_dir=str(tmp_path / "test"))
        wf.add_job(job)
        assert len(wf.jobs) == 1

    def test_run_all_no_vasp(self, tmp_path: Path) -> None:
        wf = DFTWorkflow(max_retries=1)
        job = VaspJob(name="a", structure_cif=SAMPLE_CIF, work_dir=str(tmp_path / "a"))
        wf.add_job(job)
        results = wf.run_all()
        assert len(results) == 1
        assert results[0]["name"] == "a"


# ── Output Parsing ────────────────────────────────────────────────────────────


class TestParseVaspOutput:
    def test_empty_directory(self, tmp_path: Path) -> None:
        result = parse_vasp_output(tmp_path / "nonexistent")
        assert result["success"] is False

    def test_no_output_files(self, tmp_path: Path) -> None:
        (tmp_path / "INCAR").write_text("SYSTEM = test\n")
        result = parse_vasp_output(tmp_path)
        assert result["converged"] is False
        assert result["final_energy_eV"] == 0.0

    def test_parse_incar_only(self, tmp_path: Path) -> None:
        incar = "SYSTEM = test\nENCUT = 520\nISMEAR = 0\nLWAVE = .FALSE.\n"
        (tmp_path / "INCAR").write_text(incar)
        result = parse_vasp_output(tmp_path)
        assert result["incar"]["SYSTEM"] == "test"
        assert result["incar"]["ENCUT"] == 520
        assert result["incar"]["LWAVE"] is False


class TestParseToMaterialRecord:
    def test_basic_conversion(self) -> None:
        parsed = {
            "success": True,
            "converged": True,
            "relaxed_structure_cif": SAMPLE_CIF,
            "final_energy_eV": -50.0,
            "outcar": {"num_ions": 10},
            "incar": {"PREC": "Accurate", "ENCUT": 520},
        }
        record = parse_to_material_record(parsed, "LiCl", source_id="001", family=None)
        assert record.identity.source_db.value == "scandium_computed"
        assert record.identity.material_id == "scandium_computed_001"
        assert record.thermodynamics.formation_energy_per_atom == -5.0
        assert record.structure.structure_relaxed == SAMPLE_CIF

    def test_family_assignment(self) -> None:
        from ssb_dataset.schema import Family
        parsed = {"success": True}
        record = parse_to_material_record(parsed, "Li6PS5Cl", source_id="002", family=Family.sulfide)
        assert record.identity.family == Family.sulfide


# ── AIMD ──────────────────────────────────────────────────────────────────────


class TestAIMDWorkflow:
    def test_aimd_metadata(self, tmp_path: Path) -> None:
        aimd = AIMDWorkflow(
            name="test_aimd",
            structure_cif=SAMPLE_CIF,
            work_dir=str(tmp_path / "aimd"),
            temperature_K=600.0,
        )
        assert aimd.name == "test_aimd"
        assert aimd.temperature_K == 600.0

    def test_generate_vasp_aimd_inputs(self, tmp_path: Path) -> None:
        aimd = AIMDWorkflow(
            name="aimd_test",
            structure_cif=SAMPLE_CIF,
            work_dir=str(tmp_path / "aimd"),
        )
        inputs = aimd.generate_vasp_aimd_inputs()
        assert (tmp_path / "aimd" / "INCAR").exists()
        incar = (tmp_path / "aimd" / "INCAR").read_text()
        assert "IBRION = 0" in incar
        assert "MDALGO = 2" in incar
        assert "POTIM" in incar

    def test_estimate_conductivity_from_msd(self) -> None:
        aimd = AIMDWorkflow(
            name="msd_test",
            structure_cif=SAMPLE_CIF,
            work_dir="/tmp/msd_test",
        )
        msd_data = [(0.0, 0.0), (100.0, 50.0), (200.0, 100.0), (300.0, 150.0)]
        result = aimd.estimate_conductivity_from_msd(
            msd_data=msd_data,
            n_li=10,
            volume_cm3=1e-21,
            temperature_K=600.0,
        )
        assert result["conductivity_S_per_cm"] > 0
        assert result["diffusivity_cm2_s"] > 0

    def test_estimate_conductivity_insufficient_data(self) -> None:
        aimd = AIMDWorkflow(name="short", structure_cif=SAMPLE_CIF, work_dir="/tmp/short")
        result = aimd.estimate_conductivity_from_msd(
            msd_data=[(0.0, 0.0)],
            n_li=10,
            volume_cm3=1e-21,
        )
        assert "error" in result
