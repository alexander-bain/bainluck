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

Markers (amendment P2, the 20261030T0615Z causal contract). DARK unless BOTH a
trace in this pid is armed AND ``CLOCK_MARKER_CASE`` names an admitted case with
``CLOCK_MARKER_EXPIRES_AT`` in the next two hours, so a later ordinary arming of
P never carries marker traffic. Then, after the run's first probe on a
connection, the bridge LISTENs on ONE channel addressed to this incarnation
(``cm_<case>_<tok>``, ``tok`` hashed from case, dyno, pid, boot id and run) and
announces it once (``bind``) on the case's reply channel ``cmr_<case>``. Each
valid request ``{v, case, tok, run, slot, nonce}`` is answered on the same
connection, between P's own statements, with ``lo`` (this pid's
``time.monotonic`` when its callback ran, after receipt) and ``hi`` (read just
before the reply is sent): every stamp of this pid below ``lo`` came before
the request was received, and every stamp above ``hi`` after the reply left.
No marker line goes to the log and no marker spends P's ``MAX_LINES``. Caps,
counters and the pinned schema: ``MARKER_*`` below and
``tests/fixtures/clock_marker_10090_schema.json``. Dark, the run makes exactly
P's calls, including its thread-blocking wait.
"""

from __future__ import annotations

import asyncio
import functools
import hashlib
import json
import logging
import os
import re
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

MARKER_SCHEMA = "clock_marker/1"
MARKER_POLL_S = 0.050  # how late an ARMED wake can be seen while markers listen
MARKER_ARM_MAX_S = 7200.0  # CLOCK_MARKER_EXPIRES_AT may sit no further out
MARKER_MAX = 760  # accepted markers (= slots) per run; P's MAX_LINES is untouched
MARKER_MAX_RECEIVED = 1520  # notifications a run looks at, valid or not
MARKER_QUEUE = 4  # requests waiting behind one of P's statements
MARKER_REQUEST_MAX_B = 256
MARKER_REPLY_MAX_B = 512
MARKER_PAYLOAD_MAX_B = 583_680  # received + sent payload bytes per run (760 x 768)
MARKER_WIRE_MAX_B = 2 * 1024 * 1024  # payload plus ESTIMATED protocol framing
MARKER_FRAME_IN_B = 64  # NotificationResponse header + TLS record, estimated
MARKER_FRAME_OUT_B = 192  # Bind/Execute/Sync + replies + TLS records, estimated
MARKER_FAULTS = ("big", "bad", "foreign", "dup", "ord", "q", "drop")
_MARKER_CASE = re.compile(r"[a-z0-9]{8,24}")
_MARKER_NONCE = re.compile(r"[0-9a-f]{32}")
_MARKER_REQUEST_KEYS = frozenset({"v", "case", "tok", "run", "slot", "nonce"})

_PROBE_SQL = "SELECT clock_timestamp()"
_NOTIFY_SQL = "SELECT pg_notify($1, $2)"
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
        markers = self._markers(run)  # None: dark, and every call below is P's
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
                if markers is not None and conn is not None:
                    conn = await markers.listen(conn)
                wait = min(tick + self.period_s, deadline) - self.mono()
                if wait > 0:
                    if markers is None or not markers.listening(conn):
                        self._wake.wait(wait)  # this thread's own loop: nothing else runs here
                    else:
                        conn = await markers.wait(conn, self.mono() + wait)
        finally:
            if markers is not None and conn is not None:
                conn = await markers.stop(conn, "RUN_END")
            if conn is not None:
                await self._close(conn)

    def _markers(self, run):
        """This run's marker state, or None (dark) unless a case is admitted."""
        try:
            case = self.env.get("CLOCK_MARKER_CASE")
            raw = self.env.get("CLOCK_MARKER_EXPIRES_AT")
            if not (isinstance(case, str) and _MARKER_CASE.fullmatch(case) and raw):
                return None  # without both, not even a clock read
            expires = float(raw)
            if not self.wall() < expires <= self.wall() + MARKER_ARM_MAX_S:
                return None
            return _Markers(self, case, expires, run)
        except Exception:
            return None

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


