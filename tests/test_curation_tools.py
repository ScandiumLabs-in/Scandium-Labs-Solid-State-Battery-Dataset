"""Tests for the curation tooling — unit/temperature normalization,
material fingerprinting, and literature consensus engines."""

from __future__ import annotations

import math

import numpy as np
import pytest

from ssb_dataset.pipeline.consensus import (
    MAX_ORDER_SPREAD,
    MaterialConsensus,
    compute_consensus,
)
from ssb_dataset.pipeline.fingerprint import (
    fingerprint,
    group_key,
    same_material,
)
from ssb_dataset.pipeline.normalization import (
    c_to_k,
    normalize_ea,
    normalize_record_units,
    normalize_sigma,
    normalize_temperature,
)


# --------------------------------------------------------------------------
# Unit + temperature normalization
# --------------------------------------------------------------------------

class TestNormalizeSigma:
    @pytest.mark.parametrize("value,unit,expected", [
        ("0.81", "mS/cm", 8.1e-4),
        ("0.81", "uS/cm", 8.1e-7),
        ("4.5", "S/m", 4.5e-2),
        ("3.2e-4", "S/cm", 3.2e-4),
        ("0.5", "Ω^-1cm^-1", 0.5),
        ("0.5", "Ω⁻¹cm⁻¹", 0.5),
        ("1.2E-3", "ohm^-1 cm^-1", 1.2e-3),
        ("2", "S m-1", 2e-2),
        ("-4.5", "log σ", 10 ** -4.5),
        ("1e-3", "S/cm", 1e-3),
    ])
    def test_units(self, value, unit, expected):
        r = normalize_sigma(value, unit)
        assert r.value_s_per_cm == pytest.approx(expected)

    def test_log_form_flag(self):
        r = normalize_sigma("-4", "log10")
        assert r.is_log is True
        assert r.value_s_per_cm == pytest.approx(1e-4)

    def test_no_unit_keeps_value_but_flags(self):
        r = normalize_sigma("1e-3", None)
        assert r.value_s_per_cm == pytest.approx(1e-3)
        assert "no unit" in r.note

    def test_none_value_raises(self):
        with pytest.raises(ValueError):
            normalize_sigma(None, "S/cm")


class TestNormalizeEa:
    def test_kj_mol(self):
        # 40 kJ/mol ~ 0.4146 eV (via 1/96.485)
        assert normalize_ea("40", "kJ/mol") == pytest.approx(0.41457, abs=1e-3)

    def test_mev(self):
        assert normalize_ea("350", "meV") == pytest.approx(0.35)

    def test_bare_eV_default(self):
        assert normalize_ea("0.35", None) == pytest.approx(0.35)

    def test_unparseable_unit(self):
        with pytest.raises(ValueError):
            normalize_ea("0.35", "furlongs")


class TestNormalizeTemperature:
    def test_k_to_c(self):
        assert normalize_temperature("298", "K") == pytest.approx(24.85, abs=0.01)

    def test_c_to_c(self):
        assert normalize_temperature("25", "C") == pytest.approx(25)

    def test_c_to_k(self):
        assert c_to_k(25) == pytest.approx(298.15)

    def test_bare_number_assumed_c(self):
        assert normalize_temperature("25") == pytest.approx(25)


class TestNormalizeRecordUnits:
    def _rec(self, **kw):
        base = dict(property="conductivity", value=0.81, unit="mS/cm",
                    temperature_celsius=None)
        base.update(kw)
        return base

    def test_ms_cm_conversion_written_back(self):
        rec = normalize_record_units(self._rec())
        assert rec["normalized_sigma"] == pytest.approx(8.1e-4)
        assert rec["sigma_multiplier"] == pytest.approx(1e-3)
        assert "normalization_issues" in rec

    def test_temperature_k_record(self):
        rec = normalize_record_units(self._rec(temperature_K=298))
        assert rec["normalized_temperature_c"] == pytest.approx(24.85, abs=0.01)
        assert rec["temperature_K"] == pytest.approx(298)

    def test_ea_normalized(self):
        rec = normalize_record_units(self._rec(Ea=40, ea_unit="kJ/mol"))
        assert rec["normalized_ea"] == pytest.approx(0.41457, abs=1e-3)

    def test_ea_property_not_misread_as_sigma(self):
        # an activation-energy record must NOT produce a normalized_sigma that
        # would poison the consensus group with a fake conductivity value
        rec = normalize_record_units(dict(property="activation_energy",
                                          value=0.21, unit="eV"))
        assert "normalized_sigma" not in rec
        assert rec["normalized_ea"] == pytest.approx(0.21)

    def test_idempotent_rerun(self):
        # re-running must not inherit a wrong classification from a previous run
        rec = dict(property="activation_energy", value=0.21, unit="eV")
        rec["normalized_sigma"] = 0.21  # simulate a stale wrong field
        normalize_record_units(rec)
        assert "normalized_sigma" not in rec
        assert rec["normalized_ea"] == pytest.approx(0.21)


