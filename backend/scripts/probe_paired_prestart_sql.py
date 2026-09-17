#!/usr/bin/env python3
"""Prove :mod:`app.utils.calibration_paired_prestart`'s SQL and Python agree. #6176.

WHY THIS EXISTS. The module carries the pairing rule twice — once as the
statement the feasibility walk runs on production, once as a pure-Python twin
the unit tests can reach without a database. The unit tests can only assert the
Python half and the TEXT of the SQL half. Nothing in CI executes the statement,
so the SQL could be wrong in a way that reads perfectly: an ``EXTRACT(SECOND …)``
that does not mean what the Python ``second == 0 and microsecond == 0`` means, a
LATERAL that cannot see ``fo.id``, a ``timestamp``/``timestamptz`` subtraction
resolved at the session timezone. Each of those returns rows. None of them
returns the right ones.

So this runs the REAL statement against a throwaway local Postgres holding a
synthetic fixture, runs the Python twin over the same fixture, and asserts the
``pair_class`` per outcome is identical. Every number here is INVENTED; nothing
is read from production and nothing is written anywhere but the scratch
database, which is dropped and recreated on every run.

The fixture is the control set from
``artifacts/other-model-paired-accuracy/paired_accuracy_example.py`` (C1-C6, E7,
E4, E5, G1), plus the four classes this module added that the example predates:
``start_provenance_unknown``, ``unanchored_boundary``, ``start_contradicted`` and
the poll-clock-minted start.

Usage::

    python3 -m scripts.probe_paired_prestart_sql --dry-run   # no DB, renders only
    python3 -m scripts.probe_paired_prestart_sql             # needs local Postgres

    PROBE_DSN=postgresql://user@host:5432/postgres python3 -m scripts.probe_paired_prestart_sql

Exit 0 = SQL and Python agreed on every row. Imported by nothing under
``app/``; it is a developer tool, not a task.
"""

from __future__ import annotations

import argparse
import os
import sys
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from typing import Any, Optional

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from app.utils.calibration_paired_prestart import (  # noqa: E402
    classify_pair,
    paired_legs_sql,
)
from app.utils.resolution_authority import (  # noqa: E402
    CALIBRATION_TRUTH_ELIGIBLE_SOURCES,
)

H = timedelta(hours=1)
D = timedelta(days=1)
T0 = datetime(2026, 1, 10, 20, 0, tzinfo=timezone.utc)
SCRATCH_DB = "cal6176_probe"

SCHEMA = """
DROP TABLE IF EXISTS futures_odds_snapshots, futures_outcomes, futures_markets, events;
CREATE TABLE events (
  id BIGINT PRIMARY KEY,
  commence_time TIMESTAMPTZ,
  commence_time_source TEXT,
  created_at TIMESTAMP,
  completed_at TIMESTAMPTZ
);
CREATE TABLE futures_markets (
  id BIGINT PRIMARY KEY,
  event_id BIGINT,
  source TEXT,
  status TEXT,
  resolution_date TIMESTAMPTZ,
  llm_sport_category TEXT
);
CREATE TABLE futures_outcomes (
  id BIGINT PRIMARY KEY,
  market_id BIGINT,
  is_winner BOOLEAN,
  resolution_source TEXT
);
CREATE TABLE futures_odds_snapshots (
  id BIGINT PRIMARY KEY,
  outcome_id BIGINT,
  bookmaker TEXT,
  probability NUMERIC(7,6),
  yes_bid NUMERIC(5,4),
  yes_ask NUMERIC(5,4),
  captured_at TIMESTAMPTZ,
  valid_until TIMESTAMPTZ,
  reading_count INT
);
CREATE INDEX idx_fos_outcome_captured
    ON futures_odds_snapshots (outcome_id, captured_at);
"""


@dataclass
class Ev:
    id: int
    commence_time: Optional[datetime]
    commence_time_source: Optional[str]
    created_at: Optional[datetime]
    completed_at: Optional[datetime]


