"""The NFL stamper's decision, driven by a REAL StatPal payload. #2867 / D50.

`app/tasks/stamp_nfl_statpal_fixtures.classify_fixture` is the whole judgement the
task makes: which of our rows, if any, is this StatPal contest, and what state is
that row in. It is pure — no session, no clock, no network — so these tests drive
the code that runs rather than a mock that agrees with whatever it is told.

## the corpus is a real response, and the rows are real rows

`tests/fixtures/statpal_nfl_season_schedule_20260903.json` is the actual
`/v1/nfl/season-schedule` body of 2026-09-03 (Pre Season + Regular Season Week 1),
parsed through the same `_parse_nfl_season_schedule` production uses — including
the three shapes that parser exists for: games two levels down under
`stage → week → matches`, a day wrapper whose `match` may be a dict or a list, and
a game keyed `contestid` rather than `id`.

The event rows are production as it stood 2026-09-04, including:

  * the 16 Week-1 rows whose kickoffs agree with StatPal to the minute;
  * the two **Los Angeles phantoms** — `Los Angeles Rams v Arizona Cardinals` at
    the Chargers' 2026-09-13 20:25 kickoff, and `Los Angeles Chargers v
    San Francisco 49ers` at the Rams' 2026-09-11 00:35 — which StatPal does not
    have and which no rule here may link;
  * a preseason row carrying the fabricated
    `statpal_live_Buffalo Bills_Pittsburgh Steelers` (#2963).

## what each test can fail on

* the parser reading the payload at all (NFL nests two levels deeper than NBA);
* the ±1h window being read from the wrong side of the comparison;
* a phantom being linked because the rule got looser;
* a polluted row being treated as linkable, which would write a `game` anchor
  keyed on team names;
* an already-linked row being reported as a miss — the CERT-871 follow-up class,
  built in here from the start rather than learned again.
"""

from __future__ import annotations

import json
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest

from app.services.statpal_api import StatPalAPIService
from app.tasks.stamp_nfl_statpal_fixtures import (
    MATCH_WINDOW,
    NFL_SPORT_KEY,
    VERDICT_ALREADY_LINKED,
    VERDICT_AMBIGUOUS,
    VERDICT_POLLUTED,
    VERDICT_STAMP,
    VERDICT_UNMATCHED,
    classify_fixture,
    is_statpal_contest_id,
)
from app.utils.provider_anchor_keys import (
    ANCHOR_KIND_GAME,
    SOURCE_STATPAL,
    statpal_anchor_key,
    statpal_id_space,
)

FIXTURES_DIR = Path(__file__).parent / "fixtures"
FIXTURE = FIXTURES_DIR / "statpal_nfl_season_schedule_20260903.json"
#: The other arm the task reads. Pinned too, because the preseason games that
#: carry the #2963 fabricated ids are here and not in the season schedule.
LIVE_FIXTURE = FIXTURES_DIR / "statpal_nfl_livescores_20260903.json"


def _service():
    return StatPalAPIService.__new__(StatPalAPIService)  # no HTTP client needed


def _fixtures():
    return _service()._parse_nfl_season_schedule(json.loads(FIXTURE.read_text()))


def _live_fixtures():
    return _service()._parse_fixtures(json.loads(LIVE_FIXTURE.read_text()), "nfl")


def _by_id(contest_id: str):
    for f in list(_fixtures()) + list(_live_fixtures()):
        if f.fixture_id == contest_id:
            return f
    raise AssertionError(f"contest {contest_id} not in the pinned payloads")


def _row(event_id, home, away, when, statpal_fixture_id=None, status="scheduled"):
    return {
        "id": event_id,
        "home": home,
        "away": away,
        "commence_time": when,
        "statpal_fixture_id": statpal_fixture_id,
        "status": status,
    }


def _utc(text: str) -> datetime:
    return datetime.fromisoformat(text).replace(tzinfo=timezone.utc)


# --- the corpus itself, checked first ------------------------------------------
# A drifted or truncated fixture must fail as a CORPUS problem, not slip through
# as a silent 0-of-0 pass on every test below.


