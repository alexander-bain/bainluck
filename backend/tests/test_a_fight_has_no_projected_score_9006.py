"""#9006: a fight stops being stored as a projected final score.

The poller turned every book's spread + total into ``projected_home/away_score``.
On a fight the total is a ROUNDS line and the spread is no margin of anything,
so the pair is nonsense and can go negative:

- event 15314292 (Rosas Jr v Barcelos, UFC, 2026-09-27 01:42Z) served
  ``spread -7.5, over_under 3.7 -> 5.8 / -1.8`` and the card printed "Proj 6--2";
- event 15314289 (a settled UFC bout) history carried
  ``over_under 2.5 -> 3.0 / -0.5`` on 39 of 86 points.

The web already declares it (``marketMapUtils.ts``: ``match: ["mma", "boxing"]``,
``sportsbookSpreadIsAMargin: false``); this is the producer's half, through the
same predicate that refuses baseball's run line (#8617).
"""

from types import SimpleNamespace

import pytest

from app.tasks.odds_polling import _parse_snapshot_values, _snapshots_are_equal
from app.utils.odds_math import sportsbook_spread_is_a_margin


def _board(home: str, away: str, spread: float, total: float) -> dict:
    return {
        "key": "draftkings",
        "markets": [
            {
                "key": "h2h",
                "outcomes": [
                    {"name": home, "price": -400},
                    {"name": away, "price": 310},
                ],
            },
            {
                "key": "spreads",
                "outcomes": [
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


def _event(sport_key, home="Raul Rosas Jr", away="Raoni Barcelos") -> dict:
    return {"home_team": home, "away_team": away, "sport_key": sport_key}


class TestAFightProjectsNothing:
    # The two production specimens, by their served spread/total.
    @pytest.mark.parametrize(
        "spread,total", [(-7.5, 3.7), (-3.5, 2.5)], ids=["15314292", "15314289"]
    )
    def test_the_ufc_specimens_store_no_projected_pair(self, spread, total):
        values = _parse_snapshot_values(
            _board("Raul Rosas Jr", "Raoni Barcelos", spread, total),
            _event("mma_mixed_martial_arts"),
        )

        assert values["projected_home_score"] is None
        assert values["projected_away_score"] is None

    @pytest.mark.parametrize("sport_key", ["mma_mixed_martial_arts", "mma_ufc", "boxing_boxing"])
    def test_every_fight_key_refuses(self, sport_key):
        values = _parse_snapshot_values(
            _board("Raul Rosas Jr", "Raoni Barcelos", -7.5, 3.7), _event(sport_key)
        )

        assert values["projected_home_score"] is None
        assert values["projected_away_score"] is None

    def test_a_fight_keeps_every_price_it_was_quoted(self):
        values = _parse_snapshot_values(
            _board("Raul Rosas Jr", "Raoni Barcelos", -7.5, 3.7),
            _event("mma_mixed_martial_arts"),
        )

        assert values["home_spread"] == -7.5
        assert values["home_spread_odds"] == -110
        assert values["over_under"] == 3.7
        assert values["home_moneyline"] == -400
        assert values["home_win_probability"] is not None

    @pytest.mark.parametrize(
        "sport_key", ["americanfootball_nfl", "basketball_nba", "icehockey_nhl", "soccer_epl"]
    )
    def test_a_points_sport_still_projects(self, sport_key):
        # Control: the refusal is the fight's, not every sport's.
        values = _parse_snapshot_values(
            _board("Home", "Away", 3.5, 45.0), _event(sport_key, home="Home", away="Away")
        )

        assert values["projected_home_score"] == 20.8
        assert values["projected_away_score"] == 24.2

    def test_baseball_still_refuses(self):
        values = _parse_snapshot_values(
            _board("Home", "Away", -1.5, 7.5), _event("baseball_mlb", home="Home", away="Away")
        )

        assert values["projected_home_score"] is None


class TestThePredicateMirrorsTheWeb:
    @pytest.mark.parametrize(
        "sport_key", ["mma_mixed_martial_arts", "mma_ufc", "boxing_boxing", "MMA_UFC"]
    )
    def test_a_fight_is_not_a_margin(self, sport_key):
        assert sportsbook_spread_is_a_margin(sport_key) is False

    @pytest.mark.parametrize(
        "sport_key",
        ["americanfootball_nfl", "basketball_nba", "icehockey_nhl", "tennis_atp_us_open", None, ""],
    )
    def test_points_sports_and_unknowns_still_are(self, sport_key):
        assert sportsbook_spread_is_a_margin(sport_key) is True


class TestTheRefusalReachesTheLatestRow:
    def test_unmoved_prices_with_a_stale_fight_projection_write_a_new_row(self):
        # A fight whose prices have not moved must not keep its stored 5.8 / -1.8
        # as the latest row, or the refusal never reaches the payload.
        new_values = _parse_snapshot_values(
            _board("Raul Rosas Jr", "Raoni Barcelos", -7.5, 3.7),
            _event("mma_mixed_martial_arts"),
        )
        existing = SimpleNamespace(
            home_moneyline=new_values["home_moneyline"],
            away_moneyline=new_values["away_moneyline"],
            home_spread=-7.5,
            over_under=3.7,
            home_win_probability=new_values["home_win_probability"],
            projected_home_score=5.8,
            projected_away_score=-1.8,
        )

        assert _snapshots_are_equal(existing, new_values) is False
