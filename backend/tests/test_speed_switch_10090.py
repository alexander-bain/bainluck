"""#10090 — a reviewed speed switch is trialled on half of the live games, for
30 minutes at most, without a release (`app.tasks.speed_switches`).

Alex's standing approval (ALEX-DECISIONS item 4) is at most HALF of live games,
at most 30 minutes, automatic switch-back when the timer ends or on any error,
every trial logged. These tests pin each limit in code: default OFF, expiry
OFF, Redis down or hanging OFF with the hot path never waiting, ``ab`` on for
exactly one event-id parity and stably, a switched path's error turning it OFF
locally for the rest of the trial, the admin setter's validation and auth, and
the receipts carrying each event's arm.
"""

import asyncio
import json
import math
import os
import logging
import threading
import time

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

import app.tasks.live_blend_refresh as blend_mod
from app.tasks import speed_switches as sw
from app.tasks.live_blend_refresh import OPTIONAL_DB_ABANDON_ENV, OPTIONAL_DB_SWITCH
from app.tasks.speed_switches import OFF, SpeedSwitches, SwitchState

NAME = "abandon_optional_db"
NOW = 1_800_000_000.0


@pytest.fixture(autouse=True)
def _trials_enabled(monkeypatch):
    monkeypatch.setenv(sw.TRIALS_ENV, "1")


@pytest.fixture(autouse=True)
def _todays_setting(monkeypatch):
    """`pending_attempts`' and `admitted_debt_slots`' today is the worker's own
    setting; pinned at 1 here."""
    monkeypatch.setattr(blend_mod, "FRESH_FLUSH_PENDING_ATTEMPTS", 1)
    monkeypatch.setattr(blend_mod, "ADMITTED_DEBT_SLOTS", 1)


class _Clock:
    def __init__(self, t):
        self.t = t

    def __call__(self):
        return self.t


def _stored(half=0, expires_in=600.0, now=NOW, **extra):
    return json.dumps({"mode": "ab", "half": half, "expires_at": now + expires_in, **extra})


def _switches(values, wall=NOW, mono=0.0):
    """Switches over a fake store whose clocks the test moves."""
    store = {"values": values, "reads": 0}

    def read():
        store["reads"] += 1
        if isinstance(store["values"], BaseException):
            raise store["values"]
        return list(store["values"])

    clock, monotonic = _Clock(wall), _Clock(mono)
    return SpeedSwitches(read=read, clock=clock, monotonic=monotonic), store, clock, monotonic


async def _refreshed(s):
    s.state(NAME)
    if s._refresh is not None:
        await s._refresh


# ── what a stored value means ────────────────────────────────────────────────


@pytest.mark.parametrize("raw", [
    None, "", "x", "[]", "{}", json.dumps({"mode": "on", "half": 0, "expires_at": NOW + 60}),
    json.dumps({"mode": "all", "half": 0, "expires_at": NOW + 60}),
    json.dumps({"mode": "ab", "half": 2, "expires_at": NOW + 60}),
    json.dumps({"mode": "ab", "half": True, "expires_at": NOW + 60}),
    json.dumps({"mode": "ab", "half": "0", "expires_at": NOW + 60}),
    json.dumps({"mode": "ab", "half": 0}),
    json.dumps({"mode": "ab", "half": 0, "expires_at": "soon"}),
    json.dumps({"mode": "ab", "half": 0, "expires_at": NOW}),          # passed
    json.dumps({"mode": "ab", "half": 0, "expires_at": NOW - 1}),
    json.dumps({"mode": "ab", "half": 0, "expires_at": NOW + 1801}),   # past 30 min
    b"\xff\xfe",
])
def test_anything_but_a_running_half_trial_reads_off(raw):
    assert sw.parse(raw, NOW, NAME) == OFF


def test_a_trial_up_to_thirty_minutes_reads_as_written():
    assert sw.parse(_stored(1, 1800), NOW, NAME) == SwitchState("ab", 1, NOW + 1800)
    assert sw.parse(_stored(0, 1).encode(), NOW, NAME) == SwitchState("ab", 0, NOW + 1)


# ── one process's reader ─────────────────────────────────────────────────────


async def test_default_is_off_and_no_key_is_off():
    s, store, _, _ = _switches([None])
    assert s.state(NAME) == OFF and not s.arm(NAME, 2)
    await _refreshed(s)
    assert store["reads"] == 1
    assert s.state(NAME) == OFF and not s.arm(NAME, 2) and s.tags(2) == ""


async def test_ab_is_on_for_exactly_one_parity_and_stays_there():
    s, _, _, _ = _switches([_stored(half=1)])
    await _refreshed(s)
    ids = range(15_300_000, 15_301_000)
    on = {eid for eid in ids if s.arm(NAME, eid)}
    assert len(on) == 500 and all(eid % 2 == 1 for eid in on)
    assert on == {eid for eid in ids if s.arm(NAME, eid)}, "the same games every time"
    assert s.tags(3) == " sw=abandon_optional_db:on"
    assert s.tags(4) == " sw=abandon_optional_db:off"


async def test_the_trial_ends_at_its_expiry_without_another_read():
    s, store, clock, _ = _switches([_stored(expires_in=60)])
    await _refreshed(s)
    assert s.arm(NAME, 2)
    clock.t = NOW + 60
    assert not s.arm(NAME, 2) and s.state(NAME) == OFF
    assert store["reads"] == 1


async def test_cleared_key_reads_off_after_the_next_refresh():
    s, store, _, mono = _switches([_stored()])
    await _refreshed(s)
    assert s.arm(NAME, 2)
    store["values"] = [None]
    mono.t = sw.CACHE_S
    await _refreshed(s)
    assert not s.arm(NAME, 2)


async def test_redis_down_reads_off():
    s, store, _, _ = _switches(ConnectionError("redis down"))
    assert s.state(NAME) == OFF
    await _refreshed(s)
    assert store["reads"] == 1 and s.state(NAME) == OFF


async def test_a_running_trial_reads_off_once_redis_fails():
    s, store, _, mono = _switches([_stored()])
    await _refreshed(s)
    assert s.arm(NAME, 2)
    store["values"] = TimeoutError("socket timeout")
    mono.t = sw.CACHE_S
    await _refreshed(s)
    assert not s.arm(NAME, 2)


