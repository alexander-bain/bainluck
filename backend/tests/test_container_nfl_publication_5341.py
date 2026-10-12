"""#5341 — the NFL week publication policy, the half no server is needed for.

SHIP: the next authority-defined NFL week becomes a complete usable hub without
a per-week declaration or publication command; wrong or partial weeks stay
withheld and corrected hubs stay corrected. Pillars: MATCHING / DISCOVER / TRUTH.

The stored half — the lock, the ledger, idempotency, withdrawals across a
commit, the moved-game edge, the outage — is graded on a real server in
``tests/integration/test_container_nfl_publication_5341_pg.py`` through the
mounted collection pass. This file grades what the harvest alone decides, and
that the switch is dark: with it off, or on a dry run, not one statement runs.
"""

from __future__ import annotations

import ast
import dataclasses
import inspect
import json
from datetime import datetime, timezone
from pathlib import Path
from types import SimpleNamespace

import pytest

from app.services.statpal_api import StatPalAPIService, StatPalFixture
from app.tasks.container_nfl_assembly import NflWeekHarvest, run_nfl_week_assembly
from app.utils import container_nfl_publication as pub
from app.utils.container_nfl import (
    EventRow,
    NflWeek,
    WeekMembers,
    resolve_week_members,
    select_week_contests,
)

REAL_SCHEDULE = Path(__file__).parent / "fixtures" / "statpal_nfl_season_schedule_20260903.json"
WEEK_1 = NflWeek(season=2026, week=1)


@pytest.fixture(scope="module")
def real():
    """The banked StatPal 2026 capture: Week 1 (16 games) + the Hall of Fame game."""
    return StatPalAPIService()._parse_nfl_season_schedule(json.loads(REAL_SCHEDULE.read_text()))


def _rows(fixtures, *, skip=(), twice=()):
    rows, next_id = [], 1000
    for f in fixtures:
        if not f.fixture_id or f.fixture_id in skip:
            continue
        for _ in range(2 if f.fixture_id in twice else 1):
            rows.append(
                EventRow(next_id, f.fixture_id, "scheduled", f.start_time, f.home_team, f.away_team)
            )
            next_id += 1
    return rows


def _harvest(fixtures, target=WEEK_1, *, truncated=False, **rows):
    selection = select_week_contests(fixtures, target)
    members = (
        WeekMembers()
        if selection.unavailable
        else resolve_week_members(selection, _rows(fixtures, **rows), [])
    )
    return NflWeekHarvest(selection=selection, members=members, markets_truncated=truncated)


def _week_1_ids(real):
    return [f.fixture_id for f in real if (f.round_info or "").endswith("/ Week 1")]


def _extra(fixture_id, round_info, *, home="Bears", away="Packers", home_id="h", away_id="a"):
    return StatPalFixture(
        fixture_id=fixture_id,
        home_team=home,
        away_team=away,
        home_team_id=home_id,
        away_team_id=away_id,
        start_time=datetime(2026, 9, 13, 17, tzinfo=timezone.utc),
        round_info=round_info,
    )


# --- what the harvest alone decides ---------------------------------------------------


def test_a_fully_accounted_week_passes(real):
    harvest = _harvest(real)
    assert len(harvest.selection.contests) == 16
    assert pub.harvest_refusal(harvest, WEEK_1) is None


@pytest.mark.parametrize(
    "build, reason",
    [
        (lambda real: _harvest(real, skip={_week_1_ids(real)[0]}), "contest_without_event_row"),
        (
            lambda real: _harvest(real, twice={_week_1_ids(real)[0]}),
            "contest_with_duplicate_event_rows",
        ),
        (lambda real: _harvest(real, truncated=True), "market_read_truncated"),
        (
            lambda real: _harvest(real + [_extra(_week_1_ids(real)[0], "Regular Season / Week 2")]),
            "week_contest_with_conflicting_identity",
        ),
        (lambda real: _harvest(real, NflWeek(season=2025, week=1)), "schedule_is_another_season"),
        (lambda real: _harvest(real, NflWeek(season=2026, week=9)), "week_not_in_schedule"),
        (lambda real: _harvest([]), "schedule_season_unknown"),
        (
            lambda real: _harvest(real + [_extra("", "Regular Season / Week 1")]),
            "week_slot_without_contest_id",
        ),
        (
            lambda real: _harvest(real + [_extra("", "Regular Season / Wild Card")]),
            "week_slot_without_contest_id",
        ),
        (
            lambda real: _harvest(
                real + [_extra("tbd1", "Regular Season / Week 1", home="TBD", away="TBD",
                               home_id="", away_id="")]
            ),
            "week_slot_is_placeholder",
        ),
    ],
    ids=[
        "missing-row",
        "two-rows-one-game",
        "capped-question-read",
        "also-filed-under-another-week",
        "another-season",
        "week-not-scheduled",
        "unknown-season",
        "id-less-slot-this-week",
        "id-less-slot-unplaceable",
        "placeholder-this-week",
    ],
)
def test_every_partial_or_unknowable_week_refuses(real, build, reason):
    assert pub.harvest_refusal(build(real), WEEK_1) == reason


def test_a_placeholder_in_another_round_does_not_hold_this_week(real):
    bracket = _extra("tbd2", "Post Season / Week 1", home="TBD", away="TBD", home_id="", away_id="")
    assert pub.harvest_refusal(_harvest(real + [bracket]), WEEK_1) is None


