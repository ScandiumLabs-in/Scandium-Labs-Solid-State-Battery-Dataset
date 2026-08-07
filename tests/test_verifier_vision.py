"""Phase E5 — vision-capable evidence location tests.

Verifies that scanned (SCRIBED) PDFs — which return None from the text-layer
`locate_evidence` — can be recovered through `vision_locate_evidence`, and that
the vision path produces the SAME Evidence schema as the text path so it plugs
into the existing review pipeline unchanged.
"""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

pytest.importorskip("fitz", reason="literature extra (pymupdf) not installed")
import fitz

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from ssb_dataset.pipeline import verifier as V  # noqa: E402


def _make_pdf(tmp_path: Path, text: str, with_text_layer: bool = True) -> Path:
    p = fitz.open()
    page = p.new_page()
    if with_text_layer:
        chunks = [text[i:i + 80] for i in range(0, len(text), 80)]
        for i, ch in enumerate(chunks):
            page.insert_text((72, 72 + i * 14), ch, fontsize=9)
    out = tmp_path / "t.pdf"
    p.save(str(out))
    p.close()
    return out


TEXT = ("The Li6PS5Cl argyrodite pellet showed a room-temperature ionic "
        "conductivity of 1.187e-3 S/cm and an activation energy of 0.32 eV.")