def _boot_id():
    try:
        with open("/proc/sys/kernel/random/boot_id") as handle:
            return handle.read(64).strip() or None
    except Exception:
        return None


def _compact(record):
    return json.dumps(record, separators=(",", ":"), sort_keys=True)


class _Markers:
    """One run's request-caused markers, all on the bridge's own loop.

    The notification callback only stamps, validates and queues (no await, no
    task). Replies go out from the run's coroutine, so they are serialized with
    P's statements on the one connection; a probe in flight makes a reply
    later, never a probe later. Any reply/LISTEN failure halts markers for the
    run and abandons the connection exactly as a P fault does; P reconnects on
    its next tick and markers stay halted.
    """

    def __init__(self, bridge, case, expires, run):
        self.bridge, self.case, self.expires, self.run = bridge, case, expires, run
        env = bridge.env
        self.pid, self.boot = os.getpid(), _boot_id()
        self.dyno = _text(env.get("DYNO"))
        self.tok = hashlib.sha256(
            f"{case}|{self.dyno}|{self.pid}|{self.boot}|{run}".encode()).hexdigest()[:16]
        self.channel = f"cm_{case}_{self.tok}"
        self.reply_channel = f"cmr_{case}"
        self.bind_fields = dict(
            dyno=self.dyno, rel=_text(env.get("HEROKU_RELEASE_VERSION")),
            commit=_text(env.get("HEROKU_SLUG_COMMIT")), boot=self.boot,
        )
        self.conn = None  # the connection currently LISTENing
        self.listens = self.received = self.accepted = 0
        self.payload_b = self.wire_b = 0
        self.last_slot = -1
        self.slots, self.nonces, self.pending = set(), set(), []
        self.faults = dict.fromkeys(MARKER_FAULTS, 0)
        self.halted = None  # the reason markers stopped, once they have
        self.event = asyncio.Event()

    # ── the callback: asyncpg calls it with call_soon on this loop ──────────

    def on_notify(self, _conn, _server_pid, channel, payload):
        lo = self.bridge.mono()
        try:
            self.received += 1
            if self.halted:
                return
            if self.received > MARKER_MAX_RECEIVED:
                return self.halt("RECEIVED_CAP")
            size = len(payload.encode("utf-8", "replace")) if isinstance(payload, str) else 0
            if not self.spend(size, MARKER_FRAME_IN_B + len(channel)):
                return
            if not 0 < size <= MARKER_REQUEST_MAX_B:
                self.faults["big"] += 1
                return
            slot, nonce = self.parse(payload)
            if slot is None:
                return
            if slot in self.slots or nonce in self.nonces:
                self.faults["dup"] += 1
            elif slot <= self.last_slot:
                self.faults["ord"] += 1
            elif len(self.pending) >= MARKER_QUEUE:
                self.faults["q"] += 1
            else:
                self.slots.add(slot)
                self.nonces.add(nonce)
                self.last_slot = slot
                self.pending.append((lo, self.received, slot, nonce))
                self.event.set()
        except Exception:
            self.faults["bad"] += 1

    def parse(self, payload):
        try:
            request = json.loads(payload)
        except ValueError:
            request = None
        if (not isinstance(request, dict) or request.keys() != _MARKER_REQUEST_KEYS
                or type(request["v"]) is not int or request["v"] != 1
                or type(request["slot"]) is not int or not 0 <= request["slot"] < MARKER_MAX
                or not isinstance(request["nonce"], str)
                or not _MARKER_NONCE.fullmatch(request["nonce"])):
            self.faults["bad"] += 1
            return None, None
        if (request["case"], request["tok"], request["run"]) != (self.case, self.tok, self.run):
            self.faults["foreign"] += 1
            return None, None
        return request["slot"], request["nonce"]

    def spend(self, payload_b, frame_b):
        self.payload_b += payload_b
        self.wire_b += payload_b + frame_b
        if self.payload_b > MARKER_PAYLOAD_MAX_B or self.wire_b > MARKER_WIRE_MAX_B:
            self.halt("BYTE_CAP")
            return False
        return True

    def halt(self, reason):
        if self.halted is None:
            self.halted = reason
            self.event.set()

    # ── the run's side: LISTEN, wait, reply, stop ───────────────────────────

    def listening(self, conn):
        return conn is not None and conn is self.conn and self.halted is None

    def message(self, kind, **fields):
        return _compact(dict(v=1, k=kind, case=self.case, tok=self.tok, run=self.run,
                             pid=self.pid, **fields))

    async def notify(self, conn, payload):
        """One reply on the shared connection; False means the conn is gone."""
        size = len(payload.encode())
        if size > MARKER_REPLY_MAX_B:
            self.halt("REPLY_TOO_BIG")
            return True
        if not self.spend(size, MARKER_FRAME_OUT_B + len(self.reply_channel)):
            return True
        try:
            async with asyncio.timeout(PROBE_TIMEOUT_S):
                await conn.execute(_NOTIFY_SQL, self.reply_channel, payload)
            return True
        except Exception:
            self.halt("REPLY_FAILED")
            return False

    async def listen(self, conn):
        if self.halted is not None or conn is self.conn:
            return conn
        if self.bridge.wall() >= self.expires:
            self.halt("EXPIRED")
            return conn
        self.conn = None
        try:
            async with asyncio.timeout(PROBE_TIMEOUT_S):
                await conn.add_listener(self.channel, self.on_notify)
        except Exception:
            self.halt("LISTEN_FAILED")
            return await self.bridge._abandon(conn)
        self.conn, self.listens = conn, self.listens + 1
        bind = self.message("bind", ch=self.channel, listen=self.listens,
                            clock="time.monotonic", mono=round(self.bridge.mono(), 6),
                            exp=self.expires, slots=MARKER_MAX, **self.bind_fields)
        if not await self.notify(conn, bind):
            self.conn = None
            return await self.bridge._abandon(conn)
        return conn

    async def wait(self, conn, until):
        """P's wait while listening: serve replies, see an ARMED wake in <=50 ms."""
        while True:
            if self.listening(conn) and self.pending:
                conn = await self.serve(conn)
            if self.halted is None and self.bridge.wall() >= self.expires:
                self.halt("EXPIRED")
            if self.halted is not None:
                if conn is not None and conn is self.conn:
                    conn = await self.stop(conn, self.halted)
                left = until - self.bridge.mono()
                if left > 0 and not self.bridge._wake.is_set():
                    self.bridge._wake.wait(left)  # back to P's own wait
                return conn
            left = until - self.bridge.mono()
            if left <= 0 or self.bridge._wake.is_set():
                return conn
            self.event.clear()
            try:
                async with asyncio.timeout(min(MARKER_POLL_S, left)):
                    await self.event.wait()
            except TimeoutError:
                pass

    async def serve(self, conn):
        while self.pending and self.halted is None:
            lo, rx, slot, nonce = self.pending.pop(0)
            if self.accepted >= MARKER_MAX:
                self.faults["drop"] += 1
                self.halt("MARKER_CAP")
                break
            self.accepted += 1
            hi = self.bridge.mono()
            reply = self.message("m", slot=slot, nonce=nonce, i=self.accepted, rx=rx,
                                 lo=round(lo, 6), hi=round(hi, 6), q=1e-06,
                                 f=dict(self.faults))
            if not await self.notify(conn, reply):
                self.conn = None
                return await self.bridge._abandon(conn)
        return conn

    async def stop(self, conn, reason):
        """Say why markers ended (bounded) and stop LISTENing; never retried."""
        if conn is None or conn is not self.conn:
            return conn
        self.faults["drop"] += len(self.pending)
        self.pending.clear()
        self.halt(reason)
        self.conn = None
        end = self.message("end", why=reason, i=self.accepted, rx=self.received,
                           f=dict(self.faults), pb=self.payload_b, wb=self.wire_b)
        if reason in ("BYTE_CAP", "REPLY_TOO_BIG", "REPLY_FAILED"):
            end = None
        if end is not None and not await self.notify(conn, end):
            return await self.bridge._abandon(conn)
        if reason == "RUN_END":
            return conn  # the close that follows ends the LISTEN
        try:
            async with asyncio.timeout(PROBE_TIMEOUT_S):
                await conn.remove_listener(self.channel, self.on_notify)
        except Exception:
            return await self.bridge._abandon(conn)
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
