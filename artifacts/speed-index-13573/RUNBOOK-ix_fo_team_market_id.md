# `#13573` — Attended index build: `ix_fo_team_market_id`

**PILLAR:** DISCOVER / INFRASTRUCTURE  
**SHIP:** Team pages (`/api/teams/{slug}`) and My Stuff (`/api/me/team-futures`, `/api/shared/team-futures`) scan only non-null `(team_id, market_id)` leaf entries via Index-Only Scan instead of reading ~62k cold settled `futures_outcomes` heap pages across 9.4 GB on big clubs (Lakers / Celtics).

Why attended (gotcha #31): `futures_outcomes` is 8.8 M+ rows / ~9.4 GB on production. `CREATE INDEX CONCURRENTLY` cannot run inside an Alembic transaction and must not hold a release phase; a plain `CREATE INDEX` takes an `ACCESS EXCLUSIVE` lock against live pollers.

## Pre-check (read-only)

```sql
SELECT indexrelid::regclass, indisvalid, indisready
FROM pg_index
WHERE indexrelid = 'ix_fo_team_market_id'::regclass;
```

## Build (attended, OUTSIDE any transaction block — never `--single-transaction`)

```sql
CREATE INDEX CONCURRENTLY IF NOT EXISTS ix_fo_team_market_id
ON futures_outcomes (team_id, market_id)
INCLUDE (id)
WHERE team_id IS NOT NULL;
```

## Post-check (verify `indisvalid = true` and `indisready = true`)

```sql
SELECT indexrelid::regclass, indisvalid, indisready, pg_size_pretty(pg_relation_size(indexrelid)) AS size
FROM pg_index
WHERE indexrelid = 'ix_fo_team_market_id'::regclass;
```

## Rollback

```sql
DROP INDEX CONCURRENTLY IF EXISTS ix_fo_team_market_id;
```
