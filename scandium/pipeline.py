from __future__ import annotations

import json
import re
import sys
import time
from pathlib import Path
from typing import Any

from scandium.ingestion.parser import parse_paper, save_paper
from scandium.ingestion.tables import extract_tables, tables_to_markdown
from scandium.ingestion.ocr import try_extract
from scandium.indexing.chunker import chunk_paper, build_chunk_metadata
from scandium.indexing.embeddings import index_chunks, query_collection
from scandium.indexing.bm25 import BM25Index, hybrid_retrieval
from scandium.retrieval.context_builder import build_context
from scandium.extraction import (
    extract_conductivity,
    extract_activation_energy,
    extract_composition,
    extract_primary_material,
    extract_experimental_text,
    EvidenceGraph,
    EvidenceNode,
)
from scandium.verification import full_verification_report
from scandium.resolver.evidence import merge_paper_results_into_evidence, build_dataset_record

CHECKPOINT_DIR = Path("scandium_output/checkpoints")

PIPELINE_VERSION = "0.3.0"


def _resolve_provenance(
    record: dict[str, Any],
    retrieval_results: list[dict[str, Any]],
    llm_model: str,
    prompt_version: str,
    fallback_section: str = "Unknown",
) -> dict[str, Any]:
    """Resolve page/section/sentence provenance for an extraction record.

    The LLM rarely echoes a reliable chunk reference, so we match the record's
    evidence text (notes/source) against the retrieved chunk texts. Preference:
      1. chunk whose text contains the extracted value string AND material
      2. chunk with max word overlap against the evidence sentence
      3. first retrieved chunk (top retrieval result)
    """
    source = record.get("source") or ""
    notes = record.get("notes") or ""
    source_lower = source.lower()
    provenance: dict[str, Any] = {
        "page": None,
        "section": fallback_section,
        "table_number": None,
        "sentence": "",
        "chunk_text": "",
        "llm_model": llm_model,
        "prompt_version": prompt_version,
        "pipeline_version": PIPELINE_VERSION,
    }

    table_match = re.search(r"table\s*(\d+)", source_lower)
    if table_match:
        provenance["table_number"] = int(table_match.group(1))

    value_str = ""
    raw = record.get("value")
    if raw is not None:
        value_str = f"{raw:.6g}" if isinstance(raw, float) else str(raw)
    material = record.get("material_formula") or record.get("_primary_composition") or ""
    material_norm = material.lower().replace(" ", "")

    evidence = notes or source
    evidence_norm = re.sub(r"\s+", " ", evidence.lower()).strip()
    evidence_words = set(evidence_norm.split()) if evidence_norm else set()

    NON_CONTENT_SECTIONS = {
        "references", "bibliography", "acknowledgements", "acknowledgments",
        "supplementary", "appendix", "supporting information",
    }

    best_idx = None
    best_score = 0.0

    for i, r in enumerate(retrieval_results):
        meta = r.get("metadata", {})
        section = (meta.get("section") or "").lower().strip()
        if section in NON_CONTENT_SECTIONS:
            continue
        chunk_text = r.get("text") or ""
        chunk_lower = chunk_text.lower()
        score = 0.0
        if value_str and value_str in chunk_lower:
            score += 3.0
        if material_norm and material_norm in chunk_lower.replace(" ", ""):
            score += 1.5
        if evidence_norm and evidence_norm[:80] in chunk_lower:
            score += 2.0
        if evidence_words and evidence_norm:
            overlap = len(evidence_words & set(chunk_lower.split()))
            if overlap > 0:
                score += min(overlap / max(len(evidence_words), 1), 1.0)
        if score > best_score:
            best_score = score
            best_idx = i

    if best_idx is not None and best_score > 0:
        meta = retrieval_results[best_idx].get("metadata", {})
        provenance["page"] = meta.get("page")
        provenance["section"] = meta.get("section", fallback_section)
        provenance["sentence"] = (retrieval_results[best_idx].get("text") or "")[:500]
        provenance["chunk_text"] = (retrieval_results[best_idx].get("text") or "")[:1000]

    return provenance


