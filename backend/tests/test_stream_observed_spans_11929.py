"""#11929 Decide 27-B: observed spans, the WRITER (a span, not a row).

What is pinned here:

* the switch: off by default, same grammar as ``STREAM_HISTORY_POINTS``, and
  only effective for a venue whose move points are on;
* the tracker: a newly alive leg opens, an alive leg extends in memory only, a
  leg that left closes at the last tick it was SEEN alive (never at "now");
  memory moves only after COMMIT; a failed tick retries its opens and holds its
  closes for the next tick; a tick never raises (except cancellation);
* run end closes every open span at its last tick alive; run start recovers a
  dead run's open spans at the venue heartbeat;
* Alex's condition, at both sockets: a connection that is connected and
  subscribed but has sent no frame within ``SPAN_LIFE_S`` contributes no live
  legs (Polymarket per shard, PONGs not counted; Kalshi per connection);
* the consumer wiring (source-shaped), and the migration;
* on real PostgreSQL (``SEARCH_TEST_DATABASE_URL``, asyncpg like production):
  open → extend → close, the close-once rule, the heartbeat upsert and recover.
"""

from __future__ import annotations

import asyncio
import importlib.util
import os
import re
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest

from app.utils.stream_observed_spans import (
    END_LEFT,
    END_RECOVERED,
    END_RUN,
    SPAN_LIFE_S,
    STREAM_OBSERVED_SPANS_ENV,
    ObservedSpans,
    close_statement,
    heartbeat_statement,
    open_statement,
    recover_statement,
    stream_spans_enabled,
)
from tests.pm_bulk_test_support import cleanup_pg_engines  # noqa: F401 — autouse

BACKEND = Path(__file__).resolve().parents[1]
T0 = datetime(2026, 11, 5, 18, 0, 0, tzinfo=timezone.utc)
ON = {STREAM_OBSERVED_SPANS_ENV: "1", "STREAM_HISTORY_POINTS": "kalshi,polymarket"}


def spans(venue="kalshi", env=None):
    return ObservedSpans(venue, environ=ON if env is None else env)


class _Result:
    def __init__(self, rows=(), rowcount=0):
        self._rows = list(rows)
        self.rowcount = rowcount

    def all(self):
        return list(self._rows)


class FakeDB:
    """A session factory recording the four span statements.

    Opens return ``(span_id, outcome_id)`` with ids counting up from 100.
    ``fail``: "open" | "close" | "heartbeat" | "commit" | "recover".
    """

    def __init__(self, fail=None):
        self.fail = fail
        self.calls = []  # (kind, params)
        self.commits = 0
        self.sessions = 0
        self.next_id = 100

    def __call__(self):
        db = self

        class Session:
            async def execute(self, stmt, params=None):
                kind = {
                    id(open_statement()): "open",
                    id(close_statement()): "close",
                    id(heartbeat_statement()): "heartbeat",
                    id(recover_statement()): "recover",
                }[id(stmt)]
                db.calls.append((kind, params))
                if db.fail == kind:
                    raise RuntimeError(f"{kind} failed")
                if kind == "open":
                    rows = []
                    for oid in params["ids"]:
                        rows.append((db.next_id, oid))
                        db.next_id += 1
                    return _Result(rows)
                if kind == "recover":
                    return _Result(rowcount=3)
                return _Result()

            async def commit(self):
                if db.fail == "commit":
                    raise RuntimeError("commit failed")
                db.commits += 1

            async def __aenter__(self):
                db.sessions += 1
                return self

            async def __aexit__(self, *exc):
                return False

        return Session()

    def kinds(self):
        return [kind for kind, _params in self.calls]

    def last(self, kind):
        return [p for k, p in self.calls if k == kind][-1]


def clock(*times):
    it = iter(times)
    return lambda: next(it)


# ── the switch ──────────────────────────────────────────────────────────────


class TestTheSwitch:
    def test_off_by_default(self):
        assert not stream_spans_enabled("kalshi", {"STREAM_HISTORY_POINTS": "1"})

    @pytest.mark.parametrize("raw, venues", [
        ("1", {"kalshi", "polymarket"}), ("all", {"kalshi", "polymarket"}),
        ("kalshi", {"kalshi"}), ("polymarket", {"polymarket"}), ("0", set()), ("off", set()),
    ])
    def test_same_grammar_as_history_points(self, raw, venues):
        env = {STREAM_OBSERVED_SPANS_ENV: raw, "STREAM_HISTORY_POINTS": "1"}
        assert {v for v in ("kalshi", "polymarket") if stream_spans_enabled(v, env)} == venues

    def test_without_move_points_there_is_no_unchanged_to_derive(self):
        env = {STREAM_OBSERVED_SPANS_ENV: "1", "STREAM_HISTORY_POINTS": "kalshi"}
        assert stream_spans_enabled("kalshi", env)
        assert not stream_spans_enabled("polymarket", env)

    async def test_disabled_touches_no_database(self):
        db = FakeDB()
        s = spans(env={})
        assert await s.tick(db, [1, 2]) is None
        assert await s.close_all(db) == 0
        assert await s.recover(db) == 0
        assert db.sessions == 0


