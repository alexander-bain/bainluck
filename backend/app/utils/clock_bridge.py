"""#10090 amendment P: producer monotonic clock -> database clock, while armed.

Why. A display score bounds every producer's times on ONE reference: the
database's ``clock_timestamp()`` (one primary, no replica in app code). The
nonvenue and Polymarket traces already bracket a DB stamp between two of the
writer's own monotonic readings; Kalshi and the fold do not, and nothing
retained maps a trace's ``*_mono`` fields to the DB clock. This module does,
and only in a process whose existing trace is ARMED.

What it writes (exact formats: the 20261029T1318Z measurement note):

  clock_bridge[pid=N] {json}            one probe: ``wall_before``/``mono_before``,
                                        the DB's ``SELECT clock_timestamp()``
                                        (``db_clock``, ``db_clock_epoch``),
                                        ``wall_after``/``mono_after``; ``trigger``
                                        ARMED (first probe after a trace in this
                                        pid armed) or PERIODIC (every 5 s)
  clock_bridge_fault[pid=N] {json}      a CONNECT, PROBE or AUTHORITY step that
                                        did not answer (TIMEOUT or ERROR): no
                                        bracket, the cadence continues
  clock_bridge_authority[pid=N] {json}  once per run, after its first probe: this
                                        pid's DNPL registry as held in memory,
                                        one bounded read of the durable
                                        ``dnpl_authority`` row, the authority a
                                        ``preview_open_v3`` would carry, and
                                        DNPL on as this pid sees it

The DB read ``db_clock`` somewhere inside ``[mono_before, mono_after]`` of the
same pid, the clock the traces' ``*_mono`` fields use. Nothing here converts
between clocks; an empty intersection across probes is a step, never averaged.

When. A trace calls ``on_armed(window_left_s)`` at its ARMED line, or at START
when it has no ``*_ARM_AT`` (Kalshi always). `attach` wires that hook in the
four production factories. The bridge then probes at once and every
``PERIOD_S`` until the latest armed trace's deadline in this pid, even past a
trace's budget STOP. Each new incarnation (a restart after the arming PATCH)
anchors itself at its own ARMED. Unarmed: no thread, connection or line.

Cost and isolation. One daemon thread per armed pid with its OWN asyncio loop
and ONE dedicated asyncpg connection (server ``statement_timeout`` 150 ms, a
150 ms client bound per statement, a 2 s connect outside any bracket). It never
takes a pool slot or an event-loop turn from a writer, and Celery prefork
children run each task in its own ``asyncio.run`` loop, where a loop-resident
task would die with the task. ``armed`` only updates state under a lock and
may start the thread; a failure anywhere is a fault line or nothing, never an
exception into the write path. About window/5 + 2 round trips per armed pid.
"""

from __future__ import annotations

import asyncio
import functools
import json
import logging
import os
import _thread
import sys
import threading
import time
import uuid
from datetime import timezone

logger = logging.getLogger(__name__)

SCHEMA = "clock_bridge/1"
PERIOD_S = 5.0
PROBE_TIMEOUT_S = 0.150
CONNECT_TIMEOUT_S = 2.0
MAX_WINDOW_S = 600.0  # every trace's own window cap
MAX_LINES = 256  # per run: 600 s / 5 s probes plus ARMED triggers and faults
ROLES = frozenset({"kalshi", "polymarket", "nonvenue", "fold"})
PRODUCER_ROLES = frozenset({"kalshi", "polymarket"})

_PROBE_SQL = "SELECT clock_timestamp()"
_AUTHORITY_SQL = (
    "SELECT protocol, incarnation, namespace, state, clock_timestamp() AS read_clock "
    "FROM dnpl_authority WHERE id = 1"
)


def _dsn(env=os.environ):
    url = env.get("DATABASE_URL", "")
    for prefix in ("postgresql+asyncpg://", "postgres+asyncpg://"):
        if url.startswith(prefix):
            url = "postgresql://" + url[len(prefix):]
    return url


