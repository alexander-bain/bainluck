# LAT-P131 — the nine grids nobody warmed, and the one that cannot be built

**Date:** 2026-08-29 · **Branch:** `program/latency-117` · **Cut from:** current master `387979c3`
**Pillar:** DISCOVER · **Discharges:** P128-2
**Ship:** landing on the NFL, NCAA football, MLS, EPL, Bundesliga or WNBA grid stops erroring or
stalling — every league that can be built is served from a warm key like MLB's.

---

## The defect

`GRID_WARM_LEAGUES = ["mlb", "nba", "nhl", "golf"]`. Fourteen leagues have a grid config. **Nine of
the other ten were never warmed by anything.**

Their pages were not broken, which is why this survived: they worked for as long as some earlier
visitor's own rebuild survived in Redis. `get_playoff_grid_cached` keeps a fresh key for 3900 s and
a labelled `:stale` mirror for 24 h, and a fresh-miss serves the mirror **without triggering a
rebuild**. So the page is fast right up until nobody has visited for a day, and then the next
visitor builds the whole grid themselves, on a route whose wall is 25 s.

Measured on production 2026-08-29, cold on the ordinary cache-eligible path — these three leagues
had genuinely lapsed both keys when the sweep ran:

| league | cold build | outcome |
|---|---|---|
| ncaa-football | **12.45 s** | 200, 40 teams |
| ncaa-women-basketball | **7.83 s** | 200, **0 teams** |
| wnba | **6.83 s** | 200, 13 teams |

The other five were served from a live key at 0.23–0.39 s with `q=0`, which is the point: *warm is
not the same as warmed*. Nothing kept them that way.

## NFL straddles the wall, and it is a week from its season

Forcing the rebuild path on NFL three times in a row:

| attempt | result |
|---|---|
| `?top=11` | **25.30 s → 503** (`unfinished=1`) |
| `?top=12` | 8.65 s → 200 |
| `?top=13` | 14.02 s → 200 |

and two earlier attempts (`?hours=168`, `?top=11`) returned **HTTP 500 at 20.3 s each**. 🔴 **20.3 s
is not the route's 25 s wall.** That is the database's own `statement_timeout` surfacing as
`QueryCanceledError` → `DBAPIError` → an unhandled 500. Sentry carries the matching
`QueryCanceledError` group. So the NFL grid has **two** failure modes above the wall and one below
it, and which one a user gets depends on how warm `shared_buffers` happen to be — the P130 shape
again, where the first probe pays for the later one.

**The warm beat is not a nicety for these leagues, it is the thing that makes them work.** It builds
under `GRID_WARM_TIMEOUT_S = 120`, **five times the request's 25 s**, so the background job absorbs
the variance that the request path can only report as a 500 or a 503. That is exactly what #901
already bought golf and what LAT-P130 re-proved: the page usually works because a background job
with five times the budget pays for it.

## Why P128 refused to just lengthen the list, and what had to come with it

LAT-P128 parked this rather than folding it in, with the reason stated: *"Widening
`GRID_WARM_LEAGUES` is a warm-beat budget decision (`GRID_WARM_TIMEOUT_S = 120` per league, serial)
with its own user-visible ship. A queue does not get to make another surface's call by lengthening a
list."* It was right, and here is the arithmetic behind it.

`precompute_category_pages` is declared `soft_time_limit=300, time_limit=360`. The grid loop had a
**per-league** ceiling and **no pass bound at all**, so its worst case was `120 × N`:

* at N=4 — 480 s, already over the soft limit, latent only because none of the four ever hit the
  ceiling (measured 2026-08-29T17:26:25Z: mlb 53.4, nhl 19.6, golf 17.9, nba 12.4 = **103.5 s**);
* at N=13 — **1,560 s** inside a 300 s task. `time_limit=360` is a SIGKILL, and a SIGKILL is not a
  slow run, it is an untracked death.

So the widening ships with two properties, and neither is decoration:

**1. One pass budget.** `GRID_WARM_PASS_BUDGET_S = 180.0`, sized from measurement rather than taste:
the same production report shows the five non-grid sections costing **49.5 s** (politics 17.3,
entertainment 10.6, economics 11.3, weather 8.8, golf 1.5), so `49.5 + 180 = 229.5 s worst case
against a 300 s soft limit`, and the *typical* pass is ~131 s of measured build, not 180.

Allocation is `_prewarm_target_deadline` — the helper LAT-P100 already put in this file — dividing
what is **left** by what is **left to do**, so gotcha #34 cannot bite: every league is guaranteed at
least `budget / N` = 13.8 s in every order, and a league that finishes early hands its unspent time
to the ones behind it. A league the budget never reached records **`budget_exhausted`**, not
`timeout` and not `not_attempted` — #1484's entire point was that "never reached" and "tried and
failed" must not look alike from the outside, and adding nine leagues to a bounded pass is precisely
the change that makes the distinction load-bearing.

🔴 **The ordering is an optimisation; the budget is the invariant.** The list is ordered by measured
build cost, ascending, so the cheap head leaves the expensive tail slack it did not spend — mlb,
last, is offered ~102 s against a measured 53.4 s. But the floor holds in *every* order, which is
what the guard executes. Costs rot; the per-league `duration_s` in the run report is the instrument
for re-deriving the order, not a re-read of the comment.

