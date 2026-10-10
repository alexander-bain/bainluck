"""#10851 (backend half of #10549) — a basketball page's first period is observed, not listed.

    cd backend && python3 -m pytest tests/test_basketball_observed_period_starts_10549.py

The native projected-final chart (#10549, PR #10849) admits NBA, WNBA, NCAAB and
WNCAAB. During and after a game it needs an OBSERVED start for the league's first
period: `1st Quarter`, or `1st Half` for the men's college game, carrying
`precision` and a real `not_before`. `observed_transition_markers` read football
only, so every basketball page refused.

These cases pin the extension to the four exact keys and the vocabulary already
measured in this repo: `M:SS - Nth Quarter`, a tenths clock in the last minute
(`0:04.2`, `game_state._GAME_CLOCK_RE`), `End of Nth Quarter`, `End of 2nd Half`
(men's college), `Halftime`, `End of OT`. They also pin each refusal #6718/#9179
built for football, re-run on basketball rows. The status strings below are
SYNTHETIC, written in that vocabulary. No basketball replay is retained, and these
tests do not claim a production capture.
"""

from datetime import datetime, timedelta, timezone
from unittest.mock import MagicMock

import pytest

from app.routes.events import get_event_odds_history
from app.utils import period_markers as pm
from tests.test_game_period_timing_5140 import _session

UTC = timezone.utc
T0 = datetime(2026, 10, 10, 23, 30, tzinfo=UTC)  # the listed tip


def _obs(minute, period, second=0, source=None):
    row = {"timestamp": (T0 + timedelta(minutes=minute, seconds=second)).isoformat(),
           "period": period}
    if source:
        row["source"] = source
    return row


def _markers(sport, rows, kickoff=None):
    return pm.observed_transition_markers(sport, rows, kickoff_not_before=kickoff)


def _by(markers):
    return {m["period"]: m for m in markers}


NBA_GAME = [
    _obs(8, "12:00 - 1st Quarter"), _obs(9, "11:41 - 1st Quarter"),
    _obs(36, "0:04.2 - 1st Quarter"), _obs(37, "End of 1st Quarter"),
    _obs(39, "12:00 - 2nd Quarter"), _obs(40, "11:48 - 2nd Quarter"),
    _obs(68, "0:00.0 - 2nd Quarter"), _obs(69, "Halftime"), _obs(83, "Halftime"),
    _obs(84, "11:50 - 3rd Quarter"), _obs(112, "End of 3rd Quarter"),
    _obs(115, "11:52 - 4th Quarter"), _obs(145, "End of 4th Quarter"),
    _obs(147, "5:00 - OT"), _obs(148, "4:40 - OT"),
]

NCAAB_GAME = [
    _obs(6, "20:00 - 1st Half"), _obs(7, "19:31 - 1st Half"),
    _obs(50, "End of 1st Half"), _obs(51, "Halftime"), _obs(66, "Halftime"),
    _obs(67, "20:00 - 2nd Half"), _obs(68, "19:40 - 2nd Half"),
    _obs(112, "End of 2nd Half"), _obs(114, "5:00 - OT"), _obs(115, "4:21 - OT"),
]


