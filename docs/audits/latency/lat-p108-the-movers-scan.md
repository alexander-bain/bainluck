# LAT-P108 — "Biggest Movers" stops sorting the whole outcome table

date: 2026-08-28
queue: LAT-P108 (cycle 80) · runner directive `runner-inbox/latency/013-coldpath-conveyor.md`,
staged by Fable under Alex's standing authorization for this lane
identity: `LAT-P108-20260828-w18205`
branch: `program/latency-93`, cut from `origin/master` @ `9ae282a7`
issue: filed this cycle — see §7

---

## 0 — the headline metric set (ruling 137), taken before anything was built

Slug `9ae282a7`, uptime 1,662 s, 2026-08-28T20:08:38Z. Equal-weighted cold p50 per
Alex's option-b ruling; `search_trending` produced no cold sample and is absent from
the median, not counted as fast.

| surface | member path | cold n | cold p50 |
|---|---|---:|---:|
| Discover open | `discover_native` | 3/5 | 2,283 ms |
| | `discover_web` | 1/5 | 2,096 ms |
| tab loads | `sports_native` | 3/5 | 1,375 ms |
| | `sports_web` | 1/5 | 1,171 ms |
| | `search_trending` | 0/5 | — |
| | `my_stuff_stats` | 5/5 | 13 ms |
| cold search | `search_cold` | 6/6 | 350 ms |
| Browse | — | — | NO SERVER DEPENDENCY |

**NEEDLE: latency 1273 ms @ 2026-08-28T20:08:38+00:00.** Series **882 → 873 → 940 →
1273**. Raw-pooled cross-check 485 ms over n=19 — the two diverging is the composition
signal, not a speed signal.

🔴 **Nothing was deployed between 940 and 1273.** Both readings are on code the lane
has not changed (`bddb5f3f` then `9ae282a7`, and no latency branch has merged since
LAT-P099). The rise is the four `/api/feed` members: `discover_native` 1,636 → 2,283,
`discover_web` 1,267 → 2,096, `sports_native` 612 → 1,375, `sports_web` 1,771 → 1,171.
Four of the six contributing members are one endpoint, so the needle is currently
mostly a report on `/api/feed`'s cold build — which is the property that made this
cycle look elsewhere for its ship (§1).

---

## 1 — why this cycle did not touch the biggest number

The directive's standing rule while the merge stack is deep: **branch from current
master, never stack on unmerged latency-8x branches.** Six latency branches are
awaiting integration (`-87` … `-91` as a five-deep chain, plus `-92` standalone), and
their union of touched source files is:

```
app/routes/feed.py            app/tasks/__init__.py
app/tasks/precompute_category_pages.py   app/tasks/search_head_warmer.py
app/utils/feed_cache.py       app/utils/principal_independent_cache.py
scripts/measure_live_feed_sawtooth.py    (-92) app/routes/events.py
```

Every member of the needle pool is served by `feed.py` or `events.py`. A cold-path win
inside either would have to be written against master and would collide with work
already gated and waiting. So this cycle did what LAT-P107 did: **found a user-visible
cold path OUTSIDE the graded five and outside every contended file.** The census below
is the search, written down so the next cycle does not repeat it.

🟢 **AND THE CONSTRAINT DISSOLVED MID-SESSION — say so plainly rather than let the next
cycle inherit a rule that has expired.** Between this branch being cut (`9ae282a7`) and
its gates closing, the Integrator drained the **entire five-deep stack**: `-87` … `-91`
are all ancestors of `origin/master` @ **`0e2414cd`**. Only `-92` is still out, and its
nine files are disjoint from this branch's two. **The next cycle should go straight at
`/api/feed`'s cold build** — it is four of the six contributing needle members and
nothing is holding `feed.py` any more. This cycle's route sweep is what a lane does
when the biggest number is fenced off; it should not become the habit once it is not.

### The sweep — 27 public GET routes, two passes each, `/api/health` interleaved

Wall p50, production, 2026-08-28 ~20:1xZ. Control (`/api/health`) 253 ms; the sandbox
transport floor is ~250 ms, so anything at ~250 ms is *at the floor*, not measured.

