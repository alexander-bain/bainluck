"""#10090 amendment P: an armed process bridges its monotonic clock to the DB's.

The A6 display score bounds every producer's times on the database clock. The
bridge writes ``clock_bridge[pid=N]`` probes (wall+mono before, the DB's
``clock_timestamp()``, wall+mono after) from a trace's ARMED until its expiry,
plus one ``clock_bridge_authority`` line. These tests pin: nothing at all when
unarmed; a hung or failing database never reaches the caller (the write path
only ever calls `armed`); every producer's trace calls the hook at ARMED, or at
START when it has no ARM_AT; and the lines parse as the measurement note says.
"""

import asyncio
import inspect
import json
import re
import threading
import time
import uuid
from datetime import datetime, timezone
from types import SimpleNamespace

import pytest

from app.utils import blend_preview
from app.utils import clock_bridge as cb
from app.utils import fold_base_trace as fbt
from app.utils import nonvenue_trace as nvt
from app.utils.kalshi_exact_trace import ExactKalshiTrace
from app.utils.pm_stage_trace import PMStageTrace

# The adapter's parse, verbatim from the 20261029T1318Z measurement note.
LINE = re.compile(r"(clock_bridge|clock_bridge_fault|clock_bridge_authority)\[pid=(\d+)\] (\{.*\})$")
NAMESPACE = uuid.UUID("0f0e0d0c-0b0a-4908-8706-050403020100")


class FakeConn:
    def __init__(self, delay=0.0, row=None, error=None):
        self.delay, self.row, self.error = delay, row, error
        self.statements, self.closed, self.terminated = [], False, False

    async def fetchval(self, sql):
        self.statements.append(sql)
        if self.error:
            raise self.error
        if self.delay:
            await asyncio.sleep(self.delay)
        return datetime.now(timezone.utc)

    async def fetchrow(self, sql):
        self.statements.append(sql)
        return self.row

    async def close(self):
        self.closed = True

    def terminate(self):
        self.terminated = True


def make_bridge(conns, period_s=0.05, env=None):
    """A bridge on fake connections; returns (bridge, lines, connects)."""
    lines, connects = [], []
    pool = list(conns)

    async def connect():
        conn = pool.pop(0) if len(pool) > 1 else pool[0]
        connects.append(conn)
        if isinstance(conn, Exception):
            raise conn
        if callable(conn):
            return await conn()
        return conn

    bridge = cb.ClockBridge(
        connect=connect, period_s=period_s, env=env or {"DYNO": "worker-ws.1"},
        emit=lambda prefix, pid, text: lines.append(f"{prefix}[pid={pid}] {text}"),
    )
    return bridge, lines, connects


def finish(bridge, timeout=5.0):
    thread = bridge._thread
    if thread is not None:
        thread._started.wait(timeout)  # started by a raw helper, not the hook
        thread.join(timeout)
        assert not thread.is_alive()


def parsed(lines):
    out = []
    for text in lines:
        match = LINE.search(text)
        assert match, text
        record = json.loads(match.group(3))
        assert record["pid"] == int(match.group(2))
        out.append((match.group(1), record))
    return out


# ── unarmed: nothing ────────────────────────────────────────────────────────

def test_an_unarmed_process_starts_no_thread_connection_or_line(monkeypatch):
    bridge, lines, connects = make_bridge([FakeConn()])
    monkeypatch.setattr(cb, "_BRIDGE", bridge)
    for key in ("NONVENUE_TRACE_EVENTS", "FOLD_TRACE_EVENTS"):
        monkeypatch.delenv(key, raising=False)
    monkeypatch.setattr(nvt, "_TRACE", nvt._UNSET)
    monkeypatch.setattr(fbt, "_TRACE", fbt._UNSET)
    assert nvt.nonvenue_trace() is None
    assert fbt.fold_base_trace() is None
    cb.attach(None, "kalshi")
    cb.attach(None, "polymarket")
    # A trace that was never attached (tests, one-offs) never reaches the bridge.
    now = time.time()
    trace = nvt.NonvenueTrace.from_env(
        {"NONVENUE_TRACE_EVENTS": "1", "NONVENUE_TRACE_EXPIRES_AT": str(now + 60)},
        emit=lambda text: None)
    assert trace is not None and trace.on_armed is None and trace.active()
    assert (bridge._thread, lines, connects) == (None, [], [])


def test_armed_refuses_a_window_no_trace_can_have():
    bridge, lines, connects = make_bridge([FakeConn()])
    for role, window in (("kalshi", 0), ("kalshi", -1), ("kalshi", 601), ("kalshi", "60"),
                         ("unknown", 60)):
        bridge.armed(role, window)
    assert (bridge._thread, lines, connects) == (None, [], [])


