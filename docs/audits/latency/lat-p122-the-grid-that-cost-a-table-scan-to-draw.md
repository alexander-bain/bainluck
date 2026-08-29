# LAT-P122 — the grid that cost a table scan to draw

**Pillar: DISCOVER. Ship: the Search tab's category grid opens without every
visitor paying a ~305 MB scan of `futures_markets`.**

Branch `program/latency-108`, cut from master `a68b2a1b`. Cycle 2026-08-29.

---

## 1. What a person waits for

`/search` renders `CategoryBrowser` (`frontend/components/CategoryBrowser.tsx`),
whose first act on mount is `fetchFuturesCategories()`. Until that answers there
is no grid — the page is the grid. Measured on production slug `a68b2a1b`,
2026-08-29, two consecutive reads ten seconds apart:

| read | `x-timing-split` |
|---|---|
| 1 | `wall=1585.9; db=1577.6; app=8.3; q=1; maxq=1577.6; router=1.5` |
| 2 | `wall=1365.1; db=1357.2; app=7.9; q=1; maxq=1357.2; router=1.9` |

`q=1`. One statement, ~99 % of the request — **and the second read is as slow as
the first.** That is the whole finding. This tier had no cache of any kind: not a
small one, not a per-process one, not a broken one. None.

The same surface's other half is worse and is deliberately not touched this
cycle (§7): `GET /api/admin/latency-stats` reports `/api/futures/browse` over the
hour at **n=10, p50 3,796.8 ms, max 4,318.5 ms** — a p50, not a tail.

## 2. Where the second and a half goes

`EXPLAIN (ANALYZE, BUFFERS)` on the emitted statement, production, same day,
via `POST /api/admin/db-query` with `explain: true, analyze: true`
(`duration_ms` 1,732.3):

```
Sort  (count DESC)                                   actual 1,696.2 ms   rows=42
  GroupAggregate  Group Key: llm_sport_category      actual 1,696.1 ms   rows=42
    Sort  Sort Key: llm_sport_category               actual 1,651.8 ms   rows=21,439
      Bitmap Heap Scan on futures_markets            actual 1,565.9 ms   rows=21,439
        Recheck: resolution_date IS NULL AND status='open' AND event_id IS NULL
                 OR resolution_date >= now() AND status='open' AND event_id IS NULL
        Filter:  name !~~* '% vs %' AND name !~~* '% vs. %'
        Rows Removed by Filter: 27,897
        Exact Heap Blocks: 38,201
        -> BitmapOr                                  actual    72.3 ms
Shared Hit Blocks: 39,014
```

**39,014 blocks — roughly 305 MB of buffer traffic — to produce 42 rows of
`(key, count)`.** Three facts worth separating, because they suggest three
different fixes and only one of them is this ship:

1. **The two negated `ILIKE`s are unindexable.** `name !~~* '% vs %'` cannot be
   served by any index, so all 49,336 candidate rows (21,439 kept + 27,897
   removed) are visited on the heap. Cheapening this needs DDL or a stored
   column; the migration slot is Integrator-owned (ruling 080). **Not taken.**
2. **The planner estimates 728 rows and gets 21,439** — a 29x misestimate driven
   by the same unindexable filter — so it picks a sorted `GroupAggregate` and
   sorts 21,439 rows to group them into 42. A hash aggregate would skip the
   sort, worth roughly the 86 ms between the heap scan and the group. **Not
   taken:** it is 5 % of the cost and it is a planner hint, not a fix.
3. **Every visitor ran it.** That is 100 % of the cost for everyone after the
   first, and it needs no DDL, no hint and no new statement. **This ship.**

## 3. What shipped

`backend/app/utils/futures_categories_cache.py` — the tier's policy, extracted
under ruling 005 (extract-on-touch) because this queue changes its serve
decision, its fallback and its write path. It adopts `event_concept_cache`'s
primitives as the **third customer** (`/event/{key}` first, `hub.py` #1651
second, game-markets #1587 third — this is the fourth tier and third adoption of
`cache_keys(prefix=...)`).