@dataclass
class Out:
    id: int
    name: str
    event: Optional[Ev]
    source: str
    resolution_date: Optional[datetime]
    is_winner: Optional[bool]
    resolution_source: str


@dataclass
class Snap:
    id: int
    outcome_id: int
    bookmaker: str
    probability: float
    captured_at: datetime
    valid_until: Optional[datetime] = None
    yes_bid: Optional[float] = None
    yes_ask: Optional[float] = None


EVENTS: list[Ev] = []
OUTCOMES: list[Out] = []
SNAPS: list[Snap] = []
_next_ids = {"event": 1, "outcome": 1, "snap": 1}


def _take(kind: str) -> int:
    value = _next_ids[kind]
    _next_ids[kind] = value + 1
    return value


def game(
    *,
    commence: Optional[datetime] = T0,
    source: Optional[str] = "espn",
    created: Optional[datetime] = None,
    completed: Optional[datetime] = None,
) -> Ev:
    ev = Ev(
        _take("event"),
        commence,
        source,
        created if created is not None else (T0 - 30 * D).replace(tzinfo=None),
        completed if completed is not None else T0 + 3 * H,
    )
    EVENTS.append(ev)
    return ev


def outcome(
    name: str,
    ev: Optional[Ev],
    *,
    won: Optional[bool] = True,
    source: str = "kalshi",
    res: str = "api_settlement",
    resolution_date: Optional[datetime] = None,
) -> Out:
    out = Out(
        _take("outcome"),
        name,
        ev,
        source,
        resolution_date if resolution_date is not None else (T0 + 3 * H),
        won,
        res,
    )
    OUTCOMES.append(out)
    return out


def snap(out: Out, book: str, at: datetime, p: float, **kw: Any) -> None:
    SNAPS.append(Snap(_take("snap"), out.id, book, p, at, **kw))


def standard_pair(
    out: Out, early: float, final: float, *, book: Optional[str] = None
) -> None:
    """The ordinary shape: one look 26h out (re-confirmed at 25h), one an hour before."""
    book = book or out.source
    snap(out, book, T0 - 26 * H, early, valid_until=T0 - 25 * H)
    snap(out, book, T0 - 1 * H, final, yes_bid=final - 0.01, yes_ask=final + 0.01)


