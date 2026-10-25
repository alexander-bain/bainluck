#!/usr/bin/env python3
"""#2316 / P144-1 — print the EXACT season-market discovery statement for psql.

This script reads no database and writes nothing. It drives the real
`_build_related_futures` (routes/events.py) against a recording fake session,
captures two statements, and prints them as one psql block:

  1. the route's own compatible-sports lookup, which psql runs first and stores
     with `\\gset`. An empty lookup refuses the block (`\\if`) instead of
     leaving `:sport_ids` unexpanded, and
  2. the season-market discovery statement as a server-side PREPARE carrying
     the same `$n` binds the asyncpg dialect sends (only the sport ids are
     inlined, from that `\\gset` variable). It is planned five times without
     running, then run once under EXPLAIN (ANALYZE, BUFFERS): the sixth
     execution is the first one `plan_cache_mode = auto` may switch to a generic
     plan, and a generic plan cannot prove the partial-index predicate.
     `pg_prepared_statements` then prints which kind it chose.

Every block opens with the gate's own `statement_timeout`, so it never inherits
the build's `statement_timeout = 0`, and with `max_parallel_workers_per_gather
= 0`. Before PostgreSQL 18 a `Parallel Bitmap Heap Scan` prints `Heap Blocks:`
for the leader's share only (production is 17), so a parallel plan could pass
the heap-block ceiling while reading more. With no workers the count is
complete and the time is a serial upper bound.

Why it exists: the attended admission in
`docs/audits/latency/2316-p144-1-season-discovery-index-runbook.md` §3 must
EXPLAIN the statement production actually runs, not a hand copy that can drift
from the route. The predicate is a four-arm OR plus league-scope refusals, and
both change. Regenerate the block on the day of the build.

    cd backend && python3 scripts/season_discovery_admission_sql.py --gate-set
    cd backend && python3 scripts/season_discovery_admission_sql.py \\
        --sport-key americanfootball_ncaaf --finished
    cd backend && python3 scripts/season_discovery_admission_sql.py --dry-run

Exit 0 = block printed. Exit 2 = the route did not issue the statement this
script expects, so the runbook's premise is stale. Anything else is the harness.
"""

from __future__ import annotations

import argparse
import asyncio
import os
import re
import sys
from datetime import datetime, timedelta, timezone
from types import SimpleNamespace
from unittest.mock import patch

BACKEND = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, BACKEND)

# A sport id no real row carries. The script swaps its literal for the psql
# variable, so the printed statement takes production's ids, not this one.
SENTINEL_SPORT_ID = 987654321
SPORT_IDS_VAR = ":sport_ids"
PREPARED_NAME = "season_discovery_2316"
# Executions before the one EXPLAIN ANALYZE reads. PostgreSQL's plan cache
# always builds a custom plan for the first five and may switch to a generic
# plan from the sixth on, so the sixth is the first that can show the switch.
PLANS_BEFORE_ANALYZE = 5

# The three indexes, in build order. The runbook's CREATE set, its P2 and A2
# catalog reads and its section-4 DROP set must all name exactly these.
INDEX_NAMES = (
    "ix_fm_t14_llm_sport_category",
    "ix_fm_t14_sport_id",
    "ix_fm_t14_external_id_trgm",
)

# The A3 gate runs the finished shape for these sports, one statement each.
# ncaaf: the 2026-10-17 16 s reader. mlb: the 2026-08-30 Seq Scan specimen.
# soccer_epl: the generic `soccer%` arm plus every soccer sport id, likely the
# broadest bitmap. basketball_other: `basketball%` plus five Kalshi roots.
GATE_SPORTS = (
    "americanfootball_ncaaf",
    "baseball_mlb",
    "soccer_epl",
    "basketball_other",
)

# Criteria the block also SETs, in this order, before anything else runs. No
# workers: a parallel bitmap heap scan prints the leader's heap blocks only
# before PostgreSQL 18 (lane1b R1a), so the ceiling needs a serial plan.
GATE_SESSION_SETTINGS = ("statement_timeout", "max_parallel_workers_per_gather")

