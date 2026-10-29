"""One database engine per run of a socket consumer (#2471).

WHY. The Kalshi and Polymarket consumers open a database session for every
flush, every blend refresh, every lifecycle and resolution write — and each
``get_task_session()`` used to build a NEW engine and connection pool, connect,
do one transaction, and dispose it. On a flush that runs every 2 seconds, start
to start (#10090), that is a Postgres connect/TLS/startup handshake paid again
and again on the path a genuine venue price travels to the headline.

WHAT THIS DOES. :class:`ConsumerSessions` owns ONE engine for the life of one
consumer run (one call of ``_run_kalshi_ws_consumer`` or
``_run_polymarket_ws_consumer``, i.e. one recycle). Every operation still gets a
FRESH session and its own transaction through ``get_task_session(engine=...)``,
so commit-before-publish, rollback on error and the committed non-venue frames
are exactly the task factory's — reused, not copied. Only the engine outlives
the transaction.

WHAT IT REFUSES.

* Another event loop or another process. An asyncpg connection belongs to the
  loop that opened it, and a pool inherited through ``fork`` shares sockets with
  its parent. The engine is pinned to the loop and pid that created it; any use
  from elsewhere raises instead of borrowing it.
* A per-call budget. ``statement_timeout_ms`` / ``lock_timeout_ms`` are
  per-ENGINE startup parameters (#4482), so they cannot vary per session on a
  shared engine. These consumers never passed one; the engine carries the same
  resting bounds every task engine does (five connections maximum, pre-ping,
  1800 s recycle, the resting ``statement_timeout``; the pre-ping is the
  switch below). Socket consumers retain
  all five connections so overlapping flush/stamp work can reuse them.
  A caller that needs a tighter budget uses ``get_task_session`` directly.
* Use after close. Once the run has drained, a late caller cannot quietly
  re-create a pool nobody will dispose.

CLEANUP. :meth:`ConsumerSessions.aclose` stops new sessions, waits (bounded) for
the ones still open — a cancelled flush or resolution write unwinding its
rollback — and disposes the engine exactly once. :func:`owns_consumer_sessions`
calls it in a ``finally`` around the whole consumer, after the consumer's own
final drain has returned.

PRE-PING (#10090). On asyncpg the pool's pre-ping is three round trips per
checkout (BEGIN, ``;``, ROLLBACK), and a Kalshi price phase checks out once, so
three of the five round trips its first statement waits on are the ping.
``WS_CONSUMER_POOL_PRE_PING`` (read once at import; default on, today's
behaviour) turns it off for this engine only, never the web or Celery engines.
Off, a connection the server closed is found by the operation's first
statement: SQLAlchemy invalidates it on the disconnect error, the session rolls
back through the task factory (nothing commits or publishes), and the next
checkout connects afresh. ``pool_recycle`` is unchanged.

CHECKOUT PROBE (#10090). :func:`checkout_probe` lets a caller time what the
pool did inside one span on this engine — when the connection was handed over,
how many connects that took and how long they ran, and whether every slot was
already out when the span began — without touching the statements it times.
"""

from __future__ import annotations

import asyncio
import contextlib
import functools
import logging
import os
from contextlib import asynccontextmanager, contextmanager
from contextvars import ContextVar

logger = logging.getLogger(__name__)

#: How long :meth:`ConsumerSessions.aclose` waits for sessions still open when
#: the consumer returns. Everything still running then has been cancelled by the
#: consumer's ``finally``, so this only covers a rollback unwinding; it is a
#: bound, not an expected wait.
CLOSE_WAIT_S = 10.0


def _pre_ping_env(name: str, default: bool) -> bool:
    """#10090 — one boolean setting. Missing or blank is the default; anything
    but true/false/1/0/yes/no/on/off is the default with one warning."""
    raw = os.environ.get(name)
    if raw is None or not raw.strip():
        return default
    value = raw.strip().lower()
    if value in ("1", "true", "yes", "on"):
        return True
    if value in ("0", "false", "no", "off"):
        return False
    logger.warning(
        "ws_consumer_sessions: %s=%r is not a valid boolean; using %r",
        name, raw, default,
    )
    return default


