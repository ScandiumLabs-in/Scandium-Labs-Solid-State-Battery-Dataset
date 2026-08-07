"""Regression tests for the deterministic evidence verifier.

Covers the two false-positive classes that let compromised records auto-approve:

1. Unit-context requirement (`_has_unit_context`) — a numeric match is only
   accepted when a conductivity/Ea unit token is actually near the number, so
   coincidental figures (cycle rates "0.2C", x-substitution "x = 0.2",
   temperatures) are not mistaken for the reported sigma/Ea.

2. The meV trap — `ev\b` (IGNORECASE) matches the "eV" inside "meV", so a
   neutron-spectrometer "~ 0.1 meV" energy resolution was stamped as Ea=0.1 eV
   for Na3PS4 and re-auto-approved. `(?<![a-z])ev\b` rejects that.
"""

from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "scripts"))

from verify_extraction_evidence import _has_unit_context, find_nearby_value


class TestVisionScannedFallback:
    """Phase E5 — scanned (SCRIBED) PDFs get an evidence-backed verdict via the
    vision path instead of an unconditional SCRIBED stamp."""

    def test_no_pdf_stays_scribed(self, tmp_path, monkeypatch) -> None:
        from verify_extraction_evidence import _verify_scanned_with_vision
        res = _verify_scanned_with_vision(tmp_path / "missing.pdf", "x.pdf",
                                          "Li6PS5Cl", 1.187e-3, 0.32)
        assert res["verdict"] == "SCRIBED"
        assert res["vision"] is True

    def test_vision_found_stamps_evidence(self, tmp_path, monkeypatch) -> None:
        from verify_extraction_evidence import _verify_scanned_with_vision
        from ssb_dataset.pipeline.verifier import Evidence

        def fake_vision(pdf, comp, sigma, ea):
            return Evidence(
                page=3,
                window="the pellet showed a conductivity of 1.187e-3 S/cm",
                sigma_in_window="conductivity of 1.187e-3 S/cm",
                found_sigma=True, found_composition=True,
                found_ea=False)

        monkeypatch.setattr(
            "ssb_dataset.pipeline.verifier.vision_locate_evidence", fake_vision)
        res = _verify_scanned_with_vision(tmp_path / "scan.pdf", "scan.pdf",
                                          "Li6PS5Cl", 1.187e-3, 0.32)
        assert res["verdict"] == "FOUND"
        assert res["digit_match"] is True
        assert res["pages"] == [3]
        assert res["evidence"][0]["source"] == "vision"

    def test_vision_false_sigma_demoted_without_unit_context(self, tmp_path, monkeypatch) -> None:
        """The OCR-noise guard: a number that matches by value tolerance but
        carries no conductivity unit in context (e.g. '0.12 times the
        cross-sectional area' matching a uS/cm variant) must NOT stamp a sigma
        FOUND — it demotes to PARTIAL/NOT_FOUND instead."""
        from verify_extraction_evidence import _verify_scanned_with_vision
        from ssb_dataset.pipeline.verifier import Evidence

        def fake_vision(pdf, comp, sigma, ea):
            return Evidence(
                page=6,
                window="280.40 times the ionic conductivity and 0.12 times the "
                       "cross-sectional area of Region I",
                sigma_in_window="and 0.12 times the cross-sectional area of Region I",
                found_sigma=True, found_composition=True,
                found_ea=False)

        monkeypatch.setattr(
            "ssb_dataset.pipeline.verifier.vision_locate_evidence", fake_vision)
        res = _verify_scanned_with_vision(tmp_path / "scan.pdf", "scan.pdf",
                                          "PEO-LiTFSI", 1.69e-7, None)
        assert res["verdict"] == "PARTIAL"
        assert res["digit_match"] is False
        assert res["evidence"][0]["values_found"] == [None, None]

    def test_vision_no_match_stamps_not_found(self, tmp_path, monkeypatch) -> None:
        from verify_extraction_evidence import _verify_scanned_with_vision

        monkeypatch.setattr(
            "ssb_dataset.pipeline.verifier.vision_locate_evidence",
            lambda *a, **k: None)
        res = _verify_scanned_with_vision(tmp_path / "scan.pdf", "scan.pdf",
                                          "Li6PS5Cl", 1.187e-3, 0.32)
        assert res["verdict"] == "SCRIBED"
        assert "not configured" in res.get("note", "")