# The provisional KEEP criteria (runbook section 3, A2 and A3). The runbook
# prints the same table in its `gate-criteria` block and the guard test holds
# all three copies equal. The gate runs right after three builds and an
# ANALYZE, so its time is a warm time and decides nothing alone: the heap-block
# ceiling is the cache-independent bound. Cold budget 2,000 ms = 3,000 heap
# blocks x 0.5 ms per random heap read (1,500 ms) + a full 4 MB GIN pending
# list, 512 pages x 0.5 ms (256 ms) + index pages. Per-row size ceilings: the
# fixture's production-shaped Polymarket ids (0x + 64 hex) built at 216-238 B
# per tier-1-4 row for the trigram index and 21 B for each btree; x1.4 margin.
GATE_CRITERIA = {
    "statement_timeout": "30s",
    "max_parallel_workers_per_gather": "0",
    "every_index_valid": "yes",
    "seq_scan_on_futures_markets": "none",
    "parallel_bitmap_heap_scan": "none",
    "bitmapor_lists_all_three_indexes": "yes",
    "lossy_heap_blocks": "0",
    "max_exact_heap_blocks": "3000",
    "max_execution_ms": "2000",
    "generic_plans_after_sixth": "0",
    "max_trgm_bytes_per_t14_row_at_build": "330",
    "max_btree_bytes_per_t14_row_at_build": "40",
}

# The final KEEP (runbook section 6): a cold-path acceptance latency reads
# after the build, from pg_stat_statements deltas, outside the attended block.
# Steady-state trigram size: under churn the fixture's hex-id index settled at
# 640-810 B per row (vacuumed between rewrites) and kept growing slowly. The
# window mean mixes warm and cold calls, so one cold reader check carries its
# own bound (lane1b R1b): a mostly-warm window cannot average over it.
ACCEPTANCE_CRITERIA = {
    "window_starts_hours_after_build": "6",
    "window_hours": "24",
    "window_may_extend_to_hours": "72",
    "min_finished_shape_calls": "10",
    "max_mean_exec_ms": "2000",
    "max_trgm_bytes_per_t14_row_steady": "1000",
    "reader_check_reads": "1",
    "reader_check_taken_by": "latency",
    "reader_check_inside_window": "yes",
    "reader_check_max_maxq_ms": "2000",
    "reader_check_none_in_window": "UNMEASURED",
    "on_failure": "section 4 rollback",
}

# Every DROP and every re-read in the rollback (runbook section 4) and the A2
# failure path is bounded and attended: no step repeats on its own, and a
# leftover is reported, not retried (Root 0123Z/0147Z, lane1b R6').
ROLLBACK_BOUNDS = {
    "attended_passes": "1",
    "build_in_flight_at_start": "HOLD, drop nothing",
    "max_drop_attempts_per_index": "2",
    "drop_lock_timeout": "60s",
    "max_lock_waits_per_drop": "3",
    "pass_minutes_if_one_holder_per_wait": "18",
    "each_further_holder_adds": "60s",
    "a2_p1c_reread_max_minutes": "10",
    "a2_p1c_reread_every_minutes": "1",
    "a2_build_still_in_flight": "HOLD, drop nothing",
    "a2_step2_max_repeats": "1",
    "leftover_after_final_read": "ROLLBACK INCOMPLETE",
    "rollback_incomplete_operator": "Alex",
    "next_admission": "latency asks Root for the next attended slot, P1 P1b P1c first",
}

class _Captured(Exception):
    """Stops the build once the discovery statement has been recorded."""


class _Result:
    def __init__(self, rows=None, scalar=None):
        self._rows = rows or []
        self._scalar = scalar

    def scalar_one_or_none(self):
        return self._scalar

    def scalars(self):
        return self

    def all(self):
        return list(self._rows)

    def first(self):
        return self._rows[0] if self._rows else None


