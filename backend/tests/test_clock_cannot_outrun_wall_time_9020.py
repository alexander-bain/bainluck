"""#9020 clock half — a game clock can stop; it cannot run faster than time.

## what a reader saw

Oregon at USC (14870010), iPhone, 2026-09-27 02:36Z: the hero chip said
**Q4 1:27** while the chart readout directly below said **Q4 ~9:51**, one
minute earlier by its own label. The row had taken `'1:27 - 4th Quarter'` from
`'12:41 - 4th Quarter'` in one pass — 11:14 of game clock in about a minute.
After that every correct ESPN reading sat "earlier in the game" and the #6056
guard refused its clock, so the row's clock stuck.

## the producer publishes these readings (espn_snapshots, SMU 15316003)

    03:29:32  End of 3rd Quarter
    03:30:32  End of 3rd Quarter
    03:31:32  4:38 - 4th Quarter    <- new label, old quarter's clock
    03:32:32  4:38 - 4th Quarter
    03:33:32  14:59 - 4th Quarter   <- the real reading

## the rule

A reading that places the game further on than the wall clock allows since the
row's position was first seen (plus 90 s of slack) does not write its clock or
period. Scores keep their own rule (#9039). Unknown anything ⇒ no evidence ⇒
today's behaviour. Every refusal has a twin that lands (gotcha #43).
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

import pytest

from app.utils.game_state import (
    WALL_CLOCK_SLACK_SECONDS,
    clock_outruns_wall_time,
    game_seconds_elapsed_at_least,
    regulation_period_seconds_at_least,
)
from tests.test_live_state_does_not_run_backwards_6056 import (
    _drive_espn,
    _EspnEvent,
    _Row,
)

FOOTBALL = regulation_period_seconds_at_least("americanfootball_ncaaf")
END_Q3 = ("End of 3rd Quarter", "0:00")
ROLLOVER = ("4:38 - 4th Quarter", "4:38")
REAL_Q4 = ("14:59 - 4th Quarter", "14:59")


class TestTheBound:
    def test_the_smu_rollover_is_ten_minutes_of_game_clock(self):
        assert game_seconds_elapsed_at_least(
            *END_Q3, *ROLLOVER, period_seconds=FOOTBALL
        ) == 622

    def test_the_oregon_jump_is_exact_within_a_quarter(self):
        assert game_seconds_elapsed_at_least(
            "12:41 - 4th Quarter", "12:41", "1:27 - 4th Quarter", "1:27"
        ) == 674

    def test_the_real_reading_after_the_break_is_near_zero(self):
        assert game_seconds_elapsed_at_least(
            *END_Q3, *REAL_Q4, period_seconds=FOOTBALL
        ) == 1

    def test_an_unknown_sport_is_bounded_from_below(self):
        """Ten-minute quarters are the shortest played; the bound must not
        exceed what a WNBA game could really have run."""
        assert regulation_period_seconds_at_least(None) == 600
        assert regulation_period_seconds_at_least("basketball_wnba") == 600
        assert game_seconds_elapsed_at_least(*END_Q3, *ROLLOVER) == 600 - 278

    @pytest.mark.parametrize(
        "stored,incoming",
        [
            (("5:21 - 4th Quarter", "5:21"), ("5:26 - 4th Quarter", "5:26")),
            (("0:00 - 4th Quarter", "0:00"), ("10:00 - OT", "10:00")),
            (("Top 3rd", None), ("Bottom 3rd", None)),
            (("Halftime", None), ("4:38 - 3rd Quarter", "4:38")),
            (("2:00 - 4th Quarter", "2:00"), ("Final", None)),
            (("4th Quarter", None), ("4th Quarter", None)),
        ],
        ids=["backwards", "overtime", "innings", "halftime", "final", "no-clock"],
    )
    def test_anything_it_cannot_place_is_no_evidence(self, stored, incoming):
        assert game_seconds_elapsed_at_least(*stored, *incoming) is None
        assert clock_outruns_wall_time(*stored, *incoming, 0.0) is False


class TestTheVerdict:
    @pytest.mark.parametrize("wall", [60, 120, 180])
    def test_the_rollover_is_refused_minutes_after_the_break(self, wall):
        assert clock_outruns_wall_time(
            *END_Q3, *ROLLOVER, wall, period_seconds=FOOTBALL
        ) is True

    def test_twin_the_real_reading_lands(self):
        assert clock_outruns_wall_time(
            *END_Q3, *REAL_Q4, 60, period_seconds=FOOTBALL
        ) is False

    def test_not_a_clamp_the_same_reading_lands_once_time_allows_it(self):
        assert clock_outruns_wall_time(
            *END_Q3, *ROLLOVER, 622 - WALL_CLOCK_SLACK_SECONDS, period_seconds=FOOTBALL
        ) is False

    def test_the_slack_boundary(self):
        at = 674 - WALL_CLOCK_SLACK_SECONDS
        args = ("12:41 - 4th Quarter", "12:41", "1:27 - 4th Quarter", "1:27")
        assert clock_outruns_wall_time(*args, at) is False
        assert clock_outruns_wall_time(*args, at - 1) is True

    def test_no_anchor_is_no_evidence(self):
        assert clock_outruns_wall_time(
            *END_Q3, *ROLLOVER, None, period_seconds=FOOTBALL
        ) is False


def _ago(seconds: float) -> datetime:
    return datetime.now(timezone.utc) - timedelta(seconds=seconds)


def _smu_row():
    row = _Row(period=END_Q3[0], game_clock=END_Q3[1], home_score=21, away_score=10)
    row.home_team_name, row.away_team_name = "SMU Mustangs", "Opponent"
    return row


#: The board as ESPN published it before the rollover pass, oldest first.
SMU_BOARD = [
    (_ago(180), "0:42 - 3rd Quarter"),
    (_ago(120), "End of 3rd Quarter"),
    (_ago(60), "End of 3rd Quarter"),
]


class TestTheRealEspnWriter:
    """Through `update_event_fields_from_espn`, read back from the database."""

    @pytest.mark.asyncio
    async def test_the_smu_rollover_does_not_reach_the_row(self):
        ee = _EspnEvent(
            clock=ROLLOVER[1], status_detail=ROLLOVER[0], home_score=21, away_score=10
        )
        row, _snaps, stats = await _drive_espn(
            _smu_row(), ee, sport_key="americanfootball_ncaaf", espn_snapshots=SMU_BOARD,
        )
        assert (row.period, row.game_clock) == END_Q3, (
            "the rollover reading reached the row"
        )
        assert stats["live_clock_outran_wall_refused"] == 1, stats

    @pytest.mark.asyncio
    async def test_twin_the_real_fourth_quarter_reading_lands(self):
        ee = _EspnEvent(
            clock=REAL_Q4[1], status_detail=REAL_Q4[0], home_score=21, away_score=10
        )
        row, _snaps, stats = await _drive_espn(
            _smu_row(), ee, sport_key="americanfootball_ncaaf", espn_snapshots=SMU_BOARD,
        )
        assert (row.period, row.game_clock) == REAL_Q4
        assert stats.get("live_clock_outran_wall_refused", 0) == 0, stats

    @pytest.mark.asyncio
    async def test_a_score_on_the_same_board_still_lands(self):
        """Only the clock and period are withheld; a touchdown is a touchdown."""
        ee = _EspnEvent(
            clock=ROLLOVER[1], status_detail=ROLLOVER[0], home_score=21, away_score=17
        )
        row, snaps, stats = await _drive_espn(
            _smu_row(), ee, sport_key="americanfootball_ncaaf", espn_snapshots=SMU_BOARD,
        )
        assert (row.home_score, row.away_score) == (21, 17)
        assert [(s.home_score, s.away_score) for s in snaps] == [(21, 17)]
        assert (row.period, row.game_clock) == END_Q3
        assert stats["live_clock_outran_wall_refused"] == 1, stats

    @pytest.mark.asyncio
    async def test_the_oregon_specimen_keeps_its_clock_and_takes_the_score(self):
        row = _Row(
            period="12:41 - 4th Quarter", game_clock="12:41", home_score=26, away_score=27
        )
        ee = _EspnEvent(
            clock="1:27", status_detail="1:27 - 4th Quarter", home_score=27, away_score=27
        )
        row, _snaps, stats = await _drive_espn(
            row, ee, sport_key="americanfootball_ncaaf",
            espn_snapshots=[
                (_ago(120), "12:47 - 4th Quarter"),
                (_ago(60), "12:41 - 4th Quarter"),
            ],
        )
        assert (row.home_score, row.away_score) == (27, 27)
        assert (row.period, row.game_clock) == ("12:41 - 4th Quarter", "12:41")
        assert stats["live_clock_outran_wall_refused"] == 1, stats

    @pytest.mark.asyncio
    async def test_a_board_that_sat_still_and_caught_up_is_not_refused(self):
        """The anchor is the FIRST snapshot of the row's latest run, not the
        newest: five minutes on one reading is five minutes of wall time."""
        row = _Row(
            period="8:00 - 2nd Quarter", game_clock="8:00", home_score=7, away_score=7
        )
        ee = _EspnEvent(
            clock="3:00", status_detail="3:00 - 2nd Quarter", home_score=7, away_score=7
        )
        row, _snaps, stats = await _drive_espn(
            row, ee, espn_snapshots=[
                (_ago(420), "8:40 - 2nd Quarter"),
                *[(_ago(s), "8:00 - 2nd Quarter") for s in (360, 300, 240, 180, 120, 60)],
            ],
        )
        assert (row.period, row.game_clock) == ("3:00 - 2nd Quarter", "3:00")
        assert stats.get("live_clock_outran_wall_refused", 0) == 0, stats

    @pytest.mark.asyncio
    async def test_no_board_history_changes_nothing(self):
        """StatPal wrote the position, or ESPN published no win probability:
        no anchor, no evidence, today's behaviour."""
        ee = _EspnEvent(
            clock=ROLLOVER[1], status_detail=ROLLOVER[0], home_score=21, away_score=10
        )
        row, _snaps, stats = await _drive_espn(
            _smu_row(), ee, sport_key="americanfootball_ncaaf",
        )
        assert (row.period, row.game_clock) == ROLLOVER
        assert stats.get("live_clock_outran_wall_refused", 0) == 0, stats

    @pytest.mark.asyncio
    async def test_a_reading_after_a_slow_pass_lands(self):
        """The slack is real, not a formula: Oregon's own board went 14:36 →
        12:47 (109 s of game clock) between consecutive minute passes when one
        read was a little stale. That must land."""
        row = _Row(
            period="14:36 - 4th Quarter", game_clock="14:36", home_score=20, away_score=27
        )
        ee = _EspnEvent(
            clock="12:47", status_detail="12:47 - 4th Quarter", home_score=20, away_score=27
        )
        row, _snaps, stats = await _drive_espn(
            row, ee, sport_key="americanfootball_ncaaf",
            espn_snapshots=[(_ago(60), "14:36 - 4th Quarter")],
        )
        assert (row.period, row.game_clock) == ("12:47 - 4th Quarter", "12:47")
        assert stats.get("live_clock_outran_wall_refused", 0) == 0, stats

    @pytest.mark.asyncio
    async def test_the_anchor_is_the_latest_run_not_an_older_one(self):
        """An older, separate run of the same string says nothing about since
        when the row has stood there NOW; reading through the gap would hand
        the rollover fifteen minutes of wall time it never had."""
        ee = _EspnEvent(
            clock=ROLLOVER[1], status_detail=ROLLOVER[0], home_score=21, away_score=10
        )
        row, _snaps, stats = await _drive_espn(
            _smu_row(), ee, sport_key="americanfootball_ncaaf",
            espn_snapshots=[
                (_ago(900), "End of 3rd Quarter"),
                (_ago(840), "3:10 - 3rd Quarter"),
                *SMU_BOARD,
            ],
        )
        assert (row.period, row.game_clock) == END_Q3
        assert stats["live_clock_outran_wall_refused"] == 1, stats
