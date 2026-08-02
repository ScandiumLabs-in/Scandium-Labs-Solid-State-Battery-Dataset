"""Phase 3.3 — Extraction pipeline: GROBID PDF parsing + LLM structured extraction.

Extracts conductivity, activation energy, composition, and measurement method
from scientific PDFs. Outputs structured records matching Section 2 schema.
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from ssb_dataset.literature.discovery import PaperCandidate
from ssb_dataset.schema import (
    ConductivityPoint,
    ConductivitySourceType,
    ConductivityType,
    ExtractionMethod,
    Family,
    MaterialRecord,
    TemperatureRange,
)
from ssb_dataset.sources.classifier import classify_family


@dataclass
class ExtractedConductivityRecord:
    composition: str
    sigma_S_per_cm: float | None = None
    sigma_vs_T: list[tuple[float, float]] = field(default_factory=list)
    activation_energy_eV: float | None = None
    temperature_K: float | None = None
    temperature_range: tuple[float, float] | None = None
    measurement_method: str = ""
    conductivity_type: str = "total"
    synthesis_route: str = ""
    source_doi: str = ""
    source_paper_title: str = ""
    confidence_score: float = 0.0
    # M6 experimental metadata — measurement conditions
    sample_form: str = ""
    pellet_diameter_mm: float | None = None
    thickness_mm: float | None = None
    relative_density_pct: float | None = None
    pelletizing_pressure_MPa: float | None = None
    electrode_material: str = ""
    frequency_min_Hz: float | None = None
    frequency_max_Hz: float | None = None
    atmosphere: str = ""
    humidity: str = ""
    sinter_temperature_C: float | None = None
    sinter_time_h: float | None = None
    annealing_temperature_C: float | None = None
    annealing_time_h: float | None = None
    instrument: str = ""
    equivalent_circuit: str = ""
    dc_bias_V: float | None = None
    raw_extraction: dict[str, Any] = field(default_factory=dict)
    # Ensemble provenance — the signal a calibrated confidence is built from.
    ensemble_votes: int | None = None
    ensemble_size: int | None = None
    sigma_spread_frac: float | None = None  # max relative dev from median across runs, 0=perfect agree


EXTRACTION_PROMPT = """You are extracting solid-state battery electrolyte data from a scientific paper.
Extract ALL reported ionic conductivity measurements and activation energies as structured JSON.

FIRST, locate the paper's "Experimental Section", "Methods", and "Supporting Information".
Then extract conductivity data from the Results/Tables/Figures.

For each distinct measurement (or set of measurements for one composition), create one object with:

REQUIRED fields:
- "composition": exact chemical formula as written (e.g. "Li6PS5Cl", "Li7La3Zr2O12", "Li1.3Al0.3Ti1.7(PO4)3")
- "sigma_S_per_cm": room-temperature (or reported) ionic conductivity in S/cm. MUST CONVERT to S/cm. null if not reported.

OPTIONAL fields (include if available):
- "sigma_vs_T": array of [temperature_K, sigma_S_per_cm] pairs from Arrhenius plots or temperature-dependent tables
- "activation_energy_eV": activation energy in eV. MUST CONVERT to eV. null if not reported.
- "temperature_K": measurement temperature in Kelvin (use 298 if "room temperature" stated)
- "sigma_error": error/uncertainty on sigma in S/cm if reported (e.g. ±0.3e-3)
- "Ea_error": error on activation energy in eV if reported
- "measurement_method": e.g. "AC impedance spectroscopy", "EIS", "DC polarization", "4-probe"
- "conductivity_type": "bulk", "grain_boundary", "total", or "single crystal"
- "synthesis_route": e.g. "solid state", "sol-gel", "mechanochemical", "melt-quench", "co-precipitation"
- "dopant": specific dopant/substitution if noted (e.g. "Ta-doped", "Al-doped")
- "crystal_structure": phase noted (e.g. "cubic", "tetragonal", "hexagonal")
- "relative_density": % if reported
- "measurement_notes": any relevant details (e.g. "pellet sintered at 900°C", "measured under Ar")
- "figure_or_table_ref": reference to figure/table number in paper for provenance

EXPERIMENTAL CONDITIONS (M6 — include each if the paper states it):
- "sample_form": "pellet", "thin film", "composite", "single crystal", "pressed powder", etc.
- "pelletizing_pressure_MPa": cold-press/pelletizing pressure in MPa
- "pellet_diameter_mm": pellet diameter in mm
- "thickness_mm": pellet thickness in mm
- "relative_density": % of theoretical density if reported
- "electrode_material": e.g. "Au", "Ag", "Pt", "stainless steel", "graphite", "Li metal"
- "frequency_min_Hz" and "frequency_max_Hz": EIS frequency sweep range
- "atmosphere": e.g. "Ar", "N2", "air", "vacuum", "He"
- "humidity": glovebox/dev-point humidity if reported
- "sinter_temperature_C": sintering/annealing temperature in °C
- "sinter_time_h": sintering/annealing duration in hours
- "annealing_temperature_C": annealing temperature in °C if distinct from sintering
- "annealing_time_h": annealing duration in hours
- "instrument": impedance analyzer model if reported
- "equivalent_circuit": equivalent circuit model used for fitting (e.g. "R1-R2CPE")
- "dc_bias_V": DC bias applied during measurement in volts
- "sigma_error": error/uncertainty on sigma in S/cm if reported (e.g. ±0.3e-3)
- "Ea_error": error on activation energy in eV if reported

