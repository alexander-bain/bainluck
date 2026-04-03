# Pure-SQL Snapshot Collapse — OOM Fix Plan

**Priority:** #2 (actively OOMing on Heroku worker)
**Goal:** Rewrite `_collapse_table_for_partition` from Python-in-memory to pure SQL for constant memory usage.

---

## Current Problem

The Python collapse in `tasks/retention.py` loads ALL snapshot rows for each (event, bookmaker) partition into memory via `.all()`, walks them sequentially to find consecutive identical values, then deletes duplicates. For high-traffic events:

- A major event with 100+ polls/day × 8 bookmakers × 48+ hours = 40,000+ rows per event
- Each row becomes a full SQLAlchemy ORM object in Python memory
- Multiply across 200 events per task invocation = millions of objects
- Result: R14 Memory quota exceeded on Heroku worker (512MB)

## Tables Affected

| Table | Partition Key | Sub-Partition | Value Column |
|-------|-------------|---------------|--------------|
| `odds_snapshots` | event_id | bookmaker | home_win_probability |
| `win_prob_snapshots` | event_id | source | home_win_probability |
| `futures_odds_snapshots` | outcome_id | bookmaker | probability |

## Solution: Window Function + Batch DELETE

### Core SQL Pattern

Use `LAG()` to detect value changes, `SUM()` window to assign group IDs, then keep the first row per group and delete the rest:

```sql
-- Step 1: Identify groups of consecutive identical values
WITH value_groups AS (
  SELECT
    id,
    captured_at,
    valid_until,
    reading_count,
    home_win_probability,
    -- Assign group ID: increment when value changes from previous row
    SUM(CASE
      WHEN home_win_probability IS DISTINCT FROM
           LAG(home_win_probability) OVER (
             PARTITION BY event_id, bookmaker
             ORDER BY captured_at
           )
      THEN 1 ELSE 0
    END) OVER (
      PARTITION BY event_id, bookmaker
      ORDER BY captured_at
    ) AS group_id
  FROM odds_snapshots
  WHERE event_id = :event_id
    AND captured_at < :cutoff
),

-- Step 2: Find the keeper (earliest row) per group + aggregate metadata
group_summary AS (
  SELECT
    group_id,
    MIN(id) AS keeper_id,
    -- valid_until = latest timestamp in the group
    MAX(COALESCE(valid_until, captured_at)) AS final_valid_until,
    -- reading_count = sum of all readings in the group
    SUM(COALESCE(reading_count, 1)) AS total_reading_count,
    COUNT(*) AS group_size
  FROM value_groups
  GROUP BY group_id
  HAVING COUNT(*) > 1  -- Only groups with duplicates
)

-- Step 3: Update keepers with aggregated metadata
UPDATE odds_snapshots s
SET
  valid_until = gs.final_valid_until,
  reading_count = gs.total_reading_count
FROM group_summary gs
WHERE s.id = gs.keeper_id;

-- Step 4: Delete non-keeper rows (in batches)
DELETE FROM odds_snapshots
WHERE id IN (
  SELECT vg.id
  FROM value_groups vg
  JOIN group_summary gs ON vg.group_id = gs.group_id
  WHERE vg.id != gs.keeper_id
)
-- LIMIT batch via ctid range or subquery LIMIT to avoid long locks
```

### Key SQL Details

- **`IS DISTINCT FROM`** handles NULL correctly (unlike `!=` which returns NULL for NULL comparisons). This matches the Python `eq()` helper's behavior.
- **`PARTITION BY event_id, bookmaker`** matches the existing sub-partition strategy.
- **One event at a time** — the outer loop still iterates over event_ids (or outcome_ids), but each event's collapse is a single SQL roundtrip with zero Python memory.

## Implementation Steps

### Phase 1: SQL function (replaces `_collapse_table_for_partition`)

1. Write a new async function `_collapse_partition_sql(session, table, event_id, cutoff)` that:
   - Runs the CTE query above as raw SQL via `session.execute(text(...))`
   - Uses parameterized queries (`:event_id`, `:cutoff`) to avoid injection
   - Returns count of deleted rows

2. The outer loop in `_collapse_snapshots_impl` stays the same — it still discovers partitions and iterates. Only the inner function changes.

3. Batch the DELETE if needed: PostgreSQL can handle large DELETEs, but if any single event has 100K+ rows, use `LIMIT` on the delete subquery and loop until 0 rows affected.

### Phase 2: Per-table parameterization

Each table has different column names. Parameterize the SQL template:

```python
TABLE_COLLAPSE_CONFIG = {
    "odds": {
        "table": "odds_snapshots",
        "partition_cols": ["event_id", "bookmaker"],
        "value_col": "home_win_probability",
        "main_id_col": "event_id",
    },
    "winprob": {
        "table": "win_prob_snapshots",
        "partition_cols": ["event_id", "source"],
        "value_col": "home_win_probability",
        "main_id_col": "event_id",
    },
    "futures": {
        "table": "futures_odds_snapshots",
        "partition_cols": ["outcome_id", "bookmaker"],
        "value_col": "probability",
        "main_id_col": "outcome_id",
    },
}
```

Use f-string interpolation for table/column names (safe — these are hardcoded config, not user input) and `:param` binding for values.

### Phase 3: Verify correctness

- Run new SQL collapse against a known dataset and compare output to the Python version
- The existing 13 tests in `test_snapshot_collapse.py` test the Python logic — adapt them to also test the SQL path (or write new ones using raw SQL assertions)
- Key edge cases: NULL values, single-row partitions (no collapse needed), all-identical partitions (keep one, delete rest)

## Memory Analysis

| Approach | Memory per Event | Memory for 200 Events |
|----------|-----------------|----------------------|
| Current Python | ~5-50 MB (ORM objects) | 1-10 GB (OOM) |
| SQL approach | ~0 (query runs in Postgres) | ~0 |

The SQL approach uses constant memory in the Python worker — only the query text and result count come back.

## Migration Strategy

1. Deploy SQL version behind a feature flag (or just replace — the existing tests catch correctness issues)
2. Run against a few events manually via admin endpoint
3. Compare row counts before/after to verify no data loss
4. Switch beat schedule to use new implementation
5. Monitor Heroku worker memory (should stay well under 512MB)

## Risks

- **Long-running queries**: A single event with 100K+ snapshots could produce a slow query. Mitigate with LIMIT on delete + loop.
- **Lock contention**: The DELETE acquires row-level locks. Since collapse runs on old data (48h+ cutoff), this shouldn't conflict with live writes. But monitor for lock waits.
- **Index usage**: Ensure indexes on `(event_id, bookmaker, captured_at)` exist for the CTE's PARTITION BY + ORDER BY. Check with `EXPLAIN ANALYZE`.

## Estimated Effort

- SQL function + table parameterization: ~2 hours
- Test adaptation: ~1 hour
- Deploy + verify: ~30 minutes

This is a focused refactor — same algorithm, same outer loop, just moving the inner comparison from Python to SQL.
