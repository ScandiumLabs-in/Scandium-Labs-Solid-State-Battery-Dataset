"""Phase E6 — extraction-model benchmark scoring tests (no LLM/network)."""

from __future__ import annotations

import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "scripts"))

from benchmark_extraction_model import sigma_match  # noqa: E402


class TestSigmaMatch:
    def test_exact_sigma(self) -> None:
        assert sigma_match(1.187e-3, 1.187e-3)

    def test_within_35_pct(self) -> None:
        assert sigma_match(1.3e-3, 1.187e-3)

    def test_unit_multiplier_applied(self) -> None:
        # expected mS/cm (unit_multiplier 1e-3 when stored in S/cm)
        assert sigma_match(1.187, 1.187e-3, unit_mult=1e3)

    def test_outside_tolerance_rejected(self) -> None:
        assert not sigma_match(2.0e-3, 1.187e-3, unit_mult=1.0)   # ~68% off
        assert not sigma_match(1.187e-4, 1.187e-3)                # 10x off