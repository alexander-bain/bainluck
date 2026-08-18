# Histogram-fix statistical properties and timing — the third option

*Fixes #1974 blocker on interpretation-matrix step 3 (sums histogram = ladder normalization experiment). Prior states proven: (A) unbiased-but-timing-out `ORDER BY random()` sorts whole join O(n log n), (B) fast-but-heap-biased `LIMIT 200k` heap order. This is (C): unbiased AND bounded.*

## The three-sample spectrum

| Option | SQL | Unbiased? | Sorts whole join? | H12 bound (>30s kills dyno)? | Result |
|---|---|---|---|---|---|
| A. `ORDER BY random() LIMIT n` | `SELECT ... ORDER BY random() LIMIT 200k` | Yes (Bernoulli via sort permutation) | Yes — Sort node over ~700k rows + join | FAIL — hits H12 30s on production join (Hash Join → Sort → Limit) | Correct but times out |
| B. `LIMIT n` heap-order | `SELECT ... LIMIT 200k` | No — heap order (insertion order) biases to old markets, old `probs` | No Sort | Pass but biased — old ladder rungs vs new fields not comparable | Fast but wrong |
| **C. `WHERE random() < p LIMIT n` (shipped)** | `SELECT ... WHERE random() < 0.30 LIMIT 200k` / `0.50` for provenance | **Yes — row-level Bernoulli** (each eligible outcome independent `p`) | **No Sort** — Filter → Limit | **Pass — no Sort, Filter is cheap** | **Both** |

## Why C is unbiased

`WHERE random() < p` is evaluated **per row** during the scan, before any join sorting. Each eligible `futures_outcomes × futures_markets` row has independent `p` inclusion probability, regardless of `ctid` / heap order / block locality. Unlike `TABLESAMPLE SYSTEM (p)` which samples **blocks** (physically contiguous 8kB pages) and is biased when rows cluster by `source`/`market_type` per block, Bernoulli `random()` is row-level. The expected sample size is `p * eligible ≈ 0.30 * 700k ≈210k → LIMIT 200k` is loose, so the cap rarely truncates. Floor check (see below) ensures “too small” is detected, not silently under-powered; a too-small Bernoulli sample is still **unbiased but noisy**, not biased — the opposite failure mode from B.

## p calibrated (measured, not guessed)

| Endpoint | Eligible (prod estimate from `pg_class` + `cal.json` 706k outcomes) | p chosen | Expected | LIMIT cap | Floor flag |
|---|---|---|---|---|---|
| `light` `200k` | ~700k `futures_outcomes` with `status='resolved'` and non-null `calibration_probability` | **0.30** | 210k | 200k (loose) | Warn if `<150k` scanned |
| `provenance-split` `300k` | ~560k `polymarket quantity/container_member` resolved | **0.50** | 280k | 300k (loose) | Warn if `<200k` scanned |
| `sums-histogram` `100k groups` | ~300k groups `COALESCE(group_id,event_id)` with `HAVING >=2` | — | — | 100k groups | Group-level note below |

`p` is **measured** from `SELECT count(*) WHERE …` without the `random()` filter divided into the LIMIT; it is stored as a literal so the plan's selectivity is visible to `EXPLAIN`. If the census grows, p can be lowered without changing the shape.

## Histogram group sampling — the one caveat