# --------------------------------------------------------------------------
# Fingerprinting
# --------------------------------------------------------------------------

class TestFingerprint:
    def test_alias_resolution(self):
        f = fingerprint("LLZO")
        assert f["reduced_formula"] == "Li7La3Zr2O12"
        assert f["alias_resolved"] == "LLZO"

    def test_reduced_formula(self):
        f = fingerprint("Li7La3Zr2O12")
        assert f["reduced_formula"] == "Li7La3Zr2O12"
        assert "Li" in f["key_elements"]

    def test_same_material_whitespace_variant(self):
        assert same_material("Li7La3Zr2O12", "Li7 La3 Zr2 O12")

    def test_same_material_ratio_variants(self):
        # Li6PS5Cl vs Li6PS5Cl.5 (close ratio) -> same reduced formula
        assert same_material("Li6PS5Cl", "Li6PS5Cl")

    def test_group_key_stable(self):
        assert group_key("Li7La3Zr2O12") == "Li7La3Zr2O12"
        assert group_key("Li7La3Zr2O12 ") == "Li7La3Zr2O12"

    def test_type_descriptor_stripped(self):
        # "X-type (composition)" -> the parenthetical IS the identity
        assert group_key("Li10GeP2S12-type (Li9.54Si1.74P1.44S11.7Cl0.3)") == "Li9.54Si1.74P1.44S11.7Cl0.3"
        assert group_key("Li10GeP2S12-type(Li9.54Si1.74P1.44S11.7Cl0.3)") == "Li9.54Si1.74P1.44S11.7Cl0.3"

    def test_type_descriptor_groups_with_base(self):
        assert same_material("Li10GeP2S12-type (Li9.54Si1.74P1.44S11.7Cl0.3)",
                             "Li9.54Si1.74P1.44S11.7Cl0.3")

    def test_dopant_suffix_preserved(self):
        # Ta-doped LLZO is a distinct benchmark material, NOT the pristine phase
        assert group_key("Li7La3Zr2O12:Ta") != group_key("Li7La3Zr2O12")

    def test_paren_label_kept_when_stoichiometric(self):
        # a genuine two-component composite is not a descriptor
        assert group_key("0.7Li(CB9H10)-0.3Li(CB11H12)") == "0.7Li(CB9H10)-0.3Li(CB11H12)"

    def test_lgps_notation_variants_agree(self):
        # Li10Ge(PS6)2 and Li10GeP2S12 are the same reduced formula in pymatgen
        assert same_material("Li10Ge(PS6)2", "Li10GeP2S12")

    def test_unresolvable_falls_back(self):
        f = fingerprint("some prose with Li and Zr")
        assert f["reduced_formula"] == ""
        assert "Li" in f["key_elements"]


# --------------------------------------------------------------------------
# Literature consensus
# --------------------------------------------------------------------------

