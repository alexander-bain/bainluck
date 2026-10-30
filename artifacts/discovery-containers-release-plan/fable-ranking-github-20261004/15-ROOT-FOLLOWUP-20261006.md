# Root follow-up: preservation and capture cost, October 6

Alex requested preservation and answers, with no capture dispatch implied. No collection job or feature code was implemented or enabled. This follow-up supplements file 13 and the implementation proposal in file 14; it does not authorize that proposal. Existing Discover priorities and the #5440 post-launch boundary remain unchanged.

## Preservation and reproducibility

Fable's `14-FABLE-ERRATA-AND-EVIDENCE.md` and the bundle's 35 non-gzip files (including the original manifest) are preserved byte-for-byte in PR #10623. Original files 11–13 are unchanged. The manifest covers 38 payload files; with the manifest and errata there are 40 supplied files. All 38 size/hash entries verify.

The complete 29,085,438-byte archive includes all four compressed venue pulls: two Polymarket files around 10.46 MB each and two Kalshi files around 3.61 MB each. Large archives are excluded from Git history. Storage and recovery details are in `16-EVIDENCE-ARCHIVE-20261006.md`.

Recomputed grades: 98 total, 46 amazing / 44 fine / 8 no; the reported type tallies agree. The endpoint CSV contains 32 rows (7 week, 21 month, 4 overnight), including six synthetic prior endpoints among 28 week/month rows, on cards 1, 6, 13 and 18. These are now explicit, not observed earlier blended prices. The history file holds 413 Polymarket histories. An “observed” flag alone still does not establish identical historical and current displayed composition.

The new bundle resolves the earlier lack of grade exports, claim tables, histories, final selections and checker outputs for the supplied slates. It does not recreate the overwritten v1/v2 venue pulls or the first two v4 grading passes. The venue listings are reduced rows, not original API response bytes. Founder grades remain founder evidence, not daily supply or reader acceptance.

## 1. Why only three of 36 markets had a dated bank

Source pin: master `cf5ff9397d884d3b6669b1eb09e86e76e9aaa9b0`, `backend/app/tasks/__init__.py`, general A8/A9 around lines 4590–4745; constants around lines 3307–3565. The inspected movement files match the previously read live revision `0f3f3a65`.

**Yes: for ordinary non-DataGolf markets, the bank is gated by a last-write change of at least 0.02 (two percentage points), not a measured day-over-day change.** A8 requires a non-null current probability and stored delta, an open market, and that magnitude floor. A9 removes a market's bank when no outcome retains a qualifying delta. A quiet subsequent poll can therefore remove an otherwise useful dated basis. Earlier sweep stages can retire deltas before banking.

Other gates also matter: snapshots strictly inside the preceding 24 hours; oldest qualifying priced observation at least 12 hours old; exactly one bookmaker across the window; only the allowed scale-identical source names; and a priced book (both sides absent, or spread under 0.20; one-sided/wide books fail). Unpriced observations still count in source/scale checks. Banking is bounded to 10,000 markets per run, ordered by last-write magnitude; an empty qualifying payload removes a bank. DataGolf has a separate arm that admits zero delta.

This establishes a structural coverage bottleneck, not the individual reason for all 33 missing banks. The retained 36-market sample does not include contemporaneous per-write deltas, complete daily snapshot/book details or sweep state. Per-row attribution remains UNKNOWN. It was one stale cached first-20-card sample, not the eligible population. Raw bank observations are also not historical displayed blends.

## 2. Cost and risk of accruing displayed-probability history now

A useful durable record needs canonical question/option identity, the displayed probability and scale, actual contributing sources and weights/normalization, source quote observation times, capture time, and display/aggregation policy version. Available `sources` / `source_count` describe available venues, not necessarily arithmetic contributors. Missing lineage must remain UNKNOWN; it cannot be reconstructed from today's source list. Recopying a cached quote does not create a new quote observation.

Planning ranges, not commitments:

| Scope | Engineering estimate | What it buys |
|---|---|---|
| Bounded capture of already selected feed inventory | 1–2 days, if provenance is available | History only for those selected options; incomplete eligible-population coverage |
| Full Discover-eligible inventory with durable actual display lineage | 3–5 days plus normal integration, conditional on reusable canonical IDs and lineage | History for eligible options regardless of whether selected; provenance and retention contract |

If actual contributors or display normalization are unavailable at the capture seam, writer-side plumbing increases the second estimate. Both ranges exclude waiting for historical endpoints, release scheduling and reader acceptance. A baseline publisher/consumer is additional work (roughly one day for a bounded contract), not part of merely preserving rows. Card implementation is not included.

For selected inventory, `_prewarm_feed_shape` in `backend/app/tasks/precompute_category_pages.py` already checks complete/nonempty newly built payloads and publishes cache entries before recording served-market IDs (around lines 1230–1330 and 1399–1417). A sampled capture hook could reuse this work, after successful publication, with independent bounded asynchronous writes. This is only selected inventory. Full eligibility requires an earlier candidate/precompute seam and the same display computation/provenance; the feed warmer is not a population census.

Illustrative hourly storage, assuming 300–600 logical bytes per option record (not a measured population or guaranteed schema size): N options produce 24N rows/day. At 10,000 options that is 240,000 rows/day, 72–144 MB/day; eight days is 1.92 million rows and 0.58–1.15 GB; 32 days is 7.68 million rows and 2.3–4.6 GB. Indexes, WAL, backups and variable source composition add overhead. The average is 2.78 rows/second but hourly batches need size/time bounds. Dollar cost is unknown until storage and eligible population are specified.

Reusing computed data needs no new provider or LLM calls. The main costs are engineering displacement, database/worker writes and retention, and the risk of delaying feed publication or recording misleading provenance. Keep collection out of request handling, fail independently of cache publication, batch and cap writes, use bounded retention, preserve real observation freshness, and make gaps visible. Avoid unbounded market JSONB or a new broad production scan merely to size this proposal.

My recommendation is to design durable capture as a small substrate of the already named “Since yesterday” ship, only when explicitly staged against current priorities. A selected-only archive is cheaper but does not satisfy the full eligible-question request. Qualifying yesterday pairs cannot accrue before at least 20 hours; week pairs need at least seven days; elapsed time alone guarantees neither valid composition nor enough supply.

## Work state and anything needed from Alex

No decision is needed to preserve this evidence. Capture remains a costed proposal, not dispatched work. Root's temporary #948 implementation claim preceded this clarification; it has been returned to Review / Verify, with Discover still accountable and its next step explicitly stating that no collector/card implementation is active. Priority and release gates are unchanged. Starting collection would need a separately authorized scope and scheduling decision; nothing is being requested now.
