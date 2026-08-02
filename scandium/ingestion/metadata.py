from __future__ import annotations

import re
from typing import Any

import httpx

DOI_PATTERN = re.compile(r"(10\.\d{4,}/[-._;()/:\w]+)", re.IGNORECASE)
TITLE_PATTERN = re.compile(r"^[A-Z][A-Za-z\s,;:\-()/0-9εμθ]{20,200}$", re.MULTILINE)


def extract_doi_from_text(text: str) -> str | None:
    m = DOI_PATTERN.search(text)
    if m:
        return m.group(0).rstrip(".,; ")
    return None


def extract_title_from_text(first_page: str) -> str | None:
    candidates = TITLE_PATTERN.findall(first_page[:2000])
    if candidates:
        return max(candidates, key=len).strip()
    return None


def lookup_doi(doi: str, email: str = "") -> dict[str, Any] | None:
    url = f"https://api.crossref.org/works/{doi}"
    headers = {"User-Agent": f"ScandiumLabs/1.0 ({email})" if email else "ScandiumLabs/1.0"}
    try:
        resp = httpx.get(url, headers=headers, timeout=15)
        resp.raise_for_status()
        data = resp.json()
        msg = data.get("message", {})
        return {
            "doi": doi,
            "title": msg.get("title", [None])[0] if msg.get("title") else None,
            "authors": [
                f"{a.get('given', '')} {a.get('family', '')}".strip()
                for a in msg.get("author", [])
            ],
            "year": msg.get("published-print", {}).get("date-parts", [[None]])[0][0]
            or msg.get("created", {}).get("date-parts", [[None]])[0][0],
            "journal": msg.get("container-title", [None])[0] if msg.get("container-title") else None,
            "publisher": msg.get("publisher"),
            "type": msg.get("type"),
        }
    except Exception:
        return None
