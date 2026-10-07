"""#2471 — a socket consumer keeps ONE database engine for its run.

THE SHIP. A genuine Kalshi/Polymarket price reaches the headline and chart
sooner because the flush path stops paying a fresh engine, pool and Postgres
connect for every transaction. Before this change every ``get_task_session()``
inside ``_run_kalshi_ws_consumer`` / ``_run_polymarket_ws_consumer`` (slate
read, every 2 s flush, every blend stamp, lifecycle and resolution writes)
built an engine and disposed it again.

WHAT THIS FILE PROVES, and what stays unchanged.

* The real consumers, driven over the fake socket the Q491 file established,
  lend ONE engine to every session they open across several flush cycles, and
  dispose it exactly once, after the final drain's last session has closed —
  on a planned recycle, on a hard cancellation, and per run across a recycle.
  On the pre-#2471 code every one of those sessions arrives with no engine,
  i.e. builds its own: the lifecycle assertions fail there.
* Against the REAL ``get_task_session`` and a real (never-connected) engine:
  each operation is still a separate session and transaction, a failure rolls
  back only that transaction, and the lent engine survives it.
* The engine is pinned to its loop and process, refuses use after close and
  refuses per-session budgets; its pool/query/lock bounds are the task engine's.

Commit-before-publish, the requeue of a failed write, the newest-tick rule and
the final drain are the Q491 / #9484 files' guards; they run unchanged against
this code (the fakes there accept the new ``engine=`` keyword).
"""

import ast
import asyncio
import inspect
import json
import threading

import pytest
from sqlalchemy.dialects import postgresql
from sqlalchemy.sql.dml import Update

import app.services.kalshi_ws as kalshi_svc
import app.tasks.base as task_base
import app.tasks.kalshi_ws as kalshi_task
import app.tasks.live_blend_refresh as blend_mod
import app.tasks.polymarket_ws as poly_task
from app.utils.repair_lock_budget import SET_LOCK_TIMEOUT_SQL

from tests.test_ws_flush_retry_q491 import (
    KALSHI_SLATE,
    KALSHI_TICKER,
    POLY_SLATE,
    YES_TOKEN,
    _install_socket,
    _poly_frame,
    _Result,
)

#: A URL whose engine can be built and disposed without a server: nothing in
#: these tests executes SQL on it.
UNREACHABLE_PG = "postgresql+asyncpg://u:p@db.invalid:5432/x"


# ---------------------------------------------------------------- fakes ----


class _FakeEngine:
    def __init__(self, n, log):
        self.n = n
        self.log = log
        self.disposed = 0

    async def dispose(self):
        self.disposed += 1
        self.log.append(("dispose", self.n))


class _Rig:
    """Counts engines the consumer builds and records every session it opens.

    ``get_task_session`` is replaced the way every consumer test replaces it;
    the difference is that this one records the ``engine`` it was lent. A call
    with no engine is one the real factory would have built (and disposed) an
    engine for — the pre-#2471 shape.
    """

    def __init__(self, slate):
        self.batches = [list(b) for b in slate]
        self.log: list[tuple] = []
        self.engines: list[_FakeEngine] = []
        self.calls: list[dict] = []
        self.writes: list[tuple[int, float]] = []
        self.open = 0

    def build_engine(self, **budget):
        assert not budget, f"the consumer engine must carry no budget: {budget}"
        engine = _FakeEngine(len(self.engines), self.log)
        self.engines.append(engine)
        self.log.append(("engine", engine.n))
        return engine

    def get_task_session(self, *, engine=None, **budget):
        rig = self

        class _Session:
            def __init__(self):
                self.info = {}

            async def execute(self, stmt, params=None):
                if stmt is SET_LOCK_TIMEOUT_SQL:  # #10661: the flush's lock budget
                    return _Result([])
                if isinstance(stmt, Update):
                    params = stmt.compile(dialect=postgresql.dialect()).params
                    if (
                        stmt.table.name == "futures_outcomes"
                        and "current_probability" in params
                    ):
                        rig.writes.append(
                            (params["id_1"], params["current_probability"])
                        )
                    return _Result([])
                return _Result(rig.batches.pop(0) if rig.batches else [])

        class _Ctx:
            async def __aenter__(self_inner):
                session = _Session()
                rig.calls.append(
                    {"engine": engine, "budget": budget, "session": session}
                )
                rig.open += 1
                rig.log.append(("enter", len(rig.calls)))
                return session

            async def __aexit__(self_inner, *_exc):
                rig.open -= 1
                rig.log.append(("exit", len(rig.calls)))
                return False

        return _Ctx()


