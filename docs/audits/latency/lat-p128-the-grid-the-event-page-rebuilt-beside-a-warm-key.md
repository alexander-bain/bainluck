# LAT-P128 — the grid the event page rebuilt while the same grid sat warm in Redis

**Pillar: DISCOVER.**
**Ships: tapping an event from Discover stops taking twenty to twenty-nine seconds
before the page has its data** — the wait was a championship-progression grid being
rebuilt inline, one that another surface was serving from Redis in 21 ms at the same
moment.

Branch `program/latency-114`, cut from CURRENT master `d9b76e9b`. Not stacked on
`-108`/`-109`/`-110`/`-111`/`-112`/`-113` (all unmerged), per the inbox directive.
`migration_slot: none`, `beat_schedule_change: FALSE`, no config var, no DDL,
backend only, 5 files, **zero frontend files**.

---

## 1. The item was handed over, and the caller grep ran first

LAT-P127 parked `/api/events/{id}/related-futures` as **P127-2** — "19.85 s cold →
0.42 s warm, a WARMER defect, own cycle". It was the head of the parked list that was
neither BLOCKED (P127-1 waits on `-109`) nor NEEDS-ALEX (P127-3).

P127's own lesson ran first, because it is the cheaper of the two checks: **gotcha #155
answers "will this collide?", not "does anyone wait on this?"** The caller grep found
two real callers, so the endpoint is not another `/api/market-moves`:

| caller | surface |
|---|---|
| `frontend/components/RelatedFutures.tsx` via `fetchRelatedFutures` | `/events/[id]` — the web event detail page |
| `ios/.../ViewModels/EventDetailViewModel.swift` | the native event detail screen |

Event pages with props as the story are product priority #3. This is a first-class
surface on both platforms.

---

## 2. The first hypothesis was wrong, and killing it is the reusable part

The endpoint's `x-timing-split` said the cost was **DB, not app**:

```
14970280  wall=17529.2;db=17453.0;app=76.2;q=23;maxq=11817.8;router=1.8
```

`db` is 99.6 % of `wall`, and **one query is 11.8 s of it**. So: find the query.

Reading the handler, the obvious suspect was step 7 — a liquidity signal built by
counting distinct bookmakers per outcome over `futures_odds_snapshots`, the same
million-row table LAT-P127 had just found 189,312 rows of behind one market. An
`EXPLAIN ANALYZE` on production made it look like a certainty:

```
Aggregate (Sorted)  actual_time=3477.573  rows=1000
  -> Index Only Scan  ix_fos_outcome_bookmaker  actual_rows=1,221,798
```

**1.22 million index entries read to produce 1,000 small integers.** It even had a
clean fix: the index is `(outcome_id, bookmaker)`, so a loose index scan gets the same
answer by skipping. Measured, chunked, on production, over the same 1,000 outcome ids:

| form | time | result |
|---|---|---|
| `count(DISTINCT bookmaker) GROUP BY outcome_id` | **3,795.7 ms** | 1,000 rows |
| recursive-CTE skip scan | **173.5 ms** | 1,000 rows |
| | | **byte-identical, 0 diffs** |

A 21.9× win, proven equivalent. And it is **not this ship**, because the next step was
to check the hypothesis instead of the fix.

Reconstructing the handler's ACTUAL outcome set for event 14970280 — the season market
discovery, the two teams' name patterns, the market-name subquery — returned **12
outcomes over 9,193 snapshot rows**, and the bookmaker query on exactly that set ran in
**28.3 ms**. Not 11.8 seconds. Not close.

> **A query that is expensive in general is not thereby the expensive query in this
> request.** The plan said 1.22 M rows because the *probe* handed it 1,000 outcome ids;
> the route hands it twelve. The reconstruction cost four db-query round-trips and it
> is the only reason this cycle did not ship a real, correct, 21.9× optimisation of
> something nobody was waiting on. **Size the query on the request's own inputs before
> you believe a plan.**

The skip-scan rewrite is parked as **P128-1**, with its evidence, because it is still a
real defect — just one that needs an event whose outcome set is large enough to matter.

---

## 3. The real defect: two functions, one letter of difference, one of them has the cache

`get_related_futures` ends by attaching `league_context` — the championship-progression
grid for the event's league, which feeds the Playoff Path card:

