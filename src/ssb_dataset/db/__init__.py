"""v1.0 — relational dataset (material -> experiment -> measurement -> evidence).

Turns the flat canonical table into first-class relational entities
(materials, papers, experiments, measurements, synthesis, dopants) keyed by
deterministic ids, preserving experimental variability and per-field
confidence. See `src/ssb_dataset/db/schema.py` (ids, fingerprints, field-level
confidence) and `src/ssb_dataset/db/build.py` (table builders).
"""

from ssb_dataset.db import build, schema

__all__ = ["build", "schema"]
