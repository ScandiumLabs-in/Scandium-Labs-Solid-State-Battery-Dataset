from __future__ import annotations

from pathlib import Path
from typing import Any

import chromadb
from chromadb.config import Settings


def get_chroma_client(persist_dir: str | Path = "scandium_output/chroma") -> chromadb.ClientAPI:
    path = Path(persist_dir)
    path.mkdir(parents=True, exist_ok=True)
    return chromadb.PersistentClient(
        path=str(path),
        settings=Settings(anonymized_telemetry=False),
    )


def index_chunks(
    chunks: list[dict[str, Any]],
    collection_name: str = "papers",
    persist_dir: str | Path = "scandium_output/chroma",
    model: str = "nomic-embed-text",
) -> int:
    import ollama

    client = get_chroma_client(persist_dir)
    try:
        client.delete_collection(collection_name)
    except Exception:
        pass
    collection = client.create_collection(collection_name)

    texts = [c["text"] for c in chunks]
    metadatas: list[dict[str, Any]] = []
    ids: list[str] = []
    for i, c in enumerate(chunks):
        metadatas.append({
            "paper_id": c["paper_id"],
            "section": c["section"],
            "page": str(c["page"]),
            "para_num": str(c["para_num"]),
            "chunk_index": str(c["chunk_index"]),
            "doi": c.get("doi", ""),
        })
        ids.append(f"{c['paper_id']}_{c['para_num']}_{c['chunk_index']}")

    batch_size = 32
    total = 0
    for i in range(0, len(texts), batch_size):
        batch_texts = texts[i : i + batch_size]
        batch_ids = ids[i : i + batch_size]
        batch_metas = metadatas[i : i + batch_size]

        embeddings = [
            ollama.embeddings(model=model, prompt=t)["embedding"]
            for t in batch_texts
        ]

        collection.add(
            embeddings=embeddings,
            documents=batch_texts,
            metadatas=batch_metas,
            ids=batch_ids,
        )
        total += len(batch_texts)

    return total


def query_collection(
    query: str,
    collection_name: str = "papers",
    persist_dir: str | Path = "scandium_output/chroma",
    n_results: int = 10,
    model: str = "nomic-embed-text",
) -> list[dict[str, Any]]:
    import ollama

    client = get_chroma_client(persist_dir)
    collection = client.get_collection(collection_name)

    q_embedding = ollama.embeddings(model=model, prompt=query)["embedding"]

    results = collection.query(
        query_embeddings=[q_embedding],
        n_results=n_results,
        include=["documents", "metadatas", "distances"],
    )

    outputs: list[dict[str, Any]] = []
    if results["ids"]:
        for i in range(len(results["ids"][0])):
            outputs.append({
                "id": results["ids"][0][i],
                "text": results["documents"][0][i],
                "metadata": results["metadatas"][0][i],
                "distance": results["distances"][0][i],
            })
    return outputs