```python
# app/services/league_context.py
from app.routes.playoffs import get_playoff_grid          # <- the RAW builder
grid_data = await get_playoff_grid(
    league_slug=league_slug, hours=None, top=10, debug=False, db=db,
)
```

`app/routes/playoffs.py` exports two functions:

* **`get_playoff_grid`** — the builder. Nine DB queries, `SET LOCAL statement_timeout =
  '20s'`, no cache of any kind.
* **`get_playoff_grid_cached`** — the route. Reads
  `bainluck:category:playoffs:{slug}`, falls back to a labelled 24 h `:stale` copy,
  bounds the rebuild at 25 s, and **writes both keys** on a live rebuild. It has had a
  3900 s TTL since #901.

The event page called the first one. Every miss of `league_context`'s own **300-second**
Redis key paid a full inline grid rebuild.

**The parameters were cache-eligible the whole time.** The wrapper caches when
`not debug and hours is None and top == 10`, and this call has always passed exactly
that triple. Nothing had to be made cacheable. The caller just had to ask the function
that reads the cache.

### 3.1 The transcript that settles it

One sequence, `2026-08-29T14:56:57Z`, three requests back to back against production:

```
1) GET /api/playoffs/bundesliga                200  0.356 s  wall=20.7    db=0.0      q=0
2) GET /api/events/14970280/related-futures    200 21.678 s  wall=21418.0 db=21339.7  q=23  maxq=13554.5
3) GET /api/playoffs/bundesliga                200  0.329 s  wall=22.2    db=0.0      q=0
4) GET /health                          (control)  0.241 s
```

**The key was warm on both sides of the twenty-one-second read.** The grid page served
it in 21 ms with zero DB queries at 14:56:57, the event page rebuilt the same grid from
scratch two seconds later, and the grid page served it in 22 ms again immediately
after. No hypothesis is required to read that transcript.

### 3.2 Three independent confirmations

**(a) The A/B on `league_context`'s own key.** Two events in the SAME league, two
seconds apart, with nothing changing but whether `bainluck:league_context:bundesliga`
was warm:

```
14970283  league_context COLD   28.667 s   wall=28396.9  db=28286.6  q=23  maxq=16387.5
14970280  league_context WARM    2.170 s   wall=1913.0   db=1870.6   q=14  maxq=1155.9
/health   control                0.262 s
```

**(b) The query count is exact.** Cold `q=23`, warm `q=14`, difference **9**. A grid
rebuild measured on its own endpoint is **`q=9`**. The nine extra queries are the grid,
not a coincidence of arithmetic.

**(c) It reproduces across leagues and sessions.** `15290740` (EPL) read 19.414 s cold
and 0.335 / 0.346 s warm; `14970280` read 17.807 s, 21.678 s and 2.170 s depending only
on the state of that one Redis key. The `/health` control held at 0.241–0.263 s
throughout.

---

## 4. The fix

One import and one call:

```python
from app.routes.playoffs import get_playoff_grid_cached
grid_data = await get_playoff_grid_cached(
    league_slug=league_slug, hours=None, top=10, debug=False, db=db,
)
```

**The wrapper is strictly safer here, not merely faster.** It adds the 25 s wall and the
labelled last-good fallback this path never had, and on a genuine miss it REFILLS the
shared key — so an event page can no longer rebuild a grid and throw the result away.

The one behaviour that had to be handled rather than noticed later: the wrapper answers
a timeout-with-no-last-good with `HTTPException(503)`, where the raw builder returned.
That 503 is the honest answer for the grid PAGE and the wrong answer for an event page.
`_compute_league_context`'s `except Exception` already catches it — `HTTPException`
subclasses `Exception` — so it degrades to `league_context: null`, the same shape a
caller already gets when a league has no grid data. That `except` is now load-bearing
and says so in the source, and `M-SWALLOW` in the mutation battery narrows it to prove
the point.

---

## 5. What the fix is worth, stated honestly in both halves

`GRID_WARM_LEAGUES = ["mlb", "nba", "nhl", "golf"]`. The hourly warm beat covers four
leagues, not all of them, so the payoff splits:

| leagues | before | after |
|---|---|---|
| **mlb, nba, nhl, golf** | a full grid rebuild on every 300 s `league_context` miss | a Redis GET against a key the warm beat keeps populated — the 21 ms / `q=0` read in §3.1 |
| **everything else** (epl, bundesliga, la-liga, champions-league, mls, …) | a full grid rebuild every 300 s, **per surface** | one rebuild per 3900 s, **shared with the grid page**, plus a 24 h labelled `:stale` fallback and a 25 s wall |

