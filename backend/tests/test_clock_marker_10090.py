"""#10090 amendment P2: request-caused clock markers on the bridge's connection.

A collector sends ``{v, case, tok, run, slot, nonce}`` on the producer
incarnation's own channel; the producer answers on the case's reply channel
with ``lo``/``hi`` read on its own ``time.monotonic``. These tests pin: DARK
means P's exact calls (no LISTEN, no reply, P's thread-blocking wait); a
request in flight behind P's probe makes the reply later, never the probe;
spoofed, stale, reordered, duplicate, oversized and malformed requests are
counted drops that earn no marker; every cap stops markers without touching
P's lines; and the pinned schema fixture is what the code sends.
"""

import asyncio
import inspect
import json
import os
import re
import threading
import time
from datetime import datetime, timezone
from pathlib import Path

import pytest

from app.utils import clock_bridge as cb

SCHEMA = json.loads(
    (Path(__file__).parent / "fixtures" / "clock_marker_10090_schema.json").read_text())
LINE = re.compile(r"(clock_bridge|clock_bridge_fault|clock_bridge_authority)\[pid=(\d+)\] (\{.*\})$")
CASE = "case20261030a"
NONCE = "00112233445566778899aabbccddeeff"


def nonce(i):
    return f"{i:032x}"


class MarkerConn:
    """P's statements plus the three calls markers make; records every call."""

    def __init__(self, probe_delay=0.0, notify_delay=0.0, notify_error=None,
                 listen_error=None, on_probe=None):
        self.probe_delay, self.notify_delay = probe_delay, notify_delay
        self.notify_error, self.listen_error, self.on_probe = notify_error, listen_error, on_probe
        self.calls, self.sent, self.listeners = [], [], {}
        self.closed = self.terminated = False
        self.loop = None
        self.probe_ends = []

    async def fetchval(self, sql):
        self.calls.append(("fetchval", sql))
        if self.on_probe:
            self.on_probe(self)
        if self.probe_delay:
            await asyncio.sleep(self.probe_delay)
        self.probe_ends.append(time.monotonic())
        return datetime.now(timezone.utc)

    async def fetchrow(self, sql):
        self.calls.append(("fetchrow", sql))
        return None

    async def add_listener(self, channel, callback):
        self.calls.append(("listen", channel))
        if self.listen_error:
            raise self.listen_error
        self.loop = asyncio.get_running_loop()
        self.listeners[channel] = callback

    async def remove_listener(self, channel, callback):
        self.calls.append(("unlisten", channel))
        self.listeners.pop(channel, None)

    async def execute(self, sql, *args):
        self.calls.append(("execute", sql, args[0]))
        if self.notify_error:
            raise self.notify_error
        if self.notify_delay:
            await asyncio.sleep(self.notify_delay)
        self.sent.append((time.monotonic(), args[0], json.loads(args[1])))

    async def close(self):
        self.closed = True

    def terminate(self):
        self.terminated = True

    # asyncpg delivers a notification with call_soon on the connection's loop
    def deliver(self, payload, channel=None):
        (ch, callback), = self.listeners.items()
        self.loop.call_soon_threadsafe(callback, self, 4242, channel or ch, payload)

    def kinds(self):
        return [m["k"] for _, _, m in self.sent]

    def bind(self):
        return next(m for _, _, m in self.sent if m["k"] == "bind")


def request(bind, slot, nonce_=None, **override):
    body = dict(v=1, case=bind["case"], tok=bind["tok"], run=bind["run"], slot=slot,
                nonce=nonce_ or nonce(slot + 1))
    body.update(override)
    return json.dumps(body)


def marker_env(case=CASE, expires_in=600.0, **extra):
    env = {"DYNO": "worker-ws.1", "HEROKU_RELEASE_VERSION": "v5999",
           "HEROKU_SLUG_COMMIT": "f" * 40, **extra}
    if case is not None:
        env["CLOCK_MARKER_CASE"] = case
    if expires_in is not None:
        env["CLOCK_MARKER_EXPIRES_AT"] = str(time.time() + expires_in)
    return env


