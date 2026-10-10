# Smallest truthful Movers implementation — October 6, 2026

PILLARS: DISCOVER and TRUTH.
SHIP: a reader sees a compact “Since yesterday” card with observed prior/current probabilities for 2–4 questions, and can open each exact question and return to the feed.

This is a proposed implementation handoff under existing #948/#4079/#5440, not a Ready queue, file claim, new release gate or dispatch. Alex authorized Sol subagents; three bounded source/evidence/ownership checks informed this packet. Source remains master `cf5ff9397d884d3b6669b1eb09e86e76e9aaa9b0`. Current priorities and #5440's post-launch boundary remain unchanged.

## Current ownership and overlap

- #948 is open, Project Review / Verify; #4079 is open, Inbox / needs-triage; #5440 is open, Inbox / post-launch. No GitHub assignee does not make the implementation unowned: Discover owns the feed/bank/card work, with normal platform contributions.
- Discover currently has PR #10622 for #10621, touching `routes/playoffs.py` and its dedicated same-blend test. That is a playoff-grid repair, not this Discover card. Do not duplicate or interrupt it.
- Open PR #2466 touches `tasks/__init__.py` and movement-expiry logic. Its ancestry and scope require reconciliation before claiming the producer file. A next build must claim its exact files through the existing owner; this packet changes no issue fields.
- Evidence PR #10623 is preservation only. Its current source is not a product implementation.

## Exact implementation sequence

1. **Producer and quantity identity.** Extend the existing asynchronous capture/precompute path with opt-in, versioned comparison evidence. Reuse bank machinery without repurposing the legacy `dated_movement_basis` or per-write delta. Store canonical question/option identity, actual observation time, actual displayed probability, contributing source identity, probability/display policy version and price-validity evidence. Bound work to existing Discover candidate inventory. Ordinary A8 currently filters on last-write magnitude (`tasks/__init__.py:4670`); new comparison capture must not inherit that filter.
2. **Admission helper.** Initially support explicitly evidenced single-source, unnormalized product quantities. Today's source-count list alone is insufficient. Admit a prior observation 20–24 hours before the current observation, require current freshness, and expire the cached pair. Reject changed identity, contributor set, probability policy, withdrawn/illiquid data and settlement artifacts. Compute change from actual displayed endpoints, before rounding. If a historical quantity cannot be reconstructed exactly, capture new evidence and allow at least 20 hours to mature.
3. **Card contract and selection.** Add an optional typed verified pair to the exact displayed answer. The current selector reads `top_outcomes[].probability_change_24h` (`discover_bundles.py:2129`), while served rows expose `movement` (`feed.py:12262`, `13885`). Consume the verified pair explicitly; merely renaming the bundle or editing `/futures/movers` is insufficient. The compact answer can be a selected ladder rung: do not silently compare another outcome.
4. **Existing presentation.** Reuse `assemble_swings_theme_bundles` and `frontend/components/discover/ThemeBundleCard.tsx`. Show prior/current probability, percentage-point change and inspectable observation times in a 2–4-row peek. Preserve member links, expansion, actions and Back context. Keep the product light-only. No compulsory slot; 0/1 valid questions leave the ordinary feed intact. Suppress repeated or complementary questions and their redundant standalone cards.

The initial restricted slice deliberately refuses unsupported blended/normalized histories. A later normalized comparison may legitimately have different numerical denominators at the two times, but both must be evidenced under the same display policy; dividing yesterday's raw value by today's denominator is never sufficient. Do not replace a displayed blend with a source quote to manufacture supply.

## Acceptance cases to implement with the patch

- Observed 42% → 51% on the same product quantity 22h apart publishes +9 points.
- 19h59m and >24h refuse; expiry suppresses an otherwise valid cached comparison.
- A large dated change with a zero last-poll change remains eligible; a large last-poll change with no dated change does not qualify.
- Missing/malformed endpoint, changed question/season/round/option, changed source/policy, unsupported normalization, withdrawal, illiquidity and settlement jumps refuse.
- An inferred prior blend made by subtracting one venue's change refuses.
- Measured flat and unavailable evidence remain distinct.
- The pair refers to the compact row's actual selected answer; arithmetic agrees with displayed endpoints.
- 0/1 valid questions preserve the existing feed; 2–4 distinct questions form at most one optional card; represented questions appear once and remain reachable.
- Real selected-feed → exact question → Back works, including stale/partial states, readable phone width and existing client requirements.

Extend the existing #4079 and bundle guard families and add a meaningful presentation/navigation check. Existing `/movers` behavior is outside this slice. No request-time provider calls, history scan, model call or new ranking service.

## Coverage and delivery boundary

For one captured pre-selection Discover inventory, count deduplicated eligible canonical questions, then valid endpoint pairs, then the subset meeting the reviewed editorial threshold. Do not use page-one selection, non-null per-write deltas or raw snapshot presence as that denominator or numerator. One edition does not prove daily renewing supply. The retained sample supports no claim of a currently admissible comparison under the full contract; this is not a measured zero across Discover.

Rough implementation estimate: 5–7 production files plus focused tests, 2–4 engineering days if the existing asynchronous path can carry candidate IDs and writer provenance, then any baseline maturation and existing integration/client/whole-feed acceptance. If that assumption fails, re-scope the visible slice rather than start an architecture program. #10356/#5105 retain whole-feed opportunity-cost acceptance. No delivery date or capacity has been promised.
