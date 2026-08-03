"""Verification agent — AI review of extracted conductivity records.

Turns the "is this value right?" manual question into a structured, scored,
multi-model review that only escalates uncertain records to a human.

Pipeline stages (each returns a partial score 0..100 and evidence):

  1. locate_evidence()   — find the exact value-window in the PDF text around the
                           matched sigma/Ea, plus the composition context.
  2. verify_single()     — one LLM (extractor-independent) reads the window and
                           answers structured YES/NO/DIFFERENT for composition,
                           sigma, Ea, temperature, units, and must QUOTE the
                           exact location of the value.
  3. cross_verify()      — run N different models (e.g. 8b, 70b, gpt-oss-20b) and
                           require >=2/3 agreement (consensus opinion).
  4. physics_check()     — Arrhenius prefactor range + family sigma/Ea ranges.
  5. literature_check()  — compare against benchmark inventory + approved records;
                           flag order-of-magnitude mismatches.
  6. composite_score()   — weighted sum -> 0..100 review score + auto-decision
                           (auto_approve / needs_review / reject).

The verifier NEVER edits values. It reports; a human (or a later auto-apply step
for high-confidence agreements) makes the decision.
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import fitz  # PyMuPDF

from ssb_dataset.pipeline.redflags import (
    FAMILY_EA_RANGES,
    FAMILY_SIGMA_RANGES,
    TYPICAL_PREFACTOR_RANGE,
    RT_K,
)

# --------------------------------------------------------------------------
# Configuration
# --------------------------------------------------------------------------

# Models available on the Groq-compatible endpoint, used as independent verifiers.
VERIFIER_MODELS = [
    "llama-3.1-8b-instant",   # current extractor model
    "llama-3.3-70b-versatile",  # different size / family behavior
    "openai/gpt-oss-20b",      # cross-vendor open model
]
MIN_AGREEMENT = 2  # require >=2 of the models to agree to form a consensus

# Composite scoring weights (sum = 100)
WEIGHTS = {
    "evidence": 25,    # value window located, exact quote produced
    "llm_agreement": 25,  # fraction of verifying models that confirm the value
    "physics": 20,     # Arrhenius + family-range consistency
    "literature": 15,  # agreement with benchmark / prior approved values
    "units": 10,       # unit sanity (S/cm vs mS/cm vs uS/cm)
    "temp": 5,         # temperature was reported and matches
}

# Auto-decision thresholds on the 0..100 composite score.
AUTO_APPROVE_MIN = 98
SPOT_CHECK_MIN = 95
NEEDS_REVIEW_MIN = 80


# --------------------------------------------------------------------------
# Data structures
# --------------------------------------------------------------------------

@dataclass
class Evidence:
    """Where the value/composition was actually found in the PDF text."""
    page: int = 0
    window: str = ""                 # +/- N chars around the matched value
    quote: str = ""                  # exact quote containing the value
    found_sigma: bool = False
    found_ea: bool = False
    found_composition: bool = False
    sigma_in_window: str = ""
    ea_in_window: str = ""


@dataclass
class VerifierVerdict:
    model: str = ""
    evidence_ok: bool = False
    composition_ok: bool = False
    sigma_ok: bool = False
    sigma_different: bool = False
    ea_ok: bool = False
    ea_different: bool = False
    temp_ok: bool = False
    units_ok: bool = False
    units_note: str = ""
    quote: str = ""
    confidence_1_5: int = 0
    raw: dict[str, Any] = field(default_factory=dict)

    @property
    def agree(self) -> bool:
        """A model 'agrees' when the key fields it could check are all ok."""
        if not self.evidence_ok:
            return False
        if not self.composition_ok:
            return False
        # at least one of the value fields must be confirmed (the record may be
        # sigma-only, Ea-only, or both)
        return self.sigma_ok or self.ea_ok or (not self.sigma_different and not self.ea_different)


@dataclass
class ReviewResult:
    record_id: str = ""
    paper_id: str = ""
    composition: str = ""
    sigma: float | None = None
    ea: float | None = None
    family: str = ""
    evidence: Evidence | None = None
    verdicts: list[VerifierVerdict] = field(default_factory=list)
    consensus_agree: bool = False
    n_agree: int = 0
    n_models: int = 0
    physics_ok: bool = True
    physics_notes: list[str] = field(default_factory=list)
    literature_note: str = ""
    units_note: str = ""
    temp_reported: bool = False
    score: float = 0.0
    decision: str = "needs_review"
    notes: list[str] = field(default_factory=list)


# --------------------------------------------------------------------------
# Evidence location (text-layer, exact window)
# --------------------------------------------------------------------------

_NUM_RE = re.compile(
    r"(\d+\.?\d*)\s*[x×]\s*10\s*([-\u2212\u2010\u2011\u2012\u2013\u2014]?\s*\d+)|"
    r"(\d+\.?\d*)[eE]([-\u2212\u2010\u2011\u2012\u2013\u2014]?\d+)|"
    r"(\d+\.?\d*)"
)
_ELEM_RE = re.compile(r"[A-Z][a-z]?")  # chemical element symbol


def _in_formula(text: str, m: re.Match) -> bool:
    """True if the number at match position is part of a chemical formula,
    e.g. the '0.3' in 'Li1.3Al0.3Ti1.7(PO4)3' or subscript stoichiometry.
    """
    before = text[: m.start()]
    # element immediately before the number: 'Al0.3', 'Li1.3', '(PO4)3'
    last_word = re.findall(r"[A-Z][a-z]?|[()]|\d+", before[-30:])
    if last_word:
        tok = last_word[-1]
        if tok == ")":
            return True  # '(PO4)3'
        if tok == "(":
            return False  # standalone '(0.3'
        if re.fullmatch(r"[A-Z][a-z]?", tok):
            # element symbol directly before number (could be composition 'Al0.3'
            # OR a unit like 'eV0.3' — only treat as formula if preceded by more
            # element/stoich chars rather than a space-delineated unit)
            return True
    return False
_VALUE_WINDOW = 240  # chars before/after the matched value


def _parse_number(text: str) -> float | None:
    m = _NUM_RE.search(text)
    if not m:
        return None
    if m.group(1) and m.group(2):
        exp_str = "".join(c for c in m.group(2) if c.isdigit() or c == "-")
        try:
            exp = int(exp_str)
        except ValueError:
            exp = 0
        if -32 <= exp <= 32:
            return float(m.group(1)) * 10 ** exp
    if m.group(3) and m.group(4):
        try:
            exp = int(m.group(4))
        except ValueError:
            exp = 0
        if -32 <= exp <= 32:
            return float(m.group(3)) * 10 ** exp
    if m.group(5):
        return float(m.group(5))
    return None


def _norm_formula(f: str) -> str:
    f = f.split("(")[0].split("/")[0].split("-")[0]
    return f.strip()


def _scan_pages(pages: list[str], composition: str,
                sigma: float | None, ea: float | None,
                window_expand: int = 0) -> Evidence | None:
    """Core evidence search over a list of page-texts (shared by the text-layer
    and vision paths). Returns Evidence when a composition/value match is found."""
    comp_clean = _norm_formula(composition)
    targets = [("sigma", sigma), ("ea", ea)]

    best: Evidence | None = None
    best_score = -1
    for page_idx, text in enumerate(pages, 1):
        found_comp = comp_clean.replace(".", "").replace("x", "").lower() in text.lower()
        if not found_comp and len(comp_clean) >= 4:
            # allow element-subset match for long/composite formulas
            elems = set(re.findall(r"[A-Z][a-z]?", composition))
            present = sum(1 for e in elems if re.search(rf"\b{e}\b", text))
            found_comp = present >= max(2, len(elems) - 2)

        # find value windows
        win_sigma, win_ea = "", ""
        found_sigma = found_ea = False
        for label, target in targets:
            if target is None:
                continue
            # candidate numeric values to look for (unit-aware)
            if label == "sigma":
                # Purely relative tolerance (35%): a large absolute floor would
                # let stray header/DOI digits match tiny conductivities.
                tol = abs(target) * 0.35
            else:
                # Ea in eV: tight absolute tolerance (avoid ppm/other-digit false matches)
                tol = 0.05
            variants: list[tuple[float, float]] = [(target, tol)]
            if label == "sigma":
                # paper-side equivalents: mS/cm and uS/cm read directly
                variants.append((target * 1e3, abs(target * 1e3) * 0.35))   # mS/cm
                variants.append((target * 1e6, abs(target * 1e6) * 0.35))    # uS/cm
            # Track the single closest match across all variants (unit-agnostic)
            best_dist: float = float("inf")
            best_pos: int | None = None
            for i, (tv, ttol) in enumerate(variants):
                if i > 0:
                    # avoid re-matching the same raw digit for converted forms
                    ttol = max(ttol, abs(tv) * 0.5)
                for m in _NUM_RE.finditer(text):
                    if _in_formula(text, m):
                        continue
                    v = _parse_number(m.group(0))
                    if v is None:
                        continue
                    if label == "sigma":
                        # Reject matches whose context carries a non-conductivity
                        # density/current unit (mA cm-2, mAh, mA, uA, W, Hz...).
                        near = text[max(0, m.start() - 24): m.end() + 40]
                        if re.search(r"(mA|mAh|µA|μA|uA|W ?cm|Hz|cm−2|cm-2|mAh)", near):
                            continue
                        # Reject axis-tick table cells (bare number followed by newline
                        # then another bare number — a plot axis, not a value).
                        after = text[m.end(): m.end() + 8]
                        if re.match(r"\s*\d+\s*\n", after) and re.match(r"\s*0\.\d", text[m.end(): m.end() + 8]):
                            continue
                    d = abs(v - tv)
                    if d <= ttol and d < best_dist:
                        best_dist = d
                        best_pos = m.start()
            if best_pos is not None:
                w = _VALUE_WINDOW + window_expand
                start = max(0, best_pos - w)
                end = min(len(text), best_pos + w)
                win = text[start:end].replace("\n", " ")
                if label == "sigma":
                    win_sigma, found_sigma = win, True
                else:
                    win_ea, found_ea = win, True

        score = (3 if found_comp else 0) + (2 if found_sigma else 0) + (1 if found_ea else 0)
        if score > best_score:
            window = win_sigma or win_ea
            if not window and found_comp:
                ci = text.find(comp_clean.lower())
                if ci >= 0:
                    window = text[max(0, ci - 120): ci + _VALUE_WINDOW + window_expand].replace("\n", " ")
            best = Evidence(
                page=page_idx,
                window=window[:_VALUE_WINDOW * 2],
                found_sigma=found_sigma,
                found_ea=found_ea,
                found_composition=found_comp,
                sigma_in_window=win_sigma,
                ea_in_window=win_ea,
            )
            best_score = score
    return best if best_score >= 0 else None


def locate_evidence(pdf_path: str | Path, composition: str,
                    sigma: float | None, ea: float | None,
                    window_expand: int = 0) -> Evidence | None:
    """Scan the PDF text layer for the composition and the sigma/Ea values,
    returning a window of text around the best match.

    Unit-aware sigma matching: the paper may report mS/cm or uS/cm while the
    record stores S/cm; the matcher tries the raw value AND its converted
    equivalents within a page so the window lands on the real number.

    Returns None for scanned/SCRIBED PDFs (thin or empty text layer) — the
    caller should then fall back to ``vision_locate_evidence``.
    """
    pdf_path = Path(pdf_path)
    if not pdf_path.exists():
        return None
    try:
        doc = fitz.open(str(pdf_path))
        pages = [p.get_text("text") for p in doc]
        doc.close()
    except Exception:
        return None
    if not pages or sum(len(p) for p in pages) < 100:
        return None  # scanned/SCRIBED — no text layer (needs vision)
    return _scan_pages(pages, composition, sigma, ea, window_expand)


# --------------------------------------------------------------------------
# Vision path (Phase E5) — unlocks scanned/SCRIBED PDFs with a clean text layer
# --------------------------------------------------------------------------

VISION_PROMPT = (
    "You are an OCR/reconstruction model for a scientific battery paper page. "
    "Transcribe EVERY number and chemical formula on this page, especially any "
    "table of ionic conductivity vs temperature and any activation-energy "
    "values, preserving the surrounding words (units like mS/cm, 'S cm-1', and "
    "labels like 'Li6PS5Cl'). Output only plain text."
)


def vision_enabled() -> bool:
    """True when a vision provider is configured via env vars."""
    import os
    return bool(os.environ.get("VISION_PROVIDER", "")) or bool(
        os.environ.get("VISION_BASE_URL", ""))


def _render_page_png(pdf_path: str | Path, page_idx: int, dpi: int = 160) -> bytes | None:
    """Render a single PDF page to PNG bytes via PyMuPDF (no external dep)."""
    try:
        doc = fitz.open(str(pdf_path))
        page = doc[page_idx]
        pix = page.get_pixmap(matrix=fitz.Matrix(dpi / 72, dpi / 72))
        doc.close()
        return pix.tobytes("png")
    except Exception:
        return None


def _vision_transcribe_bytes(png_bytes: bytes, page_no: int, provider: str,
                             model: str, *, base_url: str = "") -> str:
    """Send one page image to a vision model; return a plain-text transcription.

    provider ``ollama`` — POST to a local Ollama :11434/api/chat with an image
        (fully free, deterministic, no rate limit).
    provider ``groq`` (or a custom OpenAI-compatible base_url) — a chat
        completion with an image part.

    Injectable: tests monkeypatch this to avoid the network.
    """
    import base64
    import os
    import httpx

    b64 = base64.b64encode(png_bytes).decode()

    if provider == "ollama":
        if not model:
            model = os.environ.get("VISION_MODEL", "llava")
        payload = {
            "model": model,
            "images": [b64],
            "messages": [{"role": "user", "content": VISION_PROMPT}],
            "stream": False,
        }
        r = httpx.post(
            base_url or "http://localhost:11434/api/chat",
            json=payload, timeout=180,
        )
        r.raise_for_status()
        return (r.json().get("message", {}) or {}).get("content", "")

    # OpenAI-compatible (Groq) vision
    _base = base_url or os.environ.get("VISION_BASE_URL",
                                       "https://api.groq.com/openai/v1")
    _model = model or os.environ.get("VISION_MODEL",
                                     "llama-3.2-90b-vision-preview")
    _key = os.environ.get("VISION_API_KEY", os.environ.get("LLM_API_KEY", ""))
    if not _key:
        return ""
    payload = {
        "model": _model,
        "temperature": 0.0,
        "messages": [{
            "role": "user",
            "content": [
                {"type": "text", "text": VISION_PROMPT},
                {"type": "image_url", "image_url": {
                    "url": f"data:image/png;base64,{b64}"}},
            ],
        }],
    }
    r = httpx.post(
        f"{_base.rstrip('/')}/chat/completions",
        headers={"Authorization": f"Bearer {_key}"},
        json=payload, timeout=180,
    )
    r.raise_for_status()
    try:
        return r.json()["choices"][0]["message"]["content"]
    except Exception:
        return ""


def vision_locate_evidence(pdf_path: str | Path, composition: str,
                           sigma: float | None, ea: float | None,
                           window_expand: int = 0,
                           provider: str | None = None,
                           model: str = "",
                           transcribe=None) -> Evidence | None:
    """Vision OCR fallback for scanned PDFs (Phase E5).

    Renders each page to an image, transcribes it (Groq vision or local Ollama),
    then runs the SAME deterministic matcher as the text-layer path so the vision
    result carries an identical Evidence schema and plugs straight into
    ``verify_single`` / the review pipeline — one input format, not a second one.

    ``transcribe`` is injectable for deterministic tests (defaults to
    ``_vision_transcribe_bytes``). Returns None when no provider is configured or
    nothing is found.
    """
    import os
    pdf_path = Path(pdf_path)
    if not pdf_path.exists():
        return None
    provider = provider or os.environ.get("VISION_PROVIDER", "")
    if not provider:
        return None  # vision not configured — this stays a SCRIBED/needs_review gap
    model = model or os.environ.get("VISION_MODEL", "")
    transcribe = transcribe or _vision_transcribe_bytes

    try:
        doc = fitz.open(str(pdf_path))
        n_pages = doc.page_count
        doc.close()
    except Exception:
        return None

    pages: list[str] = []
    for i in range(n_pages):
        png = _render_page_png(pdf_path, i)
        if not png:
            continue
        text = ""
        try:
            text = transcribe(png, i + 1, provider=provider, model=model)
        except Exception:
            text = ""
        if text:
            pages.append(text)

    if not pages:
        return None
    return _scan_pages(pages, composition, sigma, ea, window_expand)


def locate_evidence_with_fallback(pdf_path: str | Path, composition: str,
                                  sigma: float | None, ea: float | None,
                                  window_expand: int = 0,
                                  transcribe=None) -> Evidence | None:
    """Text layer first; if None (SCRIBED), fall back to the vision path."""
    ev = locate_evidence(pdf_path, composition, sigma, ea, window_expand)
    if ev is not None:
        return ev
    if vision_enabled():
        return vision_locate_evidence(pdf_path, composition, sigma, ea,
                                      window_expand, transcribe=transcribe)
    return None


# --------------------------------------------------------------------------
# LLM structured verification
# --------------------------------------------------------------------------

VERIFY_PROMPT = """You are an independent scientific-data reviewer. Given a solid-state
battery electrolyte record and a snippet of the source paper, check each field.