class RecordingSession:
    """Answers the route's queries up to the discovery statement, then stops."""

    def __init__(self, event):
        self.event = event
        self.sports_stmt = None
        self.discovery_stmt = None

    async def execute(self, stmt, *args, **kwargs):
        sql = str(stmt)
        if "FROM events" in sql:
            return _Result(scalar=self.event)
        if "FROM sports" in sql and self.sports_stmt is None:
            self.sports_stmt = stmt
            return _Result(rows=[SimpleNamespace(id=SENTINEL_SPORT_ID)])
        if sql.startswith("SELECT futures_markets.id, futures_markets.market_tier"):
            self.discovery_stmt = stmt
            raise _Captured()
        return _Result(rows=[])


def _event(sport_key: str, finished: bool, now: datetime):
    return SimpleNamespace(
        id=101,
        sport=SimpleNamespace(id=SENTINEL_SPORT_ID, key=sport_key),
        sport_id=SENTINEL_SPORT_ID,
        status="completed" if finished else "scheduled",
        # No team names: the route's women's-club lookup and series pass both
        # need them. Neither changes the discovery statement's shape.
        home_team_name=None,
        away_team_name=None,
        commence_time=now - timedelta(hours=4) if finished else now + timedelta(hours=3),
        completed_at=now - timedelta(hours=1) if finished else None,
        llm_gender=None,
    )


async def capture(sport_key: str, finished: bool) -> RecordingSession:
    """Drive the real build and return the session holding both statements."""
    from app.routes import events as events_route
    from app.utils import season_market_discovery as smd

    session = RecordingSession(_event(sport_key, finished, datetime.now(timezone.utc)))
    # No Redis: `read` misses and the single-flight lease fails open, so the
    # route reaches its own discovery query exactly as a cold reader does.
    with patch.object(smd, "_client", lambda: None):
        try:
            await events_route._build_related_futures(session.event.id, session, debug=False)
        except _Captured:
            # Expected: the session raises it right after recording the
            # discovery statement, so the build stops there on purpose.
            pass
    return session


def literal_sql(stmt) -> str:
    """Render for psql, where the route itself sends binds.

    The asyncpg dialect is the one production compiles with, and its `$n`
    paramstyle leaves `%` alone (the default dialect would print `%%`).
    `standard_conforming_strings` has been on by default since PostgreSQL 9.1,
    so a `\\y` in a league-scope regex is printed as written, not doubled.
    """
    from sqlalchemy.dialects.postgresql import asyncpg

    dialect = asyncpg.dialect()
    dialect._backslash_escapes = False
    return str(stmt.compile(dialect=dialect, compile_kwargs={"literal_binds": True}))


def _pg_literal(value) -> str:
    """One EXECUTE argument, as psql must type it."""
    if isinstance(value, bool):
        return "true" if value else "false"
    if isinstance(value, int):
        return str(value)
    if isinstance(value, datetime):
        return f"'{value.isoformat()}'::timestamptz"
    if isinstance(value, str):
        # standard_conforming_strings is on, so a backslash is printed as is.
        return "'" + value.replace("'", "''") + "'"
    raise SystemExit(2)


def prepared_sql(stmt) -> tuple[str, list[str]]:
    """The statement as asyncpg sends it, with the sport ids inlined.

    Returns the PREPARE body (`$n` binds renumbered after the sport ids are
    swapped for the psql variable) and the EXECUTE arguments in `$n` order.
    """
    from sqlalchemy.dialects.postgresql import asyncpg

    compiled = stmt.compile(
        dialect=asyncpg.dialect(), compile_kwargs={"render_postcompile": True}
    )
    values = [compiled.params[name] for name in compiled.positiontup]
    sentinel = {i + 1 for i, v in enumerate(values) if v == SENTINEL_SPORT_ID}
    if len(sentinel) != 1:
        raise SystemExit(2)
    renumber, args = {}, []
    for i, value in enumerate(values, start=1):
        if i not in sentinel:
            args.append(_pg_literal(value))
            renumber[i] = len(args)

    def _swap(m):
        n = int(m.group(1))
        # Drop the bind's cast with it: the ids are a list, not one INTEGER.
        return SPORT_IDS_VAR if n in sentinel else f"${renumber[n]}{m.group(2) or ''}"

    body = re.sub(r"\$(\d+)(::INTEGER)?(?!\d)", _swap, str(compiled))
    return body, args


