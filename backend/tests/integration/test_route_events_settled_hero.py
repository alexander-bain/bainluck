"""Q441 (#1495) — GET /api/events/{id} resolves a finished game's hero to the result.

RED-FIRST against master: on the unfixed route every specimen below comes back with
``hero_probability_source == "blend"`` and a number that points at the team that lost.

The specimens are production rows read through the real route on 2026-08-29 and
verified against ESPN before the fix was written — see ``app/utils/settled_hero``.

This drives the REAL route rather than the pure helper on purpose. The helper being
correct is not the ship; the ship is the payload a client actually receives, and a
pure-lib guard stays green when the route forgets to call it.
"""

from datetime import datetime, timedelta, timezone
from unittest.mock import AsyncMock, patch

import pytest
from httpx import ASGITransport, AsyncClient

from app.dependencies.auth import get_optional_user
from app.services.database import get_db, get_db_rw

from .test_route_events_seeded import _make_event, _make_event_detail_session

# (event_id, home, away, home_score, away_score, blend_home, winner)
# blend_home is what production published as hero_probability on 2026-08-29.
SETTLED_SPECIMENS = [
    (15294037, "Villanova Wildcats", "William and Mary Tribe", 32, 35, 0.8199, "away"),
    (15291335, "Carolina Panthers", "Houston Texans", 16, 13, 0.4859, "home"),
    (15195988, "Watford", "Peterborough United", 1, 5, 0.6492, "away"),
    (15200188, "Criciuma", "Fortaleza", 0, 2, 0.6845, "away"),
    (15193258, "Sarmiento de Junin", "Estudiantes", 2, 0, 0.4533, "home"),
]


def _settled_event(event_id, home, away, hs, as_, blend_home, status="completed"):
    """A finished event whose blend disagrees with its own final score."""
    event = _make_event(
        id=event_id,
        home_team=home,
        away_team=away,
        status=status,
        home_score=hs,
        away_score=as_,
        home_prob=blend_home,
    )
    event.commence_time = datetime.now(timezone.utc) - timedelta(hours=4)
    event.completed_at = datetime.now(timezone.utc) - timedelta(hours=1)
    # a single source, so the weighted median IS blend_home and the specimen
    # reproduces production's number exactly rather than approximately.
    event.win_probability_sources = {
        "betting": {"value": blend_home, "home_probability": blend_home}
    }
    event.game_clock = None
    event.period = None
    return event


async def _get(event):
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


class TestSettledHeroResolvesToTheWinner:
    @pytest.mark.parametrize(
        "event_id,home,away,hs,as_,blend_home,winner", SETTLED_SPECIMENS
    )
    async def test_hero_points_at_the_team_that_won(
        self, event_id, home, away, hs, as_, blend_home, winner
    ):
        body = await _get(_settled_event(event_id, home, away, hs, as_, blend_home))

        hero = body["hero_probability"]
        assert hero is not None
        home_won = winner == "home"
        assert (hero > 0.5) is home_won, (
            f"{event_id}: hero {hero} still points at the loser "
            f"({home} {hs} - {away} {as_})"
        )

    @pytest.mark.parametrize(
        "event_id,home,away,hs,as_,blend_home,winner", SETTLED_SPECIMENS
    )
    async def test_hero_is_terminal_and_labelled_settled(
        self, event_id, home, away, hs, as_, blend_home, winner
    ):
        body = await _get(_settled_event(event_id, home, away, hs, as_, blend_home))

        assert body["hero_probability_source"] == "settled"
        assert body["hero_settled_result"] == winner
        assert {body["hero_probability"], body["hero_probability_away"]} == {0.0, 1.0}

    @pytest.mark.parametrize(
        "event_id,home,away,hs,as_,blend_home,winner", SETTLED_SPECIMENS
    )
    async def test_the_published_number_actually_changed(
        self, event_id, home, away, hs, as_, blend_home, winner
    ):
        """Guards against a fix that agrees with the broken value."""
        body = await _get(_settled_event(event_id, home, away, hs, as_, blend_home))
        assert body["hero_probability"] != pytest.approx(blend_home, abs=1e-6)


class TestSettledHeroKills:
    """The must-not-regress half."""

    @pytest.mark.parametrize(
        "event_id,home,away,hs,as_,blend_home,winner", SETTLED_SPECIMENS
    )
    async def test_closed_keeps_the_blend(
        self, event_id, home, away, hs, as_, blend_home, winner
    ):
        """`closed` scores are frozen mid-game and invert the winner (two of four
        sampled rows). The route must NOT resolve them."""
        body = await _get(
            _settled_event(event_id, home, away, hs, as_, blend_home, status="closed")
        )
        assert body["hero_probability_source"] == "blend"
        assert body["hero_probability"] == pytest.approx(blend_home, abs=1e-4)
        assert "hero_settled_result" not in body

    async def test_live_game_keeps_the_blend(self):
        event = _settled_event(1, "Celtics", "76ers", 88, 82, 0.65, status="live")
        body = await _get(event)
        assert body["hero_probability_source"] == "blend"
        assert body["hero_probability"] == pytest.approx(0.65, abs=1e-4)

    async def test_completed_without_completed_at_keeps_the_blend(self):
        event = _settled_event(1, "Celtics", "76ers", 88, 82, 0.65)
        event.completed_at = None
        body = await _get(event)
        assert body["hero_probability_source"] == "blend"

    async def test_completed_without_scores_keeps_the_blend(self):
        event = _settled_event(1, "Celtics", "76ers", None, None, 0.65)
        body = await _get(event)
        assert body["hero_probability_source"] == "blend"

    async def test_draw_is_explicit_not_a_stale_blend(self):
        event = _settled_event(1, "Watford", "Peterborough United", 2, 2, 0.6492)
        body = await _get(event)
        assert body["hero_probability_source"] == "settled"
        assert body["hero_settled_result"] == "draw"
        assert body["hero_probability"] == 0.5

    async def test_current_odds_still_carries_the_market_price(self):
        """The hero resolves; the MARKET's own number is untouched. Deliberate —
        'what the market thought' is real history and the chart still needs it."""
        event = _settled_event(*SETTLED_SPECIMENS[0][:6])
        body = await _get(event)
        assert body["hero_probability_source"] == "settled"
        assert body["current_odds"]["home_probability"] == pytest.approx(
            0.8199, abs=1e-4
        )