RECORD:
- composition: {composition}
- sigma (S/cm): {sigma}
- Ea (eV): {ea}
- family: {family}

SOURCE SNIPPET (from page {page}):
"{window}"

Answer STRICTLY as JSON with these fields (no prose outside the JSON):
{{
  "evidence_present": true|false,
  "composition_found": true|false|"partial",
  "sigma_found": "yes"|"no"|"different",
  "sigma_quote": "exact quoted text containing sigma, or \"\"",
  "ea_found": "yes"|"no"|"different"|"not_reported",
  "ea_quote": "exact quoted text containing Ea, or \"\"",
  "temperature_found": true|false,
  "temperature_quote": "quoted temperature text, or \"\"",
  "units_found": "S/cm"|"mS/cm"|"uS/cm"|"unknown",
  "units_consistent": true|false,
  "notes": "brief justification"
}}

Rules:
- sigma_found is "yes" only if the value in the snippet matches the record sigma to
  within ~35% and is clearly the same measurement.
- sigma_found is "different" if a different sigma value is present.
- ea_found is "not_reported" if the paper simply does not give an Ea.
- QUOTE the exact substring (verbatim) containing each value — no summaries.
- If the snippet is empty or unrelated, set evidence_present=false.
"""


def _call_llm(prompt: str, model: str, *, max_tokens: int = 700) -> str:
    from ssb_dataset.config.settings import settings
    from dotenv import load_dotenv
    load_dotenv()
    import os

    api_key = os.environ.get("LLM_API_KEY") or settings.llm.api_key
    base_url = os.environ.get("LLM_BASE_URL") or settings.llm.base_url
    if not api_key:
        return ""
    import httpx

    payload = {
        "model": model,
        "messages": [{"role": "user", "content": prompt}],
        "temperature": 0.0,
        "max_tokens": max_tokens,
        "response_format": {"type": "json_object"},
    }
    try:
        r = httpx.post(
            f"{base_url.rstrip('/')}/chat/completions",
            json=payload,
            headers={"Authorization": f"Bearer {api_key}"},
            timeout=45,
        )
        if r.status_code == 200:
            return r.json()["choices"][0]["message"]["content"]
    except Exception:
        pass
    return ""


def _parse_verdict(raw: str) -> VerifierVerdict:
    v = VerifierVerdict()
    try:
        data = json.loads(raw)
    except Exception:
        data = {}
    v.raw = data
    v.evidence_ok = bool(data.get("evidence_present"))
    comp = str(data.get("composition_found", "")).lower()
    v.composition_ok = comp == "true" or comp == "partial"
    v.sigma_ok = data.get("sigma_found") == "yes"
    v.sigma_different = data.get("sigma_found") == "different"
    v.ea_ok = data.get("ea_found") == "yes"
    v.ea_different = data.get("ea_found") == "different"
    v.temp_ok = bool(data.get("temperature_found"))
    v.units_ok = bool(data.get("units_consistent"))
    v.units_note = str(data.get("units_found", ""))
    v.quote = str(data.get("sigma_quote", "") or data.get("ea_quote", ""))
    return v


def verify_single(evidence: Evidence, record: dict, model: str,
                  api_key: str = "", base_url: str = "") -> VerifierVerdict:
    """One model reviews one record against its evidence window."""
    window = evidence.window or evidence.sigma_in_window or evidence.ea_in_window
    prompt = VERIFY_PROMPT.format(
        composition=record.get("composition", ""),
        sigma=record.get("sigma_RT"),
        ea=record.get("Ea"),
        family=record.get("family", ""),
        page=evidence.page,
        window=window[:1800],
    )
    raw = _call_llm(prompt, model) if not api_key else ""
    if not raw:
        # allow the caller to inject a key/base_url through env normally; fallback empty
        pass
    v = _parse_verdict(raw)
    v.model = model
    return v


# --------------------------------------------------------------------------
# Physics check
# --------------------------------------------------------------------------

def physics_check(sigma: float | None, ea: float | None, family: str,
                  temperature_c: float | None) -> tuple[bool, list[str]]:
    notes: list[str] = []
    ok = True
    if sigma is not None and family in FAMILY_SIGMA_RANGES:
        lo, hi = FAMILY_SIGMA_RANGES[family]
        if not (lo <= sigma <= hi):
            notes.append(f"sigma {sigma:.2e} outside {family} range [{lo:.0e},{hi:.0e}]")
            ok = False
    if ea is not None and family in FAMILY_EA_RANGES:
        lo, hi = FAMILY_EA_RANGES[family]
        if not (lo <= ea <= hi):
            notes.append(f"Ea {ea:.2f} outside {family} Ea range [{lo:.2f},{hi:.2f}]")
            ok = False
    # Arrhenius prefactor sanity: sigma ~= sigma0 * exp(-Ea/kT)
    if sigma is not None and ea is not None:
        t_k = (temperature_c or 25) + RT_K
        kt = 8.617333262e-5 * t_k
        prefactor = sigma * (2.7182818 ** (ea / kt))
        lo_pf, hi_pf = TYPICAL_PREFACTOR_RANGE
        if not (lo_pf <= prefactor <= hi_pf):
            notes.append(f"Arrhenius prefactor {prefactor:.1e} outside typical [{lo_pf:.0e},{hi_pf:.0e}]")
            ok = False
    return ok, notes


# --------------------------------------------------------------------------
# Composite score + decision
# --------------------------------------------------------------------------

def composite_score(result: ReviewResult, *, units_ok: bool,
                    temp_reported: bool) -> float:
    """Weighted 0..100 review score.

    A record with located evidence, a confirming quote from >=2 models, physics
    pass, and no literature conflict reaches >=95 (spot_check); reaching 98
    additionally requires literature agreement or a known benchmark reference.
    Explicit 'different value' verdicts cap the score below the review gate.
    """
    s = 0.0
    ev = result.evidence
    evidence_present = bool(ev and (ev.sigma_in_window or ev.ea_in_window))

    # evidence: full credit only if a value window AND a confirming quote exist
    has_quote = any(bool(vd.quote) for vd in result.verdicts)
    ev_factor = 1.0 if (evidence_present and has_quote) else 0.9 if evidence_present else 0.15
    s += WEIGHTS["evidence"] * ev_factor

    # llm agreement: fraction of models confirming (a 'different' verdict is dissent)
    agreement = result.n_agree / max(result.n_models, 1)
    s += WEIGHTS["llm_agreement"] * agreement

    # any model reporting a DIFFERENT value for the checked field is a strong flag
    any_different = any(vd.sigma_different or vd.ea_different for vd in result.verdicts)

    # physics
    s += WEIGHTS["physics"] * (1.0 if result.physics_ok else 0.25)

    # literature
    s += WEIGHTS["literature"] * (0.75 if result.literature_note == "agree" else
                                  0.15 if result.literature_note == "conflict" else 0.5)

    # units
    s += WEIGHTS["units"] * (1.0 if units_ok else 0.2)

    # temp
    s += WEIGHTS["temp"] * (1.0 if temp_reported else 0.4)

    # hard cap: a 'different value' verdict means the model saw a value that
    # conflicts with the record — keep it under auto-approval but still allow
    # human review (could be a variant/composite case or an off-target window).
    if any_different:
        s = min(s, 82.0)

    # if no LLM model could review (0 models), cap so nothing auto-approves
    if result.n_models == 0:
        s = min(s, 74.0)

    return round(s, 1)


def decide(score: float) -> str:
    if score >= AUTO_APPROVE_MIN:
        return "auto_approve"
    if score >= SPOT_CHECK_MIN:
        return "spot_check"
    if score >= NEEDS_REVIEW_MIN:
        return "needs_review"
    return "reject"