def build_fixture() -> dict[int, str]:
    """Returns ``{outcome_id: expected pair_class}``. Every value is invented."""
    expected: dict[int, str] = {}

    # -- four games observed at BOTH instants: the only rows a fair comparison may use
    e1, e2, e3 = game(), game(), game()
    for ev, legs in (
        (e1, [("E1-A", True, 0.55, 0.70), ("E1-B", False, 0.45, 0.30)]),
        (e2, [("E2-A", True, 0.60, 0.50), ("E2-B", False, 0.40, 0.50)]),
        (e3, [("E3-A", True, 0.50, 0.65), ("E3-B", False, 0.50, 0.35)]),
    ):
        for name, won, pe, pf in legs:
            o = outcome(name, ev, won=won)
            standard_pair(o, pe, pf)
            expected[o.id] = "paired"

    # E1-A was ALSO seen 30 days out. "First snapshot ever" would use that 0.40.
    unequal_lead = OUTCOMES[0]
    snap(unequal_lead, "kalshi", T0 - 30 * D, 0.40, valid_until=T0 - 29 * D)

    # E7: ONE collapsed row covers both instants (looked repeatedly, never
    # moved). CAL-P1331 moved the capture from 3 days out to 30 hours out: the
    # run must PROVE a look before each instant, and a 3-day-old capture proves
    # nothing about the early one. The 3-day variant is now C12 below.
    e7 = game()
    for name, won, p in (("E7-A", True, 0.70), ("E7-B", False, 0.30)):
        o = outcome(name, e7, won=won)
        snap(o, "kalshi", T0 - 30 * H, p, valid_until=T0 - 1 * H)
        expected[o.id] = "paired_unchanged"

    # -- early-ONLY: 3% longshots watched a week out, then polling stopped
    e4 = game()
    for i in range(3):
        o = outcome(f"E4-{i}", e4, won=False)
        snap(o, "kalshi", T0 - 7 * D, 0.03, valid_until=T0 - 6 * D)
        expected[o.id] = "no_final_stale"

    # -- final-ONLY: coin flips first polled two hours before kickoff
    e5 = game()
    for name, won in (("E5-A", True), ("E5-B", False)):
        o = outcome(name, e5, won=won)
        snap(o, "kalshi", T0 - 1 * H, 0.50, yes_bid=0.49, yes_ask=0.51)
        expected[o.id] = "no_early_none_before"

    # -- REJECTION CONTROLS ------------------------------------------------
    # C1 missing close: only the early look exists; the writer's opening
    # fallback is never consulted by this rule.
    c1 = outcome("C1-A", game())
    snap(c1, "kalshi", T0 - 26 * H, 0.35, valid_until=T0 - 25 * H)
    expected[c1.id] = "no_final_stale"

    # C2 after-start: the only late look is 20 minutes INTO the game, at 0.97.
    c2 = outcome("C2-A", game())
    snap(c2, "kalshi", T0 - 26 * H, 0.55, valid_until=T0 - 25 * H)
    snap(c2, "kalshi", T0 + timedelta(minutes=20), 0.97)
    expected[c2.id] = "no_final_stale"

    # C3 price-derived winner: excluded by the POPULATION, so the statement
    # never emits a class for it. Asserted by absence.
    c3 = outcome("C3-A", game(), res="settlement_sync")
    standard_pair(c3, 0.55, 0.90)
    expected[c3.id] = "__absent__"

    # C3b ungraded truth: is_winner NULL is never a loss.
    c3b = outcome("C3-B", game(), won=None)
    standard_pair(c3b, 0.55, 0.90)
    expected[c3b.id] = "__absent__"

    # C4 stand-in start: commence_time is midnight UTC parsed from a ticker date.
    c4 = outcome("C4-A", game(commence=T0.replace(hour=0), source="kalshi_ticker"))
    standard_pair(c4, 0.55, 0.70)
    expected[c4.id] = "start_not_reported"

    # C5 two sportsbooks: early is DraftKings, late is FanDuel.
    c5 = outcome("C5-A", game(), source="odds_api", res="game_score")
    snap(c5, "draftkings", T0 - 26 * H, 0.52, valid_until=T0 - 25 * H)
    snap(c5, "fanduel", T0 - 1 * H, 0.58, yes_bid=0.57, yes_ask=0.59)
    expected[c5.id] = "legs_from_different_books"

    # C6 fabricated midpoint: empty book (bid .001 / ask 1.0) averages to .5005.
    c6 = outcome("C6-A", game())
    snap(c6, "kalshi", T0 - 26 * H, 0.55, valid_until=T0 - 25 * H)
    snap(c6, "kalshi", T0 - 1 * H, 0.5005, yes_bid=0.001, yes_ask=1.0)
    expected[c6.id] = "no_final_stale"

    # C7 provenance unknown: a start nobody can vouch for.
    c7 = outcome("C7-A", game(source=None))
    standard_pair(c7, 0.55, 0.70)
    expected[c7.id] = "start_provenance_unknown"

    # C8 no linked event at all: the boundary would silently be the SETTLEMENT date.
    c8 = outcome("C8-A", None)
    standard_pair(c8, 0.55, 0.70)
    expected[c8.id] = "unanchored_boundary"

    # C9 our own columns contradict the start (gotcha #46).
    c9 = outcome("C9-A", game(completed=T0 - 1 * H))
    standard_pair(c9, 0.55, 0.70)
    expected[c9.id] = "start_contradicted"

    # C9b settlement long before the start: the wrong-game-in-a-series specimen.
    c9b = outcome("C9-B", game(), resolution_date=T0 - 1 * D)
    standard_pair(c9b, 0.55, 0.70)
    expected[c9b.id] = "start_contradicted"

    # C10 the start IS the clock of the poll that minted the row.
    minted_at = (T0 - 2 * D).replace(second=17, microsecond=316804)
    c10 = outcome(
        "C10-A",
        game(
            commence=minted_at, source="kalshi", created=minted_at.replace(tzinfo=None)
        ),
        resolution_date=minted_at + 3 * H,
    )
    snap(c10, "kalshi", minted_at - 26 * H, 0.55, valid_until=minted_at - 25 * H)
    snap(c10, "kalshi", minted_at - 1 * H, 0.70, yes_bid=0.69, yes_ask=0.71)
    expected[c10.id] = "start_not_reported"

    # C11 a REAL fixture merely discovered near its start: the positive control
    # for C10. Same source, same nearness, but a minute-boundary kickoff.
    real_at = (T0 - 2 * D).replace(second=0, microsecond=0)
    c11 = outcome(
        "C11-A",
        game(commence=real_at, source="kalshi", created=real_at.replace(tzinfo=None)),
        resolution_date=real_at + 3 * H,
    )
    snap(c11, "kalshi", real_at - 26 * H, 0.55, valid_until=real_at - 25 * H)
    snap(c11, "kalshi", real_at - 1 * H, 0.70, yes_bid=0.69, yes_ask=0.71)
    expected[c11.id] = "paired"

    # C12 CAL-P1331, the FINAL leg: one run first seen 3 days before the start
    # and last seen 2 hours AFTER it. The old clamp scored this staleness zero
    # and published it as a flat pair; the only evidence promoting it over an
    # identical stale row came from after the event began.
    c12 = outcome("C12-A", game())
    snap(c12, "kalshi", T0 - 3 * D, 0.62, valid_until=T0 + 2 * H)
    expected[c12.id] = "no_final_unconfirmed_span"

    # C13 the same defect at the EARLY boundary, reachable with no after-start
    # evidence at all: a 30-day-old price whose only confirmation lands 22 hours
    # after the instant it is being offered as the market's view of.
    c13 = outcome("C13-A", game())
    snap(c13, "kalshi", T0 - 30 * D, 0.20, valid_until=T0 - 2 * H)
    snap(c13, "kalshi", T0 - 1 * H, 0.80, yes_bid=0.79, yes_ask=0.81)
    expected[c13.id] = "no_early_unconfirmed_span"

    # C14 the positive control for both: identical shape to C13, confirmed an
    # hour BEFORE the early instant rather than after it, and it pairs.
    c14 = outcome("C14-A", game())
    snap(c14, "kalshi", T0 - 30 * D, 0.20, valid_until=T0 - 25 * H)
    snap(c14, "kalshi", T0 - 1 * H, 0.80, yes_bid=0.79, yes_ask=0.81)
    expected[c14.id] = "paired"

    # G1 DataGolf: a valid pair, but a MODEL forecast — its own set, never pooled.
    g1 = outcome("G1-A", game(), won=False, source="datagolf", res="game_score")
    standard_pair(g1, 0.12, 0.10)
    expected[g1.id] = "paired"

    return expected


