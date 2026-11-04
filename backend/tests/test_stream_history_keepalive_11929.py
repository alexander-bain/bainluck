"""#11929 keep-alive — a flat stretch draws flat.

WHAT A READER SEES. The socket writes a price only when it CHANGES, so a leg
whose price sat still for an hour never reached the flush's history plan and
its chart showed a hole across a stretch we were reading the whole time. With
`STREAM_HISTORY_KEEPALIVE` on (and `STREAM_HISTORY_POINTS` on for the venue),
each socket's minute loop writes a point for every live leg whose last point is
15 minutes old — at the leg's COMMITTED price, even if it did not change.

THE CASES:

* the switch: default off, its own values, only where points are on, and off
  means no pass and no statement;
* the rule: due at 900 s (not 899), an unchanged price is still due, refused
  and graded legs never, a leg the INSERT refused is held for an interval;
* the cap is the move points' cap (one `_market_minute`, both directions,
  in-flight reservations), stalest first, and a per-pass ceiling;
* memory and counts advance only after the pass's COMMIT; a failed pass is
  counted and never touches a price flush;
* seeding from the database only for live legs without memory, once, bounded;
* a live leg is never pruned;
* the statement reads the price from `futures_outcomes` (never a buffer or a
  preview) and refuses settled rows;
* through the REAL Kalshi and Polymarket consumers (fake sessions): the live
  population is what the connected sockets carry, the pass runs from the
  stats loop, and a failing pass leaves the price write and its move point;
* on real PostgreSQL (`SEARCH_TEST_DATABASE_URL`, asyncpg like production):
  the point equals the stored row, seeding reads the newest snapshot, settled
  rows get nothing, and a failed insert writes nothing.
"""

from __future__ import annotations

import ast
import asyncio
from datetime import datetime, timedelta, timezone
from pathlib import Path
from types import SimpleNamespace

import pytest
from sqlalchemy.dialects import postgresql
from sqlalchemy.sql.dml import Insert

import app.utils.stream_history_points as shp
from app.utils.stream_history_points import (
    HISTORY_KEEPALIVE_S,
    HISTORY_MAX_PER_MARKET_MINUTE,
    KeepalivePlan,
    StreamHistoryPoints,
    is_keepalive_statement,
    keepalive_insert_statement,
    keepalive_seed_statement,
    stream_history_keepalive_enabled,
)
from tests.pm_bulk_test_support import cleanup_pg_engines  # noqa: F401 — autouse

BACKEND = Path(__file__).resolve().parents[1]
T0 = datetime(2026, 11, 4, 18, 0, 5, tzinfo=timezone.utc)


def history(**kwargs):
    kwargs.setdefault("enabled", True)
    kwargs.setdefault("keepalive", True)
    return StreamHistoryPoints(kwargs.pop("venue", "kalshi"), **kwargs)


def pointed(h, oid, at, prob=0.42):
    h.last_point[oid] = (prob, at)
    return h


class _Result:
    def __init__(self, rows):
        self._rows = list(rows)

    def all(self):
        return list(self._rows)


class FakeDB:
    """A session factory answering the keep-alive's two statements.

    ``stored``: outcome_id → stored price; ``refuse``: ids the INSERT's WHERE
    refuses; ``snapshots``: outcome_id → (probability, captured_at) of its
    newest snapshot. ``fail``: "open" | "seed" | "insert" | "commit".
    ``db_now``: the INSERT's ``now()``; None = the wall clock.
    """

    def __init__(self, stored=None, *, refuse=(), snapshots=None, fail=None,
                 db_now=T0):
        self.stored = dict(stored or {})
        self.refuse = set(refuse)
        self.snapshots = dict(snapshots or {})
        self.fail = fail
        self.db_now = db_now
        self.calls = []  # (kind, params)
        self.sessions = 0
        self.commits = 0

    def __call__(self):
        db = self

        class Session:
            async def execute(self, stmt, params=None):
                if stmt is keepalive_seed_statement():
                    db.calls.append(("seed", params))
                    if db.fail == "seed":
                        raise RuntimeError("seed read failed")
                    return _Result([
                        (oid, *db.snapshots[oid])
                        for oid in params["keepalive_seed_ids"] if oid in db.snapshots
                    ])
                assert any(stmt is keepalive_insert_statement(v) for v in ("kalshi", "polymarket"))
                db.calls.append(("insert", params))
                if db.fail == "insert":
                    raise RuntimeError("insert failed")
                now = db.db_now or datetime.now(timezone.utc)
                return _Result([
                    (oid, db.stored[oid], now)
                    for oid in params["keepalive_outcome_ids"]
                    if oid in db.stored and oid not in db.refuse
                ])

            async def commit(self):
                if db.fail == "commit":
                    raise RuntimeError("commit failed")
                db.commits += 1

        class Ctx:
            async def __aenter__(self):
                db.sessions += 1
                if db.fail == "open":
                    raise RuntimeError("no connection")
                return Session()

            async def __aexit__(self, *_exc):
                return False

        return Ctx()

    def kinds(self):
        return [kind for kind, _p in self.calls]

    def inserted_ids(self):
        return [p["keepalive_outcome_ids"] for kind, p in self.calls if kind == "insert"]


