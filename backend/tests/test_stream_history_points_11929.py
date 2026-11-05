"""#11929 cause 2 — the live stream writes bounded chart history from its flush.

WHAT A READER SEES. A futures or props chart drew a handful of dots joined by
dashes because only the polling tasks wrote `futures_odds_snapshots`; a leg the
socket moved 200 times an hour still charted at the poll's cadence. With
`STREAM_HISTORY_POINTS` on, the socket's committed flush adds a chart point when
the leg really moved (>= 1 point, or 5 minutes and a different price).

THE CASES:

* the rule (`StreamHistoryPoints.due` / `plan`): first sight writes, a 1-point
  move writes, a smaller move inside 5 minutes does not, 5 minutes later it
  does, the same price never does;
* the per-market cap holds the rest for a later minute (stalest first) and they
  stay due;
* a rolled-back flush advances no memory and no cap count;
* settled means settled: graded legs, tier-3 settled legs, a market the run saw
  settle, a terminal price, and (in SQL) a resolved market get no point; a
  retracted leg (`ungradeable_result`) does;
* the rows ride the existing flush transaction as ONE INSERT per flush, absent
  with the switch off — through the REAL Kalshi and Polymarket consumers
  (fake-session rigs everywhere; the real-PostgreSQL rig of
  `test_ws_market_change_hooks_9484` where `SEARCH_TEST_DATABASE_URL` is set);
* the previews (market preview, blend preview) never write a snapshot;
* the minute lines carry the counters.
"""

from __future__ import annotations

import ast
import json
from datetime import datetime, timedelta, timezone
from pathlib import Path
from types import SimpleNamespace

import pytest
from sqlalchemy.dialects import postgresql
from sqlalchemy.sql.dml import Insert, Update

import app.utils.stream_history_points as shp
from app.utils.stream_history_points import (
    HISTORY_MAX_PER_MARKET_MINUTE,
    StreamHistoryPoints,
    history_insert_parameters,
    history_insert_statement,
    is_history_insert,
    stream_history_venues,
)

BACKEND = Path(__file__).resolve().parents[1]
T0 = datetime(2026, 11, 3, 23, 0, 5, tzinfo=timezone.utc)


def row(oid, *, market_id=1, at=T0, **extra):
    """One RETURNING row of a flush's price UPDATE."""
    return SimpleNamespace(id=oid, market_id=market_id, last_updated=at, **extra)


def history(**kwargs):
    kwargs.setdefault("enabled", True)
    return StreamHistoryPoints("kalshi", **kwargs)


def commit_all(h, plan):
    """The INSERT returned every planned row, and the flush committed."""
    plan.written = {p.outcome_id for p in plan.points}
    h.committed(plan)


# ── the switch ──────────────────────────────────────────────────────────────


@pytest.mark.parametrize("raw, venues", [
    (None, set()), ("", set()), ("0", set()), ("off", set()),
    ("1", {"kalshi", "polymarket"}), ("all", {"kalshi", "polymarket"}),
    ("kalshi", {"kalshi"}), ("polymarket", {"polymarket"}),
    (" Kalshi , polymarket ", {"kalshi", "polymarket"}), ("espn", set()),
])
def test_the_switch_names_venues_and_defaults_off(raw, venues):
    assert stream_history_venues(raw) == venues


def test_the_default_is_off(monkeypatch):
    monkeypatch.delenv(shp.STREAM_HISTORY_ENV, raising=False)
    assert StreamHistoryPoints("kalshi").enabled is False
    assert StreamHistoryPoints("polymarket").enabled is False
    monkeypatch.setenv(shp.STREAM_HISTORY_ENV, "kalshi")
    assert StreamHistoryPoints("kalshi").enabled is True
    assert StreamHistoryPoints("polymarket").enabled is False


def test_off_plans_nothing():
    h = history(enabled=False)
    plan = h.plan([row(1)], {1: 0.42})
    assert plan.points == [] and h.last_point == {}


# ── the rule ────────────────────────────────────────────────────────────────


