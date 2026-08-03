# Literature sizing memo — total addressable SSE literature

**Action 1 of the Path-to-10k plan.** Purpose: turn "how many papers do I need"
into a number before building scale infrastructure. Data sources: OpenAlex
(counts captured 2026-08-03 before the batch matrix run consumed the polite
pool; on-disk discovery/harvest artifacts for yield rates).

## 1. Total addressable papers (the denominator)

OpenAlex counts for the SSE-adjacent query space (materials-science venues,
2000–2026, captured while the polite pool was available):

| Query | OpenAlex count |
|---|---|
| `sulfide solid electrolyte ionic conductivity` | 14,056 |
| `Li6PS5X OR thio-LISICON OR Li7P3S11 solid electrolyte ionic conductivity` | 75,719 |
| `Li6PS5Cl ionic conductivity` | 247 |

The 14k–75k band is the broad "touches SSE conductivity" pool. The realistic
**addressable core** — papers where a solid electrolyte's ionic conductivity is
a primary measured quantity, not a passing mention — is much smaller. On-disk
discovery evidence supports this: 11 families of curated candidates total
**1,230 papers** after relevance triage (OpenAlex 474, Semantic Scholar 66,
untagged 756), of which **287 carry an OA URL**.

**Estimated addressable core: ~2,000–4,000 distinct papers.**

## 2. Accessible fraction

- OA-bearing candidates (OA URL on-disk): **287 / 1,230 ≈ 23%** of curated
  candidates.
- Current on-disk harvest state: 924-DOI manifest, **117 downloaded_direct +
  37 downloaded_epmc + 11 downloaded ≈ 165 PDFs on disk**, 732 blocked.
- The 2026-08-03 Unpaywall re-sweep of all 732 blocked DOIs is running;
  `blocked_doi_reasons.json` will record the per-DOI reason for every one that
  stays blocked.

**Accessible fraction estimate: 25–35%** of the addressable core, i.e. roughly
500–1,400 papers with a legal full-text route from this (no-institutional-access)
network.

## 3. Records-per-accessible-paper yield rate

Deterministic extraction has been run on ~99 unprocessed PDFs with an ensemble
of 3; verified label count sits at 116 from ~165 PDFs. Yield drivers:

- A single-compound paper → 1–5 records (σ + Ea, possibly multi-temperature).
- A doping-series paper → 5–15 records (multiple compositions × temperature).
- A combinatorial / high-throughput screening paper → 20–200 records in one
  table (Action 3 lever — this is the order-of-magnitude source).

Current conservative blended yield from on-disk PDFs: **~0.7 verified
records/PDF**. That rises toward **2–5 records/PDF** once combinatorial-table
papers (Action 3) and plot digitization (Action 4) contribute, since those
sources yield many more records per paper.

## 4. Resulting realistic ceiling

With the conservative 0.7 records/PDF and 500–1,400 accessible papers:

| Scenario | Accessible papers | Yield | Ceiling |
|---|---|---|---|
| Current machinery, single-compound papers only | 700 | 0.7 | ~500 verified |
| + combinatorial tables (Action 3) | 700 | 2.0 | ~1,400 |
| + plot digitization (Action 4) | 700 | 3.0 | ~2,100 |
| + institutional/community access (E2/E9) | 1,400 | 3.0 | ~4,200 |

**Verdict: 10,000+ verified records is an 18–36 month, multi-contributor
target, NOT a solo near-term deliverable.** The 1,500–3,000-record band is the
realistic ceiling of this pipeline on free-only access; 10k requires either a
large accessible fraction via institutional access, sustained community
submissions (E9), or both — exactly the conclusion of the companion plan's
milestone ladder.

## 5. Actionable consequence

The ceiling is set by **accessible-paper count × records-per-paper**, and the
multiplier that moves first is records-per-paper (combinatorial tables + plot
digitization), not paper count. Prioritization order confirmed:
1. Run the blocked-DOI Unpaywall sweep to closure (Action 0.2).
2. Process combinatorial-screening papers end-to-end as a proof of throughput
   (Action 3 DoD).
3. Only then invest in widening access channels (E9/E2) — they matter, but
   they don't move the number until the per-paper multiplier is working.

_Generated 2026-08-03. OpenAlex counts will be refreshed once the polite pool
recovers from the batch matrix run._