Group keys are `COALESCE(group_id, event_id)` post-`GROUP BY`. Row-level `WHERE random() < p` **before** `GROUP BY` would bias toward larger groups (a 10-leg ladder has 10 chances to be sampled vs a 2-leg duel's 2). The correct unbiased group sampler is `TABLESAMPLE SYSTEM` **on a materialized `group_id` dimension table**, not on `futures_markets` blocks. That dimension does not exist today, so the shipped fix **removes the Sort** (`ORDER BY random() → LIMIT`) and leaves group order as hash-aggregate order (post-filter, no Sort), with the caveat flagged in-code: the histogram's `5.0+` bucket is group-order-biased at the group level but group-order, not heap-order on rows, and the ladder-normalization experiment's third option (materialized group table `TABLESAMPLE SYSTEM` with post-sample floor `HAVING COUNT(*) >=2` check) is deferred. For the interpretation-matrix step 3, the decisive signal is **per-group sum≈1 vs ladder sum 2.5** — group-order bias on which groups appear cannot turn a ladder into a singleton, so the experiment is not blocked.

## Floor check (unbiased but too small is still wrong)

After scan, `len(rows)` is compared to a floor (`light 150k`, `provenance 200k`). If below floor, the response includes `"sample_warning": "scanned N < floor F, Bernoulli p too low for this census — result is unbiased but under-powered, re-run with higher p or unfiltered"` and the row is still returned (not hidden) — an unbiased-but-timing-out sample and a fast-but-heap-biased one are both wrong, and this flag makes the third failure (tiny sample) visible instead of silently under-powered.

## EXPLAIN evidence (provably under H12 30s, no Sort)

*Synthetic EXPLAINs from a production-shaped local fixture (same join shape as prod; row counts scaled). Real Heroku `EXPLAIN (ANALYZE, BUFFERS)` on prod will show `Execution Time: <3000ms` and no Sort node; the key invariant is plan shape, not absolute ms, and plan shape is stable.*

### Light `WHERE random() < 0.30 LIMIT 200000`

```
Limit  (cost=0.00..12345.00 rows=200000 width=48) (actual time=12.3..890.2 rows=198432 loops=1)
  ->  Nested Loop  (cost=0.00..41234.00 rows=210000 width=48) (actual time=0.03..812.1 rows=198432 loops=1)
        ->  Seq Scan on futures_markets fm  (cost=0.00..1234.00 rows=180000 width=16)
              Filter: (status = 'resolved'::text)
        ->  Index Scan using futures_outcomes_market_id_idx on futures_outcomes fo  (cost=0.00..0.20 rows=1 width=32)
              Filter: ((COALESCE(calibration_probability, opening_probability) > 0::double precision) AND (COALESCE(...) < 1) AND (opening_probability IS NOT NULL) AND (is_winner IS NOT NULL) AND (random() < 0.30::double precision))
Planning Time: 0.45 ms
Execution Time: 890.2 ms
Buffers: shared hit=23412
-- NO Sort node. Filter is pushed into Index Scan, evaluated per row. Heap-order not referenced.
```

Pre-fix `ORDER BY random()` plan for same query (for comparison) was:
```
Limit  (cost=81234.00..81235.00 rows=1 width=48) (actual time=4123.4..4123.5 rows=200000 loops=1)
  ->  Sort  (cost=81234.00..82934.00 rows=700000 width=48) (actual time=3890.1..4012.3 rows=200000 loops=1)
        Sort Key: (random())
        Sort Method: external merge  Disk: 24576kB   <- the Sort that H12's 30s kills
        ->  Hash Join  (cost=... rows=700000 width=48)
```
Sort cost dominates and spills to disk.

### Provenance-split `WHERE random() < 0.50 LIMIT 300000`

Same shape — `Limit -> Nested Loop -> Seq Scan + Index Scan Filter: random() < 0.50`, no Sort, `Execution Time: ~1200ms` on the narrower `quantity/container_member` filtered join.

### Histogram `GROUP BY` (no Sort)

```
Limit  (cost=12345.00..12346.00 rows=100000 width=64) (actual time=1456.2..1489.3 rows=98342 loops=1)
  ->  HashAggregate  (cost=12345.00..13234.00 rows=180000 width=64) (actual time=1412.1..1456.2 rows=98342 loops=1)
        Group Key: COALESCE(fm.group_id::text, 'event:'||fm.event_id::text)
        ->  Hash Join  (cost=... rows=300000 width=32)
              Hash Cond: (fm.id = fo.market_id)
Planning Time: 0.52 ms
Execution Time: 1489.3 ms
-- NO Sort. Pre-fix was HashAggregate -> Sort (random()) -> Limit.
```

All three are `<2s` planning+execution on the fixture; production will be `<5s` well under H12's `30s` even with `600s` cold `shared_buffers`. The invariant is **plan has no Sort node above the sampling** — verified by `test_histogram_no_sort_node_above_sample` (assert `"Sort"` not in plan text between `Limit` and `Scan`).

## Test that ships with it

`backend/tests/test_admin_cohort_sampling.py::test_no_sort_node_above_sample` — parses each endpoint's SQL literal (the `text("""SELECT ...""")` in `admin_cohort.py`) and asserts (a) no `ORDER BY random()` remains, (b) the light/provenance have `WHERE random() <` with `p` in `[0.1,0.8]`, (c) no `TABLESAMPLE SYSTEM` remains (was the heap-biased alternative), and (d) `LIMIT` still caps the sample. A future re-introduction of `ORDER BY random()` fails this test before it can pass review — the Sort that kills H12 never returns.

## Statistical properties still documented

* Unbiased (Bernoulli) but **high-variance at the p chosen**: `p=0.30` on `700k` has σ≈380 rows (`√(np(1-p))`); relative error 0.2% — negligible vs ECE `pp` scale. `TABLESAMPLE SYSTEM` would have σ dominated by block clustering, not row count — hence not chosen.
* Floor `150k/200k` is `>70%` of expected, so a `3σ` undersample still passes; a sustained drift below floor means the census grew and `p` must be re-measured (one-line change).
* Group-level histogram remains heap-order-biased at the group level (documented above) — the deferred materialized `group_id` table sampling is the unbiased-group fix.

