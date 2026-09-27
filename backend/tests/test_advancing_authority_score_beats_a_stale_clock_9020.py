"""#9020 — a stale clock on the row can no longer freeze a live score.

## what a reader saw

Oregon at USC (14870010), 2026-09-27. At ~02:26Z the row took
'1:27 - 4th Quarter' — a third-quarter clock under a fourth-quarter label. From
then on the #6056 revert guard refused every ESPN write as "earlier in the game",
because ESPN's real clock (12:41, 8:35, 2:03 …) always sat before 1:27. The
served score stayed USC 27 – Oregon 27 for 34 minutes, through two Oregon
touchdowns, on /sports and search (worker log 02:58:44: row '1:27'/27-27, ESPN
offered '2:03'/27-41).

## the rule

An AUTHORITY observation whose scoreboard is strictly ahead of the row's (ahead
on one side, behind on neither) is not refused for sitting earlier in game time:
a real scoreboard does not run backwards and ESPN does not lag itself, so the
row's position is the stale value. Everything else keeps its #6056/#6251 answer —
in particular the same pair from a secondary feed is still refused (#6251's
pinned "lagging feed's disguise"), and a lower, equal or crossed score from an
earlier position is still refused from anyone.

Every refusal has a twin that lands (gotcha #43).
"""

from __future__ import annotations

import pytest

from app.utils.game_state import live_write_would_revert
from tests.test_live_state_does_not_run_backwards_6056 import (
    _drive_espn,
    _EspnEvent,
    _Row,
)

#: The specimen: the row's stale position and ESPN's offer at 02:58:44Z.
ROW_AT = ("1:27 - 4th Quarter", "1:27")
ESPN_AT = ("2:03 - 4th Quarter", "2:03")


def _verdict(stored_scores, incoming_scores, *, authority, row=ROW_AT, offer=ESPN_AT):
    (sh, sa), (ih, ia) = stored_scores, incoming_scores
    return live_write_would_revert(
        *row,
        *offer,
        stored_home_score=sh,
        stored_away_score=sa,
        incoming_home_score=ih,
        incoming_away_score=ia,
        incoming_is_authority=authority,
    )


class TestTheAuthorityScoreboardUnsticksAStaleClock:
    def test_the_specimen_lands(self):
        """USC 27 – Oregon 27 on the row; ESPN offers 27–41 at 2:03 Q4."""
        assert _verdict((27, 27), (27, 41), authority=True) is False

    def test_one_touchdown_ahead_is_enough(self):
        assert _verdict((27, 27), (27, 34), authority=True) is False

    def test_an_earlier_quarter_lands_too_when_the_board_is_ahead(self):
        """The row's label can be as wrong as its clock."""
        assert _verdict(
            (27, 27), (27, 34), authority=True, offer=("12:41 - 3rd Quarter", "12:41"),
        ) is False


class TestWhatIsStillRefused:
    def test_the_same_pair_from_a_secondary_feed(self):
        """#6251: from StatPal or the odds feed, an earlier position with a
        higher score is a lagging feed's disguise, and the row wins."""
        assert _verdict((27, 27), (27, 41), authority=False) is True

    def test_an_equal_board_says_nothing_about_which_clock_is_right(self):
        assert _verdict((27, 27), (27, 27), authority=True) is True

    def test_a_lower_score_from_earlier_is_the_6056_reversion(self):
        """Giants–Cowboys: 28–20 @5:21 on the row, 28–14 @5:26 offered."""
        assert _verdict(
            (28, 20), (28, 14), authority=True,
            row=("5:21 - 4th Quarter", "5:21"), offer=("5:26 - 4th Quarter", "5:26"),
        ) is True

    def test_a_crossed_board_is_not_ahead(self):
        assert _verdict((27, 27), (34, 20), authority=True) is True

    @pytest.mark.parametrize(
        "stored,incoming",
        [((None, 27), (27, 41)), ((27, 27), (27, None)), ((27, "x"), (27, 41))],
        ids=["stored-missing", "incoming-missing", "unreadable"],
    )
    def test_a_board_that_cannot_be_read_changes_nothing(self, stored, incoming):
        assert _verdict(stored, incoming, authority=True) is True


class TestTheRealEspnWriter:
    """The specimen through `update_event_fields_from_espn`, read back from the
    database (the #6056 rail) — the writer passes `incoming_is_authority=True`
    and the four scores, so the rule reaches the row."""

    @staticmethod
    def _usc_row():
        row = _Row(period=ROW_AT[0], game_clock=ROW_AT[1], home_score=27, away_score=27)
        row.home_team_name, row.away_team_name = "USC Trojans", "Oregon Ducks"
        return row

    @pytest.mark.asyncio
    async def test_espn_moves_the_frozen_score_forward(self):
        ee = _EspnEvent(
            clock=ESPN_AT[1], status_detail=ESPN_AT[0], home_score=27, away_score=41,
        )
        row, _snaps, stats = await _drive_espn(
            self._usc_row(), ee, sport_key="americanfootball_ncaaf",
        )
        assert (row.home_score, row.away_score) == (27, 41), (
            "the frozen 27-27 survived ESPN's 27-41"
        )
        assert row.game_clock == "2:03" and row.period == "2:03 - 4th Quarter"
        assert stats.get("live_state_reversions_refused", 0) == 0, stats

    @pytest.mark.asyncio
    async def test_control_espn_with_an_equal_board_is_still_refused(self):
        ee = _EspnEvent(
            clock=ESPN_AT[1], status_detail=ESPN_AT[0], home_score=27, away_score=27,
        )
        row, _snaps, stats = await _drive_espn(
            self._usc_row(), ee, sport_key="americanfootball_ncaaf",
        )
        assert row.game_clock == "1:27", "control: the refusal path did not run"
        assert stats["live_state_reversions_refused"] == 1, stats
