"""Guard: a finished soccer game stored twice, minutes apart, on one scoreline, is one card (#3391).

THE PAGE. `bainluck.com/search?q=lafc` at 390px, 2026-09-27 01:5xZ, after PR
#8988 let "lafc" reach the Odds API's `Los Angeles FC` rows: tonight's game once,
then three finished LAFC games twice each. Production:

    15315799  San Jose v LAFC               espn 761817   09-19 23:30Z  2-2
    15311364  San Jose v Los Angeles FC     odds_api      09-19 23:40Z  2-2
    15309106  Sporting KC v LAFC            espn 761806   09-13 00:30Z  3-1
    15301218  Sporting KC v Los Angeles FC  odds_api      09-13 00:41Z  3-1
    15305754  LAFC v Red Bull New York      espn 761795   09-10 02:30Z  2-0
    15298741  Los Angeles FC v New York Red Bulls  odds_api  09-10 02:40Z  2-0

The soccer fold's clock bound is five minutes, so ten and eleven were never
asked the name question; the Red Bulls pair also needed the club alias.
`SETTLED_SOCCER_KICKOFF_DRIFT` lets a pair that is final on ONE scoreline be
asked it up to 25 minutes apart. Everything unfinished keeps five.
"""

from datetime import datetime, timedelta, timezone

import pytest

import app.utils.event_twin_fold as fold_module
from app.utils.event_twin_fold import fold_twin_events

MLS_SPORT_ID = 40
ESPN_KICKOFF = datetime(2026, 9, 19, 23, 30, tzinfo=timezone.utc)


class _Sport:
    def __init__(self, key):
        self.key = key


class _Row:
    """The subset of `Event` the fold reads. Not a MagicMock (an auto-attribute
    mock makes every `espn_id` truthy and every status anything at all)."""

    def __init__(self, id, home, away, *, minutes=0, espn_id=None, external_id=None,
                 status="completed", score=(2, 2), sources=None, sport_key="soccer_usa_mls",
                 commence_time_source="espn"):
        self.id = id
        self.sport_id = MLS_SPORT_ID
        self.sport = _Sport(sport_key)
        self.home_team_name = home
        self.away_team_name = away
        self.commence_time = ESPN_KICKOFF + timedelta(minutes=minutes)
        self.status = status
        self.home_score, self.away_score = score if score is not None else (None, None)
        self.espn_id = espn_id
        self.external_id = external_id
        self.commence_time_source = commence_time_source
        self.win_probability_sources = sources


def _san_jose_pair(**odds_overrides):
    """The production pair, read 2026-09-27 01:5xZ."""
    espn = _Row(15315799, "San Jose Earthquakes", "LAFC", espn_id="761817")
    odds = dict(
        minutes=10, external_id="74f2c90f26", commence_time_source="odds_api",
        sources={"betting": {"value": 0.38}},
    )
    odds.update(odds_overrides)
    return espn, _Row(15311364, "San Jose Earthquakes", "Los Angeles FC", **odds)


def _served_ids(rows):
    return sorted(e.id for e in fold_twin_events(rows).events)