async def test_a_hanging_redis_never_holds_the_hot_path_and_reads_off():
    release = asyncio.Event()
    loop = asyncio.get_running_loop()

    def hang():
        time.sleep(2)  # a socket that never answers, bounded only by its timeout
        return [_stored()]

    s = SpeedSwitches(read=hang, clock=_Clock(NOW), monotonic=time.monotonic)
    started = loop.time()
    for _ in range(100):
        assert s.state(NAME) == OFF
    assert loop.time() - started < .05, "the switch read waited for Redis"
    # The background read gives up at its own bound and reads OFF.
    await asyncio.wait_for(s._refresh, 1.5)
    assert loop.time() - started < 2 * sw.READ_TIMEOUT_S + .3
    assert s.state(NAME) == OFF
    release.set()


async def test_a_cache_that_stops_refreshing_reads_off():
    s, store, _, mono = _switches([_stored()])
    await _refreshed(s)
    assert s.arm(NAME, 2)
    # Every later refresh is still in flight (never completes): past STALE_S, OFF.
    s._refresh = asyncio.get_running_loop().create_future()
    mono.t = sw.STALE_S
    assert not s.arm(NAME, 2)
    s._refresh.cancel()


async def test_an_error_turns_the_switch_off_here_for_the_rest_of_the_trial(caplog):
    s, store, _, mono = _switches([_stored(expires_in=600)])
    await _refreshed(s)
    with caplog.at_level(logging.WARNING, logger="app.tasks.speed_switches"):
        s.trip(NAME, RuntimeError("abandoned read failed"))
        s.trip(NAME, RuntimeError("again"))
    assert not s.arm(NAME, 2)
    mono.t = sw.CACHE_S
    await _refreshed(s)
    assert not s.arm(NAME, 2), "the same trial stays off after a refresh"
    assert sum("switched off for the rest of its trial" in r.getMessage()
               for r in caplog.records) == 1
    # A NEW trial (another expiry) runs again.
    store["values"] = [_stored(expires_in=900)]
    mono.t = 2 * sw.CACHE_S
    await _refreshed(s)
    assert s.arm(NAME, 2)


async def test_each_mode_change_is_logged_once_per_process(caplog):
    s, store, clock, _ = _switches([_stored(half=0, expires_in=60)])
    with caplog.at_level(logging.INFO, logger="app.tasks.speed_switches"):
        await _refreshed(s)
        for _ in range(5):
            s.arm(NAME, 2)
        clock.t = NOW + 61
        s.arm(NAME, 2)
    lines = [r.getMessage() for r in caplog.records if "speed_switch[pid=" in r.getMessage()]
    assert len(lines) == 2
    assert f"{NAME} mode=ab half=0 values=- period_s=- expires_at=" in lines[0]
    assert f"{NAME} mode=off half=- values=- period_s=- expires_at=-" in lines[1]


@pytest.mark.parametrize("setting", [None, "", "0", "off"])
async def test_without_the_layer_enabled_nothing_is_read_and_everything_is_off(
    monkeypatch, setting,
):
    if setting is None:
        monkeypatch.delenv(sw.TRIALS_ENV, raising=False)
    else:
        monkeypatch.setenv(sw.TRIALS_ENV, setting)
    s, store, _, _ = _switches([_stored(half=0)])
    s._stored = {NAME: SwitchState("ab", 0, NOW + 600)}
    s._read_at = 0.0
    for eid in range(10):
        assert not s.arm(NAME, eid)
    assert s.state(NAME) == OFF and s.tags(2) == "" and s._refresh is None
    await asyncio.sleep(0)
    assert store["reads"] == 0


def test_no_running_loop_reads_off_without_reading():
    s, store, _, _ = _switches([_stored()])
    assert s.state(NAME) == OFF and store["reads"] == 0


def test_each_process_has_its_own_switches(monkeypatch):
    first = sw.speed_switches()
    assert sw.speed_switches() is first
    monkeypatch.setattr(sw, "_SWITCHES_PID", -1)
    assert sw.speed_switches() is not first


# ── the admin setter ─────────────────────────────────────────────────────────


class _FakeRedis:
    def __init__(self):
        self.values, self.ttls = {}, {}

    def set(self, key, value, ex=None):
        self.values[key], self.ttls[key] = value, ex

    def delete(self, key):
        self.values.pop(key, None)
        self.ttls.pop(key, None)

    def mget(self, keys):
        return [self.values.get(k) for k in keys]


@pytest.fixture
def admin(monkeypatch):
    from app.routes import admin_speed_switch

    monkeypatch.setenv("ADMIN_TOKEN", "t0ken")
    fake = _FakeRedis()
    monkeypatch.setattr(admin_speed_switch, "_client", lambda: fake)
    app = FastAPI()
    app.include_router(admin_speed_switch.router, prefix="/api")
    return TestClient(app), fake


AUTH = {"Authorization": "Bearer t0ken"}


def test_setter_needs_the_admin_token(admin):
    client, fake = admin
    body = {"name": NAME, "mode": "ab", "ttl_s": 600}
    assert client.post("/api/admin/speed-switch", json=body).status_code == 403
    assert client.post("/api/admin/speed-switch", json=body,
                       headers={"Authorization": "Bearer wrong"}).status_code == 403
    assert client.get("/api/admin/speed-switch").status_code == 403
    assert fake.values == {}


@pytest.mark.parametrize("body", [
    {"name": "everything", "mode": "ab", "ttl_s": 600},
    {"name": NAME, "mode": "on", "ttl_s": 600},
    {"name": NAME, "mode": "all", "ttl_s": 600},
    {"name": NAME, "mode": "ab"},
    {"name": NAME, "mode": "ab", "ttl_s": 0},
    {"name": NAME, "mode": "ab", "ttl_s": 1801},
    {"name": NAME, "mode": "ab", "ttl_s": 600, "half": 2},
])
def test_setter_refuses_anything_outside_the_limits(admin, body):
    client, fake = admin
    assert client.post("/api/admin/speed-switch", json=body, headers=AUTH).status_code == 422
    assert fake.values == {}


