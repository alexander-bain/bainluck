# LAT-P094 — the next biggest stage on a feed miss, and what it was doing

**Cycle:** LAT-P094 · **Date:** 2026-08-26 · **Identity:** `LAT-P094-20260826-w14381`
**Directive:** Fable 2026-08-26, pasted and reviewed by Alex — *"with `canonical_counts` dying and
the response cache merging, read your own ring: what is the NEXT biggest stage on a feed miss, and
is it worth a session? If yes, build it."*
**Ship:** the feed loads fast even on a cache miss.

---

## 0. The read, and what it is scoped to

`GET /api/admin/latency-slow-events?limit=500&min_ms=0`, 2026-08-26 20:07:16Z.
`ring_used 500 / 500 · unparseable 0 · oldest 544,512s · newest 30,634s`.

**Cohort: 166 `/api/feed` requests whose `x-feed-cache` was `miss`** — 21 more than LAT-P093 saw,
same instrument, no load generated. Total p50 **7,314.2 ms** (p90 17,476.0, max 25,707.7).

⚠️ Same scope caveat as LAT-P093, restated rather than inherited: the ring only admits requests
above 5,000 ms, so this is the **tail** of the miss population, not its p50. LAT-P091's 4,502.7 ms
is the p50 over ALL misses. The absolute numbers below are tail numbers; the **proportions** are
the finding.

---

## 1. The stage table, with LAT-P093's target removed

| stage | n | p50 ms | max ms | note |
|---|---:|---:|---:|---|
| `futures` | 162 | 3,947.7 | 21,969.0 | **parent** — contains every `futures.*` below |
| **`concepts`** | 161 | **1,447.2** | 16,439.0 | **the largest remaining stage — LAT-P094's target** |
| ~~`futures.canonical_counts`~~ | 144 | ~~1,338.4~~ | ~~15,848.3~~ | killed by LAT-P093 (`-82`, unmerged) |
| `events` | 165 | 1,212.9 | 8,201.5 | |
| `futures.market_load` | 155 | 1,032.2 | 7,519.9 | hydrates ORM rows; unshareable (#2107) |
| `futures.scoring_loop` | 150 | 297.4 | 667.9 | pure Python |
| `futures.interestingness_cache` | 16 | 371.5 | 1,007.4 | |
| `personalization` | 102 | 168.6 | 2,977.4 | the only principal-DEPENDENT stage |
| `team_enrichment` | 74 | 180.4 | 558.8 | |
| `golf` | 123 | 60.0 | 328.4 | |
| `review_decisions` | 39 | 39.4 | 1,146.3 | |
| `ranking` | 24 | 17.6 | 73.4 | |
| `futures.candidate_base_fresh` | 2 | 46.9 | 117.9 | candidate base v2 doing its job |
| `golf.base_read` | 11 | 3.8 | 87.8 | |

Grouped by each miss's OWN dominant stage:

| dominant stage | n | worst-query p50 | queries p50 | total p50 |
|---|---:|---:|---:|---:|
| `futures` | 138 | 1,639.5 ms | 21.0 | 7,004.5 ms |
| **`concepts`** | **18** | **6,012.3 ms** | 14.0 | **12,627.7 ms** |
| `events` | 10 | 2,766.7 ms | 16.0 | 8,089.9 ms |

**`concepts` is the answer to the directive's question twice over.** It is the largest remaining
stage at the p50, and it is the dominant stage of the 18 worst misses in the ring — the ones that
take 12.6 s and whose worst single statement is 6.0 s. `events` (1,212.9 ms) is a close third and
`futures.market_load` (1,032.2 ms) is fourth but is already ruled unshareable by #2107.

**Is it worth a session? Yes** — ~1.45 s of a 4.5 s p50 miss, and it owns the tail.

---

## 2. What the stage was doing

The concept tier has three sources, and each read its own open markets:

| source | `llm_sport_category` | rows it wanted |
|---|---|---:|
| `list_ufc_card_concepts` | `mma` | 168 |
| `list_f1_gp_concepts` | `motorsports` | 144 |
| `list_cycling_concepts` | `cycling` | 3 |

`futures_markets` carries **871,381** rows, of which **50,749** are `status = 'open'`. Every index
on that table that includes `llm_sport_category` is partial on `event_id IS NULL`
(`ix_fm_feed_open_sports`), and the listers cannot use it — 32 of their 315 rows are linked to an
event. So all three reads resolve to the same plan. `EXPLAIN (ANALYZE, BUFFERS)`, production
2026-08-26:

```
Index Scan using ix_futures_markets_status  on futures_markets
  Index Cond: status = 'open'
  Filter: llm_sport_category = 'mma'
  Actual Rows 168 · Rows Removed by Filter 50,581 · Shared Hit 27,839 · 523.9 ms
```

**50,749 rows visited to emit 168, three times over, for 315 rows in total.**

This is the same defect LAT-P093 killed one stage over, wearing different clothes: the cost tracks
a quantity that grows without bound (every open market on the platform) while the answer is
bounded by the concept tier's own size (three sports' worth of cards). The difference is that here
the fix is **not a better query** — the single scan IS the same query. It is doing it once for
every source instead of once per source.