UNIT CONVERSION RULES (MANDATORY — convert ALL values):
- Conductivity: 1 S/cm = 1 S/cm; 1 mS/cm = 0.001 S/cm; 1 uS/cm = 1e-6 S/cm; 1 S/m = 0.01 S/cm
- Activation energy: 1 eV = 1 eV; 1 kJ/mol = 0.010364 eV; 1 kcal/mol = 0.043364 eV; 1 meV = 0.001 eV

EDGE CASE HANDLING:
- If a paper reports conductivity at multiple temperatures for the same composition, include ALL points in sigma_vs_T AND set sigma_S_per_cm to the room-temp (or most prominent) value
- If the paper reports different conductivity types (bulk vs total) for the same composition, create SEPARATE objects for each
- If multiple dopant concentrations are studied, create SEPARATE objects for each distinct composition
- If only an Arrhenius plot is shown (no numeric table), estimate values from the plot and note "estimated from Arrhenius plot" in measurement_notes
- For composite/hybrid electrolytes, include both the composition and the polymer matrix name

OUTPUT FORMAT:
- Return ONLY a valid JSON array of objects — no markdown code fences, no explanation text, no comments
- If no valid conductivity data is found, return an empty array []
- If a paper only mentions conductivity of non-SSB materials (e.g. liquid electrolytes, anode materials), return []
"""


def normalize_composition(comp_str: str) -> str:
    """Normalize a composition string for consistent matching."""
    s = comp_str.strip()
    s = re.sub(r"\s+", "", s)
    s = re.sub(r"·|∙|•", "", s)
    s = s.replace("−", "-").replace("–", "-")
    return s


def extract_table_data(grobid_xml: str) -> list[dict[str, str]]:
    """Parse GROBID XML output to extract table rows as structured dicts."""
    import xml.etree.ElementTree as ET

    tables: list[dict[str, str]] = []
    try:
        root = ET.fromstring(grobid_xml)
        ns = {"tei": "http://www.tei-c.org/ns/1.0"}
        for table in root.iter("{http://www.tei-c.org/ns/1.0}table"):
            rows = table.findall(".//tei:row", ns) or table.findall(".//row")
            for row in rows:
                cells = row.findall(".//tei:cell", ns) or row.findall(".//cell")
                row_data: dict[str, str] = {}
                for i, cell in enumerate(cells):
                    row_data[f"col_{i}"] = "".join(cell.itertext()).strip()
                if row_data:
                    tables.append(row_data)
    except Exception:
        pass
    return tables


def extract_body_text(grobid_xml: str) -> str:
    """Extract body text from GROBID XML output."""
    import xml.etree.ElementTree as ET

    texts: list[str] = []
    try:
        root = ET.fromstring(grobid_xml)
        for p in root.iter("{http://www.tei-c.org/ns/1.0}p"):
            texts.append("".join(p.itertext()).strip())
    except Exception:
        pass
    return "\n".join(texts)


def run_grobid_parse(pdf_path: str | Path, grobid_url: str = "http://localhost:8070") -> str:
    """Send a PDF to a GROBID server and return the TEI XML output."""
    import httpx

    with open(pdf_path, "rb") as f:
        resp = httpx.post(
            f"{grobid_url}/api/processFulltextDocument",
            files={"input": f},
            timeout=300,
        )
        resp.raise_for_status()
        return resp.text


def run_llm_extraction(
    text: str,
    api_key: str | None = None,
    model: str = "gpt-4o-mini",
    base_url: str = "https://api.openai.com/v1",
) -> list[ExtractedConductivityRecord]:
    """Run LLM extraction over paper text/tables to get structured conductivity data.

    Supports any OpenAI-compatible API (OpenAI, Groq, Together, etc.).
    Set base_url to the provider's chat completions endpoint.
    """
    import httpx

    max_chars = 15000
    if len(text) > max_chars:
        idx = text.lower().find("conductivity")
        if 0 <= idx < len(text) - max_chars:
            start = max(0, idx - 5000)
            text = text[start:start + max_chars]
        else:
            text = text[:max_chars]

    messages = [
        {"role": "system", "content": EXTRACTION_PROMPT},
        {"role": "user", "content": f"Extract conductivity data from this paper content:\n\n{text}"},
    ]

    headers: dict[str, str] = {
        "Content-Type": "application/json",
    }
    if api_key:
        headers["Authorization"] = f"Bearer {api_key}"

    payload: dict[str, Any] = {
        "model": model,
        "messages": messages,
        "temperature": 0.0,
    }

    # Prefer JSON response format for deterministic parsing; fall back to plain JSON prompt
    # if the API doesn't support response_format (e.g., some Groq models).
    import time as _time

    content: str | None = None
    last_error: str = ""
    configs_to_try: list[dict[str, Any]] = [{**payload, "response_format": {"type": "json_object"}}]
    # Only add the no-response_format fallback if the first attempt fails with a format error
    has_tried_plain = False

    for attempt in range(3):
        for use_plain in ([False, True] if not has_tried_plain else [False]):
            cfg = {**payload} if use_plain else {**payload, "response_format": {"type": "json_object"}}
            if use_plain:
                has_tried_plain = True
            try:
                resp = httpx.post(
                    f"{base_url.rstrip('/')}/chat/completions",
                    headers=headers,
                    json=cfg,
                    timeout=30,
                )
                if resp.status_code == 429 or resp.status_code == 413:
                    wait = 10 * (attempt + 1)
                    print(f"  LLM rate-limited (429/413), retrying in {wait}s (attempt {attempt+1}/3)")
                    _time.sleep(wait)
                    continue
                if resp.status_code == 400 and not use_plain:
                    # response_format not supported, fall back to plain
                    continue
                if resp.status_code != 200:
                    last_error = f"LLM returned HTTP {resp.status_code}"
                    print(f"  {last_error}")
                    continue
                data = resp.json()
                content = data["choices"][0]["message"]["content"]
                import os as _os
                if _os.environ.get("EXTRACTION_DEBUG"):
                    _log_path = Path(f"/tmp/llm_response_{_time.time_ns()}.txt")
                    _log_path.write_text(content)
                    print(f"  [debug] Raw LLM response saved to {_log_path} ({len(content)} chars)")
                break
            except httpx.TimeoutException:
                last_error = f"LLM timeout after 30s (attempt {attempt+1}/3)"
                print(f"  {last_error}")
                continue
            except Exception as e:
                last_error = f"LLM error: {e}"
                print(f"  {last_error}")
                continue
        if content is not None:
            break

    if content is None:
        return []

    content = content.strip()
    if content.startswith("```"):
        content = content.split("\n", 1)[1] if "\n" in content else content[3:]
        content = content.rsplit("```", 1)[0] if "```" in content else content
        content = content.strip()
    content = re.sub(r'//[^\n]*', '', content)
    content = re.sub(r',\s*]', ']', content)
    content = re.sub(r',\s*}', '}', content)
    try:
        parsed = json.loads(content)
    except json.JSONDecodeError:
        return []
    except Exception:
        return []
    raw_records = parsed if isinstance(parsed, list) else parsed.get("data", parsed.get("records", [parsed]))

    records: list[ExtractedConductivityRecord] = []
    for item in raw_records:
        if not isinstance(item, dict):
            continue
        comp = normalize_composition(item.get("composition", ""))
        if not comp:
            continue

        sigma_vs_T: list[tuple[float, float]] = []
        svst = item.get("sigma_vs_T") or []
        for pt in svst:
            if isinstance(pt, (list, tuple)) and len(pt) >= 2:
                if pt[0] is not None and pt[1] is not None:
                    sigma_vs_T.append((float(pt[0]), float(pt[1])))
            elif isinstance(pt, dict):
                t = pt.get("temperature_K") or pt.get("temperature")
                s = pt.get("sigma_S_per_cm") or pt.get("conductivity")
                if t is not None and s is not None:
                    sigma_vs_T.append((float(t), float(s)))

        temp_range = item.get("temperature_range")
        if temp_range:
            if isinstance(temp_range, dict):
                temp_range = (temp_range.get("min_K", 298), temp_range.get("max_K", 298))
            elif isinstance(temp_range, (list, tuple)) and len(temp_range) >= 2:
                temp_range = (float(temp_range[0]), float(temp_range[1]))

        records.append(
            ExtractedConductivityRecord(
                composition=comp,
                sigma_S_per_cm=_safe_float(item.get("sigma_S_per_cm")),
                sigma_vs_T=sigma_vs_T,
                activation_energy_eV=_safe_float(item.get("activation_energy_eV")),
                temperature_K=_safe_float(item.get("temperature_K")),
                temperature_range=temp_range,
                measurement_method=item.get("measurement_method", ""),
                conductivity_type=item.get("conductivity_type", "total"),
                synthesis_route=item.get("synthesis_route", ""),
                confidence_score=0.85,
                sample_form=item.get("sample_form", ""),
                relative_density_pct=_safe_float(item.get("relative_density")),
                pelletizing_pressure_MPa=_safe_float(item.get("pelletizing_pressure_MPa")),
                electrode_material=item.get("electrode_material", ""),
                frequency_min_Hz=_safe_float(item.get("frequency_min_Hz")),
                frequency_max_Hz=_safe_float(item.get("frequency_max_Hz")),
                atmosphere=item.get("atmosphere", ""),
                humidity=item.get("humidity", ""),
                sinter_temperature_C=_safe_float(item.get("sinter_temperature_C")),
                sinter_time_h=_safe_float(item.get("sinter_time_h")),
                annealing_temperature_C=_safe_float(item.get("annealing_temperature_C")),
                annealing_time_h=_safe_float(item.get("annealing_time_h")),
                instrument=item.get("instrument", ""),
                equivalent_circuit=item.get("equivalent_circuit", ""),
                dc_bias_V=_safe_float(item.get("dc_bias_V")),
                raw_extraction=item,
            )
        )
    return records


def _safe_float(v: Any) -> float | None:
    if v is None:
        return None
    try:
        return float(v)
    except (ValueError, TypeError):
        return None


def extraction_record_to_material_record(
    extracted: ExtractedConductivityRecord,
    doi: str = "",
    title: str = "",
) -> MaterialRecord:
    """Convert an extracted record into a MaterialRecord for the unified schema."""
    from datetime import datetime, timezone

    from ssb_dataset.schema import (
        ConfidenceTier,
        ExperimentBlock,
        IdentityProvenance,
        IonTransportBlock,
        SourceDB,
        TextProvenanceBlock,
    )

    family = classify_family(composition=extracted.composition)

    ion_transport = IonTransportBlock(
        sigma_RT=extracted.sigma_S_per_cm,
        activation_energy_Ea=extracted.activation_energy_eV,
        temperature_range_measured=(
            TemperatureRange(min_K=extracted.temperature_range[0], max_K=extracted.temperature_range[1])
            if extracted.temperature_range
            else None
        ),
        measurement_method=extracted.measurement_method or None,
        label_available=extracted.sigma_S_per_cm is not None,
        conductivity_type=(
            {"bulk": ConductivityType.bulk, "grain_boundary": ConductivityType.grain_boundary, "total": ConductivityType.total}.get(
                extracted.conductivity_type.lower()
            )
            if extracted.conductivity_type
            else None
        ),
        conductivity_source_type=ConductivitySourceType.measured,
    )

    if extracted.sigma_vs_T:
        ion_transport.sigma_vs_T_curve = [
            ConductivityPoint(temperature_K=t, conductivity_S_per_cm=s) for t, s in extracted.sigma_vs_T
        ]

    confidence = ConfidenceTier.high_confidence_extraction if extracted.confidence_score >= 0.85 else ConfidenceTier.low_confidence_extraction

    return MaterialRecord(
        identity=IdentityProvenance(
            source_db=SourceDB.literature_mined,
            source_id=f"lit-{doi.replace('/', '-')}" if doi else "lit-unknown",
            composition=extracted.composition,
            family=family,
            ingestion_date=datetime.now(timezone.utc),
            confidence_tier=confidence,
        ),
        ion_transport=ion_transport,
        experiment=ExperimentBlock(
            sample_form=extracted.sample_form or None,
            pellet_diameter_mm=extracted.pellet_diameter_mm,
            thickness_mm=extracted.thickness_mm,
            relative_density_pct=extracted.relative_density_pct,
            pelletizing_pressure_MPa=extracted.pelletizing_pressure_MPa,
            electrode_material=extracted.electrode_material or None,
            frequency_min_Hz=extracted.frequency_min_Hz,
            frequency_max_Hz=extracted.frequency_max_Hz,
            atmosphere=extracted.atmosphere or None,
            humidity=extracted.humidity or None,
            measurement_method=extracted.measurement_method or None,
            conductivity_type=extracted.conductivity_type or None,
            sinter_temperature_C=extracted.sinter_temperature_C,
            sinter_time_h=extracted.sinter_time_h,
            annealing_temperature_C=extracted.annealing_temperature_C,
            annealing_time_h=extracted.annealing_time_h,
            instrument=extracted.instrument or None,
            equivalent_circuit=extracted.equivalent_circuit or None,
            dc_bias_V=extracted.dc_bias_V,
        ),
        text_provenance=TextProvenanceBlock(
            source_doi=doi or None,
            source_paper_title=title or None,
            extraction_method=ExtractionMethod.llm_extraction,
            extraction_confidence_score=extracted.confidence_score,
            ensemble_votes=extracted.ensemble_votes,
            ensemble_size=extracted.ensemble_size,
            sigma_spread_frac=extracted.sigma_spread_frac,
        ),
    )


REVIEW_PATTERNS = re.compile(
    r"(this review|review article|we review|literature review|mini.?review|critical review|overview of)",
    re.IGNORECASE,
)


def _is_review(text: str) -> bool:
    return bool(REVIEW_PATTERNS.search(text[:5000]))


def _fix_units(records: list[ExtractedConductivityRecord], paper_text: str) -> list[ExtractedConductivityRecord]:
    """Post-process extracted records to fix missed unit conversions.

    Detects if the paper uses mS/cm but the LLM failed to convert to S/cm.
    """
    uses_ms_per_cm = bool(re.search(r"mS\s*/?\s*cm", paper_text))
    if not uses_ms_per_cm:
        return records

    for rec in records:
        if rec.sigma_S_per_cm is not None and rec.sigma_S_per_cm > 0.001:
            expected_if_mS = rec.sigma_S_per_cm / 0.001
            if 0.001 <= expected_if_mS <= 10000:
                rec.sigma_S_per_cm = rec.sigma_S_per_cm * 0.001
                rec.confidence_score = min(rec.confidence_score, 0.7)
    return records


def _extract_conductivity_text(pdf_path: str | Path, max_chars: int = 15000) -> tuple[str, str]:
    """Extract conductivity-relevant text from a PDF using table-first + centered prose.

    Returns (table_text, prose_text) as separate strings for dual-pass LLM extraction.

    Strategy:
    1. Extract tables via pdfplumber (fast, detects tabular data)
    2. Extract full text via PyMuPDF
    3. Center prose around conductivity keyword
    """
    table_text = _extract_tables_from_pdf(pdf_path)
    prose_text = _extract_text_from_pdf(pdf_path)

    if len(prose_text) > max_chars:
        idx = prose_text.lower().find("conductivity")
        if 0 <= idx < len(prose_text) - max_chars:
            start = max(0, idx - 5000)
            prose_text = prose_text[start:start + max_chars]
        else:
            prose_text = prose_text[:max_chars]

    return table_text, prose_text


def _extract_conductivity_combined(pdf_path: str | Path, max_chars: int = 15000) -> str:
    """Legacy: extract conductivity text as single combined string."""
    table_text, prose_text = _extract_conductivity_text(pdf_path, max_chars)
    combined = ""
    if table_text:
        combined += f"--- TABLES ---\n{table_text}\n\n"
    combined += f"--- TEXT ---\n{prose_text}"
    return combined


def _dict_to_extraction_record(candidate: dict[str, Any], source_text: str) -> ExtractedConductivityRecord | None:
    """Convert a regex candidate dict to an ExtractedConductivityRecord."""
    sigma = candidate.get("sigma_S_per_cm")
    if sigma is None or sigma <= 0:
        return None
    sigma_vs_T_raw = candidate.get("sigma_vs_T", [])
    sigma_vs_T: list[tuple[float, float]] = []
    for pt in sigma_vs_T_raw:
        if isinstance(pt, (list, tuple)) and len(pt) >= 2:
            try:
                sigma_vs_T.append((float(pt[0]), float(pt[1])))
            except (ValueError, TypeError):
                pass
    return ExtractedConductivityRecord(
        composition=candidate.get("composition", "unknown"),
        sigma_S_per_cm=sigma,
        sigma_vs_T=sigma_vs_T,
        confidence_score=candidate.get("confidence_score", 0.3),
        raw_extraction={"source_text": candidate.get("source_text", "")},
    )


def _ensemble_fingerprint(r: ExtractedConductivityRecord) -> tuple:
    """Fingerprint for deduplication across ensemble runs."""
    comp = r.composition.strip().lower() if r.composition else ""
    temps = tuple(sorted(r.sigma_vs_T)) if r.sigma_vs_T else (0,)
    return (comp, temps)


def _aggregate_ensemble(
    runs: list[list[ExtractedConductivityRecord]],
    min_consensus: int | None = None,
) -> list[ExtractedConductivityRecord]:
    """Aggregate multiple extraction runs, keeping only records with consistent values.

    A record is kept if its (composition, sigma_vs_T fingerprint) appears in at least
    `min_consensus` runs, AND its sigma_S_per_cm values are within 10% relative of
    each other across those runs.
    """
    n = len(runs)
    min_consensus = min_consensus or (n // 2 + 1)

    from collections import defaultdict
    votes: dict[tuple, list[ExtractedConductivityRecord]] = defaultdict(list)
    for run in runs:
        seen: set[tuple] = set()
        for r in run:
            fp = _ensemble_fingerprint(r)
            if fp in seen:
                continue
            seen.add(fp)
            votes[fp].append(r)

    kept: list[ExtractedConductivityRecord] = []
    for fp, records in votes.items():
        if len(records) < min_consensus:
            continue
        sigmas = [r.sigma_S_per_cm for r in records if r.sigma_S_per_cm is not None and r.sigma_S_per_cm > 0]
        if not sigmas:
            continue
        median_sigma = sorted(sigmas)[len(sigmas) // 2]
        all_close = all(
            abs(s - median_sigma) / median_sigma < 0.1
            for s in sigmas
        )
        if not all_close:
            print(f"  [ensemble] Discarding {records[0].composition}: sigma varies ({[f'{s:.1e}' for s in sigmas]})")
            continue
        eas = [r.activation_energy_eV for r in records if r.activation_energy_eV is not None]
        median_ea = sorted(eas)[len(eas) // 2] if eas else None
        conf = min(0.85, 0.5 + 0.1 * len(records))
        # Sigma spread across the agreeing runs: 0 = perfect agreement, near/below
        # the 0.1 keep-threshold = tight. This is the raw material for a calibrated
        # confidence (tight agreement + many votes = high confidence).
        max_dev = max(abs(s - median_sigma) / median_sigma for s in sigmas)
        # Use the first record as template, updating values to consensus
        record = records[0]
        kept.append(ExtractedConductivityRecord(
            composition=record.composition,
            sigma_S_per_cm=median_sigma,
            sigma_vs_T=record.sigma_vs_T,
            activation_energy_eV=median_ea,
            confidence_score=round(conf, 2),
            raw_extraction=record.raw_extraction,
            ensemble_votes=len(records),
            ensemble_size=n,
            sigma_spread_frac=round(max_dev, 4),
        ))

    print(f"  [ensemble] {len(votes)} candidates, {len(kept)} survived {n}-run consensus (min={min_consensus})")
    return kept


def extract_from_pdf(
    pdf_path: str | Path,
    grobid_url: str = "http://localhost:8070",
    llm_api_key: str | None = None,
    llm_model: str | None = None,
    llm_base_url: str | None = None,
    skip_grobid: bool = False,
    exclude_review: bool = True,
    ensemble_size: int = 1,
) -> list[MaterialRecord]:
    """Full extraction pipeline: regex pre-pass -> dual-pass LLM extraction -> MaterialRecords.

    Uses dual-pass LLM extraction: tables first (markdown format for clean parsing),
    then conductivity-centered prose. Table data typically yields higher-quality
    results with small models since the format is predictable.

    When skip_grobid=True, uses pdfplumber + PyMuPDF instead of GROBID.
    When exclude_review=True, skips review articles entirely.
    When ensemble_size > 1, runs extraction N times and aggregates by consensus.
    """
    from ssb_dataset.config.settings import settings

    api_key = llm_api_key or settings.llm.api_key or None
    model = llm_model or settings.llm.model_extraction
    base_url = llm_base_url or settings.llm.base_url

    if not api_key:
        base_url = "http://localhost:11434/v1"
        if model.startswith("gpt-"):
            model = "llama3.2:3b"

    table_text: str = ""
    prose_text: str = ""
    extraction_text: str = ""

    if skip_grobid:
        table_text, prose_text = _extract_conductivity_text(pdf_path)
        extraction_text = table_text + "\n" + prose_text
        tt = len(table_text) if table_text else 0
        pt = len(prose_text)
        print(f"  Extracted {tt} table chars + {pt} prose chars from PDF")
    else:
        try:
            grobid_xml = run_grobid_parse(pdf_path, grobid_url)
            body = extract_body_text(grobid_xml)
            grobid_tables = extract_table_data(grobid_xml)
            table_text = ""
            if grobid_tables:
                table_parts: list[str] = []
                for i, t in enumerate(grobid_tables):
                    desc = t.pop("caption", f"Table {i+1}")
                    table_parts.append(f"Table: {desc}")
                    headers = list(t.keys())
                    table_parts.append("| " + " | ".join(headers) + " |")
                    table_parts.append("| " + " | ".join("---" for _ in headers) + " |")
                    table_parts.append("| " + " | ".join(str(t.get(h, "")) for h in headers) + " |")
                    table_parts.append("")
                table_text = "\n".join(table_parts)
            prose_text = body
            extraction_text = body + "\n\n--- TABLES ---\n" + table_text if table_text else body
            print(f"  Extracted {len(prose_text)} prose chars + {len(table_text)} table chars via GROBID")
        except Exception as e:
            print(f"  GROBID failed ({e}), falling back to table+text extraction...")
            table_text, prose_text = _extract_conductivity_text(pdf_path)
            extraction_text = table_text + "\n" + prose_text

    if exclude_review and _is_review(extraction_text):
        print(f"  Skipping review article (no primary data extraction)")
        return []

    # Run extraction (possibly multiple passes for ensemble)
    runs: list[list[ExtractedConductivityRecord]] = []
    for i in range(max(ensemble_size, 1)):
        if ensemble_size > 1:
            print(f"  [ensemble] Pass {i+1}/{ensemble_size}")
        extracted: list[ExtractedConductivityRecord] = []

        if table_text:
            extracted += run_llm_extraction(table_text, api_key=api_key, model=model, base_url=base_url)

        if prose_text:
            extracted += run_llm_extraction(prose_text, api_key=api_key, model=model, base_url=base_url)

        extracted = _fix_units(extracted, extraction_text)
        runs.append(extracted)

    if ensemble_size > 1:
        extracted = _aggregate_ensemble(runs, min_consensus=ensemble_size - 1)
    else:
        extracted = runs[0]

    return [extraction_record_to_material_record(r) for r in extracted]


def _extract_tables_from_pdf(pdf_path: str | Path) -> str:
    """Extract table content from a PDF using pdfplumber.

    Returns a text block with tables formatted as clean markdown tables.
    Falls back to empty string if pdfplumber is unavailable.
    """
    try:
        import pdfplumber
        table_lines: list[str] = []
        with pdfplumber.open(str(pdf_path)) as pdf:
            for page_num, page in enumerate(pdf.pages, 1):
                tables = page.find_tables()
                for table in tables:
                    rows = [[(c or "").replace("\n", " ") for c in row.cells] for row in table.rows]
                    if len(rows) < 2:
                        continue
                    table_lines.append(f"Table (page {page_num}):")
                    header = rows[0]
                    table_lines.append("| " + " | ".join(header) + " |")
                    table_lines.append("| " + " | ".join("---" for _ in header) + " |")
                    for row in rows[1:]:
                        table_lines.append("| " + " | ".join(row) + " |")
                    table_lines.append("")
        result = "\n".join(table_lines)
        if not result:
            return ""
        max_chars = 15000
        if len(result) > max_chars:
            idx = result.lower().find("conductivity")
            if 0 <= idx < len(result) - max_chars:
                start = max(0, idx - 5000)
                result = result[start:start + max_chars]
            else:
                result = result[:max_chars]
        return result
    except ImportError:
        return ""
    except Exception:
        return ""


CONDUCTIVITY_RE = re.compile(
    r"(\d+(?:\.\d+)?)\s*(?:×|x|\*)?\s*(?:10[⁻−\-\^–]\s*[⁻−\-+]?\s*)?(\d+)\s*[Ssc]\s*(?:[Cc]m|cm|/cm|\.cm)",
    re.IGNORECASE,
)

E_NOTATION_RE = re.compile(
    r"(\d+(?:\.\d+)?)\s*[eE]\s*[⁻−\-+]?\s*(\d+)\s*[Ssc]\s*(?:[Cc]m|cm|/cm|\.cm)",
    re.IGNORECASE,
)


def _regex_prepass(text: str) -> list[dict[str, Any]]:
    """Catch straightforward conductivity mentions via regex without any LLM call.

    Returns a list of candidate dicts with composition, sigma_S_per_cm, and
    confidence_score. Designed for cases where the pattern is simple enough
    that an LLM call would be overkill.
    """
    candidates: list[dict[str, Any]] = []

    def _extract_from_match(match: re.Match) -> None:
        mantissa = float(match.group(1))
        exponent_str = match.group(2).lstrip("⁻−+")
        exponent = int(exponent_str) if exponent_str else 0
        sigma = mantissa * 10 ** (-exponent)
        lookback = min(80, match.start())
        snippet = text[match.start() - lookback:match.start()]
        comp_match = re.search(r"[A-Z][a-z]?\d*(?:\.[\d]+)?(?:[A-Z][a-z]?\d*(?:\.[\d]+)?)+", snippet)
        composition = comp_match.group(0) if comp_match else "unknown"
        candidates.append({
            "composition": composition,
            "sigma_S_per_cm": sigma,
            "sigma_vs_T": [[298, sigma]],
            "source_text": match.group(0),
            "confidence_score": 0.4,
        })

    for match in CONDUCTIVITY_RE.finditer(text):
        _extract_from_match(match)
    for match in E_NOTATION_RE.finditer(text):
        _extract_from_match(match)
    return candidates


def _extract_text_from_pdf(pdf_path: str | Path) -> str:
    """Extract plain text from a PDF using PyMuPDF (fitz), with OCR fallback for scanned PDFs."""
    import fitz  # PyMuPDF

    text_parts: list[str] = []
    with fitz.open(str(pdf_path)) as doc:
        for page in doc:
            text_parts.append(page.get_text())
    text = "\n".join(text_parts)

    if len(text.strip()) < 500:
        try:
            from pdf2image import convert_from_path
            import pytesseract

            ocr_parts: list[str] = []
            images = convert_from_path(str(pdf_path), dpi=300)
            for i, img in enumerate(images):
                ocr_text = pytesseract.image_to_string(img)
                ocr_parts.append(ocr_text)
            ocr_text = "\n".join(ocr_parts)
            if len(ocr_text.strip()) > len(text.strip()):
                print(f"  OCR fallback: {len(ocr_text)} chars (was {len(text.strip())} from text layer)")
                return ocr_text
        except Exception as exc:
            print(f"  OCR fallback failed: {exc}")

    return text


def batch_extract_from_discovery(
    discovery_results: dict[Family, list[PaperCandidate]],
    max_per_family: int = 5,
    llm_api_key: str | None = None,
    llm_model: str | None = None,
    llm_base_url: str | None = None,
) -> list[MaterialRecord]:
    """Run extraction on the top N papers per family from discovery results.

    Downloads PDFs (open-access only) and runs LLM extraction on each.
    Returns accumulated MaterialRecords across all families.
    """
    from ssb_dataset.config.settings import settings

    api_key = llm_api_key or settings.llm.api_key or None
    model = llm_model or settings.llm.model_extraction
    base_url = llm_base_url or settings.llm.base_url

    all_records: list[MaterialRecord] = []
    total = sum(min(len(papers), max_per_family) for papers in discovery_results.values())
    completed = 0
    failures = 0

    for family, papers in discovery_results.items():
        sorted_papers = sorted(papers, key=lambda p: p.relevance_score, reverse=True)
        batch = sorted_papers[:max_per_family]
        print(f"\n--- {family.value}: processing up to {len(batch)} papers ---")

        for paper in batch:
            try:
                records = extract_from_doi(
                    doi=paper.doi,
                    llm_api_key=api_key,
                    llm_model=model,
                    llm_base_url=base_url,
                )
                for rec in records:
                    if family not in rec.identity.subfamily_tag:
                        rec.identity.subfamily_tag.append(family.value)
                all_records.extend(records)
                completed += 1
                print(f"  [{completed}/{total}] {paper.doi[:50]} → {len(records)} records extracted")
            except Exception as e:
                failures += 1
                print(f"  [{completed+1}/{total}] FAILED {paper.doi[:50]}: {e}")
                completed += 1

    print(f"\nBatch extraction complete: {len(all_records)} records from {completed - failures}/{total} papers")
    if failures:
        print(f"  {failures} papers failed (may not be open-access)")
    return all_records


def extract_from_doi(
    doi: str,
    llm_api_key: str | None = None,
    llm_model: str = "gpt-4o-mini",
    llm_base_url: str = "https://api.openai.com/v1",
    download_dir: str | Path = "literature_output/pdfs",
) -> list[MaterialRecord]:
    """Download a paper from its DOI and extract conductivity data.

    Uses arXiv for open-access PDFs, then falls back to Semantic Scholar
    PDF endpoint. Saves the PDF locally for reproducibility.
    """
    import shutil

    from ssb_dataset.config.settings import settings

    api_key = llm_api_key or settings.llm.api_key or None
    model = llm_model or settings.llm.model_extraction
    base_url = llm_base_url or settings.llm.base_url

    dl_dir = Path(download_dir)
    dl_dir.mkdir(parents=True, exist_ok=True)

    pdf_path = dl_dir / f"{doi.replace('/', '_')}.pdf"

    if not pdf_path.exists():
        _download_pdf_from_doi(doi, pdf_path)

    if not pdf_path.exists():
        print(f"  Could not download PDF for DOI {doi}")
        return []

    return extract_from_pdf(pdf_path, llm_api_key=api_key, llm_model=model, llm_base_url=base_url, skip_grobid=True)


def _save_pdf_if_valid(output_path: Path, content: bytes) -> bool:
    """Save content only if it looks like a real PDF (%PDF magic bytes)."""
    if content[:5] == b"%PDF-" and len(content) > 10000:
        output_path.write_bytes(content)
        return True
    return False


def _download_pdf_from_doi(doi: str, output_path: Path) -> None:
    """Try to download a PDF from a DOI using arXiv and Semantic Scholar."""
    import httpx

    # Try arXiv first (best for open-access papers)
    try:
        arxiv_id = None
        resp = httpx.get(
            f"https://api.semanticscholar.org/graph/v1/paper/DOI:{doi}",
            params={"fields": "externalIds"},
            timeout=15,
        )
        if resp.status_code == 200:
            ext_ids = resp.json().get("externalIds", {})
            arxiv_id = ext_ids.get("ArXiv")

        if arxiv_id:
            pdf_url = f"https://arxiv.org/pdf/{arxiv_id}.pdf"
            pdf_resp = httpx.get(pdf_url, follow_redirects=True, timeout=60)
            if _save_pdf_if_valid(output_path, pdf_resp.content):
                print(f"  Downloaded PDF for {doi} from arXiv ({arxiv_id})")
                return
    except Exception:
        pass

    # Fallback: Semantic Scholar Direct PDF link
    try:
        resp = httpx.get(
            f"https://api.semanticscholar.org/graph/v1/paper/DOI:{doi}",
            params={"fields": "openAccessPdf"},
            timeout=15,
        )
        if resp.status_code == 200:
            data = resp.json()
            oa_url = data.get("openAccessPdf", {}).get("url")
            if oa_url:
                pdf_resp = httpx.get(oa_url, follow_redirects=True, timeout=60)
                if _save_pdf_if_valid(output_path, pdf_resp.content):
                    print(f"  Downloaded PDF for {doi} from Semantic Scholar OA")
                    return
    except Exception:
        pass

    # Fallback: SpringerLink direct PDF (works reliably for Springer Nature)
    try:
        if doi.startswith("10.1038/") or doi.startswith("10.1007/"):
            pdf_url = f"https://link.springer.com/content/pdf/{doi}.pdf"
            pdf_resp = httpx.get(pdf_url, follow_redirects=True, timeout=60)
            if _save_pdf_if_valid(output_path, pdf_resp.content):
                print(f"  Downloaded PDF for {doi} from SpringerLink")
                return
    except Exception:
        pass

    # Fallback: Unpaywall (reliable OA locator, covers MDPI/RSC/Elsevier OA etc.)
    try:
        from ssb_dataset.config.settings import settings

        mailto = settings.crossref.mailto
        resp = httpx.get(
            f"https://api.unpaywall.org/v2/{doi}",
            params={"email": mailto},
            timeout=15,
        )
        if resp.status_code == 200:
            data = resp.json()
            if data.get("is_oa"):
                candidate_urls: list[str] = []
                loc = data.get("best_oa_location") or {}
                for key in ("url_for_pdf", "url"):
                    if loc.get(key):
                        candidate_urls.append(loc[key])
                for oa_loc in data.get("oa_locations", []) or []:
                    for key in ("url_for_pdf", "url"):
                        u = oa_loc.get(key)
                        if u and u not in candidate_urls:
                            candidate_urls.append(u)
                for u in list(candidate_urls):
                    m = re.search(r"pmc/articles/(?:PMC)?(\d+)", u)
                    if m:
                        pmc_id = m.group(1)
                        candidate_urls.extend(
                            [
                                f"https://www.ncbi.nlm.nih.gov/pmc/articles/PMC{pmc_id}/pdf/",
                                f"https://europepmc.org/articles/PMC{pmc_id}?pdf=render",
                            ]
                        )
                for pdf_url in candidate_urls:
                    if any(host in pdf_url for host in ("europepmc.org", "ncbi.nlm.nih.gov", "springer.com", "arxiv.org")):
                        try:
                            pdf_resp = httpx.get(pdf_url, follow_redirects=True, timeout=30)
                            if _save_pdf_if_valid(output_path, pdf_resp.content):
                                print(f"  Downloaded PDF for {doi} from Unpaywall OA")
                                return
                        except Exception:
                            continue
                for pdf_url in candidate_urls:
                    try:
                        pdf_resp = httpx.get(pdf_url, follow_redirects=True, timeout=20)
                        if _save_pdf_if_valid(output_path, pdf_resp.content):
                            print(f"  Downloaded PDF for {doi} from Unpaywall OA")
                            return
                    except Exception:
                        continue
    except Exception:
        pass

    print(f"  Cannot download PDF for DOI {doi} (not open access)")
