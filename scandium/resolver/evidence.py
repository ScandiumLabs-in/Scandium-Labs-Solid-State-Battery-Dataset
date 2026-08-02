from __future__ import annotations

import hashlib
import uuid
from datetime import datetime
from typing import Any


def generate_evidence_id(
    paper_doi: str,
    composition: str,
    property_type: str,
    value: float,
) -> str:
    raw = f"{paper_doi}|{composition}|{property_type}|{value}"
    return hashlib.sha256(raw.encode()).hexdigest()[:16]


def build_evidence_record(
    extraction: dict[str, Any],
    paper_id: str,
    paper_doi: str,
    composition: str,
    family: str,
) -> dict[str, Any]:
    property_type = extraction.get("_property_type", "unknown")
    value = extraction.get("value_normalized") or extraction.get("value")
    unit = extraction.get("unit_normalized") or extraction.get("unit", "")

    provenance = extraction.get("_provenance") or {}

    record: dict[str, Any] = {
        "evidence_id": generate_evidence_id(paper_doi, composition, property_type, value or 0),
        "paper_id": paper_id,
        "doi": paper_doi,
        "composition": composition,
        "family": family,
        "property": property_type,
        "value": value,
        "unit": unit,
        "normalized_value": extraction.get("value_normalized"),
        "normalized_unit": extraction.get("unit_normalized"),
        "temperature_celsius": extraction.get("temperature_celsius"),
        "conductivity_type": extraction.get("conductivity_type"),
        "measurement_method": extraction.get("measurement_method"),
        "pressure_MPa": extraction.get("pressure_MPa"),
        "source": extraction.get("source", ""),
        "is_primary": extraction.get("is_primary_measurement", True),
        "confidence": extraction.get("_confidence", 0),
        "issues": extraction.get("_issues", []),
        "valid": extraction.get("_valid", True),
        "extraction_date": datetime.now().isoformat(),
        "page": provenance.get("page"),
        "section": provenance.get("section", "Unknown"),
        "table_number": provenance.get("table_number"),
        "evidence_sentence": provenance.get("sentence", ""),
        "llm_model": provenance.get("llm_model", ""),
        "prompt_version": provenance.get("prompt_version", ""),
        "pipeline_version": provenance.get("pipeline_version", ""),
    }
    return record


def build_dataset_record(
    evidence_records: list[dict[str, Any]],
    paper_metadata: dict[str, Any],
) -> dict[str, Any]:
    dataset: dict[str, Any] = {
        "dataset_id": str(uuid.uuid4())[:8],
        "generated_at": datetime.now().isoformat(),
        "paper": {
            "paper_id": paper_metadata.get("paper_id", ""),
            "doi": paper_metadata.get("doi", ""),
            "title": paper_metadata.get("title", ""),
            "year": paper_metadata.get("year"),
        },
        "evidence": evidence_records,
        "n_evidence": len(evidence_records),
        "n_high_confidence": sum(
            1 for e in evidence_records if e.get("confidence", 0) >= 0.6
        ),
        "n_flagged": sum(
            1 for e in evidence_records if e.get("confidence", 0) < 0.6
        ),
    }
    return dataset


def merge_paper_results_into_evidence(
    result: dict[str, Any],
) -> list[dict[str, Any]]:
    paper_id = result.get("paper_id", "")
    doi = result.get("doi", "")
    composition = result.get("primary_composition", "")
    family = ""

    if result.get("compositions"):
        family = result["compositions"][0].get("family", "")

    evidence: list[dict[str, Any]] = []

    for cond in result.get("conductivities", {}).get("high_confidence", []) + \
                 result.get("conductivities", {}).get("flagged", []):
        if not cond.get("_valid", True) and cond.get("_confidence", 0) < 0.3:
            continue
        cond["_property_type"] = "conductivity"
        record = build_evidence_record(cond, paper_id, doi, composition, family)
        evidence.append(record)

    for ea in result.get("activation_energies", {}).get("high_confidence", []) + \
                result.get("activation_energies", {}).get("flagged", []):
        if not ea.get("_valid", True) and ea.get("_confidence", 0) < 0.3:
            continue
        ea["_property_type"] = "activation_energy"
        record = build_evidence_record(ea, paper_id, doi, composition, family)
        evidence.append(record)

    return evidence