def make_bridge(conns, env, period_s=0.05):
    lines, connects = [], []
    pool = list(conns)

    async def connect():
        conn = pool.pop(0) if len(pool) > 1 else pool[0]
        connects.append(conn)
        return conn

    bridge = cb.ClockBridge(
        connect=connect, period_s=period_s, env=env,
        emit=lambda prefix, pid, text: lines.append(f"{prefix}[pid={pid}] {text}"),
    )
    return bridge, lines, connects


def finish(bridge, timeout=5.0):
    thread = bridge._thread
    if thread is not None:
        thread._started.wait(timeout)
        thread.join(timeout)
        assert not thread.is_alive()


def wait_for(predicate, timeout=2.0):
    end = time.monotonic() + timeout
    while time.monotonic() < end:
        if predicate():
            return True
        time.sleep(0.002)
    return False


def parsed(lines):
    out = []
    for text in lines:
        match = LINE.search(text)
        assert match, text  # nothing but P's three line kinds ever reaches the log
        out.append((match.group(1), json.loads(match.group(3))))
    return out


class Clock:
    def __init__(self):
        self.mono_now, self.wall_now = 100.0, 1_800_000_000.0

    def mono(self):
        return self.mono_now

    def wall(self):
        return self.wall_now


def unit(env=None, clock=None, run="a1b2c3d4"):
    """A `_Markers` on a fake clock, driven directly on a test loop."""
    clock = clock or Clock()
    env = env or marker_env()
    env["CLOCK_MARKER_EXPIRES_AT"] = str(clock.wall_now + 600)
    bridge = cb.ClockBridge(connect=None, wall=clock.wall, mono=clock.mono, env=env)
    markers = bridge._markers(run)
    assert markers is not None
    return bridge, markers, clock


def notify_now(markers, conn, payload, channel=None):
    markers.on_notify(conn, 4242, channel or markers.channel, payload)


# ── dark: P's exact calls ───────────────────────────────────────────────────

@pytest.mark.parametrize("case, expires_in", [
    (None, None),
    (CASE, None),  # no expiry
    (None, 60.0),  # no case
    (CASE, -1.0),
    (CASE, cb.MARKER_ARM_MAX_S + 100),
    (CASE, "soon"),
    ("Case-With-Dash", 60.0),
    ("short", 60.0),
])
def test_without_an_admitted_case_an_armed_run_makes_only_ps_calls(monkeypatch, case, expires_in):
    # The expiry is read from the clock HERE, never at collection: a CI shard
    # reaches this test minutes after collecting it (+7300 s became +6700 s).
    env = {} if case is None else {"CLOCK_MARKER_CASE": case}
    if expires_in is not None:
        env["CLOCK_MARKER_EXPIRES_AT"] = (
            expires_in if isinstance(expires_in, str) else str(time.time() + expires_in))
    conn = MarkerConn()
    bridge, lines, _ = make_bridge([conn], {"DYNO": "worker-ws.1", **env})
    waits = []
    real = threading.Event.wait

    def spy(self, timeout=None):
        if threading.current_thread().name == "clock-bridge":
            waits.append(timeout)
        return real(self, timeout)

    monkeypatch.setattr(threading.Event, "wait", spy)
    assert bridge._markers("a1b2c3d4") is None
    bridge.armed("kalshi", 0.2)
    finish(bridge)
    assert {c[0] for c in conn.calls} == {"fetchval", "fetchrow"}
    assert conn.sent == [] and conn.listeners == {}
    assert waits and all(w is not None and w > 0 for w in waits)  # P's blocking wait
    assert [k for k, _ in parsed(lines)][:2] == ["clock_bridge", "clock_bridge_authority"]


def test_a_case_without_an_armed_trace_starts_nothing():
    conn = MarkerConn()
    bridge, lines, connects = make_bridge([conn], marker_env())
    time.sleep(0.05)
    assert (bridge._thread, lines, connects, conn.calls) == (None, [], [], [])


def test_the_hook_is_unchanged_and_nothing_crosses_threads_with_call_soon_threadsafe():
    source = inspect.getsource(cb)
    assert "call_soon_threadsafe" not in source
    hook = inspect.getsource(cb.ClockBridge.armed)
    assert "_markers" not in hook and "Markers" not in hook
    # The marker clock is the traces' clock.
    assert cb.ClockBridge().mono is time.monotonic


