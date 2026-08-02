from __future__ import annotations

from typing import Any


class EvidenceNode:
    def __init__(
        self,
        sentence: str,
        material: str,
        property_type: str,
        value: float,
        unit: str,
        source_type: str,
        source: str,
        section: str = "",
        is_primary: bool = False,
        confidence: float = 0.5,
        issues: list[str] | None = None,
    ):
        self.sentence = sentence
        self.material = material
        self.property_type = property_type
        self.value = value
        self.unit = unit
        self.source_type = source_type
        self.source = source
        self.section = section
        self.is_primary = is_primary
        self.confidence = confidence
        self.issues = issues or []

    def to_dict(self) -> dict[str, Any]:
        return {
            "sentence": self.sentence,
            "material": self.material,
            "property_type": self.property_type,
            "value": self.value,
            "unit": self.unit,
            "source_type": self.source_type,
            "source": self.source,
            "section": self.section,
            "is_primary": self.is_primary,
            "confidence": self.confidence,
            "issues": self.issues,
            "valid": len(self.issues) == 0,
        }

    def should_keep(self, primary_material: str = "") -> bool:
        if not self.is_primary:
            return False
        if self.source_type == "literature":
            return False
        if self.confidence < 0.3:
            return False
        if primary_material and self.material:
            if (self.material or "").lower() != primary_material.lower():
                return False
        return True

    def __repr__(self) -> str:
        return (
            f"EvidenceNode({self.property_type}: {self.value} {self.unit} "
            f"for {self.material}, type={self.source_type}, "
            f"sec={self.section}, conf={self.confidence:.2f})"
        )


class EvidenceGraph:
    def __init__(self, primary_material: str = ""):
        self.primary_material = primary_material
        self.nodes: list[EvidenceNode] = []

    def add_node(self, node: EvidenceNode) -> None:
        self.nodes.append(node)

    def add_raw(
        self,
        sentence: str,
        material: str,
        property_type: str,
        value: float,
        unit: str,
        source_type: str = "unknown",
        source: str = "",
        section: str = "",
        is_primary: bool = False,
        confidence: float = 0.5,
        issues: list[str] | None = None,
    ) -> EvidenceNode:
        node = EvidenceNode(
            sentence=sentence,
            material=material,
            property_type=property_type,
            value=value,
            unit=unit,
            source_type=source_type,
            source=source,
            section=section,
            is_primary=is_primary,
            confidence=confidence,
            issues=issues,
        )
        self.add_node(node)
        return node

    def filter_primary(self) -> list[EvidenceNode]:
        return [
            n for n in self.nodes
            if n.should_keep(self.primary_material)
        ]

    def filter_by_property(self, property_type: str) -> list[EvidenceNode]:
        return [n for n in self.nodes if n.property_type == property_type]

    def filter_by_source_type(self, source_type: str) -> list[EvidenceNode]:
        return [n for n in self.nodes if n.source_type == source_type]

    def filter_by_section(self, section_name: str) -> list[EvidenceNode]:
        return [n for n in self.nodes if section_name.lower() in n.section.lower()]

    def to_dicts(self) -> list[dict[str, Any]]:
        return [n.to_dict() for n in self.nodes]

    def __len__(self) -> int:
        return len(self.nodes)

    def summary(self) -> dict[str, Any]:
        n_primary = len(self.filter_primary())
        by_type: dict[str, int] = {}
        for n in self.nodes:
            by_type[n.property_type] = by_type.get(n.property_type, 0) + 1
        by_source: dict[str, int] = {}
        for n in self.nodes:
            by_source[n.source_type] = by_source.get(n.source_type, 0) + 1
        return {
            "total_nodes": len(self.nodes),
            "primary_nodes": n_primary,
            "by_property": by_type,
            "by_source_type": by_source,
        }

    def clear(self) -> None:
        self.nodes = []
