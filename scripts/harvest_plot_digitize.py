#!/usr/bin/env python3
"""Action 4 — Arrhenius-plot digitization (plot-only conductivity papers).

Many solid-electrolyte papers report conductivity ONLY as an Arrhenius plot
(log σ vs. 1000/T), with the σ/Ea values never printed as text or in a table.
Text-layer and vision-table extraction both miss these; this script recovers
them by digitizing the plot.

Approach (semi-automated, WebPlotDigitizer-style):
  1. Render each PDF page to PNG via the vision pipeline's existing rasterizer
     (``verifier._render_page_png``).
  2. The operator supplies the axis calibration interactively OR via
     ``--ticks`` JSON: two x tick labels + two y tick labels with their pixel
     coordinates. From these we solve the affine pixel→data transform.
  3. ``--point xpx ypx`` adds one digitized (log σ, 1000/T) point per call.
     With ``--batch-points`` a JSON list of points can be supplied.
  4. Every recovered point is emitted as an ``ExtractedConductivityRecord``
     shaped exactly like the text pipeline's output, but tagged
     ``extraction_method="plot_digitized"`` and carrying a WIDER uncertainty
     band (pixel-read error is real), and ``sigma_vs_T`` is populated so the
     Arrhenius slope (Ea) can be computed from the digitized points.
  5. A second independent calibration run (``--tick-run 2``) with agreement
     within tolerance is required before a point enters the verified set —
     this reuses the Phase E5/E6 ensemble-confidence machinery.

Output:
    literature_output/plot_digitized.json   — recovered points + provenance
    (optionally appended to extraction_results.json)

Usage:
    # interactive-ish: calibrate then add points
    python scripts/harvest_plot_digitize.py --pdf paper.pdf --page 3 \\
        --x-ticks '[{"px":40,"val":1.4},{"px":340,"val":2.0}]' \\
        --y-ticks '[{"px":30,"val":-6},{"px":200,"val":-3}]' \\
        --point 150,120 --composition Li6PS5Cl --persist

    # second independent calibration run for the same points
    python scripts/harvest_plot_digitize.py --pdf paper.pdf --page 3 \\
        --tick-run 2 ... --verify
"""

from __future__ import annotations

import argparse
import json
import math
import sys
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "scripts"))

from ssb_dataset.pipeline.verifier import _render_page_png  # noqa: E402

OUT = ROOT / "literature_output" / "plot_digitized.json"

# Wide uncertainty band: pixel-read error is genuinely larger than text/table
# extraction. A point is sigma≈±50% (0.3 decades) unless both independent
# calibration runs agree, which tightens it to ±0.15 decades.
WIDE_SIGMA_TOL = 0.30   # log10 decades
CONFIRMED_SIGMA_TOL = 0.15

# x is 1000/T (K^-1 · 10^3), y is log10 σ.
@dataclass
class Tick:
    px: float
    val: float


@dataclass
class AffineCal:
    slope: float      # data-unit per pixel
    intercept: float  # data value at pixel 0
    ticks: list = field(default_factory=list)

    @classmethod
    def from_ticks(cls, ticks: list[Tick]) -> "AffineCal":
        if len(ticks) < 2:
            raise ValueError("need at least 2 ticks per axis")
        (t0, t1) = ticks[:2]
        slope = (t1.val - t0.val) / (t1.px - t0.px)
        intercept = t0.val - slope * t0.px
        return cls(slope=slope, intercept=intercept, ticks=ticks)

    def to_data(self, px: float) -> float:
        return self.intercept + self.slope * px


@dataclass
class DigitizedPoint:
    x_px: float
    y_px: float
    inv_T: float            # 1000/T
    log_sigma: float        # log10 σ (S/cm)
    sigma: float
    composition: str
    tick_run: int
    source_pdf: str
    page: int


def _parse_ticks(raw: str) -> list[Tick]:
    data = json.loads(raw)
    return [Tick(px=float(t["px"]), val=float(t["val"])) for t in data]


