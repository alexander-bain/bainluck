# LAT-P130 — the grid that ran the same whole-table scan once per tour

**Date:** 2026-08-29 · **Branch:** `program/latency-116` · **Cut from:** `origin/master` `d9b76e9b`
**Pillar:** DISCOVER
**Ships:** when the golf grid actually has to be rebuilt, the user who lands on it stops getting a
503.

---

## 1. What the user saw

`GET /api/playoffs/golf` serves from Redis in **1.04 s**. That is the number anyone checking would
have found, and it is not the number this queue is about.

When both cache keys are cold the route rebuilds live, under an `asyncio.wait_for(..., timeout=25)`.
Measured on production 2026-08-29:

| probe | result |
|---|---|
| `?top=11` (bypasses cache) run 1 | **HTTP 503 after 26.1 s** |
| `?top=11` run 2 | **HTTP 503 after 25.4 s** |
| `?hours=168` (bypasses cache, otherwise the default build) run 1 | **HTTP 503 after 25.3 s** |
| `?hours=168` run 2, immediately after | **HTTP 200 in 15.3 s**, 725,480 bytes |

The body of the 503 is explicit and correct about what it is:

> `Playoff grid for 'golf' timed out and no last-good payload is available. This is a degraded
> state, not an empty league.`

The fourth probe is the interesting one. It succeeded because the first three had just dragged
50,364 blocks of `futures_markets` into `shared_buffers`. **Cold, the build does not fit in the
route's 25 s budget. Warm, it takes 15.3 s.**

### Why the page usually works anyway

Golf is in `GRID_WARM_LEAGUES`, and the hourly warm beat runs the *same* build under
`GRID_WARM_TIMEOUT_S = 120` — nearly five times the request's budget. The last run completed golf in
**15.2 s** (`/api/admin/category-precompute/last`), which matches the warm-buffer probe exactly.

So the warm key exists because a background job with a 120 s budget keeps paying for something the
user's own request cannot afford. Every deploy, and every hour the warm cycle misses, is a window in
which a real request has to do the build itself — and loses.

---

## 2. The first defect: an OR across two columns is a decision to read the whole table

`_query_tournament_db_markets` found its candidates with:

```python
sport_conditions = [FuturesMarket.external_id.ilike(f"{sk}%") for sk in config.sport_keys]
stmt = select(FuturesMarket).where(
    or_(*sport_conditions, FuturesMarket.llm_sport_category == "golf"),
    FuturesMarket.status != "resolved",
    FuturesMarket.source != "datagolf",
).options(selectinload(FuturesMarket.outcomes))
```

Two unrelated columns under one `OR`. No index serves that, so Postgres does not try.

`EXPLAIN (ANALYZE, BUFFERS)` on the exact SQL SQLAlchemy emits — not a hand-written approximation of
it:

```
Gather  actual_rows=96  t=6045.98
  Parallel Seq Scan on futures_markets  actual_rows=48 loops=2
      Rows Removed by Filter: 455594
      Shared Read Blocks: 50364
duration_ms 6122.3
```

**911,284 rows read to return 96.** The table:

| source | rows |
|---|---|
| polymarket | 645,312 |
| kalshi | 265,933 |
| datagolf | 330 |
| odds_api | **12** |

Golf's `config.sport_keys` are `golf_pga`, `golf_masters`, `golf_us_open`, `golf_open`,
`golf_pga_championship` — Odds API sport keys. The `external_id` branch of that OR can only ever
match rows from the twelve-row `odds_api` space. It read 911,284 rows to search twelve.

### The fix is the pairing `models.py` already documents

`FuturesMarket.external_id` is not one id space. It is one column holding several, and which one a
row holds is decided entirely by `source` — the model says so: *"sport_key or event_ticker"*. Nobody
had written that where a query planner could read it.

```python
_GOLF_SPORT_KEY_ID_SPACE_SOURCE = "odds_api"

market_filter = or_(
    and_(
        FuturesMarket.source == _GOLF_SPORT_KEY_ID_SPACE_SOURCE,
        or_(*sport_key_prefixes),
    ),
    category_branch,
)
```