def test_completeness_is_the_contest_set_never_a_count(real):
    """Same number of member games as contests, one game swapped: refused.

    A count-based rule would pass this — 16 games for 16 contests — while the
    hub held another week's game in place of one of this week's.
    """
    harvest = _harvest(real)
    swapped = dict(harvest.members.games[0], statpal_id="not-this-week")
    harvest.members.games[0] = swapped
    assert len(harvest.members.games) == len(harvest.selection.contests)
    assert pub.harvest_refusal(harvest, WEEK_1) == "contests_not_exactly_members"


def test_two_games_on_one_event_row_is_not_sixteen_members(real):
    harvest = _harvest(real)
    candidates = harvest.members.candidates
    first, second = [i for i, c in enumerate(candidates) if c.child_type == "event"][:2]
    candidates[second] = dataclasses.replace(
        candidates[second], child_id=candidates[first].child_id
    )
    assert pub.harvest_refusal(harvest, WEEK_1) == "contests_not_exactly_members"


# --- dark: off and dry runs issue no statement -----------------------------------------


class _Refuses:
    async def execute(self, *a, **k):
        raise AssertionError("the publication policy issued a statement")


@pytest.mark.parametrize("value", [None, "", "false", "0", "off", "no", "nope"])
def test_the_switch_is_off_unless_set_truthy(monkeypatch, value):
    if value is None:
        monkeypatch.delenv(pub.AUTO_PUBLISH_ENV, raising=False)
    else:
        monkeypatch.setenv(pub.AUTO_PUBLISH_ENV, value)
    assert pub.auto_publish_enabled() is False


@pytest.mark.parametrize("value", ["true", "TRUE", " 1 ", "yes", "on"])
def test_the_switch_reads_truthy_at_call_time(monkeypatch, value):
    monkeypatch.setenv(pub.AUTO_PUBLISH_ENV, value)
    assert pub.auto_publish_enabled() is True


def test_it_is_not_the_assembly_switch():
    from app.tasks.container_assembly import COLLECTIONS_ENABLED_ENV

    assert pub.AUTO_PUBLISH_ENV != COLLECTIONS_ENABLED_ENV


@pytest.mark.asyncio
async def test_switch_off_reports_the_harvest_verdict_and_touches_nothing(real, monkeypatch):
    monkeypatch.delenv(pub.AUTO_PUBLISH_ENV, raising=False)
    report = await pub.publish_complete_week(
        _Refuses(), SimpleNamespace(id=7, slug=WEEK_1.slug), WEEK_1, _harvest(real), {}, apply=True
    )
    assert report["decision"] == pub.DECISION_DISABLED
    assert report["harvest_complete"] is True
    assert report["policy"] == pub.POLICY


@pytest.mark.asyncio
@pytest.mark.parametrize("apply, container_id", [(False, 7), (True, None)])
async def test_a_dry_run_or_a_stand_in_row_touches_nothing(real, monkeypatch, apply, container_id):
    monkeypatch.setenv(pub.AUTO_PUBLISH_ENV, "true")
    report = await pub.publish_complete_week(
        _Refuses(),
        SimpleNamespace(id=container_id, slug=WEEK_1.slug),
        WEEK_1,
        _harvest(real, skip={_week_1_ids(real)[0]}),
        None,
        apply=apply,
    )
    assert report["decision"] == pub.DECISION_NOT_APPLIED
    assert report["harvest_refusal"] == "contest_without_event_row"


@pytest.mark.asyncio
async def test_the_mounted_week_run_carries_the_decision_on_an_unreadable_week(monkeypatch):
    """The task hook runs on the unavailable path too, and still touches nothing."""
    monkeypatch.delenv(pub.AUTO_PUBLISH_ENV, raising=False)
    report = await run_nfl_week_assembly(
        _Refuses(), SimpleNamespace(id=7, slug=WEEK_1.slug), [], WEEK_1, apply=True
    )
    assert report["terminal"] == "unavailable"
    assert report["publication"]["decision"] == pub.DECISION_DISABLED
    assert report["publication"]["harvest_refusal"] == "schedule_season_unknown"


# --- what it may write, read off its source ------------------------------------------------


def test_the_only_correction_it_calls_is_publish():
    """It never withdraws, unpublishes or readmits: those stay named decisions."""
    tree = ast.parse(inspect.getsource(pub))
    called = {
        node.func.attr if isinstance(node.func, ast.Attribute) else getattr(node.func, "id", None)
        for node in ast.walk(tree)
        if isinstance(node, ast.Call)
    }
    assert "publish_container" in called
    for forbidden in ("withdraw_publication", "withdraw_member", "readmit_member", "commit"):
        assert forbidden not in called, forbidden
    statements = [
        n.value for n in ast.walk(tree) if isinstance(n, ast.Constant) and isinstance(n.value, str)
    ]
    for sql in statements:
        assert not any(verb in sql.upper().split() for verb in ("UPDATE", "INSERT", "DELETE")), sql


def test_the_actor_fits_the_ledger_and_names_no_person():
    assert 0 < len(pub.ACTOR) <= 64
    assert pub.ACTOR.startswith("auto:")
