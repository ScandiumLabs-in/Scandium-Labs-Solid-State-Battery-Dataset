from __future__ import annotations

import math
from collections import Counter
from typing import Any


class BM25Index:
    def __init__(self, k1: float = 1.5, b: float = 0.75):
        self.k1 = k1
        self.b = b
        self.documents: list[dict[str, Any]] = []
        self.doc_lengths: list[int] = []
        self.avg_doc_length: float = 0.0
        self.inverted: dict[str, dict[int, int]] = {}
        self.n_docs: int = 0

    def add_documents(self, docs: list[dict[str, Any]], field: str = "text") -> None:
        for doc in docs:
            self.documents.append(doc)
            tokens = doc.get(field, "").lower().split()
            self.doc_lengths.append(len(tokens))
            term_counts = Counter(tokens)
            for term, count in term_counts.items():
                if term not in self.inverted:
                    self.inverted[term] = {}
                self.inverted[term][self.n_docs] = count
            self.n_docs += 1

        self.avg_doc_length = (
            sum(self.doc_lengths) / self.n_docs if self.n_docs > 0 else 0.0
        )

    def search(self, query: str, top_k: int = 10) -> list[tuple[int, float, dict[str, Any]]]:
        query_tokens = query.lower().split()
        scores: list[float] = [0.0] * self.n_docs
        n = self.n_docs

        for qt in query_tokens:
            if qt not in self.inverted:
                continue
            posting = self.inverted[qt]
            idf = math.log((n - len(posting) + 0.5) / (len(posting) + 0.5) + 1.0)
            for doc_id, freq in posting.items():
                dl = self.doc_lengths[doc_id]
                numerator = freq * (self.k1 + 1.0)
                denominator = freq + self.k1 * (
                    1.0 - self.b + self.b * dl / self.avg_doc_length
                )
                scores[doc_id] += idf * numerator / denominator

        ranked = sorted(
            [(i, scores[i], self.documents[i]) for i in range(self.n_docs) if scores[i] > 0],
            key=lambda x: -x[1],
        )
        return ranked[:top_k]


def _chunk_key(c: dict[str, Any]) -> str:
    return f"{c['paper_id']}_{c['para_num']}_{c['chunk_index']}"


def hybrid_retrieval(
    query: str,
    chunks: list[dict[str, Any]],
    vector_results: list[dict[str, Any]],
    bm25_index: BM25Index,
    top_k: int = 10,
    alpha: float = 0.5,
) -> list[dict[str, Any]]:
    vector_docs = {r["id"]: r for r in vector_results}
    chunk_by_key = {f"{c['paper_id']}_{c['para_num']}_{c['chunk_index']}": c for c in chunks}

    bm25_results = bm25_index.search(query, top_k=top_k * 3)

    combined_scores: dict[str, float] = {}

    max_v = max((r["distance"] for r in vector_results), default=1.0)
    for r in vector_results:
        combined_scores[r["id"]] = alpha * (1.0 - r["distance"] / max_v)

    max_b = max((s[1] for s in bm25_results), default=1.0)
    for doc_idx, score, doc_data in bm25_results:
        doc_key = _chunk_key(doc_data)
        combined_scores[doc_key] = combined_scores.get(doc_key, 0.0) + (
            1.0 - alpha
        ) * (score / max_b)

    if not combined_scores:
        return vector_results[:top_k]

    ranked = sorted(combined_scores.items(), key=lambda x: -x[1])
    results: list[dict[str, Any]] = []
    for doc_key, score in ranked[:top_k]:
        if doc_key in vector_docs:
            item = vector_docs[doc_key].copy()
            item["hybrid_score"] = score
            results.append(item)
        elif doc_key in chunk_by_key:
            c = chunk_by_key[doc_key]
            results.append({
                "id": doc_key,
                "text": c["text"],
                "metadata": c,
                "distance": 0,
                "hybrid_score": score,
            })

    return results
