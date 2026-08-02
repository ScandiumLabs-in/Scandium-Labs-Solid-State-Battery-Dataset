"""FastAPI review dashboard — interactive human review over the queue.

Serves the review queue as a web UI. Each card shows:
  paper metadata / DOI / family / composition / property / temperature / units
  / confidence / extraction snippet / highlighted PDF page / consensus values /
  expected family range / similar papers, plus Approve / Reject / Edit buttons.

Decisions write through the shared persistence layer (store.py) so a click
updates queue.json + training_pairs.jsonl + approved_records.parquet in exactly
the same on-disk state as the CLI reviewer.

Run:
    python -m uvicorn ssb_dataset.review.dashboard:app --reload --port 8000
"""

from __future__ import annotations

import json
from pathlib import Path

from fastapi import FastAPI, Form, HTTPException, Request
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.templating import Jinja2Templates

from ssb_dataset.pipeline.consensus import compute_consensus
from ssb_dataset.pipeline.fingerprint import group_key
from ssb_dataset.pipeline.normalization import normalize_record_units

from ssb_dataset.review import decide, evaluate_rules, score_record
from ssb_dataset.review.rules import ReviewContext
from ssb_dataset.review.store import (
    REVIEW_DIR,
    apply_decision,
    load_queue,
    save_queue,
)

ROOT = Path(__file__).resolve().parent.parent.parent.parent
TEMPLATES_DIR = Path(__file__).resolve().parent / "templates"

app = FastAPI(title="SSB Review Dashboard")
templates = Jinja2Templates(directory=str(TEMPLATES_DIR))

# family aliases used in the queue -> redflags' family keys
FAMILY_ALIASES = {
    "garnet": "garnet",
    "perovskite": "perovskite",
    "perovskite/llto": "perovskite",
    "sulfide": "sulfide",
    "argyrodite": "sulfide",
    "halide": "halide",
    "nasicon": "nasicon",
    "antiperovskite": "antiperovskite",
    "hydride": "hydride",
    "borohydride": "borohydride",
    "polymer": "polymer_composite",
    "polymer_composite": "polymer_composite",
    "oxide": "oxide",
}


def _alias(family: str | None) -> str:
    return FAMILY_ALIASES.get((family or "").lower(), "")


# ---------------------------------------------------------------------------
# Context + AI review
# ---------------------------------------------------------------------------

def _build_context(queue: dict) -> ReviewContext:
    items = queue["items"]
    pending = [it for it in items if it.get("status") == "pending"]
    approved = [it for it in items if it.get("status") == "approved"]
    for it in pending:
        normalize_record_units(it)
    consensus = compute_consensus(pending)
    return ReviewContext(
        consensus=consensus,
        approved_records=approved,
        consensus_db=_load_consensus_db(),
        family_alias=_alias,
    )


def _load_consensus_db() -> dict:
    """Load the persistent cross-paper consensus DB if present."""
    path = ROOT / "literature_output/consensus_db.json"
    if not path.exists():
        return {}
    try:
        return json.loads(path.read_text())
    except Exception:
        return {}


def _review(record: dict, ctx: ReviewContext) -> dict:
    """Run the AI review engine on one record, returning a display-ready dict."""
    results = evaluate_rules(record, ctx)
    factors = score_record(record, results, ctx)
    decision = decide(results, factors, record, ctx)
    return {
        "rules": [{"rule": r.rule, "status": r.status.value, "message": r.message} for r in results],
        "factors": factors.summary()["factors"],
        "overall": factors.overall,
        "decision": decision.decision.value,
        "reasons": decision.reasons,
    }


def _material_consensus(queue: dict, record: dict) -> dict | None:
    """Consensus over every queue record with the same material group, merged
    with the persistent cross-paper consensus DB entry (CI, pub count, temp
    histogram) when present."""
    grp = group_key(record.get("composition", ""))
    if not grp:
        return None
    from ssb_dataset.pipeline.consensus import compute_consensus

    all_recs = [it for it in queue["items"] if group_key(it.get("composition", "")) == grp]
    cons = compute_consensus(all_recs)
    mc = cons.materials.get(grp)
    out = {
        "group": grp,
        "n_sigma": mc.n_sigma if mc else 0,
        "median_sigma": mc.median_sigma if mc else None,
        "min_sigma": mc.min_sigma if mc else None,
        "max_sigma": mc.max_sigma if mc else None,
        "n_ea": mc.n_ea if mc else 0,
        "median_ea": mc.median_ea if mc else None,
        "flagged": mc is not None and any(f.get("review_id") == record.get("review_id") for f in cons.flagged),
        "n_papers": None,
        "sigma_ci95": None,
        "temperature_histogram": [],
        "outliers": [],
    }
    db = _load_consensus_db().get(grp)
    if db:
        out["n_papers"] = db.get("n_papers")
        out["sigma_ci95"] = db.get("sigma_ci95")
        out["temperature_histogram"] = db.get("temperature_histogram") or []
        out["outliers"] = db.get("outliers") or []
    return out


