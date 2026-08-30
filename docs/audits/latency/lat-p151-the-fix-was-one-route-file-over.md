# LAT-P151 — the fix was one route file over, and two queues parked an index instead

**Pillar:** DISCOVER / FORMATTING experience. **Ship:** tapping **Search** stops showing
"Loading suggestions…" for nine to eighteen seconds. The zero-state chips are the first thing
a person sees on that surface, and until now every visitor who arrived more than five minutes
after the last one paid the whole build.

**Issue:** [#2285](https://github.com/alexander-bain/bainluck/issues/2285).
Branch `program/latency-151`, cut from `origin/master` @ `6933b6ef`. `migration_slot: none`,
`beat_schedule_change: FALSE`, `ddl: NONE`.

**Directive:** `runner-inbox/latency/055-coldpath-conveyor.md`, the standing coldpath conveyor.

---

## 1. The census first, because the directive says so and it was right to

`for b in $(git branch --list "program/latency-*"); do git log --oneline origin/master..$b; done`
— eight live unmerged branches. Ranking the 24 h slow-request ring against them:

| endpoint | n (24 h) | p50 | banked by |
|---|---|---|---|
| `/api/events/typeahead` | 68 | 8,075 | `-128` |
| `/api/events/{id}/related-futures` | 47 | 7,426 | `-129` / `-149` |
| `/api/playoffs/{league_slug}` | 37 | 10,966 | already merged — silent 19.1 h |
| `/api/teams/{id}/prop-families` | 34 | 12,077 | `-130` |
| `/api/feed` | 17 | 9,072 | `-126` |
| `/api/tournaments/{slug}` | 11 | 8,852 | `-132` |
| `/api/event/{key}` | 9 | 18,637 | `-131` |
| **`/api/events/search-suggestions`** | **8** | **12,969** | **nothing** |

LAT-P150's ranking reproduced exactly (8 requests, p50 12,969 ms, max 18,388 ms), which is
the cross-check that the ring had not moved between us.

**And a caveat that belongs in the record rather than in a footnote.** Reading the ring
entry-by-entry, most of those eight are AGENT PROBES, not visitors: the 04:29–04:54 cluster is
LAT-P139's own measurement session (12,782 / 8,338 / 12,103 / 13,156 / 17,583 / 17,918 ms —
the same numbers that queue's docstring quotes), 14:24 is LAT-P150's, and 16:44 is this
queue's. Two of the fourteen ring entries look like real traffic. The ring's COUNT on a
low-traffic surface is not a demand signal.

That does not weaken the ship, and the reason is measured below: the tier's stale-serve
ceiling is 300 s, so a genuine visitor who arrives more than five minutes after the previous
one pays the full build. On this surface that is nearly all of them. The defect is the WAIT,
not the count of agents who have stood in it.

## 2. Reproduced live, and where the wait goes

```
curl -s -o /dev/null -D - "$BAINLUCK_API/api/events/search-suggestions"
x-timing-split: wall=8009.5;db=7914.0;app=95.4;q=5;maxq=7732.6;router=2.4
```

**7,732 of 8,009 ms is one statement.** `q=5` rather than the ring's `q=7` was the clue to
which: the served payload had six "Tips off in N min" chips from section 2 and **two
"Surging/Falling" chips from section 3**, so the window was not full and section 3's query
ran — the two extra statements in the `q=7` reads are sections 4 and 5.

Sections 1 and 2, `EXPLAIN (ANALYZE, BUFFERS)` on production the same minute: **6 ms each**,
129 and 120 shared blocks, both on `ix_events_status` / `ix_events_status_commence`. They are
not the wait and never were.

Section 3 is:

```sql
SELECT ... FROM futures_outcomes fo
JOIN futures_markets fm ON fm.id = fo.market_id
WHERE fm.status = 'open'
  AND fo.probability_change_24h IS NOT NULL
  AND abs(fo.probability_change_24h) > 0.02
ORDER BY abs(fo.probability_change_24h) DESC
LIMIT 5
```

Production plan, fingerprint `775d6ff2b74e14cd`:

```
Limit                                      9,498 ms
  Nested Loop        <- futures_markets, ABOVE the sort
    Gather Merge
      Sort    external merge, 5,736 kB to DISK
        parallel Seq Scan futures_outcomes
146,425 shared blocks (~1.14 GB)   Shared I/O Read Time 15,428 ms
Temp Written 1,409 blocks
```

`abs()` is not indexed — but that alone would still allow a bounded top-N sort. **The join
sits above the sort, so `LIMIT 5` cannot bound it**: Postgres must sort every survivor because
the join might eliminate any of them. That is the difference between a 5-row heapsort and a
5,736 kB external merge, and it is the mechanism neither prior queue named.

## 3. The finding: the fix was already in the repo, shipped, proven, and measured

`app/routes/events.py` carried a 33-line comment saying the permanent form is an expression
index, that DDL is integrator-owned (ruling 080), and that it was REQUESTED and parked as
**P124-1**. `app/utils/search_suggestions_cache.py` (LAT-P139) then wrote, under "WHAT IS NOT
DONE HERE, NAMED SO IT IS A DECISION":

> **The build is not made faster.** The 8-13 s is untouched […] P124-1 (the expression index)
> remains the fix for the build itself and remains parked.

Both are wrong, and the counter-example was one route file over the whole time.
`/api/futures/movers` ran the **identical** `ORDER BY abs(probability_change_24h) DESC` and
LAT-P108 fixed it on **2026-08-28**, two days before LAT-P124, with no DDL:

> `futures_markets.max_movement_24h` is, by the definition of the task that writes it
> (`update_max_movement`, every 10 min), `MAX(ABS(outcome.probability_change_24h))` for that
> market. So an outcome whose |change| beats the smallest max_movement in the pool must live
> in a market already inside the pool: the pool is a provable SUPERSET of the answer, not a
> sample of it.

11,129 ms → 627 ms, with a rollback flag and an equivalence gate. It shipped. Then two
consecutive queues on the neighbouring surface parked an index request against the same
statement.

**Why it was missable, written down so the class is:** LAT-P124 searched for an INDEX that
could serve `abs(...)`, found none, and correctly concluded none exists. The question that
would have found the answer is not "what index serves this?" but "has anything else in this
repo ranked outcomes by movement?" — a search on the *problem*, not on the *remedy*. A parked
DDL request is a comfortable place to stop, because it converts "I could not fix this" into
"somebody else owns the fix".

## 4. The measurement

Pooled arm, same production minute:

```
Limit                                        588 ms
  Sort   top-N heapsort, in MEMORY
    Nested Loop
      Index Scan ix_futures_markets_max_movement   400 rows,   7.7 ms
      Index Scan ix_fo_market_movement               5 rows,   1.4 ms
3,629 shared blocks
```

| | legacy | pooled |
|---|---|---|
| execution | 9,498 ms | **588 ms** |
| shared blocks | 146,425 (~1.14 GB) | **3,629** |
| sort | external merge, 5,736 kB to disk | **top-N heapsort, memory** |

🔴 **AND THEN THE SAME PAIR AGAIN ON THE STATEMENTS THE SHIPPED CODE ACTUALLY
EMITS**, compiled out of `_build_suggestion_movers_query` with `literal_binds`
and posted verbatim — not the four-column hand-written probe above, the whole
22-column ORM select:

| | legacy (`0a68e1248032ba92`) | pooled (`c62f86daa17baf13`) |
|---|---|---|
| execution | 5,840 ms | **305 ms** |
| shared blocks | 174,806 | **3,572** |
| plan | Hash Join over a 116,497-row Seq Scan | Index Scan × 2, top-N heapsort |

**49× fewer blocks, 19× faster on the wall.**

⚠️ Note the legacy arm's plan is NOT stable between those two probes — the
four-column form took Gather Merge → external merge to disk, the full-column
form took a Hash Join with a top-N heapsort in 27 kB. Same statement class, same
afternoon, two plans, and one of them looks reassuring. Read the BLOCKS: 146,425
and 174,806. LAT-P124 wrote "read the blocks, not the milliseconds" and it was
right for a second reason it did not know about.

**Equivalence, verified on production 2026-08-30, ONE ATOMIC STATEMENT PER PROBE** so both
arms read the same snapshot — `update_max_movement` rewrites the column every ten minutes, so
a two-statement comparison would be churn rather than evidence:

```
legacy top-5   ->  5 of  5 inside the pool of 400     fp b2e02339a8f83f30
legacy top-20  -> 20 of 20 inside the pool of 400
legacy top-50  -> 50 of 50 inside the pool of 400
```

The 10× and 25× probes are margin: the section can only ever use five.

A two-arm value-vector comparison in one statement was ATTEMPTED and could not be run — the
`db-query` row path has a hard 10 s timeout and `timeout_ms` is only honoured with
`explain: true`, so the legacy arm alone (9.5 s) does not leave room for the pooled arm beside
it. The superset probe above is the atomic form that does fit, and it is the property the
reduction actually needs. Recorded rather than quietly swapped.

## 5. What changed, and what deliberately did not

* `app/utils/movement_pool.py` — **new**. The bound, its proof, and its precondition, in one
  place. `routes/futures.py` now calls it and emits byte-identical SQL; the pool SIZE stays
  with each caller, because `/movers` scales it with a caller-supplied `limit` and this
  section asks for a fixed five.
* `routes/events.py` — `_build_suggestion_movers_query(pooled=...)`, both arms, plus
  `SEARCH_SUGGESTIONS_MOVERS_POOLED=0` as rollback AND as the equivalence oracle.
* **Unchanged:** the `> 0.02` threshold, the `open`-only status list (deliberately not widened
  to `/movers`' `('open','active')` — that would change which chips a person sees), the limit
  of five, the cache tier, the beat schedule. `beat_schedule_change: FALSE`, `ddl: NONE`.
* **P124-1 is WITHDRAWN**, not parked a third time. The expression index would still help, but
  nothing is waiting on it now, and a parked request that nothing needs is a queue item
  pretending to be a blocker.

**What the bound costs, stated rather than discovered later:** an outcome in a market whose
`max_movement_24h` has never been written is outside the pool and therefore outside the
answer, however far it has moved. Same trade `/api/futures/movers` has shipped since
2026-08-28. `test_a_market_with_null_max_movement_is_out_of_the_pool` pins it.

## 6. A floor the superset proof does not mention

Found by the new suite failing, not by reading the argument. With one outcome per market, a
pool of N markets can supply at most N rows — so a pool SMALLER than the limit truncates the
answer even though every market in it was correctly chosen. The proof is about *which markets
qualify* and is silent on *how many rows they hold*. Production has 400 against an ask of 5, so
the property holds with 80× of headroom and can only be broken by an edit;
`test_the_pool_can_never_be_smaller_than_the_ask` is the edit-detector.

## 7. Gates

| gate | result |
|---|---|
| `tests/test_search_suggestions_movers_pool_lat_p151.py` | 40 passed, **EXIT CODE 0** read by value |
| `test_futures_movers_pool_bound.py` + `test_route_search_suggestions_cold_p124.py` | 57 passed, EXIT CODE 0 |
| `test_search_suggestions_mirror_lat_p139.py` + `test_futures_movers_warm_p115.py` + `test_startup.py` | 57 passed, EXIT CODE 0 |
| mutation battery | **20/20 killed**, 0 survived, 0 harness failures, EXIT CODE 0 |
| `scan_mutation_residue.py` | CLEAN, 364 needles verified in place, EXIT CODE 0 |
| full backend suite | see the cert block — run to completion with the exit code captured by value |
| frontend | **not run, and not applicable** — zero files under `frontend/` in this diff |

## 8. Where I think I am most likely wrong

1. **The `open`-only status list.** `/api/futures/movers` counts `('open','active')` and this
   section counts `open`. Both arms agree, so the change is not a regression — but if `active`
   is the status live markets actually carry on some source, then section 3 has been quietly
   under-selecting since before this queue and the pool inherits that. Not investigated: it
   would be a product change inside a latency queue.
2. **`_seed` derives `max_movement_24h` from its own outcomes**, so the SQLite suite can never
   catch a production population where the column has drifted. The precondition test seeds by
   hand to cover exactly that, but it covers ONE drift shape, not the distribution.
3. **The 588 ms is one measurement**, taken with the pool's own index warm. The block count
   (3,629 vs 146,425) is the number to trust — LAT-P124's own note says read the blocks, not
   the milliseconds, and it was right.
4. **`renders_to_something` interacts with a cheaper build in a way I have not measured.** A
   sub-second build makes the reader's fall-through cheap, which makes the mirror's 300 s
   ceiling matter less — but I did not re-derive whether the ceiling is still the right number
   now that blocking costs 0.6 s instead of 9 s. It is now a latency question rather than a
   correctness one, which is a better place for it to be, but it is not answered here.
