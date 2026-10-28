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
import logging
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
    assert sw.parse(raw, NOW) == OFF


def test_a_trial_up_to_thirty_minutes_reads_as_written():
    assert sw.parse(_stored(1, 1800), NOW) == SwitchState("ab", 1, NOW + 1800)
    assert sw.parse(_stored(0, 1).encode(), NOW) == SwitchState("ab", 0, NOW + 1)


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
    assert f"{NAME} mode=ab half=0 expires_at=" in lines[0]
    assert f"{NAME} mode=off half=- expires_at=-" in lines[1]


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
    assert sw.parse(fake.values[sw.key(NAME)], time.time()) == SwitchState(
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
