"""#8961 — Red Sox @ Yankees Wild Card Game 1 shows once, not twice.

WHAT A READER SAW
=================
Production 2026-09-26 ~23:00Z, `bainluck.com/search?q=red sox`: Game 1 as two
cards — "Sep 29 · TBD / No price yet" (15319235, StatPal's pre-load at its
20:00Z placeholder, fixture 369024) and "Sep 29 4:10 PM, 56% / 44%" (15319563,
The Odds API's listing at its own guessed 23:10Z, created 22:19Z). ESPN
(`timeValid=false`) and MLB (`startTimeTBD`) had no start time at all.

WHY THEY DID NOT FOLD
=====================
The drain folds two rows only on a shared provider id (ruling 048). The hourly
stamp pass supplies one (`VERDICT_STAMP_TWIN`) — but it matched within ±1h of
StatPal's start, and a postseason `week[]` start is an on-the-hour placeholder
(#8841). 3h10m apart, the pass saw one candidate.

THE FIX
=======
The authority reader keeps the placeholder mark, and a placeholder fixture
matches on the Eastern calendar DATE it names. These tests pin: the specimen now
twin-stamps; Game 2 cannot reach Game 1's row; the date edges; nothing changes
for a regular-season (`match[]`) game or for NBA/NHL; the candidate query
reaches every row the classifier can accept.
"""

from __future__ import annotations

import json
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest

from app.services.statpal_api import StatPalAPIService
from app.tasks.stamp_v1_statpal_fixtures import (
    CANDIDATE_SLACK,
    MATCH_WINDOW,
    VERDICT_AMBIGUOUS,
    VERDICT_ANCHOR_ONLY,
    VERDICT_STAMP,
    VERDICT_STAMP_TWIN,
    VERDICT_UNMATCHED,
    candidate_window,
    classify_fixture,
    fixture_match_bounds,
    in_match_bounds,
)

FIXTURES = Path(__file__).parent / "fixtures"
WILDCARD = FIXTURES / "statpal_mlb_season_schedule_wildcard_8841.json"
NHL = FIXTURES / "statpal_nhl_season_schedule_20260904.json"

YANKEES, RED_SOX = "New York Yankees", "Boston Red Sox"


def _utc(text: str) -> datetime:
    return datetime.fromisoformat(text).replace(tzinfo=timezone.utc)


def _parse(path: Path, sport: str):
    service = StatPalAPIService.__new__(StatPalAPIService)  # no HTTP client
    return service._parse_v1_season_schedule(json.loads(path.read_text()), sport)


def _wildcard(contest_id: str):
    for f in _parse(WILDCARD, "mlb"):
        if f.fixture_id == contest_id:
            return f
    raise AssertionError(f"{contest_id} not in the pinned Wild Card payload")


def _row(event_id, when, statpal_fixture_id=None, home=YANKEES, away=RED_SOX):
    return {
        "id": event_id,
        "home": home,
        "away": away,
        "commence_time": when,
        "statpal_fixture_id": statpal_fixture_id,
        "status": "scheduled",
    }


# The production rows, as read 2026-09-26 23:00Z.
STATPAL_G1 = lambda: _row(15319235, _utc("2026-09-29T20:00:00"), "369024")  # noqa: E731
ODDS_G1 = lambda: _row(15319563, _utc("2026-09-29T23:10:00"))  # noqa: E731
STATPAL_G2 = lambda: _row(15319236, _utc("2026-09-30T20:00:00"), "369023")  # noqa: E731


# ---------------------------------------------------------------------------
# the reader keeps the mark
# ---------------------------------------------------------------------------


def test_the_authority_reader_marks_both_wild_card_games_and_no_regular_season_game():
    fixtures = _parse(WILDCARD, "mlb")
    marked = sorted(f.fixture_id for f in fixtures if f.start_is_placeholder)
    assert marked == ["369023", "369024"]
    # The corpus is the regular season too: 91 real `match[]` games, none marked.
    assert len(fixtures) == 93


def test_nhl_on_the_hour_starts_are_never_marked():
    """On-the-hour is the NORMAL shape of an NHL start; the mark is MLB-only."""
    fixtures = _parse(NHL, "nhl")
    assert fixtures, "pinned NHL corpus parsed to nothing"
    assert any(f.start_time and f.start_time.minute == 0 for f in fixtures)
    assert not any(f.start_is_placeholder for f in fixtures)


# ---------------------------------------------------------------------------
# the specimen
# ---------------------------------------------------------------------------


def test_the_production_pair_is_now_twin_stamped_onto_the_odds_row():
    fixture = _wildcard("369024")
    verdict, matches = classify_fixture(fixture, [STATPAL_G1(), ODDS_G1()])
    assert verdict == VERDICT_STAMP_TWIN
    # The write goes to the unlinked Odds row; the StatPal row is the witness.
    assert [m["id"] for m in matches] == [15319563, 15319235]