# ── the tracker ─────────────────────────────────────────────────────────────


class TestOpenExtendClose:
    async def test_a_newly_alive_leg_opens_once_at_the_tick(self):
        db, s = FakeDB(), spans()
        await s.tick(db, [7, 5, 7], now=clock(T0))
        assert db.kinds() == ["open", "heartbeat"] and db.commits == 1
        assert db.last("open") == {"venue": "kalshi", "at": T0, "ids": [5, 7]}
        assert db.last("heartbeat") == {"venue": "kalshi", "at": T0}
        assert s.open == {5: [100, T0, T0], 7: [101, T0, T0]}
        assert s.stats["spans_opened"] == 2 and s.stats["spans_open"] == 2

    async def test_an_alive_leg_extends_in_memory_and_writes_only_the_heartbeat(self):
        db, s = FakeDB(), spans()
        t1 = T0 + timedelta(minutes=1)
        await s.tick(db, [5], now=clock(T0))
        await s.tick(db, [5], now=clock(t1))
        assert db.kinds() == ["open", "heartbeat", "heartbeat"]
        assert s.open[5] == [100, T0, t1]

    async def test_a_leg_that_left_closes_at_its_last_tick_alive_never_now(self):
        db, s = FakeDB(), spans()
        t1, t2, t3 = (T0 + timedelta(minutes=m) for m in (1, 2, 3))
        for at, alive in ((T0, [5, 6]), (t1, [5, 6]), (t2, [6]), (t3, [6])):
            await s.tick(db, alive, now=clock(at))
        closes = [p for k, p in db.calls if k == "close"]
        assert closes == [{"reason": END_LEFT, "span_ids": [100], "ended": [t1]}]
        assert 5 not in s.open and s.open[6] == [101, T0, t3]
        assert s.stats["spans_closed"] == 1

    async def test_a_leg_back_after_leaving_opens_a_new_span(self):
        db, s = FakeDB(), spans()
        times = [T0 + timedelta(minutes=m) for m in range(3)]
        for at, alive in zip(times, ([5], [], [5])):
            await s.tick(db, alive, now=clock(at))
        assert s.open[5] == [101, times[2], times[2]]
        assert [p["ids"] for k, p in db.calls if k == "open"] == [[5], [5]]

    async def test_one_tick_is_one_transaction_opens_closes_then_heartbeat(self):
        db, s = FakeDB(), spans()
        t1 = T0 + timedelta(minutes=1)
        await s.tick(db, [5], now=clock(T0))
        await s.tick(db, [6], now=clock(t1))
        assert db.kinds()[2:] == ["open", "close", "heartbeat"]
        assert db.sessions == 2 and db.commits == 2


class TestFailuresNeverCostAPrice:
    @pytest.mark.parametrize("fail", ["open", "heartbeat", "commit"])
    async def test_a_failed_tick_is_counted_and_its_opens_retry(self, fail, caplog):
        db, s = FakeDB(fail=fail), spans()
        plan = await s.tick(db, [5], now=clock(T0))  # does not raise
        assert plan is not None and s.open == {} and s.stats["spans_errors"] == 1
        assert "observed spans: tick" in caplog.text
        db.fail = None
        await s.tick(db, [5], now=clock(T0 + timedelta(minutes=1)))
        assert 5 in s.open

    async def test_a_failed_close_is_held_and_retried_by_the_next_tick(self):
        db, s = FakeDB(), spans()
        t1, t2 = T0 + timedelta(minutes=1), T0 + timedelta(minutes=2)
        await s.tick(db, [5], now=clock(T0))
        db.fail = "close"
        await s.tick(db, [], now=clock(t1))
        assert 5 not in s.open and s.stats["spans_errors"] == 1
        db.fail = None
        await s.tick(db, [], now=clock(t2))
        # Retried with its ORIGINAL end: the last tick it was seen alive (T0).
        assert db.last("close") == {"reason": END_LEFT, "span_ids": [100], "ended": [T0]}
        assert s.stats["spans_closed"] == 1

    async def test_a_held_close_is_not_doubled_by_a_second_failure(self):
        db, s = FakeDB(), spans()
        await s.tick(db, [5], now=clock(T0))
        db.fail = "close"
        await s.tick(db, [], now=clock(T0 + timedelta(minutes=1)))
        await s.tick(db, [], now=clock(T0 + timedelta(minutes=2)))
        db.fail = None
        await s.tick(db, [], now=clock(T0 + timedelta(minutes=3)))
        assert db.last("close")["span_ids"] == [100]

    async def test_a_cancel_always_reaches_the_caller(self):
        class Hang(FakeDB):
            def __call__(self):
                session = super().__call__()

                async def execute(stmt, params=None):
                    await asyncio.sleep(3600)

                session.execute = execute
                return session

        s = spans()
        task = asyncio.create_task(s.tick(Hang(), [5], now=clock(T0)))
        await asyncio.sleep(0.01)
        task.cancel()
        with pytest.raises(asyncio.CancelledError):
            await task

    async def test_a_hung_tick_ends_at_its_bound_and_counts(self):
        class Hang(FakeDB):
            def __call__(self):
                session = super().__call__()

                async def execute(stmt, params=None):
                    await asyncio.sleep(3600)

                session.execute = execute
                return session

        s = spans()
        await s.tick(Hang(), [5], now=clock(T0), timeout_s=0.01)
        assert s.stats["spans_errors"] == 1 and s.open == {}


