"""Phase E4/E8 — deficit-weighted discovery + consensus-growth queue tests."""

from __future__ import annotations

import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "scripts"))


class TestPrioritizeDiscovery:
    def test_deficit_ranks_under_target_family_first(self) -> None:
        from prioritize_discovery import build_queue
        report = {"family_distribution": {
            "polymer_composite": 100,  # wildly over-supplied
            "sulfide": 1,              # starved
            "garnet": 5,
            "oxide": 2,
            "halide": 2,
        }}
        queue = build_queue(report)
        assert queue[0]["family"] == "sulfide" or queue[0]["deficit"] >= queue[1]["deficit"]
        sulfide = next(e for e in queue if e["family"] == "sulfide")
        assert sulfide["deficit"] > 0

    def test_sulfide_family_gets_targeted_queries(self) -> None:
        from prioritize_discovery import build_queue, SULFIDE_QUERIES
        queue = build_queue({"family_distribution": {"sulfide": 1, "oxide": 1}})
        sulfide = next(e for e in queue if e["family"] == "sulfide")
        assert sulfide["queries"] == SULFIDE_QUERIES
        assert any("Li6PS5Cl" in q for q in sulfide["queries"])

    def test_ranks_are_sorted_desc_by_deficit(self) -> None:
        from prioritize_discovery import build_queue
        report = {"family_distribution": {
            "oxide": 2, "sulfide": 1, "hydride": 3, "garnet": 8, "halide": 2,
            "polymer_composite": 9, "nasicon": 3, "perovskite": 2,
            "argyrodite": 1, "borohydride": 2, "antiperovskite": 2,
        }}
        queue = build_queue(report)
        deficits = [e["deficit"] for e in queue]
        assert deficits == sorted(deficits, reverse=True)


class TestPrioritizeConsensus:
    def _consensus(self) -> dict:
        return {
            "Li6PS5Cl": {"n_papers": 5, "families": ["argyrodite"]},
            "Li3PS4": {"n_papers": 1, "families": ["sulfide"]},
            "SomeExotic": {"n_papers": 1, "families": ["oxide"]},
            "Zero": {"n_papers": 0, "families": ["unknown"]},
        }

    def test_priority_benchmarks_first(self) -> None:
        from prioritize_consensus_growth import prioritize
        targets = prioritize(self._consensus())
        assert targets[0]["material"] == "Li6PS5Cl"   # priority + already n≥3
        assert targets[0]["is_priority_benchmark"] is True
        first_non_priority = next(t for t in targets if not t["is_priority_benchmark"])
        assert first_non_priority["material"] == "SomeExotic"

    def test_additions_needed_and_query(self) -> None:
        from prioritize_consensus_growth import prioritize
        targets = prioritize(self._consensus(), target_n=3)
        lp = next(t for t in targets if t["material"] == "Li3PS4")
        assert lp["additions_needed"] == 2
        assert "Li3PS4" in lp["query"]

    def test_zero_paper_materials_excluded(self) -> None:
        from prioritize_consensus_growth import prioritize
        targets = prioritize(self._consensus())
        assert all(t["material"] != "Zero" for t in targets)
