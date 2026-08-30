# LAT-P139 — the Search page that was slow once a minute

**Pillar: DISCOVER (Instant Answers, priority #4).**
**Ship: opening Search stops taking eight to eighteen seconds.**

Branch `program/latency-125`, cut from `origin/master` `b7a7bbd0`. Issue #2285's residual,
the half its own closing sentence named and left.

---

## 1. The ranking this came off

The conveyor asks for the highest-impact cold user-visible path with no banked fix. So the
ranking was re-derived rather than inherited: one first touch per BLOCKING first-load request
across every web surface, round-robin, 1.2 s apart, `x-timing-split` server time, production
`b7a7bbd0`, 2026-08-30 ~04:20 UTC. The organic `latency-stats` read was taken FIRST
(ruling 127's protocol) and is in `/tmp/lat125-stats-before.json`: 3 samples in the hour, so
there is no organic distribution to contaminate at this time of night, and the survey is the
only instrument.

| ms (server) | surface | banked? |
|---|---|---|
| **12,782** | **`/api/events/search-suggestions` — the Search zero-state** | ❌ **no fix — this queue** |
| 7,305 | `/api/events/{id}/related-futures` | ✅ LAT-P136 shipped the cache; build cost parked P136-1 |
| 6,180 | `/api/teams/{slug}/prop-families` | ✅ LAT-P138, `program/latency-124`, awaiting integration |
| 4,277 | `/api/tournaments/us-open` | ❌ uncached — one page, 667 KB. Parked P139-1 |
| 2,126 | `/api/feed?limit=30&event_pct=0.35` (`/daily`) | feed cache, shape not pre-warmed |
| 2,064 | `/api/feed?limit=120…` (`/play`) | feed cache, shape not pre-warmed |
| 1,813 | `/api/teams/{slug}` | ❌ uncached. Parked P139-2 |
| 1,085 | `/api/feed/tag-counts` (`/categories`) | ❌ uncached, 2 queries, maxq 1,021 ms. Parked P139-3 |
| 725 | `/api/events/{id}/game-markets` | ✅ LAT-P121 |
| 328 | `/api/feed?tags=["sport:nba"]` | feed cache |
| 209 | `/api/calibration` | 1 h process cache |
| 182 | `/api/events/{id}/history` | see §2 |
| ≤ 120 | every league grid, category page, hub, concept page, trending | warm |

Raw: `/tmp/lat139-survey-r1.json`.

## 2. P138-1 is answered, and the answer is NO

LAT-P138 parked **P138-1**: `/api/events/{id}/history` read 2,424 ms on ONE event, and one
event is not a population (LAT-P128's lesson). That sweep was run first, exactly as parked —
12 events spanning NFL / NCAAF / MLB / WNBA / two soccer leagues / NHL, and scheduled / live /
completed / closed, at `?hours=48`, four interleaved rounds, 48 samples:

```
min 19.7   p50 ~130-200   max 1,725 ms
```

**The chart is not slow.** 2,424 ms was a tail sample. The sweep is not wasted — it produced two
facts worth keeping, both parked below: the p95 is bad and variance-driven (`nfl/scheduled+20d`
read 266 / 1,725 / 163 / 1,358 ms across rounds), and `EXPLAIN (ANALYZE, BUFFERS)` on its odds
query shows why — `ix_odds_snapshots_event_id` has no `captured_at`, so the window predicate is a
FILTER: 1,263 heap tuples read, **1,073 removed by filter**, 1,441 shared blocks read from disk,
**846.8 ms of the 862 ms execution is `Shared I/O Read Time`**. Parked **P139-4**.

Raw: `/tmp/lat139-sweep-r1.json`, `/tmp/lat139-sweep-r234.json`.

## 3. The finding

`GET /api/events/search-suggestions` is what `frontend/app/search/page.tsx:313` calls on mount;
it renders "Loading suggestions…" until it answers. It is the first thing anybody sees after
tapping Search.

LAT-P124 (#2285) gave this route a cache that finally wrote — its `setex` had referenced
`_cache_key` and `_json`, neither of which existed in scope, behind a bare `except Exception:
pass`, so it had never written and there was no read path at all. It also skipped the expensive
sections when the answer window was already full. And it wrote down what it was leaving:

> Until it lands, the cache above is what bounds the reader who arrives when sections 1 and 2
> came up short: **this degrades to slow once a minute, never to wrong.**

This is that once a minute. Production `b7a7bbd0`, `x-timing-split` server time. One read taken
immediately after each idle gap, so every one lands on a just-expired slot:

| read | server | db | maxq |
|---|---|---|---|
| first touch, cold slot | **12,782 ms** | 12,708 | 12,672 |
| +2 s, inside the TTL | 24 ms | 0.0 | 0.0 |
| +4 s / +6 s / +8 s | 15 / 16 / 15 ms | 0.0 | 0.0 |
| after **65 s** idle | **8,338 ms** | 8,282 | 8,191 |
| after **70 s** idle | **13,156 ms** | 13,066 | 12,968 |
| after **75 s** idle | **12,103 ms** | 12,054 | 11,928 |
| after **90 s** idle | **18,387 ms** | 18,344 | 18,253 |
| after **120 s** idle | **17,583 ms** | 17,436 | 17,410 |

🔴 **Five out of five.** That is not a tail; it is the price of arriving one second after the
slot expires, and on a site with no steady traffic that is most people. `db` is 99 % of every
one of those numbers and `maxq` is 99 % of `db` — **one statement**.

Which statement is not re-derived here, because LAT-P124 already measured it with
`EXPLAIN (ANALYZE, BUFFERS)` on production: section 3's
`ORDER BY abs(probability_change_24h) DESC` over `futures_outcomes` — 146,437 shared blocks
(~1.14 GB), 1,808,454 rows removed by filter, an external merge to disk, to keep **five** rows.
The only index that mentions the column, `ix_fo_market_movement`, leads with `market_id`, which
this run re-confirmed against `pg_indexes`.

## 4. Why the obvious fix is not taken

The permanent form is an expression index:

```sql
CREATE INDEX ON futures_outcomes (abs(probability_change_24h) DESC)
WHERE probability_change_24h IS NOT NULL
```

It is DDL, the migration slot is Integrator-owned (ruling 080), and LAT-P124 already REQUESTED
and parked it as **P124-1**. It is still parked and this queue does not take it.

**This queue makes a different claim, and only that one: nobody waits for the build any more.**
The build still costs 8–18 s; a background task pays it. `migration_slot: none`, no DDL.

## 5. The fix

### 5.1 The mirror

`app/utils/search_suggestions_cache.py` — the tier extracted out of the route under ruling 005
(extract-on-touch) and converted to the cache envelope, exactly as `related_futures_cache` was
one queue earlier:

* **Primary 60 s, unchanged, and the SAME production key.** `cache_keys("v1",
  prefix="bainluck:search_suggestions:")` reproduces `bainluck:search_suggestions:v1`, the key
  that is live today. A new name would orphan every warm entry at deploy and put the whole fleet
  on the 13 s build at once.
* **A 24 h mirror, served as a first-class path**, with exactly one rebuild scheduled behind it
  via `_serve_stale_and_refresh` — the primitive both event-page tiers already use.
* **Ceiling 5 × the fresh TTL = 300 s.** Inherited, not chosen: `_STALE_SERVE_CEILING` in
  `routes/events.py` and `STALE_SERVE_CEILING` in `game_markets_cache` are both 5, and a test
  asserts all three are the same number. Past the ceiling the reader BLOCKS and rebuilds, so a
  rebuild failing forever degrades to the old slow behaviour and never to silently serving
  hour-old chips.
* Live entries written by the pre-LAT-P139 writer carry no envelope, so `read_slot` reads them
  as a miss and rebuilds. Clean cutover; a pre-envelope payload can never be served as though it
  had one.

### 5.2 🔴 The countdown stops being baked — the half that makes 5.1 legal

LAT-P124 refused to widen the TTL and wrote down exactly why:

> THE TTL STAYS 60s BECAUSE THE PAYLOAD CARRIES A RENDERED COUNTDOWN. `label` is baked at build
> time — "Tips off in 12 min", "Starts in 2h" — so a mirror older than a minute prints a minute
> count that is wrong. A longer TTL would buy latency with a formatting lie.

**That is correct and it is not argued with.** Serving a mirror is precisely the thing it
forbids, so the constraint is *dissolved* rather than paid for. Section 2 now stores its
DEADLINE (`countdown_from`) and the label is computed at SERVE time by `countdown_label`, from
the serving clock. The same function is called on both sides, so a build and a mirror of that
build cannot print different strings for the same instant. The deadline is stripped on the way
out; the response keeps the keys it has today.

An item whose start has passed is DROPPED rather than re-labelled — a started game is not a
member of the set section 2's query (`commence_time BETWEEN now AND now + 3h`) claims to
describe. And the expiry test reads **seconds**, not the truncated minute count: `int()` rounds
toward zero, so `int(-59/60)` is 0 and a `minutes < 0` guard would print "Tips off in 0 min" for
a whole minute after kickoff — the wrong-clock-text this module exists to prevent, arriving
through the guard meant to prevent it.

### 5.3 What else in the payload can age — enumerated, not assumed

Five sections build the response and **two have never run**: LAT-P124 found, and #2286 records,
that section 1 (live close games) and section 5 (popular championship markets) each name a model
attribute that does not exist and die while their statement is being built.
`TestSectionsThatHaveNeverRun` pins both. So the served content is only ever:

| section | text | ages? |
|---|---|---|
| 2 — starting soon | "Tips off in N min" | **clock-relative — RE-RENDERED** |
| 3 — futures movers | "Surging +4.1% — <market>" | a 24 h statistic whose input refreshes every 10 min |
| 4 — recent upsets | "Pulled the upset vs X" on a finished game | a historical fact |

**There is no clock-relative text left that a 300 s-old mirror can get wrong**, which is the
whole argument for the ceiling.

## 6. Gates

| gate | result |
|---|---|
| `tests/test_startup.py` | **0** — 4 passed |
| `tests/test_search_suggestions_mirror_lat_p139.py` (new, 37 guards) | **0** |
| `tests/integration/test_route_search_suggestions_cold_p124.py` (21, updated) | **0** |
| `scripts/evals/search_suggestions_mirror_mutations.py` (new, 14 mutants) | **0** — 14/14 killed, control green |
| `scripts/evals/search_suggestions_cold_mutations.py` (re-targeted, 12) | **0** — 12/12 killed, `events.py` byte-identical after |
| `scripts/evals/scan_mutation_residue.py` | **0** — CLEAN, 300 needles in place |
| full backend suite | see report §4 |

## 7. What this queue did NOT do

* **The build is not faster.** P124-1 stays parked and stays the fix for that.
* **No warmer.** Serve-stale has no schedule that can silently stop (LAT-P116); the rebuild is
  triggered by the request that would otherwise have paid for it. **`beat_schedule_change:
  FALSE`** — this branch does not touch `BACKGROUND_BEAT_COUNT`, the constant six consecutive
  latency integrations have collided on.
* **Sections 1 and 5 are still dead.** Reviving them changes what a user sees and is a product
  call. #2286 stays open.
* **No in-process L1.** The payload is principal-free and one shared Redis slot serves the
  fleet; a per-worker dict in front of it would be the 30-entry shape LAT-P121 and LAT-P136 both
  had to remove.

## 8. Parked

* **P139-1** — `/api/tournaments/us-open`, 4,277 ms, 667 KB, no cache of any kind. Second on the
  ranking with no banked fix.
* **P139-2** — `/api/teams/{slug}`, 1,813 ms, maxq 908 ms, no cache. Blocks the team page, and
  the grid call is serially dependent on it.
* **P139-3** — `/api/feed/tag-counts`, 1,085 ms in TWO queries (maxq 1,021), no cache. Blocks
  `/categories`.
* **P139-4** — `/api/events/{id}/history`: the p50 is fine and the p95 is not. One event read
  266 / 1,725 / 163 / 1,358 ms across four rounds, and its plan is 85 % of tuples discarded by a
  filter with 847 ms of pure disk I/O. Sized, with the plan, above.