For the unwarmed leagues that is a **13× reduction in rebuild frequency**, not an
elimination — and the reduction is compounded by the two surfaces now sharing one key
instead of each paying separately. Quoting only the warmed-league number would be
quoting the flattering half.

The soccer grids being unwarmed is itself a finding, and it is parked (**P128-2**), not
folded in: `/api/playoffs/bundesliga` and `/api/playoffs/epl` both took **22.5 s / 22.1 s
cold** (`q=9`, `db` 99.7 %) on their own endpoint. That is a grid-page defect with its
own ship and its own decision about `GRID_WARM_LEAGUES`, and this queue does not get to
make it by widening a list.

---

## 6. The trap this defect was hiding in, and why it gets a guard

The broken call **looked correct**. Both functions are in the same module, take the same
arguments, return the same shape, and have names that differ by one suffix. Nothing in
`league_context.py` was wrong to read. A reviewer would have to already know which of
the two owns the Redis key.

That is why the guard suite asserts WIRING rather than latency
(`backend/tests/test_league_context_grid_cache_lat_p128.py`, 8 tests):

* **`test_warm_grid_key_does_not_rebuild`** — the load-bearing one. The raw builder is
  replaced with a landmine that raises. Re-point the call at it and the test does not
  get slower, it fails.
* **`test_call_is_cache_eligible`** — pins the `hours is None / top == 10 / not debug`
  triple at the call boundary. **The defect has a second door.** A later edit passing
  `hours=24` would leave the import correct and every other test green while silently
  bypassing the cache. Three mutants attack exactly that door.
* **`test_json_roundtrip_context_matches_live_context`** — gotcha #1587's class, one
  layer up. The wrapper stores `json.dumps(result, default=str)`, so a warm read hands
  `_compute_league_context` JSON types and a cold read hands it live Python objects.
  The test builds a context from a live grid, reads back **exactly what the wrapper
  persisted on that pass**, builds a second context from it, and compares the two
  (minus `last_computed`, the one field that legitimately differs).
* **`test_warm_key_read_twice_is_stable`** — `_compute_league_context` extends
  `grid_data["teams"]` in place on the grouped-teams path. Harmless when every payload
  is freshly parsed, and invisible from a single call. Pinned before it stops being
  harmless.
* **`test_503_from_wrapper_degrades_to_none`**, **`test_degraded_last_good_still_builds_a_context`**,
  **`test_unknown_league_never_touches_the_grid`**, **`test_cold_key_refills_the_shared_grid_cache`**.

### Mutation battery — 8/8 killed, exit 0

`backend/scripts/evals/league_context_grid_cache_mutations.py`:

```
denominator: 8 mutants queued against league_context.py
baseline: suite GREEN on the unmutated tree

M-RAW       killed   alias the RAW builder over the cached name — the defect itself, restored
M-HOURS     killed   pass hours=24 — import stays right, cache_eligible goes false
M-TOP       killed   pass top=25 — same silent bypass through the argument list
M-DEBUG     killed   pass debug=True — the third term of cache_eligible
M-SWALLOW   killed   narrow the except — the wrapper's 503 escapes into the event page
M-TREND     killed   write the probability into changes_24h — warm and cold both wrong
M-PROB      killed   invert the stage probability guard — every cell drops out
M-NORM      killed   skip name normalisation — the teams dict keys stop being lookup-able

8/8 killed, 0 survived, 0 harness failures
```

`M-RAW` is the honest restoration of the bug: it aliases `get_playoff_grid` over the
cached name, leaving the call site untouched, so it tests the import and nothing else.
Six of the eight tests fail under it.

The three existing `test_league_context.py` tests that monkeypatched
`app.routes.playoffs.get_playoff_grid` were repointed at the wrapper. They are unit
tests of the payload→context transformation, not of the cache, and they must patch the
function the code now calls.

---

## 7. A false control, caught, and why it is written down

The first reading taken of the grid endpoint was `/api/playoffs/bundesliga/grid` →
`0.304 s, wall=5.7, db=0.0, q=0`, and it was recorded as "the grid page serves this in
5 ms". **It was a 404.** The route is `GET /api/playoffs/{league_slug}` — there is no
`/grid` suffix — and only `%{time_total}` had been captured, not `%{http_code}`.