# ── armed: the probes ───────────────────────────────────────────────────────

def test_armed_probes_at_once_then_on_the_cadence_until_the_deadline():
    row = {"protocol": 3, "incarnation": 0, "namespace": uuid.UUID(int=0),
           "state": "disabled", "read_clock": datetime.now(timezone.utc)}
    conn = FakeConn(row=row)
    bridge, lines, connects = make_bridge([conn])
    began = time.monotonic()
    bridge.armed("kalshi", 0.22)
    finish(bridge)
    records = parsed(lines)
    probes = [r for kind, r in records if kind == "clock_bridge"]
    assert [kind for kind, _ in records][:2] == ["clock_bridge", "clock_bridge_authority"]
    assert len(connects) == 1 and conn.closed
    assert 4 <= len(probes) <= 6  # 0.22 s at 0.05 s
    assert [p["seq"] for p in probes] == list(range(1, len(probes) + 1))
    assert [p["trigger"] for p in probes] == ["ARMED"] + ["PERIODIC"] * (len(probes) - 1)
    assert [r["line"] for _, r in records] == list(range(1, len(records) + 1))
    assert len({r["run"] for _, r in records}) == 1
    first = probes[0]
    assert first["mono_before"] - began < 0.05  # the anchor is AT arming
    for p in probes:
        assert p["schema"] == "clock_bridge/1" and p["roles"] == ["kalshi"]
        assert p["mono_before"] <= p["mono_after"] and p["wall_before"] <= p["wall_after"]
        assert re.fullmatch(r"\d{4}-\d\d-\d\dT\d\d:\d\d:\d\d\.\d{6}\+00:00", p["db_clock"])
        assert abs(datetime.fromisoformat(p["db_clock"]).timestamp() - p["db_clock_epoch"]) < 1e-6
        assert p["rtt_ms"] == round((p["mono_after"] - p["mono_before"]) * 1000, 3)
        assert p["dyno"] == "worker-ws.1" and p["release"] is None
    assert probes[-1]["mono_before"] - began < 0.22 + 0.05
    assert conn.statements.count(cb._PROBE_SQL) == len(probes)
    assert conn.statements.count(cb._AUTHORITY_SQL) == 1


def test_a_second_trace_arming_extends_the_run_and_probes_at_once():
    bridge, lines, _ = make_bridge([FakeConn()], period_s=10.0)
    bridge.armed("fold", 0.3)
    time.sleep(0.1)
    bridge.armed("nonvenue", 0.3)  # wakes the 10 s wait
    finish(bridge)
    probes = [r for kind, r in parsed(lines) if kind == "clock_bridge"]
    assert [(p["trigger"], p["roles"]) for p in probes] == [
        ("ARMED", ["fold"]), ("ARMED", ["fold", "nonvenue"])]
    # And a later ARMED after the run ended starts a NEW run.
    bridge.armed("fold", 0.05)
    finish(bridge)
    runs = [r["run"] for kind, r in parsed(lines) if kind == "clock_bridge"]
    assert len(set(runs)) == 2


# ── faults never reach the write path ───────────────────────────────────────

@pytest.mark.asyncio
async def test_a_hung_probe_is_a_150ms_fault_and_never_delays_a_stamp(monkeypatch):
    hung = FakeConn(delay=5.0)
    healthy = FakeConn()
    bridge, lines, connects = make_bridge([hung, healthy], period_s=0.3)

    stamps = []

    async def stamp():  # stands in for a writer on the caller's own loop
        for _ in range(20):
            started = time.monotonic()
            await asyncio.sleep(0.01)
            stamps.append(time.monotonic() - started)

    started = time.monotonic()
    bridge.armed("polymarket", 0.5)
    called = time.monotonic() - started
    await stamp()
    await asyncio.to_thread(finish, bridge)
    assert called < 0.02  # the hook updates state and returns
    assert max(stamps) < 0.1
    records = parsed(lines)
    (kind, fault), *rest = records
    assert kind == "clock_bridge_fault"
    assert (fault["stage"], fault["reason"], fault["error_class"], fault["seq"]) == (
        "PROBE", "TIMEOUT", None, 1)
    assert fault["mono_after"] - fault["mono_before"] < cb.PROBE_TIMEOUT_S + 0.1
    assert hung.terminated  # a cancelled statement's connection is abandoned
    # The next tick reconnects and the bracket resumes on the cadence.
    assert connects[:2] == [hung, healthy]
    assert [k for k, _ in rest][:2] == ["clock_bridge", "clock_bridge_authority"]
    assert rest[0][1]["seq"] == 2 and rest[0][1]["trigger"] == "PERIODIC"


