# LAT-P093 — where the feed's cache-miss build actually spends its time

**Cycle:** LAT-P093 · **Date:** 2026-08-26 · **Identity:** `LAT-P093-20260826-w31534`
**Directive:** Fable 2026-08-25, pasted and reviewed by Alex — *"break down where the 4,502ms goes
on a feed cache miss using your existing instrumentation, and BUILD the biggest reduction."*
**Ship:** the feed loads fast even on a cache miss.

---

## 0. The instrument, and why this is not another stakeout

LAT-P008, P009 and P011 each hand-fired a spaced benchmark hoping to catch the feed tail live and
measured 2-in-23, 6-in-59, then 1-in-345. The phenomenon is episodic; a one-hour stakeout is a coin
flip. That is why `/api/admin/latency-slow-events` exists (#1459): a Redis ring that records **every
request over 5s together with its `X-Feed-Stages` breakdown**, capped at 500 entries, 7-day TTL.

This decomposition is a **read of that ring**, not a fresh probe. No `/api/feed` load was generated
to produce it.

    GET /api/admin/latency-slow-events?limit=300&min_ms=0     2026-08-26 19:13:11Z
    ring_used 500 / 500 · unparseable 0 · oldest 541,267s · newest 27,390s

**Cohort: 145 `/api/feed` requests whose `x-feed-cache` was `miss`.** Total p50 **7,243 ms**
(p90 17,476 ms, max 25,708 ms).

⚠️ **This cohort is the >5s TAIL, not the whole miss population.** LAT-P091's 4,502.7 ms is the p50
over ALL misses; the ring only admits requests above 5,000 ms. So the absolute numbers below are
tail numbers and the **proportions** are the finding. Said plainly rather than left for a reader to
discover: this decomposition cannot tell you the p50 miss's stage split, only which stages dominate
when a miss is slow. Every claim below is scoped that way.

---

## 1. The breakdown

Per-stage p50 across the 145 misses (`n` = misses where the stage appears in the top-8 header —
`X-Feed-Stages` is truncated to eight, so a stage's absence is "not in the top eight", never zero):

| stage | n | p50 ms | max ms | note |
|---|---:|---:|---:|---|
| `futures` | 142 | **3,934.0** | 21,969.0 | **parent** — contains every `futures.*` below |
| `concepts` | 140 | 1,441.6 | 16,439.0 | already principal-shared (#2143); this is the cold build |
| **`futures.canonical_counts`** | 126 | **1,428.4** | 15,848.3 | **largest LEAF — LAT-P093's target** |
| `events` | 144 | 1,203.2 | 6,646.5 | |
| `futures.market_load` | 137 | 997.9 | 5,944.5 | hydrates ORM rows; unshareable (#2107) |
| `futures.scoring_loop` | 132 | 288.1 | 667.9 | pure Python |
| `personalization` | 87 | 193.5 | 2,977.4 | the only principal-DEPENDENT stage |
| `team_enrichment` | 68 | 184.1 | 558.8 | |
| `golf` | 104 | 59.4 | 328.4 | |
| `futures.interestingness_cache` | 14 | 378.2 | 1,007.4 | |
| `review_decisions` | 35 | 39.4 | 1,146.3 | |
| `ranking` | 21 | 18.7 | 73.4 | |
| `futures.candidate_base_fresh` | 2 | 82.4 | 117.9 | candidate base v2 doing its job |
| `golf.base_read` | 8 | 3.6 | 87.8 | |

Layer split over the same cohort, from the ring's own `db_ms`/`app_ms`/`router_queue_ms` fields:

| layer | mean ms | share |
|---|---:|---:|
| **db_ms** | **7,748** | **71.2 %** |
| app_ms | 1,837 | 28.3 % |
| router_queue_ms | 8 | 0.6 % |

**The build is database-bound, not CPU-bound and not queued.** Mean 18.7 queries per miss, mean
worst-query 3,529 ms.

### The single line that chose the target

Grouping the misses by their own dominant stage and reading `max_query_ms` — the slowest individual
statement in that request:

| dominant stage | n | worst-query p50 | queries p50 | total p50 |
|---|---:|---:|---:|---:|
| `futures` | **125** | **1,639.5 ms** | 21.0 | 7,093.3 ms |
| `concepts` | 15 | 6,792.7 ms | 14.0 | 13,351.3 ms |
| `events` | 5 | 2,496.4 ms | 16.0 | 7,242.7 ms |

In **125 of 145 misses** the slowest single statement in the whole request is ~1,640 ms and sits
inside the futures stage. `futures.canonical_counts` is 1,428 ms p50 of that stage. They are the
same query. The worst statement on a cache-miss feed build was **one aggregate**, and across the
cohort the single worst query is **38 % of all database time** (p50).

---

## 2. What that query was doing

`_query_canonical_source_counts` answers, per candidate market key: *which of our sources carry
this canonical market?* The answer is used for the cross-source agreement bonus in scoring.

Production shape, measured 2026-08-26:

| quantity | value |
|---|---:|
| `futures_markets` rows | 871,381 |
| … carrying a `canonical_market_key` | 345,334 |
| **DISTINCT `canonical_market_key`** | **747** |
| **DISTINCT `source`** | **4** (`kalshi`, `polymarket`, `datagolf`, `odds_api`) |

So the answer for one key is at most four short strings, and the average key has ~462 rows behind
it. The implementation was `count(DISTINCT source)` + `array_agg(DISTINCT source)` grouped by key.
`EXPLAIN (ANALYZE, BUFFERS)` over a real 150-key candidate set:

```
Aggregate (Sorted)  actual rows=150  time=1522.3ms  shared hit=70,779
  -> Index Only Scan using ix_fm_canonical_source_count
       actual rows=302,027  time=977.9ms
```

**302,027 index rows read to emit 150.** The index is the right one and the aggregate is correct;
the SHAPE is wrong. A DISTINCT aggregate has to visit every duplicate to learn it is a duplicate,
so its cost tracks the one quantity that grows without bound — the row count — while the answer it
produces is bounded by 747 × 4.

---

## 3. The fix, and the two wrong versions of it that came first

A skip scan: one `LIMIT 1` probe of the covering partial index
`ix_fm_canonical_source_count (canonical_market_key, source)` per (key, source) pair. 150 keys ×
4 sources = 600 probes.

```
Nested Loop Semi   actual rows=150  time=27.7ms  shared hit=2,118
  -> Index Only Scan using ix_fm_canonical_source_count  loops=600
```

Six **interleaved** A/B round trips against production (interleaved so buffer-cache warmth and
database load fall on both arms equally):

| round | BEFORE | AFTER |
|---|---:|---:|
| 1 | 2,094.7 ms | 211.9 ms |
| 2 | 1,775.8 ms | 298.9 ms |
| 3 | 1,706.4 ms | 19.3 ms |
| 4 | 1,449.2 ms | 36.0 ms |
| 5 | 1,627.8 ms | 121.0 ms |
| 6 | 1,295.4 ms | 231.6 ms |
| **p50** | **1,667.1 ms** | **166.4 ms** |

**−1,500.6 ms p50 · 90.0 % · 10.0×.** The AFTER spread (19–299 ms) is admin round-trip overhead,
not query time; the plan-level number is 27.7 ms.

**Equivalence is measured, not argued.** Both statements were executed against production over all
150 keys and compared key by key: identical counts, identical sorted source-name lists, **zero
diffs**.

### The source universe is derived, not written down

Four sources is a fact about today, not a contract. A hardcoded list under-counts silently the day
a fifth source ships — the market stops earning its cross-source bonus, and a wrong count has the
same type as a right one (gotcha #53). `SELECT DISTINCT source` would read all 871,381 rows, so the
universe comes from a loose index scan (recursive CTE) over `ix_futures_markets_source`: **4 rows,
24.7 ms, 135 buffers**, folded into the same statement so it costs one round trip.

### Two shapes that return a feed and are wrong

Both were written first. Both are pinned by the gate rather than remembered.

1. **Flattening the LATERAL** into a cross join with the `EXISTS` in the outer `WHERE` lets the
   planner pull the semi-join up and hash it, restoring an Aggregate over the full index:
   cost 89,601, 872,813 planned rows, **2,272–3,170 ms measured** — *slower than the aggregate it
   replaces.* It is also the more natural thing to write.
2. **Omitting `.correlate()`** makes SQLAlchemy render the candidate `VALUES` list a second time
   inside the `EXISTS` as an independent FROM entry. The predicate becomes "does ANY candidate key
   carry this source", so **every key comes back carrying every source** — uniformly generous,
   ranks fine, renders fine, reports nothing.

`tests/test_feed_canonical_counts_skip_scan.py` holds both: the candidate key list must appear
exactly once in the compiled SQL, and the probe must stay inside a LATERAL.

---

## 4. What was NOT taken, and why

**`concepts` (1,441.6 ms p50) — parked, not dropped.** Its own cohort (n=15, dominant-stage
`concepts`) carries a **6,792.7 ms** worst query and a 13,351 ms total p50 — a different and rarer
pathology than the one fixed here, and the concept build is already shared across principals
(#2143), so the cost lands only on a genuinely cold window. Filed to
`PARKED-MEASUREMENTS.md`; it needs its own diagnosis, not a guess.

**`futures.market_load` (997.9 ms) — refused.** It hydrates live ORM rows. Sharing those is #2107
verbatim, and a latency lane does not widen a live P0's blast radius to buy 600 ms. This is the
same refusal LAT-P084 recorded.

**Serial source fan-out made concurrent — refused as out of authority.** `events`, `golf`,
`concepts` and `futures` run serially, and inside `_compute_ordered_candidate_ids` the candidate
pools run serially too (`for name, query, _limit in pool_specs: await db.execute(query)`). Making
them concurrent requires more than one connection, because an `AsyncSession` is not
concurrency-safe. The code already carries an explicit standing decision against exactly this —
*"no new blind parallelism, no `gather()` on this AsyncSession"* (Queue 305) — and the candidate
pools it names are already answered from candidate base v2 (`futures.candidate_base_fresh`, 82.4 ms,
n=2) rather than run inline. Overturning that decision to buy concurrency is a call for Alex or
Fable, with a connection-pool budget attached; it is not a thing to slip into a latency queue.

**Payload assembly — not a target on the evidence.** `app_ms` is 28.3 % of the build and
`futures.scoring_loop` (the largest pure-Python stage) is 288.1 ms. The build is database-bound.

---

## 5. Honest scope of the claim

* The fix removes ~1.4–1.5 s from the cache-miss build path. Against LAT-P091's 4,502.7 ms miss p50
  that is roughly **a third of the miss cost** — a real cut, and **not the whole ship**. The 4,502 ms
  cold build is wounded, not dead.
* The before/after is measured on the **query**, which is what the directive asked for
  (*"before/after on the build path's own timing"*) and what P091-1 says organic p50 cannot
  resolve. **A post-deploy `X-Feed-Stages` read of `futures.canonical_counts` on a real miss is the
  confirming evidence and it is OWED** — this branch is not deployed.
* n=6 per arm on the A/B. The plan-level difference (302,027 rows vs 600 probes; 70,779 buffers vs
  2,118) is the structural claim and does not depend on the timing sample.