def _checkpoint(paper_id: str, stage: str, data: Any) -> None:
    path = CHECKPOINT_DIR / paper_id / f"{stage}.json"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, indent=2, default=str))


def _load_checkpoint(paper_id: str, stage: str) -> Any:
    path = CHECKPOINT_DIR / paper_id / f"{stage}.json"
    if path.exists():
        return json.loads(path.read_text())
    return None


def _filter_table_by_material(table_md: str, formulas: list[str]) -> str:
    if not formulas or not table_md:
        return table_md
    aliases = set()
    for f in formulas:
        aliases.add(f.lower().replace(" ", "").replace("(", "").replace(")", ""))
        aliases.add(f.lower().replace(" ", ""))
        element_match = re.match(r"([A-Z][a-z]*)", f)
        if element_match:
            aliases.add(element_match.group(1).lower())
    lines = table_md.split("\n")
    kept = [lines[0]] if lines else []
    for line in lines[1:]:
        line_lower = line.lower()
        if any(a in line_lower for a in aliases):
            kept.append(line)
    if len(kept) <= 1:
        return table_md
    return "\n".join(kept)


def _save_stage_result(
    output_dir: Path, paper_id: str, data: dict[str, Any]
) -> None:
    path = output_dir / paper_id / "extraction_result.json"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, indent=2, default=str))


