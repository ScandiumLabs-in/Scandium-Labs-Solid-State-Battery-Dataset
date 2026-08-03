# Access Strategy (Phase E2 adaptation)

> **Adaptation from the expansion guide's Phase E2.** The original plan assumed
> VIT Bhopal institutional library subscriptions (ACS/Elsevier/Wiley/RSC/Springer)
> could be used to legally download a slice of the currently-blocked DOIs. **This
> build has no institution access**, so Phase E2 is deliberately NOT pursued. We
> source papers only through routes that are open by design — no paywall bypass,
> no scraping of access-controlled sites, no shared credentials.

## What that means in practice

| Route | Still used | Notes |
|---|---|---|
| Unpaywall (OA lookup) | ✅ | For every blocked DOI, only legitimately-OA copies |
| OpenAlex OA URL | ✅ | Phase E1 — free, no key, 100k req/day polite pool |
| Europe PMC render | ✅ | OA-deposited articles only |
| CORE API (free tier, key) | ✅ | Repository OA copies |
| BASE search | ✅ | Institutional-repository OA landing pages |
| Direct publisher OA | ✅ | Only when the venue is genuinely OA (DOAJ pre-check) |
| University / library proxy | ❌ | No institutional subscription available |
| Paywalled MCDFI/ACS/Elsevier/Wiley | ❌ | Accepted as a hard boundary — never circumvented |

Consequence: some gold DOIs (ACS/Elsevier/Wiley with no OA deposit) will remain
unreachable indefinitely. That is the honest ceiling this build works with. The
evidence gate is already tuned for it (85%, release_config.toml) and the README/
datasheet state it explicitly, so the limitation is a documented property, not a
quiet gap.

The pipeline never changes: any PDF that IS obtainable legally flows through the
exact same `extraction → verify_extraction_evidence → review queue` gates as
every other record, with `source_id` = DOI provenance.