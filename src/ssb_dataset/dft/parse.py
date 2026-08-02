from __future__ import annotations

import re
from pathlib import Path
from typing import Any

import numpy as np

from ssb_dataset.schema import (
    ConfidenceTier,
    Family,
    IdentityProvenance,
    IonTransportBlock,
    MaterialRecord,
    MLFeaturesBlock,
    SourceDB,
    StructureBlock,
    SynthesisBlock,
    ThermodynamicsBlock,
)


def _parse_incar(path: str | Path) -> dict[str, Any]:
    """Parse INCAR file for calculation parameters."""
    params: dict[str, Any] = {}
    path = Path(path)
    if not path.exists():
        return params
    for line in path.read_text().splitlines():
        line = line.strip()
        if "=" in line and not line.startswith("#") and not line.startswith("!"):
            parts = line.split("=", 1)
            key = parts[0].strip()
            val = parts[1].strip().strip("'\"")
            try:
                val = int(val)
            except ValueError:
                try:
                    val = float(val)
                except ValueError:
                    if val.upper() in (".TRUE.", ".FALSE."):
                        val = val.upper() == ".TRUE."
                    pass
            params[key] = val
    return params


def _parse_outcar(path: str | Path) -> dict[str, Any]:
    """Parse selected quantities from VASP OUTCAR."""
    path = Path(path)
    if not path.exists():
        return {}

    text = path.read_text()
    result: dict[str, Any] = {}

    energy_match = re.search(r"energy\s+without\s+entropy\s*=\s*([-\d.]+)", text)
    if energy_match:
        result["energy_without_entropy_eV"] = float(energy_match.group(1))

    energy_with_entropy = re.search(r"energy\s+\(sigma->0\)\s*=\s*([-\d.]+)", text)
    if energy_with_entropy:
        result["energy_sigma_0_eV"] = float(energy_with_entropy.group(1))

    num_atoms_match = re.search(r"NIONS\s*=\s*(\d+)", text)
    if num_atoms_match:
        result["num_ions"] = int(num_atoms_match.group(1))

    return result


def _parse_oszicar(path: str | Path) -> list[dict[str, float]]:
    """Parse OSZICAR for electronic steps and energies."""
    path = Path(path)
    if not path.exists():
        return []

    steps: list[dict[str, float]] = []
    for line in path.read_text().splitlines():
        parts = line.split()
        if len(parts) >= 4 and parts[0].lstrip("-").isdigit():
            try:
                steps.append({
                    "step": int(parts[0]),
                    "free_energy": float(parts[1]),
                    "energy_change": float(parts[2]),
                })
            except (ValueError, IndexError):
                continue
    return steps


def _parse_contcar(path: str | Path) -> str | None:
    """Extract relaxed structure from CONTCAR as CIF string."""
    path = Path(path)
    if not path.exists():
        return None
    try:
        from pymatgen.core import Structure
        struct = Structure.from_file(str(path))
        return struct.to(fmt="cif")
    except Exception:
        return None


def parse_vasp_output(work_dir: str | Path) -> dict[str, Any]:
    """Parse VASP output files from a completed job directory."""
    work_dir = Path(work_dir)
    result: dict[str, Any] = {
        "work_dir": str(work_dir),
        "success": False,
    }

    incar = _parse_incar(work_dir / "INCAR")
    outcar = _parse_outcar(work_dir / "OUTCAR")
    oszicar = _parse_oszicar(work_dir / "OSZICAR")
    contcar = _parse_contcar(work_dir / "CONTCAR")

    converged = False
    if oszicar and len(oszicar) >= 2:
        last_steps = oszicar[-2:]
        converged = all(abs(s["energy_change"]) < 1e-4 for s in last_steps)

    result.update({
        "success": converged,
        "converged": converged,
        "incar": incar,
        "outcar": outcar,
        "electronic_steps": oszicar,
        "relaxed_structure_cif": contcar,
        "final_energy_eV": outcar.get("energy_without_entropy_eV", 0.0),
    })

    return result


def parse_qe_output(work_dir: str | Path) -> dict[str, Any]:
    """Parse Quantum Espresso output files."""
    work_dir = Path(work_dir)
    result: dict[str, Any] = {"work_dir": str(work_dir), "success": False}
    output_file = work_dir / "ssb.out"
    if not output_file.exists():
        return result

    text = output_file.read_text()
    energy_match = re.search(r"!\s+total energy\s+=\s+([-\d.]+)\s+Ry", text)
    if energy_match:
        result["final_energy_Ry"] = float(energy_match.group(1))
        result["final_energy_eV"] = float(energy_match.group(1)) * 13.6057

    converged = "convergence has been achieved" in text or "JOB DONE" in text
    result["converged"] = converged
    result["success"] = converged
    return result


def parse_to_material_record(
    parsed_output: dict[str, Any],
    composition: str,
    source_id: str,
    family: Family | None = None,
) -> MaterialRecord:
    """Convert parsed DFT output to a MaterialRecord."""
    relaxed_cif = parsed_output.get("relaxed_structure_cif", "")
    final_energy = parsed_output.get("final_energy_eV", 0.0)
    num_atoms = parsed_output.get("outcar", {}).get("num_ions", 0)

    identity = IdentityProvenance(
        material_id=f"scandium_computed_{source_id}",
        source_db=SourceDB.scandium_computed,
        source_id=source_id,
        family=family or Family.unknown,
        confidence_tier=ConfidenceTier.dft_native,
    )

    thermo = ThermodynamicsBlock(
        formation_energy_per_atom=final_energy / max(num_atoms, 1) if num_atoms else None,
    )

    transport = IonTransportBlock(
        sigma_RT=None,
        activation_energy_Ea=None,
        label_available=False,
    )

    structure = StructureBlock(
        structure_relaxed=relaxed_cif if relaxed_cif else None,
    )

    synthesis = SynthesisBlock(
        processing_metadata=parsed_output.get("incar", {}),
    )

    ml = MLFeaturesBlock()

    return MaterialRecord(
        identity=identity,
        ion_transport=transport,
        thermodynamics=thermo,
        structure=structure,
        synthesis=synthesis,
        ml_features=ml,
    )
