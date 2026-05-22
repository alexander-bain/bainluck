# Search FTS Readiness Runbook

Issue [#447](https://github.com/alexander-bain/bainluck/issues/447) is a decision gate, not a migration task. The current `/api/events/search` implementation uses query-time weighted PostgreSQL full-text ranking and keeps broad `ILIKE` recall. Do not add stored `ts_vector` columns, triggers, or indexes until production traces show that query-time ranking is a real latency bottleneck.

## Evidence To Collect

Use at least 7 days of production search traces when possible. The export should include:

- Query text (`query`, `q`, `search_query`, or one query per TXT line)
- Endpoint latency in milliseconds (`latency_ms`, `duration_ms`, `response_time_ms`, or `elapsed_ms`)
- Result count or zero-result flag when available
- Click flag when available
- Timestamp when available

Run the read-only audit:

```bash
python3 scripts/audit_search_fts_readiness.py --queries-file /path/to/search-traces.csv --no-db
```

When endpoint traces look slow, add database plan evidence from a production follower or a short read-only production window:

```bash
DATABASE_URL="$(heroku config:get DATABASE_URL -a bainluck-api)" \
python3 scripts/audit_search_fts_readiness.py \
  --queries-file /path/to/search-traces.csv \
  --plan-limit 25
```

The script sets the database session read-only and runs `EXPLAIN (ANALYZE, BUFFERS, FORMAT JSON)` for representative events, futures, and teams searches. It does not mutate schema or data.

## Decision Criteria

Keep query-time FTS unless all of these are true:

- The trace sample has at least 500 rows and 50 unique queries, preferably across 7+ days.
- Search endpoint latency is materially high: p95 >= 300ms or p99 >= 750ms.
- Representative database plans are also materially high: any surface p95 >= 150ms or max >= 750ms.
- The slow plans point at search ranking/vector computation or sort cost, not unrelated response formatting, network, odds snapshot loading, or relevance/content gaps.

Stored vectors are not the fix for poor relevance, zero-result intent, missing markets, or low search-result click-through. Those should become separate search quality issues.

## If Stored Vectors Become Justified

Open a new migration spike before implementation. That spike should benchmark:

- Stored weighted vectors for `events`, `teams`, and `futures_markets`
- GIN indexes on those vectors
- Maintenance strategy for `futures_outcomes` text aggregation
- Trigger/backfill cost on Heroku Postgres
- Before/after `EXPLAIN ANALYZE` on the same trace-derived query set

Only ship a migration if the benchmark clearly beats query-time FTS without introducing fragile trigger maintenance.