def test_setter_starts_reads_and_stops_a_trial(admin):
    client, fake = admin
    before = time.time()
    started = client.post("/api/admin/speed-switch", headers=AUTH,
                          json={"name": NAME, "mode": "ab", "ttl_s": 1800, "half": 1})
    assert started.status_code == 200, started.text
    out = started.json()
    assert out["mode"] == "ab" and out["half"] == 1
    assert before + 1800 <= out["expires_at"] <= time.time() + 1800
    assert fake.ttls[sw.key(NAME)] == 1800
    assert sw.parse(fake.values[sw.key(NAME)], time.time(), NAME) == SwitchState(
        "ab", 1, out["expires_at"])
    read = client.get("/api/admin/speed-switch", headers=AUTH).json()
    assert read["switches"][NAME]["mode"] == "ab" and read["max_ttl_s"] == 1800
    assert read["trials_enabled"] is True and out["trials_enabled"] is True
    stopped = client.post("/api/admin/speed-switch", headers=AUTH,
                          json={"name": NAME, "mode": "off"})
    assert stopped.json()["mode"] == "off" and sw.key(NAME) not in fake.values
    assert client.get("/api/admin/speed-switch", headers=AUTH).json()["switches"][NAME] == {
        "mode": "off", "half": None, "expires_at": None}


def test_setter_is_mounted_behind_the_admin_router():
    from app.main import app

    paths = {route.path for route in app.routes}
    assert "/api/admin/speed-switch" in paths


# ── bucket 1's switched path: abandon only the trial's half ──────────────────


@pytest.fixture
def trial(monkeypatch):
    """A running trial, half 0, through the module's own seam."""
    monkeypatch.delenv(OPTIONAL_DB_ABANDON_ENV, raising=False)
    s = SpeedSwitches(read=lambda: [_stored(half=0, now=time.time())],
                      monotonic=time.monotonic)
    s._stored = {NAME: SwitchState("ab", 0, time.time() + 600)}
    s._read_at = time.monotonic()
    monkeypatch.setattr(blend_mod, "_optional_db_trial", lambda: s)
    return s


def _refresher():
    from tests.test_optional_db_abandon_10090 import refresher

    return refresher()[0]


async def test_trial_abandons_its_half_and_cancels_the_other(trial):
    from tests.test_optional_db_abandon_10090 import Body

    assert OPTIONAL_DB_SWITCH == NAME
    r = _refresher()
    off_half = Body()
    with pytest.raises(TimeoutError):
        await r._optional_db("normal_read", .02, off_half, 3)
    assert off_half.ended == "cancelled" and r.optional_db_abandoned == 0
    unkeyed = Body()
    with pytest.raises(TimeoutError):
        await r._optional_db("normal_read", .02, unkeyed)
    assert unkeyed.ended == "cancelled" and r.optional_db_abandoned == 0
    on_half = Body()
    with pytest.raises(blend_mod.OptionalDbAbandoned):
        await r._optional_db("normal_read", .02, on_half, 4)
    assert on_half.ended is None and r.optional_db_abandoned == 1
    on_half.release.set()
    await asyncio.sleep(0)
    await asyncio.sleep(0)
    assert on_half.ended == "finished"


async def test_trial_capacity_read_follows_its_key(trial):
    from tests.test_optional_db_abandon_10090 import Body

    r = _refresher()
    for key, abandoned in ((5, False), (6, True)):
        read = Body()

        async def body(gate, read=read):
            if gate is not None:
                gate.reading = True
            return await read()

        caller = asyncio.create_task(r._optional_db_in_pass("preview_capacity", body, key))
        await read.started.wait()
        caller.cancel()
        with pytest.raises(asyncio.CancelledError):
            await caller
        assert (read.ended is None) is abandoned
        read.release.set()
        await asyncio.sleep(0)
        await asyncio.sleep(0)


async def test_trial_late_failure_switches_it_off_in_this_process(trial, caplog):
    r = _refresher()
    release = asyncio.Event()

    async def fails_late():
        await release.wait()
        raise ValueError("late")

    with pytest.raises(blend_mod.OptionalDbAbandoned):
        await r._optional_db("normal_ack", .02, fails_late, 2)
    release.set()
    for _ in range(5):
        await asyncio.sleep(0)
    assert not trial.arm(NAME, 2)
    from tests.test_optional_db_abandon_10090 import Body

    after = Body()
    with pytest.raises(TimeoutError):
        await r._optional_db("normal_read", .02, after, 2)
    assert after.ended == "cancelled", "the tripped switch still abandoned"


async def test_trial_counts_the_detached_observation_read(trial):
    r = _refresher()
    r._detached_reads = {asyncio.get_running_loop().create_future()}
    assert r._optional_db_busy()


async def test_without_a_trial_the_switched_paths_are_unchanged(monkeypatch):
    from tests.test_optional_db_abandon_10090 import Body

    monkeypatch.delenv(OPTIONAL_DB_ABANDON_ENV, raising=False)
    s = SpeedSwitches(read=lambda: [None], monotonic=time.monotonic)
    monkeypatch.setattr(blend_mod, "_optional_db_trial", lambda: s)
    r = _refresher()
    for key in (None, 2, 3):
        body = Body()
        with pytest.raises(TimeoutError):
            await r._optional_db("normal_read", .02, body, key)
        assert body.ended == "cancelled"
    r._detached_reads = {asyncio.get_running_loop().create_future()}
    assert not r._optional_db_busy()
    assert blend_mod._switch_tags(2) == ""


# ── receipts carry each event's arm ──────────────────────────────────────────


async def test_receipt_tags_name_each_events_arm(trial):
    assert blend_mod._switch_tags(10) == " sw=abandon_optional_db:on"
    assert blend_mod._switch_tags(11) == " sw=abandon_optional_db:off"
    assert blend_mod._switch_tags("not-an-id") == ""


async def test_tail_and_delivery_receipts_carry_the_arm(trial, monkeypatch, caplog):
    from tests import test_delivery_receipt_10090 as dr
    from tests import test_live_blend_tail_receipt_837 as tr

    caplog.set_level(logging.INFO, logger="app.tasks.live_blend_refresh")
    clock = _Clock(0.0)
    monkeypatch.setattr(blend_mod, "_mono", clock)
    monkeypatch.setattr(blend_mod, "_wall", lambda: dr.EPOCH + clock.t)
    monkeypatch.setattr(blend_mod, "_live_handoff", {})
    # The switch reads the receipts' clock; this process runs the trial from 0.
    monkeypatch.setattr(trial, "_clock", blend_mod._wall)
    trial.state(NAME)

    held, _ = tr._refresher()
    await tr._commit(held, clock, 1000.0, event_id=2)
    await tr._commit(held, clock, 1001.0, event_id=2)
    clock.t = 1006.0
    await held.refresh_pending()
    (tail,) = tr._receipts(caplog)
    assert tail["sw"] == "abandon_optional_db:on"

    clock.t = 0.0
    r, _ = dr._refresher(previously_live=(1,))
    await dr._flush(r, clock, 1.0, [(11, 0.60)], event_id=1)
    clock.t = 61.0
    await r.refresh_pending()
    (line,) = dr._lines(caplog)
    assert line["event"] == "1" and line["sw"] == "abandon_optional_db:off"


