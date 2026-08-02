#!/usr/bin/env python3
"""Targeted discovery for Benchmark-100: search Semantic Scholar for each
canonical composition, collect real DOIs, and (optionally) grow the inventory.

Unlike build_gold_papers.py (which scores the existing candidate pool), this
searches S2 directly per composition so we can find DOIs for materials that
never appeared in the generic family queries.

Usage:
    python scripts/discover_benchmark_targets.py              # search, print results
    python scripts/discover_benchmark_targets.py --persist   # save to literature_output/
"""

from __future__ import annotations

import json
import os
import time
from pathlib import Path

import httpx

from dotenv import load_dotenv

load_dotenv()

ROOT = Path(__file__).resolve().parent.parent
API_BASE = "https://api.semanticscholar.org/graph/v1/paper/search"
OUT = ROOT / "literature_output/benchmark_target_discovery.json"

# Canonical solid electrolytes we want in Benchmark-100, keyed by family.
# Each entry: composition -> canonical sigma (S/cm) + Ea (eV) + search terms.
# Values are verification targets from the literature (flagged as targets).
BENCHMARK_TARGETS: dict[str, dict[str, dict]] = {
    "sulfide": {
        "Li7P3S11": {"sigma_S_per_cm": 1.7e-2, "Ea_eV": 0.18, "q": ["Li7P3S11 glass-ceramic conductivity"]},
        "Li10SnP2S12": {"sigma_S_per_cm": 1.4e-2, "Ea_eV": 0.24, "q": ["Li10SnP2S12"]},
        "Li4SnS4": {"sigma_S_per_cm": 1.4e-4, "Ea_eV": 0.35, "q": ["Li4SnS4 solid electrolyte"]},
        "Li3.833Sn0.833P0.167S4": {"sigma_S_per_cm": 2.0e-3, "Ea_eV": 0.30, "q": ["thio-LISICON Li3.833Sn0.833P0.167S4"]},
        "Li3.25Ge0.25P0.75S4": {"sigma_S_per_cm": 2.2e-3, "Ea_eV": 0.30, "q": ["Li3.25Ge0.25P0.75S4 thio-LISICON"]},
        "Li9.54Si1.74P1.44S11.7Cl0.3": {"sigma_S_per_cm": 2.5e-2, "Ea_eV": 0.20, "q": ["Li9.54Si1.74P1.44S11.7Cl0.3"]},
        "Li6.6P0.4Ge0.6S5I": {"sigma_S_per_cm": 2.0e-2, "Ea_eV": 0.17, "q": ["Li6.6P0.4Ge0.6S5I"]},
        "Li6PS5Cl0.5Br0.5": {"sigma_S_per_cm": 1.2e-2, "Ea_eV": 0.27, "q": ["Li6PS5Cl0.5Br0.5"]},
    },
    "oxide": {
        "Li0.34La0.51TiO2.94": {"sigma_S_per_cm": 1.4e-3, "Ea_eV": 0.28, "q": ["LLTO Li0.34La0.51TiO2.94"]},
        "Li1.4Al0.4Ti1.6(PO4)3": {"sigma_S_per_cm": 3.4e-4, "Ea_eV": 0.32, "q": ["Li1.4Al0.4Ti1.6(PO4)3"]},
        "Li1.5Al0.5Ge1.5(PO4)3": {"sigma_S_per_cm": 4.0e-4, "Ea_eV": 0.32, "q": ["LAGP Li1.5Al0.5Ge1.5(PO4)3"]},
        "Li1.3Al0.3Ge1.7(PO4)3": {"sigma_S_per_cm": 2.0e-4, "Ea_eV": 0.30, "q": ["Li1.3Al0.3Ge1.7(PO4)3"]},
        "Li2O-B2O3-SiO2": {"sigma_S_per_cm": 1.0e-6, "Ea_eV": 0.80, "q": ["lithium oxide glass solid electrolyte conductivity"]},
    },
    "garnet": {
        "Li6.4Ga0.2La3Zr2O12": {"sigma_S_per_cm": 1.3e-3, "Ea_eV": 0.30, "q": ["Ga-doped LLZO"]},
        "Li6.28Al0.24La3Zr2O12": {"sigma_S_per_cm": 6.0e-4, "Ea_eV": 0.32, "q": ["Al-doped LLZO Li6.28Al0.24La3Zr2O12"]},
        "Li6.75La3Zr1.75Nb0.25O12": {"sigma_S_per_cm": 8.0e-4, "Ea_eV": 0.30, "q": ["Nb-doped LLZO"]},
        "Li7La3Zr2O12:Al": {"sigma_S_per_cm": 4.0e-4, "Ea_eV": 0.35, "q": ["Al stabilized LLZO conductivity"]},
    },
    "halide": {
        "Li3ErCl6": {"sigma_S_per_cm": 3.0e-4, "Ea_eV": 0.38, "q": ["Li3ErCl6"]},
        "Li3HoCl6": {"sigma_S_per_cm": 1.0e-3, "Ea_eV": 0.32, "q": ["Li3HoCl6"]},
        "Li3YCl3Br3": {"sigma_S_per_cm": 1.0e-3, "Ea_eV": 0.33, "q": ["Li3YCl3Br3"]},
        "Li2YCl5": {"sigma_S_per_cm": 2.0e-4, "Ea_eV": 0.35, "q": ["Li2YCl5"]},
        "Li6ZnCl8": {"sigma_S_per_cm": 1.0e-3, "Ea_eV": 0.33, "q": ["Li6ZnCl8"]},
    },
    "nasicon": {
        "Li1.2Al0.2Ti1.8(PO4)3": {"sigma_S_per_cm": 2.0e-4, "Ea_eV": 0.32, "q": ["Li1.2Al0.2Ti1.8(PO4)3"]},
        "Li1.2Al0.2Ge1.8(PO4)3": {"sigma_S_per_cm": 3.0e-4, "Ea_eV": 0.30, "q": ["Li1.2Al0.2Ge1.8(PO4)3"]},
        "Li1.3Cr0.3Ti1.7(PO4)3": {"sigma_S_per_cm": 1.0e-3, "Ea_eV": 0.25, "q": ["Cr-doped LATP"]},
        "Li1.3Sc0.3Ti1.7(PO4)3": {"sigma_S_per_cm": 8.0e-4, "Ea_eV": 0.26, "q": ["Sc-doped LATP"]},
        "Li1.3Y0.3Ti1.7(PO4)3": {"sigma_S_per_cm": 5.0e-4, "Ea_eV": 0.28, "q": ["Y-doped LATP"]},
    },
    "hydride": {
        "LiBH4-LiCl": {"sigma_S_per_cm": 1.0e-4, "Ea_eV": 0.55, "q": ["LiBH4-LiCl"]},
        "LiBH4-SiO2": {"sigma_S_per_cm": 1.0e-4, "Ea_eV": 0.50, "q": ["LiBH4 SiO2"]},
        "Li2B10H10": {"sigma_S_per_cm": 1.0e-3, "Ea_eV": 0.30, "q": ["Li2B10H10"]},
    },
    "polymer_composite": {
        "PEO-LiFSI": {"sigma_S_per_cm": 1.0e-5, "Ea_eV": 0.60, "q": ["PEO LiFSI polymer electrolyte"]},
        "PEO-LiClO4": {"sigma_S_per_cm": 1.0e-6, "Ea_eV": 1.00, "q": ["PEO LiClO4 electrolyte conductivity"]},
        "PVDF-HFP-LiTFSI": {"sigma_S_per_cm": 1.0e-3, "Ea_eV": 0.30, "q": ["PVDF-HFP LiTFSI"]},
        "PAN-LiClO4": {"sigma_S_per_cm": 1.0e-3, "Ea_eV": 0.30, "q": ["PAN LiClO4 solid polymer electrolyte"]},
    },
    "antiperovskite": {
        "Li3SBr": {"sigma_S_per_cm": 1.5e-3, "Ea_eV": 0.25, "q": ["Li3SBr antiperovskite"]},
        "Li3OCl0.5Br0.5": {"sigma_S_per_cm": 2.0e-4, "Ea_eV": 0.30, "q": ["Li3OCl0.5Br0.5"]},
        "Li2OHCl0.5Br0.5": {"sigma_S_per_cm": 1.0e-4, "Ea_eV": 0.40, "q": ["Li2OHCl0.5Br0.5"]},
    },
}


