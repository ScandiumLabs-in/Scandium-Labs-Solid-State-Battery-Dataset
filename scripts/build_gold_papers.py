#!/usr/bin/env python3
"""Build gold_papers.csv — scored, prioritized paper list for the Scandium Gold Dataset.

Scores every discovery candidate by the rubric:
    score = 4×benchmark material + 3×open access + 2×tables + 2×conductivity
          + 1×activation energy + 1×impedance plots

Fetches publication year from Crossref (batched, cached) and applies the
year >= 2016 filter. Writes gold_papers.csv ranked by score, plus keeps the
full scored set in literature_output/gold_scored.json.

Usage:
    python scripts/build_gold_papers.py                # score all candidates
    python scripts/build_gold_papers.py --refresh-years   # refetch years
"""

from __future__ import annotations

import argparse
import csv
import json
import re
import time
from pathlib import Path

import httpx

from dotenv import load_dotenv

load_dotenv()

from ssb_dataset.literature.benchmark_inventory import BENCHMARK_INVENTORY

ROOT = Path(__file__).resolve().parent.parent
CANDIDATES = ROOT / "literature_output/discovery_candidates.json"
YEAR_CACHE = ROOT / "literature_output/doi_years_cache.json"
OUT_CSV = ROOT / "gold_papers.csv"
OUT_SCORED = ROOT / "literature_output/gold_scored.json"

# Venues whose DOIs are reliably open-access (heuristic for the +3 OA term;
# final OA status is resolved at download time via Unpaywall/EuropePMC).
OA_DOI_PREFIXES = (
    "10.1038/s41467",      # Nature Communications
    "10.1038/s43246",      # Communications Materials
    "10.1126/sciadv",      # Science Advances
    "10.3390/",            # MDPI
    "10.3389/",            # Frontiers
    "10.1371/",            # PLOS
    "10.1080/",            # some Taylor & Francis OA
    "10.1021/acscentsci",  # ACS Central Science
)

YEAR_THRESHOLD = 2016


def benchmark_score(composition_hint: str, title: str, abstract: str) -> bool:
    """True if the paper mentions a benchmark-inventory material."""
    text = f"{composition_hint} {title} {abstract}".lower().replace(" ", "")
    for name in BENCHMARK_INVENTORY:
        n = name.lower().replace(" ", "")
        if n and (n in text or any(re.search(rf"\b{c}\b", text) for c in n.split("(")[0].split(","))):
            return True
    return False


def rubric_score(title: str, abstract: str, is_benchmark: bool, is_oa: bool) -> dict:
    text = f"{title} {abstract}".lower()
    score = 0.0
    breakdown = {}

    # 4 x benchmark material
    if is_benchmark:
        score += 4
        breakdown["benchmark"] = 4

    # 3 x open access (heuristic on DOI prefix)
    if is_oa:
        score += 3
        breakdown["oa"] = 3

    # 2 x contains tables (detected from phrases suggesting tabular data)
    has_table = bool(re.search(r"table\s+\d|summari[sz]ed in table|listed in table", text))
    if has_table:
        score += 2
        breakdown["tables"] = 2

    # 2 x conductivity values
    has_sigma = bool(re.search(r"conductivity|S cm[-\u2212]?\s?1|siemens|S/cm", text))
    if has_sigma:
        score += 2
        breakdown["conductivity"] = 2

    # 1 x activation energy
    has_ea = bool(re.search(r"activation energy|eV\b|arrhenius", text))
    if has_ea:
        score += 1
        breakdown["activation_energy"] = 1

    # 1 x impedance plots
    has_impedance = bool(re.search(r"impedance|nyquist|eis\b|eis\s", text))
    if has_impedance:
        score += 1
        breakdown["impedance"] = 1

    return {"score": score, "breakdown": breakdown,
            "has_table": has_table, "has_sigma": has_sigma,
            "has_ea": has_ea, "has_impedance": has_impedance}


def load_year_cache() -> dict:
    if YEAR_CACHE.exists():
        return json.loads(YEAR_CACHE.read_text())
    return {}


def fetch_year(doi: str, mailto: str, cache: dict) -> int | None:
    if doi in cache:
        return cache[doi]
    try:
        resp = httpx.get(
            f"https://api.crossref.org/works/{doi}",
            params={"mailto": mailto},
            timeout=20,
        )
        if resp.status_code == 200:
            data = resp.json().get("message", {})
            year = None
            ip = data.get("issued", {}).get("date-parts", [[None]])
            if ip and ip[0] and ip[0][0]:
                year = int(ip[0][0])
            elif data.get("published-print"):
                year = int(data["published-print"]["date-parts"][0][0])
            cache[doi] = year
            return year
        cache[doi] = None
    except Exception:
        cache[doi] = None
    return None


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--refresh-years", action="store_true")
    args = parser.parse_args()

    from ssb_dataset.config.settings import settings

    mailto = settings.crossref.mailto
    candidates = json.loads(CANDIDATES.read_text())
    year_cache = load_year_cache()

    if args.refresh_years:
        year_cache = {}

    scored_rows = []
    total = sum(len(v) for v in candidates.values())

    print(f"Scoring {total} candidates...")
    n = 0
    for fam, papers in candidates.items():
        for p in papers:
            n += 1
            doi = p["doi"]
            title = p.get("title", "")
            abstract = p.get("abstract", "")
            rel = p.get("relevance_score", 0.0)

            year = fetch_year(doi, mailto, year_cache)
            if (n % 25 == 0):
                YEAR_CACHE.write_text(json.dumps(year_cache))
            is_bench = benchmark_score("", title, abstract)
            is_oa = doi.startswith(OA_DOI_PREFIXES)
            rub = rubric_score(title, abstract, is_bench, is_oa)

            scored_rows.append({
                "doi": doi,
                "family": fam,
                "title": title,
                "year": year,
                "relevance": rel,
                "is_benchmark": is_bench,
                "is_oa_heuristic": is_oa,
                "score": rub["score"],
                "breakdown": rub["breakdown"],
                **{f"has_{k}": v for k, v in rub.items() if k in ("has_table", "has_sigma", "has_ea", "has_impedance")},
            })

    YEAR_CACHE.write_text(json.dumps(year_cache))

    # Apply year >= 2016 filter (keep rows with unknown year, flag them)
    for r in scored_rows:
        r["year_ok"] = r["year"] is None or r["year"] >= YEAR_THRESHOLD

    filtered = [r for r in scored_rows if r["year_ok"]]
    filtered.sort(key=lambda r: (r["is_benchmark"], r["score"], r["relevance"]), reverse=True)

    OUT_SCORED.write_text(json.dumps(filtered, indent=2))

    # Gold set: cap at 200 highest-scoring rows
    gold = filtered[:200]
    with open(OUT_CSV, "w", newline="") as f:
        writer = csv.DictWriter(
            f,
            fieldnames=["doi", "family", "title", "year", "score",
                        "is_benchmark", "is_oa_heuristic",
                        "has_table", "has_sigma", "has_ea", "has_impedance"],
        )
        writer.writeheader()
        for r in gold:
            writer.writerow({k: r.get(k) for k in writer.fieldnames})

    n_bench = sum(1 for r in gold if r["is_benchmark"])
    n_oa = sum(1 for r in gold if r["is_oa_heuristic"])
    print(f"Scored {len(scored_rows)}; kept {len(filtered)} with year>=2016; gold set = {len(gold)}")
    print(f"  benchmark mentions: {n_bench}   OA-heuristic: {n_oa}")
    print(f"  CSV -> {OUT_CSV}")


if __name__ == "__main__":
    main()