class TestRunEndAndRecovery:
    async def test_run_end_closes_every_open_span_at_its_last_tick_alive(self):
        db, s = FakeDB(), spans()
        t1 = T0 + timedelta(minutes=1)
        await s.tick(db, [5, 6], now=clock(T0))
        await s.tick(db, [6], now=clock(t1))  # 5 closes here
        assert await s.close_all(db) == 1
        assert db.last("close") == {"reason": END_RUN, "span_ids": [101], "ended": [t1]}
        assert s.open == {}

    async def test_run_end_also_flushes_a_close_held_by_a_failed_tick(self):
        db, s = FakeDB(), spans()
        await s.tick(db, [5, 6], now=clock(T0))
        db.fail = "close"
        await s.tick(db, [6], now=clock(T0 + timedelta(minutes=1)))
        db.fail = None
        assert await s.close_all(db) == 2
        assert sorted(db.last("close")["span_ids"]) == [100, 101]

    async def test_a_failed_run_end_is_counted_and_left_for_recover(self, caplog):
        db, s = FakeDB(), spans()
        await s.tick(db, [5], now=clock(T0))
        db.fail = "close"
        assert await s.close_all(db) == 0
        assert s.stats["spans_errors"] == 1 and "next run closes them" in caplog.text

    async def test_recover_closes_this_venues_open_spans_at_the_heartbeat(self):
        db, s = FakeDB(), spans("polymarket")
        assert await s.recover(db) == 3
        assert db.calls == [("recover", {"venue": "polymarket", "reason": END_RECOVERED})]
        assert db.commits == 1

    async def test_a_failed_recover_never_blocks_the_consumer(self):
        db, s = FakeDB(fail="recover"), spans()
        assert await s.recover(db) == 0 and s.stats["spans_errors"] == 1

    def test_the_minute_line_names_every_counter(self):
        assert spans().line() == "spans_open=0 spans_opened=0 spans_closed=0 spans_errors=0"


# ── Alex's condition: silence closes ────────────────────────────────────────


class TestASilentConnectionIsNotLive:
    def _pm(self):
        from app.services.polymarket_ws import PolymarketWebSocket

        ws = PolymarketWebSocket.__new__(PolymarketWebSocket)
        ws._shards_connected = {0, 1, 2}
        ws._shard_connected_at = {0: 1.0, 1: 1.0, 2: 1.0}
        ws._shard_ids = {0: ["a", "b"], 1: ["c"], 2: ["d"], 3: ["e"]}
        ws._shard_last_message = {0: 1000.0, 1: 1000.0 - SPAN_LIFE_S - 1}  # 2 never spoke
        return ws

    def test_polymarket_only_connected_shards_with_a_recent_frame_are_live(self):
        ws = self._pm()
        assert ws.live_asset_ids(SPAN_LIFE_S, now=1000.0) == {"a", "b"}
        # The keep-alive's population is unchanged: every connected shard.
        assert ws.connected_asset_ids() == {"a", "b", "c", "d"}

    def test_polymarket_a_shard_marked_down_forgets_its_last_frame(self):
        ws = self._pm()
        ws._mark_shard_down(0)
        assert 0 not in ws._shard_last_message
        assert ws.live_asset_ids(SPAN_LIFE_S, now=1000.0) == set()

    def test_polymarket_stamps_data_frames_and_never_pongs(self):
        src = (BACKEND / "app" / "services" / "polymarket_ws.py").read_text()
        loop = src[src.index('if raw in ("PONG", b"PONG"):'):]
        loop = loop[: loop.index("try:", loop.index("self._message_count += 1"))]
        assert loop.index("continue") < loop.index("self._shard_last_message[shard] = time.monotonic()")

    def test_kalshi_stamps_every_frame_on_its_connection(self):
        from app.services.kalshi_ws import KalshiWebSocket

        src = (BACKEND / "app" / "services" / "kalshi_ws.py").read_text()
        assert re.search(
            r"self\._message_count \+= 1\n\s+self\.last_message_at = time\.monotonic\(\)", src,
        )
        assert KalshiWebSocket().last_message_at is None


