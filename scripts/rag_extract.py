#!/usr/bin/env python3
"""RAG-based extraction: chunk, embed, retrieve, then extract with Groq LLM.

Usage:
    python scripts/rag_extract.py literature_output/pdfs/sulfide_preprint.pdf

Embeds PDF paragraphs via Ollama (nomic-embed-text), retrieves conductivity-relevant
chunks from ChromaDB, and feeds only those chunks to the extraction LLM.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import Any

# ── Imports (lazy, fail fast) ─────────────────────────────────────────────────


def _check_deps():
    try:
        import chromadb  # noqa: F401
        import ollama   # noqa: F401
    except ImportError as e:
        print(f"Missing dependency: {e}")
        print("Install: pip install chromadb ollama")
        sys.exit(1)


_check_deps()

import chromadb
import ollama

# ── Chunking ──────────────────────────────────────────────────────────────────


def chunk_pdf_text(text: str, min_chunk: int = 100) -> list[dict[str, Any]]:
    """Split full PDF text into paragraph/section-aware chunks.

    Splits on double newlines (paragraph breaks), merges tiny fragments,
    keeps tables intact.
    """
    raw_chunks = text.split("\n\n")
    chunks: list[dict[str, Any]] = []
    buffer = ""

    for i, piece in enumerate(raw_chunks):
        piece = piece.strip()
        if not piece:
            continue
        # Keep table-like blocks intact (rows with pipes or numbers)
        is_table = any(c in piece[:80] for c in "|") and len(piece) > 60

        if is_table or len(buffer) + len(piece) > 2000:
            if buffer:
                chunks.append({"text": buffer, "idx": len(chunks)})
            if is_table:
                chunks.append({"text": piece, "idx": len(chunks)})
                buffer = ""
            else:
                buffer = piece
        else:
            buffer = (buffer + "\n\n" + piece) if buffer else piece

    if buffer:
        chunks.append({"text": buffer, "idx": len(chunks)})

    # Drop tiny fragments that are just headers or noise
    return [c for c in chunks if len(c["text"]) >= min_chunk]


# ── Embedding ─────────────────────────────────────────────────────────────────


def embed_chunks(chunks: list[dict[str, Any]], model: str = "nomic-embed-text") -> list[list[float]]:
    """Embed a list of text chunks via Ollama."""
    texts = [c["text"] for c in chunks]
    response = ollama.embed(model=model, input=texts)
    return response["embeddings"]


# ── Vector store ──────────────────────────────────────────────────────────────


def build_index(chunks: list[dict[str, Any]], embeddings: list[list[float]]) -> Any:
    """Build an in-memory ChromaDB index from chunks and their embeddings."""
    client = chromadb.Client()
    collection = client.create_collection(
        name="pdf_chunks",
        metadata={"hnsw:space": "cosine"},
    )
    ids = [str(c["idx"]) for c in chunks]
    texts = [c["text"] for c in chunks]
    collection.add(
        embeddings=embeddings,
        documents=texts,
        ids=ids,
    )
    return collection


# ── Retrieval ─────────────────────────────────────────────────────────────────


RETRIEVAL_QUERIES = [
    "room temperature ionic conductivity S/cm",
    "activation energy eV Arrhenius lithium",
    "bulk grain boundary conductivity solid electrolyte",
]

SOURCE_QUERIES = [
    "synthesis method solid state reaction",
    "composition stoichiometry doping",
    "EIS impedance measurement conditions",
]


MAX_CONTEXT_CHARS = 6000


def retrieve_relevant_chunks(
    collection: Any,
    queries: list[str] = RETRIEVAL_QUERIES,
    k: int = 2,
) -> list[str]:
    """Query the vector store for conductivity-relevant chunks, deduped."""
    seen: set[int] = set()
    results: list[tuple[float, str]] = []

    for query in queries:
        try:
            q_embed = ollama.embed(model="nomic-embed-text", input=[query])["embeddings"][0]
            hits = collection.query(query_embeddings=[q_embed], n_results=k)
        except Exception:
            continue

        for doc, dist in zip(hits["documents"][0], hits["distances"][0]):
            doc_hash = hash(doc)
            if doc_hash not in seen:
                seen.add(doc_hash)
                results.append((dist, doc))

    results.sort(key=lambda x: x[0])
    return [r[1] for r in results]


# ── Extraction (reuses existing pipeline) ─────────────────────────────────────


def extract_with_rag(
    pdf_path: str | Path,
    llm_api_key: str = "",
    llm_model: str = "llama3.2:3b",
    llm_base_url: str = "http://localhost:11434/v1",
    ensemble_size: int = 3,
) -> list[dict[str, Any]]:
    """Full RAG extraction pipeline: chunk → embed → retrieve → LLM extract."""
    from ssb_dataset.literature.extraction import (
        _extract_text_from_pdf,
        _extract_tables_from_pdf,
        run_llm_extraction,
        _fix_units,
        extraction_record_to_material_record,
        _aggregate_ensemble,
    )

    pdf_path = Path(pdf_path)

    # 1. Extract text + tables
    print(f"  [rag] Extracting text from {pdf_path.name}...")
    table_text = _extract_tables_from_pdf(pdf_path)
    prose_text = _extract_text_from_pdf(pdf_path)

    print(f"  [rag] Got {len(table_text)} table chars, {len(prose_text)} prose chars")

    # 2. Chunk the prose text
    chunks = chunk_pdf_text(prose_text)
    print(f"  [rag] Split into {len(chunks)} chunks")

    # 3. Embed and index
    print(f"  [rag] Embedding chunks via Ollama (nomic-embed-text)...")
    embeddings = embed_chunks(chunks)
    collection = build_index(chunks, embeddings)
    print(f"  [rag] Built ChromaDB index with {collection.count()} vectors")

    # 4. Retrieve relevant chunks
    relevant = retrieve_relevant_chunks(collection, k=min(5, len(chunks)))
    print(f"  [rag] Retrieved {len(relevant)} relevant chunks")

    # 5. Build the extraction text from retrieved chunks + tables
    extraction_text = ""
    chunk_sources: list[str] = []
    if table_text:
        extraction_text += f"--- TABLES ---\n{table_text}\n\n"
    if relevant:
        extraction_text += "--- RELEVANT SECTIONS ---\n"
        for i, chunk in enumerate(relevant):
            new_section = f"\n--- Section {i+1} ---\n{chunk}\n"
            if len(extraction_text) + len(new_section) > MAX_CONTEXT_CHARS:
                break
            extraction_text += new_section
            chunk_sources.append(chunk)

    print(f"  [rag] Extraction context: {len(extraction_text)} chars (vs 15000 without RAG)")

    if not extraction_text.strip():
        print("  [rag] No extraction context found")
        return []

    # 6. Run ensemble extraction on the focused context
    runs: list = []
    for i in range(ensemble_size):
        print(f"  [rag] LLM pass {i+1}/{ensemble_size}...")
        extracted = run_llm_extraction(
            extraction_text,
            api_key=llm_api_key,
            model=llm_model,
            base_url=llm_base_url,
        )
        extracted = _fix_units(extracted, extraction_text)
        runs.append(extracted)

    if ensemble_size > 1:
        extracted = _aggregate_ensemble(runs, min_consensus=ensemble_size - 1)
    else:
        extracted = runs[0]

    # 7. Convert to MaterialRecord and log source info
    records = []
    for er in extracted:
        mr = extraction_record_to_material_record(er)
        records.append(mr)

    print(f"  [rag] Extracted {len(records)} records from {len(relevant)} retrieved chunks "
          f"(ensemble={ensemble_size})")

    return records


# ── CLI ───────────────────────────────────────────────────────────────────────


def main():
    import argparse

    parser = argparse.ArgumentParser(description="RAG-based conductivity extraction")
    parser.add_argument("pdf", type=str, help="Path to PDF file")
    parser.add_argument("--ensemble", type=int, default=3, help="Ensemble size (default: 3)")
    parser.add_argument("--output", type=str, default="", help="Output JSON path (default: print to stdout)")
    parser.add_argument("--provider", type=str, default="local", choices=["local", "groq"],
                        help="LLM provider: local (Ollama) or groq (default: local)")
    args = parser.parse_args()

    # Load API key from .env (needed for Groq)
    env_path = Path(__file__).resolve().parent.parent / ".env"
    api_key = ""
    base_url = "http://localhost:11434/v1"
    model = "llama3.2:3b"

    if args.provider == "groq":
        if env_path.exists():
            for line in env_path.read_text().splitlines():
                if "=" in line:
                    k, v = line.strip().split("=", 1)
                    if k == "LLM_API_KEY":
                        api_key = v
        base_url = "https://api.groq.com/openai/v1"
        model = "llama-3.1-8b-instant"
        if not api_key:
            print("Error: LLM_API_KEY not found in .env (required for --provider groq)")
            sys.exit(1)

    pdf_path = Path(args.pdf)
    if not pdf_path.exists():
        print(f"Error: PDF not found: {pdf_path}")
        sys.exit(1)

    records = extract_with_rag(
        pdf_path,
        llm_api_key=api_key,
        llm_model=model,
        llm_base_url=base_url,
        ensemble_size=args.ensemble,
    )

    output = []
    for r in records:
        output.append({
            "composition": r.identity.material_id if hasattr(r, "identity") and r.identity else "",
            "family": r.identity.family.value if hasattr(r, "identity") and r.identity and r.identity.family else "",
            "sigma_S_per_cm": r.ion_transport.sigma_RT if hasattr(r, "ion_transport") else None,
            "Ea_eV": r.ion_transport.activation_energy_Ea if hasattr(r, "ion_transport") else None,
            "conductivity_type": r.ion_transport.conductivity_type.value if hasattr(r, "ion_transport") and r.ion_transport.conductivity_type else "",
            "confidence_score": r.ion_transport.conductivity_source_type.value if hasattr(r, "ion_transport") and r.ion_transport.conductivity_source_type else "",
            "notes": "",
        })

    result = json.dumps(output, indent=2)
    if args.output:
        Path(args.output).write_text(result)
        print(f"Saved {len(output)} records to {args.output}")
    else:
        print(result)


if __name__ == "__main__":
    main()
