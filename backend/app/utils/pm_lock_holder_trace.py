"""#10090: bounded attribution of the transaction a Polymarket rank write waits on.

Why. On v5775 (05:15:13-05:16:24Z, 2026-10-18) 31 flush errors were the field
re-rank `UPDATE futures_outcomes SET rank=...` cancelled at its lock budget, and
each one rolled back its whole price chunk (Root attempt58, real PG: 537 ms, no
publication). Nothing recorded WHICH transaction held the rows, so the repair
cannot be chosen: shorten the holder's transaction, or isolate the market. This
records that one fact, and stops.

What. When the writer is about to run the re-rank statement it hands this
sampler its own backend pid and the chunk's market ids. The sampler waits
`PROBE_DELAY_S` (150 ms), and only if that statement is STILL running asks
PostgreSQL, on its own connection, who the writer is waiting on:
`pg_blocking_pids` joined to `pg_stat_activity` (pid, application_name, state,
transaction age, the writer's wait event). A rank that finished inside 150 ms
spends nothing. Root measured the shape locally: one probe 150 ms after the
RANK statement starts named the known holder in 7.56 ms; a trigger at the
price statement's start sampled before the rank was blocked and missed it.

Bounds. Off unless WS_PM_LOCK_HOLDER_EXPIRES_AT is an absolute epoch second no
more than `MAX_WINDOW_S` away. One probe in flight per process, at least
`MIN_PROBE_INTERVAL_S` between probes, at most WS_PM_LOCK_HOLDER_MAX_PROBES
(default 10, cap 30). STOP at the first probe that names a holder, at expiry or
at the probe budget, and dispose the connection. The probe runs on a one-
connection engine of its own (`statement_timeout` 100 ms, warmed at START,
never the writer's pool) under a `PROBE_DEADLINE_S` wait. The writer never
awaits the observer: it flips a flag when its statement returns. A probe that
completes after that flag is set is STALE_RANK_ENDED and names nobody: its
snapshot may be of the writer's next statement (Root attempt60).

What is NOT recorded. No SQL text, no parameters, no prices. An empty or absent
`application_name` is written as UNKNOWN; it is never filled in from a schedule
that happened to overlap. Market ids (first `MAX_MARKETS_LOGGED`) and counts are
taken before the statement runs, so a truncated exception record downstream
cannot cost the join (the v5775 records were cut at ~10 KB, before their
parameters).

Every entry point catches its own exceptions. Evidence must never cost a price,
an exception, a cancellation or a retry. Activation is owner-controlled; a
Heroku config change restarts the dyno, so it must not overlap a deployment.
"""

from __future__ import annotations

import asyncio
import json
import logging
import time

logger = logging.getLogger(__name__)

PROBE_DELAY_S = 0.150
PROBE_DEADLINE_S = 0.100
PROBE_STATEMENT_TIMEOUT_MS = 100
MIN_PROBE_INTERVAL_S = 60.0
MAX_WINDOW_S = 3600
DEFAULT_MAX_PROBES = 10
MAX_PROBES_CAP = 30
MAX_MARKETS_LOGGED = 8
MAX_HOLDERS_LOGGED = 4
WARM_TIMEOUT_S = 5.0
APPLICATION_NAME = "bl-pm-lock-holder-trace"

PROBE_SQL = """
SELECT waiting.wait_event_type AS writer_wait_event_type,
       waiting.wait_event AS writer_wait_event,
       holder.pid AS blocking_pid,
       holder.application_name AS blocker_application,
       holder.state AS blocker_state,
       EXTRACT(EPOCH FROM clock_timestamp() - holder.xact_start)::float
           AS blocker_transaction_age_s
  FROM pg_stat_activity waiting
  CROSS JOIN LATERAL unnest(pg_blocking_pids(waiting.pid)) blocker(pid)
  JOIN pg_stat_activity holder ON holder.pid = blocker.pid
 WHERE waiting.pid = :pid
   AND waiting.wait_event_type = 'Lock'
"""

#: One sampler per process: the consumer re-enters on every recycle, and the
#: per-minute and per-window budgets are the process's, not the run's.
_process_sampler: RankLockHolderSampler | None = None
_process_configured = False


def for_process(env, *, run):
    """The process's sampler, built from `env` on the first call only."""
    global _process_sampler, _process_configured
    try:
        if not _process_configured:
            _process_configured = True
            _process_sampler = RankLockHolderSampler.from_env(env, run=run)
        return _process_sampler
    except Exception:
        return None


