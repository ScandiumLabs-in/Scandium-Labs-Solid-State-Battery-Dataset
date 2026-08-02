from __future__ import annotations

from typing import Any


def cross_encoder_score(query: str, texts: list[str]) -> list[float]:
    try:
        from sentence_transformers import CrossEncoder
    except ImportError:
        return [1.0 - (i * 0.01) for i in range(len(texts))]

    model = CrossEncoder("cross-encoder/ms-marco-MiniLM-L-6-v2")
    pairs = [[query, t] for t in texts]
    scores = model.predict(pairs)
    return scores.tolist()


def rerank(
    query: str,
    results: list[dict[str, Any]],
    top_k: int = 5,
) -> list[dict[str, Any]]:
    if not results:
        return results

    texts = [r["text"] for r in results]
    try:
        scores = cross_encoder_score(query, texts)
    except Exception:
        return results[:top_k]

    for r, s in zip(results, scores):
        r["rerank_score"] = float(s)

    results.sort(key=lambda x: -x.get("rerank_score", 0.0))
    return results[:top_k]
