"""Cross-paper consensus database (Scandium Stage 3 / M5).

Builds the per-material "community consensus" from every verified label in the
pipeline: the review queue's approved records, the canonical dataset's verified
experimental labels, and the benchmark inventory. For each material it persists:

  - publication count, record count (σ + Ea separately)
  - median σ and Ea (log10-space for σ), min/max, geometric spread
  - approximate 95% confidence interval on the median (log10-space)
  - temperature histogram (when records carry measurement temperature)
  - DOI list of every contributing paper
  - outlier records (>1.5 orders from the group median, n>=3)

This is the queryable knowledge base: given any new extracted record, look up
the material's consensus to instantly see whether the value is believable.
Statistical only — never edits values.

Sources (dedup by review_id / material+DOI+value):
  1. review queue approved records  (review_output/queue.json, status=approved)
  2. canonical dataset verified labels (cleaning_output/canonical_dataset.parquet
     where ion_transport.label_available)
  3. benchmark inventory (src/ssb_dataset/literature/benchmark_inventory.py)

Usage:
    python scripts/build_consensus_db.py
        # writes literature_output/consensus_db.parquet + consensus_db.json
"""

from __future__ import annotations

import json
import math
from collections import defaultdict
from dataclasses import dataclass, field
from pathlib import Path
from statistics import median
from typing import Any

import numpy as np

from ssb_dataset.pipeline.fingerprint import group_key
from ssb_dataset.pipeline.normalization import normalize_ea, normalize_sigma

ROOT = Path(__file__).resolve().parent.parent.parent.parent

# Order-of-magnitude outlier threshold (log10 units) — matches consensus.py.
MAX_ORDER_SPREAD = 1.5
# Fewer sigma records than this -> no consensus range, only spread check.
MIN_N_FOR_CONSENSUS = 3


@dataclass
class ConsensusRecord:
    """Aggregated cross-paper statistics for one material group."""

    group: str = ""
    n_papers: int = 0
    n_sigma: int = 0
    n_ea: int = 0
    sigma_values: list[float] = field(default_factory=list)
    ea_values: list[float] = field(default_factory=list)
    median_sigma: float | None = None
    sigma_ci95: tuple[float, float] | None = None
    min_sigma: float | None = None
    max_sigma: float | None = None
    sigma_mad_log10: float | None = None
    sigma_std_log10: float | None = None
    sigma_iqr_log10: float | None = None
    agreement_grade: str = ""
    sigma_by_temp: list[dict] = field(default_factory=list)
    median_ea: float | None = None
    doiss: list[str] = field(default_factory=list)
    outliers: list[dict] = field(default_factory=list)
    temp_bins: list[dict] = field(default_factory=list)
    families: list[str] = field(default_factory=list)
    publication_years: list[int] = field(default_factory=list)
    journals: list[str] = field(default_factory=list)
    method_distribution: list[dict] = field(default_factory=list)
    pressure_distribution: list[dict] = field(default_factory=list)
    density_distribution: list[dict] = field(default_factory=list)
    # Preserved measurement-level detail — the Material → Paper → Experiment →
    # Measurement → Evidence hierarchy. Every contributing record keeps its own
    # value, unit, temperature, DOI, reviewer, page, sentence and method rather
    # than being collapsed into the aggregates above.
    measurements: list[dict] = field(default_factory=list)

    def to_dict(self, with_measurements: bool = True) -> dict[str, Any]:
        out = {
            "group": self.group,
            "n_papers": self.n_papers,
            "n_sigma": self.n_sigma,
            "n_ea": self.n_ea,
            "median_sigma": self.median_sigma,
            "sigma_ci95": self.sigma_ci95,
            "min_sigma": self.min_sigma,
            "max_sigma": self.max_sigma,
            "sigma_mad_log10": self.sigma_mad_log10,
            "sigma_std_log10": self.sigma_std_log10,
            "sigma_iqr_log10": self.sigma_iqr_log10,
            "agreement_grade": self.agreement_grade,
            "sigma_by_temp": self.sigma_by_temp,
            "median_ea": self.median_ea,
            "dois": sorted(set(self.doiss)),
            "outliers": self.outliers,
            "temperature_histogram": self.temp_bins,
            "families": sorted(set(self.families)),
            "publication_years": sorted(set(p for p in self.publication_years if p)),
            "journals": sorted(set(j for j in self.journals if j)),
            "method_distribution": self.method_distribution,
            "pressure_distribution": self.pressure_distribution,
            "density_distribution": self.density_distribution,
        }
        if with_measurements:
            out["measurements"] = self.measurements
        return out


