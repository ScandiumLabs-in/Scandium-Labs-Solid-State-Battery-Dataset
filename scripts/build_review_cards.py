#!/usr/bin/env python3
"""Build HTML evidence review cards for pending review-queue records.

For each pending record that has a resolvable PDF, this script:

  1. Locates the value evidence via verifier.locate_evidence() (page + window).
  2. Renders a PNG crop of that PDF page region (text-layer PDFs only; scanned
     pages have no text layer and are left image-only so a human can still
     read the page visually).
  3. Runs unit/temperature normalization + material fingerprinting + literature
     consensus so the card shows, at a glance: the reported value, its
     canonical S/cm value, the multiplier used, the material's consensus
     median across all records, and the AI-review score/decision.
  4. Writes a self-contained HTML file to review_output/cards/<review_id>.html
     plus an index.html linking every card.

The point of a card is to make human review a 30-second visual decision:
look at the paper's own number in context (the crop) and say approve/reject.
No value is ever auto-edited.

Usage:
  python scripts/build_review_cards.py [--queue review_output/queue.json]
      [--pdf-dir literature_output/pdfs] [--cards-dir review_output/cards]
      [--limit N] [--only STATUS]
"""

from __future__ import annotations

import argparse
import html
import json
import re
from pathlib import Path

import fitz

from ssb_dataset.pipeline.consensus import compute_consensus
from ssb_dataset.pipeline.fingerprint import group_key
from ssb_dataset.pipeline.normalization import normalize_record_units
from ssb_dataset.pipeline.verifier import locate_evidence

REVIEW_DIR = Path("review_output")
DEFAULT_QUEUE = REVIEW_DIR / "queue.json"
DEFAULT_PDF_DIR = Path("literature_output/pdfs")
DEFAULT_CARDS_DIR = REVIEW_DIR / "cards"

_PDF_NAME_RE = re.compile(r"[^A-Za-z0-9_.\-]")


def _pdf_path_for(record: dict, pdf_dir: Path) -> Path | None:
    for key in ("paper_id", "doi"):
        pid = str(record.get(key, "") or "").replace("/", "_")
        if not pid:
            continue
        for p in pdf_dir.iterdir():
            if p.stem.replace("_", "/").replace("/", "/") == pid.replace("_", "/"):
                return p
        cand = pdf_dir / f"{pid}.pdf"
        if cand.exists():
            return cand
    return None


def render_page_crop(pdf_path: Path, page: int, out_path: Path,
                     window_text: str = "", *, crop_ratio: float = 0.35) -> Path | None:
    """Render a page (1-indexed) to a PNG; if we know a text window, crop the
    region containing the first match of a quoted value to keep the card
    visually tight. Returns the output path or None on failure."""
    try:
        doc = fitz.open(str(pdf_path))
        if page < 1 or page > doc.page_count:
            doc.close()
            return None
        pg = doc[page - 1]
        if window_text:
            rl = pg.search_for(window_text[:80])
            if rl:
                rect = rl[0]
                full = pg.rect
                # expand around the found text
                x0 = max(0, rect.x0 - full.width * 0.08)
                y0 = max(0, rect.y0 - full.height * 0.06)
                x1 = min(full.width, rect.x1 + full.width * 0.5)
                y1 = min(full.height, rect.y1 + full.height * crop_ratio)
                clip = fitz.Rect(x0, y0, x1, y1)
                pix = pg.get_pixmap(matrix=fitz.Matrix(2, 2), clip=clip)
            else:
                pix = pg.get_pixmap(matrix=fitz.Matrix(1.6, 1.6))
        else:
            pix = pg.get_pixmap(matrix=fitz.Matrix(1.6, 1.6))
        pix.save(str(out_path))
        doc.close()
        return out_path
    except Exception:
        return None


