"""Phase 10 — Maintenance documentation.

Generates CONTRIBUTING.md, MAINTENANCE.md, DEPRECATION.md, USAGE_GUIDE.md,
and issue/PR templates for community contribution.
"""

from ssb_dataset.maintenance.generator import (
    generate_contributing,
    generate_maintenance_plan,
    generate_deprecation_policy,
    generate_usage_guide,
    generate_issue_templates,
    generate_pr_template,
)

__all__ = [
    "generate_contributing",
    "generate_maintenance_plan",
    "generate_deprecation_policy",
    "generate_usage_guide",
    "generate_issue_templates",
    "generate_pr_template",
]
