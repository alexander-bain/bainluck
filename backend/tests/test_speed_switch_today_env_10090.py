"""#10090 — a speed switch an A/B shows safe can be left on by one config
change: ``SPEED_SWITCH_TODAY_<NAME>`` sets that switch's "today"
(`app.tasks.speed_switches.today_env`).

Alex's item 31C: a switch shown safe may be left fully on. A trial is at most
30 minutes and alternates, so before this the only full-on was a release. The
override is read where a switch's no-trial value is decided — `today()` and the
no-trial path of `SpeedSwitches.value` — so every read site gets it. Pinned
here: unset is exactly today; a valid value is in force with no trial and with
the layer off; a running trial still alternates and hands back to the env
value at expiry; an invalid value, or the generic name on a switch that has
its own setting, is ignored with one warning per process.
"""

import json
import logging
import os

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

import app.tasks.live_blend_refresh as blend_mod
from app.tasks import speed_switches as sw
from app.tasks.speed_switches import SpeedSwitches
from tests.test_lock_retry_prompt_10090 import busy_flushes, locking
from tests.test_single_event_commit_10090 import rig

NOW = 1_800_000_000.0
START = 1_799_999_940.0  # a minute boundary just before NOW
PROMPT = "lock_retry_prompt"
HANDOVER = "handover_fresh"
RELEASE = "release_unattempted_debt"
LITERAL_TODAY = (PROMPT, HANDOVER, RELEASE)


@pytest.fixture(autouse=True)
def _clean(monkeypatch):
    """No override, the layer off, a fresh warn-once memo and switchboard."""
    for name in os.environ:
        if name.startswith("SPEED_SWITCH_TODAY_"):
            monkeypatch.delenv(name)
    monkeypatch.delenv(sw.TRIALS_ENV, raising=False)
    monkeypatch.setattr(sw, "_WARNED_TODAY_ENV", set(), raising=False)
    monkeypatch.setattr(sw, "_SWITCHES", None)
    monkeypatch.setattr(blend_mod, "FRESH_FLUSH_PENDING_ATTEMPTS", 1)
    monkeypatch.setattr(blend_mod, "ADMITTED_DEBT_SLOTS", 1)
    monkeypatch.setattr(blend_mod, "ADMITTED_STAMP_BATCH", 1)


@pytest.fixture
def clock(monkeypatch):
    now = [1000.0]
    monkeypatch.setattr(blend_mod, "_mono", lambda: now[0])
    return now


class _Clock:
    def __init__(self, t):
        self.t = t

    def __call__(self):
        return self.t


def _switches(stored: dict, wall=NOW):
    """A switchboard over a fixed store (name → raw value)."""
    wall_clock = _Clock(wall)
    s = SpeedSwitches(read=lambda: [stored.get(name) for name in sw.SWITCHES],
                      clock=wall_clock, monotonic=lambda: 0.0)
    return s, wall_clock


async def _refreshed(s):
    s.state(PROMPT)
    if s._refresh is not None:
        await s._refresh


def _alternation(a, b, period_s=60, span_s=120.0):
    return json.dumps({"mode": "alternate", "a": a, "b": b, "period_s": period_s,
                       "start": START, "expires_at": START + span_s})


# ── unset is exactly today ───────────────────────────────────────────────────


def test_unset_every_switch_reads_exactly_todays_value():
    settings = {"pending_attempts": 1, "admitted_debt_slots": 1, "admitted_stamp_batch": 1}
    for name, spec in sw.SPECS.items():
        assert sw.today_env(name) is None, name
        assert sw.today(name) == settings.get(name, spec["today"]), name
        assert SpeedSwitches(read=list).value(name, 7) == 7, name
    assert sw.today_env_in_force() == {}
    assert blend_mod._lock_retry_prompt() is False
    assert blend_mod._handover_fresh() is False
    assert blend_mod._release_unattempted_debt() is False


# ── set: in force with no trial ──────────────────────────────────────────────