# ── consumer wiring (source-shaped) ─────────────────────────────────────────


def _src(name):
    return (BACKEND / "app" / "tasks" / name).read_text()


class TestConsumerWiring:
    @pytest.mark.parametrize("name, venue", [("kalshi_ws.py", "kalshi"), ("polymarket_ws.py", "polymarket")])
    def test_recover_runs_before_any_tick_and_only_when_on(self, name, venue):
        src = _src(name)
        made = src.index(f'observed_spans = ObservedSpans("{venue}")')
        assert src.index("await observed_spans.recover(get_task_session)", made) > made
        assert "if observed_spans.enabled:\n        await observed_spans.recover" in src

    @pytest.mark.parametrize("name", ["kalshi_ws.py", "polymarket_ws.py"])
    def test_the_tick_follows_the_keepalive_inside_the_stats_loop_guarded(self, name):
        src = _src(name)
        keepalive = src.index(".keepalive_pass(\n") if name == "kalshi_ws.py" else src.index(".keepalive_pass(get_task_session")
        tick = src.index("await observed_spans.tick(get_task_session", keepalive)
        assert tick - keepalive < 1500
        block = src[src.rindex("if observed_spans.enabled:", 0, tick):tick + 400]
        assert "except Exception:" in block and 'stats["spans_errors"] += 1' in block

    @pytest.mark.parametrize("name, reaped", [
        ("kalshi_ws.py", 'reap_stopped_loops(\n                "kalshi"'),
        ("polymarket_ws.py", 'reap_stopped_loops(\n                "polymarket"'),
    ])
    def test_run_end_closes_after_the_stats_loop_is_reaped(self, name, reaped):
        src = _src(name)
        assert src.index("await observed_spans.close_all(", src.index(reaped)) > src.index(reaped)

    def test_kalshi_live_legs_need_a_subscribed_connection_with_a_recent_frame(self):
        src = _src("kalshi_ws.py")
        body = src[src.index("async def span_legs():"):src.index("async def keepalive_legs():")]
        assert 'getattr(sock, "is_subscribed", False)' in body
        assert 'last = getattr(sock, "last_message_at", None)' in body
        assert "if last is None or now - last > SPAN_LIFE_S:" in body

    def test_polymarket_live_legs_come_only_from_live_shards(self):
        src = _src("polymarket_ws.py")
        body = src[src.index("def span_legs():"):src.index("def keepalive_legs():")]
        assert 'getattr(ws, "live_asset_ids", None)' in body
        assert 'getattr(sock, "live_asset_ids", None)' in body
        assert "connected_asset_ids" not in body and "is_connected" not in body


# ── the migration ───────────────────────────────────────────────────────────