#: #10090 — the consumer engine's ``pool_pre_ping``. Env
#: `WS_CONSUMER_POOL_PRE_PING`; default True is today's engine exactly.
CONSUMER_POOL_PRE_PING = _pre_ping_env("WS_CONSUMER_POOL_PRE_PING", True)
_PRE_PING_LOGGED = False


class CheckoutProbe:
    """What this engine's pool did inside one :func:`checkout_probe` span."""

    __slots__ = (
        "clock", "full_at_start", "checked_out_at", "connects", "connect_s",
        "_connect_started",
    )

    def __init__(self, clock, full_at_start: bool) -> None:
        self.clock = clock
        self.full_at_start = full_at_start
        self.checked_out_at = None
        self.connects = 0
        self.connect_s = 0.0
        self._connect_started = None


_PROBE: ContextVar[CheckoutProbe | None] = ContextVar("ws_checkout_probe", default=None)
_SESSION_ENGINE: ContextVar = ContextVar("ws_consumer_session_engine", default=None)


def _pool_full(pool) -> bool:
    overflow = getattr(pool, "_max_overflow", 0)
    if overflow < 0:
        return False
    return pool.checkedout() >= pool.size() + overflow


@contextmanager
def checkout_probe(clock):
    """Record this task's pool events until exit, on ``clock``.

    ``full_at_start`` reads the pool of the consumer session this task is in;
    outside one (or on another engine) the probe records nothing. Contexts are
    per task, and SQLAlchemy's greenlet shares its task's, so a concurrent
    task's checkout or connect never lands here.
    """
    engine = _SESSION_ENGINE.get()
    full = False
    if engine is not None:
        try:
            full = _pool_full(engine.sync_engine.pool)
        except Exception:  # a log field must never fail the phase
            full = False
    probe = CheckoutProbe(clock, full)
    token = _PROBE.set(probe)
    try:
        yield probe
    finally:
        _PROBE.reset(token)


def _probe_connect_started(*_args):
    probe = _PROBE.get()
    if probe is not None:
        probe._connect_started = probe.clock()
    return None  # the dialect's own connect runs


def _probe_connected(*_args):
    probe = _PROBE.get()
    if probe is not None and probe._connect_started is not None:
        probe.connects += 1
        probe.connect_s += probe.clock() - probe._connect_started
        probe._connect_started = None


def _probe_checked_out(*_args):
    probe = _PROBE.get()
    if probe is not None and probe.checked_out_at is None:
        probe.checked_out_at = probe.clock()


def _consumer_engine():
    from sqlalchemy import event

    from app.tasks import base as task_base

    global _PRE_PING_LOGGED
    # On (the default) the factory is asked exactly what it was asked before.
    if CONSUMER_POOL_PRE_PING:
        engine = task_base._get_task_engine(retain_full_pool=True)
    else:
        engine = task_base._get_task_engine(retain_full_pool=True, pool_pre_ping=False)
    if not _PRE_PING_LOGGED:
        # Once per process, so a capture binds its window to the setting.
        _PRE_PING_LOGGED = True
        logger.info(
            "ws_consumer_sessions: consumer engine pool_pre_ping=%s "
            "(WS_CONSUMER_POOL_PRE_PING)", CONSUMER_POOL_PRE_PING,
        )
    try:
        sync = engine.sync_engine
        event.listen(sync, "do_connect", _probe_connect_started)
        event.listen(sync, "connect", _probe_connected)
        event.listen(sync, "checkout", _probe_checked_out)
    except Exception:  # log fields only: the engine serves without them
        logger.warning(
            "ws_consumer_sessions: checkout probe not installed", exc_info=True,
        )
    return engine


class _SingleRead:
    """Only one SQLAlchemy SELECT may use the autocommit connection."""

    def __init__(self, connection):
        self._connection = connection
        self._used = False

    async def execute(self, statement):
        if self._used or not getattr(statement, "is_select", False):
            raise ValueError("observation read scope permits exactly one SELECT")
        self._used = True
        return await self._connection.execute(statement)