def at(seconds):
    return lambda: T0 + timedelta(seconds=seconds)


# ── the switch ──────────────────────────────────────────────────────────────


@pytest.mark.parametrize("points, keepalive, venue, on", [
    (None, None, "kalshi", False),
    ("kalshi", None, "kalshi", False),      # points on, keep-alive unset
    ("kalshi", "0", "kalshi", False),
    ("kalshi", "1", "kalshi", True),
    ("kalshi", "on", "kalshi", True),
    ("kalshi", "1", "polymarket", False),   # points off for the venue
    (None, "1", "kalshi", False),           # keep-alive alone does nothing
    ("all", "on", "polymarket", True),
])
def test_the_switch_defaults_off_and_needs_points_on(points, keepalive, venue, on):
    env = {}
    if points is not None:
        env[shp.STREAM_HISTORY_ENV] = points
    if keepalive is not None:
        env[shp.STREAM_HISTORY_KEEPALIVE_ENV] = keepalive
    assert stream_history_keepalive_enabled(venue, env) is on


def test_the_switch_is_read_when_the_consumer_starts(monkeypatch):
    monkeypatch.setenv(shp.STREAM_HISTORY_ENV, "kalshi")
    monkeypatch.delenv(shp.STREAM_HISTORY_KEEPALIVE_ENV, raising=False)
    assert StreamHistoryPoints("kalshi").keepalive is False
    monkeypatch.setenv(shp.STREAM_HISTORY_KEEPALIVE_ENV, "1")
    assert StreamHistoryPoints("kalshi").keepalive is True
    assert StreamHistoryPoints("polymarket").keepalive is False
    # Points off ⇒ keep-alive off, whatever its own switch says.
    assert StreamHistoryPoints("kalshi", enabled=False, keepalive=True).keepalive is False


async def test_switch_off_runs_no_pass_and_no_statement():
    h = history(keepalive=False)
    db = FakeDB({1: 0.42})
    assert await h.keepalive_pass(db, [(1, 9)], now=at(0)) is None
    assert db.sessions == 0 and db.calls == []
    assert h.keepalive_plan([(1, 9)], T0).legs == []


# ── the rule ────────────────────────────────────────────────────────────────


class TestTheRule:
    @pytest.mark.parametrize("age, due", [(899, False), (900, True), (901, True)])
    def test_due_at_fifteen_minutes(self, age, due):
        h = pointed(history(), 1, T0)
        now = T0 + timedelta(seconds=age)
        assert h.keepalive_due(1, now) is due
        assert [oid for oid, _m in h.keepalive_plan([(1, 9)], now).legs] == ([1] if due else [])

    def test_an_unchanged_price_is_still_due(self):
        """The move rule says no (same price); the keep-alive says yes."""
        h = pointed(history(), 1, T0, prob=0.42)
        later = T0 + timedelta(seconds=HISTORY_KEEPALIVE_S + 1)
        assert h.due(1, 0.42, later) is False
        assert h.keepalive_due(1, later) is True

    async def test_an_unchanged_price_gets_its_point_and_memory_moves_on(self):
        h = pointed(history(), 1, T0, prob=0.42)
        db = FakeDB({1: 0.42}, db_now=T0 + timedelta(seconds=901))
        plan = await h.keepalive_pass(db, [(1, 9)], now=at(901))
        assert db.inserted_ids() == [[1]] and db.commits == 1
        assert plan.written == {1: (0.42, T0 + timedelta(seconds=901))}
        assert h.last_point[1] == (0.42, T0 + timedelta(seconds=901))
        assert h.stats["history_keepalive"] == 1
        # Fifteen minutes from the NEW point, not the old one.
        assert h.keepalive_due(1, T0 + timedelta(seconds=901 + 899)) is False

    def test_refused_and_settled_legs_never(self):
        settled = {7}
        h = history(refused_market=lambda mid: mid in settled)
        h.refuse_market(8)
        h.refuse_outcome(6)
        stale = T0 - timedelta(hours=1)
        for oid in (4, 5, 6, 10):
            pointed(h, oid, stale)
        legs = [(4, 7), (5, 8), (6, 1), (10, 1)]
        assert h.keepalive_plan(legs, T0).legs == [(10, 1)]

    def test_a_refusing_callback_that_raises_refuses(self):
        def boom(_mid):
            raise RuntimeError("no answer")

        h = pointed(history(refused_market=boom), 1, T0 - timedelta(hours=1))
        assert h.keepalive_plan([(1, 9)], T0).legs == []

    async def test_a_leg_the_insert_refused_is_held_for_an_interval(self):
        """Graded/settled/terminal in SQL: counted, memory unchanged, and not
        asked again every minute."""
        h = pointed(history(), 1, T0 - timedelta(hours=1))
        db = FakeDB({1: 0.42}, refuse={1})
        plan = await h.keepalive_pass(db, [(1, 9)], now=at(0))
        assert plan.legs == [(1, 9)] and plan.written == {}
        assert h.last_point[1][1] == T0 - timedelta(hours=1)
        assert h.stats["history_refused"] == 1 and h.stats["history_keepalive"] == 0
        assert await h.keepalive_pass(db, [(1, 9)], now=at(60)) is not None
        assert db.inserted_ids() == [[1]], "held: not asked again a minute later"
        await h.keepalive_pass(db, [(1, 9)], now=at(HISTORY_KEEPALIVE_S))
        assert db.inserted_ids() == [[1], [1]]


