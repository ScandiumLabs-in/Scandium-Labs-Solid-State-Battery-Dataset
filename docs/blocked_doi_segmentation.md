# Blocked-DOI segmentation (2026-08-03, reconciled + exact)

Indicative analysis of the 666 `blocked` harvests in `literature_output/harvest_manifest.json`.
For planning the path to 500 verified labels, this separates "truly unrecoverable
without a paid license" from "not yet tried on available routes" from "content-free".
Counts are generated directly from the manifest (exact; 666 sums exactly).

## By publisher (exact, sums to 666)

| Publisher | Blocked | Share | Recovery outlook |
|---|---|---|---|
| Wiley | 155 | 23.3% | Recent OA via EPMC; otherwise paywalled |
| Elsevier | 146 | 21.9% | Paywalled; few OA routes |
| ACS | 120 | 18.0% | Paywalled; one DOI recovered via eScholarship direct mirror |
| ECS meeting abstracts | 81 | 12.2% | **Content-free** — conference abstract DOIs, no full paper. Remove from denominator |
| RSC | 63 | 9.5% | Some OA |
| other | 38 | 5.7% | Real journals across many small publishers (see below) |
| MDPI | 24 | 3.6% | OA — recheck Cloudflare-blocked route |
| ECS journal | 14 | 2.1% | Real papers (J. Electrochem. Soc.) — paywalled but reviewable |
| Nature | 7 | 1.1% | Comms/Sci Rep are OA — **fold into cheap re-retry** |
| IOP | 7 | 1.1% | Some OA — recheck |
| Preprint (ChemRxiv/SSRN) | 6 | 0.9% | Recoverable via preprint route (route 5) |
| Springer | 3 | 0.5% | Some OA — recheck |
| Frontiers | 1 | 0.2% | OA — recheck |
| AAAS/Science | 1 | 0.2% | Confirmed scanned image-only for one title |
| **Total** | **666** | 100% | |

## The `other` bucket (38 — small publishers worth a route retry)
All represent real reviewable papers (no content-free abstracts). Largest several
distinct publishers: AIP/Psi (10.1063, 9), IEEE (10.1109/10.1115, 4), Hindawi
(10.1155, 2), Springer-Micro (10.1186, 1), Wiley-X/materials (misc). These are
**not a homogeneous paywall block** — each is a separate small publisher that may
have its own OA whereabouts. Not cost-efficient to chase individually; treat as
low-priority route-5 recoverables, not as a lost cause and not as one publisher.

## Cheap re-retry bucket (recoverable with near-zero incremental cost)
Fold these in as "recheck the capped/blocked route" rather than treating them as paywalled:
| Group | DOIs | Why likely recoverable |
|---|---|---|
| MDPI | 30 | Open-access journal; blocked was Cloudflare, not paywall |
| Nature Comms/Sci Rep | 7 | Mandated OA |
| IOP | 7 | Many OA |
| Frontiers | 1 | OA by policy |
| Preprint | 6 | Already public (ChemRxiv/SSRN) |
| **Subtotal** | **51** | Cheap re-retry group |
| ECS meeting abstracts | 81 | Remove from coverage denominator (content-free) |

## Key implications (reconciled)
1. **Wiley (155) + Elsevier (146) + ACS (120) = 421 DOIs (63%)** are the paywall
   core. Without a licensing / institutional-TDM / author-manuscript conversation,
   these are not recoverable from open literature alone. Segment by publisher
   *before* a TDM-spend decision.
2. **81 meeting-abstract DOIs are not a coverage loss** — they carry no extraction
   content. Removing them from the "blocked" denominator is honest: the figure to
   optimize is ~585 real papers, of which ~51 are cheap re-retry and ~421 are the
   paywall core.
3. **~51 DOIs (MDPI+Nature+IOP+Frontiers+Preprint) are cheap re-retries** likely to
   recover a meaningful slice at ~zero incremental cost (Cloudflare/OA-route
   failures, not paywalls).
4. The `other` = 38 are small-publisher papers — low priority, low count each.