class TestConsensus:
    def _recs(self):
        return [
            dict(review_id="a", composition="Li2ZrCl6", property="conductivity",
                 value=0.00081, unit="S/cm"),
            dict(review_id="b", composition="Li2ZrCl6", property="conductivity",
                 value=5.81e-7, unit="S/cm"),
            dict(review_id="c", composition="Li2ZrCl6", property="conductivity",
                 value=0.0007, unit="S/cm"),
            dict(review_id="d", composition="Li2ZrCl6", property="conductivity",
                 value=0.0006, unit="S/cm"),
        ]

    def test_grouped_and_median(self):
        from ssb_dataset.pipeline.normalization import normalize_record_units
        recs = self._recs()
        for r in recs:
            normalize_record_units(r)
        res = compute_consensus(recs)
        mc = res.materials["Li2ZrCl6"]
        assert mc.n_sigma == 4
        assert mc.median_sigma == pytest.approx(6.48e-4, rel=0.05)

    def test_outlier_flagged(self):
        from ssb_dataset.pipeline.normalization import normalize_record_units
        recs = self._recs()
        for r in recs:
            normalize_record_units(r)
        res = compute_consensus(recs)
        assert any(f["review_id"] == "b" for f in res.flagged)
        assert not any(f["review_id"] == "a" for f in res.flagged)

    def test_log_space_aggregation(self):
        recs = [
            dict(review_id="x", composition="A", value=1e-3, unit="S/cm"),
            dict(review_id="y", composition="A", value=1e-4, unit="S/cm"),
            dict(review_id="z", composition="A", value=1e-5, unit="S/cm"),
        ]
        from ssb_dataset.pipeline.normalization import normalize_record_units
        for r in recs:
            normalize_record_units(r)
        res = compute_consensus(recs)
        mc = res.materials["A"]
        # geometric mean of 1e-3,1e-4,1e-5 = 1e-4
        assert mc.median_sigma == pytest.approx(1e-4)

    def test_consensus_threshold(self):
        mc = MaterialConsensus(group="X", sigma_values=[1e-3, 1e-4])
        assert not mc.has_consensus  # n=2 < 3
        mc2 = MaterialConsensus(group="X", sigma_values=[1e-3, 1e-4, 1e-5])
        assert mc2.has_consensus

    def test_no_flag_below_consensus_n(self):
        # n=2 group with wildly different values: neither can be an outlier
        # against a non-existent consensus (both may be right or one wrong)
        from ssb_dataset.pipeline.normalization import normalize_record_units
        recs = [
            dict(review_id="p", composition="M", value=0.00081, unit="S/cm"),
            dict(review_id="q", composition="M", value=5.81e-7, unit="S/cm"),
        ]
        for r in recs:
            normalize_record_units(r)
        res = compute_consensus(recs)
        assert res.flagged == []

    def test_ea_records_do_not_join_sigma_consensus(self):
        # an activation-energy record in the queue must not contribute a fake
        # sigma to the material group (would create spurious outliers)
        from ssb_dataset.pipeline.normalization import normalize_record_units
        recs = [
            dict(review_id="s1", composition="M", value=1e-3, unit="S/cm"),
            dict(review_id="s2", composition="M", value=2e-3, unit="S/cm"),
            dict(review_id="s3", composition="M", value=1.5e-3, unit="S/cm"),
            dict(review_id="e1", composition="M", property="activation_energy",
                 value=0.21, unit="eV"),
        ]
        for r in recs:
            normalize_record_units(r)
        res = compute_consensus(recs)
        mc = res.materials["M"]
        assert mc.n_sigma == 3          # the Ea record is excluded from sigma
        assert mc.n_ea == 1
        assert res.flagged == []


def test_filer_existing_keys_match_add_key_7_field():
    """Regression: _existing_keys must build the same 7-field key as the
    filer's add-check, or every re-run re-adds every record (85 phantom
    pending items / 81 duplicate review_ids on 2026-08-01)."""
    import sys
    from pathlib import Path
    sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
    from file_extraction_to_queue import _existing_keys

    queue = {
        "items": [
            {
                "paper_id": "10.9999_paper",
                "composition": "LiX",
                "property": "conductivity",
                "value": 0.0001,
                "unit": "S/cm",
                "temperature_celsius": 25.0,
                "conductivity_type": "total",
            },
            {
                "paper_id": "10.9999_paper",
                "composition": "LiX",
                "property": "activation_energy",
                "value": 0.3,
                "unit": "eV",
                "temperature_celsius": None,
                "conductivity_type": None,
            },
        ]
    }
    keys = _existing_keys(queue)
    assert (
        "10.9999_paper|LiX|conductivity|0.0001|S/cm|25.0|total" in keys
    )
    assert (
        "10.9999_paper|LiX|activation_energy|0.3|eV|None|None" in keys
    )

    # the add-key computed by the filer for the same record must be present
    sigma_key = (
        f"10.9999_paper|LiX|conductivity|{0.0001}|S/cm|"
        f"{25.0}|total"
    )
    assert sigma_key in keys