* **A shared Redis slot.** `bainluck:futures_categories:all`. The answer has no
  per-user, per-session or per-argument variation — `/categories` takes no
  parameters — so one slot serves the entire fleet.
* **No in-memory L1, deliberately.** A Redis round trip is single-digit
  milliseconds against a 1,400 ms build. LAT-P121 kept game-markets' L1 because
  it was already there and removing it was not the ship; adding one here would
  be a second freshness rule to keep in phase for no measured win.
* **A 24 h mirror as a first-class SERVE path.** On a primary miss the reader
  gets the mirror immediately and exactly one rebuild runs behind it. This is
  the defect `#1651` recorded for `hub.py` and `#1587` for game-markets, refused
  in advance on a fourth tier rather than found there later.
* **The five envelope fields** on the stored artifact
  (`docs/contracts/cache-envelope.md`).

### 3.1 The mirror is age-bounded, and here that is the honest part

`STALE_SERVE_CEILING = 5`, against `FRESH_TTL = 300` — 25 minutes.

These numbers are **printed to the user**: `6,614` beside the Politics tile,
`21,439 markets` across the top of the grid. A day-old mirror would print a count
nobody can reproduce by tapping the tile, while every latency number improved —
the trap LAT-P121 named on its own tier and the FORMATTING pillar exists to
stop. Past the ceiling the reader blocks and rebuilds, which is exactly today's
behaviour. **A permanently-failing refresh degrades this tier to slow, never to
wrong.**

The ceiling multiple is deliberately the same 5x as
`routes/events.py::_STALE_SERVE_CEILING` and
`game_markets_cache.STALE_SERVE_CEILING`: two serve-stale ceilings in one product
that disagree are a coin flip about which one a reader gets. Asserted as a
cross-module equality, not a literal.

### 3.2 `serve_stale_and_refresh` moved to the policy home, and got stronger

LAT-P121's finding was a serve-stale helper **forty lines above** a cache that
ignored it. The response to that finding is not to make a third copy. So the
helper moved into `app/utils/event_concept_cache.py`, which ruling 005 already
names as the policy home for cache-envelope tiers, and the new tier uses it.

`routes/events.py` keeps its own copy this cycle — `program/latency-107` is in
flight on that file and a second edit buys a conflict, not a ship. **Parked as
P122-1.** The migration is worth doing because the shared one is *strictly
stronger*, not merely shared:

