"""Phase E5 — vision-capable evidence location tests.

Verifies that scanned (SCRIBED) PDFs — which return None from the text-layer
`locate_evidence` — can be recovered through `vision_locate_evidence`, and that
the vision path produces the SAME Evidence schema as the text path so it plugs
into the existing review pipeline unchanged.
"""

from __future__ import annotations

import sys
from pathlib import Path

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
    def test_text_layer_still_wins(self, tmp_path: Path) -> None:
        pdf = _make_pdf(tmp_path, TEXT, with_text_layer=True)
        ev = V.locate_evidence(pdf, "Li6PS5Cl", 1.187e-3, 0.32)
        assert ev is not None
        assert ev.found_sigma and ev.found_ea
        # fallback must prefer the text layer, not trigger vision
        V._vision_transcribe_bytes = lambda *a, **k: (_ for _ in ()).throw(
            AssertionError("vision should not run when text layer works"))
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

        def fake_transcribe(png, page_no, *, provider, model):
            return TEXT  # deterministic stand-in for a vision model's output
        V._vision_transcribe_bytes = fake_transcribe
        ev = V.vision_locate_evidence(pdf, "Li6PS5Cl", 1.187e-3, 0.32,
                                      provider="ollama", model="llava")
        assert ev is not None
        assert ev.found_sigma and ev.found_composition
        assert ev.sigma_in_window

    def test_fallback_uses_vision_when_scanned(self, tmp_path: Path, monkeypatch) -> None:
        pdf = _make_pdf(tmp_path, "", with_text_layer=False)
        monkeypatch.setenv("VISION_PROVIDER", "ollama")
        V._vision_transcribe_bytes = lambda png, n, *, provider, model: TEXT
        ev = V.locate_evidence_with_fallback(pdf, "Li6PS5Cl", 1.187e-3, 0.32)
        assert ev is not None and ev.found_sigma
        monkeypatch.delenv("VISION_PROVIDER")