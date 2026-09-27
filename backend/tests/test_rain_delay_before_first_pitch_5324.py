"""#5324, delayed start — a rain-delayed MLB game stops reading LIVE 0-0 before first pitch.

WHAT A READER SAW, production 2026-09-27 17:21Z (lane1 D48 look): the first card
on `bainluck.com/search?q=yankees` was `● LIVE Yankees 0 / Orioles 0` for event
15319530, while ESPN 401817103 read `STATUS_RAIN_DELAY` / `state: pre` and MLB
823490 read `Delayed Start`. The stored row at 17:28Z:

    status 'live'   period 'Rain Delay'   game_clock '0:00'   0-0

THE MECHANISM: `_parse_event` translated one not-started NAME,
`STATUS_SCHEDULED`; `STATUS_RAIN_DELAY` fell through as the raw
`status_rain_delay`. #8745's refusal, withdrawal, demotion and hold all key on
`"scheduled"`, so none of them ran, and the board's filler landed on the row as
play. The repair reads ESPN's closed `state` field. These tests parse the board
entry as ESPN serves it and drive the result through the REAL live pass and the
REAL promoter, so deleting the parser arm turns them red.
"""

from datetime import timedelta

import pytest

from app.services.espn_api import ESPNAPIService, espn_not_started_state
from app.utils.espn_helpers import ESPN_NOT_STARTED_KEY

from tests.test_authority_demotes_the_live_latch_5324 import NOW, _run_transition
from tests.test_team_sport_pregame_filler_5324 import (
    _LIVE_STATE,
    _board,
    _live_pass,
    _started_row,
)


def _espn_entry(name, state, detail, *, type_id, completed=False, hs="0", aws="0"):
    """One MLB scoreboard entry in ESPN's own shape (401817103, 17:28Z)."""
    return {
        "id": "401817103",
        "name": "Baltimore Orioles at New York Yankees",
        "shortName": "BAL @ NYY",
        "date": "2026-09-27T17:05Z",
        "status": {
            "displayClock": "0:00",
            "period": 1,
            "type": {
                "id": type_id, "name": name, "state": state,
                "completed": completed, "detail": detail,
            },
        },
        "competitions": [{
            "competitors": [
                {"homeAway": "home", "score": hs,
                 "team": {"id": "10", "name": "Yankees", "abbreviation": "NYY"}},
                {"homeAway": "away", "score": aws,
                 "team": {"id": "1", "name": "Orioles", "abbreviation": "BAL"}},
            ],
        }],
    }


RAIN_DELAY = _espn_entry("STATUS_RAIN_DELAY", "pre", "Rain Delay", type_id="17")


def _parsed_board(entry):
    """Parse the entry with the real parser, then hand its status, detail,
    clock, period and score to the live-pass rig's anchored board."""
    ee = ESPNAPIService()._parse_event(entry)
    assert ee is not None
    return ee, _board(
        ee.status, detail=ee.status_detail, clock=ee.clock, period=ee.period,
        hs=ee.home_score, aws=ee.away_score,
    )


# ═══════════════════════════════════════════════════════════════════════════
# THE SHIP, through the parser, the live pass and the promoter
# ═══════════════════════════════════════════════════════════════════════════


def test_a_rain_delay_before_first_pitch_is_read_as_not_started():
    ee, _ = _parsed_board(RAIN_DELAY)
    assert ee.status == "scheduled"


def test_the_row_carrying_the_rain_delay_filler_is_demoted_and_held():
    """15319530 as stored at 17:28Z. The pass withdraws the board's own
    'Rain Delay' / '0:00' / 0-0, demotes the row, and the clock one beat later
    does not put it back."""
    row = _started_row(period="Rain Delay", game_clock="0:00", home_score=0, away_score=0)
    _, board = _parsed_board(RAIN_DELAY)

    stats, _ = _live_pass(row, board)

    assert row.status == "scheduled"
    assert stats["pregame_filler_withdrawn"] == 1
    assert stats["live_demoted_by_authority"] == 1
    assert ESPN_NOT_STARTED_KEY in row.win_probability_sources
    for column in _LIVE_STATE:
        assert getattr(row, column) is None, f"{column} kept {getattr(row, column)!r}"

    promote = _run_transition([row], now=NOW + timedelta(seconds=60))
    assert row.status == "scheduled", "the clock re-promoted a game nobody has started"
    assert promote["held_authority_not_started"] == 1


