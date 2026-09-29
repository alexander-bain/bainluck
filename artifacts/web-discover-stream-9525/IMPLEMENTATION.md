# #9525 — visible Discover cards change price without a gesture

PILLAR: TRUTH. Parent #9484. Author: Codex deep_live_delivery_review.

Visible event and futures leaves subscribe to genuine invalidations, then request exact fresh `/api/feed/price-cards` bodies. Projection runs after Discover ranking/filtering/grouping and preserves card membership, order, parent identities, editorial copy and imagery. No quote is painted directly from a stream heartbeat or invalidation.

One foreground dispatcher coalesces requests, caps each batch at 50 combined identities and enforces at least two seconds between starts. Every batch, fallback read and retry shares that budget. A 429 uses positive Retry-After or a 60-second fallback, with no hidden API retry; cooldown survives hide/show. Unmount, hidden pages and principal changes stop requests/streams, and retired or no-longer-visible responses cannot paint. A 60-second recovery read remains even with healthy stream heartbeats.

Event adoption uses the complete fold revision and source clock; equal known folds cannot change their hero. Authoritative withholding clears a quote and finished truth may land without an invented quote clock. Futures use the entire raw outcome row-revision vector, preserving microseconds and coherent normalized/top-N bodies. The endpoint's legacy outcome clock aliases are ordering metadata, not proof of a quote observation; the existing card-level quote-age field remains authoritative. A newer sibling cannot cover an older raw leg; explicit withdrawals retain private clocks and null markers so cached bodies cannot restore them. Known settled winner, final event scores and source/group/canonical identity are protected.

Shared transport lives in `marketStreamController.ts` and `useMarketStream.ts`; #9526 consumes the same two helper commits fc964f1267 and df52e7ee8a. The common API default remains two retries; these consumers explicitly use zero. Integrator should compose the shared helper once and retain both independent API additions. No edits to existing event-page streaming, DiscoverCard, MasonryCell, shared types, backend, native or schema.

## Validation

- 66 tests passed in seven focused/adjacent suites (price adoption, dispatcher, API, market stream, existing Discover membership/order/paging).
- Backend startup: four tests passed.
- Frontend production build: passed after final source corrections.
- TypeScript: final result recorded in GATES.md.
- Independent shared transport and full Discover source reviews passed; review receipts include exact source hashes. Source files were rehashed against the eight-file Discover binding with every match.
- No production data operations or duplicate captures. No merge, deployment, timing or rendered acceptance claimed.

## Release dependencies and remaining acceptance

Requires fresh Discover leaf endpoint #9515 / PR #9518 with its separate finite route budget, market transport #9511 / PR #9510, and corresponding producer carriage. The endpoint currently returns unresolved/no body for assigned-settlement and some wholly withheld futures; this consumer preserves those held cards and does not claim those representation gaps are solved. Backend freshness source, deployed consumer and rendered delivery remain separate gates.

After release, UX owns one representative 390px held-page observation: a visible card changes following a genuine market/event commit without a gesture, maintains its position and membership, and burst dispatch stays at the two-second floor. No issue-closing keyword is included in the PR. Integrator alone composes, gates, merges and releases.