| route | pass 1 | pass 2 | server time | verdict |
|---|---:|---:|---|---|
| `/api/oscars` | 14,773 | 11,815 | 14,339 / 11,396 ms | **no cache, no consumer** — §6 |
| `/api/futures/browse` | 863 | 15,583 | 580 / 15,299 ms | **no consumer** — §6 |
| `/api/march-madness/mens` | 4,716 | 4,650 | — | **HTTP 500** — §6 |
| `/api/futures/movers` | 6,275 | 253 | 6,054 / 27 ms | **iOS Futures tab — THE SHIP** |
| `/api/leagues/americanfootball_nfl` | 2,102 | 559 | 1,610 / 73 ms | parked |
| `/api/events/faceted` | 802 | 1,748 | 447 / 1,450 ms | parked |
| `/api/feed/tag-counts` | 414 | 360 | — | **HTTP 500** — §6 |
| `/api/events/discover` | 402 | 416 | — | **HTTP 503** — §6 |
| everything else (19 routes) | — | — | ≤ 865 ms | no finding |

`/api/futures/movers` is the only row that is both **slow** and **on a screen a person
opens**: `Views/FuturesListView.swift:51` awaits `viewModel.load()` then
`viewModel.loadMovers()`, and the "Biggest Movers" strip renders above the market list.
`/api/oscars` and `/api/futures/browse` are slower and have no caller — a route with no
consumer is not a ship, and both are parked rather than fixed (§6).

---

## 2 — the finding: one statement, thirteen seconds

Cold request, `?hours=24&limit=10`, the exact shape iOS sends
(`Services/APIClient.swift:875`):

```
x-response-time: 13095ms
x-timing-split: wall=13090.5; db=13041.5; app=49.0; q=1; maxq=13041.5; router=1.9
```

**`q=1`.** One query, 13,041 ms of a 13,090 ms request. Everything else in the endpoint
is 49 ms. Warm (Redis, 60 s TTL): 19–28 ms.

`EXPLAIN (ANALYZE)` on production, the same statement:

```
Limit                                                 11,122 ms
  Gather Merge
    Sort (abs(fo.probability_change_24h) DESC)        10,517 ms
      Hash Join                        rows 62,136 × 2 loops
        Seq Scan futures_outcomes      rows 977,240 × 2 loops    9,799 ms
        Hash
          Index Scan futures_markets   rows 26,365 × 2 loops       121 ms
Execution Time: 11,129 ms
```

`abs()` has no index, and the partial index that exists —
`ix_fo_market_movement (market_id, probability_change_24h) WHERE probability_change_24h
IS NOT NULL` — leads on `market_id`, so it cannot serve a global ordering. The planner
therefore reads **1.95 million outcome rows**, joins down to **124,272**, sorts all of
them, and returns **ten**.

### What was tried and rejected, so it is not tried again