**2. An empty build never overwrites a good grid.** The publish now asks
`_grid_payload_usable` — **the route's own read-side predicate** — whether what it built is worth
storing. This matters because the writer sets *both* keys including the 24 h `:stale` mirror:
publishing a transiently-empty build would replace a working grid with one the reader then refuses
as a fallback, turning a healthy page into a live rebuild — and for NFL a live rebuild is the 503.
Not hypothetical: **three leagues build empty today out of season** (la-liga, champions-league,
ncaa-women-basketball — all 0 teams / 0 columns when measured), so this is the ordinary case for a
widened list. Reusing the reader's predicate rather than writing a second one is the whole point: a
private `len(teams) > 0` in the writer would publish an error envelope that the reader then refuses,
and the two disagreeing *is* the bug.

## The league that is deliberately not warmed, and why that is the finding

🔴 **`ncaa-basketball` is absent from the widened list on purpose.** It is the one league that
cannot be built at all:

* `?top=11` → **25.36 s to `unfinished=1`**, and 🔴 **17.87 s of that is `app`, not `db`** — a
  Python-side cost (68 teams plus the NCAA bracket filtering), so it is not the query shape the last
  three cycles have been fixing;
* Sentry carries **7** of its `"timed out and no last-good payload is available"` 503s in the
  preceding 24 h, plus the matching statement-timeout group.

Warming it would spend up to the whole per-league ceiling every hour to publish nothing, and under a
shared budget it would spend the tail's time doing it. Its 503 is a real user-visible defect with
its own ship — parked **P131-1**. **A warm list is not the place to hide a page that does not
build.**

## The measurement, and the instrument that had to be corrected first

The per-league costs above come from `/api/playoffs/{slug}?top=11`. That is deliberate:
`cache_eligible = not debug and hours is None and top == 10`, so `top=11` is cache-**ineligible**
and forces the rebuild, while `trend_hours = hours or config.trend_hours` means the build is
**exactly the one the warm beat asks for**.

🔴 **The first sweep used `?hours=168` and those numbers were discarded.** `hours=168` also bypasses
the cache — but it *overrides the league's own trend window*, so it builds a different grid. It is a
cache-bypass, not a warm-beat proxy, and quoting it would have sized the budget against work the
beat never does. The two instruments disagree by more than 3× on EPL (4.06 s vs 1.19 s).

Both readings are also **warm-buffer** readings, taken after earlier probes had already dragged the
pages into `shared_buffers`. Said plainly rather than buried: they are lower bounds on a genuinely
cold build, which is the conservative direction for a budget only in the sense that the *typical*
pass will be larger than 131 s — the 180 s bound is what protects the task either way, and that is
the reason the design leans on a bound instead of on a cost estimate.

## The guards assert shape and bounds, because widening a list cannot fail visibly

Every league still returns the right grid after every regression in this class, so a results test
passes against all of them. What breaks is invisible from the payload: the pass overrunning its
host, the tail starving, an empty build clobbering last-good. **16 tests**
(`tests/test_precompute_grids_budget.py`), including:

* a **landmine** on the warm list derived from `get_all_league_slugs()`, so shrinking it back FAILS
  rather than getting slower — and a *new* league config nobody triaged also fails, which forces the
  decision instead of defaulting it;
* the **second door**: compute `deadline_s`, write it into the report, and hand `asyncio.wait_for`
  the old 120 s ceiling anyway. That version is bounded by nothing and looks entirely correct in the
  report, so the test asserts the value that reached the timeout, not the value that was written
  down;
* gotcha #34's floor **executed**, not argued — the allocation replayed against the pathological
  profile where every league spends its whole share;
* the `finally` that charges the budget on failure, because the expensive failure is the one debt a
  budget must never miss;
* `budget_exhausted` ≠ `timeout` ≠ `not_attempted`;
* the empty guard, the error-envelope case a naive `len(teams) > 0` would publish, and the proof
  that a good build still writes **both** keys at 3600 s / 86400 s;
* the warm arguments pinned against `cache_eligible` — warm with `hours=24` and the beat populates a
  key no request ever reads, the grid stays cold, and the report says `ok`. That is LAT-P128's class
  one layer down.

🔴 **Two of those tests failed on their first draft, and both failures were the test being wrong
about the code — worth recording, because each was the design working.** The `budget_exhausted` test
starved the pass with one hog and expected the tail to be skipped; it never was, because fair-share
allocation means **a single hog cannot consume the pass**. And the charge-on-failure test slept
longer than its own share, so it timed out before it could raise and tested the wrong branch.

**Mutation battery** (`scripts/lat_p131_mutation_battery.py`): **13/13 killed, 0 survived, 0 harness
failures, exit 0**, restore SHA-256 identical, both suites run per mutant so a mutant cannot satisfy
the new file by breaking #901's.

## Not this queue

* **P131-1** — `/api/playoffs/ncaa-basketball` 503s on rebuild; **17.9 s of the 25 s is `app`, not
  `db`**, so it is not the query shape. 7 Sentry 503s in 24 h. Its own ship.
* **P131-2** — the NFL rebuild's **HTTP 500 at 20.3 s** is a `statement_timeout` reaching the client
  unhandled. The warm beat now hides it from most users; it is still a 500 on a public route and the
  route should degrade like the wall does.
* **P131-3** — la-liga and champions-league build **0 teams** in 0.4–0.6 s. P129-2 already names the
  cause for la-liga (`_league_pattern_to_ilike` kills 33 of 51 name patterns; la-liga is 3/3). A
  content ship, not a latency one — but the empty guard means the beat will start publishing them
  the moment they build.
* **P131-4** — `GRID_WARM_LEAGUES` is now thirteen serial builds. Nothing here parallelises them;
  the budget makes that safe to consider, and the report's `duration_s` per league is the evidence
  for whether it is worth it.
