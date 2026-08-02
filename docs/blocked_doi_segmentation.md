# Blocked-DOI segmentation (2026-08-03)

Indicative analysis of the 666 `blocked` harvests in `literature_output/harvest_manifest.json`.
For planning the path to 500 verified labels, this separates "truly unrecoverable
without a paid license" from "not yet tried on available routes" from "content-free".

## By publisher (grouped)

| Publisher | Blocked | Share | Recoverability |
|---|---|---|---|
| Wiley | 155 | 23% | Recent OA via EPMC; otherwise paywalled |
| Elsevier | 146 | 22% | Paywalled; few OA routes |
| other | 142 | 21% | Mostly ECS *meeting abstracts* + repositories (see below) |
| ACS | 120 | 18% | Paywalled; eScholarship direct mirror worked for one DOI |
| RSC | 63 | 9% | Some OA |
| MDPI | 24 | 4% | Usually OA — recheck Cloudflare-blocked route |
| Nature | 7 | 1% | Mostly OA (Comms/Sci Rep) — recheck |
| IOP | 7 | 1% | Some OA |
| Springer | 3 | 0% | Some OA |
| Frontiers | 1 | 0% | OA — recheck |
| AAAS/Science | 1 | 0% | Confirmed scanned image-only for one title |
| **Total** | **666** | 100% | |

## The `other` bucket (141) — read before lumping it in

- ~30 are **ECS Meeting Abstracts** (`10.1149/ma20XX-*.mtg*`), i.e. conference
  abstract DOIs with no full paper. These are **content-free** for extraction and
  should be treated as permanently non-extractable, not "blocked."
- ~15 are Springer journal DOIs (`s10008`, `s11581`, etc.) miscounted by the coarse
  grouping — reclassify to Springer.
- `chemrxiv` / `preprints` DOIs are preprints (should be recoverable via route 5).

## Key implications

1. **Wiley + Elsevier = 301 DOIs (45%)** are the hard paywall core. Without a
   licensing / institutional TDM / author-manuscript conversation these are not
   recoverable from open literature alone.
2. **MDPI (24), Nature (7), IOP (7), Frontiers (1)** are disproportionately just
   Cloudflare/route failures — a **re-route retry** against these is cheap and
   likely to recover most of ~40 DOIs.
3. The **ECS-abstract false positives** should be removed from the "blocked"
   denominator; they are not a coverage loss.
4. So realistic recoverable-Yet-on-current-route ≈ 666 − 30(ECS abstracts) −
   ~40(MDPI/Nature/IOP/Frontiers retry) ≈ a smaller, more tractable backlog than 666.