async def _connect(env=os.environ):
    import asyncpg

    dsn = _dsn(env)
    kwargs = {}
    if "localhost" not in dsn and "127.0.0.1" not in dsn:
        kwargs["ssl"] = "require"  # as `build_connect_args`
    return await asyncpg.connect(
        dsn,
        timeout=CONNECT_TIMEOUT_S,
        server_settings={
            "statement_timeout": str(int(PROBE_TIMEOUT_S * 1000)),
            "application_name": "clock_bridge",
        },
        **kwargs,
    )


def _text(value):
    return value if isinstance(value, str) and value else None


def _db_time(value):
    stamp = value.astimezone(timezone.utc)
    return stamp.isoformat(timespec="microseconds"), round(stamp.timestamp(), 6)


class ClockBridge:
    """One per process; `armed` is the only entry point a trace touches."""

    def __init__(self, *, connect=None, wall=time.time, mono=time.monotonic,
                 emit=None, env=os.environ, period_s=PERIOD_S):
        self._connect = connect or functools.partial(_connect, env)
        self.wall, self.mono = wall, mono
        self.emit = emit or (lambda prefix, pid, text: logger.info(
            "%s[pid=%d] %s", prefix, pid, text))
        self.env = env
        self.period_s = period_s
        self._reset()

    def _reset(self):
        self._lock = threading.Lock()
        self._pid = os.getpid()
        self._thread = None
        self._roles = set()
        self._deadline = None
        self._armed_pending = 0
        self._wake = threading.Event()

    def after_fork_in_child(self):
        # A forked child inherits no thread, and a lock held at fork stays held.
        self._reset()

    # ── the hook ─────────────────────────────────────────────────────────────

    def armed(self, role, window_left_s):
        """A trace in this pid just armed. Never raises; never waits on I/O."""
        try:
            if role not in ROLES or type(window_left_s) not in (int, float):
                return
            if not 0 < window_left_s <= MAX_WINDOW_S:
                return
            if self._pid != os.getpid():
                self._reset()
            deadline = self.mono() + window_left_s
            with self._lock:
                self._roles.add(role)
                if self._deadline is None or deadline > self._deadline:
                    self._deadline = deadline
                self._armed_pending += 1
                if self._thread is None:
                    # Nothing here may give up the GIL: beside one GIL-busy
                    # sibling, `uuid4` (os.urandom) cost the writer 7.5 ms and
                    # `Thread.start`'s bootstrap wait 12-30 ms. The run id is
                    # drawn on the bridge thread; a raw helper starts it.
                    thread = threading.Thread(
                        target=self._thread_main, name="clock-bridge", daemon=True,
                    )
                    self._thread = thread
                    _thread.start_new_thread(self._start, (thread,))
                else:
                    self._wake.set()
        except Exception:
            pass  # evidence must never cost a write

    # ── the run (its own thread and loop) ───────────────────────────────────

    def _start(self, thread):
        try:
            thread.start()
        except Exception:
            with self._lock:
                if self._thread is thread:
                    self._thread = None

    def _thread_main(self):
        try:
            asyncio.run(self._run(uuid.uuid4().hex[:8]))
        except Exception:
            pass
        finally:
            with self._lock:
                if self._thread is threading.current_thread():
                    self._thread = None
                    self._roles = set()
                    self._deadline = None
                    self._armed_pending = 0

    def _take(self):
        """``(deadline, roles, armed?)``; ends the run under the same lock
        `armed` takes, so a hook either extends this run or starts the next."""
        with self._lock:
            self._wake.clear()
            if (self._deadline is None or self.mono() >= self._deadline):
                self._thread = None
                self._roles = set()
                self._deadline = None
                self._armed_pending = 0
                return None
            armed, self._armed_pending = self._armed_pending > 0, 0
            return self._deadline, sorted(self._roles), armed

    async def _run(self, run):
        state = dict(run=run, line=0, seq=0, authority=False)
        conn = None
        try:
            while state["line"] <= MAX_LINES - 3:  # a pass writes at most 3 lines
                taken = self._take()
                if taken is None:
                    return
                deadline, roles, armed = taken
                trigger = "ARMED" if armed else "PERIODIC"
                tick = self.mono()
                if conn is None:
                    conn = await self._open(state, roles, trigger)
                if conn is not None:
                    conn = await self._probe(conn, state, roles, trigger, deadline)
                if conn is not None and not state["authority"]:
                    state["authority"] = True
                    conn = await self._authority(conn, state, roles)
                wait = min(tick + self.period_s, deadline) - self.mono()
                if wait > 0:
                    self._wake.wait(wait)  # this thread's own loop: nothing else runs here
        finally:
            if conn is not None:
                await self._close(conn)

    def _line(self, state, prefix, record):
        state["line"] += 1
        pid = os.getpid()
        record = dict(
            schema=SCHEMA, pid=pid, run=state["run"], line=state["line"],
            dyno=_text(self.env.get("DYNO")),
            release=_text(self.env.get("HEROKU_RELEASE_VERSION")),
            slug_commit=_text(self.env.get("HEROKU_SLUG_COMMIT")),
            **record,
        )
        try:
            self.emit(prefix, pid, json.dumps(record, sort_keys=True, default=str))
        except Exception:
            pass

    def _fault(self, state, roles, trigger, stage, error, before):
        wall_after, mono_after = self.wall(), self.mono()
        timeout = isinstance(error, (asyncio.TimeoutError, TimeoutError))
        self._line(state, "clock_bridge_fault", dict(
            seq=state["seq"], trigger=trigger, roles=roles, stage=stage,
            reason="TIMEOUT" if timeout else "ERROR",
            error_class=None if timeout else type(error).__name__,
            wall_before=round(before[0], 6), mono_before=round(before[1], 6),
            wall_after=round(wall_after, 6), mono_after=round(mono_after, 6),
        ))

    async def _open(self, state, roles, trigger):
        before = (self.wall(), self.mono())
        try:
            async with asyncio.timeout(CONNECT_TIMEOUT_S):
                return await self._connect()
        except Exception as error:
            self._fault(state, roles, trigger, "CONNECT", error, before)
            return None

    async def _close(self, conn):
        try:
            async with asyncio.timeout(1.0):
                await conn.close()
        except Exception:
            try:
                conn.terminate()
            except Exception:
                pass

    async def _abandon(self, conn):
        # A cancelled statement leaves the connection's state unknown.
        try:
            conn.terminate()
        except Exception:
            pass
        return None

    async def _probe(self, conn, state, roles, trigger, deadline):
        state["seq"] += 1
        wall_before, mono_before = self.wall(), self.mono()
        try:
            async with asyncio.timeout(PROBE_TIMEOUT_S):
                value = await conn.fetchval(_PROBE_SQL)
            mono_after, wall_after = self.mono(), self.wall()
            db_clock, db_epoch = _db_time(value)
        except Exception as error:
            self._fault(state, roles, trigger, "PROBE", error, (wall_before, mono_before))
            return await self._abandon(conn)
        mono_before, mono_after = round(mono_before, 6), round(mono_after, 6)
        self._line(state, "clock_bridge", dict(
            seq=state["seq"], trigger=trigger, roles=roles,
            wall_before=round(wall_before, 6), mono_before=mono_before,
            db_clock=db_clock, db_clock_epoch=db_epoch,
            wall_after=round(wall_after, 6), mono_after=mono_after,
            rtt_ms=round((mono_after - mono_before) * 1000, 3),  # of the printed values
            window_left_s=round(deadline - mono_after, 3),
        ))
        return conn

    async def _authority(self, conn, state, roles):
        record = dict(roles=roles, **registry_state())
        wall_before, mono_before = self.wall(), self.mono()
        row = None
        try:
            async with asyncio.timeout(PROBE_TIMEOUT_S):
                row = await conn.fetchrow(_AUTHORITY_SQL)
            record["db_read"] = "OK" if row is not None else "MISSING"
        except Exception as error:
            self._fault(state, roles, "ARMED", "AUTHORITY", error, (wall_before, mono_before))
            timeout = isinstance(error, (asyncio.TimeoutError, TimeoutError))
            record["db_read"] = "TIMEOUT" if timeout else "ERROR"
            conn = await self._abandon(conn)
        record.update(db_read_mono_before=round(mono_before, 6),
                      db_read_mono_after=round(self.mono(), 6))
        record.update(db_row_fields(row))
        record.update(activation(roles, record))
        self._line(state, "clock_bridge_authority", record)
        return conn