class TestTheBound:
    def test_first_sight_writes(self):
        h = history()
        plan = h.plan([row(1)], {1: (0.42, 0.40, 0.44)})
        assert [(p.outcome_id, p.probability, p.yes_bid, p.yes_ask, p.captured_at)
                for p in plan.points] == [(1, 0.42, 0.40, 0.44, T0)]

    def test_a_one_point_move_writes_and_a_smaller_one_inside_five_minutes_does_not(self):
        h = history()
        commit_all(h, h.plan([row(1)], {1: 0.56}))
        later = T0 + timedelta(seconds=20)
        # 0.57 - 0.56 is 0.00999… in floats: still a whole point.
        assert h.due(1, 0.57, later) is True
        assert h.due(1, 0.5650, later) is False
        assert h.due(1, 0.5501, later) is False
        plan = h.plan([row(1, at=later)], {1: 0.565})
        assert plan.points == [] and plan.skipped == 1

    def test_five_minutes_later_a_smaller_move_writes(self):
        h = history()
        commit_all(h, h.plan([row(1)], {1: 0.56}))
        assert h.due(1, 0.563, T0 + timedelta(seconds=299)) is False
        five = T0 + timedelta(seconds=300)
        plan = h.plan([row(1, at=five)], {1: 0.563})
        assert [p.probability for p in plan.points] == [0.563]

    def test_the_same_price_never_writes_again(self):
        """A liveness re-stamp of an unchanged price adds nothing to a chart."""
        h = history()
        commit_all(h, h.plan([row(1)], {1: 0.56}))
        plan = h.plan([row(1, at=T0 + timedelta(hours=0.5))], {1: 0.56})
        assert plan.points == [] and plan.skipped == 1

    def test_the_point_is_the_stored_precision_and_the_rows_own_clock(self):
        h = history()
        stamp = T0 + timedelta(milliseconds=731)
        plan = h.plan([row(1, at=stamp)], {1: 0.41234567})
        assert plan.points[0].probability == 0.412346
        assert plan.points[0].captured_at == stamp

    def test_half_a_book_is_no_book(self):
        h = history()
        plan = h.plan([row(1)], {1: (0.42, 0.40, None)})
        assert (plan.points[0].yes_bid, plan.points[0].yes_ask) == (None, None)

    def test_a_row_the_update_did_not_return_is_never_planned(self):
        """The batch carries 2 and 3; the UPDATE returned only 2."""
        h = history()
        plan = h.plan([row(2)], {2: 0.4, 3: 0.6})
        assert [p.outcome_id for p in plan.points] == [2]

    def test_a_held_back_polymarket_row_is_not_a_write(self):
        h = history()
        plan = h.plan([row(2, skipped=True), row(3, skipped=False)], {2: 0.4, 3: 0.6})
        assert [p.outcome_id for p in plan.points] == [3]


# ── the cap ─────────────────────────────────────────────────────────────────


class TestTheCap:
    def test_the_cap_is_per_market_per_minute_and_the_rest_stay_due(self):
        h = history()
        legs = list(range(1, 31))
        rows = [row(oid, market_id=9) for oid in legs] + [row(100, market_id=10)]
        quotes = {oid: 0.01 * (oid + 10) for oid in legs} | {100: 0.5}
        plan = h.plan(rows, quotes)
        assert len([p for p in plan.points if p.market_id == 9]) == HISTORY_MAX_PER_MARKET_MINUTE
        assert [p.outcome_id for p in plan.points if p.market_id == 10] == [100]
        assert plan.capped == 30 - HISTORY_MAX_PER_MARKET_MINUTE
        commit_all(h, plan)
        written = {p.outcome_id for p in plan.points}
        held = [oid for oid in legs if oid not in written]
        assert len(held) == 6 and all(oid not in h.last_point for oid in held)

        # Same minute: no room left in market 9; the held legs stay due.
        same_minute = T0 + timedelta(seconds=30)
        again = h.plan([row(oid, market_id=9, at=same_minute) for oid in held], quotes)
        assert again.points == [] and again.capped == 6
        h.committed(again)

        # Next minute: they go, ahead of legs that already have a point.
        next_minute = T0 + timedelta(seconds=60)
        moved = {oid: quotes[oid] + 0.05 for oid in legs}
        third = h.plan([row(oid, market_id=9, at=next_minute) for oid in legs], moved)
        assert len(third.points) == HISTORY_MAX_PER_MARKET_MINUTE
        assert set(held) <= {p.outcome_id for p in third.points}
        assert third.capped == 6

    def test_a_rolled_back_flush_spends_no_cap(self):
        h = history()
        rows = [row(oid, market_id=9) for oid in range(1, 25)]
        plan = h.plan(rows, {oid: 0.3 for oid in range(1, 25)})
        assert len(plan.points) == 24
        # Never committed: the next flush in the same minute has the full room.
        retry = h.plan(rows, {oid: 0.3 for oid in range(1, 25)})
        assert len(retry.points) == 24 and retry.capped == 0


# ── rollback ────────────────────────────────────────────────────────────────