A 404 and a warm cache hit produce the same shape on every term of `x-timing-split`:
fast wall, `db=0.0`, `q=0`. Re-measured with the status code, the real endpoint reads
**200, 0.329–0.356 s, wall 20.7–22.2 ms, `q=0`** when warm and **200, 22.487 s, `q=9`**
when cold — which is a *better* number for the argument and a differently-sized one for
the record.

> **Gotcha #53's shape, one notch sharper: an empty 200 is a response shape, and so is a
> 404 timed without its status code.** Never quote a latency number from a `curl` that
> did not also print `%{http_code}`.

---

## 8. Gates

| gate | result |
|---|---|
| full backend suite | see `.claude/handoff/REPORT-LAT-P128.md` (exit code read BY VALUE) |
| new suite `test_league_context_grid_cache_lat_p128.py` | 8 passed, exit 0 |
| + contract `test_league_context.py` | 34 passed together, exit 0 |
| mutation battery | 8/8 killed, exit 0 |
| mutation residue (`--changed-only` vs `origin/master`, on a commit) | **CLEAN exit 0** — 224 needles / 790 broad checks; the same two pre-existing `typeahead_warmer` drifts master has |
| ruff (changed files) | branch **2**, master **2** on the same files → **net 0** (both are pre-existing unused imports in `test_league_context.py`) |
| frontend build (ESLint gate) | exit 0 |
| frontend typecheck (TS gate) | exit 0, **70 = baseline 70** |
| `merge-tree` vs `origin/master` | exit 0, tree `a1ccddf5` |
| `merge-tree` vs `-108`/`-109`/`-110`/`-111`/`-112`/`-113`/`calibration-118` | **all exit 0** — no `SHAPES` collision, because this entry sits at its own alphabetical anchor |
| `merge-tree` vs `ux-122` | exit 1 on `frontend/components/FeedCard.tsx` — **not this branch**: `ux-122` is already exit 1 against `origin/master` alone, and LAT-P128 touches zero frontend files |

---

## 9. Parked

* **P128-1** — the `count(DISTINCT bookmaker)` liquidity scan in
  `get_related_futures` step 7. Real, and the rewrite is already proven: a recursive-CTE
  loose index scan over `ix_fos_outcome_bookmaker` returned **byte-identical results for
  1,000 outcomes in 173.5 ms against the current form's 3,795.7 ms**, and the current
  form cannot complete 1,000 ids inside db-query's 10 s row-path timeout at all. It is
  parked and not shipped because **on the events measured it is 28 ms, not the
  bottleneck** — it needs a request whose outcome set is large enough for the scan to
  bind. Find that population first.
* **P128-2** — `GRID_WARM_LEAGUES` covers `mlb, nba, nhl, golf` only. `/api/playoffs/
  bundesliga` and `/api/playoffs/epl` measured **22.487 s / 22.110 s cold** (`q=9`,
  `db` 99.7 %, `maxq` 14.0 s / 12.8 s) on their own endpoint. Widening the list is a
  decision about warm-beat budget (`GRID_WARM_TIMEOUT_S = 120` per league, serial), not
  a line edit, and it belongs to the grid page's own ship.
* **P128-3** — the grid rebuild itself is `q=9` with `maxq` 12.8–16.4 s. One query
  inside `get_playoff_grid` is most of a soccer grid. Not opened this cycle.
* Carried from LAT-P127, unchanged: **P127-1** (BLOCKED on `-109`) · **P127-3** (NEEDS
  ALEX — gotcha #31 + blocked 5432 egress, already on `YOUR-TURN.md`) · **P127-4** ·
  **P127-5** · **P126-1** · **P125-A** · **P125-1** · **P125-2** ·
  **P124-1**–**P124-5** · **P110-4** (#2260, the needle's self-inflicted rate limit) ·
  **P122-5** (option b/c, **FOURTEENTH** consecutive cycle — already escalated to
  `YOUR-TURN.md`).

---

## 10. The sentence worth keeping

**When one surface is fast and another is slow on the same data, check whether they are
calling different functions before you profile either.** LAT-P126 found a page whose
two halves were one cached and one not. This is the same shape with the halves on
different pages: the fix had existed since #901, in the same module, under a name four
characters longer.

And its corollary, paid for in §2: **a plan is an answer about the inputs you gave it.**
The bookmaker scan really does read 1.22 million index entries — for a thousand
outcomes. This route hands it twelve.
