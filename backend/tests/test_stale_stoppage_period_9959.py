"""#9959 — a re-dated postponed match stops reading LIVE at its new kickoff.

WHAT A READER SAW, production 2026-09-30 23:34Z (`/search?q=new york`, 390px):
New York Red Bulls v St. Louis City SC, event 15314000, green live border and a
green pill reading ``Postponed 0'``. The row was ``status='live'``, scores null,
``period='Postponed'``; ESPN 761833 still read ``state: pre`` (kick-off ~23:41Z).

THE MECHANISM: the match was postponed on 26 Sep (#8960 — the sync wrote ESPN's
stoppage word into ``period``) and ESPN re-dated it to 30 Sep 23:30Z. Nothing
cleared the word. At the new kickoff the clock promoted the row, and the #5324
demotion that should have answered "ESPN says not started" refused, because
``play_evidence`` reads any period as play and ``Postponed`` was not the
pre-game board's own filler (the board's detail is a date / ``Scheduled``).
Same row shape still waiting on production: 15305825, ``scheduled`` for 21 Oct
carrying ``Postponed`` / ``0'``.

Driven through the real `_process_live_sport` + transition rig of #5324.
"""

from datetime import timedelta

import pytest

from app.utils.espn_helpers import (
    ESPN_NOT_STARTED_KEY,
    espn_pregame_filler,
    play_evidence,
)
from app.utils.game_state import _sanitize_period, authority_stoppage_label

from tests.test_authority_demotes_the_live_latch_5324 import NOW, _run_transition
from tests.test_team_sport_pregame_filler_5324 import (
    _LIVE_STATE,
    _board,
    _live_pass,
    _started_row,
)


def _soccer_pregame(detail):
    """ESPN's pre-game MLS board as served (761773, read 2026-09-30 for 21 Oct):
    STATUS_SCHEDULED / state pre, displayClock "0'", score "0"-"0"."""
    return _board("scheduled", detail=detail, clock="0'", period=0, hs=0, aws=0)


_DETAILS = ["Wed, September 30th at 7:30 PM EDT", "Scheduled"]


def _redated_row(period="Postponed", **kw):
    """15314000 at 23:34Z: promoted live by the clock, the 26 Sep stoppage
    word and ESPN's "0'" still on it, no score."""
    return _started_row(period=period, game_clock="0'", **kw)


# ═══════════════════════════════════════════════════════════════════════════
# THE SHIP, through both real tasks
# ═══════════════════════════════════════════════════════════════════════════


@pytest.mark.parametrize("detail", _DETAILS, ids=["date-detail", "short-detail"])
@pytest.mark.parametrize("word", ["Postponed", "Canceled", "cancelled"])
def test_a_redated_postponement_stops_reading_live_at_its_new_kickoff(detail, word):
    row = _redated_row(period=word)

    stats, _ = _live_pass(row, _soccer_pregame(detail))

    assert row.status == "scheduled", "a match ESPN still reads pre stayed live"
    assert stats["live_demoted_by_authority"] == 1
    assert stats["pregame_filler_withdrawn"] == 1
    assert ESPN_NOT_STARTED_KEY in row.win_probability_sources
    for column in _LIVE_STATE:
        assert getattr(row, column) is None, (
            f"{column}={getattr(row, column)!r} survived; the pill paints it"
        )

    promote = _run_transition([row], now=NOW + timedelta(seconds=60))
    assert row.status == "scheduled", "the clock re-promoted the re-dated match"
    assert promote["held_authority_not_started"] == 1


def test_the_waiting_scheduled_row_is_cleaned_before_it_can_be_promoted():
    """15305825's shape: still `scheduled`, carrying the old word. The pass
    withdraws it, so at kickoff nothing on the row can supersede the hold."""
    row = _redated_row()
    row.status = "scheduled"

    stats, _ = _live_pass(row, _soccer_pregame("Scheduled"))

    assert row.status == "scheduled"
    assert row.period is None and row.game_clock is None
    assert stats["pregame_filler_withdrawn"] == 1


def test_kickoff_after_the_redate_still_goes_live():
    """The match actually starting: ESPN `in`, 1' — the row is live and takes
    the clock, the stoppage word replaced by real play."""
    row = _redated_row()

    stats, _ = _live_pass(
        row, _board("in", detail="1'", clock="1'", period=1, hs=0, aws=0)
    )

    assert row.status == "live"
    assert row.period == "1'" and row.game_clock == "1'"
    assert stats.get("live_demoted_by_authority", 0) == 0


# ═══════════════════════════════════════════════════════════════════════════
# CONTROLS
# ═══════════════════════════════════════════════════════════════════════════


@pytest.mark.parametrize("espn_status", ["post", "status_postponed", "status_delayed", "in"])
def test_THE_CONTROL_only_a_scheduled_board_retires_the_word(espn_status):
    """#8960 keeps writing and reading `Postponed` while ESPN reports the
    stoppage; this rule speaks only once the board says the game is re-dated."""
    assert espn_pregame_filler(
        espn_status, None, "0'", 0, 0,
        period="Postponed", game_clock=None, home_score=None, away_score=None,
    ) == {}


def test_THE_CONTROL_a_real_score_keeps_the_row_live():
    """An abandoned match that had play keeps its score as evidence: the word
    goes, the score stays, and the demotion is refused on the score."""
    row = _redated_row(home_score=1, away_score=0)

    stats, _ = _live_pass(row, _soccer_pregame("Scheduled"))

    assert row.status == "live"
    assert (row.home_score, row.away_score) == (1, 0)
    assert stats.get("live_demoted_by_authority", 0) == 0


@pytest.mark.parametrize("period", ["2nd Half", "HT", "Top 1st", "Postponed due to rain"])
def test_THE_CONTROL_only_the_exact_stoppage_word_is_retired(period):
    assert "period" not in espn_pregame_filler(
        "scheduled", "Scheduled", "0'", 0, 0,
        period=period, game_clock=None, home_score=None, away_score=None,
    )


# ═══════════════════════════════════════════════════════════════════════════
# STRAWMAN — why the #5324 discount alone left the specimen live
# ═══════════════════════════════════════════════════════════════════════════


def test_THE_STRAWMAN_the_word_is_play_evidence_and_matches_no_board_filler():
    assert play_evidence(None, None, "Postponed", None) is True
    for detail in _DETAILS:
        assert _sanitize_period(detail) != "Postponed"
    assert authority_stoppage_label(" postponed ") == "Postponed"
    assert authority_stoppage_label("Scheduled") is None