def run_pipeline(
    pdf_path: str | Path,
    output_dir: str | Path = "scandium_output",
    chunk_size: int = 500,
    llm_model: str = "llama3.2:3b",
    api_key: str = "",
    base_url: str = "http://localhost:11434/v1",
) -> dict[str, Any]:
    pdf = Path(pdf_path)
    paper_id = pdf.stem
    out_path = Path(output_dir)
    CHECKPOINT_DIR.mkdir(parents=True, exist_ok=True)

    print(f"[pipeline] Processing {pdf.name}...")

    # --- Checkpoint: try resume ---
    result = _load_checkpoint(paper_id, "final")
    if result:
        print(f"[pipeline] Loaded from checkpoint: {len(result.get('evidence',[]))} evidence records")
        return result

    # --- Stage 0: Extract text + parse ---
    text, was_ocr = try_extract(pdf)
    if len(text) < 100:
        print(f"[pipeline] Too little text ({len(text)} chars) — skipping (likely non-PDF or scanned)")
        return _empty_result(pdf, {"note": "insufficient text content"})
    print(f"[pipeline] Extracted {len(text)} chars (OCR={was_ocr})")
    try:
        paper = parse_paper(pdf)
    except Exception as e:
        print(f"[pipeline] PDF parse error: {e} — skipping")
        return _empty_result(pdf, {"note": f"PDF parse error: {e}"})
    save_paper(paper, output_dir)
    print(f"[pipeline] Parsed: {len(paper.sections)} sections, {len(paper.paragraphs)} paragraphs")
    _checkpoint(paper_id, "parsed", {"n_sections": len(paper.sections), "n_paragraphs": len(paper.paragraphs)})
    # --- Table extraction ---
    tables = extract_tables(pdf)
    table_md = tables_to_markdown(tables)
    print(f"[pipeline] Extracted {len(tables)} tables")

    # --- Review detection ---
    is_review = False
    title = (paper.metadata.get("title") or "").lower()
    abstract_text = text[:2000].lower()
    # Check title for review keywords
    review_keywords = ["review", "mini-review", "mini review", "systematic review", "perspective", "tutorial"]
    if any(w in title for w in review_keywords):
        is_review = True
        print(f"[pipeline] Review detected: title contains 'review' keyword")
    # Check abstract for review indicators
    if not is_review:
        abstract_indicators = ["this review", "we review", "review of", "overview of", "survey of"]
        if any(w in abstract_text for w in abstract_indicators):
            is_review = True
            print(f"[pipeline] Review detected: abstract contains 'this review' indicator")
    # Check abstract for "review article" explicitly
    if not is_review:
        if "review article" in abstract_text:
            is_review = True
            print(f"[pipeline] Review detected: abstract contains 'review article'")
    # Paragraph count heuristic: reviews typically have 80+ paragraphs
    if not is_review:
        if len(paper.paragraphs) > 80:
            is_review = True
            print(f"[pipeline] Review detected: {len(paper.paragraphs)} paragraphs (exceeds 80 threshold)")
    if is_review:
        print(f"[pipeline] Skipping extraction — review paper")
        return _empty_result(paper, {"note": "review paper — no primary measurements"})

    # --- Stage 1: Primary material detection ---
    cached = _load_checkpoint(paper_id, "primary_material")
    if cached:
        primary = cached
        print(f"[pipeline] Primary material (cached): {primary.get('primary_material','?')}")
    else:
        experimental_text = extract_experimental_text(paper.sections, paper.paragraphs, max_chars=5000)
        primary = extract_primary_material(experimental_text, api_key, llm_model, base_url)
        _checkpoint(paper_id, "primary_material", primary)

    primary_formula = primary.get("primary_material", "") or ""
    primary_name = primary.get("name", "") or ""
    primary_confidence = primary.get("confidence", 0)
    print(f"[pipeline] Primary material: {primary_formula or '?'} (conf={primary_confidence:.2f})")

    # --- Stage 2: Build chunks + index ---
    chunks = chunk_paper(paper, chunk_size=chunk_size)
    chunks = build_chunk_metadata(chunks, paper)
    print(f"[pipeline] Created {len(chunks)} chunks")
    n_indexed = index_chunks(chunks)
    print(f"[pipeline] Indexed {n_indexed} chunks in ChromaDB")
    bm25 = BM25Index()
    bm25.add_documents(chunks)

    def hybrid_query(query: str, k: int = 7) -> list[dict[str, Any]]:
        vector_results = query_collection(query, n_results=k * 2)
        return hybrid_retrieval(query, chunks, vector_results, bm25, top_k=k)

    # --- Stage 3: Build compact contexts ---
    MAX_CTX = 2500
    formulas_for_table = [primary_formula, primary_name] if primary_formula else []

    if primary_formula:
        conductivity_query = (
            f"conductivity of {primary_formula} {primary_name} S/cm mS/cm"
        )
        ea_query = (
            f"activation energy Ea of {primary_formula} {primary_name} eV Arrhenius"
        )
    else:
        conductivity_query = "conductivity S/cm mS/cm solid electrolyte"
        ea_query = "activation energy eV Ea solid electrolyte"

    comp_results = hybrid_query(conductivity_query, k=5)
    comp_context = build_context(comp_results, max_chars=MAX_CTX)
    ea_results = hybrid_query(ea_query, k=5)
    ea_context = build_context(ea_results, max_chars=MAX_CTX)

    # Table-aware filtering: keep only rows matching primary material
    if table_md and primary_formula:
        filtered_table = _filter_table_by_material(table_md, formulas_for_table)
        if filtered_table:
            half = MAX_CTX // 2
            comp_context = f"--- TABLE (rows matching {primary_formula}) ---\n{filtered_table[:half]}\n\n{comp_context[:half]}"
            ea_context = f"--- TABLE (rows matching {primary_formula}) ---\n{filtered_table[:half]}\n\n{ea_context[:half]}"
        comp_context = comp_context[:MAX_CTX]
        ea_context = ea_context[:MAX_CTX]

    print(f"[pipeline] Contexts: σ={len(comp_context)} chars, Ea={len(ea_context)} chars")

    def _safe_extract(extract_fn, context, stage_name, **kwargs):
        cached = _load_checkpoint(paper_id, stage_name)
        if cached is not None:
            return cached
        try:
            result = extract_fn(context, api_key, llm_model, base_url, **kwargs)
            _checkpoint(paper_id, stage_name, result)
            return result
        except Exception as e:
            print(f"[pipeline] {stage_name} extraction failed: {e} — returning empty")
            return []

    # --- Stage 4: Extract compositions ---
    comps = _safe_extract(extract_composition, comp_context, "compositions", primary_hint=primary_formula)

    primary_family = ""
    for c in comps:
        if c.get("is_primary"):
            if not primary_formula:
                primary_formula = c.get("formula", "")
            primary_family = c.get("family", "")
            break
    if not primary_family and comps:
        primary_family = comps[0].get("family", "")
    _checkpoint(paper_id, "primary_family", {"formula": primary_formula, "family": primary_family})

    # --- Stage 5: Extract conductivity ---
    conds = _safe_extract(extract_conductivity, comp_context, "conductivity", primary_material=primary_formula, is_review=is_review)

    # --- Stage 6: Extract activation energy ---
    eas = _safe_extract(extract_activation_energy, ea_context, "activation_energy", family=primary_family, primary_material=primary_formula, is_review=is_review)

    # Annotate
    from scandium.extraction.conductivity import PROMPT_VERSION as COND_PROMPT_V, LLM_MODEL as COND_MODEL
    from scandium.extraction.activation_energy import PROMPT_VERSION as EA_PROMPT_V, LLM_MODEL as EA_MODEL
    for c in conds:
        c["_primary_composition"] = primary_formula
        c["_family"] = primary_family
        c["_provenance"] = _resolve_provenance(
            c, comp_results, COND_MODEL, COND_PROMPT_V, fallback_section="Table"
        )
    for e in eas:
        e["_primary_composition"] = primary_formula
        e["_family"] = primary_family
        e["_provenance"] = _resolve_provenance(
            e, ea_results, EA_MODEL, EA_PROMPT_V, fallback_section="Unknown"
        )

    # --- Stage 7: Build evidence graph with section labels ---
    evidence_graph = EvidenceGraph(primary_material=primary_formula)

    section_map: dict[int, str] = {}
    for s in paper.sections:
        for pnum in range(s.start_para, s.end_para + 1):
            section_map[pnum] = s.name

    chunk_section = {}
    for c in chunks:
        key = f"{c['para_num']}_{c['chunk_index']}"
        chunk_section[key] = c.get("section", "Unknown")

    for c in conds:
        src = c.get("source") or ""
        if "Table" in src:
            section = "Table"
        elif "Fig" in src:
            section = "Figure"
        else:
            chunk_key_match = re.search(r"Source (\d+)", str(c.get("notes", "")))
            section = "Unknown"
            if chunk_key_match:
                idx = int(chunk_key_match.group(1)) - 1
                if idx < len(comp_results):
                    section = comp_results[idx].get("metadata", {}).get("section", "Unknown")
        evidence_graph.add_raw(
            sentence=c.get("notes") or c.get("source") or "",
            material=c.get("material_formula") or primary_formula or "",
            property_type="conductivity",
            value=c.get("value", 0),
            unit=c.get("unit") or "",
            source_type=c.get("source_type") or "unknown",
            source=src,
            section=section,
            is_primary=c.get("is_primary_measurement", False),
            confidence=c.get("_confidence", 0),
            issues=c.get("_issues") or [],
        )
    for e in eas:
        evidence_graph.add_raw(
            sentence=e.get("notes") or e.get("source") or "",
            material=e.get("material_formula") or primary_formula or "",
            property_type="activation_energy",
            value=e.get("value", 0),
            unit=e.get("unit") or "",
            source_type=e.get("source_type") or "unknown",
            source=e.get("source") or "",
            section="Table" if "Table" in (e.get("source") or "") else "Unknown",
            is_primary=e.get("is_primary", False),
            confidence=e.get("_confidence", 0),
            issues=e.get("_issues") or [],
        )

    primary_nodes = evidence_graph.filter_primary()
    conds = [c for c in conds if any(
        (n.material or "") == (c.get("material_formula") or primary_formula or "")
        and n.property_type == "conductivity"
        and n.value == c.get("value", 0)
        for n in primary_nodes
    )]
    eas = [e for e in eas if any(
        (n.material or "") == (e.get("material_formula") or primary_formula or "")
        and n.property_type == "activation_energy"
        and n.value == e.get("value", 0)
        for n in primary_nodes
    )]

    high_conf_conds = [c for c in conds if c.get("_confidence", 0) >= 0.6]
    high_conf_eas = [e for e in eas if e.get("_confidence", 0) >= 0.6]
    flagged_conds = [c for c in conds if c.get("_confidence", 0) < 0.6]
    flagged_eas = [e for e in eas if e.get("_confidence", 0) < 0.6]

    print(f"[pipeline] Extracted: {len(comps)} compositions, "
          f"{len(high_conf_conds)} high-conf + {len(flagged_conds)} flagged σ, "
          f"{len(high_conf_eas)} high-conf + {len(flagged_eas)} flagged Ea")
    print(f"[pipeline] Evidence graph: {len(evidence_graph)} nodes, {len(primary_nodes)} primary")

    verification = full_verification_report(
        comps, high_conf_conds + flagged_conds, high_conf_eas + flagged_eas, primary_formula
    )

    result = {
        "paper_id": paper_id,
        "doi": paper.metadata.get("doi"),
        "metadata": paper.metadata,
        "primary_composition": primary_formula,
        "primary_material_detector": {
            "primary_material": primary_formula,
            "name": primary_name,
            "confidence": primary_confidence,
            "evidence": primary.get("evidence", ""),
        },
        "compositions": comps,
        "conductivities": {"high_confidence": high_conf_conds, "flagged": flagged_conds},
        "activation_energies": {"high_confidence": high_conf_eas, "flagged": flagged_eas},
        "evidence_graph_nodes": [n.to_dict() for n in evidence_graph.nodes],
        "evidence_graph": evidence_graph.summary(),
        "verification": verification,
        "n_chunks": len(chunks),
        "n_sections": len(paper.sections),
    }
    _checkpoint(paper_id, "result", result)

    evidence_records = merge_paper_results_into_evidence(result)
    dataset_record = build_dataset_record(evidence_records, {
        "paper_id": paper_id,
        "doi": paper.metadata.get("doi"),
        "title": paper.metadata.get("title"),
        "year": paper.metadata.get("year"),
    })
    result["evidence"] = evidence_records
    result["dataset_record"] = dataset_record

    _save_stage_result(out_path, paper_id, result)
    _checkpoint(paper_id, "final", result)
    return result


