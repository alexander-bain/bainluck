# Independent fresh standalone market budget source review PASS

Reviewer: Codex deep_live_delivery_review. Two changed source/test files bound by accompanying SHA-256 map. No executable gates or production operations duplicated.

Reviewed exact GET classifier for /api/futures/{positive-id} and /probability-timeline with explicit truthy fresh opt-in, last-query-value semantics and matching Pydantic integer timeline bounds (top 1..50, hours 1..8760). The actual detail and probability-timeline handlers were inspected and read current outcome rows; this middleware isolates their request budget without changing price data or freshness claims.

One finite 120/minute fresh-market namespace preserves existing verified UID, trusted-router provenance or anonymous IP identity. IDs, top/hours and unverified bearer rotation do not create new buckets. Both asynchronous Redis and memory fallback choose the same ceiling/key, while ordinary feed/search/detail, event and feed-price budgets retain their prior paths. 429 remains the existing positive Retry-After/body contract. No exemptions or production environment/configuration writes introduced.

Source test review covers both storage paths and anonymous/authenticated/trusted identities, exhausted-bucket isolation, forged-token rotation, exact route/query restrictions and actual production route existence. Author reports 91 focused/adjacent/startup tests and Ruff passing; these were not rerun by reviewer.

Source PASS only. Exact committed binding, CI, Integrator composition with #9515 and release still belong to author/desk. Client fresh=true carriage, two-second dispatch/cooldown, actual provider-to-page delivery and rendered acceptance remain separate gates. The existing fail-open behavior on Redis faults is unchanged; 120/minute is a configured ceiling, not measured server capacity.