def _migration():
    path = BACKEND / "alembic" / "versions" / "stream_observed_spans_11929.py"
    spec = importlib.util.spec_from_file_location("stream_observed_spans_11929", path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod, path.read_text()


class TestMigration:
    def test_revision_fits_gotcha_1_and_chains_on_pr_a(self):
        mod, _src = _migration()
        assert mod.revision == "stream_observed_spans_11929" and len(mod.revision) <= 32
        assert mod.down_revision == "venue_history_points_11929"

    def test_single_head_with_this_revision_on_its_chain(self):
        from alembic.config import Config
        from alembic.script import ScriptDirectory

        script = ScriptDirectory.from_config(Config(str(BACKEND / "alembic.ini")))
        heads = list(script.get_heads())
        assert len(heads) == 1, heads
        chain = [rev.revision for rev in script.iterate_revisions(heads[0], "base")]
        assert "stream_observed_spans_11929" in chain

    def test_no_foreign_key_and_no_concurrent_index(self):
        _mod, src = _migration()
        code = src[src.index("def upgrade"):]
        assert "ForeignKey" not in code and "CONCURRENTLY" not in code.upper()

    def test_the_models_match_the_migration(self):
        from app.models.models import StreamObservedSpan, StreamSpanHeartbeat

        spans_t = StreamObservedSpan.__table__
        assert [c.name for c in spans_t.columns] == [
            "id", "venue", "outcome_id", "started_at", "ended_at", "end_reason",
        ]
        assert {i.name for i in spans_t.indexes} == {"ix_sos_outcome_started", "ix_sos_open_by_venue"}
        assert not spans_t.foreign_keys
        assert [c.name for c in StreamSpanHeartbeat.__table__.columns] == ["venue", "beat_at"]


# ── real PostgreSQL ─────────────────────────────────────────────────────────


async def _pg():
    from sqlalchemy.engine import make_url
    from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine

    import tests.pm_bulk_test_support as support
    from app.models.models import StreamObservedSpan, StreamSpanHeartbeat

    engine = support.pg_engine()  # skips without SEARCH_TEST_DATABASE_URL
    StreamObservedSpan.__table__.create(engine)
    StreamSpanHeartbeat.__table__.create(engine)
    schema = support._ENGINES[-1][2]
    url = make_url(os.environ["SEARCH_TEST_DATABASE_URL"]).set(drivername="postgresql+asyncpg")
    aengine = create_async_engine(url, connect_args={"server_settings": {"search_path": schema}})
    return engine, aengine, (lambda: AsyncSession(aengine))


def _rows(engine):
    from sqlalchemy import text

    with engine.connect() as conn:
        spans_rows = conn.execute(text(
            "SELECT id, venue, outcome_id, started_at, ended_at, end_reason "
            "FROM stream_observed_spans ORDER BY id"
        )).all()
        beats = dict(conn.execute(text("SELECT venue, beat_at FROM stream_span_heartbeats")).all())
    return spans_rows, beats


class TestOnRealPostgres:
    async def test_open_extend_close_and_the_heartbeat(self):
        engine, aengine, factory = await _pg()
        try:
            s = spans()
            t1, t2 = T0 + timedelta(minutes=1), T0 + timedelta(minutes=2)
            await s.tick(factory, [81, 82], now=clock(T0))
            await s.tick(factory, [81, 82], now=clock(t1))
            await s.tick(factory, [82], now=clock(t2))
            assert s.stats["spans_errors"] == 0
            rows, beats = _rows(engine)
            assert [(r.outcome_id, r.started_at, r.ended_at, r.end_reason) for r in rows] == [
                (81, T0, t1, END_LEFT), (82, T0, None, None),
            ]
            assert beats == {"kalshi": t2}
            assert await s.close_all(factory) == 1
            rows, _ = _rows(engine)
            assert (rows[1].ended_at, rows[1].end_reason) == (t2, END_RUN)
        finally:
            await aengine.dispose()

    async def test_a_span_closes_once(self):
        from sqlalchemy import text

        engine, aengine, factory = await _pg()
        try:
            s = spans()
            await s.tick(factory, [81], now=clock(T0))
            async with factory() as session:
                for ended in (T0 + timedelta(minutes=5), T0 + timedelta(minutes=9)):
                    await session.execute(close_statement(), {
                        "reason": END_LEFT, "span_ids": [s.open[81][0]], "ended": [ended],
                    })
                await session.commit()
            rows, _ = _rows(engine)
            assert rows[0].ended_at == T0 + timedelta(minutes=5)
            with engine.connect() as conn:  # the CHECK refuses an end before its start
                with pytest.raises(Exception, match="ck_sos_order"):
                    conn.execute(text(
                        "INSERT INTO stream_observed_spans (venue, outcome_id, started_at, ended_at) "
                        "VALUES ('kalshi', 1, now(), now() - interval '1 minute')"
                    ))
        finally:
            await aengine.dispose()

    async def test_recover_closes_a_dead_runs_spans_at_its_heartbeat(self):
        engine, aengine, factory = await _pg()
        try:
            dead = spans()
            t3 = T0 + timedelta(minutes=3)
            await dead.tick(factory, [81, 82], now=clock(T0))
            await dead.tick(factory, [81, 82], now=clock(t3))
            await spans("polymarket").tick(factory, [90], now=clock(T0))
            # The run dies without close_all. The next kalshi run recovers.
            assert await spans().recover(factory) == 2
            rows, _ = _rows(engine)
            by_oid = {r.outcome_id: r for r in rows}
            assert {(by_oid[o].ended_at, by_oid[o].end_reason) for o in (81, 82)} == {(t3, END_RECOVERED)}
            assert by_oid[90].ended_at is None  # another venue's open span is untouched
        finally:
            await aengine.dispose()
