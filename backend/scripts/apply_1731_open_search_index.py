#!/usr/bin/env python3
"""#1731 — hand-create the open-cohort covering index on `futures_markets`.

VERDICT (LAT-P041, 2026-08-12): **BUILT, MEASURED, ROLLED BACK. DO NOT RE-APPLY
WITHOUT A NEW RULING.** #1731 is CLOSED accepted-with-evidence.

This file is kept as the reproducible rail, not as pending work — #1731's own
complaint was that "every cycle rediscovers the same wall at real cost", and a
committed negative result is the only thing that stops a sixth cycle.

    specimen   WITH index (median)   WITHOUT index (median)
    la         1779 ms               1421 ms      <- index 25% SLOWER
    fed         558 ms                445 ms      <- index slower
    re         1247 ms               1119 ms      <- wash

Controlled A/B, both halves after the SAME `VACUUM (ANALYZE)` so only the index
varies; 5 passes each, 3s spacing (the public 60/min limit turns a throttled
response into a phantom regression). The planner DID adopt the index — the la/re
arms switched to `Index Only Scan` — it simply did not pay: it trades a heap
sweep for a per-tuple visibility-map probe across all 79,085 open rows, and the
extra 8.7 MB competes for a 1 GB `shared_buffers` against a 1.7 GB table.

Beware the measurement trap this exposed (gotcha #123): blocks read 34,456 with
the index vs 33,982 without, which looks like a wash, but block counts are NOT
comparable across plan node types. The endpoint A/B is the arbiter.

What actually moved the number was not an index: `VACUUM (ANALYZE)` cut the
`fed` arm 3,158 -> 999 blocks (-68%) and 35.3 -> 2.9 ms by letting the planner
drop a redundant bitmap, and that win PERSISTED after this index was dropped.
Follow-up: #1794 (autoanalyze tuning).

WHY THIS IS A SCRIPT AND NOT A MIGRATION
----------------------------------------
Gotcha #31: `CREATE INDEX CONCURRENTLY` inside an Alembic migration hangs
Heroku's ~5-minute release phase and caused the May 22 outage. Every latency
queue therefore carries `migration_slot: none`. This DDL is applied by hand,
outside the migration chain, on Alex's explicit ruling (2026-08-12):

    "#1731 is RULED: GO, full version — partial index on the open cohort
     (status='open' AND unresolved) PLUS the covering columns the sort needs
     (market_tier, volume, updated_at)."

WHY `heroku pg:psql` IS NOT THE RAIL
------------------------------------
TCP 5432 egress is blocked from an agent sandbox — `pg:psql` dies with
"Operation not permitted" before it reaches the server. A `run:detached`
one-off dyno executes INSIDE Heroku's network, so it can reach the database.
That is the rail this script is built for:

    heroku run:detached -a bainluck -- python3 scripts/apply_1731_open_search_index.py
    heroku run:detached -a bainluck -- python3 scripts/apply_1731_open_search_index.py --rollback

Gotcha (memory, `reference_heroku_oneoff_dyno_no_cd_backend`): scripts live at
`/app`, NOT `/app/backend`. A `cd backend &&` prefix SILENTLY no-ops. Verify by
census (`pg_stat_user_indexes`), never by the dyno's stdout — a non-detached
`heroku run` does not execute at all in the sandbox (gotcha #48).

WHAT `unresolved` COULD AND COULD NOT BECOME
--------------------------------------------
Alex's predicate is `status = 'open' AND unresolved`, where the route spells
unresolved as `resolution_date IS NULL OR resolution_date >= now()`
(`app/routes/events.py`, `_futures_open_now`).

**`now()` cannot appear in a partial-index predicate** — Postgres requires the
predicate be IMMUTABLE, and a time-dependent predicate would silently change
which rows the index claims to contain. So the ruled predicate is split:

  * `status = 'open'`      -> the partial predicate (79,085 of 766,050 rows, 10.3%)
  * `resolution_date`      -> a KEY column, so the now() comparison is still
                              answered from the index instead of the heap

That is the ruling honoured to the letter it permits, not a narrowing.

WHY THE FILTER COLUMNS ARE KEYS AND THE SORT COLUMNS ARE `INCLUDE`
-------------------------------------------------------------------
`name` and `resolution_date` are FILTERED on, so they are key columns —
Postgres 17 does not push quals onto non-key `INCLUDE` columns, so an
INCLUDE-only `name` would be returned but not filtered, and the scan would
fall back to the heap. `market_tier`, `volume` and `updated_at` are pure
output (sort payload), so `INCLUDE` is correct and keeps the tuple smaller.

The ORDER BY this index feeds CANNOT be index-served and that is not the
point: its first two keys are query-dependent expressions (a CASE over the
match arms, then `ts_rank` against the expanded tsquery). There will always
be a sort. What the index removes is the 33,982-block (272 MB) HEAP SWEEP the
2-char-infix arms currently pay to recheck `name ILIKE '%la%'`.
"""

