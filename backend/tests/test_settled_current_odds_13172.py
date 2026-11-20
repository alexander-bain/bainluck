"""#13172 Option B — finished games serve their settled result, never the last
live price, across all six server routes (game page, lists/search, feed, league
rail, team page, and grouping passthrough).

Guardrails pinned here:
1. Finished draw in a draw-priced sport (soccer): draw 100, home 0, away 0
   (never 50 and 50).
2. Finished with no verified result yet (`final_unresolved`): current-chance
   fields are empty/None, never the last live price.
3. Not finished: a live game in its last minute, a suspended game, and a
   postponed game keep their exact existing behaviour.
4. Downstream lines: a finished game on the feed does not pick up a
   "moved N points since open" line or a movement bonus from serving 100/0.
5. Pregame & non-chance metadata stay intact: `opening_odds`, `prematch_odds`,
   `spread`, `over_under`, `bookmaker_count`, `captured_at`.
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

import pytest
from httpx import ASGITransport, AsyncClient

from app.dependencies.auth import get_optional_user
from app.routes.events import (
    _format_event_with_aggregated_odds,
    _format_event_with_latest_odds,
    _format_event_with_odds,
)
from app.routes.league_futures import _format_game_brief
from app.routes.teams import _format_event_brief
from app.services.database import get_db, get_db_rw
from app.utils.container_machinery import SubjectArtResolver, _hydrate_event_visual_item
from app.utils.feed_reasons import generate_event_reason
from app.utils.feed_scoring import format_event_data
from app.utils.hero_probability import HeroReading, resolve_hero
from app.utils.highlights import compute_highlight
from app.utils.settled_hero import apply_settled_current_odds, settled_current_chance
from tests.integration.test_route_events_seeded import (
    _make_event,
    _make_event_detail_session,
)

FIXED_NOW = datetime(2025, 11, 20, 14, 0, tzinfo=timezone.utc)
FIXED_START = FIXED_NOW - timedelta(hours=4)
FIXED_END = FIXED_NOW - timedelta(hours=1)
FIXED_CAPTURED = FIXED_NOW - timedelta(hours=1, minutes=5)


def _flyers_senators_event(
    *,
    status: str = "completed",
    home_score: int | None = 5,
    away_score: int | None = 6,
    completed_at: datetime | None = FIXED_END,
    sport_key: str = "icehockey_nhl",
    home_team: str = "Ottawa Senators",
    away_team: str = "Philadelphia Flyers",
    live_home_prob: float = 0.5261,
    opening_home: float = 0.583,
    opening_away: float = 0.417,
    period: str | None = "Final/OT",
):
    ev = _make_event(
        id=15350936,
        home_team=home_team,
        away_team=away_team,
        status=status,
        home_score=home_score,
        away_score=away_score,
        home_prob=live_home_prob,
        sport_key=sport_key,
    )
    ev.commence_time = FIXED_START
    ev.completed_at = completed_at
    ev.period = period
    ev.game_clock = "0:42" if status == "live" else None
    ev.opening_home_probability = opening_home
    ev.opening_away_probability = opening_away
    ev.opening_home_spread = -1.5
    ev.opening_over_under = 6.0
    ev.opening_favorite = "home"
    ev.home_team_id = 13381
    ev.away_team_id = 55
    ev.score_source = "espn"
    ev.score_observed_at = FIXED_END
    ev.win_probability_sources = {
        "betting": {
            "value": live_home_prob,
            "home_probability": live_home_prob,
            "updated_at": FIXED_CAPTURED.isoformat(),
        },
        "betting_book_count": 11,
    }
    return ev


def _soccer_draw_event(
    *,
    status: str = "completed",
    home_score: int | None = 0,
    away_score: int | None = 0,
    completed_at: datetime | None = FIXED_END,
):
    return _flyers_senators_event(
        status=status,
        home_score=home_score,
        away_score=away_score,
        completed_at=completed_at,
        sport_key="soccer_brazil_campeonato",
        home_team="Grêmio",
        away_team="Bahia",
        live_home_prob=0.0627,
        opening_home=0.41,
        opening_away=0.29,
        period="FT",
    )


def _sample_odds_data(home_prob: float, away_prob: float):
    return {
        "captured_at": FIXED_CAPTURED,
        "aggregated": {
            "home_probability": home_prob,
            "away_probability": away_prob,
            "home_spread": -1.5,
            "over_under": 7.7,
            "projected_home_score": None,
            "projected_away_score": None,
            "bookmaker_count": 20,
            "projection_captured_at": None,
            "projection_bookmaker_count": 0,
            "projection_unavailable": "pinned_handicap",
        },
        "snapshots": [],
        "all_snapshots": [],
    }


async def _get_detail(event) -> dict:
    from app.main import app
    from app.routes.events import _event_detail_cache, _game_markets_cache

    _game_markets_cache.clear()
    _event_detail_cache.clear()
    session = _make_event_detail_session(event=event)

    async def _mock_get_db():
        yield session

    async def _mock_get_optional_user():
        return None

    app.dependency_overrides[get_db] = _mock_get_db
    app.dependency_overrides[get_db_rw] = _mock_get_db
    app.dependency_overrides[get_optional_user] = _mock_get_optional_user
    try:
        with patch("app.main.init_db", new_callable=AsyncMock):
            async with AsyncClient(
                transport=ASGITransport(app=app), base_url="http://test"
            ) as ac:
                resp = await ac.get(f"/api/events/{event.id}")
        assert resp.status_code == 200, resp.text
        return resp.json()
    finally:
        _event_detail_cache.clear()
        _game_markets_cache.clear()
        app.dependency_overrides.clear()


class TestSettledCurrentChanceHelper:
    def test_two_way_decisive_away_win(self):
        hero = HeroReading(0.0, 1.0, "settled", settled_result="away")
        sc = settled_current_chance(hero, sport_key="icehockey_nhl")
        assert sc.resolved is True
        assert sc.home_probability == 0.0
        assert sc.away_probability == 1.0
        assert sc.draw_probability is None
        assert sc.home_rendered_percent == 0
        assert sc.away_rendered_percent == 100
        assert sc.draw_rendered_percent is None

    def test_three_way_soccer_draw_is_draw_100_not_50_50(self):
        hero = HeroReading(0.5, 0.5, "settled", settled_result="draw")
        sc = settled_current_chance(hero, sport_key="soccer_brazil_campeonato")
        assert sc.resolved is True
        assert sc.home_probability == 0.0
        assert sc.away_probability == 0.0
        assert sc.draw_probability == 1.0
        assert sc.home_rendered_percent == 0
        assert sc.away_rendered_percent == 0
        assert sc.draw_rendered_percent == 100

    def test_three_way_soccer_decisive_home_win_has_draw_zero(self):
        hero = HeroReading(1.0, 0.0, "settled", settled_result="home")
        sc = settled_current_chance(hero, sport_key="soccer_epl")
        assert sc.resolved is True
        assert sc.home_probability == 1.0
        assert sc.away_probability == 0.0
        assert sc.draw_probability == 0.0
        assert sc.home_rendered_percent == 100
        assert sc.away_rendered_percent == 0
        assert sc.draw_rendered_percent == 0

    def test_two_way_tie_keeps_50_50(self):
        hero = HeroReading(0.5, 0.5, "settled", settled_result="draw")
        sc = settled_current_chance(hero, sport_key="americanfootball_nfl")
        assert sc.resolved is True
        assert sc.home_probability == 0.5
        assert sc.away_probability == 0.5
        assert sc.draw_probability is None
        assert sc.home_rendered_percent == 50
        assert sc.away_rendered_percent == 50

    def test_final_unresolved_clears_all_chance_fields(self):
        hero = HeroReading(0.84, 0.16, "final_unresolved")
        sc = settled_current_chance(hero, sport_key="icehockey_nhl")
        assert sc.resolved is False
        assert sc.home_probability is None
        assert sc.away_probability is None
        assert sc.draw_probability is None
        assert sc.home_rendered_percent is None
        assert sc.away_rendered_percent is None
        assert sc.draw_rendered_percent is None

    def test_apply_preserves_spread_total_bookmaker_count_and_captured_at(self):
        existing = {
            "captured_at": FIXED_CAPTURED.isoformat(),
            "home_probability": 0.5261,
            "away_probability": 0.4739,
            "home_rendered_percent": 53,
            "away_rendered_percent": 47,
            "spread": -1.5,
            "over_under": 7.7,
            "bookmaker_count": 20,
        }
        hero = HeroReading(0.0, 1.0, "settled", settled_result="away")
        out = apply_settled_current_odds(existing, hero, sport_key="icehockey_nhl")
        assert out["home_probability"] == 0.0
        assert out["away_probability"] == 1.0
        assert out["home_rendered_percent"] == 0
        assert out["away_rendered_percent"] == 100
        assert out["spread"] == -1.5
        assert out["over_under"] == 7.7
        assert out["bookmaker_count"] == 20
        assert out["captured_at"] == FIXED_CAPTURED.isoformat()


class TestFlyersSenatorsAllSixRoutes:
    """15350936 (Flyers 6 @ Senators 5): last live price 53%/47% for the loser
    must be replaced with 0%/100% settled result on every route."""

    @pytest.mark.asyncio
    async def test_1_game_page(self):
        ev = _flyers_senators_event()
        body = await _get_detail(ev)
        co = body["current_odds"]
        assert co["home_probability"] == 0.0
        assert co["away_probability"] == 1.0
        assert co["home_rendered_percent"] == 0
        assert co["away_rendered_percent"] == 100
        # Non-chance metadata & opening odds stay intact
        assert co["bookmaker_count"] >= 0
        assert body["opening_odds"]["home_probability"] == pytest.approx(0.583)
        assert body["opening_odds"]["away_probability"] == pytest.approx(0.417)

    def test_2_list_and_search_formatters(self):
        ev = _flyers_senators_event()
        odds_data = _sample_odds_data(0.5261, 0.4739)
        row = _format_event_with_aggregated_odds(ev, odds_data)
        co = row["current_odds"]
        assert co["home_probability"] == 0.0
        assert co["away_probability"] == 1.0
        assert co["home_rendered_percent"] == 0
        assert co["away_rendered_percent"] == 100
        assert co["spread"] == -1.5
        assert co["over_under"] == 7.7
        assert co["bookmaker_count"] == 20
        assert row["opening_odds"]["home_probability"] == pytest.approx(0.583)

        snap = SimpleNamespace(
            bookmaker="fanduel",
            captured_at=FIXED_CAPTURED,
            home_moneyline=-110,
            away_moneyline=-110,
            home_win_probability=0.5261,
            away_win_probability=0.4739,
            home_spread=-1.5,
            over_under=7.7,
            projected_home_score=3.9,
            projected_away_score=2.4,
        )
        ev.odds_snapshots = [snap]
        row_odds = _format_event_with_odds(ev)
        assert row_odds["current_odds"]["home_probability"] == 0.0
        assert row_odds["current_odds"]["away_probability"] == 1.0
        assert row_odds["current_odds"]["spread"] == -1.5
        row_latest = _format_event_with_latest_odds(ev, snap)
        assert row_latest["current_odds"]["home_probability"] == 0.0
        assert row_latest["current_odds"]["away_probability"] == 1.0
        assert row_latest["current_odds"]["over_under"] == 7.7

    def test_3_feed_card_and_no_movement_bonus(self):
        ev = _flyers_senators_event()
        hero = resolve_hero(ev)
        # Highlight & reason use the raw pre-format inputs, NEVER the settled 0/100
        hl = compute_highlight(
            status=ev.status,
            commence_time=ev.commence_time,
            sport_key="icehockey_nhl",
            current_home_prob=0.5261,
            current_away_prob=0.4739,
            opening_home_prob=0.583,
            opening_away_prob=0.417,
            now=FIXED_NOW,
            home_team_name=ev.home_team_name,
            away_team_name=ev.away_team_name,
            completed_at=ev.completed_at,
            home_score=5,
            away_score=6,
        )
        reason = generate_event_reason(
            home_team=ev.home_team_name,
            away_team=ev.away_team_name,
            status="completed",
            highlight_reasons=hl.reasons,
            home_probability=0.5261,
            away_probability=0.4739,
            opening_home_prob=0.583,
            home_score=5,
            away_score=6,
            sport="icehockey_nhl",
            opening_away_prob=0.417,
            now=FIXED_NOW,
        )
        assert "moved" not in (reason or "").lower()
        assert "since open" not in (reason or "").lower()

        card = format_event_data(
            event_id=ev.id,
            external_id="nhl-15350936",
            sport_key="icehockey_nhl",
            sport_name="NHL",
            home_team=ev.home_team_name,
            away_team=ev.away_team_name,
            commence_time=ev.commence_time,
            status="completed",
            home_score=5,
            away_score=6,
            current_home_prob=0.5261,
            current_away_prob=0.4739,
            opening_home_prob=0.583,
            opening_away_prob=0.417,
            opening_favorite="home",
            win_probability_sources=ev.win_probability_sources,
            prob_source=None,
            game_clock=None,
            period="Final/OT",
            broadcast_info=None,
            highlight_label=None,
            raw_ei=None,
            inline_tags=[],
            ended_at=FIXED_END,
            hero=hero,
        )
        assert card["current_odds"] == {
            "home_probability": 0.0,
            "away_probability": 1.0,
            "home_rendered_percent": 0,
            "away_rendered_percent": 100,
        }
        assert card["opening_odds"]["home_probability"] == pytest.approx(0.583)

    def test_4_league_rail(self):
        ev = _flyers_senators_event()
        brief = _format_game_brief(ev, "icehockey_nhl")
        assert brief["home_win_probability"] == 0.0
        assert brief["current_odds"] == {
            "home_probability": 0.0,
            "away_probability": 1.0,
            "home_rendered_percent": 0,
            "away_rendered_percent": 100,
        }
        assert brief["source_mark"]["state"] == "settled"
        assert brief["source_mark"]["settled"]["result"] == "Lost"
        assert brief["away_source_mark"]["settled"]["result"] == "Won"
        assert brief["opening_odds"]["home_probability"] == pytest.approx(0.583)

    def test_5_team_page(self):
        ev = _flyers_senators_event()
        senators = SimpleNamespace(id=13381, name="Ottawa Senators")
        flyers = SimpleNamespace(id=55, name="Philadelphia Flyers")

        sen_brief = _format_event_brief(ev, senators)
        assert sen_brief["win_probability"] == 0.0
        assert sen_brief["source_mark"]["state"] == "settled"
        assert sen_brief["source_mark"]["settled"]["result"] == "Lost"
        assert sen_brief["pregame_win_probability"] == pytest.approx(0.583)

        phi_brief = _format_event_brief(ev, flyers)
        assert phi_brief["win_probability"] == 1.0
        assert phi_brief["source_mark"]["state"] == "settled"
        assert phi_brief["source_mark"]["settled"]["result"] == "Won"
        assert phi_brief["pregame_win_probability"] == pytest.approx(0.417)

    def test_6_grouping_passthrough(self):
        ev = _flyers_senators_event()
        row = _format_event_with_aggregated_odds(ev, _sample_odds_data(0.5261, 0.4739))
        item = _hydrate_event_visual_item(row, resolver=SubjectArtResolver())
        assert item is not None
        co = item["card"]["current_odds"]
        assert co["home_probability"] == 0.0
        assert co["away_probability"] == 1.0
        assert co["home_rendered_percent"] == 0
        assert co["away_rendered_percent"] == 100


class TestFinishedSoccerDrawAcrossAllRoutes:
    """Guardrail 1: finished draw in a draw-priced sport -> draw 100, home 0,
    away 0 (never 50 and 50) across every route."""

    @pytest.mark.asyncio
    async def test_game_page_draw_100(self):
        ev = _soccer_draw_event()
        body = await _get_detail(ev)
        co = body["current_odds"]
        assert co["home_probability"] == 0.0
        assert co["away_probability"] == 0.0
        assert co["draw_probability"] == 1.0
        assert co["home_rendered_percent"] == 0
        assert co["away_rendered_percent"] == 0
        assert co["draw_rendered_percent"] == 100
        assert body["hero_probability"] == 0.0
        assert body["hero_probability_away"] == 0.0
        assert body["hero_probability_draw"] == 1.0

    def test_list_feed_league_team_and_grouping_draw_100(self):
        ev = _soccer_draw_event()
        hero = resolve_hero(ev)

        # List/search
        row = _format_event_with_aggregated_odds(ev, _sample_odds_data(0.0627, 0.1844))
        assert row["current_odds"]["home_probability"] == 0.0
        assert row["current_odds"]["away_probability"] == 0.0
        assert row["current_odds"]["draw_probability"] == 1.0
        assert row["current_odds"]["home_rendered_percent"] == 0
        assert row["current_odds"]["away_rendered_percent"] == 0
        assert row["current_odds"]["draw_rendered_percent"] == 100

        # Feed
        card = format_event_data(
            event_id=ev.id,
            external_id="br-15343913",
            sport_key="soccer_brazil_campeonato",
            sport_name="Brasileirão",
            home_team="Grêmio",
            away_team="Bahia",
            commence_time=ev.commence_time,
            status="completed",
            home_score=0,
            away_score=0,
            current_home_prob=0.0627,
            current_away_prob=0.1844,
            current_draw_prob=0.7529,
            opening_home_prob=0.41,
            opening_away_prob=0.29,
            opening_favorite="home",
            win_probability_sources=ev.win_probability_sources,
            prob_source=None,
            game_clock=None,
            period="FT",
            broadcast_info=None,
            highlight_label=None,
            raw_ei=None,
            inline_tags=[],
            ended_at=FIXED_END,
            hero=hero,
        )
        assert card["current_odds"] == {
            "home_probability": 0.0,
            "away_probability": 0.0,
            "draw_probability": 1.0,
            "home_rendered_percent": 0,
            "away_rendered_percent": 0,
            "draw_rendered_percent": 100,
        }
        assert card["hero_probability"] == 0.0
        assert card["hero_probability_away"] == 0.0
        assert card["hero_probability_draw"] == 1.0

        # League rail
        lg = _format_game_brief(ev, "soccer_brazil_campeonato")
        assert lg["home_win_probability"] == 0.0
        assert lg["current_odds"] == {
            "home_probability": 0.0,
            "away_probability": 0.0,
            "draw_probability": 1.0,
            "home_rendered_percent": 0,
            "away_rendered_percent": 0,
            "draw_rendered_percent": 100,
        }
        assert lg["source_mark"]["settled"]["result"] == "Draw"

        # Team page (neither team won; draw=1.0, not 0.5)
        gremio = SimpleNamespace(id=13381, name="Grêmio")
        bahia = SimpleNamespace(id=55, name="Bahia")
        g_brief = _format_event_brief(ev, gremio)
        b_brief = _format_event_brief(ev, bahia)
        assert g_brief["win_probability"] == 0.0
        assert g_brief["draw_probability"] == 1.0
        assert g_brief["source_mark"]["settled"]["result"] == "Draw"
        assert b_brief["win_probability"] == 0.0
        assert b_brief["draw_probability"] == 1.0
        assert b_brief["source_mark"]["settled"]["result"] == "Draw"

        # Grouping passthrough
        item = _hydrate_event_visual_item(row, resolver=SubjectArtResolver())
        assert item is not None
        assert item["card"]["current_odds"]["home_probability"] == 0.0
        assert item["card"]["current_odds"]["away_probability"] == 0.0
        assert item["card"]["current_odds"]["draw_probability"] == 1.0
        assert item["card"]["current_odds"]["draw_rendered_percent"] == 100


class TestFinalUnresolvedEmptiesChanceFields:
    """Guardrail 2: finished with no verified result yet (closed, missing
    completed_at, or missing scores) -> empty current-chance fields everywhere."""

    @pytest.mark.parametrize(
        "status,hs,as_,completed_at",
        [
            ("closed", 5, 6, FIXED_END),
            ("completed", 5, 6, None),
            ("completed", None, None, FIXED_END),
        ],
    )
    @pytest.mark.asyncio
    async def test_all_routes_empty_current_chance(self, status, hs, as_, completed_at):
        ev = _flyers_senators_event(
            status=status, home_score=hs, away_score=as_, completed_at=completed_at
        )
        hero = resolve_hero(ev)
        assert hero is not None and hero.source == "final_unresolved"

        # 1. Game page
        body = await _get_detail(ev)
        assert body["current_odds"]["home_probability"] is None
        assert body["current_odds"]["away_probability"] is None
        assert body["current_odds"]["home_rendered_percent"] is None
        assert body["current_odds"]["away_rendered_percent"] is None

        # 2. List / search
        row = _format_event_with_aggregated_odds(ev, _sample_odds_data(0.5261, 0.4739))
        assert row["current_odds"]["home_probability"] is None
        assert row["current_odds"]["away_probability"] is None
        assert row["current_odds"]["spread"] == -1.5
        assert row["current_odds"]["bookmaker_count"] == 20

        # 3. Feed
        card = format_event_data(
            event_id=ev.id,
            external_id="nhl-15350936",
            sport_key="icehockey_nhl",
            sport_name="NHL",
            home_team=ev.home_team_name,
            away_team=ev.away_team_name,
            commence_time=ev.commence_time,
            status=status,
            home_score=hs,
            away_score=as_,
            current_home_prob=0.5261,
            current_away_prob=0.4739,
            opening_home_prob=0.583,
            opening_away_prob=0.417,
            opening_favorite="home",
            win_probability_sources=ev.win_probability_sources,
            prob_source=None,
            game_clock=None,
            period=None,
            broadcast_info=None,
            highlight_label=None,
            raw_ei=None,
            inline_tags=[],
            ended_at=completed_at,
            hero=hero,
        )
        assert "current_odds" not in card

        # 4. League rail
        lg = _format_game_brief(ev, "icehockey_nhl")
        assert lg["home_win_probability"] is None
        assert "current_odds" not in lg
        assert lg["source_mark"]["state"] == "none"

        # 5. Team page
        senators = SimpleNamespace(id=13381, name="Ottawa Senators")
        tb = _format_event_brief(ev, senators)
        assert tb["win_probability"] is None
        assert tb["source_mark"]["state"] == "none"

        # 6. Grouping passthrough refuses final_unresolved
        assert _hydrate_event_visual_item(row, resolver=SubjectArtResolver()) is None


class TestNearestWrongNeighboursUnchanged:
    """Guardrail 3: a live game in its last minute, a suspended game, and a
    postponed game keep their exact live/current price on every route."""

    @pytest.mark.parametrize(
        "status,period",
        [
            ("live", "3rd"),
            ("suspended", "Suspended"),
            ("suspended", "Postponed"),
            ("postponed", "Postponed"),
        ],
    )
    @pytest.mark.asyncio
    async def test_unfinished_statuses_keep_current_price(self, status, period):
        ev = _flyers_senators_event(
            status=status,
            home_score=5,
            away_score=5,
            completed_at=None,
            period=period,
            live_home_prob=0.5261,
        )
        hero = resolve_hero(ev)
        assert hero is not None and hero.source == "blend"

        # 1. Game page
        body = await _get_detail(ev)
        assert body["current_odds"]["home_probability"] == pytest.approx(0.5261, abs=1e-4)
        assert body["current_odds"]["away_probability"] == pytest.approx(0.4739, abs=1e-4)

        # 2. List / search
        row = _format_event_with_aggregated_odds(ev, _sample_odds_data(0.5261, 0.4739))
        assert row["current_odds"]["home_probability"] == pytest.approx(0.5261, abs=1e-4)
        assert row["current_odds"]["away_probability"] == pytest.approx(0.4739, abs=1e-4)

        # 3. Feed
        card = format_event_data(
            event_id=ev.id,
            external_id="nhl-15350936",
            sport_key="icehockey_nhl",
            sport_name="NHL",
            home_team=ev.home_team_name,
            away_team=ev.away_team_name,
            commence_time=ev.commence_time,
            status=status,
            home_score=5,
            away_score=5,
            current_home_prob=0.5261,
            current_away_prob=0.4739,
            opening_home_prob=0.583,
            opening_away_prob=0.417,
            opening_favorite="home",
            win_probability_sources=ev.win_probability_sources,
            prob_source=None,
            game_clock="0:42" if status == "live" else None,
            period=period,
            broadcast_info=None,
            highlight_label=None,
            raw_ei=None,
            inline_tags=[],
            ended_at=None,
            hero=hero,
        )
        assert card["current_odds"]["home_probability"] == pytest.approx(0.5261, abs=1e-4)
        assert card["current_odds"]["away_probability"] == pytest.approx(0.4739, abs=1e-4)

        # 4. League rail
        lg = _format_game_brief(ev, "icehockey_nhl")
        assert lg["home_win_probability"] == pytest.approx(0.5261, abs=1e-4)
        assert lg["current_odds"]["home_probability"] == pytest.approx(0.5261, abs=1e-4)

        # 5. Team page
        senators = SimpleNamespace(id=13381, name="Ottawa Senators")
        tb = _format_event_brief(ev, senators)
        assert tb["win_probability"] == pytest.approx(0.526, abs=1e-3)