# ── alternate: server-wide settings by wall-clock period ─────────────────────

ATTEMPTS = "pending_attempts"
START = 1_799_999_940.0  # a minute boundary just before NOW


def _alternation(a=1, b=3, period_s=60, start=START, span_s=1200.0, expires_in=None, now=NOW,
                 **extra):
    """Whole a/b pairs from ``start`` (``span_s``), unless ``expires_in`` (from ``now``) is given."""
    expires_at = start + span_s if expires_in is None else now + expires_in
    return json.dumps({"mode": "alternate", "a": a, "b": b, "period_s": period_s,
                       "start": start, "expires_at": expires_at, **extra})


def _both(attempts=None, abandon=None):
    """Stored values in SWITCHES order."""
    by_name = {NAME: abandon, ATTEMPTS: attempts}
    return [by_name.get(name) for name in sw.SWITCHES]


@pytest.mark.parametrize("name, mode, kwargs", [
    (ATTEMPTS, "ab", {"half": 0}),                       # a flush constant has no per-game arm
    (ATTEMPTS, "alternate", {"a": 3, "b": 5, "period_s": 60}),   # neither arm is today's
    (ATTEMPTS, "alternate", {"a": 1, "b": 1, "period_s": 60}),
    (ATTEMPTS, "alternate", {"a": 1, "b": 33, "period_s": 60}),
    (ATTEMPTS, "alternate", {"a": 0, "b": 1, "period_s": 60}),
    (ATTEMPTS, "alternate", {"a": 1, "b": 3, "period_s": 30}),   # under a minute
    (ATTEMPTS, "alternate", {"a": 1, "b": 3, "period_s": 90}),   # not whole minutes
    (ATTEMPTS, "alternate", {"a": 1, "b": 3, "period_s": 960}),
    (ATTEMPTS, "alternate", {"a": True, "b": 3, "period_s": 60}),
    (NAME, "alternate", {"a": 1, "b": 1, "period_s": 60}),
    (NAME, "alternate", {"a": 1, "b": 2, "period_s": 60}),
    (NAME, "all", {}),
])
def test_alternation_outside_the_limits_is_refused(name, mode, kwargs):
    assert sw.validate(name, mode, **kwargs) is not None


@pytest.mark.parametrize("raw", [
    _alternation(start=START + 30),            # not a minute boundary
    _alternation(start=NOW + 120),             # starts in the future
    _alternation(start=NOW - 3600),            # older than any 30-minute trial
    _alternation(expires_in=1801),
    _alternation(b=5, a=3),
])
def test_a_stored_alternation_outside_the_limits_reads_off(raw):
    assert sw.parse(raw, NOW, ATTEMPTS) == OFF


async def test_alternation_switches_by_period_and_every_process_agrees():
    stored = _both(attempts=_alternation(a=1, b=3, period_s=60))
    first, _, clock_1, _ = _switches(stored)
    second, _, clock_2, _ = _switches(stored)
    await _refreshed(first)
    await _refreshed(second)
    seen = []
    for t in range(int(NOW), int(NOW) + 600):
        clock_1.t = clock_2.t = float(t)
        value = first.value(ATTEMPTS, 1)
        assert value == second.value(ATTEMPTS, 1), "two venue processes disagree"
        seen.append(value)
    assert seen.count(3) == 300 and seen.count(1) == 300, "half the time on each arm"
    # Arms follow whole minutes from the start minute: a first.
    clock_1.t = START + 5
    assert first.value(ATTEMPTS, 1) == 1
    clock_1.t = START + 65
    assert first.value(ATTEMPTS, 1) == 3


async def test_each_arm_boundary_is_logged_once_per_process(caplog):
    s, _, clock, _ = _switches(_both(attempts=_alternation(a=1, b=3, period_s=60)))
    await _refreshed(s)
    with caplog.at_level(logging.INFO, logger="app.tasks.speed_switches"):
        for t in range(int(NOW), int(NOW) + 130, 5):
            clock.t = float(t)
            s.value(ATTEMPTS, 1)
    arms = [r.getMessage() for r in caplog.records
            if f"{ATTEMPTS} arm=" in r.getMessage()]
    # NOW sits 60 s into the trial (arm b); two boundaries follow in 130 s.
    assert [m.split(" arm=")[1].split()[0:2] for m in arms] == [
        ["b", "value=3"], ["a", "value=1"], ["b", "value=3"]]
    assert all("since=" in m and "until=" in m for m in arms)


async def test_tags_name_the_arm_of_the_moment_the_line_describes():
    s, _, clock, _ = _switches(_both(attempts=_alternation(a=1, b=3, period_s=60)))
    await _refreshed(s)
    s.state(ATTEMPTS)                          # this process runs the trial from NOW
    clock.t = START + 130                      # a now
    assert s.tags(5) == " sw=pending_attempts:1"
    # A delivery line written now about the minute that started at NOW is arm b.
    assert s.tags(5, at=NOW) == " sw=pending_attempts:3"
    # The minute that started at START opened before this process ran the trial.
    assert s.tags(5, at=START) == ""


async def test_a_boolean_switch_alternates_off_and_on_for_every_read():
    s, _, clock, _ = _switches(_both(abandon=_alternation(a=0, b=1, period_s=120)))
    await _refreshed(s)
    clock.t = START + 30
    assert not any(s.arm(NAME, eid) for eid in range(10))
    clock.t = START + 150
    assert all(s.arm(NAME, eid) for eid in range(10))
    assert s.tags(4) == " sw=abandon_optional_db:on"


# ── pending_attempts: read once per flush, never stalls the flush ────────────


