from __future__ import annotations

import json
from datetime import datetime, timezone
from enum import Enum
from pathlib import Path
from typing import Any


class JobStatus(Enum):
    PENDING = "pending"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"
    RETRYING = "retrying"
    SKIPPED = "skipped"


class JobMonitor:
    """Track job status across the DFT compute pipeline."""

    def __init__(self, log_path: str | Path | None = None) -> None:
        self.jobs: dict[str, dict[str, Any]] = {}
        self.log_path = Path(log_path) if log_path else None

    def register_job(self, name: str, **metadata: Any) -> None:
        self.jobs[name] = {
            "name": name,
            "status": JobStatus.PENDING.value,
            "attempts": 0,
            "created_at": datetime.now(timezone.utc).isoformat(),
            "updated_at": datetime.now(timezone.utc).isoformat(),
            "error": None,
            **metadata,
        }

    def update_job(
        self,
        name: str,
        status: JobStatus,
        error: str | None = None,
        attempt: int | None = None,
    ) -> None:
        if name not in self.jobs:
            self.register_job(name)
        self.jobs[name]["status"] = status.value
        self.jobs[name]["updated_at"] = datetime.now(timezone.utc).isoformat()
        if error:
            self.jobs[name]["error"] = error
        if attempt is not None:
            self.jobs[name]["attempts"] = attempt
        elif status == JobStatus.RETRYING:
            self.jobs[name]["attempts"] += 1
        self._maybe_log()

    def summary(self) -> dict[str, int]:
        counts: dict[str, int] = {}
        for job in self.jobs.values():
            s = job["status"]
            counts[s] = counts.get(s, 0) + 1
        return counts

    def failures(self) -> list[dict[str, Any]]:
        return [j for j in self.jobs.values() if j["status"] == JobStatus.FAILED.value]

    def completed(self) -> list[dict[str, Any]]:
        return [j for j in self.jobs.values() if j["status"] == JobStatus.COMPLETED.value]

    @property
    def success_rate(self) -> float:
        if not self.jobs:
            return 0.0
        total = len(self.jobs)
        completed = len(self.completed()) + len(self.failures())
        if completed == 0:
            return 0.0
        return len(self.completed()) / completed

    def _maybe_log(self) -> None:
        if self.log_path:
            self.log_path.parent.mkdir(parents=True, exist_ok=True)
            self.log_path.write_text(self.to_json(indent=2))

    def to_json(self, indent: int = None) -> str:
        data = {
            "summary": self.summary(),
            "success_rate": self.success_rate,
            "jobs": list(self.jobs.values()),
        }
        return json.dumps(data, indent=indent)