def _install(monkeypatch, rig):
    monkeypatch.setattr(task_base, "_get_task_engine", rig.build_engine)
    monkeypatch.setattr(task_base, "get_task_session", rig.get_task_session)


def _kalshi_tick(bid, ask):
    return json.dumps({
        "type": "ticker",
        "msg": {
            "market_ticker": KALSHI_TICKER,
            "yes_bid_dollars": bid,
            "yes_ask_dollars": ask,
        },
    })


async def _run_kalshi(monkeypatch, frames, rig, recycle=0.4):
    monkeypatch.setenv("KALSHI_API_KEY_ID", "test-key")
    monkeypatch.setenv("KALSHI_RSA_PRIVATE_KEY", "test-secret")
    monkeypatch.setattr(kalshi_svc, "_load_rsa_key", lambda: object())
    monkeypatch.setattr(kalshi_svc, "_sign_ws_request", lambda _k, _i: {})
    monkeypatch.setattr(kalshi_task, "SUBSCRIPTION_REFRESH_SECONDS", recycle)
    monkeypatch.setattr(kalshi_task, "PRICE_FLUSH_SECONDS", 0.02)
    _install_socket(monkeypatch, frames)
    _install(monkeypatch, rig)
    return await kalshi_task._run_kalshi_ws_consumer()


async def _run_poly(monkeypatch, frames, rig, recycle=0.4):
    monkeypatch.setattr(poly_task, "SUBSCRIPTION_REFRESH_SECONDS", recycle)
    monkeypatch.setattr(poly_task, "PRICE_FLUSH_SECONDS", 0.02)
    _install_socket(monkeypatch, frames)
    _install(monkeypatch, rig)
    return await poly_task._run_polymarket_ws_consumer()


def _assert_one_lent_engine(rig, label):
    lent = {id(c["engine"]) for c in rig.calls}
    unlent = sum(c["engine"] is None for c in rig.calls)
    assert unlent == 0, (
        f"{label}: {unlent} of {len(rig.calls)} sessions built their own engine "
        "(no engine lent) — the per-transaction connect #2471 removes"
    )
    assert len(rig.engines) == 1, f"{label}: engines built = {len(rig.engines)}"
    assert lent == {id(rig.engines[0])}, f"{label}: sessions saw several engines"
    assert len({id(c["session"]) for c in rig.calls}) == len(rig.calls), (
        f"{label}: an operation reused another operation's session"
    )
    assert all(not c["budget"] for c in rig.calls), label


def _assert_disposed_once_after_last_session(rig, label):
    (engine,) = rig.engines
    assert engine.disposed == 1, f"{label}: disposed {engine.disposed}x"
    dispose_at = rig.log.index(("dispose", 0))
    last_exit = max(i for i, e in enumerate(rig.log) if e[0] == "exit")
    assert last_exit < dispose_at, (
        f"{label}: the engine was disposed before the last session closed"
    )
    assert not any(e[0] == "enter" for e in rig.log[dispose_at:]), (
        f"{label}: a session opened after the engine was disposed"
    )
    assert rig.open == 0, label


# ------------------------------------------------- the real consumers ----