# ── the cap ─────────────────────────────────────────────────────────────────


class TestTheSharedCap:
    def test_move_points_spend_the_keepalives_room(self):
        h = history()
        rows = [SimpleNamespace(id=oid, market_id=9, last_updated=T0) for oid in range(100, 120)]
        plan = h.plan(rows, {oid: 0.3 for oid in range(100, 120)})
        plan.written = {p.outcome_id for p in plan.points}
        h.committed(plan)  # 20 move points in market 9 this minute
        stale = T0 - timedelta(hours=1)
        for oid in range(1, 11):
            pointed(h, oid, stale + timedelta(seconds=oid))
        ka = h.keepalive_plan([(oid, 9) for oid in range(1, 11)], T0 + timedelta(seconds=10))
        assert len(ka.legs) == HISTORY_MAX_PER_MARKET_MINUTE - 20
        assert ka.capped == 10 - (HISTORY_MAX_PER_MARKET_MINUTE - 20)
        # Stalest first.
        assert [oid for oid, _m in ka.legs] == [1, 2, 3, 4]

    def test_keepalive_points_spend_the_move_points_room(self):
        h = history()
        stale = T0 - timedelta(hours=1)
        for oid in range(1, 21):
            pointed(h, oid, stale)
        ka = h.keepalive_plan([(oid, 9) for oid in range(1, 21)], T0)
        assert len(ka.legs) == 20
        rows = [SimpleNamespace(id=oid, market_id=9, last_updated=T0) for oid in range(100, 110)]
        quotes = {oid: 0.3 for oid in range(100, 110)}
        # In flight: its reservation already counts against a flush.
        assert len(h.plan(rows, quotes).points) == HISTORY_MAX_PER_MARKET_MINUTE - 20
        # Committed: counted in `_market_minute` exactly like move points.
        ka.written = {oid: (0.42, T0) for oid, _m in ka.legs}
        h.keepalive_committed(ka)
        assert h._market_minute[9] == (shp._minute(T0), 20)
        assert len(h.plan(rows, quotes).points) == HISTORY_MAX_PER_MARKET_MINUTE - 20

    def test_a_released_plan_gives_its_room_back(self):
        h = history()
        for oid in range(1, 25):
            pointed(h, oid, T0 - timedelta(hours=1))
        ka = h.keepalive_plan([(oid, 9) for oid in range(1, 25)], T0)
        assert len(ka.legs) == 24 and h._used(9, shp._minute(T0)) == 24
        h.keepalive_release(ka)
        h.keepalive_release(ka)  # idempotent
        assert h._used(9, shp._minute(T0)) == 0 and h._market_minute == {}

    def test_the_pass_ceiling_takes_the_stalest(self, monkeypatch):
        monkeypatch.setattr(shp, "HISTORY_KEEPALIVE_MAX_PER_PASS", 3)
        h = history()
        for oid in range(1, 7):
            pointed(h, oid, T0 - timedelta(hours=2) + timedelta(minutes=oid))
        ka = h.keepalive_plan([(oid, oid) for oid in range(1, 7)], T0)
        assert [oid for oid, _m in ka.legs] == [1, 2, 3] and ka.capped == 3


# ── commit, failure ─────────────────────────────────────────────────────────


