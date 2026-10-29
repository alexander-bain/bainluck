"""#10090 — the owed-stamp catch-up budget is a setting, not a release.

`FRESH_FLUSH_PENDING_ATTEMPTS` and `PENDING_STAMP_BUDGET_S` are read from the
environment once at import, so each value is tried with one config change.
Missing keeps today's behaviour (1 and 1.0); invalid keeps the default and
warns; out of range is clamped. The module names stay, so references and
monkeypatches keep working.
"""

import json
import logging
import os
import subprocess
import sys
from pathlib import Path

import pytest

import app.tasks.live_blend_refresh as lbr
from tests.test_ws_flush_cadence_10090 import _Recording

BACKEND = Path(__file__).resolve().parents[1]
NAMES = ("FRESH_FLUSH_PENDING_ATTEMPTS", "PENDING_STAMP_BUDGET_S")


def _attempts(monkeypatch, raw):
    monkeypatch.setenv("FRESH_FLUSH_PENDING_ATTEMPTS", raw)
    return lbr._owed_budget_env("FRESH_FLUSH_PENDING_ATTEMPTS", 1, int, 1, 32)


def _budget(monkeypatch, raw):
    monkeypatch.setenv("PENDING_STAMP_BUDGET_S", raw)
    return lbr._owed_budget_env("PENDING_STAMP_BUDGET_S", 1.0, float, 0.25, 5.0)


def _imported_values(env_overrides):
    """The module's values as a fresh interpreter imports them."""
    env = {k: v for k, v in os.environ.items() if k not in NAMES}
    env.update(env_overrides)
    out = subprocess.run(
        [
            sys.executable,
            "-c",
            "import json, app.tasks.live_blend_refresh as m; print(json.dumps("
            "[m.FRESH_FLUSH_PENDING_ATTEMPTS, m.PENDING_STAMP_BUDGET_S]))",
        ],
        cwd=BACKEND,
        env=env,
        capture_output=True,
        text=True,
        timeout=120,
        check=True,
    )
    return tuple(json.loads(out.stdout.strip().splitlines()[-1])), out.stderr


def test_missing_env_is_todays_behaviour_at_import():
    (attempts, budget), _ = _imported_values({})
    assert (attempts, budget) == (1, 1.0)
    assert type(attempts) is int


def test_env_override_is_honoured_at_import():
    (attempts, budget), _ = _imported_values(
        {"FRESH_FLUSH_PENDING_ATTEMPTS": "8", "PENDING_STAMP_BUDGET_S": "2.5"}
    )
    assert (attempts, budget) == (8, 2.5)


def test_invalid_env_at_import_is_the_default_with_a_warning():
    (attempts, budget), stderr = _imported_values(
        {"FRESH_FLUSH_PENDING_ATTEMPTS": "three", "PENDING_STAMP_BUDGET_S": "nan"}
    )
    assert (attempts, budget) == (1, 1.0)
    assert "FRESH_FLUSH_PENDING_ATTEMPTS='three'" in stderr
    assert "PENDING_STAMP_BUDGET_S='nan'" in stderr


@pytest.mark.parametrize("raw", ["", "   "])
def test_blank_is_missing(monkeypatch, caplog, raw):
    with caplog.at_level(logging.WARNING, logger=lbr.logger.name):
        assert _attempts(monkeypatch, raw) == 1
        assert _budget(monkeypatch, raw) == 1.0
    assert not caplog.records


@pytest.mark.parametrize("raw", ["three", "3.0", "1e2", "0x3"])
def test_invalid_attempts_is_default_with_one_warning(monkeypatch, caplog, raw):
    with caplog.at_level(logging.WARNING, logger=lbr.logger.name):
        assert _attempts(monkeypatch, raw) == 1
    assert len(caplog.records) == 1
    assert "not a valid int" in caplog.records[0].getMessage()


@pytest.mark.parametrize("raw", ["fast", "nan", "inf", "-inf"])
def test_invalid_budget_is_default_with_one_warning(monkeypatch, caplog, raw):
    with caplog.at_level(logging.WARNING, logger=lbr.logger.name):
        assert _budget(monkeypatch, raw) == 1.0
    assert len(caplog.records) == 1
    assert "not a valid float" in caplog.records[0].getMessage()