def test_connect_and_statement_errors_are_fault_lines(monkeypatch):
    monkeypatch.setattr(cb, "CONNECT_TIMEOUT_S", 0.05)

    async def never():
        await asyncio.sleep(5)

    bridge, lines, _ = make_bridge([never, OSError("refused"),
                                    FakeConn(error=RuntimeError("boom"))], period_s=0.05)
    bridge.armed("nonvenue", 0.3)
    finish(bridge)
    faults = [(r["stage"], r["reason"], r["error_class"]) for k, r in parsed(lines)
              if k == "clock_bridge_fault"]
    assert faults[:3] == [("CONNECT", "TIMEOUT", None), ("CONNECT", "ERROR", "OSError"),
                          ("PROBE", "ERROR", "RuntimeError")]
    assert not [k for k, _ in parsed(lines) if k != "clock_bridge_fault"]


def test_an_emit_failure_or_thread_failure_never_raises_into_the_hook(monkeypatch):
    bridge, _, _ = make_bridge([FakeConn()])
    bridge.emit = lambda *a: (_ for _ in ()).throw(RuntimeError("log down"))
    bridge.armed("kalshi", 0.06)
    finish(bridge)

    def broken(*a, **k):
        raise RuntimeError("no threads")

    monkeypatch.setattr(cb.threading, "Thread", broken)
    bridge.armed("kalshi", 0.06)  # must not raise


# ── each producer calls the hook at ARMED ───────────────────────────────────

class Recorder:
    def __init__(self):
        self.calls = []

    def armed(self, role, window_left_s):
        self.calls.append((role, round(window_left_s, 3)))


def clocks(wall0=1_000_000.0, mono0=500.0):
    t = [0.0]
    return t, (lambda: wall0 + t[0]), (lambda: mono0 + t[0])


@pytest.mark.parametrize("cls,prefix,role", [
    (nvt.NonvenueTrace, "NONVENUE_TRACE", "nonvenue"),
    (fbt.FoldBaseTrace, "FOLD_TRACE", "fold"),
])
def test_bounded_traces_call_the_hook_at_armed_once(monkeypatch, cls, prefix, role):
    recorder = Recorder()
    monkeypatch.setattr(cb, "_BRIDGE", recorder)
    t, wall, mono = clocks()
    env = {f"{prefix}_EVENTS": "7", f"{prefix}_ARM_AT": str(wall() + 100),
           f"{prefix}_EXPIRES_AT": str(wall() + 400)}
    trace = cls.from_env(env, wall=wall, mono=mono, emit=lambda text: None)
    cb.attach(trace, role)
    assert recorder.calls == []  # waiting for ARM_AT
    t[0] = 99.0
    assert not trace.active() and recorder.calls == []
    t[0] = 101.0
    assert trace.active()
    assert trace.active()
    assert recorder.calls == [(role, 299.0)]
    # Without ARM_AT the START is the ARMED instant.
    env.pop(f"{prefix}_ARM_AT")
    env[f"{prefix}_EXPIRES_AT"] = str(wall() + 200)
    cb.attach(cls.from_env(env, wall=wall, mono=mono, emit=lambda text: None), role)
    assert recorder.calls[-1] == (role, 200.0)


def test_kalshi_trace_has_no_arm_at_so_start_anchors_it(monkeypatch):
    recorder = Recorder()
    monkeypatch.setattr(cb, "_BRIDGE", recorder)
    _, wall, mono = clocks()
    trace = ExactKalshiTrace.from_env(
        {"WS_KALSHI_TRACE_TICKERS": "KXNFLGAME-26OCT29-BUF",
         "WS_KALSHI_TRACE_EXPIRES_AT": str(wall() + 300)},
        run="r", wall=wall, mono=mono, emit=lambda record: None)
    cb.attach(trace, "kalshi")
    assert recorder.calls == [("kalshi", 300.0)]


