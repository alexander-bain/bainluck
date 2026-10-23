"""#847: the Correctness Console's Kalshi / Polymarket coverage counts every
covered event once, whichever channel the source reached it through.

These tests run the REAL ``_query_event_source_coverage`` (imported, not
copied) against an in-memory SQLite database. The only translation is the
dialect: the two ``NOW() +/- INTERVAL`` window bounds become fixed literals and
SQLite gets a ``bool_or`` aggregate. Everything else — the CTEs, the 1:1 joins,
the ``FILTER`` counts and the Python row mapping — is the production code.

This proves the helper's arithmetic. It says nothing about PostgreSQL cost,
plan shape or production prevalence.
"""

from __future__ import annotations

import asyncio
import importlib
import sqlite3
from types import SimpleNamespace

import pytest

ad = importlib.import_module("app.utils.admin_dashboard")

_WINDOW_START = "2026-10-12 00:00:00"
_WINDOW_END = "2026-10-21 00:00:00"
_IN_WINDOW = "2026-10-19 12:00:00"
_BEFORE_WINDOW = "2026-10-01 12:00:00"
_AFTER_WINDOW = "2026-10-25 12:00:00"


class _BoolOr:
    def __init__(self) -> None:
        self.value = False

    def step(self, value) -> None:
        self.value = self.value or bool(value)

    def finalize(self) -> int:
        return int(self.value)


class _SqliteSession:
    """Just enough of AsyncSession for the helper: ``await db.execute(text)``."""

    def __init__(self, conn: sqlite3.Connection) -> None:
        self.conn = conn
        self.statements: list[str] = []

    async def execute(self, clause):
        sql = str(clause)
        for pg, lit in (
            ("NOW() - INTERVAL '7 days'", f"'{_WINDOW_START}'"),
            ("NOW() + INTERVAL '2 days'", f"'{_WINDOW_END}'"),
        ):
            assert sql.count(pg) == 1, f"window bound {pg!r} moved; re-check the window"
            sql = sql.replace(pg, lit)
        self.statements.append(sql)
        cur = self.conn.execute(sql)
        names = [d[0] for d in cur.description]
        rows = [SimpleNamespace(**dict(zip(names, r))) for r in cur.fetchall()]
        return SimpleNamespace(all=lambda: rows)


class _World:
    def __init__(self) -> None:
        assert sqlite3.sqlite_version_info >= (3, 30), "COUNT(*) FILTER needs SQLite 3.30+"
        self.conn = sqlite3.connect(":memory:")
        self.conn.create_aggregate("bool_or", 1, _BoolOr)
        self.conn.executescript(
            """
            CREATE TABLE sports (id INTEGER PRIMARY KEY, key TEXT);
            CREATE TABLE events (
                id INTEGER PRIMARY KEY, sport_id INTEGER, external_id TEXT,
                espn_id TEXT, statpal_fixture_id TEXT, status TEXT,
                commence_time TEXT, win_probability_sources TEXT
            );
            CREATE TABLE win_prob_snapshots (
                id INTEGER PRIMARY KEY, event_id INTEGER, source TEXT, captured_at TEXT
            );
            CREATE TABLE futures_markets (
                id INTEGER PRIMARY KEY, event_id INTEGER, source TEXT
            );
            INSERT INTO sports VALUES (1, 'basketball_nba'), (2, 'icehockey_nhl');
            """
        )

    def event(self, eid: int, *, sport: int = 1, when: str = _IN_WINDOW, **cols) -> None:
        self.conn.execute(
            "INSERT INTO events (id, sport_id, external_id, espn_id, statpal_fixture_id,"
            " status, commence_time) VALUES (?,?,?,?,?,?,?)",
            (
                eid, sport, cols.get("external_id"), cols.get("espn_id"),
                cols.get("statpal_fixture_id"), cols.get("status", "upcoming"), when,
            ),
        )

    def snapshot(self, eid: int, source: str, captured_at: str = _IN_WINDOW) -> None:
        self.conn.execute(
            "INSERT INTO win_prob_snapshots (event_id, source, captured_at) VALUES (?,?,?)",
            (eid, source, captured_at),
        )

    def market(self, eid: int, source: str) -> None:
        self.conn.execute(
            "INSERT INTO futures_markets (event_id, source) VALUES (?,?)", (eid, source)
        )

    def run(self) -> dict[str, dict]:
        rows = asyncio.run(ad._query_event_source_coverage(_SqliteSession(self.conn)))
        return {r["sport"]: r for r in rows}


def _three_events_plus_out_of_window() -> _World:
    """Three in-window NBA events, and one event either side of the window that
    carries BOTH channels for BOTH sources — it must never be counted."""
    w = _World()
    for eid in (1, 2, 3):
        w.event(eid)
    w.event(98, when=_BEFORE_WINDOW)
    w.event(99, when=_AFTER_WINDOW)
    for eid in (98, 99):
        for src in ("kalshi", "polymarket"):
            w.snapshot(eid, src)
            w.market(eid, src)
    return w


