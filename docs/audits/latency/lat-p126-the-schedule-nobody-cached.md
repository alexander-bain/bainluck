# LAT-P126 — the schedule nobody cached, on the page whose other half was cached five years of tickets ago

**Date:** 2026-08-29 · **Branch:** `program/latency-112` · **Base:** `origin/master` `d9b76e9b`
**Pillar:** DISCOVER · **Ship:** the tournament schedule on `/playoffs/golf` stops making every
first visitor wait most of a second for data that changes weekly. · **Issue:** #2290

---

## 1. The item, and why it was already sitting on a plate

LAT-P125 shipped nothing — it re-implemented a fix `program/latency-108` already had, and the
duplicate was its finding. But the check it built to catch that produced a **free/taken table** over
every unmerged `program/*` branch, and it named the strongest free candidate outright:

> **P125-3 is the strongest free candidate: `/api/playoffs/golf/schedule` at 0.82 / 0.94 / 0.68 s
> for 29,662 bytes** — three slow reads in a row, so a CACHE defect, and verified claimed by no
> unmerged branch.

That entry told the truth and this cycle spent no time re-deriving it. **A cycle that ships nothing
can still leave the next one a measured, de-conflicted item, and this is what that looks like.**

Gotcha #155's check was still run first, because a table is a claim about a moment:

```
for b in $(git branch -r --no-merged origin/master ... | grep program/); do
  git diff origin/master...$b | grep -qE 'playoffs/golf/schedule' && echo "TAKEN: $b"
done
→ (no output)
```

Still free. Thirty seconds, before the EXPLAIN.

## 2. The defect, re-measured independently

Three reads in a row, plus a control on the same connection path:

| read | total | bytes |
|---|---|---|
| 1 | **0.739 s** | 29,662 |
| 2 | **0.801 s** | 29,662 |
| 3 | **0.686 s** | 29,662 |
| `/health` ×3 | 0.250 / 0.261 / 0.260 s | — |

LAT-P124's rule reads this off the table without any further instrumentation: **a second read as
slow as the first is a CACHE defect; a first read much slower than the second is a WARMER defect.**
Three slow reads, ~0.45 s of server work each time, for a byte-identical answer.

The code says the same thing. `get_golf_schedule` had **no cache of any kind** and made **five
SEQUENTIAL DataGolf calls** — one per tour — inside the request handler, on every request:

```python
tours = ["pga", "euro", "kft", "opp", "alt"]
for tour in tours:
    schedule = await service.get_schedule(tour=tour)   # five round trips, in a row
```

`x-timing-split: wall=317.3; db=0.0; app=317.3` on a separate read — **zero database time.** The
whole cost is external I/O the user is made to wait behind.

### The caller is a `useEffect`, so this is user-visible by construction

`frontend/app/playoffs/[sport]/page.tsx:592` — `useSWR(slug === "golf" ? "golf-schedule" : null,
fetchGolfSchedule)`. The `GolfScheduleSection` renders only once that resolves. Every visitor to
`/playoffs/golf` waits for it.

### The `max-age=300` that is not a counter-argument

`GET /api/playoffs/golf/schedule` does return `cache-control: public, max-age=300,
stale-while-revalidate=60`. It is not a server cache and it is not route-owned: it is the blanket
`("/api/playoffs/", 300)` rule in `app/utils/http_cache_policy.py`, applied by middleware to
everything under that prefix. Nothing caches on it between users — no CDN sits in front of the
Heroku router — so it is a **per-browser** directive. It makes a reload free. It does nothing at all
for a first load, which is the load the three reads above measure and the only load this lane exists
to fix.

## 3. The page's other half has had the fix since #901

`/playoffs/golf` renders two things. The championship grid is `bainluck:category:playoffs:golf`:
Redis-cached with a 3900 s TTL, a 24 h `:stale` last-good mirror, and an hourly warm in
`_precompute_grids`. The comment on that warmer is this cycle's defect, written down a year early:

> **#901: golf was missing from this warm list, so `/playoffs/golf` read an unwarmed
> `bainluck:category:playoffs:golf` key on every load → cold rebuild via ~15 sequential DataGolf
> calls (~12 s) and frequent skeleton stalls.**

Same page, same external API, same shape of defect, same fix — and the schedule section rendered
directly beside the grid was never given it. **The interesting part is not that the schedule was
missed; it is that the fix for it was already written, tested and running one function away.**

## 4. The fix, in three parts

### (a) The five round trips become one