| | `routes/events.py::_serve_stale_and_refresh` | `event_concept_cache::serve_stale_and_refresh` |
|---|---|---|
| single-flight scope | a process-global `set` | the Redis `:refreshing` lock |
| rebuilds per expiry | one per Uvicorn worker per dyno — `WEB_CONCURRENCY=2` makes that **2N** | **one, fleet-wide** |
| lock release | n/a | compare-and-delete by owner token (#1678 finding 1) |
| refused (no loop) | returns False | returns False **and gives the lock back** |

### 3.3 The watermark is null, and that is a published answer

`lifecycle_watermark` is contract field 5. The only honest value here is
`max(updated_at)` over the population being counted — which is a **second pass
over the 39,014 blocks this ship exists to stop reading**. Buying a freshness
field with the cost the fix removes is not a trade worth making, and the
contract's own answer for a watermark that cannot be computed is `null` rather
than a plausible-looking substitute. The field is present and null; a mutant
(M10) that stamps the build time instead is killed.

## 4. The response shape did not move

`{categories: [{key, count}], total}` is unchanged; the `cache` envelope is
additive, exactly as it is on `/api/hub/{competition}` and
`/api/events/{id}/game-markets`. `frontend/lib/types.ts::FuturesCategoriesResponse`
needs no change and none was made — **no frontend or native file is touched and
no frontend gate is claimed.** The `row.llm_sport_category or "other"` collapse
is carried across verbatim and pinned by a test.

⚠️ **One pre-existing shape hazard, observed and NOT fixed.** The grid maps a
`NULL` category to the key `"other"`, and `browse_futures` filters
`llm_sport_category == category` — so a tile labelled `other` opens a query for
the literal string `'other'`, not for the NULLs the tile counted. Today's census
returns exactly one `other` row (123), so at least one of the two populations is
currently empty and nothing is visibly wrong. It is a taxonomy question, not a
latency one, and it is recorded rather than repaired here. **Parked as P122-3.**

## 5. And the residue scanner was asking the wrong question

Pass B of `scan_mutation_residue.py` flags a replacement literal found in a
changed file that is not its declared target — "was a mutant COPIED out of its
target". Running it on this commit turned it **red**:

```
🔴 RESIDUE: 1 candidate mutant(s) outside a declared target
     backend/app/utils/event_concept_cache.py  <-  game_markets_shared_cache_mutations:M13
```

`M13` replaces game-markets' `CACHE_PREFIX` with `"bainluck:event_concept:"` —
**which is the genuine, shipped constant at the top of
`event_concept_cache.py`.** It is not residue and never was. It had simply never
fired, because Pass B sweeps only files changed against `origin/master` and
nothing had touched that file since the harness landed. The first branch to touch
it turns the gate red on a line master already has.

The repair is to compare against the BASE, which is the question Pass B meant to
ask all along: a literal already present in that file at `origin/master` predates
every mutant run and cannot be this branch's residue. The cleared candidates are
**named and counted** in the output, never filtered in silence — a scan that
quietly narrows its own scope is the failure this file's docstring refuses — and
`_base_already_has` **fails closed**: an unreadable base blob (a file this branch
added, an unresolvable base) keeps the finding.

**Verified in both directions, because a suppressor is only as good as what it
still catches:**

| case | expectation | result |
|---|---|---|
| the pre-existing `event_concept_cache.py` collision | cleared, named, counted | ✅ exit **0**, listed under "pre-existing source, not residue" |
| the SAME literal planted into `futures_categories_cache.py`, a file master does not have | still residue | ✅ exit **1**, `🔴 RESIDUE: 1 candidate` |

The plant was done in a throwaway worktree at this branch's head, committed
there so `git diff --name-only base...HEAD` could see it, and the worktree
removed.

**Offered as a gotcha:** *a broad-sweep gate that only looks at changed files has
never been run against most of the tree, so its first true reading of a file can
be a false positive that has been latent for months. Diff-scoped scanners must
compare against the base, not against absolute presence.*

## 6. Gates

| gate | result |
|---|---|
| new suite `tests/test_futures_categories_cache.py` | **32 passed, exit 0** — every assertion is shape, TTL or CALL COUNT; none is wall clock |
| scoped (`test_route_futures_browse`, the four `event_concept_*`, `game_markets_shared_cache`, this file) | **248 passed, exit 0** |
| `tests/test_mutation_guard.py` | **9 passed, exit 0** |
| mutants `futures_categories_census_mutations.py` | **17/17 killed, exit 0**, denominator printed BEFORE the first verdict |
| residue scanner, on a COMMIT | **CLEAN, exit 0** — 232 needles, 1,002 broad checks, 1 pre-existing collision named |
| ruff, touched paths | **1 = master `a68b2a1b`'s own 1 on the same paths, measured → +0** (the one is a pre-existing `F401` at `futures.py:2306`; there is no Python lint gate in CI) |
| collect baseline | `a68b2a1b` **21,659 MEASURED** in a throwaway worktree; this branch **21,691** → **+32, exactly the new file** |
| full backend suite | see the READY token — run to completion after every source edit was finished |
| frontend / native | **not claimed.** No file of either kind is touched |

### 6.1 One full-suite run killed BY PID on purpose

A first full run (pids 6418/6475) was started before the residue-scanner repair
and was killed at ~8 % once that repair became necessary, because a source edit
during a pytest run produces phantom failures. Killed by **pid**, never
`pkill -f`; the ux lane's own pytest (89135/89140) was verified **ALIVE in `ps`**
immediately afterwards. The launcher reported its own exit 0 — that is the
launcher, not a verdict, and the tell is the missing verdict line.

### 6.2 Two guard tests were rewritten during the cycle, and why

* `test_a_mirror_exactly_at_the_ceiling_is_still_served` read the wall clock
  between the stamp and the comparison, so an exactly-at-the-ceiling payload
  aged a few microseconds past it. `now` is now passed explicitly (gotcha #44's
  shape: an anchor that depends on how fast the machine is).
* `test_the_mirror_ttl_is_the_shared_one_not_a_second_copy` asserted
  `fcc.STALE_TTL is concept_cache.STALE_TTL`. The mutation harness re-execs that
  module from source, minting a fresh `int`, so the identity failed for a reason
  unrelated to the property. It now asserts identity against the tier's own
  import alias `_SHARED_STALE_TTL` — the same claim with no such hole.

Both were found by the mutation battery's **red baseline**, which is what a
baseline check is for.

### 6.3 The battery's own repair, worth one line

The first battery run reported a red baseline on `event_concept_cache`. The cause
was that swapping `sys.modules[dotted]` is **not enough**: `from app.utils import
event_concept_cache as x` resolves through the parent package's attribute, so the
guard file kept binding the real module while the route — which imports the
dotted name — got the mutant. The two then disagreed about which
`_REFRESH_TASKS` set existed and which `get_client` a test had patched. The
oracle now sets both and restores both.

## 7. Parked, each with what it needs

* **P122-1 — migrate `routes/events.py` to the shared
  `serve_stale_and_refresh`.** Blocked only by `program/latency-107` being in
  flight on that file. The table in §3.2 is the argument; it is a strict upgrade
  from 2N rebuilds per expiry to one.
* **P122-2 — `/api/futures/browse`'s `COUNT(*)`.** Same predicate, same
  population, measured at **2,038 ms of a 2,424 ms request** with no category.
  It is derivable from this census exactly: `browse(category=X).total ==
  census[X]`, for any X that is a non-null category key. Two things must hold and
  both are cheap: derive `has_more` from a `limit + 1` fetch rather than from
  `total`, so a stale count can never hide or invent a page; and fall back to the
  live `COUNT` when the requested category is `other` (§4's NULL/literal
  ambiguity) or when `q` is present. **Blocked on `program/ux-122`**, which
  rewrites `browse_futures`' item loop.
* **P122-3 — the `other` tile.** §4. Taxonomy, not latency.
* **P122-4 — the DDL.** A partial expression index cannot help the negated
  `ILIKE`s; what would is a stored boolean (`is_game_level`) maintained on write,
  which is a migration and a backfill. Migration slot is Integrator-owned
  (ruling 080). Staged in `PARKED-MEASUREMENTS.md` with the block counts above so
  nobody re-derives them.
* **P122-5 — the needle definition.** The directive still names **option b**;
  the tree's harness is **option c** (ruling 127). **EIGHTH** consecutive cycle:
  P116-6 → P117 → P118-5 → P119 → P120 → P121-5 → P122-5.

## 8. Issues

* **#2281 filed** for this defect with the plan, the EXPLAIN and the measured
  before-numbers, and left **OPEN** — nothing is deployed, and closure requires a
  measured production reading of the deployed slug, not a merged branch.
* **#1651 is DONE and should be closed.** Its fix (LAT-P026) shipped, and the
  owed production after-reading was collected by INT-039 on 2026-08-11 and is in
  the issue's own comments: a plain TTL expiry reaches the mirror at
  `hub.py:448-451`, four readers in one expiry window produced one rebuild, and
  the empty-build rescue is kept at `hub.py:468-473`. Verified still true on
  master today (`hub.py:523-526`). **LAT-P121's report named #1651 as the NEXT
  SHIP; it had already shipped nine cycles earlier.** Recorded as a process note:
  a "next ship" pointer written from a queue header rather than from the tree
  costs the next cycle its first twenty minutes.