def criteria_lines(prefix: str = "") -> list[str]:
    return [f"{prefix}{key} = {value}" for key, value in GATE_CRITERIA.items()]


def psql_block(session: RecordingSession, sport_key: str, finished: bool) -> str:
    sports_sql = literal_sql(session.sports_stmt)
    body, args = prepared_sql(session.discovery_stmt)
    sports_sql = sports_sql.replace(
        "SELECT sports.id", "SELECT string_agg(sports.id::text, ',') AS sport_ids", 1
    )
    shape = "finished" if finished else "live"
    execute = f"EXECUTE {PREPARED_NAME}({', '.join(args)})"
    return "\n".join(
        [
            f"-- #2316 season-market discovery, {sport_key} / {shape} shape.",
            "-- Generated by backend/scripts/season_discovery_admission_sql.py from",
            "-- routes/events.py; regenerate on the day of use, never hand-edit.",
            "-- KEEP criteria (runbook section 3, A3):",
            *criteria_lines("--   "),
            *[f"SET {name} = '{GATE_CRITERIA[name]}';" for name in GATE_SESSION_SETTINGS],
            "\\unset sport_ids",
            f"{sports_sql} \\gset",
            "\\if :{?sport_ids}",
            f"\\echo {sport_key} sport_ids=:sport_ids",
            "DEALLOCATE ALL;",
            f"PREPARE {PREPARED_NAME} AS",
            f"{body};",
            "\\o /dev/null",
            *[f"EXPLAIN {execute};" for _ in range(PLANS_BEFORE_ANALYZE)],
            "\\o",
            f"EXPLAIN (ANALYZE, BUFFERS) {execute};",
            "SELECT name, generic_plans, custom_plans FROM pg_prepared_statements"
            f" WHERE name = '{PREPARED_NAME}';",
            f"DEALLOCATE {PREPARED_NAME};",
            "\\else",
            f"\\echo ABORT {sport_key}: the sports lookup returned no ids, so this is not the route's statement",
            "\\endif",
        ]
    )


def gate_set() -> str:
    """The A3 file: the finished shape for every GATE_SPORTS key."""
    blocks = []
    for sport_key in GATE_SPORTS:
        s = asyncio.run(capture(sport_key, True))
        if s.sports_stmt is None or s.discovery_stmt is None:
            raise SystemExit(2)
        blocks.append(psql_block(s, sport_key, True))
    header = [
        "-- #2316 A3 gate set. Run with \\i inside the attended session, AFTER the builds.",
        "SHOW track_io_timing;",
    ]
    return "\n\n".join(["\n".join(header), *blocks])


def main(argv=None) -> int:
    p = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    p.add_argument("--sport-key", default="americanfootball_ncaaf")
    p.add_argument("--finished", action="store_true", help="the finished-event shape")
    p.add_argument(
        "--gate-set",
        action="store_true",
        help="print the whole A3 gate file: the finished shape for every gate sport",
    )
    p.add_argument(
        "--dry-run",
        action="store_true",
        help="capture both shapes for the default sport and print only a summary",
    )
    args = p.parse_args(argv)

    if args.dry_run:
        for finished in (True, False):
            s = asyncio.run(capture(args.sport_key, finished))
            ok = s.sports_stmt is not None and s.discovery_stmt is not None
            print(
                f"dry-run {args.sport_key} {'finished' if finished else 'live'}: "
                f"{'captured' if ok else 'NOT CAPTURED'}"
            )
            if not ok:
                return 2
        return 0

    if args.gate_set:
        print(gate_set())
        return 0

    s = asyncio.run(capture(args.sport_key, args.finished))
    if s.sports_stmt is None or s.discovery_stmt is None:
        print("the route did not issue the expected statements", file=sys.stderr)
        return 2
    print(psql_block(s, args.sport_key, args.finished))
    return 0


if __name__ == "__main__":
    sys.exit(main())