`fetch_golf_schedule_raw` gathers the tours concurrently. `return_exceptions=True` preserves the old
per-tour tolerance exactly — a tour that raises is logged and skipped, its siblings survive
(gotcha #42) — and the render order is the declared `GOLF_SCHEDULE_TOURS` order, not the completion
order, so which tab opens first cannot drift with network timing.

### (b) The cached payload is CLOCK-FREE, and that is what makes the TTL safe

This is the load-bearing design decision. The surface renders a **"This Week"** badge. Caching a
response that contains a serve-time decision for an hour is how a cached page ends up announcing
that a tournament which finished in April is on this week.

So nothing time-dependent is cached. `fetch_golf_schedule_raw` stores only what DataGolf said —
names, courses, dates, locations, upstream `status`, `current_round`. Every derived field —
`is_current`, `display_status`, `current_event_id` — is computed at **serve** time by
`shape_golf_schedule(raw, now_str)`, from a date the caller passes in.

**A cached response therefore cannot print a stale badge, because the badge was never in the
cache.** The only thing that can age is DataGolf's own `status`/`current_round`, and those move on
a scale of days: `current_round` advances once per tournament round.

The shaping function is pure and clock-injected, so a test proves the property directly (gotcha
#44): shape the *same bytes* on two different days and watch the badge move.

The status cascade itself is carried over verbatim — same order, same `break` semantics, same
fallbacks. The ship here is latency, and a rendering change smuggled in beside it would be invisible
in the timings.

### (c) TTL 3900 s, and an hourly warm — because a cache alone ships nothing here

**TTL 3900, not 3600.** #901's lesson, applied one endpoint later: an hourly warm with a 3600 s TTL
expires marginally *before* the thing that refills it, and hands a cold rebuild to whoever arrives
in the gap. A TTL must outlive the cadence that refreshes it.

**And the warm is not optional.** The route fills the cache on a MISS, so without a warmer the first
visitor after every lapse still pays the full set of round trips. That is exactly the hole LAT-P115
recorded after LAT-P108 made `/futures/movers` fast — *and warm for nobody* — and `/playoffs/golf`
is a low-traffic page, which is precisely the page where "the second reader is fast" ships the
least.

`_precompute_golf_schedule` rides the hourly `precompute_category_pages`. **No new beat entry**
(gotcha #12), the same task whose grid section already warms the other half of this same page.

Two placement decisions in it are deliberate:

* **It is its own section, not an addition to `_precompute_golf`.** That function serves a different
  endpoint (`/api/golf`), and hanging this off its success path would reintroduce the coupling
  LAT-P001 removed from the Discover warm: a hiccup in the listing build would silently stop warming
  the schedule.
* **It runs BEFORE `grids`, not after.** The dispatch list's own comment says the last section
  starves first. A single external round trip must not sit behind a 120 s-per-league database build.

### (d) Two truthfulness repairs that came along for free

* **A failed or empty fetch serves the labelled 24 h last-good** instead of a 500 or an empty
  section. The old code returned `{"tours": []}` when every tour failed, which renders as a page with
  no schedule at all — indistinguishable from "golf has no season" (gotcha #53). An empty fetch also
  never overwrites a good cache.
* **`last_updated` is now the FETCH time, not the serve time.** Before a cache existed the two were
  the same. With one, a serve-time stamp on hour-old bytes is a freshness claim the payload cannot
  back. Nothing renders the field today; it is fixed because the cache is what makes it wrong.

## 5. The guard suite, and the one lesson it is built around

27 tests, exit 0, **none reads a clock** (verified by grep, not by assertion).

The suite's shape is set by **LAT-P125's M5/M6, which SURVIVED**: every test in that cycle read the
cache key *through the shared constant*, so the route and its warmer moved in lockstep and a
respelling was invisible. Here the key is a written-out literal in the test file
(`"bainluck:category:playoffs:golf:schedule"`), never the imported constant, and two mutants
respell it on one side only.

Both directions are asserted throughout (gotcha #43): the cache hit makes **zero** DataGolf calls
*and* the miss writes both keys; the failing tour is dropped *and* every sibling survives; the
date-derived badge moves with the day *and* the status-derived one does not.

One test crosses the two halves end to end: run the warmer against a fake Redis, then read the bytes
it wrote back *through the route*, and assert the route made no external call. If warm and route ever
key differently, that test fails and no amount of constant-sharing hides it.

## 6. Mutation battery — 17/17 killed, exit 0

Denominator printed first: **17 mutants queued across 2 target files.** Baseline green on the
unmutated tree before any mutant ran.

| # | mutant | class |
|---|---|---|
| M1 | never read the cache | the ship itself |
| M2 | back to five sequential round trips | the ship itself |
| M3 | drop `return_exceptions` | one dead tour takes the page down |
| M4 | TTL back to 3600 | expires before the warm that refills it |
| M5 | stop writing the last-good mirror | an outage empties the page |
| M6 | shape reads the clock itself | the badge freezes on the fetch day |
| M7 | `last_updated` back to serve time | a false freshness claim |
| M8 | cache an empty fetch over a good one | the section vanishes for an hour |
| M9 | 500 instead of last-good | truthful degradation |
| M10 | respell the key on the ROUTE side only | **LAT-P125's M5/M6 class** |
| M11 | sort the tours | the PGA tab stops opening first |
| M12 | shape mutates the cached dict | the second serve sees the first's answer |
| M13 | warmer writes only the primary | nothing behind it when DataGolf dies |
| M14 | warmer overwrites a good cache with an empty fetch | |
| M15 | move the warm behind the grids | it starves first |
| M16 | respell the key on the WARMER side only | **LAT-P125's M5/M6 class** |
| M17 | delete the warm section entirely | LAT-P001's coupling |

No mutant was reported NOT-APPLIED and no anchor matched twice — both halves of every mutant are
written as verbatim literals, which is also what keeps `scan_mutation_residue.py` Pass B clean.

## 7. Gates

| gate | result |
|---|---|
| new suite | **27 passed, exit 0** — none reads a clock |
| scoped `-k "golf or playoff or precompute_category"` | **1,380 passed / 2 skipped, exit 0** |
| mutation battery | **17/17 killed, exit 0**, denominator first |
| residue scan | **CLEAN exit 0 ON A COMMIT**, 233 needles / 830 broad checks — same two pre-existing `typeahead_warmer` drifts as master |
| ruff, same paths | branch **10** vs master's measured **10** → **net 0** |
| frontend build (ESLint gate) | **exit 0** |
| frontend typecheck (TS deploy gate) | **exit 0, 70 = baseline 70** |
| collect | branch **21,717** = base **21,690** + **27**, and the new file collects exactly 27 |
| full backend suite | see the report |
| `merge-tree` vs `origin/master` | **exit 0** |
| `merge-tree` vs `-108`, `-109`, `-110` | **exit 0** on all three |

### Two merge-tree exit-1s that are not collisions, said up front

* **`program/latency-111`** — conflicts in `precompute_category_pages.py`. That is the branch the
  board says **HAS NO READY TOKEN AND MUST NOT MERGE**. Recorded, not resolved. It does mean that
  **P125-A's hourly warmer, when it lands on top of `-108`, will meet this cycle's hunk in the same
  file** — the two are different sections of the same dispatch list, so it is a keep-both.
* **`origin/program/latency-106`** — a stale REMOTE ref. Four of its five code files are already
  byte-identical to master (its ship landed as LAT-P121b via `-107`, `d9b76e9b`); the local branch
  is even renamed `program/latency-106-superseded-by-LAT-P121b`. The only file that differs is
  `scan_mutation_residue.py`'s `SHAPES` — the append hunk six latency branches have now collided on,
  and the reason this cycle's entry is inserted **alphabetically** rather than at the head.

## 8. The free/taken table, updated rather than re-derived

Carried from LAT-P125 and amended by this cycle:

| endpoint | claim |
|---|---|
| `/api/futures/categories` | **TAKEN** — `-108` (LAT-P122, #2281) |
| `/api/playoffs/golf/schedule` | **TAKEN as of this cycle** — `-112` |
| `/api/market-moves` | **free** |
| `/api/events/ei-rankings` | **free** |
| `/api/sports/hierarchy` | **free** |
| `/api/calibration` | the calibration lane's, not this one's |

## 9. What this cycle did NOT do, stated plainly

* **It cannot move the needle, and that was known before it started.** `/api/playoffs/golf/schedule`
  is not one of the seven member paths, and `/playoffs/golf` is not one of the three graded surfaces.
  The needle is reported because the lane reports it every cycle, not as evidence for this ship.
* **The ~0.45 s of server cost was not decomposed per tour.** `DATAGOLF_API_KEY` is production-only,
  so a per-call breakdown would need a one-off dyno and a durable place to write the result. It is
  not load-bearing: the cost is provably external (`db=0.0`), the cache removes all of it on a hit,
  and the warmer's own measured duration lands in the `category-precompute` admin report after
  deploy, which is where the parallel-fetch cost becomes visible without any new instrument.
* **No post-deploy timing.** This lane builds; the Integrator merges and deploys. The re-measure of
  0.739 / 0.801 / 0.686 s against a warm cache belongs to whoever verifies the merge.
