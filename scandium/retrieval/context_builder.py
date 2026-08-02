from __future__ import annotations

from typing import Any


def build_context(results: list[dict[str, Any]], max_chars: int = 8000) -> str:
    parts: list[str] = []
    total = 0

    for i, r in enumerate(results):
        header = f"--- Source {i+1} ---"
        meta = r.get("metadata", {})
        if isinstance(meta, dict):
            section = meta.get("section", "")
            page = meta.get("page", "")
            if section:
                header += f" [Section: {section}"
                if page:
                    header += f", Page: {page}"
                header += "]"
        text = r.get("text", "")
        block = f"{header}\n{text}"
        if total + len(block) > max_chars and total > 0:
            break
        parts.append(block)
        total += len(block)

    return "\n\n".join(parts)
