# #9515 — fresh Discover leaf prices

PILLAR: TRUTH. SHIP: already-painted Discover cards update prices without a gesture.

GET `/api/feed/price-cards?event_ids=1,2&market_ids=3,4` accepts at most50 combined unique positive identities. Public read-only, `Cache-Control: no-store`; no full-feed cache/ranking rebuild, LLM or global invalidation.

Response: `{items:[FeedItem], dispositions:{"event-1":"updated", "futures-3":"unresolved"}, built_at:178...}`. `built_at` is numeric request-start epoch seconds, NEVER quote observation time. Items have exact existing `type` and `data.id`, ordered as requested events then markets. Private scoring fields are stripped. Native replaces exact matching leaves inside existing groups and keeps parent identity/order; never substitute a grouped question with standalone detail.

Event data: `current_odds` uses the authoritative folded hero, with served rounded percentages and draw-priced away refusal. `blend_fold_revision` names every read source row. `hero_probability_observed_at` dates the source inputs only when complete; unknown stays null. Source is `hero_probability_source`; opening-only/final-unresolved clears current_odds with `withheld`, not live credit. Final scores/result remain the existing serializer's truth.

Futures data: existing full normalized feed projection plus `external_id`; source/group/canonical identity unchanged. Each top_outcome has optional `price_observed_at`; `outcome_observed_at` maps ALL loaded outcome IDs to own precise ISO observation or null, including off-top legs. This map supports legitimate top-N/divisor changes without using one newer leg to promote an older leg. No timestamp is invented from request, publication or market-level clocks.

Dispositions: `updated` identifies a supported fresh projection, not acceptance or evidence of value change. `withheld` event items explicitly have no fresh current quote. `missing` means the exact row was not read; not a delete instruction. `unresolved` leaves the held card and coverage debt explicit. Current unresolved shapes include assigned-settlement futures (the existing feed serializer does not handle all verdict shapes), partial/unknown event revision, and futures omitted by retained safety rules. This endpoint alone does not complete all-surface streaming; producer signals, consumers and rendered delivery remain separate.

Fresh futures reuse existing quote/withholding/divisor formatting via `_score_futures(preloaded_base=..., price_refresh=True)`, skipping only editorial membership/caps and caches. Fresh events reuse `_score_events(price_refresh_events=...)` on already folded, read-only proxies. Ordinary feed defaults and display-chain code remain unchanged.

Gates:23 direct tests pass;51 existing price-safety, event resilience/hero, snapshot projection and startup controls pass. Ruff on new route/tests passes; feed.py's13 pre-existing lint findings unchanged (RUFF-BASELINE.json). Independent source review pending. No production read/write, merge, release or phone acceptance performed.
