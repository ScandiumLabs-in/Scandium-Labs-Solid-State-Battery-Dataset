"""Tests for v1.5 — negative results database (Phase C).

Covers the deterministic anti-survivorship-bias signals (thermodynamically
unstable, electronic conductor, poor Li-transport proxy), the unknown-never-
fabricated convention, threshold behavior, and the canonical build. No
network, no LLM.
"""

from __future__ import annotations

import pandas as pd

from ssb_dataset.negative import negative as N


def _row(**kw):
    row = {
        "thermodynamics.energy_above_hull": None,
        "thermodynamics.is_metal": None,
        "thermodynamics.band_gap": None,
        "structure.li_hopping_distance": None,
    }
    aliases = {
        "energy_above_hull": "thermodynamics.energy_above_hull",
        "is_metal": "thermodynamics.is_metal",
        "band_gap": "thermodynamics.band_gap",
        "li_hopping_distance": "structure.li_hopping_distance",
    }
    for k, v in kw.items():
        row[aliases.get(k, k)] = v
    return row


# --------------------------------------------------------------------------
# per-record signals
# --------------------------------------------------------------------------

def test_clean_record_not_negative():
    r = N.evaluate_row(_row(energy_above_hull=0.0, is_metal=False,
                            band_gap=4.4, li_hopping_distance=2.9))
    assert r["negative.is_negative_result"] is False
    assert r["negative.reasons"] == []
    assert r["negative.confidence"] == "high"


def test_unstable_signal():
    r = N.evaluate_row(_row(energy_above_hull=0.1, is_metal=False,
                            band_gap=3.0, li_hopping_distance=3.0))
    assert r["negative.is_negative_result"] is True
    assert "thermodynamically_unstable" in r["negative.reasons"]
    assert r["negative.confidence"] == "high"


def test_unstable_threshold_boundary():
    inside = N.evaluate_row(_row(energy_above_hull=0.025, is_metal=False,
                                 band_gap=3.0, li_hopping_distance=3.0))
    outside = N.evaluate_row(_row(energy_above_hull=0.026, is_metal=False,
                                  band_gap=3.0, li_hopping_distance=3.0))
    assert "thermodynamically_unstable" not in inside["negative.reasons"]
    assert "thermodynamically_unstable" in outside["negative.reasons"]


def test_electronic_conductor_via_metal():
    r = N.evaluate_row(_row(energy_above_hull=0.0, is_metal=True,
                            band_gap=1.2, li_hopping_distance=3.0))
    assert "electronic_conductor" in r["negative.reasons"]


def test_electronic_conductor_via_zero_gap():
    r = N.evaluate_row(_row(energy_above_hull=0.0, is_metal=False,
                            band_gap=0.0, li_hopping_distance=3.0))
    assert "electronic_conductor" in r["negative.reasons"]


def test_poor_transport_proxy_medium_confidence():
    r = N.evaluate_row(_row(energy_above_hull=0.0, is_metal=False,
                            band_gap=3.0, li_hopping_distance=4.9))
    assert "poor_li_transport_proxy" in r["negative.reasons"]
    # only-proxy flags are medium confidence (proxy, not measured conductivity)
    assert r["negative.confidence"] == "medium"


def test_hop_threshold_boundary():
    inside = N.evaluate_row(_row(energy_above_hull=0.0, is_metal=False,
                                 band_gap=3.0, li_hopping_distance=4.5))
    outside = N.evaluate_row(_row(energy_above_hull=0.0, is_metal=False,
                                  band_gap=3.0, li_hopping_distance=4.51))
    assert "poor_li_transport_proxy" not in inside["negative.reasons"]
    assert "poor_li_transport_proxy" in outside["negative.reasons"]


def test_multiple_signals_accumulate():
    r = N.evaluate_row(_row(energy_above_hull=0.1, is_metal=True,
                            band_gap=0.0, li_hopping_distance=5.0))
    assert set(r["negative.reasons"]) == {
        "thermodynamically_unstable", "electronic_conductor",
        "poor_li_transport_proxy"}
    assert r["negative.confidence"] == "high"  # hard fact dominates


def test_no_signal_data_is_unknown_not_false():
    r = N.evaluate_row(_row())
    assert r["negative.is_negative_result"] is None
    assert r["negative.reasons"] == []
    assert r["negative.confidence"] is None