@pytest.mark.parametrize("layer", [None, "1"])
async def test_env_one_turns_lock_retry_prompt_and_handover_fresh_on_with_no_trial(
        monkeypatch, layer):
    monkeypatch.setenv("SPEED_SWITCH_TODAY_LOCK_RETRY_PROMPT", "1")
    monkeypatch.setenv("SPEED_SWITCH_TODAY_HANDOVER_FRESH", " 1 ")
    if layer:
        monkeypatch.setenv(sw.TRIALS_ENV, layer)
        s, _ = _switches({})                      # the layer on, no key stored
        await _refreshed(s)
        monkeypatch.setattr(blend_mod, "_optional_db_trial", lambda: s)
    assert blend_mod._lock_retry_prompt() is True
    assert blend_mod._handover_fresh() is True
    assert blend_mod._release_unattempted_debt() is False   # not set, still today
    assert sw.today(PROMPT) == 1 and sw.today(HANDOVER) == 1 and sw.today(RELEASE) == 0
    assert sw.today_env_in_force() == {HANDOVER: 1, PROMPT: 1}
    # One of a/b must be today's: with today 1 an off/on alternation still runs.
    assert sw.validate(PROMPT, "alternate", a=1, b=0, period_s=60) is None


async def test_with_env_one_a_lock_skipped_price_is_retried_promptly(monkeypatch, clock):
    """The real switchboard, no trial, the layer off: the env alone puts the
    row-lock skip on the prompt path (cf. the trial-driven control in
    test_lock_retry_prompt_10090)."""
    monkeypatch.setenv("SPEED_SWITCH_TODAY_LOCK_RETRY_PROMPT", "1")
    x = rig(monkeypatch, count=10)
    x.r._throttle_deferred = {3, 4, 5, 6, 7, 8, 9}
    locked = {2}
    attempts = locking(x, locked)
    await x.r.refresh([2], flush_started=clock[0])
    assert x.r._lock_retry == {2}
    locked.clear()
    assert await busy_flushes(x, clock, lambda: 2 in x.committed) == 1
    assert attempts.count(2) == 2


# ── a trial still alternates, then hands back to the env value ───────────────


async def test_a_trial_overrides_the_env_in_its_window_and_returns_to_it_after_expiry(
        monkeypatch):
    monkeypatch.setenv("SPEED_SWITCH_TODAY_LOCK_RETRY_PROMPT", "1")
    monkeypatch.setenv(sw.TRIALS_ENV, "1")
    s, wall_clock = _switches({PROMPT: _alternation(a=0, b=1)}, wall=START + 30)
    await _refreshed(s)
    assert s.value(PROMPT, 0) == 0                # arm a: off, though the env says 1
    assert s.tags(5) == " sw=lock_retry_prompt:off"
    wall_clock.t = START + 90
    assert s.value(PROMPT, 0) == 1                # arm b
    wall_clock.t = START + 121                    # past its expiry, no re-read
    assert s.state(PROMPT).mode == "off"
    assert s.value(PROMPT, 0) == 1                # back to the env's today
    assert s.tags(5) == ""


async def test_a_tripped_trial_reads_the_env_value_for_the_rest_of_its_window(monkeypatch):
    monkeypatch.setenv("SPEED_SWITCH_TODAY_LOCK_RETRY_PROMPT", "1")
    monkeypatch.setenv(sw.TRIALS_ENV, "1")
    s, _ = _switches({PROMPT: _alternation(a=0, b=1)}, wall=START + 30)
    await _refreshed(s)
    assert s.value(PROMPT, 0) == 0
    s.trip(PROMPT, RuntimeError("boom"))
    assert s.value(PROMPT, 0) == 1


# ── an invalid value, or a switch with its own setting, is ignored ───────────


@pytest.mark.parametrize("raw", ["2", "-1", "yes", "on", "", " ", "1.0", "0x1", "--1"])
def test_an_invalid_env_value_is_ignored_with_one_warning(monkeypatch, caplog, raw):
    monkeypatch.setenv("SPEED_SWITCH_TODAY_LOCK_RETRY_PROMPT", raw)
    with caplog.at_level(logging.WARNING, logger=sw.logger.name):
        for _ in range(3):
            assert sw.today_env(PROMPT) is None
            assert sw.today(PROMPT) == 0
            assert blend_mod._lock_retry_prompt() is False
    warned = [r.getMessage() for r in caplog.records
              if "SPEED_SWITCH_TODAY_LOCK_RETRY_PROMPT" in r.getMessage()]
    assert len(warned) == 1 and "ignored" in warned[0]