@pytest.fixture
def attempts_trial(monkeypatch):
    """An alternation whose current arm the test sets (`arm['value']`)."""
    arm = {"value": 3, "tripped": []}

    class _Trial:
        def value(self, name, default, at=None):
            assert name == ATTEMPTS
            return default if arm["tripped"] else arm["value"]

        def trip(self, name, error):
            arm["tripped"].append((name, error))

        def state(self, name):
            return OFF

        def arm(self, name, event_id, at=None):
            return False

        def tags(self, event_id, at=None):
            return ""

    monkeypatch.setattr(blend_mod, "_optional_db_trial", lambda: _Trial())
    monkeypatch.setattr(blend_mod, "FRESH_FLUSH_PENDING_ATTEMPTS", 1)
    return arm


def _recording():
    from tests.test_ws_flush_cadence_10090 import _Recording

    async def prepared(event_ids):
        return {}

    r = _Recording(min_refresh_interval_s=0)
    r._prepare_groups = prepared
    return r


async def test_a_busy_flush_attempts_the_trials_owed_stamps_and_keeps_the_rest(attempts_trial):
    r = _recording()
    r.adopt_pending(range(1, 9))
    await r.refresh([99], flush_started=1000)
    await r.refresh([98], flush_started=1000)
    assert [ids for ids, _ in r.batches] == [[99], [1], [2], [3], [98]]
    assert r.pending_event_ids() == frozenset(range(4, 9))


async def test_the_allowance_is_read_once_per_flush(attempts_trial):
    r = _recording()
    r.adopt_pending(range(1, 9))
    await r.refresh([99], flush_started=1000)
    attempts_trial["value"] = 1               # the arm changes mid-flush
    await r.refresh([98], flush_started=1000)
    assert [ids for ids, _ in r.batches] == [[99], [1], [2], [3], [98]]
    await r.refresh([97], flush_started=1001)   # the next flush reads the new arm
    assert [ids for ids, _ in r.batches][-2:] == [[97], [4]]


async def test_without_a_trial_the_allowance_is_the_setting(monkeypatch):
    s = SpeedSwitches(read=lambda: _both(), monotonic=time.monotonic)
    monkeypatch.setattr(blend_mod, "_optional_db_trial", lambda: s)
    for setting in (1, 2):
        monkeypatch.setattr(blend_mod, "FRESH_FLUSH_PENDING_ATTEMPTS", setting)
        assert blend_mod._fresh_flush_pending_attempts() == setting


async def test_a_failed_attempt_only_the_trial_allowed_switches_it_off(attempts_trial):
    r = _recording()
    real = r._refresh_batch

    async def batch(event_ids, now, **kw):
        if event_ids == [2]:
            raise RuntimeError("stamp failed")
        return await real(event_ids, now, **kw)

    r._refresh_batch = batch
    r.adopt_pending(range(1, 9))
    await r.refresh([99], flush_started=1000)
    assert [name for name, _ in attempts_trial["tripped"]] == [ATTEMPTS]
    assert [ids for ids, _ in r.batches] == [[99], [1]], "this flush stopped at the failure"
    await r.refresh([97], flush_started=1001)
    assert [ids for ids, _ in r.batches][-2:] == [[97], [3]], "back to today's one"


async def test_a_failed_first_attempt_is_todays_and_trips_nothing(attempts_trial):
    r = _recording()
    real = r._refresh_batch

    async def batch(event_ids, now, **kw):
        if event_ids == [1]:
            raise RuntimeError("stamp failed")
        return await real(event_ids, now, **kw)

    r._refresh_batch = batch
    r.adopt_pending(range(1, 9))
    await r.refresh([99], flush_started=1000)
    assert attempts_trial["tripped"] == []


async def test_a_slow_redis_never_stalls_the_flush_read(monkeypatch):
    """The reporting chat's 0023Z bound: a slow (not refused) Redis returns the
    cached value, then the setting, promptly — never after a socket timeout."""
    stored = {"values": _both(attempts=_alternation(a=1, b=3, period_s=60,
                                                    now=time.time(),
                                                    start=math.floor(time.time() / 60) * 60.0))}
    slow = {"on": False}

    def read():
        if slow["on"]:
            time.sleep(2)  # a Redis that accepts the connection and never answers
        return list(stored["values"])

    mono = _Clock(0.0)
    s = SpeedSwitches(read=read, monotonic=mono)
    monkeypatch.setattr(blend_mod, "_optional_db_trial", lambda: s)
    monkeypatch.setattr(blend_mod, "FRESH_FLUSH_PENDING_ATTEMPTS", 1)
    blend_mod._fresh_flush_pending_attempts()
    await s._refresh
    trial_value = s.value(ATTEMPTS, 1)
    assert trial_value in (1, 3)
    slow["on"] = True
    loop = asyncio.get_running_loop()
    mono.t = sw.CACHE_S                       # due for a refresh, which now hangs
    started = loop.time()
    for _ in range(100):
        assert blend_mod._fresh_flush_pending_attempts() in (1, 3)
    assert loop.time() - started < .05, "the flush read waited on Redis"
    await asyncio.wait_for(s._refresh, 1.5)    # gives up at its own bound
    assert blend_mod._fresh_flush_pending_attempts() == 1, "slow Redis reads as the setting"


# ── setter: alternation ──────────────────────────────────────────────────────


def test_setter_starts_and_stops_an_alternation(admin):
    client, fake = admin
    before = time.time()
    out = client.post("/api/admin/speed-switch", headers=AUTH, json={
        "name": ATTEMPTS, "mode": "alternate", "ttl_s": 600, "a": 1, "b": 3, "period_s": 60,
    })
    assert out.status_code == 200, out.text
    body = out.json()
    assert (body["mode"], body["a"], body["b"], body["period_s"]) == ("alternate", 1, 3, 60)
    assert body["start"] % 60 == 0 and before - 60 < body["start"] <= time.time()
    # Whole a/b pairs from the start minute: the key lives until then, never longer.
    assert body["expires_at"] == body["start"] + 600
    assert 540 <= fake.ttls[sw.key(ATTEMPTS)] <= 600
    stopped = client.post("/api/admin/speed-switch", headers=AUTH,
                          json={"name": ATTEMPTS, "mode": "off"})
    assert stopped.json()["mode"] == "off" and sw.key(ATTEMPTS) not in fake.values


