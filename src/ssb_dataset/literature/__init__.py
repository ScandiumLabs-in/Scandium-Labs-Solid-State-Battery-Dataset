"""Literature package — discovery, extraction, linking, and seed-set QC."""

from ssb_dataset.literature.discovery import PaperCandidate, run_discovery, save_discovery_results, triage_candidates
from ssb_dataset.literature.extraction import (
    ExtractedConductivityRecord,
    extract_from_pdf,
    extraction_record_to_material_record,
    run_llm_extraction,
)
from ssb_dataset.literature.linking import StructureIndex, match_composition
from ssb_dataset.literature.seed import SEED_RECORDS, get_seed_records, validate_extraction_against_seed

__all__ = [
    "ExtractedConductivityRecord",
    "PaperCandidate",
    "StructureIndex",
    "extract_from_pdf",
    "extraction_record_to_material_record",
    "get_seed_records",
    "match_composition",
    "run_discovery",
    "run_llm_extraction",
    "save_discovery_results",
    "triage_candidates",
    "validate_extraction_against_seed",
]