@pytest.mark.parametrize("name, env, value", [
    ("pending_attempts", "SPEED_SWITCH_TODAY_PENDING_ATTEMPTS", "5"),
    ("admitted_debt_slots", "SPEED_SWITCH_TODAY_ADMITTED_DEBT_SLOTS", "3"),
    ("admitted_stamp_batch", "SPEED_SWITCH_TODAY_ADMITTED_STAMP_BATCH", "8"),
    ("abandon_optional_db", "SPEED_SWITCH_TODAY_ABANDON_OPTIONAL_DB", "1"),
])
def test_a_switch_with_its_own_setting_ignores_the_generic_name(
        monkeypatch, caplog, name, env, value):
    monkeypatch.setenv(env, value)
    with caplog.at_level(logging.WARNING, logger=sw.logger.name):
        assert sw.today_env(name) is None
        assert sw.today(name) == {"abandon_optional_db": 0}.get(name, 1)
        assert SpeedSwitches(read=list).value(name, 1) == 1
    assert sw.today_env_in_force() == {}
    assert blend_mod._fresh_flush_pending_attempts() == 1
    assert blend_mod._admitted_debt_slots() == 1
    assert blend_mod._admitted_stamp_batch() == 1
    assert not blend_mod.LiveBlendRefresher._optional_db_on(4)
    assert any(env in r.getMessage() and "ignored" in r.getMessage() for r in caplog.records)


def test_own_settings_name_the_real_worker_settings():
    for name, setting in sw._TODAY_SETTINGS.items():
        assert sw._OWN_SETTING[name] == setting and hasattr(blend_mod, setting)
    assert sw._OWN_SETTING["abandon_optional_db"] == blend_mod.OPTIONAL_DB_ABANDON_ENV
    assert set(sw._OWN_SETTING) <= set(sw.SWITCHES)


# ── readbacks: the admin read and the per-process start line ─────────────────


def test_the_admin_read_shows_each_switchs_effective_today(monkeypatch):
    from app.routes import admin_speed_switch

    class _Empty:
        def mget(self, keys):
            return [None] * len(keys)

    monkeypatch.setenv("ADMIN_TOKEN", "t0ken")
    monkeypatch.setenv("SPEED_SWITCH_TODAY_LOCK_RETRY_PROMPT", "1")
    monkeypatch.setattr(admin_speed_switch, "_client", lambda: _Empty())
    app = FastAPI()
    app.include_router(admin_speed_switch.router, prefix="/api")
    read = TestClient(app).get("/api/admin/speed-switch",
                               headers={"Authorization": "Bearer t0ken"}).json()
    assert read["today"][PROMPT] == 1
    assert read["today"][HANDOVER] == 0 and read["today"]["pending_attempts"] == 1
    assert set(read["today"]) == set(sw.SWITCHES)


def test_the_start_line_names_each_override_in_force(monkeypatch, caplog):
    monkeypatch.setenv("SPEED_SWITCH_TODAY_LOCK_RETRY_PROMPT", "1")
    monkeypatch.setattr(blend_mod, "_SPEED_SWITCH_LOGGED_PID", None)
    with caplog.at_level(logging.INFO, logger=blend_mod.logger.name):
        blend_mod.LiveBlendRefresher("kalshi")
    lines = [r.getMessage() for r in caplog.records if r.getMessage().startswith("speed_switch[")]
    assert lines == [f"speed_switch[pid={os.getpid()}]: layer SPEED_SWITCH_TRIALS=off "
                     "today pending_attempts=1 abandon_optional_db=0 admitted_debt_slots=1 "
                     "admitted_stamp_batch=1 lock_retry_prompt=1"]