@pytest.mark.parametrize("body", [
    {"name": ATTEMPTS, "mode": "ab", "ttl_s": 600, "half": 0},
    {"name": ATTEMPTS, "mode": "alternate", "ttl_s": 600, "a": 3, "b": 5, "period_s": 60},
    {"name": ATTEMPTS, "mode": "alternate", "ttl_s": 600, "a": 1, "b": 3, "period_s": 30},
    {"name": ATTEMPTS, "mode": "alternate", "ttl_s": 1801, "a": 1, "b": 3, "period_s": 60},
    {"name": ATTEMPTS, "mode": "alternate", "ttl_s": 600, "a": 1, "b": 3},
])
def test_setter_refuses_an_alternation_outside_the_limits(admin, body):
    client, fake = admin
    assert client.post("/api/admin/speed-switch", json=body, headers=AUTH).status_code == 422
    assert fake.values == {}


async def test_bucket1_alternation_abandons_every_read_in_its_on_period(monkeypatch):
    from tests.test_optional_db_abandon_10090 import Body

    monkeypatch.delenv(OPTIONAL_DB_ABANDON_ENV, raising=False)
    clock = _Clock(START + 30)                # the off period (a = 0)
    s = SpeedSwitches(read=lambda: _both(), clock=clock, monotonic=time.monotonic)
    s._stored = {NAME: SwitchState("alternate", 0, NOW + 600, 0, 1, 60, START)}
    s._read_at = time.monotonic()
    monkeypatch.setattr(blend_mod, "_optional_db_trial", lambda: s)
    r = _refresher()
    off = Body()
    with pytest.raises(TimeoutError):
        await r._optional_db("normal_read", .02, off, 4)
    assert off.ended == "cancelled" and r.optional_db_abandoned == 0
    clock.t = START + 90                      # the on period, every read, keyed or not
    for key in (3, None):
        on = Body()
        with pytest.raises(blend_mod.OptionalDbAbandoned):
            await r._optional_db("normal_ack", .02, on, key)
        on.release.set()
        for _ in range(3):
            await asyncio.sleep(0)
        assert on.ended == "finished"
    assert r.optional_db_abandoned == 2


# ── review R1/R2: no game outside the half has a switched read; one read thread ──
@pytest.mark.parametrize("ids", [[4, 7], [7, 4], [2, 4, 9], (e for e in (6, 3))])
def test_a_read_about_both_halves_has_no_key(ids):
    assert blend_mod._optional_db_key(ids) is None


def test_a_read_about_one_half_is_keyed_to_that_half():
    assert blend_mod._optional_db_key([8, 4, 6]) % 2 == 0
    assert blend_mod._optional_db_key([9, 5]) % 2 == 1
    assert blend_mod._optional_db_key([]) is None


async def test_a_read_about_both_halves_is_never_abandoned_in_a_trial(trial):
    from tests.test_optional_db_abandon_10090 import Body

    r = _refresher()
    mixed = Body()
    with pytest.raises(TimeoutError):
        await r._optional_db("normal_ack", .02, mixed, blend_mod._optional_db_key([4, 7]))
    assert mixed.ended == "cancelled" and r.optional_db_abandoned == 0


async def test_the_recovery_page_read_stays_off_in_a_trial(trial, monkeypatch):
    r = _refresher()
    keys = []

    async def capture(kind, budget_s, body, key=None, gate=None):
        keys.append((kind, key))
        return None

    monkeypatch.setattr(r, "_optional_db", capture)
    r._normal_after = 32  # an owed_chart_points row id in the trial's parity
    await r._recover_normal_prices()
    assert keys == [("normal_read", None)]


async def test_a_read_thread_that_outlives_its_bound_is_never_joined_by_a_second():
    gate = threading.Event()
    running = {"now": 0, "peak": 0}
    lock = threading.Lock()

    def stalled():  # a resolver stall: socket timeouts do not bound getaddrinfo
        with lock:
            running["now"] += 1
            running["peak"] = max(running["peak"], running["now"])
        try:
            gate.wait(5)
            return []
        finally:
            with lock:
                running["now"] -= 1

    mono = {"t": 0.0}
    s = SpeedSwitches(read=stalled, monotonic=lambda: mono["t"])
    try:
        for step in range(6):
            mono["t"] = step * sw.CACHE_S
            assert s.state(NAME) == OFF
            await asyncio.wait_for(s._refresh, 2)
        assert running["peak"] == 1
    finally:
        gate.set()


# ── lane1 review: receipt edges and today's setting ──────────────────────────


async def _running_from(values, wall):
    """Switches whose process begins running the stored trials at ``wall``."""
    s, _, clock, _ = _switches(values, wall=wall)
    await _refreshed(s)
    for name in sw.SWITCHES:
        s.state(name)
    return s, clock


async def test_the_minute_before_an_alternation_carries_no_arm():
    # (at - start) // period is -1 there, and -1 % 2 is arm b.
    s, clock = await _running_from(_both(attempts=_alternation(a=1, b=3)), START + 5)
    clock.t = START + 20                       # the line for [START-60, START) closes now
    assert s.tags(5, at=START - 60) == ""


async def test_the_minute_before_a_half_trial_carries_no_arm():
    s, clock = await _running_from(_both(abandon=_stored(half=0)), NOW)
    clock.t = NOW + 20
    assert s.tags(4, at=NOW - 60) == ""
    assert s.tags(4, at=NOW) == " sw=abandon_optional_db:on"


@pytest.fixture
def setting_3(monkeypatch):
    """Speed's step 2: FRESH_FLUSH_PENDING_ATTEMPTS=3 in the worker's env (#11709)."""
    monkeypatch.setattr(blend_mod, "FRESH_FLUSH_PENDING_ATTEMPTS", 3)


def test_an_alternation_must_keep_the_workers_own_setting_on_one_arm(setting_3):
    assert sw.validate(ATTEMPTS, "alternate", a=1, b=32, period_s=60) is not None
    assert sw.parse(_alternation(a=1, b=32), NOW, ATTEMPTS) == OFF
    assert sw.validate(ATTEMPTS, "alternate", a=3, b=8, period_s=60) is None
    assert sw.parse(_alternation(a=3, b=8), NOW, ATTEMPTS).mode == "alternate"


@pytest.mark.parametrize("body", [
    # one 15-minute arm in a 10-minute trial: the whole trial at 3
    {"name": ATTEMPTS, "mode": "alternate", "ttl_s": 600, "a": 3, "b": 1, "period_s": 900},
    # one 15-minute "on" arm in a 15-minute trial: every read of every game, the whole trial
    {"name": NAME, "mode": "alternate", "ttl_s": 900, "a": 1, "b": 0, "period_s": 900},
    # three one-minute arms, two of them away from today
    {"name": ATTEMPTS, "mode": "alternate", "ttl_s": 180, "a": 3, "b": 1, "period_s": 60},
])
def test_an_alternation_that_is_not_whole_pairs_is_refused(admin, body):
    client, fake = admin
    assert client.post("/api/admin/speed-switch", json=body, headers=AUTH).status_code == 422
    assert fake.values == {}