def search_s2(term: str, api_key: str) -> list[dict]:
    headers = {"x-api-key": api_key} if api_key else {}
    for attempt in range(3):
        try:
            r = httpx.get(
                API_BASE,
                params={"query": term, "limit": 5, "fields": "title,externalIds,year"},
                headers=headers,
                timeout=20,
            )
            if r.status_code == 200:
                return r.json().get("data", [])
            if r.status_code == 429:
                time.sleep(2 ** (attempt + 2))
                continue
            return []
        except Exception:
            time.sleep(2)
    return []


def main() -> None:
    import argparse

    parser = argparse.ArgumentParser()
    parser.add_argument("--persist", action="store_true")
    args = parser.parse_args()

    api_key = os.environ.get("S2_API_KEY", "")
    out: dict[str, dict] = {}

    for family, comps in BENCHMARK_TARGETS.items():
        out[family] = {}
        for comp, spec in comps.items():
            best = None
            for q in spec.get("q", []):
                papers = search_s2(q, api_key)
                # pick the paper whose title contains the composition
                comp_n = comp.lower().replace(" ", "")
                for p in papers:
                    title_n = (p.get("title") or "").lower().replace(" ", "")
                    if comp_n in title_n:
                        best = {"doi": (p.get("externalIds") or {}).get("DOI"),
                                "title": p.get("title"), "year": p.get("year")}
                        break
                if best:
                    break
                time.sleep(0.5)
            if best and best["doi"]:
                out[family][comp] = {**spec, "doi": best["doi"], "title": best["title"]}
                print(f"  {family:18s} {comp:32s} {best['doi']}")
            else:
                print(f"  {family:18s} {comp:32s} -- not found")
            time.sleep(0.8)

    if args.persist:
        OUT.write_text(json.dumps(out, indent=2))
        print(f"\nSaved to {OUT}")


if __name__ == "__main__":
    main()