def test_pm_trace_calls_the_hook_at_its_armed_and_not_when_nothing_mapped(monkeypatch):
    recorder = Recorder()
    monkeypatch.setattr(cb, "_BRIDGE", recorder)
    t, wall, mono = clocks()
    env = {"WS_PM_TRACE_EVENT": "1", "WS_PM_TRACE_OUTCOMES": "11",
           "WS_PM_TRACE_ARM_AT": str(wall() + 60), "WS_PM_TRACE_EXPIRES_AT": str(wall() + 360)}
    trace = PMStageTrace.from_env(env, run="r", event_of={11: 1}, wall=wall, mono=mono,
                                  emit=lambda record: None)
    cb.attach(trace, "polymarket")
    assert recorder.calls == []
    t[0] = 61.0
    assert trace.active()
    assert recorder.calls == [("polymarket", 299.0)]
    # Armed with no mapped outcome: the trace STOPs and nothing is bridged.
    t[0] = 0.0
    lost = PMStageTrace.from_env(env, run="r", event_of={11: 2}, wall=wall, mono=mono,
                                 emit=lambda record: None)
    cb.attach(lost, "polymarket")
    t[0] = 61.0
    lost.active()
    assert recorder.calls == [("polymarket", 299.0)]


def test_a_failing_hook_never_costs_the_trace(monkeypatch):
    t, wall, mono = clocks()
    trace = nvt.NonvenueTrace.from_env(
        {"NONVENUE_TRACE_EVENTS": "7", "NONVENUE_TRACE_ARM_AT": str(wall() + 1),
         "NONVENUE_TRACE_EXPIRES_AT": str(wall() + 100)},
        wall=wall, mono=mono, emit=lambda text: None)
    trace.on_armed = lambda window: 1 / 0
    t[0] = 2.0
    assert trace.active()


def test_every_production_factory_attaches_its_role(monkeypatch):
    seen = []
    monkeypatch.setattr(cb, "attach", lambda trace, role: seen.append(role))
    now = time.time()
    monkeypatch.setenv("NONVENUE_TRACE_EVENTS", "7")
    monkeypatch.setenv("NONVENUE_TRACE_EXPIRES_AT", str(now + 60))
    monkeypatch.setenv("FOLD_TRACE_EVENTS", "7")
    monkeypatch.setenv("FOLD_TRACE_EXPIRES_AT", str(now + 60))
    monkeypatch.setattr(nvt, "_TRACE", nvt._UNSET)
    monkeypatch.setattr(fbt, "_TRACE", fbt._UNSET)
    assert nvt.nonvenue_trace() is not None and fbt.fold_base_trace() is not None
    assert seen == ["nonvenue", "fold"]
    # The two WS factories sit inside their long run functions: pin the call
    # right after each trace is built.
    from app.tasks import kalshi_ws, polymarket_ws

    k = inspect.getsource(kalshi_ws)
    built = k.index("ExactKalshiTrace.from_env(os.environ, run=None)")
    assert k.index('attach(exact_trace, "kalshi")', built) - built < 300
    p = inspect.getsource(polymarket_ws)
    built = p.index("tail_receipts.exact_trace = PMStageTrace.from_env(")
    assert p.index('attach(tail_receipts.exact_trace, "polymarket")', built) - built < 400


# ── part 2: authority / DNPL as this pid holds it ───────────────────────────

def authority(state="ready", incarnation=12):
    return SimpleNamespace(incarnation=incarnation, namespace=NAMESPACE, state=state)


def test_a_producer_reports_its_bound_registry_and_dnpl_on(monkeypatch):
    registry = SimpleNamespace(_authority=authority(), _halted=False, claims={"polymarket": 41})
    monkeypatch.setattr(blend_preview, "_REGISTRY", registry)
    row = {"protocol": 3, "incarnation": 12, "namespace": NAMESPACE, "state": "ready",
           "read_clock": datetime(2026, 10, 30, 1, 0, 0, 123456, tzinfo=timezone.utc)}
    bridge, lines, _ = make_bridge([FakeConn(row=row)])
    bridge.armed("polymarket", 0.03)
    finish(bridge)
    (record,) = [r for k, r in parsed(lines) if k == "clock_bridge_authority"]
    assert {k: record[k] for k in (
        "registry", "registry_incarnation", "registry_namespace", "registry_state",
        "registry_halted", "registry_claims", "db_read", "db_incarnation", "db_namespace",
        "db_state", "db_protocol", "db_read_clock", "preview_activation",
        "preview_activation_source", "dnpl_on", "dnpl_on_basis", "roles")} == {
        "registry": "BOUND", "registry_incarnation": "12",
        "registry_namespace": str(NAMESPACE), "registry_state": "ready",
        "registry_halted": False, "registry_claims": {"polymarket": 41},
        "db_read": "OK", "db_incarnation": "12", "db_namespace": str(NAMESPACE),
        "db_state": "ready", "db_protocol": 3,
        "db_read_clock": "2026-10-30T01:00:00.123456+00:00",
        "preview_activation": {"protocol": 3, "authority": {
            "incarnation": "12", "namespace": str(NAMESPACE)}},
        "preview_activation_source": "REGISTRY",
        "dnpl_on": True, "dnpl_on_basis": "REGISTRY_READY_UNHALTED_CLAIMED",
        "roles": ["polymarket"],
    }
    assert record["db_read_mono_before"] <= record["db_read_mono_after"]