# ── part 2: what this pid holds, read from memory only ──────────────────────

def registry_state():
    """This pid's producer DNPL registry as held; never constructs one."""
    empty = dict(registry_incarnation=None, registry_namespace=None,
                 registry_state=None, registry_halted=None, registry_claims=None)
    module = sys.modules.get("app.utils.blend_preview")
    registry = getattr(module, "_REGISTRY", None) if module is not None else None
    if registry is None:
        return dict(registry="NONE_IN_PROCESS", **empty)
    try:
        claims = {str(k): int(v) for k, v in dict(getattr(registry, "claims", {})).items()}
    except Exception:
        claims = None
    halted = getattr(registry, "_halted", None)
    authority = getattr(registry, "_authority", None)
    if authority is None:
        return dict(empty, registry="UNBOUND", registry_halted=halted,
                    registry_claims=claims)
    return dict(
        registry="BOUND",
        registry_incarnation=str(authority.incarnation),
        registry_namespace=str(authority.namespace).lower(),
        registry_state=authority.state,
        registry_halted=halted,
        registry_claims=claims,
    )


def db_row_fields(row):
    if row is None:
        return dict(db_incarnation=None, db_namespace=None, db_state=None,
                    db_protocol=None, db_read_clock=None)
    return dict(
        db_incarnation=str(row["incarnation"]),
        db_namespace=str(row["namespace"]).lower(),
        db_state=row["state"],
        db_protocol=row["protocol"],
        db_read_clock=_db_time(row["read_clock"])[0],
    )