def test_the_pinned_payload_still_parses():
    fixtures = _fixtures()
    assert len(fixtures) >= 17, f"payload shrank to {len(fixtures)} fixtures"
    assert all(f.fixture_id and f.fixture_id.isdigit() for f in fixtures)
    assert all(f.start_time is not None for f in fixtures)
    assert all(f.home_team and f.away_team for f in fixtures)
    # `contestid`, not `id` — the whole reason NFL needs its own parser.
    assert _by_id("280445").home_team == "Seattle Seahawks"
    assert _by_id("280445").away_team == "New England Patriots"

    live = _live_fixtures()
    assert len(live) >= 4, f"livescores payload shrank to {len(live)} fixtures"
    assert all(f.fixture_id and f.fixture_id.isdigit() for f in live)


# --- the happy path ------------------------------------------------------------


def test_a_week_one_game_finds_its_row():
    """Both names exact, kickoff to the minute — the 16-of-16 case."""
    fixture = _by_id("280445")
    pool = [
        _row(14780138, "Seattle Seahawks", "New England Patriots",
             _utc("2026-09-10T00:20:00")),
        _row(14632820, "Los Angeles Rams", "San Francisco 49ers",
             _utc("2026-09-11T00:35:00")),
    ]
    verdict, matches = classify_fixture(fixture, pool)
    assert verdict == VERDICT_STAMP
    assert [m["id"] for m in matches] == [14780138]


def test_the_anchor_key_this_stamp_would_write():
    """`americanfootball_nfl:280445`, `game` — the D55 shape, asserted end to end.

    The task builds the key from `statpal_id_space(NFL_SPORT_KEY)`, so this pins
    the composition rather than a hand-written string: NFL is 1:1 with StatPal's
    `nfl`, so our `sports.key` IS the id space, and a 6-digit `contestid` must not
    fall back into MLB's legacy `s6:` namespace.
    """
    key = statpal_anchor_key("280445", statpal_id_space(NFL_SPORT_KEY))
    assert key is not None
    assert key.source == SOURCE_STATPAL
    assert key.source_id == "americanfootball_nfl:280445"
    assert key.id_kind == ANCHOR_KIND_GAME
    assert key.may_anchor_absorption is True
    # The pre-D55 digit rule would have filed this 6-digit id under MLB's space.
    assert not key.source_id.startswith("s6:")


# --- the window ----------------------------------------------------------------


@pytest.mark.parametrize("skew_minutes", [0, 30, 59, -59, -30])
def test_a_kickoff_inside_the_window_still_matches(skew_minutes):
    fixture = _by_id("280445")
    pool = [
        _row(14780138, "Seattle Seahawks", "New England Patriots",
             fixture.start_time + timedelta(minutes=skew_minutes))
    ]
    assert classify_fixture(fixture, pool)[0] == VERDICT_STAMP


@pytest.mark.parametrize("skew_hours", [2, -2, 24, -24])
def test_a_kickoff_outside_the_window_is_a_different_game(skew_hours):
    """Two teams meet twice a season. A two-hour gap is evidence, not noise."""
    fixture = _by_id("280445")
    pool = [
        _row(14780138, "Seattle Seahawks", "New England Patriots",
             fixture.start_time + timedelta(hours=skew_hours))
    ]
    assert classify_fixture(fixture, pool)[0] == VERDICT_UNMATCHED


def test_the_window_is_an_hour_and_that_is_deliberate():
    """A guard against someone widening it to "fix" a miss (see the docstring)."""
    assert MATCH_WINDOW == timedelta(hours=1)


# --- the phantoms --------------------------------------------------------------