class TestTheConsumerLendsOneEngineToEverySession:
    async def test_kalshi_several_flushes_one_engine(self, monkeypatch):
        rig = _Rig(KALSHI_SLATE)
        await _run_kalshi(
            monkeypatch,
            [_kalshi_tick("0.40", "0.44"), _kalshi_tick("0.50", "0.54")],
            rig,
        )
        # The two ticks coalesce or not depending on the flush timing; the
        # newest one is the last stored either way.
        assert rig.writes and rig.writes[-1][1] == pytest.approx(0.52), rig.writes
        # Slate + periodic flushes + blend stamps + admission reads: the
        # control is that MANY operations share the engine, not a count tuned
        # to the timer.
        assert len(rig.calls) >= 4, len(rig.calls)
        _assert_one_lent_engine(rig, "kalshi")
        _assert_disposed_once_after_last_session(rig, "kalshi")

    async def test_polymarket_several_flushes_one_engine(self, monkeypatch):
        rig = _Rig(POLY_SLATE)
        await _run_poly(
            monkeypatch,
            [
                _poly_frame("best_bid_ask", YES_TOKEN, best_bid="0.68", best_ask="0.72"),
                _poly_frame("best_bid_ask", YES_TOKEN, best_bid="0.58", best_ask="0.62"),
            ],
            rig,
        )
        assert rig.writes and rig.writes[-1][1] == pytest.approx(0.60), rig.writes
        assert len(rig.calls) >= 4, len(rig.calls)
        _assert_one_lent_engine(rig, "polymarket")
        _assert_disposed_once_after_last_session(rig, "polymarket")

    async def test_the_blend_stamp_borrows_the_same_engine(self, monkeypatch):
        """The refresher is the second writer on the flush path. Its session
        must come from the consumer's factory, not the default one."""
        seen = []

        async def _spy_batch(self, event_ids, now):
            async with self._session_factory() as _session:
                seen.append(self._session_factory)

        monkeypatch.setattr(blend_mod.LiveBlendRefresher, "_refresh_batch", _spy_batch)
        rig = _Rig(KALSHI_SLATE)
        await _run_kalshi(monkeypatch, [_kalshi_tick("0.40", "0.44")], rig)
        assert seen, "the flush never reached the blend stamp"
        _assert_one_lent_engine(rig, "kalshi+refresher")

    async def test_a_recycle_is_a_new_run_with_its_own_engine(self, monkeypatch):
        """Each run owns its engine; nothing is carried across the recycle."""
        rig = _Rig(KALSHI_SLATE + KALSHI_SLATE)
        await _run_kalshi(monkeypatch, [_kalshi_tick("0.40", "0.44")], rig, recycle=0.2)
        await _run_kalshi(monkeypatch, [_kalshi_tick("0.40", "0.44")], rig, recycle=0.2)
        assert len(rig.engines) == 2
        assert [e.disposed for e in rig.engines] == [1, 1]
        first_dispose = rig.log.index(("dispose", 0))
        assert rig.log.index(("engine", 1)) > first_dispose, (
            "the second run's engine must not exist while the first is alive"
        )
        assert all(c["engine"] is not None for c in rig.calls)

    async def test_hard_cancellation_still_disposes_once_after_the_drain(
        self, monkeypatch
    ):
        rig = _Rig(KALSHI_SLATE)
        task = asyncio.create_task(
            _run_kalshi(monkeypatch, [_kalshi_tick("0.40", "0.44")], rig, recycle=30)
        )
        for _ in range(200):
            if rig.writes:
                break
            await asyncio.sleep(0.01)
        assert rig.writes, "no flush landed before the cancel"
        task.cancel()
        with pytest.raises(asyncio.CancelledError):
            await task
        _assert_one_lent_engine(rig, "kalshi-cancelled")
        _assert_disposed_once_after_last_session(rig, "kalshi-cancelled")

    async def test_a_run_that_opens_no_session_builds_no_engine(self, monkeypatch):
        """Missing credentials return before any read: the lazy engine is
        never built, so there is nothing to dispose."""
        monkeypatch.delenv("KALSHI_API_KEY_ID", raising=False)
        rig = _Rig([])
        _install(monkeypatch, rig)
        stats = await kalshi_task._run_kalshi_ws_consumer()
        assert stats["status"] == "skipped"
        assert rig.engines == [] and rig.calls == []


class TestEveryConsumerSiteIsWired:
    """A NEW `get_task_session` import inside a consumer would silently go
    back to a pool per transaction; the refresher must be handed the factory."""

    @pytest.mark.parametrize(
        "module, consumer",
        [(kalshi_task, "_run_kalshi_ws_consumer"),
         (poly_task, "_run_polymarket_ws_consumer")],
    )
    def test_consumer_binds_the_scope_and_hands_it_to_the_refresher(
        self, module, consumer
    ):
        tree = ast.parse(inspect.getsource(module))
        (fn,) = [
            n for n in ast.walk(tree)
            if isinstance(n, ast.AsyncFunctionDef) and n.name == consumer
        ]
        imports = [
            alias.name
            for n in ast.walk(fn) if isinstance(n, ast.ImportFrom)
            for alias in n.names
        ]
        assert "get_task_session" not in imports, consumer
        assert any(
            isinstance(d, ast.Call) and getattr(d.func, "id", "") == "owns_consumer_sessions"
            for d in fn.decorator_list
        ), consumer
        refreshers = [
            n for n in ast.walk(fn)
            if isinstance(n, ast.Call) and getattr(n.func, "id", "") == "LiveBlendRefresher"
        ]
        assert refreshers and all(
            any(k.arg == "session_factory" for k in c.keywords) for c in refreshers
        ), consumer

    async def test_a_default_refresher_still_uses_the_task_factory(self, monkeypatch):
        """Callers outside a consumer are unchanged."""
        opened = []

        class _Ctx:
            async def __aenter__(self):
                opened.append("default")

                class _S:
                    async def execute(self, _stmt):
                        return _EmptyResult()

                return _S()

            async def __aexit__(self, *_e):
                return False

        monkeypatch.setattr(task_base, "get_task_session", lambda **_kw: _Ctx())
        r = blend_mod.LiveBlendRefresher("kalshi")
        await r._refresh_batch([1], now=0.0)
        assert opened == ["default"]