class TestRollback:
    def test_a_rolled_back_flush_advances_no_memory(self):
        h = history()
        plan = h.plan([row(1)], {1: 0.42})
        plan.written = {1}  # the INSERT ran inside the transaction …
        # … which rolled back: `committed` is never called.
        assert h.last_point == {}
        assert [p.outcome_id for p in h.plan([row(1)], {1: 0.42}).points] == [1]
        assert h.stats["history_points"] == 0

    def test_a_row_the_insert_refused_advances_no_memory(self):
        """The INSERT's SQL guard refused it (settled since this process looked)."""
        h = history()
        plan = h.plan([row(1), row(2)], {1: 0.42, 2: 0.58})
        plan.written = {2}
        h.committed(plan)
        assert set(h.last_point) == {2}
        assert h.stats["history_points"] == 1 and h.stats["history_refused"] == 1

    async def test_a_failed_insert_costs_the_point_not_the_price(self):
        """In a SAVEPOINT: the insert's failure is counted and swallowed."""
        events = []

        class Nested:
            async def __aenter__(self):
                events.append("savepoint")

            async def __aexit__(self, exc_type, *_exc):
                events.append("rollback to savepoint" if exc_type else "release")
                return False

        class Session:
            def begin_nested(self):
                return Nested()

            async def execute(self, stmt, params=None):
                assert is_history_insert(stmt)
                raise RuntimeError("insert failed")

        h = history()
        plan = h.plan([row(1)], {1: 0.42})
        await h.write(Session(), plan)
        assert events == ["savepoint", "rollback to savepoint"]
        assert plan.failed and plan.written == set()
        h.committed(plan)
        assert h.last_point == {} and h.stats["history_errors"] == 1


# ── settled means settled ───────────────────────────────────────────────────


class TestSettledMeansSettled:
    def test_graded_or_settled_legs_and_terminal_prices_get_no_point(self):
        settled = {7}
        h = history(refused_market=lambda mid: mid in settled)
        h.refuse_market(8)
        h.refuse_outcome(6)
        rows = [
            row(1, is_winner=True, resolution_source=None),
            row(2, is_winner=False, resolution_source="api_settlement"),
            row(3, is_winner=None, resolution_source="clob_authoritative"),
            row(4, market_id=7),
            row(5, market_id=8),
            row(6),
            row(10),
        ]
        quotes = {oid: 0.5 for oid in (1, 2, 3, 4, 5, 6)} | {10: 1.0}
        plan = h.plan(rows, quotes)
        assert plan.points == [] and plan.refused == 7

    def test_a_retracted_leg_and_a_born_false_leg_do_get_a_point(self):
        """`is_winner` is born False; `ungradeable_result` is a retraction (#1852)."""
        h = history()
        rows = [
            row(1, is_winner=False, resolution_source="ungradeable_result"),
            row(2, is_winner=False, resolution_source=None),
        ]
        assert [p.outcome_id for p in h.plan(rows, {1: 0.3, 2: 0.7}).points] == [1, 2]

    def test_the_insert_itself_refuses_settled_rows_and_resolved_markets(self):
        sql = str(history_insert_statement("kalshi").compile(dialect=postgresql.dialect()))
        assert "futures_outcomes.is_winner IS NOT true" in sql
        assert "futures_outcomes.resolution_source NOT IN" in sql
        assert "futures_markets.status IS DISTINCT FROM" in sql


# ── the statement ───────────────────────────────────────────────────────────


def test_one_insert_of_the_polling_writers_columns():
    stmt = history_insert_statement("polymarket")
    assert isinstance(stmt, Insert) and stmt.table.name == "futures_odds_snapshots"
    sql = str(stmt.compile(dialect=postgresql.dialect()))
    assert sql.startswith(
        "INSERT INTO futures_odds_snapshots (outcome_id, bookmaker, probability, "
        "american_odds, yes_bid, yes_ask, captured_at, reading_count) SELECT"
    )
    assert "RETURNING futures_odds_snapshots.outcome_id" in sql
    assert history_insert_statement("polymarket") is stmt  # prepared once
    points = history(enabled=True).plan(
        [row(1), row(2, market_id=2)], {1: (0.6, 0.59, 0.61), 2: 0.25},
    ).points
    assert history_insert_parameters(points) == {
        "history_outcome_ids": [1, 2],
        "history_probabilities": [0.6, 0.25],
        "history_american_odds": [-150, 300],
        "history_yes_bids": [0.59, None],
        "history_yes_asks": [0.61, None],
        "history_captured_at": [T0, T0],
    }


# ── through the real Kalshi consumer (fake sessions, runs everywhere) ───────


class _Recorder:
    """Every StreamHistoryPoints a consumer builds, and every statement run."""

    def __init__(self, monkeypatch):
        self.instances = []
        self.log = []  # (session id, "price" | "history" | "other", params)
        recorder = self

        class Recording(StreamHistoryPoints):
            def __init__(self, *a, **kw):
                super().__init__(*a, **kw)
                recorder.instances.append(self)

        monkeypatch.setattr(shp, "StreamHistoryPoints", Recording)

    def history_inserts(self):
        return [entry for entry in self.log if entry[1] == "history"]