def test_the_los_angeles_phantom_is_not_linked():
    """Real production shape: two of our rows, one StatPal contest, one is wrong.

    StatPal has only `Arizona Cardinals @ Los Angeles Chargers` at 20:25. We hold
    a Rams row at the same minute. Exact naming links the Chargers row and leaves
    the Rams row untouched — and, crucially, this is NOT an ambiguity: only one
    of the two can match, so the finding surfaces as an unclaimed row rather than
    as a coin flip.
    """
    fixture = _by_id("280456")
    assert (fixture.home_team, fixture.away_team) == (
        "Los Angeles Chargers", "Arizona Cardinals"
    )
    pool = [
        _row(14780147, "Los Angeles Chargers", "Arizona Cardinals",
             _utc("2026-09-13T20:25:00")),
        _row(14781140, "Los Angeles Rams", "Arizona Cardinals",
             _utc("2026-09-13T20:25:00")),  # phantom, #2693
    ]
    verdict, matches = classify_fixture(fixture, pool)
    assert verdict == VERDICT_STAMP
    assert [m["id"] for m in matches] == [14780147]


def test_the_second_los_angeles_phantom_is_not_linked():
    """The 2026-09-11 pair: `Rams v 49ers` is real, `Chargers v 49ers` is not."""
    fixture = _by_id("280446")
    pool = [
        _row(14632820, "Los Angeles Rams", "San Francisco 49ers",
             _utc("2026-09-11T00:35:00")),
        _row(14780595, "Los Angeles Chargers", "San Francisco 49ers",
             _utc("2026-09-11T00:35:00")),  # phantom, #2693
    ]
    verdict, matches = classify_fixture(fixture, pool)
    assert verdict == VERDICT_STAMP
    assert [m["id"] for m in matches] == [14632820]


def test_two_identical_rows_are_reported_not_resolved():
    """A genuine duplicate: same teams, same kickoff, two ids. D35 — file it."""
    fixture = _by_id("280445")
    pool = [
        _row(14780138, "Seattle Seahawks", "New England Patriots",
             _utc("2026-09-10T00:20:00")),
        _row(99999999, "Seattle Seahawks", "New England Patriots",
             _utc("2026-09-10T00:20:00")),
    ]
    verdict, matches = classify_fixture(fixture, pool)
    assert verdict == VERDICT_AMBIGUOUS
    assert sorted(m["id"] for m in matches) == [14780138, 99999999]


# --- the polluted column (#2963) -----------------------------------------------


@pytest.mark.parametrize(
    "value,expected",
    [
        ("280445", True),
        ("354453", True),
        ("13291000001", True),
        ("statpal_live_Buffalo Bills_Pittsburgh Steelers", False),
        ("statpal_live_", False),
        ("", False),
        ("   ", False),
        (None, False),
        ("280445 ", True),  # whitespace only
        ("28-0445", False),
    ],
)
def test_a_contest_id_is_told_apart_from_a_sentence(value, expected):
    assert is_statpal_contest_id(value) is expected


def test_a_fabricated_id_is_receipted_and_never_written_over():
    """The 48 NFL rows of #2963. Selected on purpose so they are not invisible."""
    fixture = _by_id("280526")
    assert (fixture.home_team, fixture.away_team) == (
        "Buffalo Bills", "Pittsburgh Steelers"
    )
    pool = [
        _row(15292742, "Buffalo Bills", "Pittsburgh Steelers",
             _utc("2026-08-27T23:00:00"),
             statpal_fixture_id="statpal_live_Buffalo Bills_Pittsburgh Steelers",
             status="completed"),
    ]
    verdict, matches = classify_fixture(fixture, pool)
    assert verdict == VERDICT_POLLUTED
    assert matches[0]["id"] == 15292742


def test_a_real_id_already_present_is_already_linked_not_a_miss():
    """CERT-871's follow-up class, built in from the start.

    A row this task stamped on an earlier pass must not come back as UNMATCHED —
    "StatPal has this game and we do not" is the opposite of the truth, and at an
    hourly cadence it would bury the real misses under the task's own successes.
    """
    fixture = _by_id("280445")
    pool = [
        _row(14780138, "Seattle Seahawks", "New England Patriots",
             _utc("2026-09-10T00:20:00"), statpal_fixture_id="280445"),
    ]
    assert classify_fixture(fixture, pool)[0] == VERDICT_ALREADY_LINKED


# --- refusals ------------------------------------------------------------------


def test_no_kickoff_is_no_window_not_a_wide_one():
    fixture = _by_id("280445")
    fixture.start_time = None
    pool = [
        _row(14780138, "Seattle Seahawks", "New England Patriots",
             _utc("2026-09-10T00:20:00")),
    ]
    assert classify_fixture(fixture, pool)[0] == VERDICT_UNMATCHED


