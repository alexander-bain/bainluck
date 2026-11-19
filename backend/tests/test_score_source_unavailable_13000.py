"""#13000 (Decision 250-A): explicit ``score_source_unavailable`` boolean.

Distinguishes a live match with NO score source carrying it (e.g. ATP
Challenger / ITF tennis, or an unmapped niche league) from a covered match
whose score has not moved yet or a scheduled/finished match.
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from types import SimpleNamespace

import pytest

from app.routes.events import _format_event
from app.routes.league_futures import _format_game_brief
from app.routes.teams import _format_event_brief
from app.utils.score_source_availability import event_score_source_unavailable

NOW = datetime(2026, 6, 15, 20, 0, tzinfo=timezone.utc)


def _event(
    *,
    sport_key: str = "tennis_atp",
    status: str = "live",
    commence_time: datetime | None = None,
    home_score: int | None = None,
    away_score: int | None = None,
    score_source: str | None = None,
    score_observed_at: datetime | None = None,
    period: str | None = None,
    espn_id: str | None = None,
    home_team: str = "Olivieri",
    away_team: str = "Boyer",
):
    return SimpleNamespace(
        id=9001,
        external_id="ext-9001",
        sport=SimpleNamespace(key=sport_key, name=sport_key, group="Tennis"),
        sport_id=1,
        home_team_id=10,
        away_team_id=20,
        home_team_name=home_team,
        away_team_name=away_team,
        home_team=None,
        away_team=None,
        commence_time=commence_time or (NOW - timedelta(minutes=30)),
        completed_at=None,
        status=status,
        home_score=home_score,
        away_score=away_score,
        score_source=score_source,
        score_observed_at=score_observed_at,
        period=period,
        game_clock=None,
        espn_id=espn_id,
        espn_win_probability=None,
        espn_win_prob_updated_at=None,
        win_probability_sources={
            "kalshi": {
                "value": 0.62,
                "updated_at": NOW.isoformat(),
            }
        },
        opening_home_probability=0.55,
        opening_away_probability=0.45,
        opening_draw_probability=None,
        opening_home_spread=None,
        opening_over_under=None,
        opening_favorite=None,
        opening_odds_recorded_at=NOW - timedelta(hours=2),
        closing_home_probability=None,
        espn_win_prob_home=None,
        event_tags=[],
        broadcast_info=None,
        venue_name=None,
        llm_importance="regular",
        llm_gender=None,
        llm_level=None,
        llm_league=None,
        statpal_end_time=None,
        raw_ei=60.0,
        ei_metadata=None,
        box_score_data=None,
        ei_score=None,
        ei_components=None,
        odds_snapshots=[],
    )


class TestEventScoreSourceUnavailablePredicate:
    def test_live_unanchored_challenger_tennis_is_true(self):
        ev = _event(sport_key="tennis_atp", status="live", espn_id=None)
        assert event_score_source_unavailable(ev) is True

    def test_live_wta_unanchored_itf_tennis_is_true(self):
        ev = _event(sport_key="tennis_wta", status="live", espn_id=None)
        assert event_score_source_unavailable(ev) is True

    def test_live_espn_anchored_tennis_even_before_first_point_is_false(self):
        ev = _event(sport_key="tennis_atp", status="live", espn_id="401999123")
        assert event_score_source_unavailable(ev) is False

    @pytest.mark.parametrize(
        "overrides",
        [
            {"home_score": 1, "away_score": 0},
            {"home_score": 0, "away_score": 0},
            {"score_source": "espn", "score_observed_at": NOW},
            {"score_observed_at": NOW},
            {"period": "Set 1"},
        ],
    )
    def test_live_tennis_with_any_score_or_observation_is_false(self, overrides):
        ev = _event(sport_key="tennis_atp", status="live", **overrides)
        assert event_score_source_unavailable(ev) is False

    def test_live_tennis_with_payload_linescore_is_false(self):
        ev = _event(sport_key="tennis_atp", status="live", espn_id=None)
        payload = {"linescore": {"sets": [[6, 4]]}}
        assert event_score_source_unavailable(ev, payload=payload) is False

    @pytest.mark.parametrize("status", ["scheduled", "completed", "closed", "suspended", "final"])
    def test_non_live_challenger_tennis_is_always_false(self, status):
        ev = _event(sport_key="tennis_atp", status=status, espn_id=None)
        assert event_score_source_unavailable(ev, status=status) is False

    @pytest.mark.parametrize(
        "sport_key",
        [
            "basketball_nba",
            "basketball_ncaab",
            "icehockey_nhl",
            "americanfootball_nfl",
            "soccer_epl",
            "golf_pga",
            "mma_mixed_martial_arts",
        ],
    )
    def test_live_covered_leagues_are_false_even_without_espn_id(self, sport_key):
        ev = _event(sport_key=sport_key, status="live", espn_id=None)
        assert event_score_source_unavailable(ev) is False

    @pytest.mark.parametrize("sport_key", ["basketball_other", "icehockey_ahl"])
    def test_live_uncovered_niche_team_leagues_are_true_when_scoreless(self, sport_key):
        ev = _event(sport_key=sport_key, status="live", espn_id=None)
        assert event_score_source_unavailable(ev) is True
        scored = _event(sport_key=sport_key, status="live", home_score=2, away_score=1)
        assert event_score_source_unavailable(scored) is False


class TestRouteFormattersEmitScoreSourceUnavailable:
    def test_format_event_emits_true_for_live_scoreless_tennis_and_false_for_covered(self):
        past = datetime.now(timezone.utc) - timedelta(minutes=20)
        unanchored = _event(sport_key="tennis_atp", status="live", commence_time=past)
        covered = _event(
            sport_key="tennis_atp",
            status="live",
            commence_time=past,
            espn_id="401777",
        )
        nba = _event(sport_key="basketball_nba", status="live", commence_time=past)
        scheduled = _event(
            sport_key="tennis_atp",
            status="scheduled",
            commence_time=datetime.now(timezone.utc) + timedelta(hours=2),
        )

        assert _format_event(unanchored)["score_source_unavailable"] is True
        assert "score_source_unavailable" not in _format_event(covered)
        assert "score_source_unavailable" not in _format_event(nba)
        assert "score_source_unavailable" not in _format_event(scheduled)

    def test_league_futures_format_game_brief_emits_score_source_unavailable(self):
        past = datetime.now(timezone.utc) - timedelta(minutes=20)
        unanchored = _event(sport_key="tennis_atp", status="live", commence_time=past)
        covered = _event(
            sport_key="tennis_atp",
            status="live",
            commence_time=past,
            espn_id="401777",
        )
        assert _format_game_brief(unanchored, "tennis_atp")["score_source_unavailable"] is True
        assert "score_source_unavailable" not in _format_game_brief(covered, "tennis_atp")

    def test_teams_format_event_brief_emits_score_source_unavailable(self):
        past = datetime.now(timezone.utc) - timedelta(minutes=20)
        team = SimpleNamespace(id=10, name="Olivieri")
        unanchored = _event(sport_key="tennis_atp", status="live", commence_time=past)
        covered = _event(
            sport_key="tennis_atp",
            status="live",
            commence_time=past,
            espn_id="401777",
        )
        assert _format_event_brief(unanchored, team)["score_source_unavailable"] is True
        assert "score_source_unavailable" not in _format_event_brief(covered, team)

    @pytest.mark.asyncio
    async def test_feed_score_events_emits_score_source_unavailable(self, monkeypatch):
        from unittest.mock import AsyncMock, MagicMock
        from app.routes import feed as feed_route

        now = datetime.now(timezone.utc)
        past = now - timedelta(minutes=20)
        unanchored = _event(sport_key="tennis_atp", status="live", commence_time=past)
        unanchored.id = 9101
        unanchored.win_probability_sources = {
            "kalshi": 0.62,
            "betting": 0.62,
            "betting_book_count": 4,
        }
        covered = _event(
            sport_key="tennis_atp",
            status="live",
            commence_time=past,
            espn_id="401777",
        )
        covered.id = 9102
        covered.win_probability_sources = {
            "kalshi": 0.58,
            "betting": 0.58,
            "betting_book_count": 4,
        }

        class _FakeDb:
            async def execute(self, stmt, params=None, *a, **k):
                r = MagicMock()
                r.scalars.return_value.all.return_value = []
                r.all.return_value = []
                return r

        monkeypatch.setattr(
            feed_route, "_get_championship_probabilities", AsyncMock(return_value={})
        )
        monkeypatch.setattr(feed_route, "_attach_card_projected_pairs", AsyncMock())
        monkeypatch.setattr(feed_route, "_attach_pregame_projections", AsyncMock())
        monkeypatch.setenv("FEED_SHARED_BUILD_TTL_S_EVENTS_SCORED", "0")

        scored = await feed_route._score_events(
            _FakeDb(),
            now,
            None,
            feed_route.PersonalizationContext(),
            sports_mode=True,
            price_refresh_events=[unanchored, covered],
        )
        by_id = {item["data"]["id"]: item["data"] for item in scored}
        assert by_id[9101]["score_source_unavailable"] is True
        assert "score_source_unavailable" not in by_id[9102]