@pytest.mark.parametrize(
    "label, snapshot_ids, market_ids, expected",
    [
        ("disjoint", [1], [2], 2),
        ("partial_overlap", [1, 2], [2, 3], 3),
        ("full_overlap", [1, 2], [1, 2], 2),
        ("duplicate_records", [1, 1, 1], [2, 2], 2),
        ("snapshot_only", [1, 2], [], 2),
        ("market_only", [], [1, 3], 2),
        ("neither_channel", [], [], 0),
        ("every_event_both_channels", [1, 2, 3], [1, 2, 3], 3),
    ],
)
@pytest.mark.parametrize("source", ["kalshi", "polymarket"])
def test_a_source_counts_the_union_of_its_two_channels(
    source, label, snapshot_ids, market_ids, expected
):
    w = _three_events_plus_out_of_window()
    for eid in snapshot_ids:
        w.snapshot(eid, source)
    for eid in market_ids:
        w.market(eid, source)

    row = w.run()["basketball_nba"]

    assert row["total"] == 3, "the out-of-window events entered the denominator"
    assert row[source] == expected, (
        f"{label}: snapshots on {sorted(set(snapshot_ids))}, markets on "
        f"{sorted(set(market_ids))} cover {expected} events; got {row[source]}"
    )
    other = "polymarket" if source == "kalshi" else "kalshi"
    assert row[other] == 0, f"{source} coverage leaked into {other}"


def test_the_two_sources_are_counted_independently():
    w = _three_events_plus_out_of_window()
    w.snapshot(1, "kalshi")
    w.market(2, "kalshi")
    w.market(3, "polymarket")
    # Sources that are not Kalshi/Polymarket never count as either.
    w.snapshot(3, "espn")
    w.snapshot(2, "stat_model")
    w.market(1, "odds_api")

    row = w.run()["basketball_nba"]

    assert row["kalshi"] == 2
    assert row["polymarket"] == 1
    assert row["espn_wp"] == 1
    assert row["model"] == 1


def test_coverage_is_grouped_per_sport():
    w = _World()
    w.event(1, sport=1)
    w.event(2, sport=1)
    w.event(3, sport=2)
    w.snapshot(1, "kalshi")
    w.market(2, "kalshi")
    w.market(3, "kalshi")

    rows = w.run()

    assert rows["basketball_nba"]["total"] == 2
    assert rows["basketball_nba"]["kalshi"] == 2
    assert rows["icehockey_nhl"]["total"] == 1
    assert rows["icehockey_nhl"]["kalshi"] == 1


def test_union_never_exceeds_the_event_count_under_duplicate_rows():
    """Many snapshot rows and many market rows on every event: still one each."""
    w = _three_events_plus_out_of_window()
    for eid in (1, 2, 3):
        for _ in range(4):
            w.snapshot(eid, "kalshi")
            w.market(eid, "kalshi")

    row = w.run()["basketball_nba"]

    assert row["total"] == 3
    assert row["kalshi"] == 3


def test_snapshot_age_still_does_not_gate_coverage():
    """LAT-P017's deliberate semantics: an in-window event's old snapshot counts."""
    w = _three_events_plus_out_of_window()
    w.snapshot(1, "kalshi", captured_at="2025-01-01 00:00:00")
    w.market(2, "kalshi")

    assert w.run()["basketball_nba"]["kalshi"] == 2


def test_unrelated_fields_are_unchanged():
    w = _World()
    w.event(1, external_id="oa-1", espn_id="e-1", statpal_fixture_id="sp-1", status="live")
    w.event(2, external_id="oa-2")
    w.event(3, sport=1, when=_AFTER_WINDOW, external_id="oa-3", status="live")
    w.snapshot(1, "espn")
    w.snapshot(1, "stat_model")
    w.snapshot(2, "mlb")

    row = w.run()["basketball_nba"]

    assert set(row) == {
        "sport", "total", "live", "odds_api", "espn", "statpal", "espn_wp",
        "model", "mlb", "kalshi", "polymarket", "expected_sources",
    }
    assert (row["total"], row["live"]) == (2, 1)
    assert (row["odds_api"], row["espn"], row["statpal"]) == (2, 1, 1)
    assert (row["espn_wp"], row["model"], row["mlb"]) == (1, 1, 1)
    assert (row["kalshi"], row["polymarket"]) == (0, 0)
    assert row["expected_sources"] == ad._expected_sources_for_sport("basketball_nba")


def test_the_helper_issues_one_statement():
    w = _World()
    w.event(1)
    session = _SqliteSession(w.conn)
    asyncio.run(ad._query_event_source_coverage(session))
    assert len(session.statements) == 1