from __future__ import annotations

import argparse
import os
import sys
import time

INDEX_NAME = "ix_fm_open_search_cover"

CREATE_DDL = f"""
CREATE INDEX CONCURRENTLY IF NOT EXISTS {INDEX_NAME}
    ON public.futures_markets USING btree (name, resolution_date, id)
    INCLUDE (market_tier, volume, updated_at)
    WHERE status = 'open'
"""

ROLLBACK_DDL = f"DROP INDEX CONCURRENTLY IF EXISTS public.{INDEX_NAME}"

# A failed CREATE INDEX CONCURRENTLY leaves an INVALID index behind that still
# costs writes while serving no reads. Never leave one standing.
INVALID_CHECK = """
SELECT c.relname, i.indisvalid, i.indisready
  FROM pg_class c
  JOIN pg_index i ON i.indexrelid = c.oid
 WHERE c.relname = %s
"""

SIZE_CHECK = """
SELECT pg_size_pretty(pg_relation_size(c.oid))
  FROM pg_class c WHERE c.relname = %s
"""


def _connect():
    """Autocommit connection. CONCURRENTLY cannot run inside a transaction."""
    import psycopg2

    url = os.environ.get("DATABASE_URL")
    if not url:
        sys.exit("DATABASE_URL is unset — this must run on a Heroku dyno.")
    # SQLAlchemy-style scheme that psycopg2 does not accept.
    url = url.replace("postgresql+asyncpg://", "postgresql://").replace(
        "postgres://", "postgresql://", 1
    )
    conn = psycopg2.connect(url, sslmode="require")
    conn.autocommit = True
    return conn


def _report(cur, label: str) -> None:
    cur.execute(INVALID_CHECK, (INDEX_NAME,))
    row = cur.fetchone()
    if not row:
        print(f"[{label}] {INDEX_NAME}: ABSENT")
        return
    cur.execute(SIZE_CHECK, (INDEX_NAME,))
    size = cur.fetchone()[0]
    print(f"[{label}] {INDEX_NAME}: valid={row[1]} ready={row[2]} size={size}")
    if not row[1]:
        print(
            f"[{label}] !! INVALID INDEX PRESENT. It costs every write and serves "
            f"no read. Drop it: DROP INDEX CONCURRENTLY {INDEX_NAME};"
        )


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--rollback", action="store_true", help="drop the index instead")
    args = ap.parse_args()

    conn = _connect()
    cur = conn.cursor()

    _report(cur, "before")
    ddl = ROLLBACK_DDL if args.rollback else CREATE_DDL
    print(f"[exec] {' '.join(ddl.split())}")
    t0 = time.time()
    cur.execute(ddl)
    print(f"[exec] completed in {time.time() - t0:.1f}s")
    _report(cur, "after")

    cur.close()
    conn.close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