@pytest.mark.parametrize("registry,roles,row_state,expected", [
    (None, ["fold"], "ready", (True, "DB_ROW_READY_ALL_ROUTE_EVENTS", "DB_ROW")),
    (None, ["fold"], "disabled", (False, "DB_ROW_NOT_READY", None)),
    (None, ["fold"], None, (False, "DB_ROW_UNREAD", None)),
    (None, ["kalshi"], "ready", (False, "NO_REGISTRY", "DB_ROW")),
    ("unbound", ["kalshi"], "ready", (False, "REGISTRY_UNBOUND", "DB_ROW")),
    ("halted", ["kalshi"], "ready", (False, "REGISTRY_HALTED", "REGISTRY")),
    ("unclaimed", ["kalshi"], "ready", (False, "REGISTRY_UNCLAIMED", "REGISTRY")),
    ("preparing", ["kalshi"], "ready", (False, "REGISTRY_NOT_READY", None)),
    (None, ["nonvenue"], "ready", (False, "NOT_A_DNPL_PRODUCER", "DB_ROW")),
])
def test_dnpl_on_names_the_rule_that_decided_it(monkeypatch, registry, roles, row_state, expected):
    registries = {
        None: None,
        "unbound": SimpleNamespace(_authority=None, _halted=False, claims={}),
        "halted": SimpleNamespace(_authority=authority(), _halted=True, claims={"kalshi": 1}),
        "unclaimed": SimpleNamespace(_authority=authority(), _halted=False, claims={}),
        "preparing": SimpleNamespace(_authority=authority("preparing"), _halted=False,
                                     claims={"kalshi": 1}),
    }
    monkeypatch.setattr(blend_preview, "_REGISTRY", registries[registry])
    record = dict(cb.registry_state())
    if row_state is None:
        record.update(db_read="TIMEOUT", **cb.db_row_fields(None))
    else:
        record.update(db_read="OK", **cb.db_row_fields({
            "protocol": 3, "incarnation": 12, "namespace": NAMESPACE, "state": row_state,
            "read_clock": datetime.now(timezone.utc)}))
    got = cb.activation(roles, record)
    assert (got["dnpl_on"], got["dnpl_on_basis"], got["preview_activation_source"]) == expected


def test_the_bridge_never_builds_a_registry(monkeypatch):
    monkeypatch.setattr(blend_preview, "_REGISTRY", None)
    assert cb.registry_state()["registry"] == "NONE_IN_PROCESS"
    assert blend_preview._REGISTRY is None


def test_the_dsn_drops_the_sqlalchemy_driver_suffix():
    assert cb._dsn({"DATABASE_URL": "postgresql+asyncpg://u:p@h:5432/d"}) == "postgresql://u:p@h:5432/d"
    assert cb._dsn({"DATABASE_URL": "postgres://u:p@h/d"}) == "postgres://u:p@h/d"


def test_a_forked_child_inherits_no_run():
    bridge, _, _ = make_bridge([FakeConn()], period_s=10.0)
    bridge.armed("polymarket", 0.5)
    running = bridge._thread
    bridge.after_fork_in_child()
    assert bridge._thread is None and bridge._roles == set()
    assert isinstance(bridge._lock, type(threading.Lock()))
    bridge._wake.set()
    running._started.wait(1.0)
    running.join(1.0)


def test_the_hook_never_waits_for_the_new_thread_beside_a_gil_busy_sibling():
    # `uuid4` (os.urandom) gives up the GIL and `Thread.start` waits until the new
    # thread holds it once: beside one busy thread, 12 ms median on the caller.
    stop = []

    def busy():
        while not stop:
            sum(range(1000))

    sibling = threading.Thread(target=busy, daemon=True)
    sibling.start()
    took = []
    try:
        for _ in range(10):
            bridge, _, _ = make_bridge([FakeConn()], period_s=10.0)
            started = time.perf_counter()
            bridge.armed("kalshi", 0.05)
            took.append(time.perf_counter() - started)
            finish(bridge)
    finally:
        stop.append(True)
        sibling.join(2.0)
    assert sorted(took)[len(took) // 2] < 0.005