Same SQL, one conjunct added:

```
Bitmap Heap Scan on futures_markets  actual_rows=96  removed=7533  read_blocks=1346
  BitmapOr
    Bitmap Index Scan on ix_fm_source_created_at        rows=155
    Bitmap Index Scan on ix_fm_golf_identity_category   rows=11002
duration_ms 483.1
```

**6,122 ms → 483 ms. 50,364 blocks → 1,346. Identical 96 rows.**

(An earlier pair of runs on the same predicates, with different buffer state, measured 7,914 ms →
843.9 ms. Both are recorded; the ratio is 9.4×–12.7× depending on how cold the table is.)

---

## 3. The second defect: nothing in that SQL depends on the tournament

`_build_golf_grid_from_datagolf` loops five tours:

```python
tours = ["pga", "euro", "kft", "opp", "alt"]
for tour in tours:
    event_grid = await _build_golf_tour_grid(service, tour, config, db, trend_hours, top)
```

and each `_build_golf_tour_grid` called `_query_tournament_db_markets`. The tournament name reaches
that function, but **only the Python filter under the query uses it.** The SQL is byte-identical for
every tour: same config, same `llm_sport_category = 'golf'`, same exclusions.

`_build_upcoming_golf_event_grid` — the upcoming-major path — issued the *same* query again, a third
distinct copy of the same six lines.

Three tours were live on the day of measurement (PGA · TOUR Championship, European · Husqvarna
British Masters, Korn Ferry · Simmons Bank Open), each returning a grid. So a cold build ran that
seq scan **at least three times**: ~18.4 s of the request's 25 s budget spent fetching the identical
96 rows three times over.

`GolfCandidateMarkets` makes it one load per build:

```python
candidates = GolfCandidateMarkets(db, config)
for tour in tours:
    event_grid = await _build_golf_tour_grid(..., candidates=candidates)
```

Three properties, each deliberate and each guarded:

* **Lazy** — an off-season build where no tour has a current event still issues no query. Eagerly
  loading would have been simpler and would have added ~0.5 s to a request that returns `None`.
* **Instance, not module global** — it holds live ORM rows bound to one build's session. Gotcha #6
  is that a module-level cache must never do that. `__slots__` keeps the storage per-instance and a
  test asserts it.
* **`None` means unloaded, `[]` means loaded-and-empty** — the obvious `if not self._markets`
  rescans forever on an empty corpus. That is one of the killed mutants.

The parameter defaults to `None`, so `_query_tournament_db_markets` still works standalone and loads
its own set. The holder is an optimisation, not a new required argument.

---

## 4. Equivalence: proven on the population, and said as a population claim

Scoping `external_id ILIKE 'golf_pga%'` to `source = 'odds_api'` is **not a logical identity**. It is
an identity *on the population that exists*, and the difference between those two sentences is the
entire risk of this change. So `backend/scripts/lat_p130_verify_golf_equivalence.py` measures it, in
two independent ways.

**STRUCTURAL** — take the filter the route actually builds, strip the `source = 'odds_api'`
conjuncts back out, compile both to SQL and compare byte-for-byte to the legacy predicate. If they
differ, the change did something other than add a source scope, and no population check covers that.

**POPULATION** — the rows the old filter matched and the new one drops are exactly
`source <> 'odds_api' AND (external_id matches a golf sport key)`, plus any NULL source.

```
STRUCTURAL
  OK   the new filter is the legacy filter plus a source scope

POPULATION
  futures_markets ~911117 rows (pg_class estimate)
  NULL source rows: 0
  sources (census): datagolf, kalshi, odds_api, polymarket
  OK    datagolf: 0 matched, 330 examined
  OK    kalshi: 0 matched, 265933 examined
  keep  odds_api: 3 matched, 12 examined
  OK    polymarket: 0 matched, 645312 examined
  examined 911587 of ~911117
  OK   no non-odds_api row carries a golf sport-key prefix

VERDICT  EQUIVALENT on the current population        (exit 0)
```

### Three harness failures that had to be told apart from a result