async def _drive_kalshi(monkeypatch, recorder, *, rowcount=1, held=(), redis=None):
    """The 8753 harness: the REAL Kalshi consumer over one tick, 0.40/0.44."""
    import websockets

    import app.services.kalshi_ws as kalshi_svc
    import app.tasks.base as task_base
    import app.tasks.kalshi_ws as kalshi_task
    import app.tasks.live_blend_refresh as blend_mod
    import tests.test_kalshi_socket_prices_by_the_rest_rule_8753 as rig
    from app.utils import market_preview as mp
    from tests._kalshi_price_session import bind_sessions, returned
    from tests.test_a_settled_leg_takes_no_live_price_5411 import (
        _CapturingSession, _Frames, _NoopRefresher, _Result,
    )

    batches = [list(b) for b in rig.SLATE]

    class Session(_CapturingSession):
        async def execute(self, stmt, params=None):
            if is_history_insert(stmt):
                recorder.log.append((id(self), "history", params))
                return _Result([(oid,) for oid in params["history_outcome_ids"]])
            if isinstance(stmt, Update) and stmt.table.name == "futures_outcomes" \
                    and params and "kalshi_outcome_id" in params:
                recorder.log.append((id(self), "price", params))
                landed = (
                    [returned(params["kalshi_outcome_id"], market_id=rig.MARKET_ID,
                              quote_moved=False)]
                    if rowcount else []
                )
                return _Result(landed, rowcount=rowcount)
            return await super().execute(stmt, params)

    class SessionCtx:
        async def __aenter__(self):
            return Session(batches, [], rowcount)

        async def __aexit__(self, *_exc):
            return False

    class Refresher(_NoopRefresher):
        def _client(self):
            return redis

    def _connect(*_a, **_kw):
        class _Ctx:
            async def __aenter__(self_inner):
                return _Frames([rig._tick(yes_bid_dollars="0.40", yes_ask_dollars="0.44")])

            async def __aexit__(self_inner, *_exc):
                return False

        return _Ctx()

    monkeypatch.setenv("KALSHI_API_KEY_ID", "test-key")
    monkeypatch.setenv("KALSHI_RSA_PRIVATE_KEY", "test-secret")
    monkeypatch.setattr(kalshi_svc, "_load_rsa_key", lambda: object())
    monkeypatch.setattr(kalshi_svc, "_sign_ws_request", lambda _k, _i: {})
    monkeypatch.setattr(kalshi_task, "SUBSCRIPTION_REFRESH_SECONDS", 0.5)
    monkeypatch.setattr(kalshi_task, "PRICE_FLUSH_SECONDS", 0.02)
    monkeypatch.setattr(blend_mod, "LiveBlendRefresher", Refresher)
    monkeypatch.setattr(websockets, "connect", _connect)
    monkeypatch.setattr(mp, "_held_market_ids", lambda: frozenset(held))
    monkeypatch.setattr(
        task_base, "get_task_session", bind_sessions(lambda *a, **kw: SessionCtx())
    )
    await kalshi_task._run_kalshi_ws_consumer()
    return rig


class TestTheKalshiFlushWritesThePoint:
    async def test_one_insert_in_the_price_writes_own_transaction(self, monkeypatch):
        monkeypatch.setenv(shp.STREAM_HISTORY_ENV, "kalshi")
        recorder = _Recorder(monkeypatch)
        rig = await _drive_kalshi(monkeypatch, recorder)

        inserts = recorder.history_inserts()
        assert len(inserts) == 1, recorder.log
        session_id, _kind, params = inserts[0]
        assert params["history_outcome_ids"] == [rig.OUTCOME_ID]
        assert params["history_probabilities"] == [pytest.approx(0.42)]
        assert (params["history_yes_bids"], params["history_yes_asks"]) == ([0.40], [0.44])
        from tests._kalshi_price_session import STAMP
        assert params["history_captured_at"] == [STAMP], "the row's own returned clock"
        # The same session (transaction) as the price UPDATE it follows.
        kinds = [kind for sid, kind, _p in recorder.log if sid == session_id]
        assert kinds[0] == "price" and kinds.count("history") == 1
        assert kinds.index("history") > kinds.index("price")
        (instance,) = recorder.instances
        assert instance.stats["history_points"] == 1
        assert instance.last_point[rig.OUTCOME_ID][0] == pytest.approx(0.42)

    async def test_no_insert_with_the_switch_off(self, monkeypatch):
        monkeypatch.delenv(shp.STREAM_HISTORY_ENV, raising=False)
        recorder = _Recorder(monkeypatch)
        await _drive_kalshi(monkeypatch, recorder)
        assert [k for _s, k, _p in recorder.log].count("price") >= 1
        assert recorder.history_inserts() == []

    async def test_no_insert_for_a_venue_the_switch_does_not_name(self, monkeypatch):
        monkeypatch.setenv(shp.STREAM_HISTORY_ENV, "polymarket")
        recorder = _Recorder(monkeypatch)
        await _drive_kalshi(monkeypatch, recorder)
        assert recorder.history_inserts() == []

    async def test_a_refused_price_write_writes_no_point(self, monkeypatch):
        """The #5411 guard returned no row: nothing committed, nothing charted."""
        monkeypatch.setenv(shp.STREAM_HISTORY_ENV, "kalshi")
        recorder = _Recorder(monkeypatch)
        await _drive_kalshi(monkeypatch, recorder, rowcount=0)
        assert recorder.history_inserts() == []


