# LAT-P063 §I — `/api/admin/interestingness-side-by-side` ranks **PRE-interleave**. Alex's blend re-rule needs the interleave-aware mode, and here is its design.

**Asked:** FABLE DIRECTIVE, open since the week of 2026-08-10, re-asked 2026-08-17 item 5.
**Answered against:** `29639b78` (deployed, Heroku v3830), read from source, not inferred.

---

## §I1 — The answer, in one paragraph

**Pre-interleave.** `interestingness_side_by_side` (`backend/app/routes/admin_feed_config.py:74`)
runs exactly three stages per weight — `_score_futures(...)` → `_dedupe_futures_by_canonical(...)` →
`rows.sort(key=_rank_key, reverse=True)` — and then slices `[:limit]`. That is the whole chain; it
stops at the same `sort` line the live feed reaches at `feed.py:2109`, and it executes **none** of
what `get_feed` does afterwards. The *scoring-time* story caps ARE represented, which is the part
that makes the answer easy to get wrong: `cap_low_quality_families(cap=1)` and
`cap_repeated_market_families(story_family_cap=5)` live **inside** `_score_futures`
(`feed.py:7074`, `:7078`), so "story tier" in the family-cap sense is in the artifact. What is
**not** in it is every stage that reorders the slate afterwards —
`_demote_non_exceptional_discover_events` and its re-sort, `_filter_discover_event_noise`,
`balance_discover_event_category_mix`, `_ensure_feed_diversity` (which is the literal interleave:
*"Among the top N items, interleave so events aren't all pushed down"*, `feed.py:7189`–`7234`),
`diversify_discover_first_page` — **which applies its own first-page story cap of 2 per
`_quality_story_key`, on top of per-category and per-archetype caps** —
`backfill_discover_editorial_tail`, the four bundle assemblers, and lead composition (marquee pin +
tonight's games). There is also a **population** difference, not merely an ordering one: the endpoint
calls `_score_futures` with `sport_filter=None` and assembles **no events pool at all**, while the
served Discover slate interleaves events with futures. So the artifact answers *"does this weight
change the futures ranking?"* and Alex's re-rule needs *"does this weight change the page?"* — and
those are different questions separated by roughly a dozen reordering stages and a whole card type.

## §I2 — Why the gap is not merely cosmetic, in both directions

The endpoint's `comparison` block reports `positions_changed`, `entered_top_n`, `left_top_n` and
`biggest_movers` over a list **no user is ever served in that order**. `diversify_discover_first_page`
re-picks the first 20 cards under category/archetype/story quotas, so a pre-interleave delta can be:

- **ABSORBED** — two markets in the same category group swapping ranks 6 and 9 changes
  `positions_changed` by 2 and leaves the served page **byte-identical**, because the quota picks the
  same card either way. The artifact over-states the effect.
- **AMPLIFIED** — one market crossing a quota boundary at rank 3 evicts a *different* card at rank 11
  and pulls a third in from rank 24. The artifact reports one move; the user sees three.

**Neither direction is bounded and the current output cannot tell them apart**, so the artifact
supports "the weight is not inert" and cannot support "the weight is worth N". That is precisely the
distinction a blend re-rule turns on. It is also the same failure the endpoint's own docstring already
names about the offline replay — *"models the ranking chain faithfully but not the display chain's
`+15` cap and `0-98` clamp, so a weight ratified against the replay would be a weight ratified against
a function Discover does not run."* **The endpoint fixed that for the scorer and reproduced it one
stage later for the display chain.**

## §I3 — The proposal: `?stage=` , and the one structural rule that makes it worth building

Add `stage: str = Query("ranked")` with two values:

| `stage` | chain | purpose |
|---|---|---|
| `ranked` (**default, unchanged**) | today's three stages | keeps every artifact already produced comparable; nothing regrades |
| `served` | the full Discover chain, through lead composition, truncated at `limit` | what Alex's re-rule actually needs |

**The rule that makes this safe, and the reason to build it rather than re-implement it:** `served`
must call an **extracted** `apply_discover_display_chain(items, *, limit, ctx, event_pct, cold_start)`
that `get_feed` also calls — a pure reordering function lifted out of `get_feed`'s ~100 inline lines
(`feed.py:2109`–`2210`), not a second copy in the admin route. A second copy drifts, and a drifted
ratification artifact is worse than none: it would carry Alex's authority while describing a page
Discover does not build. This is `#257`'s shared-payload lesson (one `compute_calibration_payload`
feeding both precompute and route) applied to the feed's display chain, and it is the majority of the
work — the endpoint change itself is a dozen lines.

`served` must also **build the events pool**, or the interleave has nothing to interleave and
`_ensure_feed_diversity` is a no-op. Cheapest faithful route is the candidate-pool assembly `get_feed`
already uses in Discover mode; scoring events per weight is wasted work only if the blend cannot move
an event, which it cannot today — so **score events once and reuse across weights**, and say so in the
response (`events_scored_once: true`) rather than letting a reader assume otherwise.

**The two fields that are the actual answer to Alex's question**, computed by diffing the two stages
for the same weight:

- `absorbed` — moved pre-interleave, identical post-interleave
- `amplified` — unmoved pre-interleave, different post-interleave

A weight whose `absorbed` is high is a weight the ranking notices and the user does not. That number,
not `positions_changed`, is what a blend re-rule should be graded on.

**Preserved unchanged:** per-pass weight injection via `config["interestingness_blend_weight_override"]`,
`live_key_untouched: True`, and `cache_hits` — which stays the **first** thing to read in both modes,
because an empty `interestingness:*` cache still renders as `identical: true` and is still
indistinguishable from a genuinely neutral weight (gotcha #53).

**Bound it, because this is the latency program.** `served` runs a full Discover build per weight. Cap
it at **2 weights and `limit ≤ 20`** in `served` mode and return a 400 outside that, rather than
letting a 4-weight `served` call turn an admin diagnostic into four feed builds in one request. Also
report `build_ms` per weight in the response so the instrument prices itself.

## §I4 — Registered expectation, so the mode can be wrong in a legible way

Written before the mode exists (ruling 050). When `served` first runs at the weights Alex is
considering: **`absorbed` > 0 on at least one weight.** If `absorbed` is zero across every weight and
every card — that is, if the display chain turns out to pass ranking deltas through untouched — then
this whole finding is a distinction without a difference, `ranked` was always sufficient, and the mode
should be deleted rather than kept. I do not expect that (`diversify_discover_first_page`'s caps are
tight and the first page is exactly where quotas bind), but it is the result that would refute the
proposal, and it is cheap to check first.

## §I5 — Not proposed

- **Changing the blend weight, or the default.** The signal stays dark; this is instrumentation for
  the decision, not the decision.
- **Making `served` the default.** `ranked` stays default so prior artifacts remain comparable, per
  ruling 069's "re-measure, never re-quote" — a changed default silently re-bases every comparison.
- **Touching `_rank_key`, the `+15` cap, or the `0–98` clamp.**