The first draft of this script reported `UNMEASURED` three times before it reported anything true,
and each time the cause was db-query's ceiling rather than the data:

1. **Whole-table probe** — one `count(*)` over all 911K rows: `statement_timeout` on the 10 s row
   path, then **21.6 s** on the 25 s explain path. Correct, but one bad minute from being a lie.
2. **Per-source probe on the row path** — `source = 'polymarket'` measures **9.35 s** against a hard
   10 s ceiling. It timed out on the first run and would have timed out again.
3. **Source-RANGE partitioning** (`source >= 'k' AND source < 'p'`) — an attempt to chunk without
   needing a source list. It does *not* get an index range scan and blew the 25 s ceiling too.

What works: `source = '...'` equality, which drives `uq_futures_source_external` (kalshi 5.1 s,
polymarket 9.4 s), read off the plan through the 25 s explain path.

**A timeout is a story about the harness, not a difference.** The script exits **2**, not 1, when it
could not measure, and it never scores a timeout as "no rows lost". It also reconciles the rows each
scan actually walked against `pg_class.reltuples` before claiming a zero — *it returned* is not *it
worked*, and a scan cut short reports zero matches exactly like a complete one. 911,587 examined vs
~911,117 estimated is full coverage.

The source list is discovered by census when the census query survives (it is itself marginal at
4.7–9.9 s) and falls back to the known set when it does not. That fallback is safe **only** because
of the coverage reconciliation: a source missing from the list would show up as a shortfall in
`examined`, not as a silent pass.

### The one row shape where old and new differ

A non-`odds_api` row carrying an Odds API sport key in `external_id`. The old filter kept it; the new
one drops it. **There are zero such rows in 911,587.** That divergence is asserted explicitly in the
guard suite rather than left implicit, so it is a decision on the record. If it ever becomes
reachable, the source-scoping premise is broken and the equivalence script is what says so.

---

## 5. The guards assert the shape, because both defects returned the right rows

Neither defect was visible on the page. The predicate selected exactly the right 96 markets. The
repetition returned exactly the right rows every time it ran. A results test passes against both, and
a timing test merely gets slower on a bad day. The only tells were **a query plan** and **a query
count**, so those are what the 34 tests in
`backend/tests/test_golf_grid_candidate_scan_lat_p130.py` assert:

* **The plan's cause.** A tree-walk over the real clause object: every `external_id ILIKE` node must
  have an ancestor `AND` pinning `source = 'odds_api'`. A companion test runs the same walk over the
  legacy predicate and requires it to be *detected as unscoped* — a guard that cannot see its own
  defect proves nothing.
* **The second door.** Scoping the *category* branch to `odds_api` as well is faster still, entirely
  silent, and drops from 96 candidates to 12 — the grid empties and every timing check looks
  excellent. Pinned by a test that fails if the category branch acquires a source scope.
* **The query count.** `GolfCandidateMarkets.loads` is public precisely so "five consumers, one
  scan" is assertable without monkeypatching a session, and stubs standing where the real grid
  builders stand fail if `candidates` arrives as `None`.
* **Behaviour, on the expression the route actually uses.** A 25-line evaluator over the real clause
  object, so the behavioural cases cannot drift into being a re-implementation of the filter. No DB.
* **The measured SQL.** One test pins the compiled text whose `EXPLAIN ANALYZE` is the evidence for
  6,122 ms → 483 ms. If the text drifts, the measurement no longer describes the code, and this
  document needs re-running rather than re-reading.

**Mutation battery: 10/10 killed, exit 0** (`backend/scripts/lat_p130_mutation_battery.py`) —
`flat-or`, `second-door`, `wrong-id-space`, `drop-resolved-exclusion`, `drop-datagolf-exclusion`,
`no-memo`, `empty-list-reloads`, `unwired-tour-grid`, `unwired-major-grid`, `class-level-state`.