class TestCommitAndFailure:
    @pytest.mark.parametrize("fail", ["seed", "insert", "commit"])
    async def test_a_failed_pass_advances_nothing_and_is_counted(self, fail):
        stale = T0 - timedelta(hours=1)
        h = pointed(history(), 1, stale)
        db = FakeDB({1: 0.42, 2: 0.5}, fail=fail)
        await h.keepalive_pass(db, [(1, 9), (2, 9)], now=at(0))
        assert h.last_point[1] == (0.42, stale)
        assert h.stats["history_keepalive"] == 0
        assert h.stats["history_keepalive_errors"] == 1
        assert h._reserved == {} and h._market_minute == {}
        # The legs stay due: the next pass writes them.
        db.fail = None
        plan = await h.keepalive_pass(db, [(1, 9), (2, 9)], now=at(60))
        assert sorted(plan.written) == [1, 2] and h.stats["history_keepalive"] == 2

    async def test_a_pass_over_its_time_bound_is_counted_and_releases(self):
        h = pointed(history(), 1, T0 - timedelta(hours=1))

        class Slow:
            async def __aenter__(self):
                return self

            async def __aexit__(self, *_exc):
                return False

            async def execute(self, stmt, params=None):
                await asyncio.sleep(10)

        await h.keepalive_pass(lambda: Slow(), [(1, 9)], now=at(0), timeout_s=0.05)
        assert h.stats["history_keepalive_errors"] == 1
        assert h._reserved == {} and h.last_point[1][1] == T0 - timedelta(hours=1)

    async def test_a_failed_keepalive_never_touches_a_price_flush(self):
        """Same writer, same leg, same minute: the keep-alive fails, the move
        point from the flush still plans its full room, writes and commits."""
        h = pointed(history(), 1, T0 - timedelta(hours=1), prob=0.40)
        for oid in range(2, 25):
            pointed(h, oid, T0 - timedelta(hours=1))
        await h.keepalive_pass(FakeDB({}, fail="insert"), [(oid, 9) for oid in range(1, 25)],
                               now=at(0))
        assert h.stats["history_keepalive_errors"] == 1
        rows = [SimpleNamespace(id=1, market_id=9, last_updated=T0 + timedelta(seconds=1))]
        plan = h.plan(rows, {1: 0.45})
        assert [p.outcome_id for p in plan.points] == [1] and plan.capped == 0
        plan.written = {1}
        h.committed(plan)
        assert h.stats["history_points"] == 1 and h.last_point[1][0] == 0.45

    async def test_memory_never_moves_back_past_a_newer_flush_point(self):
        h = pointed(history(), 1, T0 - timedelta(hours=1))
        ka = h.keepalive_plan([(1, 9)], T0)
        h.last_point[1] = (0.55, T0 + timedelta(seconds=5))  # a flush landed meanwhile
        ka.written = {1: (0.42, T0)}
        h.keepalive_committed(ka)
        assert h.last_point[1] == (0.55, T0 + timedelta(seconds=5))


# ── seeding ─────────────────────────────────────────────────────────────────


class TestSeeding:
    async def test_only_memoryless_live_legs_and_only_once(self):
        h = pointed(history(), 1, T0 - timedelta(minutes=5))
        db = FakeDB(
            {1: 0.4, 2: 0.5, 3: 0.6, 4: 0.7},
            snapshots={2: (0.5, T0 - timedelta(minutes=20)),
                       4: (0.7, T0 - timedelta(minutes=5))},
        )
        legs = [(1, 9), (2, 9), (3, 9), (4, 9)]
        plan = await h.keepalive_pass(db, legs, now=at(0))
        (seed,) = [p for kind, p in db.calls if kind == "seed"]
        assert sorted(seed["keepalive_seed_ids"]) == [2, 3, 4]
        # 2: newest point 20 min old → due. 3: no point at all → due.
        # 4: newest point 5 min old → not due. 1: memory 5 min old → not due.
        assert sorted(oid for oid, _m in plan.legs) == [2, 3]
        assert plan.seeded == 2
        await h.keepalive_pass(db, legs, now=at(60))
        assert db.kinds().count("seed") == 1, "seeded once"

    async def test_an_unseeded_leg_is_not_due_before_its_seed(self):
        h = history()
        assert h.keepalive_due(5, T0) is False
        assert h.keepalive_plan([(5, 9)], T0).legs == []

    async def test_the_seed_is_bounded_per_pass(self, monkeypatch):
        monkeypatch.setattr(shp, "HISTORY_KEEPALIVE_SEED_BATCH", 2)
        h = history()
        db = FakeDB({oid: 0.5 for oid in range(1, 6)})
        legs = [(oid, 9) for oid in range(1, 6)]
        for minute in range(3):
            await h.keepalive_pass(db, legs, now=at(60 * minute))
        asked = [p["keepalive_seed_ids"] for kind, p in db.calls if kind == "seed"]
        assert [len(a) for a in asked] == [2, 2, 1]
        assert sorted(sum(asked, [])) == [1, 2, 3, 4, 5]

    def test_a_seed_never_overwrites_a_newer_point(self):
        h = pointed(history(), 1, T0, prob=0.6)
        h.keepalive_seeded([1, 2], [(1, 0.5, T0 - timedelta(minutes=30)),
                                    (2, 0.5, T0 - timedelta(minutes=30))])
        assert h.last_point[1] == (0.6, T0)
        assert h.last_point[2] == (0.5, T0 - timedelta(minutes=30))

    def test_the_seed_reads_one_newest_row_per_leg(self):
        sql = str(keepalive_seed_statement().compile(dialect=postgresql.dialect()))
        assert "JOIN LATERAL" in sql
        assert "WHERE futures_odds_snapshots.outcome_id = keepalive_seed.outcome_id" in sql
        assert "ORDER BY futures_odds_snapshots.captured_at DESC" in sql
        assert "LIMIT" in sql and "GROUP BY" not in sql and "max(" not in sql.lower()


# ── memory ──────────────────────────────────────────────────────────────────


def test_a_live_leg_is_never_pruned():
    h = history()
    old = T0 - timedelta(hours=5)
    pointed(h, 1, old)
    pointed(h, 2, old)
    h._live = frozenset({1})
    h._prune(T0)
    assert 1 in h.last_point and 2 not in h.last_point