def test_every_accepted_alternation_spends_exactly_half_its_minutes_away_from_today(admin):
    client, fake = admin
    for period_s in range(60, 901, 60):
        for ttl_s in (60, 120, 180, 300, 600, 900, 1200, 1740, 1800):
            for a, b in ((1, 3), (3, 1)):
                fake.values.clear()
                out = client.post("/api/admin/speed-switch", headers=AUTH, json={
                    "name": ATTEMPTS, "mode": "alternate", "ttl_s": ttl_s,
                    "a": a, "b": b, "period_s": period_s})
                if out.status_code != 200:
                    continue
                state = sw.parse(fake.values[sw.key(ATTEMPTS)], time.time(), ATTEMPTS)
                assert state.mode == "alternate"
                assert state.expires_at - time.time() <= sw.MAX_TTL_S
                span = range(int(state.start), int(math.ceil(state.expires_at)))
                away = sum(state.value_at(t + .5) != sw.today(ATTEMPTS) for t in span)
                assert 2 * away == len(span), (period_s, ttl_s, a, b, away, len(span))


@pytest.mark.parametrize("period_s, expires_at", [
    (900, START + 900), (60, START + 660), (60, START + 61)])
def test_a_stored_alternation_that_is_not_whole_pairs_reads_off(period_s, expires_at):
    raw = json.dumps({"mode": "alternate", "a": 3, "b": 1, "period_s": period_s,
                      "start": START, "expires_at": expires_at})
    assert sw.parse(raw, NOW, ATTEMPTS) == OFF


# ── the start line: R8's per-process readback ────────────────────────────────


@pytest.mark.parametrize(
    "layer, abandon, attempts, slots, expected",
    [
        ("1", None, 1, 1, "layer SPEED_SWITCH_TRIALS=on today pending_attempts=1 "
                          "abandon_optional_db=0 admitted_debt_slots=1"),
        (None, "1", 3, 2, "layer SPEED_SWITCH_TRIALS=off today pending_attempts=3 "
                          "abandon_optional_db=1 admitted_debt_slots=2"),
    ],
)
def test_each_process_logs_the_layer_and_todays_values_once(
        monkeypatch, caplog, layer, abandon, attempts, slots, expected):
    for env, value in ((sw.TRIALS_ENV, layer), (OPTIONAL_DB_ABANDON_ENV, abandon)):
        if value is None:
            monkeypatch.delenv(env, raising=False)
        else:
            monkeypatch.setenv(env, value)
    monkeypatch.setattr(blend_mod, "FRESH_FLUSH_PENDING_ATTEMPTS", attempts)
    monkeypatch.setattr(blend_mod, "ADMITTED_DEBT_SLOTS", slots)
    monkeypatch.setattr(blend_mod, "_SPEED_SWITCH_LOGGED_PID", None)

    def no_redis():
        raise AssertionError("the start line reads the environment only")

    monkeypatch.setattr(blend_mod, "_optional_db_trial", no_redis)
    monkeypatch.setattr(sw, "_read_stored", no_redis)
    with caplog.at_level(logging.INFO, logger=blend_mod.logger.name):
        blend_mod.LiveBlendRefresher("kalshi")
        blend_mod.LiveBlendRefresher("polymarket")
    lines = [r.getMessage() for r in caplog.records if r.getMessage().startswith("speed_switch[")]
    assert lines == [f"speed_switch[pid={os.getpid()}]: {expected}"]


def test_a_forked_process_logs_its_own_start_line(monkeypatch, caplog):
    monkeypatch.setattr(blend_mod, "_SPEED_SWITCH_LOGGED_PID", os.getpid() + 1)  # the parent's
    with caplog.at_level(logging.INFO, logger=blend_mod.logger.name):
        blend_mod.LiveBlendRefresher("kalshi")
    assert [r for r in caplog.records if r.getMessage().startswith("speed_switch[")]


# ── admitted_debt_slots: read once per door admission (#11718) ───────────────

SLOTS = "admitted_debt_slots"


@pytest.mark.parametrize("mode, kwargs", [
    ("ab", {"half": 0}),                                  # a door constant has no per-game arm
    ("alternate", {"a": 2, "b": 3, "period_s": 60}),      # neither arm is today's
    ("alternate", {"a": 1, "b": 4, "period_s": 60}),      # above the stamp workers
    ("alternate", {"a": 0, "b": 1, "period_s": 60}),
])
def test_a_debt_slots_trial_outside_the_limits_is_refused(mode, kwargs):
    assert sw.validate(SLOTS, mode, **kwargs) is not None


def test_a_debt_slots_alternation_of_today_and_three_is_accepted():
    assert sw.validate(SLOTS, "alternate", a=1, b=3, period_s=60) is None


def test_a_debt_slots_alternation_keeps_the_workers_own_setting_on_one_arm(monkeypatch):
    # R8 step 2 may set ADMITTED_DEBT_SLOTS=2 in the worker's env (#11718).
    monkeypatch.setattr(blend_mod, "ADMITTED_DEBT_SLOTS", 2)
    assert sw.validate(SLOTS, "alternate", a=1, b=3, period_s=60) is not None
    assert sw.parse(_alternation(a=1, b=3), NOW, SLOTS) == OFF
    assert sw.validate(SLOTS, "alternate", a=2, b=3, period_s=60) is None
    assert sw.parse(_alternation(a=2, b=3), NOW, SLOTS).mode == "alternate"


async def test_debt_slots_tag_names_the_arm():
    stored = [_alternation(a=1, b=3, period_s=60) if name == SLOTS else None
              for name in sw.SWITCHES]
    s, _, clock, _ = _switches(stored)
    await _refreshed(s)
    s.state(SLOTS)                             # this process runs the trial from NOW
    clock.t = START + 130
    assert s.tags(5) == " sw=admitted_debt_slots:1"
    assert s.tags(5, at=NOW) == " sw=admitted_debt_slots:3"