# ── enabled: one bracket per request, on the bridge's own connection ────────

def test_an_admitted_case_binds_answers_and_ends_on_the_reply_channel():
    conn = MarkerConn()
    env = marker_env()
    bridge, lines, connects = make_bridge([conn], env, period_s=0.05)
    bridge.armed("polymarket", 0.6)
    assert wait_for(lambda: "bind" in conn.kinds())
    bind = conn.bind()
    # The LISTEN came after P's first probe and its authority read.
    assert [c[0] for c in conn.calls][:4] == ["fetchval", "fetchrow", "listen", "execute"]
    assert conn.calls[2][1] == bind["ch"] == f"cm_{CASE}_{bind['tok']}"
    replies = []
    for slot in range(5):
        sent = time.monotonic()
        conn.deliver(request(bind, slot))
        assert wait_for(lambda: len([k for k in conn.kinds() if k == "m"]) == slot + 1)
        received, channel, reply = conn.sent[-1]
        replies.append((sent, reply, received))
        assert channel == f"cmr_{CASE}"
    finish(bridge)
    for sent, reply, received in replies:
        # The causal order the scorer relies on, on one host clock.
        assert sent < reply["lo"] <= reply["hi"] < received
        assert reply["hi"] - reply["lo"] < 0.06  # answered between waits, not on P's 5 s
    assert [r["slot"] for _, r, _ in replies] == list(range(5))
    assert [r["i"] for _, r, _ in replies] == [1, 2, 3, 4, 5]
    assert conn.kinds()[-1] == "end" and conn.sent[-1][2]["why"] == "RUN_END"
    assert conn.closed and len(connects) == 1
    # No marker line in the log; P's lines are its own.
    kinds = [k for k, _ in parsed(lines)]
    assert kinds.count("clock_bridge_authority") == 1 and set(kinds) <= {
        "clock_bridge", "clock_bridge_authority"}


def test_a_request_behind_ps_probe_makes_the_reply_later_never_the_probe():
    conn = MarkerConn()
    bridge, lines, _ = make_bridge([conn], marker_env(), period_s=0.15)
    bridge.armed("kalshi", 0.6)
    assert wait_for(lambda: "bind" in conn.kinds())
    bind = conn.bind()
    conn.probe_delay = 0.08
    conn.on_probe = lambda c: c.loop.call_later(
        0.02, lambda: c.listeners[bind["ch"]](c, 1, bind["ch"], request(bind, 0)))
    assert wait_for(lambda: "m" in conn.kinds(), timeout=1.0)
    conn.on_probe = None
    finish(bridge)
    _, _, reply = next(s for s in conn.sent if s[2]["k"] == "m")
    probe_end = conn.probe_ends[1]
    assert reply["lo"] < probe_end <= reply["hi"]  # stamped on arrival, sent after the probe
    probes = [r for k, r in parsed(lines) if k == "clock_bridge"]
    assert probes[1]["rtt_ms"] < 80 + 40  # the probe ran its own length


def test_an_armed_wake_is_seen_within_the_50ms_poll_while_listening():
    conn = MarkerConn()
    bridge, lines, _ = make_bridge([conn], marker_env(), period_s=10.0)
    bridge.armed("fold", 0.8)
    assert wait_for(lambda: "bind" in conn.kinds())
    time.sleep(0.05)
    began = time.monotonic()
    bridge.armed("nonvenue", 0.8)
    assert wait_for(lambda: len([c for c in conn.calls if c[0] == "fetchval"]) == 2)
    assert time.monotonic() - began < cb.MARKER_POLL_S + 0.04
    finish(bridge)
    probes = [r for k, r in parsed(lines) if k == "clock_bridge"]
    assert [p["trigger"] for p in probes[:2]] == ["ARMED", "ARMED"]


def test_a_hung_reply_halts_markers_abandons_and_p_reconnects_without_relistening():
    hung, healthy = MarkerConn(notify_delay=5.0), MarkerConn()
    bridge, lines, connects = make_bridge([hung, healthy], marker_env(), period_s=0.05)
    began = time.monotonic()
    bridge.armed("kalshi", 0.5)
    finish(bridge)
    assert hung.terminated and hung.sent == []  # the bind itself timed out
    assert [c[0] for c in healthy.calls if c[0] in ("listen", "execute")] == []
    probes = [r for k, r in parsed(lines) if k == "clock_bridge"]
    assert len(probes) >= 3 and connects[:2] == [hung, healthy]
    assert not [k for k, _ in parsed(lines) if k == "clock_bridge_fault"]  # no P line spent
    assert time.monotonic() - began < 0.5 + 1.0