| shape | measured | verdict |
|---|---:|---|
| baseline seq scan | 11,129 ms | — |
| `LATERAL` per-market top-10, two signed arms | 11,044 ms | **no better** — it is I/O bound, not sort bound. The second arm cost 691 ms against the first arm's 6,338 ms for identical work, purely on warm buffers |
| `last_updated >= now() - 1h` | 804 ms | narrows the product, and see §5 |
| `last_updated >= now() - 6h` | 6,458 ms | planner flips back toward a scan |
| `last_updated >= now() - 24h` | 4,541 ms | ditto |
| an expression index on `abs(...)` | — | **DDL. Out of lane** (gotcha #31, ruling 131) |

---

## 3 — the fix: a bound, not a sample

`futures_markets.max_movement_24h` is defined by the task that writes it
(`app.tasks.update_max_movement`, beat `*/10`) as
`MAX(ABS(outcome.probability_change_24h))` over that market's outcomes. So for every
outcome, its market's `max_movement_24h` is **≥ its own |change|**.

Take the top-N markets by `max_movement_24h`; call the smallest value in that pool `v`.
Any outcome whose |change| exceeds `v` sits in a market whose `max_movement_24h`
exceeds `v`, and therefore in a market **already inside the pool**. The pool is a
provable superset of the answer.

This is the third consumer of the column, not a new idea: `routes/feed.py:6542` and
`routes/admin_judgments.py:370` already rank markets by it.

```sql
SELECT fo.* FROM futures_outcomes fo
WHERE fo.probability_change_24h IS NOT NULL
  AND fo.market_id IN (
    SELECT fm.id FROM futures_markets fm
    WHERE fm.status IN ('open','active') AND fm.max_movement_24h IS NOT NULL
    ORDER BY fm.max_movement_24h DESC LIMIT :pool)
ORDER BY abs(fo.probability_change_24h) DESC LIMIT :limit
```

`pool = clamp(limit × 40, 400, 1500)`. The bound is sound at any pool size; the
generous floor buys margin over the ≤10-minute lag of `update_max_movement`.

### Equivalence, proven on production and inside one snapshot

A two-statement comparison of this endpoint is churn, not evidence — prices move
between the two reads, and the first attempt at it produced a spurious disagreement
that took a control run to explain. Each probe below is therefore **one atomic
statement** carrying both arms, executed via `EXPLAIN (ANALYZE)` (the row path's hard
10 s timeout cannot hold the unbounded arm) with the comparison expressed as a
`WHERE`, so *actual rows = 1* means equal and *0* means not equal.

| probe | value vector | id list |
|---|---|---|
| limit 10 / pool 400 | **IDENTICAL** | **IDENTICAL** |
| limit 20 / pool 800 | **IDENTICAL** | **IDENTICAL** |
| limit 100 / pool 1500 | **IDENTICAL** | differs inside a tie group |

The limit-100 id difference is not a regression: the legacy `ORDER BY abs(...) DESC`
carries no tie-break and hundreds of outcomes sit on the same value, so which of them
production returned was already the planner's choice. **The served values are
identical at every limit tested.**

### Measured

| | |
|---|---:|
| baseline, `EXPLAIN ANALYZE` | **11,129 ms** |
| pooled, pool 400 (limit 10, the iOS shape) | **627 ms** — **17.7×** |
| pooled, pool 800 (limit 20, the default) | 427 ms |
| pooled, pool 1000 | 1,138 ms |
| pooled, pool 2500 | 2,833 ms |

### Two bounds that were not there before

- **`limit` was unbounded.** `?limit=99999` sorted the whole table and minted its own
  Redis key. It is now clamped to 100 — clamped *before* the cache key, which is a
  gated assertion, not a comment.
- **The legacy arm survives as `FUTURES_MOVERS_POOLED=0`**, so the rollback needs no
  deploy — and it is also the oracle the equivalence gate drives both paths through, so
  it is not a dead branch maintained on faith.

---

## 4 — gates

- **Full backend suite: see the READY token** — one run, on this exact code tree, exit
  code read by VALUE (gotcha #54).

  🔴 **The first full run on this branch was RED — 1 failed, 20,646 passed, exit code
  1, 839 s — and the failure was mine.** It is recorded here rather than replaced by
  the green, because a report that shows only the second run is a report about a
  different tree. `test_read_side_consumers_are_exactly_the_audited_set` (#2024's
  census) reported `app/routes/futures.py` as an unaudited new consumer of the futures
  poll stamp. **It is not one** — this branch compares `last_updated` nowhere; it
  removed the only draft that did. What the census matched was the *comment* explaining
  why a freshness filter had been refused, which wrote the refused comparison out
  literally. `_GATE.search(_read(f))` reads raw source, so prose counts.

  The comment was reworded. Adding `futures.py` to `READ_SIDE_CONSUMERS` was the
  tempting fix and would have been wrong — that list is documented as *"not a list to
  keep current; a list whose growth is the finding"*, so growing it with a false
  positive blunts the one signal it exists to give. #2024's guard belongs to another
  queue and was not edited; the shape is noted on the issue instead.

  ⚠️ Also recorded: an *earlier* run was **killed by this window at 29 s** (exit 144)
  so `black` could be applied to the new test file without editing source under a live
  pytest — `inspect.getsource` re-reads from disk and the run would have produced
  phantom failures. That kill is not a gate result and is not quoted as one. **Two
  non-verdicts and one real red precede the green below; none of them is hidden by it.**
- `tests/test_futures_movers_pool_bound.py` — **36 passed**, exit 0. NEW file.
- `python3 -c "from app.main import app"` — OK.
- **ruff: zero new, one pre-existing REMOVED.** `origin/master`'s copy of `futures.py`
  reports 2 (`F841 now` unused, `F401 Team` unused); this branch's copy reports 1 — the
  rewrite deleted the dead `now` local. New test file clean.
- **black**: the new test file is formatted. `futures.py` is **deliberately not
  black-formatted** — `origin/master`'s copy is already not black-clean, so running it
  would emit a large unrelated reformat (the same call LAT-P107 made and recorded).

### RED-FIRST — nine mutations, each applied alone, every one caught

Each from a `cp` pristine backup, restore verified by **both** `filecmp` and sha256
before the next; the harness **refuses** a pattern matching other than exactly once, so
a no-op cannot read as a pass.

| | mutation | result |
|---|---|---|
| M1 | pool ordered ASC — the wrong markets become the pool | RED (1 fail) — **load-bearing; the only one a user would see directly** |
| M2 | pool drops the status filter — closed markets leak in | RED |
| M3 | pool drops `max_movement_24h IS NOT NULL` | RED |
| M4 | pool size ignores `limit` | RED |
| M5 | the clamp stops clamping | RED |
| M6 | the outcome-level `IS NOT NULL` is dropped | RED |
| M7 | the route clamps AFTER minting the cache key | RED |
| M8 | the fast path ships OFF | RED |
| M9 | the route silently uses the legacy scan | RED |

🔴 **M3 and M6 were GREEN on the first pass, and the reason is worth carrying.**
SQLite sorts NULLs **last** under `ORDER BY ... DESC`; **Postgres sorts them first.**
So dropping either `IS NOT NULL` is invisible to every in-memory test in the file, and
in production would put NULL-change rows at the top of Movers (M6) or fill the whole
pool with the ~20,200 open markets that have never recorded a mover, emptying the strip
(M3). Both are now pinned by **shape** assertions with that reason written into the
docstring. **The behavioural test was not weaker than the shape test by accident — it
was weaker in the one direction the dialect hides, and only a mutation found it.**

---

## 5 — what this deliberately does NOT fix, and why doing it here would be wrong

The list production served on 2026-08-28 was ten rows, every one of them
`probability_change_24h = -0.98` collapsing to `current_probability = 0.01`, and
**three of them were last written on 2026-07-24** — thirty-five days of "24-hour
change" (`Akshay Bhatia`, `Wyndham Clark`, `Collin Morikawa`, all in *Golfers to
compete in PGA TOUR Championship this year*).

A read-side `last_updated >= now() - 24h` filter looks like the fix. It is **not
compatible with the bound in §3**, and this was measured rather than assumed:
`max_movement_24h` is computed over *all* of a market's outcomes including stale ones,
so ranking the pool by an unfiltered statistic while filtering the answer by freshness
breaks the superset guarantee. At limit 20 / pool 800 the pooled and unbounded arms
disagreed on the **value vector**, not merely on ties.

It is also the wrong layer. Nothing ever clears `probability_change_24h` on a row that
stops being written, so the same stale delta is visible to `max_movement_24h` itself,
to `feed.py`'s mover-ranked pools, to `admin_judgments`, and to the >15pp push-alert
path (`tasks/push_notifications.py:96`). **Parked as an upstream data bug**, with the
evidence, in `PARKED-MEASUREMENTS.md`.

---

## 6 — parked, not dropped (all in `PARKED-MEASUREMENTS.md`)

- **P108-1** — the stale-delta class above.
- **P108-2** — `/api/oscars`: 14,339 ms and 11,396 ms server time on two consecutive
  passes, **no cache at all**, and no consumer found in `frontend/` or `ios/`. Slower
  than the ship and not a ship, because nobody is waiting on it.
- **P108-3** — `/api/futures/browse`: 15,299 ms cold / 580 ms warm; `getFuturesBrowse`
  is defined in `lib/api.ts:1443` and called from no page.
- **P108-4** — three broken public routes found by the sweep and not diagnosed here:
  `/api/march-madness/mens` **500** (both passes), `/api/feed/tag-counts` **500**,
  `/api/events/discover` **503**.
- **P108-5** — `hours` on `/api/futures/movers` is a **no-op**. The column is fixed at
  24 h; `hours` reaches only the response echo and the cache key, so `?hours=1` and
  `?hours=24` return the same list from two different Redis entries.
- **P108-6** — `/api/leagues/americanfootball_nfl` 1,610 ms cold / 73 ms warm, and
  `/api/events/faceted` 1,450 / 447 ms. Real, second-order, not this session's ship.
- **P108-7** — #2024's read-side census greps raw source, so a **comment** naming the
  stamp comparison registers as a consumer. Cost one 14-minute suite run to find.
  Noted on #2024; not fixed here, because it is another queue's guard.

---

## 7 — issues

Filed/commented this cycle: see the READY token. Nothing closed — closure needs
measured production evidence after deploy, and this branch has not deployed.

## 8 — owed after deploy, pre-registered and unrun

Compare against the slug named in each line, not against "before".

1. Re-run `/api/futures/movers?hours=24&limit=10` **cold** (Redis key absent — the TTL
   is 60 s, so a read spaced past a minute from any other is cold), 3 passes, past the
   5-minute post-deploy window. Baseline **13,095 ms** on `9ae282a7`. A cold pass still
   in double-digit seconds means the pooled query did not take and the report is wrong.
2. Confirm `x-timing-split` reports `q=1` still, and `db` under ~1,000 ms.
3. Payload comparison against the capture taken before the deploy: the served
   `probability_change_24h` **value vector** must be unchanged for `limit=10`. Ids may
   differ inside a tie group and that is not a regression (§3).
4. `?limit=99999` returns at most 100 movers and does not take double-digit seconds.
5. Next needle reading continues the series **882 → 873 → 940 → 1273 → …**, taken with
   a real gap after any other run — the instrument warms what it measures.

---

## 9 — the closing needle REFUSED, twice, and that is the cycle's second finding

Both closing reads were taken on slug **`0e2414cd`** — the slug that appeared when the
Integrator drained the five-deep stack mid-session — past the post-deploy window
(uptime 811 s, then 1,696 s), 26 minutes apart, at the canonical depth.

| run | cold members | cold surfaces | verdict |
|---|---|---|---|
| `LAT-P108-close` 21:16Z | **1 of 7** (`my_stuff_stats` only) | 1 of 3 | REFUSED — all three floors fired |
| `LAT-P108-close-r2` 21:47Z | **2 of 7** (`+ search_cold` 684.5 ms) | 2 of 3 | REFUSED — `MIN_COLD_MEMBERS`, `MIN_SURFACES` |

**All four `/api/feed` members produced ZERO cold samples on both runs.** Without the
floors LAT-P107 added, the first run would have published **`NEEDLE: latency 14 ms`**
— a 99 % "improvement" over 1,273, from a median over one 14 ms endpoint. That is the
exact failure mode Alex's option-b ruling was reasoning about, and the floors are the
reason it is a refusal instead of a headline. **The instrument working is the report.**

### Why, evidenced rather than guessed

Three fresh-principal `/api/feed` requests, immediately after the second refusal:

```
x-feed-cache: shared_stale_hit   x-response-time: 65ms
x-feed-cache: shared_stale_hit   x-response-time: 53ms
x-feed-cache: shared_hit         x-response-time: 74ms
```

A brand-new session — which is what a new install sends, and what `cold_path_snapshot`
uses to define a first load — is now served by the **shared** build. That is LAT-P103's
cross-worker shared build and LAT-P101's `prewarm-live-feed-shapes` (40 s, realtime
queue) doing precisely what they shipped to do. It reached production during this
session.