class _Token:
    __slots__ = (
        "writer_pid", "markets", "markets_n", "outcomes_n", "started", "done",
        "probed", "task",
    )

    def __init__(self, writer_pid, markets, outcomes_n, started):
        ordered = sorted(markets)
        self.writer_pid = writer_pid
        self.markets = ordered[:MAX_MARKETS_LOGGED]
        self.markets_n = len(ordered)
        self.outcomes_n = outcomes_n
        self.started = started
        self.done = False
        self.probed = False
        self.task = None


class RankLockHolderSampler:
    @classmethod
    def from_env(
        cls, env, *, run, wall=time.time, mono=time.monotonic, emit=None,
        engine_factory=None,
    ):
        try:
            raw = env.get("WS_PM_LOCK_HOLDER_EXPIRES_AT", "")
            if not raw or len(raw) > 32:
                return None
            expiry = float(raw)
            remaining = expiry - wall()
            raw_max = env.get("WS_PM_LOCK_HOLDER_MAX_PROBES", str(DEFAULT_MAX_PROBES))
            max_probes = int(raw_max)
            if not 0 < remaining <= MAX_WINDOW_S or not 1 <= max_probes <= MAX_PROBES_CAP:
                return None
            sampler = cls(
                expiry, max_probes, run, wall, mono, emit,
                engine_factory or _default_engine_factory,
            )
            sampler._send(
                "START", window_s=round(remaining, 3), max_probes=max_probes,
                probe_delay_ms=PROBE_DELAY_S * 1000,
                probe_deadline_ms=PROBE_DEADLINE_S * 1000,
                min_interval_s=MIN_PROBE_INTERVAL_S,
            )
            return sampler
        except (ValueError, TypeError, OverflowError):
            return None

    def __init__(self, expiry, max_probes, run, wall, mono, emit, engine_factory):
        self.expiry, self.max_probes, self.run = expiry, max_probes, run
        self.wall, self.mono = wall, mono
        self.deadline = mono() + expiry - wall()
        self.emit = emit or (
            lambda record: logger.info(
                "pm-lock-holder %s", json.dumps(record, sort_keys=True)
            )
        )
        self.engine_factory = engine_factory
        self.engine = None
        self.engine_loop = None
        self.warming = None
        self.pending = None
        self.last_probe = None
        self.probes = 0
        self.stopped = False

    # --- writer side: synchronous apart from reading its own pid ------------

    def ready(self):
        """True when a rank start now would arm a probe. Never raises."""
        try:
            if not self._active() or self.pending is not None:
                return False
            if self.last_probe is not None and (
                self.mono() - self.last_probe < MIN_PROBE_INTERVAL_S
            ):
                return False
            self._ensure_warm()
            return self.engine is not None
        except Exception:
            return False

    async def writer_pid(self, session):
        """The writer's backend pid, read off its driver connection (no I/O)."""
        try:
            conn = await session.connection()
            raw = await conn.get_raw_connection()
            return raw.driver_connection.get_server_pid()
        except Exception:
            return None

    def rank_started(self, writer_pid, chunk, market_ids):
        """Arm one delayed probe for this rank statement. Never raises."""
        try:
            if writer_pid is None or not self.ready():
                return None
            token = _Token(writer_pid, market_ids, len(chunk), self.mono())
            self.pending = token
            token.task = asyncio.get_running_loop().create_task(self._observe(token))
            return token
        except Exception:
            self.pending = None
            return None

    def rank_finished(self, token, error):
        """The writer's statement returned (or raised). Never raises."""
        try:
            token.done = True
            if token.probed:
                self._send(
                    "RANK_END", writer_pid=token.writer_pid, markets=token.markets,
                    rank_elapsed_ms=round((self.mono() - token.started) * 1000, 3),
                    rank_result="ok" if error is None else _error_name(error),
                )
        except Exception:
            pass

    # --- observer side ------------------------------------------------------

    async def _observe(self, token):
        try:
            await asyncio.sleep(PROBE_DELAY_S)
            if token.done or not self._active():
                return
            token.probed = True
            self.last_probe = self.mono()
            self.probes += 1
            started = self.mono()
            rows, error = [], None
            try:
                rows = await asyncio.wait_for(
                    self._probe(token.writer_pid), PROBE_DEADLINE_S
                )
                result = "HOLDER" if rows else "NO_LOCK_WAIT"
            except asyncio.TimeoutError:
                result = "PROBE_TIMEOUT"
            except Exception as exc:
                result, error = "PROBE_FAILED", type(exc).__name__
            if token.done:
                # Root attempt60: the rank returned while the probe was in
                # flight, so its snapshot may be of the writer's NEXT
                # statement's wait. Nothing here can tell which, so nothing is
                # attributed and the sampler does not stop on it. The budget
                # and the per-minute floor are spent as for any probe.
                result, rows = "STALE_RANK_ENDED", []
            self._send(
                "PROBE", result=result, error=error,
                writer_pid=token.writer_pid, markets=token.markets,
                markets_n=token.markets_n, outcomes_n=token.outcomes_n,
                rank_waited_ms=round((started - token.started) * 1000, 3),
                probe_ms=round((self.mono() - started) * 1000, 3),
                rank_still_running=not token.done,
                writer_wait=_writer_wait(rows),
                holders=[_holder(r) for r in rows[:MAX_HOLDERS_LOGGED]],
                holders_n=len(rows), probe=self.probes,
            )
            if result == "HOLDER":
                self._stop("FIRST_HOLDER")
            elif self.probes >= self.max_probes:
                self._stop("PROBE_BUDGET")
        except asyncio.CancelledError:
            raise
        except Exception:
            pass
        finally:
            if self.pending is token:
                self.pending = None

    async def _probe(self, writer_pid):
        from sqlalchemy import text

        async with self.engine.connect() as conn:
            result = await conn.execute(text(PROBE_SQL), {"pid": writer_pid})
            return [dict(row) for row in result.mappings()]

    def _ensure_warm(self):
        loop = asyncio.get_running_loop()
        if self.engine is not None and self.engine_loop is loop:
            return
        if self.warming is not None and not self.warming.done():
            return
        self.engine, self.engine_loop = None, None
        self.warming = loop.create_task(self._warm(loop))

    async def _warm(self, loop):
        """Open the probe's own connection outside any probe's deadline."""
        engine = None
        try:
            from sqlalchemy import text

            engine = self.engine_factory()

            async def _first_connection():
                async with engine.connect() as conn:
                    await conn.execute(text("SELECT 1"))

            # The bound covers acquiring the connection, not only the SELECT.
            await asyncio.wait_for(_first_connection(), WARM_TIMEOUT_S)
            if self._active():
                self.engine, self.engine_loop = engine, loop
                self._send("WARM")
                return
        except asyncio.CancelledError:
            if engine is not None:
                await asyncio.shield(_dispose(engine))
            raise
        except Exception as exc:
            self._send("UNAVAILABLE", error=type(exc).__name__)
            self._stop("UNAVAILABLE")
        if engine is not None and self.engine is not engine:
            await _dispose(engine)

    # --- lifecycle ------------------------------------------------------------

    def _active(self):
        if self.stopped:
            return False
        if self.wall() >= self.expiry or self.mono() >= self.deadline:
            self._stop("EXPIRED")
            return False
        return True

    def _stop(self, reason):
        if self.stopped:
            return
        self.stopped = True
        self._send("STOP", reason=reason, probes=self.probes)
        engine, self.engine, self.engine_loop = self.engine, None, None
        if engine is not None:
            try:
                asyncio.get_running_loop().create_task(_dispose(engine))
            except Exception:
                pass

    def _send(self, kind, **fields):
        try:
            record = {"run": self.run, "kind": kind, "wall": self.wall(), "mono": self.mono()}
            record.update(fields)
            self.emit(record)
        except Exception:
            pass  # evidence must never cost a price


def _default_engine_factory():
    from sqlalchemy.ext.asyncio import create_async_engine

    from app.services.database import DATABASE_URL, build_connect_args

    args = build_connect_args(statement_timeout_ms=PROBE_STATEMENT_TIMEOUT_MS)
    args.setdefault("server_settings", {})["application_name"] = APPLICATION_NAME
    return create_async_engine(
        DATABASE_URL, pool_size=1, max_overflow=0, pool_recycle=1800,
        connect_args=args,
    )


async def _dispose(engine):
    try:
        await engine.dispose()
    except Exception:
        pass


def _error_name(error):
    from app.utils.repair_lock_budget import is_lock_timeout

    try:
        if is_lock_timeout(error):
            return "LOCK_TIMEOUT"
    except Exception:
        pass
    return type(error).__name__


def _writer_wait(rows):
    if not rows:
        return None
    first = rows[0]
    return f"{first.get('writer_wait_event_type')}/{first.get('writer_wait_event')}"


def _holder(row):
    age = row.get("blocker_transaction_age_s")
    return {
        "pid": row.get("blocking_pid"),
        "application": row.get("blocker_application") or "UNKNOWN",
        "state": row.get("blocker_state"),
        "xact_age_s": None if age is None else round(float(age), 3),
    }
