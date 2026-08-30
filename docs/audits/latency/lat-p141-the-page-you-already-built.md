# LAT-P141 — the page the server had already built

**Pillar: DISCOVER (product priority #2, the default landing page).**
**Ship: scrolling Discover stops rebuilding the page you already have.**

Issue **#2143**. Branch `program/latency-126`, cut from `origin/master`
`944c466e` (which merged LAT-P140 mid-session — `program/latency-125` is spent).
No DDL · no migration · no beat change · no config var · backend only · zero
frontend files · zero ios files.

---

## 1. The finding, before any code

`GET /api/feed` builds the whole ranked list and then does

```python
total = len(feed_items)
paginated = feed_items[offset : offset + limit]
```

`offset` reaches the build at **exactly that expression**. The candidate pools,
the scoring, and `apply_discover_display_chain` are all functions of the shape
and of `limit` — the chain's own docstring says so about `limit` ("Several
stages size their windows from it, so it is part of the build, not just the
slice") and says nothing about `offset`, because there is nothing to say.

The response cache keys on it anyway (`feed_cache.feed_response_cache_key`,
`…:{limit}:{offset}:…`). So page 2 is a different key, holding a build
indistinguishable from page 1's, and **nothing warms it or can** —
`FEED_PREWARM_SHAPES` is five entries and every one of them is `offset: 0`,
because warming page 2 separately would mean running the identical build twice
and storing two windows onto one list.

#2143 named this in August and left it unmeasured: *"`offset` is part of the
cache key and only `offset=0` is pre-warmed, so pagination is always cold. (This
split is not yet measured.)"* This queue measures it and closes it.

## 2. The measurement — pre-registered, production, one fresh install per sample

`lat_p141_pagination_probe.py`, n=5 per shape, round-robin (a dyno restart lands
on whichever shape is running; block-sequential would blame one page for the
whole transient). A new `x-session-id` per sample, which is what a new install
sends and is not a cache poison — LAT-P089's inert-principal share lets a fresh
session READ the anonymous entry and republish only to its own private key.
Server time (`x-response-time`), because this sandbox's transport floor is
~250 ms against tab loads that can be 15 ms.

Every offset and limit below is a client constant, not one this probe invented:
`DiscoverViewModel.firstPageLimit = 50` and `loadMoreIfNeeded` advancing by the
**server page boundary** (`offset + limit`, not the decoded count), and the web
page's `FEED_PAGE_LIMIT` 20 via `nextFeedRequest(loadedItems.length)`.

```
shape         n   p50 srv       max  cache states
native p1     5      47.0     945.0  {'shared_hit': 3, 'shared_stale_hit': 1, 'miss': 1}
native p2     5     884.0    6665.0  {'miss': 5}
native p3     5     898.0    1592.0  {'miss': 5}
web p1        5      31.0     915.0  {'shared_hit': 3, 'shared_stale_hit': 1, 'miss': 1}
web p2        5    1059.0    1267.0  {'miss': 5}
web p3        5     941.0    1341.0  {'miss': 5}
sports p2     5     992.0    3625.0  {'miss': 5}

HEADLINE  first page p50 39.0 ms  ·  PAGES 2+ p50 941.0 ms
```

Three things in that table and only the first is the headline.

**The ratio is 24×, and the cache-state column is why it is not a fluke.**
`miss` **25 of 25** on every page past the first. Not "usually cold" — never
warm, on any surface, on any sample. Ruling 127's rule cuts the other way here
for once: a p50 over mixed states is a statement about the hit rate, and this
one is over a *pure* state.

🔴 **`native p2` peaked at 6,665 ms, and 6,000 is a hard client deadline.**
`DiscoverViewModel.retryBudget = 6` is non-retryable: past it the native client
gives up and paints whatever it has on disk. The cold-path charter grades that
ceiling on the **max** and not the median precisely because one sample over it
is a user-visible failure. One sample of five went over. That is a scroll that
stops, not a scroll that stutters — and it is the first time this program has
measured the deadline being busted by something other than a first paint.

**The feed is 105 items.** So the whole product is three native pages, two of
which were the expensive ones. This is not a deep-pagination edge case; it is
most of the feed.

## 3. The fix — store the list, slice at serve time

One entry per shape-minus-offset holds the complete post-chain list.
`render_feed_page_from_base` slices it. One build serves every page, **including
the warmer's** — the warmer already produces this list for page 1, so the whole
scroll goes warm at zero extra cost to it.

### 3.1 It is always the anonymous build, structurally

`feed_page_base_cache_key` takes **no `user_id` and no `session_id`** — not
"defaulted to None", absent. There is no argument by which a caller could key a
personalized list into a base. Publishing and reading are gated on

```python
and feed_page_base_enabled()
and not my_teams_only
and ctx == PersonalizationContext()
```

which is **LAT-P089's own equality predicate**, already ratified and already
pinned by `test_feed_inert_principal_share_p089.py`. This queue inherits that
soundness argument rather than inventing a second one: the principal reaches the
build through exactly one value, `ctx`, so a default-constructed context makes
this build byte-identical to the anonymous build of the same shape. Not similar
— equal. A personalized reader fails closed to the build.

`my_teams_only` is refused outright even though a default ctx would already
exclude it. A followed-teams page must never be reachable from a shared list,
and stating that costs one clause.

### 3.2 The three things that are load-bearing and were nearly lost

**The warmer must skip the READ and keep the WRITE.** LAT-P001's rule, one tier
down: a warmer served from any cache republishes the same ageing payload forever
and, from outside, looks exactly like a warmer that works. The base is the tier
the warmer exists to fill, so a warmer served from it would refresh nothing at
all. **The first draft did exactly that and
`test_route_feed_prewarm.py::test_a_stale_entry_serves_requests_but_does_not_satisfy_the_warmer`
caught it** — an existing guard, written for a different tier three months
earlier, red on the first run of the new code. That test is why this section is
two lines of `if` and not a bug.

**The base is stored with the ANONYMOUS TTL, not the builder's.** `_live_ttls`
asks `identified=bool(feed_user or feed_session_id)`, which is a statement about
the READER. But the base is not the reader's entry — it is the anonymous list,
and a fresh session that happens to build it must not stamp its 5 s lifetime on
a 60 s entry. That mistake would have expired the base before the next scroll
and made this whole fix measure as noise. The live ceiling (#2216) still applies
and is derived from the **full** list, so a live card at position 60 shortens the
base even though page 1 cannot see it — the conservative direction.

**The renderer refuses a base whose `total` its items cannot support.** That is
the one failure mode invisible in the served page: fifty correct-looking cards
and a `has_more` computed off a number that is not there, ending the user's
scroll early. Slow is recoverable. Wrong is not. `render_feed_page_from_base`
returns `None` — meaning "build it" — on that and on every other shape it cannot
vouch for.

### 3.3 The scrub

The internal-key strip now runs over `feed_items` rather than `paginated`. That
is a strict superset for the returned page (same dict objects; the response is
byte-identical), and without it a base scrubbed only in its first window would
ship `_rank_score`, `_quality_story_key` and the rest to every reader of page 2
— while `test_response_shape_exposes_public_item_contract`, which only ever sees
page one, stayed green.

### 3.4 Two boring properties that matter

The prefix is `feed_cache:pagebase`, i.e. **under** `FEED_RESPONSE_CACHE_PREFIX`,
so `invalidate_feed_response_cache`'s existing `feed_cache:*` scan already
deletes bases and their stale mirrors. An invalidation that cleared the pages but
left the base would re-serve the pre-invalidation list on the very next scroll.

`FEED_PAGE_BASE=0` is its own lever, not `FEED_INERT_PRINCIPAL_SHARE`'s. The two
share a soundness argument but not a failure mode, and an operator narrowing one
should not have to accept the other.

## 4. Gates

| gate | result |
|---|---|
| `tests/test_feed_page_base_p141.py` (new, 68) | PASS |
| `tests/integration/test_route_feed_page_base_p141.py` (new, 22) | PASS |
| `scripts/lat_p141_mutation_battery.py`, 29 mutants | **29/29 killed**, 0 survived, 0 harness failures, both targets restored SHA-256 identical |
| `scan_mutation_residue.py` | CLEAN — 344 needles, 0 residual mutants |
| `-k feed` (1,321 tests) | PASS |
| `tests/test_startup.py` smoke | PASS |
| full backend suite | see the report |
| frontend build / typecheck / jest | **not run — zero frontend files in the diff** |

### 4.1 The battery found a hole, and the hole was the fixture

`mock_db` answers every query empty, so the built list is `[]` and `total` is 0
— under which *"store the whole list"* and *"store the served page"* are the same
zero items. `M-ROUTE-BASE-STORES-THE-PAGE` survived a green suite for exactly
that reason.

The remedy is `_plant_a_real_list`, which patches
`apply_discover_display_chain` — the last stage before the slice, so the real
pagination, the real scrub, the real key derivation and the real publish all
still run — over 105 items, where a window can differ from the whole. Three
tests came out of it, including the round trip: build page 1, then read page 2
off the base it published and get items 50–99 with no internal keys on them.

**The generalisable sentence: a fixture that returns nothing makes "all of it"
and "some of it" the same assertion, so a suite built on one cannot test a
partition.** Worth a gotcha; parked as P141-4.

### 4.2 Three mutants were silently editing the wrong function

The base key's second and third f-string lines are **byte-identical** to
`feed_response_cache_key`'s. `str.replace` reached the first copy, the mutant
"applied", and it proved nothing about the function under test. The battery now
refuses a non-unique anchor as a HARNESS-FAIL rather than editing whichever copy
it finds first — the same discipline as "a mutation that fails to apply reports
green", one step further in.

## 5. Parked

**P141-1** — **a base hit still parses the whole list.** ~197 KB per read
against ~96 KB for a page hit, so a base serve is roughly two page-hits' worth
of `json.loads` (gotcha #38: that parse holds the GIL). Against 941 ms it is not
close to a trade worth refusing, but it is a real cost and it is not zero.
Republishing the per-offset private key after a base hit (LAT-P089's own
backfill shape) would make the *second* request for the same page cheap; it was
deliberately not done, because it adds a write per page view and the first
request is the one the user feels. Needs a measurement, not an opinion.

**P141-2** — **identified, genuinely-personalized readers still pay per page.**
They are refused by the ctx guard, correctly. Their per-offset TTL is 5 s anyway,
so they re-pay constantly regardless, and a per-principal base would multiply
Redis footprint by the number of principals to fix a case whose cache regime is
already five seconds. A real answer needs the personalized share of feed traffic,
which is a MEASUREMENT-lane question.

**P141-3** — **the 6 s client deadline was busted once in five samples on
`native p2`.** This ship attacks the cause, but the post-deploy status of that
ceiling is UNMEASURED and this doc does not claim it clears. Re-run the probe
after deploy.

**P141-4** — the empty-fixture gotcha of §4.1.

**P141-5** — 🔴 **`/api/oscars` is 10.9 s on every request, `app=9,946 ms`, and
`/api/futures/browse` uncategorised is 1.1–1.6 s of pure db on every request.**
Both were measured this session while ranking. `/api/oscars` has **zero callers**
in `frontend/` or `ios/` and ships nothing if optimised. `/api/futures/browse`
DOES have one — `bainluck.com/search` zero-state → tap a category tile →
`CategoryBrowser.tsx:140` — which corrects P123-1/P124-3's standing
"no identified caller" note; but the reachable call always carries a category
(`category=politics` measures 264 ms), and the 1.6 s uncategorised plan is not
on a path the UI issues. The genuinely user-visible defect there is a different
one: **that in-category search box is undebounced** (`CategoryBrowser.tsx:196` —
`onChange` calls `handleSearch` directly), so every keystroke issues a fresh
uncached `/browse` carrying `%q%`. That is a keystroke path with no cache and no
debounce and it deserves its own cycle.

**P141-6** — the **05:25 category-precompute run died inside `ncaa-basketball`
with `grids: started`**, leaving that grid serving a payload built at 04:28 with
`stale: true` for over an hour. The 06:25 run completed it in 10.3 s, so it is
INTERMITTENT, not standing. `outcome: "started"` with a written `finished_at`
means the task died on a `BaseException` the `except Exception` could not see —
a cancellation or a limit — at t≈93 s against a 300 s `soft_time_limit` and a
180 s pass budget, so neither declared bound explains it. Diagnosis, not a build:
MEASUREMENT lane.

Carried unchanged: **P140-1** (grade `ix_fm_open_category` or drop it — needs
Alex), **P140-2** (the typeahead top-20 is underdetermined), **P140-3**,
**P129-1**…**P129-5**.

## 6. Contamination declared

* `cold_path_snapshot.py --n 6 --with-search`: 36 `/api/feed`, 24 other tab
  endpoints, 6 typeahead (`debug_timing` + origin → 0 trending votes), 6
  `/api/events/search` (origin header sent), 4 `/api/health`. Organic
  `latency-stats` read taken **before** it (ruling 127).
* `lat_p141_pagination_probe.py --n 5`: **35 `/api/feed`**, all always-sampled.
  A second organic `latency-stats` read was taken immediately before it.
* Ranking probes: ~20 single reads of `/api/politics`, `/api/entertainment`,
  `/api/economics`, `/api/calibration`, `/api/futures/browse`,
  `/api/playoffs/*`, `/api/oscars`, `/api/hub/mma`, `/api/leagues/*`, and 4
  `/api/events/search` with `X-Bainluck-Origin: harness`.
* Two reads of `/api/admin/category-precompute/last`. No `db-query` calls this
  cycle.