@pytest.mark.parametrize(
    "raw, expected",
    [("0", 1), ("-4", 1), ("1", 1), (" 3 ", 3), ("32", 32), ("33", 32), ("1000", 32)],
)
def test_attempts_clamps_to_1_through_32(monkeypatch, raw, expected):
    value = _attempts(monkeypatch, raw)
    assert value == expected and type(value) is int


@pytest.mark.parametrize(
    "raw, expected",
    [
        ("0", 0.25), ("0.1", 0.25), ("0.25", 0.25), ("1.5", 1.5),
        ("5", 5.0), ("5.01", 5.0), ("60", 5.0),
    ],
)
def test_budget_clamps_to_quarter_through_five_seconds(monkeypatch, raw, expected):
    assert _budget(monkeypatch, raw) == expected


def test_a_clamp_warns_once(monkeypatch, caplog):
    with caplog.at_level(logging.WARNING, logger=lbr.logger.name):
        assert _attempts(monkeypatch, "99") == 32
    assert len(caplog.records) == 1
    assert "outside [1, 32]" in caplog.records[0].getMessage()


def test_effective_values_are_logged_once_per_process(monkeypatch, caplog):
    monkeypatch.setattr(lbr, "_OWED_BUDGET_LOGGED", False)
    with caplog.at_level(logging.INFO, logger=lbr.logger.name):
        lbr.LiveBlendRefresher("kalshi")
        lbr.LiveBlendRefresher("kalshi")
    lines = [r.getMessage() for r in caplog.records if "owed-stamp budget" in r.getMessage()]
    assert lines == [
        "live_blend_refresh[kalshi]: owed-stamp budget "
        f"FRESH_FLUSH_PENDING_ATTEMPTS={lbr.FRESH_FLUSH_PENDING_ATTEMPTS} "
        f"PENDING_STAMP_BUDGET_S={lbr.PENDING_STAMP_BUDGET_S:.3g} "
        f"ADMITTED_DEBT_SLOTS={lbr.ADMITTED_DEBT_SLOTS}"
    ]


async def _prepared(event_ids):
    return {}


async def test_a_raised_attempt_count_stamps_that_many_old_events_after_fresh(monkeypatch):
    """The module name is still the one the refresher reads."""
    clock = {"t": 1000.0}
    monkeypatch.setattr(lbr, "_mono", lambda: clock["t"])
    monkeypatch.setattr(lbr, "FRESH_FLUSH_PENDING_ATTEMPTS", 3)
    r = _Recording(min_refresh_interval_s=0)
    r._prepare_groups = _prepared
    r.adopt_pending(range(1, 9))
    await r.refresh([99], flush_started=1000)
    assert [ids for ids, _ in r.batches] == [[99], [1], [2], [3]]
    assert r.pending_event_ids() == frozenset(range(4, 9))


async def test_the_time_budget_still_stops_a_large_attempt_count(monkeypatch):
    """Above 1 attempt the old work is serial and the time budget is checked
    before each stamp, so 32 attempts at a 1 s budget stop when it is spent."""
    clock = {"t": 1000.0}
    monkeypatch.setattr(lbr, "_mono", lambda: clock["t"])
    monkeypatch.setattr(lbr, "FRESH_FLUSH_PENDING_ATTEMPTS", 32)
    monkeypatch.setattr(lbr, "PENDING_STAMP_BUDGET_S", 1.0)
    r = _Recording(min_refresh_interval_s=0)
    r._prepare_groups = _prepared
    original = r._refresh_batch

    async def slow(event_ids, now, **kwargs):
        await original(event_ids, now, **kwargs)
        if 99 not in event_ids:
            clock["t"] += 0.4  # each old stamp costs 0.4 s

    r._refresh_batch = slow
    r.adopt_pending(range(1, 9))
    await r.refresh([99], flush_started=1000)
    # 0.0, 0.4, 0.8 elapsed before stamps 1-3 start; 1.2 >= 1.0 stops stamp 4.
    assert [ids for ids, _ in r.batches] == [[99], [1], [2], [3]]
    assert r.pending_event_ids() == frozenset(range(4, 9))