def _empty_result(paper_or_path: Any, extra: dict | None = None) -> dict[str, Any]:
    if hasattr(paper_or_path, "paper_id"):
        paper_id = paper_or_path.paper_id
        doi = getattr(paper_or_path, "metadata", {}).get("doi")
    else:
        paper_id = Path(paper_or_path).stem
        doi = None
    out: dict[str, Any] = {
        "paper_id": paper_id,
        "doi": doi,
        "primary_composition": "",
        "compositions": [],
        "conductivities": {"high_confidence": [], "flagged": []},
        "activation_energies": {"high_confidence": [], "flagged": []},
        "evidence_graph": {"total_nodes": 0, "primary_nodes": 0},
        "evidence": [],
        "dataset_record": {"n_evidence": 0, "n_high_confidence": 0, "n_flagged": 0},
    }
    if extra:
        out.update(extra)
    out_path = Path("scandium_output") / paper_id / "extraction_result.json"
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(json.dumps(out, indent=2, default=str))
    print(f"[pipeline] Result saved to {out_path}")
    return out


if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("Usage: python -m scandium.pipeline <pdf_path>")
        sys.exit(1)
    result = run_pipeline(sys.argv[1])
    hc = result.get("conductivities", {}).get("high_confidence", [])
    fl = result.get("conductivities", {}).get("flagged", [])
    print(f"[pipeline] Done: {len(hc)} high-conf, {len(fl)} flagged conductivities")