# ── through the real Polymarket consumer (fake sessions, runs everywhere) ───


async def _drive_polymarket(monkeypatch, recorder, *, resolve=False):
    import tests.test_poly_ws_side1_leg_pairing_8403 as rig
    from tests.pm_bulk_test_support import price_writes

    class Session(rig._Session):
        async def execute(self, stmt, binds=None):
            if is_history_insert(stmt):
                recorder.log.append((id(self), "history", binds))
                return rig._Result([(oid,) for oid in binds["history_outcome_ids"]])
            pairs = price_writes(stmt, binds) if isinstance(stmt, Update) else []
            if pairs:
                recorder.log.append((id(self), "price", binds))
                self._writes.extend(pairs)
                from tests._kalshi_price_session import STAMP
                return rig._Result([
                    SimpleNamespace(
                        ord=i, id=oid, market_id=rig.MARKET_ID, last_updated=STAMP,
                        quote_moved=False, skipped=False, database_clock=None,
                        current_probability=price, is_winner=False,
                        resolution_source=None,
                    )
                    for i, (oid, price) in enumerate(pairs, start=1)
                ])
            return await super().execute(stmt, binds)

    monkeypatch.setattr(rig, "_Session", Session)
    frames = [rig._book(rig.LUKKO_TOKEN, "0.42", "0.50")]
    if resolve:
        frames.insert(0, json.dumps({
            "event_type": "market_resolved", "market": rig.CONDITION,
            "winning_outcome": "Lukko Rauma",
        }))
    writes, _stats = await rig._run(monkeypatch, rig.SPECIMEN_LEGS, frames)
    return rig, writes


class TestThePolymarketFlushWritesThePoint:
    async def test_one_insert_in_the_price_writes_own_transaction(self, monkeypatch):
        monkeypatch.setenv(shp.STREAM_HISTORY_ENV, "all")
        recorder = _Recorder(monkeypatch)
        rig, writes = await _drive_polymarket(monkeypatch, recorder)

        assert writes, "the harness drove no flush"
        inserts = recorder.history_inserts()
        assert len(inserts) == 1, recorder.log
        session_id, _kind, params = inserts[0]
        written = dict(writes)
        assert sorted(params["history_outcome_ids"]) == sorted(written)
        assert params["history_probabilities"] == [
            pytest.approx(round(written[oid], 6)) for oid in params["history_outcome_ids"]
        ]
        assert params["history_yes_bids"] == [None] * len(written)
        kinds = [kind for sid, kind, _p in recorder.log if sid == session_id]
        assert kinds.index("history") > kinds.index("price")
        (instance,) = recorder.instances
        assert instance.stats["history_points"] == len(written)

    async def test_no_insert_with_the_switch_off(self, monkeypatch):
        monkeypatch.setenv(shp.STREAM_HISTORY_ENV, "0")
        recorder = _Recorder(monkeypatch)
        _rig, writes = await _drive_polymarket(monkeypatch, recorder)
        assert writes and recorder.history_inserts() == []

    async def test_a_market_the_socket_saw_resolve_gets_no_point(self, monkeypatch):
        """`market_resolved` first: its terminal price may still reach the row
        through the flush, never the chart."""
        import app.services.polymarket_api as polymarket_api
        from tests.test_ws_market_change_hooks_9484 import _UndecidedPolymarketVenue

        monkeypatch.setattr(polymarket_api, "PolymarketAPIService", _UndecidedPolymarketVenue)
        monkeypatch.setenv(shp.STREAM_HISTORY_ENV, "polymarket")
        recorder = _Recorder(monkeypatch)
        _rig, writes = await _drive_polymarket(monkeypatch, recorder, resolve=True)
        assert writes, "the terminal-window price still reached the row"
        assert recorder.history_inserts() == []
        (instance,) = recorder.instances
        assert instance.stats["history_points"] == 0


# ── the previews never write a snapshot ─────────────────────────────────────