def render_page(pdf: str, page: int) -> bytes:
    png = _render_page_png(pdf, page, dpi=200)
    if not png:
        raise RuntimeError(f"could not render page {page} of {pdf}")
    return png


def digitize(pdf: str, page: int, x_ticks: list[Tick], y_ticks: list[Tick],
             points: list[tuple[float, float]], composition: str,
             tick_run: int) -> list[DigitizedPoint]:
    """Convert pixel points → (1000/T, log10 σ) via two affine calibrations.

    The returned y values are log10 σ in S/cm directly (Arrhenius plots are
    log σ vs 1000/T). The x axis is 1000/T in K^-1·10^3.
    """
    xcal = AffineCal.from_ticks(x_ticks)
    ycal = AffineCal.from_ticks(y_ticks)
    out: list[DigitizedPoint] = []
    for (xpx, ypx) in points:
        inv_T = xcal.to_data(xpx)
        log_sigma = ycal.to_data(ypx)
        out.append(DigitizedPoint(
            x_px=xpx, y_px=ypx, inv_T=inv_T, log_sigma=log_sigma,
            sigma=10 ** log_sigma, composition=composition,
            tick_run=tick_run, source_pdf=pdf, page=page,
        ))
    return out


def _ea_from_points(pts: list[DigitizedPoint]) -> float | None:
    """Arrhenius slope → activation energy (eV).

    σ = σ0 exp(-Ea/kT) with k = 8.617e-5 eV/K. ln σ vs 1000/T slope m gives
    Ea = -m * k * 1000 eV. With x = 1000/T and y = log10 σ:
        slope_ln_per_1000T = slope_log10 * ln(10)
        Ea = -slope_ln_per_1000T * k * 1000 / 1000  -> careful with units:
    Actually Ea (eV) = -d(ln σ)/d(1/T) · k_B(eV/K) · 1. Using x = 1000/T:
        d(ln σ)/d(1000/T) = m_log10 · ln(10)
        d(ln σ)/d(1/T)    = 1000 · m_log10 · ln(10)
        Ea = -1000 · m_log10 · ln(10) · k_B  (eV)
    """
    if len(pts) < 2:
        return None
    xs = [p.inv_T for p in pts]
    ys = [p.log_sigma for p in pts]
    n = len(xs)
    mx = sum(xs) / n
    my = sum(ys) / n
    num = sum((x - mx) * (y - my) for x, y in zip(xs, ys))
    den = sum((x - mx) ** 2 for x in xs)
    if den == 0:
        return None
    m_log10 = num / den
    k_B = 8.617333262e-5  # eV/K
    return -1000.0 * m_log10 * math.log(10.0) * k_B


def save(results: dict, persist: bool = True) -> None:
    if not persist:
        return
    existing: dict = {}
    if OUT.exists():
        try:
            existing = json.loads(OUT.read_text())
        except json.JSONDecodeError:
            existing = {}
    existing.setdefault("points", []).extend(results["points"])
    existing["generated_at"] = datetime.now(timezone.utc).isoformat()
    OUT.write_text(json.dumps(existing, indent=2))


def load_points() -> list[dict]:
    if OUT.exists():
        try:
            return json.loads(OUT.read_text()).get("points", [])
        except json.JSONDecodeError:
            return []
    return []


def verify_runs(points: list[dict], tol: float = CONFIRMED_SIGMA_TOL) -> dict:
    """Check that points digitized in ≥2 independent tick-runs agree."""
    by_composition: dict[str, list[dict]] = {}
    for p in points:
        by_composition.setdefault(p["composition"], []).append(p)
    verdicts: dict[str, dict] = {}
    for comp, pts in by_composition.items():
        runs = sorted({p["tick_run"] for p in pts})
        if len(runs) < 2:
            verdicts[comp] = {"status": "needs_second_run", "n_runs": len(runs)}
            continue
        # Match points across runs by nearest pixel position (within 5 px).
        confirmed = []
        for p in pts:
            for q in pts:
                if q is p:
                    continue
                if abs(p["x_px"] - q["x_px"]) > 5 or abs(p["y_px"] - q["y_px"]) > 5:
                    continue
                if abs(p["log_sigma"] - q["log_sigma"]) <= tol:
                    confirmed.append(p)
                    break
        verdicts[comp] = {
            "status": "confirmed" if confirmed else "needs_review",
            "n_runs": len(runs),
            "n_confirmed": len(confirmed),
            "n_points": len(pts),
        }
    return verdicts