def test_a_failed_listen_is_a_hole_and_p_continues():
    bad, good = MarkerConn(listen_error=RuntimeError("no listen")), MarkerConn()
    bridge, lines, _ = make_bridge([bad, good], marker_env(), period_s=0.05)
    bridge.armed("kalshi", 0.3)
    finish(bridge)
    assert bad.terminated and bad.sent == [] and good.sent == []
    assert len([k for k, _ in parsed(lines) if k == "clock_bridge"]) >= 3


# ── unit controls on a fake clock ───────────────────────────────────────────

def drive(markers, conn, coro_fn):
    async def main():
        conn.loop = asyncio.get_running_loop()
        conn.listeners[markers.channel] = markers.on_notify
        markers.conn = conn
        return await coro_fn()
    return asyncio.run(main())


def test_each_reply_carries_its_own_arrival_and_send_stamps_in_fifo_order():
    bridge, m, clock = unit()
    conn = MarkerConn()
    bind = dict(case=m.case, tok=m.tok, run=m.run)
    clock.mono_now = 200.0
    notify_now(m, conn, request(bind, 0))
    clock.mono_now = 200.010
    notify_now(m, conn, request(bind, 1))
    clock.mono_now = 200.500  # P's probe held both

    async def go():
        return await m.serve(conn)

    drive(m, conn, go)
    (_, _, a), (_, _, b) = conn.sent
    assert (a["slot"], a["lo"], a["hi"], a["i"], a["rx"]) == (0, 200.0, 200.5, 1, 1)
    assert (b["slot"], b["lo"], b["hi"], b["i"], b["rx"]) == (1, 200.01, 200.5, 2, 2)
    assert a["nonce"] == nonce(1) and b["nonce"] == nonce(2)  # never a cached marker


def test_wall_steps_never_move_a_bracket():
    bridge, m, clock = unit()
    conn = MarkerConn()
    bind = dict(case=m.case, tok=m.tok, run=m.run)
    clock.mono_now = 300.0
    notify_now(m, conn, request(bind, 0))
    clock.wall_now -= 3600  # a wall step backwards
    clock.mono_now = 300.002

    async def go():
        return await m.serve(conn)

    drive(m, conn, go)
    reply = conn.sent[0][2]
    assert (reply["lo"], reply["hi"]) == (300.0, 300.002)
    assert not {k for k in reply if "wall" in k}


def test_a_coarse_clock_reports_equal_stamps_and_never_invents_order():
    bridge, m, clock = unit()
    conn = MarkerConn()
    bind = dict(case=m.case, tok=m.tok, run=m.run)
    clock.mono_now = 400.0000004
    notify_now(m, conn, request(bind, 0))

    async def go():
        return await m.serve(conn)

    drive(m, conn, go)
    reply = conn.sent[0][2]
    assert reply["lo"] == reply["hi"] == 400.0 and reply["q"] == 1e-06


@pytest.mark.parametrize("payload,fault", [
    ("not json", "bad"),
    (json.dumps([1, 2]), "bad"),
    ("{}", "bad"),
    ("x" * 300, "big"),
    ("", "big"),
])
def test_malformed_and_oversized_requests_are_counted_and_earn_nothing(monkeypatch, payload, fault):
    bridge, m, _ = unit()
    if fault == "big":
        monkeypatch.setattr(cb.json, "loads", lambda *a, **k: pytest.fail("parsed"))
    notify_now(m, MarkerConn(), payload)
    assert m.pending == [] and m.faults[fault] == 1