Two things the battery is careful about, both stated rather than assumed. A mutation that fails to
**apply** reports green, so every mutant asserts its anchor was found exactly once before the suite
runs, and a pytest exit that is not 0 or 1 is scored `UNSCORED`, never as a kill. And the restore is
**asserted** — original bytes written back in a `finally`, final SHA-256 compared to the starting
one. Trade stated, not hidden: this battery is `scripts/lat_p130_mutation_battery.py`, not
`evals/*_mutations.py`, so it needs no residue-registry entry and stays clear of the hunk the
unmerged `-108`/`-111`/`-113` branches share — and it is therefore not covered by that scanner, which
is why it restores from a byte-for-byte backup instead.

---

## 6. Caller grep ran first — and killed a third target

Per the standing rule from LAT-P127/P128, callers were grepped before anything was measured.

* `_build_golf_grid_from_datagolf` ← `get_playoff_grid` (line 2756) → `/api/playoffs/golf`, reached
  by the league page, the team page, the grid page and the native screen. **Real.**
* `_build_upcoming_golf_event_grid` ← `_build_golf_grid_from_datagolf` only. **Real.**

The parked item **P129-4** also named `_get_team_progression_for_event_uncached` as carrying the same
OR shape. It does — and it is **dead code**. `get_team_progression_for_event`, its only caller, has
no callers anywhere in the repo. The route that looks like it should use it,
`GET /api/events/{id}/team-progression` in `routes/events.py:9457`, goes through
`enrich_event_with_context` in the league-context service instead. Fixing its query would have
shipped nothing and cost a full gate cycle. Re-parked below as a deletion, not a performance item.

---

## 7. Scope, stated precisely

* **A warm read is 1.04 s and this queue does not touch it.**
* The rebuild is reached when both `bainluck:category:playoffs:golf` and its `:stale` companion are
  cold — after a deploy, or when an hourly warm cycle misses. The `:stale` key holds 24 h and serves
  a labelled last-good payload without triggering a rebuild, so the 503 needs the primary key cold
  **and** no usable stale payload.
* This does not change what the grid shows. Same 96 candidate markets, same Python filters, same
  output. The equivalence script is the evidence.
* **What is claimed:** three cold candidate scans at 6,122 ms become one at 483 ms — **~17.9 s of
  measured DB work removed** from a build that today exceeds 25 s, and the same three-into-one
  saving on the hourly warm beat.
* **What is not claimed:** a post-deploy number. Nothing is deployed. Whether the cold rebuild now
  lands inside the 25 s budget is a measurement the Integrator owes after merge — re-run
  `/api/playoffs/golf?hours=168` twice and compare against 25.3 s / 15.3 s here.

---

## 8. Parked

* **P130-1** — delete `get_team_progression_for_event` and
  `_get_team_progression_for_event_uncached` from `playoffs.py`. Dead since the team-progression
  route moved to `enrich_event_with_context`; ~120 lines carrying a copy of the seq-scan defect that
  can never run. A deletion, so it needs its own caller grep and its own gate cycle.
* **P130-2** — `_build_golf_tour_grid` runs five tours **sequentially**, each awaiting three
  DataGolf HTTP calls (`get_schedule`, `get_in_play_with_info`, `get_pre_tournament`) — fifteen
  serial round trips per build. Whether they dominate what remains is **not measured**: this queue
  timed the candidate scan, not the HTTP legs, and the arithmetic that would infer it is exactly the
  kind of subtraction LAT-P128's first hypothesis punished. Time them before rewriting anything, and
  check DataGolf's rate limit before reaching for `asyncio.gather`.
* **P130-3** — `_lookup_datagolf_outcome_ids` runs once per tour and was not examined. Unknown cost.
* **P129-1** · **P129-2** · **P129-3** (NEEDS ALEX) · **P129-5** · **P128-1** · **P128-2** ·
  **P127-1** (BLOCKED on `-109`) · **P127-3** (NEEDS ALEX) · **P127-4** · **P127-5** · **P126-1** ·
  **P125-A** · **P125-1** · **P125-2** · **P124-1**–**P124-5** · **P110-4** · **P122-5**.
* **P129-4 is DISCHARGED** — two of its three functions are the subject of this queue, and the
  third is dead code, re-parked as P130-1.

---

## 9. Gates

Recorded in `.claude/handoff/REPORT-LAT-P130.md`.
