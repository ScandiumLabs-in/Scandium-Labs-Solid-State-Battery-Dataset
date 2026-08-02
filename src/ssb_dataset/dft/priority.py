from __future__ import annotations

import json
from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path
from typing import Any


class GapType(Enum):
    unmatched_structure = "unmatched_structure"
    family_undersampled = "family_undersampled"
    synthesis_accessible_unstructured = "synthesis_accessible_unstructured"
    thermodynamic_missing = "thermodynamic_missing"
    conductivity_missing = "conductivity_missing"


class JobPriority(Enum):
    critical = 1
    high = 2
    medium = 3
    low = 4


@dataclass
class BuildPriorityQueue:
    compositions: list[dict[str, Any]] = field(default_factory=list)

    def add(self, composition: str, gap_type: GapType, priority: JobPriority, **extra: Any) -> None:
        self.compositions.append({
            "composition": composition,
            "gap_type": gap_type.value,
            "priority": priority.value,
            "priority_label": priority.name,
            **extra,
        })

    def sort(self) -> list[dict[str, Any]]:
        self.compositions.sort(key=lambda x: (x["priority"], x.get("score", 0)))
        return self.compositions

    def __len__(self) -> int:
        return len(self.compositions)


def _load_survey_inventory(path: str | Path) -> dict[str, Any]:
    path = Path(path)
    if path.exists():
        return json.loads(path.read_text())
    return {}


def _load_literature_unmatched(path: str | Path) -> list[dict[str, Any]]:
    path = Path(path)
    if path.exists():
        return json.loads(path.read_text())
    return []


def compute_queue(
    survey_path: str | Path = "survey_output/source_inventory.json",
    literature_unmatched_path: str | Path = "literature_output/unmatched_compositions.json",
    family_targets: dict[str, int] | None = None,
) -> BuildPriorityQueue:
    queue = BuildPriorityQueue()
    survey = _load_survey_inventory(survey_path)
    unmatched = _load_literature_unmatched(literature_unmatched_path)

    for entry in unmatched:
        queue.add(
            composition=entry.get("composition", "unknown"),
            gap_type=GapType.unmatched_structure,
            priority=JobPriority.critical,
            source="literature_unmatched",
            doi=entry.get("doi", ""),
            reported_sigma=entry.get("sigma_RT"),
            reported_ea=entry.get("activation_energy_Ea"),
        )

    if family_targets:
        for family, target in family_targets.items():
            source_count = 0
            for src_name, src_data in survey.items():
                if isinstance(src_data, dict):
                    source_count += src_data.get(family, 0)
            if source_count < target:
                queue.add(
                    composition=f"{family}_family_gap",
                    gap_type=GapType.family_undersampled,
                    priority=JobPriority.high,
                    family=family,
                    current_count=source_count,
                    target_count=target,
                    deficit=target - source_count,
                )

    return queue