def test_spoofed_stale_reordered_duplicate_and_mistyped_requests_are_dropped():
    bridge, m, clock = unit()
    conn = MarkerConn()
    bind = dict(case=m.case, tok=m.tok, run=m.run)
    cases = [
        (request(bind, 3, tok="f" * 16), "foreign"),  # another incarnation's token
        (request(bind, 3, run="00000000"), "foreign"),  # a previous run (stale)
        (request(bind, 3, case="othercase1"), "foreign"),
        (request(bind, 3, v=True), "bad"),
        (request(bind, True), "bad"),
        (request(bind, 760), "bad"),
        (request(bind, -1), "bad"),
        (request(bind, 3, nonce_=NONCE.upper()), "bad"),
        (request(bind, 3, nonce_="ab" * 8), "bad"),  # 64-bit, not 128
        (json.dumps({**json.loads(request(bind, 3)), "extra": 1}), "bad"),
    ]
    for payload, fault in cases:
        before = dict(m.faults)
        notify_now(m, conn, payload)
        assert m.faults[fault] == before[fault] + 1, payload
    assert m.pending == []
    notify_now(m, conn, request(bind, 5, NONCE))
    notify_now(m, conn, request(bind, 5, nonce(99)))  # duplicate slot
    notify_now(m, conn, request(bind, 6, NONCE))  # replayed nonce
    notify_now(m, conn, request(bind, 4))  # reordered: older slot after a newer one
    assert [p[2] for p in m.pending] == [5]
    assert (m.faults["dup"], m.faults["ord"]) == (2, 1)

    async def go():
        return await m.serve(conn)

    drive(m, conn, go)
    assert [s[2]["slot"] for s in conn.sent] == [5]
    assert conn.sent[0][2]["f"]["foreign"] == 3


def test_the_queue_is_bounded_and_overflow_is_a_counted_gap():
    bridge, m, _ = unit()
    conn = MarkerConn()
    bind = dict(case=m.case, tok=m.tok, run=m.run)
    for slot in range(cb.MARKER_QUEUE + 3):
        notify_now(m, conn, request(bind, slot))
    assert len(m.pending) == cb.MARKER_QUEUE and m.faults["q"] == 3


def test_the_marker_cap_received_cap_and_byte_cap_each_halt(monkeypatch):
    bridge, m, _ = unit()
    conn = MarkerConn()
    bind = dict(case=m.case, tok=m.tok, run=m.run)
    m.accepted = cb.MARKER_MAX
    notify_now(m, conn, request(bind, 0))

    async def go():
        return await m.serve(conn)

    drive(m, conn, go)
    assert m.halted == "MARKER_CAP" and conn.sent == [] and m.faults["drop"] == 1

    bridge, m, _ = unit()
    for i in range(cb.MARKER_MAX_RECEIVED + 5):
        notify_now(m, conn, "{}")
    assert m.halted == "RECEIVED_CAP" and m.faults["bad"] == cb.MARKER_MAX_RECEIVED

    bridge, m, _ = unit()
    monkeypatch.setattr(cb, "MARKER_PAYLOAD_MAX_B", 300)
    bind = dict(case=m.case, tok=m.tok, run=m.run)
    notify_now(m, conn, request(bind, 0))  # ~110 B in
    conn2 = MarkerConn()

    async def go2():
        return await m.serve(conn2)

    drive(m, conn2, go2)
    assert m.halted == "BYTE_CAP" and conn2.sent == []  # the reply would pass 300 B


def test_a_halt_sends_end_then_unlistens_and_the_wait_falls_back_to_ps_wait(monkeypatch):
    bridge, m, clock = unit()
    conn = MarkerConn()
    bind = dict(case=m.case, tok=m.tok, run=m.run)
    waits = []
    monkeypatch.setattr(bridge._wake, "wait", lambda t: waits.append(t))
    notify_now(m, conn, request(bind, 0))
    clock.wall_now = m.expires  # the case expired

    async def go():
        return await m.wait(conn, clock.mono_now + 1.0)

    drive(m, conn, go)
    assert conn.kinds() == ["m", "end"] and conn.sent[-1][2]["why"] == "EXPIRED"
    assert conn.calls[-1] == ("unlisten", m.channel)
    assert waits == [1.0] and not m.listening(conn)