async def test_the_pass_records_the_live_population():
    h = history()
    await h.keepalive_pass(FakeDB({}), [(1, 9), (2, 9)], now=at(0))
    assert h._live == frozenset({1, 2})


# ── the statement ───────────────────────────────────────────────────────────


class TestTheStatement:
    def test_the_price_is_read_from_futures_outcomes(self):
        """The guard: the point's probability is the stored row's, and the
        only thing the pass binds is which legs."""
        stmt = keepalive_insert_statement("kalshi")
        assert isinstance(stmt, Insert) and stmt.table.name == "futures_odds_snapshots"
        compiled = stmt.compile(dialect=postgresql.dialect())
        sql = str(compiled)
        assert sql.startswith(
            "INSERT INTO futures_odds_snapshots (outcome_id, bookmaker, probability, "
            "american_odds, yes_bid, yes_ask, captured_at, reading_count) SELECT "
            "futures_outcomes.id, CAST(%(param_1)s AS VARCHAR(50)) AS anon_1, "
            "futures_outcomes.current_probability, "
        )
        assert "FROM futures_outcomes JOIN futures_markets" in sql
        assert "now()" in sql
        # What a caller binds is WHICH legs; every other bind is a constant
        # of the statement (venue, 0.5/100/1, the refusals, the 0 < p < 1 bounds).
        named = {key for key in compiled.params if not key.startswith(("param_", "%("))}
        assert named - {"resolution_source_1", "status_1", "current_probability_1",
                        "current_probability_2"} == {"keepalive_outcome_ids", "reading_count"}
        assert (compiled.params["current_probability_1"],
                compiled.params["current_probability_2"]) == (0, 1)
        assert "RETURNING futures_odds_snapshots.outcome_id, futures_odds_snapshots.probability, "\
               "futures_odds_snapshots.captured_at" in sql

    async def test_the_pass_binds_only_the_due_ids(self):
        h = pointed(history(), 1, T0 - timedelta(hours=1))
        db = FakeDB({1: 0.42})
        await h.keepalive_pass(db, [(1, 9)], now=at(0))
        (params,) = [p for kind, p in db.calls if kind == "insert"]
        assert params == {"keepalive_outcome_ids": [1]}

    def test_it_refuses_what_the_move_insert_refuses_and_more(self):
        sql = str(keepalive_insert_statement("polymarket").compile(dialect=postgresql.dialect()))
        assert "futures_outcomes.is_winner IS NOT true" in sql
        assert "futures_outcomes.resolution_source NOT IN" in sql
        assert "futures_markets.status IS DISTINCT FROM" in sql
        assert "futures_markets.settled_at IS NULL" in sql
        assert "futures_outcomes.current_probability > " in sql
        assert "futures_outcomes.current_probability < " in sql

    def test_the_same_bookmaker_as_the_move_points(self):
        for venue in ("kalshi", "polymarket"):
            params = keepalive_insert_statement(venue).compile(dialect=postgresql.dialect()).params
            assert params["param_1"] == venue

    def test_polymarket_carries_no_book_and_kalshi_only_a_bracketing_one(self):
        poly = str(keepalive_insert_statement("polymarket").compile(dialect=postgresql.dialect()))
        assert "current_yes_bid" not in poly and "CAST(NULL AS NUMERIC(5, 4))" in poly
        kalshi = str(keepalive_insert_statement("kalshi").compile(dialect=postgresql.dialect()))
        assert ("futures_outcomes.current_yes_bid <= futures_outcomes.current_probability AND "
                "futures_outcomes.current_probability <= futures_outcomes.current_yes_ask") in kalshi

    def test_rigs_can_name_the_statements(self):
        assert is_keepalive_statement(keepalive_seed_statement())
        assert is_keepalive_statement(keepalive_insert_statement("kalshi"))
        assert not is_keepalive_statement(shp.history_insert_statement("kalshi"))
        assert not shp.is_history_insert(keepalive_insert_statement("kalshi"))


# ── where it runs ───────────────────────────────────────────────────────────


def _function_source(path, name):
    tree = ast.parse((BACKEND / path).read_text())
    found = [ast.unparse(node) for node in ast.walk(tree)
             if isinstance(node, (ast.AsyncFunctionDef, ast.FunctionDef)) and node.name == name]
    assert found, f"{name} not found in {path}"
    return "\n".join(found)


@pytest.mark.parametrize("path, flushes", [
    ("app/tasks/kalshi_ws.py", ("flush_prices", "timed_flush", "flush_loop")),
    ("app/tasks/polymarket_ws.py", ("write_chunk", "_flush_prices", "timed_game_flush",
                                    "flush_loop", "_flush_props", "_flush_standalone")),
])
def test_the_pass_runs_from_the_stats_loop_never_a_flush(path, flushes):
    assert ".keepalive_pass(get_task_session" in _function_source(path, "stats_loop")
    for name in flushes:
        source = _function_source(path, name)
        assert "keepalive" not in source, f"{name} reaches the keep-alive"