class _EmptyResult:
    def all(self):
        return []


# ---------------------------- the real factory, the real session class ----


class _Counted:
    """A real engine plus how many times it was disposed (AsyncEngine has
    __slots__, so the count lives beside it)."""

    def __init__(self, engine):
        self.engine = engine
        self.disposals = 0


@pytest.fixture
def counted_engines(monkeypatch):
    """Real engines from the real `_get_task_engine`, counted, never connected."""
    from sqlalchemy.ext.asyncio import AsyncEngine

    monkeypatch.setattr(task_base, "DATABASE_URL", UNREACHABLE_PG)
    built: list[_Counted] = []
    real = task_base._get_task_engine
    real_dispose = AsyncEngine.dispose

    def _counting(**budget):
        engine = real(**budget)
        built.append(_Counted(engine))
        return engine

    async def _dispose(self, *a, **kw):
        for c in built:
            if c.engine is self:
                c.disposals += 1
        return await real_dispose(self, *a, **kw)

    monkeypatch.setattr(task_base, "_get_task_engine", _counting)
    monkeypatch.setattr(AsyncEngine, "dispose", _dispose)
    return built


class TestTheRealFactoryOnALentEngine:
    async def test_old_path_builds_an_engine_per_operation(self, counted_engines):
        """The before-picture, on the real factory: N operations, N engines."""
        for _ in range(3):
            async with task_base.get_task_session():
                pass
        assert len(counted_engines) == 3
        assert [e.disposals for e in counted_engines] == [1, 1, 1]

    async def test_scope_one_engine_separate_committed_sessions(
        self, counted_engines, monkeypatch
    ):
        from sqlalchemy.ext.asyncio import AsyncSession

        from app.tasks.ws_consumer_sessions import ConsumerSessions

        committed, rolled_back = [], []
        real_commit, real_rollback = AsyncSession.commit, AsyncSession.rollback

        async def _commit(self):
            committed.append(id(self))
            return await real_commit(self)

        async def _rollback(self):
            rolled_back.append(id(self))
            return await real_rollback(self)

        monkeypatch.setattr(AsyncSession, "commit", _commit)
        monkeypatch.setattr(AsyncSession, "rollback", _rollback)

        scope = ConsumerSessions("test")
        sessions = []
        for _ in range(3):
            async with scope.session() as s:
                sessions.append(s)
        with pytest.raises(RuntimeError, match="boom"):
            async with scope.session() as s:
                sessions.append(s)
                raise RuntimeError("boom")
        async with scope.session() as s:
            sessions.append(s)

        assert len(counted_engines) == 1
        assert all(s.bind is counted_engines[0].engine for s in sessions)
        assert len({id(s) for s in sessions}) == 5
        # Each operation is its own transaction: four committed, the failing
        # one rolled back and did not commit, and the engine outlived it.
        assert committed == [id(s) for i, s in enumerate(sessions) if i != 3]
        assert rolled_back == [id(sessions[3])]
        assert counted_engines[0].disposals == 0

        await scope.aclose()
        await scope.aclose()
        assert counted_engines[0].disposals == 1

    async def test_closed_scope_refuses_a_late_session(self, counted_engines):
        from app.tasks.ws_consumer_sessions import ConsumerSessions

        scope = ConsumerSessions("test")
        async with scope.session():
            pass
        await scope.aclose()
        with pytest.raises(RuntimeError, match="closed"):
            async with scope.session():
                pass
        assert len(counted_engines) == 1 and counted_engines[0].disposals == 1

    async def test_close_waits_for_an_open_session_then_disposes_once(
        self, counted_engines
    ):
        from app.tasks.ws_consumer_sessions import ConsumerSessions

        scope = ConsumerSessions("test")
        inside, release = asyncio.Event(), asyncio.Event()

        async def _straggler():
            async with scope.session():
                inside.set()
                await release.wait()

        task = asyncio.create_task(_straggler())
        await inside.wait()
        closing = asyncio.create_task(scope.aclose())
        await asyncio.sleep(0.02)
        assert counted_engines[0].disposals == 0, "disposed under an open session"
        release.set()
        await task
        await closing
        assert counted_engines[0].disposals == 1

    async def test_close_is_bounded_when_a_session_never_finishes(
        self, counted_engines
    ):
        from app.tasks.ws_consumer_sessions import ConsumerSessions

        scope = ConsumerSessions("test", close_wait_s=0.05)
        inside = asyncio.Event()

        async def _stuck():
            async with scope.session():
                inside.set()
                await asyncio.sleep(3600)

        task = asyncio.create_task(_stuck())
        await inside.wait()
        await asyncio.wait_for(scope.aclose(), timeout=2)
        assert counted_engines[0].disposals == 1
        task.cancel()
        with pytest.raises(asyncio.CancelledError):
            await task

    async def test_two_consumers_never_share_an_engine(self, counted_engines):
        from app.tasks.ws_consumer_sessions import ConsumerSessions

        a, b = ConsumerSessions("kalshi"), ConsumerSessions("polymarket")
        async with a.session() as sa, b.session() as sb:
            assert sa.bind is not sb.bind
        await a.aclose()
        await b.aclose()
        assert [e.disposals for e in counted_engines] == [1, 1]

    async def test_another_event_loop_cannot_borrow_the_engine(self, counted_engines):
        from app.tasks.ws_consumer_sessions import ConsumerSessions

        scope = ConsumerSessions("test")
        async with scope.session():
            pass
        errors = []

        def _other_loop():
            async def _borrow():
                async with scope.session():
                    pass

            try:
                asyncio.run(_borrow())
            except RuntimeError as exc:
                errors.append(str(exc))

        thread = threading.Thread(target=_other_loop)
        thread.start()
        thread.join(5)
        assert errors and "another event loop" in errors[0], errors
        assert len(counted_engines) == 1
        await scope.aclose()

    async def test_another_process_cannot_borrow_the_engine(
        self, counted_engines, monkeypatch
    ):
        import app.tasks.ws_consumer_sessions as mod

        scope = mod.ConsumerSessions("test")
        async with scope.session():
            pass
        real_pid = mod.os.getpid()
        monkeypatch.setattr(mod.os, "getpid", lambda: real_pid + 1)
        with pytest.raises(RuntimeError, match="another event loop or process"):
            async with scope.session():
                pass
        monkeypatch.setattr(mod.os, "getpid", lambda: real_pid)
        await scope.aclose()

    async def test_a_per_session_budget_is_refused(self, counted_engines):
        from app.tasks.ws_consumer_sessions import ConsumerSessions

        scope = ConsumerSessions("test")
        with pytest.raises(TypeError, match="per-engine"):
            async with scope.session(statement_timeout_ms=500):
                pass
        assert counted_engines == []
        with pytest.raises(ValueError, match="per-engine"):
            async with task_base.get_task_session(
                engine=object(), lock_timeout_ms=100
            ):
                pass