class TestTheFinishedPairsServeOnce:
    def test_san_jose_ten_minutes_apart_folds(self):
        espn, odds = _san_jose_pair()
        assert len(_served_ids([espn, odds])) == 1

    def test_sporting_kc_eleven_minutes_apart_folds(self):
        espn = _Row(15309106, "Sporting Kansas City", "LAFC", espn_id="761806", score=(3, 1))
        odds = _Row(15301218, "Sporting Kansas City", "Los Angeles FC", minutes=11,
                    external_id="4076bf9617", score=(3, 1), commence_time_source="odds_api")
        assert len(_served_ids([espn, odds])) == 1

    def test_red_bulls_folds_under_the_club_alias(self):
        espn = _Row(15305754, "LAFC", "Red Bull New York", espn_id="761795", score=(2, 0))
        odds = _Row(15298741, "Los Angeles FC", "New York Red Bulls", minutes=10,
                    external_id="7ac3342859", score=(2, 0), commence_time_source="odds_api")
        assert len(_served_ids([espn, odds])) == 1

    def test_the_surviving_card_keeps_the_stranded_venue(self):
        espn, odds = _san_jose_pair()
        result = fold_twin_events([espn, odds])
        (survivor,) = result.events
        assert survivor.id == 15315799, "the ESPN-anchored row is the card"
        assert "betting" in result.merged_sources[survivor.id]

    def test_the_whole_lafc_search_page_serves_each_game_once(self):
        """All three pairs on one page, the way search hands them to the fold."""
        rows = [
            *_san_jose_pair(),
            _Row(15309106, "Sporting Kansas City", "LAFC", espn_id="761806", score=(3, 1),
                 minutes=-6 * 24 * 60 - 23 * 60),
            _Row(15301218, "Sporting Kansas City", "Los Angeles FC", external_id="4076bf9617",
                 score=(3, 1), minutes=-6 * 24 * 60 - 23 * 60 + 11,
                 commence_time_source="odds_api"),
        ]
        assert len(_served_ids(rows)) == 2


class TestOnlyASettledPairBuysTheWiderClock:
    def test_an_unscored_pair_ten_minutes_apart_stays_two_cards(self):
        espn, odds = _san_jose_pair(status="scheduled", score=None)
        espn.status, espn.home_score, espn.away_score = "scheduled", None, None
        assert len(_served_ids([espn, odds])) == 2

    def test_two_scorelines_stay_two_cards(self):
        espn, odds = _san_jose_pair(score=(1, 2))
        assert len(_served_ids([espn, odds])) == 2

    def test_a_live_row_stays_two_cards(self):
        espn, odds = _san_jose_pair(status="live")
        assert len(_served_ids([espn, odds])) == 2

    def test_one_side_missing_a_score_stays_two_cards(self):
        espn, odds = _san_jose_pair(score=None)
        assert len(_served_ids([espn, odds])) == 2

    def test_two_espn_ids_stay_two_cards(self):
        espn, odds = _san_jose_pair(espn_id="761999")
        assert len(_served_ids([espn, odds])) == 2

    def test_past_the_settled_bound_stays_two_cards(self):
        espn, odds = _san_jose_pair(minutes=26)
        assert len(_served_ids([espn, odds])) == 2

    def test_a_different_club_on_one_scoreline_stays_two_cards(self):
        espn, _ = _san_jose_pair()
        galaxy = _Row(15311365, "San Jose Earthquakes", "LA Galaxy", minutes=10,
                      external_id="0000000000", commence_time_source="odds_api")
        assert len(_served_ids([espn, galaxy])) == 2

    def test_an_unfinished_pair_inside_five_minutes_still_folds(self):
        """The narrow bound is untouched for everything else."""
        espn, odds = _san_jose_pair(minutes=3, status="scheduled", score=None)
        espn.status, espn.home_score, espn.away_score = "scheduled", None, None
        assert len(_served_ids([espn, odds])) == 1


class TestTheGuardsAreNotVacuous:
    def test_without_the_settled_bound_the_specimen_does_not_fold(self, monkeypatch):
        monkeypatch.setattr(
            fold_module, "SETTLED_SOCCER_KICKOFF_DRIFT", fold_module.SOCCER_KICKOFF_DRIFT
        )
        espn, odds = _san_jose_pair()
        assert len(_served_ids([espn, odds])) == 2

    def test_without_the_scoreline_licence_the_unscored_control_would_fold(self, monkeypatch):
        """The unscored control is refused by the licence, not by the names."""
        monkeypatch.setattr(fold_module, "_settled_on_one_scoreline", lambda l, r: True)
        espn, odds = _san_jose_pair(status="scheduled", score=None)
        espn.status, espn.home_score, espn.away_score = "scheduled", None, None
        assert len(_served_ids([espn, odds])) == 1

    @pytest.mark.parametrize("minutes", [10, 11, 15, 20])
    def test_every_measured_gap_is_inside_the_bound(self, minutes):
        espn, odds = _san_jose_pair(minutes=minutes)
        assert len(_served_ids([espn, odds])) == 1