def test_a_row_with_no_commence_time_is_never_a_candidate():
    fixture = _by_id("280445")
    pool = [_row(14780138, "Seattle Seahawks", "New England Patriots", None)]
    assert classify_fixture(fixture, pool)[0] == VERDICT_UNMATCHED


def test_an_empty_pool_is_an_ingestion_gap_not_a_crash():
    assert classify_fixture(_by_id("280445"), [])[0] == VERDICT_UNMATCHED


def test_every_pinned_week_one_contest_finds_exactly_one_row():
    """The whole Week-1 slate at once, against the real rows, with both phantoms.

    A per-case test can pass on a rule that only works for the case it was written
    for. This drives all of them through one pool — the exact production window,
    phantoms included — and asserts 16 stamps, 0 ambiguities, and that neither
    phantom is ever the row chosen.
    """
    week_one = {
        "280445": (14780138, "Seattle Seahawks", "New England Patriots", "2026-09-10T00:20:00"),
        "280446": (14632820, "Los Angeles Rams", "San Francisco 49ers", "2026-09-11T00:35:00"),
        "280447": (14780142, "Carolina Panthers", "Chicago Bears", "2026-09-13T17:00:00"),
        "280448": (14780143, "Cincinnati Bengals", "Tampa Bay Buccaneers", "2026-09-13T17:00:00"),
        "280449": (14780145, "Detroit Lions", "New Orleans Saints", "2026-09-13T17:00:00"),
        "280450": (14780141, "Houston Texans", "Buffalo Bills", "2026-09-13T17:00:00"),
        "280451": (14780140, "Indianapolis Colts", "Baltimore Ravens", "2026-09-13T17:00:00"),
        "280452": (14780144, "Jacksonville Jaguars", "Cleveland Browns", "2026-09-13T17:00:00"),
        "280453": (14780139, "Pittsburgh Steelers", "Atlanta Falcons", "2026-09-13T17:00:00"),
        "280454": (14780146, "Tennessee Titans", "New York Jets", "2026-09-13T17:00:00"),
        "280455": (14780149, "Las Vegas Raiders", "Miami Dolphins", "2026-09-13T20:25:00"),
        "280456": (14780147, "Los Angeles Chargers", "Arizona Cardinals", "2026-09-13T20:25:00"),
        "280457": (14780148, "Minnesota Vikings", "Green Bay Packers", "2026-09-13T20:25:00"),
        "280458": (14780150, "Philadelphia Eagles", "Washington Commanders", "2026-09-13T20:25:00"),
        "280459": (14637256, "New York Giants", "Dallas Cowboys", "2026-09-14T00:20:00"),
        "280460": (14638896, "Kansas City Chiefs", "Denver Broncos", "2026-09-15T00:15:00"),
    }
    phantoms = {
        14780595: _row(14780595, "Los Angeles Chargers", "San Francisco 49ers",
                       _utc("2026-09-11T00:35:00")),
        14781140: _row(14781140, "Los Angeles Rams", "Arizona Cardinals",
                       _utc("2026-09-13T20:25:00")),
    }
    pool = [
        _row(eid, home, away, _utc(when))
        for eid, home, away, when in week_one.values()
    ] + list(phantoms.values())

    stamped, seen_rows = 0, set()
    for contest_id, (expected_row, _h, _a, _w) in week_one.items():
        verdict, matches = classify_fixture(_by_id(contest_id), pool)
        assert verdict == VERDICT_STAMP, f"{contest_id} -> {verdict}"
        assert [m["id"] for m in matches] == [expected_row], contest_id
        stamped += 1
        seen_rows.add(matches[0]["id"])

    assert stamped == 16
    assert not (seen_rows & phantoms.keys()), "a phantom was chosen as a candidate"
    # And the phantoms fall out as unclaimed rows — the other direction of the
    # receipt, which is how they become visible at all.
    assert set(phantoms) == {r["id"] for r in pool} - seen_rows