def _similar_papers(queue: dict, record: dict, limit: int = 8) -> list[dict]:
    """Other queue records for the same material group (prior art + variance)."""
    grp = group_key(record.get("composition", ""))
    if not grp:
        return []
    out = []
    for it in queue["items"]:
        if it.get("review_id") == record.get("review_id"):
            continue
        if group_key(it.get("composition", "")) != grp:
            continue
        out.append({
            "composition": it.get("composition"),
            "doi": it.get("doi"),
            "property": it.get("property"),
            "value": it.get("value"),
            "unit": it.get("unit"),
            "temperature": it.get("temperature_celsius"),
            "status": it.get("status"),
        })
    return out[:limit]


# ---------------------------------------------------------------------------
# Templates helper: number formatting
# ---------------------------------------------------------------------------

def _fmt(v, unit=""):
    if v is None:
        return "—"
    if isinstance(v, float):
        if abs(v) >= 1e4 or (abs(v) < 1e-3 and v != 0):
            s = f"{v:.2e}"
        else:
            s = f"{v:.4g}"
    else:
        s = str(v)
    return (s + " " + unit).strip()


templates.env.filters["fmt"] = _fmt
templates.env.filters["canon"] = _alias


# ---------------------------------------------------------------------------
# Routes
# ---------------------------------------------------------------------------

@app.get("/", response_class=HTMLResponse)
def index(request: Request, family: str = "", status: str = ""):
    queue = load_queue()
    items = queue["items"]
    ctx = _build_context(queue)

    enriched = []
    for it in items:
        ai = _review(it, ctx)
        it["_ai"] = ai
        it["_material_consensus"] = _material_consensus(queue, it)
        enriched.append(it)

    from collections import Counter
    status_counts = Counter(i.get("status", "pending") for i in items)
    families = sorted({i.get("family") or "unknown" for i in items})

    filtered = [i for i in enriched if (not family or i.get("family") == family)]
    filtered = [i for i in filtered if (not status or i.get("status") == status)]

    return templates.TemplateResponse(request, "index.html", {
        "items": filtered,
        "all_items": enriched,
        "status_counts": dict(status_counts),
        "families": families,
        "family": family,
        "status": status,
        "total": len(items),
    })


@app.get("/record/{review_id}", response_class=HTMLResponse)
def record(request: Request, review_id: str):
    queue = load_queue()
    item = next((i for i in queue["items"] if i.get("review_id") == review_id), None)
    if item is None:
        raise HTTPException(404, "record not found")
    ctx = _build_context(queue)
    item["_ai"] = _review(item, ctx)
    item["_material_consensus"] = _material_consensus(queue, item)
    item["_similar"] = _similar_papers(queue, item)
    return templates.TemplateResponse(request, "record.html", {"item": item})


@app.post("/record/{review_id}/decision")
def decision(
    review_id: str,
    action: str = Form(...),
    reviewer: str = Form("dashboard"),
    note: str = Form(""),
    edited_value: str = Form(""),
    edited_unit: str = Form(""),
    edited_property: str = Form(""),
):
    queue = load_queue()
    try:
        ev = float(edited_value) if edited_value.strip() else None
    except ValueError:
        ev = None
    item = apply_decision(
        queue, review_id, action, reviewer,
        edited_value=ev,
        edited_unit=edited_unit.strip() or None,
        note=note.strip(),
    )
    if item is None:
        raise HTTPException(404, "record not found")
    return RedirectResponse(f"/record/{review_id}", status_code=303)


@app.get("/queue.json")
def queue_json():
    return load_queue()


@app.get("/health")
def health():
    return {"ok": True, "queue": str(REVIEW_DIR / "queue.json")}
