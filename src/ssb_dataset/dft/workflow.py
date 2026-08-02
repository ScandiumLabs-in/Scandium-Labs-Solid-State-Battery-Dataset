from __future__ import annotations

import subprocess
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from ssb_dataset.dft.inputs import write_inputs
from ssb_dataset.dft.monitor import JobMonitor, JobStatus


@dataclass
class VaspJob:
    """Represents a single VASP calculation job."""
    name: str
    structure_cif: str
    work_dir: str | Path
    incar_overrides: dict[str, Any] | None = None
    functional: str = "PBE"
    kppa: int = 1000
    potcar_dir: str | None = None
    vasp_command: str = "vasp_std"
    monitor: JobMonitor | None = None

    def __post_init__(self) -> None:
        self.work_dir = Path(self.work_dir)

    @property
    def input_files(self) -> dict[str, str]:
        return write_inputs(
            structure_cif=self.structure_cif,
            output_dir=self.work_dir,
            code="vasp",
            incar_overrides=self.incar_overrides,
            functional=self.functional,
            kppa=self.kppa,
            potcar_dir=self.potcar_dir,
        )

    def run(self, timeout_minutes: int = 120) -> dict[str, Any]:
        if self.monitor:
            self.monitor.update_job(self.name, JobStatus.RUNNING)
        try:
            self.input_files
            result = subprocess.run(
                [self.vasp_command],
                cwd=str(self.work_dir),
                capture_output=True,
                text=True,
                timeout=timeout_minutes * 60,
            )
            if result.returncode != 0:
                if self.monitor:
                    self.monitor.update_job(self.name, JobStatus.FAILED,
                                            error=result.stderr[-500:])
                return {
                    "success": False,
                    "name": self.name,
                    "returncode": result.returncode,
                    "stdout": result.stdout[-1000:],
                    "stderr": result.stderr[-1000:],
                }
            if self.monitor:
                self.monitor.update_job(self.name, JobStatus.COMPLETED)
            return {
                "success": True,
                "name": self.name,
                "work_dir": str(self.work_dir),
            }
        except subprocess.TimeoutExpired:
            if self.monitor:
                self.monitor.update_job(self.name, JobStatus.FAILED, error="Timeout")
            return {"success": False, "name": self.name, "error": "timeout"}
        except FileNotFoundError:
            if self.monitor:
                self.monitor.update_job(self.name, JobStatus.FAILED, error="vasp not found")
            return {"success": False, "name": self.name, "error": "vasp not found"}


@dataclass
class QuantumEspressoJob:
    """Represents a single Quantum Espresso calculation job."""
    name: str
    structure_cif: str
    work_dir: str | Path
    pseudopotentials: dict[str, str] | None = None
    pw_command: str = "pw.x"
    monitor: JobMonitor | None = None

    def __post_init__(self) -> None:
        self.work_dir = Path(self.work_dir)

    def run(self, timeout_minutes: int = 120) -> dict[str, Any]:
        if self.monitor:
            self.monitor.update_job(self.name, JobStatus.RUNNING)
        try:
            inputs = write_inputs(
                structure_cif=self.structure_cif,
                output_dir=self.work_dir,
                code="qe",
                pseudopotentials=self.pseudopotentials,
            )
            input_file = inputs.get("input", "")
            result = subprocess.run(
                [self.pw_command, "-i", input_file],
                cwd=str(self.work_dir),
                capture_output=True,
                text=True,
                timeout=timeout_minutes * 60,
            )
            if result.returncode != 0:
                if self.monitor:
                    self.monitor.update_job(self.name, JobStatus.FAILED,
                                            error=result.stderr[-500:])
                return {"success": False, "name": self.name, "returncode": result.returncode}
            if self.monitor:
                self.monitor.update_job(self.name, JobStatus.COMPLETED)
            return {"success": True, "name": self.name, "work_dir": str(self.work_dir)}
        except subprocess.TimeoutExpired:
            if self.monitor:
                self.monitor.update_job(self.name, JobStatus.FAILED, error="Timeout")
            return {"success": False, "name": self.name, "error": "timeout"}


@dataclass
class DFTWorkflow:
    """Orchestrate a batch of DFT jobs with Custodian-style error handling."""
    jobs: list[VaspJob | QuantumEspressoJob] = field(default_factory=list)
    monitor: JobMonitor | None = None
    max_retries: int = 2
    results: list[dict[str, Any]] = field(default_factory=list)

    def add_job(self, job: VaspJob | QuantumEspressoJob) -> None:
        self.jobs.append(job)

    def run_all(self, parallel: bool = False) -> list[dict[str, Any]]:
        for job in self.jobs:
            attempt = 0
            while attempt <= self.max_retries:
                result = job.run()
                if result["success"]:
                    self.results.append(result)
                    break
                attempt += 1
                if attempt <= self.max_retries:
                    if self.monitor:
                        self.monitor.update_job(job.name, JobStatus.RETRYING,
                                                attempt=attempt)
                    if not parallel:
                        continue
            if attempt > self.max_retries:
                self.results.append({
                    "success": False,
                    "name": job.name,
                    "error": f"Failed after {self.max_retries} retries",
                })
        return self.results


def run_custodian_workflow(
    jobs: list[VaspJob],
    work_base_dir: str | Path = "dft_jobs",
    max_retries: int = 2,
) -> tuple[list[dict[str, Any]], JobMonitor]:
    monitor = JobMonitor()
    workflow = DFTWorkflow(jobs=jobs, monitor=monitor, max_retries=max_retries)
    results = workflow.run_all()
    return results, monitor
