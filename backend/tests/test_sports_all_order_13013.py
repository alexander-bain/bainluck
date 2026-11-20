"""Unit & contract tests for Rulings 256: B + 267: A (#13013) Sports "All" order."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

import pytest

from app.utils.sports_all_order import (
    is_sports_all_major_league,
    order_sports_all_feed,
)

NOW = datetime(2025, 1, 15, 22, 0, 0, tzinfo=timezone.utc)


def _event_card(
    event_id: int,
    *,
    sport: str = "basketball_nba",
    status: str = "live",
    score: float = 80.0,
    home_prob: float | None = 0.55,
    away_prob: float | None = 0.45,
    commence_offset: timedelta = timedelta(hours=-1),
    league: str | None = None,
    home_team_id: int | None = None,
    away_team_id: int | None = None,
) -> dict:
    data: dict = {
        "id": event_id,
        "sport": sport,
        "status": status,
        "home_team": f"Home {event_id}",
        "away_team": f"Away {event_id}",
        "commence_time": (NOW + commence_offset).isoformat(),
    }
    if league is not None:
        data["league"] = league
    if home_team_id is not None:
        data["home_team_data"] = {"team_id": home_team_id}
    if away_team_id is not None:
        data["away_team_data"] = {"team_id": away_team_id}
    if home_prob is not None and away_prob is not None:
        data["current_odds"] = {
            "home_probability": home_prob,
            "away_probability": away_prob,
        }
    return {
        "type": "event",
        "score": score,
        "_rank_score": score,
        "data": data,
    }


def _futures_card(market_id: int, *, score: float = 95.0, card_type: str = "futures") -> dict:
    return {
        "type": card_type,
        "score": score,
        "_rank_score": score,
        "data": {"id": market_id, "name": f"Championship {market_id}"},
    }


class TestApprovedMajorMinorLeagueList267A:
    @pytest.mark.parametrize(
        ("sport_key", "league", "expected_major"),
        [
            # Major leagues stay on main "All"
            ("americanfootball_nfl", None, True),
            ("americanfootball_ncaaf", None, True),
            ("basketball_nba", None, True),
            ("basketball_wnba", None, True),
            ("basketball_ncaab", None, True),
            ("basketball_wncaab", None, True),
            ("baseball_mlb", None, True),
            ("icehockey_nhl", None, True),
            ("soccer_epl", None, True),
            ("soccer_uefa_champs_league", None, True),
            ("soccer_spain_la_liga", None, True),
            ("soccer_germany_bundesliga", None, True),
            ("soccer_italy_serie_a", None, True),
            ("soccer_france_ligue_one", None, True),
            ("soccer_uefa_europa_league", None, True),
            ("soccer_usa_mls", None, True),
            ("soccer_fifa_world_cup", None, True),
            ("soccer_conmebol_copa_libertadores", None, True),
            ("soccer_uefa_nations_league", None, True),
            ("tennis_atp_us_open", None, True),
            ("tennis_wta_wimbledon", None, True),
            # 267: A — regular ATP & WTA Tour stops stay on main "All"
            ("tennis_atp", None, True),
            ("tennis_wta", None, True),
            ("tennis_atp_dubai", None, True),
            ("tennis_wta_qatar_open", None, True),
            ("golf_pga", None, True),
            ("golf_lpga", None, True),
            ("mma_mixed_martial_arts", None, True),
            ("mma_ufc", None, True),
            ("cricket_t20_world_cup", None, True),
            ("icehockey_olympics", None, True),
            # Minor/niche leagues tuck behind "and more"
            ("tennis_atp_challenger_milan", None, False),
            ("tennis_atp", "ATP Challenger Tour", False),
            ("tennis_wta", "ITF Women's Tour", False),
            ("tennis_itf_men", None, False),
            ("tennis_other", None, False),
            ("soccer_efl_champ", None, False),
            ("soccer_england_league1", None, False),
            ("soccer_england_league2", None, False),
            ("soccer_uefa_europa_conference_league", None, False),
            ("soccer_mexico_ligamx", None, False),
            ("soccer_brazil_serie_a", None, False),
            ("soccer_netherlands_eredivisie", None, False),
            ("soccer_portugal_primeira_liga", None, False),
            ("soccer_fa_cup", None, False),
            ("icehockey_ahl", None, False),
            ("icehockey_sweden_hockey_league", None, False),
            ("icehockey_sweden_allsvenskan", None, False),
            ("icehockey_liiga", None, False),
            ("icehockey_mestis", None, False),
            ("basketball_euroleague", None, False),
            ("basketball_nbl", None, False),
            ("americanfootball_ncaaf_fcs", None, False),
            ("americanfootball_cfl", None, False),
            ("americanfootball_ufl", None, False),
            ("baseball_mlb_preseason", None, False),
            ("baseball_ncaa", None, False),
            ("boxing_boxing", None, False),
            ("cricket_international_t20", None, False),
            ("cricket_test_match", None, False),
            ("rugbyleague_nrl", None, False),
            ("rugbyunion_six_nations", None, False),
            ("aussierules_afl", None, False),
            ("lacrosse_ncaa", None, False),
            ("lacrosse_pll", None, False),
        ],
    )
    def test_league_classification(self, sport_key, league, expected_major):
        data = {"league": league} if league else None
        assert is_sports_all_major_league(sport_key, event_data=data) is expected_major

    def test_followed_team_or_pinned_event_stays_on_main_view(self):
        minor_data = {
            "id": 9001,
            "league": "AHL",
            "home_team_data": {"team_id": 555},
            "away_team_data": {"team_id": 556},
        }
        assert is_sports_all_major_league("icehockey_ahl", event_data=minor_data) is False
        assert (
            is_sports_all_major_league(
                "icehockey_ahl", event_data=minor_data, followed_team_ids={555}
            )
            is True
        )
        assert (
            is_sports_all_major_league(
                "icehockey_ahl", event_data=minor_data, pinned_event_ids={9001}
            )
            is True
        )


class TestSportsAllFourBlockOrder256B:
    def test_four_block_order_and_live_in_doubt_above_decided_and_futures_off_seat_1(self):
        items = [
            # High-scoring future used to take Seat 1
            _futures_card(1, score=99.0),
            # Decided live NBA blowout (99%) with high score
            _event_card(10, sport="basketball_nba", status="live", score=92.0, home_prob=0.99, away_prob=0.01),
            # Unpriced live NBA game
            _event_card(11, sport="basketball_nba", status="live", score=91.0, home_prob=None, away_prob=None),
            # In-doubt live NBA game (52%)
            _event_card(12, sport="basketball_nba", status="live", score=84.0, home_prob=0.52, away_prob=0.48),
            # In-doubt live NHL game (58%) with higher score than NBA #12
            _event_card(13, sport="icehockey_nhl", status="live", score=88.0, home_prob=0.58, away_prob=0.42),
            # Minor-league live game (Challenger tennis)
            _event_card(14, sport="tennis_atp_challenger_milan", status="live", score=95.0, home_prob=0.51, away_prob=0.49),
            # Starting within 6h (major & minor)
            _event_card(20, sport="basketball_nba", status="scheduled", score=70.0, commence_offset=timedelta(hours=2)),
            _event_card(21, sport="icehockey_ahl", status="scheduled", score=85.0, commence_offset=timedelta(hours=1)),
            # Recent final (major & minor)
            _event_card(30, sport="americanfootball_nfl", status="completed", score=89.0, commence_offset=timedelta(hours=-3)),
            _event_card(31, sport="soccer_efl_champ", status="completed", score=93.0, commence_offset=timedelta(hours=-2)),
            # Later upcoming (> 6h)
            _event_card(40, sport="americanfootball_nfl", status="scheduled", score=96.0, commence_offset=timedelta(hours=20)),
            # Golf tournament card belongs on the futures shelf
            _futures_card(2, score=80.0, card_type="tournament"),
        ]

        ordered = order_sports_all_feed(items, now=NOW)
        ids = [i["data"]["id"] for i in ordered]

        # Expected order:
        # 1. Live major: in-doubt sorted by score (13, 12) -> decided (10) -> unpriced (11)
        # 2. Live minor (tucked): (14)
        # 3. Starting within 6h: major (20) -> minor (21)
        # 4. Recent finals: major (30) -> minor (31)
        # 5. Futures & tournaments shelf: (1, 2)
        # 6. Later upcoming (> 6h): (40)
        assert ids == [13, 12, 10, 11, 14, 20, 21, 30, 31, 1, 2, 40]

        # Present-only `sports_all_tucked` marker only on minor-league event cards
        by_id = {i["data"]["id"]: i["data"] for i in ordered}
        assert by_id[14].get("sports_all_tucked") is True
        assert by_id[21].get("sports_all_tucked") is True
        assert by_id[31].get("sports_all_tucked") is True
        for major_id in (10, 11, 12, 13, 20, 30, 40, 1, 2):
            assert "sports_all_tucked" not in by_id[major_id]

    def test_quiet_day_with_no_live_and_no_6h_upcoming_lets_futures_shelf_lead(self):
        items = [
            _event_card(30, sport="americanfootball_nfl", status="completed", score=90.0, commence_offset=timedelta(hours=-3)),
            _event_card(40, sport="basketball_nba", status="scheduled", score=88.0, commence_offset=timedelta(hours=10)),
            _futures_card(1, score=82.0),
            _futures_card(2, score=75.0, card_type="tournament"),
        ]
        ordered = order_sports_all_feed(items, now=NOW)
        assert [i["data"]["id"] for i in ordered] == [1, 2, 30, 40]

    def test_does_not_mutate_input_cards(self):
        minor = _event_card(14, sport="icehockey_ahl", status="live", score=80.0)
        ordered = order_sports_all_feed([minor], now=NOW)
        assert "sports_all_tucked" not in minor["data"]
        assert ordered[0]["data"]["sports_all_tucked"] is True

    def test_imminent_block_sorts_strictly_by_interestingness_without_league_cap(self):
        items = [
            _event_card(1, sport="icehockey_nhl", status="scheduled", score=60.0, commence_offset=timedelta(hours=1)),
            _event_card(2, sport="basketball_nba", status="scheduled", score=92.0, commence_offset=timedelta(hours=3)),
            _event_card(3, sport="basketball_nba", status="scheduled", score=88.0, commence_offset=timedelta(hours=4)),
            _event_card(4, sport="basketball_nba", status="scheduled", score=84.0, commence_offset=timedelta(hours=2)),
            _event_card(5, sport="americanfootball_nfl", status="scheduled", score=95.0, commence_offset=timedelta(hours=5)),
        ]
        ordered = order_sports_all_feed(items, now=NOW)
        assert [i["data"]["id"] for i in ordered] == [5, 2, 3, 4, 1]

    @pytest.mark.parametrize("recent_finals_count", [0, 4, 17])
    def test_quiet_clock_caps_shelf_lead_and_puts_games_and_upcoming_in_first_20(
        self, recent_finals_count
    ):
        """Fable look #13095: quiet clock with 49 non-game cards in the pool —
        first 20 seats hold at least 12 games and the first upcoming game sits
        inside the first 20 when one exists; zero items dropped."""
        shelf = [_futures_card(1000 + i, score=99.0 - i * 0.1) for i in range(49)]
        finals = [
            _event_card(
                2000 + i,
                sport="basketball_nba",
                status="completed",
                score=85.0 - i,
                commence_offset=timedelta(hours=-3),
            )
            for i in range(recent_finals_count)
        ]
        # Tomorrow's upcoming games in reverse start-time order to prove start-time sort.
        upcoming = [
            _event_card(
                3000 + i,
                sport="basketball_nba",
                status="scheduled",
                score=70.0 + i,
                commence_offset=timedelta(hours=20 - i),
            )
            for i in range(12)
        ]
        older = [
            _event_card(
                4000 + i,
                sport="basketball_nba",
                status="completed",
                score=60.0,
                commence_offset=timedelta(hours=-48),
            )
            for i in range(3)
        ]
        pool = shelf + finals + upcoming + older
        ordered = order_sports_all_feed(pool, now=NOW)
        assert len(ordered) == len(pool), "must never drop any item"

        first_20 = ordered[:20]
        games_in_20 = [c for c in first_20 if c["type"] == "event"]
        assert len(games_in_20) >= 12, f"expected >= 12 games in first 20, got {len(games_in_20)}"

        # First 8 seats are the capped shelf lead.
        assert all(c["type"] != "event" for c in ordered[:8])
        assert ordered[8]["type"] == "event"

        # First upcoming game is inside the first 20, ordered by start time ascending.
        upcoming_positions = [
            idx
            for idx, c in enumerate(ordered)
            if c["type"] == "event" and c["data"]["status"] == "scheduled"
        ]
        assert upcoming_positions[0] < 20, (
            f"first upcoming game landed at seat {upcoming_positions[0] + 1}, outside first 20"
        )
        ordered_upcoming_ids = [ordered[idx]["data"]["id"] for idx in upcoming_positions]
        # 3011 starts in +9h, 3010 in +10h, ..., 3000 in +20h
        assert ordered_upcoming_ids == [3000 + i for i in range(11, -1, -1)]

        # Remaining shelf cards appear after the games and before older finals.
        last_shelf_pos = max(idx for idx, c in enumerate(ordered) if c["type"] != "event")
        first_older_pos = min(
            idx for idx, c in enumerate(ordered) if c["data"]["id"] in {4000, 4001, 4002}
        )
        assert last_shelf_pos < first_older_pos