def test_the_minute_lines_carry_the_keepalive_counters(caplog):
    import logging

    from app.tasks import polymarket_ws as pm

    assert {"history_keepalive", "history_keepalive_errors"} <= set(shp.HISTORY_COUNTERS)
    kalshi = (BACKEND / "app/tasks/kalshi_ws.py").read_text()
    assert ('"bundled_refused=%d parked=%d history_points=%d "\n'
            '                "history_keepalive=%d history_keepalive_errors=%d "') in kalshi
    stats = {"price_updates": 0, "trade_updates": 0, "resolutions": 0, "errors": 0,
             "history_points": 3, "history_keepalive": 12, "history_keepalive_errors": 2}
    with caplog.at_level(logging.INFO, logger=pm.logger.name):
        pm._log_stats_line(stats, {}, {"stamped": 0, "no_reading": 0, "throttled": 0, "errors": 0})
    (line,) = [r.getMessage() for r in caplog.records if "Polymarket WS: " in r.getMessage()]
    assert "history_points=3 history_keepalive=12 history_keepalive_errors=2 " in line


def test_the_polymarket_client_names_its_connected_ids():
    from app.services.polymarket_ws import PolymarketWebSocket

    client = PolymarketWebSocket()
    client._shard_ids = {0: ["a", "b"], 1: ["c"], 2: ["d"]}
    client._shards_connected = {0, 2}
    assert client.connected_asset_ids() == {"a", "b", "d"}
    client._shards_connected = set()
    assert client.connected_asset_ids() == set()


# ── through the real consumers (fake sessions, runs everywhere) ─────────────


def _fast_minute(monkeypatch):
    """The stats loop's 60 s sleep becomes a yield, so the minute loop runs
    inside the rig's short run. Every other sleep is unchanged."""
    from tests.test_a_settled_leg_takes_no_live_price_5411 import _NoopRefresher as Kalshi
    from tests.test_poly_ws_side1_leg_pairing_8403 import _NoopRefresher as Poly

    blend = {"stamped": 0, "no_reading": 0, "throttled": 0, "errors": 0}
    for refresher in (Kalshi, Poly):
        monkeypatch.setattr(refresher, "stats", blend, raising=False)
    real = asyncio.sleep

    async def sleep(delay, *a, **kw):
        return await real(0 if delay == 60 else delay, *a, **kw)

    monkeypatch.setattr(asyncio, "sleep", sleep)


_REAL_PASS = StreamHistoryPoints.keepalive_pass


def _spy_passes(monkeypatch, db=None):
    """Every keep-alive pass the consumers run: its legs; the real pass runs
    over ``db`` when one is given."""
    passes = []
    real = _REAL_PASS

    async def spy(self, session_factory, legs, **kw):
        legs = list(legs)
        passes.append(legs)
        if db is None:
            return None
        return await real(self, db, legs, **kw)

    monkeypatch.setattr(StreamHistoryPoints, "keepalive_pass", spy)
    return passes


def _subscribed(monkeypatch):
    """The 8753 rig never acknowledges a subscription; stand one in."""
    import app.services.kalshi_ws as kalshi_svc

    monkeypatch.setattr(kalshi_svc.KalshiWebSocket, "is_subscribed",
                        property(lambda self: self.is_connected))


