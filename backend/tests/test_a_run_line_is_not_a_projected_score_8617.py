"""#8617: a baseball run line stops being stored as a projected final score.

The poller turned every book's spread + total into ``projected_home/away_score``.
A baseball run line is pinned at ±1.5 whatever the matchup, so a coin flip
(event 15318355, Pirates @ Tigers, home 0.50) was served as ``4.7 – 3.1`` and
the card printed "Proj 5-3"; the iPhone hero printed the same pair. Refused at
the producer, every surface that prints the pair withholds it.

The dedup arm matters on its own: ``_snapshots_are_equal`` used to ignore the
projected pair, so a book whose prices had not moved kept its stored run-line
projection as the latest row and the refusal never reached the page.
"""

from types import SimpleNamespace

import pytest

from app.tasks.odds_polling import _parse_snapshot_values, _snapshots_are_equal
from app.utils.odds_math import sportsbook_spread_is_a_margin


def _board(home: str, away: str, spread: float, total: float) -> dict:
    return {
        "key": "fanduel",
        "markets": [
            {
                "key": "h2h",
                "outcomes": [
                    {"name": home, "price": -102},
                    {"name": away, "price": -118},
                ],
            },
            {
                "key": "spreads",
                "outcomes": [
                    {"name": home, "point": -1.5, "price": 150},
                    {"name": away, "point": 1.5, "price": -180},
                ]
                if spread < 0
                else [
                    {"name": home, "point": spread, "price": -110},
                    {"name": away, "point": -spread, "price": -110},
                ],
            },
            {
                "key": "totals",
                "outcomes": [
                    {"name": "Over", "point": total, "price": -110},
                    {"name": "Under", "point": total, "price": -110},
                ],
            },
        ],
    }


def _event(sport_key, home="Detroit Tigers", away="Pittsburgh Pirates") -> dict:
    data = {"home_team": home, "away_team": away}
    if sport_key is not None:
        data["sport_key"] = sport_key
    return data


class TestTheRunLineProjectsNothing:
    def test_mlb_run_line_stores_no_projected_pair(self):
        values = _parse_snapshot_values(
            _board("Detroit Tigers", "Pittsburgh Pirates", -1.5, 7.5),
            _event("baseball_mlb"),
        )

        assert values["projected_home_score"] is None
        assert values["projected_away_score"] is None

    def test_mlb_keeps_every_price_it_was_quoted(self):
        values = _parse_snapshot_values(
            _board("Detroit Tigers", "Pittsburgh Pirates", -1.5, 7.5),
            _event("baseball_mlb"),
        )

        assert values["home_spread"] == -1.5
        assert values["home_spread_odds"] == 150
        assert values["over_under"] == 7.5
        assert values["home_moneyline"] == -102
        assert values["home_win_probability"] is not None

    @pytest.mark.parametrize(
        "sport_key", ["basketball_nba", "americanfootball_nfl", "icehockey_nhl"]
    )
    def test_a_sport_whose_spread_is_a_margin_still_projects(self, sport_key):
        # Control: the refusal is baseball's, not every sport's.
        values = _parse_snapshot_values(
            _board("Home", "Away", 3.5, 45.0),
            _event(sport_key, home="Home", away="Away"),
        )

        assert values["projected_home_score"] == 20.8
        assert values["projected_away_score"] == 24.2

    def test_a_feed_without_a_sport_key_keeps_the_old_answer(self):
        values = _parse_snapshot_values(
            _board("Home", "Away", 3.5, 45.0), _event(None, home="Home", away="Away")
        )

        assert values["projected_home_score"] == 20.8


class TestThePredicateMirrorsTheWeb:
    @pytest.mark.parametrize("sport_key", ["baseball_mlb", "baseball_ncaa", "baseball_kbo"])
    def test_baseball_is_not_a_margin(self, sport_key):
        assert sportsbook_spread_is_a_margin(sport_key) is False

    @pytest.mark.parametrize(
        "sport_key", ["icehockey_nhl", "basketball_nba", "soccer_epl", None, ""]
    )
    def test_everything_else_is(self, sport_key):
        assert sportsbook_spread_is_a_margin(sport_key) is True


def _stored(**kw):
    row = {
        "home_moneyline": -102,
        "away_moneyline": -118,
        "home_spread": -1.5,
        "over_under": 7.5,
        "home_win_probability": 0.4943,
        "projected_home_score": 4.5,
        "projected_away_score": 3.0,
    }
    row.update(kw)
    return SimpleNamespace(**row)


class TestTheRefusalReachesTheLatestRow:
    def test_unmoved_prices_with_a_stale_projection_write_a_new_row(self):
        new_values = _parse_snapshot_values(
            _board("Detroit Tigers", "Pittsburgh Pirates", -1.5, 7.5),
            _event("baseball_mlb"),
        )
        existing = _stored(home_win_probability=new_values["home_win_probability"])

        assert _snapshots_are_equal(existing, new_values) is False

    def test_a_row_that_already_refused_is_deduped(self):
        new_values = _parse_snapshot_values(
            _board("Detroit Tigers", "Pittsburgh Pirates", -1.5, 7.5),
            _event("baseball_mlb"),
        )
        existing = _stored(
            home_win_probability=new_values["home_win_probability"],
            projected_home_score=None,
            projected_away_score=None,
        )

        assert _snapshots_are_equal(existing, new_values) is True

    def test_a_margin_sport_writes_no_extra_row(self):
        # The pair is a function of spread + total there, so an unmoved board
        # dedups exactly as it did before.
        new_values = _parse_snapshot_values(
            _board("Home", "Away", 3.5, 45.0), _event("basketball_nba", "Home", "Away")
        )
        existing = _stored(
            home_spread=3.5,
            over_under=45.0,
            home_win_probability=new_values["home_win_probability"],
            projected_home_score=20.8,
            projected_away_score=24.2,
        )

        assert _snapshots_are_equal(existing, new_values) is True