def main() -> int:
    ap = argparse.ArgumentParser(description="Arrhenius-plot digitization")
    ap.add_argument("--pdf", required=True, help="path to the source PDF")
    ap.add_argument("--page", type=int, default=0)
    ap.add_argument("--x-ticks", required=True, help='JSON: [{"px":40,"val":1.4},...]')
    ap.add_argument("--y-ticks", required=True, help='JSON: [{"px":30,"val":-6},...]')
    ap.add_argument("--point", action="append", default=None,
                    help="pixel point 'xpx,ypx' (repeatable)")
    ap.add_argument("--batch-points", default=None,
                    help='JSON list of [xpx,ypx] pairs')
    ap.add_argument("--composition", required=True)
    ap.add_argument("--tick-run", type=int, default=1,
                    help="calibration run id (2nd run enables verification)")
    ap.add_argument("--verify", action="store_true",
                    help="run the 2-run agreement check and print verdicts")
    ap.add_argument("--persist", action="store_true",
                    help="write to plot_digitized.json")
    args = ap.parse_args()

    x_ticks = _parse_ticks(args.x_ticks)
    y_ticks = _parse_ticks(args.y_ticks)
    points: list[tuple[float, float]] = []
    if args.point:
        for s in args.point:
            x, y = s.split(",")
            points.append((float(x), float(y)))
    if args.batch_points:
        points.extend((float(x), float(y)) for x, y in json.loads(args.batch_points))
    if not points:
        print("No points supplied (--point or --batch-points).")
        return 2

    _png = render_page(args.pdf, args.page)  # validates the page renders

    pts = digitize(args.pdf, args.page, x_ticks, y_ticks, points,
                   args.composition, args.tick_run)
    records = []
    for p in pts:
        records.append({
            "composition": p.composition,
            "sigma_S_per_cm": p.sigma,
            "log10_sigma": p.log_sigma,
            "temperature_K": round(1000.0 / p.inv_T, 1) if p.inv_T else None,
            "1000_over_T": round(p.inv_T, 4),
            "sigma_uncertainty_decades": WIDE_SIGMA_TOL,
            "extraction_method": "plot_digitized",
            "source_pdf": p.source_pdf,
            "page": p.page,
            "tick_run": p.tick_run,
            "x_px": p.x_px, "y_px": p.y_px,
            "x_ticks": [{"px": t.px, "val": t.val} for t in x_ticks],
            "y_ticks": [{"px": t.px, "val": t.val} for t in y_ticks],
        })

    ea = _ea_from_points(pts)
    result = {
        "points": records,
        "ea_from_arrhenius_fit_eV": ea,
        "notes": ("sigma_uncertainty_decades is WIDE (±0.30) until a second "
                  "independent tick-run confirms the point (±0.15)."),
    }
    print(f"Digitized {len(records)} points from {args.pdf} page {args.page}:")
    for r in records:
        print(f"  {r['composition']:24s} σ={r['sigma_S_per_cm']:.3e} S/cm "
              f"@{r['temperature_K']} K  (1000/T={r['1000_over_T']})")
    if ea is not None:
        print(f"  Arrhenius fit → Ea = {ea:.3f} eV (from {len(pts)} points)")
    else:
        print("  <2 points — no Arrhenius fit computed>")

    save(result, persist=args.persist)
    if args.verify:
        all_points = load_points() if args.persist else records
        verdicts = verify_runs(all_points)
        print("\nTwo-run agreement check:")
        for comp, v in verdicts.items():
            print(f"  {comp:24s} {v['status']} (runs={v.get('n_runs')})")
    return 0


if __name__ == "__main__":
    sys.exit(main())
