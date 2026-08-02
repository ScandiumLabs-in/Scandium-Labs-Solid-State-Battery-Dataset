from __future__ import annotations

from pathlib import Path
from typing import Any

import fitz


def needs_ocr(pdf_path: str | Path, min_chars: int = 500) -> bool:
    doc = fitz.open(str(pdf_path))
    total = sum(len(page.get_text()) for page in doc)
    doc.close()
    return total < min_chars


def ocr_pdf(pdf_path: str | Path) -> str | None:
    try:
        from pdf2image import convert_from_path
        import pytesseract
    except ImportError as e:
        raise ImportError(
            "OCR requires pdf2image and pytesseract. "
            "Install: pip install pdf2image pytesseract"
        ) from e

    images = convert_from_path(str(pdf_path), dpi=300)
    texts: list[str] = []
    for img in images:
        text = pytesseract.image_to_string(img, lang="eng")
        texts.append(text)
    return "\n".join(texts)


def try_extract(pdf_path: str | Path) -> tuple[str, bool]:
    doc = fitz.open(str(pdf_path))
    text = "\n".join(page.get_text() for page in doc)
    doc.close()
    was_ocr = False

    if len(text.strip()) < 500:
        try:
            ocr_text = ocr_pdf(pdf_path)
            if ocr_text and len(ocr_text.strip()) > len(text.strip()):
                text = ocr_text
                was_ocr = True
        except Exception:
            pass

    return text, was_ocr