def _forbid_history_writes(monkeypatch):
    def forbidden(*_a, **_kw):
        raise AssertionError("a preview path reached the history writer")

    monkeypatch.setattr(StreamHistoryPoints, "write", forbidden)
    monkeypatch.setattr(StreamHistoryPoints, "plan", forbidden)
    monkeypatch.setattr(shp, "history_insert_statement", forbidden)


async def test_the_market_preview_publishes_with_the_history_writer_forbidden(monkeypatch):
    """The market preview's whole publish path, with every history entry point
    and every database door raising (the #10090 no-database rig)."""
    import tests.test_market_preview_10090 as preview_rig

    monkeypatch.setenv(shp.STREAM_HISTORY_ENV, "all")
    _forbid_history_writes(monkeypatch)
    await preview_rig.test_the_publish_path_touches_no_database(monkeypatch)


async def test_the_kalshi_preview_goes_out_before_and_apart_from_the_point(monkeypatch):
    """Through the real consumer, a held market: the preview frame is published
    before any history INSERT, and a price write the guard refuses (nothing
    committed) still previews but charts nothing."""
    from tests.test_market_preview_10090 import FakeRedis

    monkeypatch.setenv(shp.STREAM_HISTORY_ENV, "kalshi")
    for rowcount, expected in ((1, 1), (0, 0)):
        recorder = _Recorder(monkeypatch)
        at_publish = []
        redis = FakeRedis(on_publish=lambda *_: at_publish.append(
            len(recorder.history_inserts())))
        import tests.test_kalshi_socket_prices_by_the_rest_rule_8753 as rig

        await _drive_kalshi(
            monkeypatch, recorder, rowcount=rowcount, held=(rig.MARKET_ID,), redis=redis,
        )
        frames = [f for f in redis.frames() if f.get("type") == "market_preview"]
        assert len(frames) == 1, redis.frames()
        assert at_publish[0] == 0, "the preview went out before any history point"
        assert len(recorder.history_inserts()) == expected


def test_only_the_committed_flush_paths_reach_the_history_writer():
    """Structural: the module is imported only by the two consumers, and the
    preview modules name neither it nor the snapshot table."""
    importers = set()
    for path in (BACKEND / "app").rglob("*.py"):
        if path.name == "stream_history_points.py":
            continue
        text = path.read_text()
        if "stream_history_points" in text:
            importers.add(path.relative_to(BACKEND).as_posix())
    assert importers == {"app/tasks/kalshi_ws.py", "app/tasks/polymarket_ws.py"}
    for preview in ("app/utils/market_preview.py", "app/tasks/live_blend_refresh.py"):
        text = (BACKEND / preview).read_text()
        for name in ("stream_history", "FuturesOddsSnapshot", "futures_odds_snapshots"):
            assert name not in text, f"{preview} names {name}"


def _calls_in(path, function):
    tree = ast.parse((BACKEND / path).read_text())
    for node in ast.walk(tree):
        if isinstance(node, ast.AsyncFunctionDef) and node.name == function:
            return ast.unparse(node)
    raise AssertionError(f"{function} not found in {path}")


def test_the_write_sits_inside_each_flush_and_memory_after_its_commit():
    for path, function in (
        ("app/tasks/kalshi_ws.py", "flush_prices"),
        ("app/tasks/polymarket_ws.py", "write_chunk"),
    ):
        source = _calls_in(path, function)
        assert ".write(session, history_plan)" in source, path
        assert ".committed(history_plan)" in source, path
        assert source.index(".write(session, history_plan)") < source.index(
            ".committed(history_plan)"
        )


# ── the minute lines ────────────────────────────────────────────────────────


def test_the_kalshi_minute_line_carries_the_counters():
    tree = ast.parse((BACKEND / "app/tasks/kalshi_ws.py").read_text())
    (call,) = [
        node for node in ast.walk(tree)
        if isinstance(node, ast.Call) and node.args
        and isinstance(node.args[0], ast.Constant) and isinstance(node.args[0].value, str)
        and node.args[0].value.startswith("Kalshi WS: %d updates")
    ]
    fmt = call.args[0].value
    for name in shp.HISTORY_COUNTERS:
        assert f"{name}=%d" in fmt
        assert f"stream_history.stats['{name}']" in ast.unparse(call)
    assert fmt.endswith("skipped_locked=%d | %s")
    assert fmt.count("%d") + fmt.count("%s") == len(call.args) - 1


