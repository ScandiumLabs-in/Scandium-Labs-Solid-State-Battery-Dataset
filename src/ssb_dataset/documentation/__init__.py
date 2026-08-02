"""Documentation generation for the SSB Dataset.

Generates Datasheet for Datasets (Gebru et al. format), per-family READMEs,
confidence-tier documentation, CITATION.cff, and CHANGELOG updates.
"""

from ssb_dataset.documentation.generator import (
    generate_citation_cff,
    generate_confidence_tier_doc,
    generate_datasheet,
    generate_family_readme,
    update_changelog,
)

__all__ = [
    "generate_datasheet",
    "generate_family_readme",
    "generate_confidence_tier_doc",
    "generate_citation_cff",
    "update_changelog",
]