class ConsumerSessions:
    """One lazily-created engine, fresh sessions per operation, one dispose."""

    def __init__(self, label: str, *, close_wait_s: float = CLOSE_WAIT_S) -> None:
        self.label = label
        self._close_wait_s = close_wait_s
        self._engine = None
        self._loop: asyncio.AbstractEventLoop | None = None
        self._pid: int | None = None
        self._open = 0
        self._idle = asyncio.Event()
        self._idle.set()
        self._closing = False
        self._disposed = False
        self._observation_closers: set[asyncio.Task] = set()

    def _engine_here(self):
        if self._closing:
            raise RuntimeError(
                f"{self.label}: consumer sessions are closed; this run has drained"
            )
        loop = asyncio.get_running_loop()
        if self._engine is None:
            self._engine = _consumer_engine()
            self._loop = loop
            self._pid = os.getpid()
        elif loop is not self._loop or os.getpid() != self._pid:
            raise RuntimeError(
                f"{self.label}: this consumer's engine belongs to another event "
                "loop or process and cannot be shared"
            )
        return self._engine

    @asynccontextmanager
    async def session(self, **budget):
        """Drop-in for ``get_task_session()`` inside one consumer run."""
        from app.tasks import base as task_base

        if budget:
            raise TypeError(
                f"{self.label}: a per-session budget {sorted(budget)} cannot be "
                "honoured on a shared engine (#4482: budgets are per-engine); "
                "use get_task_session() directly for that operation"
            )
        engine = self._engine_here()
        self._open += 1
        self._idle.clear()
        engine_token = _SESSION_ENGINE.set(engine)
        try:
            # Looked up at call time so the factory's transaction semantics —
            # commit, publish committed frames, rollback, close — stay the one
            # definition in `app.tasks.base`.
            async with task_base.get_task_session(engine=engine) as session:
                yield session
        finally:
            with contextlib.suppress(ValueError):  # exited in another context
                _SESSION_ENGINE.reset(engine_token)
            self._open -= 1
            if not self._open:
                self._idle.set()

    @asynccontextmanager
    async def observation_read(self):
        """One fresh statement snapshot, with no separate COMMIT round trip.

        Only the observation-preview graph SELECT uses this scope. Writers
        still use session(), including its commit and publication hooks.
        The connection shares this consumer's pool. A close exceeding the
        caller's budget stays owned and counted until it completes; shutdown
        drains it under the existing close bound.
        """
        engine = self._engine_here()
        self._open += 1
        self._idle.clear()
        connection = None
        try:
            connection = await engine.connect().__aenter__()
            connection = await connection.execution_options(
                isolation_level="AUTOCOMMIT",
            )
            yield _SingleRead(connection)
        finally:
            if connection is None:
                self._observation_finished()
            else:
                # Match AsyncConnection.__aexit__'s shielded close, but retain
                # the task and open count if the caller's deadline interrupts
                # the await. A late exception must also be retrieved.
                close_task = asyncio.create_task(connection.close())
                self._observation_closers.add(close_task)
                close_task.add_done_callback(self._observation_closed)
                await asyncio.shield(close_task)

    def _observation_finished(self) -> None:
        self._open -= 1
        if not self._open:
            self._idle.set()

    def _observation_closed(self, task: asyncio.Task) -> None:
        self._observation_closers.discard(task)
        if not task.cancelled():
            error = task.exception()
            if error is not None:
                logger.warning(
                    "%s: observation connection cleanup failed", self.label,
                    exc_info=(type(error), error, error.__traceback__),
                )
        self._observation_finished()

    async def aclose(self) -> None:
        """Refuse new sessions, let open ones finish (bounded), dispose once."""
        self._closing = True
        if self._disposed or self._engine is None:
            return
        try:
            if self._open:
                try:
                    await asyncio.wait_for(self._idle.wait(), self._close_wait_s)
                except asyncio.TimeoutError:
                    logger.warning(
                        "%s: %d session(s) still open %.0fs after the consumer "
                        "returned; disposing the engine anyway",
                        self.label, self._open, self._close_wait_s,
                    )
        finally:
            if not self._disposed:
                self._disposed = True
                await self._engine.dispose()


def owns_consumer_sessions(label: str):
    """Run the decorated consumer with its own :class:`ConsumerSessions`.

    The consumer receives it as ``sessions`` and closes nothing itself: the
    engine is disposed here, after the consumer — including its final drain and
    every ``finally`` — has returned or raised, on every exit path.
    """

    def decorate(consumer):
        @functools.wraps(consumer)
        async def run(*args, **kwargs):
            sessions = ConsumerSessions(label)
            try:
                return await consumer(*args, sessions=sessions, **kwargs)
            finally:
                await sessions.aclose()

        return run

    return decorate
