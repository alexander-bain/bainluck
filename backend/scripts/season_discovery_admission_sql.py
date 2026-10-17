#!/usr/bin/env python3
"""#2316 / P144-1 — print the EXACT season-market discovery statement for psql.

This script reads no database and writes nothing. It drives the real
`_build_related_futures` (routes/events.py) against a recording fake session,
captures two statements, and prints them as one psql block:

  1. the route's own compatible-sports lookup, which psql runs first and stores
     with `\\gset`, and
  2. the season-market discovery statement, with literal binds and the sport
     ids taken from that `\\gset` variable.

Why it exists: the attended admission in
`docs/audits/latency/2316-p144-1-season-discovery-index-runbook.md` §3 must
EXPLAIN the statement production actually runs, not a hand copy that can drift
from the route. The predicate is a four-arm OR plus league-scope refusals, and
both change. Regenerate the block on the day of the build.

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


def psql_block(session: RecordingSession, sport_key: str, finished: bool) -> str:
    sports_sql = literal_sql(session.sports_stmt)
    discovery_sql = literal_sql(session.discovery_stmt)
    if str(SENTINEL_SPORT_ID) not in discovery_sql:
        raise SystemExit(2)
    discovery_sql = discovery_sql.replace(str(SENTINEL_SPORT_ID), SPORT_IDS_VAR)
    sports_sql = sports_sql.replace(
        "SELECT sports.id", "SELECT string_agg(sports.id::text, ',') AS sport_ids", 1
    )
    shape = "finished" if finished else "live"
    return "\n".join(
        [
            f"-- #2316 season-market discovery, {sport_key} / {shape} shape.",
            "-- Generated by backend/scripts/season_discovery_admission_sql.py from",
            "-- routes/events.py; regenerate on the day of use, never hand-edit.",
            f"{sports_sql} \\gset",
            "\\echo sport_ids=:sport_ids",
            "EXPLAIN (ANALYZE, BUFFERS)",
            f"{discovery_sql};",
        ]
    )


def main(argv=None) -> int:
    p = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    p.add_argument("--sport-key", default="americanfootball_ncaaf")
    p.add_argument("--finished", action="store_true", help="the finished-event shape")
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

    s = asyncio.run(capture(args.sport_key, args.finished))
    if s.sports_stmt is None or s.discovery_stmt is None:
        print("the route did not issue the expected statements", file=sys.stderr)
        return 2
    print(psql_block(s, args.sport_key, args.finished))
    return 0


if __name__ == "__main__":
    sys.exit(main())
