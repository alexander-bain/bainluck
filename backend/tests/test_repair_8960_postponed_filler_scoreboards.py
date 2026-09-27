"""#8960 — the repair that takes the filler 0-0 off three postponed matches.

The repair is a D51(b) production write, so the policy lives in pure per-row
functions and is pinned here: which rows may be blanked, which snapshots may be
deleted, which app may run it, and what the restore will and will not put back.
"""

from __future__ import annotations

import importlib.util
import sys
from datetime import datetime, timezone
from pathlib import Path

import pytest

_SCRIPTS = Path(__file__).resolve().parents[1] / "scripts"


def _load(name: str):
    """Import a `scripts/` module by path (same seam as the #8247 test)."""
    sys.path.insert(0, str(_SCRIPTS))
    spec = importlib.util.spec_from_file_location(name, _SCRIPTS / f"{name}.py")
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


repair = _load("repair_8960_postponed_filler_scoreboards")
restore = _load("restore_8960_postponed_filler_scoreboards")

#: /events/15315470, Crawley Town v Barnet, ESPN 401881358 STATUS_POSTPONED.
SPECIMEN = 15315470
SPECIMEN_ESPN = "401881358"
SPECIMEN_SNAPSHOT = 398937


def _row(**kw):
    base = {
        "id": SPECIMEN,
        "status": "suspended",
        "completed_at": None,
        "espn_id": SPECIMEN_ESPN,
        "period": "Postponed",
        "home_score": 0,
        "away_score": 0,
    }
    base.update(kw)
    return base


def _snap(**kw):
    base = {
        "id": SPECIMEN_SNAPSHOT,
        "event_id": SPECIMEN,
        "captured_at": datetime(2026, 9, 26, 13, 59, 55, tzinfo=timezone.utc),
        "home_score": 0,
        "away_score": 0,
    }
    base.update(kw)
    return base


def _banked(**kw):
    base = {
        "id": SPECIMEN,
        "prior_home_score": 0,
        "prior_away_score": 0,
        "status": "suspended",
        "completed_at": None,
        "home_score": None,
        "away_score": None,
    }
    base.update(kw)
    return base


# ---------------------------------------------------------------------------
# the event half
# ---------------------------------------------------------------------------


def test_the_pinned_population_is_the_three_measured_rows():
    assert {row[0] for row in repair.EXPECTED} == {15314000, 15315470, 15315471}
    assert all((row[2], row[3]) == (0, 0) for row in repair.EXPECTED)


def test_the_specimen_in_its_measured_shape_is_writable():
    assert repair.row_is_writable(_row()) is None


def test_every_pinned_row_in_its_measured_shape_is_writable():
    for eid, espn_id, home, away in repair.EXPECTED:
        row = _row(id=eid, espn_id=espn_id, home_score=home, away_score=away)
        assert repair.row_is_writable(row) is None, eid


def test_a_row_outside_the_pinned_population_is_never_written():
    assert repair.row_is_writable(_row(id=15315472)) == "not in the pinned population"


def test_a_row_that_resumed_is_refused():
    assert "status moved" in repair.row_is_writable(_row(status="live"))


def test_a_row_that_settled_is_refused():
    why = repair.row_is_writable(
        _row(completed_at=datetime(2026, 9, 30, tzinfo=timezone.utc))
    )
    assert "settled" in why


def test_a_row_whose_anchor_changed_is_refused():
    assert "espn_id" in repair.row_is_writable(_row(espn_id="999"))
    assert "espn_id" in repair.row_is_writable(_row(espn_id=None))


def test_a_row_no_longer_carrying_the_stoppage_word_is_refused():
    assert "period" in repair.row_is_writable(_row(period="1st Half"))
    assert "period" in repair.row_is_writable(_row(period=None))


def test_a_canceled_word_is_still_the_stoppage():
    assert repair.row_is_writable(_row(period="Canceled")) is None


def test_a_row_carrying_a_real_score_is_refused():
    assert "drifted" in repair.row_is_writable(_row(home_score=1))


def test_an_already_repaired_row_is_a_no_op():
    assert repair.row_is_writable(
        _row(home_score=None, away_score=None)
    ) == "already repaired"


# ---------------------------------------------------------------------------
# the chart half
# ---------------------------------------------------------------------------


def test_the_pinned_snapshots_are_one_per_pinned_event():
    assert sorted(s[1] for s in repair.EXPECTED_SNAPSHOTS) == sorted(
        e[0] for e in repair.EXPECTED
    )


def test_the_specimens_snapshot_is_deletable_when_its_event_was_repaired():
    assert repair.snapshot_is_deletable(_snap(), {SPECIMEN}) is None


def test_a_snapshot_whose_event_was_skipped_is_never_deleted():
    assert "not repaired" in repair.snapshot_is_deletable(_snap(), set())


def test_a_snapshot_outside_the_pin_is_never_deleted():
    assert repair.snapshot_is_deletable(
        _snap(id=1), {SPECIMEN}
    ) == "not in the pinned population"


def test_a_snapshot_carrying_a_real_score_is_never_deleted():
    assert "drifted" in repair.snapshot_is_deletable(_snap(away_score=2), {SPECIMEN})


def test_a_snapshot_on_another_event_is_never_deleted():
    why = repair.snapshot_is_deletable(_snap(event_id=15315471), {15315471})
    assert "belongs to event" in why


# ---------------------------------------------------------------------------
# the app guard, shared by import
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("app", [None, "", "bainluck", "bainluck-staging"])
def test_the_repair_refuses_every_app_but_the_named_one(app, monkeypatch):
    if app is None:
        monkeypatch.delenv("HEROKU_APP_NAME", raising=False)
    else:
        monkeypatch.setenv("HEROKU_APP_NAME", app)
    assert repair.wrong_app_refusal() is not None


def test_the_named_app_is_permitted(monkeypatch):
    monkeypatch.setenv("HEROKU_APP_NAME", "bainluck-heavy")
    assert repair.wrong_app_refusal() is None


def test_the_restore_shares_the_repairs_guard_and_banks_by_import():
    assert restore.wrong_app_refusal is repair.wrong_app_refusal
    assert restore.BACKUP_TABLE == repair.BACKUP_TABLE
    assert restore.SNAPSHOT_BACKUP_TABLE == repair.SNAPSHOT_BACKUP_TABLE
    assert repair.BACKUP_TABLE != repair.SNAPSHOT_BACKUP_TABLE


def test_the_repair_refuses_to_apply_off_the_named_app(monkeypatch, capsys):
    import asyncio

    monkeypatch.setenv("HEROKU_APP_NAME", "bainluck")
    assert asyncio.run(repair.run(apply=True)) == 2
    assert "REFUSED" in capsys.readouterr().out


# ---------------------------------------------------------------------------
# the restore
# ---------------------------------------------------------------------------


def test_a_repaired_row_is_restorable():
    assert restore.classify(_banked()) == restore.RESTORE


def test_a_row_that_took_a_real_score_after_the_repair_is_diverged():
    assert restore.classify(_banked(home_score=2, away_score=1)) == restore.DIVERGED


def test_a_row_that_settled_after_the_repair_is_diverged():
    assert restore.classify(
        _banked(completed_at=datetime(2026, 9, 30, tzinfo=timezone.utc))
    ) == restore.DIVERGED


def test_a_row_that_resumed_after_the_repair_is_diverged():
    assert restore.classify(_banked(status="live")) == restore.DIVERGED


def test_a_row_already_holding_the_pre_image_is_a_no_op():
    assert restore.classify(_banked(home_score=0, away_score=0)) == restore.ALREADY_BACK