class TestThroughTheKalshiConsumer:
    async def test_the_population_is_what_a_subscribed_socket_carries(self, monkeypatch):
        from tests.test_stream_history_points_11929 import _drive_kalshi, _Recorder

        monkeypatch.setenv(shp.STREAM_HISTORY_ENV, "kalshi")
        monkeypatch.setenv(shp.STREAM_HISTORY_KEEPALIVE_ENV, "1")
        _fast_minute(monkeypatch)
        _subscribed(monkeypatch)
        passes = _spy_passes(monkeypatch)
        rig = await _drive_kalshi(monkeypatch, _Recorder(monkeypatch))
        assert passes, "the stats loop ran no keep-alive pass"
        assert [(rig.OUTCOME_ID, rig.MARKET_ID)] in passes

    async def test_an_unacknowledged_socket_has_no_live_legs(self, monkeypatch):
        """Not subscribed ⇒ not being read ⇒ no point."""
        from tests.test_stream_history_points_11929 import _drive_kalshi, _Recorder

        monkeypatch.setenv(shp.STREAM_HISTORY_ENV, "kalshi")
        monkeypatch.setenv(shp.STREAM_HISTORY_KEEPALIVE_ENV, "1")
        _fast_minute(monkeypatch)
        passes = _spy_passes(monkeypatch)
        await _drive_kalshi(monkeypatch, _Recorder(monkeypatch))
        assert passes and all(legs == [] for legs in passes)

    @pytest.mark.parametrize("points, keepalive", [("kalshi", "0"), ("polymarket", "1"), ("0", "1")])
    async def test_no_pass_with_the_switch_off(self, monkeypatch, points, keepalive):
        from tests.test_stream_history_points_11929 import _drive_kalshi, _Recorder

        monkeypatch.setenv(shp.STREAM_HISTORY_ENV, points)
        monkeypatch.setenv(shp.STREAM_HISTORY_KEEPALIVE_ENV, keepalive)
        _fast_minute(monkeypatch)
        _subscribed(monkeypatch)
        passes = _spy_passes(monkeypatch)
        recorder = _Recorder(monkeypatch)
        await _drive_kalshi(monkeypatch, recorder)
        assert passes == []
        assert [k for _s, k, _p in recorder.log].count("price") >= 1

    async def test_the_pass_writes_and_a_failing_one_leaves_the_flush_alone(self, monkeypatch):
        from tests.test_stream_history_points_11929 import _drive_kalshi, _Recorder
        import tests.test_kalshi_socket_prices_by_the_rest_rule_8753 as rig

        monkeypatch.setenv(shp.STREAM_HISTORY_ENV, "kalshi")
        monkeypatch.setenv(shp.STREAM_HISTORY_KEEPALIVE_ENV, "1")
        for fail in (None, "open"):
            _fast_minute(monkeypatch)
            _subscribed(monkeypatch)
            # The rig's move point is stamped 2026-10-07 (`_kalshi_price_session`),
            # weeks before any wall clock this runs on: the leg is due.
            db = FakeDB({rig.OUTCOME_ID: 0.42}, fail=fail, db_now=None)
            _spy_passes(monkeypatch, db)
            recorder = _Recorder(monkeypatch)
            await _drive_kalshi(monkeypatch, recorder)
            (instance,) = recorder.instances
            # The price write and its move point, either way.
            assert [k for _s, k, _p in recorder.log].count("price") >= 1
            assert len(recorder.history_inserts()) == 1
            assert instance.stats["history_points"] == 1
            if fail is None:
                assert instance.stats["history_keepalive_errors"] == 0
                assert db.inserted_ids() and all(
                    ids == [rig.OUTCOME_ID] for ids in db.inserted_ids())
                assert instance.stats["history_keepalive"] == len(db.inserted_ids())
            else:
                assert instance.stats["history_keepalive_errors"] >= 1
                assert instance.stats["history_keepalive"] == 0


class TestThroughThePolymarketConsumer:
    async def test_the_population_is_what_a_connected_socket_carries(self, monkeypatch):
        from tests.test_stream_history_points_11929 import _drive_polymarket, _Recorder

        monkeypatch.setenv(shp.STREAM_HISTORY_ENV, "polymarket")
        monkeypatch.setenv(shp.STREAM_HISTORY_KEEPALIVE_ENV, "on")
        _fast_minute(monkeypatch)
        passes = _spy_passes(monkeypatch)
        rig, writes = await _drive_polymarket(monkeypatch, _Recorder(monkeypatch))
        assert writes and passes, "the stats loop ran no keep-alive pass"
        live = max(passes, key=len)
        assert {oid for oid, _mid in live} >= {oid for oid, _p in writes}
        assert {mid for _oid, mid in live} == {rig.MARKET_ID}

    async def test_no_pass_with_the_switch_off(self, monkeypatch):
        from tests.test_stream_history_points_11929 import _drive_polymarket, _Recorder

        monkeypatch.setenv(shp.STREAM_HISTORY_ENV, "polymarket")
        monkeypatch.delenv(shp.STREAM_HISTORY_KEEPALIVE_ENV, raising=False)
        _fast_minute(monkeypatch)
        passes = _spy_passes(monkeypatch)
        _rig, writes = await _drive_polymarket(monkeypatch, _Recorder(monkeypatch))
        assert writes and passes == []


# ── real PostgreSQL (production's asyncpg driver) ───────────────────────────


def _snapshots(engine):
    from sqlalchemy import text

    with engine.connect() as conn:
        return [tuple(r) for r in conn.execute(text(
            "SELECT outcome_id, bookmaker, probability, american_odds, yes_bid, yes_ask, "
            "captured_at, reading_count FROM futures_odds_snapshots ORDER BY id"
        ))]


async def _pg_pass(tmp_path, *, venue="kalshi", setup=(), h=None, **database):
    """One keep-alive pass on asyncpg against the #9484 rig's schema."""
    import os

    from sqlalchemy import text
    from sqlalchemy.engine import make_url
    from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine

    import tests.pm_bulk_test_support as support
    import tests.test_ws_market_change_hooks_9484 as hooks
    from app.models.models import FuturesOddsSnapshot

    engine = hooks._database(tmp_path, **database)  # skips without SEARCH_TEST_DATABASE_URL
    FuturesOddsSnapshot.__table__.create(engine)
    with engine.begin() as conn:
        for sql in setup:
            conn.execute(text(sql))
    schema = support._ENGINES[-1][2]
    url = make_url(os.environ["SEARCH_TEST_DATABASE_URL"]).set(drivername="postgresql+asyncpg")
    aengine = create_async_engine(url, connect_args={"server_settings": {"search_path": schema}})
    h = h or history(venue=venue)
    try:
        plan = await h.keepalive_pass(
            lambda: AsyncSession(aengine), [(hooks.OUTCOME_ID, hooks.MARKET_ID)],
        )
        async with AsyncSession(aengine) as session:
            db_now = (await session.execute(text("SELECT now()"))).scalar_one()
    finally:
        await aengine.dispose()
    return hooks, engine, h, plan, db_now


