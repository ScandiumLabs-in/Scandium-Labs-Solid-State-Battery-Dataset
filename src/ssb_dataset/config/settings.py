"""Configuration management for the SSB dataset pipeline.

Credentials loaded from environment variables with .env file fallback.
Never commit credentials to the repo (see .gitignore for config/credentials*).
"""

from __future__ import annotations

import os
from dataclasses import dataclass, field
from pathlib import Path


def _env(key: str, default: str = "") -> str:
    return os.environ.get(key, default)


@dataclass
class MPSettings:
    api_key: str = field(default_factory=lambda: _env("MP_API_KEY"))


@dataclass
class SemanticScholarSettings:
    api_key: str = field(default_factory=lambda: _env("S2_API_KEY"))


@dataclass
class CrossrefSettings:
    mailto: str = field(default_factory=lambda: _env("CROSSREF_MAILTO", "user@scandiumlabs.com"))


@dataclass
class LLMSettings:
    provider: str = field(default_factory=lambda: _env("LLM_PROVIDER", "openai"))
    api_key: str = field(default_factory=lambda: _env("LLM_API_KEY", _env("OPENAI_API_KEY")))
    base_url: str = field(default_factory=lambda: _env("LLM_BASE_URL", "https://api.openai.com/v1"))
    model_triage: str = field(default_factory=lambda: _env("LLM_MODEL_TRIAGE", "gpt-4o-mini"))
    model_extraction: str = field(default_factory=lambda: _env("LLM_MODEL_EXTRACTION", "gpt-4o"))


@dataclass
class StorageSettings:
    staging_dir: Path = field(
        default_factory=lambda: Path(_env("SSB_STAGING_DIR", "staging"))
    )
    data_dir: Path = field(
        default_factory=lambda: Path(_env("SSB_DATA_DIR", "data"))
    )


@dataclass
class PipelineSettings:
    max_records_per_source: int = 0  # 0 = no limit
    batch_size: int = 100
    retry_attempts: int = 3


@dataclass
class Settings:
    mp: MPSettings = field(default_factory=MPSettings)
    semantic_scholar: SemanticScholarSettings = field(default_factory=SemanticScholarSettings)
    crossref: CrossrefSettings = field(default_factory=CrossrefSettings)
    llm: LLMSettings = field(default_factory=LLMSettings)
    storage: StorageSettings = field(default_factory=StorageSettings)
    pipeline: PipelineSettings = field(default_factory=PipelineSettings)


settings = Settings()