def test_run_end_drops_pending_requests_as_counted_and_sends_one_end():
    bridge, m, _ = unit()
    conn = MarkerConn()
    bind = dict(case=m.case, tok=m.tok, run=m.run)
    notify_now(m, conn, request(bind, 0))
    notify_now(m, conn, request(bind, 1))

    async def go():
        return await m.stop(conn, "RUN_END")

    drive(m, conn, go)
    (_, _, end), = conn.sent
    assert (end["k"], end["why"], end["i"], end["rx"], end["f"]["drop"]) == ("end", "RUN_END", 0, 2, 2)
    assert ("unlisten", m.channel) not in conn.calls  # the close ends the LISTEN


def test_a_forked_child_derives_its_own_channel_and_inherits_no_run(monkeypatch):
    bridge, parent, _ = unit()
    bridge.after_fork_in_child()
    assert bridge._thread is None
    monkeypatch.setattr(cb.os, "getpid", lambda: parent.pid + 1)
    child = bridge._markers(parent.run)  # even with the same run id
    assert child.pid == parent.pid + 1 and child.tok != parent.tok
    assert child.channel != parent.channel and child.pending == [] and child.accepted == 0


# ── the pinned schema is what the code sends ────────────────────────────────

def test_the_schema_fixture_matches_the_code():
    limits = SCHEMA["limits"]
    assert SCHEMA["schema"] == cb.MARKER_SCHEMA
    assert (limits["markers_per_run"], limits["received_per_run"], limits["queue"]) == (
        cb.MARKER_MAX, cb.MARKER_MAX_RECEIVED, cb.MARKER_QUEUE)
    assert (limits["payload_bytes_per_run"], limits["wire_bytes_per_run_estimated"]) == (
        cb.MARKER_PAYLOAD_MAX_B, cb.MARKER_WIRE_MAX_B)
    assert (limits["frame_in_bytes_estimated"], limits["frame_out_bytes_estimated"]) == (
        cb.MARKER_FRAME_IN_B, cb.MARKER_FRAME_OUT_B)
    assert (limits["statement_timeout_s"], limits["poll_s"]) == (cb.PROBE_TIMEOUT_S, cb.MARKER_POLL_S)
    assert (SCHEMA["request"]["max_bytes"], SCHEMA["reply"]["max_bytes"]) == (
        cb.MARKER_REQUEST_MAX_B, cb.MARKER_REPLY_MAX_B)
    assert sorted(SCHEMA["request"]["keys"]) == sorted(cb._MARKER_REQUEST_KEYS)
    assert tuple(SCHEMA["faults"]) == cb.MARKER_FAULTS
    assert SCHEMA["enable"]["arm_max_s"] == cb.MARKER_ARM_MAX_S
    assert SCHEMA["enable"]["case_pattern"] == "^" + cb._MARKER_CASE.pattern + "$"

    # Worst-case field widths still fit, and the keys are the fixture's.
    env = marker_env(case="z" * 24, DYNO="worker-heavy.12", HEROKU_RELEASE_VERSION="v99999")
    clock = Clock()
    bridge, m, _ = unit(env=env, clock=clock, run="ffffffff")
    m.boot = "0" * 36
    m.bind_fields["boot"] = m.boot
    conn = MarkerConn()
    bind = dict(case=m.case, tok=m.tok, run=m.run)
    example = dict(SCHEMA["request"]["example"], case=m.case, tok=m.tok, run=m.run, slot=759)
    notify_now(m, conn, json.dumps(example))
    assert len(json.dumps(example)) <= cb.MARKER_REQUEST_MAX_B
    for k in cb.MARKER_FAULTS:
        m.faults[k] = 1520
    m.received = 1519
    clock.mono_now = 9_999_999.123456

    async def go():
        conn.listeners.clear()
        m.conn = None
        await m.listen(conn)
        await m.serve(conn)
        await m.stop(conn, "RUN_END")

    asyncio.run(go())
    assert [s[2]["k"] for s in conn.sent] == ["bind", "m", "end"]
    for _, _, message in conn.sent:
        section = {"bind": "bind", "m": "reply", "end": "end"}[message["k"]]
        assert sorted(message) == SCHEMA[section]["keys"], section
        assert len(json.dumps(message, separators=(",", ":"))) <= SCHEMA[section]["max_bytes"]
    assert conn.sent[0][2]["ch"] == f"cm_{m.case}_{m.tok}"
    assert len(conn.sent[0][2]["ch"]) <= 63  # a Postgres identifier
