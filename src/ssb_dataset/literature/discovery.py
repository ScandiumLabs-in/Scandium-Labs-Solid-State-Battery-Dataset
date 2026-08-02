from __future__ import annotations

import random
from dataclasses import dataclass, field
from pathlib import Path
from time import sleep
from typing import Any

import httpx

from ssb_dataset.schema import Family


@dataclass
class PaperCandidate:
    doi: str
    title: str
    abstract: str
    relevance_score: float
    family_tags: list[Family] = field(default_factory=list)


SEARCH_TERMS: dict[Family, list[str]] = {
    Family.sulfide: [
        "Li6PS5X solid electrolyte ionic conductivity",
        "sulfide lithium solid electrolyte conductivity",
        "thio-LISICON conductivity",
    ],
    Family.oxide: [
        "oxide lithium solid electrolyte ionic conductivity",
        "Li garnet-free oxide electrolyte conductivity",
    ],
    Family.garnet: [
        "LLZO garnet lithium ionic conductivity",
        "Li7La3Zr2O12 solid electrolyte conductivity",
    ],
    Family.perovskite: [
        "LLTO perovskite lithium ionic conductivity",
        "Li3xLa2/3-xTiO3 solid electrolyte",
    ],
    Family.nasicon: [
        "LATP nasicon lithium ionic conductivity",
        "Li1+xAlxTi2-x(PO4)3 solid electrolyte",
    ],
    Family.halide: [
        "Li3InCl6 halide solid electrolyte conductivity",
        "Li3YCl6 lithium halide ionic conductivity",
    ],
    Family.argyrodite: [
        "Li6PS5Cl argyrodite ionic conductivity",
        "argyrodite solid electrolyte lithium",
    ],
    Family.hydride: [
        "LiH complex hydride ion conductor",
        "complex hydride lithium ionic conductivity",
    ],
    Family.borohydride: [
        "LiBH4 borohydride ionic conductivity",
        "lithium borohydride solid electrolyte",
    ],
    Family.antiperovskite: [
        "Li3OCl antiperovskite ionic conductivity",
        "Li-rich antiperovskite solid electrolyte",
    ],
    Family.polymer_composite: [
        "PEO composite polymer electrolyte conductivity",
        "polymer ceramic composite solid electrolyte",
    ],
}

RELEVANCE_KEYWORDS = [
    "ionic conductivity",
    "solid electrolyte",
    "lithium ion",
    "Li-ion",
    "activation energy",
    "S cm",
    "siemens",
    "electrochemical",
    "impedance",
    "arrhenius",
]

API_BASE = "https://api.semanticscholar.org/graph/v1/paper/search"


def compute_relevance(title: str, abstract: str | None) -> float:
    text = ((title or "") + " " + (abstract or "")).lower()
    score = 0.0
    for kw in RELEVANCE_KEYWORDS:
        if kw.lower() in text:
            score += 1.0
    return score / max(len(RELEVANCE_KEYWORDS), 1)


def triage_candidates(raw: list[dict[str, Any]]) -> list[PaperCandidate]:
    candidates: list[PaperCandidate] = []
    for item in raw:
        ext_ids = item.get("externalIds", {}) or {}
        doi = ext_ids.get("DOI", "")
        title = item.get("title", "") or ""
        abstract = item.get("abstract")
        if not doi or not title:
            continue
        relevance = compute_relevance(title, abstract) if abstract else 0.0
        if relevance >= 0.2:
            candidates.append(
                PaperCandidate(
                    doi=doi,
                    title=title,
                    abstract=abstract or "",
                    relevance_score=relevance,
                )
            )
    return sorted(candidates, key=lambda c: c.relevance_score, reverse=True)


def _search_term(
    term: str,
    headers: dict[str, str],
    max_results: int,
    max_retries: int = 3,
) -> list[dict[str, Any]]:
    for attempt in range(max_retries):
        try:
            resp = httpx.get(
                API_BASE,
                params={
                    "query": term,
                    "limit": min(max_results, 100),
                    "fields": "title,abstract,externalIds",
                },
                headers=headers,
                timeout=15,
            )
            if resp.status_code == 429:
                wait = 2 ** (attempt + 2) + random.uniform(0, 3)
                print(f"  Rate limited. Backing off {wait:.0f}s...")
                sleep(wait)
                continue
            if resp.status_code == 200:
                data = resp.json()
                return data.get("data", [])
            return []
        except httpx.TimeoutException:
            if attempt == max_retries - 1:
                return []
            sleep(2 ** attempt * 2 + random.uniform(0, 1))
        except httpx.HTTPStatusError:
            return []
        except Exception:
            return []
    return []


def _paper_to_dict(p: PaperCandidate) -> dict[str, Any]:
    return {
        "doi": p.doi,
        "title": p.title,
        "abstract": p.abstract,
        "relevance_score": p.relevance_score,
        "family_tags": [f.value for f in p.family_tags],
    }


def save_discovery_results(
    results: dict[Family, list[PaperCandidate]],
    output_dir: str | Path = "literature_output",
) -> Path:
    """Persist full discovery results to a JSON file (not just counts)."""
    output_dir = Path(output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)
    path = output_dir / "discovery_candidates.json"
    data = {
        fam.value: [_paper_to_dict(p) for p in papers]
        for fam, papers in results.items()
    }
    import json
    path.write_text(json.dumps(data, indent=2))
    print(f"Saved {sum(len(v) for v in data.values())} candidate papers to {path}")
    return path


def run_discovery(
    api_key: str | None = None,
    max_results_per_family: int = 100,
    max_retries: int = 3,
    persist: bool = True,
) -> dict[Family, list[PaperCandidate]]:
    results: dict[Family, list[PaperCandidate]] = {}

    headers = {}
    if api_key:
        headers["x-api-key"] = api_key

    total_terms = sum(len(terms) for terms in SEARCH_TERMS.values())
    term_idx = 0

    for family, terms in SEARCH_TERMS.items():
        all_papers: list[dict[str, Any]] = []
        for term in terms:
            term_idx += 1
            papers = _search_term(term, headers, max_results_per_family, max_retries)
            all_papers.extend(papers)
            print(f"  [{term_idx}/{total_terms}] {family.value}: '{term[:50]}' → {len(papers)} papers")

        candidates = triage_candidates(all_papers)
        results[family] = candidates[:max_results_per_family]

    if persist:
        save_discovery_results(results)

    return results
