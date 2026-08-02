#!/usr/bin/env python3
"""Fill Benchmark-100 gaps using OpenAlex (free, no key, ~10 req/s).

Semantic Scholar rate-limited several targeted searches to zero (garnet,
NASICON, antiperovskite variants). OpenAlex is a drop-in replacement for
title-verification discovery: query per composition, confirm the composition
string appears in the result title, and collect the DOI + OA status.

Usage:
    python scripts/discover_benchmark_openalex.py            # dry run
    python scripts/discover_benchmark_openalex.py --persist  # save + merge into inventory
"""

from __future__ import annotations

import json
import re
import time
from pathlib import Path

import httpx

ROOT = Path(__file__).resolve().parent.parent
API = "https://api.openalex.org/works"
OUT = ROOT / "literature_output/benchmark_target_openalex.json"
INVENTORY = ROOT / "src/ssb_dataset/literature/benchmark_inventory.py"

# Same canonical targets as the S2 discovery, minus ones already found.
# (Compositions already in the inventory are skipped at merge time anyway.)
TARGETS: dict[str, dict[str, dict]] = {
    "sulfide": {
        "Li4SnS4": {"sigma_S_per_cm": 1.4e-4, "Ea_eV": 0.35},
        "Li3.25Ge0.25P0.75S4": {"sigma_S_per_cm": 2.2e-3, "Ea_eV": 0.30},
        "Li3.833Sn0.833P0.167S4": {"sigma_S_per_cm": 2.0e-3, "Ea_eV": 0.30},
    },
    "garnet": {
        "Li6.4Ga0.2La3Zr2O12": {"sigma_S_per_cm": 1.3e-3, "Ea_eV": 0.30},
        "Li6.28Al0.24La3Zr2O12": {"sigma_S_per_cm": 6.0e-4, "Ea_eV": 0.32},
        "Li6.75La3Zr1.75Nb0.25O12": {"sigma_S_per_cm": 8.0e-4, "Ea_eV": 0.30},
        "Li7La3Zr2O12:Al": {"sigma_S_per_cm": 4.0e-4, "Ea_eV": 0.35},
    },
    "oxide": {
        "Li1.4Al0.4Ti1.6(PO4)3": {"sigma_S_per_cm": 3.4e-4, "Ea_eV": 0.32},
        "Li1.3Al0.3Ge1.7(PO4)3": {"sigma_S_per_cm": 2.0e-4, "Ea_eV": 0.30},
    },
    "nasicon": {
        "Li1.2Al0.2Ti1.8(PO4)3": {"sigma_S_per_cm": 2.0e-4, "Ea_eV": 0.32},
        "Li1.2Al0.2Ge1.8(PO4)3": {"sigma_S_per_cm": 3.0e-4, "Ea_eV": 0.30},
        "Li1.3Cr0.3Ti1.7(PO4)3": {"sigma_S_per_cm": 1.0e-3, "Ea_eV": 0.25},
        "Li1.3Sc0.3Ti1.7(PO4)3": {"sigma_S_per_cm": 8.0e-4, "Ea_eV": 0.26},
        "Li1.3Y0.3Ti1.7(PO4)3": {"sigma_S_per_cm": 5.0e-4, "Ea_eV": 0.28},
    },
    "halide": {
        "Li2YCl5": {"sigma_S_per_cm": 2.0e-4, "Ea_eV": 0.35},
        "Li6ZnCl8": {"sigma_S_per_cm": 1.0e-3, "Ea_eV": 0.33},
    },
    "antiperovskite": {
        "Li3SBr": {"sigma_S_per_cm": 1.5e-3, "Ea_eV": 0.25},
        "Li3OCl0.5Br0.5": {"sigma_S_per_cm": 2.0e-4, "Ea_eV": 0.30},
        "Li2OHCl0.5Br0.5": {"sigma_S_per_cm": 1.0e-4, "Ea_eV": 0.40},
    },
    "polymer_composite": {
        "PEO-LiFSI": {"sigma_S_per_cm": 1.0e-5, "Ea_eV": 0.60},
        "PVDF-HFP-LiTFSI": {"sigma_S_per_cm": 1.0e-3, "Ea_eV": 0.30},
    },
}


def norm(s: str) -> str:
    return re.sub(r"[^a-z0-9]", "", s.lower())


def is_subject(comp: str, title: str) -> bool:
    """The composition must be the subject of the title, not an incidental
    mention. Rules:
      - composition appears in the normalized title, AND
      - the composition match starts in the first half of the title (it leads
        the sentence), AND
      - it is not preceded by a passive-mention phrase like 'using a', 'with',
        'employing', 'for', 'in a' (composition-as-ingredient patterns).
    """
    tn = norm(title)
    cn = norm(comp)
    idx = tn.find(cn)
    if idx < 0:
        return False
    if idx > len(tn) / 2:
        return False
    prefix = tn[:idx]
    for bad in ("usinga", "using", "with", "employing", "infree-standing", "inalithium", "hybrid", "composite"):
        if prefix.endswith(bad):
            return False
    return True


def search_openalex(term: str) -> list[dict]:
    """Search OpenAlex works by title/abstract text; return top results."""
    params = {
        "search": term,
        "per-page": 8,
        "select": "id,doi,title,publication_year,open_access,type",
        "mailto": "scandium-labs@example.com",
    }
    try:
        r = httpx.get(API, params=params, timeout=25)
        if r.status_code == 200:
            return r.json().get("results", [])
    except Exception:
        pass
    return []


def main() -> None:
    import argparse

    parser = argparse.ArgumentParser()
    parser.add_argument("--persist", action="store_true")
    args = parser.parse_args()

    # Skip compositions already in the inventory
    inv_src = INVENTORY.read_text()
    existing = set(re.findall(r'^    "([^"]+)":', inv_src, re.M))

    out: dict[str, dict] = {}
    n_found = 0
    for family, comps in TARGETS.items():
        out[family] = {}
        for comp, spec in comps.items():
            if comp in existing:
                print(f"  {family:14s} {comp:34s} already-in-inventory")
                continue
            comp_n = norm(comp)
            best = None
            # try a couple of query formulations
            queries = [f'"{comp}" solid electrolyte', comp, f"{comp} ionic conductivity"]
            for q in queries:
                for w in search_openalex(q):
                    title = w.get("title") or ""
                    if is_subject(comp, title):
                        best = {
                            "doi": w.get("doi", "").replace("https://doi.org/", ""),
                            "title": title,
                            "year": w.get("publication_year"),
                            "oa": bool((w.get("open_access") or {}).get("is_oa")),
                            "oa_url": (w.get("open_access") or {}).get("oa_url"),
                        }
                        break
                if best:
                    break
                time.sleep(0.4)
            if best and best["doi"]:
                out[family][comp] = {**spec, **best}
                n_found += 1
                oa = "OA" if best["oa"] else "--"
                print(f"  {family:14s} {comp:34s} {oa} {best['doi']}")
            else:
                print(f"  {family:14s} {comp:34s} -- not found on OpenAlex")
            time.sleep(0.5)

    if args.persist:
        OUT.write_text(json.dumps(out, indent=2))
        print(f"\nSaved to {OUT} ({n_found} compositions with DOIs)")


if __name__ == "__main__":
    main()