class TestUnitContext:
    def test_mev_is_not_ea_context(self) -> None:
        text = "an elastic energy resolution of ~ 0.1 meV, as determined"
        assert not _has_unit_context(text, text.index("0.1"), text.index("0.1") + 3, "Ea")

    def test_standalone_ev_is_ea_context(self) -> None:
        text = "an activation energy of 0.276 eV"
        assert _has_unit_context(text, text.index("0.276"), text.index("0.276") + 5, "Ea")

    def test_adjacent_ev_is_ea_context(self) -> None:
        text = "low activation energy (0.13 eV)"
        assert _has_unit_context(text, text.index("0.13"), text.index("0.13") + 4, "Ea")

    def test_activation_word_counts_without_unit(self) -> None:
        text = "activation energy = 0.45"
        assert _has_unit_context(text, text.index("0.45"), text.index("0.45") + 4, "Ea")

    def test_sigma_requires_conductivity_unit(self) -> None:
        text = "the capacity reached 2000 mAh at 0.0005 C"
        assert not _has_unit_context(text, text.index("0.0005"), text.index("0.0005") + 6, "sigma")

    def test_sigma_with_s_per_cm_is_context(self) -> None:
        text = "ionic conductivity of 2.9x10-4 S cm-1 at 25 C"
        assert _has_unit_context(text, text.index("2.9"), text.index("2.9") + 3, "sigma")


class TestFindNearbyValue:
    def test_rejects_zero_matches(self) -> None:
        # The 1.4Li2O leak: target sigma=2.55e-6 matched axis tick "0.000".
        text = "Arrhenius plot 0.000 0.001 0.002 0.003"
        found = find_nearby_value(text, [("sigma", 2.55e-6)])
        assert found == []

    def test_rejects_mev_resolution_as_ea(self) -> None:
        # The Na3PS4 leak: "~ 0.1 meV" resolution falsely matched Ea=0.1.
        text = ("Spectra were measured using an incident wavelength of 5.12 A "
                "offering an elastic energy resolution of ~ 0.1 meV.")
        found = find_nearby_value(text, [("Ea", 0.1)])
        assert found == []

    def test_finds_genuine_ea(self) -> None:
        text = "shows an activation energy of 0.276 eV (Arrhenius plot)"
        found = find_nearby_value(text, [("Ea", 0.276)])
        assert len(found) == 1
        assert found[0]["label"] == "Ea"
        assert abs(found[0]["found"] - 0.276) < 1e-9

    def test_rejects_bare_number_without_unit(self) -> None:
        # 1.4Li2O paper: "2.55 mS cm-1" — but a bare "2.55" elsewhere with no
        # unit token must not match sigma=2.55e-6 (nor would it be in range).
        text = "the pellet weight was 2.55 g and the diameter 10 mm"
        found = find_nearby_value(text, [("sigma", 2.55e-6)])
        assert found == []

    def test_finds_genuine_sigma(self) -> None:
        text = "high ionic conductivity of 2.9x10-4 S cm-1 at 25 C"
        found = find_nearby_value(text, [("sigma", 2.9e-4)])
        assert len(found) == 1
        assert found[0]["label"] == "sigma"

    def test_rejects_zero_value_number(self) -> None:
        # A legit sigma target never equals 0; the axis tick "0" must not match.
        text = "0 1 2 3 4 5 conductivity mS/cm"
        found = find_nearby_value(text, [("sigma", 1e-4)])
        assert found == []
