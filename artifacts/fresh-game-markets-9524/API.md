# #9524 fresh embedded market contract
PILLAR TRUTH. SHIP: held iPhone event props/spreads/totals update without a gesture; final scores and grades remain authoritative.

Implemented route: GET `/api/events/{positive_event_id}/game-markets?fresh=true`. Same full rendered builder projection, canonical event identity and existing grading rules. `fresh=true` bypasses memo/shared response cache reads and publication; response no-store. Ordinary requests retain existing cache behavior. Rate-limit extension belongs to root, not this branch.

Additive envelope fields from the builder's already-loaded inputs:
- `stream_market_ids`: sorted unique numeric candidate IDs, including currently withheld or empty-price markets so they can recover. No hidden50-ID truncation; consumer must represent overflow honestly.
- `outcome_market_ids`: exact loaded outcome→market binding, including off-screen rows which may affect normalized projections.
- `outcome_revision_at`: raw loaded row last_updated ISO clock/null, preserving microseconds. Ordering metadata only; rank/settlement/volume writes may advance it.
- `outcome_observed_at`: existing real-price observation metadata from the builder's snapshot/price_changed_at map, independently nullable. Never substitute row revision, request time or server build time. This map is not the ordering vector.

Whole projection reads must be adopted coherently; never replace a normalized sibling percentage by comparing its unchanged displayed value against only that sibling's raw quote clock. Embedded view consumer is now Codex review_recovered_source_bars ownership; root owns the finite fresh-read request budget.

Additive projected-row identity: `contributor_outcome_ids` holds the exact contributing outcome ID(s), unioned for blended props and represented per nested matchup leg. Existing `_market_id` / `_market_ids` remain available. These identities bind withdrawals/restores to their own quote rows so an unrelated sibling revision cannot restore an old quote. Price caps, source normalization, and grades remain unchanged.

Current: Latency exact hunk clearance granted04:15Z. Route bypass + provenance/envelope implemented.71 endpoint, cache, observation-age and startup testsPASS; exact source review, CI and Integrator delivery remain. No production query/write, merge, release or rendered acceptance.