def test_the_polymarket_minute_line_carries_the_counters(caplog):
    import logging

    from app.tasks import polymarket_ws as pm

    stats = {"price_updates": 3, "trade_updates": 0, "resolutions": 0, "errors": 0,
             "price_rows_skipped_locked": 5, "repeats_skipped": 4321,
             "history_points": 11, "history_keepalive": 7, "history_keepalive_errors": 1,
             "history_capped": 2, "history_skipped": 40,
             "history_refused": 1, "history_errors": 0}
    blend = {"stamped": 0, "no_reading": 0, "throttled": 0, "errors": 0}
    with caplog.at_level(logging.INFO, logger=pm.logger.name):
        pm._log_stats_line(stats, {}, blend)
    (line,) = [r.getMessage() for r in caplog.records if "Polymarket WS: " in r.getMessage()]
    assert ("history_points=11 history_keepalive=7 history_keepalive_errors=1 "
            "history_capped=2 history_skipped=40 history_refused=1 "
            "history_errors=0 skipped_locked=5 repeats_skipped=4321") in line
    assert line.endswith("repeats_skipped=4321")


# ── the real PostgreSQL rig (#9484's), where the database is available ──────


def _snapshots(engine):
    from sqlalchemy import text

    with engine.connect() as conn:
        return [
            tuple(r) for r in conn.execute(text(
                "SELECT outcome_id, bookmaker, probability, yes_bid, yes_ask, "
                "captured_at, reading_count FROM futures_odds_snapshots ORDER BY id"
            ))
        ]


def _pg_database(tmp_path, monkeypatch, **kwargs):
    import tests.test_ws_market_change_hooks_9484 as hooks
    from app.models.models import FuturesOddsSnapshot

    engine = hooks._database(tmp_path, **kwargs)
    FuturesOddsSnapshot.__table__.create(engine)
    route = hooks._routes_to_the_database
    monkeypatch.setattr(
        hooks, "_routes_to_the_database", lambda stmt: is_history_insert(stmt) or route(stmt),
    )
    return hooks, engine


class TestOnRealPostgres:
    async def test_the_kalshi_point_is_the_committed_row(self, monkeypatch, tmp_path):
        monkeypatch.setenv(shp.STREAM_HISTORY_ENV, "kalshi")
        hooks, engine = _pg_database(tmp_path, monkeypatch)
        _published, stats = await hooks._drive_kalshi(monkeypatch, engine, [hooks.TICK])
        assert stats["errors"] == 0
        stored_at = hooks._as_utc(
            hooks._stored(engine, "futures_outcomes", "last_updated", hooks.OUTCOME_ID))
        [(oid, bookmaker, prob, bid, ask, captured_at, readings)] = _snapshots(engine)
        assert (oid, bookmaker, readings) == (hooks.OUTCOME_ID, "kalshi", 1)
        assert (float(prob), float(bid), float(ask)) == (0.42, 0.40, 0.44)
        assert hooks._as_utc(captured_at) == stored_at

    async def test_the_switch_off_writes_no_row(self, monkeypatch, tmp_path):
        monkeypatch.delenv(shp.STREAM_HISTORY_ENV, raising=False)
        hooks, engine = _pg_database(tmp_path, monkeypatch)
        await hooks._drive_kalshi(monkeypatch, engine, [hooks.TICK])
        assert hooks._stored(engine, "futures_outcomes", "current_probability",
                             hooks.OUTCOME_ID) == pytest.approx(0.42)
        assert _snapshots(engine) == []

    async def test_a_settled_leg_gets_no_point(self, monkeypatch, tmp_path):
        monkeypatch.setenv(shp.STREAM_HISTORY_ENV, "kalshi")
        hooks, engine = _pg_database(tmp_path, monkeypatch, resolution_source="api_settlement")
        await hooks._drive_kalshi(monkeypatch, engine, [hooks.TICK])
        assert _snapshots(engine) == []

    async def test_a_resolved_market_gets_no_point_though_its_price_lands(
        self, monkeypatch, tmp_path,
    ):
        """The SQL guard: resolved by another writer, unknown to this process."""
        from sqlalchemy import text

        monkeypatch.setenv(shp.STREAM_HISTORY_ENV, "kalshi")
        hooks, engine = _pg_database(tmp_path, monkeypatch)
        with engine.begin() as conn:
            conn.execute(text("UPDATE futures_markets SET status = 'resolved'"))
        await hooks._drive_kalshi(monkeypatch, engine, [hooks.TICK])
        assert hooks._stored(engine, "futures_outcomes", "current_probability",
                             hooks.OUTCOME_ID) == pytest.approx(0.42)
        assert _snapshots(engine) == []

    async def test_a_failed_commit_keeps_the_leg_due(self, monkeypatch, tmp_path):
        """The first transaction (price + point) rolls back; the retry writes
        exactly one point — so the rolled-back attempt advanced no memory (an
        advanced memory would read the same price as already charted)."""
        monkeypatch.setenv(shp.STREAM_HISTORY_ENV, "kalshi")
        hooks, engine = _pg_database(tmp_path, monkeypatch)
        _published, stats = await hooks._drive_kalshi(
            monkeypatch, engine, [hooks.TICK], fail_commits=1,
        )
        assert stats["errors"] >= 1 and stats["requeued"] >= 1
        assert [r[0] for r in _snapshots(engine)] == [hooks.OUTCOME_ID]

    async def test_the_polymarket_point_is_the_committed_row(self, monkeypatch, tmp_path):
        monkeypatch.setenv(shp.STREAM_HISTORY_ENV, "polymarket")
        hooks, engine = _pg_database(tmp_path, monkeypatch)
        _published, stats = await hooks._drive_kalshi(
            monkeypatch, engine, [hooks.POLY_TICK], venue="polymarket",
        )
        assert stats["errors"] == 0
        stored_at = hooks._as_utc(
            hooks._stored(engine, "futures_outcomes", "last_updated", hooks.OUTCOME_ID))
        # Only the row that exists: the NO leg (82) has no row, so no point.
        [(oid, bookmaker, prob, bid, ask, captured_at, _n)] = _snapshots(engine)
        assert (oid, bookmaker, float(prob), bid, ask) == (
            hooks.OUTCOME_ID, "polymarket", 0.42, None, None)
        assert hooks._as_utc(captured_at) == stored_at

    async def test_a_resolved_polymarket_market_gets_no_point(self, monkeypatch, tmp_path):
        from sqlalchemy import text

        monkeypatch.setenv(shp.STREAM_HISTORY_ENV, "polymarket")
        hooks, engine = _pg_database(tmp_path, monkeypatch)
        with engine.begin() as conn:
            conn.execute(text("UPDATE futures_markets SET status = 'resolved'"))
        await hooks._drive_kalshi(monkeypatch, engine, [hooks.POLY_TICK], venue="polymarket")
        assert _snapshots(engine) == []