def test_partial_signal_data_evaluates_what_exists():
    # only a band gap present -> can still fire electronic conductor
    r = N.evaluate_row(_row(band_gap=0.0))
    assert r["negative.is_negative_result"] is True
    assert r["negative.reasons"] == ["electronic_conductor"]


def test_nan_handling():
    r = N.evaluate_row(_row(energy_above_hull=float("nan"),
                            band_gap=2.0))
    assert r["negative.energy_above_hull_eV_atom"] is None
    assert "thermodynamically_unstable" not in r["negative.reasons"]


def test_evidence_carries_raw_values():
    r = N.evaluate_row(_row(energy_above_hull=0.1, band_gap=3.0,
                            li_hopping_distance=3.0))
    assert r["negative.evidence"]["energy_above_hull_eV_atom"] == 0.1
    assert r["negative.evidence"]["li_hopping_distance_A"] == 3.0


# --------------------------------------------------------------------------
# known-good electrolytes sanity
# --------------------------------------------------------------------------

def test_known_good_electrolyte_not_flagged():
    for row in [
        _row(energy_above_hull=0.0068, is_metal=False, band_gap=4.45,
             li_hopping_distance=2.9),   # LLZO
        _row(energy_above_hull=0.0, is_metal=False, band_gap=2.81,
             li_hopping_distance=3.0),   # Li3PS4
    ]:
        r = N.evaluate_row(row)
        assert r["negative.is_negative_result"] is False, r["negative.reasons"]


# --------------------------------------------------------------------------
# whole-canonical build
# --------------------------------------------------------------------------

def test_build_negative_frame_columns(tmp_path, monkeypatch):
    canon = pd.DataFrame([
        {"identity.material_id": "mp-a", "identity.source_db": "materials_project",
         "thermodynamics.energy_above_hull": 0.1,
         "thermodynamics.is_metal": False, "thermodynamics.band_gap": 2.0,
         "structure.li_hopping_distance": 3.0},
        {"identity.material_id": "mp-b", "identity.source_db": "materials_project",
         "thermodynamics.energy_above_hull": 0.0,
         "thermodynamics.is_metal": True, "thermodynamics.band_gap": 0.0,
         "structure.li_hopping_distance": 3.0},
        {"identity.material_id": "lit-1", "identity.source_db": "literature_mined",
         "thermodynamics.energy_above_hull": None,
         "thermodynamics.is_metal": None, "thermodynamics.band_gap": None,
         "structure.li_hopping_distance": None},
    ])
    monkeypatch.setattr(N, "CANONICAL", tmp_path / "canonical.parquet")
    canon.to_parquet(tmp_path / "canonical.parquet", index=False)
    df = N.build_negative_frame()
    assert df["negative.is_negative_result"].tolist() == [True, True, None]
    assert df["negative.reasons"].iloc[0] == ["thermodynamically_unstable"]
    assert df["negative.reasons"].iloc[1] == ["electronic_conductor"]
    assert df.loc[2, "negative.confidence"] is None


def test_summarize_distribution(tmp_path, monkeypatch):
    canon = pd.DataFrame([
        {"identity.material_id": "mp-a", "identity.source_db": "materials_project",
         "thermodynamics.energy_above_hull": 0.1,
         "thermodynamics.is_metal": False, "thermodynamics.band_gap": 2.0,
         "structure.li_hopping_distance": 3.0},
        {"identity.material_id": "mp-b", "identity.source_db": "materials_project",
         "thermodynamics.energy_above_hull": 0.0,
         "thermodynamics.is_metal": False, "thermodynamics.band_gap": 3.0,
         "structure.li_hopping_distance": 3.0},
        {"identity.material_id": "lit-1", "identity.source_db": "literature_mined",
         "thermodynamics.energy_above_hull": None,
         "thermodynamics.is_metal": None, "thermodynamics.band_gap": None,
         "structure.li_hopping_distance": None},
    ])
    monkeypatch.setattr(N, "CANONICAL", tmp_path / "canonical.parquet")
    canon.to_parquet(tmp_path / "canonical.parquet", index=False)
    df = N.build_negative_frame()
    s = N.summarize(df)
    assert s["negative_records"] == 1
    assert s["unknown_records"] == 1
    assert s["signal_counts"]["thermodynamically_unstable"] == 1
    assert "never a fabricated False" in s["convention"]
