"""Base classes for per-source connectors.

Every source connector inherits from BaseSourceConnector and implements:
- connect(): authenticate and establish session
- fetch_records(): generator yielding raw records
- to_material_record(): normalize a raw record into the unified schema
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from collections.abc import Generator
from typing import Any

from ssb_dataset.schema import MaterialRecord


class BaseSourceConnector(ABC):
    source_db: str = ""

    def __init__(self) -> None:
        self._connected = False

    @abstractmethod
    def connect(self) -> None:
        ...

    @abstractmethod
    def fetch_records(self, **kwargs: Any) -> Generator[dict[str, Any], None, None]:
        ...

    @abstractmethod
    def to_material_record(self, raw: dict[str, Any]) -> MaterialRecord:
        ...

    def ingest(
        self, **kwargs: Any
    ) -> Generator[MaterialRecord, None, None]:
        if not self._connected:
            self.connect()
        for raw in self.fetch_records(**kwargs):
            yield self.to_material_record(raw)