def python_classes() -> dict[int, str]:
    """The Python twin's verdict on the same fixture."""
    by_outcome: dict[int, list[tuple]] = {}
    for s in SNAPS:
        by_outcome.setdefault(s.outcome_id, []).append(
            (
                s.captured_at,
                s.probability,
                s.yes_bid,
                s.yes_ask,
                s.bookmaker,
                s.valid_until,
            )
        )
    out: dict[int, str] = {}
    for o in OUTCOMES:
        klass, _, _ = classify_pair(
            by_outcome.get(o.id, []),
            event=o.event,
            market_source=o.source,
            resolution_date=o.resolution_date,
            is_winner=o.is_winner,
            resolution_source=o.resolution_source,
            eligible_sources=CALIBRATION_TRUTH_ELIGIBLE_SOURCES,
        )
        out[o.id] = klass
    return out


def load(conn) -> None:
    cur = conn.cursor()
    cur.execute(SCHEMA)
    for e in EVENTS:
        cur.execute(
            "INSERT INTO events VALUES (%s,%s,%s,%s,%s)",
            (
                e.id,
                e.commence_time,
                e.commence_time_source,
                e.created_at,
                e.completed_at,
            ),
        )
    for o in OUTCOMES:
        cur.execute(
            "INSERT INTO futures_markets VALUES (%s,%s,%s,%s,%s,%s)",
            (
                o.id,
                o.event.id if o.event else None,
                o.source,
                "resolved",
                o.resolution_date,
                "test",
            ),
        )
        cur.execute(
            "INSERT INTO futures_outcomes VALUES (%s,%s,%s,%s)",
            (o.id, o.id, o.is_winner, o.resolution_source),
        )
    for s in SNAPS:
        cur.execute(
            "INSERT INTO futures_odds_snapshots VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s)",
            (
                s.id,
                s.outcome_id,
                s.bookmaker,
                s.probability,
                s.yes_bid,
                s.yes_ask,
                s.captured_at,
                s.valid_until,
                1,
            ),
        )
    conn.commit()


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument(
        "--dry-run",
        action="store_true",
        help="render the statement and the Python verdicts; touch no database",
    )
    args = ap.parse_args()

    expected = build_fixture()
    statement = paired_legs_sql(cursor="0", scan="100000")
    py = python_classes()

    mismatched_python = {
        oid: (py[oid], want)
        for oid, want in expected.items()
        if want != "__absent__" and py[oid] != want
    }
    if mismatched_python:
        print("PYTHON TWIN DISAGREES WITH THE FIXTURE:")
        for oid, (got, want) in sorted(mismatched_python.items()):
            print(f"  outcome {oid}: got {got!r}, expected {want!r}")
        return 1
    print(f"python twin: {len(expected)} outcomes classified as the fixture expects")

    if args.dry_run:
        print(f"--dry-run: rendered {len(statement)} chars of SQL, no database touched")
        return 0

    try:
        import psycopg2
    except ImportError:
        print("psycopg2 is not installed; nothing to execute", file=sys.stderr)
        return 2

    dsn = os.environ.get("PROBE_DSN", "postgresql://localhost:5432/postgres")
    admin = psycopg2.connect(dsn)
    admin.autocommit = True
    admin.cursor().execute(f"DROP DATABASE IF EXISTS {SCRATCH_DB}")
    admin.cursor().execute(f"CREATE DATABASE {SCRATCH_DB}")
    admin.close()

    conn = psycopg2.connect(dsn.rsplit("/", 1)[0] + "/" + SCRATCH_DB)
    try:
        load(conn)
        cur = conn.cursor()
        cur.execute(statement)
        cols = [d[0] for d in cur.description]
        rows = [dict(zip(cols, r)) for r in cur.fetchall()]
    finally:
        conn.close()

    sql_classes = {r["outcome_id"]: r["pair_class"] for r in rows}
    failures = []
    for oid, want in sorted(expected.items()):
        got = sql_classes.get(oid, "__absent__")
        if got != want:
            failures.append(
                f"  outcome {oid}: SQL said {got!r}, fixture expects {want!r}"
            )
        if want != "__absent__" and got != py[oid]:
            failures.append(f"  outcome {oid}: SQL {got!r} != Python {py[oid]!r}")
    extra = set(sql_classes) - set(expected)
    if extra:
        failures.append(f"  SQL emitted rows for unknown outcomes: {sorted(extra)}")

    for r in sorted(rows, key=lambda r: r["outcome_id"]):
        print(
            f"  {r['outcome_id']:>3}  {r['pair_class']:<26} {r['forecast_kind']:<7} {r['bookmaker']}"
        )

    if failures:
        print("\nSQL / PYTHON DISAGREE:")
        print("\n".join(failures))
        return 1
    print(
        f"\nAGREED on all {len(expected)} outcomes "
        f"({len(rows)} emitted, {len(expected) - len(rows)} excluded by the population)"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