def test_a_freshly_promoted_row_takes_no_rain_delay_filler():
    """The row the clock promoted at 17:05Z before any ESPN pass landed."""
    row = _started_row()
    _, board = _parsed_board(RAIN_DELAY)

    stats, _ = _live_pass(row, board)

    assert row.status == "scheduled"
    assert stats["pregame_board_live_writes_refused"] >= 1
    for column in _LIVE_STATE:
        assert getattr(row, column) is None


# ═══════════════════════════════════════════════════════════════════════════
# CONTROLS — the names this must leave alone
# ═══════════════════════════════════════════════════════════════════════════


def test_THE_CONTROL_first_pitch_after_the_delay_goes_live():
    """ESPN flips to in-progress: the row is live with a real inning."""
    row = _started_row()
    _live_pass(row, _parsed_board(RAIN_DELAY)[1])
    assert row.status == "scheduled"

    first_pitch = _espn_entry("STATUS_IN_PROGRESS", "in", "Top 1st", type_id="2")
    ee, board = _parsed_board(first_pitch)
    assert ee.status == "in"
    _live_pass(row, board)
    assert row.period == "Top 1st"
    assert ESPN_NOT_STARTED_KEY not in row.win_probability_sources
    _run_transition([row], now=NOW + timedelta(seconds=60))
    assert row.status == "live"


def test_THE_CONTROL_a_delay_ESPN_calls_in_progress_stays_ambiguous():
    """Mets @ Nationals 401817106 at the same minute: STATUS_DELAYED,
    state `in`, 'Delayed, Top 1st'. Published before a start AND mid-game, so
    it stays the raw name every not-started predicate is silent on."""
    ee, _ = _parsed_board(
        _espn_entry("STATUS_DELAYED", "in", "Delayed, Top 1st", type_id="7")
    )
    assert ee.status == "status_delayed"


def test_THE_CONTROL_a_postponement_is_not_not_started():
    """`post` + completed False is #3397's stopped-without-result class."""
    ee, _ = _parsed_board(
        _espn_entry("STATUS_POSTPONED", "post", "Postponed", type_id="6")
    )
    assert ee.status != "scheduled"


def test_THE_CONTROL_a_final_still_settles():
    ee, _ = _parsed_board(
        _espn_entry("STATUS_FINAL", "post", "Final", type_id="3",
                    completed=True, hs="4", aws="2")
    )
    assert ee.status == "post"


def test_THE_STRAWMAN_the_raw_name_leaves_the_row_live():
    """The pre-fix parse: the same board under the raw name demotes nothing.
    If this ever demotes, the parser arm above is dead weight."""
    row = _started_row(period="Rain Delay", game_clock="0:00", home_score=0, away_score=0)
    _, board = _parsed_board(RAIN_DELAY)
    board.status = "status_rain_delay"

    stats, _ = _live_pass(row, board)

    assert row.status == "live"
    assert stats.get("live_demoted_by_authority", 0) == 0


# ═══════════════════════════════════════════════════════════════════════════
# THE PREDICATE
# ═══════════════════════════════════════════════════════════════════════════


@pytest.mark.parametrize(
    "status_type, expected",
    [
        ({"state": "pre"}, True),
        ({"state": "PRE "}, True),
        ({"state": "in"}, False),
        ({"state": "post"}, False),
        ({}, False),
        (None, False),
        ("pre", False),
    ],
)
def test_the_predicate_reads_state_only(status_type, expected):
    assert espn_not_started_state(status_type) is expected
