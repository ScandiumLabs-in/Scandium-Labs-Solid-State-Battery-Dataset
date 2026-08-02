from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import numpy as np


@dataclass
class AIMDWorkflow:
    """AIMD-based conductivity estimation workflow.

    Runs AIMD on a priority compound and estimates sigma from MSD analysis.
    This is a scaffold — actual AIMD is extremely expensive (tens of thousands
    of core-hours per compound). The pipeline prepares inputs and parses
    outputs; the compute itself runs on HPC.
    """
    name: str
    structure_cif: str
    work_dir: str | Path
    temperature_K: float = 600.0
    timestep_fs: float = 2.0
    nsteps: int = 10000
    nsw: int = 10000
    tau: float = 100.0
    potcar_dir: str | None = None
    results: dict[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        self.work_dir = Path(self.work_dir)
        self.work_dir.mkdir(parents=True, exist_ok=True)

    def generate_vasp_aimd_inputs(self, incar_overrides: dict[str, Any] | None = None) -> dict[str, str]:
        from ssb_dataset.dft.inputs import generate_vasp_inputs
        aimd_incar = {
            "IBRION": 0,
            "MDALGO": 2,
            "ISIF": 2,
            "NSW": self.nsw,
            "POTIM": self.timestep_fs,
            "TEBEG": self.temperature_K,
            "TEEND": self.temperature_K,
            "SMASS": 0,
            "PREC": "Normal",
            "NBLOCK": 1,
            "KBLOCK": 10,
        }
        if incar_overrides:
            aimd_incar.update(incar_overrides)
        return generate_vasp_inputs(
            structure_cif=self.structure_cif,
            output_dir=self.work_dir,
            incar_overrides=aimd_incar,
            kppa=400,
            potcar_dir=self.potcar_dir,
        )

    def generate_qe_aimd_inputs(self, pseudopotentials: dict[str, str] | None = None) -> dict[str, str]:
        from ssb_dataset.dft.inputs import generate_qe_inputs
        return generate_qe_inputs(
            structure_cif=self.structure_cif,
            output_dir=self.work_dir,
            pseudopotentials=pseudopotentials,
        )

    def estimate_conductivity_from_msd(
        self,
        msd_data: list[tuple[float, float]],
        n_li: int,
        volume_cm3: float,
        temperature_K: float | None = None,
    ) -> dict[str, float]:
        """Estimate ionic conductivity from MSD (mean squared displacement) data.

        Uses the Einstein relation:
            sigma = (q^2 * D * n) / (V * KB * T)

        where D = MSD_slope / (6 * timestep_correction)
        """
        T = temperature_K or self.temperature_K
        timesteps, msd = zip(*msd_data) if msd_data else ([], [])
        if len(timesteps) < 2:
            return {"conductivity_S_per_cm": 0.0, "diffusivity": 0.0, "error": "insufficient_msd_data"}

        coeffs = np.polyfit(timesteps, msd, 1)
        msd_slope = coeffs[0]
        diffusivity = msd_slope / 6.0

        diffusivity_cm2_s = diffusivity * 1e-8
        n_density = n_li / volume_cm3
        q = 1.602e-19
        KB = 1.381e-23
        sigma = (q ** 2 * diffusivity_cm2_s * n_density) / (KB * T)

        return {
            "conductivity_S_per_cm": sigma,
            "diffusivity_cm2_s": diffusivity_cm2_s,
            "msd_slope_A2_per_step": msd_slope,
            "n_li": n_li,
            "temperature_K": T,
        }
