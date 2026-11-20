"""Regression guards for #13112 — withhold sportsbook projected finals on pinned-handicap sports.

Hockey's puck line and baseball's run line are fixed at ±1.5 regardless of win
probability, so ``project_scores(spread, over_under)`` always projects a 1.5
goal/run gap even on a 52% coin flip (e.g. NHL 2.4 to 3.9). The server must stop
serving ``projected_home_score`` and ``projected_away_score`` on hockey and
baseball (with ``projection_unavailable: "pinned_handicap"``) while keeping
real lines (``spread``, ``over_under``), keeping football and basketball
projected finals intact, and leaving ``pm_spread_data`` on ``/history``
untouched.
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from types import SimpleNamespace

import pytest

from app.models.models import Event, Sport
from app.routes.events import (
    _format_event_with_aggregated_odds,
    _format_event_with_latest_odds,
)
from app.tasks.odds_polling import _parse_snapshot_values
from app.utils.odds_math import (
    aggregate_bookmaker_odds,
    refuse_incoherent_projections,
    sportsbook_handicap_is_pinned,
    sportsbook_spread_is_a_margin,
)
from app.utils.recent_line_readings import (
    PINNED_HANDICAP,
    apply_projection,
    projection_from_rows,
    withhold_pinned_handicap_projection,
)

NOW = datetime(2026, 7, 30, 22, 0, 0, tzinfo=timezone.utc)


def _snap(
    *,
    bookmaker: str = "draftkings",
    home_prob: float = 0.52,
    away_prob: float = 0.48,
    home_spread: float = -1.5,
    over_under: float = 6.3,
    proj_home: float | None = 3.9,
    proj_away: float | None = 2.4,
    captured_at: datetime | None = None,
):
    ts = captured_at or (NOW - timedelta(minutes=5))
    return SimpleNamespace(
        id=1,
        event_id=15350934,
        bookmaker=bookmaker,
        captured_at=ts,
        valid_until=ts,
        home_moneyline=-110,
        away_moneyline=-102,
        home_win_probability=home_prob,
        away_win_probability=away_prob,
        home_spread=home_spread,
        over_under=over_under,
        projected_home_score=proj_home,
        projected_away_score=proj_away,
    )


def _fake_event(
    *,
    event_id: int,
    sport_key: str,
    home: str,
    away: str,
    status: str = "scheduled",
):
    return Event(
        id=event_id,
        external_id=f"ext-{event_id}",
        sport_id=1,
        sport=Sport(id=1, key=sport_key, name=sport_key, active=True),
        home_team_name=home,
        away_team_name=away,
        commence_time=NOW + timedelta(hours=1),
        status=status,
        opening_home_probability=0.52,
        opening_away_probability=0.48,
        win_probability_sources={},
        event_tags=[],
    )


class TestPinnedHandicapPredicates:
    @pytest.mark.parametrize(
        "sport_key",
        [
            "icehockey_nhl",
            "icehockey_ahl",
            "icehockey_sweden_hockey_league",
            "icehockey_liiga",
            "icehockey_olympics",
            "baseball_mlb",
            "baseball_ncaa",
            "baseball_kbo",
        ],
    )
    def test_hockey_and_baseball_are_pinned_handicaps(self, sport_key):
        assert sportsbook_handicap_is_pinned(sport_key) is True
        assert sportsbook_spread_is_a_margin(sport_key) is False

    @pytest.mark.parametrize(
        "sport_key",
        [
            "americanfootball_nfl",
            "americanfootball_ncaaf",
            "basketball_nba",
            "basketball_ncaab",
            "basketball_wnba",
            "soccer_epl",
            None,
            "",
        ],
    )
    def test_football_basketball_and_soccer_are_not_pinned(self, sport_key):
        assert sportsbook_handicap_is_pinned(sport_key) is False
        assert sportsbook_spread_is_a_margin(sport_key) is True


class TestPollerStopsWritingHockeyProjections:
    def test_nhl_snapshot_writes_spread_and_total_but_no_projected_scores(self):
        board = {
            "markets": [
                {
                    "key": "h2h",
                    "outcomes": [
                        {"name": "Toronto Maple Leafs", "price": -110},
                        {"name": "Los Angeles Kings", "price": -102},
                    ],
                },
                {
                    "key": "spreads",
                    "outcomes": [
                        {"name": "Toronto Maple Leafs", "price": 195, "point": -1.5},
                        {"name": "Los Angeles Kings", "price": -240, "point": 1.5},
                    ],
                },
                {
                    "key": "totals",
                    "outcomes": [
                        {"name": "Over", "price": -110, "point": 6.3},
                        {"name": "Under", "price": -110, "point": 6.3},
                    ],
                },
            ]
        }
        event_data = {
            "sport_key": "icehockey_nhl",
            "home_team": "Toronto Maple Leafs",
            "away_team": "Los Angeles Kings",
        }
        values = _parse_snapshot_values(board, event_data)
        assert values["home_spread"] == -1.5
        assert values["over_under"] == 6.3
        assert values["projected_home_score"] is None
        assert values["projected_away_score"] is None

    def test_nfl_snapshot_still_writes_projected_scores(self):
        board = {
            "markets": [
                {
                    "key": "h2h",
                    "outcomes": [
                        {"name": "Chiefs", "price": -250},
                        {"name": "Bills", "price": 205},
                    ],
                },
                {
                    "key": "spreads",
                    "outcomes": [
                        {"name": "Chiefs", "price": -110, "point": -6.5},
                        {"name": "Bills", "price": -110, "point": 6.5},
                    ],
                },
                {
                    "key": "totals",
                    "outcomes": [
                        {"name": "Over", "price": -110, "point": 45.5},
                        {"name": "Under", "price": -110, "point": 45.5},
                    ],
                },
            ]
        }
        values = _parse_snapshot_values(
            board,
            {"sport_key": "americanfootball_nfl", "home_team": "Chiefs", "away_team": "Bills"},
        )
        assert values["projected_home_score"] == 26.0
        assert values["projected_away_score"] == 19.5


class TestServeTimeWithholding:
    def test_recent_line_projection_withholds_hockey_and_baseball_but_keeps_lines(self):
        snaps = [_snap(bookmaker="draftkings"), _snap(bookmaker="fanduel")]
        for sport in ("icehockey_nhl", "baseball_mlb"):
            proj = projection_from_rows(snaps, [], now=NOW, sport_key=sport)
            assert proj["projected_home_score"] is None
            assert proj["projected_away_score"] is None
            assert proj["projection_captured_at"] is None
            assert proj["projection_bookmaker_count"] == 0
            assert proj["projection_unavailable"] == PINNED_HANDICAP
            # Real sportsbook lines stay served
            assert proj["home_spread"] == -1.5
            assert proj["over_under"] == 6.3

    def test_recent_line_projection_still_serves_nfl_and_nba(self):
        nfl_snaps = [
            _snap(
                bookmaker="draftkings",
                home_prob=0.68,
                away_prob=0.32,
                home_spread=-6.5,
                over_under=45.5,
                proj_home=26.0,
                proj_away=19.5,
            )
        ]
        proj = projection_from_rows(nfl_snaps, [], now=NOW, sport_key="americanfootball_nfl")
        assert proj["projected_home_score"] == 26.0
        assert proj["projected_away_score"] == 19.5
        assert proj["projection_unavailable"] is None
        assert proj["projection_bookmaker_count"] == 1

    @pytest.mark.parametrize("status", ["scheduled", "live"])
    @pytest.mark.parametrize("sport_key", ["icehockey_nhl", "baseball_mlb"])
    def test_aggregated_formatter_withholds_preexisting_db_hockey_and_baseball_pairs(
        self, status, sport_key
    ):
        # Simulates tonight's pre-existing DB rows carrying 3.9 / 2.4 for NHL
        # on both scheduled and live games.
        snaps = [_snap(bookmaker="draftkings"), _snap(bookmaker="fanduel")]
        agg = aggregate_bookmaker_odds(snaps)
        assert agg["projected_home_score"] == 3.9
        assert agg["projected_away_score"] == 2.4

        event = _fake_event(
            event_id=15350934,
            sport_key=sport_key,
            home="Toronto Maple Leafs",
            away="Los Angeles Kings",
            status=status,
        )
        formatted = _format_event_with_aggregated_odds(
            event,
            {
                "aggregated": agg,
                "snapshots": snaps,
                "all_snapshots": snaps,
                "captured_at": NOW,
            },
        )
        co = formatted["current_odds"]
        assert co["projected_home_score"] is None
        assert co["projected_away_score"] is None
        assert co["projection_unavailable"] == PINNED_HANDICAP
        assert co["projection_bookmaker_count"] == 0
        assert co["projection_captured_at"] is None
        assert co["spread"] == -1.5
        assert co["over_under"] == 6.3
        for bk in formatted["bookmaker_odds"]:
            assert bk["projected_home_score"] is None
            assert bk["projected_away_score"] is None

    @pytest.mark.parametrize(
        "sport_key,spread,total,ph,pa",
        [
            ("americanfootball_nfl", -6.5, 45.5, 26.0, 19.5),
            ("basketball_nba", -5.0, 224.0, 114.5, 109.5),
        ],
    )
    def test_aggregated_formatter_keeps_nfl_and_nba_projected_pairs(
        self, sport_key, spread, total, ph, pa
    ):
        snaps = [
            _snap(
                bookmaker="draftkings",
                home_prob=0.65,
                away_prob=0.35,
                home_spread=spread,
                over_under=total,
                proj_home=ph,
                proj_away=pa,
            )
        ]
        agg = apply_projection(
            aggregate_bookmaker_odds(snaps),
            projection_from_rows(snaps, [], now=NOW, sport_key=sport_key),
        )
        event = _fake_event(
            event_id=99999,
            sport_key=sport_key,
            home="Home Team",
            away="Away Team",
            status="scheduled",
        )
        formatted = _format_event_with_aggregated_odds(
            event,
            {
                "aggregated": agg,
                "snapshots": snaps,
                "all_snapshots": snaps,
                "captured_at": NOW,
            },
        )
        co = formatted["current_odds"]
        assert co["projected_home_score"] == ph
        assert co["projected_away_score"] == pa
        assert co["projection_unavailable"] is None
        assert formatted["bookmaker_odds"][0]["projected_home_score"] == ph
        assert formatted["bookmaker_odds"][0]["projected_away_score"] == pa

    def test_latest_odds_formatter_withholds_hockey_and_keeps_nba(self):
        nhl_ev = _fake_event(
            event_id=15350938,
            sport_key="icehockey_nhl",
            home="Tampa Bay Lightning",
            away="Edmonton Oilers",
        )
        out_nhl = _format_event_with_latest_odds(nhl_ev, _snap())
        assert out_nhl["current_odds"]["projected_home_score"] is None
        assert out_nhl["current_odds"]["projected_away_score"] is None
        assert out_nhl["current_odds"]["projection_unavailable"] == PINNED_HANDICAP

        nba_ev = _fake_event(
            event_id=88888,
            sport_key="basketball_nba",
            home="Boston Celtics",
            away="New York Knicks",
        )
        out_nba = _format_event_with_latest_odds(
            nba_ev, _snap(home_spread=-5.0, over_under=224.0, proj_home=114.5, proj_away=109.5)
        )
        assert out_nba["current_odds"]["projected_home_score"] == 114.5
        assert out_nba["current_odds"]["projected_away_score"] == 109.5

    def test_refuse_incoherent_and_withhold_helpers(self):
        rows = [{"home_probability": 0.58, "projected_home_score": 3.9, "projected_away_score": 2.4}]
        refuse_incoherent_projections(rows, sport_key="icehockey_nhl")
        assert rows[0]["projected_home_score"] is None
        assert rows[0]["projected_away_score"] is None

        agg = {"home_spread": -1.5, "over_under": 6.2, "projected_home_score": 3.9, "projected_away_score": 2.3}
        stripped = withhold_pinned_handicap_projection(agg, "icehockey_nhl")
        assert stripped["projected_home_score"] is None
        assert stripped["projected_away_score"] is None
        assert stripped["home_spread"] == -1.5
        assert stripped["over_under"] == 6.2
        assert stripped["_projection"]["projection_unavailable"] == PINNED_HANDICAP