**This is good for users and it breaks the instrument's definition of cold.** Ruling
137 says a first load is "the request a tab issues when a person opens it on an install
the server has never served"; on `0e2414cd` that request is a cache hit, so the four
feed members can no longer contribute to a cold p50 by this method. Whether the needle
should follow the definition (and read ~60 ms, because that genuinely is what a new
install now waits) or keep measuring the build behind it is **not a call this lane
makes** — it is an amendment to the statistic Alex ruled on. Raised in `YOUR-TURN.md`.

⚠️ Also visible above and not chased here: two of three fresh sessions got
`shared_stale_hit`, which is LAT-P093's parked **P093-2** still live.

---

**NEEDLE: latency 1273 ms @ 2026-08-28T20:08:38+00:00** (this session's opening read,
slug `9ae282a7`). Series **882 → 873 → 940 → 1273**. **The closing read REFUSED twice
on slug `0e2414cd`** — 1/7 then 2/7 cold members against a floor of 4 — so no closing
point is added to the series, and 1,273 is not restated as if it were one.

---

## Appendix — gates, verbatim

```
full suite      20647 passed, 112 skipped, 61 xfailed, 0 failed   EXIT CODE: 0   845.48s
                code tree cd460ba6 (HEAD ded8ab1e)
prior run       20646 passed, 1 failed                            EXIT CODE: 1   839.09s
                code tree 124d8d82 — the #2024 census false positive, §4
new gate        36 passed                                          EXIT CODE: 0
startup         from app.main import app                           OK
ruff futures.py 2 errors on origin/master, 1 on this branch — zero new
ruff new test   All checks passed
black new test  formatted;  futures.py deliberately untouched (master is not black-clean)
red-first       9 mutations, 9 caught, 0 refused, restore verified by filecmp + sha256
```
