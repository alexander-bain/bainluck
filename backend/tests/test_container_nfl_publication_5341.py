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


LIMIT = 200


def _harvest(fixtures, target=WEEK_1, *, truncated=False, unidentified=(), **rows):
    selection = select_week_contests(fixtures, target)
    members = (
        WeekMembers()
        if selection.unavailable
        else resolve_week_members(selection, _rows(fixtures, **rows), [])
    )
    harvest = NflWeekHarvest(
        selection=selection,
        members=members,
        markets_truncated=truncated,
        unidentified_in_span=list(unidentified),
    )
    harvest.read = list(fixtures)  # the schedule read it was cut from
    return harvest


def _refusal(harvest, target=WEEK_1):
    return pub.harvest_refusal(harvest, target, harvest.read, unidentified_limit=LIMIT)


def _week_1_ids(real):
    return [f.fixture_id for f in real if (f.round_info or "").endswith("/ Week 1")]


SEP_13 = datetime(2026, 9, 13, 17, tzinfo=timezone.utc)


def _extra(
    fixture_id,
    round_info,
    *,
    home="Bears",
    away="Packers",
    home_id="h",
    away_id="a",
    start=SEP_13,
):
    return StatPalFixture(
        fixture_id=fixture_id,
        home_team=home,
        away_team=away,
        home_team_id=home_id or "",
        away_team_id=away_id or "",
        start_time=start,
        round_info=round_info,
    )


# --- what the harvest alone decides ---------------------------------------------------


def test_a_fully_accounted_week_passes(real):
    harvest = _harvest(real)
    assert len(harvest.selection.contests) == 16
    assert _refusal(harvest) is None


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
    assert _refusal(build(real)) == reason


def test_a_placeholder_in_another_round_does_not_hold_this_week(real):
    bracket = _extra("tbd2", "Post Season / Week 1", home="TBD", away="TBD", home_id="", away_id="")
    assert _refusal(_harvest(real + [bracket])) is None


def test_completeness_is_the_contest_set_never_a_count(real):
    """Same number of member games as contests, one game swapped: refused.

    A count-based rule would pass this — 16 games for 16 contests — while the
    hub held another week's game in place of one of this week's.
    """
    harvest = _harvest(real)
    swapped = dict(harvest.members.games[0], statpal_id="not-this-week")
    harvest.members.games[0] = swapped
    assert len(harvest.members.games) == len(harvest.selection.contests)
    assert _refusal(harvest) == "contests_not_exactly_members"


def test_two_games_on_one_event_row_is_not_sixteen_members(real):
    harvest = _harvest(real)
    candidates = harvest.members.candidates
    first, second = [i for i, c in enumerate(candidates) if c.child_type == "event"][:2]
    candidates[second] = dataclasses.replace(
        candidates[second], child_id=candidates[first].child_id
    )
    assert _refusal(harvest) == "contests_not_exactly_members"


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
        _Refuses(),
        SimpleNamespace(id=7, slug=WEEK_1.slug),
        WEEK_1,
        _harvest(real),
        {},
        fixtures=real,
        unidentified_limit=LIMIT,
        apply=True,
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
        fixtures=real,
        unidentified_limit=LIMIT,
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


# --- D2: an id with an unreadable round may be this week's (Authority 10/12) ---------


def _at(y, m, d, h=17, minute=0):
    return datetime(y, m, d, h, minute, tzinfo=timezone.utc)


def test_an_id_bearing_contest_with_an_unreadable_round_inside_the_week_refuses(real):
    first = min(f.start_time for f in real if (f.round_info or "").endswith("/ Week 1"))
    odd = _extra("w1x", "Regular Season / Week One", start=first)
    assert _refusal(_harvest(real + [odd])) == "week_slot_without_week_identity"


def test_an_unreadable_round_with_no_known_kickoff_refuses(real):
    odd = _extra("w1y", "Regular Season / Week One", start=None)
    assert _refusal(_harvest(real + [odd])) == "week_slot_without_week_identity"


def test_the_hall_of_fame_game_does_not_hold_preseason_week_1(real):
    preseason = NflWeek(season=2026, week=1, stage="Pre Season")
    week = [
        _extra(f"p1{i}", "Pre Season / Week 1", home=f"H{i}", away=f"A{i}",
               home_id=f"h{i}", away_id=f"a{i}", start=_at(2026, 8, 13 + i, 23))
        for i in range(3)
    ]
    harvest = _harvest(real + week, preseason)
    hof = harvest.selection.excluded["no_week_identity"]
    assert [r["round"] for r in hof] == ["Pre Season / Hall of Fame Weekend"]
    assert _refusal(harvest, preseason) is None


def _week_18_and_wild_card():
    week_18 = [
        _extra(f"r18{i}", "Regular Season / Week 18", home=f"H{i}", away=f"A{i}",
               home_id=f"h{i}", away_id=f"a{i}", start=_at(2027, 1, 3, 18 + i))
        for i in range(3)
    ]
    wild_card = _extra("wc1", "Post Season / Wild Card", home="Bills", away="Steelers",
                       home_id="hb", away_id="as", start=_at(2027, 1, 9, 21, 30))
    return week_18, wild_card


def test_a_known_wild_card_kickoff_does_not_hold_week_18(real):
    week_18, wild_card = _week_18_and_wild_card()
    target = NflWeek(season=2026, week=18)
    assert _refusal(_harvest(real + week_18 + [wild_card], target), target) is None


def test_the_bound_bites_a_day_after_the_weeks_last_game(real):
    week_18, _ = _week_18_and_wild_card()
    target = NflWeek(season=2026, week=18)
    odd = _extra("r18x", "Regular Season / Week Eighteen", start=_at(2027, 1, 4, 20))
    assert _refusal(_harvest(real + week_18 + [odd], target), target) == (
        "week_slot_without_week_identity"
    )


# --- D4: our own stamped row in the span says the read is short ---------------------


def _row(statpal_id):
    return {"event_id": 1, "statpal_fixture_id": statpal_id, "teams": ["A", "B"]}


def test_a_stamped_row_whose_contest_the_read_omits_refuses(real):
    harvest = _harvest(real, unidentified=[_row("999999")])
    assert _refusal(harvest) == "stamped_game_missing_from_schedule"


@pytest.mark.parametrize("statpal_id", [None, "", "280493"], ids=["unstamped", "blank", "other-week"])
def test_unstamped_rows_and_other_week_contests_stay_report_only(real, statpal_id):
    """280493 is the banked Hall of Fame contest: in the read, filed elsewhere."""
    assert _refusal(_harvest(real, unidentified=[_row(statpal_id)])) is None


def test_a_capped_read_of_our_in_span_rows_refuses(real):
    harvest = _harvest(real, unidentified=[_row(None)] * LIMIT)
    assert _refusal(harvest) == "unidentified_read_truncated"
    harvest = _harvest(real, unidentified=[_row(None)] * (LIMIT - 1))
    assert _refusal(harvest) is None


def test_the_omission_checks_cannot_be_skipped_by_leaving_out_the_read():
    params = inspect.signature(pub.harvest_refusal).parameters
    assert params["fixtures"].default is inspect.Parameter.empty
    assert params["unidentified_limit"].default is inspect.Parameter.empty
    hook = inspect.signature(pub.publish_complete_week).parameters
    assert hook["fixtures"].default is inspect.Parameter.empty