def _log_ci(values: list[float]) -> tuple[float, float] | None:
    """Approx 95% CI on the median of a small log10 sample."""
    logs = np.log10([v for v in values if v and v > 0])
    if len(logs) < 3:
        return None
    lo = float(np.percentile(logs, 2.5))
    hi = float(np.percentile(logs, 97.5))
    return (10**lo, 10**hi)


def _log_stats(values: list[float]) -> tuple[float | None, float | None, float | None]:
    """MAD, std, IQR of the log10 spread. None for <2 samples."""
    logs = [math.log10(v) for v in values if v and v > 0]
    if len(logs) < 2:
        return (None, None, None)
    med = float(median(logs))
    mad = float(median(abs(l - med) for l in logs))
    std = float(np.std(logs))
    q1, q3 = float(np.percentile(logs, 25)), float(np.percentile(logs, 75))
    iqr = q3 - q1
    return (mad, std, iqr)


def _sigma_by_temp(measurements: list[dict]) -> list[dict]:
    """Per-temperature-bin median σ (log10-space), so 25°C and 80°C values are
    never compared against each other. Bins are 25°C wide; only bins with >=1
    σ-bearing measurement are emitted."""
    bins: dict[int, list[float]] = defaultdict(list)
    for m in measurements:
        s = m.get("sigma_S_per_cm")
        t = _normalize_temp(m.get("temperature_celsius"))
        if s is None or t is None:
            continue
        try:
            s = float(s)
        except (TypeError, ValueError):
            continue
        key = int(round(t / 25.0)) * 25
        bins[key].append(s)
    out = []
    for k in sorted(bins):
        logs = [math.log10(v) for v in bins[k] if v and v > 0]
        if not logs:
            continue
        out.append({
            "temp_c": k,
            "n": len(logs),
            "median_sigma": float(10 ** median(logs)),
            "min_sigma": float(10 ** min(logs)),
            "max_sigma": float(10 ** max(logs)),
        })
    return out


def _agreement_grade(values: list[float]) -> str:
    """Letter grade for cross-paper agreement (A+..D).

    Uses log10 spread relative to the median:
      A+  n>=3, all within 0.2 log10 (~1.6x) of median
      A   n>=3, all within 0.5 log10 (~3x) of median
      B   n>=2, all within 0.7 log10 (~5x) of median
      C   n>=2, spread < 1.0 log10 (~10x), or n==1
      D   anything else (spread >= 1 order or inconsistent)
    """
    logs = [math.log10(v) for v in values if v and v > 0]
    n = len(logs)
    if n == 0:
        return ""
    med = float(median(logs))
    max_dev = max(abs(l - med) for l in logs)
    if n >= 3 and max_dev <= 0.2:
        return "A+"
    if n >= 3 and max_dev <= 0.5:
        return "A"
    if n >= 2 and max_dev <= 0.7:
        return "B"
    if n >= 2 and max_dev <= 1.0:
        return "C"
    if n == 1:
        return "C"
    return "D"