def _wire(incarnation, namespace, state):
    if state != "ready" or incarnation in (None, "0"):
        return None
    return {"protocol": 3, "authority": {"incarnation": incarnation, "namespace": namespace}}


def activation(roles, record):
    """``preview_activation`` and ``dnpl_on`` with the rule that decided each."""
    bound = record["registry"] == "BOUND"
    if bound:
        wire = _wire(record["registry_incarnation"], record["registry_namespace"],
                     record["registry_state"])
        source = "REGISTRY"
    else:
        wire = _wire(record["db_incarnation"], record["db_namespace"], record["db_state"])
        source = "DB_ROW"
    if PRODUCER_ROLES.intersection(roles):
        if not bound:
            basis = ("NO_REGISTRY" if record["registry"] == "NONE_IN_PROCESS"
                     else "REGISTRY_UNBOUND")
        elif wire is None:
            basis = "REGISTRY_NOT_READY"
        elif record["registry_halted"]:
            basis = "REGISTRY_HALTED"
        elif not record["registry_claims"]:
            basis = "REGISTRY_UNCLAIMED"
        else:
            basis = "REGISTRY_READY_UNHALTED_CLAIMED"
        on = basis == "REGISTRY_READY_UNHALTED_CLAIMED"
    elif "fold" in roles:
        if record["db_read"] != "OK":
            basis = "DB_ROW_UNREAD"
        else:
            basis = ("DB_ROW_READY_ALL_ROUTE_EVENTS" if wire is not None
                     else "DB_ROW_NOT_READY")
        on = basis == "DB_ROW_READY_ALL_ROUTE_EVENTS"
    else:
        basis, on = "NOT_A_DNPL_PRODUCER", False
    return dict(
        preview_activation=wire,
        preview_activation_source=source if wire is not None else None,
        dnpl_on=on,
        dnpl_on_basis=basis,
    )


_BRIDGE = ClockBridge()
if hasattr(os, "register_at_fork"):
    os.register_at_fork(after_in_child=lambda: _BRIDGE.after_fork_in_child())


def attach(trace, role):
    """Wire a production trace's ARMED hook to this pid's bridge. Never raises.

    A trace with no pending ``arm_mono`` is collecting from START (no
    ``*_ARM_AT``), so START is its ARMED and the bridge starts now.
    """
    try:
        if trace is None or role not in ROLES:
            return
        bridge = _BRIDGE
        trace.on_armed = functools.partial(bridge.armed, role)
        if getattr(trace, "arm_mono", None) is None and not trace.stopped:
            bridge.armed(role, trace.deadline - trace.mono())
    except Exception:
        pass
