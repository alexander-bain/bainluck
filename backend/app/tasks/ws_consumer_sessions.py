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
  1800 s recycle, the resting ``statement_timeout``). Socket consumers retain
  all five connections so overlapping flush/stamp work can reuse them.
  A caller that needs a tighter budget uses ``get_task_session`` directly.
* Use after close. Once the run has drained, a late caller cannot quietly
  re-create a pool nobody will dispose.

CLEANUP. :meth:`ConsumerSessions.aclose` stops new sessions, waits (bounded) for
the ones still open — a cancelled flush or resolution write unwinding its
rollback — and disposes the engine exactly once. :func:`owns_consumer_sessions`
calls it in a ``finally`` around the whole consumer, after the consumer's own
final drain has returned.
"""

from __future__ import annotations

import asyncio
import functools
import logging
import os
from contextlib import asynccontextmanager

logger = logging.getLogger(__name__)

#: How long :meth:`ConsumerSessions.aclose` waits for sessions still open when
#: the consumer returns. Everything still running then has been cancelled by the
#: consumer's ``finally``, so this only covers a rollback unwinding; it is a
#: bound, not an expected wait.
CLOSE_WAIT_S = 10.0


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

    def _engine_here(self):
        from app.tasks import base as task_base

        if self._closing:
            raise RuntimeError(
                f"{self.label}: consumer sessions are closed; this run has drained"
            )
        loop = asyncio.get_running_loop()
        if self._engine is None:
            self._engine = task_base._get_task_engine(retain_full_pool=True)
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
        try:
            # Looked up at call time so the factory's transaction semantics —
            # commit, publish committed frames, rollback, close — stay the one
            # definition in `app.tasks.base`.
            async with task_base.get_task_session(engine=engine) as session:
                yield session
        finally:
            self._open -= 1
            if not self._open:
                self._idle.set()

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