def _temp_bins(temps_c: list[float | None]) -> list[dict]:
    """Histogram of measurement temperatures in °C (50°C bins, -50..400)."""
    bins = defaultdict(int)
    for t in temps_c:
        if t is None:
            continue
        try:
            t = float(t)
        except (TypeError, ValueError):
            continue
        key = int(t // 50) * 50
        bins[key] += 1
    return [{"bin_c": k, "count": v} for k, v in sorted(bins.items())]


def _value_distribution(measurements: list[dict], field: str) -> list[dict]:
    """Count distinct reported values of an experimental field (pressure, density,
    method) across a group's measurements. Used to surface how *diverse* the
    experimental conditions are — a group measured only under one condition is
    weaker than one measured across a range. Numeric values are preserved as
    numbers (so 300 MPa and 300.0 MPa collapse); strings are kept as-is."""
    counts: dict[str, tuple[int, Any]] = defaultdict(lambda: (0, None))
    for m in measurements:
        v = m.get(field)
        if v is None or v == "":
            continue
        try:
            v = float(v)
        except (TypeError, ValueError):
            pass
        key = repr(v) if isinstance(v, float) else str(v)
        n, _ = counts[key]
        counts[key] = (n + 1, v)
    return [{"value": v, "n": n} for n, v in (counts[k] for k in sorted(counts, key=lambda k: str(k)))]


# Path to the DOI->publication-year cache (persisted, network-free on rebuild).
_DOI_YEARS_CACHE = ROOT / "literature_output" / "doi_years_cache.json"
_DOI_META_CACHE: dict = {}


def _load_doi_year_cache() -> dict:
    """Best-effort DOI -> year map from the persisted discovery cache."""
    if _DOI_YEARS_CACHE.exists():
        try:
            return json.loads(_DOI_YEARS_CACHE.read_text())
        except Exception:
            return {}
    return {}


def _doi_variants(doi: str) -> list[str]:
    """Return lookup variants for a DOI. Underscore form (10.1021_acs...) is a
    filename-safe artifact of paper_id; the canonical Crossref form uses slashes
    (10.1021/acs...). Try both, deduped."""
    out: list[str] = []
    if not doi:
        return out
    for cand in (doi,):
        if cand not in out:
            out.append(cand)
        if "_" in cand:
            alt = cand.replace("_", "/", 1) if cand.startswith("10.") else cand.replace("_", "/")
            if alt not in out:
                out.append(alt)
    return out


def _canonical_doi(doi: str) -> str:
    """Return a single canonical DOI form for counting/grouping. The underscore
    form (10.1021_acs...) is a filename-safe artifact of paper_id; the Crossref
    form uses slashes. Prefer the slash form so one paper is counted once
    regardless of which form a record carries."""
    for cand in _doi_variants(doi):
        if "/" in cand:
            return cand
    return doi


def _doi_year(doi: str, cache: dict) -> int | None:
    for cand in _doi_variants(doi):
        v = cache.get(cand)
        if isinstance(v, (int, float)) and v:
            return int(v)
    return None


def _enrich_doi_meta(records: list[dict]) -> dict[str, dict]:
    """Attach publication year + journal to each DOI present in the records.

    Network-free: uses the persisted doi_years_cache.json for years, and an
    in-memory DOI->{journal,title} map for journals when present. Never fails
    the build when metadata is missing — the health report exposes coverage."""
    cache = _load_doi_year_cache()
    out: dict[str, dict] = {}
    for rec in records:
        doi = rec.get("doi") or rec.get("text_provenance.source_doi") or ""
        if not doi or doi in out:
            continue
        doi = _canonical_doi(doi)
        if doi in out:
            continue
        out[doi] = {
            "year": _doi_year(doi, cache),
            "journal": _doi_journal(doi),
        }
    return out


def _doi_journal(doi: str) -> str | None:
    """Journal from the in-memory DOI metadata map, if populated by an earlier
    Crossref/OpenAlex pass."""
    for cand in _doi_variants(doi):
        meta = _DOI_META_CACHE.get(cand) or {}
        if meta.get("journal"):
            return meta["journal"]
    return None


def _register_doi_meta(doi_meta: dict[str, dict]) -> None:
    """External hook for the build script to register fresh Crossref metadata."""
    global _DOI_META_CACHE
    for doi, meta in (doi_meta or {}).items():
        _DOI_META_CACHE[doi] = meta


def _normalize_temp(t) -> float | None:
    """Coerce a temperature (number, K-range dict) to a single °C value."""
    if t is None:
        return None
    if isinstance(t, (int, float)):
        return float(t)
    if isinstance(t, dict):
        try:
            lo = float(t.get("min_K") or t.get("min_C") or t.get("min"))
            hi = float(t.get("max_K") or t.get("max_C") or t.get("max"))
            if t.get("min_K") is not None or t.get("max_K") is not None:
                return (lo + hi) / 2 - 273.15
            return (lo + hi) / 2
        except (TypeError, ValueError):
            return None
    return None


def _canonical_sigma(rec: dict) -> float | None:
    if rec.get("normalized_sigma") is not None:
        return float(rec["normalized_sigma"])
    if str(rec.get("property", "")).lower() == "conductivity":
        try:
            return normalize_sigma(rec.get("value"), rec.get("unit")).value_s_per_cm
        except Exception:
            return None
    return None


def _canonical_ea(rec: dict) -> float | None:
    if rec.get("normalized_ea") is not None:
        return float(rec["normalized_ea"])
    if str(rec.get("property", "")).lower() == "activation_energy":
        try:
            return float(normalize_ea(rec.get("value"), rec.get("unit")))
        except Exception:
            return None
    return None


def _rec_id(rec: dict) -> str:
    rid = rec.get("review_id")
    if rid:
        return str(rid)
    # canonical dataset rows don't carry review_id — synthesize one
    return f"{rec.get('composition', '')}|{rec.get('text_provenance.source_doi', rec.get('doi', ''))}|{rec.get('property', '')}"


def _iter_records(queue_path, canonical_path) -> list[dict]:
    """Gather all verified experimental records as dicts with normalized fields.

    Dedups: a record seen in both the queue (approved) and the canonical dataset
    is only counted once (keyed by material|doi|property|value).
    """
    import pandas as pd
    from pathlib import Path

    seen: set[tuple] = set()
    out: list[dict] = []

    def _emit(rec: dict) -> None:
        key = (
            str(rec.get("composition", "")),
            _canonical_doi(str(rec.get("doi", "") or rec.get("text_provenance.source_doi", ""))),
            str(rec.get("property", "")),
            str(rec.get("value", "")),
        )
        if key in seen:
            return
        seen.add(key)
        out.append(rec)

    # 1. review queue approved
    qp = Path(queue_path)
    if qp.exists():
        queue = json.loads(qp.read_text())
        for it in queue.get("items", []):
            if it.get("status") != "approved":
                continue
            value = it.get("edited_value")
            if value is None:
                value = it.get("value")
            unit = it.get("edited_unit") or it.get("unit")
            _emit({
                **it,
                "value": value,
                "unit": unit,
                "doi": it.get("doi") or it.get("paper_id"),
            })

    # 2. canonical dataset verified labels
    cp = Path(canonical_path)
    if cp.exists():
        df = pd.read_parquet(cp)
        col_sigma = "ion_transport.sigma_RT"
        col_ea = "ion_transport.activation_energy_Ea"
        if col_sigma in df.columns or col_ea in df.columns:
            mask = df.get("ion_transport.label_available", pd.Series(False, index=df.index))
            mask = mask.fillna(False).astype(bool)
            for _, row in df[mask].iterrows():
                comp = row.get("identity.composition") or row.get("composition") or ""
                # Known canonical bug: some literature-mined rows carry the source
                # DOI in identity.composition (or leave it empty) instead of the
                # formula. material_id always holds the real composition — fall back.
                if not comp or str(comp).startswith("10."):
                    comp = row.get("identity.material_id") or ""
                if not comp:
                    continue
                doi = row.get("text_provenance.source_doi") or ""
                # Fall back to source_id ONLY when it actually looks like a DOI
                # (some literature-mined rows carry the material name in
                # identity.source_id, which must never become a paper DOI).
                if not doi:
                    sid = row.get("identity.source_id") or ""
                    if str(sid).startswith("10.") or "/" in str(sid):
                        doi = sid
                for prop, col, u in (
                    ("conductivity", col_sigma, "S/cm"),
                    ("activation_energy", col_ea, "eV"),
                ):
                    val = row.get(col)
                    if val is None:
                        continue
                    try:
                        val = float(val)
                    except (TypeError, ValueError):
                        continue
                    _emit({
                        "composition": comp,
                        "property": prop,
                        "value": val,
                        "unit": u,
                        "doi": doi,
                        "reviewer": row.get("text_provenance.extraction_reviewer"),
                        "temperature_celsius": _normalize_temp(row.get("ion_transport.temperature_range_measured")),
                        "measurement_method": row.get("ion_transport.measurement_method"),
                        "conductivity_type": str(row.get("ion_transport.conductivity_type") or ""),
                        "experiment": row.get("experiment") if isinstance(row.get("experiment"), dict) else {},
                    })

    return out


def _benchmark_records() -> list[dict]:
    from ssb_dataset.literature.benchmark_inventory import BENCHMARK_INVENTORY

    out = []
    for name, entry in BENCHMARK_INVENTORY.items():
        comp = entry.get("formula") or name
        if entry.get("sigma_S_per_cm") is not None:
            out.append({
                "composition": comp,
                "property": "conductivity",
                "value": entry["sigma_S_per_cm"],
                "unit": "S/cm",
                "doi": entry.get("doi", ""),
                "temperature_celsius": 25,
                "reviewer": "benchmark-inventory",
                "family": entry.get("family", ""),
            })
        if entry.get("Ea_eV") is not None:
            out.append({
                "composition": comp,
                "property": "activation_energy",
                "value": entry["Ea_eV"],
                "unit": "eV",
                "doi": entry.get("doi", ""),
                "reviewer": "benchmark-inventory",
                "family": entry.get("family", ""),
            })
    return out


def build_consensus_db(
    queue_path="review_output/queue.json",
    canonical_path="cleaning_output/canonical_dataset.parquet",
    include_benchmarks: bool = True,
) -> dict[str, ConsensusRecord]:
    records = _iter_records(queue_path, canonical_path)
    if include_benchmarks:
        records.extend(_benchmark_records())

    groups: dict[str, ConsensusRecord] = {}
    for rec in records:
        grp = group_key(str(rec.get("composition", "")))
        if not grp:
            continue
        cr = groups.setdefault(grp, ConsensusRecord(group=grp))
        sigma = _canonical_sigma(rec)
        ea = _canonical_ea(rec)
        if sigma is not None:
            cr.sigma_values.append(sigma)
            cr.n_sigma += 1
        if ea is not None:
            cr.ea_values.append(ea)
            cr.n_ea += 1
        doi = _canonical_doi(str(rec.get("doi") or rec.get("text_provenance.source_doi") or ""))
        if doi and doi not in cr.doiss:
            cr.doiss.append(doi)
        fam = rec.get("family")
        if fam and fam not in cr.families:
            cr.families.append(fam)
        # Preserve the full measurement-level record (property-agnostic).
        measurement = {
            "property": str(rec.get("property", "")),
            "value": rec.get("value"),
            "unit": rec.get("unit"),
            "sigma_S_per_cm": sigma,
            "activation_energy_eV": ea,
            "temperature_celsius": rec.get("temperature_celsius"),
            "doi": doi,
            "paper_id": rec.get("paper_id") or "",
            "source": rec.get("source") or "",
            "reviewer": rec.get("reviewer") or "",
            "page": rec.get("page"),
            "section": rec.get("section") or "",
            "table_number": rec.get("table_number") or "",
            "evidence_sentence": rec.get("evidence_sentence") or rec.get("review_note") or "",
            "measurement_method": rec.get("measurement_method") or rec.get("method") or "",
            "conductivity_type": rec.get("conductivity_type") or "",
            "confidence_tier": rec.get("confidence_tier") or rec.get("tier") or "",
            "confidence": rec.get("confidence"),
        }
        cr.measurements.append(measurement)
        # Experimental-condition distributions (A3): pressure/density come from
        # the experiment block when a record carries it; method from the record.
        exp = rec.get("experiment") or {}
        for fld in ("pressure_distribution", "density_distribution"):
            key = "pelletizing_pressure_MPa" if fld == "pressure_distribution" else "relative_density_pct"
            v = exp.get(key)
            if v is not None and v != "":
                getattr(cr, fld).append(float(v) if isinstance(v, (int, float)) else v)
        method = measurement.get("measurement_method")
        if method:
            cr.method_distribution.append(method)

    # recompute stats
    doi_meta = _enrich_doi_meta(records)
    for cr in groups.values():
        if cr.sigma_values:
            logs = np.log10([v for v in cr.sigma_values if v and v > 0])
            if len(logs) > 0:
                cr.median_sigma = float(10 ** median(logs))
                cr.min_sigma = float(10 ** logs.min())
                cr.max_sigma = float(10 ** logs.max())
                cr.sigma_ci95 = _log_ci(cr.sigma_values)
            mad, std, iqr = _log_stats(cr.sigma_values)
            cr.sigma_mad_log10 = mad
            cr.sigma_std_log10 = std
            cr.sigma_iqr_log10 = iqr
            cr.agreement_grade = _agreement_grade(cr.sigma_values)
        cr.sigma_by_temp = _sigma_by_temp(cr.measurements)
        if cr.ea_values:
            cr.median_ea = float(median(cr.ea_values))
        cr.n_papers = len(set(cr.doiss))
        cr.temp_bins = _temp_bins([_normalize_temp(r.get("temperature_celsius")) for r in records
                                   if group_key(str(r.get("composition", ""))) == cr.group])

        # Publication year + journal coverage (A3), via the persisted DOI cache.
        for d in set(cr.doiss):
            meta = doi_meta.get(d) or {}
            if meta.get("year"):
                cr.publication_years.append(meta["year"])
            if meta.get("journal"):
                cr.journals.append(meta["journal"])
        # Collapse the collected raw pressure/density/method values into
        # distributions (counts per distinct value).
        cr.pressure_distribution = _value_distribution(
            [{"pressure_MPa": p} for p in cr.pressure_distribution], "pressure_MPa")
        cr.density_distribution = _value_distribution(
            [{"density_pct": p} for p in cr.density_distribution], "density_pct")
        cr.method_distribution = _value_distribution(
            [{"method": m} for m in cr.method_distribution], "method")

        # outlier detection (only with a real consensus, n>=3)
        if cr.n_sigma >= MIN_N_FOR_CONSENSUS and cr.median_sigma:
            med = np.log10(cr.median_sigma)
            for v in cr.sigma_values:
                delta = abs(np.log10(v) - med)
                if delta > MAX_ORDER_SPREAD:
                    cr.outliers.append({
                        "sigma": v,
                        "median_sigma": cr.median_sigma,
                        "delta_log10": round(float(delta), 2),
                        "note": f"{v:.2e} is {10**delta:.0f}x from group median",
                    })

    return groups


def to_parquet(groups: dict[str, ConsensusRecord], out_path: str) -> None:
    import pandas as pd

    rows = []
    for grp, cr in groups.items():
        row = cr.to_dict(with_measurements=False)
        row.pop("outliers", None)
        rows.append(row)
    df = pd.DataFrame(rows)
    df.to_parquet(out_path, index=False)


def summary(groups: dict[str, ConsensusRecord]) -> dict:
    n_with_consensus = sum(1 for cr in groups.values() if cr.n_sigma >= MIN_N_FOR_CONSENSUS)
    n_with_records = sum(1 for cr in groups.values() if cr.measurements)
    return {
        "materials_total": len(groups),
        "materials_with_sigma": sum(1 for cr in groups.values() if cr.n_sigma > 0),
        "materials_with_ea": sum(1 for cr in groups.values() if cr.n_ea > 0),
        "materials_with_consensus_n3": n_with_consensus,
        "materials_with_paper_count_ge2": sum(1 for cr in groups.values() if cr.n_papers >= 2),
        "materials_with_measurements": n_with_records,
        "total_sigma_records": sum(cr.n_sigma for cr in groups.values()),
        "total_ea_records": sum(cr.n_ea for cr in groups.values()),
        "total_measurement_records": sum(len(cr.measurements) for cr in groups.values()),
        "outlier_records": sum(len(cr.outliers) for cr in groups.values()),
    }