def test_control_the_same_pair_under_the_old_one_hour_window_never_meets():
    """The BEFORE, on the same rows: without the mark the pass sees one row."""
    fixture = _wildcard("369024")
    fixture.start_is_placeholder = False
    verdict, matches = classify_fixture(fixture, [STATPAL_G1(), ODDS_G1()])
    assert verdict == VERDICT_ANCHOR_ONLY
    assert [m["id"] for m in matches] == [15319235]


def test_game_two_cannot_reach_game_ones_row():
    fixture = _wildcard("369023")
    verdict, matches = classify_fixture(
        fixture, [STATPAL_G1(), ODDS_G1(), STATPAL_G2()]
    )
    assert verdict == VERDICT_ANCHOR_ONLY
    assert [m["id"] for m in matches] == [15319236]


def test_game_one_alone_with_only_the_odds_row_is_stamped():
    fixture = _wildcard("369024")
    verdict, matches = classify_fixture(fixture, [ODDS_G1()])
    assert verdict == VERDICT_STAMP
    assert [m["id"] for m in matches] == [15319563]


def test_two_unlinked_rows_on_the_date_stay_ambiguous():
    """No coin flip: the date widens the window, not the licence to pick."""
    fixture = _wildcard("369024")
    other = _row(15319999, _utc("2026-09-29T17:08:00"))
    verdict, matches = classify_fixture(fixture, [ODDS_G1(), other])
    assert verdict == VERDICT_AMBIGUOUS
    assert {m["id"] for m in matches} == {15319563, 15319999}


def test_orientation_still_binds_on_the_date():
    fixture = _wildcard("369024")
    flipped = _row(15319998, _utc("2026-09-29T23:10:00"), home=RED_SOX, away=YANKEES)
    assert classify_fixture(fixture, [flipped]) == (VERDICT_UNMATCHED, [])


# ---------------------------------------------------------------------------
# the date's edges
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "when,inside",
    [
        ("2026-09-29T04:00:00", True),   # 00:00 ET — ESPN's own date-only stamp
        ("2026-09-29T16:05:00", True),   # a noon-ET first pitch
        ("2026-09-30T00:08:00", True),   # 8:08 PM ET, the next UTC day
        ("2026-09-30T03:59:00", True),   # 11:59 PM ET
        ("2026-09-30T04:00:00", False),  # 00:00 ET on Game 2's date
        ("2026-09-29T03:59:00", False),  # 11:59 PM ET the day before
        ("2026-09-30T17:08:00", False),  # Game 2 at its earliest real hour
    ],
)
def test_the_placeholder_matches_its_eastern_date_and_nothing_else(when, inside):
    fixture = _wildcard("369024")
    assert in_match_bounds(fixture, _utc(when)) is inside


def test_the_date_is_25_hours_long_on_the_night_the_clocks_go_back():
    """2026-11-01 is the fall-back date: a fixed 24h UTC span would drop 11 PM ET."""
    fixture = _wildcard("369024")
    fixture.start_time = _utc("2026-11-01T20:00:00")
    lo, hi = fixture_match_bounds(fixture)
    assert lo == _utc("2026-11-01T04:00:00")
    assert hi == _utc("2026-11-02T05:00:00")
    assert in_match_bounds(fixture, _utc("2026-11-02T04:30:00"))


def test_a_regular_season_game_keeps_its_one_hour_window():
    fixture = next(f for f in _parse(WILDCARD, "mlb") if not f.start_is_placeholder)
    assert fixture_match_bounds(fixture) == (
        fixture.start_time - MATCH_WINDOW,
        fixture.start_time + MATCH_WINDOW,
    )
    far = _row(1, fixture.start_time + timedelta(hours=3, minutes=10),
               home=fixture.home_team, away=fixture.away_team)
    assert classify_fixture(fixture, [far]) == (VERDICT_UNMATCHED, [])


# ---------------------------------------------------------------------------
# the candidate query reaches what the classifier accepts
# ---------------------------------------------------------------------------


def test_the_candidate_window_reaches_the_last_placeholders_whole_date():
    fixtures = _parse(WILDCARD, "mlb")
    now = _utc("2026-09-26T23:00:00")
    lo, hi = candidate_window(fixtures, now)
    # Game 2 (9/30) is the latest fixture; its Eastern date ends 10/1 04:00Z,
    # 7h past what `max(start) + CANDIDATE_SLACK` used to reach.
    assert hi == _utc("2026-10-01T04:00:00")
    assert hi > max(f.start_time for f in fixtures) + CANDIDATE_SLACK
    assert lo == min(f.start_time for f in fixtures) - CANDIDATE_SLACK


def test_without_placeholders_the_candidate_window_is_unchanged():
    fixtures = [f for f in _parse(WILDCARD, "mlb") if not f.start_is_placeholder]
    starts = [f.start_time for f in fixtures]
    now = _utc("2026-09-26T23:00:00")
    assert candidate_window(fixtures, now) == (
        min(starts) - CANDIDATE_SLACK,
        max(starts) + CANDIDATE_SLACK,
    )
    assert candidate_window([], now) == (now - CANDIDATE_SLACK, now + CANDIDATE_SLACK)