@pytest.fixture
def slots_trial(monkeypatch):
    """An admitted_debt_slots alternation whose current arm the test sets."""
    arm = {"value": 3, "tripped": []}

    class _Trial:
        def value(self, name, default, at=None):
            if name != SLOTS:
                return default
            return default if arm["tripped"] else arm["value"]

        def trip(self, name, error):
            arm["tripped"].append((name, error))

        def state(self, name):
            return OFF

        def arm(self, name, event_id, at=None):
            return False

        def tags(self, event_id, at=None):
            return ""

    monkeypatch.setattr(blend_mod, "_optional_db_trial", lambda: _Trial())
    monkeypatch.setattr(blend_mod, "ADMITTED_DEBT_SLOTS", 1)
    monkeypatch.setattr(blend_mod, "_mono", lambda: 1000.0)
    return arm


async def test_each_admission_reads_the_trials_arm(slots_trial):
    from tests.test_admitted_debt_slots_10090 import _Gated, _finish, _running_call, _settle

    r = _Gated(blocked={99, 1, 2, 3, 4, 5})
    task = await _running_call(r)
    r.adopt_pending(range(1, 9))
    r.admit_fresh((), flush_started=1001)
    await _settle()
    assert r.started == [99, 1, 2, 3], "arm b: three owed stamps beside the call"
    slots_trial["value"] = 1                  # the arm changes while three are in flight
    r.admit_fresh((), flush_started=1002)
    await _settle()
    assert r.started == [99, 1, 2, 3], "arm a: no new debt until below today's one"
    await _finish(r, task)


async def test_a_failed_debt_stamp_only_the_trial_let_in_switches_it_off(slots_trial):
    from tests.test_admitted_debt_slots_10090 import _Gated, _finish, _running_call, _settle

    r = _Gated(blocked={99})
    real = r._refresh_batch

    async def batch(event_ids, now, **kw):
        if event_ids == [2]:
            raise RuntimeError("stamp failed")
        return await real(event_ids, now, **kw)

    r._refresh_batch = batch
    task = await _running_call(r)
    r.adopt_pending(range(1, 9))
    r.admit_fresh((), flush_started=1001)
    await _settle()
    assert [name for name, _ in slots_trial["tripped"]] == [SLOTS]
    r.admit_fresh((), flush_started=1002)
    await _settle()
    r.admit_fresh((), flush_started=1003)
    await _settle()
    # Back to today's one slot: one owed event per admission from here.
    assert r.started[-2:] == [4, 5] and r.pending_event_ids() == frozenset({2, 6, 7, 8})
    await _finish(r, task)


async def test_a_failed_debt_stamp_within_todays_slot_trips_nothing(slots_trial):
    from tests.test_admitted_debt_slots_10090 import _Gated, _finish, _running_call, _settle

    slots_trial["value"] = 1
    r = _Gated(blocked={99})
    real = r._refresh_batch

    async def batch(event_ids, now, **kw):
        if event_ids == [1]:
            raise RuntimeError("stamp failed")
        return await real(event_ids, now, **kw)

    r._refresh_batch = batch
    task = await _running_call(r)
    r.adopt_pending(range(1, 4))
    r.admit_fresh((), flush_started=1001)
    await _settle()
    assert slots_trial["tripped"] == []
    await _finish(r, task)


async def test_one_read_of_the_arm_sets_both_the_free_slots_and_the_cohort_first_order(
        monkeypatch):
    # calibration review of a7dc24e0: the arm read once per admission must also
    # order the cohort ahead of its debt (#11718), or the 3-slot minutes compare
    # a different queue from the one R8 step 2 would run.
    from tests.test_admitted_debt_slots_10090 import _Slotted, _finish, _running_call, _settle

    reads = []

    class _Trial:
        def value(self, name, default, at=None):
            if name != SLOTS:
                return default
            reads.append(name)
            return 3 if len(reads) == 1 else 1   # a later read would see arm a

        def trip(self, name, error):
            pass

        def state(self, name):
            return OFF

        def arm(self, name, event_id, at=None):
            return False

        def tags(self, event_id, at=None):
            return ""

    monkeypatch.setattr(blend_mod, "_optional_db_trial", lambda: _Trial())
    monkeypatch.setattr(blend_mod, "ADMITTED_DEBT_SLOTS", 1)
    monkeypatch.setattr(blend_mod, "_mono", lambda: 1000.0)
    r = _Slotted(blocked={99, 1, 2, 3})
    task = await _running_call(r)
    r._live_event_ids.update({1, 2, 3, 50})
    r.adopt_pending([1, 2, 3])
    reads.clear()
    assert r.admit_fresh([50], flush_started=1001) == frozenset({50})
    await _settle()
    assert reads == [SLOTS], "one read of the arm per admission"
    assert r.started == [99, 50, 1, 2], "arm 3: the fresh price starts ahead of its debt"
    await _finish(r, task)


# ── release_unattempted_debt: read once per mixed refresh (R8b) ──────────────

RELEASE = "release_unattempted_debt"


@pytest.mark.parametrize("mode, kwargs", [
    ("ab", {"half": 0}),                                  # a call-level choice has no per-game arm
    ("alternate", {"a": 1, "b": 1, "period_s": 60}),      # no today arm
    ("alternate", {"a": 0, "b": 2, "period_s": 60}),
    ("alternate", {"a": True, "b": 0, "period_s": 60}),
])
def test_a_release_trial_outside_the_limits_is_refused(mode, kwargs):
    assert sw.validate(RELEASE, mode, **kwargs) is not None


def test_a_release_alternation_of_off_and_on_is_accepted():
    assert sw.validate(RELEASE, "alternate", a=0, b=1, period_s=60) is None
    assert sw.today(RELEASE) == 0


async def test_release_tag_names_the_arm():
    stored = [_alternation(a=0, b=1, period_s=60) if name == RELEASE else None
              for name in sw.SWITCHES]
    s, _, clock, _ = _switches(stored)
    await _refreshed(s)
    s.state(RELEASE)                           # this process runs the trial from NOW
    clock.t = START + 130
    assert s.tags(5) == " sw=release_unattempted_debt:off"
    assert s.tags(5, at=NOW) == " sw=release_unattempted_debt:on"


def test_the_release_arm_is_off_on_any_switch_error(monkeypatch):
    def broken():
        raise RuntimeError("switchboard unreadable")

    monkeypatch.setattr(blend_mod, "_optional_db_trial", broken)
    assert blend_mod._release_unattempted_debt() is False
