"""Action 4 — Arrhenius-plot digitization tests.

Verifies the affine pixel→data calibration, the Arrhenius Ea recovery from
digitized points, the wide-uncertainty provenance tag, and the two-run
agreement gate — all without any network or PDF rendering.
"""

from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "scripts"))

from harvest_plot_digitize import (  # noqa: E402
    AffineCal,
    Tick,
    WIDE_SIGMA_TOL,
    _ea_from_points,
    digitize,
    verify_runs,
)


def test_affine_from_ticks():
    cal = AffineCal.from_ticks([Tick(px=40, val=1.4), Tick(px=340, val=2.0)])
    assert abs(cal.to_data(40) - 1.4) < 1e-9
    assert abs(cal.to_data(340) - 2.0) < 1e-9
    assert abs(cal.to_data(190) - 1.7) < 1e-9


def test_affine_needs_two_ticks():
    try:
        AffineCal.from_ticks([Tick(px=1, val=1)])
        assert False, "expected ValueError"
    except ValueError:
        pass


def test_digitize_recovery():
    pts = digitize(
        "paper.pdf", 3,
        x_ticks=[Tick(px=50, val=1.4), Tick(px=350, val=2.0)],
        y_ticks=[Tick(px=50, val=-6.0), Tick(px=250, val=-3.0)],
        points=[(200, 100), (350, 250)],
        composition="Li6PS5Cl",
        tick_run=1,
    )
    assert len(pts) == 2
    # x: midpoint 200px -> 1.7  (1000/T)
    assert abs(pts[0].inv_T - 1.7) < 1e-6
    # y: 100px -> -6 + (100-50)*(3/200) = -5.25
    assert abs(pts[0].log_sigma - (-5.25)) < 1e-6
    assert abs(pts[0].sigma - 10 ** -5.25) < 1e-12
    assert pts[0].tick_run == 1
    assert pts[0].source_pdf == "paper.pdf"


def test_ea_from_digitized_points():
    # Synthetic Arrhenius line: log10 σ = 6 - 1.5*(1000/T), i.e. positive slope
    # with respect to 1000/T means... an Arrhenius line is log σ vs 1000/T
    # with NEGATIVE slope (conductivity rises with T). Ea = 0.4 eV means
    # d(ln σ)/d(1000/T) = -Ea/(1000 k_B). m_log10 = m_ln/ln10.
    k_B = 8.617333262e-5
    m_ln = -0.4 / (1000 * k_B)          # slope in ln σ per (1000/T)
    m_log10 = m_ln / 2.302585092994046   # slope in log10 σ per (1000/T)
    b = 2.0
    points = []
    for i, inv_T in enumerate([1.2, 1.4, 1.6, 1.8, 2.0]):
        points.append(type("P", (), {
            "inv_T": inv_T, "log_sigma": b + m_log10 * inv_T})())
    ea = _ea_from_points(points)
    assert abs(ea - 0.4) < 1e-3, f"Ea={ea}"


def test_ea_needs_two_points():
    p = type("P", (), {"inv_T": 1.5, "log_sigma": -4.0})
    assert _ea_from_points([p]) is None


def test_wide_uncertainty_tag():
    assert WIDE_SIGMA_TOL == 0.30


def test_verify_runs_confirms_agreement():
    common = {
        "composition": "Li6PS5Cl", "x_px": 150.0, "y_px": 120.0,
        "log_sigma": -4.0,
    }
    r1 = {**common, "tick_run": 1}
    r2 = {**common, "tick_run": 2}
    verdicts = verify_runs([r1, r2])
    assert verdicts["Li6PS5Cl"]["status"] == "confirmed"


def test_verify_runs_needs_second_run():
    common = {
        "composition": "LiBH4", "x_px": 150.0, "y_px": 120.0,
        "log_sigma": -4.0, "tick_run": 1,
    }
    verdicts = verify_runs([common])
    assert verdicts["LiBH4"]["status"] == "needs_second_run"


def test_verify_runs_flags_disagreement():
    common = {"composition": "LLZO", "x_px": 150.0, "y_px": 120.0}
    r1 = {**common, "log_sigma": -4.0, "tick_run": 1}
    r2 = {**common, "log_sigma": -4.5, "tick_run": 2}
    verdicts = verify_runs([r1, r2])
    assert verdicts["LLZO"]["status"] == "needs_review"