class TestTheEngineIsBounded:
    def test_pool_query_and_lock_bounds_are_the_task_engines(self, monkeypatch):
        """No new knobs: the consumer engine is `_get_task_engine()` with no
        budget — pool 3 + 2 overflow, pre-ping, 1800 s recycle and the resting
        statement bound on every connection. The one lock bound on this path is
        the refresher's, and it is TRANSACTION-local (`set_config(..., true)`),
        so it ends at commit and cannot ride a pooled connection into the next
        operation."""
        from app.services.database import DB_STATEMENT_TIMEOUT_MS
        from app.utils.repair_lock_budget import SET_LOCK_TIMEOUT_SQL

        captured = {}

        def _capture(url, **kw):
            captured.update(kw)
            return object()

        monkeypatch.setattr(task_base, "DATABASE_URL", UNREACHABLE_PG)
        monkeypatch.setattr(task_base, "create_async_engine", _capture)
        task_base._get_task_engine()
        assert captured["pool_size"] == 3
        assert captured["max_overflow"] == 2
        assert captured["pool_recycle"] == 1800
        assert captured["pool_pre_ping"] is True
        settings = captured["connect_args"]["server_settings"]
        assert settings["statement_timeout"] == str(DB_STATEMENT_TIMEOUT_MS)
        assert "lock_timeout" not in settings
        assert "true)" in str(SET_LOCK_TIMEOUT_SQL).replace(" ", "")