def build_cards(queue_path: Path, pdf_dir: Path, cards_dir: Path,
                limit: int | None, only: str | None) -> None:
    cards_dir.mkdir(parents=True, exist_ok=True)
    queue = json.loads(queue_path.read_text())
    items = queue["items"] if isinstance(queue, dict) else queue

    pending = [i for i in items if i.get("status") in (only or ("pending", "spot_check", "needs_review"))]
    if limit:
        pending = pending[:limit]

    # normalize + consensus across ALL pending records (consensus needs group n)
    for rec in pending:
        normalize_record_units(rec)
    consensus = compute_consensus(pending)

    links: list[tuple[str, str]] = []
    for rec in pending:
        rid = rec.get("review_id", "unknown")
        pdf = _pdf_path_for(rec, pdf_dir)
        ev = None
        crop_html = ""
        if pdf is not None:
            try:
                ev = locate_evidence(
                    pdf, rec.get("composition", ""),
                    rec.get("normalized_sigma"), rec.get("normalized_ea"),
                )
            except Exception:
                ev = None
            if ev is not None:
                crop_path = cards_dir / f"{rid}.png"
                quote_hint = (rec.get("verified_snippet") or rec.get("evidence_sentence") or ev.quote or ev.window)[:80]
                if render_page_crop(pdf, ev.page, crop_path, quote_hint):
                    crop_html = f'<img src="{rid}.png" alt="page {ev.page} crop" style="max-width:100%;border:1px solid #ccc;">'
            else:
                # scanned page or no text layer: render page 1 as visual context
                crop_path = cards_dir / f"{rid}.png"
                if render_page_crop(pdf, 1, crop_path, ""):
                    crop_html = f'<img src="{rid}.png" alt="page 1 (scanned)" style="max-width:100%;border:1px solid #ccc;">'

        grp = group_key(rec.get("composition", ""))
        mc = consensus.materials.get(grp)
        consensus_html = ""
        if mc and mc.n_sigma >= 2:
            consensus_html = (
                f"<tr><td>group n</td><td>{mc.n_sigma} records</td></tr>"
                f"<tr><td>median σ</td><td>{mc.median_sigma:.2e} S/cm</td></tr>"
                f"<tr><td>range</td><td>{mc.min_sigma:.1e} – {mc.max_sigma:.1e}</td></tr>"
            )
            outlier = any(f.get("review_id") == rid for f in consensus.flagged)
            if outlier:
                consensus_html += "<tr><td style='color:#b00020;font-weight:700'>OUTLIER</td><td style='color:#b00020'>disagrees with group median</td></tr>"

        sig_html = ""
        if rec.get("normalized_sigma") is not None:
            sig_html = (
                f"<tr><td>σ (S/cm)</td><td>{rec['normalized_sigma']:.3e}</td></tr>"
                f"<tr><td>σ reported</td><td>{rec.get('value')} {rec.get('unit','')}</td></tr>"
                f"<tr><td>σ conversion</td><td>{rec.get('sigma_note','')}</td></tr>"
            )
        ea_html = ""
        if rec.get("normalized_ea") is not None:
            ea_html = f"<tr><td>Ea (eV)</td><td>{rec['normalized_ea']:.4f}</td></tr>"
        elif rec.get("Ea") is not None:
            ea_html = f"<tr><td>Ea (reported)</td><td>{rec.get('Ea')} eV</td></tr>"

        issues = rec.get("normalization_issues") or []
        issues_html = "".join(f"<li style='color:#b00020'>{html.escape(i)}</li>" for i in issues) or "<li>none</li>"

        evidence_html = ""
        if ev is not None:
            evidence_html = (
                f"<tr><td>evidence page</td><td>{ev.page}</td></tr>"
                f"<tr><td>composition found</td><td>{ev.found_composition}</td></tr>"
                f"<tr><td>σ found</td><td>{ev.found_sigma}</td></tr>"
                f"<tr><td>Ea found</td><td>{ev.found_ea}</td></tr>"
            )

        ai_score = rec.get("auto_review_score")
        ai_decision = rec.get("auto_decision", "")
        ai_color = "#1a7f37" if ai_decision == "spot_check" else "#9a6700" if ai_decision == "needs_review" else "#b00020" if ai_decision == "reject" else "#333"
        ai_html = f"<span style='color:{ai_color};font-weight:700'>{ai_score} / {ai_decision}</span>" if ai_score is not None else "<em>not scored</em>"

        card = f"""<!DOCTYPE html><html><head><meta charset="utf-8">
<title>{html.escape(rid)}</title></head><body style="font-family:sans-serif;margin:24px">
<h2>{html.escape(rec.get('composition',''))}</h2>
<p><strong>review_id:</strong> {html.escape(rid)}<br>
<strong>DOI:</strong> {html.escape(str(rec.get('doi') or rec.get('paper_id') or ''))}<br>
<strong>status:</strong> {html.escape(str(rec.get('status','')))}<br>
<strong>AI review:</strong> {ai_html}<br>
<strong>verifier consensus:</strong> {html.escape(str(rec.get('verifier_consensus','')))}<br>
<strong>verifier note:</strong> {html.escape(str(rec.get('verifier_note','')))}</p>
<table border="1" cellpadding="6" cellspacing="0" style="border-collapse:collapse">
{sig_html}{ea_html}
<tr><td>temperature</td><td>{rec.get('temperature_celsius') if rec.get('temperature_celsius') is not None else rec.get('temperature_K','')}</td></tr>
<tr><td>property</td><td>{html.escape(str(rec.get('property','')))}</td></tr>
<tr><td>conductivity type</td><td>{html.escape(str(rec.get('conductivity_type','')))}</td></tr>
<tr><td>family</td><td>{html.escape(str(rec.get('family','')))}</td></tr>
{consensus_html}
{evidence_html}
</table>
<h3>Normalization issues</h3><ul>{issues_html}</ul>
<h3>Source evidence</h3>
<pre style="white-space:pre-wrap;background:#f5f5f5;padding:10px">{html.escape(rec.get('verified_snippet') or rec.get('evidence_sentence') or ev.window if ev else rec.get('evidence_sentence',''))}</pre>
<h3>Paper page</h3>{crop_html}
<p><a href="../queue.json">back to queue</a></p>
</body></html>"""
        (cards_dir / f"{rid}.html").write_text(card)
        links.append((rid, rec.get("composition", "")))

    links.sort(key=lambda t: t[0])
    idx = "<!DOCTYPE html><html><head><meta charset='utf-8'><title>Review cards</title></head><body><h1>Evidence review cards</h1><ul>"
    for rid, comp in links:
        idx += f'<li><a href="{rid}.html">{html.escape(comp)} — {html.escape(rid)}</a></li>'
    idx += "</ul></body></html>"
    (cards_dir / "index.html").write_text(idx)
    print(f"wrote {len(links)} cards to {cards_dir}/ (index.html + {len(links)}.html)")


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--queue", type=Path, default=DEFAULT_QUEUE)
    ap.add_argument("--pdf-dir", type=Path, default=DEFAULT_PDF_DIR)
    ap.add_argument("--cards-dir", type=Path, default=DEFAULT_CARDS_DIR)
    ap.add_argument("--limit", type=int, default=None)
    ap.add_argument("--only", default="pending")
    args = ap.parse_args()
    build_cards(args.queue, args.pdf_dir, args.cards_dir, args.limit, args.only)


if __name__ == "__main__":
    main()