class TestTheFourLeaguesAreRead:
    def test_an_nba_game_is_bracketed_period_by_period(self):
        m = _markers("basketball_nba", NBA_GAME)
        assert [x["period"] for x in m] == [
            "1st Quarter", "2nd Quarter", "Halftime", "3rd Quarter", "4th Quarter", "Overtime"]
        by = _by(m)
        # Q1: the 12:00 clock leaving its opening value. Two observations, first_seen.
        assert (by["1st Quarter"]["not_before"], by["1st Quarter"]["timestamp"]) == (
            NBA_GAME[0]["timestamp"], NBA_GAME[1]["timestamp"])
        assert by["1st Quarter"]["precision"] == pm.PRECISION_FIRST_SEEN
        # Q2: 2 min after `End of 1st Quarter`, inside POLL_TOLERANCE.
        assert by["2nd Quarter"]["not_before"] == NBA_GAME[3]["timestamp"]
        assert by["2nd Quarter"]["precision"] == pm.PRECISION_BOUNDARY
        # Q3 is bounded by the LAST halftime row, not the first.
        assert by["3rd Quarter"]["not_before"] == NBA_GAME[8]["timestamp"]
        # The tenths clock row bounds halftime; a parser that cannot read
        # `0:00.0` would leave halftime unbracketed and drop it.
        assert by["Halftime"]["not_before"] == NBA_GAME[6]["timestamp"]
        assert all(x["not_before"] for x in m)

    @pytest.mark.parametrize("sport", ["basketball_wnba", "basketball_wncaab"])
    def test_ten_minute_quarters_open_on_ten_minutes(self, sport):
        rows = [_obs(5, "10:00 - 1st Quarter"), _obs(6, "9:40 - 1st Quarter")]
        q1 = _by(_markers(sport, rows))["1st Quarter"]
        assert (q1["not_before"], q1["timestamp"]) == (rows[0]["timestamp"], rows[1]["timestamp"])
        assert q1["precision"] == pm.PRECISION_FIRST_SEEN

    def test_a_ten_minute_opening_is_not_an_nba_opening(self):
        """`10:00` in the NBA is a clock that has already run two minutes: there
        is nothing earlier to bound it, so no Q1."""
        rows = [_obs(5, "10:00 - 1st Quarter"), _obs(6, "9:40 - 1st Quarter")]
        assert _markers("basketball_nba", rows) == []

    def test_a_mens_college_game_is_played_in_halves(self):
        m = _markers("basketball_ncaab", NCAAB_GAME)
        assert [x["period"] for x in m] == ["1st Half", "Halftime", "2nd Half", "Overtime"]
        by = _by(m)
        assert (by["1st Half"]["not_before"], by["1st Half"]["timestamp"]) == (
            NCAAB_GAME[0]["timestamp"], NCAAB_GAME[1]["timestamp"])
        # Halftime sits AFTER `End of 1st Half` and BEFORE the 2nd half.
        assert by["Halftime"]["not_before"] == NCAAB_GAME[2]["timestamp"]
        assert by["2nd Half"]["not_before"] == NCAAB_GAME[4]["timestamp"]
        assert by["Overtime"]["not_before"] == NCAAB_GAME[7]["timestamp"]

    def test_the_tenths_clock_is_a_state_row_that_bounds(self):
        rows = [_obs(140, "0:04.2 - 4th Quarter"), _obs(141, "5:00 - OT")]
        ot = _by(_markers("basketball_wnba", rows))["Overtime"]
        assert ot["not_before"] == rows[0]["timestamp"]
        assert ot["precision"] == pm.PRECISION_BOUNDARY

    def test_the_marker_carries_the_instrument_that_saw_it(self):
        rows = [_obs(5, "12:00 - 1st Quarter", source=pm.SOURCE_ESPN_STATE),
                _obs(6, "11:40 - 1st Quarter", source=pm.SOURCE_ESPN_STATE)]
        assert _markers("basketball_nba", rows)[0]["source"] == pm.SOURCE_ESPN_STATE


class TestUnknownInputIsRefused:
    @pytest.mark.parametrize("sport, rows", [
        # clocks inside each league's period, so only the WORD can refuse them
        ("basketball_nba", ["12:00 - 1st Half", "11:31 - 1st Half"]),
        ("basketball_wncaab", ["10:00 - 1st Half", "9:31 - 1st Half"]),
        ("basketball_ncaab", ["20:00 - 1st Quarter", "19:31 - 1st Quarter"]),
        ("basketball_ncaab", ["End of 2nd Half", "5:00 - 3rd Half"]),
    ])
    def test_a_period_word_the_league_does_not_play_is_not_its_state(self, sport, rows):
        assert _markers(sport, [_obs(i, r) for i, r in enumerate(rows)]) == []

    @pytest.mark.parametrize("sport, opening", [
        ("basketball_nba", "15:00"), ("basketball_wnba", "12:00"), ("basketball_wncaab", "12:00"),
    ])
    def test_a_clock_longer_than_the_leagues_period_is_not_its_game(self, sport, opening):
        """Read as a state, the foreign clock would be a Q2 one poll after the end
        of Q1, the tightest bracket there is. Only the clock rule refuses it."""
        rows = [_obs(37, "End of 1st Quarter"), _obs(38, f"{opening} - 2nd Quarter")]
        assert _markers(sport, rows) == []

    @pytest.mark.parametrize("sport", ["basketball_euroleague", "basketball_nbl", "icehockey_nhl"])
    def test_an_unlisted_league_gets_nothing(self, sport):
        assert _markers(sport, NBA_GAME) == []

    def test_end_of_halftime_is_not_basketball_vocabulary(self):
        """Football ranks `End of Halftime` ABOVE the 3rd quarter. Read here, it
        would turn the 3rd-quarter row into a regression that cannot bound the
        4th, and Q4 would fall to a 45-minute bracket and vanish. (One 3rd-quarter
        row, so the halftime row is not a retracted blip, which a second lower row
        would make it.)"""
        rows = [_obs(68, "0:00.0 - 2nd Quarter"), _obs(69, "End of Halftime"),
                _obs(112, "0:01.0 - 3rd Quarter"), _obs(114, "11:40 - 4th Quarter")]
        q4 = _by(_markers("basketball_nba", rows))["4th Quarter"]
        assert (q4["not_before"], q4["precision"]) == (rows[2]["timestamp"], pm.PRECISION_BOUNDARY)