---

## 3. The measurement

Six interleaved A/B round trips against production, `Execution Time` taken from
`EXPLAIN (ANALYZE, BUFFERS)` so the number is the database's and not the network's:

| | p50 exec | rows scanned | rows emitted | buffers |
|---|---:|---:|---:|---:|
| A — three separate reads | **1,109.5 ms** | 50,749 × 3 | 315 | 27,839 × 3 |
| B — one combined read | **453.4 ms** | 50,749 | 315 | 27,839 |
| **delta** | **−656.1 ms (59.1 %, 2.45×)** | | | |

Per-arm p50: `mma` 387.2 ms, `motorsports` 377.5 ms, `cycling` 428.3 ms. The cycling read — three
rows — cost the same as the other two, which is the whole shape of the defect in one line.

**Correctness: zero diffs.** Both shapes run against production over all three categories, rows
re-projected per source and compared as sorted sets: 308 rows (160 mma / 145 motorsports / 3
cycling — the population moved between measurements as markets opened and closed), **identical in
all three buckets**.

---

## 4. What was refused

**Two arms instead of one.** 283 of the 315 rows have `event_id IS NULL` and can be read through
`ix_fm_feed_open_sports` in **0.6 ms** (238 buffers). The other 32 rows are linked to events, and
there is no index path for them — the linked arm still costs the full 27,839-buffer scan, measured
at 392.7–486.2 ms. A `UNION ALL` of the two measured 392.5–464.7 ms, i.e. **no better than the
single scan**, and it costs a second statement plus a shape that reads like an optimisation. Not
built.

**Filtering by `category_tags` (GIN-indexed).** Would be selective and index-driven, but two of the
32 linked motorsports rows carry `category_tags = []`. A filter that silently drops rows is the
exact failure class this repo refuses; a faster answer that is missing two markets is not the same
answer. Not built.

---

## 5. What is left, and why it is not in this commit

The remaining 453 ms is **still 50,749 rows scanned to emit 315**. No query rewrite fixes that.
The only thing that does is a partial index on `llm_sport_category WHERE status = 'open'`, which
is DDL — and DDL in this lane gets a pre-registered gate with the bar frozen **before** the index
exists (LAT-P090's standing rule after LAT-P088, plus gotcha #31: never
`CREATE INDEX CONCURRENTLY` in Alembic).

That spec is written and is the companion to this document:
`docs/audits/latency/lat-p094-open-category-index-gate-spec.md`.

---

## 6. Contamination introduced by this read, declared

This lane issued **24 `EXPLAIN (ANALYZE, BUFFERS)` statements** and 6 row-returning statements
through `POST /api/admin/db-query` while measuring. All are read-only `SELECT`s against
`futures_markets` and `pg_indexes`; none writes a row, and none touches `/api/feed`, so the ring
this decomposition is read from contains **no request this lane generated**. Two `/api/events/search`
and two `/api/events/search` repeats were issued for the #1916 item (§ report); those write
`search_query_logs`, which is not read here. Stated because ruling 127's general form is that an
instrument writing to what it reads must say so.