class TestOnRealPostgres:
    async def test_the_point_is_the_stored_row_after_a_stale_seed(self, tmp_path):
        old = "now() - interval '20 minutes'"
        hooks, engine, h, plan, db_now = await _pg_pass(
            tmp_path, current_probability=0.62, book=(0.60, 0.64),
            setup=[f"INSERT INTO futures_odds_snapshots (outcome_id, bookmaker, probability, "
                   f"captured_at, reading_count) VALUES (81, 'kalshi', 0.62, {old}, 1)"],
        )
        assert h.stats["history_keepalive_errors"] == 0 and plan.seeded == 1
        rows = _snapshots(engine)
        assert len(rows) == 2
        oid, bookmaker, prob, american, bid, ask, captured_at, readings = rows[-1]
        assert (oid, bookmaker, readings) == (hooks.OUTCOME_ID, "kalshi", 1)
        assert (float(prob), american, float(bid), float(ask)) == (0.62, -163, 0.60, 0.64)
        assert abs((db_now - captured_at).total_seconds()) < 60
        assert plan.written[hooks.OUTCOME_ID] == (0.62, captured_at)
        assert h.last_point[hooks.OUTCOME_ID] == (0.62, captured_at)

    async def test_a_recent_snapshot_seeds_and_writes_nothing(self, tmp_path):
        recent = "now() - interval '5 minutes'"
        _hooks, engine, h, plan, _now = await _pg_pass(
            tmp_path,
            setup=[f"INSERT INTO futures_odds_snapshots (outcome_id, bookmaker, probability, "
                   f"captured_at, reading_count) VALUES (81, 'kalshi', 0.30, {recent}, 1)"],
        )
        assert plan.seeded == 1 and plan.legs == []
        assert len(_snapshots(engine)) == 1

    async def test_a_leg_with_no_point_gets_one_and_polymarket_has_no_book(self, tmp_path):
        hooks, engine, h, _plan, _now = await _pg_pass(
            tmp_path, venue="polymarket", current_probability=0.25, book=(0.24, 0.26),
        )
        [(oid, bookmaker, prob, american, bid, ask, _at, _n)] = _snapshots(engine)
        assert (oid, bookmaker, float(prob), american, bid, ask) == (
            hooks.OUTCOME_ID, "polymarket", 0.25, 300, None, None)
        assert h.stats["history_keepalive"] == 1

    async def test_a_book_that_does_not_bracket_the_price_is_dropped(self, tmp_path):
        _hooks, engine, _h, _plan, _now = await _pg_pass(
            tmp_path, current_probability=0.50, book=(0.30, 0.34),
        )
        [(_oid, _b, prob, _am, bid, ask, _at, _n)] = _snapshots(engine)
        assert (float(prob), bid, ask) == (0.50, None, None)

    @pytest.mark.parametrize("database, setup", [
        ({"resolution_source": "api_settlement"}, ()),
        ({}, ("UPDATE futures_markets SET status = 'resolved'",)),
        ({}, ("UPDATE futures_markets SET settled_at = now()",)),
        ({}, ("UPDATE futures_outcomes SET is_winner = true",)),
        ({"current_probability": 1.0}, ()),
        ({"current_probability": None}, ()),
    ])
    async def test_settled_terminal_or_priceless_legs_get_nothing(self, tmp_path, database, setup):
        _hooks, engine, h, plan, _now = await _pg_pass(tmp_path, setup=setup, **database)
        assert _snapshots(engine) == []
        assert plan.legs and plan.written == {}
        assert h.stats["history_refused"] == 1 and h.stats["history_keepalive"] == 0

    async def test_a_failed_insert_writes_nothing_and_counts(self, tmp_path):
        trigger = [
            "CREATE FUNCTION ka_fail() RETURNS trigger LANGUAGE plpgsql AS "
            "$$ BEGIN RAISE EXCEPTION 'boom'; END $$",
            "CREATE TRIGGER ka_fail BEFORE INSERT ON futures_odds_snapshots "
            "FOR EACH ROW EXECUTE FUNCTION ka_fail()",
        ]
        hooks, engine, h, _plan, _now = await _pg_pass(tmp_path, setup=trigger)
        assert _snapshots(engine) == []
        assert h.stats["history_keepalive_errors"] == 1
        assert hooks.OUTCOME_ID not in h.last_point and h._reserved == {}
        assert hooks._stored(engine, "futures_outcomes", "current_probability",
                             hooks.OUTCOME_ID) == pytest.approx(0.30)


def test_keepalive_plan_type_is_exported():
    assert KeepalivePlan(at=T0, minute=shp._minute(T0)).legs == []