class TestTheSavepointOnAsyncpg:
    """Production's driver: the statement binds on asyncpg, and its SAVEPOINT
    lets a failed insert cost the point while the price write commits."""

    async def test_the_point_lands_and_a_failed_insert_keeps_the_price(self, tmp_path):
        import os

        from sqlalchemy import text
        from sqlalchemy.engine import make_url
        from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine

        import tests.pm_bulk_test_support as support
        import tests.test_ws_market_change_hooks_9484 as hooks
        from app.models.models import FuturesOddsSnapshot
        from app.utils.kalshi_price_statement import (
            KALSHI_PRICE_STATEMENTS, kalshi_price_parameters,
        )

        engine = hooks._database(tmp_path)  # skips without SEARCH_TEST_DATABASE_URL
        FuturesOddsSnapshot.__table__.create(engine)
        schema = support._ENGINES[-1][2]
        url = make_url(os.environ["SEARCH_TEST_DATABASE_URL"]).set(drivername="postgresql+asyncpg")
        aengine = create_async_engine(
            url, connect_args={"server_settings": {"search_path": schema}},
        )
        h = history()
        try:
            async with AsyncSession(aengine) as session:
                result = await session.execute(
                    KALSHI_PRICE_STATEMENTS[True],
                    kalshi_price_parameters(hooks.OUTCOME_ID, 0.42, 0.40, 0.44),
                )
                plan = h.plan(result.all(), {hooks.OUTCOME_ID: (0.42, 0.40, 0.44)})
                assert len(plan.points) == 1
                await h.write(session, plan)
                await session.commit()
            h.committed(plan)
            assert plan.written == {hooks.OUTCOME_ID} and not plan.failed

            # An insert the database rejects (NUMERIC(7, 6) overflow), in the
            # same transaction as a price write: the point is lost, the price is not.
            bad = shp.HistoryPlan(points=[shp.HistoryPoint(
                hooks.OUTCOME_ID, hooks.MARKET_ID, 99.0, None, None, plan.points[0].captured_at,
            )])
            async with AsyncSession(aengine) as session:
                await session.execute(
                    KALSHI_PRICE_STATEMENTS[False],
                    kalshi_price_parameters(hooks.OUTCOME_ID, 0.47, None, None),
                )
                await h.write(session, bad)
                await session.commit()
            assert bad.failed and bad.written == set()
        finally:
            await aengine.dispose()

        with engine.connect() as conn:
            price = conn.execute(text(
                "SELECT current_probability FROM futures_outcomes WHERE id = :id"
            ), {"id": hooks.OUTCOME_ID}).scalar_one()
        assert float(price) == pytest.approx(0.47)
        [(oid, bookmaker, prob, bid, ask, captured_at, readings)] = _snapshots(engine)
        assert (oid, bookmaker, float(prob), float(bid), float(ask), readings) == (
            hooks.OUTCOME_ID, "kalshi", 0.42, 0.40, 0.44, 1)
        assert captured_at == plan.points[0].captured_at