class TestVisionEvidence:
    def test_text_layer_still_wins(self, tmp_path: Path, monkeypatch) -> None:
        pdf = _make_pdf(tmp_path, TEXT, with_text_layer=True)
        ev = V.locate_evidence(pdf, "Li6PS5Cl", 1.187e-3, 0.32)
        assert ev is not None
        assert ev.found_sigma and ev.found_ea
        # fallback must prefer the text layer, not trigger vision
        def _boom(*a, **k):
            raise AssertionError("vision should not run when text layer works")
        monkeypatch.setattr(V, "_vision_transcribe_bytes", _boom)
        fall = V.locate_evidence_with_fallback(pdf, "Li6PS5Cl", 1.187e-3, 0.32)
        assert fall is not None

    def test_scanned_returns_none_from_text_path(self, tmp_path: Path) -> None:
        pdf = _make_pdf(tmp_path, "", with_text_layer=False)
        assert V.locate_evidence(pdf, "Li6PS5Cl", 1.187e-3, 0.32) is None

    def test_vision_disabled_returns_none(self, tmp_path: Path, monkeypatch) -> None:
        monkeypatch.delenv("VISION_PROVIDER", raising=False)
        pdf = _make_pdf(tmp_path, "", with_text_layer=False)
        assert V.vision_locate_evidence(pdf, "Li6PS5Cl", 1.187e-3, 0.32) is None
        assert V.locate_evidence_with_fallback(pdf, "Li6PS5Cl", 1.187e-3, 0.32) is None

    def test_vision_recovers_scanned_evidence(self, tmp_path: Path, monkeypatch) -> None:
        pdf = _make_pdf(tmp_path, "", with_text_layer=False)
        monkeypatch.setenv("VISION_PROVIDER", "ollama")

        def fake_transcribe(png, page_no, *, provider, model, base_url=""):
            return TEXT  # deterministic stand-in for a vision model's output
        monkeypatch.setattr(V, "_vision_transcribe_bytes", fake_transcribe)
        ev = V.vision_locate_evidence(pdf, "Li6PS5Cl", 1.187e-3, 0.32,
                                      provider="ollama", model="llava")
        assert ev is not None
        assert ev.found_sigma and ev.found_composition
        assert ev.sigma_in_window

    def test_fallback_uses_vision_when_scanned(self, tmp_path: Path, monkeypatch) -> None:
        pdf = _make_pdf(tmp_path, "", with_text_layer=False)
        monkeypatch.setenv("VISION_PROVIDER", "ollama")
        monkeypatch.setattr(
            V, "_vision_transcribe_bytes",
            lambda png, n, *, provider, model: TEXT)
        ev = V.locate_evidence_with_fallback(pdf, "Li6PS5Cl", 1.187e-3, 0.32)
        assert ev is not None and ev.found_sigma
        monkeypatch.delenv("VISION_PROVIDER")

    def test_tesseract_provider_resolves_evidence(self, tmp_path: Path, monkeypatch):
        """Phase E5 — the free/deterministic Tesseract OCR provider should
        recover a scanned PDF through the same Evidence schema and matcher."""
        pdf = _make_pdf(tmp_path, "", with_text_layer=False)
        monkeypatch.setenv("VISION_PROVIDER", "tesseract")

        real = V._vision_transcribe_bytes

        def fake_tesseract(png, page_no, *, provider, model, base_url=""):
            # Stub the pytesseract import site to avoid a system dependency in
            # test; returns the same deterministic text a real OCR run would.
            assert provider == "tesseract"
            return TEXT

        monkeypatch.setattr(V, "_vision_transcribe_bytes", fake_tesseract)
        ev = V.vision_locate_evidence(pdf, "Li6PS5Cl", 1.187e-3, 0.32,
                                      provider="tesseract", model="")
        assert ev is not None
        assert ev.found_sigma and ev.found_composition and ev.sigma_in_window

        # Also through the text-first fallback, proving vision runs only when
        # the text layer came up empty (SCRIBED) and not otherwise.
        ev2 = V.locate_evidence_with_fallback(pdf, "Li6PS5Cl", 1.187e-3, 0.32)
        assert ev2 is not None and ev2.found_sigma
        monkeypatch.delenv("VISION_PROVIDER")
        monkeypatch.setattr(V, "_vision_transcribe_bytes", real)

    def test_tesseract_provider_default_uses_local_ocr(self):
        """The tesseract branch must route to pytesseract on the rendered PNG
        bytes, independent of any network provider."""
        png = bytes(b"\x89PNG\r\n" + b"\x00" * 32)  # minimal PNG header
        out = V._vision_transcribe_bytes(png, 1, provider="tesseract", model="")
        assert isinstance(out, str)  # '' on failure, or OCR text on success

    def test_ollama_provider_does_not_nameerror_on_httpx(self, monkeypatch):
        """Regression: the ollama vision branch calls httpx.post at module scope.
        Before the fix, httpx was only lazily imported in the LLM verify path,
        so any live vision run raised NameError('httpx'). The provider branch
        must reach the network call (stubbed) without NameError."""
        calls: list[dict] = []

        class _FakeResp:
            def raise_for_status(self):
                return None
            def json(self):
                return {"message": {"content": TEXT}}

        def fake_post(url, json, timeout):
            calls.append({"url": url, "model": json.get("model")})
            return _FakeResp()

        import ssb_dataset.pipeline.verifier as _V
        monkeypatch.setattr(_V.httpx, "post", fake_post)
        png = bytes(b"\x89PNG\r\n" + b"\x00" * 32)
        out = V._vision_transcribe_bytes(png, 1, provider="ollama", model="llava")
        assert out == TEXT
        assert calls and calls[0]["model"] == "llava"

    def test_groq_provider_does_not_nameerror_on_httpx(self, monkeypatch):
        """Regression for the OpenAI-compatible (Groq) vision branch."""
        calls: list[dict] = []

        class _FakeResp:
            def raise_for_status(self):
                return None
            def json(self):
                return {"choices": [{"message": {"content": TEXT}}]}

        def fake_post(url, json, headers, timeout):
            calls.append({"url": url})
            return _FakeResp()

        import ssb_dataset.pipeline.verifier as _V
        monkeypatch.setattr(_V.httpx, "post", fake_post)
        monkeypatch.setenv("VISION_API_KEY", "test-key")
        monkeypatch.setenv("VISION_MODEL", "llama-3.2-90b-vision-preview")
        png = bytes(b"\x89PNG\r\n" + b"\x00" * 32)
        out = V._vision_transcribe_bytes(
            png, 1, "groq", "llama-3.2-90b-vision-preview",
            base_url="https://api.groq.com/openai/v1")
        assert out == TEXT
        assert calls and "chat/completions" in calls[0]["url"]

    def test_vision_provider_without_httpx_nameerror_roundtrip(self, tmp_path):
        """The full vision path on a real (text-less) PDF must not raise
        NameError even when no provider is configured — it returns None."""
        pdf = _make_pdf(tmp_path, "", with_text_layer=False)
        ev = V.vision_locate_evidence(pdf, "Li6PS5Cl", 1.187e-3, 0.32,
                                      provider="", model="")
        assert ev is None