class TestTheListedTipIsNotATipOff:
    def test_an_opening_clock_alone_is_no_marker(self):
        assert _markers("basketball_nba", [_obs(4, "12:00 - 1st Quarter")], kickoff=T0) == []

    def test_a_running_reading_inside_the_tip_window_is_first_seen_with_the_listing_as_floor(self):
        rows = [_obs(9, "11:40 - 1st Quarter")]
        q1 = _markers("basketball_nba", rows, kickoff=T0)[0]
        assert (q1["period"], q1["timestamp"], q1["not_before"], q1["precision"]) == (
            "1st Quarter", rows[0]["timestamp"], T0.isoformat(), pm.PRECISION_FIRST_SEEN)

    def test_a_clock_that_outran_the_wall_since_the_listing_refuses(self):
        # six minutes of game time three minutes after the listed tip: began earlier
        assert _markers("basketball_nba", [_obs(3, "6:00 - 1st Quarter")], kickoff=T0) == []

    def test_a_first_reading_past_the_bracket_limit_refuses(self):
        assert _markers("basketball_ncaab", [_obs(25, "19:00 - 1st Half")], kickoff=T0) == []

    def test_no_listing_no_earlier_state_no_marker(self):
        assert _markers("basketball_nba", [_obs(9, "11:40 - 1st Quarter")]) == []


class TestFootballRefusalsHoldOnBasketball:
    def test_a_contradictory_instant_neither_carries_nor_bounds(self):
        rows = [_obs(37, "End of 1st Quarter"), _obs(39, "11:40 - 2nd Quarter"),
                _obs(39, "11:41 - 1st Quarter")]
        assert _markers("basketball_nba", rows) == []

    def test_a_stale_row_does_not_tighten_a_bracket(self):
        rows = [_obs(37, "End of 1st Quarter"), _obs(50, "0:30 - 1st Quarter"),
                _obs(51, "11:30 - 2nd Quarter"), _obs(52, "11:00 - 2nd Quarter")]
        q2 = _by(_markers("basketball_nba", rows))["2nd Quarter"]
        assert q2["not_before"] == rows[0]["timestamp"]
        assert q2["precision"] == pm.PRECISION_FIRST_SEEN

    def test_a_one_row_blip_is_not_the_periods_start(self):
        rows = [_obs(37, "End of 1st Quarter"), _obs(38, "11:50 - 3rd Quarter"),
                _obs(39, "11:40 - 2nd Quarter"), _obs(40, "11:00 - 2nd Quarter")]
        assert "3rd Quarter" not in _by(_markers("basketball_nba", rows))

    def test_an_over_wide_bracket_is_no_marker(self):
        rows = [_obs(37, "End of 1st Quarter"), _obs(60, "9:00 - 2nd Quarter")]
        assert _markers("basketball_nba", rows) == []


def _probabilities(rows):
    """espn_history rows that also carry a line, so the domain guard keeps markers."""
    return [dict(r, home_probability=0.55, away_probability=0.45, home_score=0, away_score=0)
            for r in rows]


@pytest.mark.asyncio
class TestServedHistory:
    async def _serve(self, sport_key, rows, plays=()):
        session = _session(
            event_id=15999010, sport_key=sport_key, commence=T0,
            completed=T0 + timedelta(hours=3), plays=list(plays),
            espn_rows=_probabilities([_obs(0, None)] + rows),
        )
        body = await get_event_odds_history(event_id=15999010, hours=720,
                                            response=MagicMock(headers={}), db=session)
        return body["period_markers"]

    @pytest.mark.parametrize("sport, first", [
        ("basketball_nba", "1st Quarter"), ("basketball_ncaab", "1st Half")])
    async def test_the_first_period_reaches_the_payload_in_the_client_contract(self, sport, first):
        rows = NBA_GAME if sport == "basketball_nba" else NCAAB_GAME
        served = _by(await self._serve(sport, rows))
        start = served[first]
        # native `ProjectedFinalPointsMount`: precision in {first_seen, boundary_observed},
        # a non-null not_before, and the league's first-period label.
        assert start["precision"] in (pm.PRECISION_FIRST_SEEN, pm.PRECISION_BOUNDARY)
        assert start["not_before"] == rows[0]["timestamp"]
        assert start["source"] == pm.SOURCE_ESPN_STATE

    async def test_a_first_score_alone_stays_an_unlabelled_score_marker(self):
        """No state text: the scoring-play tier is served exactly as before, with
        no `precision` key, so no client can read a first basket as a tip-off."""
        plays = [{"period": 1, "clock": "11:12", "home_score": 2, "away_score": 0}]
        served = await self._serve("basketball_nba", [], plays=plays)
        assert served and all("precision" not in m and "not_before" not in m for m in served)
